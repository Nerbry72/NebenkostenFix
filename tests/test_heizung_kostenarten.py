"""NK-232/NK-233: die abgerechneten Kostenarten einer Abrechnung mit Heizungsanlage.

Der Heizposten heißt „Heizkosten (Anlage)“, nicht „Heizkosten“. Die
Festsetzung ohne Auswahl leitete die Kostenarten aus den Postennamen ab und
verlor so die Heizkosten. Daran hingen drei Stellen: die Details nannten
„Teilauswahl“ statt des Vorauszahlungsvorschlags, die Überlappungsprüfung ließ
eine zweite Abrechnung der Heizkosten durch, und die Korrektur rechnete ohne
Heizkosten neu.
"""

from __future__ import annotations

from datetime import date

from nebenkostenfix import vorauszahlung
from nebenkostenfix.models import (BillingReportCategory, Heizungsanlage,
                                   TenantBillingReport, db)

from billing_factories import (apt, category, house, invoice, meter, payment,
                               reading, tenant)

JAHR_2025 = (date(2025, 1, 1), date(2025, 12, 31))
ZEITRAUM = {'start_date': '2025-01-01', 'end_date': '2025-12-31'}


def _heizwelt():
    """Ein Mieter allein im Haus: Grundsteuer und Heizkosten über eine Anlage."""
    prop = house('Heizhaus')
    wohnung = apt(prop, 'EG', 50.0)
    mieter = tenant(wohnung, 'Hanna Heizerin', move_in=date(2024, 1, 1))
    invoice(prop, category('Grundsteuer'), 1200.0, *JAHR_2025)
    anlage = Heizungsanlage(property_id=prop.id, name='Zentral',
                            verbrauchsanteil_prozent=70)
    db.session.add(anlage)
    db.session.commit()
    heiz = category('Heizkosten')
    rechnung = invoice(prop, heiz, 1200.0, *JAHR_2025, invoice_number='H-1')
    rechnung.heizungsanlage_id = anlage.id
    rechnung.heizkostenart = 'brennstoff'
    zaehler = meter(prop, heiz, 'W1', is_main=False, apartment=wohnung)
    zaehler.heizungsanlage_id = anlage.id
    db.session.commit()
    reading(zaehler, date(2025, 1, 1), 0)
    reading(zaehler, date(2026, 1, 1), 100)
    for m in range(1, 13):
        payment(mieter, 80.0, date(2025, m, 1))
    return mieter, heiz


def _festsetzen(client, mieter, **zusatz):
    antwort = client.post('/api/billing/finalize',
                          json={'tenant_id': mieter.id, **ZEITRAUM, **zusatz})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return TenantBillingReport.query.one()


def test_die_details_nennen_den_vorschlag_der_vorschau(auth_client, app_ctx, monkeypatch):
    monkeypatch.setattr(vorauszahlung, '_heute', lambda: date(2026, 3, 15))
    mieter, _ = _heizwelt()
    vorschau = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id, **ZEITRAUM}).get_json()['vorauszahlung']
    assert vorschau['neu'] == '200.00'
    report = _festsetzen(auth_client, mieter)
    report.aktuelle_version.erstellt_am = date(2026, 3, 15)
    db.session.commit()

    details = auth_client.get(f'/api/billing/reports/{report.id}/details') \
        .get_json()['vorauszahlung']
    assert details == vorschau


def test_die_festsetzung_speichert_die_heizkosten(auth_client, app_ctx):
    mieter, heiz = _heizwelt()
    report = _festsetzen(auth_client, mieter)
    assert heiz.id in {c.category_id for c in report.categories}


def test_eine_zweite_abrechnung_der_heizkosten_wird_abgewiesen(auth_client, app_ctx):
    mieter, heiz = _heizwelt()
    _festsetzen(auth_client, mieter)
    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id, **ZEITRAUM, 'category_ids': [heiz.id]})
    assert antwort.status_code == 400
    assert 'überschneidet' in antwort.get_json()['error']


def test_die_korrektur_rechnet_mit_den_heizkosten(auth_client, app_ctx):
    """Auch eine schon gespeicherte Abrechnung ohne die Heizkosten-Zeile.

    So liegen die Abrechnungen im Bestand: die Korrektur nimmt die Auswahl
    aus dem Schnappschuss, nicht aus den gespeicherten Kostenarten.
    """
    mieter, heiz = _heizwelt()
    report = _festsetzen(auth_client, mieter)
    BillingReportCategory.query.filter_by(report_id=report.id,
                                          category_id=heiz.id).delete()
    db.session.commit()

    vorschau = auth_client.get(f'/api/billing/reports/{report.id}/korrektur/vorschau')
    assert vorschau.get_json()['unveraendert'] is True
