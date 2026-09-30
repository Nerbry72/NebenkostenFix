"""Werkzeug des Herausgebers: Schlüssel und Update-Manifeste (NK-175, D-101).
Läuft beim Herausgeber oder im Release-Workflow, nie beim Nutzer, und gehört
nicht ins Abbild.

    # Einmalig: Schlüsselpaar. Der private Schlüssel verlässt diesen Rechner
    # nur als Actions-Secret UPDATE_SCHLUESSEL und gehört nicht ins
    # Repository; den öffentlichen trägt man in
    # aktualisierung.HERAUSGEBER_SCHLUESSEL ein.
    python scripts/update_signieren.py schluessel ~/nk-herausgeber.pem

    # Das Manifest eines Releases signieren (release.yml)
    python scripts/update_signieren.py manifest ~/nk-herausgeber.pem \\
        --version 0.10.0 --installer dist/NebenkostenFix-0.10.0-Setup.exe \\
        --url https://…/NebenkostenFix-0.10.0-Setup.exe \\
        --notizen https://github.com/Nerbry72/NebenkostenFix/releases/tag/v0.10.0 \\
        --docker ghcr.io/nerbry72/nebenkostenfix:0.10.0 \\
        --ausgabe update.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import (  # noqa: E402
    Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key)

from nebenkostenfix import aktualisierung  # noqa: E402


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


def manifest_signieren(privat: Ed25519PrivateKey, version: str, installer: Path | None,
                       url: str | None, docker: str | None, hinweise: str,
                       veroeffentlicht: date | None = None,
                       notizen: str | None = None) -> dict:
    daten = {'version': version,
             'veroeffentlicht': (veroeffentlicht or date.today()).isoformat(),
             'hinweise': hinweise}
    if notizen:
        daten['notizen'] = notizen
    if installer is not None:
        if not url:
            raise SystemExit('Zum Installer gehört --url.')
        daten['windows'] = {'url': url,
                            'sha256': hashlib.sha256(installer.read_bytes()).hexdigest()}
    if docker:
        daten['docker'] = docker
    umschlag = aktualisierung.signieren(daten, privat)
    aktualisierung.manifest_pruefen(json.dumps(umschlag).encode('utf-8'),
                                    oeffentlich_b64(privat))  # Gegenprobe
    return umschlag


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    befehle = zerleger.add_subparsers(dest='befehl', required=True)
    s = befehle.add_parser('schluessel', help='Schlüsselpaar erzeugen')
    s.add_argument('datei', type=Path)
    m = befehle.add_parser('manifest', help='Update-Manifest signieren')
    m.add_argument('schluessel', type=Path)
    m.add_argument('--version', required=True)
    m.add_argument('--installer', type=Path)
    m.add_argument('--url')
    m.add_argument('--docker')
    m.add_argument('--hinweise', default='')
    m.add_argument('--notizen')
    m.add_argument('--ausgabe', required=True, type=Path)
    argumente = zerleger.parse_args(argv)

    if argumente.befehl == 'schluessel':
        oeffentlich = schluessel_erzeugen(argumente.datei)
        print(f'Privater Schlüssel: {argumente.datei} (nur hier, nie ins Repository)')
        print(f"In aktualisierung.py eintragen: HERAUSGEBER_SCHLUESSEL = '{oeffentlich}'")
        return 0
    privat = schluessel_laden(argumente.schluessel)
    umschlag = manifest_signieren(privat, argumente.version, argumente.installer,
                                  argumente.url, argumente.docker, argumente.hinweise,
                                  notizen=argumente.notizen)
    argumente.ausgabe.write_text(json.dumps(umschlag, ensure_ascii=False, indent=2) + '\n',
                                 encoding='utf-8')
    print(f'Geschrieben: {argumente.ausgabe}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
