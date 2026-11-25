"""Zahlungen: eine Serie zum Monatsende rutscht nach dem Februar.

POST /api/payments mit is_recurring bucht Monat für Monat. Jeder Termin wurde
aus dem vorherigen berechnet und nur auf das Monatsende gekappt. War der
Vormonat kürzer, blieb der gekappte Tag stehen: Start am 31.01. ergab 31.01.,
28.02., 28.03., 28.04. … statt 31.03., 30.04. Die Zahlungen lagen damit Monat
für Monat vor dem vereinbarten Tag, und ein Enddatum am Monatsende traf die
Serie einen Termin zu spät oder gar nicht.

Erwartet: jeder Termin wird vom Starttag aus berechnet und nur gekappt, wenn
sein Monat kürzer ist. Alle Namen, Daten und Beträge sind erfunden.
"""

from __future__ import annotations

from datetime import date

import pytest

from nebenkostenfix.models import Payment, db
from tests import billing_factories as f


@pytest.fixture
def mieter(app_ctx):
    haus = f.house('Testhaus Monatsende')
    eins = f.tenant(f.apt(haus, 'W1', 50), 'Mieter Monatsende', date(2023, 1, 1))
    db.session.commit()
    return eins


def _termine(client, mieter, beginn, ende, art='Miete'):
    antwort = client.post('/api/payments', data={
        'tenant_id': str(mieter.id), 'amount': '100.00', 'type': art,
        'payment_date': beginn, 'end_date': ende, 'is_recurring': 'true'})
    assert antwort.status_code == 201, antwort.get_json()
    return [p.payment_date for p in
            Payment.query.filter_by(tenant_id=mieter.id)
            .order_by(Payment.payment_date)]


def test_start_am_31_ohne_schaltjahr(auth_client, mieter):
    assert _termine(auth_client, mieter, '2025-01-31', '2025-06-30') == [
        date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31),
        date(2025, 4, 30), date(2025, 5, 31), date(2025, 6, 30)]


def test_start_am_31_im_schaltjahr(auth_client, mieter):
    assert _termine(auth_client, mieter, '2024-01-31', '2024-04-30') == [
        date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31),
        date(2024, 4, 30)]


def test_start_am_30_ueber_den_jahreswechsel_ins_schaltjahr(auth_client, mieter):
    assert _termine(auth_client, mieter, '2023-11-30', '2024-03-31') == [
        date(2023, 11, 30), date(2023, 12, 30), date(2024, 1, 30),
        date(2024, 2, 29), date(2024, 3, 30)]


def test_start_am_29_ohne_schaltjahr(auth_client, mieter):
    assert _termine(auth_client, mieter, '2025-01-29', '2025-04-30') == [
        date(2025, 1, 29), date(2025, 2, 28), date(2025, 3, 29),
        date(2025, 4, 29)]


def test_enddatum_vor_dem_starttag_im_folgemonat(auth_client, mieter):
    """Endet die Serie am 30.03., fällt der Termin 31.03. weg."""
    assert _termine(auth_client, mieter, '2025-01-31', '2025-03-30') == [
        date(2025, 1, 31), date(2025, 2, 28)]


def test_jahresserie_bleibt_am_monatsende(auth_client, mieter):
    termine = _termine(auth_client, mieter, '2024-08-31', '2025-08-31',
                       art='Nebenkostenvorauszahlung')
    assert len(termine) == 13
    for tag in termine:
        folgetag = date.fromordinal(tag.toordinal() + 1)
        assert folgetag.day == 1, f'{tag} ist kein Monatsende'


def test_serie_mitten_im_monat_bleibt_wie_bisher(auth_client, mieter):
    assert _termine(auth_client, mieter, '2024-01-15', '2024-04-15') == [
        date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15),
        date(2024, 4, 15)]
