"""Inhalt des MSIX-Pakets für den Microsoft Store vorbereiten (NK-173).

    python packaging/windows/msix.py vorbereiten <pyinstaller-ordner> <ziel> <version>

Kopiert die PyInstaller-Ausgabe (``NebenkostenFix.exe`` samt ``_internal``)
nach ``<ziel>``, schreibt ``AppxManifest.xml`` mit der Paketversion
(``0.10.4`` wird ``0.10.4.0``) und zeichnet die Logos aus dem App-Symbol.
Packen (MakeAppx) und die Probe mit Testsignatur macht ``windows.yml``.
Das Paket bleibt unsigniert: Der Store signiert es bei der Veröffentlichung.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
VORLAGE = HIER / 'msix' / 'AppxManifest.xml'
SYMBOL = HIER / 'nebenkostenfix.ico'
# Name und Kantenlänge der Logos, auf die das Manifest verweist.
LOGOS = {
    'StoreLogo.png': 50,
    'Square44x44Logo.png': 44,
    'Square150x150Logo.png': 150,
}


def paketversion(version: str) -> str:
    """Die Version im Format des Stores: vier Zahlen, die letzte 0.

    >>> paketversion('0.10.4')
    '0.10.4.0'
    """
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError(f'Version „{version}“ hat nicht die Form x.y.z.')
    teile = [int(t) for t in version.split('.')]
    if any(t > 65535 for t in teile):
        raise ValueError(f'Version „{version}“: jede Zahl höchstens 65535.')
    return '.'.join(map(str, teile)) + '.0'


def manifest(version: str) -> str:
    return VORLAGE.read_text(encoding='utf-8').replace('$VERSION$', paketversion(version))


def logos(ziel: Path, symbol: Path = SYMBOL) -> list[Path]:
    """Die Logos aus der größten Stufe des App-Symbols (256 px)."""
    from PIL import Image

    ziel.mkdir(parents=True, exist_ok=True)
    with Image.open(symbol) as ico:
        groesste = max(ico.info.get('sizes') or [ico.size])
        ico.size = groesste
        bild = ico.convert('RGBA')
    dateien = []
    for name, kante in LOGOS.items():
        pfad = ziel / name
        bild.resize((kante, kante), Image.LANCZOS).save(pfad)
        dateien.append(pfad)
    return dateien


def vorbereiten(quelle: Path, ziel: Path, version: str) -> Path:
    if not (quelle / 'NebenkostenFix.exe').is_file():
        raise FileNotFoundError(f'{quelle}: NebenkostenFix.exe fehlt (erst PyInstaller).')
    if ziel.exists():
        shutil.rmtree(ziel)
    shutil.copytree(quelle, ziel)
    (ziel / 'AppxManifest.xml').write_text(manifest(version), encoding='utf-8')
    logos(ziel / 'Assets')
    return ziel


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[0] != 'vorbereiten':
        sys.stderr.write(__doc__)
        return 2
    ziel = vorbereiten(Path(argv[1]), Path(argv[2]), argv[3])
    print(f'{ziel}: Manifest {paketversion(argv[3])}, {len(LOGOS)} Logos')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
