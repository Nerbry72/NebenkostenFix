"""Zahlungen: die Serie prüft ihre Eingaben, bevor ein Soll entsteht.

POST /api/payments mit is_recurring bucht Monat für Monat und hinterlegt bei
einer Nebenkostenvorauszahlung danach den Betrag als Soll (R-VZ-02). Drei
Eingaben prüfte die Serie nicht, die Soll-Route dagegen schon:

* ein Enddatum vor dem ersten Zahlungstag: 201 „0 Zahlungen“, aber ein Soll,
  also ein Rückstand und eine Zahlungserinnerung ohne gebuchte Zahlung;
* ein negativer Betrag: 500 aus ck_vorauszahlung_soll_betrag statt einer
  deutschen Absage am Feld;
* ein Beginn nach dem Auszug: ein Soll-Stichtag, den die Soll-Route mit 400
  ablehnt.

Alle Namen, Daten und Beträge sind erfunden.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix.models import Payment, VorauszahlungSoll, db
from tests import billing_factories as f

VZ = 'Nebenkostenvorauszahlung'


@pytest.fixture
def mieter(app_ctx):
    """Mieter Eins wohnt seit 2024, Mieter Zwei ist Ende März 2024 ausgezogen."""
    haus = f.house('Testhaus Nachtweg')
    eins = f.tenant(f.apt(haus, 'W1', 45), 'Mieter Eins', date(2024, 1, 1))
    zwei = f.tenant(f.apt(haus, 'W2', 55), 'Mieter Zwei', date(2023, 1, 1),
                    date(2024, 3, 31))
    db.session.commit()
    return eins, zwei


def _serie(client, mieter, **felder):
    daten = {'tenant_id': str(mieter.id), 'is_recurring': 'true', 'type': VZ}
    daten.update(felder)
    return client.post('/api/payments', data=daten)


def _bestand(mieter):
    zahlungen = Payment.query.filter_by(tenant_id=mieter.id).count()
    soll = [(s.gueltig_ab, s.betrag) for s in
            VorauszahlungSoll.query.filter_by(tenant_id=mieter.id)
            .order_by(VorauszahlungSoll.gueltig_ab)]
    return zahlungen, soll


# --- Bug-Index 2: Enddatum vor dem ersten Zahlungstag --------------------------

def test_ende_vor_beginn_wird_am_enddatum_abgewiesen(auth_client, mieter):
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='120.00',
                     payment_date='2024-06-01', end_date='2024-01-01')

    assert antwort.status_code == 400, (antwort.status_code, antwort.get_json())
    fehler = antwort.get_json()
    assert fehler['feld'] == 'end_date'
    assert fehler['error'] == 'Das Enddatum der Serie liegt vor dem ersten Zahlungstag.'
    assert _bestand(eins) == (0, [])

    # Ohne Soll gibt es keinen Rückstand und keine Zahlungserinnerung.
    ansicht = auth_client.get(f'/api/tenants/{eins.id}/vorauszahlungen').get_json()
    assert ansicht['soll'] == []
    assert not any(m['rueckstand'] for m in ansicht['monate'])
    assert ansicht['offen'] == '0.00'
    assert ansicht['erinnerung'] is None


def test_ende_vor_beginn_gilt_fuer_jede_zahlungsart(auth_client, mieter):
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='120.00', type='Miete',
                     payment_date='2024-06-01', end_date='2024-01-01')

    assert antwort.status_code == 400, (antwort.status_code, antwort.get_json())
    assert antwort.get_json()['feld'] == 'end_date'
    assert _bestand(eins) == (0, [])


def test_ohne_enddatum_und_beginn_nach_dem_vorgabeende(auth_client, mieter):
    """Ohne Enddatum läuft die Serie bis Ende nächsten Jahres. Beginnt sie
    danach, entstünde dieselbe leere Serie mit Soll."""
    eins, _ = mieter
    beginn = date(date.today().year + 2, 1, 1)
    antwort = _serie(auth_client, eins, amount='120.00',
                     payment_date=beginn.isoformat())

    assert antwort.status_code == 400, (antwort.status_code, antwort.get_json())
    fehler = antwort.get_json()
    assert fehler['feld'] == 'end_date'
    assert f'31.12.{date.today().year + 1}' in fehler['error']
    assert _bestand(eins) == (0, [])


def test_ende_gleich_beginn_bucht_eine_zahlung(auth_client, mieter):
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='120.00',
                     payment_date='2024-06-01', end_date='2024-06-01')

    assert antwort.status_code == 201, antwort.get_json()
    assert _bestand(eins) == (1, [(date(2024, 6, 1), Decimal('120.00'))])


# --- Bug-Index 1: negativer Betrag in einer Vorauszahlungs-Serie ---------------

def test_negative_vorauszahlungsserie_wird_am_betrag_abgewiesen(auth_client, mieter):
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='-80.00',
                     payment_date='2024-02-01', end_date='2024-04-01')

    assert antwort.status_code == 400, (antwort.status_code, antwort.get_data(as_text=True))
    fehler = antwort.get_json()
    assert fehler['feld'] == 'amount'
    assert fehler['error'] == 'Eine Vorauszahlung kann nicht negativ sein.'
    assert _bestand(eins) == (0, [])


def test_vorauszahlungsserie_mit_null_bleibt_erlaubt(auth_client, mieter):
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='0.00',
                     payment_date='2024-02-01', end_date='2024-04-01')

    assert antwort.status_code == 201, antwort.get_json()
    assert _bestand(eins) == (3, [(date(2024, 2, 1), Decimal('0.00'))])


def test_negative_einzelbuchung_bleibt_wie_bisher(auth_client, mieter):
    eins, _ = mieter
    antwort = auth_client.post('/api/payments', data={
        'tenant_id': str(eins.id), 'amount': '-50.00', 'type': 'Miete',
        'payment_date': '2024-05-15'})

    assert antwort.status_code == 201, antwort.get_json()
    zahlung = Payment.query.filter_by(tenant_id=eins.id).one()
    assert (zahlung.amount, zahlung.payment_date) == (Decimal('-50.00'), date(2024, 5, 15))


def test_negative_serie_anderer_art_bleibt_wie_bisher(auth_client, mieter):
    """Eine Miet-Serie legt kein Soll an; ihr Betrag bleibt ungeprüft wie bisher."""
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='-50.00', type='Miete',
                     payment_date='2024-02-01', end_date='2024-03-01')

    assert antwort.status_code == 201, antwort.get_json()
    assert _bestand(eins) == (2, [])


# --- Bug-Index 0: Beginn nach dem Auszug -----------------------------------------

def test_serie_nach_dem_auszug_legt_kein_soll_an(auth_client, mieter):
    _, zwei = mieter
    antwort = _serie(auth_client, zwei, amount='90.00',
                     payment_date='2024-05-01', end_date='2024-07-01')

    # Die Zahlungen werden wie bisher gebucht, ein Soll-Stichtag entsteht nicht.
    assert antwort.status_code == 201, antwort.get_json()
    assert _bestand(zwei) == (3, [])
    ansicht = auth_client.get(f'/api/tenants/{zwei.id}/vorauszahlungen').get_json()
    assert ansicht['soll'] == []


def test_serie_ab_dem_auszugstag_legt_das_soll_an(auth_client, mieter):
    """Wie in der Soll-Route: der Auszugstag selbst ist noch ein Stichtag."""
    _, zwei = mieter
    antwort = _serie(auth_client, zwei, amount='90.00',
                     payment_date='2024-03-31', end_date='2024-04-30')

    assert antwort.status_code == 201, antwort.get_json()
    assert _bestand(zwei) == (2, [(date(2024, 3, 31), Decimal('90.00'))])


# --- Gegenprobe: eine gültige Serie bleibt, wie sie war --------------------------

def test_gueltige_serie_bucht_und_hinterlegt_das_soll(auth_client, mieter):
    eins, _ = mieter
    antwort = _serie(auth_client, eins, amount='120.00',
                     payment_date='2024-03-01', end_date='2024-12-31')

    assert antwort.status_code == 201, antwort.get_json()
    assert antwort.get_json()['message'] == '10 Zahlungen erfolgreich erfasst'
    assert _bestand(eins) == (10, [(date(2024, 3, 1), Decimal('120.00'))])
