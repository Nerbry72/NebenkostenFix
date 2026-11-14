"""Ein Gerätetoken gilt nur für das Konto, für das es angelegt wurde (Review zu #57).

Dasselbe Muster wie bei den Zugriffsschlüsseln
(``tests/test_zugriffsschluessel_konto_bindung.py``): ``geraete.user_id``
verweist ohne ``ondelete`` auf ``users.id``, und SQLite setzt den
Fremdschlüssel nicht durch. Wird ein Konto direkt in der Datenbank gelöscht,
bleibt sein Gerät stehen, und das nächste neue Konto bekommt dieselbe Nummer.
Ohne Prüfung holte sich das alte Gerät über ``/geraete/anmelden`` eine Sitzung
mit dem gültigen Kontostempel des neuen Kontos.

Die Regel ist dieselbe wie bei den Schlüsseln (``aelter_als_das_konto``): Ein
Gerät, das vor seinem Konto angelegt wurde, zählt wie ein falsches Token.
Abholen, Erneuern und Anmelden lehnen es ab, mit Fehlversuch im
Anmeldeschutz, und melden es gleich ab. Eine laufende Sitzung des Geräts
endet, und die Liste in den Einstellungen zeigt es nicht mehr.

Alle Daten fiktiv.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlsplit

import pytest

from nebenkostenfix import anmeldeschutz, auth, geraete
from nebenkostenfix.models import Geraet, User, db
from tests.test_geraete import APP, _abholcode, _abholen, _erneuern, _geraete_sitzung

PARTNER = 'bindung-partnerin'
PARTNER_PASSWORT = 'bindung-passwort-1'
NEUES_KONTO = 'bindung-neues-konto'
NEUES_PASSWORT = 'bindung-passwort-2'


@pytest.fixture
def fehlversuche(monkeypatch):
    """Zählt die Fehlversuche, die die Geräte-Routen im Anmeldeschutz melden."""
    gezaehlt = []
    original = anmeldeschutz.fehlversuch

    def zaehlen(ordner, merkmal, adresse):
        gezaehlt.append(merkmal)
        return original(ordner, merkmal, adresse)

    monkeypatch.setattr(anmeldeschutz, 'fehlversuch', zaehlen)
    return gezaehlt


def _partner_anmelden(app_ctx, auth_client):
    """Zweites Konto, das sich in der App mit Häkchen anmeldet. Liefert den
    Client und den Abholcode, das Gerät steht damit schon in der Tabelle."""
    assert auth_client.post('/api/konten', json={
        'username': PARTNER, 'password': PARTNER_PASSWORT}).status_code == 201
    client = app_ctx.app.test_client()
    antwort = client.post('/login', query_string={'next': '/'}, headers={'User-Agent': APP},
                          data={'username': PARTNER, 'password': PARTNER_PASSWORT,
                                'angemeldet_bleiben': '1'})
    return client, _abholcode(antwort)


def _zurueckdatieren():
    """Konto und Gerät sind eine Stunde alt, wenn das Konto verschwindet."""
    partner = User.query.filter_by(username=PARTNER).one()
    partner.created_at = partner.created_at - timedelta(hours=1)
    for geraet in Geraet.query.filter_by(user_id=partner.id):
        geraet.angelegt_am = geraet.angelegt_am - timedelta(hours=1)
    db.session.commit()
    return partner


def _ersetzen(auth_client, partner, neuer_name=NEUES_KONTO):
    """Wie ein Eingriff in die Datenbank: das Konto weg, das Gerät bleibt.
    Danach ein neues Konto mit derselben Nummer."""
    alte_id = partner.id
    db.session.delete(partner)
    db.session.commit()
    assert Geraet.query.filter_by(user_id=alte_id).count() == 1
    antwort = auth_client.post('/api/konten', json={
        'username': neuer_name, 'password': NEUES_PASSWORT})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert User.query.filter_by(username=neuer_name).one().id == alte_id
    return alte_id


def _partner_mit_token(app_ctx, auth_client):
    client, code = _partner_anmelden(app_ctx, auth_client)
    antwort = _abholen(client, code, 'Laptop Partnerin')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return antwort.get_json()['token']


# --- Die drei Wege -----------------------------------------------------------------

def test_abholen_lehnt_das_geraet_des_geloeschten_kontos_ab(
        app_ctx, auth_client, anon_client, fehlversuche):
    _, code = _partner_anmelden(app_ctx, auth_client)
    alte_id = _ersetzen(auth_client, _zurueckdatieren())

    antwort = _abholen(anon_client, code)
    assert antwort.status_code == 401, (
        f'Abholcode des alten Kontos gilt für das neue: {antwort.get_data(as_text=True)}')
    assert antwort.get_json()['code'] == 'geraet_ungueltig'
    assert len(fehlversuche) == 1
    assert Geraet.query.filter_by(user_id=alte_id).count() == 0


@pytest.mark.parametrize('neuer_name', [NEUES_KONTO, PARTNER])
def test_erneuern_lehnt_das_geraet_des_geloeschten_kontos_ab(
        app_ctx, auth_client, anon_client, fehlversuche, neuer_name):
    token = _partner_mit_token(app_ctx, auth_client)
    alte_id = _ersetzen(auth_client, _zurueckdatieren(), neuer_name)

    antwort = _erneuern(anon_client, token)
    assert antwort.status_code == 401, (
        f'altes Gerätetoken gilt für das neue Konto: {antwort.get_data(as_text=True)}')
    assert antwort.get_json()['code'] == 'geraet_ungueltig'
    assert len(fehlversuche) == 1
    assert Geraet.query.filter_by(user_id=alte_id).count() == 0


def test_anmelden_mit_einmalcode_lehnt_das_geraet_des_geloeschten_kontos_ab(
        app_ctx, auth_client, anon_client, fehlversuche):
    """Der Weg, vor dem das Review warnt: Der Einmalcode stammt noch aus der
    Zeit des alten Kontos, die Sitzung bekäme aber den Stempel des neuen."""
    token = _partner_mit_token(app_ctx, auth_client)
    code = _erneuern(anon_client, token).get_json()['code']
    alte_id = _ersetzen(auth_client, _zurueckdatieren())

    antwort = anon_client.get('/geraete/anmelden', query_string={'code': code, 'next': '/'},
                              headers={'User-Agent': APP})
    assert antwort.status_code == 302
    assert urlsplit(antwort.headers['Location']).path == '/login'
    assert anon_client.get('/api/auth/me').status_code == 401
    assert len(fehlversuche) == 1
    assert Geraet.query.filter_by(user_id=alte_id).count() == 0


def test_ohne_neues_konto_gibt_es_401_statt_eines_fehlers(
        app_ctx, auth_client, anon_client, fehlversuche):
    """Zwischen Löschen und neuem Konto hat das Gerät gar kein Konto. Das darf
    kein Serverfehler werden."""
    token = _partner_mit_token(app_ctx, auth_client)
    partner = User.query.filter_by(username=PARTNER).one()
    alte_id = partner.id
    db.session.delete(partner)
    db.session.commit()

    antwort = _erneuern(anon_client, token)
    assert antwort.status_code == 401, antwort.get_data(as_text=True)
    assert len(fehlversuche) == 1
    assert Geraet.query.filter_by(user_id=alte_id).count() == 0


# --- Vergleich auf die Sekunde ------------------------------------------------------

@pytest.mark.parametrize('geraet_angelegt, status', [
    (datetime(2026, 3, 1, 12, 0, 0, 100000), 200),
    (datetime(2026, 3, 1, 12, 0, 0), 200),
    (datetime(2026, 3, 1, 12, 0, 1), 200),
    (datetime(2026, 3, 1, 11, 59, 59, 999999), 401),
    (datetime(2025, 12, 31, 23, 0, 0), 401),
])
def test_vergleich_auf_die_sekunde(app_ctx, auth_client, anon_client,
                                  geraet_angelegt, status):
    token = _partner_mit_token(app_ctx, auth_client)
    partner = User.query.filter_by(username=PARTNER).one()
    partner.created_at = datetime(2026, 3, 1, 12, 0, 0, 500000)
    Geraet.query.filter_by(user_id=partner.id).one().angelegt_am = geraet_angelegt
    db.session.commit()
    antwort = _erneuern(anon_client, token)
    assert antwort.status_code == status, antwort.get_data(as_text=True)


# --- Laufende Sitzung und Liste -----------------------------------------------------

def test_sitzung_gilt_endet_fuer_ein_geraet_aus_der_zeit_vor_dem_konto(app_ctx, auth_client):
    """``sitzung_gilt`` für sich allein: Den Kontostempel prüft
    ``current_user`` getrennt, hier zählt nur das Gerät."""
    _partner_mit_token(app_ctx, auth_client)
    partner = User.query.filter_by(username=PARTNER).one()
    geraet = Geraet.query.filter_by(user_id=partner.id).one()
    with app_ctx.app.test_request_context('/'):
        from flask import session
        session[geraete.SITZUNG_KEY] = geraet.sitzung
        assert geraete.sitzung_gilt(partner.id) is True
        partner.created_at = geraet.angelegt_am + timedelta(seconds=5)
        db.session.commit()
        assert geraete.sitzung_gilt(partner.id) is False


def test_eine_laufende_geraete_sitzung_endet(app_ctx, auth_client):
    token = _partner_mit_token(app_ctx, auth_client)
    client, _ = _geraete_sitzung(app_ctx, token)
    assert client.get('/api/auth/me').status_code == 200
    partner = User.query.filter_by(username=PARTNER).one()
    geraet = Geraet.query.filter_by(user_id=partner.id).one()
    geraet.angelegt_am = partner.created_at - timedelta(hours=1)
    db.session.commit()
    assert client.get('/api/auth/me').status_code == 401


def test_die_liste_zeigt_das_geraet_des_geloeschten_kontos_nicht(app_ctx, auth_client):
    _partner_mit_token(app_ctx, auth_client)
    _ersetzen(auth_client, _zurueckdatieren())
    namen = [z['name'] for z in auth_client.get('/api/geraete').get_json()]
    assert 'Laptop Partnerin' not in namen
    assert Geraet.query.count() == 0


def test_das_eigene_geraet_bleibt_in_der_liste(app_ctx, auth_client):
    """Gegenprobe: ein Gerät aus der Zeit nach dem Konto bleibt stehen."""
    _partner_mit_token(app_ctx, auth_client)
    namen = [z['name'] for z in auth_client.get('/api/geraete').get_json()]
    assert namen == ['Laptop Partnerin']


# --- Zusammenspiel mit 0.19.1 -------------------------------------------------------

def test_die_geraete_sitzung_traegt_den_kontostempel(app_ctx, auth_client):
    """Nach dem Rebase auf 0.19.1: ``geraet_anmelden`` beginnt die Sitzung
    über ``_sitzung_beginnen``, sonst beendete ``current_user`` sie sofort."""
    token = _partner_mit_token(app_ctx, auth_client)
    client, _ = _geraete_sitzung(app_ctx, token)
    with client.session_transaction() as sitzung:
        assert sitzung[auth.SESSION_KONTO_KEY]
        assert sitzung[auth.SESSION_NAME_KEY] == PARTNER
    assert client.get('/api/auth/me').get_json()['username'] == PARTNER
