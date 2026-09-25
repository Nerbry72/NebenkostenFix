"""NK-153: Loeschung gegen Aufbewahrungsfristen (E-11 → D-89).

Festgesetzte Abrechnungen und Zahlungen sind Buchungsbelege des Vermieters
(§ 147 AO, § 257 HGB). Die DSGVO-Loeschung sperrt sie bis Fristende statt sie
zu vernichten, blendet das Mietverhaeltnis ueberall aus und loescht es nach
Ablauf beim Start.
"""

from datetime import date
from pathlib import Path

import pytest

import mieter_daten

PDF = b'%PDF-1.4\n%%EOF\n'


def _datei(relativ):
    from app import nas_handler
    voll = Path(nas_handler.nas_mount_path) / relativ
    voll.parent.mkdir(parents=True, exist_ok=True)
    voll.write_bytes(PDF)
    return relativ


@pytest.fixture
def mieter(app_ctx):
    from billing_factories import apt, category, house, profile, tenant
    from models import Haushaltsgroesse, Payment, TenantBillingReport, db
    haus = house('Aufbewahrungshaus')
    wohnung = apt(haus, 'EG', 50.0)
    m = tenant(wohnung, 'Anna Mieterin', move_in=date(2022, 1, 1))
    m.move_out_date = date(2024, 12, 31)
    m.contract_path = _datei('2022/' + 'a' * 32 + '.pdf')
    profile(m, category('Grundsteuer'), 'qm')
    db.session.add(Haushaltsgroesse(tenant_id=m.id, gueltig_ab=date(2022, 1, 1),
                                    personenanzahl=2))
    db.session.add(Payment(tenant_id=m.id, amount=100, payment_date=date(2024, 3, 1),
                           type='Nebenkostenvorauszahlung'))
    db.session.add(TenantBillingReport(
        tenant_id=m.id, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
        created_at=date(2025, 5, 1), frist_ende=date(2025, 12, 31),
        document_path=_datei('2025/' + 'b' * 32 + '.pdf')))
    db.session.commit()
    return m


def test_frist_zehn_jahre_nach_dem_letzten_jahr(mieter):
    # letzte Abrechnung 2025 -> Frist bis 31.12.2035
    assert mieter_daten.aufbewahrung_bis(mieter) == date(2035, 12, 31)


def test_ohne_abrechnung_und_zahlung_keine_frist(app_ctx):
    from billing_factories import apt, house, tenant
    m = tenant(apt(house('Leer'), 'EG', 40.0), 'Neu')
    assert mieter_daten.aufbewahrung_bis(m) is None


def test_loeschung_sperrt_statt_zu_loeschen(mieter, auth_client):
    from app import nas_handler
    from models import (Haushaltsgroesse, Payment, Tenant, TenantBillingReport,
                        TenantCostProfile, db)
    vertrag = mieter.contract_path
    antwort = auth_client.delete(f'/api/tenants/{mieter.id}')
    assert antwort.status_code == 200
    bericht = antwort.get_json()
    assert bericht['gesperrt_bis'] == '2035-12-31'
    assert '31.12.2035' in bericht['message']
    assert '§ 147 AO' in bericht['message']
    # sofort weg: Mietvertrag (Datei und Verweis), Kostenprofile
    assert vertrag in bericht['geloeschte_dateien']
    assert not (Path(nas_handler.nas_mount_path) / vertrag).exists()
    zeile = db.session.get(Tenant, mieter.id)
    assert zeile is not None and zeile.contract_path is None
    assert TenantCostProfile.query.count() == 0
    # bleibt: Abrechnung samt PDF, Zahlungen, Haushaltsgroessen
    assert TenantBillingReport.query.count() == 1
    assert (Path(nas_handler.nas_mount_path) /
            TenantBillingReport.query.one().document_path).exists()
    assert Payment.query.count() == 1
    assert Haushaltsgroesse.query.count() == 1


def test_gesperrte_sind_ueberall_ausgeblendet(mieter, auth_client):
    auth_client.delete(f'/api/tenants/{mieter.id}')
    assert auth_client.get('/api/tenants').get_json() == []
    assert auth_client.get('/api/billing/reports').get_json() == []
    assert auth_client.get('/api/payments').get_json() == []
    vorschlaege = auth_client.get('/api/billing/suggestions').get_json()
    assert all(v.get('tenant_id') != mieter.id for v in vorschlaege)
    gesperrt = auth_client.get('/api/tenants?gesperrte=1').get_json()
    assert [t['id'] for t in gesperrt] == [mieter.id]
    assert gesperrt[0]['gesperrt_bis'] == '2035-12-31'


def test_auskunft_bleibt_moeglich(mieter, auth_client):
    auth_client.delete(f'/api/tenants/{mieter.id}')
    antwort = auth_client.get(f'/api/tenants/{mieter.id}/export')
    assert antwort.status_code == 200


def test_nach_fristablauf_loescht_der_start_alles(mieter, auth_client):
    from app import nas_handler
    from models import Payment, Tenant, TenantBillingReport, db
    auth_client.delete(f'/api/tenants/{mieter.id}')
    pdf = TenantBillingReport.query.one().document_path
    assert mieter_daten.abgelaufene_loeschen(date(2035, 12, 31)) == 0
    assert mieter_daten.abgelaufene_loeschen(date(2036, 1, 1)) == 1
    assert db.session.get(Tenant, mieter.id) is None
    assert TenantBillingReport.query.count() == 0
    assert Payment.query.count() == 0
    assert not (Path(nas_handler.nas_mount_path) / pdf).exists()


def test_die_oberflaeche_nennt_frist_und_pruefung():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'static' / 'app.js').read_text(encoding='utf-8')
    html = (root / 'static' / 'index.html').read_text(encoding='utf-8')
    assert '§ 147 AO' in js and 'fachlich prüfen' in js
    assert 'id="gesperrte-mieter"' in html
    assert '/api/tenants?gesperrte=1' in js
