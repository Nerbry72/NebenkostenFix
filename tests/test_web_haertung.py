"""NK-128: Web-Haertung (F-56, F-57, F-59).

Die Anwendung ist ein Webserver im LAN mit Login und Mieterdaten. Geprueft
werden: Begrenzung der Anmeldeversuche, Ablehnung schreibender Anfragen von
fremden Seiten (CSRF), Sicherheitskoepfe, Abmeldung nach Leerlauf und die
Warnung beim Start ohne HTTPS.
"""

import time

import pytest

from nebenkostenfix import anmeldeschutz
from nebenkostenfix.models import User, db

KONTO = 'haertung'
PASSWORT = 'haertung-passwort-1'


@pytest.fixture
def konto(app_ctx):
    user = User(username=KONTO)
    user.set_password(PASSWORT)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, passwort, konto=KONTO, **kw):
    return client.post('/login', json={'username': konto, 'password': passwort},
                       **kw)


# --- Anmeldeversuche (F-56) --------------------------------------------------

def test_fuenf_fehlversuche_sperren_das_konto(app_ctx, konto):
    client = app_ctx.app.test_client()
    for _ in range(anmeldeschutz.GRENZE_KONTO):
        assert _login(client, 'falsch-falsch').status_code == 401
    gesperrt = _login(client, PASSWORT)
    assert gesperrt.status_code == 429
    assert 'gesperrt' in gesperrt.get_json()['error']
    assert int(gesperrt.headers['Retry-After']) > 0


def test_die_sperre_gilt_auch_fuer_unbekannte_konten(app_ctx):
    """Sonst verriete die Sperre, welche Namen es gibt."""
    client = app_ctx.app.test_client()
    for _ in range(anmeldeschutz.GRENZE_KONTO):
        _login(client, 'x', konto='gibt-es-nicht')
    assert _login(client, 'x', konto='gibt-es-nicht').status_code == 429


def test_erfolg_setzt_den_zaehler_zurueck(app_ctx, konto):
    client = app_ctx.app.test_client()
    for _ in range(anmeldeschutz.GRENZE_KONTO - 1):
        _login(client, 'falsch-falsch')
    assert _login(client, PASSWORT).status_code == 200
    client.post('/logout', headers={'Accept': 'application/json'})
    for _ in range(anmeldeschutz.GRENZE_KONTO - 1):
        assert _login(client, 'falsch-falsch').status_code == 401
    assert _login(client, PASSWORT).status_code == 200


def test_die_sperre_je_adresse(app_ctx, konto):
    """Viele Konten von einer Adresse: nach GRENZE_IP ist die Adresse zu."""
    client = app_ctx.app.test_client()
    for i in range(anmeldeschutz.GRENZE_IP):
        _login(client, 'x', konto=f'rate-{i}')
    assert _login(client, PASSWORT).status_code == 429
    anderer = app_ctx.app.test_client()
    antwort = _login(anderer, PASSWORT,
                     environ_base={'REMOTE_ADDR': '192.0.2.7'})
    assert antwort.status_code == 200


def test_die_sperre_steht_im_protokoll(app_ctx, konto, caplog):
    client = app_ctx.app.test_client()
    with caplog.at_level('WARNING'):
        for _ in range(anmeldeschutz.GRENZE_KONTO):
            _login(client, 'falsch-falsch')
    assert any('Anmeldung gesperrt' in e.getMessage() for e in caplog.records)


def test_die_sperre_laeuft_ab(app_ctx, konto, monkeypatch):
    client = app_ctx.app.test_client()
    for _ in range(anmeldeschutz.GRENZE_KONTO):
        _login(client, 'falsch-falsch')
    jetzt = time.time()
    monkeypatch.setattr(anmeldeschutz.time, 'time',
                        lambda: jetzt + anmeldeschutz.SPERRE_S + 1)
    assert _login(client, PASSWORT).status_code == 200


def test_die_wartezeit_waechst_und_ist_begrenzt(monkeypatch):
    monkeypatch.setenv('LOGIN_VERZOEGERUNG_S', '0.25')
    assert anmeldeschutz.wartezeit(1) == 0.25
    assert anmeldeschutz.wartezeit(4) == 1.0
    assert anmeldeschutz.wartezeit(100) == 2.0
    monkeypatch.setenv('LOGIN_VERZOEGERUNG_S', 'quatsch')
    assert anmeldeschutz.wartezeit(1) == 0.25


def test_zwei_arbeiter_teilen_den_zaehler(app_ctx, konto, monkeypatch):
    """Der Stand liegt im Datenordner, nicht im Prozess."""
    client = app_ctx.app.test_client()
    for _ in range(anmeldeschutz.GRENZE_KONTO - 1):
        _login(client, 'falsch-falsch')
    monkeypatch.setattr(anmeldeschutz, '_speicher', {})  # anderer Prozess
    _login(client, 'falsch-falsch')
    assert _login(client, PASSWORT).status_code == 429


def test_cli_passwd_hebt_die_sperre_auf(app_ctx, konto):
    client = app_ctx.app.test_client()
    for _ in range(anmeldeschutz.GRENZE_KONTO):
        _login(client, 'falsch-falsch')
    runner = app_ctx.app.test_cli_runner()
    runner.invoke(args=['users', 'passwd', KONTO, '--password', 'neues-passwort-9'])
    assert _login(client, 'neues-passwort-9').status_code == 200


# --- Fremde Seiten (CSRF, F-57) ---------------------------------------------

def test_schreiben_von_fremdem_ursprung_wird_abgelehnt(auth_client):
    antwort = auth_client.post('/api/properties', json={'name': 'Fremd'},
                               headers={'Origin': 'https://boese.example'})
    assert antwort.status_code == 403
    assert antwort.get_json()['code'] == 'fremder_ursprung'
    assert auth_client.get('/api/properties').get_json() == []


def test_schreiben_vom_eigenen_ursprung_geht(auth_client):
    antwort = auth_client.post('/api/properties', json={'name': 'Eigen'},
                               headers={'Origin': 'http://localhost'})
    assert antwort.status_code == 201


def test_sec_fetch_site_cross_site_wird_abgelehnt(auth_client):
    antwort = auth_client.delete('/api/properties/1',
                                 headers={'Sec-Fetch-Site': 'cross-site'})
    assert antwort.status_code == 403


def test_referer_von_fremder_seite_wird_abgelehnt(auth_client):
    antwort = auth_client.post('/api/properties', json={'name': 'X'},
                               headers={'Referer': 'https://boese.example/seite'})
    assert antwort.status_code == 403


def test_null_ursprung_wird_abgelehnt(auth_client):
    antwort = auth_client.post('/api/properties', json={'name': 'X'},
                               headers={'Origin': 'null'})
    assert antwort.status_code == 403


def test_anmelde_csrf_wird_abgelehnt(app_ctx, konto):
    client = app_ctx.app.test_client()
    antwort = _login(client, PASSWORT, headers={'Origin': 'https://boese.example'})
    assert antwort.status_code == 403


def test_lesen_von_fremdem_ursprung_bleibt_unberuehrt(auth_client):
    """GET aendert nichts; die Pruefung gilt nur schreibenden Methoden."""
    antwort = auth_client.get('/api/properties',
                              headers={'Origin': 'https://boese.example'})
    assert antwort.status_code == 200


def test_erlaubte_urspruenge_hinter_einem_proxy(auth_client, monkeypatch):
    monkeypatch.setenv('ERLAUBTE_URSPRUENGE', 'https://nk.example.org')
    antwort = auth_client.post('/api/properties', json={'name': 'Proxy'},
                               headers={'Origin': 'https://nk.example.org'})
    assert antwort.status_code == 201


# --- Koepfe (F-57) -----------------------------------------------------------

def test_sicherheitskoepfe_auf_jeder_antwort(auth_client, anon_client):
    for antwort in (auth_client.get('/api/properties'), anon_client.get('/login'),
                    auth_client.get('/')):
        koepfe = antwort.headers
        csp = koepfe['Content-Security-Policy']
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp
        assert koepfe['X-Content-Type-Options'] == 'nosniff'
        assert koepfe['X-Frame-Options'] == 'DENY'
        assert koepfe['Referrer-Policy'] == 'same-origin'
        assert 'camera=()' in koepfe['Permissions-Policy']


def test_api_antworten_werden_nicht_zwischengespeichert(auth_client):
    assert auth_client.get('/api/properties').headers['Cache-Control'] == 'no-store'


def test_hsts_nur_hinter_https(auth_client, monkeypatch):
    assert 'Strict-Transport-Security' not in auth_client.get('/api/properties').headers
    monkeypatch.setenv('BEHIND_HTTPS', '1')
    assert 'max-age' in auth_client.get('/api/properties').headers[
        'Strict-Transport-Security']


def test_csp_erlaubt_keine_fremde_quelle():
    from nebenkostenfix import auth
    for teil in auth.CSP.split(';'):
        assert 'http' not in teil and '*' not in teil, teil


# --- Leerlauf und Abmeldung (F-57) -------------------------------------------

def test_abmeldung_nach_leerlauf(auth_client, monkeypatch):
    from nebenkostenfix import auth
    assert auth_client.get('/api/properties').status_code == 200
    jetzt = time.time()
    monkeypatch.setattr(auth.time, 'time', lambda: jetzt + 61 * 60)
    assert auth_client.get('/api/properties').status_code == 401


def test_aktivitaet_haelt_die_sitzung(auth_client, monkeypatch):
    from nebenkostenfix import auth
    jetzt = time.time()
    for minute in (30, 60, 90, 120):
        monkeypatch.setattr(auth.time, 'time', lambda m=minute: jetzt + m * 60)
        assert auth_client.get('/api/properties').status_code == 200


def test_leerlauf_einstellbar(auth_client, monkeypatch):
    from nebenkostenfix import auth
    monkeypatch.setenv('SITZUNG_LEERLAUF_MIN', '5')
    auth_client.get('/api/properties')
    jetzt = time.time()
    monkeypatch.setattr(auth.time, 'time', lambda: jetzt + 6 * 60)
    assert auth_client.get('/api/properties').status_code == 401


# --- Start ohne HTTPS (F-59) ------------------------------------------------

def test_start_ohne_https_warnt(monkeypatch, caplog):
    from flask import Flask

    from nebenkostenfix import auth
    monkeypatch.delenv('BEHIND_HTTPS', raising=False)
    probe = Flask('probe')
    with caplog.at_level('WARNING'):
        auth.init_auth(probe)
    assert any('ohne HTTPS' in e.getMessage() for e in caplog.records)


def test_start_mit_https_warnt_nicht(monkeypatch, caplog):
    from flask import Flask

    from nebenkostenfix import auth
    monkeypatch.setenv('BEHIND_HTTPS', '1')
    probe = Flask('probe')
    with caplog.at_level('WARNING'):
        auth.init_auth(probe)
    assert not any('ohne HTTPS' in e.getMessage() for e in caplog.records)
