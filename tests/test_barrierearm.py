"""NK-162: barrierearm und für Ungeübte (F-91).

Kontrast der gedämpften Schrift, beschriftete Seitenleiste auf dem Tablet,
ein Name für jeden Symbolknopf, Tastatur und Fokus in Dialogen, Rückfrage
bei ungespeicherter Eingabe, größere Schrift, Leerlauf-Hinweis und ein
Entwurf, der die Abmeldung überlebt. Das Verhalten im Browser prüft der
Rundgang (NK-157); hier stehen die Regeln, die ohne Browser prüfbar sind.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
SKRIPT = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
STIL = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')


def _farbe(name: str) -> str:
    return re.search(rf'{name}:\s*(#[0-9A-Fa-f]{{6}})', STIL).group(1)


def _rgb(hexwert: str) -> tuple[float, float, float]:
    return tuple(int(hexwert[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _luminanz(rgb) -> float:
    def kanal(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (kanal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _kontrast(a, b) -> float:
    la, lb = sorted((_luminanz(a), _luminanz(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _ueber_weiss(hexwert: str, deckung: float):
    return tuple(deckung * c + (1 - deckung) * 1.0 for c in _rgb(hexwert))


def test_gedaempfte_schrift_hat_ueberall_genug_kontrast():
    """WCAG AA: 4,5 : 1 für Fließtext -- auf Weiß, auf dem Seitengrund und auf
    den Tönungen der Primärfarbe (Hinweiskästen, Marken)."""
    gedaempft = _rgb(_farbe('--text-muted'))
    for grund in ((1.0, 1.0, 1.0), _rgb(_farbe('--bg-color')),
                  _ueber_weiss(_farbe('--primary'), 0.08),
                  _ueber_weiss(_farbe('--primary'), 0.12)):
        assert _kontrast(gedaempft, grund) >= 4.5, grund


def test_primaerfarbe_als_schrift_hat_genug_kontrast():
    primaer = _rgb(_farbe('--primary'))
    assert _kontrast(primaer, (1.0, 1.0, 1.0)) >= 4.5
    assert _kontrast(primaer, _ueber_weiss(_farbe('--primary'), 0.08)) >= 4.5


def test_jeder_symbolknopf_hat_einen_namen():
    ohne = []
    for treffer in re.finditer(r'<button([^>]*)>(.*?)</button>', SEITE, re.S):
        text = re.sub(r'<[^>]+>', '', treffer.group(2)).strip()
        if not text and 'aria-label' not in treffer.group(1) and 'title=' not in treffer.group(1):
            ohne.append(SEITE.count('\n', 0, treffer.start()) + 1)
    assert ohne == [], f'Symbolknöpfe ohne Namen in den Zeilen {ohne}'
    # Zur Laufzeit gebaute Knöpfe benennt app.js nach Symbol oder title.
    assert 'symbolknoepfeBenennen(document)' in SKRIPT


def test_seitenleiste_auf_dem_tablet_mit_beschriftung():
    tablet = STIL[STIL.index('@media (max-width: 1024px)'):]
    tablet = tablet[:tablet.index('\n}\n')]
    assert 'font-size: 0' not in tablet
    assert "eintrag.setAttribute('aria-label', name)" in SKRIPT


def test_dialoge_fokus_tab_und_rueckfrage():
    for teil in ("modal.setAttribute('role', 'dialog')", "e.key === 'Tab'",
                 'dialogAusloeser.set(overlay, document.activeElement)',
                 'function darfDialogSchliessen(overlay)',
                 "overlay.addEventListener('input'"):
        assert teil in SKRIPT, teil
    # Escape (nur der oberste Dialog, NK-160) und Klick daneben fragen, bevor sie schließen.
    assert 'if (oben && darfDialogSchliessen(oben)) oben.classList.remove' in SKRIPT
    assert 'e.target === overlay && darfDialogSchliessen(overlay)' in SKRIPT


def test_groessere_schrift_in_drei_stufen():
    werte = re.findall(r'name="schriftgroesse" value="([0-9.]+)"', SEITE)
    assert werte == ['1', '1.15', '1.3']
    assert 'const SCHRIFTGROESSEN = [1, 1.15, 1.3];' in SKRIPT


def test_entwurf_ueberlebt_die_abmeldung():
    umleitung = SKRIPT[SKRIPT.index('function zurAnmeldung()'):]
    umleitung = umleitung[:umleitung.index('window.location.assign')]
    assert 'window.entwurfSichern' in umleitung
    assert "sessionStorage.setItem('nk-entwurf'" in SKRIPT
    assert "['password', 'file', 'hidden'].includes(feld.type)" in SKRIPT  # keine Passwörter
    assert 'id="entwurf-hinweis"' in SEITE and 'entwurfWiederherstellen()' in SEITE


def test_leerlauf_hinweis_fuenf_minuten_vorher(auth_client):
    import auth
    antwort = auth_client.get('/api/auth/me').get_json()
    assert antwort['leerlauf_s'] == auth._leerlauf_s()
    assert 'const LEERLAUF_WARNUNG_MS = 5 * 60 * 1000;' in SKRIPT
    assert 'Angemeldet bleiben' in SEITE
