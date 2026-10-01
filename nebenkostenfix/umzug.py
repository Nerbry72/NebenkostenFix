"""Umzugspaket: alles exportieren, auf jedem Rechner übernehmen (NK-164, E-13 → D-96).

Auf Rechner A (etwa Docker auf dem NAS) „Alles exportieren“, auf Rechner B
(etwa die Windows-App) „Daten übernehmen“ -- danach ist B derselbe Bestand:
Datenbank samt Konten und Passwörtern, Belege und PDFs, Vermieterdaten und
Logo, Lizenz. Das Paket ist eine Sicherung im Format ``.nkfix``
(``backup.py``); dieses Modul ist der Weg dorthin und zurück:

- **Exportieren:** ``GET /api/umzug/export`` (Klartext, direkt als Download),
  ``POST /api/umzug/export`` (mit Passphrase, oder in der Windows-App an den
  Ort aus dem Speichern-Dialog), ``flask umzug export``.
- **Hochladen in Stücken** (8 MB, fortsetzbar): Hunderte MB Belege passen
  weder durch ``MAX_UPLOAD_MB`` noch durch jeden Reverse Proxy. Die Stücke
  landen in ``<Datenordner>/umzug-arbeit/``.
- **Importordner** (Docker): Paket nach ``<Datenordner>/import/`` legen, in der
  Oberfläche auswählen -- ohne Hochladen.
- **Windows-App:** kein Hochladen. Der Datei-Dialog der Hülle gibt einen Pfad
  frei (wie die Ordnerwahl bei Sicherungen, F-76); nur freigegebene Pfade
  nimmt der Server an.
- **Übernehmen:** prüfen (``backup``: Format, Schemastand, ZIP-Sicherheit,
  Prüfsummen, ``integrity_check``), Ist-Stand sichern, tauschen, wandern
  (NK-165), Logo/Lizenz/Vermieterwerte anwenden, Übernahmebericht. Danach
  meldet sich jeder neu an: die Sitzung gehört zu einem Konto des alten
  Bestands, und der Sitzungsschlüssel reist nicht mit.

Vor der Einrichtung (noch kein Konto) sind Hochladen, Prüfen und Übernehmen
offen, damit eine frische Installation den alten Bestand übernehmen kann --
im Server-Betrieb nur mit dem Einmal-Code (sonst belegte ein Fremder die
Instanz mit eigenen Konten), in der Windows-App ohne (E-1).

Bewusst nicht im Paket (und im Bericht genannt): Sitzungsschlüssel,
Sicherungsziele und Datenordner-Wahl, Anmeldesperren, Protokolle, Einmal-Code.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import date, datetime
from pathlib import Path

from flask import Response, jsonify, request, session

from nebenkostenfix import backup
from nebenkostenfix import datenordner
from nebenkostenfix.backup import SicherungsFehler

ARBEIT = 'umzug-arbeit'
IMPORT = 'import'
STUECK = 8 * 1024 * 1024
HOECHSTENS_OFFEN = 3
ALTER_AUFRAEUMEN_S = 24 * 3600
BESTAETIGUNG = 'ERSETZEN'
KENNUNG = re.compile(r'^[0-9a-f]{32}$')
PAKETNAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _.()-]{0,150}\.(nkfix|tar\.gz|nkbak)$')

NICHT_IM_PAKET = [
    'Sitzungsschlüssel: Sie melden sich auf diesem Rechner einmal neu an.',
    'Sicherungsziele und die Wahl des Datenordners (Pfade des alten Rechners).',
    'Anmeldesperren, Protokolle und der Einmal-Code der Einrichtung.',
]

# Endpunkte, die vor der Einrichtung erreichbar sind (auth._require_login).
VOR_DER_EINRICHTUNG = frozenset({
    'umzug_hochladen_beginnen', 'umzug_hochladen_stand', 'umzug_hochladen_stueck',
    'umzug_pruefen', 'umzug_uebernehmen',
})

# In der Windows-App vom Datei-Dialog der Hülle freigegebene Pfade (F-76).
_freigegeben: set[str] = set()


class UmzugsFehler(Exception):
    """Übernahme oder Hochladen abgelehnt, mit einer Meldung für Menschen."""


# --- Orte ------------------------------------------------------------------------

def _ordner(app) -> Path:
    try:
        return datenordner.datenordner()
    except datenordner.DatenordnerFehler:
        return backup.datenbankpfad(app).parent


def arbeitsordner(app) -> Path:
    ordner = _ordner(app) / ARBEIT
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def importordner(app) -> Path:
    return _ordner(app) / IMPORT


def freigeben(pfad) -> str:
    """Die Hülle gibt einen Pfad aus ihrem Datei-Dialog frei."""
    echt = os.path.realpath(str(pfad))
    _freigegeben.add(echt)
    return echt


def ist_freigegeben(pfad) -> bool:
    return os.path.realpath(str(pfad)) in _freigegeben


def aufraeumen(app, alter_s: int = ALTER_AUFRAEUMEN_S) -> None:
    """Liegengebliebene Stücke und Exporte (Abbruch, geschlossener Tab)."""
    grenze = time.time() - alter_s
    for datei in arbeitsordner(app).iterdir():
        try:
            if datei.is_file() and datei.stat().st_mtime < grenze:
                datei.unlink()
        except OSError:
            continue  # unter Windows noch offen: beim nächsten Mal


# --- Exportieren -----------------------------------------------------------------

def paketname(heute: date | None = None) -> str:
    return f'NebenkostenFix-{(heute or date.today()).isoformat()}{backup.ENDUNG}'


def paket_erstellen(app, ziel: Path, passphrase: str | None = None) -> Path:
    """Schreibt das Paket genau nach ``ziel`` (Ordner muss existieren)."""
    ziel = Path(ziel)
    if ziel.exists():
        ziel.unlink()
    return backup.sicherung_erstellen(app, ziel.parent, name=ziel.name,
                                      passphrase=passphrase)


def _strom(archiv: Path, stueck: int = 1024 * 1024):
    try:
        with open(archiv, 'rb') as quelle:
            while True:
                daten = quelle.read(stueck)
                if not daten:
                    break
                yield daten
    finally:
        archiv.unlink(missing_ok=True)


# --- Hochladen in Stücken --------------------------------------------------------

def _teil(app, kennung: str) -> tuple[Path, Path]:
    if not KENNUNG.match(kennung or ''):
        raise UmzugsFehler('Unbekannter Upload.')
    ordner = arbeitsordner(app)
    return ordner / f'{kennung}.teil', ordner / f'{kennung}.json'


_letzter_stempel = 0
_stempel_sperre = threading.Lock()  # Waitress bedient Uploads parallel


def _stempel() -> int:
    """Streng steigend im Prozess, auch wo time_ns() grob tickt (Windows)."""
    global _letzter_stempel
    with _stempel_sperre:
        _letzter_stempel = max(time.time_ns(), _letzter_stempel + 1)
        return _letzter_stempel


def _begonnen(info: Path) -> int:
    """F-119: Reihenfolge aus dem Eintrag, nicht aus der groben Dateizeit."""
    try:
        return int(json.loads(info.read_text(encoding='utf-8'))['begonnen'])
    except (OSError, ValueError, KeyError, TypeError):
        return info.stat().st_mtime_ns  # Eintrag von vor F-119


def hochladen_beginnen(app, groesse: int, name: str) -> dict:
    if not isinstance(groesse, int) or groesse <= 0:
        raise UmzugsFehler('Die Datei ist leer.')
    if groesse > backup.zip_max_gesamt():
        raise UmzugsFehler(
            f'Das Paket ist größer als erlaubt ({backup.lesbare_groesse(backup.zip_max_gesamt())}, '
            'Einstellung UMZUG_MAX_GB).')
    aufraeumen(app)
    ordner = arbeitsordner(app)
    offen = sorted(ordner.glob('*.json'), key=_begonnen)
    for alt in offen[:max(0, len(offen) - HOECHSTENS_OFFEN + 1)]:
        alt.with_suffix('.teil').unlink(missing_ok=True)
        alt.unlink(missing_ok=True)
    frei = shutil.disk_usage(ordner).free
    # Paket + entpackter Inhalt + Sicherung des Ist-Stands: grob das Dreifache.
    if frei < groesse * 3:
        raise UmzugsFehler(
            f'Auf dem Datenträger ist zu wenig Platz: frei {backup.lesbare_groesse(frei)}, '
            f'nötig etwa {backup.lesbare_groesse(groesse * 3)}.')
    kennung = secrets.token_hex(16)
    teil, info = _teil(app, kennung)
    teil.write_bytes(b'')
    info.write_text(json.dumps({'groesse': groesse, 'name': str(name or '')[:200],
                                'begonnen': _stempel()}),
                    encoding='utf-8')
    stueck = min(STUECK, max(64 * 1024, (app.config.get('MAX_CONTENT_LENGTH') or STUECK)
                             - 64 * 1024))
    return {'id': kennung, 'stueck': stueck, 'empfangen': 0, 'groesse': groesse}


def hochladen_stand(app, kennung: str) -> dict:
    teil, info = _teil(app, kennung)
    if not info.is_file():
        raise UmzugsFehler('Dieser Upload ist abgelaufen. Bitte neu beginnen.')
    soll = json.loads(info.read_text(encoding='utf-8'))['groesse']
    return {'id': kennung, 'empfangen': teil.stat().st_size, 'groesse': soll}


def hochladen_stueck(app, kennung: str, ab: int, daten: bytes) -> dict:
    stand = hochladen_stand(app, kennung)
    if ab != stand['empfangen']:
        # Fortsetzen nach Abbruch: der Browser fragt den Stand und setzt dort an.
        raise UmzugsFehler(f'Stück an Stelle {ab} erwartet {stand["empfangen"]}.')
    if stand['empfangen'] + len(daten) > stand['groesse']:
        raise UmzugsFehler('Es kommen mehr Daten als angekündigt.')
    teil, _ = _teil(app, kennung)
    with open(teil, 'ab') as senke:
        senke.write(daten)
    stand['empfangen'] += len(daten)
    return stand


def hochgeladenes_paket(app, kennung: str) -> Path:
    stand = hochladen_stand(app, kennung)
    if stand['empfangen'] != stand['groesse']:
        raise UmzugsFehler(
            f'Der Upload ist unvollständig ({stand["empfangen"]} von {stand["groesse"]} Bytes).')
    teil, _ = _teil(app, kennung)
    return teil


def hochladen_verwerfen(app, kennung: str) -> None:
    teil, info = _teil(app, kennung)
    teil.unlink(missing_ok=True)
    info.unlink(missing_ok=True)


# --- Pakete finden und prüfen ----------------------------------------------------

def pakete_im_importordner(app) -> list[dict]:
    ordner = importordner(app)
    if not ordner.is_dir():
        return []
    stempel = backup.bekannte_stempel(app)
    pakete = []
    for datei in sorted(ordner.iterdir(), key=lambda p: p.name.lower()):
        if not (datei.is_file() and PAKETNAME.match(datei.name)):
            continue
        try:
            pakete.append(_kurzbericht(datei, stempel))
        except SicherungsFehler:
            continue
    return pakete


def _kurzbericht(archiv: Path, stempel: set) -> dict:
    manifest = backup.manifest_lesen(archiv)
    return {
        'name': archiv.name,
        'groesse': backup.lesbare_groesse(archiv.stat().st_size),
        'erstellt_am': manifest.get('erstellt_am'),
        'belege': (manifest.get('zusammenfassung') or {}).get('belege_anzahl'),
        'verschluesselt': bool(manifest.get('verschluesselt')),
        'einspielbar': manifest.get('alembic_revision') in stempel,
        'quelle': manifest.get('quelle'),
        'zaehlwerte': manifest.get('zaehlwerte'),
    }


def paket_aufloesen(app, daten: dict) -> tuple[Path, str | None]:
    """Aus der Anfrage das Paket: hochgeladen, Importordner oder freigegebener Pfad.

    Gibt (Pfad, Upload-Kennung oder None) zurück.
    """
    if daten.get('hochgeladen'):
        kennung = str(daten['hochgeladen'])
        return hochgeladenes_paket(app, kennung), kennung
    if daten.get('importordner'):
        name = str(daten['importordner'])
        if not PAKETNAME.match(name):
            raise UmzugsFehler('Bitte ein Paket aus der Liste wählen.')
        pfad = importordner(app) / name
        if pfad.is_symlink() or not pfad.is_file():
            raise UmzugsFehler(f'Das Paket {name} liegt nicht (mehr) im Importordner.')
        return pfad, None
    if daten.get('pfad'):
        if not (app.config.get('DESKTOP') and ist_freigegeben(daten['pfad'])):
            raise UmzugsFehler('Dieser Pfad ist nicht freigegeben. Bitte die Datei '
                               'über „Paket auswählen“ wählen.')
        pfad = Path(os.path.realpath(str(daten['pfad'])))
        if not pfad.is_file():
            raise UmzugsFehler('Die gewählte Datei gibt es nicht mehr.')
        return pfad, None
    raise UmzugsFehler('Bitte ein Paket auswählen.')


def pruefen(app, archiv: Path) -> dict:
    """Vorschau vor dem Übernehmen: was steckt drin, passt es zu dieser Fassung?"""
    bericht = _kurzbericht(archiv, backup.bekannte_stempel(app))
    if not bericht['einspielbar']:
        bericht['hinweis'] = ('Das Paket stammt aus einer neueren Version. Bitte zuerst '
                              'NebenkostenFix aktualisieren.')
    return bericht


# --- Übernehmen ------------------------------------------------------------------

def uebernehmen(app, archiv: Path, passphrase: str | None = None) -> dict:
    """Ersetzt den Bestand durch das Paket und berichtet, was angekommen ist."""
    try:
        sicherungen = datenordner.sicherungsordner()
    except datenordner.DatenordnerFehler:
        sicherungen = backup.datenbankpfad(app).parent
    bericht = backup.sicherung_einspielen(
        app, archiv, sicherheitskopie_nach=sicherungen, passphrase=passphrase)
    nachher = backup.zaehlwerte(backup.datenbankpfad(app))
    vorher = bericht.get('zaehlwerte') or {}
    abweichend = {t: {'paket': n, 'hier': nachher.get(t)}
                  for t, n in vorher.items() if nachher.get(t) != n}
    return {
        'sicherheitskopie': bericht['sicherheitskopie'],
        'schemastand_paket': bericht['alembic_revision'],
        'schemastand_nachher': bericht['schemastand_nachher'],
        'quelle': bericht.get('quelle'),
        'belege': bericht['belege'],
        'zeilen': sum(nachher.values()),
        'tabellen': nachher,
        # Nachgesäte Kostenarten oder neue Tabellen nach einer Wanderung
        # sind erwartbar; der Bericht nennt sie, statt sie zu verschweigen.
        'abweichend': abweichend,
        'fehlende_verweise': bericht['fehlende_verweise'],
        'zusatz': bericht.get('zusatz') or {},
        'nicht_im_paket': NICHT_IM_PAKET,
    }


def bestandsbericht(app) -> dict:
    """Was nach einer Übernahme da ist -- für die Proben der CI (Quelle und
    gebaute Windows-App, ``scripts/umzug_kreuzprobe.py``, ``paketprobe.py``).
    Nur Zahlen, Prüfsummen und Kontennamen, keine Mieterdaten."""
    from nebenkostenfix import einstellungen
    from nebenkostenfix import vermieter_logo
    from nebenkostenfix.models import User, Vermieterdaten, db

    belege = backup.belegwurzel()
    dateien = {}
    if belege.is_dir():
        for datei in sorted(p for p in belege.rglob('*') if p.is_file()):
            dateien[datei.relative_to(belege).as_posix()] = backup.pruefsumme(datei)
    with app.app_context():
        zeile = Vermieterdaten.einziger()
        konten = sorted(u.username for u in User.query.all())
        db.session.remove()
    ordner = _ordner(app)
    return {
        'zeilen': backup.zaehlwerte(backup.datenbankpfad(app)),
        'belege': dateien,
        'fehlend': len(backup.dateiverweise_pruefen(app)),
        'vermieter': {'name': zeile.name if zeile else None,
                      'iban': zeile.iban if zeile else None},
        'logo': vermieter_logo.pfad(ordner) is not None,
        'einstellungen': {k: einstellungen.lesen(ordner)[k]
                          for k in einstellungen.UEBERTRAGBAR},
        'konten': konten,
    }


# --- Routen und Kommandozeile ----------------------------------------------------

def init_umzug(app):
    import click
    from flask.cli import AppGroup

    from nebenkostenfix import auth
    from nebenkostenfix.models import User, db

    def _fehler(text, status=400):
        return jsonify({'error': text}), status

    def _vor_der_einrichtung() -> bool:
        return db.session.query(User.id).first() is None

    def _zugang():
        """None, wenn die Anfrage darf; sonst die Ablehnung."""
        if auth.current_user() is not None:
            return None
        if not _vor_der_einrichtung():
            return _fehler('Bitte melden Sie sich an.', 401)
        if app.config.get('DESKTOP'):
            return None
        code = request.headers.get('X-Einmal-Code') or \
            (request.get_json(silent=True) or {}).get('code')
        if not code:
            # Ohne Code wie jede gesperrte Route; ein Fehlversuch zählt erst,
            # wenn jemand einen Code probiert.
            return _fehler('Bitte melden Sie sich an oder geben Sie den Einmal-Code ein.', 401)
        if not auth._einmal_code_pruefen(app, code):
            return _fehler('Der Einmal-Code stimmt nicht. Er steht in der Datei '
                           'ERSTEINRICHTUNG-CODE.txt im Datenordner und im Protokoll '
                           '(Docker: docker compose logs web).', 403)
        return None

    @app.route('/api/umzug/export', methods=['GET', 'POST'])
    def umzug_export():
        """Alles exportieren: das Paket als Download, verschlüsselt auf Wunsch."""
        daten = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
        passphrase = daten.get('passphrase') or None
        name = paketname()
        try:
            if daten.get('pfad'):
                if not (app.config.get('DESKTOP') and ist_freigegeben(daten['pfad'])):
                    return _fehler('Dieser Pfad ist nicht freigegeben.')
                ziel = Path(os.path.realpath(str(daten['pfad'])))
                archiv = paket_erstellen(app, ziel, passphrase)
                return jsonify({'pfad': str(archiv),
                                'groesse': backup.lesbare_groesse(archiv.stat().st_size)})
            aufraeumen(app)
            ziel = arbeitsordner(app) / f'export-{secrets.token_hex(8)}{backup.ENDUNG}'
            archiv = paket_erstellen(app, ziel, passphrase)
        except SicherungsFehler as fehler:
            return _fehler(str(fehler))

        # Ein Generator statt send_file: send_file reicht die Datei direkt durch,
        # dann läuft kein call_on_close, und das Paket bliebe liegen. Der
        # Generator schließt die Datei, bevor er sie löscht (Windows).
        return Response(_strom(archiv), mimetype='application/zip', headers={
            'Content-Disposition': f'attachment; filename="{name}"',
            'Content-Length': str(archiv.stat().st_size),
            'Cache-Control': 'no-store',
        })

    @app.route('/api/umzug/hochladen', methods=['POST'])
    def umzug_hochladen_beginnen():
        abgelehnt = _zugang()
        if abgelehnt:
            return abgelehnt
        daten = request.get_json(silent=True) or {}
        try:
            return jsonify(hochladen_beginnen(app, daten.get('groesse'), daten.get('name'))), 201
        except UmzugsFehler as fehler:
            return _fehler(str(fehler))

    @app.route('/api/umzug/hochladen/<kennung>', methods=['GET'])
    def umzug_hochladen_stand(kennung):
        abgelehnt = _zugang()
        if abgelehnt:
            return abgelehnt
        try:
            return jsonify(hochladen_stand(app, kennung))
        except UmzugsFehler as fehler:
            return _fehler(str(fehler), 404)

    @app.route('/api/umzug/hochladen/<kennung>', methods=['PUT'])
    def umzug_hochladen_stueck(kennung):
        abgelehnt = _zugang()
        if abgelehnt:
            return abgelehnt
        try:
            ab = int(request.args.get('ab', '-1'))
            return jsonify(hochladen_stueck(app, kennung, ab, request.get_data(cache=False)))
        except ValueError:
            return _fehler('Stelle fehlt.')
        except UmzugsFehler as fehler:
            return _fehler(str(fehler), 409)

    @app.route('/api/umzug/importordner', methods=['GET'])
    def umzug_importordner():
        return jsonify({'ordner': str(importordner(app)),
                        'pakete': pakete_im_importordner(app)})

    @app.route('/api/umzug/pruefen', methods=['POST'])
    def umzug_pruefen():
        abgelehnt = _zugang()
        if abgelehnt:
            return abgelehnt
        try:
            archiv, _ = paket_aufloesen(app, request.get_json(silent=True) or {})
            return jsonify(pruefen(app, archiv))
        except (UmzugsFehler, SicherungsFehler) as fehler:
            return _fehler(str(fehler))

    @app.route('/api/umzug/uebernehmen', methods=['POST'])
    def umzug_uebernehmen():
        """Ersetzt alles. Mit bestehendem Konto nur nach ausgeschriebener Bestätigung."""
        abgelehnt = _zugang()
        if abgelehnt:
            return abgelehnt
        daten = request.get_json(silent=True) or {}
        frisch = _vor_der_einrichtung()
        if not frisch and (daten.get('bestaetigung') or '').strip() != BESTAETIGUNG:
            return _fehler(f'Bitte bestätigen Sie mit „{BESTAETIGUNG}“: die Übernahme '
                           'ersetzt alle Daten dieser Installation.')
        try:
            archiv, kennung = paket_aufloesen(app, daten)
            bericht = uebernehmen(app, archiv, daten.get('passphrase') or None)
        except (UmzugsFehler, SicherungsFehler) as fehler:
            return _fehler(str(fehler))
        if kennung:
            hochladen_verwerfen(app, kennung)
        if frisch:
            auth._einmal_code_verfallen()
        # Die Sitzung zeigt auf ein Konto des alten Bestands: neu anmelden.
        session.clear()
        app.logger.info('Umzugspaket übernommen: %s Zeilen, %s Belege.',
                        bericht['zeilen'], bericht['belege'])
        bericht['anmelden'] = True
        return jsonify(bericht)

    umzug_cli = AppGroup('umzug', help='Umzugspaket exportieren und übernehmen (NK-164).')

    @umzug_cli.command('export')
    @click.option('--ziel', default=None, help='Ordner für das Paket. Standard: backups/.')
    @click.option('--verschluesseln', is_flag=True, help='Mit Passphrase verschlüsseln.')
    def cli_export(ziel, verschluesseln):
        """Alles in ein .nkfix-Paket schreiben."""
        ordner = Path(ziel or backup.standardziel(app))
        ordner.mkdir(parents=True, exist_ok=True)
        passphrase = None
        if verschluesseln:
            passphrase = click.prompt('Passphrase', hide_input=True, confirmation_prompt=True)
        pfad = backup._freier_name(ordner, 'NebenkostenFix', datetime.now(), backup.ENDUNG)
        try:
            archiv = paket_erstellen(app, pfad, passphrase)
        except SicherungsFehler as fehler:
            raise click.ClickException(str(fehler))
        click.echo(f'Paket: {archiv}')
        click.echo(f'Größe: {backup.lesbare_groesse(archiv.stat().st_size)}')

    @umzug_cli.command('import')
    @click.argument('paket')
    @click.option('--ja', is_flag=True, help='Ohne Rückfrage übernehmen.')
    @click.option('--passphrase', default=None, hide_input=True)
    def cli_import(paket, ja, passphrase):
        """Ein .nkfix-Paket übernehmen (ersetzt alles, sichert vorher)."""
        if not ja:
            click.confirm('Die Übernahme ersetzt alle Daten dieser Installation. Der '
                          'Ist-Stand wird vorher gesichert. Weiter?', abort=True)
        from nebenkostenfix import verschluesselung
        if verschluesselung.ist_verschluesselt(paket) and not passphrase:
            passphrase = click.prompt('Passphrase', hide_input=True)
        try:
            bericht = uebernehmen(app, Path(paket), passphrase)
        except SicherungsFehler as fehler:
            raise click.ClickException(str(fehler))
        click.echo(json.dumps(bericht, ensure_ascii=False, indent=2))

    app.cli.add_command(umzug_cli)
