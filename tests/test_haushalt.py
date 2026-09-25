"""NK-046: Personentage statt gezaehlter Koepfe (R-NUM-04).

Der Befund war eine Division: der Rechenkern hat den anteiligen
Rechnungsbetrag durch die **Anzahl** der im Zeitraum aktiven
Mietverhaeltnisse geteilt. Das macht aus einer vierkoepfigen Familie und
einem Single dieselbe Groesse, und es gibt dem Mieter, der im Juli
eingezogen ist, denselben Nenner wie dem, der das ganze Jahr da war.

R-NUM-04 verlangt Personentage: jeder Tag zaehlt so oft, wie an ihm
Personen im Haushalt lebten. Der Testfall, den die Regel selbst vorgibt,
steht weiter unten unter *Der Fall aus der Regel*: drei Personen
ganzjaehrig gegen eine Person ab dem 01.07. -- 1095 zu 184.

Diese Datei prueft von unten nach oben:

1. ``haushalt.py`` selbst -- die Treppenfunktion, die Abschnitte und die
   gewichtete Summe,
2. den Weg aus der Datenbank in den Kern -- dass die Historie eines
   Mietverhaeltnisses ORM-frei beim Rechnen ankommt,
3. den Rechenkern -- den Personenschluessel und den Allgemeinanteil.
"""

from __future__ import annotations

import ast
import doctest
import pathlib
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

import haushalt
from abrechnungsdaten import lade_vorgang
from haushalt import (
    MINDESTENS,
    VORGABE,
    HaushaltsFehler,
    Stand,
    abschnitte,
    normiere,
    personen_am,
    personentage,
    pruefe,
)
from rechenkern import Kategorie, Mieter, Rechnung, Vorgang, Wohnung, Zaehler, rechne
from rechenkern import Stand as Zaehlerstand
from tests import billing_factories as f

WURZEL = pathlib.Path(__file__).resolve().parent.parent

# Der Fall aus der Regel spielt 2025 -- kein Schaltjahr, damit die Zahlen
# 1095 und 184 dieselben bleiben, die R-NUM-04 nennt.
JAHR_BEGINN = date(2025, 1, 1)
JAHR_ENDE = date(2025, 12, 31)
ZUR_JAHRESMITTE = date(2025, 7, 1)


# --- Was das Modul ueber sich selbst sagt -----------------------------------


def test_doctests_im_modul_laufen():
    ergebnis = doctest.testmod(haushalt, verbose=False)
    assert ergebnis.failed == 0, f'{ergebnis.failed} Doctests in haushalt.py schlagen fehl'


def test_vorgabe_ist_die_kleinste_zulaessige_groesse():
    """Ein Mietverhaeltnis ohne Eintrag ist ein Einpersonenhaushalt.

    Nicht null: ein Nenner von null wuerde die Umlage verschwinden lassen
    statt sie zu verteilen. Und genau diesen Wert hat die Wanderung aus
    NK-045 dem Altbestand gegeben -- ein anderer Vorgabewert wuerde beim
    Einspielen eines Updates stillschweigend das Ergebnis aendern.
    """
    assert VORGABE == MINDESTENS == 1
    assert pruefe(VORGABE) == VORGABE


def test_modul_haengt_nur_an_der_standardbibliothek_und_zeitraum():
    """Der Rechenkern importiert kein ORM (NK-037) -- das gilt fuer seine Bausteine mit.

    ``zeitraum`` darf herein: es traegt die halboffene Tageskonvention aus
    R-NUM-03 und haengt selbst an nichts als ``datetime``.
    """
    baum = ast.parse((WURZEL / 'haushalt.py').read_text(encoding='utf-8'))
    importiert = {
        (knoten.module or '').split('.')[0]
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.ImportFrom)
    } | {
        alias.name.split('.')[0]
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Import)
        for alias in knoten.names
    }
    assert importiert <= {'__future__', 'datetime', 'typing', 'zeitraum'}, (
        f'haushalt.py zieht fremde Module herein: {sorted(importiert)}'
    )


# --- Die Pruefung einer einzelnen Groesse -----------------------------------


@pytest.mark.parametrize('wert', [1, 2, 5, 99])
def test_jede_ganze_zahl_ab_eins_geht_durch(wert):
    assert pruefe(wert) == wert


@pytest.mark.parametrize('wert', [0, -1, -99])
def test_null_und_negatives_werden_abgelehnt(wert):
    with pytest.raises(HaushaltsFehler) as fehler:
        pruefe(wert)
    assert str(wert) in str(fehler.value)
    assert 'mindestens 1' in str(fehler.value)


@pytest.mark.parametrize('wert', [None, '3', 3.0, True, False, [3]])
def test_was_keine_ganze_zahl_ist_wird_abgelehnt(wert):
    """``True`` ist in Python eine Eins, hier aber keine Haushaltsgroesse.

    Wer ein Kaestchen statt einer Zahl schickt, hat sich im Feld geirrt --
    und ``3.0`` ist keine Zahl von Menschen.
    """
    with pytest.raises(HaushaltsFehler):
        pruefe(wert)


def test_fehler_ist_ein_valueerror():
    """Wer nur ``ValueError`` faengt, faengt auch diesen -- wie in ``geld.py``."""
    assert issubclass(HaushaltsFehler, ValueError)


# --- Die Historie -----------------------------------------------------------


def test_normieren_sortiert_nach_stichtag():
    roh = [(date(2024, 7, 1), 3), (date(2024, 1, 1), 2), (date(2024, 4, 1), 4)]
    assert normiere(roh) == (
        Stand(date(2024, 1, 1), 2),
        Stand(date(2024, 4, 1), 4),
        Stand(date(2024, 7, 1), 3),
    )


def test_normieren_macht_aus_paaren_staende():
    (stand,) = normiere([(date(2024, 1, 1), 2)])
    assert stand.gueltig_ab == date(2024, 1, 1)
    assert stand.personen == 2
    assert stand == (date(2024, 1, 1), 2), 'ein Stand ist ein Tupel und bleibt eines'


def test_zwei_staende_ab_demselben_tag_sind_ein_widerspruch():
    """Kein Transportrauschen, sondern ein Sachfehler.

    Im Schema haelt das die UNIQUE-Bedingung ``(tenant_id, gueltig_ab)``
    fest (NK-045); hier faellt es auf, bevor gerechnet wird.
    """
    with pytest.raises(HaushaltsFehler) as fehler:
        normiere([(date(2024, 1, 1), 2), (date(2024, 1, 1), 3)])
    assert '2024-01-01' in str(fehler.value)


def test_ein_stichtag_der_kein_datum_ist_wird_abgelehnt():
    with pytest.raises(HaushaltsFehler):
        normiere([('2024-01-01', 2)])


def test_leere_historie_bleibt_leer():
    assert normiere([]) == ()


# --- Die Treppenfunktion ----------------------------------------------------


def test_es_gilt_der_juengste_nicht_zukuenftige_stand():
    h = [(date(2024, 1, 1), 2), (date(2024, 7, 1), 4)]
    assert personen_am(h, date(2024, 6, 30)) == 2
    assert personen_am(h, date(2024, 7, 1)) == 4, 'der Stichtag gehoert zum neuen Stand'
    assert personen_am(h, date(2024, 12, 31)) == 4


def test_vor_dem_ersten_eintrag_gilt_die_vorgabe():
    h = [(date(2024, 7, 1), 4)]
    assert personen_am(h, date(2024, 6, 30)) == VORGABE


def test_ohne_eintrag_gilt_die_vorgabe():
    assert personen_am([], date(2024, 5, 5)) == VORGABE


# --- Die Abschnitte ---------------------------------------------------------


def test_abschnitte_schneiden_am_stichtag():
    h = [(date(2024, 1, 1), 2), (date(2024, 7, 1), 4)]
    assert abschnitte(h, date(2024, 1, 1), date(2025, 1, 1)) == (
        (date(2024, 1, 1), date(2024, 7, 1), 2),
        (date(2024, 7, 1), date(2025, 1, 1), 4),
    )


def test_ein_stichtag_ausserhalb_schneidet_nicht():
    """Was vor dem Zeitraum liegt, gilt in ihm -- es teilt ihn aber nicht."""
    h = [(date(2020, 1, 1), 3)]
    assert abschnitte(h, date(2024, 1, 1), date(2025, 1, 1)) == (
        (date(2024, 1, 1), date(2025, 1, 1), 3),
    )


def test_ein_stichtag_genau_auf_der_oberen_grenze_schneidet_nicht():
    """``[von, bis)`` ist halboffen: der Tag ``bis`` gehoert nicht mehr dazu."""
    h = [(date(2024, 1, 1), 2), (date(2025, 1, 1), 9)]
    assert abschnitte(h, date(2024, 1, 1), date(2025, 1, 1)) == (
        (date(2024, 1, 1), date(2025, 1, 1), 2),
    )


@pytest.mark.parametrize(
    ('von', 'bis'),
    [
        (date(2024, 5, 1), date(2024, 5, 1)),
        (date(2024, 6, 1), date(2024, 5, 1)),
    ],
)
def test_ein_leerer_oder_umgedrehter_zeitraum_hat_keine_abschnitte(von, bis):
    assert abschnitte([(date(2024, 1, 1), 3)], von, bis) == ()


# --- Die gewichtete Summe ---------------------------------------------------


def test_personentage_sind_koepfe_mal_tage():
    assert personentage([(date(2024, 1, 1), 3)], date(2024, 1, 1), date(2025, 1, 1)) == 3 * 366


def test_ohne_historie_sind_personentage_einfach_tage():
    assert personentage([], date(2025, 7, 1), date(2026, 1, 1)) == 184


def test_ein_wachsender_haushalt_zaehlt_anteilig():
    h = [(date(2025, 1, 1), 2), (date(2025, 7, 1), 3)]
    assert personentage(h, date(2025, 1, 1), date(2026, 1, 1)) == 181 * 2 + 184 * 3


def test_ein_schrumpfender_haushalt_zaehlt_genauso():
    h = [(date(2025, 1, 1), 4), (date(2025, 7, 1), 1)]
    assert personentage(h, date(2025, 1, 1), date(2026, 1, 1)) == 181 * 4 + 184 * 1


def test_personentage_sind_ueber_teilzeitraeume_additiv():
    """Der Zeitraum darf geteilt werden, ohne dass sich die Summe aendert.

    Das ist die Eigenschaft, auf der die Verteilung im Kern beruht: ein
    Mietverhaeltnis, das mitten im Rechnungszeitraum beginnt, bringt genau
    die Personentage mit, die ihm gehoeren -- nicht mehr und nicht weniger.
    """
    h = [(date(2025, 1, 1), 2), (date(2025, 4, 15), 3), (date(2025, 9, 1), 1)]
    ganz = personentage(h, date(2025, 1, 1), date(2026, 1, 1))
    geteilt = (
        personentage(h, date(2025, 1, 1), date(2025, 5, 1))
        + personentage(h, date(2025, 5, 1), date(2025, 10, 20))
        + personentage(h, date(2025, 10, 20), date(2026, 1, 1))
    )
    assert ganz == geteilt


def test_der_wechseltag_wird_nicht_doppelt_gezaehlt():
    """R-NUM-03: der Tag, ab dem ein Stand gilt, gehoert nur dem neuen.

    Zwei aneinandergrenzende Zeitraeume ergeben zusammen genau den ganzen --
    ohne Ueberlappung am Beruehrungstag.
    """
    h = [(date(2025, 1, 1), 2), (date(2025, 7, 1), 3)]
    vorher = personentage(h, date(2025, 1, 1), date(2025, 7, 1))
    nachher = personentage(h, date(2025, 7, 1), date(2026, 1, 1))
    assert vorher == 181 * 2
    assert nachher == 184 * 3
    assert vorher + nachher == personentage(h, date(2025, 1, 1), date(2026, 1, 1))


# --- Der Weg aus der Datenbank in den Kern ----------------------------------


def _haus_mit_zwei_mietverhaeltnissen():
    """Der Fall aus R-NUM-04, einmal als Datenbank.

    Drei Personen ganzjaehrig in der einen Einheit, eine Person ab dem
    01.07. in der anderen. Die Rechnung ist so gewaehlt, dass der Anteil
    genau die Personentage ist: 1279,00 EUR auf 1279 Personentage, ein Euro
    je Personentag -- dann steht das Ergebnis der Regel ungerundet da.
    """
    prop = f.house('Hauptstrasse 1')
    links = f.apt(prop, 'EG links', 50.0)
    rechts = f.apt(prop, 'EG rechts', 50.0)

    familie = f.tenant(links, 'Familie Gross', move_in=date(2020, 1, 1))
    f.haushalt(familie, date(2020, 1, 1), 3)

    single = f.tenant(rechts, 'Bert Klein', move_in=ZUR_JAHRESMITTE)
    f.haushalt(single, ZUR_JAHRESMITTE, 1)

    kat = f.category('Müllabfuhr')
    f.profile(familie, kat, 'personen')
    f.profile(single, kat, 'personen')
    f.invoice(prop, kat, 1279.00, start=JAHR_BEGINN, end=JAHR_ENDE)
    return familie, single


def test_die_historie_kommt_orm_frei_im_kern_an(app_ctx):
    """Der Lader uebergibt Staende, keine Zeilen.

    Der Rechenkern darf kein ORM sehen (NK-037). Die Haushaltsgroessen sind
    die juengste Gelegenheit, eine Beziehung versehentlich durchzureichen --
    deshalb steht hier, was ankommen muss: ``haushalt.Stand``, sortiert.
    """
    familie, _ = _haus_mit_zwei_mietverhaeltnissen()
    f.haushalt(familie, ZUR_JAHRESMITTE, 4)

    vorgang = lade_vorgang(familie.id, JAHR_BEGINN, JAHR_ENDE)

    assert vorgang.mieter.haushaltsgroessen == (
        Stand(date(2020, 1, 1), 3),
        Stand(ZUR_JAHRESMITTE, 4),
    )
    assert all(type(s) is Stand for s in vorgang.mieter.haushaltsgroessen)


def test_ein_mietverhaeltnis_ohne_gepflegte_groesse_kommt_leer_an(app_ctx):
    """Kein Eintrag heisst leer, nicht `[(einzug, 1)]`.

    Die Vorgabe steht an einem Ort -- ``haushalt.VORGABE``. Wuerde der Lader
    hier eine Eins erfinden, gaebe es zwei Orte, und beim naechsten Mal
    liefen sie auseinander.
    """
    prop = f.house('Ohne Pflege')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Anna Mieterin', move_in=date(2020, 1, 1))
    kat = f.category('Müllabfuhr')
    f.profile(mieter, kat, 'personen')
    f.invoice(prop, kat, 1200.00, start=JAHR_BEGINN, end=JAHR_ENDE)

    vorgang = lade_vorgang(mieter.id, JAHR_BEGINN, JAHR_ENDE)

    assert vorgang.mieter.haushaltsgroessen == ()
    assert personen_am(vorgang.mieter.haushaltsgroessen, JAHR_BEGINN) == VORGABE


def test_die_beiden_treppen_sagen_dasselbe(app_ctx):
    """``Tenant.personenanzahl_am`` und ``haushalt.personen_am`` sind eins.

    Die Oberflaeche fragt das Modell, der Kern fragt das Modul. Gaeben sie
    verschiedene Antworten, stuende auf dem Blatt eine andere Zahl als im
    Formular.
    """
    familie, _ = _haus_mit_zwei_mietverhaeltnissen()
    f.haushalt(familie, ZUR_JAHRESMITTE, 4)
    staende = lade_vorgang(familie.id, JAHR_BEGINN, JAHR_ENDE).mieter.haushaltsgroessen

    for tag in (date(2019, 6, 1), JAHR_BEGINN, date(2025, 6, 30),
                ZUR_JAHRESMITTE, JAHR_ENDE):
        assert familie.personenanzahl_am(tag) == personen_am(staende, tag)


# --- Der Rechenkern ---------------------------------------------------------


def _kern_welt(*, wer, betrag='1279.00', profil='personen', zaehler=(),
               kat=None, rechnungen=None):
    """Derselbe Fall wie oben, aber als Datensatz -- ohne Datenbank."""
    kat = kat or Kategorie(id=1, name='Muellabfuhr', braucht_zaehler=False)
    links = Wohnung(id=1, name='EG links', qm=50.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=50.0)
    familie = Mieter(
        id=1, name='Familie Gross', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=1, haushaltsgroessen=(Stand(date(2020, 1, 1), 3),))
    single = Mieter(
        id=2, name='Bert Klein', einzug=ZUR_JAHRESMITTE, auszug=None,
        wohnung_id=2, haushaltsgroessen=(Stand(ZUR_JAHRESMITTE, 1),))
    ich, meine = (familie, links) if wer == 1 else (single, rechts)
    return Vorgang(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(links, rechts),
        mieter_der_immobilie=(familie, single),
        profile={kat.id: profil},
        rechnungen=tuple(rechnungen if rechnungen is not None else (
            Rechnung(id=1, kategorie=kat, betrag=Decimal(betrag),
                     beginn=JAHR_BEGINN, ende=JAHR_ENDE),)),
        zaehler=tuple(zaehler),
    )


def test_der_fall_aus_der_regel():
    """R-NUM-04 woertlich: 1095 zu 184 Personentagen -- plus der Leerstand.

    Drei Personen ganzjaehrig gegen eine Person ab dem 01.07. -- das ist der
    Testfall, den die Regel selbst vorgibt. Bei 1279,00 EUR auf 1279
    Personentage kostet ein Personentag einen Euro, und die beiden Anteile
    stehen unverrechnet da.

    Seit NK-098 steht im Nenner noch eine dritte Zahl: Wohnung rechts ist bis
    zum Einzug am 01.07. leer und zaehlt wie ein Einpersonenhaushalt, 181
    Personentage. 1095 + 184 + 181 = 1460; der Leerstandsanteil bleibt beim
    Vermieter und wird ausgewiesen, statt sich still auf die beiden zu
    verteilen (F-34).
    """
    welt = _kern_welt(wer=1)
    familie = rechne(welt)['line_items'][0]
    single = rechne(_kern_welt(wer=2))['line_items'][0]

    assert familie['tenant_cost'] == Decimal('959.25')
    assert single['tenant_cost'] == Decimal('161.19')
    assert '1095 von 1460 Personentagen' in familie['description']
    assert '184 von 1460 Personentagen' in single['description']
    # Die Aufgeh-Probe: beide Zeilen plus der Leerstandsanteil des Vermieters
    # ergeben wieder die Rechnung.
    assert (
        familie['tenant_cost'] + single['tenant_cost']
        + rechne(welt)['landlord_share']['total_amount']
    ) == Decimal('1279.00')


def test_die_kopfzahl_allein_verteilt_nicht_mehr():
    """Vor NK-046 haetten beide die Haelfte getragen.

    Der alte Zweig teilte durch die Zahl der Mietverhaeltnisse im Zeitraum:
    639,50 EUR fuer die Familie, 639,50 EUR fuer den, der ein halbes Jahr
    allein da war. Genau das ist der Befund, den die Karte behebt.
    """
    familie = rechne(_kern_welt(wer=1))['line_items'][0]

    assert familie['tenant_cost'] != Decimal('639.50')


def test_der_zeitanteil_wird_nicht_zweimal_abgezogen():
    """Die Personentage tragen die Zeit schon in sich.

    Wuerde der Zweig den auf die Mietzeit gestutzten Betrag noch einmal mit
    dem Personentage-Anteil gewichten, bekaeme der Mieter, der zur
    Jahresmitte eingezogen ist, seinen halben Anteil ein zweites Mal
    gekuerzt. Ein Euro je Personentag macht den Fehler sichtbar.

    Seit NK-098 ist der Nenner 1460 statt 1279 -- die 181 Personentage der
    bis zu Berts Einzug leeren Wohnung rechnen fuer den Vermieter mit --,
    also traegt Bert 161,19 EUR statt der frueheren 184,00 EUR.
    """
    single = rechne(_kern_welt(wer=2))['line_items'][0]

    assert single['tenant_cost'] == Decimal('161.19')


def test_ein_wachsender_haushalt_traegt_ab_dem_stichtag_mehr():
    """Zieht jemand ein, steigt der Anteil -- ab dem Tag, nicht rueckwirkend.

    Der Single bekommt zum 01.10. Gesellschaft: 92 Tage zu einem Kopf und 92
    zu zweien sind 276 statt 184 Personentage. Die Familie bleibt bei 1095,
    die bis zum Einzug leere Wohnung zaehlt mit ihren 181 Personentagen fuer
    den Vermieter (NK-098) -- der Nenner waechst auf 1552.
    """
    v = _kern_welt(wer=2)
    gewachsen = replace(v.mieter, haushaltsgroessen=(
        Stand(ZUR_JAHRESMITTE, 1), Stand(date(2025, 10, 1), 2)))
    v = replace(
        v,
        mieter=gewachsen,
        mieter_der_immobilie=(v.mieter_der_immobilie[0], gewachsen),
    )

    posten = rechne(v)['line_items'][0]

    assert '276 von 1552 Personentagen' in posten['description']


def test_der_allgemeinanteil_folgt_denselben_personentagen():
    """Was am Hauptzaehler uebrig bleibt, wird genauso verteilt.

    Der Zweig 'direkt' rechnet den eigenen Verbrauch nach Zaehler ab und
    verteilt den Rest -- was das Haus verbraucht hat, ohne dass eine Wohnung
    es gemessen hat -- auf die Mieter. Stuende dort eine andere Regel als
    beim Personenschluessel, truege die Familie beim Wasser drei Koepfe und
    bei der Treppenbeleuchtung einen.
    """
    wasser = Kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    zaehler = (
        Zaehler(id=10, nummer='Z-10', kategorie_id=2, kategorie_name='Wasser',
                ist_hauptzaehler=True, immobilie_id=1, wohnung_id=None,
                staende=(Zaehlerstand(JAHR_BEGINN, 0.0),
                         Zaehlerstand(JAHR_ENDE, 100.0))),
        Zaehler(id=11, nummer='Z-11', kategorie_id=2, kategorie_name='Wasser',
                ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                staende=(Zaehlerstand(JAHR_BEGINN, 0.0),
                         Zaehlerstand(JAHR_ENDE, 30.0))),
        Zaehler(id=12, nummer='Z-12', kategorie_id=2, kategorie_name='Wasser',
                ist_hauptzaehler=False, immobilie_id=1, wohnung_id=2,
                staende=(Zaehlerstand(JAHR_BEGINN, 0.0),
                         Zaehlerstand(JAHR_ENDE, 30.0))),
    )
    v = _kern_welt(
        wer=1, profil='direkt', kat=wasser, zaehler=zaehler,
        rechnungen=(Rechnung(id=1, kategorie=wasser, betrag=Decimal('1000.00'),
                             beginn=JAHR_BEGINN, ende=JAHR_ENDE),))

    posten = rechne(v)['line_items'][0]

    # 100 Einheiten zu 10,00 EUR, davon 30 eigen gemessen und 40 allgemein.
    # Vom Allgemeinen traegt die Familie 1095 von 1279 Personentagen.
    assert '1095 von 1279 Personentagen' in posten['description']
    assert posten['tenant_cost'] == Decimal('300.00') + Decimal('342.46')
