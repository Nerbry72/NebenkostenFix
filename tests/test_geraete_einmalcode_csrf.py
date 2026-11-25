"""Login-CSRF beim Einmalcode (Review zu #57, Backlog SEC-001).

``GET /geraete/anmelden?code=…`` beginnt eine Sitzung über eine Adresse. Wer
ein eigenes Konto auf demselben Server hat, holt sich über
``/api/geraete/erneuern`` einen Code und schickt ihn einer anderen Person als
Link. Öffnete sie ihn innerhalb der Minute, arbeitete sie danach unbemerkt
in seinem Konto, und was sie dort einträgt, kann er lesen.

Die Riegel:

    - Ist im Browser schon ein anderes Konto angemeldet, bleibt dessen
      Sitzung, und der Code ist verbraucht.
    - Eingelöst wird nur, was die App selbst lädt: mit ihrer Kennung im
      User-Agent und ohne ``Sec-Fetch-Site: cross-site`` oder ``same-site``.
      Gemessen mit WKWebView (pywebview 6.2.1): ``load_url`` schickt
      ``none``, eine Navigation auf derselben Seite ``same-origin``, ein Link
      von einer fremden Seite ``cross-site``. Den User-Agent des Opfers
      bestimmt der Angreifer nicht, darum taugt die Kennung hier als Riegel.

Alle Daten fiktiv.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from nebenkostenfix import anmeldeschutz, geraete
from nebenkostenfix.models import Geraet, GeraetCode, User
from tests.conftest import TEST_USER
from tests.test_geraete import APP, BROWSER, _abholcode, _abholen, _erneuern, _neues_geraet

ANGREIFER = 'csrf-angreifer'
ANGREIFER_PASSWORT = 'csrf-passwort-1'


@pytest.fixture
def fehlversuche(monkeypatch):
    gezaehlt = []
    original = anmeldeschutz.fehlversuch

    def zaehlen(ordner, merkmal, adresse):
        gezaehlt.append(merkmal)
        return original(ordner, merkmal, adresse)

    monkeypatch.setattr(anmeldeschutz, 'fehlversuch', zaehlen)
    return gezaehlt


def _code_des_angreifers(app_ctx, auth_client):
    """Ein zweites Konto mit Gerät holt sich einen frischen Einmalcode."""
    assert auth_client.post('/api/konten', json={
        'username': ANGREIFER, 'password': ANGREIFER_PASSWORT}).status_code == 201
    client = app_ctx.app.test_client()
    antwort = client.post('/login', query_string={'next': '/'}, headers={'User-Agent': APP},
                          data={'username': ANGREIFER, 'password': ANGREIFER_PASSWORT,
                                'angemeldet_bleiben': '1'})
    token = _abholen(client, _abholcode(antwort), 'Rechner Angreifer').get_json()['token']
    return _erneuern(client, token).get_json()['code']


def _einloesen(client, code, ua=APP, herkunft=None, ziel='/einstellungen'):
    kopf = {'User-Agent': ua}
    if herkunft is not None:
        kopf['Sec-Fetch-Site'] = herkunft
    return client.get('/geraete/anmelden', query_string={'code': code, 'next': ziel},
                      headers=kopf)


def _wer(client):
    antwort = client.get('/api/auth/me')
    return antwort.get_json()['username'] if antwort.status_code == 200 else None


# --- Mit bestehender Sitzung --------------------------------------------------------

@pytest.mark.parametrize('herkunft', [None, 'none'])
def test_eine_bestehende_sitzung_eines_anderen_kontos_bleibt(
        app_ctx, auth_client, fehlversuche, herkunft):
    """Die Vorgabe aus dem Review: Konto A angemeldet, Code von Konto B,
    danach ist weiterhin A angemeldet. Auch dann, wenn die Anfrage wie aus
    der App aussieht; die Sitzungsregel hält für sich allein."""
    code = _code_des_angreifers(app_ctx, auth_client)
    assert _wer(auth_client) == TEST_USER

    antwort = _einloesen(auth_client, code, herkunft=herkunft)
    assert antwort.status_code == 302
    assert _wer(auth_client) == TEST_USER, 'der fremde Code hat die Sitzung übernommen'
    assert urlsplit(antwort.headers['Location']).path == '/einstellungen'
    assert GeraetCode.query.filter_by(zweck='anmelden').count() == 0
    assert fehlversuche == []


def test_dasselbe_konto_bindet_die_sitzung_an_sein_geraet(app_ctx, auth_client):
    token = _neues_geraet(app_ctx)
    code = _erneuern(app_ctx.app.test_client(), token).get_json()['code']
    with auth_client.session_transaction() as sitzung:
        assert geraete.SITZUNG_KEY not in sitzung

    antwort = _einloesen(auth_client, code)
    assert antwort.status_code == 302
    assert _wer(auth_client) == TEST_USER
    geraet = Geraet.query.join(User).filter(User.username == TEST_USER).one()
    with auth_client.session_transaction() as sitzung:
        assert sitzung[geraete.SITZUNG_KEY] == geraet.sitzung


# --- Ohne Sitzung ------------------------------------------------------------------

@pytest.mark.parametrize('herkunft', ['cross-site', 'same-site', 'CROSS-SITE'])
def test_ein_code_von_einer_fremden_seite_wird_nicht_eingeloest(
        app_ctx, auth_client, anon_client, herkunft):
    code = _code_des_angreifers(app_ctx, auth_client)
    antwort = _einloesen(anon_client, code, herkunft=herkunft)
    ort = urlsplit(antwort.headers['Location'])
    assert ort.path == '/login'
    assert parse_qs(ort.query)['next'] == ['/einstellungen']
    assert _wer(anon_client) is None, 'Link einer fremden Seite setzt in fremdes Konto'
    assert GeraetCode.query.filter_by(zweck='anmelden').count() == 0


def test_ohne_die_kennung_der_app_wird_nicht_eingeloest(app_ctx, auth_client, anon_client):
    """Der Browser des Opfers schickt seinen eigenen User-Agent."""
    code = _code_des_angreifers(app_ctx, auth_client)
    antwort = _einloesen(anon_client, code, ua=BROWSER, herkunft='none')
    assert urlsplit(antwort.headers['Location']).path == '/login'
    assert _wer(anon_client) is None
    assert GeraetCode.query.filter_by(zweck='anmelden').count() == 0


@pytest.mark.parametrize('herkunft', [None, 'none', 'same-origin'])
def test_die_app_loest_ihren_code_ein(app_ctx, auth_client, anon_client, herkunft):
    """Gegenprobe: so lädt die App die Adresse selbst (S0, WKWebView)."""
    token = _neues_geraet(app_ctx)
    code = _erneuern(app_ctx.app.test_client(), token).get_json()['code']
    antwort = _einloesen(anon_client, code, herkunft=herkunft)
    assert urlsplit(antwort.headers['Location']).path == '/einstellungen'
    assert _wer(anon_client) == TEST_USER
