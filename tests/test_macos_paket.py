"""Das Paket für macOS, ohne Mac geprüft (#44, Schritt 2).

Bau und Proben laufen in ``.github/workflows/macos.yml`` auf einem
macOS-Runner. Hier steht, was sich vorher statisch sagen lässt: Spec und
Info.plist, gleiche Positivliste wie unter Windows, Icon, Marker der
Abhängigkeiten und dass das Release (Schritt 3) den Workflow noch nicht
kennt.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement

WURZEL = Path(__file__).resolve().parents[1]
SPEC_MAC = WURZEL / 'packaging' / 'macos' / 'nebenkosten.spec'
SPEC_WIN = WURZEL / 'packaging' / 'windows' / 'nebenkosten.spec'
WORKFLOW = WURZEL / '.github' / 'workflows' / 'macos.yml'
PROBE = WURZEL / 'packaging' / 'macos' / 'fensterprobe.py'


def _text(pfad: Path) -> str:
    return pfad.read_text(encoding='utf-8')


def _bundle() -> dict:
    """Die Schlüsselwörter des Aufrufs ``BUNDLE(...)`` in der Spec."""
    for knoten in ast.walk(ast.parse(_text(SPEC_MAC))):
        if isinstance(knoten, ast.Call) and getattr(knoten.func, 'id', '') == 'BUNDLE':
            return {k.arg: k.value for k in knoten.keywords}
    raise AssertionError('BUNDLE fehlt in der Spec')


def _info_plist() -> dict:
    """``info_plist`` als Wörterbuch; die Version kommt zur Bauzeit aus dem Code."""
    knoten = _bundle()['info_plist']
    ergebnis = {}
    for schluessel, wert in zip(knoten.keys, knoten.values):
        ergebnis[schluessel.value] = wert.value if isinstance(wert, ast.Constant) else ast.unparse(wert)
    return ergebnis


# --- Spec und Info.plist -------------------------------------------------------

def test_bundle_mit_name_und_kennung_des_maintainers():
    bundle = _bundle()
    assert bundle['name'].value == 'NebenkostenFix.app'
    assert bundle['bundle_identifier'].value == 'de.nebenkostenfix.app'
    assert 'nebenkostenfix.icns' in ast.unparse(bundle['icon'])


def test_info_plist():
    """Ohne CFBundleName hieß das App-Menü „Python“ (Phase 0)."""
    plist = _info_plist()
    assert plist['CFBundleName'] == plist['CFBundleDisplayName'] == 'NebenkostenFix'
    assert plist['LSMinimumSystemVersion'] == '15.0'
    assert plist['NSHighResolutionCapable'] is True
    assert 'SOFTWARE_VERSION' in plist['CFBundleShortVersionString']
    assert 'SOFTWARE_VERSION' in plist['CFBundleVersion']
    for schluessel in ('NSDocumentsFolderUsageDescription', 'NSDesktopFolderUsageDescription',
                       'NSDownloadsFolderUsageDescription', 'NSRemovableVolumesUsageDescription',
                       'NSNetworkVolumesUsageDescription'):
        text = plist[schluessel]
        assert 'NebenkostenFix' in text and 'Sie' in text


def test_info_plist_erklaert_den_zugriff_aufs_lokale_netz():
    """Der Server steht oft im Heimnetz, etwa auf einem NAS. Apple empfiehlt
    den Text für jede App, die ins lokale Netz geht (TN3179). Unter macOS 26.5
    kam keine Rückfrage (Test mit dem Router, 31.10.2026); fragt ein späteres
    macOS doch, liest der Nutzer, wozu."""
    text = _info_plist()['NSLocalNetworkUsageDescription']
    assert 'NebenkostenFix-Server' in text and 'Ihre Daten bleiben' in text


def test_nur_apple_silicon_und_ohne_konsole():
    spec = _text(SPEC_MAC)
    assert "target_arch='arm64'" in spec
    assert 'console=False' in spec


def test_positivliste_wie_unter_windows():
    """Was in die App kommt (Module, Daten, versteckte Importe, Ausschlüsse),
    steht in beiden Specs wortgleich: ein Modul, das nur unter Windows
    nachgetragen wird, fehlte sonst still in der Mac-App (D-110)."""
    def positivliste(pfad: Path) -> str:
        text = _text(pfad)
        return text[text.index("WURZEL = Path(SPECPATH)"):text.index('pyz = PYZ(a.pure)')]
    assert positivliste(SPEC_MAC) == positivliste(SPEC_WIN)


# --- Icon -------------------------------------------------------------------

def test_icon_ist_ein_icns_bis_1024():
    from PIL import Image
    datei = WURZEL / 'packaging' / 'macos' / 'nebenkostenfix.icns'
    assert datei.read_bytes()[:4] == b'icns'
    with Image.open(datei) as bild:
        assert bild.format == 'ICNS'
        assert (512, 512, 2) in bild.info['sizes']   # 1024 px (Retina 512)


def test_marke_bilder_schreibt_das_icns():
    text = _text(WURZEL / 'scripts' / 'marke_bilder.py')
    assert 'nebenkostenfix.icns' in text and 'zeichen_bild(1024)' in text


# --- Abhängigkeiten ------------------------------------------------------------

def _desktop_abhaengigkeiten(plattform: str) -> set[str]:
    namen = set()
    for zeile in _text(WURZEL / 'requirements-desktop.txt').splitlines():
        zeile = zeile.split('#', 1)[0].strip()
        if not zeile:
            continue
        anforderung = Requirement(zeile)
        if anforderung.marker is None or anforderung.marker.evaluate({'sys_platform': plattform}):
            namen.add(anforderung.name)
    return namen


@pytest.mark.parametrize('plattform, erwartet', [
    ('win32', {'waitress', 'pywebview', 'pyinstaller'}),    # wie bisher
    ('darwin', {'waitress', 'pywebview', 'pyinstaller'}),
    ('linux', {'waitress'}),
])
def test_desktop_abhaengigkeiten_je_system(plattform, erwartet):
    assert _desktop_abhaengigkeiten(plattform) == erwartet


# --- Workflow ----------------------------------------------------------------

def _workflow() -> dict:
    import yaml   # fehlt es, sollen die Tests rot werden, nicht still entfallen
    return yaml.safe_load(_text(WORKFLOW))


def test_workflow_freiwillig_bei_pull_requests_und_von_hand():
    """Kein Pflicht-Check und nicht im Release (Schritt 2 von #44)."""
    workflow = _workflow()
    ausloeser = workflow.get('on') or workflow.get(True)
    assert set(ausloeser) == {'pull_request', 'workflow_dispatch'}
    assert set(ausloeser['pull_request']['branches']) == {'main', 'feature/macos'}
    assert workflow['permissions'] == {'contents': 'read'}
    assert 'macos.yml' not in _text(WURZEL / '.github' / 'workflows' / 'release.yml')


def _filter_trifft(muster: list[str], pfad: str) -> bool:
    """Pfadfilter wie bei GitHub: Das letzte passende Muster entscheidet,
    ein „!“ davor schließt aus."""
    treffer = False
    for eintrag in muster:
        aus = eintrag.startswith('!')
        regel = re.escape(eintrag.lstrip('!')).replace(r'\*\*', '.*').replace(r'\*', '[^/]*')
        if re.fullmatch(regel, pfad):
            treffer = not aus
    return treffer


@pytest.mark.parametrize('pfad, laeuft', [
    ('desktop.py', True),
    ('static/app.js', True),
    ('packaging/macos/dmg.py', True),
    ('docs/handbuch/mac-installation.md', True),     # steht als PDF im DMG
    ('docs/bilder/mac-ersetzen.png', True),
    ('README.md', False),
    ('docs/servermodus.md', False),
    ('docs/bilder/windows-start.png', False),
    ('packaging/windows/nebenkosten.spec', False),
])
def test_workflow_laeuft_nur_wenn_es_den_mac_betrifft(pfad, laeuft):
    """Der Maintainer wartet nicht auf macOS, wenn sich nur Texte oder der
    Windows-Bau ändern."""
    ausloeser = _workflow().get('on') or _workflow().get(True)
    assert _filter_trifft(ausloeser['pull_request']['paths'], pfad) is laeuft


def test_workflow_jobs_auf_festen_runnern_mit_zeitlimit():
    jobs = _workflow()['jobs']
    assert jobs['tests']['runs-on'] == 'macos-26'
    assert jobs['paket']['runs-on'] == 'macos-15'   # älteste gepflegte Version
    assert all(job.get('timeout-minutes') for job in jobs.values())


def test_workflow_prueft_das_gebaute_paket():
    schritte = '\n'.join(s.get('run', '') for s in _workflow()['jobs']['paket']['steps'])
    assert 'desktop.py --selbsttest' in schritte
    assert 'pyinstaller packaging/macos/nebenkosten.spec' in schritte
    programm = 'dist/NebenkostenFix.app/Contents/MacOS/NebenkostenFix'
    for probe in ('groesse', 'selbsttest', 'umzug'):
        assert f'packaging/windows/paketprobe.py {probe}' in schritte
    # Der Selbsttest startet im Ordner der Programmdatei; unter macOS löst
    # Popen einen relativen Pfad erst danach auf (erster CI-Lauf: FileNotFoundError).
    assert f'paketprobe.py selbsttest "$GITHUB_WORKSPACE/{programm}"' in schritte
    assert 'packaging/macos/fensterprobe.py' in schritte
    assert 'packaging/macos/dmg.py' in schritte


def test_workflow_prueft_die_signatur_auch_im_dmg():
    """Selbsttest, Umzug und Fensterprobe starten das Bundle vor dem DMG;
    schriebe ein Lauf hinein, hieße die App auf dem Mac „beschädigt“. Geprüft
    wird vor dem Bau und noch einmal im eingehängten DMG. Das Wiederholen bei
    „Resource busy“ prüft tests/test_macos_dmg.py."""
    schritte = [s.get('run', '') for s in _workflow()['jobs']['paket']['steps']]
    bau = next(s for s in schritte if 'packaging/macos/dmg.py --app' in s)
    assert bau.index('codesign --verify --deep --strict dist/NebenkostenFix.app') \
        < bau.index('packaging/macos/dmg.py --app')
    assert 'codesign --verify --deep --strict "$volume/NebenkostenFix.app"' in '\n'.join(schritte)


# --- Fensterprobe -------------------------------------------------------------

def _probe():
    spec = importlib.util.spec_from_file_location('fensterprobe', PROBE)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_fensterprobe_nur_standardbibliothek():
    erlaubt = {'__future__', 'json', 'os', 'secrets', 'subprocess', 'sys', 'time',
               'urllib', 'http', 'pathlib'}
    for knoten in ast.walk(ast.parse(_text(PROBE))):
        if isinstance(knoten, ast.Import):
            assert {a.name.split('.')[0] for a in knoten.names} <= erlaubt
        elif isinstance(knoten, ast.ImportFrom):
            assert knoten.module.split('.')[0] in erlaubt


def test_fensterprobe_liest_die_instanz(tmp_path):
    probe = _probe()
    assert probe.instanz_lesen(tmp_path) is None
    (tmp_path / 'instanz.json').write_text(json.dumps({'port': 4711, 'token': 'abc'}))
    assert probe.instanz_lesen(tmp_path) == (4711, 'abc')
    (tmp_path / 'instanz.json').write_text('{halb')
    assert probe.instanz_lesen(tmp_path) is None


def test_fensterprobe_wal_leer(tmp_path):
    probe = _probe()
    assert probe.wal_leer(tmp_path) is True
    (tmp_path / 'nebenkosten.db-wal').write_bytes(b'')
    assert probe.wal_leer(tmp_path) is True
    (tmp_path / 'nebenkosten.db-wal').write_bytes(b'x' * 10)
    assert probe.wal_leer(tmp_path) is False


@pytest.mark.parametrize('code, ok', [(200, True), (400, True), (502, False), (None, False)])
def test_fensterprobe_update_suche(code, ok):
    """Unter macOS antwortet die Suche mit 200; 400 kommt bei einem
    Manifest, das nicht passt -- auch dann war die Quelle erreicht. 502 heißt:
    keine Verbindung, etwa kein HTTPS im Paket (Risiko B0.6)."""
    assert _probe().update_suche_ok(code) is ok


# --- Lizenztexte ---------------------------------------------------------------

@pytest.mark.parametrize('paket', ['pyobjc-core', 'pyobjc-framework-security',
                                   'pyobjc-framework-uniformtypeidentifiers'])
def test_lizenztext_fuer_pyobjc_ohne_eigenen(paket):
    """Diese drei Pakete (von pywebview, nur macOS) liefern ihren Lizenztext
    nicht mit; ohne Ersatz bricht der Bau an ``drittlizenzen`` ab (NK-148)."""
    from nebenkostenfix import drittlizenzen
    text = (drittlizenzen.ERSATZ / f'{paket}.txt').read_text(encoding='utf-8')
    assert text.startswith('(This is the MIT license')
    assert 'Ronald Oussoren' in text


def test_fensterprobe_folgt_localappdata_wie_die_app(tmp_path, monkeypatch):
    """Ohne LOCALAPPDATA (CI) der Vorgabeordner der App, sonst wie die App
    der umgeleitete -- so lässt sich die Probe auch auf einem echten Mac
    fahren, ohne dessen Daten zu berühren."""
    probe = _probe()
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    assert probe.app_ordner() == Path.home() / 'Library' / 'Application Support' / 'NebenkostenFix'
    assert probe.startbefehl(Path('X.app')) == ['/usr/bin/open', '-n', 'X.app']
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert probe.app_ordner() == tmp_path / 'NebenkostenFix'
    assert probe.startbefehl(Path('X.app')) == [
        '/usr/bin/open', '-n', '--env', f'LOCALAPPDATA={tmp_path}', 'X.app']


def _ohne_app(probe, monkeypatch, run):
    """Probe ohne echte App: ``subprocess.run`` nach Wahl, nichts läuft."""
    monkeypatch.setattr(probe.subprocess, 'run', run)
    monkeypatch.setattr(probe, '_laeuft', lambda programm: False)
    monkeypatch.setattr(probe, 'FRIST', 0.1)


def test_fensterprobe_schreibt_den_bericht_auch_wenn_open_scheitert(tmp_path, monkeypatch):
    import subprocess
    probe = _probe()
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))

    def run(befehl, **_):
        raise subprocess.CalledProcessError(1, befehl)
    _ohne_app(probe, monkeypatch, run)
    bericht = tmp_path / 'bericht.json'
    assert probe.probe(tmp_path / 'NebenkostenFix.app', bericht) is False
    assert 'CalledProcessError' in json.loads(bericht.read_text(encoding='utf-8'))['fehler']


def test_fensterprobe_haengendes_beenden_steht_im_bericht(tmp_path, monkeypatch):
    """Braucht ``quit app`` auf dem Runner eine Freigabe, wartet osascript;
    die Werte davor sollen trotzdem im Bericht stehen (Review B, R1)."""
    import subprocess
    probe = _probe()
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))

    def run(befehl, **_):
        if befehl[0] == '/usr/bin/osascript':
            raise subprocess.TimeoutExpired(befehl, 60)
        return subprocess.CompletedProcess(befehl, 0, '', '')
    _ohne_app(probe, monkeypatch, run)
    monkeypatch.setattr(probe, 'instanz_lesen', lambda ordner: (4711, 'abc'))
    monkeypatch.setattr(probe, '_status', lambda oeffner, anfrage: 204)
    bericht = tmp_path / 'bericht.json'
    assert probe.probe(tmp_path / 'NebenkostenFix.app', bericht) is False
    gelesen = json.loads(bericht.read_text(encoding='utf-8'))
    assert gelesen['quit'] == 'zeitueberschreitung' and gelesen['nach_vorne'] == 204


def test_fensterprobe_beendet_nur_die_gepruefte_app(tmp_path, monkeypatch):
    """Eine installierte NebenkostenFix.app daneben bleibt unberührt (Review B, R4)."""
    import subprocess
    probe = _probe()
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    befehle = []

    def run(befehl, **_):
        befehle.append(befehl)
        return subprocess.CompletedProcess(befehl, 0, '', '')
    _ohne_app(probe, monkeypatch, run)
    app = tmp_path / 'dist' / 'NebenkostenFix.app'
    probe.probe(app, tmp_path / 'bericht.json')
    beenden = next(b for b in befehle if b[0] == '/usr/bin/osascript')
    assert beenden[-1] == str(app.resolve()) and 'quit app "NebenkostenFix"' not in beenden
