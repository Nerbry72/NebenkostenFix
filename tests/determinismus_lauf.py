"""Ein Abrechnungslauf, der sein Ergebnis als JSON auf die Ausgabe schreibt.

Getrennte Datei, weil ``tests/test_determinismus.py`` sie in einem eigenen
Prozess startet: nur so laesst sich ``PYTHONHASHSEED`` variieren, und nur so
faellt auf, wenn irgendwo eine Menge oder ein Hash die Reihenfolge bestimmt.
Innerhalb eines Prozesses ist der Streuwert fest -- ein Test, der bloss zweimal
dieselbe Funktion ruft, wuerde genau diese Klasse Fehler nie sehen.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rechenkern import (  # noqa: E402
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    Zahlung,
    rechne,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)


def baue_vorgang() -> Vorgang:
    """Ein Fall mit allem, was Reihenfolge haben kann.

    Drei Rechnungen in drei Kategorien, eine davon nach Zaehler, dazu ein
    Haupt- und zwei Unterzaehler mit je zwei Staenden und vier Zahlungen.
    """
    hausmeister = Kategorie(id=1, name='Hausmeister', braucht_zaehler=False)
    wasser = Kategorie(id=2, name='Wasser', braucht_zaehler=True)
    muell = Kategorie(id=3, name='Muell', braucht_zaehler=False)

    meine = Wohnung(id=1, name='EG links', qm=50.0)
    andere = Wohnung(id=2, name='EG rechts', qm=30.0)
    dritte = Wohnung(id=3, name='OG', qm=20.0)

    ich = Mieter(id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None, wohnung_id=1)
    du = Mieter(id=2, name='Bert Mieter', einzug=date(2020, 1, 1), auszug=None, wohnung_id=2)

    def staende(a, b):
        return (Stand(datum=JAHR_BEGINN, wert=a), Stand(datum=JAHR_ENDE, wert=b))

    return Vorgang(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(meine, andere, dritte),
        mieter_der_immobilie=(ich, du),
        profile={2: 'direkt'},
        rechnungen=(
            Rechnung(id=1, kategorie=hausmeister, betrag=Decimal('1000.00'),
                     beginn=JAHR_BEGINN, ende=JAHR_ENDE),
            Rechnung(id=2, kategorie=wasser, betrag=Decimal('333.33'),
                     beginn=JAHR_BEGINN, ende=JAHR_ENDE),
            Rechnung(id=3, kategorie=muell, betrag=Decimal('77.77'),
                     beginn=JAHR_BEGINN, ende=JAHR_ENDE),
        ),
        zaehler=(
            Zaehler(id=1, nummer='H-1', kategorie_id=2, kategorie_name='Wasser',
                    ist_hauptzaehler=True, immobilie_id=1, wohnung_id=None,
                    staende=staende(0.0, 300.0)),
            Zaehler(id=2, nummer='W-1', kategorie_id=2, kategorie_name='Wasser',
                    ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                    staende=staende(0.0, 100.0)),
            Zaehler(id=3, nummer='W-2', kategorie_id=2, kategorie_name='Wasser',
                    ist_hauptzaehler=False, immobilie_id=1, wohnung_id=2,
                    staende=staende(0.0, 170.0)),
        ),
        zahlungen=(
            Zahlung(datum=date(2024, 3, 1), betrag=Decimal('100.00')),
            Zahlung(datum=date(2024, 6, 1), betrag=Decimal('100.00')),
            Zahlung(datum=date(2024, 9, 1), betrag=Decimal('100.00')),
            Zahlung(datum=date(2024, 12, 1), betrag=Decimal('100.00')),
        ),
        wasser_kategorie_id=2,
    )


def als_json(ergebnis) -> str:
    """Das Blatt als Zeichenkette -- Reihenfolge der Schluessel eingeschlossen.

    ``sort_keys`` bleibt aus: gerade die Reihenfolge ist Teil der Zusage. Und
    ``default=str`` statt ``float``, damit ``Decimal('1.0')`` und
    ``Decimal('1.00')`` als verschieden auffallen; ueber die JSON-Grenze der
    Oberflaeche gehen Betraege als Zahl (D-15), hier zaehlt die Stelle mit.
    """
    return json.dumps(ergebnis, default=str, ensure_ascii=False, sort_keys=False)


if __name__ == '__main__':
    sys.stdout.write(als_json(rechne(baue_vorgang())))
