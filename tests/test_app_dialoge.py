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


def test_anmeldeseiten_laden_formularhinweise(anon_client):
    import auth
    # Anmeldung, Einrichtung und Passwort der Hülle bauen auf _seitenkopf auf.
    for seite in (auth.LOGIN_PAGE, auth.ERSTEINRICHTUNG_PAGE,
                  anon_client.get('/einrichtung').get_data(as_text=True)):
        assert '<script src="/static/formular.js"></script>' in seite
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
