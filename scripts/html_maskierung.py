"""Waechter gegen unmaskierte Einsetzungen in HTML-Schablonen (NK-149, F-78).

``static/app.js`` baut viel Oberflaeche mit Schablonenstrings und setzt sie
per ``innerHTML`` ein. Jede Einsetzung ``${…}`` in einer Schablone, die HTML
enthaelt, muss entweder

    - maskiert sein (``escapeHtml(…)``, ``dateiAdresse(…)``, Zahlformat), oder
    - einer Form folgen, die keinen Nutzertext tragen kann (Kennung ``.id``,
      Anzahl ``.length``, Ternaer aus zwei festen Zeichenketten, Variablen,
      deren Name sie als fertig gebautes HTML ausweist: ``…Html``,
      ``…Block``, ``…Icon`` …), oder
    - auf der Ausnahmeliste in ``tests/test_html_maskierung.py`` stehen, mit
      Begruendung.

Alles andere meldet der Waechter. Die Pruefung ist bewusst grob: sie liest
den Quelltext, nicht den Datenfluss. Eine neue Einsetzung von Nutzertext
faellt damit sofort auf; die Ausnahmeliste zwingt zur Begruendung.

Aufruf von Hand: ``python scripts/html_maskierung.py`` listet die Funde.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
APP_JS = WURZEL / 'static' / 'app.js'

_LIT = r"""(?:'[^'\\]*'|"[^"\\]*"|`[^`$]*`)"""
SICHERE_FORMEN = [
    # Maskierung und Formatierer
    re.compile(r'^(escapeHtml|dateiAdresse|zeitleisteBetrag|formatCurrency|'
               r'formatiere\w*|encodeURIComponent|Number|parseInt|parseFloat|'
               r'Math\.\w+)\(.*\)$', re.S),
    # Zahlen und Datumsausgabe des Browsers
    re.compile(r'.*\.(toFixed\(\d\)(\.replace\([^)]*\))?|toLocaleString\(.*\)|'
               r'toLocaleDateString\(.*\)|getFullYear\(\))$', re.S),
    # Kennungen, Anzahlen, Tage, Prozentwerte fuer die Geometrie
    re.compile(r'^[\w.]*\b(id|\w+_id|length|\w+_days|\w+Pct|\w+Width)$'),
    # Ternaer aus zwei festen Zeichenketten
    re.compile(r'^[^?]+\?\s*' + _LIT + r'\s*:\s*' + _LIT + r'$', re.S),
    # Im Code gebautes HTML und Stilwerte
    re.compile(r'^\w*(Html|Block|Buttons|Icon|Tag|Attr|Color|Bg|Border|'
               r'Weight|Fmt)$'),
]


def schablonen(quelle: str):
    """Liefert (zeile, [ausdruecke], text) fuer jede Schablone, auch
    verschachtelte. Kommentare, Zeichenketten und Regex-Literale werden
    uebersprungen."""
    n = len(quelle)
    funde = []

    def lies_schablone(i):
        start = i
        i += 1
        ausdruecke = []
        while i < n:
            c = quelle[i]
            if c == '\\':
                i += 2
                continue
            if c == '`':
                return i + 1, ausdruecke, quelle[start:i + 1]
            if c == '$' and quelle[i + 1] == '{':
                j = i + 2
                tiefe = 1
                anfang = j
                while tiefe:
                    d = quelle[j]
                    if d in '"\'':
                        j += 1
                        while quelle[j] != d:
                            if quelle[j] == '\\':
                                j += 1
                            j += 1
                    elif d == '`':
                        ende, innen, text = lies_schablone(j)
                        funde.append((quelle.count('\n', 0, j) + 1, innen, text))
                        j = ende
                        continue
                    elif d == '{':
                        tiefe += 1
                    elif d == '}':
                        tiefe -= 1
                    j += 1
                ausdruecke.append(quelle[anfang:j - 1])
                i = j
                continue
            i += 1
        raise ValueError('Schablone ohne Ende')

    i = 0
    while i < n:
        c = quelle[i]
        if quelle.startswith('//', i):
            i = quelle.find('\n', i)
            if i < 0:
                break
            continue
        if quelle.startswith('/*', i):
            i = quelle.index('*/', i) + 2
            continue
        if c in '"\'':
            i += 1
            while quelle[i] != c:
                if quelle[i] == '\\':
                    i += 1
                i += 1
            i += 1
            continue
        if c == '`':
            zeile = quelle.count('\n', 0, i) + 1
            i, ausdruecke, text = lies_schablone(i)
            funde.append((zeile, ausdruecke, text))
            continue
        if c == '/':
            k = i - 1
            while k >= 0 and quelle[k] in ' \t':
                k -= 1
            if k >= 0 and quelle[k] in '(,=:[!&|?{};\n':
                j = i + 1
                klasse = False
                while True:
                    d = quelle[j]
                    if d == '\\':
                        j += 2
                        continue
                    if d == '[':
                        klasse = True
                    elif d == ']':
                        klasse = False
                    elif (d == '/' and not klasse) or d == '\n':
                        break
                    j += 1
                i = j + 1
                continue
        i += 1
    return funde


def normiert(ausdruck: str) -> str:
    return ' '.join(ausdruck.split())


def unmaskierte_ausdruecke(quelle: str) -> list[tuple[int, str]]:
    """(Zeile, Ausdruck) fuer jede Einsetzung in HTML-Schablonen, die keiner
    sicheren Form folgt."""
    funde = []
    for zeile, ausdruecke, text in schablonen(quelle):
        if '<' not in text:
            continue
        for ausdruck in ausdruecke:
            kurz = normiert(ausdruck)
            if any(form.match(kurz) for form in SICHERE_FORMEN):
                continue
            funde.append((zeile, kurz))
    return funde


if __name__ == '__main__':
    for zeile, ausdruck in unmaskierte_ausdruecke(APP_JS.read_text(encoding='utf-8')):
        print(f'static/app.js:{zeile}: ${{{ausdruck[:100]}}}')
    sys.exit(0)
