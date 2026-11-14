"""Angemeldet bleiben in der Desktop-App (#52): Gerätetokens.

Im Servermodus meldet sich die Desktop-App mit Name und Passwort an. Mit dem
Häkchen „Angemeldet bleiben“ bekommt sie dazu ein Gerätetoken, das nur im
Schlüsselbund des Rechners liegt. Damit holt sie sich beim Start und nach
Ablauf der Leerlauf-Grenze still eine neue Sitzung. Die Regeln, die hier
festgehalten werden:

    - Das Häkchen gibt es nur in der App (User-Agent), Vorgabe aus. Ohne
      Häkchen und im Browser ändert sich nichts.
    - Das Token kommt nie in eine Adresse: die Anmeldung hängt nur einen
      Abholcode an (einmalig, 60 s), die App holt das Token per POST ab.
    - Jede Erneuerung gibt ein neues Token aus, das alte wird ungültig.
      Taucht ein ersetztes wieder auf, ist das Gerät abgemeldet.
    - Auf dem Server nur Hashes, Fehlversuche zählen im Anmeldeschutz wie bei
      den Zugriffsschlüsseln.
    - 30 Tage ohne Nutzung, Passwortwechsel, Stilllegen, „Anmeldung
      ausschalten“ und das Einspielen einer Sicherung melden Geräte ab.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from nebenkostenfix import geraete, zeit
from nebenkostenfix.models import Geraet, GeraetCode, GeraetErsetzt, User, db
from tests.conftest import TEST_PASSWORD, TEST_USER

APP = 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 NebenkostenFix-Desktop/0.19.0'
BROWSER = 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/141.0 Safari/537.36'
# Den Einmalcode loest nur die App ein (Login-CSRF, Review zu #57).
APP_KOPF = {'User-Agent': APP}


def _anmelden(client, haken=True, ua=APP, ziel='/', **formular):
    daten = {'username': TEST_USER, 'password': TEST_PASSWORD, **formular}
    if haken:
        daten['angemeldet_bleiben'] = '1'
    return client.post('/login', query_string={'next': ziel}, data=daten,
                       headers={'User-Agent': ua})


def _abholcode(antwort):
    assert antwort.status_code == 302, antwort.get_data(as_text=True)
    werte = parse_qs(urlsplit(antwort.headers['Location']).query)
    return werte.get('geraet', [None])[0]


def _abholen(client, code, name='Arbeitszimmer-PC'):
    return client.post('/api/geraete/abholen', json={'code': code, 'name': name})


def _neues_geraet(app_ctx, name='Arbeitszimmer-PC'):
    """Ein Gerät wie nach der ersten Anmeldung mit Häkchen: das Token."""
    client = app_ctx.app.test_client()
    antwort = _abholen(client, _abholcode(_anmelden(client)), name)
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return antwort.get_json()['token']


def _erneuern(client, token):
    return client.post('/api/geraete/erneuern', json={'token': token})


def _geraete_sitzung(app_ctx, token, ziel='/'):
    """Ein frischer Client, der sich wie die App mit dem Token anmeldet."""
    client = app_ctx.app.test_client()
    antwort = _erneuern(client, token)
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    daten = antwort.get_json()
    angemeldet = client.get('/geraete/anmelden',
                            query_string={'code': daten['code'], 'next': ziel}, headers=APP_KOPF)
    assert angemeldet.status_code == 302, angemeldet.get_data(as_text=True)
    return client, daten['token']


def _hash(wert):
    return hashlib.sha256(wert.encode()).hexdigest()


# --- Die Anmeldeseite --------------------------------------------------------------

def test_im_browser_gibt_es_kein_haekchen(auth_client, anon_client):
    seite = anon_client.get('/login', headers={'User-Agent': BROWSER}).get_data(as_text=True)
    assert 'angemeldet_bleiben' not in seite


def test_in_der_app_gibt_es_das_haekchen_vorgabe_aus(auth_client, anon_client):
    seite = anon_client.get('/login', headers={'User-Agent': APP}).get_data(as_text=True)
    assert 'name="angemeldet_bleiben"' in seite
    assert 'Angemeldet bleiben' in seite
    zeile = next(z for z in seite.splitlines() if 'name="angemeldet_bleiben"' in z)
    assert 'checked' not in zeile


HTTP_HINWEIS = 'Ohne https nur im eigenen Netz ankreuzen.'


@pytest.mark.parametrize('ua, basis, hinter_https, erwartet', [
    (APP, 'http://localhost', None, True),
    (APP, 'https://localhost', None, False),
    (APP, 'http://localhost', '1', False),
    (BROWSER, 'http://localhost', None, False),
])
def test_bei_http_raet_die_anmeldeseite_zum_eigenen_netz(auth_client, anon_client,
                                                        monkeypatch, ua, basis,
                                                        hinter_https, erwartet):
    """Review zu #57: Über http geht das Gerätetoken bei jedem Start
    unverschlüsselt durchs Netz. Hinter einem Proxy mit https (BEHIND_HTTPS)
    sieht der Server selbst nur http, dort gehört der Hinweis nicht hin."""
    if hinter_https:
        monkeypatch.setenv('BEHIND_HTTPS', hinter_https)
    else:
        monkeypatch.delenv('BEHIND_HTTPS', raising=False)
    seite = anon_client.get('/login', base_url=basis,
                            headers={'User-Agent': ua}).get_data(as_text=True)
    assert (HTTP_HINWEIS in seite) is erwartet


def test_ohne_haekchen_bleibt_die_anmeldung_wie_bisher(auth_client, anon_client):
    antwort = _anmelden(anon_client, haken=False, ziel='/einstellungen')
    assert antwort.status_code == 302
    assert antwort.headers['Location'].endswith('/einstellungen')
    assert GeraetCode.query.count() == 0


def test_im_browser_wirkt_das_haekchen_nicht(auth_client, anon_client):
    """Den Weg bietet der Server nur an, wenn die App ihn anfragt (#52)."""
    antwort = _anmelden(anon_client, ua=BROWSER)
    assert antwort.status_code == 302
    assert _abholcode(antwort) is None
    assert GeraetCode.query.count() == 0


@pytest.mark.parametrize('haken', [False, True])
def test_ein_fremder_abholcode_im_ziel_faellt_heraus(auth_client, anon_client, haken):
    """Review zu #57: Die App holt einen Code direkt nach der Anmeldeseite
    ab. Ein präparierter Link /login?next=/?geraet=… darf ihr dort keinen
    fremden unterschieben, auch nicht bei einer Anmeldung ohne Häkchen."""
    antwort = _anmelden(anon_client, haken=haken, ziel='/einstellungen?geraet=fremd&reiter=konto')
    assert antwort.status_code == 302
    ort = urlsplit(antwort.headers['Location'])
    assert ort.path == '/einstellungen'
    werte = parse_qs(ort.query)
    assert werte['reiter'] == ['konto']
    assert werte.get('geraet', []) == ([_eigener_code(werte)] if haken else [])


def _eigener_code(werte):
    """Der eigene Abholcode, den die Anmeldung mit Häkchen anhängt."""
    (code,) = werte['geraet']
    assert code != 'fremd' and GeraetCode.query.one().hash == _hash(code)
    return code


def test_mit_haekchen_haengt_ein_abholcode_am_ziel(auth_client, anon_client):
    antwort = _anmelden(anon_client, ziel='/einstellungen?reiter=konto')
    ort = urlsplit(antwort.headers['Location'])
    assert ort.path == '/einstellungen'
    assert parse_qs(ort.query)['reiter'] == ['konto']
    code = _abholcode(antwort)
    assert code and not code.startswith(geraete.PRAEFIX)
    # Auf dem Server nur der Hash, und die Sitzung gilt wie bei jeder Anmeldung.
    zeile = GeraetCode.query.one()
    assert zeile.hash == _hash(code)
    assert anon_client.get('/api/properties').status_code == 200


@pytest.mark.parametrize('ziel', ['/\t/boese.example/x', '/\n/boese.example/x',
                                  '/\r/boese.example/x'])
def test_der_abholcode_geht_an_keine_fremde_adresse(auth_client, anon_client, ziel):
    """Review: urlsplit warf den Tab weg, und der Code hing an //boese.example."""
    antwort = _anmelden(anon_client, ziel=ziel)
    ort = urlsplit(antwort.headers['Location'])
    assert ort.netloc in ('', 'localhost') and ort.path == '/'
    assert 'boese' not in antwort.headers['Location']


def test_die_erste_sitzung_gehoert_schon_zum_geraet(auth_client, anon_client):
    """Review: Das Abholen kommt ohne das Cookie des Fensters. Die Sitzung
    der Anmeldung muss trotzdem wissen, zu welchem Gerät sie gehört."""
    _abholen(anon_client, _abholcode(_anmelden(anon_client)))
    eintrag, = anon_client.get('/api/geraete').get_json()
    assert eintrag['dieses_geraet'] is True
    antwort = anon_client.post('/logout')
    assert 'abgemeldet=1' in antwort.headers['Location']
    assert Geraet.query.count() == 0


def test_die_liste_beendet_auch_die_erste_sitzung(auth_client, anon_client):
    _abholen(anon_client, _abholcode(_anmelden(anon_client)))
    nummer = Geraet.query.one().id
    assert auth_client.delete(f'/api/geraete/{nummer}').status_code == 200
    assert anon_client.get('/api/properties').status_code == 401


def test_ein_nie_abgeholtes_geraet_verschwindet(auth_client, anon_client, app_ctx):
    _abholcode(_anmelden(anon_client))
    assert Geraet.query.count() == 1
    GeraetCode.query.one().gueltig_bis = zeit.jetzt_utc() - timedelta(seconds=1)
    db.session.commit()
    assert auth_client.get('/api/geraete').get_json() == []
    assert Geraet.query.count() == GeraetCode.query.count() == 0


def test_eine_abgemeldete_sitzung_lebt_nicht_wieder_auf(auth_client, app_ctx):
    """Review: SQLite vergab die Nummer eines gelöschten Geräts neu, und die
    alte Sitzung galt wieder. Jetzt merkt sich die Sitzung einen Zufallswert
    des Geräts; den Fall mit einer älteren Sicherung prüft test_umzug.py."""
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    nummer = Geraet.query.one().id
    assert auth_client.delete(f'/api/geraete/{nummer}').status_code == 200
    _neues_geraet(app_ctx, name='Ersatz-PC')
    assert Geraet.query.one().id != nummer
    assert client.get('/api/properties').status_code == 401


def test_die_anmeldung_per_json_kennt_kein_haekchen(auth_client, anon_client):
    antwort = anon_client.post('/login', json={
        'username': TEST_USER, 'password': TEST_PASSWORD, 'angemeldet_bleiben': True},
        headers={'User-Agent': APP})
    assert antwort.status_code == 200
    assert GeraetCode.query.count() == 0


def test_falsches_passwort_mit_haekchen_legt_nichts_an(auth_client, anon_client):
    antwort = _anmelden(anon_client, password='falsch-falsch')
    assert antwort.status_code == 401
    assert GeraetCode.query.count() == 0


# --- Abholen -----------------------------------------------------------------------

def test_abholen_gibt_das_token_genau_einmal(auth_client, anon_client):
    code = _abholcode(_anmelden(anon_client))
    antwort = _abholen(anon_client, code)
    assert antwort.status_code == 201
    token = antwort.get_json()['token']
    assert token.startswith('nkg_')
    geraet = Geraet.query.one()
    assert geraet.hash == _hash(token)
    assert geraet.name == 'Arbeitszimmer-PC'
    assert geraet.user.username == TEST_USER
    # Der Code gilt nur einmal.
    assert _abholen(anon_client, code).status_code == 401
    assert Geraet.query.count() == 1


def test_abholen_braucht_keine_sitzung(auth_client, anon_client, app_ctx):
    """Die App holt das Token mit urllib ab, ohne das Cookie des Fensters."""
    code = _abholcode(_anmelden(anon_client))
    fremd = app_ctx.app.test_client()
    assert _abholen(fremd, code).status_code == 201


def test_der_abholcode_verfaellt_nach_einer_minute(auth_client, anon_client):
    code = _abholcode(_anmelden(anon_client))
    zeile = GeraetCode.query.one()
    zeile.gueltig_bis = zeit.jetzt_utc() - timedelta(seconds=1)
    db.session.commit()
    assert _abholen(anon_client, code).status_code == 401
    assert Geraet.query.count() == 0


def test_ohne_code_weist_die_sperre_ab(auth_client, anon_client):
    antwort = anon_client.post('/api/geraete/abholen', json={})
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'auth_required'


@pytest.mark.parametrize('name, erwartet', [
    ('  Laptop Küche  ', 'Laptop Küche'),
    ('x' * 80, 'x' * 60),
    ('', 'Rechner ohne Namen'),
    (None, 'Rechner ohne Namen'),
])
def test_der_rechnername(auth_client, anon_client, name, erwartet):
    code = _abholcode(_anmelden(anon_client))
    assert _abholen(anon_client, code, name).status_code == 201
    assert Geraet.query.one().name == erwartet


def test_hoechstens_zehn_geraete_je_konto(auth_client, app_ctx):
    """Wer sich oft neu mit Häkchen anmeldet, sammelt keine Leichen: das am
    längsten unbenutzte Gerät fällt weg."""
    for nummer in range(geraete.HOECHSTENS):
        _neues_geraet(app_ctx, name=f'Rechner {nummer}')
        Geraet.query.filter_by(name=f'Rechner {nummer}').one().zuletzt_benutzt_am = \
            zeit.jetzt_utc() - timedelta(days=geraete.HOECHSTENS - nummer)
        db.session.commit()
    _neues_geraet(app_ctx, name='Neuer Rechner')
    namen = {g.name for g in Geraet.query.all()}
    assert len(namen) == geraete.HOECHSTENS
    assert 'Rechner 0' not in namen and 'Neuer Rechner' in namen


# --- Erneuern und Rotation ---------------------------------------------------------

def test_erneuern_gibt_ein_neues_token_und_einen_einmalcode(auth_client, app_ctx, anon_client):
    alt = _neues_geraet(app_ctx)
    antwort = _erneuern(anon_client, alt)
    assert antwort.status_code == 200
    daten = antwort.get_json()
    assert daten['token'].startswith('nkg_') and daten['token'] != alt
    assert daten['code']
    assert Geraet.query.one().hash == _hash(daten['token'])
    assert 'Set-Cookie' not in antwort.headers


def test_ein_ersetztes_token_meldet_das_geraet_ab(auth_client, app_ctx, anon_client):
    """Reuse Detection (RFC 9700, 4.14.2): Das alte Token taucht noch einmal
    auf, es ist also kopiert worden. Dann ist auch das neue wertlos."""
    alt = _neues_geraet(app_ctx)
    neu = _erneuern(anon_client, alt).get_json()['token']
    antwort = _erneuern(anon_client, alt)
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'geraet_ungueltig'
    assert Geraet.query.count() == 0
    assert GeraetErsetzt.query.count() == 0
    assert _erneuern(anon_client, neu).status_code == 401


@pytest.mark.parametrize('token', ['nkg_gibtesnicht', 'nkg_' + 'a' * 300, 'nkf_falsch', 'falsch'])
def test_ein_unbekanntes_token_401(auth_client, anon_client, token):
    antwort = _erneuern(anon_client, token)
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'geraet_ungueltig'


def test_ohne_token_weist_die_sperre_ab(auth_client, anon_client):
    antwort = anon_client.post('/api/geraete/erneuern', json={'token': ''})
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'auth_required'


@pytest.mark.parametrize('tage, gilt', [(29, True), (31, False)])
def test_nach_30_tagen_ohne_nutzung_ist_das_geraet_abgemeldet(auth_client, app_ctx,
                                                             anon_client, tage, gilt):
    token = _neues_geraet(app_ctx)
    Geraet.query.one().zuletzt_benutzt_am = zeit.jetzt_utc() - timedelta(days=tage)
    db.session.commit()
    assert (_erneuern(anon_client, token).status_code == 200) is gilt
    assert (Geraet.query.count() == 1) is gilt


@pytest.mark.parametrize('ziel, erwartet', [
    ('/', '/?geraet=neu'),
    ('/?tab=1', '/?tab=1&geraet=neu'),
    # Die Oberfläche ändert die Adresse nie: nach einem 401 kommt der alte,
    # schon verbrauchte Abholcode mit dem Ziel zurück (Review zu Commit 3).
    ('/?geraet=alt', '/?geraet=neu'),
    ('/?tab=1&geraet=alt#rechnungen', '/?tab=1&geraet=neu#rechnungen'),
])
def test_das_ziel_traegt_nur_den_neuen_abholcode(ziel, erwartet):
    from nebenkostenfix import geraete
    assert geraete.ziel_mit_abholcode(ziel, 'neu') == erwartet


@pytest.mark.parametrize('tage, bleibt', [(29, True), (31, False)])
def test_nach_30_tagen_verschwindet_das_geraet_auch_aus_der_liste(auth_client, app_ctx,
                                                                 tage, bleibt):
    """Ein verlorener oder verkaufter Rechner meldet sich nie wieder. Die
    Liste darf ihn nach 30 Tagen trotzdem nicht mehr zeigen (Review #52)."""
    _neues_geraet(app_ctx)
    Geraet.query.one().zuletzt_benutzt_am = zeit.jetzt_utc() - timedelta(days=tage)
    db.session.commit()
    assert (len(auth_client.get('/api/geraete').get_json()) == 1) is bleibt
    assert (Geraet.query.count() == 1) is bleibt


def test_das_geraet_eines_stillgelegten_kontos_401(auth_client, app_ctx, anon_client):
    token = _neues_geraet(app_ctx)
    User.query.filter_by(username=TEST_USER).one().is_active = False
    db.session.commit()
    assert _erneuern(anon_client, token).status_code == 401


def test_ersetzte_hashes_bleiben_nicht_ewig(auth_client, app_ctx, anon_client):
    """Für die Reuse Detection reichen die ersetzten Tokens der letzten 30
    Tage; älter darf ein Token ohnehin nicht werden."""
    token = _neues_geraet(app_ctx)
    for _ in range(3):
        token = _erneuern(anon_client, token).get_json()['token']
    assert GeraetErsetzt.query.count() == 3
    for zeile in GeraetErsetzt.query.all():
        zeile.ersetzt_am = zeit.jetzt_utc() - timedelta(days=31)
    db.session.commit()
    _erneuern(anon_client, token)
    assert GeraetErsetzt.query.count() == 1


# --- Sperre ------------------------------------------------------------------------

def test_falsche_tokens_zaehlen_im_anmeldeschutz(auth_client, anon_client):
    from nebenkostenfix import anmeldeschutz
    for nummer in range(anmeldeschutz.GRENZE_IP):
        _erneuern(anon_client, f'nkg_{nummer:02d}falsch')
    antwort = _erneuern(anon_client, 'nkg_99falsch')
    assert antwort.status_code == 429
    assert antwort.get_json()['code'] == 'anmeldung_gesperrt'
    assert 'Retry-After' in antwort.headers


def test_falsche_abholcodes_zaehlen_im_anmeldeschutz(auth_client, anon_client):
    from nebenkostenfix import anmeldeschutz
    for nummer in range(anmeldeschutz.GRENZE_IP):
        _abholen(anon_client, f'{nummer:02d}falsch')
    assert _abholen(anon_client, '99falsch').status_code == 429


def test_ein_gueltiges_token_kommt_an_der_sperre_vorbei(auth_client, app_ctx, anon_client):
    from nebenkostenfix import anmeldeschutz
    token = _neues_geraet(app_ctx)
    for nummer in range(anmeldeschutz.GRENZE_IP):
        _erneuern(anon_client, f'nkg_{nummer:02d}falsch')
    assert _erneuern(anon_client, token).status_code == 200


def test_falsche_tokens_sperren_nicht_die_anmeldung(auth_client, anon_client):
    from nebenkostenfix import anmeldeschutz
    for nummer in range(anmeldeschutz.GRENZE_IP):
        _erneuern(anon_client, f'nkg_{nummer:02d}falsch')
    antwort = anon_client.post('/login', json={'username': TEST_USER, 'password': TEST_PASSWORD})
    assert antwort.status_code == 200


# --- Mit dem Einmalcode in die Sitzung ---------------------------------------------

def test_der_einmalcode_beginnt_eine_sitzung(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    client = app_ctx.app.test_client()
    daten = _erneuern(client, token).get_json()
    assert client.get('/api/properties').status_code == 401
    antwort = client.get('/geraete/anmelden',
                         query_string={'code': daten['code'], 'next': '/einstellungen'}, headers=APP_KOPF)
    assert antwort.status_code == 302
    assert antwort.headers['Location'].endswith('/einstellungen')
    assert client.get('/api/properties').status_code == 200
    assert client.get('/api/auth/me').get_json()['username'] == TEST_USER


def test_der_einmalcode_gilt_nur_einmal(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    code = _erneuern(app_ctx.app.test_client(), token).get_json()['code']
    assert app_ctx.app.test_client().get('/geraete/anmelden',
                                         query_string={'code': code}, headers=APP_KOPF).status_code == 302
    zweiter = app_ctx.app.test_client()
    antwort = zweiter.get('/geraete/anmelden', query_string={'code': code, 'next': '/x'}, headers=APP_KOPF)
    assert '/login' in antwort.headers['Location']
    assert zweiter.get('/api/properties').status_code == 401


def test_der_einmalcode_verfaellt(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    client = app_ctx.app.test_client()
    code = _erneuern(client, token).get_json()['code']
    for zeile in GeraetCode.query.all():
        zeile.gueltig_bis = zeit.jetzt_utc() - timedelta(seconds=1)
    db.session.commit()
    client.get('/geraete/anmelden', query_string={'code': code}, headers=APP_KOPF)
    assert client.get('/api/properties').status_code == 401


def test_der_abholcode_ist_kein_einmalcode(auth_client, anon_client, app_ctx):
    """Die beiden Codes haben verschiedene Aufgaben und taugen nicht für die andere."""
    code = _abholcode(_anmelden(anon_client))
    client = app_ctx.app.test_client()
    client.get('/geraete/anmelden', query_string={'code': code}, headers=APP_KOPF)
    assert client.get('/api/properties').status_code == 401
    assert _abholen(client, code).status_code == 201


def test_das_ziel_bleibt_im_programm(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    client = app_ctx.app.test_client()
    code = _erneuern(client, token).get_json()['code']
    antwort = client.get('/geraete/anmelden',
                         query_string={'code': code, 'next': 'https://boese.example/'}, headers=APP_KOPF)
    assert urlsplit(antwort.headers['Location']).netloc in ('', 'localhost')
    assert 'boese' not in antwort.headers['Location']


def test_ein_falscher_einmalcode_fuehrt_zur_anmeldung_mit_ziel(auth_client, anon_client):
    antwort = anon_client.get('/geraete/anmelden',
                              query_string={'code': 'falsch', 'next': '/einstellungen'}, headers=APP_KOPF)
    assert antwort.status_code == 302
    ort = urlsplit(antwort.headers['Location'])
    assert ort.path == '/login'
    assert parse_qs(ort.query)['next'] == ['/einstellungen']


def test_der_einmalcode_eines_stillgelegten_kontos(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    client = app_ctx.app.test_client()
    code = _erneuern(client, token).get_json()['code']
    User.query.filter_by(username=TEST_USER).one().is_active = False
    db.session.commit()
    antwort = client.get('/geraete/anmelden', query_string={'code': code}, headers=APP_KOPF)
    assert urlsplit(antwort.headers['Location']).path == '/login'
    assert client.get('/api/properties').status_code == 401


def test_eine_kopie_beendet_auch_die_offene_sitzung(auth_client, app_ctx, anon_client):
    alt = _neues_geraet(app_ctx)
    client, _ = _geraete_sitzung(app_ctx, alt)
    assert _erneuern(anon_client, alt).status_code == 401
    assert client.get('/api/properties').status_code == 401


def test_die_leerlauf_grenze_gilt_auch_fuer_die_geraete_sitzung(auth_client, app_ctx):
    """Der Maintainer in #52: die Leerlauf-Grenze bleibt, die App meldet sich
    danach still neu an. Der Server braucht keine Ausnahme."""
    from nebenkostenfix.auth import SESSION_AKTIV_KEY
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    with client.session_transaction() as sitzung:
        sitzung[SESSION_AKTIV_KEY] = 1000
    assert client.get('/api/properties').status_code == 401


def test_auth_me_nennt_die_geraete_sitzung(auth_client, app_ctx):
    """Nach der Leerlauf-Grenze meldet die App eine Geräte-Sitzung still
    wieder an. Die Oberfläche warnt dann nicht „Sie werden abgemeldet“."""
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    assert client.get('/api/auth/me').get_json()['geraet'] is True
    # Schon gleich nach der Anmeldung mit Häkchen, vor dem Abholen.
    mit_haken = app_ctx.app.test_client()
    _anmelden(mit_haken)
    assert mit_haken.get('/api/auth/me').get_json()['geraet'] is True
    # Ohne Häkchen, im Browser: wie bisher.
    ohne = app_ctx.app.test_client()
    _anmelden(ohne, haken=False)
    assert ohne.get('/api/auth/me').get_json()['geraet'] is False
    assert auth_client.get('/api/auth/me').get_json()['geraet'] is False

def test_der_letzte_login_wird_vermerkt(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    konto = User.query.filter_by(username=TEST_USER).one()
    konto.last_login_at = None
    db.session.commit()
    _geraete_sitzung(app_ctx, token)
    db.session.expire_all()
    assert User.query.filter_by(username=TEST_USER).one().last_login_at is not None


# --- Abmelden ----------------------------------------------------------------------

def test_abmelden_in_der_geraete_sitzung_meldet_das_geraet_ab(auth_client, app_ctx):
    client, token = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    antwort = client.post('/logout')
    assert antwort.status_code == 302
    ort = urlsplit(antwort.headers['Location'])
    assert ort.path == '/login' and parse_qs(ort.query)['abgemeldet'] == ['1']
    assert Geraet.query.count() == 0
    assert _erneuern(client, token).status_code == 401


def test_abmelden_per_json_meldet_das_geraet_ab(auth_client, app_ctx):
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    antwort = client.post('/logout', headers={'Accept': 'application/json'})
    assert antwort.status_code == 200
    assert Geraet.query.count() == 0


def test_abmelden_ohne_geraet_laesst_andere_geraete_stehen(auth_client, app_ctx):
    _neues_geraet(app_ctx)
    auth_client.post('/logout')
    assert Geraet.query.count() == 1


def test_widerrufen_mit_dem_token(auth_client, app_ctx, anon_client):
    """Der Menüpunkt „Abmelden“ der App: lokal gelöscht ist es schon, jetzt
    noch der Server. Die Antwort verrät nicht, ob es das Token gab."""
    token = _neues_geraet(app_ctx)
    antwort = anon_client.post('/api/geraete/widerrufen', json={'token': token})
    assert antwort.status_code == 200
    assert Geraet.query.count() == 0
    assert anon_client.post('/api/geraete/widerrufen',
                            json={'token': token}).status_code == 200
    assert anon_client.post('/api/geraete/widerrufen',
                            json={'token': 'nkg_gibtesnicht'}).status_code == 200


def test_widerrufen_mit_einem_ersetzten_token(auth_client, app_ctx, anon_client):
    """Ging bei einer Erneuerung die Antwort verloren, hat die App noch das
    alte Token. Abmelden soll trotzdem wirken."""
    alt = _neues_geraet(app_ctx)
    _erneuern(anon_client, alt)
    anon_client.post('/api/geraete/widerrufen', json={'token': alt})
    assert Geraet.query.count() == 0


def test_widerrufen_ohne_token_weist_die_sperre_ab(auth_client, anon_client):
    antwort = anon_client.post('/api/geraete/widerrufen', json={})
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'auth_required'


def test_ein_abgemeldetes_geraet_beendet_seine_sitzung(auth_client, app_ctx):
    """Wer in der Liste ein Gerät abmeldet (etwa ein verlorenes Notebook),
    meint auch die Sitzung, die dort gerade offen ist."""
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    assert client.get('/api/properties').status_code == 200
    geraet = Geraet.query.one()
    assert auth_client.delete(f'/api/geraete/{geraet.id}').status_code == 200
    assert client.get('/api/properties').status_code == 401
    # Die Sitzung mit Passwort läuft weiter.
    assert auth_client.get('/api/properties').status_code == 200


# --- Die Liste ---------------------------------------------------------------------

def test_die_liste_nennt_die_geraete_ohne_token_und_hash(auth_client, app_ctx):
    token = _neues_geraet(app_ctx)
    antwort = auth_client.get('/api/geraete')
    assert antwort.status_code == 200
    eintrag, = antwort.get_json()
    assert eintrag['name'] == 'Arbeitszimmer-PC'
    assert eintrag['konto'] == TEST_USER
    assert eintrag['angelegt_am'] and eintrag['zuletzt_benutzt']
    assert eintrag['dieses_geraet'] is False
    text = antwort.get_data(as_text=True)
    geraet = Geraet.query.one()
    assert token not in text and geraet.hash not in text
    # Wer den Wert der Sitzung kennt, kann sich mit dem Sitzungsschlüssel ein
    # Cookie bauen; er bleibt deshalb auf dem Server.
    assert geraet.sitzung not in text


def test_die_liste_markiert_dieses_geraet(auth_client, app_ctx):
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    _neues_geraet(app_ctx, name='Laptop')
    liste = client.get('/api/geraete').get_json()
    assert {e['name']: e['dieses_geraet'] for e in liste} == {
        'Arbeitszimmer-PC': True, 'Laptop': False}


def test_abmelden_aus_der_liste(auth_client, app_ctx, anon_client):
    token = _neues_geraet(app_ctx)
    nummer = Geraet.query.one().id
    assert auth_client.delete(f'/api/geraete/{nummer}').status_code == 200
    assert auth_client.delete(f'/api/geraete/{nummer}').status_code == 404
    assert _erneuern(anon_client, token).status_code == 401


def test_im_offenen_modus_ist_die_liste_leer(app_ctx, monkeypatch, tmp_path):
    from nebenkostenfix import datenordner, einstellungen
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    monkeypatch.setitem(app_ctx.app.config, 'DESKTOP', True)
    einstellungen.schreiben(ohne_anmeldung=True)
    assert app_ctx.app.test_client().get('/api/geraete').get_json() == []


# --- Passwort, Stilllegen, Ausschalten ---------------------------------------------

def _zweites_konto(app_ctx, auth_client, name='partnerin', passwort='zweites-konto-1'):
    assert auth_client.post('/api/konten', json={
        'username': name, 'password': passwort}).status_code == 201
    client = app_ctx.app.test_client()
    antwort = client.post('/login', query_string={'next': '/'}, headers={'User-Agent': APP},
                          data={'username': name, 'password': passwort,
                                'angemeldet_bleiben': '1'})
    assert _abholen(client, _abholcode(antwort), 'Laptop Partnerin').status_code == 201


def test_passwort_aendern_meldet_alle_geraete_des_kontos_ab(auth_client, app_ctx):
    _neues_geraet(app_ctx)
    _neues_geraet(app_ctx, name='Laptop')
    _zweites_konto(app_ctx, auth_client)
    antwort = auth_client.put('/api/konto/passwort', json={
        'altes_passwort': TEST_PASSWORD, 'neues_passwort': 'ganz-neues-passwort'})
    assert antwort.status_code == 200
    assert [g.name for g in Geraet.query.all()] == ['Laptop Partnerin']
    # Wer das Passwort gerade geändert hat, bleibt in dieser Sitzung.
    assert auth_client.get('/api/properties').status_code == 200


def test_passwort_aendern_in_der_geraete_sitzung_wirft_nicht_hinaus(auth_client, app_ctx):
    client, _ = _geraete_sitzung(app_ctx, _neues_geraet(app_ctx))
    antwort = client.put('/api/konto/passwort', json={
        'altes_passwort': TEST_PASSWORD, 'neues_passwort': 'ganz-neues-passwort'})
    assert antwort.status_code == 200
    assert Geraet.query.count() == 0
    assert client.get('/api/properties').status_code == 200


def test_falsches_altes_passwort_laesst_die_geraete_stehen(auth_client, app_ctx):
    _neues_geraet(app_ctx)
    auth_client.put('/api/konto/passwort', json={
        'altes_passwort': 'falsch', 'neues_passwort': 'ganz-neues-passwort'})
    assert Geraet.query.count() == 1


def test_kommandozeile_passwd_und_disable_melden_die_geraete_ab(auth_client, app_ctx):
    runner = app_ctx.app.test_cli_runner()
    _neues_geraet(app_ctx)
    ergebnis = runner.invoke(args=['users', 'passwd', TEST_USER,
                                   '--password', 'ganz-neues-passwort'])
    assert ergebnis.exit_code == 0, ergebnis.output
    assert Geraet.query.count() == 0
    _neues_geraet_mit_passwort(app_ctx, 'ganz-neues-passwort')
    ergebnis = runner.invoke(args=['users', 'disable', TEST_USER])
    assert ergebnis.exit_code == 0, ergebnis.output
    assert Geraet.query.count() == 0


def _neues_geraet_mit_passwort(app_ctx, passwort):
    client = app_ctx.app.test_client()
    antwort = _anmelden(client, password=passwort)
    assert _abholen(client, _abholcode(antwort)).status_code == 201


def test_passwort_in_der_app_zuruecksetzen_meldet_die_geraete_ab(auth_client, app_ctx,
                                                                 monkeypatch):
    _neues_geraet(app_ctx)
    monkeypatch.setitem(app_ctx.app.config, 'DESKTOP', True)
    antwort = app_ctx.app.test_client().post('/huelle/passwort', data={
        'username': TEST_USER, 'password': 'ganz-neues-passwort',
        'password2': 'ganz-neues-passwort'})
    assert 'Passwort gespeichert' in antwort.get_data(as_text=True)
    assert Geraet.query.count() == 0


def test_anmeldung_ausschalten_meldet_alle_geraete_ab(auth_client, app_ctx, monkeypatch,
                                                      tmp_path):
    from nebenkostenfix import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    token = _neues_geraet(app_ctx)
    _erneuern(app_ctx.app.test_client(), token)
    antwort = auth_client.post('/api/anmeldung/aus', json={'password': TEST_PASSWORD})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert Geraet.query.count() == GeraetErsetzt.query.count() == GeraetCode.query.count() == 0


# --- Ablage und Wächter ------------------------------------------------------------

def test_in_der_datenbank_liegen_nur_hashes(auth_client, app_ctx, anon_client):
    token = _neues_geraet(app_ctx)
    daten = _erneuern(anon_client, token).get_json()
    werte = []
    for modell in (Geraet, GeraetErsetzt, GeraetCode):
        for zeile in modell.query.all():
            werte += [str(getattr(zeile, spalte.name)) for spalte in modell.__table__.columns]
    for geheim in (token, daten['token'], daten['code']):
        assert all(geheim not in wert for wert in werte)


def test_der_export_enthaelt_keine_geraete(auth_client, app_ctx):
    _neues_geraet(app_ctx)
    daten = auth_client.get('/api/export').get_json()
    for modell in (Geraet, GeraetErsetzt, GeraetCode):
        assert modell.__tablename__ not in daten


@pytest.mark.parametrize('methode, pfad', [
    ('get', '/api/geraete'),
    ('delete', '/api/geraete/1'),
])
def test_ein_zugriffsschluessel_verwaltet_keine_geraete(auth_client, anon_client,
                                                        methode, pfad):
    neu = auth_client.post('/api/zugriffsschluessel',
                           json={'name': 'MCP', 'umfang': 'erfassen'}).get_json()
    antwort = getattr(anon_client, methode)(
        pfad, headers={'Authorization': f"Bearer {neu['schluessel']}"})
    assert antwort.status_code == 403


def test_jede_geraeteroute_steht_in_nie(app_ctx):
    from nebenkostenfix import zugriffsschluessel as zs
    eigene = {regel.endpoint for regel in app_ctx.app.url_map.iter_rules()
              if regel.endpoint.startswith(('geraet_', 'geraete_'))}
    assert len(eigene) == 6
    assert eigene <= zs.NIE_PER_SCHLUESSEL
