#!/usr/bin/env python3
"""Harte Abdeckungsschwelle je Datei (NK-032).

Warum es dieses Skript gibt: ``coverage.py`` kennt nur **eine** Schwelle,
``fail_under`` im Abschnitt ``[tool.coverage.report]``, und die gilt fuer das
ganze Projekt. Eine Zahl fuer alles hat einen blinden Fleck: die
Projektschwelle steht heute auf 55, und sie bliebe gruen, wenn ausgerechnet
``auth.py`` von 99 auf 40 faellt -- solange irgendwo anders genug dazukommt.
Der Tuersteher und die Datenrettung sind aber genau die zwei Dateien, bei
denen ein Rueckfall niemandem auffaellt und jedem schadet.

Die Regeln stehen in ``pyproject.toml``:

    [tool.nk.einzelschwelle]
    "auth.py" = 90

Aufruf nach ``pytest`` (``make check`` tut das), gelesen wird die Datendatei,
die pytest-cov hinterlassen hat:

    python scripts/einzelschwelle.py

Rueckgabe 0, wenn jede genannte Datei ihre Zahl haelt, sonst 1 mit einer
Zeile je Datei. Gerundet wird **nicht**: 89,97 Prozent sind weniger als 90.
Eine Rundung nach oben waere hier die falsche Freundlichkeit -- die Schwelle
soll einen Rueckfall melden, nicht ihn glattbuegeln.
"""

from __future__ import annotations

import io
import sys
import tomllib
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
PYPROJECT = WURZEL / 'pyproject.toml'


def regeln_lesen(pfad: Path = PYPROJECT) -> dict[str, float]:
    """Die Tabelle [tool.nk.einzelschwelle] aus der pyproject.toml."""
    with pfad.open('rb') as datei:
        inhalt = tomllib.load(datei)
    roh = inhalt.get('tool', {}).get('nk', {}).get('einzelschwelle', {})
    return {name: float(wert) for name, wert in roh.items()}


def bewerten(gemessen: dict[str, float | None],
             regeln: dict[str, float]) -> list[tuple[str, float | None, float, bool]]:
    """Regeln gegen Messwerte halten, ohne irgendetwas zu messen.

    Getrennt von der Messung, damit die Entscheidung "haelt oder haelt nicht"
    mit erfundenen Zahlen pruefbar ist, ohne einen Testlauf zu brauchen.
    Ein Messwert ``None`` heisst "nicht gemessen" und gilt als Durchfall: eine
    Datei, die in keinem Test mehr vorkommt, ist der Rueckfall, den die Karte
    verhindern soll -- nur eben der vollstaendige.
    """
    ergebnis = []
    for name in sorted(regeln):
        schwelle = regeln[name]
        wert = gemessen.get(name)
        haelt = wert is not None and wert >= schwelle
        ergebnis.append((name, wert, schwelle, haelt))
    return ergebnis


def messen(regeln: dict[str, float],
           pyproject: Path = PYPROJECT) -> dict[str, float | None]:
    """Die Abdeckung je genannter Datei aus der Datendatei von pytest-cov.

    ``Coverage.report(include=[...])`` liefert den Prozentsatz genau dieser
    Auswahl zurueck -- bei einer einzelnen Datei also deren eigene Zahl,
    gerechnet von coverage selbst. Ein eigener Nachbau der Rechnung wuerde
    frueher oder spaeter von dem abweichen, was ``make check`` anzeigt.
    """
    from coverage import Coverage
    from coverage.exceptions import CoverageException

    gemessen: dict[str, float | None] = {}
    for name in regeln:
        cov = Coverage(config_file=str(pyproject))
        cov.load()
        try:
            # Die Ausgabe des Reports wandert ins Leere: hier zaehlt nur die
            # Zahl, die Tabelle hat pytest-cov schon gedruckt.
            gemessen[name] = cov.report(include=[name], file=io.StringIO())
        except CoverageException:
            gemessen[name] = None
    return gemessen


def main(pyproject: Path = PYPROJECT, messer=messen) -> int:
    """Der Durchgang, den ``make check`` aufruft.

    ``messer`` haengt als Parameter daran, damit ein Test die Entscheidung mit
    erfundenen Zahlen durchspielen kann: ob ein Unterschreiten wirklich in
    einem Rueckgabewert ungleich 0 endet, ist die eigentliche Zusage der Karte,
    und die darf nicht davon abhaengen, ob gerade eine Datendatei herumliegt.
    """
    regeln = regeln_lesen(pyproject)
    if not regeln:
        print('Keine Einzelschwellen in [tool.nk.einzelschwelle] — nichts zu pruefen.')
        return 0

    zeilen = bewerten(messer(regeln), regeln)
    print('Einzelschwellen (NK-032)')
    durchgefallen = 0
    for name, wert, schwelle, haelt in zeilen:
        gemessen = 'nicht gemessen' if wert is None else f'{wert:.2f} %'
        zeichen = 'ok  ' if haelt else 'FEHL'
        print(f'  {zeichen} {name:<24} {gemessen:>16}   verlangt {schwelle:.0f} %')
        if not haelt:
            durchgefallen += 1

    if durchgefallen:
        print(f'\n{durchgefallen} Datei(en) unter ihrer Einzelschwelle.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
