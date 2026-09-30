"""Kostenarten aufraeumen, wenn die Anwendung nicht mehr startet (NK-095).

Der Notfallweg zu ``kategorien.py``. Grund ist F-16: ``app.py`` wandert die
Datenbank beim *Import*, also loest jeder ``flask``-Befehl die Wanderung mit
aus. Bricht sie an gleichnamigen Kostenarten ab, ist auch ``flask kategorien``
nicht mehr erreichbar -- genau das Werkzeug, das man dann braucht.

Dieses Skript kennt weder Flask noch SQLAlchemy noch ``models.py``. Es oeffnet
die SQLite-Datei mit ``sqlite3`` und benutzt dieselben Funktionen aus
``kategorien.py``, die auch das CLI benutzt. Eine zweite Kopie der Logik waere
die schlechtere Wahl: Kopien laufen auseinander, und ausgerechnet im Notfall
faellt das keinem auf.

    python scripts/kostenarten.py sichern
    python scripts/kostenarten.py dubletten
    python scripts/kostenarten.py zusammenfuehren "Heizung"

Die Datei wird ueber ``DATABASE_URL`` gefunden (``sqlite:////app/data/...``),
sonst ueber ``--datei``.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nebenkostenfix.kategorien import (  # noqa: E402  (erst nach sys.path)
    KategorieFehler,
    dubletten_finden,
    fastdubletten_finden,
    meldung_zu_dubletten,
    zusammenfuehren,
)


def datenbankpfad(vorgabe: str | None = None) -> Path:
    """Die SQLite-Datei aus --datei oder DATABASE_URL."""
    if vorgabe:
        return Path(vorgabe)
    uri = os.environ.get('DATABASE_URL', '')
    if uri.startswith('sqlite:///'):
        rest = uri[len('sqlite:///'):]
        # sqlite:///C:/... (Windows) und sqlite:////app/... (absolut) wie
        # SQLAlchemy lesen; ein Laufwerksbuchstabe bekommt keinen Schraegstrich.
        if re.match(r'^/?[A-Za-z]:[\\/]', rest):
            return Path(rest.lstrip('/'))
        return Path('/' + rest.lstrip('/'))
    raise SystemExit(
        'Keine Datenbank gefunden. DATABASE_URL setzen oder --datei angeben.'
    )


def sichern(pfad: Path) -> Path:
    """Eine Kopie neben die Datei legen, bevor irgendetwas geaendert wird.

    Bewusst ein schlichtes ``copy2`` und kein ``flask backup create``: das
    braeuchte wieder die Anwendung. Wer hier steht, hat keine laufende.
    """
    ziel = pfad.with_name(f'{pfad.name}.vor-kostenarten-{time.strftime("%Y%m%d-%H%M%S")}')
    shutil.copy2(pfad, ziel)
    return ziel


def main(argv=None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument('befehl',
                          choices=('sichern', 'dubletten', 'zusammenfuehren'))
    zerleger.add_argument('name', nargs='?', help='Name der Kostenart')
    zerleger.add_argument('--datei', default=None, help='Pfad der SQLite-Datei')
    argumente = zerleger.parse_args(argv)

    pfad = datenbankpfad(argumente.datei)
    if not pfad.exists():
        print(f'Datenbank nicht gefunden: {pfad}')
        return 1

    if argumente.befehl == 'sichern':
        print(f'Kopie: {sichern(pfad)}')
        return 0

    verbindung = sqlite3.connect(pfad)
    try:
        if argumente.befehl == 'dubletten':
            dubletten = dubletten_finden(verbindung)
            if dubletten:
                print(meldung_zu_dubletten(dubletten))
            else:
                print('Keine gleichnamigen Kostenarten.')
            fast = fastdubletten_finden(verbindung)
            if fast:
                print('\nHinweis — unterscheiden sich nur in Schreibweise:')
                for namen in fast.values():
                    print('  ' + ' / '.join(f'"{n}"' for n in sorted(set(namen))))
            return 1 if dubletten else 0

        if not argumente.name:
            print('zusammenfuehren braucht den Namen der Kostenart.')
            return 2
        try:
            bilanz = zusammenfuehren(verbindung, argumente.name)
        except KategorieFehler as fehler:
            verbindung.rollback()
            print(str(fehler))
            return 1
        verbindung.commit()
        for beschriftung, anzahl in bilanz.items():
            print(f'{beschriftung}: {anzahl}')
        return 0
    finally:
        verbindung.close()


if __name__ == '__main__':
    raise SystemExit(main())
