"""Die Windows-App ohne Windows geprüft (NK-079, NK-150).

Fenster und WebView2 braucht nur ``fenster_starten``; alles darum herum --
Start-Token, eine Instanz, Datenordner mit OneDrive-Weiche, die Einrichtung
ohne Einmal-Code und der Selbsttest -- läuft hier unter Linux. Der Lauf
auf windows-latest (``.github/workflows/windows.yml``) fährt dieselben Tests
und zusätzlich das gebaute Paket.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import desktop
import windows_ordner

WURZEL = Path(__file__).resolve().parents[1]


# --- Start-Token ------------------------------------------------------------

def _innen(umgebung, antworten):
    antworten('200 OK', [('Content-Type', 'text/plain')])
    return [b'innen']


def _ruf(schutz, pfad, abfrage='', **kopf):
    ergebnis = {}

    def antworten(status, koepfe):
        ergebnis['status'] = int(status.split()[0])
        ergebnis['koepfe'] = dict(koepfe)

    umgebung = {'PATH_INFO': pfad, 'QUERY_STRING': abfrage}
    umgebung.update({f'HTTP_{k.upper()}': v for k, v in kopf.items()})
    ergebnis['inhalt'] = b''.join(schutz(umgebung, antworten))
    return ergebnis


def test_ohne_token_kommt_niemand_durch():
    schutz = desktop.HuellenSchutz(_innen, 'geheim-123')
    assert _ruf(schutz, '/')['status'] == 403
    assert _ruf(schutz, '/api/health')['status'] == 403
    assert _ruf(schutz, '/', cookie='nk_huelle=falsch')['status'] == 403
    assert _ruf(schutz, '/huelle/start', 't=falsch')['status'] == 403
    assert _ruf(schutz, '/huelle/start')['status'] == 403


def test_der_start_setzt_das_cookie_und_danach_geht_es():
    schutz = desktop.HuellenSchutz(_innen, 'geheim-123')
    start = _ruf(schutz, '/huelle/start', 't=geheim-123')
    assert start['status'] == 302
    assert start['koepfe']['Location'] == '/'
    cookie = start['koepfe']['Set-Cookie']
    assert cookie.startswith('nk_huelle=geheim-123;')
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    drin = _ruf(schutz, '/api/health', cookie='andere=1; nk_huelle=geheim-123')
    assert drin['status'] == 200 and drin['inhalt'] == b'innen'


def test_nach_vorne_nur_mit_token():
    gerufen = []
    schutz = desktop.HuellenSchutz(_innen, 'geheim-123', lambda: gerufen.append(1))
    assert _ruf(schutz, '/huelle/nach-vorne')['status'] == 403
    assert gerufen == []
    assert _ruf(schutz, '/huelle/nach-vorne', x_huelle_token='geheim-123')['status'] == 204
    assert gerufen == [1]


# --- Eine Instanz -----------------------------------------------------------

def test_die_zweite_instanz_bekommt_die_sperre_nicht(tmp_path):
    erste = desktop.EineInstanz(tmp_path)
    zweite = desktop.EineInstanz(tmp_path)
    try:
        assert erste.erwerben() is True
        assert zweite.erwerben() is False
        erste.eintragen(12345, 'abc')
        info = json.loads((tmp_path / 'instanz.json').read_text(encoding='utf-8'))
        assert info == {'port': 12345, 'token': 'abc'}
    finally:
        erste.freigeben()
    assert not (tmp_path / 'instanz.json').exists()
    try:
        assert zweite.erwerben() is True
    finally:
        zweite.freigeben()


def test_wecken_ohne_laufende_instanz_ist_nein(tmp_path):
    assert desktop.EineInstanz(tmp_path).anderen_wecken() is False


# --- Datenordner, OneDrive, Einstellungen ------------------------------------

@pytest.fixture
def lokal(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    for name in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_onedrive_wird_erkannt(tmp_path):
    wolke = tmp_path / 'OneDrive'
    assert windows_ordner.liegt_in_onedrive(wolke / 'Dokumente' / 'NK', [wolke])
    assert windows_ordner.liegt_in_onedrive(wolke, [wolke])
    assert not windows_ordner.liegt_in_onedrive(tmp_path / 'OneDrive2', [wolke])
    assert not windows_ordner.liegt_in_onedrive(tmp_path / 'lokal', [wolke])


def test_einstellungen_rundlauf(lokal):
    assert windows_ordner.einstellungen_lesen() == {
        'datenordner': None, 'sicherungsziele': [], 'onedrive_bestaetigt': False}
    windows_ordner.einstellungen_schreiben(datenordner=lokal / 'Daten')
    windows_ordner.einstellungen_schreiben(
        sicherungsziele=[str(lokal / 'a'), str(lokal / 'b')], onedrive_bestaetigt=True)
    gelesen = windows_ordner.einstellungen_lesen()
    assert gelesen['datenordner'] == str(lokal / 'Daten')
    assert gelesen['sicherungsziele'] == [str(lokal / 'a'), str(lokal / 'b')]
    assert gelesen['onedrive_bestaetigt'] is True
    assert windows_ordner.einstellungen_datei().parent == lokal / 'lokal' / 'NebenkostenFix'


def test_ohne_einstellung_gilt_dokumente(lokal, monkeypatch):
    monkeypatch.setattr(windows_ordner, 'dokumente_ordner', lambda: lokal / 'Dokumente')
    assert desktop.datenordner_bestimmen() == lokal / 'Dokumente' / 'NebenkostenFix'


@pytest.mark.parametrize('antwort', [True, False])
def test_onedrive_fragt_einmal_und_merkt_sich_die_antwort(lokal, monkeypatch, antwort):
    wolke = lokal / 'OneDrive'
    monkeypatch.setenv('OneDrive', str(wolke))
    monkeypatch.setattr(windows_ordner, 'dokumente_ordner', lambda: wolke / 'Dokumente')
    fragen = []
    monkeypatch.setattr(desktop, '_meldung',
                        lambda text, frage=False: fragen.append(text) or antwort)

    erstes = desktop.datenordner_bestimmen()
    zweites = desktop.datenordner_bestimmen()

    assert len(fragen) == 1 and 'OneDrive' in fragen[0]
    if antwort:
        assert erstes == zweites == windows_ordner.lokaler_ausweich()
    else:
        assert erstes == zweites == wolke / 'Dokumente' / 'NebenkostenFix'
        assert windows_ordner.einstellungen_lesen()['onedrive_bestaetigt'] is True


def test_schreibprobe(tmp_path):
    assert windows_ordner.schreibprobe(tmp_path / 'neu') is None
    assert not list((tmp_path / 'neu').iterdir())
    datei = tmp_path / 'eine-datei'
    datei.write_text('x')
    meldung = windows_ordner.schreibprobe(datei / 'darunter')
    assert meldung and 'Überwachte Ordnerzugriff' in meldung


# --- Einrichtung und Passwort in der App --------------------------------------

@pytest.fixture
def als_app(app_ctx, monkeypatch):
    monkeypatch.setitem(app_ctx.app.config, 'DESKTOP', True)
    return app_ctx


def test_einrichtung_in_der_app_ohne_einmal_code(als_app, anon_client):
    seite = anon_client.get('/einrichtung').get_data(as_text=True)
    assert 'Einmal-Code' not in seite and 'name="code"' not in seite
    antwort = anon_client.post('/einrichtung', json={
        'username': 'anna', 'password': 'ein-langes-passwort',
        'password2': 'ein-langes-passwort'})
    assert antwort.status_code in (200, 201), antwort.get_data(as_text=True)
    from models import User
    assert User.query.filter_by(username='anna').count() == 1


def test_einrichtung_im_server_verlangt_den_code(app_ctx, anon_client):
    assert 'name="code"' in anon_client.get('/einrichtung').get_data(as_text=True)
    antwort = anon_client.post('/einrichtung', json={
        'username': 'anna', 'password': 'ein-langes-passwort',
        'password2': 'ein-langes-passwort'})
    assert antwort.status_code == 400


def test_passwort_zuruecksetzen_nur_in_der_app(app_ctx, anon_client, auth_client):
    # Ohne Sitzung greift die Sperre (Seitenaufruf: Umleitung zur Anmeldung).
    gesperrt = anon_client.get('/huelle/passwort')
    assert gesperrt.status_code == 302
    assert gesperrt.headers['Location'].startswith('/login')
    assert anon_client.post('/huelle/passwort', data={}).status_code in (302, 401)
    assert auth_client.get('/huelle/passwort').status_code == 404


def test_passwort_zuruecksetzen_in_der_app(als_app, anon_client):
    from models import User, db
    konto = User(username='anna')
    konto.set_password('das-alte-passwort')
    db.session.add(konto)
    db.session.commit()

    seite = anon_client.get('/huelle/passwort').get_data(as_text=True)
    assert '<option>anna</option>' in seite
    kurz = anon_client.post('/huelle/passwort', data={
        'username': 'anna', 'password': 'kurz', 'password2': 'kurz'})
    assert 'mindestens 10 Zeichen' in kurz.get_data(as_text=True)
    ok = anon_client.post('/huelle/passwort', data={
        'username': 'anna', 'password': 'das-neue-passwort',
        'password2': 'das-neue-passwort'})
    assert 'Passwort gespeichert' in ok.get_data(as_text=True)
    db.session.expire_all()
    assert User.query.filter_by(username='anna').one().check_password('das-neue-passwort')


# --- Selbsttest aus den Quellen ------------------------------------------------

def test_selbsttest_aus_den_quellen(tmp_path):
    """Derselbe Lauf, den die CI mit dem gebauten Paket fährt."""
    pytest.importorskip('waitress')
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ('DATABASE_URL', 'DATA_DIR', 'NAS_MOUNT_PATH', 'SECRET_KEY',
                             'LOCAL_PDF_PATH', 'LOCAL_TEMP_PATH', 'FLASK_ENV')}
    umgebung['LOCALAPPDATA'] = str(tmp_path / 'lokal')
    bericht = tmp_path / 'bericht.json'
    lauf = subprocess.run(
        [sys.executable, 'desktop.py', '--selbsttest',
         '--datenordner', str(tmp_path / 'daten'), '--bericht', str(bericht)],
        cwd=WURZEL, env=umgebung, capture_output=True, text=True, timeout=180)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    ergebnis = json.loads(bericht.read_text(encoding='utf-8'))
    assert ergebnis['ergebnis'] == 'bestanden'
    assert ergebnis['ohne_schluessel'] == 403
    assert ergebnis['pdf_ok'] is True
    assert not ergebnis['wal_nach_checkpoint']
    daten = tmp_path / 'daten'
    assert (daten / 'nebenkosten.db').is_file()
    assert (daten / 'belege').is_dir() and (daten / 'backups').is_dir()


@pytest.mark.parametrize('kodierung', ['cp1252', 'utf-8', 'utf-8-sig', 'utf-16'])
def test_einstellungen_aus_dem_installer_in_jeder_kodierung(lokal, kodierung):
    """Inno Setup legt die Datei ueber die Windows-Schnittstelle an: neu in
    der ANSI-Codepage, in eine vorhandene UTF-16-Datei als Unicode."""
    datei = windows_ordner.einstellungen_datei()
    datei.parent.mkdir(parents=True)
    datei.write_bytes('[Daten]\r\nOrdner=C:\\Users\\Jörg Müller\\Dokumente\\NK\r\n'
                      'OneDriveBestaetigt=0\r\n'.encode(kodierung))
    assert windows_ordner.einstellungen_lesen()['datenordner'] == \
        'C:\\Users\\Jörg Müller\\Dokumente\\NK'
    windows_ordner.einstellungen_schreiben(sicherungsziele=['E:\\Sicherung'])
    assert datei.read_bytes().startswith(b'\xff\xfe')
    gelesen = windows_ordner.einstellungen_lesen()
    assert gelesen['datenordner'] == 'C:\\Users\\Jörg Müller\\Dokumente\\NK'
    assert gelesen['sicherungsziele'] == ['E:\\Sicherung']


# --- Paketprobe der CI ----------------------------------------------------------

def _pe(subsystem: int) -> bytes:
    import struct
    kopf = bytearray(512)
    kopf[:2] = b'MZ'
    struct.pack_into('<I', kopf, 0x3C, 0x80)
    kopf[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', kopf, 0x80 + 24 + 68, subsystem)
    return bytes(kopf)


def test_paketprobe_erkennt_das_konsolenfenster(tmp_path):
    sys.path.insert(0, str(WURZEL / 'packaging' / 'windows'))
    try:
        import paketprobe
    finally:
        sys.path.pop(0)
    fenster = tmp_path / 'fenster.exe'
    fenster.write_bytes(_pe(paketprobe.GUI))
    konsole = tmp_path / 'konsole.exe'
    konsole.write_bytes(_pe(paketprobe.KONSOLE))
    assert paketprobe.probe_fenster(fenster) is True
    assert paketprobe.probe_fenster(konsole) is False
    assert paketprobe.groesse(tmp_path) == 1024
    with pytest.raises(ValueError):
        paketprobe.subsystem(WURZEL / 'desktop.py')


def test_paketprobe_update(tmp_path):
    sys.path.insert(0, str(WURZEL / 'packaging' / 'windows'))
    try:
        import paketprobe
    finally:
        sys.path.pop(0)
    (tmp_path / 'belege').mkdir()
    (tmp_path / 'nebenkosten.db').write_bytes(b'bestand')
    summe = paketprobe.sha256_datei(tmp_path / 'nebenkosten.db')
    assert paketprobe.probe_update(tmp_path, summe, '0.9.0', lambda: ['0.9.0']) is True
    # zwei Eintraege heisst: das Update hat daneben installiert statt darueber
    assert paketprobe.probe_update(tmp_path, summe, '0.9.0', lambda: ['0.0.1', '0.9.0']) is False
    assert paketprobe.probe_update(tmp_path, summe, '0.9.0', lambda: ['0.0.1']) is False
    (tmp_path / 'nebenkosten.db').write_bytes(b'anders')
    assert paketprobe.probe_update(tmp_path, summe, '0.9.0', lambda: ['0.9.0']) is False


# --- D-95: Installationen aus der Zeit vor der Umbenennung ----------------------

def test_vorhandener_alter_datenordner_bleibt(lokal, monkeypatch):
    """Liegen Daten schon in Dokumente\\Nebenkostenabrechnung, bleiben sie dort."""
    monkeypatch.setattr(windows_ordner, 'dokumente_ordner', lambda: lokal / 'Dokumente')
    alt = lokal / 'Dokumente' / 'Nebenkostenabrechnung'
    alt.mkdir(parents=True)
    assert windows_ordner.vorgabe_datenordner() == lokal / 'Dokumente' / 'NebenkostenFix'
    (alt / 'nebenkosten.db').write_bytes(b'bestand')
    assert windows_ordner.vorgabe_datenordner() == alt


def test_alte_einstellungen_werden_einmal_uebernommen(lokal):
    """Die einstellungen.ini des alten lokalen Ordners wandert an den neuen
    Ort; die alte bleibt liegen (Rückweg)."""
    alt = lokal / 'lokal' / 'Nebenkostenabrechnung' / 'einstellungen.ini'
    alt.parent.mkdir(parents=True)
    alt.write_bytes('[Daten]\r\nOrdner=C:\\Users\\Jörg\\Documents\\Nebenkostenabrechnung\r\n'
                    'OneDriveBestaetigt=1\r\n'.encode('cp1252'))
    gelesen = windows_ordner.einstellungen_lesen()
    assert gelesen['datenordner'] == 'C:\\Users\\Jörg\\Documents\\Nebenkostenabrechnung'
    assert gelesen['onedrive_bestaetigt'] is True
    neu = windows_ordner.einstellungen_datei()
    assert neu.parent.name == 'NebenkostenFix' and neu.is_file() and alt.is_file()
    # Danach gilt die neue: eine Änderung dort wird nicht von der alten überschrieben.
    windows_ordner.einstellungen_schreiben(datenordner='D:\\Daten')
    assert windows_ordner.einstellungen_lesen()['datenordner'] == 'D:\\Daten'


def test_datenordner_zeigen(lokal, monkeypatch, tmp_path):
    monkeypatch.setattr(windows_ordner, 'dokumente_ordner', lambda: lokal / 'Dokumente')
    bericht = tmp_path / 'ordner.json'
    assert desktop.main(['--datenordner-zeigen', '--bericht', str(bericht)]) == 0
    assert json.loads(bericht.read_text(encoding='utf-8'))['datenordner'] == \
        str(lokal / 'Dokumente' / 'NebenkostenFix')


def test_startseite_und_fehlerseite():
    seite = desktop.startseite()
    assert '<svg' in seite and 'Nebenkosten<b>Fix</b>' in seite and 'wird gestartet' in seite
    fehler = desktop.fehlerseite('Datenbank <gesperrt>')
    assert '&lt;gesperrt&gt;' in fehler and 'NebenkostenFix konnte nicht starten' in fehler


def test_bruecke_zeigt_pywebview_nur_methoden():
    """pywebview steigt nach jedem Seitenaufbau in jedes öffentliche Attribut
    der Brücke hinab. Hing das Fenster öffentlich daran, lief das durch dessen
    .NET-Objekte und ließ die Oberfläche hängen („Keine Rückmeldung“, 0.9.0)."""
    import inspect
    bruecke = desktop.Bruecke()
    oeffentlich = [name for name in dir(bruecke) if not name.startswith('_')]
    assert oeffentlich
    assert all(inspect.ismethod(getattr(bruecke, name)) for name in oeffentlich)


def test_extern_nur_projektseite_und_kofi(monkeypatch):
    """NK-175/NK-179: der Standardbrowser öffnet nur Projektseite und Ko-fi."""
    import marke
    import webbrowser
    geoeffnet = []
    monkeypatch.setattr(webbrowser, 'open', lambda adresse: geoeffnet.append(adresse) or True)
    bruecke = desktop.Bruecke()
    erlaubt = [marke.REPO_URL, marke.REPO_URL + '/releases/tag/v1.0.0', marke.KOFI_URL]
    for adresse in erlaubt:
        assert bruecke.extern_oeffnen(adresse)
    for adresse in (marke.REPO_URL + '.boese.example', 'https://example.com/',
                    'file:///C:/Windows/System32/calc.exe', marke.KOFI_URL + 'x'):
        assert not bruecke.extern_oeffnen(adresse)
    assert geoeffnet == erlaubt


def test_paket_waehlen_hat_gueltige_dateifilter(monkeypatch, tmp_path):
    """pywebview prüft jeden Eintrag in file_types und wirft sonst ValueError;
    die Oberfläche meldete dann nur „Der Datei-Dialog ließ sich nicht öffnen.“
    (0.9.2, Bindestrich in „NebenkostenFix-Paket“)."""
    import re
    import types

    import umzug
    # Aus pywebview 6.2.1, webview/util.py parse_file_type
    gueltig = r'^([\w ]+)\((\*(?:\.(?:\w+|\*))*(?:;\*(?:\.(?:\w+|\*))*)*)\)$'
    paket = tmp_path / 'umzug.nkfix'
    paket.write_bytes(b'')

    class Fenster:
        def create_file_dialog(self, art, file_types=(), **_):
            for filter_ in file_types:
                if not re.search(gueltig, filter_):
                    raise ValueError(f'{filter_} is not a valid file filter')
            return (str(paket),)

    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(OPEN_DIALOG=10))
    monkeypatch.setattr(umzug, '_freigegeben', set())
    bruecke = desktop.Bruecke()
    bruecke._fenster = Fenster()
    assert bruecke.paket_waehlen() == os.path.realpath(paket)


def test_pdf_oeffnet_auf_der_angegebenen_seite(monkeypatch, tmp_path):
    """os.startfile kennt keinen Anker: das PDF ging auf Seite 1 auf statt
    auf der Seite der Rechnung (#page=N im Browser, Fund 0.9.2). Mit Seite
    öffnet die App eine Weiterleitung, die den Anker mitnimmt."""
    import base64
    monkeypatch.setattr(desktop.tempfile, 'gettempdir', lambda: str(tmp_path))
    inhalt = base64.b64encode(b'%PDF-1.4').decode()
    bruecke = desktop.Bruecke()

    ohne = Path(bruecke.oeffnen('rechnung.pdf', inhalt))
    assert ohne.suffix == '.pdf' and ohne.read_bytes() == b'%PDF-1.4'

    mit = Path(bruecke.oeffnen('rechnung.pdf', inhalt, 3))
    assert mit.suffix == '.html'
    assert f'{ohne.as_uri()}#page=3' in mit.read_text(encoding='utf-8')
