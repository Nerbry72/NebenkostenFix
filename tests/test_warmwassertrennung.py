"""NK-050: die verbundene Anlage trennen -- § 9 HeizkostenV, R-HK-03.

Ein Kessel, zwei Kostenarten: Waerme nach § 7, Warmwasser nach § 8. Getrennt
wird **vor** der Verteilung, und zwar nach Waermemengen -- gemessen (§ 9
Abs. 2 Satz 1), gerechnet (``Q = 2,5 · V · (tw − 10)``) oder geschaetzt
(``Q = 32 · A_Wohn``). Welcher Weg genommen wurde, steht in der Abrechnung.

Die Zahlen sind mit der Hand nachgerechnet und stehen im Docstring. Alle
Faelle laufen ohne Datenbank, wie der ganze Kern seit NK-037.
"""

from datetime import date
from decimal import Decimal

from nebenkostenfix import heizung
from nebenkostenfix.rechenkern import (
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    anlagen_warmwasseranteil,
    anlagen_warmwassermenge,
    anlagen_wohnungen,
    ist_warmwasserzaehler,
    rechne,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)

WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True,
                   betrkv_nr=4)
WARMWASSER = Kategorie(id=10, name='Warmwasser', braucht_zaehler=True,
                       betrkv_nr=5)


def anlage(id=1, name='Kessel', prozent=70, versorgt=heizung.VERBUNDEN,
           weg=heizung.WW_ZAEHLER, kwh='15000', gesamt='60000', **kw):
    """Eine verbundene Anlage, die ein Viertel ihrer Waerme ans Wasser gibt."""
    return Heizungsanlage(
        id=id,
        name=name,
        versorgt=versorgt,
        verbrauchsanteil_prozent=prozent,
        warmwasser_weg=weg,
        warmwasser_kwh=Decimal(kwh) if kwh is not None else None,
        brennstoff_menge=Decimal(gesamt) if gesamt is not None else None,
        **kw,
    )


def heizrechnung(betrag='10000.00', id=1, anlage_id=1, art='brennstoff'):
    return Rechnung(
        id=id,
        kategorie=WAERME,
        betrag=Decimal(betrag),
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        heizungsanlage_id=anlage_id,
        heizkostenart=art,
    )


def _zaehler(id, wohnung_id, verbraucht, kategorie, anlage_id=1,
             kategorie_betrkv_nr='wie die Kostenart'):
    # Die Nummer kommt aus der Kostenart des Fixtures (NK-121); mit
    # ``kategorie_betrkv_nr=None`` baut einer die Probe ohne Katalog.
    if kategorie_betrkv_nr == 'wie die Kostenart':
        kategorie_betrkv_nr = kategorie.betrkv_nr
    return Zaehler(
        id=id,
        nummer=f'Z-{id}',
        kategorie_id=kategorie.id,
        kategorie_name=kategorie.name,
        ist_hauptzaehler=False,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=(Stand(datum=JAHR_BEGINN, wert=0.0),
                 Stand(datum=date(2025, 1, 1), wert=verbraucht)),
        heizungsanlage_id=anlage_id,
        kategorie_betrkv_nr=kategorie_betrkv_nr,
    )


def waermezaehler(id, wohnung_id, verbraucht, anlage_id=1,
                  kategorie_betrkv_nr='wie die Kostenart'):
    return _zaehler(id, wohnung_id, verbraucht, WAERME, anlage_id,
                    kategorie_betrkv_nr=kategorie_betrkv_nr)


def wasserzaehler(id, wohnung_id, verbraucht, anlage_id=1,
                  kategorie_betrkv_nr='wie die Kostenart'):
    return _zaehler(id, wohnung_id, verbraucht, WARMWASSER, anlage_id,
                    kategorie_betrkv_nr=kategorie_betrkv_nr)


#: Der Regelfall dieser Datei: 1.200 von 2.000 kWh Waerme, 30 von 100 m3
#: Warmwasser. Die beiden Nenner sind verschieden -- das ist der Sinn der
#: Trennung, denn wer viel heizt, badet deshalb noch lange nicht viel.
ZAEHLER = (
    waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0),
    wasserzaehler(3, 1, 30.0), wasserzaehler(4, 2, 70.0),
)


def haus(rechnungen=None, zaehler=ZAEHLER, anlagen=None, qm=50.0, **kw):
    """Zwei gleich grosse Wohnungen, mein Mieter wohnt in der linken."""
    meine = Wohnung(id=1, name='EG links', qm=qm)
    andere = Wohnung(id=2, name='EG rechts', qm=qm)
    ich = Mieter(id=1, name='Anna Mieterin', einzug=date(2020, 1, 1),
                 auszug=None, wohnung_id=1)
    nachbar = Mieter(id=2, name='Bert Nachbar', einzug=date(2020, 1, 1),
                     auszug=None, wohnung_id=2)
    grund = dict(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(meine, andere),
        mieter_der_immobilie=(ich, nachbar),
        profile={},
        rechnungen=tuple(rechnungen if rechnungen is not None
                         else (heizrechnung(),)),
        zaehler=tuple(zaehler),
        heizungsanlagen=tuple(anlagen or (anlage(),)),
    )
    grund.update(kw)
    return Vorgang(**grund)


def zeilen(ergebnis):
    """Die Zeilen der Anlage, nach Zweck -- ``{'heizung': ..., ...}``."""
    return {
        z['heizung_details']['zweck']: z
        for z in ergebnis['line_items'] if z['billing_type'] == 'heizkosten'
    }


# --- Die Trennung gelingt --------------------------------------------------


def test_der_waermezaehler_trennt_die_masse():
    """15.000 von 60.000 kWh ans Wasser: aus 10.000 werden 2.500 und 7.500.

    Heizung: Verbrauchsteil 7.500 · 0,7 = 5.250, davon 1.200 von 2.000 kWh
    = 3.150; Grundteil 2.250, davon 50 von 100 qm = 1.125. Zusammen 4.275.

    Warmwasser: Verbrauchsteil 2.500 · 0,7 = 1.750, davon 30 von 100 m3
    = 525; Grundteil 750, davon 50 von 100 qm = 375. Zusammen 900.
    """
    ergebnis = rechne(haus())
    zwei = zeilen(ergebnis)

    assert set(zwei) == {heizung.HEIZUNG, heizung.WARMWASSER}
    assert zwei[heizung.HEIZUNG]['tenant_cost'] == Decimal('4275.00')
    assert zwei[heizung.WARMWASSER]['tenant_cost'] == Decimal('900.00')
    assert ergebnis['total_amount'] == Decimal('5175.00')


def test_die_beiden_zeilen_ergeben_zusammen_die_rechnung():
    """Getrennt wird verlustfrei -- auch bei einem krummen Anteil (1 von 3)."""
    zwei = zeilen(rechne(haus(
        anlagen=(anlage(kwh='1', gesamt='3'),))))

    massen = [z['total_amount'] for z in zwei.values()]
    assert sum(massen) == Decimal('10000.00')
    assert massen == [Decimal('6666.67'), Decimal('3333.33')]


def test_jede_zeile_traegt_ihre_nummer_und_ihren_paragrafen():
    """§ 2 Nr. 4 BetrKV fuer die Waerme, Nr. 5 fuer das Warmwasser."""
    zwei = zeilen(rechne(haus()))
    heiz, warm = zwei[heizung.HEIZUNG], zwei[heizung.WARMWASSER]

    assert heiz['category'] == 'Heizkosten (Kessel)'
    assert warm['category'] == 'Warmwasserkosten (Kessel)'
    assert heiz['heizung_details']['betrkv_nr'] == 4
    assert warm['heizung_details']['betrkv_nr'] == 5
    assert '§ 7 HeizkostenV' in heiz['description']
    assert '§ 8 HeizkostenV' in warm['description']
    # Die Nenner sind verschieden, und das steht auch da.
    assert heiz['heizung_details']['unit'] == 'kWh'
    assert warm['heizung_details']['unit'] == 'm³'


def test_der_gewaehlte_weg_steht_in_der_abrechnung():
    """R-HK-03: nicht nur das Ergebnis, auch der Weg dahin."""
    warm = zeilen(rechne(haus()))[heizung.WARMWASSER]['heizung_details']

    assert warm['warmwasser_weg'] == heizung.WW_ZAEHLER
    assert 'gemessen' in warm['warmwasser_weg_text']
    assert warm['warmwasser_anteil_prozent'] == Decimal('25.00')
    assert warm['trennungsgrund'] is None


def test_die_formel_des_paragrafen_neun():
    """Q = 2,5 · 120 · (60 − 10) = 15.000 kWh -- der Pruefwert aus R-HK-03."""
    ergebnis = rechne(haus(anlagen=(anlage(
        weg=heizung.WW_FORMEL, kwh=None,
        warmwasser_volumen_m3=Decimal('120'),
        warmwasser_temperatur_c=Decimal('60')),)))
    zwei = zeilen(ergebnis)

    assert zwei[heizung.WARMWASSER]['tenant_cost'] == Decimal('900.00')
    assert zwei[heizung.HEIZUNG]['tenant_cost'] == Decimal('4275.00')


def test_die_ersatzformel_rechnet_mit_der_flaeche_der_anlage():
    """Q = 32 · 250 = 8.000 kWh, von 32.000 -- wieder ein Viertel."""
    ergebnis = rechne(haus(
        qm=125.0,
        anlagen=(anlage(weg=heizung.WW_ERSATZ, kwh=None, gesamt='32000'),)))
    zwei = zeilen(ergebnis)

    assert zwei[heizung.WARMWASSER]['tenant_cost'] == Decimal('900.00')
    assert zwei[heizung.HEIZUNG]['tenant_cost'] == Decimal('4275.00')


def test_der_heizwert_rechnet_die_waermemenge_in_brennstoff_um():
    """15.000 kWh durch 10 kWh je Liter = 1.500 von 6.000 Litern Oel."""
    ergebnis = rechne(haus(anlagen=(anlage(
        gesamt='6000', heizwert_kwh=Decimal('10')),)))

    assert zeilen(ergebnis)[heizung.WARMWASSER]['tenant_cost'] == Decimal('900.00')


# --- Die Trennung gelingt nicht -------------------------------------------


def _ohne_trennung(anlage_ohne):
    ergebnis = rechne(haus(anlagen=(anlage_ohne,)))
    eine = zeilen(ergebnis)
    assert set(eine) == {heizung.HEIZUNG}
    return ergebnis, eine[heizung.HEIZUNG]['heizung_details']


def test_ohne_weg_bleibt_es_bei_einer_zeile():
    """Kein Weg angegeben: alles als Heizkosten, Nummer 6, mit Hinweis.

    4.200 + 1.500 = 5.700 -- die ungetrennte Verteilung aus NK-049.
    """
    ergebnis, details = _ohne_trennung(anlage(weg=None))

    assert details['trennungsgrund'] == heizung.OHNE_WEG
    assert details['betrkv_nr'] == 6
    assert ergebnis['total_amount'] == Decimal('5700.00')
    assert any('§ 9 HeizkostenV' in w for w in ergebnis['warnings'])


def test_ohne_werte_zum_gewaehlten_weg():
    """Der Weg steht da, die Zahl dazu fehlt."""
    _, details = _ohne_trennung(anlage(kwh=None))
    assert details['trennungsgrund'] == heizung.OHNE_WERTE

    _, details = _ohne_trennung(anlage(weg=heizung.WW_FORMEL, kwh=None))
    assert details['trennungsgrund'] == heizung.OHNE_WERTE


def test_ohne_gesamtverbrauch_kein_bruch():
    """Ohne Nenner kein Anteil -- und ohne Anteil keine Trennung."""
    _, details = _ohne_trennung(anlage(gesamt=None))
    assert details['trennungsgrund'] == heizung.OHNE_GESAMTMENGE


def test_widersprechende_angaben_brechen_nicht_ab():
    """Mehr Warmwasser als Gesamtverbrauch: der Fehler wird zum Grund (D-48)."""
    ergebnis, details = _ohne_trennung(anlage(kwh='70000', gesamt='60000'))

    assert 'größer als der Gesamtverbrauch' in details['trennungsgrund']
    assert ergebnis['total_amount'] == Decimal('5700.00')


# --- Die reinen Anlagen ----------------------------------------------------


def test_die_reine_warmwasseranlage_rechnet_nach_paragraf_acht():
    """Versorgt sie nur das Wasser, geht alles nach § 8 -- Nummer 5.

    Verbrauchsteil 7.000, davon 30 von 100 m3 = 2.100; Grundteil 3.000,
    davon 50 von 100 qm = 1.500. Zusammen 3.600.
    """
    ergebnis = rechne(haus(anlagen=(anlage(
        name='Boiler', versorgt=heizung.WARMWASSER, weg=None, kwh=None,
        gesamt=None),)))
    eine = zeilen(ergebnis)

    assert set(eine) == {heizung.WARMWASSER}
    zeile = eine[heizung.WARMWASSER]
    assert zeile['category'] == 'Warmwasserkosten (Boiler)'
    assert zeile['heizung_details']['betrkv_nr'] == 5
    assert zeile['heizung_details']['trennungsgrund'] is None
    assert zeile['tenant_cost'] == Decimal('3600.00')


def test_die_reine_heizung_bleibt_wie_sie_war():
    """Ohne Warmwasser aendert NK-050 nichts: 4.200 + 1.500 = 5.700."""
    ergebnis = rechne(haus(anlagen=(anlage(
        versorgt=heizung.HEIZUNG, weg=None, kwh=None, gesamt=None),)))
    eine = zeilen(ergebnis)

    assert set(eine) == {heizung.HEIZUNG}
    assert eine[heizung.HEIZUNG]['heizung_details']['betrkv_nr'] == 4
    assert eine[heizung.HEIZUNG]['tenant_cost'] == Decimal('5700.00')


# --- Die Erfassung je Zweck ------------------------------------------------


def test_ein_fehlender_warmwasserzaehler_trifft_nur_das_warmwasser():
    """Die Waerme bleibt verbrauchsabhaengig, das Wasser geht nach Flaeche.

    Warmwasser ohne Erfassung: 2.500, davon 50 von 100 qm = 1.250.
    """
    ergebnis = rechne(haus(zaehler=(
        waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0),
        wasserzaehler(3, 1, 30.0),
    )))
    zwei = zeilen(ergebnis)

    assert zwei[heizung.HEIZUNG]['tenant_cost'] == Decimal('4275.00')
    assert zwei[heizung.HEIZUNG]['heizung_details']['erfasst'] is True
    warm = zwei[heizung.WARMWASSER]
    assert warm['tenant_cost'] == Decimal('1250.00')
    assert 'Warmwasserzähler' in warm['heizung_details']['fehlgrund']
    assert any('Warmwasserzähler' in w and '§ 12 Abs. 1' in w
               for w in ergebnis['warnings'])


def test_ein_fehlender_waermezaehler_trifft_nur_die_waerme():
    """Umgekehrt dasselbe: 7.500 ganz nach Flaeche = 3.750."""
    ergebnis = rechne(haus(zaehler=(
        waermezaehler(1, 1, 1200.0),
        wasserzaehler(3, 1, 30.0), wasserzaehler(4, 2, 70.0),
    )))
    zwei = zeilen(ergebnis)

    assert zwei[heizung.HEIZUNG]['tenant_cost'] == Decimal('3750.00')
    assert zwei[heizung.WARMWASSER]['tenant_cost'] == Decimal('900.00')
    assert 'Wärmezähler' in zwei[heizung.HEIZUNG]['heizung_details']['fehlgrund']


def test_der_zaehler_gehoert_zu_seinem_zweck():
    """Kubikmeter zaehlt Warmwasser, Kilowattstunden Waerme.

    Die Zaehler dieser Datei tragen die Katalognummer (Nr. 4 und Nr. 5,
    NK-121) -- dieselbe Entscheidung faellt der Weg ohne Nummer ueber den
    Namen: der Probe ohne Seed bleibt der Rueckfallweg.
    """
    assert ist_warmwasserzaehler(wasserzaehler(3, 1, 30.0)) is True
    assert ist_warmwasserzaehler(waermezaehler(1, 1, 1200.0)) is False
    assert ist_warmwasserzaehler(wasserzaehler(3, 1, 30.0,
                                               kategorie_betrkv_nr=None)) \
        is True
    assert ist_warmwasserzaehler(waermezaehler(1, 1, 1200.0,
                                               kategorie_betrkv_nr=None)) \
        is False


def test_bei_zwei_anlagen_ordnet_auch_der_warmwasserzaehler_zu():
    """Wer einen Zaehler der Anlage hat, haengt an ihr -- welchen, ist egal."""
    vorgang = haus(
        zaehler=(wasserzaehler(3, 1, 30.0), waermezaehler(2, 2, 800.0, 2)),
        anlagen=(anlage(), anlage(id=2, name='Hinterhaus')))

    vorne = anlagen_wohnungen(vorgang, vorgang.heizungsanlagen[0], True)
    hinten = anlagen_wohnungen(vorgang, vorgang.heizungsanlagen[1], True)
    assert [w.id for w in vorne] == [1]
    assert [w.id for w in hinten] == [2]


# --- Die beiden Bausteine fuer sich ---------------------------------------


def test_die_waermemenge_kennt_ihre_drei_wege():
    assert anlagen_warmwassermenge(anlage(), 100) == (Decimal('15000'), None)
    assert anlagen_warmwassermenge(
        anlage(weg=heizung.WW_ERSATZ, kwh=None), 250) == (Decimal('8000'), None)
    assert anlagen_warmwassermenge(
        anlage(weg=heizung.WW_ERSATZ, kwh=None), 0) == (None, heizung.OHNE_WERTE)


def test_der_anteil_ist_ein_bruch_zwischen_null_und_eins():
    assert anlagen_warmwasseranteil(anlage(), 100) == (Decimal('0.25'), None)
    assert anlagen_warmwasseranteil(
        anlage(versorgt=heizung.WARMWASSER), 100) == (Decimal('1'), None)
    assert anlagen_warmwasseranteil(
        anlage(versorgt=heizung.HEIZUNG), 100) == (Decimal('0'), None)
