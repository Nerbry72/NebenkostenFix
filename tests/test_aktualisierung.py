"""Updates über GitHub Releases, ohne Lizenz (NK-081, NK-175, NK-176)."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import aktualisierung
import einstellungen
import marke
from aktualisierung import AktualisierungsFehler

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = 'https://beispiel.invalid/update.json'
SETUP = 'https://beispiel.invalid/setup.exe'
JETZT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def schluessel(monkeypatch):
    privat = Ed25519PrivateKey.generate()
    oeffentlich = base64.b64encode(privat.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode('ascii')
    monkeypatch.setattr(aktualisierung, 'HERAUSGEBER_SCHLUESSEL', oeffentlich)
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: False)
    return privat


@pytest.fixture
def quelle(monkeypatch):
    monkeypatch.setenv('NK_UPDATE_QUELLE', QUELLE)
    return QUELLE


def _manifest(privat, **daten):
    werte = {'version': '0.9.1', 'veroeffentlicht': '2027-03-01',
             'hinweise': 'Kleinigkeiten.',
             'docker': 'ghcr.io/nerbry72/nebenkostenfix:0.9.1',
             'windows': {'url': SETUP, 'sha256': hashlib.sha256(b'SETUP').hexdigest()}}
    werte.update(daten)
    return json.dumps(aktualisierung.signieren(werte, privat)).encode()


def _lader(antworten, gefragt=None):
    def laden(adresse, grenze, zeit=20):
        aktualisierung._https(adresse)
        if gefragt is not None:
            gefragt.append((adresse, zeit))
        return antworten[adresse]
    return laden


# --- Quelle und Manifest ----------------------------------------------------------

def test_quelle_zeigt_auf_die_projektseite(monkeypatch):
    monkeypatch.delenv('NK_UPDATE_QUELLE', raising=False)
    assert aktualisierung.quelle() == (
        f'{marke.REPO_URL}/releases/latest/download/update.json')


def test_versionen_vergleichen():
    assert aktualisierung.version_als_tupel('0.10.0') > aktualisierung.version_als_tupel('0.9.9')
    assert aktualisierung.version_als_tupel('1.0.0-rc1') == (1, 0, 0)
    with pytest.raises(AktualisierungsFehler):
        aktualisierung.version_als_tupel('neu')


def test_ohne_quelle_keine_suche(monkeypatch):
    monkeypatch.delenv('NK_UPDATE_QUELLE', raising=False)
    monkeypatch.setattr(aktualisierung, 'UPDATE_QUELLE', '')
    with pytest.raises(AktualisierungsFehler, match='keine Update-Quelle'):
        aktualisierung.suchen('0.9.0', desktop=True)


def test_ohne_herausgeberschluessel_kein_manifest(monkeypatch, quelle):
    monkeypatch.setattr(aktualisierung, 'HERAUSGEBER_SCHLUESSEL', '')
    gefragt = []
    laden = _lader({quelle: _manifest(Ed25519PrivateKey.generate())}, gefragt)
    with pytest.raises(AktualisierungsFehler, match='Herausgeberschlüssel'):
        aktualisierung.suchen('0.9.0', desktop=True, laden=laden)
    assert gefragt == []  # kein Netzabruf, wenn nichts prüfbar ist


def test_eingebauter_herausgeberschluessel_ist_gueltig():
    """Ein Tippfehler im Schlüssel ließe jede installierte App alle Updates ablehnen."""
    assert aktualisierung.schluessel_laden() is not None


def test_nur_https(monkeypatch, schluessel, kein_update_netz):
    # Die Prüfung sitzt im echten Lader und greift vor jedem Netzzugriff.
    monkeypatch.setattr(aktualisierung, '_laden', kein_update_netz)
    monkeypatch.setenv('NK_UPDATE_QUELLE', 'http://beispiel.invalid/m.json')
    with pytest.raises(AktualisierungsFehler, match='https'):
        aktualisierung.suchen('0.9.0', desktop=True)


def test_neue_version_fuer_alle(schluessel, quelle):
    """Keine Lizenz mehr: jedes Update ist installierbar (NK-176)."""
    laden = _lader({quelle: _manifest(schluessel, veroeffentlicht='2030-01-01')})
    ergebnis = aktualisierung.suchen('0.9.0', desktop=True, laden=laden)
    assert ergebnis['neu'] and ergebnis['installierbar']
    assert 'lizenz_erlaubt' not in ergebnis
    assert ergebnis['notizen'] == f'{marke.REPO_URL}/releases'
    docker = aktualisierung.suchen('0.9.0', desktop=False, laden=laden)
    assert not docker['installierbar'] and 'docker compose pull' in docker['text']


def test_notizen_nur_von_der_projektseite(schluessel, quelle):
    eigen = f'{marke.REPO_URL}/releases/tag/v0.9.1'
    laden = _lader({quelle: _manifest(schluessel, notizen=eigen)})
    assert aktualisierung.suchen('0.9.0', True, laden=laden)['notizen'] == eigen
    laden = _lader({quelle: _manifest(schluessel, notizen='https://boese.invalid/')})
    assert aktualisierung.suchen('0.9.0', True, laden=laden)['notizen'] == (
        f'{marke.REPO_URL}/releases')


def test_aeltere_oder_gleiche_version_ist_nicht_neu(schluessel, quelle):
    for version in ('0.9.0', '0.8.5'):
        laden = _lader({quelle: _manifest(schluessel, version=version)})
        ergebnis = aktualisierung.suchen('0.9.0', desktop=True, laden=laden)
        assert not ergebnis['neu'] and not ergebnis['installierbar']
        assert 'neueste Version' in ergebnis['text']
        with pytest.raises(AktualisierungsFehler, match='keine neuere'):
            aktualisierung.installer_laden('0.9.0', laden=laden)


def test_gefaelschtes_manifest(schluessel, quelle):
    laden = _lader({quelle: _manifest(Ed25519PrivateKey.generate())})
    with pytest.raises(AktualisierungsFehler, match='nicht vertrauenswürdig'):
        aktualisierung.suchen('0.9.0', desktop=True, laden=laden)
    # Nachträglich verändert: gleiche Signatur, andere Daten.
    umschlag = json.loads(_manifest(schluessel))
    umschlag['daten']['windows']['url'] = 'https://boese.invalid/setup.exe'
    laden = _lader({quelle: json.dumps(umschlag).encode()})
    with pytest.raises(AktualisierungsFehler, match='Signatur passt nicht'):
        aktualisierung.suchen('0.9.0', desktop=True, laden=laden)


def test_installer_mit_pruefsumme(schluessel, quelle, tmp_path):
    antworten = {quelle: _manifest(schluessel), SETUP: b'SETUP'}
    datei = aktualisierung.installer_laden('0.9.0', laden=_lader(antworten), ziel=tmp_path)
    assert datei.read_bytes() == b'SETUP'
    assert datei.name == 'NebenkostenFix-0.9.1-Setup.exe'
    antworten[SETUP] = b'BOESE'
    with pytest.raises(AktualisierungsFehler, match='Prüfsumme'):
        aktualisierung.installer_laden('0.9.0', laden=_lader(antworten), ziel=tmp_path)


def test_installer_startet_still_und_die_app_danach_wieder():
    quelltext = (WURZEL / 'aktualisierung.py').read_text(encoding='utf-8')
    assert "'/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NEUSTART=1']" in quelltext
    assert 'subprocess.Popen(befehl, close_fds=True)' in quelltext
    # Der normale Start-Haken trägt skipifsilent; ohne eigenen Eintrag bliebe
    # die App nach dem stillen Update geschlossen.
    iss = (WURZEL / 'packaging/windows/installer.iss').read_text(encoding='utf-8')
    assert ('Filename: "{app}\\{#AppExe}"; Flags: nowait runasoriginaluser; '
            'Check: NachUpdateStarten\n') in iss
    assert "WizardSilent and (ExpandConstant('{param:NEUSTART|0}') = '1')" in iss


def test_paketmodus_schaltet_den_updater_ab(schluessel, quelle, monkeypatch, tmp_path):
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: True)
    laden = _lader({quelle: _manifest(schluessel)})
    ergebnis = aktualisierung.suchen('0.9.0', desktop=True, laden=laden)
    assert ergebnis['neu'] and not ergebnis['installierbar']
    assert 'Microsoft Store' in ergebnis['text']
    with pytest.raises(AktualisierungsFehler, match='Microsoft Store'):
        aktualisierung.installer_laden('0.9.0', laden=laden, ziel=tmp_path)
    gefragt = []
    assert aktualisierung.automatisch('0.9.0', True, tmp_path,
                                      laden=_lader({}, gefragt), jetzt=JETZT) is None
    assert gefragt == []


def test_paketmodus_ausserhalb_von_windows_aus():
    assert aktualisierung.paketmodus() is False


# --- Suche beim Start (NK-175) ----------------------------------------------------

def test_automatisch_findet_und_erinnert_beim_naechsten_start(schluessel, quelle, tmp_path):
    gefragt = []
    laden = _lader({quelle: _manifest(schluessel)}, gefragt)
    ergebnis = aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden, jetzt=JETZT)
    assert ergebnis['neu'] and ergebnis['version'] == '0.9.1'
    assert gefragt == [(quelle, aktualisierung.AUTOMATISCH_ZEIT_S)]
    # „Später erinnern“: der nächste Start, auch eine Minute später, meldet es wieder.
    wieder = aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden,
                                        jetzt=JETZT + timedelta(minutes=1))
    assert wieder['version'] == '0.9.1' and len(gefragt) == 2


def test_automatisch_hoechstens_alle_24_stunden(schluessel, quelle, tmp_path):
    gefragt = []
    laden = _lader({quelle: _manifest(schluessel, version='0.9.0')}, gefragt)
    assert aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden, jetzt=JETZT) is None
    assert einstellungen.lesen(tmp_path)['update_geprueft'] == JETZT.isoformat()
    kurz_davor = JETZT + timedelta(hours=23, minutes=59)
    aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden, jetzt=kurz_davor)
    assert len(gefragt) == 1
    aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden,
                               jetzt=JETZT + timedelta(hours=24))
    assert len(gefragt) == 2
    # Eine Uhr, die zurückgestellt wurde, sperrt die Suche nicht für immer.
    aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden,
                               jetzt=JETZT - timedelta(days=3))
    assert len(gefragt) == 3


def test_automatisch_aus_heisst_keine_abfrage(quelle, tmp_path):
    einstellungen.schreiben(tmp_path, updates_automatisch=False)
    gefragt = []
    assert aktualisierung.automatisch('0.9.0', True, tmp_path,
                                      laden=_lader({}, gefragt), jetzt=JETZT) is None
    assert gefragt == []


def test_automatisch_ohne_netz_still(quelle, tmp_path, schluessel):
    def kein_netz(adresse, grenze, zeit=20):
        raise OSError('kein Netz')
    assert aktualisierung.automatisch('0.9.0', True, tmp_path, laden=kein_netz,
                                      jetzt=JETZT) is None
    # Gezählt wird der Versuch, sonst fragte eine App ohne Netz bei jedem Start.
    assert einstellungen.lesen(tmp_path)['update_geprueft'] == JETZT.isoformat()
    kaputt = _lader({quelle: b'kein json'})
    assert aktualisierung.automatisch('0.9.0', True, tmp_path, laden=kaputt,
                                      jetzt=JETZT + timedelta(days=2)) is None


def test_automatisch_ohne_neue_version_nichts(schluessel, quelle, tmp_path):
    laden = _lader({quelle: _manifest(schluessel, version='0.9.0')})
    assert aktualisierung.automatisch('0.9.0', True, tmp_path, laden=laden,
                                      jetzt=JETZT) is None


# --- Einstellungen --------------------------------------------------------------

def test_einstellungen_kaputte_datei_ist_werkseinstellung(tmp_path):
    (tmp_path / einstellungen.DATEINAME).write_text('{kaputt', encoding='utf-8')
    assert einstellungen.lesen(tmp_path) == einstellungen.STANDARD
    with pytest.raises(KeyError):
        einstellungen.schreiben(tmp_path, unbekannt=1)
    einstellungen.schreiben(tmp_path, updates_automatisch=False)
    assert einstellungen.lesen(tmp_path)['updates_automatisch'] is False


# --- API und Oberfläche ----------------------------------------------------------

def test_api_update_suche(schluessel, auth_client, monkeypatch):
    monkeypatch.setenv('NK_UPDATE_QUELLE', QUELLE)
    monkeypatch.setattr(aktualisierung, '_laden', _lader(
        {QUELLE: _manifest(schluessel, version='99.0.0')}))
    ergebnis = auth_client.get('/api/aktualisierung').get_json()
    assert ergebnis['neu'] is True
    assert ergebnis['installierbar'] is False   # Docker: nur der Hinweis

    def kein_netz(adresse, grenze, zeit=20):
        raise OSError('kein Netz')
    monkeypatch.setattr(aktualisierung, '_laden', kein_netz)
    assert auth_client.get('/api/aktualisierung').status_code == 502
    # Beim Start still: kein Fehler, nur „nichts Neues“.
    automatisch = auth_client.get('/api/aktualisierung/automatisch')
    assert automatisch.status_code == 200 and automatisch.get_json() == {'neu': False}
    # Installieren gibt es nur in der Windows-App.
    assert auth_client.post('/api/aktualisierung/installieren').status_code == 400


def test_api_einstellung(auth_client, monkeypatch, tmp_path):
    import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    assert auth_client.get('/api/aktualisierung/einstellung').get_json()['automatisch'] is True
    assert auth_client.put('/api/aktualisierung/einstellung',
                           json={'automatisch': 'ja'}).status_code == 400
    aus = auth_client.put('/api/aktualisierung/einstellung', json={'automatisch': False})
    assert aus.get_json()['automatisch'] is False
    assert einstellungen.lesen(tmp_path)['updates_automatisch'] is False


def test_installieren_sichert_vorher(schluessel, auth_client, monkeypatch, tmp_path):
    import backup
    from app import app
    reihenfolge = []
    monkeypatch.setitem(app.config, 'DESKTOP', True)
    monkeypatch.setattr(aktualisierung, 'installer_laden',
                        lambda version: reihenfolge.append('laden') or tmp_path / 'x.exe')
    monkeypatch.setattr(backup, 'sicherung_erstellen',
                        lambda *a, **k: reihenfolge.append(('sichern', k['praefix'])))
    monkeypatch.setattr(aktualisierung, 'installer_starten',
                        lambda datei: reihenfolge.append('starten'))
    antwort = auth_client.post('/api/aktualisierung/installieren')
    assert antwort.status_code == 200, antwort.get_json()
    assert reihenfolge == ['laden', ('sichern', 'sicherung-vor-update'), 'starten']

    def scheitert(*a, **k):
        raise backup.SicherungsFehler('voll')
    reihenfolge.clear()
    monkeypatch.setattr(backup, 'sicherung_erstellen', scheitert)
    assert auth_client.post('/api/aktualisierung/installieren').status_code == 400
    assert 'starten' not in reihenfolge


def test_keine_lizenz_mehr_in_der_anwendung():
    """NK-176: kein Lizenzmodul, keine Lizenzkarte, keine Lizenzroute."""
    assert not (WURZEL / 'lizenz.py').exists()
    seite = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
    skript = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
    for rest in ('lizenz-stand', 'lizenzEinspielen', 'data-gruppe="lizenz"'):
        assert rest not in seite, rest
    assert '/api/lizenz' not in skript and 'ladeLizenz' not in skript
    for datei in WURZEL.glob('*.py'):
        text = datei.read_text(encoding='utf-8')
        assert 'import lizenz' not in text and 'from lizenz' not in text, datei.name


# --- Werkzeug des Herausgebers --------------------------------------------------

def test_werkzeug_rundlauf(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(WURZEL / 'scripts'))
    try:
        import update_signieren as werkzeug
    finally:
        sys.path.pop(0)
    datei = tmp_path / 'herausgeber.pem'
    oeffentlich = werkzeug.schluessel_erzeugen(datei)
    assert oct(datei.stat().st_mode & 0o777) == '0o600' or sys.platform == 'win32'
    with pytest.raises(SystemExit):
        werkzeug.schluessel_erzeugen(datei)   # nie überschreiben
    monkeypatch.setattr(aktualisierung, 'HERAUSGEBER_SCHLUESSEL', oeffentlich)

    setup = tmp_path / 'setup.exe'
    setup.write_bytes(b'SETUP')
    notizen = f'{marke.REPO_URL}/releases/tag/v0.9.1'
    assert werkzeug.main(['manifest', str(datei), '--version', '0.9.1', '--installer', str(setup),
                          '--url', SETUP, '--notizen', notizen,
                          '--ausgabe', str(tmp_path / 'update.json')]) == 0
    daten = aktualisierung.manifest_pruefen((tmp_path / 'update.json').read_bytes())
    assert daten['windows']['sha256'] == hashlib.sha256(b'SETUP').hexdigest()
    assert daten['notizen'] == notizen


# --- Haftungshinweis (NK-174) ---------------------------------------------------

def test_api_haftung(auth_client, monkeypatch, tmp_path):
    import datenordner
    import haftung
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    stand = auth_client.get('/api/haftung').get_json()
    assert stand['bestaetigt'] is False and stand['version'] == haftung.VERSION
    assert any('keine Haftung' in satz for satz in stand['text'])
    alt = auth_client.post('/api/haftung', json={'version': haftung.VERSION - 1})
    assert alt.status_code == 409
    assert auth_client.post('/api/haftung', json={'version': haftung.VERSION}).get_json()[
        'bestaetigt'] is True
    # Neue Fassung: der Hinweis kommt noch einmal.
    monkeypatch.setattr(haftung, 'VERSION', haftung.VERSION + 1)
    assert auth_client.get('/api/haftung').get_json()['bestaetigt'] is False


def test_einstellungen_gleichzeitig_geht_nichts_verloren(tmp_path):
    """Suche beim Start und „Verstanden“ zugleich: jede Änderung bleibt."""
    import threading

    fehler = []

    def schreibe(feld, werte):
        try:
            for wert in werte:
                einstellungen.schreiben(tmp_path, **{feld: wert})
        except Exception as e:  # noqa: BLE001 - jeder Fehler zählt
            fehler.append(e)

    faeden = [threading.Thread(target=schreibe, args=('update_geprueft', [str(i) for i in range(150)])),
              threading.Thread(target=schreibe, args=('haftung', [{'version': i} for i in range(150)]))]
    for faden in faeden:
        faden.start()
    for faden in faeden:
        faden.join()
    assert fehler == []
    stand = einstellungen.lesen(tmp_path)
    assert stand['update_geprueft'] == '149' and stand['haftung'] == {'version': 149}
