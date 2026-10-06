"""NK-198: der offene Modus serverseitig.

D-118: Die Windows-App läuft ohne Anmeldung, Docker mit -- solange der
Betreiber nichts anderes gewählt hat (Schalter ``ohne_anmeldung`` aus
NK-197). ``None`` heißt Plattform-Vorgabe, ``True``/``False`` heißt
ausdrücklich gewählt. Offen heißt schließlich: kein Konto in der Datenbank
UND der wirksame Schalter verlangt es -- ein Konto gewinnt immer.

Die Tests stellen Plattform und Schalter je Test ein (Datenordner per
monkeypatch, Plattform über app.config) und prüfen: Wer ohne Konto offen
ist, erreicht alles ohne Sitzung; die Konto-Routen verweigern den Dienst;
der Fremdschutz (F-57) bleibt.
"""

import json
import logging
import re
import shutil
import time
from pathlib import Path

import pytest

from nebenkostenfix import umzug
from nebenkostenfix.models import User, db

CODE_MUSTER = re.compile(
    r'\b([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})\b')
FEHLTEXT = ('Die Anmeldung ist ausgeschaltet. Schalten Sie sie in den '
            'Einstellungen unter „Konto“ ein.')


@pytest.fixture(autouse=True)
def ordner(tmp_path, monkeypatch):
    """Ein eigener Datenordner je Test (Einstellungen, Einmal-Code)."""
    from nebenkostenfix import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    return tmp_path


def auth_zuruecksetzen():
    """In-Memory-Zustand des Einmal-Codes leeren (Prozessstart nachahmen)."""
    from nebenkostenfix import auth
    auth._ersteinrichtung.update(code=None, fehlversuche=0, protokolliert=None)


@pytest.fixture(autouse=True)
def code_frisch(ordner):
    auth_zuruecksetzen()
    yield
    auth_zuruecksetzen()


@pytest.fixture(autouse=True)
def warn_merker_frisch(app_ctx):
    """Der Warnungs-Merker liegt an der App, die alle Tests teilen."""
    app_ctx.app.extensions.pop('_ohne_anmeldung_gewarnt', None)
    yield
    app_ctx.app.extensions.pop('_ohne_anmeldung_gewarnt', None)


def desktop_setzen(app_ctx, monkeypatch, desktop):
    monkeypatch.setitem(app_ctx.app.config, 'DESKTOP', desktop)


def schalter_setzen(wert):
    from nebenkostenfix import einstellungen
    einstellungen.schreiben(ohne_anmeldung=wert)


def schalter():
    from nebenkostenfix import einstellungen
    return einstellungen.lesen()['ohne_anmeldung']


def code_aus_protokoll(caplog):
    zeilen = [eintrag.getMessage() for eintrag in caplog.records
              if 'Einmal-Code' in eintrag.getMessage()]
    assert zeilen, 'Der Start hat den Einmal-Code nicht protokolliert.'
    treffer = CODE_MUSTER.search(zeilen[0])
    assert treffer, f'Kein Code in der Protokollzeile: {zeilen[0]!r}'
    return '-'.join(treffer.groups())


def fehlversuche():
    from nebenkostenfix import auth
    with auth._CodeZustand(auth._code_ablage()) as ablage:
        zustand = ablage.lesen()
    return zustand['fehlversuche'] if zustand else 0


# --- Windows frisch: offen -------------------------------------------------------

def test_windows_frisch_ist_offen(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/api/properties').status_code == 200
    login = client.get('/login')
    assert login.status_code in (301, 302, 303, 307, 308)
    assert login.headers['Location'].endswith('/')


# --- Docker frisch: gesperrt, Einrichtung mit beiden Wegen -----------------------

def test_docker_frisch_bleibt_gesperrt(app_ctx, monkeypatch, caplog):
    desktop_setzen(app_ctx, monkeypatch, False)
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 401
    with caplog.at_level(logging.WARNING):
        login = client.get('/login')
    assert login.status_code in (301, 302, 303, 307, 308)
    assert '/einrichtung' in login.headers['Location']
    seite = client.get('/einrichtung')
    text = seite.get_data(as_text=True)
    assert 'Konto anlegen' in text
    assert 'Ohne Anmeldung fortfahren' in text
    assert 'name="code"' in text


# --- Docker: der Knopf braucht den Einmal-Code -----------------------------------

def test_docker_knopf_braucht_code(app_ctx, monkeypatch, caplog):
    desktop_setzen(app_ctx, monkeypatch, False)
    client = app_ctx.app.test_client()
    with caplog.at_level(logging.WARNING):
        client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
        # Ohne Code: abgelehnt, zählt als Fehlversuch.
        assert client.post('/einrichtung',
                           data={'ohne_anmeldung': '1'}).status_code == 400
        # Falscher Code: abgelehnt, zweiter Fehlversuch.
        assert client.post(
            '/einrichtung',
            data={'ohne_anmeldung': '1',
                  'code': '0000-0000-0000-0000'}).status_code == 400
    assert fehlversuche() == 2
    # Mit dem Code aus dem Protokoll: der offene Modus wird eingeschaltet.
    with caplog.at_level(logging.WARNING):
        antwort = client.post('/einrichtung',
                              data={'ohne_anmeldung': '1', 'code': code})
    assert antwort.status_code in (200, 302)
    assert schalter() is True
    assert client.get('/api/properties').status_code == 200


# --- Die Warnung: einmal je Prozess, nur in Docker --------------------------------

def test_warnung_genau_einmal_in_docker(app_ctx, monkeypatch, caplog):
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(True)
    client = app_ctx.app.test_client()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            client.get('/api/properties')
    warnungen = [e for e in caplog.records
                 if 'Anmeldung ist ausgeschaltet' in e.getMessage()]
    assert len(warnungen) == 1


def test_keine_warnung_in_der_windows_app(app_ctx, monkeypatch, caplog):
    desktop_setzen(app_ctx, monkeypatch, True)
    schalter_setzen(True)
    client = app_ctx.app.test_client()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            client.get('/api/properties')
    assert not [e for e in caplog.records
                if 'Anmeldung ist ausgeschaltet' in e.getMessage()]


# --- Windows mit Schalter False: Einrichtung wie bisher plus Knopf ----------------

def test_windows_mit_schalter_false(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    schalter_setzen(False)
    client = app_ctx.app.test_client()
    seite = client.get('/einrichtung')
    assert seite.status_code == 200
    text = seite.get_data(as_text=True)
    assert 'Konto anlegen' in text
    assert 'Ohne Anmeldung fortfahren' in text
    assert 'name="code"' not in text
    # Der Knopf öffnet die App -- ohne Code, die Windows-App braucht keinen.
    antwort = client.post('/einrichtung', data={'ohne_anmeldung': '1'})
    assert antwort.status_code in (200, 302)
    assert schalter() is True
    assert client.get('/').status_code == 200


# --- Ein Konto gewinnt immer -------------------------------------------------------

@pytest.mark.parametrize('desktop', [True, False])
def test_bestand_mit_konto_bleibt_gesperrt(app_ctx, monkeypatch, desktop):
    desktop_setzen(app_ctx, monkeypatch, desktop)
    user = User(username='fabi')
    user.set_password('langgenug12345')
    db.session.add(user)
    db.session.commit()
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 401


def test_schalter_true_plus_konto_gesperrt(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    schalter_setzen(True)
    user = User(username='fabi')
    user.set_password('langgenug12345')
    db.session.add(user)
    db.session.commit()
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 401


def test_schalter_true_plus_stillgelegtes_konto_gesperrt(app_ctx,
                                                         monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    schalter_setzen(True)
    user = User(username='fabi')
    user.set_password('langgenug12345')
    user.is_active = False
    db.session.add(user)
    db.session.commit()
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 401


# --- Der Fremdschutz bleibt --------------------------------------------------------

def test_fremder_ursprung_gilt_im_offenen_modus(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    antwort = client.post('/api/properties',
                          headers={'Origin': 'https://boese.example'})
    assert antwort.status_code == 403
    assert antwort.get_json()['code'] == 'fremder_ursprung'


# --- Die Einrichtungsseite im offenen Modus ---------------------------------------

def test_einrichtung_get_offen_nur_kontoformular(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    text = client.get('/einrichtung').get_data(as_text=True)
    assert 'Konto anlegen' in text
    assert 'name="ohne_anmeldung"' not in text
    assert 'umzug-form' not in text


def test_einrichtung_post_ohne_anmeldung_offen_aendert_nichts(
        app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    antwort = client.post('/einrichtung', data={'ohne_anmeldung': '1'})
    assert antwort.status_code in (200, 302)
    if antwort.status_code in (301, 302, 303, 307, 308):
        assert antwort.headers['Location'].endswith('/')
    assert schalter() is None


# --- Kontoanlage im offenen Modus ---------------------------------------------------

def test_kontoanlage_im_offenen_modus_windows(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    assert client.post('/einrichtung', json={
        'username': 'fabi',
        'password': 'langgenug12345',
        'password2': 'langgenug12345'}).status_code == 201
    assert schalter() is False
    zweiter = app_ctx.app.test_client()
    assert zweiter.get('/api/properties').status_code == 401
    assert client.get('/api/properties').status_code == 200


def test_kontoanlage_im_offenen_modus_docker_mit_code(app_ctx, monkeypatch,
                                                      caplog):
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(True)
    client = app_ctx.app.test_client()
    with caplog.at_level(logging.WARNING):
        client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
    assert client.post('/einrichtung', json={
        'username': 'fabi', 'password': 'langgenug12345',
        'password2': 'langgenug12345',
        'code': code}).status_code == 201
    assert schalter() is False
    zweiter = app_ctx.app.test_client()
    assert zweiter.get('/api/properties').status_code == 401


# --- /api/auth/me -------------------------------------------------------------------

def test_auth_me_offen(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    antwort = client.get('/api/auth/me')
    assert antwort.status_code == 200
    daten = antwort.get_json()
    assert daten['username'] is None
    assert daten['ohne_anmeldung'] is True
    assert daten['last_login_at'] is None


def test_auth_me_angemeldet(app_ctx, monkeypatch):
    user = User(username='fabi')
    user.set_password('langgenug12345')
    db.session.add(user)
    db.session.commit()
    client = app_ctx.app.test_client()
    assert client.post('/login', json={
        'username': 'fabi',
        'password': 'langgenug12345'}).status_code == 200
    antwort = client.get('/api/auth/me')
    assert antwort.status_code == 200
    assert antwort.get_json()['ohne_anmeldung'] is False


# --- Konto-Routen verweigern den Dienst ---------------------------------------------

def test_konto_routen_offen(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    passwort = client.put('/api/konto/passwort',
                          json={'altes_passwort': 'x', 'neues_passwort': 'y'})
    assert passwort.status_code == 409
    assert passwort.get_json()['error'] == FEHLTEXT
    anlegen = client.post('/api/konten', json={
        'username': 'zweiter', 'password': 'langgenug12345'})
    assert anlegen.status_code == 409
    assert anlegen.get_json()['error'] == FEHLTEXT
    liste = client.get('/api/konten')
    assert liste.status_code == 200
    assert liste.get_json() == []


# --- NK-199: die Anmeldung im Betrieb ausschalten ------------------------------------

PFAD_AUS = '/api/anmeldung/aus'
PASSWORT = 'langgenug12345'


def konto(name='fabi'):
    user = User(username=name)
    user.set_password(PASSWORT)
    db.session.add(user)
    db.session.commit()
    return user


def angemeldet(app_ctx, name='fabi'):
    client = app_ctx.app.test_client()
    assert client.post('/login', json={
        'username': name, 'password': PASSWORT}).status_code == 200
    return client


def test_ausschalten_ohne_sitzung_401(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    konto()
    antwort = app_ctx.app.test_client().post(
        PFAD_AUS, json={'password': PASSWORT})
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'auth_required'
    assert User.query.count() == 1


def test_ausschalten_offen_409(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(True)
    antwort = app_ctx.app.test_client().post(
        PFAD_AUS, json={'password': PASSWORT})
    assert antwort.status_code == 409
    assert antwort.get_json()['error'] == 'Die Anmeldung ist schon ausgeschaltet.'


def test_ausschalten_falsches_passwort_403(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    konto()
    client = angemeldet(app_ctx)
    antwort = client.post(PFAD_AUS, json={'password': 'falschespasswort1'})
    assert antwort.status_code == 403
    assert antwort.get_json()['error'] == 'Das Passwort stimmt nicht.'
    assert User.query.count() == 1
    assert schalter() is None


def test_ausschalten_windows(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    konto()
    client = angemeldet(app_ctx)
    antwort = client.post(PFAD_AUS, json={'password': PASSWORT})
    assert antwort.status_code == 200
    daten = antwort.get_json()
    assert daten['ohne_anmeldung'] is True
    assert daten['geloescht'] == 1
    assert User.query.count() == 0
    assert schalter() is True
    assert app_ctx.app.test_client().get('/api/properties').status_code == 200


def test_ausschalten_docker_warnt_im_protokoll(app_ctx, monkeypatch, caplog):
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(False)
    konto()
    client = angemeldet(app_ctx)
    antwort = client.post(PFAD_AUS, json={'password': PASSWORT})
    assert antwort.status_code == 200
    assert antwort.get_json()['ohne_anmeldung'] is True
    assert User.query.count() == 0
    assert schalter() is True
    warnungen = [e for e in caplog.records
                 if 'Anmeldung ist ausgeschaltet' in e.getMessage()]
    assert warnungen, 'Der Ausschalten-Warnung fehlt im Protokoll.'
    assert app_ctx.app.test_client().get('/api/properties').status_code == 200


def test_ausschalten_löscht_beide_konten(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    konto()
    client = angemeldet(app_ctx)
    zweiter = app_ctx.app.test_client()
    assert zweiter.post('/login', json={
        'username': 'zweiter', 'password': PASSWORT}).status_code == 401
    assert client.post('/api/konten', json={
        'username': 'zweiter', 'password': PASSWORT}).status_code == 201
    assert zweiter.post('/login', json={
        'username': 'zweiter', 'password': PASSWORT}).status_code == 200
    antwort = client.post(PFAD_AUS, json={'password': PASSWORT})
    assert antwort.status_code == 200
    assert antwort.get_json()['geloescht'] == 2
    assert User.query.count() == 0
    # Der Client des zweiten Kontos arbeitet offen weiter, ohne Fehler.
    assert zweiter.get('/api/properties').status_code == 200


def test_ausschalten_fremder_ursprung_403(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    konto()
    client = angemeldet(app_ctx)
    antwort = client.post(PFAD_AUS, json={'password': PASSWORT},
                          headers={'Origin': 'https://boese.example'})
    assert antwort.status_code == 403
    assert User.query.count() == 1


def test_nach_ausschalten_neues_konto_sperrt_wieder(app_ctx, monkeypatch,
                                                    caplog):
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(False)
    konto()
    client = angemeldet(app_ctx)
    assert client.post(PFAD_AUS, json={'password': PASSWORT}).status_code == 200
    with caplog.at_level(logging.WARNING):
        client.get('/einrichtung')
        code = code_aus_protokoll(caplog)
    assert client.post('/einrichtung', json={
        'username': 'fabi', 'password': PASSWORT,
        'password2': PASSWORT, 'code': code}).status_code == 201
    assert schalter() is False
    assert app_ctx.app.test_client().get('/api/properties').status_code == 401


def test_sperre_von_vorher_gilt_nach_aus_nicht_mehr(app_ctx, monkeypatch):
    from nebenkostenfix import anmeldeschutz, auth
    desktop_setzen(app_ctx, monkeypatch, True)
    konto()
    client = angemeldet(app_ctx)
    ordner = auth._anmeldeschutz_ordner()
    for _ in range(5):
        anmeldeschutz.fehlversuch(ordner, 'fabi', '127.0.0.1')
    assert anmeldeschutz.gesperrt_fuer(ordner, 'fabi', '127.0.0.1') > 0
    assert client.post(PFAD_AUS, json={'password': PASSWORT}).status_code == 200
    assert client.post('/einrichtung', json={
        'username': 'fabi', 'password': PASSWORT,
        'password2': PASSWORT}).status_code == 201
    assert anmeldeschutz.gesperrt_fuer(ordner, 'fabi', '127.0.0.1') == 0


# --- Die Huelle ohne Passwort --------------------------------------------------------

def test_huelle_passwort_ohne_konto(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    seite = client.get('/huelle/passwort')
    assert seite.status_code == 200
    text = seite.get_data(as_text=True)
    assert 'Die Anmeldung ist ausgeschaltet, es gibt kein Passwort.' in text
    assert 'Passwort speichern' not in text


# --- CLI -----------------------------------------------------------------------------

def test_cli_users_add_schaltet_auf_anmeldung(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    runner = app_ctx.app.test_cli_runner()
    resultat = runner.invoke(
        args=['users', 'add', 'fabi', '--password', 'langgenug12345'])
    assert resultat.exit_code == 0, resultat.output
    assert schalter() is False
    assert app_ctx.app.test_client().get('/api/properties').status_code == 401


# --- Alte Sitzungen ------------------------------------------------------------------

def test_alte_sitzung_wird_geleert(app_ctx, monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1   # nie angelegt
    assert client.get('/api/properties').status_code == 200
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_abgelaufene_sitzung_stoert_im_offenen_modus_nicht(app_ctx,
                                                           monkeypatch):
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    with client.session_transaction() as sess:
        sess['aktiv'] = int(time.time()) - 7200
    assert client.get('/api/properties').status_code == 200


# --- Umzug und Sicherung im offenen Modus (NK-200) --------------------------------
#
# Quelle und Ziel sind zwei Phasen desselben Tests: die Quelle schreibt ein
# Paket (Plattform, Konto und Schalter so, wie der Fall es verlangt), dann
# stellt _ziel_einstellen die Instanz auf den Zielstand zurück. So macht es
# auch tests/test_umzug.py -- eine zweite App-Instanz wäre dasselbe Programm
# in einem anderen Prozess, die Werkzeuge hier (Datenordner-Monkeypatch,
# Plattform über app.config) sparen die und messen dieselben Wege.

QUER_USER = 'umzug-quelle'
QUER_PASS = 'umzug-quelle-123'
ZIEL_USER = 'umzug-ziel'
ZIEL_PASS = 'umzug-ziel-12345'

HAUS = 'Umzugshaus im Test'


@pytest.fixture
def umzug_statt(app_ctx, monkeypatch):
    """Stempel für Pakete und ein Stück-Upload, das ein ganzes Paket trägt."""
    from flask_migrate import stamp

    from nebenkostenfix import umzug
    stamp(revision='head')
    monkeypatch.setattr(umzug, 'STUECK', 1 << 20)
    umzug._freigegeben.clear()
    yield app_ctx
    umzug._freigegeben.clear()


def _konto(name, passwort):
    konto = User(username=name)
    konto.set_password(passwort)
    db.session.add(konto)
    db.session.commit()
    return konto


def _vor_der_einrichtung_machen():
    """Kein Konto: die Instanz steht vor der Einrichtung."""
    User.query.delete()
    db.session.commit()


def _einstellungsdatei_weg():
    from nebenkostenfix import datenordner
    (datenordner.datenordner() / 'einstellungen.json').unlink(missing_ok=True)


def _haus():
    from nebenkostenfix.models import Property
    if Property.query.count() == 0:
        db.session.add(Property(name=HAUS))
        db.session.commit()


def _quellpaket(app, tmp_path, name='Quelle.nkfix'):
    from nebenkostenfix import umzug
    return umzug.paket_erstellen(app, tmp_path / name)


def _ziel_einstellen(app_ctx, monkeypatch, desktop, schalter_wert=None):
    """Frischer Zielstand: kein Konto, keine Einstellungsdatei, Plattform ein."""
    _vor_der_einrichtung_machen()
    _einstellungsdatei_weg()
    desktop_setzen(app_ctx, monkeypatch, desktop)
    if schalter_wert is not None:
        schalter_setzen(schalter_wert)


def _paket_hinlegen(app, paket, name='Umzug.nkfix') -> str:
    """Legt das Paket in den Importordner und liefert den Namen für die Route."""
    import shutil
    from nebenkostenfix import umzug
    ordner = umzug.importordner(app)
    ordner.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paket, ordner / name)
    return name


def _umbauen(paket, ziel, aendern=None):
    """Paket aus- und wieder einpacken; dazwischen darf man pfuschen."""
    import zipfile
    from pathlib import Path
    with zipfile.ZipFile(paket) as quelle:
        inhalt = {name: quelle.read(name) for name in quelle.namelist()}
    if aendern:
        aendern(inhalt)
    with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as neu:
        for name, daten in inhalt.items():
            neu.writestr(name, daten)
    return Path(ziel)


def _anwendung_im_paket_aendern(aendern):
    """Pfuscht in einstellungen.json des Pakets und hält das Manifest aktuell."""
    import hashlib

    from nebenkostenfix import backup

    def schritt(inhalt):
        einstellungen = json.loads(inhalt[backup.EINSTELLUNGEN_IM_ARCHIV])
        aendern(einstellungen)
        neu = json.dumps(einstellungen).encode()
        inhalt[backup.EINSTELLUNGEN_IM_ARCHIV] = neu
        manifest = json.loads(inhalt[backup.MANIFEST_NAME])
        for eintrag in manifest.get('zusatz', []):
            if eintrag['pfad'] == backup.EINSTELLUNGEN_IM_ARCHIV:
                eintrag.update(groesse=len(neu),
                               sha256=hashlib.sha256(neu).hexdigest())
        inhalt[backup.MANIFEST_NAME] = json.dumps(manifest).encode()
    return schritt


def _manifest_aendern(aendern):
    from nebenkostenfix import backup

    def schritt(inhalt):
        manifest = json.loads(inhalt[backup.MANIFEST_NAME])
        aendern(manifest, inhalt)
        inhalt[backup.MANIFEST_NAME] = json.dumps(manifest).encode()
    return schritt


def _ueber_die_einrichtung(app, paket):
    """Frisches Docker-Ziel: Paket über die Einrichtungsseite mit Code einspielen."""
    from nebenkostenfix import auth
    client = app.test_client()
    client.get('/einrichtung')
    code = auth._einmal_code_legen(app)
    kopf = {'X-Einmal-Code': code}
    daten = paket.read_bytes()
    start = client.post('/api/umzug/hochladen', headers=kopf,
                        json={'groesse': len(daten), 'name': 'Umzug.nkfix'})
    assert start.status_code == 201, start.get_data(as_text=True)
    kennung = start.get_json()['id']
    stueck = start.get_json()['stueck']
    stueck_antwort = client.put(f'/api/umzug/hochladen/{kennung}?ab=0',
                                headers=kopf, data=daten[:stueck])
    assert stueck_antwort.status_code == 200, stueck_antwort.get_data(as_text=True)
    vorschau = client.post('/api/umzug/pruefen', headers=kopf,
                           json={'hochgeladen': kennung})
    assert vorschau.get_json()['einspielbar'] is True, vorschau.get_json()
    einspiel = client.post('/api/umzug/uebernehmen', headers=kopf,
                           json={'hochgeladen': kennung})
    assert einspiel.status_code == 200, einspiel.get_data(as_text=True)
    return einspiel.get_json()


def _daten_da(app):
    from sqlalchemy import text

    from nebenkostenfix.models import db
    with app.app_context():
        with db.engine.connect() as verbindung:
            namen = sorted(z[0] for z in verbindung.execute(
                text('SELECT name FROM properties')))
    return HAUS in namen


class _Sammler(logging.Handler):
    """Hört direkt am Anwendungs-Logger mit: die Wanderung eines Pakets
    konfiguriert das Protokoll neu (alembic fileConfig) und nimmt den
    pytest-Sammler von der Wurzel weg."""

    def __init__(self):
        super().__init__()
        self.zeilen = []

    def emit(self, satz):
        self.zeilen.append(satz.getMessage())


def test_umzug_1_windows_bestand_ohne_konto_zu_docker_frisch(
        app_ctx, umzug_statt, monkeypatch, tmp_path):
    """Windows-Bestand ohne Konto (exportiert True) geht an frisches Docker
    über die Einrichtungsseite mit Code. NK-206: der Import öffnet Docker
    nicht von selbst -- die Anmeldung bleibt an, das Protokoll sagt es, und
    offen wird es erst mit dem Knopf und einem neuen Einmal-Code."""
    from nebenkostenfix import auth

    desktop_setzen(app_ctx, monkeypatch, True)
    _haus()
    paket = _quellpaket(app_ctx.app, tmp_path)
    _ziel_einstellen(app_ctx, monkeypatch, False)
    sammler = _Sammler()
    app_ctx.app.logger.addHandler(sammler)
    try:
        bericht = _ueber_die_einrichtung(app_ctx.app, paket)
    finally:
        app_ctx.app.logger.removeHandler(sammler)
    assert bericht['anmelden'] is False, bericht
    assert bericht['ohne_anmeldung'] is False, bericht
    assert bericht['anmeldung_bleibt_an'] is True, bericht
    assert schalter() is False
    assert any('bleibt die Anmeldung an' in z for z in sammler.zeilen), sammler.zeilen
    assert _daten_da(app_ctx.app)
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 401
    client.get('/einrichtung')
    code = auth._einmal_code_legen(app_ctx.app)
    offen = client.post('/einrichtung', json={'ohne_anmeldung': True, 'code': code})
    assert offen.status_code == 200, offen.get_data(as_text=True)
    assert client.get('/api/properties').status_code == 200


def test_umzug_2_docker_bestand_mit_konto_zu_windows_frisch(
        app_ctx, umzug_statt, monkeypatch, tmp_path):
    """Docker-Bestand mit Konto an frisches Windows (offen, also mit
    ERSETZEN): die Anmeldung gilt, das Paketkonto meldet sich, das
    Ausschalten (NK-199) geht danach."""
    desktop_setzen(app_ctx, monkeypatch, False)
    _konto(QUER_USER, QUER_PASS)
    _haus()
    paket = _quellpaket(app_ctx.app, tmp_path)
    _ziel_einstellen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    name = _paket_hinlegen(app_ctx.app, paket)
    ohne = client.post('/api/umzug/uebernehmen', json={'importordner': name})
    assert ohne.status_code == 400, ohne.get_data(as_text=True)
    antwort = client.post('/api/umzug/uebernehmen',
                          json={'importordner': name, 'bestaetigung': 'ERSETZEN'})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert bericht['anmelden'] is True, bericht
    assert bericht['ohne_anmeldung'] is False, bericht
    assert client.post('/login', json={'username': QUER_USER,
                                       'password': QUER_PASS}).status_code == 200
    assert client.post('/api/anmeldung/aus',
                       json={'password': QUER_PASS}).status_code == 200
    assert schalter() is True


def test_umzug_3_docker_ohne_konto_zu_windows_schalter_false(
        app_ctx, umzug_statt, monkeypatch, tmp_path):
    """Docker-Bestand ohne Konto (exportiert False) an Windows: keine
    Anmeldung, Schalter aus, die Einrichtungsseite zeigt beide Knöpfe ohne
    Codefeld, die Daten aus dem Paket sind da."""
    desktop_setzen(app_ctx, monkeypatch, False)
    _haus()
    paket = _quellpaket(app_ctx.app, tmp_path)
    _ziel_einstellen(app_ctx, monkeypatch, True)
    bericht = umzug.uebernehmen(app_ctx.app, paket)
    assert bericht['anmelden'] is False, bericht
    assert bericht['ohne_anmeldung'] is False, bericht
    client = app_ctx.app.test_client()
    antwort = client.get('/login')
    assert antwort.status_code == 302
    assert antwort.headers['Location'].endswith('/einrichtung')
    seite = client.get('/einrichtung').get_data(as_text=True)
    assert 'umzug-form' in seite
    assert 'name="ohne_anmeldung"' in seite
    assert 'id="code"' not in seite
    assert _daten_da(app_ctx.app)


def test_umzug_4_docker_offen_zu_windows_offen(app_ctx, umzug_statt,
                                               monkeypatch, tmp_path):
    """Docker offen (Schalter True) an Windows: offen."""
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(True)
    _haus()
    paket = _quellpaket(app_ctx.app, tmp_path)
    _ziel_einstellen(app_ctx, monkeypatch, True)
    bericht = umzug.uebernehmen(app_ctx.app, paket)
    assert bericht['anmelden'] is False, bericht
    assert bericht['ohne_anmeldung'] is True, bericht
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 200


@pytest.mark.parametrize('desktop', [True, False], ids=['windows', 'docker'])
def test_umzug_5_ziel_mit_konto_paket_ohne_konto_true(app_ctx, umzug_statt,
                                                      monkeypatch, tmp_path,
                                                      desktop):
    """Ziel mit Konto, Paket ohne Konto mit True (ERSETZEN): Windows offen;
    Docker bleibt angemeldet (NK-206), bis die Einrichtung es anders will."""
    desktop_setzen(app_ctx, monkeypatch, True)
    _haus()
    paket = _quellpaket(app_ctx.app, tmp_path)
    _ziel_einstellen(app_ctx, monkeypatch, desktop)
    _konto(ZIEL_USER, ZIEL_PASS)
    client = app_ctx.app.test_client()
    assert client.post('/login', json={'username': ZIEL_USER,
                                       'password': ZIEL_PASS}).status_code == 200
    name = _paket_hinlegen(app_ctx.app, paket)
    ohne = client.post('/api/umzug/uebernehmen', json={'importordner': name})
    assert ohne.status_code == 400, ohne.get_data(as_text=True)
    antwort = client.post('/api/umzug/uebernehmen',
                          json={'importordner': name, 'bestaetigung': 'ERSETZEN'})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert bericht['anmelden'] is False, bericht
    assert bericht['ohne_anmeldung'] is desktop, bericht
    assert bericht['anmeldung_bleibt_an'] is not desktop, bericht
    assert client.get('/api/properties').status_code == (200 if desktop else 401)


def test_umzug_6_ziel_offen_paket_mit_konto(app_ctx, umzug_statt, monkeypatch,
                                            tmp_path):
    """Ziel offen, Paket mit Konto: ohne ERSETZEN 400, mit ERSETZEN 200,
    danach gilt die Anmeldung wieder."""
    desktop_setzen(app_ctx, monkeypatch, False)
    _konto(QUER_USER, QUER_PASS)
    _haus()
    paket = _quellpaket(app_ctx.app, tmp_path)
    _ziel_einstellen(app_ctx, monkeypatch, False, schalter_wert=True)
    client = app_ctx.app.test_client()
    name = _paket_hinlegen(app_ctx.app, paket)
    ohne = client.post('/api/umzug/uebernehmen', json={'importordner': name})
    assert ohne.status_code == 400, ohne.get_data(as_text=True)
    antwort = client.post('/api/umzug/uebernehmen',
                          json={'importordner': name, 'bestaetigung': 'ERSETZEN'})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['anmelden'] is True
    assert client.get('/api/properties').status_code == 401
    assert client.post('/login', json={'username': QUER_USER,
                                       'password': QUER_PASS}).status_code == 200


@pytest.mark.parametrize('art', ['format1', 'nkbak', 'tar'],
                         ids=['format-1', '.nkbak', '.tar.gz'])
def test_umzug_7_alte_pakete_mit_konto_auf_offenes_ziel(
        app_ctx, umzug_statt, monkeypatch, tmp_path, art):
    """Alte Pakete ohne den Schalter, aber mit Konto, an ein offenes Ziel:
    die Anmeldung gilt."""
    from nebenkostenfix import backup
    from nebenkostenfix import verschluesselung

    desktop_setzen(app_ctx, monkeypatch, False)
    _konto(QUER_USER, QUER_PASS)
    _haus()
    if art == 'tar':
        paket = backup.sicherung_erstellen(app_ctx.app, tmp_path, art='tar')
        passwort = None
    else:
        roh = _quellpaket(app_ctx.app, tmp_path, name='Roh.nkfix')
        if art == 'format1':
            paket = _umbauen(roh, tmp_path / 'alt.nkfix',
                             _manifest_aendern(lambda m, _: m.update(format=1)))
            passwort = None
        else:
            paket = tmp_path / 'alt.nkbak'
            verschluesselung.verschluesseln(
                roh, paket, 'eine lange passphrase',
                {'format': 2, 'anwendung': backup.ANWENDUNG, 'behaelter': 'zip'})
            passwort = 'eine lange passphrase'
    _ziel_einstellen(app_ctx, monkeypatch, False, schalter_wert=True)
    bericht = umzug.uebernehmen(app_ctx.app, paket, passwort)
    assert bericht['anmelden'] is True, bericht
    assert bericht['ohne_anmeldung'] is False, bericht
    client = app_ctx.app.test_client()
    assert client.post('/login', json={'username': QUER_USER,
                                       'password': QUER_PASS}).status_code == 200


@pytest.mark.parametrize('desktop', [True, False], ids=['windows', 'docker'])
def test_umzug_8_altes_paket_ohne_schluessel_ohne_konto(
        app_ctx, umzug_statt, monkeypatch, tmp_path, desktop):
    """Altes Paket ohne Schalter und ohne Konto: am Windows-Ziel mit None
    ist es offen, am Docker-Ziel mit None steht die Einrichtung."""
    desktop_setzen(app_ctx, monkeypatch, True)
    _haus()
    roh = _quellpaket(app_ctx.app, tmp_path)
    paket = _umbauen(roh, tmp_path / 'alt.nkfix',
                     _anwendung_im_paket_aendern(
                         lambda werte: werte['anwendung'].pop('ohne_anmeldung')))
    _ziel_einstellen(app_ctx, monkeypatch, desktop)
    bericht = umzug.uebernehmen(app_ctx.app, paket)
    assert bericht['anmelden'] is False, bericht
    assert schalter() is None
    client = app_ctx.app.test_client()
    if desktop:
        assert bericht['ohne_anmeldung'] is True, bericht
        assert client.get('/api/properties').status_code == 200
    else:
        assert bericht['ohne_anmeldung'] is False, bericht
        assert client.get('/api/properties').status_code == 401
        seite = client.get('/einrichtung').get_data(as_text=True)
        assert 'id="umzug-code"' in seite
    assert _daten_da(app_ctx.app)


def test_umzug_9_manipuliertes_paket_true_und_konto(app_ctx, umzug_statt,
                                                    monkeypatch, tmp_path):
    """Ein Paket, das True und ein Konto zugleich behauptet, fährt nicht den
    offenen Modus: das Konto gewinnt immer."""
    desktop_setzen(app_ctx, monkeypatch, False)
    _konto(QUER_USER, QUER_PASS)
    _haus()
    roh = _quellpaket(app_ctx.app, tmp_path)
    paket = _umbauen(roh, tmp_path / 'geflickt.nkfix',
                     _anwendung_im_paket_aendern(
                         lambda werte: werte['anwendung'].update(
                             ohne_anmeldung=True)))
    _ziel_einstellen(app_ctx, monkeypatch, True)
    bericht = umzug.uebernehmen(app_ctx.app, paket)
    assert bericht['anmelden'] is True, bericht
    assert bericht['ohne_anmeldung'] is False, bericht
    client = app_ctx.app.test_client()
    assert client.get('/api/properties').status_code == 401


def test_umzug_10_sicherung_offen_rundlauf(app_ctx, umzug_statt, monkeypatch):
    """Sicherung im offenen Modus erstellen und zurückspielen: es bleibt offen."""
    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(True)
    client = app_ctx.app.test_client()
    erstellt = client.post('/api/backup/erstellen', json={})
    assert erstellt.status_code == 201, erstellt.get_data(as_text=True)
    name = erstellt.get_json()['name']
    einspiel = client.post('/api/backup/einspielen', json={'name': name})
    assert einspiel.status_code == 200, einspiel.get_data(as_text=True)
    assert client.get('/api/properties').status_code == 200
    assert schalter() is True


def test_umzug_11_alte_sicherung_mit_konto_offenes_ziel(
        app_ctx, umzug_statt, monkeypatch):
    """Alte Sicherung mit Konto im offenen Modus zurückgespielt: die
    Anmeldung gilt; /huelle/passwort zeigt wieder das Formular (bestehender
    Weg „Passwort vergessen …“)."""
    from nebenkostenfix import backup

    desktop_setzen(app_ctx, monkeypatch, False)
    _konto(QUER_USER, QUER_PASS)
    _haus()
    ziel = backup.standardziel(app_ctx.app)
    alt = backup.sicherung_erstellen(app_ctx.app, ziel, art='tar')
    _ziel_einstellen(app_ctx, monkeypatch, True, schalter_wert=True)
    client = app_ctx.app.test_client()
    einspiel = client.post('/api/backup/einspielen', json={'name': alt.name})
    assert einspiel.status_code == 200, einspiel.get_data(as_text=True)
    assert client.get('/api/properties').status_code == 401
    assert client.post('/login', json={'username': QUER_USER,
                                       'password': QUER_PASS}).status_code == 200
    seite = client.get('/huelle/passwort').get_data(as_text=True)
    assert 'Passwort zurücksetzen' in seite
    assert 'Die Anmeldung ist ausgeschaltet' not in seite


def test_umzug_12_export_offen_docker_ohne_code(app_ctx, umzug_statt,
                                                monkeypatch):
    """Export im offenen Modus in Docker braucht keinen Einmal-Code."""
    import io
    import zipfile

    desktop_setzen(app_ctx, monkeypatch, False)
    schalter_setzen(True)
    client = app_ctx.app.test_client()
    antwort = client.get('/api/umzug/export')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    inhalt = antwort.get_data()
    antwort.close()
    assert zipfile.is_zipfile(io.BytesIO(inhalt))


def test_umzug_13_sicherung_ohne_konto_oeffnet_docker_nicht(
        app_ctx, umzug_statt, monkeypatch):
    """NK-206: auch eine zurückgespielte Sicherung ohne Konto mit True
    öffnet eine angemeldete Docker-Instanz nicht -- die Anmeldung bleibt an."""
    from nebenkostenfix import backup

    desktop_setzen(app_ctx, monkeypatch, True)
    _haus()
    alt = backup.sicherung_erstellen(app_ctx.app, backup.standardziel(app_ctx.app))
    _ziel_einstellen(app_ctx, monkeypatch, False)
    _konto(ZIEL_USER, ZIEL_PASS)
    client = app_ctx.app.test_client()
    assert client.post('/login', json={'username': ZIEL_USER,
                                       'password': ZIEL_PASS}).status_code == 200
    einspiel = client.post('/api/backup/einspielen', json={'name': alt.name})
    assert einspiel.status_code == 200, einspiel.get_data(as_text=True)
    assert schalter() is False
    assert User.query.count() == 0
    assert app_ctx.app.test_client().get('/api/properties').status_code == 401


def test_konto_liest_keine_einstellungsdatei(app_ctx, monkeypatch):
    """NK-206: mit Konto entscheidet die Abfrage allein; die Einstellungsdatei
    bleibt je Anfrage ungelesen."""
    from nebenkostenfix import auth

    _konto(QUER_USER, QUER_PASS)

    def laut(*args, **kwargs):
        raise RuntimeError('Mit Konto darf die Einstellungsdatei nicht gelesen werden.')

    monkeypatch.setattr(auth.einstellungen, 'lesen', laut)
    assert auth.ohne_anmeldung_aktiv(app_ctx.app) is False
    assert app_ctx.app.test_client().get('/api/properties').status_code == 401




# --- NK-201: Oberfläche für den offenen Modus ----------------------------------

KOPF_PFEILER = Path('static/index.html')

def _index_text():
    """static/index.html im Klartext (die Oberfläche ist kein Template)."""
    quelltext = KOPF_PFEILER.read_text(encoding='utf-8')
    # Zeilenumbrueche und Einrueckung sind keine Beschriftung; ohne sie sind
    # die Kennungen der Tests vom Wrap im Quelltext unabhaengig.
    return re.sub(r'\s+', ' ', quelltext)


def test_index_hinweisleiste_offener_modus():
    """Die Warnleiste neben dem Leerlauf-Hinweis ist im HTML vorhanden."""
    text = _index_text()
    assert 'id="ohne-anmeldung-hinweis"' in text
    assert ('Die Anmeldung ist ausgeschaltet. '
            'Jeder in Ihrem Netz kann alle Daten sehen.') in text
    assert 'Anmeldung einschalten' in text


def test_index_konto_karte_offener_abschnitt():
    """Offen zeigt die Konto-Karte den Aufklärungstext mit dem Link."""
    text = _index_text()
    assert ('Die Anmeldung ist ausgeschaltet. '
            'Jeder, der dieses Programm öffnen kann, sieht alle Daten.') in text
    assert 'Anmeldung einschalten' in text


def test_index_konto_karte_ausschalter():
    """Angemeldet bietet die Konto-Karte das Ausschalten mit Warnungen."""
    text = _index_text()
    assert 'Anmeldung ausschalten' in text
    assert 'Dabei werden alle Konten gelöscht, auch ein zweites.' in text
    assert 'Danach kann jeder in Ihrem Netz alle Daten sehen.' in text


def test_index_umzug_text_einstellungen_erwaehnt_leeres_paket():
    """Der Text in den Einstellungen hält offen, dass das Paket leer sein kann."""
    text = _index_text()
    assert 'falls das Paket eines enthält' in text


def test_auth_me_offen_leerlauf_none(app_ctx, monkeypatch):
    """Offen liefert /api/auth/me leerlauf_s None — kein Leerlauf, kein Abmelden."""
    desktop_setzen(app_ctx, monkeypatch, True)
    client = app_ctx.app.test_client()
    daten = client.get('/api/auth/me').get_json()
    assert daten['leerlauf_s'] is None


def test_ausschalter_schickt_password(app_ctx, monkeypatch):
    """NK-204: der Ausschalter im Kopf der Konto-Karte benennt das Feld so,
    wie der Server es liest — `password`, nicht `passwort` (sonst antwortet
    /api/anmeldung/aus mit 403, obwohl das Passwort stimmt)."""
    import re as _re

    quelle = Path('static/app.js').read_text(encoding='utf-8')
    anfang = quelle.index('async function anmeldungAusschalten()')
    tief = 0
    for i in range(anfang, len(quelle)):
        if quelle[i] == '{':
            tief += 1
        elif quelle[i] == '}':
            tief -= 1
            if tief == 0:
                ende = i + 1
                break
    funktion = quelle[anfang:ende]
    aufruf = _re.search(r"fetch\('/api/anmeldung/aus'[\s\S]*?\}\);", funktion)
    assert aufruf, funktion
    koerper = aufruf.group(0)
    assert 'password:' in koerper, koerper
    assert 'passwort:' not in koerper, koerper


def test_health_nie_durch_den_offenen_modus(app_ctx, monkeypatch):
    """NK-204: /api/health beantwortet der öffentliche Weg ohne Datenbank —
    auch wenn der offene Modus selbst laut würde."""
    from nebenkostenfix import auth

    def laut(app):
        raise RuntimeError('Diese Anfrage hätte /api/health nie berühren dürfen.')

    monkeypatch.setattr(auth, 'ohne_anmeldung_aktiv', laut)
    antwort = app_ctx.app.test_client().get('/api/health')
    assert antwort.status_code == 200


def test_ausschalten_schreibt_schalter_zuerst(app_ctx, monkeypatch):
    """NK-204: schlägt das Schreiben der Einstellungen fehl, bleiben die
    Konten unangetastet — erst der Schalter, dann das Löschen."""
    from nebenkostenfix import auth, einstellungen

    _konto(QUER_USER, QUER_PASS)
    monkeypatch.setattr(
        auth.einstellungen, 'schreiben',
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError('Platte voll')))
    client = app_ctx.app.test_client()
    assert client.post('/login', json={'username': QUER_USER,
                                       'password': QUER_PASS}).status_code == 200
    antwort = client.post('/api/anmeldung/aus', json={'password': QUER_PASS})
    assert antwort.status_code == 500, antwort.get_data(as_text=True)
    assert User.query.count() == 1
    assert User.query.first().username == QUER_USER
