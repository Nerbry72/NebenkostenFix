"""NK-078: Auskunft und Loeschung fuer ein Mietverhaeltnis (DSGVO).

Der Kern der Karte: die Dateien. Ein geloeschter Mieter mit Mietvertrag im
Belegordner ist nicht geloescht, und eine Auskunft ohne die Abrechnungs-PDFs
waere die haelfte der Wahrheit. Getestet wird darum durch die HTTP-Schicht,
mit echten Dateien unter NAS_MOUNT_PATH.

Die bewusste Grenze ist D-82: Zaehler und Lesungen gehoeren zur Wohnung und
ueberleben die Loeschung -- sie tragen die Abrechnung der Nachmieter. Der
Test haelt genau diese Grenze fest.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ORDNER = 'dsgvo-probe'


@pytest.fixture(autouse=True)
def _sauberer_belegordner():
    """Nur die eigenen Spuren entfernen, sonst nichts."""
    yield
    wurzel = Path(_nas_wurzel()) / ORDNER
    if wurzel.exists():
        shutil.rmtree(wurzel)


def _nas_wurzel() -> str:
    from app import nas_handler

    return nas_handler.nas_mount_path


def _datei(relativ: str, inhalt: bytes = b'%PDF-1.4\nProbe\n%%EOF\n') -> Path:
    voll = Path(_nas_wurzel()) / relativ
    voll.parent.mkdir(parents=True, exist_ok=True)
    voll.write_bytes(inhalt)
    return voll


@pytest.fixture
def mietverhaeltnis(app_ctx):
    """Wohnung, Zähler mit Lesung, Mieter mit allem Drum und Dran.

    Die Dateien liegen bewusst unter NAS_MOUNT_PATH, wie ein echter Upload
    sie hinterliesse; die Pfade in der Datenbank sind relativ.
    """
    from models import (Apartment, Haushaltsgroesse, Meter, MeterReading,
                        Payment, Property, Tenant, TenantBillingReport,
                        TenantCostProfile, db)

    haus = Property(name='Haus DSGVO', is_standalone=False)
    db.session.add(haus)
    db.session.flush()
    wohnung = Apartment(property_id=haus.id, name='EG links', sqm=52.0)
    db.session.add(wohnung)
    db.session.flush()

    zaehler = Meter(
        category_id=1, property_id=haus.id, apartment_id=wohnung.id,
        is_main_meter=False, meter_number='HK-1', heizungsanlage_id=None)
    db.session.add(zaehler)
    db.session.flush()

    lesung = MeterReading(
        meter_id=zaehler.id, reading_date=date(2024, 12, 31),
        value=1234.0)
    db.session.add(lesung)
    db.session.flush()
    _datei(f'{ORDNER}/Haus DSGVO/EG links/Ablesung Dez 2024.jpg')
    lesung.document_path = f'{ORDNER}/Haus DSGVO/EG links/Ablesung Dez 2024.jpg'

    _datei(f'{ORDNER}/Haus DSGVO/EG links/Mietvertrag Anna.pdf')
    mieter = Tenant(
        apartment_id=wohnung.id, name='Anna Beispiel',
        move_in_date=date(2024, 1, 1),
        contract_path=f'{ORDNER}/Haus DSGVO/EG links/Mietvertrag Anna.pdf')
    db.session.add(mieter)
    db.session.flush()

    bericht = TenantBillingReport(
        tenant_id=mieter.id, start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31), frist_ende=date(2025, 12, 31))
    db.session.add(bericht)
    db.session.flush()
    _datei(f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024.pdf')
    _datei(f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024 detailliert.pdf')
    bericht.document_path = f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024.pdf'
    bericht.document_path_detailed = f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024 detailliert.pdf'

    db.session.add(TenantCostProfile(
        tenant_id=mieter.id, category_id=1, billing_type='qm'))
    db.session.add(Haushaltsgroesse(
        tenant_id=mieter.id, gueltig_ab=date(2024, 1, 1),
        personenanzahl=2))
    db.session.add(Payment(
        tenant_id=mieter.id, amount=Decimal('100.00'),
        payment_date=date(2024, 2, 1), type='Miete'))
    db.session.commit()
    return mieter


def _zip_lesen(antwort) -> dict:
    archiv = zipfile.ZipFile(io.BytesIO(antwort.data))
    auskunft = json.loads(archiv.read('mieter-auskunft.json').decode('utf-8'))
    return {'namen': archiv.namelist(), 'auskunft': auskunft, 'archiv': archiv}


# --- Auskunft (Art. 15) ------------------------------------------------------


def test_auskunft_enthaelt_zeilen_und_dateien(app_ctx, auth_client, mietverhaeltnis):
    res = auth_client.get(f"/api/tenants/{mietverhaeltnis.id}/export")
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.mimetype == 'application/zip'
    paket = _zip_lesen(res)

    auskunft = paket['auskunft']
    assert auskunft['mieter']['name'] == 'Anna Beispiel'
    assert len(auskunft['kostenprofile']) == 1
    assert len(auskunft['haushaltsgroessen']) == 1
    assert len(auskunft['zahlungen']) == 1
    assert auskunft['zahlungen'][0]['amount'] == '100.00'  # Geld als Text, kein Float
    assert len(auskunft['abrechnungsberichte']) == 1
    assert len(auskunft['ablesungen']) == 1

    namen = paket['namen']
    assert 'dateien/' + mietverhaeltnis.contract_path in namen
    assert 'dateien/' + auskunft['abrechnungsberichte'][0]['document_path'] in namen
    assert 'dateien/' + auskunft['abrechnungsberichte'][0]['document_path_detailed'] in namen
    # Der Lesenachweis gehoert zur Auskunft, auch wenn er bei der Loeschung
    # bleibt (D-82).
    assert 'dateien/' + auskunft['ablesungen'][0]['document_path'] in namen
    # Die Grenze steht in der Auskunft, nicht nur im Code.
    assert 'Nachmieter' in auskunft['hinweis']


def test_auskunft_schneidet_lesungen_auf_die_mietzeit(app_ctx, auth_client,
                                                     mietverhaeltnis):
    """F-77 (NK-149): Vormieter, Mieter und Nachmieter an derselben Wohnung.
    Die Auskunft an den Mieter enthaelt nur Ablesungen aus seiner Mietzeit,
    die Raender (Einzug, Auszug) eingeschlossen -- keine Verbrauchsdaten und
    keine Ablesefotos der anderen beiden."""
    from models import MeterReading, Tenant, db

    mieter = mietverhaeltnis
    zaehler_id = mieter.apartment.meters[0].id
    # Anna zog am 01.01.2024 ein; jetzt endet ihre Mietzeit am 30.06.2025.
    mieter.move_out_date = date(2025, 6, 30)
    db.session.add(Tenant(apartment_id=mieter.apartment_id, name='Vormieter',
                          move_in_date=date(2022, 1, 1),
                          move_out_date=date(2023, 12, 31)))
    db.session.add(Tenant(apartment_id=mieter.apartment_id, name='Nachmieter',
                          move_in_date=date(2025, 7, 1)))
    _datei(f'{ORDNER}/vormieter-foto.jpg')
    _datei(f'{ORDNER}/nachmieter-foto.jpg')
    lesungen = {
        date(2023, 6, 30): f'{ORDNER}/vormieter-foto.jpg',   # Vormieter
        date(2023, 12, 31): None,                           # Vormieter-Auszug
        date(2024, 1, 1): None,                             # Einzug (Rand)
        date(2025, 6, 30): None,                            # Auszug (Rand)
        date(2025, 7, 1): None,                             # Nachmieter-Einzug
        date(2025, 12, 31): f'{ORDNER}/nachmieter-foto.jpg',  # Nachmieter
    }
    for tag, foto in lesungen.items():
        db.session.add(MeterReading(meter_id=zaehler_id, reading_date=tag,
                                    value=1000.0 + tag.toordinal() % 100,
                                    document_path=foto))
    db.session.commit()

    paket = _zip_lesen(auth_client.get(f"/api/tenants/{mieter.id}/export"))
    tage = [l['reading_date'] for l in paket['auskunft']['ablesungen']]
    assert tage == ['2024-01-01', '2024-12-31', '2025-06-30']
    namen = paket['namen']
    assert not any('vormieter-foto' in n for n in namen)
    assert not any('nachmieter-foto' in n for n in namen)
    assert 'Mietzeit' in paket['auskunft']['hinweis']

    # Der Nachmieter (ohne Auszug) bekommt seine Zeit bis heute, nichts davor.
    nachmieter = Tenant.query.filter_by(name='Nachmieter').one()
    paket = _zip_lesen(auth_client.get(f"/api/tenants/{nachmieter.id}/export"))
    tage = [l['reading_date'] for l in paket['auskunft']['ablesungen']]
    assert tage == ['2025-07-01', '2025-12-31']


def test_auskunft_meldet_fehlende_datei(app_ctx, auth_client, mietverhaeltnis):
    """Ein Verweis ohne Datei wird benannt, nicht weggelassen."""
    (Path(_nas_wurzel()) / mietverhaeltnis.contract_path).unlink()
    res = auth_client.get(f"/api/tenants/{mietverhaeltnis.id}/export")
    paket = _zip_lesen(res)
    vertrag = [d for d in paket['auskunft']['dateien'] if d['art'] == 'mietvertrag']
    assert vertrag[0].get('fehlt') is True


def test_auskunft_unbekannter_mieter_404(app_ctx, auth_client):
    assert auth_client.get('/api/tenants/9999/export').status_code == 404


def test_auskunft_braucht_anmeldung(app_ctx, anon_client, mietverhaeltnis):
    assert anon_client.get(
        f"/api/tenants/{mietverhaeltnis.id}/export").status_code == 401


# --- Loeschung (Art. 17) -----------------------------------------------------


def _frist_abgelaufen(mieter):
    """NK-153: Abrechnung und Zahlung aus 2014 -- die zehnjaehrige
    Aufbewahrung endete 2024, die Loeschung nimmt dann alles (wie NK-078).
    Den Fall mit laufender Frist prueft tests/test_aufbewahrung.py."""
    from models import db
    for bericht in mieter.billing_reports:
        bericht.created_at = date(2014, 1, 15)
    for zahlung in mieter.payments:
        zahlung.payment_date = date(2014, 2, 1)
    db.session.commit()


def test_loeschung_nimmt_zeilen_und_dateien_mit(app_ctx, auth_client, mietverhaeltnis):
    from models import (Haushaltsgroesse, Payment, Tenant, TenantBillingReport,
                        TenantCostProfile, db)

    _frist_abgelaufen(mietverhaeltnis)
    res = auth_client.delete(f"/api/tenants/{mietverhaeltnis.id}")
    assert res.status_code == 200, res.get_data(as_text=True)
    bericht = res.get_json()

    weg = bericht['geloeschte_dateien']
    assert mietverhaeltnis.contract_path in weg
    assert f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024.pdf' in weg
    assert f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024 detailliert.pdf' in weg
    for pfad in weg:
        assert not (Path(_nas_wurzel()) / pfad).is_file()

    assert db.session.get(Tenant, mietverhaeltnis.id) is None
    assert TenantCostProfile.query.count() == 0
    assert Haushaltsgroesse.query.count() == 0
    assert Payment.query.count() == 0
    assert TenantBillingReport.query.count() == 0


def test_loeschung_laesst_lesungen_stehen(app_ctx, auth_client, mietverhaeltnis):
    """D-82: die Messhistorie gehoert zur Wohnung, nicht zur Person."""
    from models import MeterReading, db

    res = auth_client.delete(f"/api/tenants/{mietverhaeltnis.id}")
    assert res.status_code == 200

    lesung = db.session.get(MeterReading, 1)
    assert lesung is not None
    nachweis = Path(_nas_wurzel()) / lesung.document_path
    assert nachweis.is_file()
    # und sie wird auch nicht als geloescht gemeldet
    assert lesung.document_path not in res.get_json()['geloeschte_dateien']


def test_loeschung_meldet_fehlende_datei_ohne_abbruch(app_ctx, auth_client,
                                                      mietverhaeltnis):
    _frist_abgelaufen(mietverhaeltnis)
    (Path(_nas_wurzel()) / mietverhaeltnis.contract_path).unlink()
    res = auth_client.delete(f"/api/tenants/{mietverhaeltnis.id}")
    assert res.status_code == 200
    bericht = res.get_json()
    assert mietverhaeltnis.contract_path in bericht['fehlende_dateien']
    assert 'nicht mehr vorhanden' in bericht['hinweis']
    # Der Rest ist trotzdem weg: die Abrechnungen wurden geloescht.
    assert f'{ORDNER}/Haus DSGVO/EG links/Abrechnung Anna 2024.pdf' in bericht['geloeschte_dateien']


def test_loeschung_braucht_anmeldung(app_ctx, anon_client, mietverhaeltnis):
    assert anon_client.delete(f"/api/tenants/{mietverhaeltnis.id}").status_code == 401
