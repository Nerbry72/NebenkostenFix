"""NK-037: der Rechenkern rechnet ohne Datenbank.

Jeder Fall hier ist ein Datensatz, kein Objektgraph. Es gibt keine Flask-App,
keine Sitzung, kein Schema und kein ``db.session.commit()`` -- das ist der
Punkt der Karte. Was vorher fuenfzehn Zeilen Aufbau kostete, kostet jetzt
einen Konstruktoraufruf, und darum koennen NK-038 und NK-039 darauf Stichproben
ueber hunderte Faelle setzen.

Die Zahlen selbst sind in ``tests/test_billing_engine_characterization.py``
festgenagelt; der Weg dorthin fuehrt ueber die Datenbank und prueft damit auch
den Lader. Hier stehen die Faelle, die dort schwer zu bauen waren.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix.abrechnungsart import ARTEN
from nebenkostenfix.rechenkern import (
    BillingDataError,
    Beleg,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    Zahlung,
    beleg_angabe,
    einheit_fuer,
    flaechen_pruefung,
    hauptzaehler,
    leerer_verbrauch,
    pruefe,
    qm_relevante_rechnungen,
    rechne,
    rechnungen_im_umfang,
    ueberschneidungstage,
    unterzaehler,
    verbrauch,
    verbrauch_detail,
    wohnungszaehler,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)


# --- Bausteine -------------------------------------------------------------


def kategorie(id=1, name='Hausmeister', braucht_zaehler=False):
    return Kategorie(id=id, name=name, braucht_zaehler=braucht_zaehler)


def rechnung(betrag='1200.00', kat=None, beginn=JAHR_BEGINN, ende=JAHR_ENDE, id=1, **kw):
    return Rechnung(
        id=id,
        kategorie=kat or kategorie(),
        betrag=Decimal(betrag),
        beginn=beginn,
        ende=ende,
        **kw,
    )


def vorgang(rechnungen=(), wohnungen=None, mieter=None, **kw):
    """Ein Vorgang mit einem Mieter in einer 50-qm-Wohnung von 100 qm."""
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    andere = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = mieter or Mieter(id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None, wohnung_id=1)
    grund = dict(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=tuple(wohnungen if wohnungen is not None else (meine, andere)),
        mieter_der_immobilie=(ich,),
        profile={},
        rechnungen=tuple(rechnungen),
    )
    grund.update(kw)
    return Vorgang(**grund)


def zaehler(id=1, kategorie_id=2, haupt=False, wohnung_id=None, staende=(), name='Wasser'):
    return Zaehler(
        id=id,
        nummer=f'Z-{id}',
        kategorie_id=kategorie_id,
        kategorie_name=name,
        ist_hauptzaehler=haupt,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=tuple(staende),
    )


# --- Der Kern kommt ohne Datenbank aus -------------------------------------


def test_kern_importiert_kein_orm():
    """Der Wortlaut der Karte: keine Datenbank im Rechenkern.

    Geprueft wird der Syntaxbaum, nicht der Text -- der Modulkopf zitiert die
    alten Queries absichtlich, und eine Textsuche wuerde daran haengenbleiben.

    ``geld`` bringt ``sqlalchemy.Numeric`` mit, eine Typangabe fuer das Schema.
    Das ist erlaubt; verboten ist, was Daten holt.

    ``zeitraum`` (NK-041) haengt an nichts als ``datetime`` und traegt die
    Tageskonvention aus R-NUM-03. Es steht auf derselben Stufe wie ``geld``:
    ein Baustein des Kerns, keine Aussenwelt. ``haushalt`` (NK-046) haengt
    seinerseits nur an ``zeitraum`` -- eine eigene Probe in
    ``tests/test_haushalt.py`` haelt das fest. ``leerstand`` (NK-047) ebenso,
    festgehalten in ``tests/test_leerstand.py``. ``heizung`` (NK-048/NK-049)
    kommt mit der Verteilung nach § 7 HeizkostenV herein und haengt an nichts
    als ``geld`` -- ``tests/test_heizung.py`` haelt auch das fest. ``co2``
    (NK-053) kommt mit der Aufteilung nach dem CO2KostAufG herein und haengt
    ebenso an nichts als ``geld`` -- ``tests/test_co2_aufteilung.py`` haelt
    auch das fest. ``betrkv`` (NK-117) kommt herein, weil ``ist_abwasser`` den
    Katalog fragt, ob ein Name das Niederschlagswasser meint; es haengt an
    nichts als der Standardbibliothek.
    """
    import ast
    from nebenkostenfix import rechenkern
    from tests.importwaechter import importierte_module

    baum = ast.parse(open(rechenkern.__file__, encoding='utf-8').read())

    importiert = importierte_module(baum)

    assert importiert <= {
        '__future__', 'os', 'dataclasses', 'datetime', 'decimal', 'typing',
        # Die eigenen Bausteine haengen selbst an nichts als der
        # Standardbibliothek -- sie duerfen mit herein, ein ORM nicht.
        'abrechnungsart', 'betrkv', 'co2', 'geld', 'haushalt', 'heizung', 'leerstand',
        'nutzung', 'zeitraum',
    }, (
        f'Der Rechenkern zieht fremde Module herein: {importiert}'
    )

    # Kein ``irgendwas.query`` und kein ``session`` im Quelltext selbst.
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Attribute):
            assert knoten.attr not in ('query', 'session'), 'Der Rechenkern fragt die Datenbank'


def test_rechnet_ohne_app_kontext():
    """Kein current_app, kein app_context -- und doch ein Ergebnis."""
    v = vorgang([rechnung('1200.00')])
    ergebnis = rechne(v)

    assert ergebnis['total_amount'] == Decimal('600.00')  # 50 von 100 qm
    assert ergebnis['tenant_name'] == 'Anna Mieterin'
    assert ergebnis['line_items'][0]['description'] == 'Umlage nach qm (50.0 von 100.0 qm)'


def test_vorgang_bleibt_unberuehrt():
    """Zweimal rechnen gibt zweimal dasselbe (Vorarbeit fuer NK-039)."""
    v = vorgang([rechnung('1000.00'), rechnung('333.33', id=2)])
    assert rechne(v) == rechne(v)


# --- Tage ------------------------------------------------------------------


@pytest.mark.parametrize('a1,a2,b1,b2,erwartet', [
    (date(2024, 1, 1), date(2024, 12, 31), date(2024, 1, 1), date(2024, 12, 31), 366),
    (date(2024, 1, 1), date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), 0),
    (date(2024, 1, 1), date(2024, 1, 31), date(2024, 1, 31), date(2024, 2, 5), 1),
    (date(2024, 3, 1), date(2024, 3, 10), date(2024, 1, 1), date(2024, 12, 31), 10),
])
def test_ueberschneidungstage_zaehlt_beide_raender(a1, a2, b1, b2, erwartet):
    """Die Fassade fuer Zeitraeume, die der Vermieter einschliesslich eingibt.

    Sie bleibt nach NK-041 bei dieser Zaehlweise, weil sie fuer sie richtig
    ist: "01.01. bis 31.12." sind 366 Tage. Nur rechnet sie das nicht mehr
    selbst, sondern verschiebt die Raender und laesst ``zeitraum`` zaehlen.
    Fuer Mietverhaeltnisse taugt sie nicht -- dafuer gibt es die Tests unten.
    """
    assert ueberschneidungstage(a1, a2, b1, b2) == erwartet


# --- Die Tageskonvention im Kern (NK-041, R-NUM-03) ------------------------


def test_ende_grenze_unterscheidet_auszug_vom_zeitraumende():
    """Dasselbe Feld, zwei Bedeutungen -- ``ende_grenze`` trennt sie.

    Der Lader stutzt ``ende`` auf das Auszugsdatum. Danach sieht ein
    Auszugsdatum aus wie ein Zeitraumende, und nur der Mieter weiss noch,
    welches von beidem dasteht.
    """
    ohne = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1), auszug=None, wohnung_id=1)
    assert vorgang(mieter=ohne).ende_grenze == date(2025, 1, 1)

    # Gestutzt: ``ende`` ist das Auszugsdatum und damit schon die Grenze.
    raus = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1), auszug=date(2024, 6, 30), wohnung_id=1)
    assert vorgang(mieter=raus, ende=date(2024, 6, 30)).ende_grenze == date(2024, 6, 30)

    # Auszug erst nach dem Zeitraum: nicht gestutzt, also ein Zeitraumende.
    spaet = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1), auszug=date(2025, 3, 1), wohnung_id=1)
    assert vorgang(mieter=spaet).ende_grenze == date(2025, 1, 1)


def test_mieterwechsel_berechnet_den_wechseltag_nur_einmal():
    """Der tragende Grund aus R-NUM-03, als Abrechnung durchgerechnet.

    A zieht am 30.06. aus, B zieht am selben Tag ein, beide in dieselbe
    Wohnung. Was auf die Wohnung entfaellt, muss sich genau auf die beiden
    verteilen -- 600 EUR von 1200, nicht 601,64.

    Vor NK-041 kam hier 601,64 heraus, und kein Test hat es bemerkt: der
    Wechselfall mit gesetztem Auszugsdatum fehlte im Bestand ganz.
    """
    wechsel = date(2024, 6, 30)
    a = Mieter(id=1, name='A', einzug=date(2020, 1, 1), auszug=wechsel, wohnung_id=1)
    b = Mieter(id=2, name='B', einzug=wechsel, auszug=None, wohnung_id=1)
    beide = (a, b)

    # So stutzt der Lader: A bis zum Auszug, B ab dem Einzug.
    va = vorgang([rechnung('1200.00')], mieter=a, profile={1: 'qm'},
                 mieter_der_immobilie=beide, ende=wechsel)
    vb = vorgang([rechnung('1200.00')], mieter=b, profile={1: 'qm'},
                 mieter_der_immobilie=beide, beginn=wechsel)

    zeile_a = rechne(va)['line_items'][0]
    zeile_b = rechne(vb)['line_items'][0]

    assert zeile_a['overlap_days'] == 181
    assert zeile_b['overlap_days'] == 185
    assert zeile_a['overlap_days'] + zeile_b['overlap_days'] == 366

    # 50 von 100 qm: die Haelfte der Rechnung gehoert der Wohnung.
    assert zeile_a['tenant_cost'] + zeile_b['tenant_cost'] == Decimal('600.00')


def test_ganzjaehriger_mieter_traegt_die_ganze_rechnung():
    """Die Gegenprobe: ohne Auszug darf sich nichts verschoben haben."""
    zeile = rechne(vorgang([rechnung('1200.00', wohnung_id=1)]))['line_items'][0]
    assert zeile['invoice_days'] == 366
    assert zeile['overlap_days'] == 366
    assert zeile['tenant_cost'] == Decimal('1200.00')


def test_am_auszugstag_zaehlt_der_mieter_nicht_mehr_mit():
    """Der Wechseltag gehoert nur einem -- sonst wird er zweimal berechnet.

    B zieht am 30.06. ein, A ist an dem Tag schon draussen. Ueber das
    Schaltjahr 2024 hat A 181 Personentage, B 185; zusammen 366, nicht 367.
    Bei einer Rechnung von 366,00 EUR heisst das 185,00 EUR fuer B.

    Die Welt hat seit NK-098 nur diese eine Wohnung: eine zweite, leer
    stehende wuerde mit ihren Personentagen in den Nenner kommen und genau
    die Eigenschaft verwischen, die dieser Fall prueft (F-34).
    """
    kat = kategorie(id=4, name='Muellabfuhr')
    wechsel = date(2024, 6, 30)
    a = Mieter(id=1, name='A', einzug=date(2020, 1, 1), auszug=wechsel, wohnung_id=1)
    b = Mieter(id=2, name='B', einzug=wechsel, auszug=None, wohnung_id=1)

    v = vorgang([rechnung('366.00', kat=kat)], mieter=b, profile={4: 'personen'},
                mieter_der_immobilie=(a, b), beginn=wechsel,
                wohnungen=[Wohnung(id=1, name='EG links', qm=50.0)])
    zeile = rechne(v)['line_items'][0]
    assert zeile['tenant_cost'] == Decimal('185.00')
    assert '185 von 366 Personentagen' in zeile['description']


# --- Flaeche ---------------------------------------------------------------


def test_flaeche_ohne_aktive_wohnung_blockiert():
    v = vorgang(wohnungen=[Wohnung(id=1, name='EG links', qm=50.0, ist_aktiv=False)])
    gesamt, befunde = flaechen_pruefung(v)
    assert gesamt == 0
    assert befunde[0][0] == 'blocker'
    assert 'keine aktive Wohnung' in befunde[0][1]


def test_flaeche_null_blockiert():
    v = vorgang(wohnungen=[Wohnung(id=1, name='EG links', qm=0)])
    _, befunde = flaechen_pruefung(v)
    assert befunde[0][0] == 'blocker'
    assert 'keiner aktiven Wohnung' in befunde[0][1]


def test_eigene_wohnung_ohne_flaeche_blockiert():
    ohne = Wohnung(id=1, name='EG links', qm=None)
    andere = Wohnung(id=2, name='EG rechts', qm=80.0)
    v = replace(vorgang(wohnungen=[ohne, andere]), wohnung=ohne)
    _, befunde = flaechen_pruefung(v)
    assert befunde[0][0] == 'blocker'
    assert "Wohnung 'EG links'" in befunde[0][1]


def test_fremde_wohnung_ohne_flaeche_warnt_nur():
    v = vorgang(wohnungen=[Wohnung(id=1, name='EG links', qm=50.0),
                           Wohnung(id=2, name='EG rechts', qm=None)])
    gesamt, befunde = flaechen_pruefung(v)
    assert gesamt == 50.0
    assert befunde[0][0] == 'warning'
    assert 'EG rechts' in befunde[0][1]


def test_qm_position_ohne_flaeche_wird_abgelehnt():
    """Der Blocker faellt erst, wenn wirklich nach qm umgelegt wird."""
    v = vorgang([rechnung('100.00')], wohnungen=[Wohnung(id=1, name='EG links', qm=0)])
    with pytest.raises(BillingDataError) as fehler:
        rechne(v)
    assert 'Quadratmeter' in str(fehler.value)


def test_ohne_qm_position_stoert_die_fehlende_flaeche_nicht():
    """Eine reine Personenumlage braucht die Gesamtflaeche gar nicht."""
    kat = kategorie(id=7, name='Muellabfuhr')
    v = vorgang(
        [rechnung('120.00', kat=kat)],
        wohnungen=[Wohnung(id=1, name='EG links', qm=0)],
        profile={7: 'personen'},
    )
    assert rechne(v)['total_amount'] == Decimal('120.00')


def test_warnung_wandert_ins_ergebnis():
    v = vorgang([rechnung('100.00')],
                wohnungen=[Wohnung(id=1, name='EG links', qm=50.0),
                           Wohnung(id=2, name='EG rechts', qm=None)])
    assert 'EG rechts' in rechne(v)['warnings'][0]


# --- Umlagearten -----------------------------------------------------------


def test_ignoriert_kostet_nichts_und_steht_trotzdem_da():
    kat = kategorie(id=3, name='Gartenpflege')
    v = vorgang([rechnung('500.00', kat=kat)], profile={3: 'ignoriert'})
    ergebnis = rechne(v)
    assert ergebnis['total_amount'] == Decimal('0.00')
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('0.00')
    assert 'Ignoriert' in ergebnis['line_items'][0]['description']


def test_personen_verteilt_nach_personentagen():
    """Zwei gleich grosse Haushalte, das ganze Jahr: die Haelfte (R-NUM-04).

    Ohne gepflegte Haushaltsgroesse ist jeder Haushalt ein Kopf -- das ist
    ``haushalt.VORGABE`` und genau die Zahl, die vor NK-046 gerechnet wurde.
    Die Beschriftung nennt jetzt die Personentage, mit denen geteilt wurde.
    """
    kat = kategorie(id=4, name='Muellabfuhr')
    zweiter = Mieter(id=2, name='Bodo', einzug=date(2020, 1, 1), auszug=None, wohnung_id=2)
    ich = Mieter(id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None, wohnung_id=1)
    v = vorgang([rechnung('300.00', kat=kat)], mieter=ich, profile={4: 'personen'},
                mieter_der_immobilie=(ich, zweiter))
    ergebnis = rechne(v)
    assert ergebnis['total_amount'] == Decimal('150.00')
    assert '366 von 732 Personentagen' in ergebnis['line_items'][0]['description']


def test_personen_ohne_aktiven_mieter_ergibt_keine_zeile():
    """Niemand im Zeitraum: der Betrag wird nicht verteilt, die Zeile faellt weg.

    Annas Mietverhaeltnis endet mit dem Vortag des Abrechnungszeitraums --
    sie hat null Personentage darin, also verteilt sich fuer sie nichts und
    die Zeile bleibt weg. Das gilt auch seit NK-098: Zwar zaehlen die
    verwaisten Wohnungen jetzt mit ihren Personentagen in den Nenner, aber
    ohne eigene Personentage entsteht keine Zeile.
    """
    kat = kategorie(id=4, name='Muellabfuhr')
    ich = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1),
                 auszug=JAHR_BEGINN, wohnung_id=1)
    v = vorgang([rechnung('300.00', kat=kat)], mieter=ich, profile={4: 'personen'},
                mieter_der_immobilie=(ich,))
    ergebnis = rechne(v)
    assert ergebnis['line_items'] == []
    assert ergebnis['total_amount'] == Decimal('0.00')


def test_rechnung_fuer_fremde_wohnung_faellt_raus():
    v = vorgang([rechnung('900.00', wohnung_id=2)])
    assert rechne(v)['line_items'] == []


def test_rechnung_fuer_die_eigene_wohnung_geht_ganz_an_sie():
    v = vorgang([rechnung('900.00', wohnung_id=1)])
    zeile = rechne(v)['line_items'][0]
    assert zeile['tenant_cost'] == Decimal('900.00')
    assert zeile['billing_type'] == 'direkt'


def test_rechnung_ausserhalb_des_zeitraums_wird_uebersprungen():
    v = vorgang([rechnung('900.00', beginn=date(2023, 1, 1), ende=date(2023, 12, 31))])
    assert rechne(v)['line_items'] == []


def test_zeitanteil_bei_teilweiser_ueberschneidung():
    """Ein halbes Jahr Rechnung, ganzes Jahr Mietzeit: nur die Rechnungstage zaehlen."""
    v = vorgang([rechnung('366.00', beginn=date(2024, 1, 1), ende=date(2024, 1, 31))])
    zeile = rechne(v)['line_items'][0]
    assert zeile['overlap_days'] == 31
    assert zeile['invoice_days'] == 31
    assert zeile['tenant_cost'] == Decimal('183.00')  # die Haelfte von 366


def test_kategorie_ohne_zaehler_bei_direkt_meldet_das():
    kat = kategorie(id=5, name='Kabelanschluss', braucht_zaehler=False)
    v = vorgang([rechnung('100.00', kat=kat)], profile={5: 'direkt'})
    zeile = rechne(v)['line_items'][0]
    assert zeile['tenant_cost'] == Decimal('0.00')
    assert 'keinen Zähler' in zeile['description']
    assert zeile['meter_details'] is None


# --- Vorauszahlungen -------------------------------------------------------


def test_guthaben_und_nachzahlung():
    v = vorgang([rechnung('1200.00')], zahlungen=(
        Zahlung(datum=date(2024, 6, 1), betrag=Decimal('300.00')),
        Zahlung(datum=date(2024, 7, 1), betrag=Decimal('400.00')),
    ))
    ergebnis = rechne(v)
    assert ergebnis['prepaid_amount'] == Decimal('700.00')
    assert ergebnis['balance'] == Decimal('-100.00')  # 600 Kosten, 700 gezahlt
    assert ergebnis['prepayments'][0] == {'date': '2024-06-01', 'amount': Decimal('300.00')}


# --- Umfang ----------------------------------------------------------------


def test_kategorienfilter_beschraenkt_das_rechnen():
    a = rechnung('100.00', kat=kategorie(id=1, name='Hausmeister'), id=1)
    b = rechnung('200.00', kat=kategorie(id=2, name='Gartenpflege'), id=2)
    v = vorgang([a, b], kategorien_filter=(2,))
    assert [r.id for r in rechnungen_im_umfang(v)] == [2]
    assert rechne(v)['total_amount'] == Decimal('100.00')  # die Haelfte von 200


def test_ohne_filter_zaehlen_alle_rechnungen():
    a = rechnung('100.00', id=1)
    v = vorgang([a])
    assert rechnungen_im_umfang(v) == [a]


def test_qm_relevante_rechnungen_laesst_wohnungsrechnungen_aus():
    eigene = rechnung('100.00', id=1)
    direkt = rechnung('100.00', id=2, wohnung_id=1)
    andere = rechnung('100.00', id=3, kat=kategorie(id=9, name='Strom'))
    treffer = qm_relevante_rechnungen([eigene, direkt, andere], {9: 'direkt'})
    assert [r.id for r in treffer] == [1]


# --- Belege ----------------------------------------------------------------


@pytest.mark.parametrize('beleg,erwartet', [
    (Beleg(), ('', '')),
    (Beleg(dateiname='rechnung.pdf', pfad='/belege/rechnung.pdf'),
     ('rechnung.pdf', '/belege/rechnung.pdf')),
    (Beleg(dateiname='sammel.pdf', pfad='/belege/sammel.pdf', seiten='3-4'),
     ('sammel.pdf, Seiten 3-4', '/belege/sammel.pdf')),
    (Beleg(pfad_alt='/alt/scan.pdf'), ('scan.pdf', '/alt/scan.pdf')),
])
def test_beleg_angabe(beleg, erwartet):
    assert beleg_angabe(beleg) == erwartet


@pytest.mark.parametrize('name,einheit', [
    ('Strom Allgemein', 'kWh'),
    ('Frischwasser', 'm³'),
    ('Abwasser', 'm³'),
    ('Gas', 'm³'),
    ('Hausmeister', 'Einheiten'),
    ('', 'Einheiten'),
])
def test_einheit_fuer(name, einheit):
    assert einheit_fuer(name) == einheit


# --- Zaehler finden --------------------------------------------------------


def test_zaehlersuche_nimmt_die_kleinste_id():
    """Vorher entschied die Reihenfolge der Datenbank, jetzt die id."""
    spaet = zaehler(id=9, wohnung_id=1)
    frueh = zaehler(id=2, wohnung_id=1)
    v = vorgang(zaehler=(spaet, frueh))
    assert wohnungszaehler(v, 2).id == 2


def test_hauptzaehler_und_unterzaehler_werden_getrennt():
    haupt = zaehler(id=1, haupt=True)
    unter_a = zaehler(id=2, wohnung_id=1)
    unter_b = zaehler(id=3, wohnung_id=2)
    v = vorgang(zaehler=(haupt, unter_a, unter_b))
    assert hauptzaehler(v, 2).id == 1
    assert [z.id for z in unterzaehler(v, 2)] == [2, 3]
    assert hauptzaehler(v, 999) is None
    assert wohnungszaehler(v, 999) is None


# --- Verbrauch -------------------------------------------------------------


def test_verbrauch_ohne_staende_ist_kein_datenbestand():
    z = zaehler(staende=())
    detail = verbrauch_detail(z, JAHR_BEGINN, JAHR_ENDE)
    assert detail['status'] == 'no_data'
    assert detail['consumption'] == 0.0
    assert detail['meter_number'] == 'Z-1'
    assert detail['unit'] == 'm³'


def test_verbrauch_mit_einem_stand_bleibt_ohne_ergebnis():
    z = zaehler(staende=[Stand(datum=JAHR_BEGINN, wert=100.0)])
    assert verbrauch_detail(z, JAHR_BEGINN, JAHR_ENDE)['status'] == 'no_data'


def test_verbrauch_ueber_das_ganze_jahr():
    z = zaehler(staende=[
        Stand(datum=date(2024, 1, 1), wert=1000.0),
        Stand(datum=date(2025, 1, 1), wert=1366.0),
    ])
    detail = verbrauch_detail(z, JAHR_BEGINN, JAHR_ENDE)
    assert detail['consumption'] == pytest.approx(366.0)
    assert detail['target_days'] == 366
    assert detail['status'] == 'excellent'
    assert detail['is_interpolated'] is False
    assert detail['reading_span_days'] == 366


def test_verbrauch_rechnet_den_rand_mit_dem_mittel_hoch():
    """Das Mietverhaeltnis beginnt vor der ersten Ablesung."""
    z = zaehler(staende=[
        Stand(datum=date(2024, 3, 1), wert=0.0),
        Stand(datum=date(2024, 4, 1), wert=31.0),   # 1 je Tag
    ])
    detail = verbrauch_detail(z, date(2024, 3, 1), date(2024, 4, 30))
    # 31 Tage gemessen, 30 hochgerechnet, beides zu 1,0 je Tag
    assert detail['consumption'] == pytest.approx(61.0)
    assert detail['status'] == 'warning'   # mehr als 10 Tage hochgerechnet
    assert detail['is_interpolated'] is True


def test_verbrauch_addiert_den_niedertarif():
    z = zaehler(name='Strom', staende=[
        Stand(datum=date(2024, 1, 1), wert=100.0, wert_nt=50.0),
        Stand(datum=date(2025, 1, 1), wert=200.0, wert_nt=150.0),
    ])
    detail = verbrauch_detail(z, JAHR_BEGINN, JAHR_ENDE)
    assert detail['consumption'] == pytest.approx(200.0)   # 100 HT + 100 NT
    assert detail['unit'] == 'kWh'
    assert detail['r_start']['value_nt'] == 50.0
    assert detail['r_start']['total'] == 150.0


def test_verbrauch_uebergeht_zwei_staende_am_selben_tag():
    z = zaehler(staende=[
        Stand(datum=date(2024, 1, 1), wert=1000.0),
        Stand(datum=date(2024, 1, 1), wert=1000.0),
        Stand(datum=date(2025, 1, 1), wert=1366.0),
    ])
    detail = verbrauch_detail(z, JAHR_BEGINN, JAHR_ENDE)
    assert detail['consumption'] == pytest.approx(366.0)
    # zwei Ablesungen am selben Tag fallen nicht zu einer zusammen
    assert len(detail['basis_readings']) == 2


def test_verbrauch_bei_umgedrehtem_zeitraum_ist_leer():
    z = zaehler(staende=[
        Stand(datum=date(2024, 1, 1), wert=1000.0),
        Stand(datum=date(2025, 1, 1), wert=1366.0),
    ])
    assert verbrauch_detail(z, JAHR_ENDE, JAHR_BEGINN)['status'] == 'no_data'


def test_verbrauch_gibt_nur_die_zahl():
    z = zaehler(staende=[
        Stand(datum=date(2024, 1, 1), wert=0.0),
        Stand(datum=date(2025, 1, 1), wert=366.0),
    ])
    assert verbrauch(z, JAHR_BEGINN, JAHR_ENDE) == pytest.approx(366.0)


@pytest.mark.parametrize('abstand,status', [(5, 'excellent'), (10, 'acceptable'), (20, 'warning')])
def test_ampel_folgt_dem_abstand_zum_zeitraumrand(abstand, status):
    from datetime import timedelta
    z = zaehler(staende=[
        Stand(datum=JAHR_BEGINN - timedelta(days=abstand), wert=0.0),
        Stand(datum=JAHR_ENDE + timedelta(days=abstand), wert=1000.0),
    ])
    assert verbrauch_detail(z, JAHR_BEGINN, JAHR_ENDE)['status'] == status


def test_leerer_verbrauch_traegt_keine_zaehlerkennung():
    """Die Engine liess 'meter_id' im Leerfall weg; das bleibt so."""
    assert 'meter_id' not in leerer_verbrauch()


# --- Vorpruefung -----------------------------------------------------------


def test_vorpruefung_ohne_zaehler_meldet_nichts():
    assert pruefe(vorgang())['overall'] == 'no_meters'


def test_vorpruefung_sieht_haupt_und_wohnungszaehler():
    kat = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    staende = [Stand(datum=JAHR_BEGINN, wert=0.0), Stand(datum=JAHR_ENDE, wert=100.0)]
    v = vorgang([rechnung('600.00', kat=kat)], profile={2: 'direkt'}, zaehler=(
        zaehler(id=1, haupt=True, staende=staende),
        zaehler(id=2, wohnung_id=1, staende=staende),
    ))
    ergebnis = pruefe(v)
    assert [c['meter_type'] for c in ergebnis['checks']] == ['Hauptzähler', 'Wohnungszähler']
    assert ergebnis['checks'][1]['apartment'] == 'EG links'
    assert ergebnis['overall'] == 'excellent'


def test_vorpruefung_meldet_jeden_zaehler_nur_einmal():
    kat = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    staende = [Stand(datum=JAHR_BEGINN, wert=0.0), Stand(datum=JAHR_ENDE, wert=100.0)]
    v = vorgang(
        [rechnung('300.00', kat=kat, id=1), rechnung('300.00', kat=kat, id=2)],
        profile={2: 'direkt'},
        zaehler=(zaehler(id=1, haupt=True, staende=staende),),
    )
    assert len(pruefe(v)['checks']) == 1


def test_vorpruefung_haengt_die_flaeche_an():
    v = vorgang([rechnung('100.00')], wohnungen=[Wohnung(id=1, name='EG links', qm=0)])
    ergebnis = pruefe(v)
    assert ergebnis['overall'] == 'warning'
    assert ergebnis['checks'][0]['category'] == 'Wohnflaeche'
    assert ergebnis['checks'][0]['blocking'] is True


def test_vorpruefung_uebergeht_fremde_wohnungsrechnungen():
    kat = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = vorgang([rechnung('300.00', kat=kat, wohnung_id=2)], profile={2: 'direkt'},
                zaehler=(zaehler(id=1, haupt=True),))
    assert pruefe(v)['checks'] == []


def test_vorpruefung_uebergeht_kategorien_ohne_zaehler():
    """Ohne Zähler an der Kostenart gibt es keine Prüfkachel (NK-105).

    Der Zaehler des Hauses gehoert einer anderen Kostenart — fuer
    Kabelanschluss haengt nichts an ihm, also wird er nicht geprüft. Vor
    NK-105 entschied das Pflichtkennzeichen, seit NK-105 die Existenz
    eines Zaehlers an der Kategorie.
    """
    kat = kategorie(id=2, name='Kabelanschluss', braucht_zaehler=False)
    fremd = kategorie(id=3, name='Wasserversorgung', braucht_zaehler=True)
    v = vorgang([rechnung('300.00', kat=kat)], profile={2: 'direkt'},
                zaehler=(zaehler(id=1, kategorie_id=fremd.id, haupt=True),))
    assert pruefe(v)['checks'] == []


def test_vorpruefung_uebergeht_qm_und_personen():
    kat = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = vorgang([rechnung('300.00', kat=kat)], profile={2: 'personen'},
                zaehler=(zaehler(id=1, haupt=True),))
    assert pruefe(v)['checks'] == []


def test_vorpruefung_nimmt_auch_abgewaehlte_kategorien():
    """Ein fehlender Zaehlerstand bleibt einer, auch wenn gerade nicht
    abgerechnet wird -- darum filtert pruefe() nicht nach Kategorien."""
    kat = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = vorgang([rechnung('300.00', kat=kat)], profile={2: 'direkt'},
                kategorien_filter=(99,),
                zaehler=(zaehler(id=1, haupt=True),))
    assert len(pruefe(v)['checks']) == 1


# --- Die Zweige, die ohne Datenbank kaum zu treffen waren -------------------
#
# Diese Gruppe kam nach dem ersten Abdeckungslauf dazu. Sie zielt auf die
# Stellen, die die Charakterisierungstests nicht erreichten: Abwasser am
# Frischwasserzaehler, ungleiche Personentage, ein Zeitraum neben allen
# Staenden. Jede davon verteilt Geld.


def _wasserwelt(staende_haupt, staende_meine, staende_andere=(), **kw):
    """Ein Vorgang mit Hauptzaehler und zwei Wohnungszaehlern fuer Wasser."""
    zaehlerliste = [
        zaehler(id=10, haupt=True, staende=staende_haupt),
        zaehler(id=11, wohnung_id=1, staende=staende_meine),
    ]
    if staende_andere:
        zaehlerliste.append(zaehler(id=12, wohnung_id=2, staende=staende_andere))
    return vorgang(zaehler=tuple(zaehlerliste), **kw)


def test_abwasser_rechnet_auf_dem_frischwasserzaehler():
    """Abwasser hat keinen eigenen Zaehler -- gemessen wird, was hineingeht.

    Die Kategorie 'Abwasser' (id 3) hat keine Zaehler. Traegt der Vorgang eine
    wasser_kategorie_id, rechnet der Zweig auf deren Zaehlern (id 2) weiter.
    Ohne diesen Umweg kaeme null heraus, und der Vermieter bliebe auf den
    Abwasserkosten sitzen.
    """
    abwasser = kategorie(id=3, name='Abwasser', braucht_zaehler=False)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 60.0)),
        rechnungen=(rechnung(betrag='1000.00', kat=abwasser),),
        profile={3: 'direkt'},
        wasser_kategorie_id=2,
    )

    posten = rechne(v)['line_items'][0]

    # 60 von 100 Einheiten eigen, der Rest ist Allgemein und geht bei einem
    # einzigen Mieter ebenfalls an ihn.
    assert posten['tenant_cost'] == Decimal('1000.00')
    assert 'Eigenverbrauch' in posten['description']
    assert posten['meter_details'] is not None


def test_abwasser_ohne_wasserkategorie_bleibt_auf_der_eigenen_id():
    """Fehlt die Frischwasserkategorie, sucht der Zweig auf der eigenen.

    Er findet dort nichts, und die Position steht mit 0,00 EUR im Bericht --
    sichtbar, statt stillschweigend zu fehlen.
    """
    abwasser = kategorie(id=3, name='Abwasser', braucht_zaehler=False)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 60.0)),
        rechnungen=(rechnung(betrag='1000.00', kat=abwasser),),
        profile={3: 'direkt'},
        wasser_kategorie_id=None,
    )

    posten = rechne(v)['line_items'][0]

    assert posten['tenant_cost'] == Decimal('0.00')
    assert 'kein Hauptzähler' in posten['description']


def _zwei_mieter_ungleich():
    """Zwei Mieter, einer nur ein halbes Jahr da -- ungleiche Personentage."""
    ich = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1), auszug=None, wohnung_id=1)
    kurz = Mieter(id=2, name='Bert', einzug=date(2024, 7, 1), auszug=None, wohnung_id=2)
    return ich, kurz


def test_allgemeinanteil_nach_personentagen_nicht_nach_koepfen():
    """Wer ein halbes Jahr da war, traegt ein halbes Jahr Allgemeinkosten.

    Die Beschreibung nennt seit NK-046 immer die Personentage -- auch dort,
    wo frueher die Kurzform '1 von n Pers.' stand (D-42). Dieser Fall prueft
    den Wortlaut und damit, dass die Verteilung nach Tagen laeuft.
    """
    ich, kurz = _zwei_mieter_ungleich()
    wasser = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 30.0)),
        staende_andere=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 30.0)),
        rechnungen=(rechnung(betrag='1000.00', kat=wasser),),
        profile={2: 'direkt'},
        mieter=ich,
        mieter_der_immobilie=(ich, kurz),
    )

    posten = rechne(v)['line_items'][0]

    assert 'Personentagen' in posten['description']
    # 366 von 366+184 Personentagen auf 40 Einheiten Allgemein zu 10 EUR
    assert posten['tenant_cost'] == Decimal('566.18')


def test_nur_allgemein_bei_ungleichen_personentagen():
    """Derselbe Wortlaut im Unterposten des Wegs 'nur_allgemein'."""
    ich, kurz = _zwei_mieter_ungleich()
    wasser = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 30.0)),
        staende_andere=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 30.0)),
        rechnungen=(rechnung(betrag='1000.00', kat=wasser),),
        profile={2: 'nur_allgemein'},
        mieter=ich,
        mieter_der_immobilie=(ich, kurz),
    )

    posten = rechne(v)['line_items'][0]

    assert 'Anteil am Allgemeinverbrauch' in posten['description']
    assert 'Personentagen' in posten['description']
    unterposten = posten['sub_items'][0]
    assert unterposten['type'] == 'allgemein'
    assert 'Personentagen' in unterposten['description']


def test_wohnungsrechnung_zeigt_den_eigenen_verbrauch_mit():
    """Eine Rechnung auf die Wohnung nennt den Zaehlerstand, wenn es einen gibt.

    Der Betrag haengt nicht daran -- 100 Prozent bleiben 100 Prozent -- aber
    der Mieter soll sehen, worauf sich die Rechnung bezieht.
    """
    wasser = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 60.0)),
        rechnungen=(rechnung(betrag='500.00', kat=wasser, wohnung_id=1),),
        profile={2: 'qm'},
    )

    posten = rechne(v)['line_items'][0]

    assert posten['tenant_cost'] == Decimal('500.00')
    assert posten['billing_type'] == 'direkt'
    assert posten['sub_items'][0]['description'].startswith('Eigenverbrauch (60.')
    assert posten['sub_items'][0]['description'].endswith(' m³)')


def test_verbrauch_wenn_der_zeitraum_neben_allen_staenden_liegt():
    """Kein Stand beruehrt den Zeitraum -- dann fuellt das Mittel auf.

    Der Rueckgabewert nennt trotzdem den ersten und letzten Stand als Herkunft,
    sonst staende im Bericht 'aus dem Nichts'.
    """
    z = zaehler(staende=(
        Stand(date(2024, 6, 1), 0.0),
        Stand(date(2024, 7, 1), 30.0),
    ))

    detail = verbrauch_detail(z, date(2024, 9, 1), date(2024, 9, 11))

    assert detail['r_start']['date'] == '2024-06-01'
    assert detail['r_end']['date'] == '2024-07-01'
    # Elf, nicht zehn: die Hochrechnung zaehlt den Zielzeitraum inklusiv
    # (1.9. bis 11.9. sind 11 Tage), die Tagesrate dagegen exklusiv
    # (1.6. bis 1.7. sind 30 Tage zu 1,0). Genau diese Uneinheitlichkeit
    # raeumt NK-041 auf; bis dahin steht sie hier als Ist.
    assert detail['consumption'] == pytest.approx(11.0)
    assert detail['is_interpolated'] is True


def test_pruefung_folgt_dem_abwasser_auf_den_wasserzaehler():
    """Auch die Vorpruefung kennt den Umweg ueber das Frischwasser.

    Sonst meldete sie 'kein Zaehler' fuer eine Kategorie, die sehr wohl einen
    hat -- nur unter anderem Namen.
    """
    abwasser = kategorie(id=3, name='Abwasser', braucht_zaehler=False)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 60.0)),
        rechnungen=(rechnung(betrag='1000.00', kat=abwasser),),
        profile={3: 'direkt'},
        wasser_kategorie_id=2,
    )

    ergebnis = pruefe(v)

    assert ergebnis['overall'] == 'excellent'
    assert [c['meter_type'] for c in ergebnis['checks']] == ['Hauptzähler', 'Wohnungszähler']
    assert all(c['category'] == 'Abwasser' for c in ergebnis['checks'])


def test_pruefung_uebergeht_die_rechnung_einer_fremden_wohnung():
    """Was einer anderen Wohnung gehoert, gehoert nicht in diese Pruefung."""
    wasser = kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
    v = _wasserwelt(
        staende_haupt=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 100.0)),
        staende_meine=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, 60.0)),
        rechnungen=(rechnung(betrag='500.00', kat=wasser, wohnung_id=2),),
        profile={2: 'direkt'},
    )

    assert pruefe(v) == {'overall': 'no_meters', 'checks': []}


# ---------------------------------------------------------------------------
# NK-096: eine Abrechnungsart, die es nicht gibt (F-25)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('art', [
    'verbrauch',   # der Fall aus F-25: klingt richtig, gibt es nicht
    'Qm',          # ein Grossbuchstabe genuegte
    'direkt ',     # ein Leerzeichen genuegte
    '',
    None,
])
def test_unbekannte_abrechnungsart_bricht_ab_statt_zu_verschwinden(art):
    """Gemessen am 21.09.2026: aus 600,00 EUR wurden lautlos 0,00 EUR.

    Der Posten fehlte im Blatt, die Summe war zu niedrig, gewarnt hat
    niemand -- und eine Abrechnung, der eine Kostenart fehlt, sieht
    vollstaendig aus. Jetzt sagt der Kern ab.
    """
    kat = kategorie(id=9, name='Wasser')
    v = vorgang([rechnung('1200.00', kat=kat)], profile={9: art})
    with pytest.raises(BillingDataError) as fehler:
        rechne(v)
    assert 'Wasser' in str(fehler.value)


def test_die_absage_nennt_die_erlaubten_arten():
    """Sonst raet der Vermieter -- und in F-25 hat genau das jemand getan."""
    kat = kategorie(id=9, name='Wasser')
    v = vorgang([rechnung('1200.00', kat=kat)], profile={9: 'verbrauch'})
    with pytest.raises(BillingDataError) as fehler:
        rechne(v)
    text = str(fehler.value)
    assert 'verbrauch' in text
    for erlaubt in ARTEN:
        assert erlaubt in text


def test_ohne_profil_bleibt_es_bei_der_flaeche():
    """Kein Eintrag heisst nicht "ungueltig", sondern "nach qm" (VORGABE)."""
    kat = kategorie(id=9, name='Wasser')
    v = vorgang([rechnung('1200.00', kat=kat)], profile={})
    ergebnis = rechne(v)
    assert ergebnis['total_amount'] == Decimal('600.00')


def test_vorpruefung_warnt_statt_abzusagen():
    """Die Ampel zeigt die Kostenart -- eine Absage naehme sie dem Vermieter weg.

    Dieselbe Arbeitsteilung wie beim Flaechenblocker aus NK-027: die
    Vorpruefung macht sichtbar, ``rechne()`` verweigert.
    """
    kat = kategorie(id=9, name='Wasser')
    v = vorgang([rechnung('1200.00', kat=kat)], profile={9: 'verbrauch'})
    ergebnis = pruefe(v)
    kacheln = [c for c in ergebnis['checks'] if c['meter_type'] == 'Abrechnungsart']
    assert len(kacheln) == 1
    assert kacheln[0]['blocking'] is True
    assert kacheln[0]['category'] == 'Wasser'
    assert 'verbrauch' in kacheln[0]['message']
    assert ergebnis['overall'] == 'warning'


def test_vorpruefung_meldet_jede_kostenart_nur_einmal():
    """Zwei Rechnungen, ein Profil -- eine Kachel, nicht zwei."""
    kat = kategorie(id=9, name='Wasser')
    v = vorgang(
        [rechnung('600.00', kat=kat, id=1), rechnung('600.00', kat=kat, id=2)],
        profile={9: 'verbrauch'},
    )
    kacheln = [
        c for c in pruefe(v)['checks'] if c['meter_type'] == 'Abrechnungsart'
    ]
    assert len(kacheln) == 1


# --- NK-105 (D-63): der Zählerweg gilt für jede Kostenart -------------------

STROM = dict(id=11, name='Beleuchtung (Allgemeinstrom)')


def test_strom_mit_wohnungszaehler_rechnet_nach_verbrauch():
    """Allgemeinstrom hat keinen Pflichtzähler — mit Zähler wird er gemessen.

    Vor NK-105 rechnete der Zählerweg nur, wo ``braucht_zaehler`` stand
    (Wasserversorgung) oder der Name Abwasser riecht. Ein Allgemeinstrom-
    zähler mit Profil ``direkt`` lief darum still auf 0,00 € und die Zeile
    behauptete, die Kategorie habe keinen Zähler. Der Zähler ist real;
    gerechnet wird nach Verbrauch: 200 kWh von 100,00 € Grundlage = 0,50 €/kWh.
    """
    kat = kategorie(**STROM, braucht_zaehler=False)
    z = zaehler(id=1, kategorie_id=11, wohnung_id=1, name=STROM['name'], staende=(
        Stand(datum=JAHR_BEGINN, wert=1000.0),
        # An der Zeitraumgrenze: der zweite Ablesetag schliesst das Fenster
        # (Halboffen, R-NUM-03), genau 200 kWh liegen zwischen den Staenden.
        Stand(datum=date(2025, 1, 1), wert=1200.0),
    ))
    v = vorgang([rechnung('100.00', kat=kat)],
                profile={11: 'direkt'}, zaehler=[z])
    zeile = rechne(v)['line_items'][0]
    assert zeile['tenant_cost'] == Decimal('100.00')
    assert 'Eigenverbrauch ohne Hauptzähler (200.0 kWh' in zeile['description']


def test_strom_ohne_zaehler_bleibt_beim_bisherigen_verhalten():
    """Ohne Zähler und ohne Pflicht entfällt die Position wie bisher.

    Kein Zähler im Haus, kein Pflichtkennzeichen — der Kern findet nichts
    zu messen. Das bisherige Verhalten (0,00 € mit Fehlerhinweis) bleibt;
    die Vorprüfung zeigt die Lage, der Weg wird nicht erfunden.
    """
    kat = kategorie(**STROM, braucht_zaehler=False)
    v = vorgang([rechnung('100.00', kat=kat)], profile={11: 'direkt'})
    zeile = rechne(v)['line_items'][0]
    assert zeile['tenant_cost'] == Decimal('0.00')
    assert 'hat keinen Zähler' in zeile['description']


def test_vorpruefung_zeigt_stromzaehler_auch_ohne_pflicht():
    """Die Prüfkachel hängt am Zähler, nicht am Pflichtkennzeichen.

    Ein Wohnungszähler für Allgemeinstrom wird geprüft wie jeder andere:
    Ablesungen decken den Zeitraum, die Kachel steht auf ok. Ohne Zähler
    und ohne Pflicht gibt es keine Kachel — nichts zu prüfen.
    """
    kat = kategorie(**STROM, braucht_zaehler=False)
    z = zaehler(id=1, kategorie_id=11, wohnung_id=1, name=STROM['name'], staende=(
        Stand(datum=JAHR_BEGINN, wert=1000.0),
        Stand(datum=date(2025, 1, 1), wert=1200.0),
    ))
    v_mit = vorgang([rechnung('100.00', kat=kat)],
                    profile={11: 'direkt'}, zaehler=[z])
    kacheln = [c for c in pruefe(v_mit)['checks'] if 'Allgemeinstrom' in c['category']]
    assert kacheln and all(k['status'] in ('ok', 'excellent') for k in kacheln)

    v_ohne = vorgang([rechnung('100.00', kat=kat)], profile={11: 'direkt'})
    assert not [c for c in pruefe(v_ohne)['checks'] if 'Allgemeinstrom' in c['category']]
