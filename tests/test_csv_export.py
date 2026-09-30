"""NK-145: Die Positionen einer Abrechnung als CSV.

Geprueft wird durch die HTTP-Schicht gegen eine festgesetzte Abrechnung:
die CSV muss dieselben Zahlen tragen wie das gespeicherte Ergebnis (der
Schnappschuss der gueltigen Version), deutsch formatiert fuer Excel, und
darf keinen Anbieternamen als Formel ausliefern.
"""

import csv
import io
from datetime import date
from decimal import Decimal

from billing_factories import apt, category, house, invoice, payment, profile, tenant

ZEITRAUM = {'start_date': '2025-01-01', 'end_date': '2025-12-31'}


def _welt():
    from nebenkostenfix.models import db

    grundsteuer = category('Grundsteuer')
    prop = house('Musterhaus Lindenstraße')
    wohnung = apt(prop, 'EG links', 50.0)
    apt(prop, 'OG rechts', 50.0)
    mieter = tenant(wohnung, 'Anna Mieterin', move_in=date(2024, 1, 1))
    profile(mieter, grundsteuer, 'qm')
    rechnung = invoice(prop, grundsteuer, 1200.0, date(2025, 1, 1),
                       date(2025, 12, 31), invoice_number='GS-2025')
    payment(mieter, 250.0, date(2025, 3, 1))
    db.session.commit()
    return mieter, rechnung


def _festsetzen(auth_client, mieter_id):
    from nebenkostenfix.models import TenantBillingReport

    antwort = auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter_id, **ZEITRAUM})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return TenantBillingReport.query.one()


def _zeilen(antwort):
    text = antwort.data.decode('utf-8')
    assert text.startswith('﻿'), 'Excel braucht den BOM für Umlaute'
    return list(csv.reader(io.StringIO(text[1:]), delimiter=';'))


def test_csv_traegt_die_positionen_der_festgesetzten_abrechnung(app_ctx, auth_client):
    mieter, _ = _welt()
    report = _festsetzen(auth_client, mieter.id)

    antwort = auth_client.get(f'/api/billing/reports/{report.id}/positionen.csv')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.mimetype == 'text/csv'
    assert 'Positionen_Anna Mieterin_20250101-20251231.csv' in \
        antwort.headers['Content-Disposition']
    assert b'\r\n' in antwort.data

    zeilen = _zeilen(antwort)
    kopf, *rumpf = zeilen
    assert kopf[0] == 'Zeile' and kopf[-1] == 'Erläuterung'
    position = rumpf[0]
    assert position[1] == 'Position'
    assert position[4] == 'GS-2025'
    assert position[6] == '01.01.2025 - 31.12.2025'
    assert position[7] == '1200,00'
    assert position[8] == 'Umlage nach Wohnfläche'
    assert position[11] == '600,00'  # die Hälfte der Fläche

    summen = {z[2]: z[11] for z in rumpf if z[1] == 'Summe'}
    assert summen['Summe Ihrer Kosten'] == '600,00'
    assert summen['Ihre Vorauszahlungen'] == '250,00'
    assert summen['Nachzahlung'] == '350,00'


def test_csv_liest_den_schnappschuss_nicht_die_heutigen_daten(app_ctx, auth_client):
    """R-DOC-02: aendert sich die Rechnung nach der Festsetzung, bleibt die
    CSV bei den Zahlen, die der Mieter bekommen hat."""
    from nebenkostenfix.models import db

    mieter, rechnung = _welt()
    report = _festsetzen(auth_client, mieter.id)
    rechnung.amount = Decimal('9999.00')
    db.session.commit()

    zeilen = _zeilen(auth_client.get(
        f'/api/billing/reports/{report.id}/positionen.csv'))
    assert zeilen[1][7] == '1200,00'
    assert zeilen[1][11] == '600,00'


def test_formel_im_anbieternamen_wird_entschaerft():
    """CSV-Injektion: ein Text, der mit = beginnt, waere in Excel eine
    Formel. Betraege bleiben Zahlen, auch negative."""
    from nebenkostenfix.csv_export import positionen_csv

    text = positionen_csv({
        'line_items': [{
            'category': '=HYPERLINK("http://x","klick")',
            'provider_name': '@SUMME(A1)', 'invoice_number': '+49',
            'period': '-', 'tenant_cost': Decimal('-12.50'),
            'billing_type': 'qm', 'description': 'ok',
        }],
        'total_amount': '-12.50', 'prepaid_amount': '0.00', 'balance': '-12.50',
    })
    zeilen = list(csv.reader(io.StringIO(text), delimiter=';'))
    position = zeilen[1]
    assert position[2].startswith("'=")
    assert position[3].startswith("'@")
    assert position[4] == "'+49"
    assert position[11] == '-12,50'
    assert zeilen[-1][2] == 'Guthaben'


def test_unbekannte_abrechnung_404(app_ctx, auth_client):
    assert auth_client.get('/api/billing/reports/999/positionen.csv').status_code == 404


def test_csv_braucht_anmeldung(app_ctx, anon_client):
    assert anon_client.get('/api/billing/reports/1/positionen.csv').status_code == 401


def test_die_detailansicht_bietet_csv_und_belege_an():
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text(
        encoding='utf-8')
    assert '/api/billing/reports/${id}/positionen.csv' in quelle
    assert '/api/billing/reports/${id}/belege' in quelle
