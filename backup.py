"""Sichern und Zurueckholen des Abrechnungsordners (NK-025).

Ein Vermieter hat genau eine Kopie seiner Abrechnung: die Instanz. Geht die
Datei kaputt oder faehrt der Rechner nicht mehr hoch, ist die Arbeit von zwei
Jahren weg. Deshalb ein Archiv, das beides zusammen haelt: die Datenbank und
die Belege. Getrennt gesichert nuetzen sie wenig, weil die Datenbank die Belege
ueber relative Pfade adressiert.

Aufbau eines Archivs (tar.gz):

    manifest.json
    datenbank/nebenkosten.db
    belege/<Immobilie>/...

Das Manifest haelt den Alembic-Stempel fest. Ein Archiv, dessen Stempel die
laufende Fassung nicht kennt, stammt aus einer neueren Version: es wird
abgelehnt statt halb eingespielt. Der umgekehrte Fall ist harmlos, ein
aelteres Archiv wandert beim naechsten Start auf den aktuellen Stand.

Sichern -- sicherung_erstellen() (NK-033)
-----------------------------------------

  Zielordner anlegen, Datenbank suchen
      |  keine Datenbank -> SicherungsFehler, nichts geschrieben
      v
  temporaerer Arbeitsordner
      |
      +-- _datenbank_ziehen(): ueber sqlite3.Connection.backup(), nicht
      |   ueber shutil.copy. Ein blindes Kopieren erwischt die Datei mitten
      |   im Schreiben; das faellt erst beim Einspielen auf, also genau
      |   dann, wenn man sie braucht.
      |
      +-- _dateien_unter(Belegwurzel): jede Belegdatei mit Pruefsumme,
      |   Unlesbares wandert nach 'uebersprungen' statt den Lauf abzubrechen
      |
      +-- manifest.json: Format, Zeitpunkt, Alembic-Stempel, Groesse und
          sha256 der Datenbank, dasselbe je Beleg, Zusammenfassung
      |
      v
  tar.gz schreiben, aber unter <name>.teil
      |
      v
  os.replace(<name>.teil, <name>)
  -- erst jetzt heisst die Datei wie eine Sicherung. Nach einem Abbruch liegt
     sonst eine halbe Datei da, die aussieht wie eine vollstaendige.
      |
      v
  Rueckgabe: Pfad des Archivs

Einspielen -- sicherung_einspielen()
------------------------------------

Die Reihenfolge ist der ganze Punkt: erst pruefen, dann sichern, dann
austauschen. Wer zuerst austauscht und dann merkt, dass das Archiv kaputt war,
hat beide Staende verloren.

  Archiv
      |
      v
  1. manifest_lesen()      nur das Manifest, ohne auszupacken
      |
      v
  2. _stempel_pruefen()    Manifestformat bekannt? Alembic-Stempel vorhanden
      |                    und dieser Fassung bekannt?
      |                    nein -> SicherungsFehler, nichts veraendert
      v
  3. _entpacken()          in einen temporaeren Ordner, Pfade mit '..' oder
      |                    fuehrendem Schraegstrich werden abgelehnt
      v
  4. _inhalt_pruefen()     jede Datei gegen ihre Pruefsumme im Manifest,
      |                    dazu: nichts fehlt und nichts ist zuviel
      |                    nein -> SicherungsFehler, nichts veraendert
      v
  5. Sicherung des Ist-Zustands (praefix 'sicherung-vor-einspielen')
      |   -- nur wenn ueberhaupt eine Datenbank da ist, die verloren gehen
      |      koennte
      v
  6. _verbindungen_schliessen()   offene SQLite-Griffe loslassen, sonst
      |                           zeigen sie gleich auf die alte Datei
      v
  7. Datenbank austauschen: erst <db>.neu schreiben, dann os.replace
      v
  8. _belege_ersetzen(): der Inhalt des Belegordners wird ersetzt, nicht der
      |   Ordner selbst -- im Container ist er ein Einhaengepunkt
      v
  9. _verbindungen_schliessen() noch einmal, dann
     dateiverweise_pruefen(): jede Pfadspalte aus PFADSPALTEN gegen die
     tatsaechlich vorhandenen Dateien
      |
      v
  Rueckgabe: Archiv, Pfad der Sicherheitskopie, Alembic-Stempel, Zahl der
             Belege, Liste fehlender Dateiverweise

Schritt 9 ist der Grund, warum PFADSPALTEN vollstaendig sein muss: steht dort
eine Spalte nicht, meldet die Pruefung "alles gut", waehrend die Oberflaeche
spaeter 404 liefert.

Alle Wege gehen ueber die Kommandozeile (`flask backup ...`). Die Datenbank
wird waehrend des Einspielens ausgetauscht, das vertraegt sich nicht mit einer
laufenden Anwendung: erst anhalten, dann einspielen.

Ein Format fuer Sicherung und Umzug (NK-164, D-96)
--------------------------------------------------

Seit 0.9 schreibt ``sicherung_erstellen`` ein ``.nkfix``: ein ZIP (im
Windows-Explorer zu oeffnen, ZIP64 fuer grosse Bestaende) mit Manifest
Format 2. Jede Sicherung ist damit zugleich ein Umzugspaket (``umzug.py``)::

    manifest.json               Format 2: dazu Quelle (Plattform, Betrieb,
                                Version), Zaehlwerte je Tabelle, Zusatzdateien
    datenbank/nebenkosten.db    ueber die Sicherungsschnittstelle, komprimiert
    belege/...                  neutrale Namen (NK-131), gespeichert, nicht
                                noch einmal komprimiert
    einstellungen.json          was nicht in der Datenbank steht: die
                                wirksamen Vermieterwerte (auch aus der Umgebung),
                                bestaetigter Haftungshinweis und Update-Einstellung
                                (NK-174, NK-175)
    einstellungen/vermieter-logo.<png|jpg>   falls hinterlegt (NK-155)

Pakete bis 0.9 koennen noch ``lizenz.nklizenz`` tragen (NK-080); die Datei
wird seit NK-176 beim Einspielen uebergangen.

Verschluesselt liegt das ganze ZIP im ``NKVERS1``-Umschlag, die Endung
bleibt ``.nkfix`` (der Kopf verraet die Verschluesselung). Alte
``.tar.gz``/``.nkbak`` (Format 1) bleiben lesbar; erkannt wird am Inhalt,
nicht an der Endung. Beim Auspacken eines ZIP gilt: kein absoluter Pfad,
kein ``..``, kein Rueckstrich, keine Verknuepfung, kein Name doppelt, jede
Groesse wie im Manifest, Grenzen fuer Dateizahl, Gesamtgroesse und
Kompressionsverhaeltnis, genug freier Platz -- geprueft, bevor ein Byte
geschrieben wird.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import jsonify, request

import festplatte
import verschluesselung
from verschluesselung import VerschluesselungsFehler

# Kind von ``nebenkosten`` wie handlers/nas_handler.py: dieselben Ausgaenge,
# dieselbe Stufe, aber am Namen der Zeile ist ablesbar, woher sie kommt.
protokoll = logging.getLogger('nebenkosten.backup')

MANIFEST_NAME = 'manifest.json'
# Format 1: tar.gz bis 0.8; Format 2: ZIP (.nkfix) mit Zusatzdateien (NK-164).
MANIFEST_FORMAT = 2
BEKANNTE_FORMATE = frozenset({1, 2})
DB_IM_ARCHIV = 'datenbank/nebenkosten.db'
BELEGE_IM_ARCHIV = 'belege'
ENDUNG = '.nkfix'
EINSTELLUNGEN_IM_ARCHIV = 'einstellungen.json'
LOGO_IM_ARCHIV = 'einstellungen'
# Kennung im Manifest und im Kopf verschluesselter Dateien. Bleibt beim alten
# Namen: sie ist ein Formatmerkmal, keine Marke, und alte Sicherungen tragen sie.
ANWENDUNG = 'nebenkostenabrechnung'

# ZIP-Grenzen (NK-164). Eine Datei im Paket entpackt nie groesser als im
# Manifest; darueber hinaus schuetzen diese Grenzen vor Paketen, die den
# Datenordner fluten sollen.
ZIP_MAX_DATEIEN = 200_000
ZIP_MAX_VERHAELTNIS = 500           # entpackt / gepackt, fuer Dateien ab ...
ZIP_VERHAELTNIS_AB = 50 * 1024 * 1024
ZIP_PLATZ_RESERVE = 1.1             # freier Platz >= 110 % des Entpackten


def zip_max_gesamt() -> int:
    """Hoechstens so viele Bytes entpackt (UMZUG_MAX_GB, Standard 50)."""
    try:
        gb = float(os.environ.get('UMZUG_MAX_GB') or 50)
    except ValueError:
        gb = 50
    if gb <= 0:
        gb = 50
    return int(gb * 1024 ** 3)

# Spalten, die auf eine Datei unter NAS_MOUNT_PATH zeigen. Steht hier falsch
# oder unvollstaendig, meldet die Pruefung nach dem Einspielen "alles gut",
# waehrend die Oberflaeche 404 liefert.
PFADSPALTEN = (
    ('tenants', 'contract_path'),
    ('cost_invoices', 'document_path'),
    ('invoice_documents', 'document_path'),
    ('meter_readings', 'document_path'),
    ('tenant_billing_reports', 'document_path'),
    ('tenant_billing_reports', 'document_path_detailed'),
)


class SicherungsFehler(Exception):
    """Sichern oder Einspielen abgebrochen, mit einer Meldung fuer Menschen."""


# --- Pfade und Pruefsummen -------------------------------------------------


def datenbankpfad(app) -> Path:
    """Die SQLite-Datei hinter der Anwendung."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        raise SicherungsFehler(
            f"Sichern kann nur SQLite, die Anwendung laeuft auf: {uri.split(':')[0]}"
        )
    # sqlite:////abs/pfad hat vier Schraegstriche, sqlite:///relativ nur drei.
    pfad = uri.split('sqlite:///', 1)[1]
    return Path(pfad).resolve()


def belegwurzel() -> Path:
    """Der Belegordner im Datenordner (NK-132)."""
    import datenordner

    return datenordner.belegordner().resolve()


def pruefsumme(pfad: Path) -> str:
    """sha256 in Haeppchen. Ein Beleg kann ein 40-MB-Scan sein."""
    hasher = hashlib.sha256()
    with open(pfad, 'rb') as fh:
        for brocken in iter(lambda: fh.read(1024 * 1024), b''):
            hasher.update(brocken)
    return hasher.hexdigest()


def _stempel(app) -> str | None:
    """Alembic-Kennung der laufenden Datenbank."""
    from alembic.migration import MigrationContext

    from models import db

    with app.app_context():
        with db.engine.connect() as verbindung:
            return MigrationContext.configure(verbindung).get_current_revision()


def bekannte_stempel(app) -> set:
    """Alle Revisionen, die diese Fassung der Anwendung kennt."""
    from alembic.script import ScriptDirectory

    with app.app_context():
        konfiguration = app.extensions['migrate'].migrate.get_config()
        skripte = ScriptDirectory.from_config(konfiguration)
        return {revision.revision for revision in skripte.walk_revisions()}


def _dateien_unter(wurzel: Path):
    """Alle Dateien unter wurzel, relativ, sortiert. Symlinks bleiben draussen.

    Ein Symlink im Archiv zeigt beim Einspielen irgendwohin, moeglicherweise
    aus dem Belegordner heraus. Er wird uebersprungen und im Manifest vermerkt,
    nicht stillschweigend mitgenommen.
    """
    dateien = []
    uebersprungen = []
    for verzeichnis, unterverzeichnisse, namen in os.walk(wurzel, followlinks=False):
        unterverzeichnisse[:] = [
            u for u in unterverzeichnisse
            if not os.path.islink(os.path.join(verzeichnis, u))
        ]
        for name in namen:
            voll = Path(verzeichnis) / name
            relativ = voll.relative_to(wurzel).as_posix()
            if voll.is_symlink() or not voll.is_file():
                uebersprungen.append(relativ)
            else:
                dateien.append(relativ)
    return sorted(dateien), sorted(uebersprungen)


# --- Sichern ---------------------------------------------------------------


def _freier_name(ordner: Path, praefix: str, zeit: datetime,
                 endung: str = '.tar.gz') -> Path:
    """Ein Archivname, den es noch nicht gibt.

    Der Zeitstempel geht nur bis zur Sekunde. Zwei Sicherungen in derselben
    Sekunde sind kein erfundener Fall: das Einspielen legt selbst eine an, und
    wer zweimal hintereinander einspielt, ist genau dort. Ohne den Zusatz
    braeche der zweite Vorgang mit "gibt es schon" ab, obwohl mit den Daten
    alles in Ordnung ist.
    """
    rumpf = f"{praefix}-{zeit.strftime('%Y%m%d-%H%M%S')}"
    kandidat = ordner / f"{rumpf}{endung}"
    zaehler = 2
    while kandidat.exists():
        kandidat = ordner / f"{rumpf}-{zaehler}{endung}"
        zaehler += 1
    return kandidat


def sicherung_erstellen(
    app, zielverzeichnis, name: str | None = None, praefix: str = 'sicherung',
    passphrase: str | None = None, art: str = 'nkfix',
) -> Path:
    """Schreibt ein Archiv mit Datenbank, Belegen und Manifest.

    Die Datenbank wird nicht kopiert, sondern ueber die Sicherungsschnittstelle
    von SQLite gezogen. Ein blindes shutil.copy erwischt eine Datei mitten im
    Schreiben und ergibt ein Archiv, das sich erst beim Einspielen als kaputt
    herausstellt.

    Ohne name wird einer aus praefix und Zeitstempel gebaut, und zwar einer,
    der frei ist. Mit name gilt genau dieser Name: wer ihn angibt, meint ihn,
    und ein stilles Ausweichen auf einen anderen waere die schlechtere Antwort
    als ein Abbruch.

    ``art='nkfix'`` (Vorgabe, NK-164) schreibt das ZIP mit Manifest Format 2
    samt Zusatzdateien; ``art='tar'`` das alte tar.gz (Format 1) -- nur noch
    fuer Tests, die das Lesen alter Sicherungen pruefen.
    """
    if art not in ('nkfix', 'tar'):
        raise ValueError(f'Unbekannte Archivart {art!r}')
    ziel = Path(zielverzeichnis).resolve()
    ziel.mkdir(parents=True, exist_ok=True)

    quelle = datenbankpfad(app)
    if not quelle.exists():
        raise SicherungsFehler(f"Keine Datenbank unter {quelle}.")

    belege = belegwurzel()
    zeit = datetime.now().astimezone()
    if passphrase is not None:
        # NK-130 (D-86): die Passphrase wird vor jeder Arbeit geprueft, nicht
        # erst nach Minuten des Packens.
        try:
            verschluesselung.passphrase_pruefen(passphrase)
        except VerschluesselungsFehler as fehler:
            raise SicherungsFehler(str(fehler)) from fehler
    if art == 'nkfix':
        endung = ENDUNG
    else:
        endung = VERSCHLUESSELT_ENDUNG if passphrase is not None else '.tar.gz'
    archiv = ziel / name if name else _freier_name(ziel, praefix, zeit, endung)
    if archiv.exists():
        raise SicherungsFehler(f"{archiv} gibt es schon.")

    with tempfile.TemporaryDirectory(prefix='nk-sicherung-') as arbeit:
        kopie = Path(arbeit) / 'nebenkosten.db'
        _datenbank_ziehen(quelle, kopie)

        belegdateien, uebersprungen = ([], [])
        if belege.is_dir():
            belegdateien, uebersprungen = _dateien_unter(belege)

        manifest = {
            'format': MANIFEST_FORMAT if art == 'nkfix' else 1,
            'anwendung': ANWENDUNG,
            'erstellt_am': zeit.isoformat(timespec='seconds'),
            'alembic_revision': _stempel(app),
            'datenbank': {
                'pfad': DB_IM_ARCHIV,
                'groesse': kopie.stat().st_size,
                'sha256': pruefsumme(kopie),
            },
            'belege': [
                {
                    'pfad': p,
                    'groesse': (belege / p).stat().st_size,
                    'sha256': pruefsumme(belege / p),
                }
                for p in belegdateien
            ],
            'uebersprungen': uebersprungen,
        }
        zusatz = []
        if art == 'nkfix':
            zusatz = _zusatzdateien(app, Path(arbeit))
            manifest['produkt'] = 'NebenkostenFix'
            manifest['quelle'] = _quelle(app)
            manifest['zaehlwerte'] = zaehlwerte(kopie)
            manifest['zusatz'] = [
                {'pfad': name_im_archiv, 'groesse': datei.stat().st_size,
                 'sha256': pruefsumme(datei)}
                for name_im_archiv, datei in zusatz
            ]
        manifest['zusammenfassung'] = {
            'belege_anzahl': len(manifest['belege']),
            'belege_groesse': sum(b['groesse'] for b in manifest['belege']),
        }

        manifestdatei = Path(arbeit) / MANIFEST_NAME
        manifestdatei.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8'
        )

        if passphrase is not None:
            # Klartext nur im Arbeitsordner, der mit dem with-Block geht.
            vorlaeufig = Path(arbeit) / ('paket.zip' if art == 'nkfix' else 'sicherung.tar.gz')
        else:
            vorlaeufig = archiv.with_suffix(archiv.suffix + '.teil')
        if art == 'nkfix':
            _zip_schreiben(vorlaeufig, manifestdatei, kopie, belege, belegdateien, zusatz)
        else:
            with tarfile.open(vorlaeufig, 'w:gz') as tar:
                tar.add(manifestdatei, arcname=MANIFEST_NAME)
                tar.add(kopie, arcname=DB_IM_ARCHIV)
                for p in belegdateien:
                    _als_datei(tar, belege / p, f"{BELEGE_IM_ARCHIV}/{p}")
        if passphrase is not None:
            verschluesselung.verschluesseln(vorlaeufig, archiv, passphrase, {
                'format': manifest['format'],
                'anwendung': ANWENDUNG,
                'behaelter': 'zip' if art == 'nkfix' else 'tar.gz',
                'erstellt_am': manifest['erstellt_am'],
                'alembic_revision': manifest['alembic_revision'],
                'belege_anzahl': manifest['zusammenfassung']['belege_anzahl'],
                'belege_groesse': manifest['zusammenfassung']['belege_groesse'],
            })
        else:
            # Erst umbenennen, wenn das Archiv vollstaendig ist. Sonst liegt
            # nach einem Abbruch eine halbe Datei da, die aussieht wie eine
            # Sicherung.
            os.replace(vorlaeufig, archiv)

    return archiv


# Schon gepackte Formate: noch einmal komprimieren kostet Zeit und bringt nichts.
_GEPACKT = frozenset({'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic',
                      '.zip', '.docx', '.xlsx', '.odt', '.ods', '.gz'})


def _zip_schreiben(ziel: Path, manifestdatei: Path, kopie: Path, belege: Path,
                   belegdateien: list[str], zusatz: list[tuple[str, Path]]) -> None:
    with zipfile.ZipFile(ziel, 'w', compression=zipfile.ZIP_DEFLATED,
                         allowZip64=True) as paket:
        paket.write(manifestdatei, MANIFEST_NAME)
        paket.write(kopie, DB_IM_ARCHIV)
        for p in belegdateien:
            quelle = belege / p
            art = (zipfile.ZIP_STORED if quelle.suffix.lower() in _GEPACKT
                   else zipfile.ZIP_DEFLATED)
            # write() liest den Inhalt; ein harter Verweis wird so zur Datei
            # (vgl. _als_datei, NK-147).
            paket.write(quelle, f"{BELEGE_IM_ARCHIV}/{p}", compress_type=art)
        for name_im_archiv, datei in zusatz:
            paket.write(datei, name_im_archiv)


def _quelle(app) -> dict:
    """Woher das Paket stammt -- fuer den Uebernahmebericht, nicht zur Pruefung."""
    from abrechnung_version import SOFTWARE_VERSION

    if app.config.get('DESKTOP'):
        betrieb = 'windows-app'
    elif os.path.exists('/.dockerenv'):
        betrieb = 'docker'
    else:
        betrieb = 'server'
    return {'plattform': sys.platform, 'betrieb': betrieb, 'version': SOFTWARE_VERSION}


def zaehlwerte(db: Path) -> dict:
    """Zeilen je Tabelle einer SQLite-Datei (ohne alembic_version)."""
    verbindung = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        tabellen = [z[0] for z in verbindung.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name")]
        return {
            # Bandit-Ausnahme (B608): Tabellennamen aus sqlite_master, gequotet
            tabelle: verbindung.execute(
                f'SELECT COUNT(*) FROM "{tabelle}"').fetchone()[0]  # nosec B608
            for tabelle in tabellen
        }
    finally:
        verbindung.close()


def _zusatzdateien(app, arbeit: Path) -> list[tuple[str, Path]]:
    """Was zum Bestand gehoert, aber nicht in Datenbank oder Belegordner liegt.

    Die Vermieterwerte werden festgeschrieben: wer unter Docker Name und IBAN
    nur ueber ``VERMIETER_NAME``/``VERMIETER_IBAN`` gesetzt hat, verloere sie
    sonst beim Wechsel in die Windows-App.
    """
    import einstellungen as app_einstellungen
    import datenordner
    import vermieter_logo
    from girocode_generator import iban_saeubern

    try:
        ordner = datenordner.datenordner()
    except datenordner.DatenordnerFehler:
        ordner = datenbankpfad(app).parent
    stand = app_einstellungen.lesen(ordner)
    einstellungen = {
        'format': 1,
        'vermieter_umgebung': {
            'name': os.environ.get('VERMIETER_NAME', '').strip(),
            'iban': iban_saeubern(os.environ.get('VERMIETER_IBAN', '')),
        },
        'anwendung': {k: stand[k] for k in app_einstellungen.UEBERTRAGBAR},
    }
    datei = arbeit / EINSTELLUNGEN_IM_ARCHIV
    datei.write_text(json.dumps(einstellungen, ensure_ascii=False, indent=2),
                     encoding='utf-8')
    zusatz = [(EINSTELLUNGEN_IM_ARCHIV, datei)]
    logo = vermieter_logo.pfad(ordner)
    if logo is not None:
        zusatz.append((f'{LOGO_IM_ARCHIV}/{logo.name}', logo))
    return zusatz


def _datenbank_ziehen(quelle: Path, ziel: Path) -> None:
    lesend = sqlite3.connect(f'file:{quelle}?mode=ro', uri=True)
    try:
        schreibend = sqlite3.connect(ziel)
        try:
            lesend.backup(schreibend)
        finally:
            schreibend.close()
    finally:
        lesend.close()


# --- Lesen und Pruefen -----------------------------------------------------


VERSCHLUESSELT_ENDUNG = '.nkbak'


def behaelter(archiv: Path) -> str:
    """'zip' oder 'tar' -- am Inhalt erkannt, nicht an der Endung."""
    return 'zip' if zipfile.is_zipfile(archiv) else 'tar'


def manifest_lesen(archiv) -> dict:
    """Holt nur das Manifest aus dem Archiv, ohne es auszupacken.

    Bei einer verschluesselten Sicherung (NK-130) ohne Passphrase: die
    lesbaren Metadaten aus dem Kopf, geformt wie ein Manifest und mit
    ``verschluesselt: True`` markiert -- genug fuer Liste und Erinnerung.
    """
    archiv = Path(archiv)
    if not archiv.exists():
        raise SicherungsFehler(f"{archiv} gibt es nicht.")
    if verschluesselung.ist_verschluesselt(archiv):
        try:
            kopf = verschluesselung.metadaten_lesen(archiv)
        except VerschluesselungsFehler as fehler:
            raise SicherungsFehler(f"{archiv.name}: {fehler}") from fehler
        if kopf.get('anwendung') != ANWENDUNG:
            raise SicherungsFehler(
                f"{archiv.name} ist keine Sicherung dieser Anwendung.")
        return {
            'format': kopf.get('format'),
            'erstellt_am': kopf.get('erstellt_am'),
            'alembic_revision': kopf.get('alembic_revision'),
            'zusammenfassung': {
                'belege_anzahl': kopf.get('belege_anzahl'),
                'belege_groesse': kopf.get('belege_groesse'),
            },
            'verschluesselt': True,
        }
    ohne = SicherungsFehler(
        f"{archiv.name} enthält kein {MANIFEST_NAME}. "
        "Das ist keine Sicherung dieser Anwendung.")
    if behaelter(archiv) == 'zip':
        try:
            with zipfile.ZipFile(archiv) as paket:
                eintrag = paket.getinfo(MANIFEST_NAME)
                if eintrag.file_size > 64 * 1024 * 1024:
                    raise SicherungsFehler(f"{archiv.name}: das Manifest ist unplausibel groß.")
                return json.loads(paket.read(eintrag).decode('utf-8'))
        except KeyError:
            raise ohne
        except (zipfile.BadZipFile, ValueError, OSError) as fehler:
            raise SicherungsFehler(f"{archiv.name} ist kein lesbares Paket: {fehler}")
    try:
        with tarfile.open(archiv, 'r:gz') as tar:
            eintrag = tar.extractfile(MANIFEST_NAME)
            if eintrag is None:
                raise ohne
            return json.loads(eintrag.read().decode('utf-8'))
    except tarfile.TarError as fehler:
        raise SicherungsFehler(f"{archiv.name} ist kein lesbares tar.gz: {fehler}")
    except KeyError:
        raise ohne


def _stempel_pruefen(app, manifest: dict) -> None:
    """Kriterium 4: ein Archiv aus der Zukunft wird abgelehnt."""
    if manifest.get('format') not in BEKANNTE_FORMATE:
        raise SicherungsFehler(
            f"Manifestformat {manifest.get('format')} ist dieser Fassung "
            "unbekannt. Das Archiv stammt aus einer anderen Fassung der "
            "Anwendung. Bitte zuerst NebenkostenFix aktualisieren."
        )

    stempel = manifest.get('alembic_revision')
    if not stempel:
        raise SicherungsFehler(
            "Im Manifest steht keine Alembic-Kennung. Woher das Archiv kommt "
            "und auf welches Schema es passt, ist damit nicht feststellbar."
        )

    if stempel not in bekannte_stempel(app):
        raise SicherungsFehler(
            f"Das Archiv hat den Schemastand {stempel}, den diese Fassung der "
            "Anwendung nicht kennt. Es stammt aus einer neueren Version. "
            "Bitte zuerst NebenkostenFix aktualisieren, dann einspielen. "
            "Nichts wurde verändert."
        )


def _pfad_ist_sicher(name: str) -> bool:
    if name.startswith('/') or name.startswith('\\'):
        return False
    teile = Path(name).parts
    return '..' not in teile


def _zipname_ist_sicher(name: str) -> bool:
    """Strenger als tar: ZIP-Namen tragen immer '/' (APPNOTE 4.4.17)."""
    if not name or '\\' in name or '\x00' in name or name.startswith('/'):
        return False
    if re.match(r'^[A-Za-z]:', name):
        return False
    return '..' not in name.split('/')


def _erwartete_dateien(manifest: dict) -> dict:
    """Name im Archiv -> (Groesse, sha256) fuer jede Datei ausser dem Manifest."""
    erwartet = {manifest['datenbank']['pfad']:
                (manifest['datenbank'].get('groesse'), manifest['datenbank']['sha256'])}
    for beleg in manifest['belege']:
        erwartet[f"{BELEGE_IM_ARCHIV}/{beleg['pfad']}"] = (beleg.get('groesse'),
                                                          beleg['sha256'])
    for eintrag in manifest.get('zusatz') or []:
        erwartet[eintrag['pfad']] = (eintrag.get('groesse'), eintrag['sha256'])
    return erwartet


def _zip_pruefen(paket: zipfile.ZipFile, manifest: dict, arbeit: Path) -> None:
    """Jede Regel, bevor ein Byte entpackt wird (NK-164)."""
    eintraege = [e for e in paket.infolist() if not e.is_dir()]
    if len(eintraege) > ZIP_MAX_DATEIEN:
        raise SicherungsFehler(
            f"Das Paket enthält {len(eintraege)} Dateien, höchstens "
            f"{ZIP_MAX_DATEIEN} sind erlaubt.")
    gesehen = set()
    gesamt = 0
    erwartet = _erwartete_dateien(manifest)
    for eintrag in paket.infolist():
        name = eintrag.filename
        if not _zipname_ist_sicher(name):
            raise SicherungsFehler(
                f"Paketeintrag zeigt aus dem Zielverzeichnis heraus: {name}")
        art = (eintrag.external_attr >> 16) & 0o170000
        if art == 0o120000:
            raise SicherungsFehler(
                f"Paket enthält eine Verknüpfung ({name}). Pakete dieser "
                "Anwendung enthalten nur echte Dateien.")
        if eintrag.is_dir():
            continue
        if name in gesehen:
            raise SicherungsFehler(f"Paket enthält {name} doppelt.")
        gesehen.add(name)
        if name == MANIFEST_NAME:
            continue
        soll = erwartet.get(name)
        if soll is not None and soll[0] is not None and eintrag.file_size != soll[0]:
            raise SicherungsFehler(
                f"{name} ist im Paket {eintrag.file_size} Bytes groß, laut "
                f"Manifest {soll[0]}. Das Paket ist beschädigt.")
        if (eintrag.file_size >= ZIP_VERHAELTNIS_AB and eintrag.file_size
                > ZIP_MAX_VERHAELTNIS * max(eintrag.compress_size, 1)):
            raise SicherungsFehler(
                f"{name} entpackt sich auf mehr als das {ZIP_MAX_VERHAELTNIS}-Fache. "
                "So sieht keine Sicherung aus; das Paket wird abgelehnt.")
        gesamt += eintrag.file_size
    if gesamt > zip_max_gesamt():
        raise SicherungsFehler(
            f"Das Paket entpackt sich auf {lesbare_groesse(gesamt)}, erlaubt sind "
            f"{lesbare_groesse(zip_max_gesamt())} (Einstellung UMZUG_MAX_GB).")
    frei = shutil.disk_usage(arbeit).free
    if frei < gesamt * ZIP_PLATZ_RESERVE:
        raise SicherungsFehler(
            f"Zum Entpacken fehlt Platz: nötig sind etwa "
            f"{lesbare_groesse(int(gesamt * ZIP_PLATZ_RESERVE))}, frei sind "
            f"{lesbare_groesse(frei)}.")


def _entpacken(archiv: Path, ziel: Path, manifest: dict | None = None) -> None:
    if behaelter(archiv) == 'zip':
        with zipfile.ZipFile(archiv) as paket:
            _zip_pruefen(paket, manifest or {'datenbank': {'pfad': DB_IM_ARCHIV,
                                                           'sha256': ''},
                                              'belege': []}, ziel)
            for eintrag in paket.infolist():
                if eintrag.is_dir():
                    continue
                zielpfad = ziel.joinpath(*eintrag.filename.split('/'))
                zielpfad.parent.mkdir(parents=True, exist_ok=True)
                # ZipExtFile liefert hoechstens file_size Bytes und prueft die
                # CRC am Ende; file_size ist oben gegen das Manifest geprueft.
                with paket.open(eintrag) as quelle, open(zielpfad, 'wb') as senke:
                    shutil.copyfileobj(quelle, senke, 1024 * 1024)
        return
    with tarfile.open(archiv, 'r:gz') as tar:
        for mitglied in tar.getmembers():
            if not _pfad_ist_sicher(mitglied.name):
                raise SicherungsFehler(
                    f"Archiveintrag zeigt aus dem Zielverzeichnis heraus: "
                    f"{mitglied.name}"
                )
            if mitglied.issym() or mitglied.islnk():
                raise SicherungsFehler(
                    f"Archiv enthält eine Verknüpfung ({mitglied.name}). "
                    "Sicherungen dieser Anwendung enthalten nur echte Dateien."
                )
        try:
            # Bandit-Ausnahme (B202): jeder Eintrag ist oben geprueft (kein .., keine
            # Verknuepfung), dazu filter='data' der Standardbibliothek.
            tar.extractall(ziel, filter='data')  # nosec B202
        except TypeError:
            # Python vor 3.11.4 kennt filter= nicht.
            # Bandit-Ausnahme (B202): die Pruefung oben hat die gefaehrlichen
            # Eintraege bereits aussortiert.
            tar.extractall(ziel)  # nosec B202


def _inhalt_pruefen(manifest: dict, entpackt: Path) -> None:
    """Vergleicht jede Datei im Archiv mit ihrer Pruefsumme im Manifest."""
    erwartet = {name: summe for name, (_, summe) in _erwartete_dateien(manifest).items()}

    vorhanden, _ = _dateien_unter(entpackt)
    vorhanden = set(vorhanden) - {MANIFEST_NAME}

    fehlend = sorted(set(erwartet) - vorhanden)
    zuviel = sorted(vorhanden - set(erwartet))
    if fehlend:
        raise SicherungsFehler(
            f"Im Archiv fehlen {len(fehlend)} im Manifest genannte Dateien, "
            f"zuerst: {fehlend[:3]}"
        )
    if zuviel:
        raise SicherungsFehler(
            f"Im Archiv liegen {len(zuviel)} Dateien, die im Manifest nicht "
            f"stehen, zuerst: {zuviel[:3]}"
        )

    falsch = [
        pfad for pfad, summe in erwartet.items()
        if pruefsumme(entpackt / pfad) != summe
    ]
    if falsch:
        raise SicherungsFehler(
            f"{len(falsch)} Dateien stimmen nicht mit ihrer Prüfsumme "
            f"überein, zuerst: {sorted(falsch)[:3]}. Das Archiv ist "
            "beschädigt, es wurde nichts eingespielt."
        )
    _datenbank_pruefen(entpackt / manifest['datenbank']['pfad'])


def _datenbank_pruefen(db: Path) -> None:
    """``PRAGMA integrity_check`` auf der entpackten Datenbank (NK-164)."""
    try:
        verbindung = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        try:
            ergebnis = verbindung.execute('PRAGMA integrity_check').fetchall()
        finally:
            verbindung.close()
    except sqlite3.DatabaseError as fehler:
        raise SicherungsFehler(
            f"Die Datenbank im Archiv ist keine lesbare SQLite-Datei ({fehler}). "
            "Es wurde nichts eingespielt.") from fehler
    if ergebnis != [('ok',)]:
        raise SicherungsFehler(
            "Die Datenbank im Archiv ist beschädigt (integrity_check: "
            f"{ergebnis[0][0] if ergebnis else '?'}). Es wurde nichts eingespielt.")


# --- Einspielen ------------------------------------------------------------


def sicherung_einspielen(app, archiv, sicherheitskopie_nach=None,
                         passphrase: str | None = None) -> dict:
    """Holt ein Archiv zurueck. Legt vorher eine Sicherung des Ist-Zustands an.

    Reihenfolge ist der ganze Punkt: erst pruefen, dann sichern, dann
    austauschen. Wer zuerst austauscht und dann merkt, dass das Archiv kaputt
    ist, hat beide Staende verloren.

    Eine verschluesselte Sicherung (NK-130) wird zuerst in einen Arbeits-
    ordner entschluesselt; falsche Passphrase oder jede Veraenderung der
    Datei bricht ab, bevor irgendetwas angefasst ist.
    """
    archiv = Path(archiv).resolve()
    if verschluesselung.ist_verschluesselt(archiv):
        if not passphrase:
            raise SicherungsFehler(
                'Diese Sicherung ist verschlüsselt. Geben Sie die Passphrase '
                'an, mit der sie erstellt wurde.')
        with tempfile.TemporaryDirectory(prefix='nk-entschluesseln-') as arbeit:
            klar = Path(arbeit) / 'sicherung.tar.gz'
            try:
                verschluesselung.entschluesseln(archiv, klar, passphrase)
            except VerschluesselungsFehler as fehler:
                raise SicherungsFehler(str(fehler)) from fehler
            # Die Sicherheitskopie des Ist-Zustands liegt neben dem Archiv
            # und wird mit derselben Passphrase verschluesselt -- sonst laege
            # auf dem USB-Stick eine Klartextkopie neben der geschuetzten.
            bericht = _einspielen_klartext(app, klar, sicherheitskopie_nach
                                           or archiv.parent, passphrase)
        bericht['archiv'] = str(archiv)
        return bericht
    return _einspielen_klartext(app, archiv, sicherheitskopie_nach)


def _einspielen_klartext(app, archiv, sicherheitskopie_nach=None,
                         passphrase: str | None = None) -> dict:
    archiv = Path(archiv).resolve()
    manifest = manifest_lesen(archiv)
    _stempel_pruefen(app, manifest)

    ziel_db = datenbankpfad(app)
    ziel_belege = belegwurzel()

    with tempfile.TemporaryDirectory(prefix='nk-einspielen-') as arbeit:
        entpackt = Path(arbeit) / 'inhalt'
        entpackt.mkdir()
        _entpacken(archiv, entpackt, manifest)
        _inhalt_pruefen(manifest, entpackt)

        # Kriterium 3: der Ist-Zustand geht nicht verloren, auch wenn sich das
        # Archiv als das falsche herausstellt.
        rueckweg = None
        if ziel_db.exists():
            ordner = Path(sicherheitskopie_nach or archiv.parent)
            rueckweg = sicherung_erstellen(
                app, ordner, praefix='sicherung-vor-einspielen',
                passphrase=passphrase,
            )

        _verbindungen_schliessen(app)

        ziel_db.parent.mkdir(parents=True, exist_ok=True)
        vorlaeufig = ziel_db.with_name(ziel_db.name + '.neu')
        shutil.copy2(entpackt / DB_IM_ARCHIV, vorlaeufig)
        # NK-076 (WAL): Journal und Index der alten Datei gehoeren nicht zur
        # neuen. Blieben sie liegen, spielte SQLite sie beim naechsten Oeffnen
        # in die eingespielte Datenbank ein.
        for beiwerk in ('-wal', '-shm'):
            rest = ziel_db.with_name(ziel_db.name + beiwerk)
            if rest.exists():
                rest.unlink()
        os.replace(vorlaeufig, ziel_db)

        _belege_ersetzen(entpackt / BELEGE_IM_ARCHIV, ziel_belege)

        _verbindungen_schliessen(app)
        # NK-165 (F-86): ein aelteres Archiv auf den Stand dieser Fassung
        # bringen (Wanderung, Katalog, Belegablage), bevor die Anwendung
        # weiterarbeitet.
        herrichten = app.extensions.get('nk_herrichten')
        if herrichten is not None:
            with app.app_context():
                herrichten(belege=False)
            _verbindungen_schliessen(app)
        zusatz = _zusatz_anwenden(app, entpackt, manifest)

    fehlende = dateiverweise_pruefen(app)
    return {
        'archiv': str(archiv),
        'sicherheitskopie': str(rueckweg) if rueckweg else None,
        'alembic_revision': manifest['alembic_revision'],
        'schemastand_nachher': _stempel(app),
        'belege': manifest['zusammenfassung']['belege_anzahl'],
        'fehlende_verweise': fehlende,
        'format': manifest.get('format'),
        'quelle': manifest.get('quelle'),
        'zaehlwerte': manifest.get('zaehlwerte'),
        'zusatz': zusatz,
    }


def _zusatz_anwenden(app, entpackt: Path, manifest: dict) -> dict:
    """Logo, Einstellungen und festgeschriebene Vermieterwerte eines Pakets
    (Format 2).

    Das Paket ist der ganze Bestand: ein Logo, das es nicht enthaelt, gibt es
    danach nicht mehr. Haftungshinweis und Update-Einstellung kommen mit
    (NK-174, NK-175); ein Paket ohne sie laesst die vorhandenen stehen. Eine
    Lizenzdatei aus Paketen bis 0.9 wird uebergangen (NK-176). Vermieterwerte
    aus der Umgebung des alten Rechners landen in der Datenbank, aber nur in
    leeren Feldern: was dort schon steht, war die wirksame Angabe.
    """
    if manifest.get('format', 1) < 2:
        return {}
    import datenordner
    import vermieter_logo

    try:
        ordner = datenordner.datenordner()
    except datenordner.DatenordnerFehler:
        ordner = datenbankpfad(app).parent
    ordner.mkdir(parents=True, exist_ok=True)
    ergebnis = {'logo': False, 'einstellungen': [], 'vermieter_festgeschrieben': []}

    while vermieter_logo.loeschen(ordner):
        pass
    logos = entpackt / LOGO_IM_ARCHIV
    for endung in vermieter_logo.ENDUNGEN:
        quelle = logos / f'{vermieter_logo.STAMM}.{endung}'
        if quelle.is_file():
            shutil.copy2(quelle, ordner / quelle.name)
            ergebnis['logo'] = True
            break

    einstellungen_datei = entpackt / EINSTELLUNGEN_IM_ARCHIV
    if einstellungen_datei.is_file():
        try:
            einstellungen = json.loads(einstellungen_datei.read_text(encoding='utf-8'))
        except ValueError as fehler:
            raise SicherungsFehler(f'{EINSTELLUNGEN_IM_ARCHIV} ist unlesbar: {fehler}')
        ergebnis['einstellungen'] = _anwendung_uebernehmen(
            ordner, einstellungen.get('anwendung'))
        umgebung = einstellungen.get('vermieter_umgebung') or {}
        ergebnis['vermieter_festgeschrieben'] = _vermieter_festschreiben(
            app, str(umgebung.get('name') or '').strip()[:200],
            str(umgebung.get('iban') or '').strip()[:34])
    return ergebnis


def _anwendung_uebernehmen(ordner: Path, werte) -> list[str]:
    import einstellungen as app_einstellungen

    if not isinstance(werte, dict):
        return []
    # Nur bekannte Schluessel mit dem erwarteten Typ; ein ``None`` beim
    # Hinweis heisst „nie bestaetigt“ und ueberschreibt nichts.
    werte = {k: v for k, v in werte.items()
             if (k == 'haftung' and isinstance(v, dict))
             or (k == 'updates_automatisch' and isinstance(v, bool))}
    if werte:
        app_einstellungen.schreiben(ordner, **werte)
    return sorted(werte)


def _vermieter_festschreiben(app, name: str, iban: str) -> list[str]:
    from models import Vermieterdaten, db

    if not (name or iban):
        return []
    felder = []
    with app.app_context():
        zeile = Vermieterdaten.einziger()
        if zeile is None:
            zeile = Vermieterdaten()
            db.session.add(zeile)
        if name and not (zeile.name or '').strip():
            zeile.name = name
            felder.append('name')
        if iban and not (zeile.iban or '').strip():
            zeile.iban = iban
            felder.append('iban')
        if felder:
            db.session.commit()
        else:
            db.session.rollback()
        db.session.remove()
    return felder


def _als_datei(tar, quelle: Path, arcname: str) -> None:
    """Legt ``quelle`` immer als eigene Datei ins Archiv.

    tarfile schreibt eine Datei mit mehreren harten Verweisen beim zweiten
    Treffer als Verweis (LNKTYPE) -- und das Einspielen lehnt Verweise aus
    gutem Grund ab. Harte Verweise im Belegordner entstehen etwa, wenn die
    Umstellung auf neutrale Namen (NK-131) unterbrochen wurde, oder von Hand.
    Sie sind ein Detail der Ablage, kein Inhalt: im Archiv stehen sie als
    zwei vollstaendige Dateien (NK-147).
    """
    info = tar.gettarinfo(str(quelle), arcname=arcname)
    info.type = tarfile.REGTYPE
    info.linkname = ''
    info.size = quelle.stat().st_size
    with open(quelle, 'rb') as inhalt:
        tar.addfile(info, inhalt)


def _verbindungen_schliessen(app) -> None:
    """Offene SQLite-Griffe loslassen, sonst zeigen sie auf die alte Datei.

    Die Sitzung haengt am Anwendungskontext. Laeuft das Einspielen in einer
    Anfrage, haelt deren Sitzung noch eine Verbindung (etwa vom Laden des
    angemeldeten Kontos) -- ein frischer Kontext saehe sie nicht, und
    ``dispose`` schliesst nur, was im Pool liegt. Unter Windows sperrt jede
    offene Verbindung Datenbank und Journal gegen Ersetzen und Loeschen
    (WinError 32), deshalb zuerst die Sitzung des laufenden Kontexts.
    """
    from flask import has_app_context

    from models import db

    if has_app_context():
        db.session.remove()
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _belege_ersetzen(quelle: Path, ziel: Path) -> None:
    """Ersetzt den Inhalt des Belegordners, nicht den Ordner selbst.

    Der Ordner ist im Container ein Einhaengepunkt. Ihn umzubenennen oder zu
    loeschen geht nicht, sein Inhalt dagegen schon.
    """
    ziel.mkdir(parents=True, exist_ok=True)
    for eintrag in ziel.iterdir():
        if eintrag.is_dir() and not eintrag.is_symlink():
            shutil.rmtree(eintrag)
        else:
            eintrag.unlink()

    if not quelle.is_dir():
        return
    for eintrag in quelle.iterdir():
        if eintrag.is_dir():
            shutil.copytree(eintrag, ziel / eintrag.name)
        else:
            shutil.copy2(eintrag, ziel / eintrag.name)


def dateiverweise_pruefen(app) -> list:
    """Kriterium 5: zeigt jeder Pfad in der Datenbank auf eine echte Datei?

    Gibt die Verweise zurueck, die ins Leere gehen. Leere Liste heisst: alles
    da. Gelesen wird ueber SQL statt ueber die Modelle, damit die Pruefung auch
    auf einer Datenbank laeuft, deren Schema aelter ist als der Code.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    from models import db

    wurzel = belegwurzel()
    fehlend = []
    with app.app_context():
        with db.engine.connect() as verbindung:
            for tabelle, spalte in PFADSPALTEN:
                try:
                    zeilen = verbindung.execute(
                        # Bandit-Ausnahme (B608): Tabelle/Spalte aus der Konstante PFADSPALTEN
                        text(f"SELECT id, {spalte} FROM {tabelle} "  # nosec B608
                             f"WHERE {spalte} IS NOT NULL AND {spalte} != ''")
                    ).all()
                except SQLAlchemyError as ausnahme:
                    # Tabelle oder Spalte gibt es in diesem Schema nicht --
                    # erwartbar bei einer Sicherung aus einer aelteren Fassung.
                    # Vorher stand hier ``except Exception: continue``, und
                    # damit verschwand auch eine kaputte Datenbank lautlos: die
                    # Pruefung meldete "keine fehlenden Belege", weil sie gar
                    # nicht erst nachsehen konnte (NK-042).
                    protokoll.debug(
                        'Belegpruefung ueberspringt %s.%s: %s',
                        tabelle, spalte, ausnahme)
                    continue
                for kennung, pfad in zeilen:
                    if not (wurzel / pfad).is_file():
                        fehlend.append(
                            {'tabelle': tabelle, 'id': kennung,
                             'spalte': spalte, 'pfad': pfad}
                        )
    return fehlend


def lesbare_groesse(bytes_: int) -> str:
    """Groessenangabe, die auch bei kleinen Archiven etwas aussagt.

    "0.0 MB" ist keine Antwort auf die Frage, ob die Sicherung plausibel ist.
    """
    for einheit, teiler in (('GB', 1024 ** 3), ('MB', 1024 ** 2), ('KB', 1024)):
        if bytes_ >= teiler:
            return f"{bytes_ / teiler:.1f} {einheit}"
    return f"{bytes_} Bytes"


# --- Kommandozeile ---------------------------------------------------------


# --- Oberflaeche (NK-077) ---------------------------------------------------
#
# Die Oberflaeche stellt drei Fragen, die die Kommandozeile nicht beantwortet:
# Wann war die letzte Sicherung (Erinnerung), wohin sichern (Ziel wahlbar) und
# welche Archive liegen dort (Einspielen per Knopf). Der Merkzustand dafuer
# ist eine kleine JSON-Datei im Datenordner, keine Tabelle: Er gehoert zur
# Einrichtung wie der Sitzungsschluessel und braucht keine Wanderung.

STAND_NAME = 'backup_stand.json'
ERINNERUNG_AB_TAGE = 30


def _standdatei(app) -> Path:
    return datenbankpfad(app).parent / STAND_NAME


def _gewaehltes_ziel_lesen(app) -> str | None:
    try:
        with open(_standdatei(app), encoding='utf-8') as datei:
            ziel = json.load(datei).get('ziel')
        return ziel or None
    except (OSError, ValueError):
        return None


def _gewaehltes_ziel_speichern(app, ziel: Path) -> None:
    """Das Ziel merken, damit die Vorgabe beim naechsten Mal stimmt."""
    try:
        _standdatei(app).write_text(
            json.dumps({'ziel': str(ziel)}, ensure_ascii=False),
            encoding='utf-8')
    except OSError as fehler:
        # Ohne Merkdatei bleibt es beim Standardziel; das Sichern selbst
        # haengt nicht daran. Still geht nicht: der Fehlerkanal verlangt
        # fuer jedes Schlucken eine Protokollzeile.
        protokoll.warning('Sicherungsziel konnte nicht gemerkt werden: %s', fehler)


def standardziel(app) -> str:
    """Ohne Wahl landet die Sicherung im Ordner ``backups`` des Datenordners
    (NK-132). Ohne erkennbaren Datenordner: neben der Datenbank."""
    import datenordner

    try:
        return str(datenordner.sicherungsordner())
    except datenordner.DatenordnerFehler:
        return str(datenbankpfad(app).parent)


# F-76 (NK-149): Die Routen nahmen jeden Serverpfad an. Ein angemeldeter
# Browser -- oder eine fremde Seite, die ihn fernsteuert -- konnte so jedes
# Verzeichnis nach Archiven durchsuchen und jedes lesbare Archiv einspielen.
# Jetzt gilt eine Positivliste: der Datenordner und die Verzeichnisse, die
# der Betreiber in BACKUP_ZIELE eintraegt (mit dem Pfadtrenner des Systems
# getrennt, unter Linux ':' , unter Windows ';'). Ein NAS bindet man als
# Verzeichnis ein und traegt es dort ein; die Oberflaeche bietet nur an,
# was auf der Liste steht.
ARCHIVNAME = re.compile(
    r'^(sicherung|NebenkostenFix)[A-Za-z0-9_.-]*\.(tar\.gz|nkbak|nkfix)$')


def erlaubte_wurzeln(app) -> list[Path]:
    """Die Verzeichnisse, unter denen Sicherungen liegen duerfen: der
    Datenordner (mit ``backups``), dazu BACKUP_ZIELE."""
    import datenordner

    try:
        daten = datenordner.datenordner()
    except datenordner.DatenordnerFehler:
        daten = datenbankpfad(app).parent
    wurzeln = [Path(os.path.realpath(daten))]
    for eintrag in (os.environ.get('BACKUP_ZIELE') or '').split(os.pathsep):
        eintrag = eintrag.strip()
        if not eintrag:
            continue
        wurzel = Path(os.path.realpath(os.path.expanduser(eintrag)))
        if wurzel not in wurzeln:
            wurzeln.append(wurzel)
    return wurzeln


def _unter_einer_wurzel(pfad: Path, wurzeln: list[Path]) -> bool:
    return any(pfad == w or w in pfad.parents for w in wurzeln)


def _ziel_pruefen(app, ziel) -> Path:
    """Das Ziel muss unter einer erlaubten Wurzel liegen, nie im Belegordner.

    ``realpath`` loest ``..`` und Verknuepfungen auf, bevor verglichen wird:
    Ein Symlink im Datenordner, der nach /etc zeigt, bleibt draussen.

    Der Belegordner wird beim Einspielen geleert: Eine Sicherung, die dort
    liegt, wirft sich selbst weg, genau dann, wenn man sie braucht. Beim
    Erstellen waere sie zusaetzlich Teil ihres eigenen Archivs.
    """
    ziel = Path(os.path.realpath(os.path.expanduser(str(ziel))))
    wurzel = Path(os.path.realpath(belegwurzel()))
    if ziel == wurzel or wurzel in ziel.parents:
        raise SicherungsFehler(
            "Das Sicherungsziel liegt im Belegordner. Beim Einspielen würde "
            "der Belegordner geleert und damit diese Sicherung selbst "
            "gelöscht. Wählen Sie ein Verzeichnis außerhalb.")
    wurzeln = erlaubte_wurzeln(app)
    if not _unter_einer_wurzel(ziel, wurzeln):
        raise SicherungsFehler(
            "Dieses Verzeichnis ist als Sicherungsziel nicht freigegeben. "
            "Erlaubt sind der Datenordner und die Verzeichnisse aus der "
            "Einstellung BACKUP_ZIELE: "
            + ', '.join(str(w) for w in wurzeln))
    return ziel


def _archiv_aufloesen(app, ziel, name) -> Path:
    """Ein Archiv nur als Name aus einem erlaubten Verzeichnis (F-76)."""
    name = (name or '').strip()
    if not ARCHIVNAME.match(name):
        raise SicherungsFehler('Bitte ein Archiv aus der Liste wählen.')
    ordner = _ziel_pruefen(app, ziel or standardziel(app))
    archiv = ordner / name
    if os.path.realpath(archiv) != str(archiv) or not archiv.is_file():
        raise SicherungsFehler(f'Das Archiv {name} ist nicht mehr da.')
    return archiv


def _kurzbericht(archiv: Path, stempel: set) -> dict:
    """Die Zeile fuer die Liste: was in einem Archiv steckt."""
    manifest = manifest_lesen(archiv)
    return {
        'name': archiv.name,
        'pfad': str(archiv),
        'erstellt_am': manifest['erstellt_am'],
        'groesse': lesbare_groesse(archiv.stat().st_size),
        'belege': manifest['zusammenfassung']['belege_anzahl'],
        'schemastand': manifest['alembic_revision'],
        'einspielbar': manifest['alembic_revision'] in stempel,
        'verschluesselt': bool(manifest.get('verschluesselt')),
    }


def _archive_in(ordner: Path) -> list[Path]:
    if not ordner.is_dir():
        return []
    archive = [p for p in ordner.iterdir()
               if p.is_file() and ARCHIVNAME.match(p.name)]
    return sorted(archive, key=lambda p: p.name, reverse=True)


def _letzte_sicherung(app, stempel: set) -> dict | None:
    """Die juengste Sicherung ueber Standardziel und gewaehltem Ziel.

    Gewaehltes Ziel zuerst: Das ist der Fall "ich sichere auf das NAS" und
    der Standardordner hat nur die Vor-Einspielens-Kopien. Bewertet wird
    nach dem Zeitpunkt im Manifest, nicht nach der Dateizeit.
    """
    ordner = []
    gewaehlt = _gewaehltes_ziel_lesen(app)
    if gewaehlt:
        try:
            ordner.append(_ziel_pruefen(app, gewaehlt))
        except SicherungsFehler as fehler:
            # Nicht mehr freigegeben (BACKUP_ZIELE geaendert): zaehlt nicht.
            protokoll.info('Gemerktes Sicherungsziel uebergangen: %s', fehler)
    standard = Path(standardziel(app))
    if standard not in ordner:
        ordner.append(standard)
    juengste = None
    for verzeichnis in ordner:
        for archiv in _archive_in(verzeichnis):
            try:
                bericht = _kurzbericht(archiv, stempel)
            except SicherungsFehler:
                continue  # halbes Archiv: zählt nicht als Sicherung
            if juengste is None or bericht['erstellt_am'] > juengste['erstellt_am']:
                juengste = bericht
    return juengste


def _erinnerung(letzte: dict | None) -> dict:
    """Die Erinnerung der Karte: nie, alt, frisch."""
    if letzte is None:
        return {
            'stufe': 'rot',
            'text': 'Es gibt noch keine Sicherung. Erstellen Sie die erste, '
                    'damit Ihre Daten einen Schaden überleben.',
        }
    erstellt = datetime.fromisoformat(letzte['erstellt_am'])
    tage = (datetime.now().astimezone() - erstellt).days
    if tage >= ERINNERUNG_AB_TAGE:
        return {
            'stufe': 'gelb',
            'text': f'Die letzte Sicherung ist {tage} Tage alt. '
                    f'Erstellen Sie eine neue.',
        }
    return {
        'stufe': 'gruen',
        'text': f'Die letzte Sicherung ist {tage} Tage alt '
                f'({letzte["name"]}).',
    }


def init_backup(app):
    """flask backup create|info|restore (NK-025)."""
    import click
    from flask.cli import AppGroup

    backup_cli = AppGroup('backup', help='Sichern und Zurückholen (NK-025).')

    @backup_cli.command('create')
    @click.option('--ziel', default=None,
                  help='Verzeichnis für das Archiv. Standard: neben der Datenbank.')
    @click.option('--verschluesseln', is_flag=True,
                  help='Mit Passphrase verschlüsseln (NK-130). Ohne die '
                       'Passphrase ist die Sicherung verloren.')
    def erstellen(ziel, verschluesseln):
        """Archiv mit Datenbank, Belegen und Manifest schreiben."""
        ordner = ziel or str(datenbankpfad(app).parent)
        passphrase = None
        if verschluesseln:
            passphrase = click.prompt('Passphrase', hide_input=True,
                                      confirmation_prompt=True)
        try:
            archiv = sicherung_erstellen(app, ordner, passphrase=passphrase)
        except SicherungsFehler as fehler:
            raise click.ClickException(str(fehler))
        manifest = manifest_lesen(archiv)
        click.echo(f"Sicherung: {archiv}")
        click.echo(f"Groesse: {lesbare_groesse(archiv.stat().st_size)}")
        click.echo(f"Belege: {manifest['zusammenfassung']['belege_anzahl']}")
        click.echo(f"Schemastand: {manifest['alembic_revision']}")
        if manifest.get('uebersprungen'):
            click.echo(
                f"Übersprungen (Verknüpfungen): "
                f"{len(manifest['uebersprungen'])}"
            )

    @backup_cli.command('info')
    @click.argument('archiv')
    def info(archiv):
        """Zeigt, was in einem Archiv steckt und ob es einspielbar ist."""
        try:
            manifest = manifest_lesen(archiv)
        except SicherungsFehler as fehler:
            raise click.ClickException(str(fehler))
        click.echo(f"Erstellt am: {manifest['erstellt_am']}")
        click.echo(f"Schemastand: {manifest['alembic_revision']}")
        if manifest.get('verschluesselt'):
            click.echo("Verschlüsselt: ja (AES-256-GCM, Passphrase nötig)")
        else:
            click.echo(f"Datenbank: {lesbare_groesse(manifest['datenbank']['groesse'])}")
        click.echo(f"Belege: {manifest['zusammenfassung']['belege_anzahl']} "
                   f"({lesbare_groesse(manifest['zusammenfassung']['belege_groesse'])})")
        bekannt = manifest['alembic_revision'] in bekannte_stempel(app)
        click.echo("Einspielbar: " + ("ja" if bekannt else
                                      "nein, der Schemastand ist neuer als diese Fassung"))

    @backup_cli.command('entschluesseln')
    @click.argument('quelle')
    @click.argument('ziel')
    @click.option('--passphrase', default=None, hide_input=True)
    def entschluesseln(quelle, ziel, passphrase):
        """Verschlüsselte Sicherung oder Export in Klartext umwandeln (NK-130).

        Für den Notfall ohne laufende Anwendung genügt dieses Modul:
        python -c "import verschluesselung as v; v.entschluesseln('<quelle>', '<ziel>', '<passphrase>')"
        """
        if not passphrase:
            passphrase = click.prompt('Passphrase', hide_input=True)
        try:
            metadaten = verschluesselung.entschluesseln(quelle, ziel, passphrase)
        except (VerschluesselungsFehler, OSError) as fehler:
            raise click.ClickException(str(fehler))
        click.echo(f"Entschlüsselt nach {ziel} ({metadaten.get('erstellt_am', '?')}).")

    @backup_cli.command('restore')
    @click.argument('archiv')
    @click.option('--ja', is_flag=True, help='Ohne Rückfrage einspielen.')
    @click.option('--passphrase', default=None, hide_input=True,
                  help='Passphrase einer verschlüsselten Sicherung (sonst Abfrage).')
    def einspielen(archiv, ja, passphrase):
        """Archiv zurueckholen. Sichert vorher den Ist-Zustand."""
        if not ja:
            click.confirm(
                "Einspielen ersetzt Datenbank und Belege. Die Anwendung sollte "
                "dabei nicht laufen. Der Ist-Zustand wird vorher gesichert. "
                "Weiter?",
                abort=True,
            )
        if verschluesselung.ist_verschluesselt(archiv) and not passphrase:
            passphrase = click.prompt('Passphrase', hide_input=True)
        try:
            bericht = sicherung_einspielen(app, archiv, passphrase=passphrase)
        except SicherungsFehler as fehler:
            raise click.ClickException(str(fehler))
        click.echo(f"Eingespielt: {bericht['archiv']}")
        click.echo(f"Ist-Zustand gesichert unter: {bericht['sicherheitskopie']}")
        click.echo(f"Schemastand: {bericht['alembic_revision']} -> "
                   f"{bericht['schemastand_nachher']}")
        fehlend = bericht['fehlende_verweise']
        if fehlend:
            click.echo(f"Achtung: {len(fehlend)} Dateiverweise gehen ins Leere:")
            for eintrag in fehlend[:10]:
                click.echo(f"  {eintrag['tabelle']}#{eintrag['id']} "
                           f"{eintrag['spalte']}: {eintrag['pfad']}")
        else:
            click.echo("Alle Dateiverweise in der Datenbank zeigen auf echte Dateien.")

    app.cli.add_command(backup_cli)

    # --- Oberflaeche (NK-077) -------------------------------------------

    @app.route('/api/backup/status', methods=['GET'])
    def backup_status():
        """Erinnerung und Vorgaben fuer die Sicherungskarte."""
        stempel = bekannte_stempel(app)
        letzte = _letzte_sicherung(app, stempel)
        return jsonify({
            'standardziel': standardziel(app),
            'zuletzt_gewaehltes_ziel': _gewaehltes_ziel_lesen(app),
            'letzte_sicherung': letzte,
            'erinnerung': _erinnerung(letzte),
            'erinnerung_ab_tage': ERINNERUNG_AB_TAGE,
            'erlaubte_ziele': [str(w) for w in erlaubte_wurzeln(app)],
            # NK-130: Empfehlung und, wo moeglich, Pruefung der
            # Festplattenverschluesselung fuer den Datenordner.
            'festplatte': festplatte.pruefen(standardziel(app)),
        }), 200

    @app.route('/api/backup/erstellen', methods=['POST'])
    def backup_erstellen():
        """Sicherung jetzt schreiben. Ziel wahlbar, Standard ist der
        Datenordner."""
        data = request.get_json(silent=True) or {}
        roh = (data.get('ziel') or '').strip() or standardziel(app)
        passphrase = data.get('passphrase') or None
        try:
            ziel = _ziel_pruefen(app, roh)
            archiv = sicherung_erstellen(app, ziel, passphrase=passphrase)
            _gewaehltes_ziel_speichern(app, ziel)
            manifest = manifest_lesen(archiv)
        except SicherungsFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
        return jsonify({
            'archiv': str(archiv),
            'name': archiv.name,
            'groesse': lesbare_groesse(archiv.stat().st_size),
            'belege': manifest['zusammenfassung']['belege_anzahl'],
            'schemastand': manifest['alembic_revision'],
            'erstellt_am': manifest['erstellt_am'],
            'verschluesselt': bool(manifest.get('verschluesselt')),
        }), 201

    @app.route('/api/backup/liste', methods=['GET'])
    def backup_liste():
        """Die Archive im gewaehlten Verzeichnis, juengste zuerst."""
        roh = (request.args.get('ziel') or '').strip() or standardziel(app)
        try:
            ordner = _ziel_pruefen(app, roh)
        except SicherungsFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
        stempel = bekannte_stempel(app)
        sicherungen = []
        for archiv in _archive_in(ordner):
            try:
                sicherungen.append(_kurzbericht(archiv, stempel))
            except SicherungsFehler:
                # Halbe oder gefaelschte Dateien bleiben aus der Liste raus,
                # statt sie zum Mitspielen anzubieten.
                continue
        return jsonify({'ziel': str(ordner), 'sicherungen': sicherungen}), 200

    @app.route('/api/backup/einspielen', methods=['POST'])
    def backup_einspielen():
        """Ein Archiv zurueckholen. Die Oberflaeche fragt vorher nach; der
        Ist-Zustand wird vom Kern selbst gesichert, bevor etwas ausgetauscht
        wird (Kriterium 3 von NK-025)."""
        data = request.get_json(silent=True) or {}
        ziel, name = data.get('ziel'), data.get('name')
        if not name and data.get('archiv'):
            # Aeltere Oberflaeche: voller Pfad. Zerlegt und genauso streng
            # geprueft -- Verzeichnis auf der Liste, Name nach Muster.
            roh = Path(str(data['archiv']))
            ziel, name = str(roh.parent), roh.name
        try:
            archiv = _archiv_aufloesen(app, ziel, name)
        except SicherungsFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
        try:
            bericht = sicherung_einspielen(
                app, archiv, passphrase=data.get('passphrase') or None)
        except SicherungsFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
        antwort = {
            'archiv': bericht['archiv'],
            'sicherheitskopie': bericht['sicherheitskopie'],
            'schemastand': bericht['alembic_revision'],
            'belege': bericht['belege'],
            'fehlende_verweise': bericht['fehlende_verweise'],
            'hinweis': 'Die Anmeldung bleibt erhalten. Falls der Schemastand '
                       'hinter dieser Fassung zurückliegt, laufen die '
                       'fälligen Wanderungen beim nächsten Start.',
        }
        if bericht['fehlende_verweise']:
            antwort['warnung'] = (
                f"{len(bericht['fehlende_verweise'])} Dateiverweise gehen "
                "ins Leere. Die zugehörigen Belege fehlen im Belegordner.")
        return jsonify(antwort), 200
