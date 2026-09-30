"""Umzug über Plattformgrenzen, als Probe der CI (NK-164, E-13 → D-96).

    python scripts/umzug_kreuzprobe.py bauen   --arbeit DIR --name linux
    python scripts/umzug_kreuzprobe.py pruefen --arbeit DIR --paket P.nkfix --erwartet P.json

``bauen`` legt in einem frischen Datenordner einen fiktiven Bestand an
(Beispielimmobilie, ein Konto, ein Beleg mit Umlaut im Anzeigenamen, Logo,
Lizenzdatei, Vermieterwerte nur aus der Umgebung), exportiert das
Umzugspaket ``<name>.nkfix`` und schreibt daneben ``<name>.json`` mit dem,
was drüben ankommen muss: Zeilen je Tabelle, sha256 jedes Belegs, Konto.

``pruefen`` übernimmt ein Paket in einen frischen Datenordner -- auf einer
anderen Plattform -- und vergleicht: gleiche Zeilen je Tabelle (Kostenarten
dürfen nachgesät sein), bytegleiche Belege, keine Lücken, Anmeldung mit dem
alten Passwort, Vermieterwerte festgeschrieben, Logo da. Exit 0 heißt
bestanden. Die CI (``.github/workflows/windows.yml``) baut unter Linux und
prüft unter Windows (dort auch in der gebauten App, ``paketprobe.py umzug``)
und umgekehrt.

Jede Stufe läuft als eigener Prozess mit eigenem ``DATA_DIR``: die
Anwendung liest ihren Datenordner beim Import.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
KONTO = 'umzug-probe'
PASSWORT = 'umzug-probe-passwort-1'
VERMIETER = {'VERMIETER_NAME': 'Anna Vermieterin', 'VERMIETER_IBAN': 'DE02120300000000202051'}
# Tabellen, die eine Übernahme ergänzen darf (Katalog, Vermieterdaten).
DARF_WACHSEN = {'cost_categories', 'vermieterdaten'}
PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d4948445200000001000000010806000000'
    '1f15c4890000000d49444154789c63f80f00000101000518d84e0000000049454e44ae426082')


def _umgebung(daten: Path, vermieter: bool) -> dict:
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ('DATABASE_URL', 'NAS_MOUNT_PATH', 'LOCAL_PDF_PATH',
                             'LOCAL_TEMP_PATH', 'SECRET_KEY', 'ENABLE_DEBUG_RESET',
                             'VERMIETER_NAME', 'VERMIETER_IBAN')}
    umgebung['DATA_DIR'] = str(daten)
    umgebung['PYTHONIOENCODING'] = 'utf-8'
    if vermieter:
        umgebung.update(VERMIETER)
    return umgebung


def _stufe(daten: Path, vermieter: bool, *argumente: str) -> dict:
    lauf = subprocess.run(  # noqa: S603 -- eigenes Skript, feste Argumente
        [sys.executable, __file__, '--stufe', *argumente, '--daten', str(daten)],
        cwd=WURZEL, env=_umgebung(daten, vermieter), capture_output=True, text=True,
        encoding='utf-8', timeout=900)
    if lauf.returncode != 0:
        raise SystemExit(f'Stufe {argumente[0]} brach ab:\n{lauf.stdout}\n{lauf.stderr}')
    return json.loads(lauf.stdout.strip().splitlines()[-1])


def _stufe_ausfuehren(argumente) -> dict:
    daten = Path(argumente.daten)
    sys.path.insert(0, str(WURZEL))
    import app as anwendung

    if argumente.stufe == 'anlegen':
        return _anlegen(anwendung, daten, Path(argumente.paket))
    if argumente.stufe == 'uebernehmen':
        return _uebernehmen(anwendung, daten, Path(argumente.paket))
    raise SystemExit(f'Unbekannte Stufe {argumente.stufe}')


def _anlegen(anwendung, daten: Path, paket: Path) -> dict:
    from nebenkostenfix import beispielimmobilie
    from nebenkostenfix import umzug
    from nebenkostenfix.models import InvoiceDocument, Property, User, db

    with anwendung.app.app_context():
        konto = User(username=KONTO)
        konto.set_password(PASSWORT)
        db.session.add(konto)
        db.session.commit()
        beispielimmobilie.anlegen()
        haus = Property.query.first()
        ordner = anwendung.datenordner.belegordner() / 'umzug-probe'
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / 'rechnung.pdf').write_bytes('%PDF-1.4\nHeizöl März\n%%EOF\n'.encode('utf-8'))
        db.session.add(InvoiceDocument(property_id=haus.id, filename='Heizöl März (2025).pdf',
                                       document_path='umzug-probe/rechnung.pdf'))
        db.session.commit()
        db.session.remove()
    (daten / 'vermieter-logo.png').write_bytes(PNG)
    from nebenkostenfix import einstellungen
    einstellungen.schreiben(daten, updates_automatisch=False,
                            haftung={'version': 1, 'bestaetigt_am': '2026-01-01T00:00:00+00:00'})
    umzug.paket_erstellen(anwendung.app, paket)
    return umzug.bestandsbericht(anwendung.app)


def _uebernehmen(anwendung, daten: Path, paket: Path) -> dict:
    from nebenkostenfix import umzug
    from nebenkostenfix.models import User

    bericht = umzug.uebernehmen(anwendung.app, paket)
    ergebnis = umzug.bestandsbericht(anwendung.app)
    with anwendung.app.app_context():
        konto = User.query.filter_by(username=KONTO).first()
        ergebnis['anmeldung'] = bool(konto and konto.check_password(PASSWORT))
    ergebnis['bericht'] = {k: bericht[k] for k in ('schemastand_paket', 'schemastand_nachher',
                                                   'quelle', 'belege', 'zusatz')}
    return ergebnis


def vergleichen(erwartet: dict, angekommen: dict) -> list[str]:
    """Was fehlt oder abweicht; leere Liste heißt bestanden."""
    fehler = []
    for tabelle, anzahl in erwartet['zeilen'].items():
        da = angekommen['zeilen'].get(tabelle)
        if da is None:
            fehler.append(f'Tabelle {tabelle} fehlt')
        elif tabelle in DARF_WACHSEN:
            if da < anzahl:
                fehler.append(f'{tabelle}: {anzahl} -> {da}')
        elif da != anzahl:
            fehler.append(f'{tabelle}: {anzahl} -> {da} Zeilen')
    if erwartet['belege'] != angekommen['belege']:
        fehlend = sorted(set(erwartet['belege']) - set(angekommen['belege']))
        fehler.append(f'Belege nicht bytegleich (fehlend: {fehlend[:3]})')
    if angekommen['fehlend'] > erwartet['fehlend']:
        fehler.append(f'{angekommen["fehlend"]} Verweise ins Leere')
    if 'anmeldung' in angekommen:
        if not angekommen['anmeldung']:
            fehler.append('Anmeldung mit dem alten Passwort geht nicht')
    elif KONTO not in angekommen.get('konten', []):
        fehler.append(f'Konto {KONTO} fehlt')
    if angekommen.get('vermieter') != {'name': VERMIETER['VERMIETER_NAME'],
                                       'iban': VERMIETER['VERMIETER_IBAN']}:
        fehler.append(f'Vermieterwerte nicht festgeschrieben: {angekommen.get("vermieter")}')
    if not angekommen.get('logo'):
        fehler.append('Logo fehlt')
    if angekommen.get('einstellungen') != erwartet.get('einstellungen'):
        fehler.append(f'Einstellungen nicht übernommen: {angekommen.get("einstellungen")}')
    return fehler


def bauen(arbeit: Path, name: str) -> dict:
    daten = arbeit / f'{name}-quelle'
    daten.mkdir(parents=True)
    paket = arbeit / f'{name}.nkfix'
    erwartet = _stufe(daten, True, 'anlegen', '--paket', str(paket))
    erwartet['plattform'] = sys.platform
    (arbeit / f'{name}.json').write_text(json.dumps(erwartet, ensure_ascii=False, indent=2),
                                         encoding='utf-8')
    return erwartet


def pruefen(arbeit: Path, paket: Path, erwartet_datei: Path) -> dict:
    daten = arbeit / f'{paket.stem}-ziel'
    daten.mkdir(parents=True)
    erwartet = json.loads(erwartet_datei.read_text(encoding='utf-8'))
    angekommen = _stufe(daten, False, 'uebernehmen', '--paket', str(paket))
    fehler = vergleichen(erwartet, angekommen)
    bericht = {'ergebnis': 'bestanden' if not fehler else 'fehlgeschlagen', 'fehler': fehler,
               'von': erwartet.get('plattform'), 'nach': sys.platform,
               'zeilen': sum(angekommen['zeilen'].values()), 'belege': len(angekommen['belege']),
               'bericht': angekommen['bericht']}
    (arbeit / f'{paket.stem}-pruefung.json').write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2), encoding='utf-8')
    return bericht


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument('befehl', nargs='?', choices=('bauen', 'pruefen'))
    zerleger.add_argument('--arbeit', type=Path)
    zerleger.add_argument('--name', default=sys.platform)
    zerleger.add_argument('--paket', type=Path)
    zerleger.add_argument('--erwartet', type=Path)
    zerleger.add_argument('--stufe', help=argparse.SUPPRESS)
    zerleger.add_argument('--daten', help=argparse.SUPPRESS)
    argumente = zerleger.parse_args(argv)
    if argumente.stufe:
        print(json.dumps(_stufe_ausfuehren(argumente), ensure_ascii=False))
        return 0
    if not argumente.befehl or not argumente.arbeit:
        zerleger.error('bauen|pruefen und --arbeit sind nötig.')
    argumente.arbeit.mkdir(parents=True, exist_ok=True)
    if argumente.befehl == 'bauen':
        erwartet = bauen(argumente.arbeit.resolve(), argumente.name)
        print(f'Paket gebaut: {sum(erwartet["zeilen"].values())} Zeilen, '
              f'{len(erwartet["belege"])} Belege')
        return 0
    if not (argumente.paket and argumente.erwartet):
        zerleger.error('pruefen braucht --paket und --erwartet.')
    bericht = pruefen(argumente.arbeit.resolve(), argumente.paket.resolve(),
                      argumente.erwartet.resolve())
    print(json.dumps(bericht, ensure_ascii=False, indent=2))
    return 0 if bericht['ergebnis'] == 'bestanden' else 1


if __name__ == '__main__':
    sys.exit(main())
