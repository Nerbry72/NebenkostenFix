"""NK-142: Der freie Weg zur Abrechnung -- ohne Vorschlagskarte.

Der Kern konnte das schon immer: ``generate`` und ``finalize`` nehmen die
Kostenarten optional; ohne die Liste rechnen sie jede Kostenart mit
Rechnungen im Zeitraum. Was fehlte, war der Weg in der Oberflaeche (F-68)
und der Rueckfall im Spieler. Diese Tests sichern die Grundlage des freien
Wegs an der HTTP-Schicht: freier Auftrag rechnet wie ein vollstaendiger
Vorschlag, die Festsetzung setzt fest, und die Schutzzaeune bleiben.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def freies_mietverhaeltnis(app_ctx):
    """Mieter mit Einzug zum Jahreswechsel und zwei Kostenarten."""
    from nebenkostenfix.models import (Apartment, CostCategory, CostInvoice, Property,
                        Tenant, db)

    haus = Property(name='Haus Frei')
    db.session.add(haus)
    db.session.flush()
    wohnung = Apartment(property_id=haus.id, name='EG', sqm=50.0)
    db.session.add(wohnung)
    db.session.flush()
    mieter = Tenant(apartment_id=wohnung.id, name='Cara Frei',
                    move_in_date=date(2025, 1, 1))
    db.session.add(mieter)
    db.session.flush()

    grund = CostCategory.query.filter_by(name='Grundsteuer').one()
    wasser = CostCategory.query.filter_by(name='Wasserversorgung').one()
    db.session.add(CostInvoice(
        category_id=grund.id, property_id=haus.id,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        amount=Decimal('1200.00')))
    db.session.add(CostInvoice(
        category_id=wasser.id, property_id=haus.id,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        amount=Decimal('300.00')))
    db.session.commit()
    return mieter


def test_freier_auftrag_rechnet_alle_kostenarten(app_ctx, auth_client,
                                                 freies_mietverhaeltnis):
    """Ohne category_ids rechnet der Kern jede Kostenart mit Rechnung im
    Zeitraum -- der Unterschied zum Vorschlagsweg ist nur die Vorarbeit."""
    auftrag = {'tenant_id': freies_mietverhaeltnis.id,
               'start_date': '2025-01-01', 'end_date': '2025-12-31'}

    frei = auth_client.post('/api/billing/generate', json=auftrag)
    assert frei.status_code == 200, frei.get_data(as_text=True)

    from nebenkostenfix.models import CostCategory
    ids = [c.id for c in CostCategory.query.filter(
        CostCategory.name.in_(['Grundsteuer', 'Wasserversorgung'])).all()]
    vorschlagsweg = auth_client.post(
        '/api/billing/generate', json={**auftrag, 'category_ids': ids})
    assert vorschlagsweg.status_code == 200

    # Der Preis des freien Wegs ist der Preis des vollstaendigen Vorschlags.
    assert frei.get_json()['total_amount'] == \
        vorschlagsweg.get_json()['total_amount']
    # 1.200 EUR Grundsteuer + 300 EUR Wasser, beide nach qm auf 50 qm einer
    # Wohnung: nur eine Wohnung, also der volle Betrag.
    assert frei.get_json()['total_amount'] == 1500


def test_festsetzung_auch_ohne_kategorienliste(app_ctx, auth_client,
                                               freies_mietverhaeltnis):
    from nebenkostenfix.models import TenantBillingReport

    res = auth_client.post('/api/billing/finalize', json={
        'tenant_id': freies_mietverhaeltnis.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    assert res.status_code == 201, res.get_data(as_text=True)
    bericht = TenantBillingReport.query.filter_by(
        tenant_id=freies_mietverhaeltnis.id).one()
    assert bericht.document_path


def test_ueberschneidung_stoppt_auch_den_freien_weg(app_ctx, auth_client,
                                                    freies_mietverhaeltnis):
    """Frei waehlen heisst nicht, doppelt abrechnen zu koennen."""
    erste = auth_client.post('/api/billing/generate', json={
        'tenant_id': freies_mietverhaeltnis.id,
        'start_date': '2025-01-01', 'end_date': '2025-06-30'})
    assert erste.status_code == 200
    auth_client.post('/api/billing/finalize', json={
        'tenant_id': freies_mietverhaeltnis.id,
        'start_date': '2025-01-01', 'end_date': '2025-06-30'})

    zweite = auth_client.post('/api/billing/generate', json={
        'tenant_id': freies_mietverhaeltnis.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    assert zweite.status_code == 400
    assert 'überschneidet sich' in zweite.get_json()['error']


def test_zeitraum_wird_auf_das_mietverhaeltnis_gestutzt(app_ctx, auth_client,
                                                      freies_mietverhaeltnis):
    """Der freie Auftrag darf schief liegen, ohne zu kippen: vor dem Einzug
    stutzt lade_vorgang auf den Mietbeginn. Die Antwort nennt den tatsaechlich
    gerechneten Zeitraum -- die Vorschau zeigt also das, was abgerechnet wird.

    Auftrag 1.6.2024–31.12.2025, Einzug 1.1.2025 → gerechnet ein ganzes Jahr,
    1200 + 300 = 1500. Gemessen am Mietverhaeltnis ist das nicht zu lang,
    also kein Hinweis auf die Ueberlaenge (F-112).
    """
    res = auth_client.post('/api/billing/generate', json={
        'tenant_id': freies_mietverhaeltnis.id,
        'start_date': '2024-06-01', 'end_date': '2025-12-31'})
    assert res.status_code == 200, res.get_data(as_text=True)
    daten = res.get_json()
    assert daten['start_date'] == '2025-01-01'
    assert daten['end_date'] == '2025-12-31'
    assert daten['total_amount'] == 1500
    assert not any('länger als ein Jahr' in w for w in daten['warnings'])


def test_laenger_als_ein_jahr_wird_gerechnet_und_gewarnt(app_ctx, auth_client,
                                                         freies_mietverhaeltnis):
    """F-112: 1.1.2025–31.1.2026 ist 13 Monate lang. Frueher kuerzte die
    Erzeugung stillschweigend auf den 31.12.2025 -- Zaehlerstaende vom
    Monatsende fielen aus der Abrechnung, und niemand sagte es. Jetzt wird der
    eingegebene Zeitraum gerechnet, Vorpruefung und Ergebnis weisen auf
    § 556 Abs. 3 BGB hin, und nichts blockiert.
    """
    auftrag = {'tenant_id': freies_mietverhaeltnis.id,
               'start_date': '2025-01-01', 'end_date': '2026-01-31'}

    vorab = auth_client.post('/api/billing/preflight', json=auftrag)
    assert vorab.status_code == 200, vorab.get_data(as_text=True)
    kacheln = [c for c in vorab.get_json()['checks']
               if 'länger als ein Jahr' in (c['message'] or '')]
    assert len(kacheln) == 1
    assert kacheln[0]['status'] == 'warning'
    assert kacheln[0]['blocking'] is False
    assert '396 Tage' in kacheln[0]['message']

    res = auth_client.post('/api/billing/generate', json=auftrag)
    assert res.status_code == 200, res.get_data(as_text=True)
    daten = res.get_json()
    assert daten['end_date'] == '2026-01-31'
    assert any('länger als ein Jahr' in w for w in daten['warnings'])


def test_freier_weg_braucht_anmeldung(app_ctx, anon_client,
                                      freies_mietverhaeltnis):
    assert anon_client.post('/api/billing/generate', json={
        'tenant_id': freies_mietverhaeltnis.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'}).status_code == 401
