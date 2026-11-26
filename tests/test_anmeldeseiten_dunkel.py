"""Die Anmelde-, Einrichtungs- und Passwortseiten folgen der Darstellung wie die App.

Vorher blieben sie hell, auch wenn die App dunkel war: Der Seitenkopf in
``nebenkostenfix/auth.py`` lud weder das Skript aus ``static/index.html``, das die
Wahl aus ``nk-thema`` übernimmt, noch die Dunkel-Farben aus ``static/style.css``.
"""
import re
from pathlib import Path

from nebenkostenfix import auth

WURZEL = Path(__file__).resolve().parents[1]
INDEX = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
STIL = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')
ANMELDUNG = (WURZEL / 'static' / 'anmeldung.css').read_text(encoding='utf-8')
DUNKEL = ':root[data-theme="dark"]'


def _thema_skript_der_app() -> str:
    treffer = re.search(r'<script>\(function \(\) \{ var t = null;.*?\}\)\(\);</script>', INDEX)
    assert treffer, 'Das Theme-Skript in static/index.html fehlt oder hat sich geändert.'
    return treffer.group(0)


def _block(text: str, selektor: str) -> str | None:
    treffer = re.search(re.escape(selektor) + r'\s*\{(.*?)\}', text, re.S)
    return treffer.group(1) if treffer else None


def _variablen(block: str | None) -> dict:
    return dict(re.findall(r'(--[\w-]+):\s*([^;]+);', block or ''))


def test_seitenkopf_setzt_das_theme_vor_dem_ersten_bild():
    kopf = auth._seitenkopf('Anmeldung')
    skript = _thema_skript_der_app()
    assert skript in kopf
    assert kopf.index(skript) < kopf.index('</head>')


def test_anmeldung_hat_einen_dunkelblock_mit_den_farben_der_app():
    dunkel_app = _variablen(_block(STIL, DUNKEL))
    dunkel_anmeldung = _variablen(_block(ANMELDUNG, DUNKEL))
    assert dunkel_anmeldung, 'static/anmeldung.css hat keinen Dunkelblock.'
    hell = _variablen(_block(ANMELDUNG, ':root'))
    geprueft = 0
    for name in hell:
        if name in dunkel_app:
            geprueft += 1
            assert dunkel_anmeldung.get(name) == dunkel_app[name], name
    assert geprueft >= 10, 'Zu wenige gemeinsame Farben, der Vergleich greift nicht.'


def test_dunkelblock_setzt_color_scheme_wie_die_app():
    # Damit Eingabefelder, Autofill und Scrollleisten mitziehen. Die Anmeldeseiten
    # bestehen fast nur aus Feldern.
    for datei, text in (('style.css', STIL), ('anmeldung.css', ANMELDUNG)):
        assert re.search(r'color-scheme:\s*dark\s*;', _block(text, DUNKEL) or ''), datei


def test_dunkelblock_gilt_nur_am_bildschirm_wie_in_der_app():
    # Gedruckt wird immer hell. Gleich gebaut lassen sich beide Dateien vergleichen.
    im_bildschirm = r'@media screen\s*\{\s*(/\*.*?\*/\s*)*' + re.escape(DUNKEL)
    for datei, text in (('style.css', STIL), ('anmeldung.css', ANMELDUNG)):
        assert re.search(im_bildschirm, text, re.S), datei
        assert text.count(DUNKEL) == 1, datei
