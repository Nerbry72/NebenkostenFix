"""Der e2e-Lauf, gegengeprueft ohne Docker (NK-031).

Ein Lauf von ``make e2e`` dauert Minuten und braucht einen Docker-Daemon --
in ``make check`` hat er deshalb nichts verloren. Geprueft wird hier, was ein
Lauf **nicht** zeigt: die Leitplanken, die nur dann greifen, wenn jemand einen
Fehler macht. Ob Port 6060 wirklich gesperrt ist, sieht man an keinem
erfolgreichen Durchgang -- nur daran, dass ein Aufruf mit 6060 abbricht.

Dazu die Leseproben am ``Makefile``: dass das Ziel existiert, dass es das
Skript aufruft, und vor allem, dass es **nicht** durch ``$(RUN)`` laeuft. Das
ist Akzeptanzpunkt 1 der Karte, und es ist genau die Zeile, die jemand beim
naechsten Aufraeumen am Makefile versehentlich wieder einfuegt.
"""

import importlib.util
import json
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent


def _laden():
    """scripts/ liegt nicht im Importpfad -- die Datei direkt laden."""
    pfad = WURZEL / 'scripts' / 'e2e.py'
    spec = importlib.util.spec_from_file_location('e2e', pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


e2e = _laden()

MAKEFILE = (WURZEL / 'Makefile').read_text(encoding='utf-8')


def _zielzeilen(ziel: str) -> list[str]:
    """Die Rezeptzeilen eines Makefile-Ziels, ohne Kopf und ohne Leerzeilen."""
    zeilen = MAKEFILE.splitlines()
    for i, zeile in enumerate(zeilen):
        if zeile.startswith(f'{ziel}:'):
            rezept = []
            for weiter in zeilen[i + 1:]:
                if weiter.startswith('\t'):
                    rezept.append(weiter)
                elif weiter.strip() == '':
                    continue
                else:
                    break
            return rezept
    pytest.fail(f'Das Makefile hat kein Ziel "{ziel}".')


# --- Akzeptanzpunkt 1: auf dem Wirt, nicht ueber den RUN-Wrapper ------------

def test_makefile_hat_das_ziel_e2e():
    assert 'e2e:' in MAKEFILE
    assert 'e2e' in MAKEFILE.split('.PHONY:')[1].splitlines()[0].split()


def test_e2e_ruft_das_skript_auf():
    rezept = '\n'.join(_zielzeilen('e2e'))
    assert 'scripts/e2e.py' in rezept


def test_e2e_geht_nicht_durch_den_run_wrapper():
    """Der Kern der Karte: $(RUN) schoebe den Lauf in den Container, den er baut."""
    rezept = '\n'.join(_zielzeilen('e2e'))
    assert '$(RUN)' not in rezept


def test_e2e_bricht_im_container_ab():
    """Wer make e2e im Container tippt, soll eine Erklaerung sehen, keinen Bau."""
    rezept = '\n'.join(_zielzeilen('e2e'))
    assert '/.dockerenv' in rezept
    assert 'exit 1' in rezept


def test_check_zieht_e2e_nicht_mit():
    """Sonst kostet jeder Commit einen Abbildbau."""
    rezept = '\n'.join(_zielzeilen('check'))
    assert 'e2e' not in rezept


def test_skript_bricht_im_container_ab(monkeypatch):
    monkeypatch.setattr(e2e.Path, 'exists', lambda selbst: True)
    with pytest.raises(e2e.Abbruch) as fehler:
        e2e.vorbedingungen(e2e.STANDARD_PORT)
    assert 'Wirt' in str(fehler.value)


# --- Leitplanke: die zwei Ports mit echten Daten ----------------------------

@pytest.mark.parametrize('port', [6060])
def test_ports_mit_echten_daten_sind_gesperrt(port):
    with pytest.raises(e2e.Abbruch) as fehler:
        e2e.port_pruefen(port)
    assert str(port) in str(fehler.value)


def test_der_vorgabeport_ist_keiner_der_gesperrten():
    assert e2e.STANDARD_PORT not in e2e.GESPERRTE_PORTS
    e2e.port_pruefen(e2e.STANDARD_PORT)


def test_privilegierte_ports_werden_abgelehnt():
    with pytest.raises(e2e.Abbruch):
        e2e.port_pruefen(80)


def test_eigener_projektname():
    """Ohne -p hiesse das Projekt nach dem Verzeichnis und traefe fremde Stapel."""
    assert e2e.PROJEKTNAME == 'nk-e2e'


def test_kein_down_mit_volumes():
    """docker compose down -v steht auf der Verbotsliste."""
    quelle = (WURZEL / 'scripts' / 'e2e.py').read_text(encoding='utf-8')
    assert "'-v'" not in quelle
    assert '--volumes' not in quelle


def test_aufgeraeumt_wird_nur_der_eigene_baum(tmp_path):
    """rmtree laeuft nur auf einem Pfad, den der Lauf selbst angelegt hat."""
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    fremd = tmp_path / 'wichtige-daten'
    fremd.mkdir()
    lauf.arbeit = fremd
    lauf.aufraeumen()
    assert fremd.exists()


def test_vor_dem_herunterfahren_wird_chown_gefahren():
    """F-17: der Datenordner gehoert dem Nutzer im Container, sonst bleibt
    der Baum liegen. Seit NK-076 laeuft die Anwendung ohne root, das chown
    ausdruecklich mit -u 0.

    Die Reihenfolge ist der Punkt -- nach dem ``down`` gibt es keinen
    Container mehr, in dem das chown laufen koennte.
    """
    quelle = (WURZEL / 'scripts' / 'e2e.py').read_text(encoding='utf-8')
    rumpf = quelle.split('def stapel_runter')[1].split('def ')[0]
    assert 'chown' in rumpf and "'-u', '0'" in rumpf
    assert rumpf.index('chown') < rumpf.index("'down'")


def test_bindziele_werden_nachgeschlagen_nicht_geraten():
    """Zweiter Teil von F-17: ./belege haengt unter /mnt/belege.

    Ein fest eingetragener Pfad hat still danebengegriffen. Im Skript darf
    deshalb kein geratener Container-Pfad mehr stehen.
    """
    quelle = (WURZEL / 'scripts' / 'e2e.py').read_text(encoding='utf-8')
    rumpf = quelle.split('def stapel_runter')[1].split('\n    def ')[0]
    assert '/app/belege' not in rumpf
    assert '_bindziele' in rumpf


def test_bindziele_nimmt_nur_bind_mounts():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    antwort = {'services': {'web': {'volumes': [
        {'type': 'bind', 'target': '/app/data'},
        {'type': 'bind', 'target': '/mnt/belege'},
        {'type': 'volume', 'target': '/var/lib/egal'},
    ]}}}

    class Antwort:
        stdout = json.dumps(antwort)

    lauf._docker = lambda *a, **k: Antwort()
    assert lauf._bindziele() == ['/app/data', '/mnt/belege']


def test_bindziele_bleibt_bei_kaputter_antwort_leer(capsys):
    """Lieber kein chown als ein chown auf einem geratenen Pfad."""
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)

    class Antwort:
        stdout = 'kein json'

    lauf._docker = lambda *a, **k: Antwort()
    assert lauf._bindziele() == []
    assert 'nicht lesbar' in capsys.readouterr().out


def test_aufraeumen_verschluckt_keinen_fehler(tmp_path, monkeypatch, capsys):
    """F-17 blieb unentdeckt, weil ignore_errors den Fehlschlag schluckte."""
    monkeypatch.setattr(e2e.tempfile, 'gettempdir', lambda: str(tmp_path))

    def sperrig(_pfad):
        raise OSError(13, 'Permission denied')

    monkeypatch.setattr(e2e.shutil, 'rmtree', sperrig)
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    eigen = tmp_path / f'{e2e.TEMP_PRAEFIX}abc'
    eigen.mkdir()
    lauf.arbeit = eigen
    lauf.aufraeumen()
    fehlertext = capsys.readouterr().err
    assert str(eigen) in fehlertext
    assert 'Permission denied' in fehlertext


def test_behalten_laesst_den_baum_stehen(tmp_path, capsys):
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=True)
    eigen = tmp_path / f'{e2e.TEMP_PRAEFIX}xyz'
    eigen.mkdir()
    lauf.arbeit = eigen
    lauf.aufraeumen()
    assert eigen.exists()
    assert str(eigen) in capsys.readouterr().out


# --- Akzeptanzpunkt 3: die Marke von 15 Minuten ------------------------------



@pytest.mark.parametrize('dauer, gehalten', [
    (0, True),
    (899, True),
    (900, True),      # genau auf der Marke zaehlt als gehalten
    (901, False),
    (3600, False),
])
def test_marke_gehalten(dauer, gehalten):
    assert e2e.marke_gehalten(dauer) is gehalten


@pytest.mark.parametrize('sekunden, text', [
    (0, '0 s'),
    (59, '59 s'),
    (60, '1 min 00 s'),
    (423, '7 min 03 s'),
    (900, '15 min 00 s'),
])
def test_zeit_in_minuten_und_sekunden(sekunden, text):
    assert e2e.zeit(sekunden) == text


def test_tabelle_meldet_die_gehaltene_marke():
    ausgabe = e2e.tabelle([('bauen', 120.0), ('starten', 30.0)], 150.0)
    assert 'gehalten' in ausgabe
    assert '2 min 00 s' in ausgabe
    assert 'GERISSEN' not in ausgabe


def test_tabelle_meldet_die_gerissene_marke():
    ausgabe = e2e.tabelle([('bauen', 1000.0)], 1000.0)
    assert 'GERISSEN' in ausgabe
    assert '1 min 40 s' in ausgabe   # 1000 - 900 = 100 Sekunden darueber


# --- Die .env, die ein Fremder anlegt ---------------------------------------

def test_env_ohne_schluessel_nur_mit_abweichungen():
    """NK-076: keine .env-Pflicht mehr. Der Lauf setzt nur Port, Nutzer und
    Abbild; einen SECRET_KEY erzeugt die Anwendung selbst im Datenordner."""
    inhalt = e2e.umgebung_bauen(6062, 1000, 1000, 'e2e')
    assert 'APP_PORT=6062' in inhalt
    assert 'PUID=1000' in inhalt and 'PGID=1000' in inhalt
    assert 'NK_VERSION=e2e' in inhalt
    assert 'SECRET_KEY' not in inhalt


def test_die_einrichtung_statt_flask_users_add():
    """E-1/NK-127: Konto im Browser mit dem Code aus dem Protokoll."""
    quelle = (WURZEL / 'scripts' / 'e2e.py').read_text(encoding='utf-8')
    rumpf = quelle.split('def konto_anlegen')[1].split('def ')[0]
    assert '/einrichtung' in rumpf and "'logs'" in rumpf
    assert "'users', 'add'" not in rumpf


def test_compose_braucht_keine_env():
    compose = (WURZEL / 'docker-compose.yml').read_text(encoding='utf-8')
    assert 'env_file' not in compose


def test_das_testpasswort_haelt_die_mindestlaenge():
    """auth.py verlangt zehn Zeichen -- sonst scheitert Schritt 5 im Lauf."""
    assert len(e2e.PASSWORT) >= 10


# --- Argumente --------------------------------------------------------------

def test_gesperrter_port_faellt_schon_im_aufruf_durch(monkeypatch, capsys):
    """6060 kommt nicht durch main() durch -- nicht erst irgendwo im Lauf.

    Der Test selbst laeuft im Container (``make check`` schiebt pytest durch
    ``$(RUN)``), und dort existiert ``/.dockerenv``. Ohne das monkeypatch
    griffe die Wirtspruefung zuerst und die Portsperre kaeme nie an die Reihe
    -- der Test wuerde also etwas anderes messen, als er behauptet.
    """
    monkeypatch.setattr(e2e.Path, 'exists', lambda selbst: False)
    assert e2e.main(['--port', '6060']) == 1
    assert '6060' in capsys.readouterr().err


# --- Zugriffsschluessel: der Weg eines MCP-Servers (#47) ---------------------

class _Antwort:
    """Was ``oeffner.open`` liefert, so weit ``_ruf`` es liest."""

    def __init__(self, inhalt=b'{}', typ='application/json'):
        self._inhalt = inhalt
        self.headers = {'Content-Type': typ}

    def read(self):
        return self._inhalt

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Oeffner:
    def __init__(self, antwort=None, fehler=None):
        self.anfragen = []
        self._antwort = antwort or _Antwort()
        self._fehler = fehler

    def open(self, anfrage, timeout=None):
        self.anfragen.append(anfrage)
        if self._fehler:
            raise self._fehler
        return self._antwort


def _http_fehler(code):
    import io
    import urllib.error
    return urllib.error.HTTPError('http://x', code, 'nein', {}, io.BytesIO(b'{"code": "x"}'))


def test_formular_mit_datei_versteht_werkzeug():
    """urllib baut kein multipart/form-data. Das Skript baut es selbst, und
    der Server muss es so lesen wie das Formular der Oberflaeche."""
    import io

    from werkzeug.formparser import parse_form_data

    rumpf, typ = e2e.formular({'property_id': 7, 'description': 'Sammel'},
                              'stadtwerke.pdf', e2e.PDF)
    umgebung = {'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': typ,
                'CONTENT_LENGTH': str(len(rumpf)), 'wsgi.input': io.BytesIO(rumpf)}
    _, felder, dateien = parse_form_data(umgebung)
    assert felder['property_id'] == '7'
    assert felder['description'] == 'Sammel'
    assert dateien['file'].filename == 'stadtwerke.pdf'
    assert dateien['file'].read() == e2e.PDF


def test_mit_schluessel_ohne_cookie_mit_bearer():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    lauf.oeffner = mit_sitzung = _Oeffner()
    lauf.ohne_sitzung = ohne = _Oeffner()
    lauf._ruf('GET', '/api/properties', schluessel='nkf_probe')
    assert mit_sitzung.anfragen == []
    assert ohne.anfragen[0].get_header('Authorization') == 'Bearer nkf_probe'


def test_ohne_schluessel_bleibt_es_bei_der_sitzung():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    lauf.oeffner = mit_sitzung = _Oeffner()
    lauf.ohne_sitzung = ohne = _Oeffner()
    lauf._ruf('GET', '/api/properties')
    assert ohne.anfragen == []
    assert mit_sitzung.anfragen[0].get_header('Authorization') is None


def test_ein_http_fehler_nennt_seinen_status():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    lauf.ohne_sitzung = _Oeffner(fehler=_http_fehler(403))
    with pytest.raises(e2e.HttpFehler) as fehler:
        lauf._ruf('DELETE', '/api/invoices/1', schluessel='nkf_probe')
    assert fehler.value.status == 403
    assert isinstance(fehler.value, e2e.Abbruch)


def test_erwartete_sperre_ist_kein_abbruch():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    lauf.ohne_sitzung = _Oeffner(fehler=_http_fehler(403))
    lauf._erwarte(403, 'GET', '/api/export', 'nkf_probe')


def test_was_durchgeht_obwohl_es_gesperrt_sein_soll_bricht_ab():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    lauf.ohne_sitzung = _Oeffner()
    with pytest.raises(e2e.Abbruch, match='erwartet war 403'):
        lauf._erwarte(403, 'GET', '/api/export', 'nkf_probe')


def test_ein_anderer_fehler_als_erwartet_bricht_ab():
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    lauf.ohne_sitzung = _Oeffner(fehler=_http_fehler(500))
    with pytest.raises(e2e.HttpFehler):
        lauf._erwarte(403, 'GET', '/api/export', 'nkf_probe')


def test_der_schluesselschritt_laeuft_vor_dem_herunterfahren(tmp_path, monkeypatch):
    lauf = e2e.Lauf(e2e.STANDARD_PORT, cache=False, behalten=False)
    gefahren = []
    schritte = ('baum_auspacken', 'umgebung_anlegen', 'stapel_hoch',
                'gesundheit_abwarten', 'konto_anlegen', 'anmelden',
                'abrechnung_erzeugen', 'zugriffsschluessel', 'stapel_runter')
    for name in schritte:
        monkeypatch.setattr(lauf, name, lambda name=name: gefahren.append(name))
    lauf.arbeit = tmp_path
    lauf.fahren()
    assert gefahren == list(schritte)
