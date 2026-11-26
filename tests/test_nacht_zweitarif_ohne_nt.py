"""Nachtschicht: ein Zweitarifzähler nahm einen Stand ohne NT-Zählwerk an.

Der Zählerwechsel verlangt beim Zweitarifzähler beide Zählwerke
(``endstand_nt`` ist Pflicht, Test ``test_beim_zweitarifzaehler_gehoeren_
beide_zaehlwerke_dazu``). ``POST /api/readings`` dagegen speicherte einen Stand
mit leerem ``value_nt`` ohne Absage und ohne Rückfrage: ``_ablesung_pruefen``
überspringt das NT-Zählwerk, wenn es ``None`` ist. Der Kern liest den
fehlenden NT-Stand als 0 (``wert_nt or 0``) -- das NT-Register läuft damit
rechnerisch rückwärts, und der Jahresverbrauch schrumpft still um den ganzen
NT-Stand (R-NUM-06: HT und NT werden getrennt gemessen und bepreist).

Jetzt gilt die Regel des Wechsels auf jedem Eingabeweg als harte Absage
(400, nicht die Rückfrage 409): Erfassen, Bearbeiten und Tabellenimport.
Alle Daten sind erfunden.
"""

from __future__ import annotations

import io
from datetime import date

from nebenkostenfix.abrechnungsdaten import lade_zaehler
from nebenkostenfix.models import CostCategory, Meter, MeterReading, db
from nebenkostenfix.rechenkern import verbrauch_detail
from tests import billing_factories as f

HAUS = 'Testhaus Nachtweg'
KOPF = 'Immobilie;Zählernummer;Datum;Stand;Stand NT;Zwischenablesung'


def _zaehler(haus, wohnung, kategorie, nummer: str, zweitarif: bool) -> Meter:
    z = Meter(category_id=kategorie.id, property_id=haus.id, apartment_id=wohnung.id,
              is_main_meter=False, meter_number=nummer, has_dual_tariff=zweitarif)
    db.session.add(z)
    db.session.commit()
    return z


def _haus():
    """Testhaus Nachtweg, W1 mit 45 m²: ein Strom-Zweitarif- und ein Wasserzähler."""
    haus = f.house(HAUS)
    wohnung = f.apt(haus, 'W1', 45.0)
    strom = CostCategory.query.filter_by(betrkv_nr=11).first()
    wasser = CostCategory.query.filter_by(betrkv_nr=2).first()
    zweitarif = _zaehler(haus, wohnung, strom, 'NZ-ZT-01', True)
    einzeltarif = _zaehler(haus, wohnung, wasser, 'NZ-ET-01', False)
    f.reading(zweitarif, date(2024, 1, 1), 1000.0, value_nt=8000.0)
    f.reading(einzeltarif, date(2024, 1, 1), 100.0)
    return zweitarif, einzeltarif


def _zweitarifzaehler():
    return _haus()[0]


def _staende(zaehler_id: int) -> int:
    db.session.expire_all()
    return MeterReading.query.filter_by(meter_id=zaehler_id).count()


def test_stand_ohne_nt_wird_nicht_still_gespeichert(auth_client, app_ctx):
    z = _zweitarifzaehler()
    antwort = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-12-31', 'value': '1500'})
    gespeichert = MeterReading.query.filter_by(meter_id=z.id).count()
    # Erwartet: Absage (400) oder wenigstens die Rückfrage (409) -- nicht 201.
    assert antwort.status_code in (400, 409), (antwort.status_code, antwort.get_json())
    assert gespeichert == 1


def test_folge_im_kern_verbrauch_negativ(auth_client, app_ctx):
    """Die Absage hält den Kern sauber: ohne Stand kein Register, das rückwärts läuft.

    Früher wurde der Stand angenommen, und aus 500 HT wurden -7500 gesamt.
    Der Kern bleibt, wie er ist (``wert_nt or 0``); es kommt nur nichts mehr
    bei ihm an.
    """
    z = _zweitarifzaehler()
    antwort = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-12-31', 'value': '1500'})
    assert antwort.status_code == 400, antwort.get_json()
    detail = verbrauch_detail(lade_zaehler(z.id), date(2024, 1, 1), date(2024, 12, 30))
    assert detail['nt'] >= 0, f"NT-Verbrauch {detail['nt']:.1f} -- Register läuft rückwärts"
    assert detail['consumption'] >= 0
    assert detail['status'] == 'no_data'  # nur der Stand vom 01.01. ist da


def test_absage_am_feld_value_nt_und_gegenprobe_mit_beiden_zaehlwerken(auth_client, app_ctx):
    z = _zweitarifzaehler()
    ohne = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-12-31', 'value': '1500'})
    assert ohne.status_code == 400, ohne.get_json()
    fehler = ohne.get_json()
    assert fehler['feld'] == 'value_nt'
    assert 'zwei Tarife' in fehler['error'] and 'NT-Stand' in fehler['error']
    assert _staende(z.id) == 1

    # Die Rückfrage (409) bleibt, wie sie war: NT unter dem vorigen Stand.
    rueckwaerts = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-12-31', 'value': '1500', 'value_nt': '7000'})
    assert rueckwaerts.status_code == 409 and rueckwaerts.get_json()['nachfrage'] is True
    assert _staende(z.id) == 1

    mit = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-12-31', 'value': '1500', 'value_nt': '8600'})
    assert mit.status_code == 201, mit.get_json()
    assert _staende(z.id) == 2
    detail = verbrauch_detail(lade_zaehler(z.id), date(2024, 1, 1), date(2024, 12, 30))
    assert round(detail['ht'], 3) == 500.0
    assert round(detail['nt'], 3) == 600.0


def test_absage_laesst_sich_nicht_wegbestaetigen(auth_client, app_ctx):
    z = _zweitarifzaehler()
    antwort = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-12-31', 'value': '1500', 'trotzdem': 'true'})
    assert antwort.status_code == 400, antwort.get_json()
    assert antwort.get_json()['feld'] == 'value_nt'
    assert 'nachfrage' not in antwort.get_json()
    assert _staende(z.id) == 1


def test_absage_kommt_vor_der_rueckfrage(auth_client, app_ctx):
    """Ein zweiter Stand am 01.01. wäre eine Rückfrage -- ohne NT ist es eine Absage."""
    z = _zweitarifzaehler()
    antwort = auth_client.post('/api/readings', data={
        'meter_id': z.id, 'reading_date': '2024-01-01', 'value': '1000'})
    assert antwort.status_code == 400, antwort.get_json()
    assert antwort.get_json()['feld'] == 'value_nt'
    assert _staende(z.id) == 1


def test_bearbeiten_darf_den_nt_stand_nicht_leeren(auth_client, app_ctx):
    z = _zweitarifzaehler()
    stand = MeterReading.query.filter_by(meter_id=z.id).one()

    leer = auth_client.put(f'/api/readings/{stand.id}', data={'value_nt': ''})
    assert leer.status_code == 400, leer.get_json()
    assert leer.get_json()['feld'] == 'value_nt'

    # Auch als JSON mit null, zusammen mit einer sonst gültigen Änderung.
    null = auth_client.put(f'/api/readings/{stand.id}', json={'value': 1001, 'value_nt': None})
    assert null.status_code == 400, null.get_json()

    db.session.expire_all()
    gespeichert = db.session.get(MeterReading, stand.id)
    assert gespeichert.value_nt == 8000.0
    assert gespeichert.value == 1000.0

    # Gegenprobe: wer den NT-Stand nicht anfasst oder einen neuen schickt, kommt durch.
    assert auth_client.put(f'/api/readings/{stand.id}', data={'value': '1001'}).status_code == 200
    assert auth_client.put(f'/api/readings/{stand.id}', data={'value_nt': '8001'}).status_code == 200
    db.session.expire_all()
    gespeichert = db.session.get(MeterReading, stand.id)
    assert (gespeichert.value, gespeichert.value_nt) == (1001.0, 8001.0)


def test_einzeltarifzaehler_braucht_weiter_keinen_nt_stand(auth_client, app_ctx):
    zweitarif, einzeltarif = _haus()
    abgewiesen = auth_client.post('/api/readings', data={
        'meter_id': zweitarif.id, 'reading_date': '2024-12-31', 'value': '1500'})
    assert abgewiesen.status_code == 400, abgewiesen.get_json()

    angenommen = auth_client.post('/api/readings', data={
        'meter_id': einzeltarif.id, 'reading_date': '2024-12-31', 'value': '160'})
    assert angenommen.status_code == 201, angenommen.get_json()
    assert _staende(einzeltarif.id) == 2
    neu = db.session.get(MeterReading, angenommen.get_json()['id'])
    assert neu.value_nt is None
    stand = auth_client.put(f'/api/readings/{neu.id}', data={'value': '161', 'value_nt': ''})
    assert stand.status_code == 200, stand.get_json()


# --- Tabellenimport -------------------------------------------------------------

def _csv(*zeilen: str) -> bytes:
    return ('﻿' + '\r\n'.join(zeilen) + '\r\n').encode('utf-8')


def _importieren(client, inhalt: bytes):
    gelesen = client.post('/api/import/zaehlerstaende/lesen',
                          data={'datei': (io.BytesIO(inhalt), 'staende.csv')},
                          content_type='multipart/form-data')
    assert gelesen.status_code == 200, gelesen.get_data(as_text=True)
    daten = gelesen.get_json()
    return client.post('/api/import/zaehlerstaende/uebernehmen', json={
        'kennung': daten['kennung'], 'zuordnung': daten['zuordnung']})


def test_import_meldet_die_zeile_ohne_nt_stand(auth_client, app_ctx):
    zweitarif, einzeltarif = _haus()
    antwort = _importieren(auth_client, _csv(KOPF, f'{HAUS};NZ-ZT-01;15.01.2025;1600;;nein'))
    bericht = antwort.get_json()
    assert antwort.status_code == 400, bericht
    assert [f['zeile'] for f in bericht['fehler']] == [2]
    assert bericht['fehler'][0]['meldung'].startswith('Stand Niedertarif')
    assert 'zwei Tarife' in bericht['fehler'][0]['meldung']
    assert _staende(zweitarif.id) == 1

    # Gegenprobe: mit NT-Stand geht dieselbe Zeile durch, der Einzeltarif ohne NT auch.
    ok = _importieren(auth_client, _csv(KOPF, f'{HAUS};NZ-ZT-01;15.01.2025;1600;8700;nein',
                                        f'{HAUS};NZ-ET-01;15.01.2025;170;;nein'))
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()['angelegt']['zaehlerstaende'] == 2
    db.session.expire_all()
    neu = MeterReading.query.filter_by(meter_id=zweitarif.id,
                                       reading_date=date(2025, 1, 15)).one()
    assert (neu.value, neu.value_nt) == (1600.0, 8700.0)
    assert MeterReading.query.filter_by(meter_id=einzeltarif.id,
                                        reading_date=date(2025, 1, 15)).one().value_nt is None
