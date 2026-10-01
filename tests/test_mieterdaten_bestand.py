"""NK-191: Mieter-, Vertrags- und Zahlungsdaten, wie sie im Bestand liegen.

Die Praxisprobe (NK-187) fand Mieter ohne Kostenprofil und ohne Rechnungen
(H8), Vorauszahlungen bis weit in die Zukunft und nach dem Auszug (H9) und
ein „abgerechnet bis“, das ein Jahr hinter der letzten Abrechnung liegt
(H10, F-127). Alle Werte sind erfunden.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from nebenkostenfix.billing_engine import BillingEngine
from nebenkostenfix.frist import frist_ende
from nebenkostenfix.models import TenantBillingReport, db
from tests import billing_factories as f

B, E = date(2025, 1, 1), date(2025, 12, 31)


def _abrechnung(mieter, beginn, ende):
    db.session.add(TenantBillingReport(tenant_id=mieter.id, start_date=beginn, end_date=ende,
                                       frist_ende=frist_ende(ende)))
    db.session.commit()


def _rechne(mieter, beginn=B, ende=E):
    return BillingEngine(mieter.id, beginn.isoformat(), ende.isoformat()).calculate_bill()


# --- H10 / F-127: „abgerechnet bis“ ist überall dasselbe ---------------------------

def test_mieterliste_zeigt_das_ende_der_letzten_abrechnung(auth_client, app_ctx):
    """Das Feld blieb beim Erstellen einer Abrechnung stehen; die Liste zeigte es roh."""
    mieter = f.tenant(f.apt(f.house(), 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    mieter.last_billed_until = date(2024, 12, 31)
    _abrechnung(mieter, B, E)

    liste = auth_client.get('/api/tenants').get_json()

    assert [m['last_billed_until'] for m in liste] == ['2025-12-31']


def test_ein_neueres_feld_gilt_auch_in_der_liste(auth_client, app_ctx):
    """Wer ausserhalb der App abgerechnet hat, traegt das Datum von Hand ein."""
    mieter = f.tenant(f.apt(f.house(), 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    mieter.last_billed_until = date(2025, 12, 31)
    _abrechnung(mieter, date(2024, 1, 1), date(2024, 12, 31))

    liste = auth_client.get('/api/tenants').get_json()

    assert [m['last_billed_until'] for m in liste] == ['2025-12-31']


def test_uebersicht_zaehlt_abgerechnete_mieter_nicht_als_offen(auth_client, app_ctx):
    heute = date.today()
    haus = f.house()
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=heute - timedelta(days=2000))
    mieter.last_billed_until = heute - timedelta(days=1000)
    _abrechnung(mieter, heute - timedelta(days=375), heute - timedelta(days=10))

    kpis = auth_client.get(f'/api/analytics/building/{haus.id}').get_json()['kpis']

    assert kpis['open_tasks'] == 0


def test_uebersicht_zaehlt_den_auszugstag_noch_mit(auth_client, app_ctx):
    """F-118: Das Auszugsdatum ist der letzte Miettag, der Mieter wohnt heute noch."""
    heute = date.today()
    haus = f.house()
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=heute - timedelta(days=2000))
    mieter.move_out_date = heute
    db.session.commit()

    kpis = auth_client.get(f'/api/analytics/building/{haus.id}').get_json()['kpis']

    assert kpis['open_tasks'] == 1


# --- H8: ohne Kostenprofil, ohne Rechnungen -----------------------------------------

def test_ohne_kostenprofil_wird_nach_flaeche_umgelegt(app_ctx):
    haus = f.house()
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    f.tenant(f.apt(haus, 'OG', 150), 'Mieter 2', move_in=date(2020, 1, 1))
    f.invoice(haus, f.category('Versicherung'), 400.0, start=B, end=E)

    ergebnis = _rechne(mieter)

    [zeile] = ergebnis['line_items']
    assert zeile['billing_type'] == 'qm'
    assert zeile['tenant_cost'] == Decimal('100.00')


def test_ohne_rechnung_sagt_die_abrechnung_was_zu_tun_ist(app_ctx):
    """Vorher: Kosten 0, alle Vorauszahlungen zurück, keine Meldung."""
    mieter = f.tenant(f.apt(f.house(), 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    f.payment(mieter, 100.0, date(2025, 3, 1))

    ergebnis = _rechne(mieter)

    assert ergebnis['line_items'] == []
    assert ('Für 01.01.2025–31.12.2025 ist keine Rechnung erfasst, die Abrechnung '
            'erstattet deshalb alle Vorauszahlungen. Erfassen Sie zuerst die '
            'Rechnungen des Zeitraums.') in ergebnis['warnings']


def test_mit_rechnung_keine_leermeldung(app_ctx):
    haus = f.house()
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    f.invoice(haus, f.category('Versicherung'), 400.0, start=B, end=E)

    assert not any('keine Rechnung erfasst' in w for w in _rechne(mieter)['warnings'])


# --- H9: Vorauszahlungen in der Zukunft, nach dem Auszug, Kaution ------------------

def test_nur_zahlungen_im_zeitraum_zaehlen(app_ctx):
    mieter = f.tenant(f.apt(f.house(), 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    for monat in range(1, 13):
        f.payment(mieter, 100.0, date(2024, monat, 1))
        f.payment(mieter, 100.0, date(2025, monat, 1))
        f.payment(mieter, 100.0, date(2027, monat, 1))
    f.payment(mieter, 900.0, date(2025, 1, 1), ptype='Kaution')

    assert _rechne(mieter)['prepaid_amount'] == Decimal('1200.00')


def test_zahlungen_nach_dem_auszug_werden_gemeldet(auth_client, app_ctx):
    """H9: Vorauszahlungen liefen nach dem Auszug weiter, niemand sah sie."""
    haus = f.house()
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1),
                      move_out=date(2025, 6, 30))
    f.invoice(haus, f.category('Versicherung'), 400.0, start=B, end=E)
    for monat in range(1, 10):
        f.payment(mieter, 100.0, date(2025, monat, 1))

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id, 'start_date': '2025-01-01', 'end_date': '2025-12-31'})

    ergebnis = antwort.get_json()
    assert ergebnis['prepaid_amount'] == 600
    assert ('Nach dem Auszug am 30.06.2025 sind 3 Vorauszahlungen über 300,00 € gebucht. '
            'Sie zählen in keiner Abrechnung. Prüfen Sie, ob sie zurückzuzahlen oder '
            'falsch gebucht sind.') in ergebnis['warnings']


def test_ohne_spaete_zahlung_kein_hinweis(auth_client, app_ctx):
    haus = f.house()
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1),
                      move_out=date(2025, 6, 30))
    f.invoice(haus, f.category('Versicherung'), 400.0, start=B, end=E)
    f.payment(mieter, 100.0, date(2025, 6, 1))
    f.payment(mieter, 500.0, date(2025, 8, 1), ptype='Kaution')

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id, 'start_date': '2025-01-01', 'end_date': '2025-12-31'})

    assert not any('Nach dem Auszug' in w for w in antwort.get_json()['warnings'])


# --- Wechsel der Personenzahl im Zeitraum --------------------------------------------

def test_personenzahl_wechselt_im_zeitraum(app_ctx):
    """Nach Personentagen: 2 × 181 + 1 × 184 = 546 gegen 730 beim Nachbarn."""
    haus = f.house()
    kat = f.category('Müllabfuhr')
    mieter = f.tenant(f.apt(haus, 'EG', 50), 'Mieter 1', move_in=date(2020, 1, 1))
    nachbar = f.tenant(f.apt(haus, 'OG', 50), 'Mieter 2', move_in=date(2020, 1, 1))
    f.haushalt(mieter, date(2020, 1, 1), 2)
    f.haushalt(mieter, date(2025, 7, 1), 1)
    f.haushalt(nachbar, date(2020, 1, 1), 2)
    f.profile(mieter, kat, 'personen')
    f.profile(nachbar, kat, 'personen')
    f.invoice(haus, kat, 1276.0, start=B, end=E)

    [zeile] = _rechne(mieter)['line_items']

    assert zeile['tenant_cost'] == Decimal('546.00')
