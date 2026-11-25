"""Zählerstände: ein NT-Stand am Eintarifzähler geht über das Formular durch.

Der Tabellenimport weist ``Stand Niedertarif`` an einem Zähler ohne
Zweitarif ab („der Zähler hat nur einen Tarif“). ``POST /api/readings``
prüft das nicht: der Stand wird mit ``value_nt`` gespeichert. Der
Rechenkern rechnet ``gesamt = value + value_nt`` und zählt den NT-Wert als
Verbrauch mit -- aus 100 → 200 m³ (100 m³) werden 100 → 200 + 50 = 150 m³.
Alle Werte sind erfunden.

Die Regel gilt jetzt auch im Formular und bei der Berichtigung, hart (400)
und nicht als Rückfrage (409). Das Leeren eines schon gespeicherten
NT-Stands und das unveränderte Mitschicken eines Altwerts bleiben möglich.
"""

from __future__ import annotations

import io
import os
from datetime import date

import pytest

from nebenkostenfix.abrechnungsdaten import lade_zaehler
from nebenkostenfix.models import MeterReading, db
from nebenkostenfix.rechenkern import verbrauch_detail, verbrauch_in
from tests import billing_factories as f

FOTO = b'\xff\xd8\xff\xe0fiktives-zaehlerfoto'


def test_nt_stand_am_eintarifzaehler_wird_abgewiesen(auth_client, app_ctx):
    haus = f.house('Nachthaus Eintarif')
    wohnung = f.apt(haus, 'EG', 55)
    z = f.meter(haus, f.category('Wasser'), 'KW-EIN-1', is_main=False, apartment=wohnung)
    assert not z.has_dual_tariff
    f.reading(z, date(2024, 1, 1), 100.0)

    antwort = auth_client.post('/api/readings', data={
        'meter_id': str(z.id), 'reading_date': '2024-12-31',
        'value': '200', 'value_nt': '50'})

    verbrauch = verbrauch_detail(lade_zaehler(z.id), date(2024, 1, 1),
                                 date(2024, 12, 31))['consumption']
    assert antwort.status_code == 400, (
        f'Status {antwort.status_code}: NT-Stand am Eintarifzähler gespeichert, '
        f'Verbrauch {verbrauch} statt 100 m³ '
        f'({MeterReading.query.filter_by(meter_id=z.id).count()} Stände)')


# --- Testhaus Nachtweg: ein Eintarif- und ein Zweitarifzähler -----------------


@pytest.fixture
def nachtweg(auth_client, app_ctx):
    haus = f.house('Testhaus Nachtweg')
    w1 = f.apt(haus, 'W1', 45)
    eintarif = f.meter(haus, f.category('Wasser'), 'NZ-ET-01', is_main=False, apartment=w1)
    zweitarif = f.meter(haus, f.category('Strom'), 'NZ-ZT-01', is_main=False, apartment=w1)
    zweitarif.has_dual_tariff = True
    db.session.commit()
    anfang = f.reading(eintarif, date(2024, 1, 1), 100.0)
    f.reading(zweitarif, date(2024, 1, 1), 1000.0, 8000.0)
    return {'client': auth_client, 'et_id': eintarif.id, 'zt_id': zweitarif.id,
            'anfang_id': anfang.id}


def _staende(meter_id):
    return [(r.reading_date, r.value, r.value_nt) for r in
            MeterReading.query.filter_by(meter_id=meter_id)
            .order_by(MeterReading.reading_date).all()]


def _dateien_im_belegordner():
    import app as app_module
    wurzel = app_module.nas_handler.wurzel
    return {os.path.join(ordner, name)
            for ordner, _, namen in os.walk(wurzel) for name in namen}


def _verbrauch_2024(meter_id):
    """Von Stand zu Stand, 01.01. bis 31.12.: genau die Differenz der Stände."""
    db.session.expire_all()
    return verbrauch_in(lade_zaehler(meter_id), date(2024, 1, 1),
                        date(2024, 12, 31))['consumption']


def _nt_stand(nachtweg, **mehr):
    daten = {'meter_id': str(nachtweg['et_id']), 'reading_date': '2024-12-31',
             'value': '200', 'value_nt': '50'}
    daten.update(mehr)
    return nachtweg['client'].post('/api/readings', data=daten,
                                   content_type='multipart/form-data')


def test_absage_steht_am_feld_value_nt_mit_deutschem_text(nachtweg):
    antwort = _nt_stand(nachtweg)

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    rumpf = antwort.get_json()
    assert rumpf['feld'] == 'value_nt'
    assert 'nur einen Tarif' in rumpf['error']
    assert 'nachfrage' not in rumpf
    assert _staende(nachtweg['et_id']) == [(date(2024, 1, 1), 100.0, None)]


def test_trotzdem_hebt_die_absage_nicht_auf(nachtweg):
    antwort = _nt_stand(nachtweg, trotzdem='1')

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert antwort.get_json()['feld'] == 'value_nt'
    assert _staende(nachtweg['et_id']) == [(date(2024, 1, 1), 100.0, None)]


def test_absage_kommt_vor_der_rueckfrage(nachtweg):
    # 90 liegt unter dem vorigen Stand (100): ohne NT wäre das die Rückfrage 409.
    antwort = _nt_stand(nachtweg, value='90')

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    rumpf = antwort.get_json()
    assert rumpf['feld'] == 'value_nt'
    assert 'nachfrage' not in rumpf
    assert _staende(nachtweg['et_id']) == [(date(2024, 1, 1), 100.0, None)]


def test_abgewiesener_nt_stand_legt_kein_foto_ab(nachtweg):
    vorher = _dateien_im_belegordner()

    antwort = _nt_stand(nachtweg, file=(io.BytesIO(FOTO), 'stand.jpg'))

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert _dateien_im_belegordner() == vorher
    assert _staende(nachtweg['et_id']) == [(date(2024, 1, 1), 100.0, None)]


def test_nach_den_absagen_bleibt_der_verbrauch_bei_100(nachtweg):
    assert _nt_stand(nachtweg).status_code == 400
    assert _nt_stand(nachtweg, trotzdem='1').status_code == 400

    gueltig = nachtweg['client'].post('/api/readings', data={
        'meter_id': str(nachtweg['et_id']), 'reading_date': '2024-12-31', 'value': '200'})

    assert gueltig.status_code == 201, gueltig.get_data(as_text=True)
    assert _verbrauch_2024(nachtweg['et_id']) == pytest.approx(100.0)


def test_berichtigung_setzt_keinen_neuen_nt_stand(nachtweg):
    antwort = nachtweg['client'].put(f"/api/readings/{nachtweg['anfang_id']}",
                                     data={'value_nt': '30'})

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert antwort.get_json()['feld'] == 'value_nt'
    db.session.expire_all()
    stand = db.session.get(MeterReading, nachtweg['anfang_id'])
    assert (stand.reading_date, stand.value, stand.value_nt) == (date(2024, 1, 1), 100.0, None)


def test_berichtigung_mit_nt_stand_aendert_auch_den_rest_nicht(nachtweg):
    antwort = nachtweg['client'].put(f"/api/readings/{nachtweg['anfang_id']}", data={
        'value': '90', 'value_nt': '30', 'ablesungsart': 'zwischenablesung',
        'trotzdem': '1'})

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    db.session.expire_all()
    stand = db.session.get(MeterReading, nachtweg['anfang_id'])
    assert (stand.value, stand.value_nt, stand.ablesungsart) == (100.0, None, 'ablesung')


def test_alter_nt_stand_laesst_sich_leeren_und_unveraendert_mitschicken(nachtweg):
    # Ein Altstand aus der Zeit vor der Regel, direkt in der Datenbank.
    alt = MeterReading(meter_id=nachtweg['et_id'], reading_date=date(2024, 6, 30),
                       value=150.0, value_nt=40.0)
    db.session.add(alt)
    db.session.commit()
    alt_id = alt.id
    client = nachtweg['client']

    unveraendert = client.put(f'/api/readings/{alt_id}',
                              data={'value': '151', 'value_nt': '40'})
    assert unveraendert.status_code == 200, unveraendert.get_data(as_text=True)
    db.session.expire_all()
    stand = db.session.get(MeterReading, alt_id)
    assert (stand.value, stand.value_nt) == (151.0, 40.0)

    geleert = client.put(f'/api/readings/{alt_id}', data={'value_nt': ''})
    assert geleert.status_code == 200, geleert.get_data(as_text=True)
    db.session.expire_all()
    stand = db.session.get(MeterReading, alt_id)
    assert (stand.value, stand.value_nt) == (151.0, None)


def test_alter_nt_stand_laesst_sich_nicht_auf_einen_anderen_wert_setzen(nachtweg):
    alt = MeterReading(meter_id=nachtweg['et_id'], reading_date=date(2024, 6, 30),
                       value=150.0, value_nt=40.0)
    db.session.add(alt)
    db.session.commit()
    alt_id = alt.id

    antwort = nachtweg['client'].put(f'/api/readings/{alt_id}', data={'value_nt': '45'})

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(MeterReading, alt_id).value_nt == 40.0


# --- Gegenproben --------------------------------------------------------------


def test_zweitarifzaehler_nimmt_beide_zaehlwerke_an(nachtweg):
    antwort = nachtweg['client'].post('/api/readings', data={
        'meter_id': str(nachtweg['zt_id']), 'reading_date': '2024-12-31',
        'value': '1500', 'value_nt': '8600'})

    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _staende(nachtweg['zt_id'])[-1] == (date(2024, 12, 31), 1500.0, 8600.0)


def test_zweitarifzaehler_nt_stand_laesst_sich_berichtigen(nachtweg):
    stand = MeterReading.query.filter_by(meter_id=nachtweg['zt_id']).one()

    antwort = nachtweg['client'].put(f'/api/readings/{stand.id}', data={'value_nt': '8100'})

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(MeterReading, stand.id).value_nt == 8100.0


def test_eintarifzaehler_ohne_nt_und_rueckfrage_wie_bisher(nachtweg):
    client = nachtweg['client']

    ohne_nt = client.post('/api/readings', data={
        'meter_id': str(nachtweg['et_id']), 'reading_date': '2024-12-31', 'value': '200'})
    assert ohne_nt.status_code == 201, ohne_nt.get_data(as_text=True)

    leer = client.post('/api/readings', data={
        'meter_id': str(nachtweg['et_id']), 'reading_date': '2024-06-30',
        'value': '150', 'value_nt': ''})
    assert leer.status_code == 201, leer.get_data(as_text=True)

    rueckwaerts = client.post('/api/readings', data={
        'meter_id': str(nachtweg['et_id']), 'reading_date': '2025-01-31', 'value': '180'})
    assert rueckwaerts.status_code == 409, rueckwaerts.get_data(as_text=True)
    assert rueckwaerts.get_json()['nachfrage'] is True

    bestaetigt = client.post('/api/readings', data={
        'meter_id': str(nachtweg['et_id']), 'reading_date': '2025-01-31', 'value': '180',
        'trotzdem': '1'})
    assert bestaetigt.status_code == 201, bestaetigt.get_data(as_text=True)
    assert [s[2] for s in _staende(nachtweg['et_id'])] == [None, None, None, None]
