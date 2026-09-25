"""NK-049: die Heizkosten nach § 7 HeizkostenV -- 50 bis 70 nach Verbrauch.

Die Faelle hier laufen ohne Datenbank, wie der ganze Kern seit NK-037. Sie
pruefen die Verteilung selbst: den Satz, die beiden Massen, den Nenner, was
bei fehlender Erfassung geschieht und was beim Vermieter bleibt.

Die Zahlen sind mit der Hand nachgerechnet und stehen im jeweiligen
Docstring -- nicht, weil der Rechner sie so ausgibt, sondern weil die
Vorschrift sie so verlangt.
"""

from datetime import date
from decimal import Decimal

import pytest

import heizung
from rechenkern import (
    BillingDataError,
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    anlagen_wohnungen,
    heizkosten_abtrennen,
    rechne,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)

WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True)


def anlage(id=1, name='Zentralheizung', prozent=70, **kw):
    return Heizungsanlage(
        id=id, name=name, verbrauchsanteil_prozent=prozent, **kw)


def heizrechnung(betrag='10000.00', id=1, anlage_id=1,
                 art='brennstoff', beginn=JAHR_BEGINN, ende=JAHR_ENDE):
    return Rechnung(
        id=id,
        kategorie=WAERME,
        betrag=Decimal(betrag),
        beginn=beginn,
        ende=ende,
        heizungsanlage_id=anlage_id,
        heizkostenart=art,
    )


def waermezaehler(id, wohnung_id, verbraucht, anlage_id=1,
                  beginn=JAHR_BEGINN, ende=date(2025, 1, 1)):
    return Zaehler(
        id=id,
        nummer=f'W-{id}',
        kategorie_id=WAERME.id,
        kategorie_name='Waerme',
        ist_hauptzaehler=False,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=(Stand(datum=beginn, wert=0.0), Stand(datum=ende, wert=verbraucht)),
        heizungsanlage_id=anlage_id,
    )


def haus(rechnungen=(), zaehler=(), anlagen=(), mieter=None, wohnungen=None,
         **kw):
    """Zwei Wohnungen zu 50 qm, mein Mieter wohnt in der linken."""
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    andere = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = mieter or Mieter(
        id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=1)
    nachbar = Mieter(
        id=2, name='Bert Nachbar', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=2)
    grund = dict(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=tuple(wohnungen if wohnungen is not None else (meine, andere)),
        mieter_der_immobilie=(ich, nachbar),
        profile={},
        rechnungen=tuple(rechnungen),
        zaehler=tuple(zaehler),
        heizungsanlagen=tuple(anlagen or (anlage(),)),
    )
    grund.update(kw)
    return Vorgang(**grund)


def heizzeile(ergebnis):
    zeilen = [z for z in ergebnis['line_items'] if z['billing_type'] == 'heizkosten']
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


# --- Die Verteilung selbst -------------------------------------------------


def test_siebzig_zu_dreissig():
    """10.000 Euro, 70 Prozent nach Verbrauch: 4.200 + 1.500 = 5.700.

    Verbrauchsteil 7.000, davon 1.200 von 2.000 kWh = 4.200.
    Grundteil 3.000, davon 50 von 100 qm = 1.500.
    """
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('5700.00')
    assert [p['cost'] for p in zeile['sub_items']] == [
        Decimal('4200.00'), Decimal('1500.00')]
    assert ergebnis['total_amount'] == Decimal('5700.00')


def test_fuenfzig_zu_fuenfzig():
    """Derselbe Fall mit dem unteren Rand des § 7 Abs. 1: 3.000 + 2.500."""
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        anlagen=(anlage(prozent=50),),
    ))
    zeile = heizzeile(ergebnis)

    assert [p['cost'] for p in zeile['sub_items']] == [
        Decimal('3000.00'), Decimal('2500.00')]
    assert zeile['tenant_cost'] == Decimal('5500.00')


def test_beide_mieter_zusammen_tragen_die_ganze_masse():
    """Was der eine nicht traegt, traegt der andere -- kein Cent bleibt liegen."""
    zaehler = (waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0))
    eins = rechne(haus(rechnungen=(heizrechnung(),), zaehler=zaehler))

    nachbar = Mieter(id=2, name='Bert Nachbar', einzug=date(2020, 1, 1),
                     auszug=None, wohnung_id=2)
    zwei = rechne(haus(
        rechnungen=(heizrechnung(),), zaehler=zaehler, mieter=nachbar,
        wohnung=Wohnung(id=2, name='EG rechts', qm=50.0),
    ))

    assert eins['total_amount'] + zwei['total_amount'] == Decimal('10000.00')


def test_acht_posten_werden_zu_einer_masse():
    """§ 7 Abs. 2 zaehlt acht Posten auf -- verteilt wird ihre Summe.

    Brennstoff 8.000, Betriebsstrom 1.000, Wartung 1.000: zusammen 10.000,
    und damit dieselben 5.700 wie bei einer einzigen Rechnung.
    """
    ergebnis = rechne(haus(
        rechnungen=(
            heizrechnung('8000.00', id=1, art='brennstoff'),
            heizrechnung('1000.00', id=2, art='betriebsstrom'),
            heizrechnung('1000.00', id=3, art='bedienung'),
        ),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('5700.00')
    assert zeile['total_amount'] == Decimal('10000.00')
    assert len(zeile['heizung_details']['rechnungen']) == 3
    assert zeile['provider_name'] == '3 Rechnungen'


def test_unterposten_addieren_sich_zur_zeile():
    """Die Restcent-Regel gilt auch hier (R-NUM-02)."""
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung('999.99'),),
        zaehler=(waermezaehler(1, 1, 1000.0), waermezaehler(2, 2, 3000.0)),
        anlagen=(anlage(prozent=65),),
    ))
    zeile = heizzeile(ergebnis)

    assert sum(p['cost'] for p in zeile['sub_items']) == zeile['tenant_cost']


# --- Das Kostenprofil tritt zurueck (D-46) ---------------------------------


def test_profil_aendert_die_verteilung_nicht():
    """§ 7 HeizkostenV ist zwingend -- 'personen' im Profil hilft nicht."""
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        profile={WAERME.id: 'personen'},
    ))

    assert heizzeile(ergebnis)['tenant_cost'] == Decimal('5700.00')


def test_ignoriert_bleibt_wirksam():
    """Der Verzicht des Vermieters geht nur zu seinen Lasten -- er gilt."""
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        profile={WAERME.id: 'ignoriert'},
    ))

    zeile, = ergebnis['line_items']
    assert zeile['billing_type'] == 'ignoriert'
    assert ergebnis['total_amount'] == Decimal('0.00')


def test_rechnung_ohne_anlage_laeuft_wie_bisher():
    """Ohne Zuordnung bleibt es eine gewoehnliche Kostenart."""
    ohne = Rechnung(id=1, kategorie=WAERME, betrag=Decimal('1000.00'),
                    beginn=JAHR_BEGINN, ende=JAHR_ENDE)
    ergebnis = rechne(haus(rechnungen=(ohne,)))

    assert [z['billing_type'] for z in ergebnis['line_items']] == ['qm']


def test_abtrennen_gibt_beide_haufen():
    vorgang = haus(rechnungen=(heizrechnung(), ))
    ohne = Rechnung(id=2, kategorie=Kategorie(id=1, name='Hausmeister',
                                              braucht_zaehler=False),
                    betrag=Decimal('100.00'), beginn=JAHR_BEGINN, ende=JAHR_ENDE)
    uebrig, je_anlage = heizkosten_abtrennen(
        vorgang, [vorgang.rechnungen[0], ohne])

    assert uebrig == [ohne]
    assert list(je_anlage) == [1]


# --- Fehlende Erfassung (D-48) ---------------------------------------------


def test_ohne_zaehler_alles_nach_flaeche():
    """Fehlt ein Zaehler, gibt es keinen ehrlichen Nenner: 5.000 nach qm.

    Gewarnt wird, und die Warnung nennt das Kuerzungsrecht des § 12 Abs. 1.
    """
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0),),
    ))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('5000.00')
    assert len(zeile['sub_items']) == 1
    assert zeile['heizung_details']['erfasst'] is False
    assert 'EG rechts' in zeile['heizung_details']['fehlgrund']
    assert any('§ 12 Abs. 1' in w for w in ergebnis['warnings'])


def test_kuerzungswarnung_nennt_ihre_kenung():
    """§ 12 Abs. 1 (NK-052, R-HK-05): ohne Verbrauchserfassung warnt die
    Abrechnung mit der Kennung W-HKV-KUERZUNG-15.

    Die Software kuerzt nicht selbst -- sie sagt dem Vermieter, dass der
    Mieter es darf. Die Warnung steht einmal je betroffener Verteilmasse
    und nennt Anlage und Verbrauchsart.
    """
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0),),
    ))

    hinweise = [w for w in ergebnis['warnings']
                if heizung.KUERZUNG_15 in w]
    assert len(hinweise) == 1
    assert '§ 12 Abs. 1' in hinweise[0]
    assert '15 %' in hinweise[0]
    assert 'Zentralheizung' in hinweise[0]
    assert 'Wärmeverbrauch' in hinweise[0]
    # Neben der § 12-Warnung bleibt die Zeilenwarnung stehen, die das
    # Missen der Erfassung selbst erklaert.
    assert any(w.startswith('Für die Heizungsanlage') for w in ergebnis['warnings'])


def test_erfasst_wird_nicht_ueber_kuerzung_gewarnt():
    """Voll erfasste Anlage: kein § 12-Warntext, auch wenn der Satz 70 ist.

    Die Verteilung läuft nach erfasstem Verbrauch; das Kuerzungsrecht des
    § 12 Abs. 1 setzt gerade das voraus.
    """
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))

    assert not [w for w in ergebnis['warnings']
                if heizung.KUERZUNG_15 in w]


def test_zaehler_ohne_verbrauch_alles_nach_flaeche():
    """Zaehler da, aber alle auf null: auch das ist keine Erfassung."""
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 0.0), waermezaehler(2, 2, 0.0)),
    ))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('5000.00')
    assert zeile['heizung_details']['fehlgrund'] == heizung.OHNE_STAENDE


# --- Wer an der Anlage haengt (D-45) ---------------------------------------


def test_selbstversorger_zaehlt_nicht_mit():
    """Wer seine Waerme selbst erzeugt, steht in keinem der beiden Nenner.

    R-CO2-03: die Software muss verhindern, dass fuer solche Einheiten
    Heizkosten des Gebaeudes umgelegt werden -- hier der Verbrauchsteil;
    dieselbe Ausnahme gilt fuer die Bezugsflaeche der CO2-Einstufung
    (rechenkern.py, Basis der Stufe).

    Bleibt eine Wohnung von 50 qm uebrig, traegt sie den ganzen Grundteil.
    """
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    selbst = Wohnung(id=2, name='EG rechts', qm=50.0, selbstversorger=True)
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0),),
        wohnungen=(meine, selbst),
    ))
    zeile = heizzeile(ergebnis)

    assert zeile['heizung_details']['total_sqm'] == 50.0
    assert zeile['tenant_cost'] == Decimal('10000.00')


def test_zwei_anlagen_trennen_sich_am_zaehler():
    """Vorderhaus und Hinterhaus: jede Anlage nur ihre eigenen Wohnungen."""
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung('4000.00', id=1, anlage_id=1),
                    heizrechnung('6000.00', id=2, anlage_id=2)),
        zaehler=(waermezaehler(1, 1, 1000.0, anlage_id=1),
                 waermezaehler(2, 2, 1000.0, anlage_id=2)),
        anlagen=(anlage(1, 'Vorderhaus'), anlage(2, 'Hinterhaus')),
    ))
    zeilen = [z for z in ergebnis['line_items'] if z['billing_type'] == 'heizkosten']

    assert len(zeilen) == 1
    assert zeilen[0]['category'] == 'Heizkosten (Vorderhaus)'
    assert zeilen[0]['tenant_cost'] == Decimal('4000.00')


def test_anlagen_wohnungen_bei_einer_anlage():
    vorgang = haus()
    assert [w.id for w in anlagen_wohnungen(vorgang, anlage(), False)] == [1, 2]


# --- Was beim Vermieter bleibt ---------------------------------------------


def test_leerstand_traegt_der_vermieter():
    """Die leere Wohnung faellt nicht aus dem qm-Nenner (D-43, R-NUM-05).

    Ihr Teil des Grundteils steht als Vermieteranteil da, statt still auf
    den Mieter zu wandern.
    """
    ich = Mieter(id=1, name='Anna Mieterin', einzug=date(2020, 1, 1),
                 auszug=None, wohnung_id=1)
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        mieter_der_immobilie=(ich,),
    ))

    anteil = ergebnis['landlord_share']
    # Seit NK-051 bleibt zusaetzlich der Verbrauchsteil der leeren Wohnung
    # beim Vermieter und wird ausgewiesen: 7.000 * 800/2.000 = 2.800,00 EUR
    # neben den 1.500,00 EUR aus dem qm-Grundteil.
    assert anteil['leerstand_amount'] == Decimal('4300.00')
    assert anteil['positions'][0]['category'] == 'Heizkosten (Zentralheizung)'
    verbrauchs_position = anteil['positions'][1]
    assert verbrauchs_position['amount'] == Decimal('2800.00')
    assert verbrauchs_position['vermieter_consumption'] == 800.0
    assert heizzeile(ergebnis)['tenant_cost'] == Decimal('5700.00')


# --- Die Begruendung auf dem Blatt (R-DOC-01) ------------------------------


def test_details_tragen_die_begruendung():
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))
    d = heizzeile(ergebnis)['heizung_details']

    assert d['anlage'] == 'Zentralheizung'
    assert d['verbrauchsanteil_prozent'] == 70
    assert d['flaechenanteil_prozent'] == 30
    assert d['betrkv_nr'] == 4
    assert d['unit'] == 'kWh'
    assert d['tenant_consumption'] == 1200.0
    assert d['total_consumption'] == 2000.0
    assert d['apartments'] == 2
    assert d['rechnungen'][0]['kostenart_text'] == heizung.bezeichnung(
        'brennstoff')


def test_fehlende_flaeche_bricht_ab():
    """Ohne Gesamtflaeche gibt es keinen Grundteil -- derselbe Abbruch wie qm.

    Der Grundkostenanteil nach § 7 Abs. 1 Satz 5 braucht einen Nenner. Fehlt
    er, waere die Zeile geraten, und geraten wird auf einer Abrechnung nicht.
    """
    leer = (Wohnung(id=1, name='EG links', qm=None),
            Wohnung(id=2, name='EG rechts', qm=None))
    with pytest.raises(BillingDataError):
        rechne(haus(
            rechnungen=(heizrechnung(),),
            zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
            wohnungen=leer,
            wohnung=leer[0],
        ))
