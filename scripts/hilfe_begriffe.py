"""Erzeugt static/hilfe-begriffe.json aus docs/glossar.md § 8 (NK-158).

    python scripts/hilfe_begriffe.py

Die Erklärungen hinter dem „?“ haben eine Quelle: den Glossar. Das Abbild
enthält ``docs/`` nicht, deshalb liegt das Ergebnis als JSON unter
``static/``; ``tests/test_hilfe.py`` prüft, dass beide übereinstimmen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
GLOSSAR = WURZEL / 'docs' / 'glossar.md'
ZIEL = WURZEL / 'static' / 'hilfe-begriffe.json'
ABSCHNITT = '## 8. Hilfe in der App'


def begriffe(text: str) -> list[dict]:
    """Die Tabelle aus § 8, in der Reihenfolge des Glossars."""
    anfang = text.index(ABSCHNITT)
    ende = text.find('\n## ', anfang + len(ABSCHNITT))
    abschnitt = text[anfang:ende if ende != -1 else None]
    eintraege = []
    for zeile in abschnitt.splitlines():
        teile = [t.strip() for t in zeile.strip().strip('|').split('|')]
        if len(teile) != 3 or teile[0] in ('Schlüssel', '') or set(teile[0]) <= {'-'}:
            continue
        eintraege.append({'schluessel': teile[0], 'begriff': teile[1], 'satz': teile[2]})
    return eintraege


def inhalt() -> str:
    return json.dumps(begriffe(GLOSSAR.read_text(encoding='utf-8')),
                      ensure_ascii=False, indent=1) + '\n'


def main() -> int:
    ZIEL.write_text(inhalt(), encoding='utf-8')
    print(f'{ZIEL.relative_to(WURZEL)}: {len(json.loads(inhalt()))} Begriffe')
    return 0


if __name__ == '__main__':
    sys.exit(main())
