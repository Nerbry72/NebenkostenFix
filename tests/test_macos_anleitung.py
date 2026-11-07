"""Die bebilderte Anleitung für den Mac (#44): Sie passt zur App.

Die Anleitung richtet sich an Leute ohne IT-Kenntnisse. Was sie nennt
(Mindestversion, Datenordner, Menüeinträge), muss deshalb genau so in der
App stehen, und jedes Bild muss es geben.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import Image

import desktop
from nebenkostenfix import aktualisierung
from nebenkostenfix import auth
from nebenkostenfix import haftung
from nebenkostenfix import windows_ordner
from tests.test_macos_paket import _info_plist

WURZEL = Path(__file__).resolve().parents[1]
ANLEITUNG = WURZEL / 'docs' / 'handbuch' / 'mac-installation.md'
FAQ = WURZEL / 'docs' / 'handbuch' / 'faq.md'
DIALOGE = ('mac-nicht-geoeffnet', 'mac-dennoch-oeffnen', 'mac-administrator', 'mac-ersetzen')
# Ausgeschnittene Fenster: Dialoge von macOS und das Fenster des DMG
FENSTER = (*DIALOGE, 'mac-dmg-fenster')


def _text() -> str:
    return ANLEITUNG.read_text(encoding='utf-8')


def _bilder() -> list[Path]:
    return [(ANLEITUNG.parent / pfad).resolve()
            for pfad in re.findall(r'!\[[^\]]+\]\(([^)]+\.png)\)', _text())]


def test_jedes_bild_gibt_es_und_alle_haben_einen_alternativtext():
    bilder = _bilder()
    assert {b.stem for b in bilder} >= {*FENSTER, 'mac-datenschutz'}
    for bild in bilder:
        assert bild.is_file(), bild
        assert bild.parent == WURZEL / 'docs' / 'bilder'
    assert not re.search(r'!\[\]\(', _text())


@pytest.mark.parametrize('name', FENSTER)
def test_dialogbilder_mit_transparenten_ecken(name):
    """Ausgeschnitten auf den Rahmen: In den Ecken stand vorher ein Stück
    Finder-Liste."""
    with Image.open(WURZEL / 'docs' / 'bilder' / f'{name}.png') as bild:
        assert bild.mode == 'RGBA'
        breite, hoehe = bild.size
        for ecke in ((0, 0), (breite - 1, 0), (0, hoehe - 1), (breite - 1, hoehe - 1)):
            assert bild.getpixel(ecke)[3] == 0, ecke
        assert bild.getpixel((breite // 2, hoehe // 2))[3] == 255


@pytest.mark.parametrize('name', [*FENSTER, 'mac-datenschutz'])
def test_jedes_bild_zeigt_rot_wo_man_klickt(name):
    """Wer den Text überliest, sieht am Bild, welchen Knopf er drückt."""
    with Image.open(WURZEL / 'docs' / 'bilder' / f'{name}.png') as bild:
        roh = bild.convert('RGBA').tobytes()
    rot = sum(1 for i in range(0, len(roh), 4)
              if roh[i + 3] > 200 and roh[i] > 200 and roh[i + 1] < 70 and roh[i + 2] < 70)
    assert rot > 1000, rot
    assert 'rot markiert' in _text()


def test_mindestversion_wie_im_paket():
    version = _info_plist()['LSMinimumSystemVersion']
    hauptversion = version.split('.')[0]
    assert f'macOS {hauptversion}' in _text()
    assert 'Apple-Chip' in _text()


def test_datenordner_wie_in_der_app(monkeypatch, tmp_path):
    monkeypatch.setattr(aktualisierung, 'betriebssystem', lambda: 'darwin')
    # Path.home() liest unter Windows USERPROFILE, sonst HOME (CI unter Windows).
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    ordner = windows_ordner.vorgabe_datenordner().relative_to(tmp_path)
    assert f'~/{ordner.as_posix()}' in _text()


def test_menueeintraege_gibt_es_in_der_app():
    quelle = Path(desktop.__file__).read_text(encoding='utf-8')
    for eintrag in re.findall(r'„Hilfe“ → „([^“]+)“', _text()):
        assert f"MenuAction('{eintrag}'" in quelle, eintrag
    assert '„Hilfe“ → „Datenordner anzeigen“' in _text()


def test_jeder_schritt_des_ersten_starts_kommt_vor():
    """Seit macOS 15 gibt es keinen Rechtsklick-Weg mehr: Systemeinstellungen,
    „Dennoch öffnen“, dann bestätigt ein Administrator."""
    text = _text()
    for schritt in ('Fertig', 'Datenschutz & Sicherheit', 'Dennoch öffnen', 'Administrator'):
        assert schritt in text, schritt
    assert text.index('Fertig') < text.index('Datenschutz & Sicherheit') \
        < text.rindex('Dennoch öffnen') < text.rindex('Administrator')


def test_faq_verweist_auf_die_anleitung():
    faq = FAQ.read_text(encoding='utf-8')
    abschnitt = faq[faq.index('### macOS sagt'):faq.index('### Windows-App oder Docker')]
    assert '(mac-installation.md)' in abschnitt
    # Die Schritte stehen nur noch in der Anleitung.
    assert 'Dennoch öffnen' not in abschnitt


def _abschnitt(titel: str) -> str:
    text = _text()
    anfang = text.index(titel)
    ende = text.find('\n## ', anfang + 1)
    return text[anfang:ende if ende != -1 else None]


def test_servermodus_mit_den_texten_der_oberflaeche():
    """#45: Die Anleitung nennt Karte, Haken und Knopf so, wie sie in der
    Oberfläche stehen, und den Rückweg so, wie er im Menü steht."""
    abschnitt = ' '.join(_abschnitt('## 9. Mit einem Server verbinden').split())
    seite = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
    quelle = Path(desktop.__file__).read_text(encoding='utf-8')
    assert 'Einstellungen → Datensicherung' in abschnitt
    for text in ('Mit einem Server verbinden', 'Adresse des Servers',
                 'Ich habe verstanden, dass ich danach mit den Daten auf dem Server arbeite.'):
        assert text in abschnitt and text in ' '.join(seite.split()), text
    assert re.search(r'>\s*Verbinden\s*</button>', seite) and '**Verbinden**' in abschnitt
    assert "MenuAction('Auf diesem Rechner arbeiten …'" in quelle
    assert '„Ablage“ → „Auf diesem Rechner arbeiten …“' in abschnitt
    assert 'http://' in abschnitt    # ohne Schema nimmt die App https an
    # Hinweg: beim ersten Start die Startwahl, später das Menü
    assert '**Mit einem NebenkostenFix-Server verbinden**' in abschnitt
    assert 'Mit einem NebenkostenFix-Server verbinden' in ' '.join(seite.split())
    assert "MenuAction('Mit einem Server verbinden …'" in quelle
    assert '„Ablage“ → „Mit einem Server verbinden …“' in abschnitt
    assert 'Bevor es losgeht' not in abschnitt   # dort gibt es keinen Server-Knopf mehr


def test_erster_start_endet_bei_der_startwahl():
    """#45: Ohne Objekte fragt die App zuerst, wo die Daten liegen sollen.
    Wer keinen Server hat, soll nicht raten müssen."""
    abschnitt = ' '.join(_abschnitt('## 4. Der erste Start').split())
    seite = ' '.join((WURZEL / 'static' / 'index.html').read_text(encoding='utf-8').split())
    for text in ('Wo sollen Ihre Daten liegen?', 'Auf diesem Rechner arbeiten'):
        assert text in abschnitt and text in seite, text
    assert '**Auf diesem Rechner arbeiten**' in abschnitt
    # Danach kommt noch der Hinweis vor dem ersten Arbeiten.
    assert f'„{haftung.TITEL}“' in abschnitt
    assert '**Verstanden**' in abschnitt and '>Verstanden</button>' in seite


def test_reiter_der_einstellungen_wie_in_der_app():
    """Der Reiter heißt „Datensicherung“, nicht „Sicherung“."""
    seite = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
    assert re.search(r'</i> Datensicherung</button>', seite)
    assert 'Einstellungen → Sicherung' not in _text()
    assert _text().count('Einstellungen → Datensicherung') >= 2


def test_neu_anfangen_ohne_die_laufende_app():
    """Die App ist schon beendet, also führt nur der Finder zum Ordner. Leer
    sind danach die Daten; die Verbindung zu einem Server bleibt gemerkt."""
    abschnitt = ' '.join(_abschnitt('## 7. Neu anfangen').split())
    assert 'Gehe zu Ordner' in abschnitt
    assert '`~/Library/Application Support/NebenkostenFix`' in abschnitt
    assert 'Hilfe' not in abschnitt
    assert 'wie am ersten Tag' not in abschnitt
    assert 'Einstellungen → Datensicherung' in abschnitt


def test_servermodus_nennt_die_grenzen_unter_macos():
    """#45: Der Server erlaubt kein 'unsafe-eval'. WKWebView baut dann die
    Brücke von pywebview nicht, Speichern und Öffnen gehen nicht. Drucken
    geht (Probe gegen den Server, 30.10.2026). Erlaubt der Server es
    eines Tages, fällt dieser Test auf und die Grenze aus der Anleitung."""
    assert "'unsafe-eval'" not in auth.CSP
    abschnitt = ' '.join(_abschnitt('## 9. Mit einem Server verbinden').split())
    for text in ('keine Dateien speichern', 'keine Belege öffnen', 'Drucken geht', 'Safari'):
        assert text in abschnitt, text
    servermodus = ' '.join((WURZEL / 'docs' / 'servermodus.md').read_text(encoding='utf-8').split())
    assert "'unsafe-eval'" in servermodus and 'api.js' in servermodus


def test_installieren_und_ersetzen_mit_bild():
    """Abschnitt 3 zeigt das Fenster des DMG, Abschnitt 5 den Knopf, mit dem
    Finder die alte Version ersetzt. Nach dem Ersetzen fragt macOS wieder
    nach (DMG-Test 0.17.1 → 0.18.0 des Nutzers, 30.10.2026)."""
    installieren = _abschnitt('## 3. Installieren')
    neue_version = ' '.join(_abschnitt('## 5. Eine neue Version installieren').split())
    assert '../bilder/mac-dmg-fenster.png' in installieren
    assert '../bilder/mac-ersetzen.png' in neue_version
    assert '**Ersetzen**' in neue_version
    assert 'fragt macOS beim nächsten Start wieder nach' in neue_version
