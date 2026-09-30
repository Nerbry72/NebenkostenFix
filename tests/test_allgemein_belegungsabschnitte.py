"""F-122: der Allgemeinverbrauch wird je Belegungsabschnitt verteilt.

Gefunden bei der Praxisprobe (NK-187): Allgemeinstrom, eine Wohnung steht bis
zur Jahresmitte leer, danach zieht jemand ein. Seit NK-097 misst die Abrechnung
des neuen Mieters den Allgemeinverbrauch in **seinem** Zeitraum. Der
Vermieteranteil am Leerstand aber rechnete mit dem Jahresdurchschnitt -- und
wo der Verbrauch im ersten Halbjahr höher lag, blieb die Differenz bei
niemandem: Mieter plus Vermieter ergaben nicht die Rechnung.

Seit dem Fix gilt für jeden, der am Allgemeinverbrauch trägt, dieselbe Regel:
das Jahr zerfällt an jedem Einzug, Auszug und jeder Änderung der
Haushaltsgröße in Abschnitte gleicher Belegung. In jedem Abschnitt wird der
Allgemeinverbrauch gemessen und nach Personentagen geteilt. Bleibt die
Belegung gleich, ist das dieselbe Rechnung wie vorher.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from nebenkostenfix.haushalt import Stand as Haushaltsstand
from nebenkostenfix.rechenkern import (
    Kategorie, Mieter, Rechnung, Stand, Vorgang, Wohnung, Zaehler, rechne)

BEGINN = date(2025, 1, 1)
MITTE = date(2025, 7, 1)
ENDE = date(2025, 12, 31)
GRENZE = date(2026, 1, 1)
WASSER = Kategorie(id=2, name='Frischwasser', braucht_zaehler=True)


def _zaehler(id, staende, wohnung_id=None):
    return Zaehler(id=id, nummer=f'Z-{id}', kategorie_id=2, kategorie_name='Frischwasser',
                   ist_hauptzaehler=wohnung_id is None, immobilie_id=1,
                   wohnung_id=wohnung_id,
                   staende=tuple(Stand(d, s) for d, s in zip((BEGINN, MITTE, GRENZE), staende)))


def _welt(wer, haushalt_erster=()):
    """1000,00 EUR für 100 m³, also 10 EUR je m³; alle Zähler am 01.07. abgelesen.

    Wohnung 3 steht bis 30.06. leer (4 m³), ab 01.07. wohnt Mieter 3 dort.
    Allgemein: erstes Halbjahr 24 m³ (240 EUR), zweites 6 m³ (60 EUR).
    """
    wohnungen = tuple(Wohnung(id=i, name=f'Wohnung {i}', qm=50.0) for i in (1, 2, 3))
    mieter = (Mieter(id=1, name='Mieter 1', einzug=BEGINN, auszug=None, wohnung_id=1,
                     haushaltsgroessen=tuple(haushalt_erster)),
              Mieter(id=2, name='Mieter 2', einzug=BEGINN, auszug=None, wohnung_id=2),
              Mieter(id=3, name='Mieter 3', einzug=MITTE, auszug=None, wohnung_id=3))
    vorgang = Vorgang(
        mieter=mieter[wer - 1], wohnung=wohnungen[wer - 1], immobilie_id=1,
        immobilie_name='Hauptstrasse 1', beginn=BEGINN, ende=ENDE,
        wohnungen=wohnungen, mieter_der_immobilie=mieter,
        profile={WASSER.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=WASSER, betrag=Decimal('1000.00'),
                             beginn=BEGINN, ende=ENDE),),
        zaehler=(_zaehler(10, (0.0, 48.0, 100.0)),
                 _zaehler(11, (0.0, 10.0, 30.0), 1),
                 _zaehler(12, (0.0, 10.0, 30.0), 2),
                 _zaehler(13, (0.0, 4.0, 10.0), 3)),
    )
    return replace(vorgang, beginn=MITTE) if wer == 3 else vorgang


def _summe(haushalt_erster=()):
    """Alle drei Mieterzeilen plus der Vermieteranteil."""
    ergebnisse = [rechne(_welt(wer, haushalt_erster)) for wer in (1, 2, 3)]
    mieter = sum(e['line_items'][0]['tenant_cost'] for e in ergebnisse)
    return mieter + ergebnisse[0]['landlord_share']['total_amount'], ergebnisse


def test_vermieter_traegt_den_gemessenen_leerstand():
    """Wohnung 3 steht im teuren Halbjahr leer: ein Drittel von 240 EUR.

    Vorher: 300 EUR × 181/1095 Personentage = 49,59 EUR.
    """
    anteil = rechne(_welt(wer=1))['landlord_share']
    allgemein = [p for p in anteil['positions'] if 'Allgemeinverbrauch' in p['category']]
    assert [p['amount'] for p in allgemein] == [Decimal('80.00')]


def test_die_rechnung_geht_auf():
    summe, ergebnisse = _summe()
    assert [e['line_items'][0]['tenant_cost'] for e in ergebnisse] == [
        Decimal('400.00'), Decimal('400.00'), Decimal('80.00')]  # je 100 bzw. 20 allgemein
    assert summe == Decimal('1000.00')


def test_haushalt_waechst_zur_jahresmitte():
    """Mieter 1 lebt erst allein, ab 01.07. zu dritt.

    Erstes Halbjahr: ein Drittel von 240 EUR = 80 EUR; zweites: drei Fünftel
    von 60 EUR = 36 EUR. Vorher: 300 EUR × 733/1463 = 150,31 EUR.
    """
    summe, ergebnisse = _summe([Haushaltsstand(BEGINN, 1), Haushaltsstand(MITTE, 3)])
    assert ergebnisse[0]['line_items'][0]['tenant_cost'] == Decimal('416.00')  # 300 + 116
    assert summe == Decimal('1000.00')


def test_gleiche_belegung_bleibt_beim_alten():
    """Ohne Wechsel ist ein Abschnitt das ganze Jahr -- wie vor dem Fix."""
    ohne_dritten = replace(_welt(wer=1), mieter_der_immobilie=_welt(wer=1).mieter_der_immobilie[:2])
    posten = rechne(ohne_dritten)['line_items'][0]
    assert '365 von 1095 Personentagen' in posten['description']
    assert posten['tenant_cost'] == Decimal('400.00')  # 300 eigen + 100 allgemein
