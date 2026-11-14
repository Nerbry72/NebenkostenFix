"""Das gestaltete DMG der Mac-App (#44): Einstellungen, Hintergrund, PDF.

dmgbuild läuft nur auf macOS und nur im Workflow. Geprüft wird hier, was
ohne Mac geht: dass die Einstellungen in sich stimmen, dass der Hintergrund
zum Fenster passt, dass die Anleitung als PDF entsteht und dass der Workflow
das fertige DMG prüft.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

WURZEL = Path(__file__).resolve().parents[1]
MACOS = WURZEL / 'packaging' / 'macos'
ANLEITUNG = WURZEL / 'docs' / 'handbuch' / 'mac-installation.md'
WORKFLOW = WURZEL / '.github' / 'workflows' / 'macos.yml'


def _modul(name):
    spec = importlib.util.spec_from_file_location(name, MACOS / f'{name}.py')
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope='module')
def dmg():
    return _modul('dmg')


@pytest.fixture(scope='module')
def anleitung_pdf():
    return _modul('anleitung_pdf')


# --- Einstellungen ------------------------------------------------------------

def _einstellungen(dmg, tmp_path):
    app = tmp_path / 'NebenkostenFix.app'
    pdf = tmp_path / dmg.ANLEITUNG_NAME
    return dmg.einstellungen(app, pdf)


def test_jede_datei_und_jede_verknuepfung_hat_einen_platz(dmg, tmp_path):
    einstellungen = _einstellungen(dmg, tmp_path)
    namen = {Path(datei).name for datei in einstellungen['files']} | set(einstellungen['symlinks'])
    assert namen == {'NebenkostenFix.app', 'Programme', 'Installationsanleitung.pdf'}
    assert set(einstellungen['icon_locations']) == namen
    breite, hoehe = einstellungen['window_rect'][1]
    for x, y in einstellungen['icon_locations'].values():
        assert 0 < x < breite and 0 < y < hoehe


def test_alles_passt_ohne_rollbalken_ins_fenster(dmg, tmp_path):
    """window_rect meint das Fenster mit Titelleiste. Mit 400 Punkt blieben
    unter macOS 26 nur 368 für den Inhalt: Die Anleitung war abgeschnitten,
    rechts kam ein Rollbalken (DMG-Test des Nutzers, 30.10.2026).

    Unter dem Symbol hält Finder mehr frei als die Beschriftung: Mit der
    Anleitung bei y = 290 kam der Rollbalken wieder, bei 280 nicht
    (Probe-DMGs unter macOS 26, 30.10.2026)."""
    einstellungen = _einstellungen(dmg, tmp_path)
    breite, hoehe = einstellungen['window_rect'][1]
    assert (breite, hoehe) == (dmg.FENSTER[0], dmg.FENSTER[1] + dmg.TITELLEISTE)
    for x, y in einstellungen['icon_locations'].values():
        assert y + dmg.SYMBOLGROESSE // 2 + 64 <= dmg.FENSTER[1]   # 64: Beschriftung und Rand
        assert x + dmg.SYMBOLGROESSE // 2 <= dmg.FENSTER[0]


def test_programme_zeigt_auf_den_ordner_programme(dmg, tmp_path):
    assert _einstellungen(dmg, tmp_path)['symlinks'] == {'Programme': '/Applications'}


def test_nur_die_symbole_ohne_leisten(dmg, tmp_path):
    einstellungen = _einstellungen(dmg, tmp_path)
    assert einstellungen['format'] == 'UDZO'
    assert einstellungen['default_view'] == 'icon-view'
    for leiste in ('show_toolbar', 'show_sidebar', 'show_status_bar', 'show_pathbar',
                   'show_tab_view'):
        assert einstellungen[leiste] is False, leiste
    assert einstellungen['icon'] == str(MACOS / 'nebenkostenfix.icns')
    assert einstellungen['background'] == str(MACOS / 'dmg-hintergrund.png')


def test_keine_finder_info_am_bundle(dmg, tmp_path):
    """hide_extensions setzt com.apple.FinderInfo an der App im DMG; danach
    scheiterte codesign --verify --strict im eingehängten DMG („resource fork,
    Finder information, or similar detritus not allowed“, lokaler Bau 30.10.2026)."""
    assert 'hide_extensions' not in _einstellungen(dmg, tmp_path)


def test_app_links_programme_rechts_auf_einer_hoehe(dmg, tmp_path):
    """Der Pfeil im Hintergrund zeigt von der App nach rechts auf Programme."""
    orte = _einstellungen(dmg, tmp_path)['icon_locations']
    app, programme = orte['NebenkostenFix.app'], orte['Programme']
    assert app[0] < programme[0] and app[1] == programme[1]
    assert orte['Installationsanleitung.pdf'][1] > app[1]


# --- Hintergrund --------------------------------------------------------------

def test_hintergrund_passt_zum_fenster_und_hat_ein_2x(dmg):
    """Unter macOS 15 ist die Titelleiste niedriger als unter 26 und der
    Inhalt etwas höher: Das Bild reicht weiter, sonst bliebe unten ein Streifen."""
    breite, hoehe = dmg.BILD
    assert breite == dmg.FENSTER[0] and hoehe >= dmg.FENSTER[1] + 8
    with Image.open(MACOS / 'dmg-hintergrund.png') as einfach, \
            Image.open(MACOS / 'dmg-hintergrund@2x.png') as doppelt:
        assert einfach.size == (breite, hoehe)
        assert doppelt.size == (2 * breite, 2 * hoehe)


def test_hintergrund_wird_aus_dem_code_erzeugt(dmg):
    """Wie die übrigen Bilder der Marke: marke_bilder.py schreibt ihn."""
    assert dmg.hintergrund(1).size == dmg.BILD
    assert dmg.hintergrund(2).size == tuple(2 * k for k in dmg.BILD)
    text = (WURZEL / 'scripts' / 'marke_bilder.py').read_text(encoding='utf-8')
    assert 'hintergrund_schreiben' in text


def test_hintergrund_unter_den_symbolen_ruhig(dmg, tmp_path):
    """Wo Finder Symbol und Beschriftung zeichnet, steht im Bild nichts: Die
    Fläche hat überall die Farbe des Verlaufs an dieser Stelle."""
    bild = dmg.hintergrund(1).convert('RGB')
    rand = dmg.SYMBOLGROESSE // 2 + 4
    for x, y in _einstellungen(dmg, tmp_path)['icon_locations'].values():
        for dy in range(-rand, rand + 24, 6):        # 24: Beschriftung darunter
            zeile = {bild.getpixel((xx, y + dy)) for xx in range(x - rand, x + rand, 6)}
            assert len(zeile) == 1, (x, y + dy)


# --- Bauen ------------------------------------------------------------------

def test_bauen_versucht_es_mehrmals(dmg, tmp_path, monkeypatch):
    """hdiutil meldet auf den Runnern gelegentlich „Resource busy“
    (runner-images#7522). Eine halbe Datei vom Fehlversuch zählt nicht."""
    aufrufe = []
    ziel = tmp_path / 'NebenkostenFix.dmg'

    def build_dmg(dateiname, name, settings, detach_retries):
        aufrufe.append((dateiname, name, detach_retries))
        Path(dateiname).write_bytes(b'halb')
        if len(aufrufe) < 3:
            raise RuntimeError('hdiutil: create failed - Resource busy')

    monkeypatch.setitem(sys.modules, 'dmgbuild', types.SimpleNamespace(build_dmg=build_dmg))
    monkeypatch.setattr(dmg.time, 'sleep', lambda s: None)
    dmg.bauen(ziel, tmp_path / 'NebenkostenFix.app', tmp_path / dmg.ANLEITUNG_NAME)
    assert len(aufrufe) == 3
    assert aufrufe[0] == (str(ziel), 'NebenkostenFix', 12)


def test_bauen_gibt_nach_den_versuchen_auf(dmg, tmp_path, monkeypatch):
    ziel = tmp_path / 'NebenkostenFix.dmg'

    def build_dmg(dateiname, name, settings, detach_retries):
        Path(dateiname).write_bytes(b'halb')
        raise RuntimeError('Resource busy')

    monkeypatch.setitem(sys.modules, 'dmgbuild', types.SimpleNamespace(build_dmg=build_dmg))
    monkeypatch.setattr(dmg.time, 'sleep', lambda s: None)
    with pytest.raises(RuntimeError):
        dmg.bauen(ziel, tmp_path / 'NebenkostenFix.app', tmp_path / dmg.ANLEITUNG_NAME)
    assert not ziel.exists()


# --- Anleitung als PDF --------------------------------------------------------

def _pdf(anleitung_pdf, tmp_path) -> bytes:
    ziel = tmp_path / 'Installationsanleitung.pdf'
    anleitung_pdf.bauen(ANLEITUNG, ziel, komprimiert=False)
    return ziel.read_bytes()


def test_pdf_entsteht(anleitung_pdf, tmp_path):
    assert _pdf(anleitung_pdf, tmp_path).startswith(b'%PDF')


def _pdf_text(roh: bytes) -> str:
    """Die Zeichenketten im unkomprimierten PDF lesbar: Umlaute stehen dort
    als Oktal-Escape (``m\\366chten``), Klammern als ``\\(``."""
    text = roh.decode('latin-1')
    text = re.sub(r'\\([0-3][0-7]{2})',
                  lambda t: bytes([int(t.group(1), 8)]).decode('cp1252', errors='replace'), text)
    return text.replace('\\(', '(').replace('\\)', ')')


def test_pdf_enthaelt_jede_ueberschrift(anleitung_pdf, tmp_path):
    inhalt = _pdf_text(_pdf(anleitung_pdf, tmp_path))
    for ueberschrift in re.findall(r'^#{1,3} (.+)$', ANLEITUNG.read_text(encoding='utf-8'),
                                   re.MULTILINE):
        assert ueberschrift in inhalt, ueberschrift


def test_pdf_enthaelt_jedes_bild(anleitung_pdf, tmp_path):
    bilder = re.findall(r'!\[[^\]]+\]\(([^)]+)\)', ANLEITUNG.read_text(encoding='utf-8'))
    inhalt = _pdf(anleitung_pdf, tmp_path)
    assert len(bilder) >= 4
    # Gezählt wird, was gezeichnet wird: Die Alpha-Masken der Dialoge sind
    # eigene Bildobjekte, aber kein eigenes Bild.
    assert len(set(re.findall(rb'/(FormXob\.\w+) Do', inhalt))) == len(bilder)


def test_pdf_pfeil_aus_der_symbolschrift(anleitung_pdf):
    """Helvetica kennt kein „→“ (nicht in Windows-1252)."""
    absatz = anleitung_pdf.inline('Einstellungen → Sicherung')
    assert absatz == 'Einstellungen <font face="Symbol">→</font> Sicherung'


@pytest.mark.parametrize('markdown, erwartet', [
    ('**fett** und `code`', '<b>fett</b> und <font face="Courier">code</font>'),
    ('a < b & c', 'a &lt; b &amp; c'),
    ('„Ablage“ → „Neu“', '„Ablage“ <font face="Symbol">→</font> „Neu“'),
    ('auf der [Projektseite](https://github.com/x#y).',
     'auf der <a href="https://github.com/x#y" color="#4F46E5"><u>Projektseite</u></a>.'),
])
def test_pdf_inline(anleitung_pdf, markdown, erwartet):
    assert anleitung_pdf.inline(markdown) == erwartet


def test_pdf_bloecke(anleitung_pdf):
    text = ('# Titel\n\nEin Absatz\nüber zwei Zeilen.\n\n## 1. Teil\n\n'
            '1. Erster Schritt\n   geht weiter.\n2. Zweiter\n\n- Punkt\n\n'
            '![Bild](../bilder/mac-datenschutz.png)\n')
    bloecke = anleitung_pdf.bloecke(text)
    assert bloecke == [
        ('h1', 'Titel'), ('absatz', 'Ein Absatz über zwei Zeilen.'), ('h2', '1. Teil'),
        ('nummer', ['Erster Schritt geht weiter.', 'Zweiter']), ('punkt', ['Punkt']),
        ('bild', '../bilder/mac-datenschutz.png')]


# --- Workflow -----------------------------------------------------------------

def _paket_schritte() -> list[dict]:
    import yaml
    return yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))['jobs']['paket']['steps']


def _run() -> str:
    return '\n'.join(s.get('run', '') for s in _paket_schritte())


def test_workflow_baut_mit_gepinntem_dmgbuild():
    run = _run()
    assert 'pip install dmgbuild==1.6.7' in run
    assert 'packaging/macos/anleitung_pdf.py docs/handbuch/mac-installation.md' in run
    assert 'packaging/macos/dmg.py' in run
    assert 'hdiutil create' not in run


def test_workflow_prueft_das_fertige_dmg():
    run = _run()
    assert 'hdiutil verify' in run
    assert re.search(r'hdiutil attach .*-readonly', run)
    assert 'codesign --verify --deep --strict "$volume/NebenkostenFix.app"' in run
    for datei in ('.DS_Store', '.background.tiff', 'Installationsanleitung.pdf'):
        assert f'"$volume/{datei}"' in run, datei
    assert 'hdiutil detach' in run


def test_workflow_laedt_das_dmg_ohne_zip_hoch():
    """Ein Doppelklick im Browser lädt dann direkt das DMG, kein ZIP (#44)."""
    uploads = [s['with'] for s in _paket_schritte()
               if s.get('uses', '').startswith('actions/upload-artifact@')]
    dmg_upload = [u for u in uploads if u.get('archive') is False]
    assert len(dmg_upload) == 1
    assert dmg_upload[0]['path'].endswith('-macOS-arm64.dmg')
    berichte = [u for u in uploads if u.get('name') == 'nebenkostenfix-macos-berichte']
    assert berichte and 'THIRD_PARTY_LICENSES.txt' in berichte[0]['path']
    assert all(s['uses'] == 'actions/upload-artifact@v7' for s in _paket_schritte()
               if s.get('uses', '').startswith('actions/upload-artifact@'))


def test_pdf_liste_unterbricht_den_absatz(anleitung_pdf):
    """Wie auf GitHub (CommonMark): Abschnitt 6 hat die Liste ohne Leerzeile."""
    assert anleitung_pdf.bloecke('So öffnen Sie ihn:\n- im Menü, oder\n- im Finder.\n') == [
        ('absatz', 'So öffnen Sie ihn:'), ('punkt', ['im Menü, oder', 'im Finder.'])]
