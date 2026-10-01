"""Neuerungen für den Microsoft Store (release.yml, Job store).

`msstore publish --noCommit` legt die Einreichung mit dem neuen Paket als
Entwurf an und übernimmt dabei den Eintrag der letzten Fassung, auch deren
„Neuerungen in dieser Version“. Dieses Skript setzt sie im deutschen Eintrag
aus packaging/windows/store/eintrag-de.md. Danach reicht der Job ein.

    python scripts/store_neuerungen.py <produkt-id>

Das JSON läuft nur durch Python: pwsh würde Datumswerte und Umlaute beim
Durchreichen umschreiben, und `submission update` ersetzt die ganze
Einreichung.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EINTRAG = Path(__file__).resolve().parents[1] / 'packaging/windows/store/eintrag-de.md'


def neuerungen(eintrag: str) -> str:
    teile = re.split(r'^## (.+)$', eintrag, flags=re.M)
    felder = {name.strip(): inhalt.strip() for name, inhalt in zip(teile[1::2], teile[2::2])}
    return felder['Neuerungen in dieser Version']


def setzen(einreichung: dict, text: str) -> None:
    deutsch = [eintrag for sprache, eintrag in (einreichung.get('Listings') or {}).items()
               if sprache.lower().startswith('de')]
    if not deutsch:
        raise SystemExit('Die Einreichung hat keinen deutschen Eintrag.')
    for eintrag in deutsch:
        eintrag['BaseListing']['ReleaseNotes'] = text


def _msstore(*argumente: str) -> bytes:
    # Fortschritt nach stderr, auf stdout steht nur das JSON
    return subprocess.run(['msstore', *argumente, '--output-stream', 'stderr'],
                          check=True, stdout=subprocess.PIPE).stdout


def main(produkt: str) -> None:
    einreichung = json.loads(_msstore('submission', 'get', produkt))
    setzen(einreichung, neuerungen(EINTRAG.read_text(encoding='utf-8')))
    with tempfile.TemporaryDirectory() as ordner:
        datei = Path(ordner) / 'einreichung.json'
        datei.write_text(json.dumps(einreichung), encoding='utf-8')
        _msstore('submission', 'update', produkt, '--payload', str(datei))


if __name__ == '__main__':
    main(sys.argv[1])
