"""PDF-Aufbau in der Oberfläche (Einstellungen → Abrechnung).

Der Server bietet das Layout der Abrechnungs-PDF unter
``/api/einstellungen/pdf-layout`` an (``nebenkostenfix/pdf_layout.py``:
GET/PUT/DELETE und POST …/vorschau). Diese Tests sichern die Oberfläche
dazu: Der Bereich wird ausgeliefert, die Aufrufe in ``static/app.js``
treffen Routen und Methoden des Servers, Serverdaten gehen nur als Text in
die Seite, und die Hülle öffnet die Vorschau-PDF in Browser und Windows-App.
Das Verhalten im Einzelnen (Verschieben, Ziehen, Pflicht, Ansage für
Bildschirmleser, Rückfrage bei ungespeicherten Änderungen, Fehlermeldungen
und Ladefehler) prüft der Rauchtest ``scripts/rauchtest_design.js``
(``pdfLayoutPruefen``).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
APP_JS = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
INDEX = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
RUNDGANG = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')

PDF_FUNKTIONEN = ('pdfLayoutAusAntwort', 'pdfLayoutZiehen', 'pdfLayoutTitel',
                  'pdfLayoutHinweisZeigen', 'ladePdfLayout', 'pdfLayoutHinweisLaden',
                  'pdfLayoutKnopf', 'pdfLayoutZeile', 'pdfLayoutZeichnen', 'pdfLayoutSchieben',
                  'pdfLayoutDaten', 'pdfLayoutSpeichern', 'pdfLayoutStandard', 'pdfLayoutVorschau',
                  'pdfLayoutGeaendert', 'pdfLayoutVerlassen', 'pdfLayoutVorDemVerlassen')


@pytest.fixture
def eigener_ordner(monkeypatch, tmp_path):
    from nebenkostenfix import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    return tmp_path


def _funktion(name: str) -> str:
    treffer = re.search(r'(?:async )?function ' + name + r'\([^)]*\) \{[\s\S]*?\n\}', APP_JS)
    assert treffer, name
    return treffer.group(0)


def _huelle_block() -> str:
    return APP_JS[APP_JS.index('const huelle = {'):APP_JS.index('window.huelle = huelle;')]


def test_der_bereich_wird_ausgeliefert(auth_client):
    seite = auth_client.get('/')
    assert seite.status_code == 200
    html = seite.get_data(as_text=True)
    assert re.search(r'data-gruppe="abrechnung"\s+onclick="zeigeEinstellungsgruppe\(\'abrechnung\'\)"', html)
    assert '<div data-gruppe="abrechnung" class="dashboard-card glass-panel" id="pdf-layout-karte">' in html
    for kennung in ('pdf-layout-liste', 'pdf-layout-girocode', 'btn-pdf-layout-vorschau',
                    'pdf-layout-eigen', 'billing-pdf-layout-hinweis'):
        assert f'id="{kennung}"' in html, kennung
    for knopf in ('pdfLayoutSpeichern()">Speichern', 'Vorschau ansehen</button>',
                  'pdfLayoutStandard()">Aufbau zurücksetzen'):
        assert knopf in html, knopf
    skript = auth_client.get('/static/app.js')
    assert skript.status_code == 200
    assert 'async function ladePdfLayout()' in skript.get_data(as_text=True)


def test_der_hinweis_steht_im_dialog_abrechnung_erstellen_und_ist_zunaechst_zu():
    dialog = INDEX[INDEX.index('id="billing-selection-modal"'):INDEX.index('id="billing-selection-body"')]
    assert 'id="billing-pdf-layout-hinweis" role="status" hidden' in dialog
    assert 'Eigenes PDF-Layout aktiv' in dialog
    assert 'pdfLayoutHinweisLaden();' in _funktion('openBillingSelectionModal')
    assert 'id="pdf-layout-eigen" role="status" hidden>Eigenes PDF-Layout aktiv<' in INDEX


def test_der_knopf_heisst_aufbau_zuruecksetzen_wie_im_glossar():
    """Glossar § 6: „zurücksetzen“ stellt einen Zustand zurück und fragt nach,
    „wiederherstellen“ holt eine gesicherte Eingabe zurück. Der Knopf und
    seine Rückfrage nehmen deshalb „zurücksetzen“."""
    glossar = (WURZEL / 'docs' / 'glossar.md').read_text(encoding='utf-8')
    assert '| **zurücksetzen** |' in glossar
    karte = INDEX[INDEX.index('id="pdf-layout-karte"'):INDEX.index('<!-- NK-127 (E-1)')]
    assert '<button class="btn-secondary" type="button" onclick="pdfLayoutStandard()">Aufbau zurücksetzen</button>' in karte
    assert 'wiederherstellen' not in karte
    rumpf = _funktion('pdfLayoutStandard')
    # Die Rückfrage verwirft den eigenen Aufbau: roter Knopf wie bei anderen
    # zerstörenden Rückfragen (gefahr=true).
    assert "'Aufbau zurücksetzen', true, 'Aufbau zurücksetzen?'" in rumpf
    assert 'wiederherstellen' not in rumpf and 'wiederhergestellt' not in rumpf


def test_der_hinweis_steht_auch_im_dialog_abrechnung_frei_erstellen():
    dialog = INDEX[INDEX.index('id="billing-frei-modal"'):INDEX.index('id="frei-mieter"')]
    assert 'id="frei-pdf-layout-hinweis" role="status" hidden' in dialog
    assert 'Eigenes PDF-Layout aktiv' in dialog
    assert 'pdfLayoutHinweisLaden();' in _funktion('openFreieAbrechnung')
    assert "'frei-pdf-layout-hinweis'" in _funktion('pdfLayoutHinweisZeigen')


def test_ungespeicherte_aenderungen_gehen_beim_gruppenwechsel_nicht_still_verloren():
    """Wer die Gruppe „Abrechnung“ mit ungespeichertem Aufbau verlässt, wird
    gefragt; ladePdfLayout überschreibt ungespeicherte Änderungen nie. Das
    Verhalten im Einzelnen prüft der Rauchtest."""
    gruppe = _funktion('zeigeEinstellungsgruppe')
    assert "if (gruppe !== 'abrechnung' && pdfLayoutGeaendert()) {" in gruppe
    assert 'pdfLayoutVerlassen(gruppe);' in gruppe
    verlassen = _funktion('pdfLayoutVerlassen')
    assert 'await frage(' in verlassen
    laden = _funktion('ladePdfLayout')
    assert laden.index('if (pdfLayoutGeaendert())') < laden.index('fetch(PDF_LAYOUT_ADRESSE)')


def test_pflichtmarke_und_ansage_fuer_bildschirmleser():
    karte = INDEX[INDEX.index('id="pdf-layout-karte"'):INDEX.index('<!-- NK-127 (E-1)')]
    assert '<span id="pdf-layout-pflicht-text">' in karte
    assert '<p class="sr-only" id="pdf-layout-ansage" aria-live="polite"></p>' in karte
    zeile = _funktion('pdfLayoutZeile')
    assert "haken.setAttribute('aria-describedby'" in zeile and 'pdf-layout-pflicht-text' in zeile
    # Die Marke ist reiner Text und kein Bedienelement; eine Beschreibung an ihr
    # liest kein Bildschirmleser vor. Sie hängt nur am Kästchen.
    assert "marke.setAttribute('aria-describedby'" not in zeile
    assert "document.getElementById('pdf-layout-ansage').textContent" in _funktion('pdfLayoutSchieben')


def test_ein_ladefehler_steht_in_der_karte():
    karte = INDEX[INDEX.index('id="pdf-layout-karte"'):INDEX.index('<!-- NK-127 (E-1)')]
    assert 'id="pdf-layout-ladefehler" role="alert" hidden' in karte
    assert '<p class="karten-text" id="pdf-layout-ladefehler-text">' in karte
    laden = _funktion('ladePdfLayout')
    assert "'pdf-layout-ladefehler'" in laden
    assert "document.getElementById('pdf-layout-ladefehler-text').textContent" in laden


def test_ein_ladefehler_wird_nur_einmal_angesagt():
    """Die Karte sagt den Ladefehler per role="alert" an. Eine zweite Meldung
    unten rechts (ebenfalls role="alert") ließe den Bildschirmleser denselben
    Fehler zweimal vorlesen; der Text steht deshalb nur in der Karte."""
    laden = _funktion('ladePdfLayout')
    assert 'showError(' not in laden
    assert 'PDF_LAYOUT_SERVERFEHLER' in laden
    konstante = re.search(r"const PDF_LAYOUT_SERVERFEHLER = '([^']+)';", APP_JS)
    assert konstante and 'Server' in konstante.group(1)


def test_ungespeicherter_aufbau_fragt_beim_verlassen_der_seite():
    """Neuladen oder Schließen der Seite verwirft ungespeicherte Änderungen am
    PDF-Aufbau sonst still. Der Browser fragt dann selbst nach; ohne Änderung
    bleibt er still. Das Verhalten prüft der Rauchtest."""
    rumpf = _funktion('pdfLayoutVorDemVerlassen')
    assert 'pdfLayoutGeaendert()' in rumpf and 'preventDefault()' in rumpf
    assert "window.addEventListener('beforeunload', pdfLayoutVorDemVerlassen);" in APP_JS


def test_die_serverkarte_wartet_auf_die_rueckfrage_zum_pdf_aufbau():
    """Mit ungespeichertem Aufbau fragt der Gruppenwechsel erst nach. Der Weg zur
    Serverkarte darf bis zur Antwort weder scrollen noch den Fokus in die noch
    verborgene Gruppe „Sicherung“ legen. Das Verhalten prüft der Rauchtest."""
    assert 'return pdfLayoutVerlassen(gruppe);' in _funktion('zeigeEinstellungsgruppe')
    assert 'return zeigeEinstellungsgruppe(gruppe);' in _funktion('pdfLayoutVerlassen')
    karte = _funktion('zeigeServerKarte')
    assert 'instanceof Promise' in karte and 'focus({ preventScroll: true })' in karte


def test_die_gruppe_abrechnung_ist_bekannt_und_laedt_den_aufbau():
    gruppen = re.search(r'const EINSTELLUNGS_GRUPPEN = \[([^\]]*)\]', APP_JS).group(1)
    assert "'abrechnung'" in gruppen
    assert "if (gruppe === 'abrechnung') ladePdfLayout();" in _funktion('zeigeEinstellungsgruppe')
    assert "'abrechnung'" in re.search(r'EINSTELLUNGS_GRUPPEN = \[([^\]]*)\]', RUNDGANG).group(1)


def _routen(app) -> dict[str, set[str]]:
    routen: dict[str, set[str]] = {}
    for regel in app.url_map.iter_rules():
        routen.setdefault(regel.rule, set()).update(regel.methods or ())
    return routen


def test_die_aufrufe_der_oberflaeche_treffen_routen_des_servers(auth_client):
    adresse = re.search(r"const PDF_LAYOUT_ADRESSE = '([^']+)';", APP_JS).group(1)
    routen = _routen(auth_client.application)
    erwartet = {
        'ladePdfLayout': (adresse, 'GET'),
        'pdfLayoutHinweisLaden': (adresse, 'GET'),
        'pdfLayoutSpeichern': (adresse, 'PUT'),
        'pdfLayoutStandard': (adresse, 'DELETE'),
        'pdfLayoutVorschau': (adresse + '/vorschau', 'POST'),
    }
    for name, (ziel, methode) in erwartet.items():
        rumpf = _funktion(name)
        if methode == 'GET':
            assert 'fetch(PDF_LAYOUT_ADRESSE)' in rumpf, name
        elif ziel.endswith('/vorschau'):
            assert "fetch(PDF_LAYOUT_ADRESSE + '/vorschau', {" in rumpf, name
            assert f"method: '{methode}'" in rumpf, name
        else:
            assert 'fetch(PDF_LAYOUT_ADRESSE, {' in rumpf or 'fetch(PDF_LAYOUT_ADRESSE, { method' in rumpf, name
            assert f"method: '{methode}'" in rumpf, name
        assert methode in routen.get(ziel, set()), (name, ziel, methode)


def test_die_oberflaeche_schickt_das_format_das_der_server_prueft(auth_client, eigener_ordner):
    """pdfLayoutDaten baut {bloecke: [{block, an}], girocode}; der Server
    nimmt genau das an und antwortet mit den Feldern, die pdfLayoutAusAntwort liest."""
    rumpf = _funktion('pdfLayoutDaten')
    assert 'bloecke: pdfLayoutStand.bloecke.map(e => ({ block: e.block, an: e.an }))' in rumpf
    assert 'girocode: pdfLayoutStand.girocode' in rumpf
    daten = auth_client.get('/api/einstellungen/pdf-layout').get_json()
    gelesen = _funktion('pdfLayoutAusAntwort')
    for feld in ('daten.bloecke', 'daten.girocode_orte', 'daten.layout.bloecke',
                 'daten.layout.girocode', 'daten.ist_standard'):
        assert feld in gelesen, feld
    assert {'layout', 'bloecke', 'girocode_orte', 'ist_standard'} <= set(daten)
    assert {'block', 'titel', 'pflicht', 'fest'} <= set(daten['bloecke'][0])
    assert {'ort', 'titel'} <= set(daten['girocode_orte'][0])
    eigen = dict(daten['layout'])
    eigen['bloecke'] = [{'block': e['block'], 'an': e['block'] != 'belegliste'}
                        for e in daten['layout']['bloecke']]
    antwort = auth_client.put('/api/einstellungen/pdf-layout', json=eigen)
    assert antwort.status_code == 200
    assert antwort.get_json()['ist_standard'] is False


def test_die_belegliste_ist_kein_pflichtblock(auth_client, eigener_ordner):
    bloecke = {b['block']: b for b in auth_client.get('/api/einstellungen/pdf-layout').get_json()['bloecke']}
    assert bloecke['belegliste']['pflicht'] is False
    assert bloecke['deckblatt']['pflicht'] is True and bloecke['deckblatt']['fest'] is True


def test_serverdaten_gehen_nur_als_text_in_die_seite():
    for name in PDF_FUNKTIONEN:
        rumpf = _funktion(name)
        assert 'innerHTML' not in rumpf, name
        assert 'insertAdjacentHTML' not in rumpf, name
        assert 'outerHTML' not in rumpf, name
    assert "zeile.querySelector('.pdf-layout-titel').textContent = titel;" in _funktion('pdfLayoutZeile')
    assert 'option.textContent = o.titel;' in _funktion('pdfLayoutZeichnen')


def test_die_pfeile_sind_per_tastatur_bedienbar():
    zeile = _funktion('pdfLayoutZeile')
    assert '`${titel} nach oben schieben`' in zeile
    assert '`${titel} nach unten schieben`' in zeile
    knopf = _funktion('pdfLayoutKnopf')
    assert "knopf.setAttribute('aria-label', beschriftung);" in knopf
    vorlage = INDEX[INDEX.index('<template id="pdf-layout-vorlage">'):]
    vorlage = vorlage[:vorlage.index('</template>')]
    assert vorlage.count('<button type="button" class="btn-icon pdf-layout-') == 2
    assert '<input type="checkbox" class="pdf-layout-haken">' in vorlage


def _node_huelle(probe: str) -> list:
    node = shutil.which('node')
    if not node:
        pytest.skip('node fehlt')
    ausgabe = subprocess.run([node, '-e', probe], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(ausgabe.stdout)


def test_die_huelle_gibt_die_vorschau_in_der_app_an_die_bruecke():
    probe = '''
        let aufruf = null;
        const window = {pywebview: {api: {oeffnen: async (...a) => { aufruf = a; }}}};
        const fetch = null, showError = null, meldungZu = null, serverFehler = null;
        ''' + _huelle_block() + '''
        huelle._base64 = async () => 'QQ==';
        huelle.blobOeffnen({}, 'Layout-Vorschau.pdf').then(() => console.log(JSON.stringify(aufruf)));
    '''
    assert _node_huelle(probe) == ['Layout-Vorschau.pdf', 'QQ==', None]


def test_die_huelle_speichert_die_vorschau_wenn_der_browser_das_fenster_blockiert():
    probe = '''
        const ergebnis = [];
        const window = {open: (a, z) => { ergebnis.push(['open', a, z]); return null; }};
        const URL = {createObjectURL: () => 'blob:probe', revokeObjectURL: a => ergebnis.push(['frei', a])};
        const fetch = null, showError = null, meldungZu = null, serverFehler = null;
        ''' + _huelle_block() + '''
        huelle.blobSpeichern = async (blob, name) => { ergebnis.push(['speichern', name]); };
        huelle.blobOeffnen({}, 'Layout-Vorschau.pdf').then(() => console.log(JSON.stringify(ergebnis)));
    '''
    assert _node_huelle(probe) == [['open', 'blob:probe', '_blank'], ['frei', 'blob:probe'],
                                   ['speichern', 'Layout-Vorschau.pdf']]
