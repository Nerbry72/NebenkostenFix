"""Der Dualtarif: HT und NT werden getrennt gerechnet (NK-055, Risiko 8).

Ein Zaehler mit Hoch- und Niedertarif liefert zwei Mengen, und der
Versorger stellt ihnen zwei Preise. Bis NK-055 wurden beide Register
einfach addiert und der Rechnungsbetrag durch die Gesamtmenge geteilt --
ein Mischpreis, mit dem der NT-Kunde den HT-Anteil des Hauses
mitfinanzierte (IST-Stand, Risiko 8, zweiter Teil).

Die Faelle dieser Datei:

* ``verbrauch_in`` liefert die Mengen der beiden Register getrennt, nach
  derselben Interpolation wie die Gesamtmenge (Summe = Verbrauch).
* ``tarifpreise`` teilt den Rechnungsbetrag nach Wertanteil auf die
  Tarife -- der Betrag bleibt die verbindliche Summe, die Preise
  bestimmen nur den Schnitt.
* Die Mieterzeile rechnet Eigenverbrauch und Allgemeinanteil je Register
  mit dem Preis seines Registers: wer NT-lastig wohnt, zahlt weniger als
  beim Mischpreis, wer HT-lastig wohnt, mehr -- und alle Zeilen addieren
  sich wieder zum Rechnungsbetrag.
* Ohne Tarifpreise (Altbestand, Einheitstarif) gilt der Mischpreis weiter.
* Beruht der Preisfuss auf hochgerechnetem Verbrauch, weil die Ablesungen
  den Rechnungszeitraum nicht decken, warnt die Abrechnung -- sie blockiert
  nicht.
* Die Route nimmt beide Tarifpreise an, lehnt einen allein ab und
  durchreicht sie bis in den Vorgang.

Jede Zahl ist von Hand nachgerechnet und steht im Test.
"""

from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix.rechenkern import (
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    rechne,
    tarifpreise,
    verbrauch_in,
)

JAHR_BEGINN = date(2026, 1, 1)
JAHR_ENDE = date(2026, 12, 31)
JAHR_GRENZE = date(2027, 1, 1)

STROM = Kategorie(id=1, name='Strom', braucht_zaehler=True)


# --- Die Welt: ein Haus, ein Hauptzaehler mit zwei Registern ---------------

HAUPT_HT = 3000.0
HAUPT_NT = 1000.0
ANNA_HT = 1200.0
ANNA_NT = 800.0
BERT_HT = 1400.0
BERT_NT = 200.0


def stand(tag, wert, nt=0.0):
    """Ein Zaehlerstand in beiden Registern."""
    return Stand(datum=tag, wert=wert, wert_nt=nt)


def hauptzaehler(staende):
    return Zaehler(
        id=10, nummer='H-STROM', kategorie_id=STROM.id,
        kategorie_name='Strom', ist_hauptzaehler=True, immobilie_id=1,
        staende=tuple(staende))


def wohnungszaehler(id, wohnung_id, staende):
    return Zaehler(
        id=id, nummer=f'S-{id}', kategorie_id=STROM.id,
        kategorie_name='Strom', ist_hauptzaehler=False, immobilie_id=1,
        wohnung_id=wohnung_id, staende=tuple(staende))


def stromrechnung(betrag='1300.00', id=1, **kw):
    """Das Jahresstromkonto: 1300,00 EUR = 3000 kWh HT * 0,40 + 1000 * 0,10."""
    return Rechnung(
        id=id, kategorie=STROM, betrag=Decimal(betrag),
        beginn=JAHR_BEGINN, ende=JAHR_ENDE, **kw)


ANNA = Mieter(
    id=1, name='Anna NT-lastig', einzug=date(2020, 1, 1), auszug=None,
    wohnung_id=1)
BERT = Mieter(
    id=2, name='Bert HT-lastig', einzug=date(2020, 1, 1), auszug=None,
    wohnung_id=2)


def haus(mieter=None, profile=None, rechnungen=None, zaehler=None, **kw):
    """Zwei Wohnungen zu 50 qm; mein Mieter wohnt links, Bert rechts."""
    links = Wohnung(id=1, name='EG links', qm=50.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = mieter or ANNA
    grund = dict(
        mieter=ich,
        wohnung=ich.wohnung_id == 1 and links or rechts,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(links, rechts),
        mieter_der_immobilie=(ANNA, BERT),
        profile=profile if profile is not None else {STROM.id: 'direkt'},
        rechnungen=(rechnungen if rechnungen is not None
                    else (stromrechnung(
                        preis_ht=Decimal('0.40'), preis_nt=Decimal('0.10')),)),
        zaehler=(zaehler if zaehler is not None else (
            hauptzaehler((
                stand(JAHR_BEGINN, 0.0, 0.0),
                stand(JAHR_GRENZE, HAUPT_HT, HAUPT_NT))),
            wohnungszaehler(11, 1, (
                stand(JAHR_BEGINN, 0.0, 0.0),
                stand(JAHR_GRENZE, ANNA_HT, ANNA_NT))),
            wohnungszaehler(12, 2, (
                stand(JAHR_BEGINN, 0.0, 0.0),
                stand(JAHR_GRENZE, BERT_HT, BERT_NT))),
        )),
        zahlungen=(),
        heizungsanlagen=(),
    )
    grund.update(kw)
    return Vorgang(**grund)


def stromzeile(ergebnis):
    zeilen = [z for z in ergebnis['line_items'] if z['billing_type'] == 'direkt']
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


# --- AK: verbrauch_in trennt die Register -----------------------------------

def test_verbrauch_in_trennt_die_register():
    """HT und NT werden getrennt interpoliert; ihre Summe ist der Verbrauch."""
    auskunft = verbrauch_in(hauptzaehler((
        stand(JAHR_BEGINN, 0.0, 0.0),
        stand(JAHR_GRENZE, HAUPT_HT, HAUPT_NT))), JAHR_BEGINN, JAHR_GRENZE)

    assert auskunft['ht'] == HAUPT_HT
    assert auskunft['nt'] == HAUPT_NT
    assert auskunft['ht'] + auskunft['nt'] == auskunft['consumption']


def test_verbrauch_in_ohne_nt_register_zaehlt_null():
    """Ein Einheitstarifzaehler hat kein NT; in nt steht die 0."""
    auskunft = verbrauch_in(hauptzaehler((
        stand(JAHR_BEGINN, 0.0),
        stand(JAHR_GRENZE, 2500.0))), JAHR_BEGINN, JAHR_GRENZE)

    assert auskunft['consumption'] == 2500.0
    assert auskunft['ht'] == 2500.0
    assert auskunft['nt'] == 0.0


# --- AK: tarifpreise teilen den Betrag nach Wertanteil ----------------------

def test_tarifpreile_nach_wertanteil():
    """Der Betrag wird nach Wertanteil gesplitet, nicht nach Menge.

    1430,00 EUR auf 3000 kWh HT (0,40) und 1000 kWh NT (0,10): der
    Wertanteil des HT ist 1200 von 1300, also entfallen 1320,00 EUR auf HT
    und 110,00 auf NT -- die effektiven Preise sind 0,44 und 0,11.
    """
    preis_ht, preis_nt = tarifpreise(
        Decimal('1430.00'), Decimal('3000'), Decimal('1000'),
        Decimal('0.40'), Decimal('0.10'))

    assert preis_ht == Decimal('0.44')
    assert preis_nt == Decimal('0.11')
    assert preis_ht * 3000 + preis_nt * 1000 == Decimal('1430.00')


def test_tarifpreile_bleiben_die_der_rechnung_wenn_sie_konsistent_ist():
    """Passt der Betrag zu den Preisen, reproduziert der Schnitt sie genau."""
    preis_ht, preis_nt = tarifpreise(
        Decimal('1300.00'), Decimal('3000'), Decimal('1000'),
        Decimal('0.40'), Decimal('0.10'))

    assert preis_ht == Decimal('0.40')
    assert preis_nt == Decimal('0.10')


def test_tarifpreile_ohne_angabe_gibt_den_einheitstarif():
    """Keine Preise, keine NT-Menge, Gesamtwert null -- alles (None, None)."""
    assert tarifpreise(
        Decimal('100.00'), Decimal('10'), Decimal('5'),
        None, Decimal('0.20')) == (None, None)
    assert tarifpreise(
        Decimal('100.00'), Decimal('10'), Decimal('0'),
        Decimal('0.40'), Decimal('0.30')) == (None, None)
    assert tarifpreise(
        Decimal('100.00'), Decimal('10'), Decimal('5'),
        Decimal('0'), Decimal('0')) == (None, None)


# --- AK: die Zeile rechnet je Register mit dem Preis des Registers ----------

def test_der_nt_lastige_zahlt_weniger_als_beim_mischpreis():
    """Der Euro-Effekt der Karte: Anna wohnt NT-lastig.

    Beim Mischpreis (1300,00 / 4000 kWh = 0,325) zahlte sie 2000 kWh * 0,325
    = 650,00 zuzüglich 65,00 Allgemeinanteil (130,00 / 2) = 715,00. Getrennt
    gerechnet zahlt sie 1200 * 0,40 + 800 * 0,10 = 560,00 zuzüglich 80,00
    (160,00 / 2) = 640,00 -- der NT-lastige Haushalt wird entlastet.
    """
    dual = stromzeile(rechne(haus()))['tenant_cost']
    einheit = stromzeile(rechne(haus(
        rechnungen=(stromrechnung(),))))['tenant_cost']

    assert dual == Decimal('640.00')
    assert einheit == Decimal('715.00')


def test_der_ht_lastige_zahlt_mehr_als_beim_mischpreis():
    """Bert wohnt HT-lastig: 660,00 statt 585,00 -- dieselbe Korrektur."""
    dual = rechne(haus(mieter=BERT))
    einheit = rechne(haus(
        mieter=BERT, rechnungen=(stromrechnung(),)))

    assert stromzeile(dual)['tenant_cost'] == Decimal('660.00')
    assert stromzeile(einheit)['tenant_cost'] == Decimal('585.00')


def test_die_zeilen_addieren_sich_wieder_zum_rechnungsbetrag():
    """Bilanz (R-NUM-02): beide Mieterzeilen ergeben wieder den Betrag."""
    for betrag in ('1300.00', '1430.00'):
        rechnung = stromrechnung(
            betrag=betrag, preis_ht=Decimal('0.40'), preis_nt=Decimal('0.10'))
        summe = sum(
            stromzeile(rechne(haus(mieter=m, rechnungen=(rechnung,))))['tenant_cost']
            for m in (ANNA, BERT))
        assert summe == Decimal(betrag), betrag


def test_die_zeile_nennt_die_tarifpreile():
    """Die Zaehlerdetails tragen die effektiven Preise (R-NUM-05-Nachweis)."""
    details = stromzeile(rechne(haus()))['meter_details']

    assert details['preis_ht'] == Decimal('0.4000')
    assert details['preis_nt'] == Decimal('0.1000')
    # Beim Dualtarif steht der Mischpreis bewusst auf None.
    assert details['cost_per_unit'] is None


# --- AK: die Zeitraumpruefung des Preisfusses -------------------------------

def test_der_preisfuss_warnt_wenn_ablesungen_den_zeitraum_nicht_decken():
    """Halbes Jahr abgelesen, ganzes Jahr abgerechnet: der Preis ist ein Schätzwert.

    Der Preisfuss rechnet den Rechnungsbetrag durch den Verbrauch des
    Rechnungszeitraums. Beruht dieser Verbrauch auf der Hochrechnung,
    weil die Ablesungen vor dem Ende des Zeitraums aufhören, ist der
    Preis eine Schätzung -- die Abrechnung sagt das mit der Kennung
    W-ZAEHLER-PREIS-HOCHGERECHNET und rechnet trotzdem.
    """
    halber = hauptzaehler((
        stand(JAHR_BEGINN, 0.0, 0.0),
        stand(date(2026, 7, 1), HAUPT_HT / 2, HAUPT_NT / 2)))
    ergebnis = rechne(haus(zaehler=(
        halber,
        wohnungszaehler(11, 1, (
            stand(JAHR_BEGINN, 0.0, 0.0),
            stand(JAHR_GRENZE, ANNA_HT, ANNA_NT))))))

    warnungen = [w for w in ergebnis['warnings']
                 if 'W-ZAEHLER-PREIS-HOCHGERECHNET' in w]
    assert len(warnungen) == 1
    assert 'H-STROM' in warnungen[0]
    assert '01.01.2026' in warnungen[0] and '31.12.2026' in warnungen[0]


def test_der_preisfuss_schweigt_bei_gedecktem_zeitraum():
    """Volle Ablesedaten: keine Preiswarnung."""
    ergebnis = rechne(haus())

    assert not [w for w in ergebnis['warnings']
                if 'W-ZAEHLER-PREIS-HOCHGERECHNET' in w]


# --- AK: die Route nimmt beide Preise oder keinen ---------------------------

from billing_factories import apt, house, tenant  # noqa: E402


def _tarifhaus(app_ctx, name='Tarifhaus'):
    prop = house(name=name)
    wng = apt(prop, 'Tarif-EG', 50.0)
    mieter = tenant(wng, 'Tarifmieter', move_in=date(2024, 1, 1))
    return prop, mieter


def test_route_nimmt_beide_tarifpreile_an(auth_client, app_ctx):
    """POST /api/invoices speichert HT- und NT-Preis auf vier Stellen."""
    prop, _ = _tarifhaus(app_ctx)
    from nebenkostenfix.models import CostCategory
    kat = CostCategory.query.filter_by(name='Wasserversorgung').first()

    antwort = auth_client.post('/api/invoices', json={
        'category_id': kat.id,
        'property_id': prop.id,
        'amount': '460.00',
        'start_date': '2026-01-01',
        'end_date': '2026-12-31',
        'preis_ht': '0,3582',
        'preis_nt': '0,2147',
    })
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    from nebenkostenfix.models import CostInvoice
    rechnung = CostInvoice.query.get(antwort.get_json()['id'])
    assert rechnung.preis_ht == Decimal('0.3582')
    assert rechnung.preis_nt == Decimal('0.2147')


def test_route_lehnt_einen_preis_allein_ab(auth_client, app_ctx):
    """Ein Tarifpreis ohne seinen Partner behauptet eine Aufteilung ohne Beleg."""
    prop, _ = _tarifhaus(app_ctx)
    from nebenkostenfix.models import CostCategory
    kat = CostCategory.query.filter_by(name='Wasserversorgung').first()

    antwort = auth_client.post('/api/invoices', json={
        'category_id': kat.id,
        'property_id': prop.id,
        'amount': '460.00',
        'start_date': '2026-01-01',
        'end_date': '2026-12-31',
        'preis_ht': '0.40',
    })
    assert antwort.status_code == 400
    assert 'zusammen' in antwort.get_json()['error']


def test_route_lehnt_negativen_tarifpreis_ab(auth_client, app_ctx):
    """Ein Preis ist ein Mengenpreis, keine Saldo -- das Vorzeichen dreht nichts."""
    prop, _ = _tarifhaus(app_ctx)
    from nebenkostenfix.models import CostCategory
    kat = CostCategory.query.filter_by(name='Wasserversorgung').first()

    antwort = auth_client.post('/api/invoices', json={
        'category_id': kat.id,
        'property_id': prop.id,
        'amount': '460.00',
        'start_date': '2026-01-01',
        'end_date': '2026-12-31',
        'preis_ht': '-0.40',
        'preis_nt': '0.30',
    })
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == 'preis_ht'


def test_der_lader_durchreicht_die_tarifpreile(app_ctx):
    """lade_vorgang traegt die Preise in den Vorgang (NK-037-Schnittstelle)."""
    from nebenkostenfix.abrechnungsdaten import lade_vorgang
    prop, mieter = _tarifhaus(app_ctx, name='Ladehaus')
    from nebenkostenfix.models import CostCategory, CostInvoice, db
    kat = CostCategory.query.filter_by(name='Wasserversorgung').first()
    db.session.add(CostInvoice(
        category_id=kat.id, property_id=prop.id,
        start_date=JAHR_BEGINN, end_date=JAHR_ENDE,
        amount=Decimal('460.00'),
        preis_ht=Decimal('0.3582'), preis_nt=Decimal('0.2147')))
    db.session.commit()

    vorgang = lade_vorgang(mieter.id, JAHR_BEGINN, JAHR_ENDE)
    rechnung = [r for r in vorgang.rechnungen if r.kategorie.id == kat.id][0]
    assert rechnung.preis_ht == Decimal('0.3582')
    assert rechnung.preis_nt == Decimal('0.2147')
