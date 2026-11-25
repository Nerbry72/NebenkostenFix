"""Zähler gehören zu Wohnung und Heizungsanlage derselben Immobilie.

Befund: ``POST /api/meters`` las ``property_id`` und ``apartment_id`` nur als
Ganzzahl. Ein Zähler ließ sich so einer Wohnung aus einem anderen Haus
zuordnen, oder einer Wohnung, die es gar nicht gibt -- SQLite setzt den
Fremdschlüssel ohne PRAGMA nicht durch. ``PUT /api/meters/<id>`` prüfte die
Heizungsanlage nur, wenn zugleich ``einheit`` mitkam; ein PUT allein mit
``heizungsanlage_id`` hängte den Zähler ungeprüft an die Anlage eines fremden
Hauses. Und eine mitgeschickte ``apartment_id`` überging der PUT still mit 200.

Alle Daten sind erfunden.
"""

from __future__ import annotations

import pytest

from nebenkostenfix.models import Meter, db
from tests import billing_factories as f


@pytest.fixture
def zwei_haeuser(app_ctx):
    """Vorderhaus mit Wohnung EG, Hinterhaus mit Wohnung OG."""
    vorne = f.house('Vorderhaus')
    hinten = f.house('Hinterhaus')
    return {
        'vorne': vorne, 'hinten': hinten,
        'eg': f.apt(vorne, 'EG', 50), 'og': f.apt(hinten, 'OG', 60),
        'wasser': f.category('Wasser'),
    }


def _anlage(client, haus):
    antwort = client.post(
        f'/api/properties/{haus.id}/heizungsanlagen',
        json={'name': f'Kessel {haus.name}', 'versorgt': 'heizung',
              'verbrauchsanteil_prozent': 50, 'sonderfall_70': False})
    assert antwort.status_code == 201
    return antwort.get_json()['id']


def _neu(client, d, **mehr):
    daten = {'category_id': d['wasser'].id, 'property_id': d['vorne'].id,
             'apartment_id': d['eg'].id, 'is_main_meter': False,
             'meter_number': 'WZ-100', **mehr}
    return client.post('/api/meters', json=daten)


def _fehlerfeld(antwort):
    assert antwort.status_code == 400, antwort.get_json()
    return antwort.get_json()['feld']


# --- Anlegen ------------------------------------------------------------------------

def test_anlegen_mit_wohnung_aus_anderem_haus_wird_abgelehnt(auth_client, zwei_haeuser):
    d = zwei_haeuser
    antwort = _neu(auth_client, d, apartment_id=d['og'].id)
    assert _fehlerfeld(antwort) == 'apartment_id'
    assert 'Immobilie' in antwort.get_json()['error']
    db.session.rollback()
    assert Meter.query.count() == 0


def test_anlegen_mit_unbekannter_wohnung_wird_abgelehnt(auth_client, zwei_haeuser):
    antwort = _neu(auth_client, zwei_haeuser, apartment_id=99999)
    assert _fehlerfeld(antwort) == 'apartment_id'
    db.session.rollback()
    assert Meter.query.count() == 0


def test_anlegen_mit_unbekannter_immobilie_wird_abgelehnt(auth_client, zwei_haeuser):
    antwort = _neu(auth_client, zwei_haeuser, property_id=99999, apartment_id=None,
                   is_main_meter=True)
    assert _fehlerfeld(antwort) == 'property_id'
    db.session.rollback()
    assert Meter.query.count() == 0


def test_anlegen_mit_wohnung_im_selben_haus_klappt(auth_client, zwei_haeuser):
    d = zwei_haeuser
    antwort = _neu(auth_client, d)
    assert antwort.status_code == 201
    zaehler = db.session.get(Meter, antwort.get_json()['id'])
    assert (zaehler.property_id, zaehler.apartment_id) == (d['vorne'].id, d['eg'].id)


def test_hauszaehler_ohne_wohnung_bleibt_erlaubt(auth_client, zwei_haeuser):
    antwort = _neu(auth_client, zwei_haeuser, apartment_id=None, is_main_meter=True,
                   meter_number='HZ-1')
    assert antwort.status_code == 201
    assert db.session.get(Meter, antwort.get_json()['id']).apartment_id is None


# --- Bearbeiten ---------------------------------------------------------------------

@pytest.fixture
def zaehler(zwei_haeuser):
    d = zwei_haeuser
    return f.meter(d['vorne'], d['wasser'], 'WZ-1', is_main=False, apartment=d['eg'])


def test_bearbeiten_mit_wohnung_aus_anderem_haus_wird_abgelehnt(auth_client, zwei_haeuser,
                                                                 zaehler):
    antwort = auth_client.put(f'/api/meters/{zaehler.id}',
                              json={'apartment_id': zwei_haeuser['og'].id})
    assert _fehlerfeld(antwort) == 'apartment_id'
    db.session.rollback()
    assert db.session.get(Meter, zaehler.id).apartment_id == zwei_haeuser['eg'].id


def test_bearbeiten_mit_unbekannter_wohnung_wird_abgelehnt(auth_client, zaehler):
    antwort = auth_client.put(f'/api/meters/{zaehler.id}', json={'apartment_id': 99999})
    assert _fehlerfeld(antwort) == 'apartment_id'


def test_bearbeiten_mit_anderer_immobilie_wird_abgelehnt(auth_client, zwei_haeuser, zaehler):
    antwort = auth_client.put(f'/api/meters/{zaehler.id}',
                              json={'property_id': zwei_haeuser['hinten'].id,
                                    'apartment_id': zwei_haeuser['og'].id})
    assert _fehlerfeld(antwort) == 'property_id'
    db.session.rollback()
    assert db.session.get(Meter, zaehler.id).property_id == zwei_haeuser['vorne'].id


def test_bearbeiten_verschiebt_den_zaehler_nicht_still(auth_client, zwei_haeuser, zaehler):
    """Immobilie und Wohnung bleiben (NK-258); statt 200 ohne Wirkung ein 400."""
    zweite = f.apt(zwei_haeuser['vorne'], '1. OG', 40)
    antwort = auth_client.put(f'/api/meters/{zaehler.id}', json={'apartment_id': zweite.id})
    assert _fehlerfeld(antwort) == 'apartment_id'
    db.session.rollback()
    assert db.session.get(Meter, zaehler.id).apartment_id == zwei_haeuser['eg'].id


def test_bearbeiten_mit_unveraenderter_zuordnung_klappt(auth_client, zwei_haeuser, zaehler):
    antwort = auth_client.put(f'/api/meters/{zaehler.id}',
                              json={'property_id': zwei_haeuser['vorne'].id,
                                    'apartment_id': zwei_haeuser['eg'].id,
                                    'meter_number': 'WZ-1a'})
    assert antwort.status_code == 200
    assert db.session.get(Meter, zaehler.id).meter_number == 'WZ-1a'


def test_altzaehler_an_fremder_wohnung_laesst_sich_mit_denselben_werten_bearbeiten(
        auth_client, zwei_haeuser):
    """Ein Bestandszähler, der durch den alten Fehler an einer Wohnung aus einem
    anderen Haus hängt, bekommt beim Zurückschicken derselben Zuordnung kein 400:
    geprüft wird nur, was sich ändert."""
    d = zwei_haeuser
    alt = f.meter(d['vorne'], d['wasser'], 'WZ-alt', is_main=False, apartment=d['og'])
    antwort = auth_client.put(f'/api/meters/{alt.id}',
                              json={'property_id': d['vorne'].id,
                                    'apartment_id': d['og'].id,
                                    'meter_number': 'WZ-alt-2'})
    assert antwort.status_code == 200, antwort.get_json()
    zaehler = db.session.get(Meter, alt.id)
    assert zaehler.meter_number == 'WZ-alt-2'
    assert (zaehler.property_id, zaehler.apartment_id) == (d['vorne'].id, d['og'].id)


def test_bearbeiten_nur_mit_fremder_heizungsanlage_wird_abgelehnt(auth_client, zwei_haeuser,
                                                                   zaehler):
    fremd = _anlage(auth_client, zwei_haeuser['hinten'])
    antwort = auth_client.put(f'/api/meters/{zaehler.id}',
                              json={'heizungsanlage_id': fremd})
    assert _fehlerfeld(antwort) == 'heizungsanlage_id'
    db.session.rollback()
    assert db.session.get(Meter, zaehler.id).heizungsanlage_id is None


def test_bearbeiten_mit_eigener_heizungsanlage_klappt(auth_client, zwei_haeuser, zaehler):
    eigen = _anlage(auth_client, zwei_haeuser['vorne'])
    antwort = auth_client.put(f'/api/meters/{zaehler.id}',
                              json={'heizungsanlage_id': eigen})
    assert antwort.status_code == 200
    assert db.session.get(Meter, zaehler.id).heizungsanlage_id == eigen
    los = auth_client.put(f'/api/meters/{zaehler.id}', json={'heizungsanlage_id': None})
    assert los.status_code == 200
    assert db.session.get(Meter, zaehler.id).heizungsanlage_id is None
