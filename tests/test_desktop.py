"""Die Windows-App ohne Windows geprüft (NK-079, NK-150).

Fenster und WebView2 braucht nur ``fenster_starten``; alles darum herum --
Start-Token, eine Instanz, Datenordner mit OneDrive-Weiche, die Einrichtung
ohne Einmal-Code und der Selbsttest -- läuft hier unter Linux. Der Lauf
auf windows-latest (``.github/workflows/windows.yml``) fährt dieselben Tests
und zusätzlich das gebaute Paket.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

import desktop
from nebenkostenfix import windows_ordner

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
        'datenordner': None, 'sicherungsziele': [], 'onedrive_bestaetigt': False,
        'server': None}
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
    from nebenkostenfix.models import User
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
    from nebenkostenfix.models import User, db
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


def _abschnitte(datei):
    import configparser
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(windows_ordner._ini_text(datei))
    return {name: dict(parser[name]) for name in parser.sections()}


def test_server_adresse_rundlauf(lokal):
    """#45: setzen, lesen, mit None entfernen; ein leerer Abschnitt geht mit."""
    windows_ordner.einstellungen_schreiben(server='https://nas.example:8443')
    assert windows_ordner.einstellungen_lesen()['server'] == 'https://nas.example:8443'
    datei = windows_ordner.einstellungen_datei()
    assert _abschnitte(datei) == {'Server': {'adresse': 'https://nas.example:8443'}}
    windows_ordner.einstellungen_schreiben(server=None)
    assert windows_ordner.einstellungen_lesen()['server'] is None
    assert _abschnitte(datei) == {}
    windows_ordner.einstellungen_schreiben(server='http://nas')
    windows_ordner.einstellungen_schreiben(server='')
    assert windows_ordner.einstellungen_lesen()['server'] is None


def test_daten_schreiben_behaelt_server(lokal):
    """So schreibt auch eine alte App: [Server] und fremde Abschnitte bleiben."""
    datei = windows_ordner.einstellungen_datei()
    datei.parent.mkdir(parents=True)
    datei.write_bytes('[Daten]\r\nOrdner=C:\\Daten\r\n[Server]\r\nAdresse=https://nas\r\n'
                      '[Fremd]\r\nSchluessel=1\r\n'.encode('cp1252'))
    windows_ordner.einstellungen_schreiben(datenordner='D:\\Neu')
    windows_ordner.einstellungen_schreiben(onedrive_bestaetigt=True)
    assert _abschnitte(datei) == {
        'Daten': {'ordner': 'D:\\Neu', 'onedrivebestaetigt': '1'},
        'Server': {'adresse': 'https://nas'}, 'Fremd': {'schluessel': '1'}}
    # Der Rückweg nimmt nur die Adresse, alles andere bleibt.
    windows_ordner.einstellungen_schreiben(server=None)
    assert _abschnitte(datei) == {
        'Daten': {'ordner': 'D:\\Neu', 'onedrivebestaetigt': '1'}, 'Fremd': {'schluessel': '1'}}


def test_ini_schreiben_atomar(lokal, monkeypatch):
    """Scheitert das Ersetzen, liegt die alte Datei unverändert da."""
    windows_ordner.einstellungen_schreiben(datenordner='C:\\Daten')
    datei = windows_ordner.einstellungen_datei()
    vorher = datei.read_bytes()

    def kaputt(*_):
        raise OSError('Platte voll')

    monkeypatch.setattr(windows_ordner.os, 'replace', kaputt)
    with pytest.raises(OSError):
        windows_ordner.einstellungen_schreiben(server='https://nas')
    assert datei.read_bytes() == vorher


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


def _pascal_block(quelle: str, kopf: str) -> str:
    """Eine Routine aus dem [Code] des Installers, bis zur nächsten."""
    anfang = quelle.index(kopf)
    folgende = [quelle.find(k, anfang + 1) for k in ('\nprocedure ', '\nfunction ')]
    return quelle[anfang:min([f for f in folgende if f != -1], default=len(quelle))]


def test_deinstallation_entfernt_einstellungen_nur_auf_wunsch_und_nie_daten():
    """#45: Wer will, nimmt beim Deinstallieren die Einstellungen dieses Rechners
    mit (sonst startet eine Neuinstallation wieder verbunden). Daten nie."""
    import re
    iss = (WURZEL / 'packaging/windows/installer.iss').read_text(encoding='utf-8')
    schritt = _pascal_block(iss, 'procedure CurUninstallStepChanged')
    entfernen = _pascal_block(iss, 'procedure EinstellungenEntfernen')
    # Gefragt wird vor dem Entfernen, Vorgabe Nein; still nur mit Parameter.
    assert 'CurUninstallStep = usUninstall' in schritt
    assert 'MB_YESNO or MB_DEFBUTTON2) = IDYES' in schritt
    # Die Frage nennt, was mit dem WebView2-Profil geht, und dass lokale Konten bleiben.
    frage = re.sub(r"' \+\s*'", '', schritt)
    for teil in ('Verbindung zu einem Server und die Anmeldung dort', 'Anzeige',
                 'Fortschritt von Assistenten', 'Ihre Daten und Benutzerkonten bleiben'):
        assert teil in frage, teil
    assert ("if UninstallSilent then\n      Entfernen := "
            "ExpandConstant('{param:EINSTELLUNGEN|0}') = '1'") in schritt
    assert 'if Entfernen then\n      EinstellungenEntfernen;' in schritt
    # Gelöscht wird gezielt: der Abschnitt [Server], nie [Daten] ...
    assert "DeleteIniSection('Server', Ini);" in entfernen
    assert not re.search(r"DeleteIni\w*\('Daten'", iss)
    assert '[UninstallDelete]' not in iss and 'uninsdelete' not in iss
    # ... und rekursiv nur das WebView2-Profil, nie der lokale Ordner, in dem
    # der OneDrive-Ausweich „Daten“ liegen kann, und nie mit dem Datenordner darin.
    assert re.findall(r'DelTree\(([^,]*),', iss) == ["Lokal + '\\WebView2'"]
    assert ("if not LiegtUnter(Daten, Lokal + '\\WebView2') then\n"
            "    DelTree(Lokal + '\\WebView2', True, True, True);") in entfernen
    assert re.findall(r'DeleteFile\(([^)]*)\)', entfernen) == [
        "Lokal + '\\konsole.log'", "Lokal + '\\app-einstellungen.json'"]
    # app-einstellungen.json gehört dem Datenordner, wenn er der lokale Ordner ist.
    # Erkannt an der Datenbank daneben, nicht am Pfad: --datenordner, DATA_DIR,
    # Junction oder Kurzname stehen nicht in der INI.
    assert ("if not FileExists(Lokal + '\\nebenkosten.db') then\n"
            "    DeleteFile(Lokal + '\\app-einstellungen.json');") in entfernen
    # Die Schlussmeldung, wo die Daten liegen, bleibt.
    assert 'bleiben erhalten in:' in schritt


def test_paketprobe_prueft_die_einstellungen_nach_der_deinstallation(lokal):
    import shutil
    sys.path.insert(0, str(WURZEL / 'packaging' / 'windows'))
    try:
        import paketprobe
    finally:
        sys.path.pop(0)
    daten = str(lokal / 'Dokumente' / 'NebenkostenFix')
    windows_ordner.einstellungen_schreiben(datenordner=daten)
    paketprobe.lokale_reste_anlegen()
    ordner = windows_ordner.lokaler_ordner()
    # Ohne Parameter bleibt alles.
    assert paketprobe.probe_lokale_reste(False, daten) is True
    assert paketprobe.probe_lokale_reste(True, daten) is False
    # So wie der Deinstaller mit /EINSTELLUNGEN=1.
    windows_ordner.einstellungen_schreiben(server=None)
    shutil.rmtree(ordner / 'WebView2')
    (ordner / 'konsole.log').unlink()
    (ordner / 'app-einstellungen.json').unlink()
    assert paketprobe.probe_lokale_reste(True, daten) is True
    assert paketprobe.probe_lokale_reste(False, daten) is False
    # [Daten] verändert oder der lokale Ausweich leer heißt: nicht bestanden.
    assert paketprobe.probe_lokale_reste(True, str(lokal / 'anders')) is False
    (ordner / 'Daten' / 'probe.txt').unlink()
    assert paketprobe.probe_lokale_reste(True, daten) is False


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
    from nebenkostenfix import marke
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

    from nebenkostenfix import umzug
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


def test_haengendes_update_ueber_die_vorversion_bricht_nach_sieben_minuten_ab():
    """Der Schritt dauert wenige Minuten; hängt der Installer, soll er
    nicht den ganzen Windows-Lauf blockieren (NK-239). Seit #45 deinstalliert
    er zweimal: ohne und mit /EINSTELLUNGEN=1."""
    windows = (WURZEL / '.github/workflows/windows.yml').read_text(encoding='utf-8')
    schritt = windows.split('- name: Vorversion (vor der Umbenennung) installieren', 1)[1]
    schritt = schritt.split('- name:', 1)[0]
    assert '\n        timeout-minutes: 7\n' in schritt
    reihenfolge = ['paketprobe.py lokale-reste\n', ' $daten behalten\n',
                   'installation-neu.log', ' $daten entfernen\n']
    stellen = [schritt.find(t) for t in reihenfolge]
    assert -1 not in stellen and stellen == sorted(stellen)


def _paketprobe():
    sys.path.insert(0, str(WURZEL / 'packaging' / 'windows'))
    try:
        import paketprobe
    finally:
        sys.path.pop(0)
    return paketprobe


def test_paketprobe_beendet_ein_haengendes_programm_nach_der_frist(monkeypatch, capsys):
    """Die Probe wartet nicht länger als ihre Frist und meldet den Abbruch
    (NK-239: der Update-Schritt hing über das timeout-minutes hinaus)."""
    paketprobe = _paketprobe()
    monkeypatch.setattr(paketprobe, 'FRIST', 1)
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    assert paketprobe._starten([sys.executable, '-c', 'import time; time.sleep(60)']) is None
    assert 'ZEITÜBERSCHREITUNG' in capsys.readouterr().out
    assert paketprobe._starten([sys.executable, '-c', 'print("ok")']) == 0


def test_paketprobe_haelt_den_ci_schritt_nicht_ueber_kindprozesse_offen():
    """Ein Kindprozess, der weiterläuft, erbt nicht die Ausgabe des Schritts.
    Sonst wartet der Runner auf ihn, obwohl die Probe längst fertig ist
    (NK-239)."""
    enkel = ('import subprocess, sys; '
             'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])')
    probe = (f'import sys; sys.path.insert(0, {str(WURZEL / "packaging" / "windows")!r}); '
             f'import paketprobe; paketprobe._starten([sys.executable, "-c", {enkel!r}])')
    lauf = subprocess.run([sys.executable, '-c', probe], capture_output=True, timeout=10,
                          env={k: v for k, v in os.environ.items() if k != 'GITHUB_STEP_SUMMARY'})
    assert lauf.returncode == 0


# --- Öffnen nur bekannter Dateitypen (#45, Commit 1) ----------------------------

class _SpeicherFenster:
    """Ersatz für das pywebview-Fenster: merkt sich den Speichern-Dialog."""

    def __init__(self, ziel):
        self.ziel = ziel
        self.dialoge = []

    def create_file_dialog(self, art, save_filename=None, **_):
        self.dialoge.append(save_filename)
        return str(self.ziel)


@pytest.fixture
def oeffnen_umgebung(monkeypatch, tmp_path):
    """Temp-Ordner, pywebview-Ersatz und gestartete Dateien wie unter Windows."""
    import types
    gestartet = []
    monkeypatch.setattr(desktop.tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))
    (tmp_path / 'temp').mkdir()
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(SAVE_DIALOG=30))
    monkeypatch.setattr(desktop.os, 'startfile', lambda pfad: gestartet.append(Path(pfad)),
                        raising=False)
    monkeypatch.setattr(desktop.sys, 'platform', 'win32')
    bruecke = desktop.Bruecke()
    bruecke._fenster = _SpeicherFenster(tmp_path / 'gespeichert.bin')
    return bruecke, gestartet, tmp_path


def test_oeffnen_startet_keine_unbekannten_typen(oeffnen_umgebung):
    """Der Name kommt aus dem Upload: „rechnung.pdf.exe“ startet nicht,
    sondern geht in den Speichern-Dialog (Altbestand bleibt erreichbar)."""
    import base64
    bruecke, gestartet, tmp_path = oeffnen_umgebung
    ergebnis = bruecke.oeffnen('rechnung.pdf.exe', base64.b64encode(b'MZ').decode())
    assert gestartet == []
    assert bruecke._fenster.dialoge == ['rechnung.pdf.exe']
    assert ergebnis == str(tmp_path / 'gespeichert.bin')
    assert (tmp_path / 'gespeichert.bin').read_bytes() == b'MZ'
    assert not list((tmp_path / 'temp').rglob('*.exe'))


def test_oeffnen_bereinigt_dateinamen(oeffnen_umgebung):
    import base64
    bruecke, gestartet, tmp_path = oeffnen_umgebung
    inhalt = base64.b64encode(b'%PDF').decode()
    assert Path(bruecke.oeffnen('a:b.pdf', inhalt)).name == 'a_b.pdf'
    temp = (tmp_path / 'temp' / 'NebenkostenFix').resolve()
    for boese in ('..\\x.pdf', '../x.pdf', 'C:\\Windows\\x.pdf'):
        pfad = Path(bruecke.oeffnen(boese, inhalt)).resolve()
        assert pfad.parent == temp, boese
    assert all(p.parent == temp for p in gestartet)
    assert bruecke._fenster.dialoge == []
    bruecke.oeffnen('x.pdf:strom', inhalt)  # ADS-Strom: keine bekannte Endung mehr
    bruecke.oeffnen('..', inhalt)
    assert bruecke._fenster.dialoge == ['x.pdf_strom', 'datei']


def test_oeffnen_bekannte_typen_wie_bisher(oeffnen_umgebung):
    import base64
    bruecke, gestartet, _ = oeffnen_umgebung
    inhalt = base64.b64encode(b'%PDF').decode()
    for name in ('foto.JPG', 'scan.png', 'beleg.heic', 'r.pdf'):
        assert Path(bruecke.oeffnen(name, inhalt)).name == name
    mit = Path(bruecke.oeffnen('r.pdf', inhalt, 2))
    assert mit.suffix == '.html' and '#page=2' in mit.read_text(encoding='utf-8')
    assert [p.name for p in gestartet] == ['foto.JPG', 'scan.png', 'beleg.heic', 'r.pdf', 'r.html']
    assert bruecke._fenster.dialoge == []


# --- Servermodus (#45, Commit 3) ---------------------------------------------

@pytest.mark.parametrize('eingabe, erwartet', [
    ('nk.example', 'https://nk.example'),
    ('  https://NK.example/  ', 'https://nk.example'),
    ('http://192.168.1.5:8080', 'http://192.168.1.5:8080'),
    ('nk.example:6060', 'https://nk.example:6060'),
    ('http://[::1]:8080/', 'http://[::1]:8080'),
    ('https://nk.example/nk', None),
    ('https://nk.example/?x=1', None),
    ('https://nk.example/#a', None),
    ('https://benutzer:geheim@nk.example', None),
    ('https://benutzer@nk.example', None),
    ('ftp://nk.example', None),
    ('file:///C:/daten', None),
    ('javascript:alert(1)', None),
    ('https://', None),
    ('https://nk.example:99999', None),
    ('https://mein server', None),
    ('', None),
    (None, None),
])
def test_adresse_normieren(eingabe, erwartet):
    assert desktop.adresse_normieren(eingabe) == erwartet


@pytest.fixture
def testserver():
    """Ein echter HTTP-Server auf 127.0.0.1; ``antworten[pfad]`` = (Status, Köpfe, Inhalt)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    antworten = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, koepfe, inhalt = antworten.get(self.path, (404, {}, b'nicht da'))
            self.send_response(status)
            for name, wert in koepfe.items():
                self.send_header(name, wert)
            self.send_header('Content-Length', str(len(inhalt)))
            self.end_headers()
            self.wfile.write(inhalt)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}', antworten
    finally:
        server.shutdown()
        server.server_close()


GESUND = (200, {'Content-Type': 'application/json'},
          b'{"status": "ok", "message": "NebenkostenFix l\\u00e4uft."}')


def test_server_pruefen_ok(testserver):
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    assert desktop.server_pruefen(basis + '/') == (True, None, basis)


@pytest.mark.parametrize('antwort', [
    (404, {}, b'nicht da'),
    (500, {}, b'kaputt'),
    (200, {'Content-Type': 'text/html'}, b'<html>Router</html>'),
    (200, {}, b'{"status": "ok"}'),
    (200, {}, b'["ok"]'),
    (200, {}, b'\xff\xfe'),
])
def test_server_pruefen_kein_nebenkostenfix(testserver, antwort):
    basis, antworten = testserver
    antworten['/api/health'] = antwort
    assert desktop.server_pruefen(basis) == (False, desktop.KEIN_NK, None)


def test_server_pruefen_folgt_keiner_fremden_weiterleitung(testserver):
    basis, antworten = testserver
    antworten['/api/health'] = (302, {'Location': 'https://boese.example/api/health'}, b'')
    ok, meldung, ende = desktop.server_pruefen(basis)
    assert (ok, ende) == (False, None)
    assert meldung == desktop.WEITERLEITUNG.format(ziel='https://boese.example/api/health')


def test_server_pruefen_nicht_erreichbar():
    import socket
    with socket.socket() as frei:
        frei.bind(('127.0.0.1', 0))
        port = frei.getsockname()[1]
    assert desktop.server_pruefen(f'http://127.0.0.1:{port}', zeit=2) == \
        (False, desktop.NICHT_ERREICHBAR, None)


def test_server_pruefen_ohne_pfad():
    assert desktop.server_pruefen('https://nk.example/nk') == (False, desktop.OHNE_PFAD, None)


class _Oeffner:
    """Ersatz für build_opener: je Adresse eine Ausnahme oder eine Antwort."""

    def __init__(self, ergebnisse):
        self.ergebnisse = ergebnisse
        self.aufrufe = []

    def open(self, adresse, timeout=None):
        import io
        self.aufrufe.append(adresse)
        ergebnis = self.ergebnisse[adresse]
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return io.BytesIO(ergebnis)


def _oeffner(monkeypatch, ergebnisse):
    oeffner = _Oeffner(ergebnisse)
    monkeypatch.setattr(desktop.urllib.request, 'build_opener', lambda *_: oeffner)
    return oeffner


@pytest.mark.parametrize('fehler, meldung', [
    ('zertifikat', 'ZERTIFIKAT'),
    ('ssl', 'VERSCHLUESSELUNG'),
    ('roh_ssl', 'VERSCHLUESSELUNG'),
    ('zeit', 'NICHT_ERREICHBAR'),
    ('url', 'NICHT_ERREICHBAR'),
])
def test_server_pruefen_ssl_und_netzfehler(monkeypatch, fehler, meldung):
    import ssl
    import urllib.error
    ausnahme = {
        'zertifikat': urllib.error.URLError(ssl.SSLCertVerificationError('selbstsigniert')),
        'ssl': urllib.error.URLError(ssl.SSLError('wrong version number')),
        'roh_ssl': ssl.SSLError('wrong version number'),
        'zeit': TimeoutError(),
        'url': urllib.error.URLError(OSError('Name unbekannt')),
    }[fehler]
    _oeffner(monkeypatch, {'https://nk.example/api/health': ausnahme})
    assert desktop.server_pruefen('nk.example') == (False, getattr(desktop, meldung), None)


def test_server_pruefen_uebernimmt_nur_http_nach_https(monkeypatch):
    import urllib.error

    def weiter(von, nach):
        return urllib.error.HTTPError(von, 301, 'Moved', {'Location': nach}, None)

    oeffner = _oeffner(monkeypatch, {
        'http://nk.example/api/health': weiter('http://nk.example/api/health',
                                               'https://nk.example/api/health'),
        'https://nk.example/api/health': GESUND[2],
        'http://nk.example:8080/api/health': weiter('http://nk.example:8080/api/health',
                                                    'https://nk.example/api/health'),
        'http://andere.example/api/health': weiter('http://andere.example/api/health',
                                                   'https://nk.example/api/health'),
    })
    assert desktop.server_pruefen('http://nk.example') == (True, None, 'https://nk.example')
    assert oeffner.aufrufe == ['http://nk.example/api/health', 'https://nk.example/api/health']
    for anders in ('http://nk.example:8080', 'http://andere.example'):
        ok, meldung, _ = desktop.server_pruefen(anders)
        assert not ok and meldung.startswith('Der Server leitet'), anders


def test_server_bruecke_hat_genau_vier_methoden():
    """Die Server-Seite bekommt weder Ordnerwahl noch Umzug noch Umschalten."""
    import inspect
    bruecke = desktop.ServerBruecke('https://nk.example')
    oeffentlich = {name for name in dir(bruecke) if not name.startswith('_')}
    assert oeffentlich == {'speichern', 'oeffnen', 'extern_oeffnen', 'lokal_arbeiten'}
    assert all(inspect.ismethod(getattr(bruecke, name)) for name in oeffentlich)
    assert not isinstance(bruecke, desktop.Bruecke)


class _UrlFenster(_SpeicherFenster):
    def __init__(self, ziel, url):
        super().__init__(ziel)
        self.url = url

    def get_current_url(self):
        if isinstance(self.url, Exception):
            raise self.url
        return self.url


def test_server_bruecke_verweigert_fremden_ursprung(oeffnen_umgebung, monkeypatch):
    import base64
    import webbrowser
    from nebenkostenfix import marke
    _, gestartet, tmp_path = oeffnen_umgebung
    extern = []
    monkeypatch.setattr(webbrowser, 'open', lambda adresse: extern.append(adresse) or True)
    inhalt = base64.b64encode(b'%PDF').decode()
    bruecke = desktop.ServerBruecke('https://nk.example')
    for fremd in ('https://boese.example/', 'http://nk.example/', 'https://nk.example:444/',
                  'https://nk.example.boese.example/', None, RuntimeError('zu')):
        bruecke._fenster = _UrlFenster(tmp_path / 'gespeichert.bin', fremd)
        assert bruecke.speichern('a.pdf', inhalt) is None
        assert bruecke.oeffnen('a.pdf', inhalt) is None
        assert bruecke.extern_oeffnen(marke.REPO_URL) is False
        assert bruecke._fenster.dialoge == []
    assert gestartet == [] and extern == []
    assert not (tmp_path / 'gespeichert.bin').exists()
    assert not list((tmp_path / 'temp').rglob('*.pdf'))

    bruecke._fenster = _UrlFenster(tmp_path / 'gespeichert.bin', 'HTTPS://NK.example:443/#/x')
    assert bruecke.speichern('a.pdf', inhalt) == str(tmp_path / 'gespeichert.bin')
    assert Path(bruecke.oeffnen('a.pdf', inhalt)).name == 'a.pdf'
    assert bruecke.extern_oeffnen(marke.REPO_URL) is True
    assert len(gestartet) == 1 and extern == [marke.REPO_URL]


def test_lokale_bruecke_ohne_lokal_arbeiten():
    """Der Rückweg gibt es nur im Servermodus, das Umschalten nur lokal (#45)."""
    assert not hasattr(desktop.Bruecke(), 'lokal_arbeiten')
    assert not hasattr(desktop.ServerBruecke('https://nk.example'), 'server_verbinden')


def test_lokal_arbeiten_verweigert_fremden_ursprung(tmp_path):
    """Eine fremde Seite im Fenster öffnet nicht einmal die Rückfrage."""
    aufrufe = []
    bruecke = desktop.ServerBruecke('https://nk.example')
    bruecke._zurueck = lambda: aufrufe.append(True) or True
    for fremd in ('https://boese.example/', 'http://nk.example/', 'https://nk.example:444/',
                  'https://nk.example.boese.example/', None, RuntimeError('zu')):
        bruecke._fenster = _UrlFenster(tmp_path / 'x', fremd)
        assert bruecke.lokal_arbeiten() is False, fremd
    assert aufrufe == []
    bruecke._fenster = _UrlFenster(tmp_path / 'x', 'HTTPS://NK.example:443/#/x')
    assert bruecke.lokal_arbeiten() is True
    assert aufrufe == [True]


def test_lokal_arbeiten_nach_nein_erst_nach_der_abkuehlzeit(tmp_path, monkeypatch):
    """Eine Seite, die nach jedem „Nein“ sofort wieder ruft, sperrt das Menü nicht aus."""
    jetzt = [1000.0]
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: jetzt[0])
    antworten = [False, True]
    bruecke = desktop.ServerBruecke('https://nk.example')
    bruecke._zurueck = lambda: antworten.pop(0)
    bruecke._fenster = _UrlFenster(tmp_path / 'x', 'https://nk.example/')
    assert bruecke.lokal_arbeiten() is False
    jetzt[0] += desktop.ABKUEHLEN - 1
    assert bruecke.lokal_arbeiten() is False and antworten == [True]
    jetzt[0] += 1
    assert bruecke.lokal_arbeiten() is True and antworten == []


def test_lokal_arbeiten_vor_dem_verdrahten(tmp_path):
    bruecke = desktop.ServerBruecke('https://nk.example')
    bruecke._fenster = _UrlFenster(tmp_path / 'x', 'https://nk.example/')
    assert bruecke.lokal_arbeiten() is False


class _Ereignis:
    def __init__(self):
        self.handler = []

    def __iadd__(self, handler):
        self.handler.append(handler)
        return self


class _ServerFenster:
    """Ersatz für das Fenster im Servermodus: merkt sich, was es lädt."""

    def __init__(self, titel, **einstellungen):
        self.titel = titel
        self.einstellungen = einstellungen
        self.url = None
        self.geladen = []
        self.html = []
        self.events = types.SimpleNamespace(loaded=_Ereignis())

    def load_url(self, url):
        self.geladen.append(url)
        self.navigiert(url)

    def navigiert(self, url):
        self.url = url
        for handler in self.events.loaded.handler:
            handler(self)

    def load_html(self, text):
        self.html.append(text)

    def get_current_url(self):
        return self.url

    def set_title(self, titel):
        self.titel = titel

    def evaluate_js(self, _):
        pass

    def destroy(self):
        pass


@pytest.fixture
def servermodus(lokal, monkeypatch):
    """pywebview-Ersatz; jeder Weg zum lokalen Server oder Datenordner wirft."""
    fenster = []

    def create_window(titel, **einstellungen):
        fenster.append(_ServerFenster(titel, **einstellungen))
        return fenster[-1]

    gestartet = {}

    def start(funktion, **einstellungen):
        gestartet.update(einstellungen)
        funktion()

    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(
        create_window=create_window, start=start, SAVE_DIALOG=30))
    monkeypatch.setitem(sys.modules, 'webview.menu', types.SimpleNamespace(
        Menu=lambda *a: a, MenuAction=lambda *a: a, MenuSeparator=lambda: None))

    def verboten(*_, **__):
        raise AssertionError('lokaler Weg im Servermodus')

    for name in ('anwendung_laden', 'server_starten', 'datenordner_bestimmen',
                 'fenster_starten', 'anhalten', 'selbsttest'):
        monkeypatch.setattr(desktop, name, verboten)
    monkeypatch.setattr(windows_ordner, 'schreibprobe', verboten)
    monkeypatch.setattr(windows_ordner, 'dokumente_ordner', lambda: lokal / 'Dokumente')
    # Die Update-Suche läuft im eigenen Faden; hier nur gemerkt, nie im Netz.
    angeboten = threading.Event()
    gestartet['update_fuer'] = []

    def update_anbieten(f):
        gestartet['update_fuer'].append(f)
        angeboten.set()

    gestartet['update_angeboten'] = angeboten
    monkeypatch.setattr(desktop, 'update_anbieten', update_anbieten)
    return fenster, gestartet


def test_servermodus_startet_keinen_lokalen_server(servermodus, testserver):
    fenster, gestartet = servermodus
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    windows_ordner.einstellungen_schreiben(server=basis)
    assert desktop.main([]) == 0
    (offen,) = fenster
    assert offen.geladen == [basis + '/']
    host = basis.split('://')[1]
    assert offen.titel == f'NebenkostenFix – verbunden mit {host} (unverschlüsselt)'
    assert isinstance(offen.einstellungen['js_api'], desktop.ServerBruecke)
    assert 'html' in offen.einstellungen and 'url' not in offen.einstellungen
    assert gestartet['storage_path'].endswith('WebView2')

    # Navigationssperre: eine fremde Seite führt zurück zum Server.
    offen.navigiert('https://boese.example/falle')
    assert offen.geladen == [basis + '/', basis + '/']
    offen.navigiert(basis + '/#/abrechnung')
    assert offen.geladen == [basis + '/', basis + '/']


def test_navigationssperre_endet_bei_fremder_weiterleitung(servermodus, testserver, monkeypatch):
    """Leitet „/“ auf einen anderen Host (Anmelde-Proxy), lädt das Fenster
    nicht ewig neu: nach wenigen Rücksprüngen kommt die Offline-Seite."""
    fenster, _ = servermodus
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    windows_ordner.einstellungen_schreiben(server=basis)

    def load_url(self, url):
        self.geladen.append(url)
        self.navigiert('https://anmeldung.example/login')

    monkeypatch.setattr(_ServerFenster, 'load_url', load_url)
    assert desktop.main([]) == 0
    (offen,) = fenster
    assert offen.geladen == [basis + '/'] * (1 + desktop.RUECKSPRUENGE)
    (seite,) = offen.html
    assert 'Keine Verbindung zum Server' in seite and 'anmeldung.example' in seite


def test_fenstertitel_folgt_der_geprueften_adresse(servermodus, monkeypatch):
    fenster, _ = servermodus
    # Die Prüfung übernimmt http → https: der Titel sagt nicht mehr „unverschlüsselt“.
    monkeypatch.setattr(desktop, 'server_pruefen', lambda _: (True, None, 'https://nk.example'))
    windows_ordner.einstellungen_schreiben(server='http://nk.example')
    assert desktop.main([]) == 0
    assert fenster[-1].titel == 'NebenkostenFix – verbunden mit nk.example'
    # Von Hand ohne Schema eingetragen: der Host steht trotzdem im Titel.
    monkeypatch.setattr(desktop, 'server_pruefen', lambda _: (False, desktop.NICHT_ERREICHBAR, None))
    windows_ordner.einstellungen_schreiben(server='nk.example:8443')
    assert desktop.main([]) == 0
    assert fenster[-1].titel == 'NebenkostenFix – verbunden mit nk.example:8443'


def test_servermodus_ohne_server_zeigt_offline_seite(servermodus):
    import socket
    fenster, _ = servermodus
    with socket.socket() as frei:
        frei.bind(('127.0.0.1', 0))
        port = frei.getsockname()[1]
    windows_ordner.einstellungen_schreiben(server=f'http://127.0.0.1:{port}')
    assert desktop.main([]) == 0
    (offen,) = fenster
    assert offen.geladen == []
    (seite,) = offen.html
    assert 'Keine Verbindung zum Server' in seite and 'Datei → Neu laden' in seite
    assert 'erwartet der Server https' in seite  # http: Hinweis auf die Anmeldeschleife
    offen.navigiert('https://boese.example/')  # ohne Verbindung keine Sperre nötig
    assert offen.geladen == []


def test_offline_seite_maskiert():
    seite = desktop.offline_seite('<b>x</b>', 'https://nk.example/<script>')
    assert '<b>x</b>' not in seite and '<script>' not in seite
    assert 'erwartet der Server https' not in seite


def _schnappschuss(ordner: Path):
    return sorted((str(p.relative_to(ordner)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in [ordner, *ordner.rglob('*')])


def test_servermodus_beruehrt_datenordner_nicht(servermodus, testserver, lokal):
    """Weder geöffnet noch angelegt noch verändert (#45, Datenerhalt)."""
    import os as _os
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    daten = lokal / 'daten'
    (daten / 'belege').mkdir(parents=True)
    (daten / 'nebenkosten.db').write_bytes(b'SQLite format 3\x00' + b'\x00' * 100)
    (daten / 'belege' / 'r.pdf').write_bytes(b'%PDF')
    alt = 1_600_000_000_000_000_000
    for pfad in [daten, *daten.rglob('*')]:
        _os.utime(pfad, ns=(alt, alt))
    windows_ordner.einstellungen_schreiben(datenordner=daten, server=basis)
    vorher = _schnappschuss(daten)
    assert desktop.main([]) == 0
    assert _schnappschuss(daten) == vorher

    # Ohne eingetragenen Datenordner wird auch die Vorgabe nicht angelegt.
    windows_ordner.einstellungen_schreiben(datenordner='')
    assert desktop.main([]) == 0
    assert not (lokal / 'Dokumente').exists()


def test_datenordner_schalter_erzwingt_lokal(lokal, monkeypatch):
    windows_ordner.einstellungen_schreiben(server='https://nk.example')
    lokal_gestartet = []
    monkeypatch.setattr(desktop, 'server_fenster_starten',
                        lambda *_: pytest.fail('Servermodus trotz --datenordner'))
    monkeypatch.setattr(desktop, 'fenster_starten', lambda ordner: lokal_gestartet.append(ordner) or 0)
    assert desktop.main(['--datenordner', str(lokal / 'daten')]) == 0
    assert lokal_gestartet == [lokal / 'daten']



def test_webview2_spricht_deutsch(lokal, monkeypatch):
    """Formulare: Kalender, Datei-Knopf und Blasen folgen sonst der
    Windows-Anzeigesprache; ein eigener Wert des Nutzers bleibt stehen."""
    monkeypatch.setattr(desktop, 'fenster_starten', lambda ordner: 0)
    monkeypatch.delenv('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', raising=False)
    assert desktop.main(['--datenordner', str(lokal / 'daten')]) == 0
    assert os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] == '--lang=de-DE'
    monkeypatch.setenv('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '--lang=fr-FR')
    assert desktop.main(['--datenordner', str(lokal / 'daten')]) == 0
    assert os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] == '--lang=fr-FR'

def test_ohne_server_eintrag_bleibt_alles_lokal(lokal, monkeypatch):
    lokal_gestartet = []
    monkeypatch.setattr(desktop, 'server_fenster_starten',
                        lambda *_: pytest.fail('Servermodus ohne Eintrag'))
    monkeypatch.setattr(desktop, 'datenordner_bestimmen', lambda **_: lokal / 'daten')
    monkeypatch.setattr(desktop, 'fenster_starten', lambda ordner: lokal_gestartet.append(ordner) or 0)
    assert desktop.main([]) == 0
    assert lokal_gestartet == [lokal / 'daten']


# --- Umschalten zwischen lokal und Server (#45, Commit 4) ----------------------

@pytest.fixture
def zeitgeber(monkeypatch):
    """threading.Timer ohne Warten: merkt sich, was nach dem Verbinden käme."""
    geplant = []

    class Zeitgeber:
        def __init__(self, sekunden, funktion):
            self.sekunden, self.funktion, self.daemon = sekunden, funktion, False

        def start(self):
            geplant.append(self)

    monkeypatch.setattr(desktop.threading, 'Timer', Zeitgeber)
    return geplant


LOKAL_BASIS = 'http://127.0.0.1:50123'


def _lokale_bruecke(ordner, url=LOKAL_BASIS + '/#/einstellungen'):
    """Die Brücke der lokalen App, das Fenster zeigt die eigene Oberfläche."""
    bruecke = desktop.Bruecke()
    bruecke._fenster = _UrlFenster(ordner / 'unbenutzt.bin', url)
    bruecke._basis = LOKAL_BASIS
    return bruecke


def test_server_verbinden_schreibt_nur_server(lokal, testserver, zeitgeber):
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    windows_ordner.einstellungen_schreiben(datenordner=lokal / 'daten',
                                           sicherungsziele=[str(lokal / 'usb')])
    datei = windows_ordner.einstellungen_datei()
    vorher = _abschnitte(datei)
    neu_gestartet = []
    bruecke = _lokale_bruecke(lokal)
    bruecke._neustart = lambda: neu_gestartet.append(True)

    assert bruecke.server_verbinden(basis + '/') == {'ok': True, 'adresse': basis}
    nachher = _abschnitte(datei)
    assert nachher.pop('Server') == {'adresse': basis}
    assert nachher == vorher
    (geplant,) = zeitgeber
    assert geplant.daemon and geplant.sekunden > 0
    geplant.funktion()
    assert neu_gestartet == [True]


def test_server_verbinden_fehler_schreibt_nichts(lokal, testserver, zeitgeber):
    basis, antworten = testserver
    antworten['/api/health'] = (200, {}, b'<html>Router</html>')
    windows_ordner.einstellungen_schreiben(datenordner=lokal / 'daten')
    datei = windows_ordner.einstellungen_datei()
    vorher = datei.read_bytes()
    bruecke = _lokale_bruecke(lokal)
    bruecke._neustart = lambda: pytest.fail('Neustart trotz Fehler')
    for adresse, meldung in ((basis, desktop.KEIN_NK), ('https://nk.example/nk', desktop.OHNE_PFAD),
                             ('ftp://nk.example', desktop.OHNE_PFAD)):
        assert bruecke.server_verbinden(adresse) == {'ok': False, 'meldung': meldung}
    assert datei.read_bytes() == vorher
    assert zeitgeber == []


def test_server_verbinden_bietet_http_nur_ohne_schema_an(lokal, zeitgeber, monkeypatch):
    """#45: Ohne Schema galt https. Scheitert nur die Verschlüsselung, bietet die
    Oberfläche http:// an; wer https:// selbst eintrug, bekommt nur die Meldung."""
    windows_ordner.einstellungen_schreiben(datenordner=lokal / 'daten')
    datei = windows_ordner.einstellungen_datei()
    vorher = datei.read_bytes()
    monkeypatch.setattr(desktop, 'server_pruefen', lambda _: (False, desktop.VERSCHLUESSELUNG, None))
    bruecke = _lokale_bruecke(lokal)
    bruecke._neustart = lambda: pytest.fail('Neustart trotz Fehler')
    assert bruecke.server_verbinden('127.0.0.1:6062') == {
        'ok': False, 'meldung': desktop.VERSCHLUESSELUNG, 'http_anbieten': True}
    assert bruecke.server_verbinden('https://127.0.0.1:6062') == {
        'ok': False, 'meldung': desktop.VERSCHLUESSELUNG}
    monkeypatch.setattr(desktop, 'server_pruefen', lambda _: (False, desktop.NICHT_ERREICHBAR, None))
    assert 'http_anbieten' not in bruecke.server_verbinden('127.0.0.1:6062')
    assert datei.read_bytes() == vorher and zeitgeber == []


def test_lokales_menue_fuehrt_zum_server():
    """#45: Datei → Mit einem Server verbinden … öffnet dieselbe Karte, auch wenn
    die leere Übersicht mit ihrem Knopf schon weg ist."""
    quelle = inspect.getsource(desktop.fenster_starten)
    assert "MenuAction('Mit einem Server verbinden …'" in quelle
    assert "fenster.evaluate_js('zeigeServerKarte()')" in quelle


def test_server_verbinden_nur_aus_der_eigenen_oberflaeche(lokal, zeitgeber, monkeypatch):
    """Eine fremde Seite im lokalen Fenster stellt die App nicht still um."""
    windows_ordner.einstellungen_schreiben(datenordner=lokal / 'daten')
    datei = windows_ordner.einstellungen_datei()
    vorher = datei.read_bytes()
    monkeypatch.setattr(desktop, 'server_pruefen', lambda _: pytest.fail('geprüft trotz Fremder'))
    for fremd in ('https://angreifer.example/', 'http://127.0.0.1:50124/', None, RuntimeError('zu')):
        bruecke = _lokale_bruecke(lokal, fremd)
        bruecke._neustart = lambda: pytest.fail('Neustart trotz Fremder')
        assert bruecke.server_verbinden('https://angreifer.example') == {
            'ok': False, 'meldung': desktop.FREMDE_SEITE}
    # Vor dem Start des lokalen Servers kennt die Brücke keinen Ursprung.
    ohne = desktop.Bruecke()
    ohne._fenster = _UrlFenster(lokal / 'unbenutzt.bin', LOKAL_BASIS + '/')
    assert ohne.server_verbinden('https://nk.example')['ok'] is False
    assert datei.read_bytes() == vorher and zeitgeber == []


def test_neustart_umgebung_bereinigt(monkeypatch):
    assert desktop.neustart_umgebung({'NK_DESKTOP': '1', 'DATA_DIR': 'x', 'BACKUP_ZIELE': 'y',
                                      'PATH': 'p'}) == \
        {'PATH': 'p', 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
    import subprocess
    aufrufe = []
    monkeypatch.setattr(subprocess, 'Popen', lambda befehl, **k: aufrufe.append((befehl, k)))
    monkeypatch.setenv('NK_DESKTOP', '1')
    monkeypatch.setenv('DATA_DIR', '/daten')
    desktop.neu_starten()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    desktop.neu_starten()
    (quellen, k1), (paket, k2) = aufrufe
    assert quellen == [sys.executable, str(WURZEL / 'desktop.py')]
    assert paket == [sys.executable]
    for k in (k1, k2):
        assert 'NK_DESKTOP' not in k['env'] and 'DATA_DIR' not in k['env']
        assert k['env']['PYINSTALLER_RESET_ENVIRONMENT'] == '1' and k['close_fds']


def _menuepunkt(gestartet, name):
    for _, punkte in gestartet['menu']:
        for punkt in punkte:
            if punkt and punkt[0] == name:
                return punkt[1]
    raise KeyError(name)


@pytest.mark.parametrize('bestaetigt', [True, False])
def test_zurueck_entfernt_nur_adresse(servermodus, testserver, lokal, monkeypatch, bestaetigt):
    import subprocess
    fenster, gestartet = servermodus
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    windows_ordner.einstellungen_schreiben(datenordner=lokal / 'daten', server=basis)
    datei = windows_ordner.einstellungen_datei()
    vorher = _abschnitte(datei)
    neu = []
    monkeypatch.setattr(subprocess, 'Popen', lambda befehl, **k: neu.append(befehl))
    fragen = []
    geschlossen = []
    monkeypatch.setattr(_ServerFenster, 'create_confirmation_dialog',
                        lambda self, titel, text: fragen.append(text) or bestaetigt, raising=False)
    monkeypatch.setattr(_ServerFenster, 'destroy', lambda self: geschlossen.append(True))

    original_start = sys.modules['webview'].start

    def start(funktion, **einstellungen):
        original_start(funktion, **einstellungen)
        _menuepunkt(gestartet, 'Auf diesem Rechner arbeiten …')()

    monkeypatch.setattr(sys.modules['webview'], 'start', start)
    assert desktop.main([]) == 0
    assert fragen == [desktop.ZURUECK_FRAGE]
    nachher = _abschnitte(datei)
    if bestaetigt:
        assert nachher == {k: v for k, v in vorher.items() if k != 'Server'}
        assert windows_ordner.einstellungen_lesen()['server'] is None
        assert geschlossen == [True] and len(neu) == 1
    else:
        assert nachher == vorher and geschlossen == [] and neu == []


def _rueckweg_umgebung(servermodus, testserver, monkeypatch, antwort, nach_dem_start):
    """Servermodus mit Ersatz für Rückfrage, Schließen und Neustart; nach dem
    Laden ruft ``nach_dem_start(bruecke, gestartet)`` den Rückweg auf."""
    import subprocess
    fenster, gestartet = servermodus
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    protokoll = {'fragen': [], 'geschlossen': [], 'neu': []}
    monkeypatch.setattr(subprocess, 'Popen', lambda befehl, **k: protokoll['neu'].append(befehl))
    monkeypatch.setattr(_ServerFenster, 'create_confirmation_dialog',
                        lambda self, titel, text: protokoll['fragen'].append(text) or antwort(),
                        raising=False)
    monkeypatch.setattr(_ServerFenster, 'destroy',
                        lambda self: protokoll['geschlossen'].append(True))
    original_start = sys.modules['webview'].start

    def start(funktion, **einstellungen):
        original_start(funktion, **einstellungen)
        protokoll['ergebnis'] = nach_dem_start(fenster[-1].einstellungen['js_api'], gestartet)

    monkeypatch.setattr(sys.modules['webview'], 'start', start)
    return basis, protokoll


@pytest.mark.parametrize('bestaetigt', [True, False])
def test_lokal_arbeiten_entfernt_nur_adresse(servermodus, testserver, lokal, monkeypatch,
                                             bestaetigt):
    """Der Knopf in den Einstellungen geht denselben Weg wie das Menü (#45)."""
    import os as _os
    basis, protokoll = _rueckweg_umgebung(servermodus, testserver, monkeypatch,
                                          lambda: bestaetigt,
                                          lambda bruecke, _: bruecke.lokal_arbeiten())
    daten = lokal / 'daten'
    daten.mkdir()
    (daten / 'nebenkosten.db').write_bytes(b'SQLite format 3\x00' + b'\x00' * 100)
    alt = 1_600_000_000_000_000_000
    for pfad in [daten, *daten.rglob('*')]:
        _os.utime(pfad, ns=(alt, alt))
    windows_ordner.einstellungen_schreiben(datenordner=daten, onedrive_bestaetigt=True,
                                           server=basis)
    datei = windows_ordner.einstellungen_datei()
    vorher = _abschnitte(datei)
    daten_vorher = _schnappschuss(daten)
    assert desktop.main([]) == 0
    assert protokoll['ergebnis'] is bestaetigt
    assert protokoll['fragen'] == [desktop.ZURUECK_FRAGE]
    nachher = _abschnitte(datei)
    if bestaetigt:
        assert nachher == {k: v for k, v in vorher.items() if k != 'Server'}
        assert nachher['Daten']['onedrivebestaetigt'] == '1'
        assert protokoll['geschlossen'] == [True] and len(protokoll['neu']) == 1
    else:
        assert nachher == vorher
        assert protokoll['geschlossen'] == [] and protokoll['neu'] == []
    assert _schnappschuss(daten) == daten_vorher


def test_lokal_arbeiten_nur_eine_rueckfrage(servermodus, testserver, lokal, monkeypatch):
    """Solange die Rückfrage offen ist, öffnen weder Seite noch Menü eine zweite."""
    innen = {}

    def antwort():
        if 'bruecke' not in innen:
            innen['bruecke'] = innen['seite'].lokal_arbeiten()
            innen['menue'] = _menuepunkt(innen['gestartet'], 'Auf diesem Rechner arbeiten …')()
        return False

    def nach_dem_start(bruecke, gestartet):
        innen['seite'], innen['gestartet'] = bruecke, gestartet
        menue = _menuepunkt(gestartet, 'Auf diesem Rechner arbeiten …')
        return [bruecke.lokal_arbeiten(), bruecke.lokal_arbeiten(), menue()]

    basis, protokoll = _rueckweg_umgebung(servermodus, testserver, monkeypatch, antwort,
                                          nach_dem_start)
    windows_ordner.einstellungen_schreiben(server=basis)
    assert desktop.main([]) == 0
    assert innen['bruecke'] is False and innen['menue'] is False
    # Nach dem „Nein“ fragt die Seite eine Weile nicht wieder, das Menü schon.
    assert protokoll['ergebnis'] == [False, False, False]
    assert protokoll['fragen'] == [desktop.ZURUECK_FRAGE] * 2
    assert windows_ordner.einstellungen_lesen()['server'] == basis


def test_menue_und_bruecke_teilen_den_rueckweg(servermodus, testserver, monkeypatch):
    basis, protokoll = _rueckweg_umgebung(
        servermodus, testserver, monkeypatch, lambda: False,
        lambda bruecke, gestartet: _menuepunkt(gestartet, 'Auf diesem Rechner arbeiten …')
        is bruecke._zurueck)
    windows_ordner.einstellungen_schreiben(server=basis)
    assert desktop.main([]) == 0
    assert protokoll['ergebnis'] is True


# --- #45: App-Update im Servermodus ---------------------------------------

class _FrageFenster:
    def __init__(self, antwort):
        self.antwort = antwort
        self.fragen = []

    def create_confirmation_dialog(self, titel, text):
        self.fragen.append((titel, text))
        return self.antwort


@pytest.fixture
def update_ersatz(lokal, monkeypatch):
    from nebenkostenfix import aktualisierung
    aufrufe = {'automatisch': [], 'laden': [], 'starten': []}
    gefunden = {'version': '9.9.9', 'neu': True, 'installierbar': True}

    def automatisch(*args, **kwargs):
        aufrufe['automatisch'].append((args, kwargs))
        return gefunden

    def installer_laden(version):
        aufrufe['laden'].append(version)
        return lokal / 'setup.exe'

    monkeypatch.setattr(aktualisierung, 'automatisch', automatisch)
    monkeypatch.setattr(aktualisierung, 'installer_laden', installer_laden)
    monkeypatch.setattr(aktualisierung, 'installer_starten', aufrufe['starten'].append)
    monkeypatch.setattr(desktop, '_meldung', lambda *a, **k: aufrufe.setdefault('meldung', []).append(a))
    return aufrufe, gefunden


def test_servermodus_update_im_lokalen_ordner(update_ersatz, lokal):
    """Gesucht und gemerkt wird im lokalen App-Ordner, nicht im Datenordner."""
    aufrufe, gefunden = update_ersatz
    gefunden['installierbar'] = False
    desktop.update_anbieten(_FrageFenster(True))
    ((args, kwargs),) = aufrufe['automatisch']
    assert args == (desktop.SOFTWARE_VERSION, True)
    assert kwargs == {'ordner': windows_ordner.lokaler_ordner()}
    assert windows_ordner.lokaler_ordner().is_relative_to(lokal / 'lokal')
    assert aufrufe['laden'] == []


def test_servermodus_bietet_update_beim_start_an(servermodus, testserver):
    fenster, gestartet = servermodus
    basis, antworten = testserver
    antworten['/api/health'] = GESUND
    windows_ordner.einstellungen_schreiben(server=basis)
    assert desktop.main([]) == 0
    assert gestartet['update_angeboten'].wait(5)
    assert gestartet['update_fuer'] == fenster


def test_update_erst_nach_bestaetigung(update_ersatz, lokal):
    aufrufe, _ = update_ersatz
    nein = _FrageFenster(False)
    desktop.update_anbieten(nein)
    ((titel, text),) = nein.fragen
    assert titel == desktop.TITEL and '(9.9.9)' in text and 'startet danach neu' in text
    assert aufrufe['laden'] == [] and aufrufe['starten'] == []

    desktop.update_anbieten(_FrageFenster(True))
    assert aufrufe['laden'] == [desktop.SOFTWARE_VERSION]
    assert aufrufe['starten'] == [lokal / 'setup.exe']


def test_update_ohne_treffer_oder_mit_fehler_fragt_nicht(update_ersatz, monkeypatch):
    from nebenkostenfix import aktualisierung
    aufrufe, _ = update_ersatz
    fenster = _FrageFenster(True)
    monkeypatch.setattr(aktualisierung, 'automatisch', lambda *a, **k: None)
    desktop.update_anbieten(fenster)

    def kaputt(*_, **__):
        raise RuntimeError('kaputt')

    monkeypatch.setattr(aktualisierung, 'automatisch', kaputt)
    desktop.update_anbieten(fenster)
    assert fenster.fragen == [] and aufrufe['laden'] == []

    # Scheitert das Laden, meldet die App das und startet nichts.
    monkeypatch.setattr(aktualisierung, 'automatisch',
                        lambda *a, **k: {'version': '9.9.9', 'installierbar': True})

    def laden_scheitert(_):
        raise aktualisierung.AktualisierungsFehler('Prüfsumme falsch')

    monkeypatch.setattr(aktualisierung, 'installer_laden', laden_scheitert)
    desktop.update_anbieten(fenster)
    assert aufrufe['starten'] == []
    assert 'Prüfsumme falsch' in aufrufe['meldung'][0][0]
