"""NK-097: der Allgemeinanteil wird im Abrechnungszeitraum gemessen.

Der Befund F-33 (erhoben bei NK-046): im Zählerzweig wurde der
Allgemeinverbrauch über den **vollen Rechnungszeitraum** genommen, während
der Eigenverbrauch schon auf den Abrechnungszeitraum geschnitten war. Eine
Abrechnung über ein Quartal berechnete denselben Allgemeinverbrauch viermal,
und ein Mieter, der zur Jahresmitte einzog, trug einen Allgemeinanteil für
eine Mietzeit, die er noch gar nicht hatte.

Seit NK-097 wird alles, was im Zählerzweig verteilt wird, im Schnitt aus
Rechnungs- und Abrechnungszeitraum gemessen: Hauptzähler, Unterzähler und
Personentage (Zähler wie Nenner). Der Preis je Einheit bleibt dagegen der der
Rechnung -- Rechnungsbetrag durch den Gesamtverbrauch des Hauptzählers über
den vollen Rechnungszeitraum. Nur so addieren sich vier Quartale wieder zum
vollen Betrag.

Die Fälle hier sind die beiden Proberechnungen aus F-33: ein Quartal statt
des ganzen Jahres, und ein Mieterwechsel zur Jahresmitte. Gerechnet wird in
2025 (365 Tage), wie im Befund.

Der Weg dorthin ist derselbe wie bei ``tests/test_rechenkern.py``: Datensätze,
keine Datenbank.
"""

from datetime import date
from decimal import Decimal

from nebenkostenfix.rechenkern import (
    Mieter,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    Kategorie,
    Rechnung,
    rechne,
)

RECHNUNG_BEGINN = date(2025, 1, 1)
RECHNUNG_ENDE = date(2025, 12, 31)
JAHRSGRENZE = date(2026, 1, 1)


# --- Bausteine -------------------------------------------------------------


def kategorie(id=2, name='Frischwasser', braucht_zaehler=True):
    return Kategorie(id=id, name=name, braucht_zaehler=braucht_zaehler)


def rechnung(betrag='1000.00', kat=None, id=1):
    """Eine Jahresrechnung: 1000 EUR, voller Rechnungszeitraum 2025."""
    return Rechnung(
        id=id,
        kategorie=kat or kategorie(),
        betrag=Decimal(betrag),
        beginn=RECHNUNG_BEGINN,
        ende=RECHNUNG_ENDE,
    )


def wohnung(id, name, qm=50.0):
    return Wohnung(id=id, name=name, qm=qm)


def mieter(id, name, wohnung_id, einzug, auszug=None):
    return Mieter(id=id, name=name, einzug=einzug, auszug=auszug, wohnung_id=wohnung_id)


def zaehler(id, haupt=False, wohnung_id=None, staende=()):
    return Zaehler(
        id=id,
        nummer=f'Z-{id}',
        kategorie_id=2,
        kategorie_name='Frischwasser',
        ist_hauptzaehler=haupt,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=tuple(staende),
    )


def wasserwelt(beginn, ende, meine, andere, profile=None):
    """Hauptzähler (0 -> 100 m³) und zwei Wohnungszaehler (0 -> 30 m³ je).

    Die Ablesungen stehen auf dem 1.1.2025 und dem 1.1.2026 -- sie klammern
    das ganze Jahr, und der Zwischenraum ist 2025 selbst. Kein Tag wird
    hochgerechnet, keine Zahl beruht auf einem Füllwert; was die Tests
    erwarten, lässt sich von Hand nachrechnen.
    """
    zliste = [
        zaehler(10, haupt=True, staende=(
            Stand(RECHNUNG_BEGINN, 0.0), Stand(JAHRSGRENZE, 100.0))),
        zaehler(11, wohnung_id=1, staende=(
            Stand(RECHNUNG_BEGINN, 0.0), Stand(JAHRSGRENZE, 30.0))),
        zaehler(12, wohnung_id=2, staende=(
            Stand(RECHNUNG_BEGINN, 0.0), Stand(JAHRSGRENZE, 30.0))),
    ]
    return Vorgang(
        mieter=meine,
        wohnung=wohnung(1, 'EG links'),
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=beginn,
        ende=ende,
        wohnungen=(wohnung(1, 'EG links'), wohnung(2, 'EG rechts')),
        mieter_der_immobilie=(meine, andere),
        profile=profile or {2: 'direkt'},
        rechnungen=(rechnung(),),
        zaehler=tuple(zliste),
    )


# --- Das Quartal aus F-33 ---------------------------------------------------


def test_quartal_berechnet_den_allgemeinanteil_nur_fuer_sein_fenster():
    """Ein Abrechnungszeitraum von 90 Tagen trägt 90 Tage Allgemeinverbrauch.

    F-33, Probelauf 1: zwei Wohnungen mit je einer Person, Jahresrechnung
    1000 EUR, Hauptzähler 100 m³, Unterzähler 30 m³ je Wohnung. Vor NK-097
    bekam der Quartalsmieter einen Allgemeinanteil aus dem vollen
    Rechnungszeitraum (etwa 273,97 EUR laut Befund); richtig sind rund
    123,29 EUR.

    Von Hand: der Preis bleibt 1000/100 = 10 EUR je m³. Im Quartal (90 Tage)
    sind das Hauptzähler 24,6575 m³, Unterzähler je 7,3973 m³, allgemein
    also 9,8630 m³ zu 98,6301 EUR. Die Personentage im selben Fenster sind
    90 und 90, also trägt jeder die Hälfte: 49,3151 EUR. Der Eigenverbrauch
    kostet 73,9726 EUR. Zusammen 123,2877 EUR.
    """
    anna = mieter(1, 'Anna', 1, einzug=date(2020, 1, 1))
    bert = mieter(2, 'Bert', 2, einzug=date(2020, 1, 1))
    v = wasserwelt(date(2025, 1, 1), date(2025, 3, 31), anna, bert)

    posten = rechne(v)['line_items'][0]

    assert posten['tenant_cost'] == Decimal('123.29')
    assert posten['sub_items'][0]['cost'] == Decimal('73.97')
    assert posten['sub_items'][1]['cost'] == Decimal('49.32')
    # Gemessen im Fenster, nicht im Rechnungszeitraum: 90 von 180
    # Personentagen, 9,9 von 100 m³ des Hauses.
    assert 'Anteil: 90 von 180 Personentagen' in posten['description']
    assert 'Haus gesamt: 9.9 m³' in posten['description']


def test_quartal_laesst_den_preis_auf_der_rechnung():
    """Der Einheitspreis bleibt Rechnungsbetrag durch Jahresverbrauch.

    Würde der Preis aus dem geschnittenen Verbrauch entstehen, trüge jede
    Teilabrechnung den vollen Betrag je Einheit, und vier Quartale ergäben
    das Vierfache. Deshalb zeigt der Nachweis jetzt beides: den Verbrauch
    im Fenster und den Verbrauch des vollen Rechnungszeitraums als Preisfuss.
    """
    anna = mieter(1, 'Anna', 1, einzug=date(2020, 1, 1))
    bert = mieter(2, 'Bert', 2, einzug=date(2020, 1, 1))
    v = wasserwelt(date(2025, 1, 1), date(2025, 3, 31), anna, bert)

    details = rechne(v)['line_items'][0]['meter_details']

    assert details['main_consumption'] == 24.7          # 100 m³ * 90/365
    assert details['sum_sub_consumption'] == 14.8       # 2 * 30 m³ * 90/365
    assert details['allgemein_consumption'] == 9.9      # 40 m³ * 90/365
    assert details['rechnung_main_consumption'] == 100.0
    assert details['cost_per_unit'] == Decimal('10.0000')


def test_vier_quartale_addieren_sich_wieder_zum_vollen_betrag():
    """Die Abschnitte tragen zusammen, was das ganze Jahr trägt.

    F-33, dritte Zeile: vier Quartalsabrechnungen ueber dieselbe Rechnung.
    Der Allgemeinanteil je Mieter summiert sich ueber die rohen Werte exakt
    auf 200,00 EUR (die Haelfte von 400 EUR), der Eigenverbrauch auf
    300,00 EUR, die Zeile auf 500,00 EUR. Was die gerundeten Zeilen zeigen,
    liegt einen Cent daneben (500,01): die Restcent-Regel R1 gleicht jede
    Zeile fuer sich aus, und vier Zeilen koennen zusammen einen Cent driften.
    Die Rechnung dahinter ist exakt; der Cent ist Rundung, kein Fehler.
    """
    anna = mieter(1, 'Anna', 1, einzug=date(2020, 1, 1))
    bert = mieter(2, 'Bert', 2, einzug=date(2020, 1, 1))
    quartale = [
        (date(2025, 1, 1), date(2025, 3, 31)),
        (date(2025, 4, 1), date(2025, 6, 30)),
        (date(2025, 7, 1), date(2025, 9, 30)),
        (date(2025, 10, 1), date(2025, 12, 31)),
    ]

    zeilen = []
    allgemein = []
    for beginn, ende in quartale:
        v = wasserwelt(beginn, ende, anna, bert)
        posten = rechne(v)['line_items'][0]
        zeilen.append(posten['tenant_cost'])
        allgemein.append(posten['sub_items'][1]['cost'])

    # 90, 91, 92 und 92 Tage: 700/365, 700*91/365, 700*92/365, 700*92/365
    # roh, je Mieter die Haelfte; gerundet auf den Cent:
    assert zeilen == [
        Decimal('123.29'), Decimal('124.66'), Decimal('126.03'), Decimal('126.03'),
    ]
    assert allgemein == [
        Decimal('49.32'), Decimal('49.87'), Decimal('50.41'), Decimal('50.41'),
    ]
    assert sum(zeilen) == Decimal('500.01')
    assert abs(sum(zeilen) - Decimal('500.00')) <= Decimal('0.02')


# --- Der Mieterwechsel aus F-33 ---------------------------------------------


def test_mieterwechsel_traegt_den_allgemeinanteil_seiner_mietzeit():
    """Wer zur Jahresmitte einzieht, trägt die Hälfte der zweiten Jahreshälfte.

    F-33, Probelauf 2: Anna lebt das ganze Jahr in Wohnung 1, Bert zieht am
    1.7. in Wohnung 2. Sein Abrechnungszeitraum ist der zweite Halbsatz
    (184 Tage). Vor NK-097 wurde der Allgemeinanteil über den vollen
    Rechnungszeitraum verteilt: 400 EUR auf 365+184 Personentage, also rund
    134,30 EUR fuer Bert, obwohl das Haus in seiner Mietzeit nur halb so
    viel allgemein verbrauchte.

    Von Hand: im Fenster (184 Tage) verbraucht das Haus allgemein
    40 m³ * 184/365 = 20,1644 m³ zu 201,6438 EUR. Die Personentage im
    Fenster sind 184 (Anna) und 184 (Bert), also trägt Bert die Hälfte:
    100,8219 EUR. Sein Eigenverbrauch kostet 151,2329 EUR. Zusammen
    252,0548 EUR. Der Befund rechnete mit 'rund 100,80'; exakt sind es
    100,82, weil er das Halbjahr auf 183 Tage rundete.
    """
    anna = mieter(1, 'Anna', 1, einzug=date(2020, 1, 1))
    bert = mieter(2, 'Bert', 2, einzug=date(2025, 7, 1))
    v = wasserwelt(date(2025, 7, 1), date(2025, 12, 31), bert, anna)

    posten = rechne(v)['line_items'][0]

    assert posten['tenant_cost'] == Decimal('252.05')
    assert posten['sub_items'][0]['cost'] == Decimal('151.23')
    assert posten['sub_items'][1]['cost'] == Decimal('100.82')
    # Personentage Zaehler wie Nenner im selben Fenster: 184 von 368, nicht
    # 184 von 549 (das waere der volle Rechnungszeitraum).
    assert 'Anteil: 184 von 368 Personentagen' in posten['description']
    assert 'Haus gesamt: 20.2 m³' in posten['description']


def test_mieterwechsel_aendert_nichts_am_ganzjaehrigen_mieter():
    """Der Altmieter rechnet ueber sein volles Jahr wie bisher.

    Ihr Abrechnungszeitraum (2025) und der Rechnungszeitraum fallen zusammen,
    also misst der Schnitt denselben Verbrauch wie vorher -- die Zahlen fuer
    den ganzjaehrigen Mieter duerfen sich durch NK-097 nicht aendern. Von
    Hand: Eigenverbrauch 300,00 EUR, allgemein 400,00 EUR auf 365 von 730
    Personentagen, zusammen 500,00 EUR. Die 181 Tage vor Berts Einzug stand
    seine Wohnung leer; die traegt seit F-121 der Vermieter (vorher 365 von
    549, 565,94 EUR).
    """
    anna = mieter(1, 'Anna', 1, einzug=date(2020, 1, 1))
    bert = mieter(2, 'Bert', 2, einzug=date(2025, 7, 1))
    v = wasserwelt(RECHNUNG_BEGINN, RECHNUNG_ENDE, anna, bert)

    posten = rechne(v)['line_items'][0]

    assert posten['tenant_cost'] == Decimal('500.00')
    assert posten['sub_items'][0]['cost'] == Decimal('300.00')
    assert posten['sub_items'][1]['cost'] == Decimal('200.00')
    assert 'Anteil: 365 von 730 Personentagen' in posten['description']


def test_nur_allgemein_schneidet_auch_ins_fenster():
    """Der Weg 'nur_allgemein' misst im selben Fenster wie 'direkt'.

    Vier Quartale, verteilt wird nur der Allgemeinverbrauch: auch hier muss
    das erste Quartal einen Vierteljahresanteil zeigen, nicht den des ganzen
    Jahres. Von Hand: 98,6301 EUR allgemein im Quartal, je Mieter die
    Haelfte.
    """
    anna = mieter(1, 'Anna', 1, einzug=date(2020, 1, 1))
    bert = mieter(2, 'Bert', 2, einzug=date(2020, 1, 1))
    v = wasserwelt(date(2025, 1, 1), date(2025, 3, 31), anna, bert,
                   profile={2: 'nur_allgemein'})

    posten = rechne(v)['line_items'][0]

    assert posten['tenant_cost'] == Decimal('49.32')
    assert 'Anteil: 90 von 180 Personentagen' in posten['description']
