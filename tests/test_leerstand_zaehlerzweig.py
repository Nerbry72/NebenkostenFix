"""F-120/F-121: der Zählerzweig weist den Leerstand beim Vermieter aus.

Gefunden bei der Praxisprobe (NK-187): ein Haus mit Hauptzähler, Unterzählern
je Wohnung und einer Wohnung, die leer steht. Zwei Lücken im Zählerzweig:

- **F-121** -- der Allgemeinverbrauch (Hauptzähler minus Unterzähler) wurde
  nach den Personentagen der Mietverhältnisse verteilt. Die leere Wohnung
  stand nicht im Nenner, ihr Anteil landete still bei den Mietern -- derselbe
  Fehler wie F-34 beim Personenschlüssel, nur im Zählerzweig übrig geblieben.
- **F-120** -- der eigene Verbrauch am Unterzähler der leeren Wohnung wurde
  niemandem berechnet und stand auch nicht im Vermieteranteil. Die Kosten
  verschwanden zwischen den Zeilen (R-NUM-05).

Seit dem Fix zählt die leere Wohnung im Allgemein-Nenner wie ein
Einpersonenhaushalt (wie NK-098), und beide Anteile stehen als
Vermieterpositionen in der Abrechnung. Die Aufgeh-Probe: alle Mieterzeilen
plus der Vermieteranteil ergeben die Rechnung.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from nebenkostenfix.leerstand import EIGENNUTZUNG, LEERSTAND
from nebenkostenfix.rechenkern import (
    Kategorie, Mieter, Rechnung, Stand, Vorgang, Wohnung, Zaehler, rechne)

BEGINN = date(2025, 1, 1)
ENDE = date(2025, 12, 31)
GRENZE = date(2026, 1, 1)
WASSER = Kategorie(id=2, name='Frischwasser', braucht_zaehler=True)


def _zaehler(id, staende, wohnung_id=None):
    return Zaehler(id=id, nummer=f'Z-{id}', kategorie_id=2, kategorie_name='Frischwasser',
                   ist_hauptzaehler=wohnung_id is None, immobilie_id=1,
                   wohnung_id=wohnung_id, staende=tuple(staende))


def _welt(wer, dritter_ab=None, eigennutzung_dritte=False):
    """Drei Wohnungen, 1000,00 EUR für 100 m³, also 10 EUR je m³.

    Wohnung 1 und 2 verbrauchen je 30 m³, Wohnung 3 10 m³; allgemein bleiben
    30 m³ = 300 EUR. ``dritter_ab`` vermietet Wohnung 3 ab diesem Tag; ihr
    Zähler steht dann dort auf 4 m³.
    """
    wohnungen = (Wohnung(id=1, name='Wohnung 1', qm=50.0),
                 Wohnung(id=2, name='Wohnung 2', qm=50.0),
                 Wohnung(id=3, name='Wohnung 3', qm=50.0, eigennutzung=eigennutzung_dritte))
    mieter = (Mieter(id=1, name='Mieter 1', einzug=BEGINN, auszug=None, wohnung_id=1),
              Mieter(id=2, name='Mieter 2', einzug=BEGINN, auszug=None, wohnung_id=2))
    dritte = [Stand(BEGINN, 0.0), Stand(GRENZE, 10.0)]
    if dritter_ab:
        mieter += (Mieter(id=3, name='Mieter 3', einzug=dritter_ab, auszug=None, wohnung_id=3),)
        dritte.insert(1, Stand(dritter_ab, 4.0))
    return Vorgang(
        mieter=mieter[wer - 1], wohnung=wohnungen[wer - 1], immobilie_id=1,
        immobilie_name='Hauptstrasse 1', beginn=BEGINN, ende=ENDE,
        wohnungen=wohnungen, mieter_der_immobilie=mieter,
        profile={WASSER.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=WASSER, betrag=Decimal('1000.00'),
                             beginn=BEGINN, ende=ENDE),),
        zaehler=(_zaehler(10, [Stand(BEGINN, 0.0), Stand(GRENZE, 100.0)]),
                 _zaehler(11, [Stand(BEGINN, 0.0), Stand(GRENZE, 30.0)], 1),
                 _zaehler(12, [Stand(BEGINN, 0.0), Stand(GRENZE, 30.0)], 2),
                 _zaehler(13, dritte, 3)),
    )


def test_leere_wohnung_steht_im_allgemein_nenner():
    """F-121: jeder Mieter trägt ein Drittel des Allgemeinen, nicht die Hälfte.

    Vorher: 300 EUR allgemein durch 730 Personentage, je Mieter 150 EUR.
    """
    ergebnis = rechne(_welt(wer=1))
    posten = ergebnis['line_items'][0]
    assert posten['tenant_cost'] == Decimal('400.00')  # 300 eigen + 100 allgemein
    assert '365 von 1095 Personentagen' in posten['description']


def test_vermieter_traegt_allgemeinanteil_und_eigenverbrauch_der_leeren_wohnung():
    """F-120 und F-121: beides steht als Vermieteranteil in der Abrechnung."""
    anteil = rechne(_welt(wer=1))['landlord_share']
    assert anteil['total_amount'] == Decimal('200.00')
    assert anteil['leerstand_amount'] == Decimal('200.00')
    betraege = sorted(p['amount'] for p in anteil['positions'])
    assert betraege == [Decimal('100.00'), Decimal('100.00')]
    assert all('Wohnung 3' in p['description'] for p in anteil['positions'])


def test_die_rechnung_geht_auf():
    """Beide Mieter plus Vermieter ergeben die 1000,00 EUR der Rechnung."""
    erster, zweiter = rechne(_welt(wer=1)), rechne(_welt(wer=2))
    assert (erster['line_items'][0]['tenant_cost']
            + zweiter['line_items'][0]['tenant_cost']
            + erster['landlord_share']['total_amount']) == Decimal('1000.00')


def test_eigennutzung_traegt_der_vermieter_ebenso():
    anteil = rechne(_welt(wer=1, eigennutzung_dritte=True))['landlord_share']
    assert anteil['eigennutzung_amount'] == Decimal('200.00')
    assert all(u['reason'] == EIGENNUTZUNG
               for p in anteil['positions'] for u in p['units'])


def test_einzug_im_jahr_nimmt_die_gemessene_menge():
    """Wohnung 3 ab 02.07. vermietet, Ablesung am Einzugstag: 4 m³ leer, 6 m³ belegt.

    Der Mieter zahlt, was sein Zähler ab Einzug misst (6 m³). Der Vermieter
    trägt genau den Rest (4 m³ = 40 EUR) -- nicht die zeitanteilige Schätzung
    (10 m³ × 182/365 = 49,86 EUR), die mit der Mieterzeile nicht zusammenpasst.
    """
    einzug = date(2025, 7, 2)
    dritter = rechne(replace(_welt(wer=3, dritter_ab=einzug), beginn=einzug))
    assert 'Eigenverbrauch (6.0 m³)' in dritter['line_items'][0]['description']
    vermieter = rechne(_welt(wer=1, dritter_ab=einzug))['landlord_share']
    eigen = [p for p in vermieter['positions'] if 'vermieter_consumption' in p]
    assert [p['amount'] for p in eigen] == [Decimal('40.00')]
    assert eigen[0]['units'][0]['reason'] == LEERSTAND
