"""Ein Design auf jeder Seite, auch nach Phase 5 (NK-156, F-89).

Der Wächter aus Phase 5 (``test_ui_konsistenz.py``) prüft Farbwerte in
Inline-Stilen. Die Drift danach lag woanders: Karten mit eigenen
Schriftgrößen und Abständen, Emoji in Knöpfen, Leerzustände ohne nächsten
Schritt, sieben Einstellungskarten untereinander. Diese Prüfungen sehen auf
die Struktur.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
SKRIPT = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
STIL = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')
ANMELDUNG = (WURZEL / 'static' / 'anmeldung.css').read_text(encoding='utf-8')

# Die Zahl sinkt nur. Wer einen Inline-Stil entfernt, senkt sie mit; wer
# einen braucht, nimmt eine Klasse aus style.css (Abschnitt NK-156).
# ``display: none;`` zählt nicht: das schaltet app.js um.
INLINE_STILE_HOECHSTENS = 108

KLEINE_SCHRIFT = re.compile(
    r'font-size:\s*(?:(?:[0-9]|1[0-2])(?:\.\d+)?px|0\.(?:[0-7]\d*|80?)(?:rem|em))\b')
EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-➿⭐✅]')


def _ohne_kommentare_html(text: str) -> str:
    return re.sub(r'<!--.*?-->', ' ', text, flags=re.S)


def _ohne_kommentare_js(text: str) -> str:
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'^\s*//.*$', ' ', text, flags=re.M)


def test_inline_stile_werden_nicht_mehr():
    stile = [re.sub(r'\s+', ' ', s).strip()
             for s in re.findall(r'style="([^"]*)"', SEITE, flags=re.S)]
    zaehlbar = [s for s in stile if s != 'display: none;']
    assert len(zaehlbar) <= INLINE_STILE_HOECHSTENS, (
        f'{len(zaehlbar)} Inline-Stile in index.html (höchstens {INLINE_STILE_HOECHSTENS}). '
        'Bitte eine Klasse aus style.css nehmen.')


def test_keine_schrift_unter_13_pixel():
    funde = []
    for name, text in (('index.html', _ohne_kommentare_html(SEITE)),
                       ('app.js', _ohne_kommentare_js(SKRIPT)),
                       ('style.css', STIL), ('anmeldung.css', ANMELDUNG)):
        funde += [f'{name}: {m.group(0)}' for m in KLEINE_SCHRIFT.finditer(text)]
    assert funde == [], funde


def test_kein_emoji_in_der_oberflaeche():
    funde = []
    for name, text in (('index.html', _ohne_kommentare_html(SEITE)),
                       ('app.js', _ohne_kommentare_js(SKRIPT))):
        for nummer, zeile in enumerate(text.splitlines(), 1):
            if EMOJI.search(zeile):
                funde.append(f'{name}:{nummer}: {zeile.strip()[:80]}')
    assert funde == [], funde


def test_jeder_leerzustand_nennt_den_naechsten_schritt():
    """K4: der Knopf benennt den nächsten sinnvollen Schritt."""
    ohne = []
    for treffer in re.finditer(r'leerzustand\(\{', SKRIPT):
        tiefe, stelle = 1, treffer.end()
        while tiefe and stelle < len(SKRIPT):
            tiefe += {'{': 1, '}': -1}.get(SKRIPT[stelle], 0)
            stelle += 1
        rumpf = SKRIPT[treffer.end():stelle]
        if 'aktion' not in rumpf:
            titel = re.search(r"titel:\s*'([^']*)'", rumpf)
            ohne.append(titel.group(1) if titel else rumpf[:60])
    assert ohne == [], ohne


def test_einstellungen_in_gruppen():
    """K8: jede Karte gehört zu genau einer Gruppe, jede Gruppe hat einen Knopf."""
    anfang = SEITE.index('id="tab-settings"')
    ende = SEITE.index('</section>', anfang)
    bereich = SEITE[anfang:ende]
    karten = re.findall(r'<div([^>]*)class="dashboard-card', bereich)
    assert karten and all('data-gruppe="' in attribute for attribute in karten), karten
    gruppen_der_karten = set(re.findall(r'data-gruppe="([a-z]+)" class="dashboard-card', bereich))
    gruppen_der_knoepfe = set(re.findall(r'class="filter-pill" role="tab" data-gruppe="([a-z]+)"',
                                         bereich))
    assert gruppen_der_karten == gruppen_der_knoepfe
    for gruppe in gruppen_der_knoepfe:
        assert f"'{gruppe}'" in SKRIPT.split('const EINSTELLUNGS_GRUPPEN')[1].split(';')[0]


def test_globaler_kopf_traegt_nur_was_ueberall_gilt():
    """K2: Drucken und Abmelden; Exporte stehen in den Einstellungen --
    Belege unter Sicherung, der JSON-Datenauszug unter Datenschutz (NK-164)."""
    anfang = SEITE.index('<div class="kopf-aktionen">')
    kopf = SEITE[anfang:SEITE.index('</header>', anfang)]
    assert 'huelle.drucken()' in kopf and 'abmelden()' in kopf
    assert 'exportData()' not in kopf and '/api/belege/export' not in kopf
    sicherung = SEITE[SEITE.index('<h3>Sicherung</h3>'):]
    assert '/api/belege/export' in sicherung.split('data-gruppe=')[0]
    auszug = SEITE[SEITE.index('<h3>Datenauszug für andere Programme</h3>'):]
    assert 'exportData()' in auszug.split('data-gruppe=')[0]
    umzug = SEITE[SEITE.index('<h3>Umzug auf einen anderen Rechner</h3>'):]
    assert 'umzugExportieren()' in umzug.split('data-gruppe=')[0]


def test_begruessung_ohne_zurueck_beim_ersten_besuch():
    assert '<h1 id="begruessung">Willkommen bei NebenkostenFix!</h1>' in SEITE
    assert "'Willkommen zurück!' : 'Willkommen bei NebenkostenFix!'" in SKRIPT


def test_platzhalter_sehen_nicht_wie_werte_aus():
    """Ein grauer Beispielwert ohne „z. B.“ wirkt wie schon ausgefüllt."""
    for platzhalter in re.findall(r'placeholder="([^"]*)"', SEITE):
        if re.search(r'Mustermann|DE\d{2}', platzhalter):
            assert platzhalter.startswith('z. B.'), platzhalter


def test_anmeldeseiten_nehmen_die_farben_der_anwendung():
    for variable in ('--primary', '--primary-hover', '--text-main'):
        wert_app = re.search(rf'{variable}:\s*([^;]+);', STIL).group(1).strip()
        wert_anmeldung = re.search(rf'{variable}:\s*([^;]+);', ANMELDUNG).group(1).strip()
        assert wert_app == wert_anmeldung, variable




def test_hidden_gilt_auch_fuer_knoepfe():
    """Ein Knopf mit ``hidden`` bleibt verborgen, auch wenn seine Klasse
    ``display`` setzt -- auch auf den Anmeldeseiten (NK-164: „Zur Anmeldung“
    stand dort vor der Übernahme)."""
    for stil in (STIL, ANMELDUNG):
        assert re.search(r'\[hidden\]\s*\{\s*display:\s*none\s*!important;', stil)
