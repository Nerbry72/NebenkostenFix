"""NK-047: der Leerstandsanteil wird ausgewiesen (R-NUM-05).

Der Befund war keine falsche Zahl, sondern eine fehlende. Drei Wohnungen zu je
50 qm, eine davon leer, 300,00 EUR Grundsteuer: der Rechenkern teilt nach
Flaeche und gibt jedem der beiden Mieter 100,00 EUR. Das ist richtig -- der
Nenner ist die volle Gesamtflaeche, also traegt der Vermieter den Leerstand.
Nur sieht das niemand. Die dritten 100,00 EUR stehen in keiner Zeile, in
keiner Summe und in keinem Hinweis; sie fallen zwischen den Zeilen heraus.

Produktprinzip 3 verlangt das Gegenteil: nachrechnen kann nur, wer alle
Summanden kennt. Seit NK-047 weist die Abrechnung deshalb aus, welcher Teil
jeder Flaechenrechnung beim Vermieter bleibt und warum -- ``Leerstand`` oder
``Eigennutzung``, getrennt, mit Wohnung und Tagen.

Gezaehlt wird taggenau, nicht nach Belegungsstatus. Die aeltere Fassung von
R-NUM-05 fragte, ob eine Wohnung "mindestens ein ueberlappendes
Mietverhaeltnis" hatte. Das verschluckt den halbleeren Fall: zieht ein Mieter
zum 01.07. aus und niemand nach, war die Wohnung ein halbes Jahr vermietet und
ein halbes Jahr leer.

Geprueft wird von unten nach oben:

1. ``leerstand.py`` selbst -- belegte Tage, Bilanzen, Gruende,
2. der Rechenkern -- der Fall aus der Regel und die Probe, dass die Summe
   aller Anteile wieder den Rechnungsbetrag ergibt.
"""

from __future__ import annotations

import ast
import doctest
import pathlib
from dataclasses import replace
from datetime import date
from decimal import Decimal

import leerstand
from leerstand import (
    EIGENNUTZUNG,
    LEERSTAND,
    VERMIETET,
    Einheit,
    belegte_tage,
    bilanzen,
    unbelegte_flaechentage,
)
from rechenkern import Kategorie, Mieter, Rechnung, Vorgang, Wohnung, rechne

WURZEL = pathlib.Path(__file__).resolve().parent.parent

# 2025 ist kein Schaltjahr -- 365 Tage, damit die Zahlen aus der Regel
# dieselben bleiben.
JAHR_BEGINN = date(2025, 1, 1)
JAHR_ENDE = date(2025, 12, 31)
JAHR_GRENZE = date(2026, 1, 1)
ZUR_JAHRESMITTE = date(2025, 7, 1)


# --- Was das Modul ueber sich selbst sagt -----------------------------------


def test_doctests_im_modul_laufen():
    ergebnis = doctest.testmod(leerstand, verbose=False)
    assert ergebnis.failed == 0, f'{ergebnis.failed} Doctests in leerstand.py schlagen fehl'


def test_modul_haengt_an_nichts_als_zeitraum():
    """Derselbe Waechter wie fuer ``haushalt``: kein ORM in den Bausteinen.

    ``leerstand`` ist ein Baustein des Rechenkerns (NK-037). Zoege es ein
    Modell herein, waere der Kern ueber einen Umweg wieder an der Datenbank.
    """
    baum = ast.parse((WURZEL / 'leerstand.py').read_text(encoding='utf-8'))

    importiert = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            importiert.update(a.name.split('.')[0] for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            importiert.add(knoten.module.split('.')[0])

    assert importiert <= {
        '__future__', 'dataclasses', 'datetime', 'typing', 'zeitraum',
    }, f'leerstand.py zieht fremde Module herein: {importiert}'


# --- Belegte Tage -----------------------------------------------------------


def test_ohne_mietverhaeltnis_ist_kein_tag_belegt():
    assert belegte_tage([], JAHR_BEGINN, JAHR_GRENZE) == 0


def test_ganzjaehriges_mietverhaeltnis_belegt_jeden_tag():
    assert belegte_tage(
        [(JAHR_BEGINN, JAHR_GRENZE)], JAHR_BEGINN, JAHR_GRENZE) == 365


def test_auszug_zur_jahresmitte_laesst_den_rest_leer():
    """Halboffen gezaehlt (R-NUM-03): 181 belegte, 184 leere Tage."""
    assert belegte_tage(
        [(JAHR_BEGINN, ZUR_JAHRESMITTE)], JAHR_BEGINN, JAHR_GRENZE) == 181


def test_der_wechseltag_laesst_keine_luecke():
    """Vormieter bis zum 01.07., Nachmieter ab dem 01.07. -- kein Leerstand.

    Genau dafuer ist die halboffene Rechnung da: zwei aneinandergrenzende
    Zeitraeume ergeben zusammen den ganzen, ohne Ueberschneidung und ohne
    Luecke.
    """
    assert belegte_tage(
        [(JAHR_BEGINN, ZUR_JAHRESMITTE), (ZUR_JAHRESMITTE, JAHR_GRENZE)],
        JAHR_BEGINN, JAHR_GRENZE,
    ) == 365


def test_ueberlappende_mietverhaeltnisse_zaehlen_einen_tag_einmal():
    """Die Vereinigung, nicht die Summe.

    Stehen Vor- und Nachmieter mit sich ueberschneidenden Zeiten in der
    Liste -- etwa weil beim Wechsel ein Datum krumm eingetragen wurde --,
    darf eine Wohnung nicht mehr belegte Tage bekommen als der Zeitraum lang
    ist. Sonst wird der Leerstand negativ.
    """
    assert belegte_tage(
        [(JAHR_BEGINN, date(2025, 8, 1)), (ZUR_JAHRESMITTE, JAHR_GRENZE)],
        JAHR_BEGINN, JAHR_GRENZE,
    ) == 365


def test_mietzeiten_ausserhalb_des_zeitraums_zaehlen_nicht():
    assert belegte_tage(
        [(date(2024, 1, 1), JAHR_BEGINN)], JAHR_BEGINN, JAHR_GRENZE) == 0


def test_luecke_zwischen_zwei_mietverhaeltnissen():
    """Zwei Monate ohne Nachmieter: 59 leere Tage im Juli und August."""
    belegt = belegte_tage(
        [(JAHR_BEGINN, ZUR_JAHRESMITTE), (date(2025, 9, 1), JAHR_GRENZE)],
        JAHR_BEGINN, JAHR_GRENZE,
    )
    assert belegt == 365 - 62


# --- Bilanzen ---------------------------------------------------------------


def _drei_einheiten(leer_mietzeiten=(), eigennutzung=False):
    """Drei Wohnungen zu je 50 qm. Die dritte ist der Streitfall."""
    return [
        Einheit(1, 'Wohnung 1', 50.0, mietzeiten=((JAHR_BEGINN, JAHR_GRENZE),)),
        Einheit(2, 'Wohnung 2', 50.0, mietzeiten=((JAHR_BEGINN, JAHR_GRENZE),)),
        Einheit(3, 'Wohnung 3', 50.0, eigennutzung=eigennutzung,
                mietzeiten=tuple(leer_mietzeiten)),
    ]


def test_belegt_und_unbelegt_ergeben_immer_den_zeitraum():
    for b in bilanzen(_drei_einheiten(), JAHR_BEGINN, JAHR_GRENZE):
        assert b.belegt + b.unbelegt == 365


def test_die_leere_wohnung_heisst_leerstand():
    dritte = bilanzen(_drei_einheiten(), JAHR_BEGINN, JAHR_GRENZE)[2]
    assert dritte.grund == LEERSTAND
    assert dritte.unbelegt == 365
    assert dritte.traegt_der_vermieter


def test_die_selbst_bewohnte_wohnung_heisst_eigennutzung():
    """Zwei Dinge, die der Vermieter beide traegt -- und doch nicht dasselbe.

    Leerstand ist ein Ausfall, Eigennutzung sind seine eigenen Wohnkosten.
    ``eigennutzung`` (NK-045) unterscheidet sie; ohne die Unterscheidung
    waere der ausgewiesene Anteil zwei Dinge in einer Zahl.
    """
    dritte = bilanzen(
        _drei_einheiten(eigennutzung=True), JAHR_BEGINN, JAHR_GRENZE)[2]
    assert dritte.grund == EIGENNUTZUNG


def test_die_vermietete_wohnung_traegt_der_vermieter_nicht():
    erste = bilanzen(_drei_einheiten(), JAHR_BEGINN, JAHR_GRENZE)[0]
    assert erste.grund == VERMIETET
    assert not erste.traegt_der_vermieter


def test_flaechentage_lassen_sich_nach_grund_trennen():
    bilanz = bilanzen(
        _drei_einheiten(eigennutzung=True), JAHR_BEGINN, JAHR_GRENZE)
    assert unbelegte_flaechentage(bilanz, LEERSTAND) == 0
    assert unbelegte_flaechentage(bilanz, EIGENNUTZUNG) == 50.0 * 365
    assert unbelegte_flaechentage(bilanz) == 50.0 * 365


# --- Der Rechenkern ---------------------------------------------------------


GRUNDSTEUER = Kategorie(id=1, name='Grundsteuer', braucht_zaehler=False)


def _welt(wer=1, auszug_zweite=None, eigennutzung_dritte=False,
          beginn=JAHR_BEGINN, ende=JAHR_ENDE):
    """Drei Wohnungen zu je 50 qm, zwei vermietet, 300,00 EUR nach qm.

    Der Fall, den R-NUM-05 selbst vorgibt. ``wer`` waehlt, fuer welchen
    Mieter abgerechnet wird.
    """
    wohnungen = (
        Wohnung(id=1, name='Wohnung 1', qm=50.0),
        Wohnung(id=2, name='Wohnung 2', qm=50.0),
        Wohnung(id=3, name='Wohnung 3', qm=50.0,
                eigennutzung=eigennutzung_dritte),
    )
    mieter = (
        Mieter(id=1, name='Mieter 1', einzug=JAHR_BEGINN, auszug=None,
               wohnung_id=1),
        Mieter(id=2, name='Mieter 2', einzug=JAHR_BEGINN,
               auszug=auszug_zweite, wohnung_id=2),
    )
    ich = mieter[wer - 1]
    return Vorgang(
        mieter=ich,
        wohnung=wohnungen[wer - 1],
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=beginn,
        ende=ende,
        wohnungen=wohnungen,
        mieter_der_immobilie=mieter,
        profile={GRUNDSTEUER.id: 'qm'},
        rechnungen=(
            Rechnung(id=1, kategorie=GRUNDSTEUER, betrag=Decimal('300.00'),
                     beginn=JAHR_BEGINN, ende=JAHR_ENDE),
        ),
    )


def test_der_fall_aus_der_regel():
    """R-NUM-05 woertlich: 3x50 qm, eine leer, 300,00 EUR Grundsteuer.

    Jeder Mieter zahlt 100,00 EUR -- so war es schon vorher, der Nenner ist
    die volle Gesamtflaeche. Neu ist die dritte Zahl: 100,00 EUR bleiben beim
    Vermieter, und sie stehen jetzt da.
    """
    ergebnis = rechne(_welt(wer=1))

    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('100.00')

    anteil = ergebnis['landlord_share']
    assert anteil['total_amount'] == Decimal('100.00')
    assert anteil['leerstand_amount'] == Decimal('100.00')
    assert anteil['eigennutzung_amount'] == Decimal('0.00')

    position = anteil['positions'][0]
    assert position['category'] == 'Grundsteuer'
    assert position['prorated_amount'] == Decimal('300.00')
    assert [e['apartment'] for e in position['units']] == ['Wohnung 3']
    assert position['units'][0]['vacant_days'] == 365
    assert 'Leerstand (Wohnung 3)' in position['description']


def test_die_summe_aller_anteile_ist_der_rechnungsbetrag():
    """Die Probe aufs Exempel: 100 + 100 + 100 = 300.

    Genau das liess sich vor NK-047 nicht nachrechnen, weil der dritte
    Summand nirgends stand.
    """
    erster = rechne(_welt(wer=1))
    zweiter = rechne(_welt(wer=2))

    assert (
        erster['line_items'][0]['tenant_cost']
        + zweiter['line_items'][0]['tenant_cost']
        + erster['landlord_share']['total_amount']
    ) == Decimal('300.00')


def test_volles_haus_hat_keinen_vermieteranteil():
    """Kein Leerstand, kein Ausweis -- und keine leere Rubrik.

    Der haeufigste Fall ist das voll vermietete Haus. Dort soll die
    Abrechnung nicht von etwas reden, das es nicht gibt.
    """
    welt = _welt(wer=1)
    voll = replace(welt, mieter_der_immobilie=welt.mieter_der_immobilie + (
        Mieter(id=3, name='Mieter 3', einzug=JAHR_BEGINN, auszug=None,
               wohnung_id=3),
    ))
    ergebnis = rechne(voll)

    assert ergebnis['landlord_share']['positions'] == []
    assert ergebnis['landlord_share']['total_amount'] == Decimal('0.00')
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('100.00')


def test_eigennutzung_steht_getrennt_vom_leerstand():
    ergebnis = rechne(_welt(wer=1, eigennutzung_dritte=True))
    anteil = ergebnis['landlord_share']

    assert anteil['eigennutzung_amount'] == Decimal('100.00')
    assert anteil['leerstand_amount'] == Decimal('0.00')
    assert anteil['positions'][0]['units'][0]['reason'] == EIGENNUTZUNG
    assert 'Eigennutzung (Wohnung 3)' in anteil['positions'][0]['description']


def test_halber_leerstand_zaehlt_halb():
    """Wohnung 2 wird zum 01.07. frei: 184 von 365 Tagen leer.

    Eine Ja/Nein-Frage nach "mindestens einem Mietverhaeltnis" haette hier
    nichts gefunden -- die Wohnung war ja vermietet. Taggenau gezaehlt traegt
    der Vermieter 50 qm x 184 Tage dazu:

        300,00 x (50x184 + 50x365) / (150x365) = 150,41
    """
    ergebnis = rechne(_welt(wer=1, auszug_zweite=ZUR_JAHRESMITTE))
    anteil = ergebnis['landlord_share']

    assert anteil['leerstand_amount'] == Decimal('150.41')

    tage_je_wohnung = {
        e['apartment']: e['vacant_days'] for e in anteil['positions'][0]['units']
    }
    assert tage_je_wohnung == {'Wohnung 2': 184, 'Wohnung 3': 365}


def test_auch_beim_halben_leerstand_geht_die_rechnung_auf():
    """100,00 + 49,59 + 150,41 = 300,00."""
    erster = rechne(_welt(wer=1, auszug_zweite=ZUR_JAHRESMITTE))
    zweiter = rechne(_welt(
        wer=2, auszug_zweite=ZUR_JAHRESMITTE, ende=ZUR_JAHRESMITTE))

    assert zweiter['line_items'][0]['tenant_cost'] == Decimal('49.59')
    assert (
        erster['line_items'][0]['tenant_cost']
        + zweiter['line_items'][0]['tenant_cost']
        + erster['landlord_share']['total_amount']
    ) == Decimal('300.00')


def test_inaktive_wohnungen_bleiben_draussen():
    """Was nicht mehr zur Immobilie gehoert, steht in keinem Nenner.

    Eine inaktive Wohnung faellt schon aus der Gesamtflaeche heraus
    (``flaechen_pruefung``). Sie darf dann auch nicht als Leerstand
    auftauchen -- sonst haette sie im Zaehler mehr Gewicht als im Nenner.
    """
    welt = _welt(wer=1)
    mit_inaktiver = replace(welt, wohnungen=welt.wohnungen + (
        Wohnung(id=4, name='Abgerissen', qm=50.0, ist_aktiv=False),
    ))
    anteil = rechne(mit_inaktiver)['landlord_share']

    assert [e['apartment'] for e in anteil['positions'][0]['units']] == ['Wohnung 3']
    assert anteil['total_amount'] == Decimal('100.00')
