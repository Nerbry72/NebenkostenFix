"""Lizenz für Updates, nie für die Daten (NK-080, NK-081, E-9 → D-93)."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import aktualisierung
import lizenz
from aktualisierung import AktualisierungsFehler
from lizenz import LizenzFehler

DATEN = {'produkt': 'nebenkostenabrechnung', 'kennung': '0f5c-4711',
         'lizenznehmer': 'Anna Vermieterin', 'ausgestellt': '2026-10-01',
         'updates_bis': '2027-10-01'}


@pytest.fixture
def schluessel(monkeypatch):
    privat = Ed25519PrivateKey.generate()
    oeffentlich = base64.b64encode(privat.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode('ascii')
    monkeypatch.setattr(lizenz, 'HERAUSGEBER_SCHLUESSEL', oeffentlich)
    return privat


def _datei(privat, **aenderung) -> str:
    return json.dumps(lizenz.signieren({**DATEN, **aenderung}, privat), indent=2)


# --- Lizenzdatei ------------------------------------------------------------

def test_gueltige_lizenz(schluessel, tmp_path):
    stand = lizenz.hinterlegen(tmp_path, _datei(schluessel))
    assert stand['status'] == 'gueltig'
    assert 'Anna Vermieterin' in stand['text'] and '01.10.2027' in stand['text']
    assert (tmp_path / lizenz.DATEINAME).is_file()


def test_einrueckung_aendert_die_signatur_nicht(schluessel):
    umschlag = json.loads(_datei(schluessel))
    kompakt = json.dumps(umschlag, separators=(',', ':'))
    assert lizenz.pruefen(kompakt)['lizenznehmer'] == 'Anna Vermieterin'


def test_veraenderte_lizenz_faellt_auf(schluessel):
    umschlag = json.loads(_datei(schluessel))
    umschlag['daten']['updates_bis'] = '2099-12-31'
    with pytest.raises(LizenzFehler, match='Signatur passt nicht'):
        lizenz.pruefen(json.dumps(umschlag))


def test_fremder_schluessel_faellt_auf(schluessel):
    fremd = Ed25519PrivateKey.generate()
    with pytest.raises(LizenzFehler, match='Signatur passt nicht'):
        lizenz.pruefen(_datei(fremd))


@pytest.mark.parametrize('inhalt', [b'', b'\xff\xfe', b'{}', b'[1]', b'x' * 20000,
                                    b'{"format":"nk-lizenz-1","daten":{},"signatur":"!!"}'])
def test_unsinn_ist_keine_lizenz(schluessel, inhalt):
    with pytest.raises(LizenzFehler):
        lizenz.pruefen(inhalt)


def test_falsches_produkt_und_fehlende_felder(schluessel):
    with pytest.raises(LizenzFehler, match='anderes Produkt'):
        lizenz.pruefen(_datei(schluessel, produkt='etwas-anderes'))
    with pytest.raises(LizenzFehler, match='fehlt'):
        lizenz.pruefen(_datei(schluessel, lizenznehmer=''))
    with pytest.raises(LizenzFehler, match='kein Datum'):
        lizenz.pruefen(_datei(schluessel, updates_bis='morgen'))


def test_ohne_datei_und_ohne_schluessel_sperrt_nichts(tmp_path, monkeypatch):
    assert lizenz.status(tmp_path)['status'] == 'keine'
    monkeypatch.setattr(lizenz, 'HERAUSGEBER_SCHLUESSEL', '')
    (tmp_path / lizenz.DATEINAME).write_text('{}')
    stand = lizenz.status(tmp_path)
    assert stand['status'] == 'ungueltig'
    assert 'uneingeschränkt' in stand['text']


def test_abgelaufen_heisst_nur_keine_neuen_updates(schluessel, tmp_path):
    lizenz.hinterlegen(tmp_path, _datei(schluessel))
    stand = lizenz.status(tmp_path, heute=date(2028, 1, 1))
    assert stand['status'] == 'abgelaufen'
    assert 'unbegrenzt weiter' in stand['text']
    # Ein Update aus der Laufzeit bleibt erlaubt, eines danach nicht.
    assert lizenz.update_erlaubt(stand, date(2027, 9, 30)) is True
    assert lizenz.update_erlaubt(stand, date(2027, 10, 1)) is True
    assert lizenz.update_erlaubt(stand, date(2027, 10, 2)) is False
    assert lizenz.update_erlaubt({'status': 'keine'}, date(2020, 1, 1)) is False


def test_eine_kaputte_datei_ersetzt_die_gute_nicht(schluessel, tmp_path):
    lizenz.hinterlegen(tmp_path, _datei(schluessel))
    with pytest.raises(LizenzFehler):
        lizenz.hinterlegen(tmp_path, '{"kaputt": true}')
    assert lizenz.status(tmp_path)['status'] == 'gueltig'


def test_keine_funktion_der_anwendung_fragt_die_lizenz():
    """E-9: nur die Update-Suche liest die Lizenz. Wer sie anderswo
    importiert, baut eine Sperre -- dieser Test hält das auf."""
    from pathlib import Path
    wurzel = Path(__file__).resolve().parents[1]
    nutzer = sorted(p.name for p in wurzel.glob('*.py')
                    if p.name not in ('lizenz.py', 'aktualisierung.py', 'app.py')
                    and ('import lizenz' in p.read_text(encoding='utf-8')
                         or 'from lizenz' in p.read_text(encoding='utf-8')))
    assert nutzer == []
    app_text = (wurzel / 'app.py').read_text(encoding='utf-8')
    assert app_text.count('lizenz.status(') <= 2


# --- Update-Suche -------------------------------------------------------------

def _manifest(privat, **daten):
    werte = {'version': '0.9.1', 'veroeffentlicht': '2027-03-01',
             'hinweise': 'Kleinigkeiten.',
             'docker': 'ghcr.io/nerbry72/nebenkostenfix:0.9.1',
             'windows': {'url': 'https://beispiel.invalid/setup.exe',
                         'sha256': hashlib.sha256(b'SETUP').hexdigest()}}
    werte.update(daten)
    return json.dumps(lizenz.signieren(werte, privat, aktualisierung.FORMAT)).encode()


def _lader(antworten):
    def laden(adresse, grenze, zeit=20):
        aktualisierung._https(adresse)
        return antworten[adresse]
    return laden


@pytest.fixture
def quelle(monkeypatch):
    monkeypatch.setenv('NK_UPDATE_QUELLE', 'https://beispiel.invalid/manifest.json')
    return 'https://beispiel.invalid/manifest.json'


def _gueltig():
    return {'status': 'gueltig', 'updates_bis': '2027-10-01'}


def test_versionen_vergleichen():
    assert aktualisierung.version_als_tupel('0.10.0') > aktualisierung.version_als_tupel('0.9.9')
    assert aktualisierung.version_als_tupel('1.0.0-rc1') == (1, 0, 0)
    with pytest.raises(AktualisierungsFehler):
        aktualisierung.version_als_tupel('neu')


def test_ohne_quelle_keine_suche(monkeypatch):
    monkeypatch.delenv('NK_UPDATE_QUELLE', raising=False)
    with pytest.raises(AktualisierungsFehler, match='keine Update-Quelle'):
        aktualisierung.suchen('0.9.0', _gueltig(), desktop=True)


def test_nur_https(monkeypatch):
    monkeypatch.setenv('NK_UPDATE_QUELLE', 'http://beispiel.invalid/m.json')
    with pytest.raises(AktualisierungsFehler, match='https'):
        aktualisierung.suchen('0.9.0', _gueltig(), desktop=True)


def test_neue_version_mit_lizenz(schluessel, quelle):
    laden = _lader({quelle: _manifest(schluessel)})
    ergebnis = aktualisierung.suchen('0.9.0', _gueltig(), desktop=True, laden=laden)
    assert ergebnis['neu'] and ergebnis['lizenz_erlaubt'] and ergebnis['installierbar']
    docker = aktualisierung.suchen('0.9.0', _gueltig(), desktop=False, laden=laden)
    assert not docker['installierbar'] and 'docker compose pull' in docker['text']


def test_neueste_version_schon_da(schluessel, quelle):
    laden = _lader({quelle: _manifest(schluessel, version='0.9.0')})
    ergebnis = aktualisierung.suchen('0.9.0', _gueltig(), desktop=True, laden=laden)
    assert not ergebnis['neu'] and not ergebnis['installierbar']
    assert 'neueste Version' in ergebnis['text']


def test_update_nach_der_laufzeit(schluessel, quelle):
    laden = _lader({quelle: _manifest(schluessel, veroeffentlicht='2028-01-01')})
    ergebnis = aktualisierung.suchen('0.9.0', _gueltig(), desktop=True, laden=laden)
    assert ergebnis['neu'] and not ergebnis['lizenz_erlaubt'] and not ergebnis['installierbar']
    assert 'läuft unverändert weiter' in ergebnis['text']


def test_gefaelschtes_manifest(schluessel, quelle):
    fremd = Ed25519PrivateKey.generate()
    laden = _lader({quelle: _manifest(fremd)})
    with pytest.raises(AktualisierungsFehler, match='nicht vertrauenswürdig'):
        aktualisierung.suchen('0.9.0', _gueltig(), desktop=True, laden=laden)


def test_installer_mit_pruefsumme(schluessel, quelle, tmp_path):
    antworten = {quelle: _manifest(schluessel),
                 'https://beispiel.invalid/setup.exe': b'SETUP'}
    datei = aktualisierung.installer_laden('0.9.0', _gueltig(), laden=_lader(antworten),
                                           ziel=tmp_path)
    assert datei.read_bytes() == b'SETUP'
    assert datei.name == 'NebenkostenFix-0.9.1-Setup.exe'
    antworten['https://beispiel.invalid/setup.exe'] = b'BOESE'
    with pytest.raises(AktualisierungsFehler, match='Prüfsumme'):
        aktualisierung.installer_laden('0.9.0', _gueltig(), laden=_lader(antworten),
                                       ziel=tmp_path)
    with pytest.raises(AktualisierungsFehler, match='Lizenz'):
        aktualisierung.installer_laden('0.9.0', {'status': 'keine'},
                                       laden=_lader(antworten), ziel=tmp_path)


# --- Oberflaeche und API --------------------------------------------------------

def test_api_zeigt_und_nimmt_die_lizenz(schluessel, auth_client, monkeypatch, tmp_path):
    import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    assert auth_client.get('/api/lizenz').get_json()['status'] == 'keine'
    kaputt = auth_client.post('/api/lizenz', json={'inhalt': '{"x": 1}'})
    assert kaputt.status_code == 400 and 'Format' in kaputt.get_json()['error']
    assert auth_client.post('/api/lizenz', json={}).status_code == 400
    gut = auth_client.post('/api/lizenz', json={'inhalt': _datei(schluessel)})
    assert gut.status_code == 200 and gut.get_json()['status'] == 'gueltig'
    assert auth_client.get('/api/lizenz').get_json()['lizenznehmer'] == 'Anna Vermieterin'


def test_lizenzkarte_in_den_einstellungen():
    from pathlib import Path
    wurzel = Path(__file__).resolve().parents[1]
    seite = (wurzel / 'static' / 'index.html').read_text(encoding='utf-8')
    skript = (wurzel / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'id="lizenz-stand"' in seite and 'lizenzEinspielen(this)' in seite
    assert "fetch('/api/lizenz'" in skript


# --- Werkzeug des Herausgebers --------------------------------------------------

def test_werkzeug_rundlauf(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    try:
        import lizenz_werkzeug as werkzeug
    finally:
        sys.path.pop(0)
    datei = tmp_path / 'herausgeber.pem'
    oeffentlich = werkzeug.schluessel_erzeugen(datei)
    assert oct(datei.stat().st_mode & 0o777) == '0o600' or sys.platform == 'win32'
    with pytest.raises(SystemExit):
        werkzeug.schluessel_erzeugen(datei)   # nie ueberschreiben
    monkeypatch.setattr(lizenz, 'HERAUSGEBER_SCHLUESSEL', oeffentlich)

    assert werkzeug.main(['ausstellen', str(datei), '--name', 'Anna Vermieterin',
                          '--bis', '2027-10-01', '--ausgabe', str(tmp_path / 'a.nklizenz')]) == 0
    assert lizenz.hinterlegen(tmp_path / 'daten', (tmp_path / 'a.nklizenz').read_text(
        encoding='utf-8'))['status'] in ('gueltig', 'abgelaufen')

    setup = tmp_path / 'setup.exe'
    setup.write_bytes(b'SETUP')
    assert werkzeug.main(['manifest', str(datei), '--version', '0.9.1', '--installer', str(setup),
                          '--url', 'https://beispiel.invalid/setup.exe',
                          '--ausgabe', str(tmp_path / 'manifest.json')]) == 0
    daten = aktualisierung.manifest_pruefen((tmp_path / 'manifest.json').read_bytes())
    assert daten['windows']['sha256'] == hashlib.sha256(b'SETUP').hexdigest()


def test_api_update_suche(schluessel, auth_client, monkeypatch, tmp_path):
    import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    monkeypatch.delenv('NK_UPDATE_QUELLE', raising=False)
    ohne = auth_client.get('/api/aktualisierung')
    assert ohne.status_code == 400 and 'keine Update-Quelle' in ohne.get_json()['error']

    monkeypatch.setenv('NK_UPDATE_QUELLE', 'https://beispiel.invalid/manifest.json')
    monkeypatch.setattr(aktualisierung, '_laden', _lader(
        {'https://beispiel.invalid/manifest.json': _manifest(schluessel, version='99.0.0')}))
    ergebnis = auth_client.get('/api/aktualisierung').get_json()
    assert ergebnis['neu'] is True and ergebnis['lizenz_erlaubt'] is False
    assert ergebnis['installierbar'] is False

    def kein_netz(adresse, grenze, zeit=20):
        raise OSError('kein Netz')
    monkeypatch.setattr(aktualisierung, '_laden', kein_netz)
    assert auth_client.get('/api/aktualisierung').status_code == 502
    # Installieren gibt es nur in der Windows-App.
    assert auth_client.post('/api/aktualisierung/installieren').status_code == 400
