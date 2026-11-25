"""Auszug und Einzug eines Mieters (Befunde vom 17.11.).

Zwei Befunde aus dem Bereich Mieter:

1. „Auszug vor Einzug“: ``POST /api/tenants`` und ``PUT /api/tenants/<id>``
   nahmen ein Auszugsdatum vor dem Einzugsdatum an, auch auf dem Umweg, nur
   den Einzug hinter einen schon gespeicherten Auszug zu schieben. Erwartet
   ist eine Absage am Feld (400), ein deutscher Text und kein geänderter
   Stand. Auszug am Tag des Einzugs bleibt erlaubt. Der Tabellenimport
   prüft dasselbe schon (``tabellenimport._zeile_mieter``).

2. „Auszugsdatum nicht entfernbar“: Die API räumt das Datum aus, wenn das
   Feld leer kommt (``test_validation``). Die Oberfläche schickte das Feld
   aber nur, wenn etwas darin stand -- ein geleertes Auszugsdatum kam nie
   beim Server an. Geprüft im Verhalten von ``saveTenant`` per Node-Probe.

Alle Daten erfunden.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
APP_JS = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')


# --- API ----------------------------------------------------------------------


@pytest.fixture
def wohnung_id(app_ctx):
    from billing_factories import apt, house
    from nebenkostenfix.models import db

    wohnung = apt(house(), 'EG links', 50.0)
    db.session.commit()
    return wohnung.id


def _anlegen(client, wohnung_id, **felder):
    daten = {'apartment_id': wohnung_id, 'name': 'Mieterin Muster',
             'move_in_date': '2025-01-01'}
    daten.update(felder)
    return client.post('/api/tenants', json=daten)


def _gelesen(client, mieter_id):
    """Der Stand, wie die App ihn ausliefert (mit Autoflush der Sitzung)."""
    return next(t for t in client.get('/api/tenants').get_json() if t['id'] == mieter_id)


def test_anlegen_mit_auszug_vor_einzug_wird_abgewiesen(auth_client, wohnung_id):
    from nebenkostenfix.models import Tenant

    antwort = _anlegen(auth_client, wohnung_id,
                       move_in_date='2025-03-01', move_out_date='2025-02-28')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    rumpf = antwort.get_json()
    assert rumpf['feld'] == 'move_out_date'
    assert 'vor dem Einzug' in rumpf['error']
    assert '28.02.2025' in rumpf['error'] and '01.03.2025' in rumpf['error']
    assert Tenant.query.count() == 0


def test_anlegen_mit_auszug_am_einzugstag_geht(auth_client, wohnung_id):
    antwort = _anlegen(auth_client, wohnung_id,
                       move_in_date='2025-03-01', move_out_date='2025-03-01')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    stand = _gelesen(auth_client, antwort.get_json()['id'])
    assert stand['move_out_date'] == '2025-03-01'


def test_aendern_auf_auszug_vor_einzug_wird_abgewiesen(auth_client, wohnung_id):
    mieter_id = _anlegen(auth_client, wohnung_id, move_in_date='2025-03-01').get_json()['id']

    antwort = auth_client.put(f'/api/tenants/{mieter_id}', json={
        'name': 'Neuer Name', 'move_out_date': '2025-01-31'})
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert antwort.get_json()['feld'] == 'move_out_date'
    assert 'vor dem Einzug' in antwort.get_json()['error']
    stand = _gelesen(auth_client, mieter_id)
    # Auch der Name aus derselben Anfrage bleibt ungeschrieben.
    assert stand['move_out_date'] is None
    assert stand['name'] == 'Mieterin Muster'


def test_einzug_hinter_den_auszug_schieben_wird_abgewiesen(auth_client, wohnung_id):
    mieter_id = _anlegen(auth_client, wohnung_id, move_in_date='2025-01-01',
                         move_out_date='2025-06-30').get_json()['id']

    antwort = auth_client.put(f'/api/tenants/{mieter_id}', json={'move_in_date': '2025-07-01'})
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    rumpf = antwort.get_json()
    assert rumpf['feld'] == 'move_in_date'
    assert 'nach dem Auszug' in rumpf['error']
    stand = _gelesen(auth_client, mieter_id)
    assert stand['move_in_date'] == '2025-01-01'
    assert stand['move_out_date'] == '2025-06-30'


def test_beide_daten_zusammen_verschieben_geht(auth_client, wohnung_id):
    """Der Prüfstand ist das Ergebnis der Anfrage, nicht der alte Stand."""
    mieter_id = _anlegen(auth_client, wohnung_id, move_in_date='2025-01-01',
                         move_out_date='2025-06-30').get_json()['id']

    antwort = auth_client.put(f'/api/tenants/{mieter_id}', json={
        'move_in_date': '2025-08-01', 'move_out_date': '2025-08-01'})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    stand = _gelesen(auth_client, mieter_id)
    assert (stand['move_in_date'], stand['move_out_date']) == ('2025-08-01', '2025-08-01')


def test_einzug_verschieben_mit_geleertem_auszug_geht(auth_client, wohnung_id):
    mieter_id = _anlegen(auth_client, wohnung_id, move_in_date='2025-01-01',
                         move_out_date='2025-06-30').get_json()['id']

    antwort = auth_client.put(f'/api/tenants/{mieter_id}', json={
        'move_in_date': '2025-09-01', 'move_out_date': ''})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    stand = _gelesen(auth_client, mieter_id)
    assert (stand['move_in_date'], stand['move_out_date']) == ('2025-09-01', None)


# --- Oberfläche: saveTenant ---------------------------------------------------


def _funktion(name):
    anfang = APP_JS.index(f'async function {name}(')
    return APP_JS[anfang:APP_JS.index('\n}\n', anfang) + 3]


def _gesendet(felder, bearbeitet):
    """Welche Felder ``saveTenant`` mit welchem Wert abschickt."""
    node = shutil.which('node')
    if not node:
        pytest.skip('node fehlt')
    probe = '''
        const werte = %s;
        const document = {getElementById: id => ({
            value: werte[id] ?? '', files: [],
        })};
        class FormData {
            constructor() { this.teile = []; }
            append(name, wert) { this.teile.push([name, String(wert)]); }
        }
        const gesendet = [];
        const fetch = async (url, opt) => {
            gesendet.push({url, methode: opt.method, teile: opt.body.teile});
            return {ok: true};
        };
        const showError = m => { throw new Error(m); };
        const serverFehler = async () => new Error('Server');
        const meldungZu = (e, ersatz) => ersatz;
        const closeAddTenantModal = () => {};
        const fetchTenants = () => {};
        let editingTenantId = %s;
        %s
        saveTenant().then(() => console.log(JSON.stringify(gesendet)));
    ''' % (json.dumps(felder), json.dumps(bearbeitet), _funktion('saveTenant'))
    ausgabe = subprocess.run([node, '-e', probe], capture_output=True, text=True,
                             timeout=30, check=True)
    return json.loads(ausgabe.stdout)


_DIALOG = {
    'tenant-name': 'Mieterin Muster', 'tenant-apartment': '3',
    'tenant-move-in': '2025-01-01', 'tenant-move-out': '',
    'tenant-last-billed': '', 'tenant-anrede': '', 'tenant-anschrift': '',
    'tenant-zustellanschrift': '',
}


def test_geleertes_auszugsdatum_geht_beim_bearbeiten_mit():
    """Ohne das leere Feld bleibt der alte Auszug beim Server stehen."""
    (anfrage,) = _gesendet(_DIALOG, 7)
    assert anfrage['url'] == '/api/tenants/7' and anfrage['methode'] == 'PUT'
    assert ['move_out_date', ''] in anfrage['teile']


def test_gesetztes_auszugsdatum_geht_mit():
    (anfrage,) = _gesendet(dict(_DIALOG, **{'tenant-move-out': '2025-06-30'}), None)
    assert anfrage['url'] == '/api/tenants' and anfrage['methode'] == 'POST'
    assert ['move_out_date', '2025-06-30'] in anfrage['teile']


def test_leer_gesendetes_auszugsdatum_raeumt_den_auszug_aus(auth_client, wohnung_id):
    """Das Formular, wie saveTenant es schickt, leert den Auszug wirklich."""
    mieter_id = _anlegen(auth_client, wohnung_id, move_out_date='2025-06-30').get_json()['id']
    antwort = auth_client.put(f'/api/tenants/{mieter_id}', content_type='multipart/form-data',
                              data={'name': 'Mieterin Muster', 'apartment_id': str(wohnung_id),
                                    'move_in_date': '2025-01-01', 'move_out_date': ''})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert _gelesen(auth_client, mieter_id)['move_out_date'] is None
