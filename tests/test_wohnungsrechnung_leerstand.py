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
    """F-128: den Leerstand zeigt die Abrechnung, deren Zeitraum ihn umfasst.

    Mieter 1 wird ab Einzug abgerechnet; Januar bis März steht beim Nachbarn,
    der das ganze Jahr abgerechnet wird. Zusammen ergibt es die Rechnung.
    """
    ergebnis = rechne(_vorgang())
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('900.00')
    assert not ergebnis['landlord_share']['positions']
    anteil = rechne(_nachbar(mit_einzug=True))['landlord_share']
    assert anteil['total_amount'] == Decimal('300.00')
    assert 'Wohnung 1' in anteil['positions'][0]['description']


def test_ohne_zaehler_nach_tagen():
    """90 von 365 Tagen leer: 1200 × 90/365 = 295,89 EUR (F-128: beim Nachbarn)."""
    mieter = rechne(_vorgang(mit_zaehler=False))['line_items'][0]['tenant_cost']
    leer = rechne(_nachbar(mit_zaehler=False, mit_einzug=True))['landlord_share']['total_amount']
    assert leer == Decimal('295.89')
    assert mieter + leer == Decimal('1200.00')


def test_vormieter_ist_kein_leerstand():
    """Wohnte vor dem Einzug jemand dort, zahlt er -- der Vermieter trägt nichts."""
    ergebnis = rechne(_vorgang(vormieter=True))
    assert not ergebnis['landlord_share']['positions']


def test_vormieter_zahlt_den_rest():
    vorgang = _vorgang(vormieter=True)
    vormieter = replace(vorgang, mieter=vorgang.mieter_der_immobilie[1],
                        beginn=BEGINN, ende=date(2025, 3, 31))
    assert rechne(vormieter)['line_items'][0]['tenant_cost'] == Decimal('300.00')


def _nachbar(mit_zaehler=True, mit_einzug=False):
    """Wohnung 1 steht das ganze Jahr leer (``mit_einzug``: bis zum Einzug von
    Mieter 1); abgerechnet wird der Mieter von Wohnung 2."""
    vorgang = _vorgang(mit_zaehler)
    zwei = Wohnung(id=2, name='Wohnung 2', qm=70.0)
    nachbar = Mieter(id=3, name='Mieter 3', einzug=BEGINN, auszug=None, wohnung_id=2)
    return replace(vorgang, mieter=nachbar, wohnung=zwei, beginn=BEGINN,
                   wohnungen=(vorgang.wohnung, zwei),
                   mieter_der_immobilie=(nachbar,) + ((vorgang.mieter,) if mit_einzug else ()))


def test_leere_wohnung_steht_in_jeder_abrechnung_des_hauses():
    """Die Rechnung der leeren Wohnung trägt niemand als der Vermieter.

    Vorher stand sie in keiner Abrechnung: die Abrechnung der Wohnung gab es
    nicht, und jede andere übersprang die Rechnung samt Vermieteranteil.
    """
    ergebnis = rechne(_nachbar())
    assert not ergebnis['line_items']
    assert ergebnis['landlord_share']['total_amount'] == Decimal('1200.00')


def test_leere_wohnung_ohne_zaehler():
    assert rechne(_nachbar(mit_zaehler=False))['landlord_share']['total_amount'] == Decimal('1200.00')
