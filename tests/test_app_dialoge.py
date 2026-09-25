"""Die Oberfläche spricht Deutsch und bleibt im Design der App (Fund 0.9.1).

Die Windows-App ist WebView2: native Dialoge erschienen als Systemfenster
„127.0.0.1 sagt …“, und die Formularprüfung meldete „This field is
required.“ in der Sprache des Systems.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
SKRIPT = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
FORMULAR = (WURZEL / 'static' / 'formular.js').read_text(encoding='utf-8')


def test_keine_nativen_dialoge():
    aufrufe = re.findall(r'(?<![\w.])(?:window\.)?(confirm|prompt|alert)\(', SKRIPT)
    assert aufrufe == [], 'frage()/fragePassphrase() statt Browserdialog'


def test_rueckfrage_liegt_ueber_jedem_dialog():
    """Escape schließt das letzte offene Overlay im Dokument; die Rückfrage
    muss es sein, sonst schließt Escape den Dialog darunter."""
    overlays = re.findall(r'class="modal-overlay[^"]*" id="([\w-]+)"', SEITE)
    assert overlays[-1] == 'frage-modal', overlays[-3:]


def test_formularhinweise_deutsch():
    assert 'Bitte füllen Sie dieses Feld aus.' in FORMULAR
    assert "addEventListener('invalid'" in FORMULAR
    assert '<script src="/static/formular.js?v=' in SEITE


def _formular_fassung(seite: str) -> str:
    return re.search(r'<script src="/static/formular\.js\?v=(\w+)"></script>', seite).group(1)


def test_hinweis_bleibt_beim_tippen_deutsch():
    """Fund 0.9.1: Die offene Hinweisblase liest beim Tippen die Meldung neu.
    Nur leeren ließ sie auf den Systemtext springen („… using 2 characters“)."""
    eingabe = FORMULAR[FORMULAR.index("['input', 'change']"):]
    assert 'deutschPruefen(e.target)' in eingabe
    import inspect
    import sys
    sys.path.insert(0, str(WURZEL / 'scripts'))
    import rundgang
    quelle = inspect.getsource(rundgang.rundgang) + inspect.getsource(rundgang.Rundgang.bereich)
    assert '(bisher 2)' in quelle and 'TRENNLINIEN_JS' in quelle


def test_anmeldeseiten_laden_formularhinweise(anon_client):
    import auth
    # Anmeldung, Einrichtung und Passwort der Hülle bauen auf _seitenkopf auf.
    for seite in (auth.LOGIN_PAGE, auth.ERSTEINRICHTUNG_PAGE,
                  anon_client.get('/einrichtung').get_data(as_text=True)):
        # Dieselbe Fassung wie die App, sonst hält WebView2 die alte im Cache.
        assert _formular_fassung(seite) == _formular_fassung(SEITE)
    antwort = anon_client.get('/static/formular.js')
    assert antwort.status_code == 200
    antwort.close()


def test_historie_der_abrechnungen_abgesetzt_wie_bei_rechnungen():
    """Trennlinie und Abstand vor „Historie“, wie vor „Alle Rechnungen“."""
    kopf = SEITE[:SEITE.index('>Historie<')].rsplit('<div class="section-header', 1)[1]
    assert kopf.startswith(' section-header-getrennt section-header-weit"'), kopf[:60]


def test_loeschen_knopf_ist_sofort_rot():
    """Der Knopf wechselt die Klasse beim Öffnen; ohne Übergang kein violettes Aufblitzen."""
    stil = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')
    assert re.search(r'#frage-ja\s*\{\s*transition:\s*none;', stil)


def _css_fehler(text: str) -> list[str]:
    """Deklarationen außerhalb eines Blocks und überzählige Klammern.

    Der Browser liest ein verwaistes „padding-top: 24px; }“ als Teil des
    nächsten Selektors und verwirft damit die ganze folgende Regel.
    """
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    fehler, tiefe, vorspann = [], 0, ''
    for zeichen in text:
        if zeichen == '{':
            tiefe, vorspann = tiefe + 1, ''
        elif zeichen == '}':
            tiefe -= 1
            if tiefe < 0:
                fehler.append('überzählige }')
                tiefe = 0
            vorspann = ''
        elif tiefe == 0:
            if zeichen == ';' and not vorspann.strip().startswith('@'):
                fehler.append(vorspann.strip())
                vorspann = ''
            else:
                vorspann += zeichen
    return fehler + (['offene {'] if tiefe else [])


def test_css_ohne_verwaiste_deklarationen():
    """Fund 0.9.1: „.section-header-weit“ wirkte nie, die Historie klebte an der Karte."""
    assert _css_fehler('a { b: c; }\n    padding-top: 24px;\n}\n.x { y: z; }')
    for datei in sorted((WURZEL / 'static').glob('*.css')):
        assert _css_fehler(datei.read_text(encoding='utf-8')) == [], datei.name
