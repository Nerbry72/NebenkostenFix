"""Die Desktop-App bleibt mit dem Server angemeldet (#52).

Nur Python spricht mit dem Server über das Gerätetoken; das Token steht
im Schlüsselbund des Systems, nie im WebView und nie in einer Adresse:

- Nach der Anmeldung mit Häkchen hängt der Server ``?geraet=<abholcode>``
  an das Ziel. Die App holt damit das Token ab.
- Beim Start und auf ``/login?next=…`` (Leerlauf-Grenze) tauscht sie das
  Token gegen ein neues und einen Einmalcode und lädt
  ``/geraete/anmelden``.
- ``/login?abgemeldet=1`` heißt abgemeldet: Token weg.

Schlüsselbund und Server sind hier Attrappen; pywebview ist nachgebaut
wie in ``tests/test_desktop.py``.
"""

from __future__ import annotations

import inspect
import json
import sys
import threading
import types
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import desktop
from nebenkostenfix import windows_ordner
from tests.test_desktop import (  # noqa: F401 -- Fixtures
    GESUND, _menuepunkt, lokal, servermodus, testserver)

WURZEL = Path(__file__).resolve().parents[1]


class Attrappe:
    """Ein Schlüsselbund im Speicher, mit der Schnittstelle von keyring."""

    def __init__(self):
        self.daten = {}

    def get_password(self, dienst, konto):
        return self.daten.get((dienst, konto))

    def set_password(self, dienst, konto, wert):
        self.daten[(dienst, konto)] = wert

    def delete_password(self, dienst, konto):
        if (dienst, konto) not in self.daten:
            raise KeyError('nicht da')  # keyring: PasswordDeleteError
        del self.daten[(dienst, konto)]


class WieWindows(Attrappe):
    """keyring unter Windows: ``set_password`` legt einen vorhandenen Wert
    unter ``<Konto>@<Dienst>`` ab, ``delete_password`` entfernt beide."""

    def set_password(self, dienst, konto, wert):
        if (dienst, konto) in self.daten:
            self.daten[(f'{konto}@{dienst}', konto)] = self.daten[(dienst, konto)]
        self.daten[(dienst, konto)] = wert

    def delete_password(self, dienst, konto):
        weg = [k for k in self.daten if k in ((dienst, konto), (f'{konto}@{dienst}', konto))]
        if not weg:
            raise KeyError('nicht da')
        for schluessel in weg:
            del self.daten[schluessel]


class Verweigert:
    """macOS-Rückfrage „Ablehnen“, gesperrter Schlüsselbund: jeder Zugriff wirft."""

    def _wirft(self, *_):
        raise RuntimeError('abgelehnt')

    get_password = set_password = delete_password = _wirft


class Server:
    """Die drei Geräteroute des Servers als Attrappe für ``_geraete_post``."""

    def __init__(self):
        self.aufrufe = []
        self.antworten = {
            '/api/geraete/abholen': (201, {'id': 1, 'name': 'Büro', 'token': 'nkg_abgeholt'}),
            '/api/geraete/erneuern': (200, {'token': 'nkg_neu', 'code': 'einmal'}),
            '/api/geraete/widerrufen': (200, {'status': 'abgemeldet'}),
        }

    def __call__(self, basis, pfad, daten, zeit=10):
        self.aufrufe.append((pfad, daten))
        antwort = self.antworten[pfad]
        return antwort(daten) if callable(antwort) else antwort

    def pfade(self):
        return [pfad for pfad, _ in self.aufrufe]


@pytest.fixture
def geraetemodus(servermodus, testserver, monkeypatch):
    """Servermodus mit Schlüsselbund-Attrappe und Geräteroute-Attrappe."""
    fenster, gestartet = servermodus
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    windows_ordner.einstellungen_schreiben(server=basis)
    bund = Attrappe()
    monkeypatch.setattr(desktop, '_systembackend', lambda: bund)
    server = Server()
    monkeypatch.setattr(desktop, '_geraete_post', server)
    return types.SimpleNamespace(fenster=fenster, gestartet=gestartet, basis=basis,
                                 bund=bund, server=server)


def _token(modus):
    return modus.bund.daten.get((desktop.DIENST, modus.basis))


def _anmelden(basis, code='einmal', weiter='/'):
    return basis + '/geraete/anmelden?' + urllib.parse.urlencode({'code': code, 'next': weiter})


# --- Schlüsselbund -----------------------------------------------------------------

def test_schluesselbund_rundlauf():
    bund = desktop.Schluesselbund(Attrappe())
    assert bund.nutzbar() and bund.name == 'Attrappe'
    assert bund.lesen('https://nk.example') is None
    assert bund.schreiben('https://nk.example', 'nkg_eins')
    assert bund.lesen('https://nk.example') == 'nkg_eins'
    # Je Server ein Eintrag.
    assert bund.lesen('https://anderer.example') is None
    bund.loeschen('https://nk.example')
    bund.loeschen('https://nk.example')  # zweimal: kein Fehler
    assert bund.lesen('https://nk.example') is None


def test_ein_ersetztes_token_bleibt_nicht_im_schluesselbund():
    """Unter Windows stünde sonst das ersetzte Token als zweiter Eintrag
    daneben. Löscht jemand von Hand nur den einen, läse die App das alte,
    und der Server hielte es für eine Kopie (Review zu Commit 3)."""
    attrappe = WieWindows()
    bund = desktop.Schluesselbund(attrappe)
    assert bund.schreiben('https://nk.example', 'nkg_eins')
    assert bund.schreiben('https://nk.example', 'nkg_zwei')
    assert attrappe.daten == {(desktop.DIENST, 'https://nk.example'): 'nkg_zwei'}


def test_ohne_schluesselbund_geht_alles_wie_bisher(monkeypatch):
    monkeypatch.setattr(desktop, '_systembackend', lambda: None)
    bund = desktop.Schluesselbund()
    assert not bund.nutzbar() and bund.name == 'keiner'
    assert bund.lesen('https://nk.example') is None
    assert bund.schreiben('https://nk.example', 'nkg_eins') is False
    bund.loeschen('https://nk.example')


def test_ein_verweigerter_schluesselbund_heisst_kein_token():
    bund = desktop.Schluesselbund(Verweigert())
    assert bund.nutzbar()
    assert bund.lesen('https://nk.example') is None
    assert bund.schreiben('https://nk.example', 'nkg_eins') is False
    bund.loeschen('https://nk.example')


def test_nur_ein_geraetetoken_gilt_als_token():
    attrappe = Attrappe()
    attrappe.set_password(desktop.DIENST, 'https://nk.example', 'irgendwas')
    assert desktop.Schluesselbund(attrappe).lesen('https://nk.example') is None


def test_das_backend_ist_fest_gewaehlt(monkeypatch):
    """Nicht über keyring.get_keyring(): sonst entschieden PYTHON_KEYRING_BACKEND
    oder ein fremdes Paket mit eigenem Backend, wohin das Token geht."""
    benutzt = desktop._systembackend.__code__.co_names
    assert 'get_keyring' not in benutzt and 'set_keyring' not in benutzt
    assert 'keyring.backends.Windows' in benutzt and 'keyring.backends.macOS' in benutzt

    class Tresor:
        priority = 5

    class _OhneSystem(type):
        @property
        def priority(cls):  # wie keyring (classproperty): wirft ohne pywin32-ctypes
            raise RuntimeError('Requires Windows and pywin32')

    class Kaputt(metaclass=_OhneSystem):
        pass

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setitem(sys.modules, 'keyring', types.ModuleType('keyring'))
    monkeypatch.setitem(sys.modules, 'keyring.backends', types.ModuleType('keyring.backends'))
    modul = types.ModuleType('keyring.backends.Windows')
    monkeypatch.setitem(sys.modules, 'keyring.backends.Windows', modul)
    modul.WinVaultKeyring = Tresor
    assert type(desktop._systembackend()) is Tresor
    modul.WinVaultKeyring = Kaputt
    assert desktop._systembackend() is None
    # Ohne keyring (Linux, der Mac auf main): kein Schlüsselbund.
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert desktop._systembackend() is None


def test_der_rechnername_ohne_domaene(monkeypatch):
    import platform
    monkeypatch.setattr(platform, 'node', lambda: 'Buero-PC.fritz.box')
    assert desktop.rechnername() == 'Buero-PC'
    monkeypatch.setattr(platform, 'node', lambda: '')
    assert desktop.rechnername() == ''


# --- User-Agent ---------------------------------------------------------------------

def test_die_kennung_passt_zum_server():
    from nebenkostenfix import geraete
    assert desktop.APP_KENNUNG == geraete.APP_KENNUNG


def test_user_agent_nur_mit_schluesselbund(geraetemodus, monkeypatch):
    """Nur dann zeigt der Server das Häkchen: ohne Ablage könnte die App das
    Token nicht behalten."""
    assert desktop.main([]) == 0
    agent = geraetemodus.gestartet['user_agent']
    assert f'{desktop.APP_KENNUNG}{desktop.SOFTWARE_VERSION}' in agent
    assert agent.startswith('Mozilla/5.0 (')
    monkeypatch.setattr(desktop, '_systembackend', lambda: None)
    assert desktop.main([]) == 0
    assert geraetemodus.gestartet['user_agent'] is None


def test_der_lokale_modus_nennt_sich_nicht_app():
    """Lokal gibt es kein Token: das Häkchen hätte dort keinen Sinn."""
    assert 'user_agent' not in inspect.getsource(desktop.fenster_starten)


# --- Abläufe ------------------------------------------------------------------------

def test_der_abholcode_wird_abgeholt(geraetemodus, monkeypatch):
    monkeypatch.setattr(desktop, 'rechnername', lambda: 'Buero-PC')
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    offen.navigiert(geraetemodus.basis + '/?geraet=abholcode')
    assert geraetemodus.server.aufrufe == [
        ('/api/geraete/abholen', {'code': 'abholcode', 'name': 'Buero-PC'})]
    assert _token(geraetemodus) == 'nkg_abgeholt'


def test_ein_abgeholtes_token_ohne_ablage_laesst_die_sitzung(geraetemodus, monkeypatch):
    """Die Sitzung hängt schon am Gerät. Ein Widerruf beendete sie beim
    nächsten Klick; das Token hält ohnehin niemand (Review zu Commit 3)."""
    assert desktop.main([]) == 0
    monkeypatch.setattr(geraetemodus.bund, 'set_password', Verweigert().set_password)
    geraetemodus.fenster[0].navigiert(geraetemodus.basis + '/?geraet=abholcode')
    assert geraetemodus.server.pfade() == ['/api/geraete/abholen']


def test_ein_altes_token_wird_beim_abholen_widerrufen(geraetemodus):
    """Scheiterte die stille Anmeldung (Netz, Sperre), liegt noch ein Token.
    Ohne Widerruf stünde der Rechner doppelt in der Liste."""
    assert desktop.main([]) == 0
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    geraetemodus.fenster[0].navigiert(geraetemodus.basis + '/?geraet=abholcode')
    assert geraetemodus.server.aufrufe[1:] == [('/api/geraete/widerrufen', {'token': 'nkg_alt'})]
    assert _token(geraetemodus) == 'nkg_abgeholt'


def test_ein_abholcode_gilt_nur_einmal(geraetemodus):
    """Die Oberfläche lässt ``?geraet=`` in der Adresse stehen: Neu laden
    holt nicht noch einmal ab, und von zweien zählt der letzte."""
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    offen.navigiert(geraetemodus.basis + '/?geraet=eins')
    offen.navigiert(geraetemodus.basis + '/?geraet=eins')
    offen.navigiert(geraetemodus.basis + '/?geraet=eins&geraet=zwei')
    assert [d['code'] for p, d in geraetemodus.server.aufrufe if p.endswith('abholen')] == [
        'eins', 'zwei']


def test_der_start_meldet_still_an(geraetemodus):
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    assert offen.geladen == [_anmelden(geraetemodus.basis)]
    assert geraetemodus.server.aufrufe == [('/api/geraete/erneuern', {'token': 'nkg_alt'})]
    assert _token(geraetemodus) == 'nkg_neu'


@pytest.mark.parametrize('status, bleibt', [(401, False), (429, True), (0, True), (500, True)])
def test_der_start_ohne_gueltiges_token(geraetemodus, status, bleibt):
    """Abgelehnt (widerrufen, abgelaufen, ersetzt): Token weg. Netz weg oder
    gesperrt: Token behalten. In beiden Fällen die normale Anmeldeseite."""
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    geraetemodus.server.antworten['/api/geraete/erneuern'] = (status, {})
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    assert offen.geladen == [geraetemodus.basis + '/']
    assert (_token(geraetemodus) == 'nkg_alt') is bleibt


def test_nach_einer_sperre_ein_zweiter_versuch_dann_die_anmeldeseite(geraetemodus,
                                                                     monkeypatch):
    """Wie der Server: „/“ ohne Sitzung leitet auf /login?next=/ um. Nach
    einer Sperre versucht die App es dort noch einmal, dann bleibt die Seite."""
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    geraetemodus.server.antworten['/api/geraete/erneuern'] = (429, {})
    from tests.test_desktop import _ServerFenster

    def load_url(self, url):
        self.geladen.append(url)
        ohne_sitzung = urllib.parse.urlsplit(url).path == '/'
        self.navigiert(geraetemodus.basis + '/login?next=/' if ohne_sitzung else url)

    monkeypatch.setattr(_ServerFenster, 'load_url', load_url)
    assert desktop.main([]) == 0
    assert geraetemodus.server.pfade() == ['/api/geraete/erneuern'] * 2
    assert geraetemodus.fenster[0].url == geraetemodus.basis + '/login?next=/'
    assert _token(geraetemodus) == 'nkg_alt'


def test_die_leerlauf_grenze_meldet_still_neu_an(geraetemodus):
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    offen.navigiert(geraetemodus.basis + '/login?next=/%23abrechnung')
    assert offen.geladen[-1] == _anmelden(geraetemodus.basis, weiter='/#abrechnung')
    assert _token(geraetemodus) == 'nkg_neu'


def test_ohne_token_bleibt_die_anmeldeseite(geraetemodus):
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    offen.navigiert(geraetemodus.basis + '/login?next=/')
    assert offen.geladen == [geraetemodus.basis + '/']
    assert geraetemodus.server.aufrufe == []


def test_abgemeldet_loescht_das_token(geraetemodus):
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    offen.navigiert(geraetemodus.basis + '/login?abgemeldet=1')
    assert _token(geraetemodus) is None
    # Der Server hat das Gerät der Sitzung schon abgemeldet; der Widerruf
    # trifft auch ein Token, das zu einer anderen Sitzung gehörte.
    assert geraetemodus.server.aufrufe == [('/api/geraete/widerrufen', {'token': 'nkg_alt'})]
    assert offen.geladen == [geraetemodus.basis + '/']


def test_eine_fremde_seite_bekommt_nichts(geraetemodus):
    """Nur Seiten des Servers zählen, sonst gäbe eine fremde Seite mit
    ``/login?next=`` der App den Anlass, ein Token zu verbrauchen."""
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    offen.navigiert('https://boese.example/login?next=/')
    offen.navigiert('https://boese.example/?geraet=abholcode')
    offen.navigiert('https://boese.example/login?abgemeldet=1')
    assert geraetemodus.server.aufrufe == []
    assert _token(geraetemodus) == 'nkg_alt'


def test_die_stille_anmeldung_kreist_nicht(geraetemodus, monkeypatch):
    """Kommt das Cookie nicht an (etwa http bei BEHIND_HTTPS), landet die App
    nach jeder stillen Anmeldung wieder auf /login. Nach wenigen Versuchen
    bleibt die Anmeldeseite stehen."""
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')

    def load_url(self, url):
        self.geladen.append(url)
        self.navigiert(geraetemodus.basis + '/login?next=/')

    from tests.test_desktop import _ServerFenster
    monkeypatch.setattr(_ServerFenster, 'load_url', load_url)
    assert desktop.main([]) == 0
    assert geraetemodus.server.pfade().count('/api/geraete/erneuern') == desktop.STILL_HOECHSTENS


def test_nie_zwei_erneuerungen_zugleich(monkeypatch):
    """Zwei gleichzeitige Erneuerungen mit demselben Token liefen auf dem
    Server ineinander (Review zu Commit 1). Die zweite wartet nicht, sie
    lässt es."""
    attrappe = Attrappe()
    attrappe.set_password(desktop.DIENST, 'https://nk.example', 'nkg_alt')
    still = desktop.StilleAnmeldung(desktop.Schluesselbund(attrappe))
    drin, weiter = threading.Event(), threading.Event()
    aufrufe = []

    def post(basis, pfad, daten, zeit=10):
        aufrufe.append(pfad)
        drin.set()
        weiter.wait(5)
        return 200, {'token': 'nkg_neu', 'code': 'einmal'}

    monkeypatch.setattr(desktop, '_geraete_post', post)
    erstes = {}
    faden = threading.Thread(target=lambda: erstes.update(
        ziel=still.ziel('https://nk.example', '/')))
    faden.start()
    assert drin.wait(5)
    assert still.ziel('https://nk.example', '/') is None
    weiter.set()
    faden.join(5)
    assert aufrufe == ['/api/geraete/erneuern']
    assert erstes['ziel'] == _anmelden('https://nk.example')


def test_ein_neues_token_ohne_ablage_wird_widerrufen(monkeypatch):
    """Sonst stünde nur noch das ersetzte Token im Schlüsselbund, und der
    nächste Start sähe für den Server aus wie eine Kopie."""
    attrappe = Attrappe()
    attrappe.set_password(desktop.DIENST, 'https://nk.example', 'nkg_alt')
    still = desktop.StilleAnmeldung(desktop.Schluesselbund(attrappe))
    monkeypatch.setattr(attrappe, 'set_password', Verweigert().set_password)
    server = Server()
    monkeypatch.setattr(desktop, '_geraete_post', server)
    assert still.ziel('https://nk.example', '/') is None
    assert server.aufrufe == [('/api/geraete/erneuern', {'token': 'nkg_alt'}),
                              ('/api/geraete/widerrufen', {'token': 'nkg_neu'})]
    assert attrappe.get_password(desktop.DIENST, 'https://nk.example') is None


# --- Menü ---------------------------------------------------------------------------

def test_menue_abmelden(geraetemodus, monkeypatch):
    geraetemodus.bund.set_password(desktop.DIENST, geraetemodus.basis, 'nkg_alt')
    assert desktop.main([]) == 0
    (offen,) = geraetemodus.fenster
    geraetemodus.server.aufrufe.clear()
    monkeypatch.setattr(desktop.threading, 'Thread', _sofort)
    _menuepunkt(geraetemodus.gestartet, 'Abmelden')()
    assert _token(geraetemodus) is None
    assert geraetemodus.server.aufrufe[0] == ('/api/geraete/widerrufen', {'token': 'nkg_neu'})
    assert offen.geladen[-1] == geraetemodus.basis + '/login?abgemeldet=1'


def test_menue_abmelden_ohne_token_sagt_es(geraetemodus, monkeypatch):
    assert desktop.main([]) == 0
    meldungen = []
    monkeypatch.setattr(desktop, '_meldung', lambda text, **_: meldungen.append(text))
    monkeypatch.setattr(desktop.threading, 'Thread', _sofort)
    _menuepunkt(geraetemodus.gestartet, 'Abmelden')()
    assert meldungen == [desktop.NICHT_ANGEMELDET]
    assert geraetemodus.server.aufrufe == []


@pytest.mark.parametrize('gespeichert_unter', ['http', 'https'])
def test_menue_abmelden_ohne_server(servermodus, monkeypatch, gespeichert_unter):
    """Offline zählt die eingetragene Adresse, auch in der https-Form, die
    die Prüfung übernommen hatte (Review zu Commit 3)."""
    _, gestartet = servermodus
    import socket
    with socket.socket() as frei:
        frei.bind(('127.0.0.1', 0))
        port = frei.getsockname()[1]
    monkeypatch.setattr(desktop, 'server_pruefen',
                        lambda _: (False, desktop.NICHT_ERREICHBAR, None))
    windows_ordner.einstellungen_schreiben(server='http://nk.example')
    attrappe = Attrappe()
    attrappe.set_password(desktop.DIENST, f'{gespeichert_unter}://nk.example', 'nkg_alt')
    monkeypatch.setattr(desktop, '_systembackend', lambda: attrappe)
    server = Server()
    server.antworten['/api/geraete/widerrufen'] = (0, {})
    monkeypatch.setattr(desktop, '_geraete_post', server)
    meldungen = []
    monkeypatch.setattr(desktop, '_meldung', lambda text, **_: meldungen.append(text))
    monkeypatch.setattr(desktop.threading, 'Thread', _sofort)
    assert desktop.main([]) == 0
    _menuepunkt(gestartet, 'Abmelden')()
    assert attrappe.daten == {}
    assert meldungen == [desktop.LOKAL_ABGEMELDET]


class _sofort:
    """threading.Thread, der gleich läuft: der Menüpunkt wartet nie im
    Hauptthread auf Server oder Schlüsselbund."""

    def __init__(self, target, args=(), daemon=None):
        self._ziel, self._args = target, args

    def start(self):
        self._ziel(*self._args)


# --- HTTP ---------------------------------------------------------------------------

@pytest.fixture
def postserver():
    """Ein echter HTTP-Server, der POSTs merkt; ``antworten[pfad]`` = (Status, Köpfe, Inhalt)."""
    antworten, eingang = {}, []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            laenge = int(self.headers.get('Content-Length') or 0)
            eingang.append((self.path, self.headers.get('Content-Type'),
                            json.loads(self.rfile.read(laenge))))
            status, koepfe, inhalt = antworten.get(self.path, (404, {}, b'{}'))
            self.send_response(status)
            for name, wert in koepfe.items():
                self.send_header(name, wert)
            self.send_header('Content-Length', str(len(inhalt)))
            self.end_headers()
            self.wfile.write(inhalt)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}', antworten, eingang
    finally:
        server.shutdown()
        server.server_close()


def test_geraete_post(postserver):
    basis, antworten, eingang = postserver
    antworten['/api/geraete/abholen'] = (201, {'Content-Type': 'application/json'},
                                         b'{"token": "nkg_x"}')
    assert desktop._geraete_post(basis, '/api/geraete/abholen', {'code': 'c'}) == (
        201, {'token': 'nkg_x'})
    assert eingang == [('/api/geraete/abholen', 'application/json', {'code': 'c'})]
    antworten['/api/geraete/erneuern'] = (401, {}, b'{"code": "geraet_ungueltig"}')
    assert desktop._geraete_post(basis, '/api/geraete/erneuern', {})[0] == 401
    # Keiner Weiterleitung folgen: das Token geht nur an den Server selbst.
    antworten['/api/geraete/widerrufen'] = (307, {'Location': 'https://boese.example/'}, b'')
    assert desktop._geraete_post(basis, '/api/geraete/widerrufen', {})[0] == 307
    antworten['/api/geraete/abholen'] = (200, {}, b'kein json')
    assert desktop._geraete_post(basis, '/api/geraete/abholen', {}) == (200, {})


def test_geraete_post_ohne_server():
    import socket
    with socket.socket() as frei:
        frei.bind(('127.0.0.1', 0))
        port = frei.getsockname()[1]
    assert desktop._geraete_post(f'http://127.0.0.1:{port}', '/api/geraete/erneuern', {},
                                 zeit=2) == (0, {})


# --- Selbsttest, Abhängigkeit, Doku -------------------------------------------------

def test_selbsttest_nennt_den_schluesselbund(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    assert desktop.schluesselbund_probe(desktop.Schluesselbund(Attrappe())) == {
        'schluesselbund': 'Attrappe', 'schluesselbund_durchlauf': True}
    assert desktop.schluesselbund_probe(desktop.Schluesselbund(Verweigert()))[
        'schluesselbund_durchlauf'] is False
    # Unter macOS fragte das System in der CI nach dem Schlüsselbund: nur der Name.
    monkeypatch.setattr(sys, 'platform', 'darwin')
    assert desktop.schluesselbund_probe(desktop.Schluesselbund(Attrappe())) == {
        'schluesselbund': 'Attrappe', 'schluesselbund_durchlauf': None}


def test_der_durchlauf_laesst_nichts_zurueck(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    attrappe = Attrappe()
    desktop.schluesselbund_probe(desktop.Schluesselbund(attrappe))
    assert attrappe.daten == {}


@pytest.mark.parametrize('plattform, bericht, ok', [
    ('win32', {'schluesselbund': 'WinVaultKeyring', 'schluesselbund_durchlauf': True}, True),
    ('win32', {'schluesselbund': 'WinVaultKeyring', 'schluesselbund_durchlauf': False}, False),
    ('win32', {'schluesselbund': 'keiner', 'schluesselbund_durchlauf': None}, False),
    ('linux', {'schluesselbund': 'keiner', 'schluesselbund_durchlauf': None}, True),
])
def test_unter_windows_gehoert_der_schluesselbund_zum_bestehen(monkeypatch, plattform,
                                                              bericht, ok):
    monkeypatch.setattr(sys, 'platform', plattform)
    assert desktop.schluesselbund_bestanden(bericht) is ok
    quelle = inspect.getsource(desktop.selbsttest)
    assert 'schluesselbund_probe()' in quelle and 'schluesselbund_bestanden(bericht)' in quelle


def test_keyring_ist_fest_gepinnt():
    zeilen = (WURZEL / 'requirements-desktop.txt').read_text(encoding='utf-8').splitlines()
    assert 'keyring==25.7.0; sys_platform == "win32"' in zeilen


def test_die_anleitung_zum_servermodus_erklaert_es():
    text = ' '.join((WURZEL / 'docs' / 'servermodus.md').read_text(encoding='utf-8').split())
    assert 'Nach jedem Start der App meldet man sich neu an.' not in text
    for wort in ('Angemeldet bleiben', 'Anmeldeinformationsverwaltung', 'Datei → Abmelden',
                 '30 Tage'):
        assert wort in text, wort
