"""Werkzeug des Herausgebers: Schlüssel, Lizenzen, Update-Manifeste
(NK-080, NK-081, D-93). Läuft beim Herausgeber, nie beim Kunden, und gehört
nicht ins Abbild.

    # Einmalig: Schlüsselpaar. Der private Schlüssel verlässt diesen Rechner
    # nie und gehört nicht ins Repository; den öffentlichen trägt man in
    # lizenz.HERAUSGEBER_SCHLUESSEL ein.
    python scripts/lizenz_werkzeug.py schluessel ~/nk-herausgeber.pem

    # Eine Lizenz ausstellen (Updates ein Jahr lang)
    python scripts/lizenz_werkzeug.py ausstellen ~/nk-herausgeber.pem \\
        --name "Anna Vermieterin" --bis 2027-10-01 --ausgabe anna.nklizenz

    # Das Manifest eines Releases signieren (NK-135)
    python scripts/lizenz_werkzeug.py manifest ~/nk-herausgeber.pem \\
        --version 0.9.1 --installer dist/NebenkostenFix-0.9.1-Setup.exe \\
        --url https://…/NebenkostenFix-0.9.1-Setup.exe \\
        --docker ghcr.io/nerbry72/nebenkostenfix:0.9.1 \\
        --ausgabe manifest.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import (  # noqa: E402
    Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key)

import aktualisierung  # noqa: E402
import lizenz  # noqa: E402


def oeffentlich_b64(privat: Ed25519PrivateKey) -> str:
    return base64.b64encode(privat.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode('ascii')


def schluessel_erzeugen(datei: Path) -> str:
    if datei.exists():
        raise SystemExit(f'{datei} gibt es schon -- ein Schlüssel wird nie überschrieben.')
    privat = Ed25519PrivateKey.generate()
    pem = privat.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    kennung = os.open(datei, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(kennung, 'wb') as ausgabe:
        ausgabe.write(pem)
    return oeffentlich_b64(privat)


def schluessel_laden(datei: Path) -> Ed25519PrivateKey:
    privat = load_pem_private_key(datei.read_bytes(), password=None)
    if not isinstance(privat, Ed25519PrivateKey):
        raise SystemExit(f'{datei} ist kein Ed25519-Schlüssel.')
    return privat


def lizenz_ausstellen(privat: Ed25519PrivateKey, name: str, bis: date,
                      heute: date | None = None) -> dict:
    daten = {'produkt': lizenz.PRODUKT, 'kennung': str(uuid.uuid4()),
             'lizenznehmer': name.strip(), 'ausgestellt': (heute or date.today()).isoformat(),
             'updates_bis': bis.isoformat()}
    umschlag = lizenz.signieren(daten, privat)
    lizenz.pruefen(json.dumps(umschlag), oeffentlich_b64(privat))  # Gegenprobe
    return umschlag


def manifest_signieren(privat: Ed25519PrivateKey, version: str, installer: Path | None,
                       url: str | None, docker: str | None, hinweise: str,
                       veroeffentlicht: date | None = None) -> dict:
    daten = {'version': version,
             'veroeffentlicht': (veroeffentlicht or date.today()).isoformat(),
             'hinweise': hinweise}
    if installer is not None:
        if not url:
            raise SystemExit('Zum Installer gehört --url.')
        daten['windows'] = {'url': url,
                            'sha256': hashlib.sha256(installer.read_bytes()).hexdigest()}
    if docker:
        daten['docker'] = docker
    umschlag = lizenz.signieren(daten, privat, aktualisierung.FORMAT)
    aktualisierung.manifest_pruefen(json.dumps(umschlag).encode('utf-8'),
                                    oeffentlich_b64(privat))  # Gegenprobe
    return umschlag


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    befehle = zerleger.add_subparsers(dest='befehl', required=True)
    s = befehle.add_parser('schluessel', help='Schlüsselpaar erzeugen')
    s.add_argument('datei', type=Path)
    a = befehle.add_parser('ausstellen', help='Lizenz ausstellen')
    a.add_argument('schluessel', type=Path)
    a.add_argument('--name', required=True)
    a.add_argument('--bis', required=True, type=date.fromisoformat)
    a.add_argument('--ausgabe', required=True, type=Path)
    m = befehle.add_parser('manifest', help='Update-Manifest signieren')
    m.add_argument('schluessel', type=Path)
    m.add_argument('--version', required=True)
    m.add_argument('--installer', type=Path)
    m.add_argument('--url')
    m.add_argument('--docker')
    m.add_argument('--hinweise', default='')
    m.add_argument('--ausgabe', required=True, type=Path)
    argumente = zerleger.parse_args(argv)

    if argumente.befehl == 'schluessel':
        oeffentlich = schluessel_erzeugen(argumente.datei)
        print(f'Privater Schlüssel: {argumente.datei} (nur hier, nie ins Repository)')
        print(f"In lizenz.py eintragen: HERAUSGEBER_SCHLUESSEL = '{oeffentlich}'")
        return 0
    privat = schluessel_laden(argumente.schluessel)
    if argumente.befehl == 'ausstellen':
        umschlag = lizenz_ausstellen(privat, argumente.name, argumente.bis)
    else:
        umschlag = manifest_signieren(privat, argumente.version, argumente.installer,
                                      argumente.url, argumente.docker, argumente.hinweise)
    argumente.ausgabe.write_text(json.dumps(umschlag, ensure_ascii=False, indent=2) + '\n',
                                 encoding='utf-8')
    print(f'Geschrieben: {argumente.ausgabe}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
