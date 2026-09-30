"""NK-127: Ersteinrichtung und Kontoverwaltung (E-1, F-62).

Bis hierher war das Konto eine Kommandozeilensache: ``flask users add`` vor
dem ersten Start, ``SECRET_KEY`` von Hand in die .env. Unter Windows und auf
einer Synology ist das fuer Laien ein Abbruchgrund (F-62). Diese Karte loest
das nach E-1:

    - Ohne Konto leitet die Anmeldung auf /einrichtung. Die Route verlangt
      einen Einmal-Code, der nur im Serverprotokoll steht -- wer das
      Protokoll lesen kann, darf das Konto anlegen, sonst niemand.
    - Der Sitzungsschluessel entsteht ohne Zutun und liegt im Datenordner
      (getestet in test_auth.py).
    - Das eigene Passwort wechselt die Oberflaeche (/api/konto/passwort),
      das zweite Konto legt die Oberflaeche an (/api/konten), mehr als zwei
      gibt es nicht (ZIEL § 8).
    - Passwort vergessen bleibt Sache des Servers: flask users passwd
      braucht lokalen Zugriff, lokaler Zugriff gilt als Berechtigung.

Die Tests lesen den Einmal-Code aus dem Protokoll, genau wie der Betreiber
im Docker-Log -- nicht aus der Anwendungsstruktur.
"""

import logging
import os
import re

import pytest

from nebenkostenfix.models import User, db

CODE_MUSTER = re.compile(
    r'\b([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})\b')


@pytest.fixture(autouse=True)
def _code_frisch():
    """Jeder Test beginnt wie ein Prozessstart: kein Code im Speicher.

    Der Einmal-Code lebt im Modul auth und ueberlebt Tests, die dieselbe
    Anwendung benutzen. Ohne Zuruecksetzen wuerde nur der erste Test die
    Protokollzeile sehen -- im echten Leben startet der Server neu, hier
    ahmt die Fixture den Neustart nach.
    """
    from nebenkostenfix import auth
    auth_zuruecksetzen(auth)
    yield
    auth_zuruecksetzen(auth)


def auth_zuruecksetzen(auth):
    """Speicher und Code-Datei leeren: der Code liegt seit NK-149 (F-73)
    im Datenordner, damit alle Arbeiter denselben sehen."""
    auth._ersteinrichtung.update(code=None, fehlversuche=0, protokolliert=None)
    pfad = auth._code_ablage()
    if pfad and os.path.exists(pfad):
        os.unlink(pfad)
    if pfad:
        text = os.path.join(os.path.dirname(pfad), auth.EINMAL_CODE_TEXTDATEI)
        if os.path.exists(text):
            os.unlink(text)


def code_aus_protokoll(caplog):
    """Den Einmal-Code aus den Protokollzeilen ziehen, wie im Docker-Log."""
    zeilen = [eintrag.getMessage() for eintrag in caplog.records
              if 'Einmal-Code' in eintrag.getMessage()]
    assert zeilen, 'Der Start hat den Einmal-Code nicht protokolliert.'
    treffer = CODE_MUSTER.search(zeilen[0])
    assert treffer, f'Kein Code in der Protokollzeile: {zeilen[0]!r}'
    return '-'.join(treffer.groups())


@pytest.fixture
def frischer_client(app_ctx):
    """Ein Client ohne Konto und ohne Sitzung: der allererste Start."""
    return app_ctx.app.test_client()


def kontozaehler():
    return User.query.count()


# --- Die Anmeldung weist den Weg ---

def test_ohne_konto_leitet_die_anmeldung_zur_einrichtung(frischer_client):
    """Erster Start: statt einer Anmeldung, die nie gelingen kann, die
    Einrichtung (E-1). Die Kette / -> /login -> /einrichtung bleibt ganz."""
    start = frischer_client.get('/')
    assert start.status_code in (301, 302, 303, 307, 308)
    assert '/login' in start.headers['Location']
    anmeldung = frischer_client.get('/login')
    assert anmeldung.status_code in (301, 302, 303, 307, 308)
    assert '/einrichtung' in anmeldung.headers['Location']


def test_die_einrichtungsseite_nennt_den_code_nicht(frischer_client, caplog):
    """Die Seite zeigt den Code nirgends -- nur das Protokoll kennt ihn.
    Sonst koennte jeder Fremde die Einrichtung erreichen, nicht nur der
    Betreiber am Server."""
    with caplog.at_level(logging.WARNING):
        seite = frischer_client.get('/einrichtung')
    assert seite.status_code == 200
    text = seite.get_data(as_text=True)
    code = code_aus_protokoll(caplog)
    assert code not in text
    assert 'Protokoll' in text  # die Wegweisung zum Docker-Log
    assert 'Einmal-Code' in text


def test_die_protokollzeile_nennt_den_code(frischer_client, caplog):
    """Der Betreiber soll den Code im Docker-Log finden koennen."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
    code = code_aus_protokoll(caplog)
    assert len(code) == 19  # vier Gruppen zu vier Zeichen: 64 Bit (F-75)


def test_der_code_bleibt_beim_zweiten_aufruf_derselbe(frischer_client, caplog):
    """Nur ein Code pro Start: neu erzeugt wird bei der Anzeige nicht."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        erster = code_aus_protokoll(caplog)
        caplog.clear()
        frischer_client.get('/einrichtung')
    zeilen = [e.getMessage() for e in caplog.records
              if 'Einmal-Code' in e.getMessage()]
    assert zeilen == []  # kein zweites Protokoll, kein zweiter Code


# --- Die Einrichtung selbst ---

def test_falscher_code_weist_ab(frischer_client):
    antwort = frischer_client.post('/einrichtung', json={
        'username': 'vermieter',
        'password': 'lang-genug-123',
        'password2': 'lang-genug-123',
        'code': '0000-0000',
    })
    assert antwort.status_code == 400
    assert kontozaehler() == 0


def test_code_ohne_trenner_und_gross_gilt(frischer_client, caplog):
    """Der Betreiber tippt ab, wie er es liest: Toleranz bei Gross-/Klein-
    schreibung und Trennzeichen, damit die Einrichtung nicht an der Form
    des Codes scheitert."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        roh = code.replace('-', '').upper()
        antwort = frischer_client.post('/einrichtung', json={
            'username': 'vermieter',
            'password': 'lang-genug-123',
            'password2': 'lang-genug-123',
            'code': roh,
        })
    assert antwort.status_code == 201, antwort.get_json()
    assert kontozaehler() == 1


def test_einrichtung_legt_konto_an_und_meldet_an(frischer_client, caplog):
    """Nach dem Anlegen ist der Betreiber angemeldet und landet in der
    Oberflaeche; das Passwort passt, der Code ist verfallen."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        antwort = frischer_client.post('/einrichtung', json={
            'username': 'vermieter',
            'password': 'lang-genug-123',
            'password2': 'lang-genug-123',
            'code': code,
        })
    assert antwort.status_code == 201
    assert antwort.get_json() == {'username': 'vermieter'}

    user = User.query.filter_by(username='vermieter').first()
    assert user is not None
    assert user.check_password('lang-genug-123')

    sitzung = frischer_client.get('/api/auth/me')
    assert sitzung.status_code == 200
    assert sitzung.get_json()['username'] == 'vermieter'


def test_formular_anmeldung_leitet_in_die_oberflaeche(
        frischer_client, caplog):
    """Der Browser schickt das Formular, kein JSON: danach geht es direkt
    hinein, ohne weiteren Klick."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        antwort = frischer_client.post('/einrichtung', data={
            'username': 'vermieter',
            'password': 'lang-genug-123',
            'password2': 'lang-genug-123',
            'code': code,
        })
    assert antwort.status_code in (301, 302, 303, 307, 308)
    assert antwort.headers['Location'].endswith('/')


def test_nach_der_einrichtung_nimmt_die_route_nichts_mehr_an(
        frischer_client, caplog):
    """Die zweite Einrichtung ist ein Angriffsfall: wer nur die Website
    kennt, koennte sich sonst ein Konto bauen, sobald eines existiert."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        erste = frischer_client.post('/einrichtung', json={
            'username': 'vermieter',
            'password': 'lang-genug-123',
            'password2': 'lang-genug-123',
            'code': code,
        })
        assert erste.status_code == 201

        andere = app_ctx_client(frischer_client)
        wiederholung_json = andere.post('/einrichtung', json={
            'username': 'spaeter',
            'password': 'lang-genug-123',
            'password2': 'lang-genug-123',
            'code': code,
        })
        assert wiederholung_json.status_code == 409
        wiederholung_seite = andere.get('/einrichtung')
        assert wiederholung_seite.status_code in (301, 302, 303, 307, 308)
        assert '/login' in wiederholung_seite.headers['Location']
    assert kontozaehler() == 1
    assert User.query.filter_by(username='spaeter').first() is None


def app_ctx_client(vorlage):
    """Ein zweiter Client derselben Anwendung, ohne die Sitzung des ersten."""
    return vorlage.application.test_client()


def test_passwortregeln_gelten_im_assistenten(frischer_client, caplog):
    """Zu kurz, ungleich, ohne Namen, zu langer Name: abgewiesen, ohne
    Konto. Dieselben Regeln wie im CLI, damit es keine Schattentuere gibt."""
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        faelle = [
            ({'username': 'vermieter', 'password': 'zu-kurz',
              'password2': 'zu-kurz', 'code': code},
             '10 Zeichen'),
            ({'username': 'vermieter', 'password': 'lang-genug-123',
              'password2': 'andere-lang-123', 'code': code},
             'überein'),
            ({'username': '  ', 'password': 'lang-genug-123',
              'password2': 'lang-genug-123', 'code': code},
             'Benutzernamen'),
            ({'username': 'x' * 41, 'password': 'lang-genug-123',
              'password2': 'lang-genug-123', 'code': code},
             '40 Zeichen'),
        ]
        for daten, stueck in faelle:
            antwort = frischer_client.post('/einrichtung', json=daten)
            assert antwort.status_code == 400, daten['username']
            assert stueck in antwort.get_json()['error']
    assert kontozaehler() == 0


def test_mit_konto_leitet_die_einrichtung_zur_anmeldung(auth_client):
    """Die offene Route ist nur der erste Start. Danach zeigt sie auf die
    Anmeldung und nimmt keinen POST mehr an (409)."""
    seite = auth_client.get('/einrichtung')
    assert seite.status_code in (301, 302, 303, 307, 308)
    assert '/login' in seite.headers['Location']
    post = auth_client.post('/einrichtung', json={'username': 'x'})
    assert post.status_code == 409


# --- Passwort aendern in der Oberflaeche ---

def test_passwort_aendern_braucht_das_alte_passwort(auth_client):
    antwort = auth_client.put('/api/konto/passwort', json={
        'altes_passwort': 'falsch-und-lang',
        'neues_passwort': 'ganz-neu-lang-123',
    })
    assert antwort.status_code == 400
    user = User.query.filter_by(username='pytest-vermieter').first()
    assert user.check_password('pytest-passwort-1')


def test_passwort_aendern_haelt_die_mindestlaenge_ein(auth_client):
    antwort = auth_client.put('/api/konto/passwort', json={
        'altes_passwort': 'pytest-passwort-1',
        'neues_passwort': 'zu-kurz',
    })
    assert antwort.status_code == 400
    assert '10 Zeichen' in antwort.get_json()['error']


def test_passwort_aendern_legt_neues_passwort_fest(auth_client, app_ctx):
    antwort = auth_client.put('/api/konto/passwort', json={
        'altes_passwort': 'pytest-passwort-1',
        'neues_passwort': 'ganz-neu-lang-123',
    })
    assert antwort.status_code == 200

    user = User.query.filter_by(username='pytest-vermieter').first()
    assert user.check_password('ganz-neu-lang-123')
    assert not user.check_password('pytest-passwort-1')

    # Alte Anmeldung tut es nicht mehr, neue schon.
    alt = app_ctx.app.test_client()
    assert alt.post('/login', json={
        'username': 'pytest-vermieter', 'password': 'pytest-passwort-1'
    }).status_code == 401
    neu = app_ctx.app.test_client()
    assert neu.post('/login', json={
        'username': 'pytest-vermieter', 'password': 'ganz-neu-lang-123'
    }).status_code == 200


def test_passwort_aendern_braucht_eine_sitzung(anon_client):
    antwort = anon_client.put('/api/konto/passwort', json={
        'altes_passwort': 'x', 'neues_passwort': 'y' * 10})
    assert antwort.status_code == 401


# --- Das zweite Konto ---

def test_zweites_konto_anlegen_und_anmelden(auth_client):
    antwort = auth_client.post('/api/konten', json={
        'username': 'partner', 'password': 'partner-passwort'})
    assert antwort.status_code == 201

    neu = auth_client.application.test_client()
    anmeldung = neu.post('/login', json={
        'username': 'partner', 'password': 'partner-passwort'})
    assert anmeldung.status_code == 200


def test_drittes_konto_wird_abgewiesen(auth_client):
    """ZIEL § 8: zwei Konten reichen, Wohnungsverwaltung ist keine
    Mandantenverwaltung."""
    for name in ('partner', 'dritter'):
        auth_client.post('/api/konten', json={
            'username': name, 'password': 'lang-passwort-1'})
    assert kontozaehler() == 2
    abweisung = auth_client.post('/api/konten', json={
        'username': 'vierter', 'password': 'lang-passwort-1'})
    assert abweisung.status_code == 400
    assert kontozaehler() == 2


def test_doppelname_und_leerer_name_sind_abgewiesen(auth_client):
    auth_client.post('/api/konten', json={
        'username': 'partner', 'password': 'lang-passwort-1'})
    doppel = auth_client.post('/api/konten', json={
        'username': 'partner', 'password': 'lang-passwort-2'})
    assert doppel.status_code == 400
    leer = auth_client.post('/api/konten', json={
        'username': '   ', 'password': 'lang-passwort-1'})
    assert leer.status_code == 400
    assert kontozaehler() == 2  # pytest-vermieter + partner


def test_kontenliste_zeigt_benutzername_und_stand(auth_client):
    antwort = auth_client.get('/api/konten')
    assert antwort.status_code == 200
    zeilen = antwort.get_json()
    assert [z['username'] for z in zeilen] == ['pytest-vermieter']
    assert zeilen[0]['is_active'] is True
    assert zeilen[0]['last_login_at'] is not None


def test_kontorouten_brauchen_eine_sitzung(anon_client):
    assert anon_client.get('/api/konten').status_code == 401
    assert anon_client.post('/api/konten', json={
        'username': 'x', 'password': 'y' * 10}).status_code == 401


# --- Passwort vergessen: lokaler Zugriff uebers CLI ---

def test_flask_users_passwd_setzt_das_passwort_zurueck(app_ctx, auth_client):
    """E-1: Passwort vergessen bleibt Sache des Servers. Der Befehl braucht
    lokalen Zugriff auf den Container, lokaler Zugriff gilt als Berechtigung."""
    runner = app_ctx.app.test_cli_runner()
    ergebnis = runner.invoke(
        args=['users', 'passwd', 'pytest-vermieter',
              '--password', 'wieder-neu-123'])
    assert ergebnis.exit_code == 0, ergebnis.output

    alt = app_ctx.app.test_client()
    assert alt.post('/login', json={
        'username': 'pytest-vermieter', 'password': 'pytest-passwort-1'
    }).status_code == 401
    neu = app_ctx.app.test_client()
    assert neu.post('/login', json={
        'username': 'pytest-vermieter', 'password': 'wieder-neu-123'
    }).status_code == 200


# --- NK-149: zwei Arbeiter, Versuchsgrenze, Maskierung (F-73, F-74, F-75) ---

def _arbeiter_wechseln(auth):
    """Ahmt den zweiten gunicorn-Arbeiter nach: eigener Prozessspeicher,
    aber derselbe Datenordner. Bis NK-149 kannte er den Code nicht."""
    auth._ersteinrichtung.update(code=None, fehlversuche=0, protokolliert=None)


def test_zwei_arbeiter_teilen_den_einmal_code(frischer_client, caplog):
    """F-73: Arbeiter A zeigt die Seite und protokolliert den Code, Arbeiter
    B bekommt das Formular. Der Code aus A's Protokoll muss bei B gelten."""
    from nebenkostenfix import auth
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        _arbeiter_wechseln(auth)
        antwort = frischer_client.post('/einrichtung', json={
            'username': 'vermieter', 'password': 'lang-genug-123',
            'password2': 'lang-genug-123', 'code': code})
    assert antwort.status_code == 201, antwort.get_json()


def test_der_zweite_arbeiter_protokolliert_denselben_code(frischer_client, caplog):
    """Nach einem Neustart soll der Code im frischen Log stehen -- jeder
    Prozess nennt ihn einmal, und es ist immer derselbe."""
    from nebenkostenfix import auth
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        erster = code_aus_protokoll(caplog)
        caplog.clear()
        _arbeiter_wechseln(auth)
        frischer_client.get('/einrichtung')
        zweiter = code_aus_protokoll(caplog)
    assert erster == zweiter


def test_die_code_datei_ist_nur_fuer_den_besitzer_lesbar(frischer_client):
    from nebenkostenfix import auth
    frischer_client.get('/einrichtung')
    pfad = auth._code_ablage()
    assert os.path.exists(pfad)
    if os.name == 'posix':
        assert os.stat(pfad).st_mode & 0o777 == 0o600


def test_nach_fuenf_fehlversuchen_gilt_ein_neuer_code(frischer_client, caplog):
    """F-75: Raten lohnt nicht. Nach fuenf Fehlversuchen ist der alte Code
    wertlos, der neue steht im Protokoll -- auch fuer den anderen Arbeiter."""
    from nebenkostenfix import auth
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        alt = code_aus_protokoll(caplog)
        caplog.clear()
        for nummer in range(auth.EINMAL_CODE_VERSUCHE):
            if nummer == 2:
                _arbeiter_wechseln(auth)  # der Zaehler ist geteilt
            antwort = frischer_client.post('/einrichtung', json={
                'username': 'vermieter', 'password': 'lang-genug-123',
                'password2': 'lang-genug-123', 'code': 'ffff-ffff-ffff-ffff'})
            assert antwort.status_code == 400
        neu_zeilen = [e.getMessage() for e in caplog.records
                      if 'Fehlversuchen' in e.getMessage()
                      and 'lautet' in e.getMessage()]
        assert neu_zeilen, 'Der neue Code steht nicht im Protokoll.'
        neu = '-'.join(CODE_MUSTER.search(neu_zeilen[-1]).groups())
        assert neu != alt
        alter_versuch = frischer_client.post('/einrichtung', json={
            'username': 'vermieter', 'password': 'lang-genug-123',
            'password2': 'lang-genug-123', 'code': alt})
        assert alter_versuch.status_code == 400
        neuer_versuch = frischer_client.post('/einrichtung', json={
            'username': 'vermieter', 'password': 'lang-genug-123',
            'password2': 'lang-genug-123', 'code': neu})
    assert neuer_versuch.status_code == 201


def test_die_einrichtung_vergleicht_in_konstanter_zeit():
    """F-75: kein == auf dem Geheimnis, sondern hmac.compare_digest."""
    import inspect

    from nebenkostenfix import auth
    quelle = inspect.getsource(auth._einmal_code_pruefen)
    assert 'compare_digest' in quelle


def test_fehlertexte_der_seiten_werden_maskiert():
    """F-75: Fehlertexte landen maskiert in der Seite."""
    from nebenkostenfix import auth
    seite = auth._einrichtungsseite('<script>alert(1)</script>')
    assert '<script>alert(1)' not in seite
    assert '&lt;script&gt;' in seite
    anmeldung = auth._login_page('<img src=x onerror=1>')
    assert '<img src=x' not in anmeldung


def test_nach_der_einrichtung_ist_die_code_datei_weg(frischer_client, caplog):
    from nebenkostenfix import auth
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
    frischer_client.post('/einrichtung', json={
        'username': 'vermieter', 'password': 'lang-genug-123',
        'password2': 'lang-genug-123', 'code': code})
    assert not os.path.exists(auth._code_ablage())


# --- NK-163: der Code als lesbare Datei im Datenordner ---

def _textdatei():
    from nebenkostenfix import auth
    return os.path.join(os.path.dirname(auth._code_ablage()), auth.EINMAL_CODE_TEXTDATEI)


def test_der_code_steht_lesbar_im_datenordner(frischer_client, caplog):
    """F-91: wer kein Protokoll lesen kann (Synology), findet den Code in
    der File Station -- derselbe Code wie im Protokoll."""
    with caplog.at_level(logging.WARNING):
        seite = frischer_client.get('/einrichtung').get_data(as_text=True)
        code = code_aus_protokoll(caplog)
    with open(_textdatei(), encoding='utf-8') as datei:
        inhalt = datei.read()
    assert code in inhalt and 'Einmal-Code' in inhalt
    assert 'ERSTEINRICHTUNG-CODE.txt' in seite and 'File Station' in seite
    assert code not in seite


def test_die_textdatei_folgt_dem_neuen_code(frischer_client, caplog):
    from nebenkostenfix import auth
    frischer_client.get('/einrichtung')
    with open(_textdatei(), encoding='utf-8') as datei:
        vorher = datei.read()
    for _ in range(auth.EINMAL_CODE_VERSUCHE):
        frischer_client.post('/einrichtung', json={
            'username': 'vermieter', 'password': 'lang-genug-123',
            'password2': 'lang-genug-123', 'code': 'ffff-ffff-ffff-ffff'})
    with open(_textdatei(), encoding='utf-8') as datei:
        nachher = datei.read()
    assert nachher != vorher
    with open(auth._code_ablage(), encoding='utf-8') as datei:
        neu = __import__('json').load(datei)['code']
    assert auth._code_anzeige(neu) in nachher


def test_nach_der_einrichtung_ist_die_textdatei_weg(frischer_client, caplog):
    with caplog.at_level(logging.WARNING):
        frischer_client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
    assert os.path.exists(_textdatei())
    frischer_client.post('/einrichtung', json={
        'username': 'vermieter', 'password': 'lang-genug-123',
        'password2': 'lang-genug-123', 'code': code})
    assert not os.path.exists(_textdatei())

