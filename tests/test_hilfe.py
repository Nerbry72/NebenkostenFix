"""NK-158: Hilfe in der App (F-88).

Eine Quelle für die Erklärungen (Glossar § 8 → static/hilfe-begriffe.json),
ein „?“ an jedem Pflichtbegriff der Karte, keines ins Leere, die
Kurzanleitung als PDF und der Satz „Was bedeutet das für den Mieter?“.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
SKRIPT = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
JSON = WURZEL / 'static' / 'hilfe-begriffe.json'

_spec = importlib.util.spec_from_file_location(
    'hilfe_begriffe', WURZEL / 'scripts' / 'hilfe_begriffe.py')
erzeuger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(erzeuger)

PFLICHT = {'umlageschluessel', 'vorauszahlung', 'kostenprofil', 'sammelrechnung',
           'hauptzaehler', 'unterzaehler', 'umlagefaehig', 'abrechnungszeitraum'}


def test_json_folgt_dem_glossar():
    """Wer den Glossar ändert, lässt scripts/hilfe_begriffe.py laufen."""
    assert JSON.read_text(encoding='utf-8') == erzeuger.inhalt()


def test_jeder_pflichtbegriff_hat_ein_fragezeichen():
    genutzt = set(re.findall(r'class="begriff-hilfe"[^>]*data-begriff="([a-z]+)"', SEITE))
    bekannt = {b['schluessel'] for b in json.loads(JSON.read_text(encoding='utf-8'))}
    assert PFLICHT <= genutzt, sorted(PFLICHT - genutzt)
    assert genutzt <= bekannt, sorted(genutzt - bekannt)


def test_erklaerungen_sind_ein_gesiezter_satz():
    for eintrag in json.loads(JSON.read_text(encoding='utf-8')):
        satz = eintrag['satz']
        assert satz.endswith(('.', ').')), eintrag
        assert not re.search(r'\b(du|dich|dir|dein\w*)\b', satz, re.I), eintrag
        assert len(satz) < 260, eintrag


def test_kurzanleitung_als_pdf(auth_client):
    import hilfe
    antwort = auth_client.get('/api/hilfe/kurzanleitung.pdf')
    assert antwort.status_code == 200 and antwort.mimetype == 'application/pdf'
    assert antwort.data.startswith(b'%PDF-')
    seiten = len(re.findall(rb'/Type /Page[^s]', antwort.data))
    assert seiten == len(hilfe.KURZANLEITUNG) >= 10


def test_kurzanleitung_nennt_die_frist_und_keine_rechtsberatung():
    import hilfe
    text = ' '.join(' '.join(absaetze) for _, absaetze in hilfe.KURZANLEITUNG)
    assert '§ 556 Abs. 3 BGB' in text and 'Keine Rechtsberatung' in text


def test_hilfe_ist_ueberall_erreichbar():
    kopf = SEITE[SEITE.index('<div class="kopf-aktionen">'):SEITE.index('</header>')]
    assert 'zeigeHilfe()' in kopf
    assert 'id="tab-hilfe"' in SEITE and '/api/hilfe/kurzanleitung.pdf' in SEITE
    for abschnitt in ('hilfe-grundlagen', 'hilfe-sammeln', 'hilfe-begriffe'):
        assert f'id="{abschnitt}"' in SEITE


def test_vorschau_und_detail_erklaeren_das_ergebnis():
    assert SKRIPT.count('html += mieterErklaerungHtml(data);') == 2
    assert 'Was bedeutet das für den Mieter?' in SKRIPT


def test_kein_fachjargon_im_abrechnungskopf():
    assert 'Smarte Vorschläge' not in SEITE
