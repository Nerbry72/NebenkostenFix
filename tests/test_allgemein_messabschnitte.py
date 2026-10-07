"""NK-213 (B6): der Allgemeinverbrauch wird nur zwischen Ablesungen gemessen.

Befund der App-Analyse vom 2026-10-06: Beim Mieterwechsel trug der
Ausziehende keinen Allgemeinanteil. F-122 schnitt das Jahr an jedem Einzug und
Auszug in Abschnitte und mass dort. Der Wohnungszaehler war am Wechseltag
abgelesen, der Hauptzaehler nicht -- er wurde geschaetzt. Lief der Verbrauch
der Wohnung im ersten Halbjahr hoeher als im Schnitt, mass der Abschnitt des
Ausziehenden negativ, zaehlte als null, und die anderen trugen seinen Anteil.

Jetzt zerfaellt die Rechnung nur an Tagen, an denen der Haupt- und alle
Wohnungszaehler einen Stand haben. Innerhalb eines Abschnitts geht der
Allgemeinverbrauch nach Personentagen.

*Haette den Fehler gefunden:* ``test_ausziehende_traegt_ihre_mietzeit`` --
vorher 450,00 EUR statt 474,79 EUR fuer Anna.

Die Daten sind synthetisch, jede Zahl ist von Hand nachgerechnet.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from nebenkostenfix.heizung import ZWISCHENABLESUNG
from nebenkostenfix.rechenkern import (
    Kategorie, Mieter, Rechnung, Stand, Vorgang, Wohnung, Zaehler, rechne)

BEGINN = date(2025, 1, 1)
WECHSEL = date(2025, 7, 1)
ENDE = date(2025, 12, 31)
GRENZE = date(2026, 1, 1)
WASSER = Kategorie(id=2, name='Frischwasser', braucht_zaehler=True)


def _zaehler(id, staende, wohnung_id=None):
    return Zaehler(id=id, nummer=f'Z-{id}', kategorie_id=2, kategorie_name='Frischwasser',
                   ist_hauptzaehler=wohnung_id is None, immobilie_id=1,
                   wohnung_id=wohnung_id, staende=tuple(staende))


def _welt(wer, haupt_am_wechsel=None):
    """1000 EUR fuer 100 m³, also 10 EUR je m³.

    Wohnung 1: Anna bis 30.06., Carl ab 01.07.; ihr Zaehler wurde am
    Wechseltag abgelesen (0 / 45 / 60 m³). Wohnung 2: Bert das ganze Jahr,
    0 -> 30 m³. Der Hauptzaehler steht nur an den Jahresenden (0 -> 100 m³),
    ausser ``haupt_am_wechsel`` gibt ihm einen Stand am 01.07. Allgemein im
    Jahr: 100 − 90 = 10 m³ = 100 EUR. Personentage: Anna 181, Carl 184,
    Bert 365, zusammen 730.
    """
    wohnungen = (Wohnung(id=1, name='Wohnung 1', qm=50.0),
                 Wohnung(id=2, name='Wohnung 2', qm=50.0))
    mieter = (Mieter(id=1, name='Anna', einzug=BEGINN, auszug=WECHSEL, wohnung_id=1),
              Mieter(id=2, name='Carl', einzug=WECHSEL, auszug=None, wohnung_id=1),
              Mieter(id=3, name='Bert', einzug=BEGINN, auszug=None, wohnung_id=2))
    haupt = [Stand(BEGINN, 0.0), Stand(GRENZE, 100.0)]
    if haupt_am_wechsel is not None:
        haupt.insert(1, Stand(WECHSEL, haupt_am_wechsel))
    vorgang = Vorgang(
        mieter=mieter[wer], wohnung=wohnungen[mieter[wer].wohnung_id - 1], immobilie_id=1,
        immobilie_name='Hauptstrasse 1', beginn=BEGINN, ende=ENDE,
        wohnungen=wohnungen, mieter_der_immobilie=mieter,
        profile={WASSER.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=WASSER, betrag=Decimal('1000.00'),
                             beginn=BEGINN, ende=ENDE),),
        zaehler=(_zaehler(10, haupt),
                 _zaehler(11, (Stand(BEGINN, 0.0), Stand(WECHSEL, 45.0, art=ZWISCHENABLESUNG),
                               Stand(GRENZE, 60.0)), 1),
                 _zaehler(12, (Stand(BEGINN, 0.0), Stand(GRENZE, 30.0)), 2)),
    )
    if wer == 0:
        return replace(vorgang, ende=date(2025, 6, 30))
    if wer == 1:
        return replace(vorgang, beginn=WECHSEL)
    return vorgang


def _zeilen(**welt):
    return [rechne(_welt(wer, **welt)) for wer in (0, 1, 2)]


def test_ausziehende_traegt_ihre_mietzeit():
    """Anna: 45 m³ eigen = 450 EUR, allgemein 100 EUR · 181/730 = 24,79 EUR.

    Vorher: der Hauptzaehler im ersten Halbjahr geschaetzt (49,6 m³) gegen
    Annas abgelesene 45 und Berts geschaetzte 14,9 m³ -- negativ, null.
    """
    posten = rechne(_welt(0))['line_items'][0]
    assert posten['tenant_cost'] == Decimal('474.79')
    assert posten['sub_items'][1]['cost'] == Decimal('24.79')
    assert 'Anteil: 181 von 730 Personentagen' in posten['description']
    assert 'Abschnitten' not in posten['description']


def test_jeder_traegt_nach_personentagen():
    """Carl 100 · 184/730 = 25,21 EUR, Bert 100 · 365/730 = 50,00 EUR.

    Vorher: Carl 50,00 EUR, Bert 50,00 EUR -- die Summe stimmte auch damals,
    deshalb zaehlen die einzelnen Zeilen.
    """
    zeilen = _zeilen()
    allgemein = [z['line_items'][0]['sub_items'][1]['cost'] for z in zeilen]
    assert allgemein == [Decimal('24.79'), Decimal('25.21'), Decimal('50.00')]
    assert [z['line_items'][0]['tenant_cost'] for z in zeilen] == [
        Decimal('474.79'), Decimal('175.21'), Decimal('350.00')]


def test_die_rechnung_geht_auf_ohne_warnung():
    zeilen = _zeilen()
    assert sum(z['line_items'][0]['tenant_cost'] for z in zeilen) == Decimal('1000.00')
    assert all(z['landlord_share']['total_amount'] == 0 for z in zeilen)
    assert not [w for z in zeilen for w in z['warnings'] if 'ALLGEMEIN-NEGATIV' in w]


def test_zaehlerdetails_zeigen_die_rechnung_und_den_anteil():
    """Haus 100 m³, Wohnungen 90 m³, allgemein 10 m³; Annas Anteil 181/730."""
    details = rechne(_welt(0))['line_items'][0]['meter_details']
    assert (details['main_consumption'], details['sum_sub_consumption'],
            details['allgemein_consumption']) == (100.0, 90.0, 10.0)
    assert details['allgemein_quote'] == round(181 / 730, 6)
    assert details['allgemein_anteil'] == 2.5


def test_ein_stand_am_hauptzaehler_allein_teilt_nicht():
    """Der Hauptzaehler steht am 01.07. auf 55, Bert hat dort keinen Stand.
    Ohne gemeinsame Ablesung bleibt es ein Abschnitt: dieselben Zahlen."""
    posten = rechne(_welt(0, haupt_am_wechsel=55.0))['line_items'][0]
    assert posten['tenant_cost'] == Decimal('474.79')
    assert 'Abschnitten' not in posten['description']


def test_alle_am_wechsel_abgelesen_misst_je_halbjahr():
    """Alle Zaehler am 01.07.: Haupt 55, Wohnung 1 45, Bert 10 m³.

    Erstes Halbjahr allgemein 55 − 55 = 0 m³, zweites 45 − 15 − 20 = 10 m³.
    Anna wohnte nur im ersten: kein Allgemeinanteil, gemessen und keine
    Schaetzung. Carl traegt 184 von 368 Personentagen des zweiten
    Halbjahrs: 50 EUR, Bert ebenso.
    """
    bert = _zaehler(12, (Stand(BEGINN, 0.0), Stand(WECHSEL, 10.0), Stand(GRENZE, 30.0)), 2)

    def mit_bert(wer):
        v = _welt(wer, haupt_am_wechsel=55.0)
        return replace(v, zaehler=v.zaehler[:2] + (bert,))

    zeilen = [rechne(mit_bert(wer))['line_items'][0] for wer in (0, 1, 2)]
    assert [z['sub_items'][1]['cost'] for z in zeilen] == [
        Decimal('0.00'), Decimal('50.00'), Decimal('50.00')]
    assert 'gemessen in 2 Abschnitten zwischen gemeinsamen Ablesungen: 50,00 %' in zeilen[1]['description']
