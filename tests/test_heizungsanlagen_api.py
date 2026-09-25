"""NK-125: die Heizungsanlage bekommt API und Oberflaeche.

Die Anlage ist seit NK-048 eine eigene Sache im Kern und in der Datenbank;
diese Karte zieht die Oberflaeche nach. Die Pruefregeln des § 7 Abs. 1
(Rahmen 50 bis 70, Sonderfall zwingend 70) und des § 9 (Weg nur an der
verbundenen Anlage, seine Mengen positiv) stehen im Fachmodul heizung.py —
die API holt sich die Pruefung von dort und erfindet keine zweite.

Die Meldungen sprechen den Vermieter an (Sie-Form, D-25).
"""

import json
from decimal import Decimal

import pytest

from models import (db, Heizungsanlage, Meter, CostInvoice, CostCategory)


@pytest.fixture
def kategorien(app_ctx):
    """Der Gesetzeskatalog des Seeds, per Name greifbar."""
    return {k.name: k for k in CostCategory.query.all()}


@pytest.fixture
def immobilie(app_ctx, auth_client):
    """Eine Immobilie, an der die Anlagen haengen."""
    antwort = auth_client.post('/api/properties', json={'name': 'Hinterhaus'})
    assert antwort.status_code == 201
    return antwort.get_json()['id']


def test_anlage_anlegen_und_lesen(app_ctx, auth_client, immobilie):
    antwort = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Zentralheizung', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 55, 'sonderfall_70': False})
    assert antwort.status_code == 201
    zeile = antwort.get_json()
    assert zeile['name'] == 'Zentralheizung'
    assert zeile['versorgt'] == 'heizung'
    assert zeile['verbrauchsanteil_prozent'] == 55
    assert zeile['warmwasser_weg'] is None

    liste = auth_client.get(
        f'/api/properties/{immobilie}/heizungsanlagen').get_json()
    assert [a['id'] for a in liste] == [zeile['id']]


def test_verbrauchsanteil_ausserhalb_des_rahmens(app_ctx, auth_client, immobilie):
    antwort = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Ofen', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 45, 'sonderfall_70': False})
    assert antwort.status_code == 400
    assert 'zwischen 50 und 70' in antwort.get_json()['error']


def test_sonderfall_verlangt_genau_70(app_ctx, auth_client, immobilie):
    antwort = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Gasheizung Altbau', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 60, 'sonderfall_70': True})
    assert antwort.status_code == 400
    assert '70 vom Hundert' in antwort.get_json()['error']

    # Mit 70 klappt es.
    gut = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Gasheizung Altbau', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 70, 'sonderfall_70': True})
    assert gut.status_code == 201


def test_verbundene_anlage_braucht_weg_und_mengen(app_ctx, auth_client, immobilie):
    # Ohne Weg geht es nicht.
    ohne = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'verbunden',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False})
    assert ohne.status_code == 400
    assert 'Weg' in ohne.get_json()['error']

    # Weg "zaehler" verlangt die gemessene Waermemenge.
    ohne_menge = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'verbunden',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False,
              'warmwasser_weg': 'zaehler', 'brennstoff_menge': 10000})
    assert ohne_menge.status_code == 400
    assert 'kWh' in ohne_menge.get_json()['error']

    # Mit Weg und Mengen klappt es; der Formelweg will Volumen und Temperatur.
    gut = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'verbunden',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False,
              'warmwasser_weg': 'formel', 'warmwasser_volumen_m3': 200,
              'warmwasser_temperatur_c': 55, 'brennstoff_menge': 10000})
    assert gut.status_code == 201
    assert gut.get_json()['warmwasser_volumen_m3'] == 200.0


def test_umbau_loescht_die_trennangaben(app_ctx, auth_client, immobilie):
    """Wird die Anlage zur reinen Heizung, wandert der §-9-Weg fort."""
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'verbunden',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False,
              'warmwasser_weg': 'zaehler', 'warmwasser_kwh': 8000,
              'brennstoff_menge': 40000}).get_json()
    umgebaut = auth_client.put(
        f"/api/heizungsanlagen/{anlage['id']}",
        json={'name': 'Kessel', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 55, 'sonderfall_70': False})
    assert umgebaut.status_code == 200
    zeile = umgebaut.get_json()
    assert zeile['warmwasser_weg'] is None
    assert zeile['warmwasser_kwh'] is None
    assert zeile['brennstoff_menge'] is None


def test_anlage_bearbeiten(app_ctx, auth_client, immobilie):
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Alt', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False}).get_json()
    geaendert = auth_client.put(
        f"/api/heizungsanlagen/{anlage['id']}",
        json={'name': 'Neu', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 65, 'sonderfall_70': False})
    assert geaendert.status_code == 200
    assert geaendert.get_json()['name'] == 'Neu'
    assert geaendert.get_json()['verbrauchsanteil_prozent'] == 65


def test_anlage_loeschen_mit_anhaengenden_rechnungen(
        app_ctx, auth_client, immobilie, kategorien):
    """Eine Anlage mit Rechnung loescht nicht einfach weg (D-46)."""
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False}).get_json()
    heizung = kategorien['Heizung']
    auth_client.post('/api/invoices', json={
        'category_id': heizung.id, 'property_id': immobilie,
        'amount': '1000.00', 'start_date': '2024-01-01',
        'end_date': '2024-12-31',
        'heizungsanlage_id': anlage['id'], 'heizkostenart': 'brennstoff'})
    ablehnung = auth_client.delete(f"/api/heizungsanlagen/{anlage['id']}")
    assert ablehnung.status_code == 400
    assert 'hängen' in ablehnung.get_json()['error']
    # Nach dem Loesen der Rechnung klappt das Loeschen.
    db.session.rollback()


def test_rechnung_mit_anlage_und_posten(app_ctx, auth_client, immobilie,
                                        kategorien):
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'verbunden',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False,
              'warmwasser_weg': 'zaehler', 'warmwasser_kwh': 8000,
              'brennstoff_menge': 40000}).get_json()
    heizung = kategorien['Heizung']
    ok = auth_client.post('/api/invoices', json={
        'category_id': heizung.id, 'property_id': immobilie,
        'amount': '1234.56', 'start_date': '2024-01-01',
        'end_date': '2024-12-31',
        'heizungsanlage_id': anlage['id'], 'heizkostenart': 'brennstoff',
        'co2_kosten': '412.60', 'co2_emission_kg': 5210.25})
    assert ok.status_code == 201
    zeilen = auth_client.get('/api/invoices').get_json()
    zeile = next(z for z in zeilen if z['heizungsanlage_id'])
    assert zeile['heizungsanlage_id'] == anlage['id']
    assert zeile['heizkostenart'] == 'brennstoff'
    # Der JSON-Anbieter gibt Dezimalzahlen als Gleitkommazahl aus.
    assert float(zeile['co2_kosten']) == pytest.approx(412.60)
    assert float(zeile['co2_emission_kg']) == pytest.approx(5210.25)


def test_rechnung_posten_ohne_anlage_abgelehnt(app_ctx, auth_client,
                                               immobilie, kategorien):
    heizung = kategorien['Heizung']
    abgelehnt = auth_client.post('/api/invoices', json={
        'category_id': heizung.id, 'property_id': immobilie,
        'amount': '100.00', 'start_date': '2024-01-01',
        'end_date': '2024-12-31', 'heizkostenart': 'brennstoff'})
    assert abgelehnt.status_code == 400
    assert 'beides' in abgelehnt.get_json()['error']
    db.session.rollback()


def test_rechnung_unbekannte_kostenart_abgelehnt(app_ctx, auth_client,
                                                 immobilie, kategorien):
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False}).get_json()
    heizung = kategorien['Heizung']
    abgelehnt = auth_client.post('/api/invoices', json={
        'category_id': heizung.id, 'property_id': immobilie,
        'amount': '100.00', 'start_date': '2024-01-01',
        'end_date': '2024-12-31',
        'heizungsanlage_id': anlage['id'], 'heizkostenart': 'geheim'})
    assert abgelehnt.status_code == 400
    assert 'Posten' in abgelehnt.get_json()['error']
    db.session.rollback()


def test_rechnung_co2_ohne_anlage_abgelehnt(app_ctx, auth_client, immobilie,
                                            kategorien):
    wasser = kategorien['Wasserversorgung']
    abgelehnt = auth_client.post('/api/invoices', json={
        'category_id': wasser.id, 'property_id': immobilie,
        'amount': '100.00', 'start_date': '2024-01-01',
        'end_date': '2024-12-31', 'co2_kosten': '50.00',
        'co2_emission_kg': 300})
    assert abgelehnt.status_code == 400
    assert 'CO2' in abgelehnt.get_json()['error']
    db.session.rollback()


def test_rechnung_co2_nur_eine_angabe_abgelehnt(app_ctx, auth_client,
                                                immobilie, kategorien):
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False}).get_json()
    heizung = kategorien['Heizung']
    abgelehnt = auth_client.post('/api/invoices', json={
        'category_id': heizung.id, 'property_id': immobilie,
        'amount': '100.00', 'start_date': '2024-01-01',
        'end_date': '2024-12-31', 'heizungsanlage_id': anlage['id'],
        'heizkostenart': 'brennstoff', 'co2_kosten': '50.00'})
    assert abgelehnt.status_code == 400
    assert 'zusammen' in abgelehnt.get_json()['error']
    db.session.rollback()


def test_zaehler_an_anderer_immobilie_abgelehnt(app_ctx, auth_client,
                                                immobilie, kategorien):
    """Ein Zaehler misst eine Anlage derselben Immobilie (D-45)."""
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False}).get_json()
    andere = auth_client.post('/api/properties', json={'name': 'Vorderhaus'})
    andere_id = andere.get_json()['id']
    abgelehnt = auth_client.post('/api/meters', json={
        'category_id': kategorien['Heizung'].id, 'property_id': andere_id,
        'is_main_meter': True, 'meter_number': 'W-1',
        'heizungsanlage_id': anlage['id']})
    assert abgelehnt.status_code == 400
    db.session.rollback()


def test_zaehler_an_anderer_immobilie_klappt(app_ctx, auth_client, immobilie,
                                             kategorien):
    anlage = auth_client.post(
        f'/api/properties/{immobilie}/heizungsanlagen',
        json={'name': 'Kessel', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False}).get_json()
    ok = auth_client.post('/api/meters', json={
        'category_id': kategorien['Heizung'].id, 'property_id': immobilie,
        'is_main_meter': True, 'meter_number': 'W-1',
        'heizungsanlage_id': anlage['id']})
    assert ok.status_code == 201
    zeilen = auth_client.get('/api/meters').get_json()
    assert zeilen[0]['heizungsanlage_id'] == anlage['id']
    assert zeilen[0]['heizungsanlage_name'] == 'Kessel'
