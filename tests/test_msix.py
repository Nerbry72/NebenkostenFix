"""MSIX-Paket für den Microsoft Store (NK-173, Spike F-102).

Das Packen mit MakeAppx und die Probe mit Testsignatur laufen nur auf
windows-latest (``windows.yml``). Hier: Manifest, Version, Logos, die
Auswertung der Probe und der Ausweichordner im Paketmodus (F-111).
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import desktop
from nebenkostenfix import aktualisierung, windows_ordner

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / 'packaging' / 'windows'))
try:
    import msix
    import paketprobe
finally:
    sys.path.pop(0)

NS = {
    'm': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
    'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
    'uap3': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/3',
    'desktop': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10',
    'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities',
}


# --- Manifest -----------------------------------------------------------------

@pytest.mark.parametrize('version, erwartet', [
    ('0.10.4', '0.10.4.0'), ('1.0.0', '1.0.0.0'), ('65535.0.12', '65535.0.12.0')])
def test_paketversion(version, erwartet):
    assert msix.paketversion(version) == erwartet


@pytest.mark.parametrize('version', ['0.10', '0.10.4.1', '0.10.4-beta', 'v1.0.0', '65536.0.0', ''])
def test_paketversion_lehnt_ab(version):
    with pytest.raises(ValueError):
        msix.paketversion(version)


def test_manifest_traegt_die_identitaet_aus_dem_partner_center():
    wurzel = ET.fromstring(msix.manifest('0.10.5'))
    identitaet = wurzel.find('m:Identity', NS)
    assert identitaet.get('Name') == 'NerbrY72.NebenkostenFix'
    assert identitaet.get('Publisher') == 'CN=5A9DC20D-397B-41AF-807A-57E2A97CF70C'
    assert identitaet.get('Version') == '0.10.5.0'
    assert identitaet.get('ProcessorArchitecture') == 'x64'
    assert wurzel.findtext('m:Properties/m:PublisherDisplayName', namespaces=NS) == 'NerbrY72'
    assert wurzel.findtext('m:Properties/m:DisplayName', namespaces=NS) == 'NebenkostenFix'
    geraet = wurzel.find('m:Dependencies/m:TargetDeviceFamily', NS)
    assert geraet.get('Name') == 'Windows.Desktop'
    assert geraet.get('MinVersion') == '10.0.17763.0'  # 1809, wie der Installer
    assert '$VERSION$' not in msix.manifest('0.10.5')


def test_manifest_startet_die_exe_mit_voller_vertrauensstufe():
    wurzel = ET.fromstring(msix.manifest('0.10.5'))
    app = wurzel.find('m:Applications/m:Application', NS)
    assert app.get('Executable') == 'NebenkostenFix.exe'
    assert app.get('EntryPoint') == 'Windows.FullTrustApplication'
    faehigkeiten = [f.get('Name') for f in wurzel.find('m:Capabilities', NS)]
    assert faehigkeiten == ['runFullTrust']
    alias = app.find('.//uap3:AppExecutionAlias/desktop:ExecutionAlias', NS)
    assert alias.get('Alias') == 'NebenkostenFix.exe'


def test_manifest_verweist_nur_auf_logos_die_gezeichnet_werden():
    verweise = set(re.findall(r'Assets\\[A-Za-z0-9]+\.png', msix.manifest('0.10.5')))
    assert verweise == {f'Assets\\{name}' for name in msix.LOGOS}


# --- Paketinhalt ---------------------------------------------------------------

def test_vorbereiten_legt_manifest_und_logos_neben_die_exe(tmp_path):
    pytest.importorskip('PIL')
    from PIL import Image

    quelle = tmp_path / 'pyinstaller'
    (quelle / '_internal').mkdir(parents=True)
    (quelle / 'NebenkostenFix.exe').write_bytes(b'MZ')
    (quelle / '_internal' / 'THIRD_PARTY_LICENSES.txt').write_text('x', encoding='utf-8')
    ziel = tmp_path / 'inhalt'
    (ziel / 'alt').mkdir(parents=True)  # Rest eines früheren Laufs

    assert msix.vorbereiten(quelle, ziel, '0.10.5') == ziel
    assert (ziel / 'NebenkostenFix.exe').read_bytes() == b'MZ'
    assert (ziel / '_internal' / 'THIRD_PARTY_LICENSES.txt').is_file()
    assert not (ziel / 'alt').exists()
    assert 'Version="0.10.5.0"' in (ziel / 'AppxManifest.xml').read_text(encoding='utf-8')
    for name, kante in msix.LOGOS.items():
        with Image.open(ziel / 'Assets' / name) as bild:
            assert bild.format == 'PNG'
            assert bild.size == (kante, kante)
            assert bild.mode == 'RGBA'


def test_vorbereiten_ohne_pyinstaller_bricht_ab(tmp_path):
    with pytest.raises(FileNotFoundError, match='NebenkostenFix.exe'):
        msix.vorbereiten(tmp_path, tmp_path / 'inhalt', '0.10.5')


def test_aufruf(tmp_path, capsys):
    assert msix.main([]) == 2
    pytest.importorskip('PIL')
    (tmp_path / 'q').mkdir()
    (tmp_path / 'q' / 'NebenkostenFix.exe').write_bytes(b'MZ')
    assert msix.main(['vorbereiten', str(tmp_path / 'q'), str(tmp_path / 'z'), '0.10.5']) == 0
    assert 'Manifest 0.10.5.0, 3 Logos' in capsys.readouterr().out


# --- F-111: Ausweichordner im Store-Paket --------------------------------------

@pytest.fixture
def lokal(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    return tmp_path / 'lokal'


def test_ausweich_ausserhalb_des_paketordners(lokal, monkeypatch):
    # Unter MSIX leitet Windows neue Dateien in %LOCALAPPDATA% in den
    # Paketordner um und löscht sie beim Deinstallieren samt Mieterdaten.
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: True)
    ausweich = windows_ordner.lokaler_ausweich()
    assert ausweich == Path.home() / 'NebenkostenFix'
    assert lokal not in ausweich.parents


def test_ausweich_ohne_paket_bleibt_lokal(lokal, monkeypatch):
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: False)
    assert windows_ordner.lokaler_ausweich() == lokal / 'NebenkostenFix' / 'Daten'


def test_datenordner_zeigen_meldet_paketmodus_und_ausweich(lokal, monkeypatch, tmp_path):
    monkeypatch.setattr(windows_ordner, 'dokumente_ordner', lambda: tmp_path / 'Dokumente')
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: True)
    bericht = tmp_path / 'ordner.json'
    assert desktop.main(['--datenordner-zeigen', '--bericht', str(bericht)]) == 0
    inhalt = json.loads(bericht.read_text(encoding='utf-8'))
    assert inhalt['paketmodus'] is True
    assert inhalt['ausweich'] == str(Path.home() / 'NebenkostenFix')
    assert inhalt['einstellungen'] == str(lokal / 'NebenkostenFix' / 'einstellungen.ini')


# --- Probe in der CI -------------------------------------------------------------

def _berichte(ausweich):
    return ({'ergebnis': 'bestanden', 'paketmodus': True},
            {'datenordner': 'C:/Daten', 'paketmodus': True, 'ausweich': str(ausweich)})


def test_msix_probe_besteht(tmp_path):
    lokal = tmp_path / 'lokal'
    selbst, ordner = _berichte(tmp_path / 'home' / 'NebenkostenFix')
    ok, zeilen = paketprobe.msix_auswerten(selbst, ordner, paketprobe.PAKETFAMILIE, lokal)
    assert ok is True
    assert not any('FEHLGESCHLAGEN' in z for z in zeilen)
    assert zeilen[-1].endswith('NICHT umgeleitet')


def test_msix_probe_meldet_die_umleitung(tmp_path):
    lokal = tmp_path / 'lokal'
    (lokal / 'Packages' / paketprobe.PAKETFAMILIE / 'LocalCache' / 'Local' / 'NebenkostenFix').mkdir(parents=True)
    selbst, ordner = _berichte(tmp_path / 'home' / 'NebenkostenFix')
    ok, zeilen = paketprobe.msix_auswerten(selbst, ordner, paketprobe.PAKETFAMILIE, lokal)
    assert ok is True
    assert 'umgeleitet nach' in zeilen[-1]


@pytest.mark.parametrize('kaputt', ['selbsttest', 'paketmodus', 'familie', 'ausweich', 'leer'])
def test_msix_probe_schlaegt_fehl(tmp_path, kaputt):
    lokal = tmp_path / 'lokal'
    selbst, ordner = _berichte(tmp_path / 'home' / 'NebenkostenFix')
    familie = paketprobe.PAKETFAMILIE
    if kaputt == 'selbsttest':
        selbst['ergebnis'] = 'fehlgeschlagen'
    elif kaputt == 'paketmodus':  # ohne Paketidentität gestartet
        ordner['paketmodus'] = False
    elif kaputt == 'familie':  # anderer Publisher im Testzertifikat
        familie = 'NerbrY72.NebenkostenFix_andererhash0'
    elif kaputt == 'ausweich':
        ordner['ausweich'] = str(lokal / 'NebenkostenFix' / 'Daten')
    else:
        selbst, ordner = {}, {}
    ok, zeilen = paketprobe.msix_auswerten(selbst, ordner, familie, lokal)
    assert ok is False
    assert any('FEHLGESCHLAGEN' in z for z in zeilen)


def test_msix_entfernt(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    daten = tmp_path / 'daten'
    daten.mkdir()
    assert paketprobe.probe_msix_entfernt(paketprobe.PAKETFAMILIE, daten) is False
    (daten / 'nebenkosten.db').write_bytes(b'bestand')
    assert paketprobe.probe_msix_entfernt(paketprobe.PAKETFAMILIE, daten) is True


def test_msix_entfernt_scheitert_wenn_der_paketordner_bleibt(tmp_path, monkeypatch):
    """Copilot zu #23: Schlug Remove-AppxPackage fehl, blieb die Probe grün,
    solange die Daten da waren."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    daten = tmp_path / 'daten'
    daten.mkdir()
    (daten / 'nebenkosten.db').write_bytes(b'bestand')
    (tmp_path / 'lokal' / 'Packages' / paketprobe.PAKETFAMILIE).mkdir(parents=True)
    assert paketprobe.probe_msix_entfernt(paketprobe.PAKETFAMILIE, daten) is False


def test_windows_lauf_packt_und_probt_das_msix():
    windows = (WURZEL / '.github/workflows/windows.yml').read_text(encoding='utf-8')
    assert 'python packaging/windows/msix.py vorbereiten dist\\NebenkostenFix' in windows
    assert 'makeappx.exe' in windows
    # Testzertifikat mit dem echten Publisher, sonst andere Paketfamilie
    assert '-Subject "CN=5A9DC20D-397B-41AF-807A-57E2A97CF70C"' in windows
    assert windows.index('Add-AppxPackage') < windows.index('paketprobe.py msix ') \
        < windows.index('Remove-AppxPackage') < windows.index('paketprobe.py msix-entfernt')
    assert 'name: nebenkostenfix-msix' in windows
    # Hochgeladen wird das unsignierte Paket, signiert wird nur die Kopie.
    assert 'Copy-Item "${{ steps.msix.outputs.datei }}" $test' in windows
    assert 'path: dist/NebenkostenFix-*.msix' in windows
