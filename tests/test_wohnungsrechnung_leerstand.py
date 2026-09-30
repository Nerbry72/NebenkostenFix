"""F-123: der Leerstand einer Wohnungsrechnung steht beim Vermieter.

Gefunden bei der Praxisprobe (NK-187): eine Gasrechnung, die nur einer
Wohnung gehört, läuft ab Januar; der Mieter zieht erst im April ein. Er zahlt,
was sein Zähler ab Einzug misst (F-114). Der Verbrauch davor zahlte niemand,
und er stand auch nicht im Vermieteranteil -- er verschwand zwischen den
Zeilen (R-NUM-05). Seit dem Fix steht er dort, gemessen am Zähler der
Wohnung; ohne Zähler nach Tagen.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from nebenkostenfix.rechenkern import (
    Kategorie, Mieter, Rechnung, Stand, Vorgang, Wohnung, Zaehler, rechne)

BEGINN = date(2025, 1, 1)
EINZUG = date(2025, 4, 1)
ENDE = date(2025, 12, 31)
GRENZE = date(2026, 1, 1)
GAS = Kategorie(id=5, name='Gas', braucht_zaehler=True)


def _vorgang(mit_zaehler=True, vormieter=False):
    """1200,00 EUR Gas für Wohnung 1; der Zähler misst 300 bis April, 900 danach."""
    wohnung = Wohnung(id=1, name='Wohnung 1', qm=50.0)
    mieter = Mieter(id=1, name='Mieter 1', einzug=EINZUG, auszug=None, wohnung_id=1)
    alle = (mieter,)
    if vormieter:
        alle += (Mieter(id=2, name='Mieter 2', einzug=BEGINN, auszug=EINZUG, wohnung_id=1),)
    zaehler = (Zaehler(id=10, nummer='Z-10', kategorie_id=5, kategorie_name='Gas',
                       ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                       staende=(Stand(BEGINN, 0.0), Stand(EINZUG, 300.0),
                                Stand(GRENZE, 1200.0))),)
    return Vorgang(
        mieter=mieter, wohnung=wohnung, immobilie_id=1, immobilie_name='Hauptstrasse 1',
        beginn=EINZUG, ende=ENDE, wohnungen=(wohnung,), mieter_der_immobilie=alle,
        profile={GAS.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=GAS, betrag=Decimal('1200.00'),
                             beginn=BEGINN, ende=ENDE, wohnung_id=1),),
        zaehler=zaehler if mit_zaehler else (),
    )


def test_verbrauch_vor_einzug_traegt_der_vermieter():
    ergebnis = rechne(_vorgang())
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('900.00')
    anteil = ergebnis['landlord_share']
    assert anteil['total_amount'] == Decimal('300.00')
    assert 'Wohnung 1' in anteil['positions'][0]['description']


def test_ohne_zaehler_nach_tagen():
    """90 von 365 Tagen leer: 1200 × 90/365 = 295,89 EUR."""
    ergebnis = rechne(_vorgang(mit_zaehler=False))
    assert (ergebnis['line_items'][0]['tenant_cost']
            + ergebnis['landlord_share']['total_amount']) == Decimal('1200.00')
    assert ergebnis['landlord_share']['total_amount'] == Decimal('295.89')


def test_vormieter_ist_kein_leerstand():
    """Wohnte vor dem Einzug jemand dort, zahlt er -- der Vermieter trägt nichts."""
    ergebnis = rechne(_vorgang(vormieter=True))
    assert not ergebnis['landlord_share']['positions']


def test_vormieter_zahlt_den_rest():
    vorgang = _vorgang(vormieter=True)
    vormieter = replace(vorgang, mieter=vorgang.mieter_der_immobilie[1],
                        beginn=BEGINN, ende=date(2025, 3, 31))
    assert rechne(vormieter)['line_items'][0]['tenant_cost'] == Decimal('300.00')
