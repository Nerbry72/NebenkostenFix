"""NK-053: die CO2-Kostenaufteilung nach dem CO2KostAufG.

Zwei Ebenen, wie ueberall im Kern: das Modul ``co2`` wird als Zahlenwerkzeug
geprueft -- Tabelle, Rundung, anteilige Kuerzung, Aufteilung -- und der
Rechenkern an Welten mit Handkalkulation. Die Zahlen stehen in den
Docstrings, weil die Vorschrift sie so verlangt, nicht weil der Rechner sie
zufaellig ausgibt.

Die Grundwelt: zwei Wohnungen zu je 50 qm, eine Anlage, Satz 70, eine
Rechnung ueber 10.000 Euro, CO2-Kosten 2.000 Euro, Emission 2.200 kg.
2.200 kg / 100 qm = 22,0 kg/m2a, gerundet vor dem Einstufen: Stufe 4,
70 % Mieter, 30 % Vermieter.

    Masse nach § 7:        8.000,00  (Anna 4.560, Bert 3.440)
    CO2-Masse des Mieters: 1.400,00  (Anna 798, Bert 602)
    Vermieteranteil:         600,00
    -------------------------------  =  10.000,00
"""

import ast
from tests.importwaechter import importierte_module
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from nebenkostenfix import co2
from nebenkostenfix.geld import NULL, runde
from nebenkostenfix.rechenkern import (
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    rechne,
)

JAHR_BEGINN = date(2025, 1, 1)
JAHR_ENDE = date(2025, 12, 31)

WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True)

WURZEL = Path(__file__).resolve().parent.parent


def anlage(id=1, name='Zentralheizung', prozent=70, **kw):
    return Heizungsanlage(
        id=id, name=name, verbrauchsanteil_prozent=prozent, **kw)


def heizrechnung(betrag='10000.00', id=1, anlage_id=1,
                 art='brennstoff', beginn=JAHR_BEGINN, ende=JAHR_ENDE,
                 co2_kosten='2000.00', co2_emission='2200.00'):
    return Rechnung(
        id=id,
        kategorie=WAERME,
        betrag=Decimal(betrag),
        beginn=beginn,
        ende=ende,
        heizungsanlage_id=anlage_id,
        heizkostenart=art,
        co2_kosten=Decimal(co2_kosten) if co2_kosten is not None else None,
        co2_emission_kg=(
            Decimal(co2_emission) if co2_emission is not None else None),
    )


def waermezaehler(id, wohnung_id, verbraucht, anlage_id=1,
                  beginn=JAHR_BEGINN, ende=date(2026, 1, 1)):
    return Zaehler(
        id=id,
        nummer=f'W-{id}',
        kategorie_id=WAERME.id,
        kategorie_name='Waerme',
        ist_hauptzaehler=False,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=(Stand(datum=beginn, wert=0.0),
                 Stand(datum=ende, wert=verbraucht)),
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
        wohnungen=tuple(
            wohnungen if wohnungen is not None else (meine, andere)),
        mieter_der_immobilie=(ich, nachbar),
        profile={},
        rechnungen=tuple(rechnungen),
        zaehler=tuple(zaehler),
        heizungsanlagen=tuple(anlagen or (anlage(),)),
    )
    grund.update(kw)
    return Vorgang(**grund)


def heizzeile(ergebnis):
    zeilen = [z for z in ergebnis['line_items']
              if z['billing_type'] == 'heizkosten']
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def unterposten_typen(zeile):
    return [p['type'] for p in zeile['sub_items']]


# --- Das Modul: Tabelle, Rundung, Kuerzung, Aufteilung ---------------------


def test_die_tabelle_hat_zehn_stufen():
    """Zehn Stufen, deren Mieteranteile von 100 auf 5 fallen.

    Die Anlage (zu den §§ 5 bis 7) CO2KostAufG: Stufe 1 traegt der Mieter
    ganz -- sein Ausstoss ist unschaedlich --, in Stufe 10 behaelt er 5 vom
    Hundert. Der Vermieteranteil ist die Differenz, kein zweiter Wert.
    """
    assert len(co2.STUFEN) == 10
    assert co2.STUFEN[0] == (12, 100)
    assert co2.STUFEN[-1] == (None, 5)
    for nummer in range(1, 11):
        mieter, vermieter = co2.anteile(nummer)
        assert mieter + vermieter == 100
    assert [co2.anteile(n) for n in range(1, 11)] == [
        (100, 0), (90, 10), (80, 20), (70, 30), (60, 40),
        (50, 50), (40, 60), (30, 70), (20, 80), (5, 95),
    ]


def test_runden_vor_dem_einstufen():
    """11,96 wird zu 12,0 gerundet und faellt in Stufe 2 (R-CO2-01).

    § 5 Abs. 1 Satz 3 rundet auf eine Nachkommastelle -- und der gerundete
    Wert, nicht der urspruengliche, wird eingeordnet. Deshalb ist 11,96
    Stufe 2 und nicht Stufe 1. Die Grenzen sind die Obergrenzen ihrer
    Stufe: 22,0 gehoert zur Stufe 4 (22 bis unter 27), nicht zu Stufe 3.
    """
    assert co2.stufe_fuer(11.94) == 1
    assert co2.runde_wert(11.96) == Decimal('12.0')
    assert co2.stufe_fuer(11.96) == 2
    assert co2.stufe_fuer(12.0) == 2
    assert co2.stufe_fuer(22.0) == 4
    assert co2.stufe_fuer(51.9) == 9
    assert co2.stufe_fuer(52.0) == 10
    assert co2.stufe_fuer(1000.0) == 10
    assert co2.stufe_fuer(0.0) == 1


def test_unterjaehrig_werden_die_grenzen_gekuerzt():
    """§ 5 Abs. 1 Satz 4: die Tabellenwerte werden anteilig gekuerzt.

    Ein halbes Jahr (180 Tage): die Grenze der Stufe 1 sinkt von 12 auf
    12 * 180/365 ≈ 5,92 -- ein Ausstoss von 11,0 kg/m2a, im Jahr noch
    Stufe 1, rutscht in den gekuerzten Grenzen auf Stufe 4. Der Wert selbst
    wird nicht angetastet: gekuerzt wird die Tabelle (F-31). Dasselbe
    Anwenden der Jahestabelle ergibt zum Vergleich Stufe 1.
    """
    assert co2.stufe_fuer(11.0) == 1
    assert co2.stufe_fuer(11.0, 180) == 4
    # Und die Grenze selbst bleibt bei der gekuerzten Stufe 1 drin:
    assert co2.stufe_fuer(5.5, 180) == 1


def test_falsche_stufen_und_hundertaetze_fallen_auf():
    """Eine Stufe ausserhalb 1 bis 10 und ein Anteil ausserhalb 0 bis 100
    sind Programmfehler, keine Randfaelle."""
    with pytest.raises(co2.CO2Fehler):
        co2.anteile(0)
    with pytest.raises(co2.CO2Fehler):
        co2.anteile(11)
    with pytest.raises(co2.CO2Fehler):
        co2.teile_aufteilung(Decimal('100.00'), 150)
    with pytest.raises(co2.CO2Fehler):
        co2.teile_aufteilung(Decimal('100.00'), -1)


def test_teile_aufteilung_durch_differenz():
    """Der Vermieteranteil ist der Rest, nicht die zweite Multiplikation.

    So ergeben beide Teile zusammen wieder genau die Kosten -- auch beim
    krummen Betrag, wo zwei Multiplikationen einen Cent verlieren.
    """
    mieter, vermieter = co2.teile_aufteilung(Decimal('2000.00'), 70)
    assert mieter == Decimal('1400.00')
    assert vermieter == Decimal('600.00')
    krumm = co2.teile_aufteilung(Decimal('1999.99'), 5)
    assert krumm[0] + krumm[1] == Decimal('1999.99')
    alles = co2.teile_aufteilung(Decimal('2000.00'), 100)
    assert alles == (Decimal('2000.00'), Decimal('0.00'))


def test_modul_haengt_an_nichts_als_geld():
    """Derselbe Waechter wie fuer ``heizung``: kein ORM im Zahlenwerk.

    ``co2`` ist ein Baustein des Rechenkerns. Zoege es ein Modell herein,
    waere der Kern ueber einen Umweg wieder an der Datenbank.
    """
    baum = ast.parse((WURZEL / 'nebenkostenfix' / 'co2.py').read_text(encoding='utf-8'))

    importiert = importierte_module(baum)

    assert importiert <= {
        '__future__', 'decimal', 'typing', 'geld',
    }, f'co2.py zieht fremde Module herein: {importiert}'


# --- Der Rechenkern: Stufe 4, die Grundwelt ---------------------------------


def test_stufe_vier_verteilt_nach_der_tabelle():
    """22,0 kg/m2a ist Stufe 4: Mieter 70 %, Vermieter 30 %.

    Von der Rechnung gehen 2.000 Euro als CO2-Kosten ab, bevor § 7 anfaengt:
    Masse 8.000, davon Anna 4.560. Die CO2-Masse des Mieters ist 1.400 und
    wird mit demselben Satz nach § 6 Abs. 3 verteilt: 980 nach Verbrauch
    (588 fuer Anna) und 420 nach Flaeche (210 fuer Anna). Der flache
    Vermieteranteil 600 geht an keine von beiden.
    """
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))

    ausweis = ergebnis['co2']
    assert ausweis['stufe'] == 4
    assert ausweis['mieter_prozent'] == 70
    assert ausweis['vermieter_prozent'] == 30
    assert ausweis['emission_kg'] == 2200.0
    assert ausweis['kg_pro_qm'] == 22.0
    assert ausweis['kosten'] == Decimal('2000.00')
    assert ausweis['quellen'] == [{
        'invoice_id': 1,
        'invoice_number': None,
        'rechnungsdatum': None,
        'emission_kg': 2200.0,
        'kosten': Decimal('2000.00'),
    }]
    assert ausweis['mieter_anteil_euro'] == Decimal('798.00')
    assert ausweis['vermieter_anteil_euro'] == Decimal('600.00')

    zeile = heizzeile(ergebnis)
    assert zeile['total_amount'] == Decimal('8000.00')
    assert zeile['tenant_cost'] == Decimal('5358.00')
    assert unterposten_typen(zeile) == [
        'heizung_verbrauch', 'heizung_flaeche', 'heizung_co2']
    verbrauch, flaeche, davon = zeile['sub_items']
    assert verbrauch['cost'] == Decimal('3360.00')
    assert flaeche['cost'] == Decimal('1200.00')
    assert davon['cost'] == Decimal('798.00')
    assert 'Stufe 4' in davon['description']
    assert '70 % Mieteranteil' in davon['description']
    assert '30 % Vermieteranteil' in davon['description']

    details = zeile['heizung_details']
    assert details['co2']['stufe'] == 4
    assert details['co2']['anteil'] == Decimal('798.00')
    assert details['co2']['vermieteranteil'] == Decimal('600.00')

    # Der flache Vermieteranteil steht als eigene Position; ohne Leerstand
    # ist das die einzige.
    positionen = ergebnis['landlord_share']['positions']
    assert len(positionen) == 1
    assert positionen[0]['category'] == 'CO2-Kosten (Zentralheizung)'
    assert positionen[0]['amount'] == Decimal('600.00')
    assert 'Stufe 4' in positionen[0]['description']
    assert ergebnis['landlord_share']['total_amount'] == Decimal('600.00')

    # Die Zeile nennt die abgetrennten CO2-Kosten je Beleg.
    beleg = zeile['heizung_details']['rechnungen'][0]
    assert beleg['co2_kosten'] == Decimal('2000.00')
    assert beleg['co2_mieteranteil'] == Decimal('1400.00')
    assert beleg['co2_vermieteranteil'] == Decimal('600.00')


def test_der_nachbar_bekommt_seinen_anteil():
    """Bert verbraucht 800 von 2.000 kWh: 2.240 + 1.200 + 602 = 4.042.

    Derselbe Schlitten wie Anna, nur mit seinem Verbrauch -- und mit dem
    Flaecheanteil, der von der Wohnung, nicht vom Verbrauch abhaengt.
    """
    bert = Mieter(
        id=2, name='Bert Nachbar', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=2)
    ergebnis = rechne(haus(
        mieter=bert,
        wohnung=Wohnung(id=2, name='EG rechts', qm=50.0),
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))
    zeile = heizzeile(ergebnis)
    assert zeile['tenant_cost'] == Decimal('4042.00')
    verbrauch, flaeche, davon = zeile['sub_items']
    assert verbrauch['cost'] == Decimal('2240.00')
    assert flaeche['cost'] == Decimal('1200.00')
    assert davon['cost'] == Decimal('602.00')


def test_die_bilanz_ist_geschlossen():
    """Anna 5.358 + Bert 4.042 + Vermieter 600 = 10.000, die Rechnung.

    Nichts bleibt zwischen den Zeilen liegen -- die Aufteilung des § 6
    verschiebt nur, wer was traegt.
    """
    anna = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))
    bert = Mieter(
        id=2, name='Bert Nachbar', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=2)
    berts = rechne(haus(
        mieter=bert,
        wohnung=Wohnung(id=2, name='EG rechts', qm=50.0),
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))
    gesamt = (
        anna['total_amount']
        + berts['total_amount']
        + anna['landlord_share']['total_amount']
    )
    assert runde(gesamt) == Decimal('10000.00')


def test_stufe_eins_veraendert_nichts():
    """1.000 kg auf 100 qm = 10,0 kg/m2a: Stufe 1, der Mieter traegt alles.

    10.000 Euro, Satz 70: genau dieselben Zeilen wie ohne jede CO2-Angabe
    (4.200 + 1.500). Der Unterposten nennt die 1.140 Euro, die nun zur
    Masse gehoeren; beim Vermieter bleibt nichts flaches.
    """
    ergebnis = rechne(haus(
        rechnungen=(
            heizrechnung(co2_kosten='2000.00', co2_emission='1000.00'),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))

    ausweis = ergebnis['co2']
    assert ausweis['stufe'] == 1
    assert ausweis['kg_pro_qm'] == 10.0
    assert ausweis['mieter_prozent'] == 100
    assert ausweis['vermieter_prozent'] == 0
    assert ausweis['mieter_anteil_euro'] == Decimal('1140.00')
    assert ausweis['vermieter_anteil_euro'] == Decimal('0.00')

    zeile = heizzeile(ergebnis)
    assert zeile['tenant_cost'] == Decimal('5700.00')
    verbrauch, flaeche, davon = zeile['sub_items']
    assert verbrauch['cost'] == Decimal('3360.00')
    assert flaeche['cost'] == Decimal('1200.00')
    assert davon['cost'] == Decimal('1140.00')

    assert ergebnis['landlord_share']['positions'] == []
    assert ergebnis['landlord_share']['total_amount'] == Decimal('0.00')


def test_ohne_angaben_keine_aufteilung_sondern_warnung():
    """Fehlt eine CO2-Angabe, wird nicht geraten: Warnung, sonst nichts.

    Alles oder nichts (D-54): eine halbe Einstufung waere schlimmer als
    keine. Die Zeile rechnet, wie sie ohne jede CO2-Angabe rechnen wuerde,
    und die Warnung traegt die Kennung, die eine endgueltige Abrechnung
    blockiert (R-CO2-02).
    """
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(co2_kosten=None, co2_emission=None),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))

    assert ergebnis['co2'] is None
    warnungen = [w for w in ergebnis['warnings']
                 if w.startswith(co2.AUSWEIS_FEHLT)]
    assert len(warnungen) == 1
    assert 'E-CO2-AUSWEIS-FEHLT' in warnungen[0]
    assert '#1' in warnungen[0]
    assert '§ 7 CO2KostAufG' in warnungen[0]

    zeile = heizzeile(ergebnis)
    assert zeile['tenant_cost'] == Decimal('5700.00')
    assert unterposten_typen(zeile) == ['heizung_verbrauch', 'heizung_flaeche']
    assert zeile['heizung_details']['co2'] is None
    assert zeile['heizung_details']['rechnungen'][0]['co2_kosten'] == NULL
    assert ergebnis['landlord_share']['positions'] == []


def test_leerstand_und_eigennutzung_vermoegen_den_co2_rest():
    """Die zweite Wohnung steht leer: sie traegt am CO2-Mieteranteil mit.

    Anna 5.358,00. Beim Vermieter bleiben der flache CO2-Anteil 600,00, an
    der Heizkostenmasse der Leerstand am Grundteil 1.200,00 und der
    Verbrauchsrest 2.240,00, an der CO2-Masse Leerstand 210,00 und
    Verbrauchsrest 392,00. Zusammen 4.642,00; mit Anna 10.000,00, die
    Rechnung.
    """
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    leer = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = Mieter(
        id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=1)
    ergebnis = rechne(haus(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        wohnungen=(meine, leer),
        mieter=ich,
        mieter_der_immobilie=(ich,),
    ))

    zeile = heizzeile(ergebnis)
    assert zeile['tenant_cost'] == Decimal('5358.00')

    positionen = ergebnis['landlord_share']['positions']
    kategorien = {}
    for p in positionen:
        kategorien.setdefault(p['category'], []).append(p)
    assert set(kategorien) == {
        'Heizkosten (Zentralheizung)',
        'CO2-Kosten (Zentralheizung)',
    }
    co2_positionen = kategorien['CO2-Kosten (Zentralheizung)']
    assert runde(sum(p['amount'] for p in co2_positionen)) == Decimal('1202.00')

    anteil = ergebnis['landlord_share']
    # Der Leerstand schliesst die Verbrauchsreste ein: die leer stehende
    # Wohnung hat jaehrliche Waerme von der Anlage genommen.
    assert anteil['leerstand_amount'] == Decimal('4042.00')
    assert anteil['eigennutzung_amount'] == Decimal('0.00')
    assert anteil['total_amount'] == Decimal('4642.00')

    # Und die Bilanz schliesst: Mieterin plus Vermieter = Rechnung.
    gesamt = zeile['tenant_cost'] + anteil['total_amount']
    assert runde(gesamt) == Decimal('10000.00')


def test_der_auszug_stutzt_die_masse_nicht_die_tabelle():
    """Ein Einzug im Juli stoert die Einstufung nicht (F-31, D-54).

    Die Stufe gehoert dem Gebaeude und dem Abrechnungszeitraum; die
    Tabellenwerte werden nur bei einem VEREINBARTEN unterjaehrigen Zeitraum
    gekuerzt, nicht beim Mieterwechsel. Das gestutzte Fenster kuerzt die
    Massen -- weniger Euro fuer Anna --, aber 2.200 kg auf 100 qm bleiben
    22,0 kg/m2a und damit Stufe 4.
    """
    halbes = Mieter(
        id=1, name='Anna Mieterin', einzug=date(2025, 7, 1), auszug=None,
        wohnung_id=1)
    ergebnis = rechne(haus(
        mieter=halbes,
        beginn=date(2025, 7, 1),
        ende=JAHR_ENDE,
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    ))

    ausweis = ergebnis['co2']
    assert ausweis['stufe'] == 4
    assert ausweis['kg_pro_qm'] == 22.0
    assert ausweis['emission_kg'] == 2200.0
    zeile = heizzeile(ergebnis)
    assert zeile['tenant_cost'] < Decimal('5358.00')
    assert zeile['heizung_details']['co2']['anteil'] < Decimal('798.00')


def test_ohne_anlage_gibt_es_kein_co2_und_keine_warnung():
    """Keine Heizkostenrechnung, keine Einstufung, keine Warnung.

    Die Ausweispflicht greift, wo CO2-Kosten anfallen. Ein Objekt ohne
    Waermeversorgung kann sie nicht verletzen.
    """
    ergebnis = rechne(haus(rechnungen=(), zaehler=()))
    assert ergebnis['co2'] is None
    assert not [w for w in ergebnis['warnings']
                if w.startswith(co2.AUSWEIS_FEHLT)]
