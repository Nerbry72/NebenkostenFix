"""NK-048: die Heizungsanlage ist eine eigene Sache (R-HK-02).

Der Befund war keine falsche Zahl, sondern ein fehlender Begriff. § 7 Abs. 1
HeizkostenV verteilt "die Kosten des Betriebs der zentralen Heizungsanlage"
zu 50 bis 70 vom Hundert nach Verbrauch. Diese Kosten sind nie eine Rechnung:
§ 7 Abs. 2 zaehlt acht Posten auf, die in der Praxis von vier bis sechs Firmen
kommen. Solange die Anwendung jede Rechnung fuer sich verteilte, war der
Verbrauchsanteil nicht einmal formulierbar -- er bezieht sich auf die Summe.

Geprueft wird hier nur ``heizung.py``, der eine Ort. Das Schema und die
Wanderung stehen in ``tests/test_migrations.py``, die Verteilung selbst kommt
mit NK-049 -- in dieser Karte wird noch nicht gerechnet.
"""

from __future__ import annotations

import ast
import doctest
import pathlib
from decimal import Decimal

import pytest

import betrkv
import heizung
from heizung import (
    ANTEIL_MAX,
    ANTEIL_MIN,
    ANTEIL_VORGABE,
    BETRKV_NR,
    HEIZUNG,
    HINWEIS_ANTEIL,
    KOSTENARTEN,
    REIHENFOLGE,
    SCHLUESSEL,
    VERBUNDEN,
    VERSORGT,
    WARMWASSER,
    HeizungsFehler,
    betrkv_nr,
    bezeichnung,
    flaechenanteil,
    gruppensumme,
    ist_kostenart,
    nach_flaeche,
    nach_verbrauch,
    ist_versorgungsart,
    pruefe_anteil,
    teile_masse,
    pruefe_kostenart,
    pruefe_versorgungsart,
    WW_ERSATZ,
    WW_ERSATZ_JE_QM,
    WW_FAKTOR,
    WW_FORMEL,
    WW_KALTWASSER_GRAD,
    WW_WEGE,
    WW_WEG_TEXT,
    WW_ZAEHLER,
    brennstoffanteil,
    ist_warmwasserweg,
    pruefe_warmwasserweg,
    trenne_verbundene,
    warmwasseranteil,
    warmwassermenge_ersatz,
    warmwassermenge_formel,
)

WURZEL = pathlib.Path(__file__).resolve().parent.parent


# --- Was das Modul ueber sich selbst sagt -----------------------------------


def test_doctests_im_modul_laufen():
    ergebnis = doctest.testmod(heizung, verbose=False)
    assert ergebnis.failed == 0, f'{ergebnis.failed} Doctests in heizung.py schlagen fehl'


def test_modul_haengt_an_nichts_als_geld():
    """Derselbe Waechter wie fuer ``haushalt`` und ``leerstand``: kein ORM.

    ``heizung`` wird ab NK-049 ein Baustein des Rechenkerns (NK-037). Zoege es
    ein Modell herein, waere der Kern ueber einen Umweg wieder an der
    Datenbank. ``geld`` ist erlaubt -- es bringt ``sqlalchemy.Numeric`` mit,
    eine Typangabe fuer das Schema, und holt keine Daten.
    """
    baum = ast.parse((WURZEL / 'heizung.py').read_text(encoding='utf-8'))

    importiert = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            importiert.update(a.name.split('.')[0] for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            importiert.add(knoten.module.split('.')[0])

    assert importiert <= {
        '__future__', 'decimal', 'typing', 'geld',
    }, f'heizung.py zieht fremde Module herein: {importiert}'


# --- Der Katalog des § 7 Abs. 2 ---------------------------------------------


def test_alle_acht_posten_des_gesetzes_stehen_drin():
    """Acht Posten, keiner mehr und keiner weniger.

    Wer einen vergisst, laesst dem Vermieter keine Stelle, an der er die
    Rechnung eintragen kann -- und die Verteilmasse des § 7 Abs. 1 waere zu
    klein.
    """
    assert set(KOSTENARTEN) == {
        'brennstoff',
        'betriebsstrom',
        'bedienung',
        'pruefung',
        'reinigung',
        'messung',
        'anmietung_erfassung',
        'verwendung_erfassung',
    }
    assert len(KOSTENARTEN) == 8


def test_die_schluesselmenge_ist_der_katalog():
    assert SCHLUESSEL == frozenset(KOSTENARTEN)


def test_jeder_schluessel_ist_kleines_ascii():
    """Die Schluessel wandern in die Datenbank und in JSON.

    Ein Umlaut oder ein Grossbuchstabe darin waere eine Falle beim Vergleich:
    die CHECK-Bedingung der Tabelle zaehlt sie woertlich auf.
    """
    for schluessel in KOSTENARTEN:
        assert schluessel.isascii()
        assert schluessel == schluessel.lower()
        assert schluessel.replace('_', '').isalpha()


def test_jeder_posten_hat_eine_bezeichnung_fuer_den_vermieter():
    for schluessel, text in KOSTENARTEN.items():
        assert bezeichnung(schluessel) == text
        assert text[0].isupper(), f'{schluessel} faengt klein an'


def test_der_katalog_kennt_nur_sich_selbst():
    assert ist_kostenart('brennstoff') is True
    for fremd in ('Brennstoff', 'grundsteuer', '', None, 4):
        assert ist_kostenart(fremd) is False


def test_ein_fremder_posten_faellt_beim_pruefen_auf():
    with pytest.raises(HeizungsFehler) as fehler:
        pruefe_kostenart('kaminkehrer')
    # Die Meldung muss sagen, was stattdessen zur Wahl steht -- sonst raet der
    # Vermieter.
    for schluessel in KOSTENARTEN:
        assert schluessel in str(fehler.value)


def test_bezeichnung_prueft_mit():
    with pytest.raises(HeizungsFehler):
        bezeichnung('gartenpflege')


# --- Was eine Anlage versorgt -----------------------------------------------


def test_es_gibt_genau_drei_versorgungsarten():
    assert VERSORGT == {HEIZUNG, WARMWASSER, VERBUNDEN}
    assert len(REIHENFOLGE) == 3
    assert frozenset(REIHENFOLGE) == VERSORGT


def test_die_reihenfolge_ist_die_des_gesetzes():
    """Nr. 4, dann Nr. 5, dann Nr. 6 -- nicht das Alphabet.

    Alphabetisch stuende "verbunden" vor "warmwasser". Der Vermieter liest die
    drei aber in jeder Meldung und in jedem Auswahlfeld, und dort sollen sie
    in der Ordnung des § 2 BetrKV stehen.
    """
    assert REIHENFOLGE == (HEIZUNG, WARMWASSER, VERBUNDEN)
    assert [BETRKV_NR[art] for art in REIHENFOLGE] == [4, 5, 6]


def test_eine_vierte_art_gibt_es_nicht():
    assert ist_versorgungsart(VERBUNDEN) is True
    for fremd in ('fernwaerme', 'beides', '', None):
        assert ist_versorgungsart(fremd) is False
    with pytest.raises(HeizungsFehler) as fehler:
        pruefe_versorgungsart('fernwaerme')
    assert 'fernwaerme' in str(fehler.value)
    for art in REIHENFOLGE:
        assert art in str(fehler.value)


def test_die_verbundene_anlage_traegt_nummer_sechs():
    """Nicht Nr. 4 und nicht Nr. 5, sondern Nr. 6 (§ 9 HeizkostenV).

    Die Abrechnung muss die Kostenart benennen (R-DOC-01). Wer eine
    verbundene Anlage unter Nr. 4 fuehrt, nennt die Warmwasserkosten
    Heizkosten.
    """
    assert betrkv_nr(HEIZUNG) == 4
    assert betrkv_nr(WARMWASSER) == 5
    assert betrkv_nr(VERBUNDEN) == 6


def test_die_nummern_gibt_es_im_katalog_des_paragrafen_zwei():
    """Der Querbezug zu NK-044: 4, 5 und 6 sind dort echte Positionen."""
    for nummer in BETRKV_NR.values():
        assert nummer in betrkv.NUMMERN
    assert 'Heizung' in betrkv.bezeichnung(4)
    assert 'Warmwasser' in betrkv.bezeichnung(5)


def test_eine_fremde_art_hat_keine_nummer():
    with pytest.raises(HeizungsFehler):
        betrkv_nr('fernwaerme')


# --- Der Rahmen des § 7 Abs. 1 ----------------------------------------------


def test_der_rahmen_ist_fuenfzig_bis_siebzig():
    assert (ANTEIL_MIN, ANTEIL_MAX) == (50, 70)
    for prozent in range(ANTEIL_MIN, ANTEIL_MAX + 1):
        assert pruefe_anteil(prozent) == prozent


def test_unter_fuenfzig_und_ueber_siebzig_ist_nichts_zulaessig():
    for daneben in (0, 49, 71, 100):
        with pytest.raises(HeizungsFehler) as fehler:
            pruefe_anteil(daneben)
        assert str(daneben) in str(fehler.value)
        assert '§ 7 Abs. 1 HeizkostenV' in str(fehler.value)


def test_eine_prozentangabe_ist_eine_ganze_zahl():
    """Ein Kaestchen ist keine Zahl, und 65,5 vom Hundert sieht die Verordnung
    nicht vor -- sie spricht von vom Hundert, nicht von Bruchteilen davon."""
    for keine_zahl in (True, False, 65.0, Decimal('65'), '65', None):
        with pytest.raises(HeizungsFehler):
            pruefe_anteil(keine_zahl)


def test_die_vorgabe_liegt_im_rahmen_und_ist_die_obergrenze():
    assert pruefe_anteil(ANTEIL_VORGABE) == ANTEIL_VORGABE
    assert ANTEIL_VORGABE == ANTEIL_MAX


def test_im_sonderfall_sind_siebzig_zwingend():
    """§ 7 Abs. 1 Satz 2 ist kein Wahlrecht, sondern ein Muss.

    Schlecht gedaemmtes Gebaeude, Oel oder Gas, ueberwiegend gedaemmte
    Leitungen: dann *sind* 70 vom Hundert nach Verbrauch zu verteilen. Ein
    Vermieter, der dort 50 eintraegt, rechnet falsch ab, und der Mieter darf
    kuerzen.
    """
    assert pruefe_anteil(ANTEIL_MAX, sonderfall=True) == ANTEIL_MAX
    for zu_wenig in (50, 60, 69):
        with pytest.raises(HeizungsFehler) as fehler:
            pruefe_anteil(zu_wenig, sonderfall=True)
        assert 'Satz 2' in str(fehler.value)


def test_der_flaechenanteil_ergaenzt_den_verbrauchsanteil_auf_hundert():
    """§ 7 Abs. 1 Satz 5: der Rest geht nach Flaeche. Kein Cent faellt weg."""
    for prozent in range(ANTEIL_MIN, ANTEIL_MAX + 1):
        assert prozent + flaechenanteil(prozent) == 100
    assert flaechenanteil(ANTEIL_VORGABE) == 30


def test_der_flaechenanteil_prueft_denselben_rahmen():
    with pytest.raises(HeizungsFehler):
        flaechenanteil(30)


def test_der_hinweis_nennt_beide_grenzen_und_die_fundstelle():
    """Steht in der Oberflaeche ueber dem Eingabefeld und in der Abrechnung."""
    assert str(ANTEIL_MIN) in HINWEIS_ANTEIL
    assert str(ANTEIL_MAX) in HINWEIS_ANTEIL
    assert '§ 7 Abs. 1' in HINWEIS_ANTEIL
    assert 'HeizkostenV' in HINWEIS_ANTEIL


# --- Die Verteilmasse: alle Posten zusammen ---------------------------------


def test_vier_rechnungen_ergeben_eine_heizkostensumme():
    """Der Fall aus R-HK-02, so wie er beim Vermieter ankommt.

    Vier Umschlaege von vier Firmen: das Gaswerk, der Stadtwerke-Zaehler fuer
    den Betriebsstrom, der Heizungsbauer fuer die Wartung und der
    Ablesedienst. Vor NK-048 waren das vier Kostenarten, jede fuer sich
    verteilt. Seither sind sie **eine** Masse -- und nur auf diese Masse
    laesst sich der Verbrauchsanteil des § 7 Abs. 1 anwenden.
    """
    posten = [
        ('brennstoff', Decimal('8200.00')),
        ('betriebsstrom', Decimal('310.50')),
        ('bedienung', Decimal('420.00')),
        ('verwendung_erfassung', Decimal('180.00')),
    ]

    assert gruppensumme(posten) == Decimal('9110.50')

    # Einzeln verteilt waere jede Rechnung ihre eigene Masse gewesen. Die
    # Probe darauf, dass hier wirklich addiert und nicht gerundet wird:
    assert gruppensumme(posten) == sum(betrag for _, betrag in posten)


def test_die_masse_bleibt_ein_decimal_und_verliert_nichts():
    """Summiert wird ueber ``geld.summe`` -- nie mit ``float`` (R-NUM-01).

    Gerundet wird hier absichtlich **nicht**: die Masse ist ein
    Zwischenergebnis, und gerundet wird erst am Ende der Kette, wenn die
    Anteile feststehen (R-NUM-02, ab NK-049). Rechnungsbetraege stehen im
    Schema auf Cent (``Numeric(12,2)``), also steht es auch die Summe.
    """
    summe = gruppensumme([
        ('brennstoff', Decimal('0.10')),
        ('betriebsstrom', Decimal('0.20')),
        ('bedienung', Decimal('0.30')),
    ])
    assert isinstance(summe, Decimal)
    assert summe == Decimal('0.60')
    # 0.1 + 0.2 + 0.3 waere als float 0.6000000000000001.
    assert summe != Decimal(repr(0.1 + 0.2 + 0.3))

    # Auch ein aus JSON hereingereichter float kommt als Decimal wieder
    # heraus -- ``geld.dec`` nimmt ihn an, ``float`` bleibt er nicht.
    assert isinstance(gruppensumme([('brennstoff', 12.34)]), Decimal)


def test_ohne_posten_ist_die_masse_null():
    assert gruppensumme([]) == Decimal('0')


def test_ein_fremder_posten_faellt_hier_auf_und_nicht_erst_beim_verteilen():
    with pytest.raises(HeizungsFehler):
        gruppensumme([
            ('brennstoff', Decimal('8200.00')),
            ('gartenpflege', Decimal('100.00')),
        ])


def test_derselbe_posten_darf_zweimal_kommen():
    """Zwei Brennstoffrechnungen im Jahr sind der Normalfall, keine Dublette:
    im Maerz getankt und im Oktober noch einmal."""
    assert gruppensumme([
        ('brennstoff', Decimal('4000.00')),
        ('brennstoff', Decimal('4200.00')),
    ]) == Decimal('8200.00')


# --- Die Verteilung nach § 7 Abs. 1 (R-HK-01, NK-049) ----------------------


def test_masse_teilt_sich_in_verbrauch_und_grund():
    """10.000 bei 70 Prozent: 7.000 nach Verbrauch, 3.000 nach Flaeche."""
    assert teile_masse(Decimal('10000.00'), 70) == (
        Decimal('7000.00'), Decimal('3000.00'))


def test_die_teilung_verliert_nichts():
    """Kein Cent faellt zwischen die beiden Massen -- bei keinem Satz.

    Gerundet wird hier noch nicht (R-NUM-02): das geschieht erst am Ende der
    Kette. Deshalb muessen die beiden Teile exakt die Masse ergeben.
    """
    for satz in range(ANTEIL_MIN, ANTEIL_MAX + 1):
        for betrag in ('999.99', '0.01', '12345.67', '1000.00'):
            verbrauch, grund = teile_masse(Decimal(betrag), satz)
            assert verbrauch + grund == Decimal(betrag), (satz, betrag)


def test_die_teilung_haelt_sich_an_den_rahmen():
    """45 Prozent gibt es nicht -- der Rahmen des Gesetzes gilt auch hier."""
    with pytest.raises(HeizungsFehler):
        teile_masse(Decimal('1000.00'), 45)


def test_verbrauchsanteil_nach_gemessener_menge():
    """1.200 von 2.000 kWh sind 60 Prozent von 7.000 = 4.200."""
    assert nach_verbrauch(Decimal('7000.00'), 1200, 6000) == Decimal('1400.00')
    assert nach_verbrauch(Decimal('7000.00'), 1200, 2000) == Decimal('4200.00')


def test_ohne_gesamtverbrauch_kein_anteil():
    """Ein Nenner von null teilt nicht -- er gibt null, statt zu stuerzen.

    Der Fall heisst nicht "kostenlos": er heisst "hier ist nichts erfasst",
    und was dann geschieht, entscheidet der Kern (D-48), nicht diese Formel.
    """
    assert nach_verbrauch(Decimal('7000.00'), 0, 0) == Decimal('0')
    assert nach_verbrauch(Decimal('7000.00'), 100, None) == Decimal('0')


def test_grundanteil_nach_flaeche():
    """75 von 250 qm sind 30 Prozent von 3.000 = 900."""
    assert nach_flaeche(Decimal('3000.00'), 75, 250) == Decimal('900.00')
    assert nach_flaeche(Decimal('3000.00'), 50, 0) == Decimal('0')


def test_alle_anteile_zusammen_ergeben_die_masse():
    """Drei Wohnungen, ein Haus: am Ende ist die ganze Masse verteilt."""
    verbrauch, grund = teile_masse(Decimal('10000.00'), 65)
    verbraeuche = (1200, 800, 2000)
    flaechen = (50, 60, 90)
    ganz = sum(
        nach_verbrauch(verbrauch, v, sum(verbraeuche))
        + nach_flaeche(grund, q, sum(flaechen))
        for v, q in zip(verbraeuche, flaechen)
    )
    assert ganz == Decimal('10000.00')


# --- Die verbundene Anlage: Warmwasser abtrennen (R-HK-03, NK-050) ---------


def test_die_drei_wege_stehen_in_der_rangfolge_des_gesetzes():
    """Gemessen vor gerechnet, gerechnet vor geschaetzt (§ 9 Abs. 2)."""
    assert WW_WEGE == (WW_ZAEHLER, WW_FORMEL, WW_ERSATZ)
    assert set(WW_WEG_TEXT) == set(WW_WEGE)


def test_jeder_weg_sagt_in_der_abrechnung_worauf_er_beruht():
    """R-HK-03 verlangt, dass der gewaehlte Weg ausgewiesen wird.

    Der Mieter soll nachrechnen koennen, warum gerade dieser Teil der Kosten
    auf das Warmwasser entfaellt. Ein Text wie "Warmwasseranteil 25 %" allein
    sagt ihm das nicht -- er muss wissen, ob gemessen oder geschaetzt wurde.
    """
    for weg in WW_WEGE:
        assert '§ 9' in WW_WEG_TEXT[weg], weg


def test_nur_die_drei_wege_zaehlen():
    assert ist_warmwasserweg(WW_FORMEL)
    assert not ist_warmwasserweg('Formel')
    assert not ist_warmwasserweg(None)
    assert pruefe_warmwasserweg(WW_ERSATZ) == WW_ERSATZ
    with pytest.raises(HeizungsFehler, match='§ 9'):
        pruefe_warmwasserweg('geschaetzt')


def test_die_formel_trifft_den_pruefwert_der_regel():
    """R-HK-03: V = 120 m3, tw = 60 Grad -> Q = 2,5 * 120 * 50 = 15.000 kWh."""
    assert warmwassermenge_formel(120, 60) == Decimal('15000')


def test_die_formel_benutzt_die_zahlen_der_verordnung():
    """2,5 kWh je m3 und Kelvin, 10 Grad Kaltwasser -- keine anderen."""
    assert WW_FAKTOR == Decimal('2.5')
    assert WW_KALTWASSER_GRAD == Decimal('10')
    assert warmwassermenge_formel(1, 11) == Decimal('2.5')


def test_warmwasser_unter_kaltwassertemperatur_ist_keine_angabe():
    """Unter 10 Grad gaebe die Formel eine negative Waermemenge her.

    Das ist keine Rechnung mit ungewoehnlichem Ergebnis, sondern ein
    Tippfehler im Formular -- und der faellt hier auf, nicht in der
    Abrechnung.
    """
    for grad in (10, 8, 0, -3):
        with pytest.raises(HeizungsFehler, match='Warmwassertemperatur'):
            warmwassermenge_formel(120, grad)


def test_negative_mengen_sind_keine_mengen():
    with pytest.raises(HeizungsFehler, match='Warmwasservolumen'):
        warmwassermenge_formel(-1, 60)
    with pytest.raises(HeizungsFehler, match='Wohnfläche'):
        warmwassermenge_ersatz(-1)


def test_die_ersatzformel_trifft_den_pruefwert_der_regel():
    """R-HK-03: A_Wohn = 250 m2 -> Q = 32 * 250 = 8.000 kWh."""
    assert warmwassermenge_ersatz(250) == Decimal('8000')
    assert WW_ERSATZ_JE_QM == Decimal('32')


def test_der_brennstoffanteil_rechnet_waerme_in_brennstoff_um():
    """B = Q / Hi. 15.000 kWh bei 10 kWh je Liter sind 1.500 Liter Heizoel."""
    assert brennstoffanteil(Decimal('15000'), 10) == Decimal('1500')


def test_ohne_heizwert_kein_brennstoffanteil():
    """Ein Heizwert von null waere eine Division durch null.

    Anders als beim fehlenden Nenner in ``nach_verbrauch`` ist das keine
    Luecke in den Daten, sondern ein unmoeglicher Wert: einen Brennstoff
    ohne Heizwert gibt es nicht.
    """
    for hi in (0, -1):
        with pytest.raises(HeizungsFehler, match='Heizwert'):
            brennstoffanteil(Decimal('15000'), hi)


def test_der_anteil_ist_ein_bruch_zweier_mengen():
    """15.000 von 60.000 kWh: ein Viertel der Kosten ist Warmwasser."""
    assert warmwasseranteil(Decimal('15000'), Decimal('60000')) == Decimal('0.25')


def test_die_einheit_kuerzt_sich_aus_dem_bruch():
    """Liter oder Kilowattstunden -- der Anteil ist derselbe.

    Deshalb ist ``brennstoffanteil`` nur noetig, wenn der Gesamtverbrauch in
    Brennstoff gemessen ist. Liegt er in Kilowattstunden vor, wie auf jeder
    Gasrechnung, entfaellt der Schritt.
    """
    in_kwh = warmwasseranteil(Decimal('15000'), Decimal('60000'))
    in_litern = warmwasseranteil(
        brennstoffanteil(Decimal('15000'), 10),
        brennstoffanteil(Decimal('60000'), 10),
    )
    assert in_kwh == in_litern


def test_ohne_gesamtmenge_kein_anteil():
    """Derselbe Weg wie bei ``nach_verbrauch``: null statt Absturz.

    Was dann geschieht, entscheidet der Kern -- er verteilt alles als
    Heizkosten und warnt (``HINWEIS_OHNE_TRENNUNG``).
    """
    assert warmwasseranteil(Decimal('15000'), 0) == Decimal('0')
    assert warmwasseranteil(Decimal('15000'), None) == Decimal('0')


def test_mehr_warmwasser_als_gesamtverbrauch_ist_ein_widerspruch():
    """Kein fehlender Wert, sondern zwei Angaben, die sich widersprechen."""
    with pytest.raises(HeizungsFehler, match='größer als der Gesamtverbrauch'):
        warmwasseranteil(Decimal('70000'), Decimal('60000'))
    with pytest.raises(HeizungsFehler, match='negative Menge'):
        warmwasseranteil(Decimal('-1'), Decimal('60000'))


def test_die_trennung_teilt_die_masse_in_zwei():
    """10.000 bei einem Viertel: 2.500 Warmwasser, 7.500 Heizung."""
    warm, heiz = trenne_verbundene(Decimal('10000.00'), Decimal('0.25'))
    assert warm == Decimal('2500')
    assert heiz == Decimal('7500')


def test_die_trennung_verliert_nichts():
    """Kein Cent faellt zwischen Warmwasser und Heizung -- bei keinem Anteil.

    Dieselbe Pruefung wie bei ``teile_masse``: der zweite Teil ist die
    Differenz und nicht die zweite Multiplikation, sonst faenden sich beide
    Teile am Ende nicht mehr zur Masse zusammen.
    """
    anteile = [Decimal('0'), Decimal('0.25'), Decimal('1'),
               Decimal('1') / Decimal('3'), Decimal('0.4712')]
    for anteil in anteile:
        for betrag in ('999.99', '0.01', '12345.67', '1000.00'):
            warm, heiz = trenne_verbundene(Decimal(betrag), anteil)
            assert warm + heiz == Decimal(betrag), (anteil, betrag)


def test_die_trennung_haelt_sich_an_null_bis_eins():
    for anteil in (Decimal('1.5'), Decimal('-0.1')):
        with pytest.raises(HeizungsFehler, match='Warmwasseranteil'):
            trenne_verbundene(Decimal('100.00'), anteil)


def test_trennung_und_verteilung_greifen_ineinander():
    """Der ganze Weg des § 9 und des § 7 an einem Beispiel.

    Eine verbundene Anlage verbraucht 60.000 kWh, davon 15.000 fuer das
    Warmwasser. Von den 12.000 Euro Kosten sind also 3.000 Warmwasser und
    9.000 Heizung; die 9.000 gehen zu 70 Prozent nach Verbrauch. Am Ende ist
    jeder Cent der 12.000 einem der drei Toepfe zugeordnet.
    """
    anteil = warmwasseranteil(Decimal('15000'), Decimal('60000'))
    warm, heiz = trenne_verbundene(Decimal('12000.00'), anteil)
    assert (warm, heiz) == (Decimal('3000'), Decimal('9000'))
    verbrauchsteil, grundteil = teile_masse(heiz, ANTEIL_VORGABE)
    assert (verbrauchsteil, grundteil) == (Decimal('6300'), Decimal('2700'))
    assert warm + verbrauchsteil + grundteil == Decimal('12000.00')
