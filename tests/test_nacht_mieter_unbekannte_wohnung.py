"""Mieter und Verträge: ein Mieter für eine Wohnung, die es nicht gibt.

POST /api/tenants prüft apartment_id nur auf eine ganze Zahl; ob die Wohnung
existiert, fragt die Route nur, wenn ein Mietvertrag mitkommt. SQLite setzt den
Fremdschlüssel nicht durch, also wird der Mieter mit 201 gespeichert. Er hängt
sich an die nächste Wohnung, die diese Nummer bekommt, und seine Übersicht der
Vorauszahlungen stürzt mit 500 ab (``tenant.apartment.name`` auf None).
Dasselbe gilt für PUT mit apartment_id. Dasselbe Muster wurde bei Zahlungen
schon behoben (``Diesen Mieter gibt es nicht.``).

Erwartet: 400 am Feld apartment_id, nichts gespeichert bzw. nichts geändert.
Alle Werte sind erfunden.
"""

from __future__ import annotations

import io
import os
from datetime import date

from nebenkostenfix.models import Apartment, Tenant, db
from tests import billing_factories as f

FEHLER = 'Die angegebene Wohnung gibt es nicht.'
# Ein kleines, erfundenes PDF; die Ablage erkennt den Typ an den ersten Bytes.
VERTRAG_PDF = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n'


def test_neuer_mieter_fuer_unbekannte_wohnung_wird_abgewiesen(auth_client, app_ctx):
    haus = f.house('Testhaus Nacht')
    wohnung = f.apt(haus, 'EG links', 52)
    db.session.commit()
    unbekannt = wohnung.id + 1

    antwort = auth_client.post('/api/tenants', data={
        'apartment_id': str(unbekannt), 'name': 'Mieterin Test',
        'move_in_date': '2025-01-01'})

    assert antwort.status_code == 400, antwort.get_json()
    assert antwort.get_json().get('feld') == 'apartment_id'
    assert Tenant.query.filter_by(apartment_id=unbekannt).count() == 0


def test_verwaister_mieter_landet_in_der_naechsten_wohnung(auth_client, app_ctx):
    """Die Folge: die nächste neu angelegte Wohnung erbt den Mieter."""
    haus = f.house('Testhaus Nacht')
    wohnung = f.apt(haus, 'EG links', 52)
    db.session.commit()
    auth_client.post('/api/tenants', data={
        'apartment_id': str(wohnung.id + 1), 'name': 'Mieter Geist',
        'move_in_date': '2025-01-01'})

    neue = f.apt(haus, 'OG rechts', 47)
    db.session.commit()

    assert Tenant.query.filter_by(apartment_id=neue.id).count() == 0


def test_mieter_umhaengen_auf_unbekannte_wohnung_wird_abgewiesen(auth_client, app_ctx):
    haus = f.house('Testhaus Nacht')
    wohnung = f.apt(haus, 'EG links', 52)
    mieter = f.tenant(wohnung, 'Mieter Eins', date(2025, 1, 1))
    db.session.commit()
    unbekannt = wohnung.id + 1

    antwort = auth_client.put(f'/api/tenants/{mieter.id}', data={
        'apartment_id': str(unbekannt)})

    assert antwort.status_code == 400, antwort.get_json()
    db.session.expire_all()
    assert db.session.get(Tenant, mieter.id).apartment_id == wohnung.id


def test_vorauszahlungen_des_verwaisten_mieters_stuerzen_nicht_ab(auth_client, app_ctx):
    """Wird der Mieter trotzdem angenommen, darf seine Übersicht nicht mit 500 enden."""
    haus = f.house('Testhaus Nacht')
    wohnung = f.apt(haus, 'EG links', 52)
    db.session.commit()
    antwort = auth_client.post('/api/tenants', data={
        'apartment_id': str(wohnung.id + 1), 'name': 'Mieter Geist',
        'move_in_date': '2025-01-01'})
    if antwort.status_code != 201:
        return  # abgewiesen: dann gibt es keinen verwaisten Mieter
    assert Apartment.query.get(wohnung.id + 1) is None

    uebersicht = auth_client.get(f"/api/tenants/{antwort.get_json()['id']}/vorauszahlungen")

    assert uebersicht.status_code != 500


# --- Testdatenplan: Testhaus Nachtweg, W1 mit Mieter Eins ---

def _w1_mit_mieter_eins():
    haus = f.house('Testhaus Nachtweg')
    w1 = f.apt(haus, 'W1', 45)
    mieter = f.tenant(w1, 'Mieter Eins', date(2024, 1, 1))
    db.session.commit()
    return haus, w1, mieter


def _anlegen(client, apartment_id, **extra):
    daten = {'apartment_id': str(apartment_id), 'name': 'Mieter Geist',
             'move_in_date': '2024-03-01'}
    daten.update(extra)
    return client.post('/api/tenants', data=daten,
                       content_type='multipart/form-data')


def _belege(app_ctx):
    """Alle Dateien unter der Belegwurzel, als Menge relativer Pfade."""
    wurzel = app_ctx.ablage.wurzel
    gefunden = set()
    for ordner, _unter, dateien in os.walk(wurzel):
        for name in dateien:
            gefunden.add(os.path.relpath(os.path.join(ordner, name), wurzel))
    return gefunden


def test_anlegen_unbekannte_wohnung_400_mit_text_und_ohne_zeile(auth_client, app_ctx):
    _haus, w1, mieter = _w1_mit_mieter_eins()

    antwort = _anlegen(auth_client, w1.id + 1)

    assert antwort.status_code == 400, antwort.get_json()
    assert antwort.get_json() == {'error': FEHLER, 'feld': 'apartment_id'}
    db.session.expire_all()
    assert [(t.id, t.name) for t in Tenant.query.all()] == [(mieter.id, 'Mieter Eins')]


def test_neue_wohnung_mit_der_freien_nummer_erbt_keinen_mieter(auth_client, app_ctx):
    haus, w1, _mieter = _w1_mit_mieter_eins()
    unbekannt = w1.id + 1
    assert _anlegen(auth_client, unbekannt).status_code == 400

    w2 = f.apt(haus, 'W2', 60)
    db.session.commit()

    assert w2.id == unbekannt  # SQLite vergibt die freie Nummer neu
    assert Tenant.query.filter_by(apartment_id=w2.id).count() == 0
    assert Tenant.query.count() == 1


def test_umhaengen_auf_unbekannte_wohnung_aendert_nichts(auth_client, app_ctx):
    _haus, w1, mieter = _w1_mit_mieter_eins()

    antwort = auth_client.put(f'/api/tenants/{mieter.id}', data={
        'apartment_id': '9999', 'name': 'Neuer Name',
        'move_in_date': '2024-02-01', 'anschrift': 'Nachtweg 1\n12345 Musterstadt'})

    assert antwort.status_code == 400, antwort.get_json()
    assert antwort.get_json() == {'error': FEHLER, 'feld': 'apartment_id'}
    db.session.expire_all()
    gespeichert = db.session.get(Tenant, mieter.id)
    assert gespeichert.apartment_id == w1.id
    assert gespeichert.name == 'Mieter Eins'
    assert gespeichert.move_in_date == date(2024, 1, 1)
    assert gespeichert.anschrift is None


def test_vorauszahlungen_nach_abgewiesenem_umhaengen_200(auth_client, app_ctx):
    _haus, _w1, mieter = _w1_mit_mieter_eins()
    assert auth_client.put(f'/api/tenants/{mieter.id}', data={
        'apartment_id': '9999', 'name': 'Neuer Name'}).status_code == 400

    uebersicht = auth_client.get(f'/api/tenants/{mieter.id}/vorauszahlungen')

    assert uebersicht.status_code == 200, uebersicht.get_data(as_text=True)


def test_gegenprobe_anlegen_in_vorhandener_wohnung_201(auth_client, app_ctx):
    """Neben dem abgewiesenen Versuch legt W1 wie bisher genau einen Mieter an."""
    _haus, w1, mieter = _w1_mit_mieter_eins()
    assert _anlegen(auth_client, w1.id + 1).status_code == 400

    antwort = _anlegen(auth_client, w1.id, name='Mieterin Zwei')

    assert antwort.status_code == 201, antwort.get_json()
    neu = db.session.get(Tenant, antwort.get_json()['id'])
    assert (neu.apartment_id, neu.name, neu.move_in_date) == (
        w1.id, 'Mieterin Zwei', date(2024, 3, 1))
    assert Tenant.query.count() == 2
    assert mieter.id != neu.id


def test_gegenprobe_umhaengen_auf_vorhandene_wohnung_200(auth_client, app_ctx):
    haus, w1, mieter = _w1_mit_mieter_eins()
    w2 = f.apt(haus, 'W2', 60)
    db.session.commit()
    assert auth_client.put(f'/api/tenants/{mieter.id}', data={
        'apartment_id': '9999'}).status_code == 400

    antwort = auth_client.put(f'/api/tenants/{mieter.id}', data={
        'apartment_id': str(w2.id), 'name': 'Mieter Eins (umgezogen)'})

    assert antwort.status_code == 200, antwort.get_json()
    db.session.expire_all()
    gespeichert = db.session.get(Tenant, mieter.id)
    assert gespeichert.apartment_id == w2.id
    assert gespeichert.name == 'Mieter Eins (umgezogen)'
    assert w1.id != w2.id


def test_unbekannte_wohnung_mit_und_ohne_vertrag_legt_nichts_ab(auth_client, app_ctx):
    """Mit und ohne Mietvertrag: 400, kein Mieter, keine Datei im Belegordner."""
    _haus, w1, mieter = _w1_mit_mieter_eins()
    vorher = _belege(app_ctx)

    ohne = _anlegen(auth_client, w1.id + 1)
    mit = _anlegen(auth_client, w1.id + 1, contract_file=(
        io.BytesIO(VERTRAG_PDF), 'vertrag.pdf'))

    for antwort in (ohne, mit):
        assert antwort.status_code == 400, antwort.get_json()
        assert antwort.get_json() == {'error': FEHLER, 'feld': 'apartment_id'}
    db.session.expire_all()
    assert [t.id for t in Tenant.query.all()] == [mieter.id]
    assert _belege(app_ctx) == vorher


def test_gegenprobe_vertrag_in_vorhandener_wohnung_wird_abgelegt(auth_client, app_ctx):
    """Der vereinfachte Vertragszweig legt den Vertrag für W1 weiter ab."""
    _haus, w1, _mieter = _w1_mit_mieter_eins()
    assert _anlegen(auth_client, w1.id + 1).status_code == 400
    vorher = _belege(app_ctx)

    antwort = _anlegen(auth_client, w1.id, contract_file=(
        io.BytesIO(VERTRAG_PDF), 'vertrag.pdf'))

    assert antwort.status_code == 201, antwort.get_json()
    neu = db.session.get(Tenant, antwort.get_json()['id'])
    assert neu.contract_path
    assert _belege(app_ctx) - vorher == {os.path.normpath(neu.contract_path)}
