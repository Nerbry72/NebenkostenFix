"""Die Karte „Zugriffsschlüssel“ in Einstellungen → Konto.

Der Server legt den Schlüssel an und nennt ihn genau einmal. Die Oberfläche
muss ihn in diesem einen Moment zeigen, kopierbar, und danach nicht mehr:
die Liste kennt nur die ersten Zeichen. Im offenen Modus gibt es keine
Konten und damit keine Schlüssel, die Karte verschwindet wie die
Kontoliste (NK-201).

Muster wie ``tests/test_review_frontend.py``: der echte Funktionsrumpf aus
``app.js`` läuft in node gegen ein Mini-DOM.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')

braucht_node = pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')


def _funktionsrumpf(name: str) -> str:
    treffer = re.search(rf'^(async )?function {name}\(', QUELLE, re.M)
    assert treffer, f'function {name} fehlt in app.js'
    return QUELLE[treffer.start():QUELLE.index('\n}', treffer.start()) + 2]


def _konstante(name: str) -> str:
    beginn = QUELLE.index(f'const {name} =')
    return QUELLE[beginn:QUELLE.index('\n', beginn) + 1]


def _node(code: str):
    lauf = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=30,
                          check=False)
    assert lauf.returncode == 0, lauf.stderr
    return json.loads(lauf.stdout.strip().splitlines()[-1])


# Ein Mini-DOM: jedes Element ist ein Objekt mit value, innerHTML, hidden.
DOM = '''
const elemente = {};
const document = { getElementById: (k) => (elemente[k] = elemente[k] || {
    id: k, value: '', innerHTML: '', hidden: false, textContent: '',
    style: {}, select() { this.markiert = true; }, focus() { document.aktiv = k; } }) };
const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const serverFehler = async (r) => new Error(r.fehler || 'fehler');
const meldungZu = (e, t) => t;
const meldungen = [];
const showError = (t) => meldungen.push(['fehler', t]);
const showSuccess = (t) => meldungen.push(['ok', t]);
'''


def test_die_seite_hat_die_karte():
    assert 'id="zugriffsschluessel-karte"' in SEITE
    karte = SEITE[SEITE.index('id="zugriffsschluessel-karte"'):]
    karte = karte[:karte.index('<!-- NK-175')]
    for kennung in ('zugriffsschluessel-zeilen', 'zugriffsschluessel-name',
                    'zugriffsschluessel-umfang', 'zugriffsschluessel-neu',
                    'zugriffsschluessel-wert'):
        assert f'id="{kennung}"' in karte, kennung
    assert 'value="lesen"' in karte and 'value="erfassen"' in karte
    # Die Überschrift folgt dem Glossar (Review zu #48). Wer „API-Key“
    # sucht, findet die Karte über das Handbuch.
    assert '<h3>Zugriffsschlüssel</h3>' in karte
    handbuch = (WURZEL / 'docs' / 'handbuch' / 'handbuch.md').read_text(encoding='utf-8')
    assert '**Zugriffsschlüssel** (englisch API-Key)' in handbuch
    # Der Schlüssel erscheint nur einmal, darum keine Spalte mit seinen
    # ersten Zeichen.
    assert 'Beginnt mit' not in karte
    # Der Datenschutzhinweis steht vor dem Anlegen, nicht in der Hilfe.
    assert 'Anbieter' in karte
    # Die Box mit dem neuen Schlüssel ist anfangs zu.
    box = re.search(r'<div[^>]*id="zugriffsschluessel-neu"[^>]*>', karte).group(0)
    assert 'hidden' in box


def test_handbuch_warnt_vor_alten_sicherungen():
    """Review zu #48: Die Schlüssel stehen in der Datenbank. Eine ältere
    Sicherung bringt also auch Schlüssel zurück, die danach gelöscht wurden."""
    handbuch = ' '.join((WURZEL / 'docs' / 'handbuch' / 'handbuch.md')
                        .read_text(encoding='utf-8').split())
    absatz = handbuch[handbuch.index('**Zugriffsschlüssel** (englisch API-Key)'):]
    absatz = absatz[:absatz.index('- **Updates**')]
    assert 'ältere Sicherung' in absatz and 'danach gelöscht' in absatz


def test_der_offene_modus_blendet_die_karte_aus():
    rumpf = _funktionsrumpf('zeigeAngemeldetenBenutzer')
    liste = rumpf[rumpf.index("['angemeldeterBenutzer'"):]
    liste = liste[:liste.index(']') + 1]
    assert "'zugriffsschluessel-karte'" in liste


@pytest.mark.parametrize('weg', ['initApp', 'initTabs'])
def test_beide_ladewege_laden_auch_die_schluessel(weg):
    assert 'ladeZugriffsschluessel();' in _funktionsrumpf(weg)


@braucht_node
def test_anlegen_zeigt_den_schluessel_genau_einmal():
    code = DOM + _funktionsrumpf('zugriffsschluesselAnlegen') + '''
let geladen = 0; const ladeZugriffsschluessel = () => { geladen++; };
const gesendet = [];
const fetch = async (pfad, opt) => { gesendet.push([pfad, opt.method, JSON.parse(opt.body)]);
    return { ok: true, json: async () => ({ id: 3, name: 'MCP', umfang: 'lesen',
        anzeige: 'nkf_AbCdEfGh', schluessel: 'nkf_AbCdEfGh-geheim' }) }; };
document.getElementById('zugriffsschluessel-name').value = '  MCP  ';
document.getElementById('zugriffsschluessel-umfang').value = 'lesen';
document.getElementById('zugriffsschluessel-neu').hidden = true;
zugriffsschluesselAnlegen().then(() => console.log(JSON.stringify({
    gesendet, geladen,
    wert: elemente['zugriffsschluessel-wert'].value,
    offen: !elemente['zugriffsschluessel-neu'].hidden,
    name: elemente['zugriffsschluessel-name'].value })));
'''
    erg = _node(code)
    assert erg['gesendet'] == [['/api/zugriffsschluessel', 'POST', {'name': 'MCP', 'umfang': 'lesen'}]]
    assert erg['wert'] == 'nkf_AbCdEfGh-geheim'
    assert erg['offen'] is True
    assert erg['name'] == ''
    assert erg['geladen'] == 1


@braucht_node
def test_nach_dem_anlegen_steht_der_fokus_auf_dem_schluessel():
    """Review zu #48: Ohne Ansage und mit dem Fokus auf dem Knopf merkte ein
    Screenreader nicht, dass der nur einmal gezeigte Schlüssel dasteht."""
    code = DOM + _funktionsrumpf('zugriffsschluesselAnlegen') + '''
const ladeZugriffsschluessel = () => {};
const fetch = async () => ({ ok: true, json: async () => ({ schluessel: 'nkf_AbCdEfGh-geheim' }) });
document.getElementById('zugriffsschluessel-name').value = 'MCP';
zugriffsschluesselAnlegen().then(() => console.log(JSON.stringify({
    meldungen, aktiv: document.aktiv,
    markiert: !!elemente['zugriffsschluessel-wert'].markiert })));
'''
    erg = _node(code)
    assert erg['meldungen'] == [['ok', 'Zugriffsschlüssel angelegt. Er wird nur dieses eine Mal angezeigt.']]
    assert erg['aktiv'] == 'zugriffsschluessel-wert'
    assert erg['markiert'] is True


@braucht_node
def test_ohne_namen_wird_nichts_geschickt():
    code = DOM + _funktionsrumpf('zugriffsschluesselAnlegen') + '''
const ladeZugriffsschluessel = () => {};
let abrufe = 0; const fetch = async () => { abrufe++; return { ok: true, json: async () => ({}) }; };
document.getElementById('zugriffsschluessel-name').value = '   ';
zugriffsschluesselAnlegen().then(() => console.log(JSON.stringify({ abrufe, meldungen })));
'''
    erg = _node(code)
    assert erg['abrufe'] == 0
    assert erg['meldungen'][0][0] == 'fehler'


@braucht_node
def test_ausblenden_vergisst_den_schluessel():
    code = DOM + _funktionsrumpf('zugriffsschluesselAusblenden') + '''
document.getElementById('zugriffsschluessel-wert').value = 'nkf_geheim';
zugriffsschluesselAusblenden();
console.log(JSON.stringify({ wert: elemente['zugriffsschluessel-wert'].value,
    zu: elemente['zugriffsschluessel-neu'].hidden }));
'''
    assert _node(code) == {'wert': '', 'zu': True}


@braucht_node
def test_die_liste_maskiert_namen_und_zeigt_keinen_schluessel():
    code = DOM + _konstante('UMFANG_TEXT') + _funktionsrumpf('ladeZugriffsschluessel') + '''
const fetch = async () => ({ ok: true, json: async () => [
    { id: 1, name: '<b>Skript</b>', umfang: 'erfassen', anzeige: 'nkf_AbCdEfGh',  // Altlast darf nicht erscheinen
      konto: 'vermieter', angelegt_am: '01.10.2026 10:00', zuletzt_benutzt: null }] });
ladeZugriffsschluessel().then(() => console.log(JSON.stringify({
    html: elemente['zugriffsschluessel-zeilen'].innerHTML })));
'''
    html = _node(code)['html']
    assert '&lt;b&gt;Skript&lt;/b&gt;' in html
    assert '<b>' not in html
    assert 'nkf_' not in html
    assert 'Lesen und erfassen' in html
    assert 'nie' in html
    assert 'zugriffsschluesselWiderrufen(1)' in html


@braucht_node
def test_ohne_schluessel_steht_ein_leerzustand_statt_nur_des_kopfs():
    """Wie bei Kostenarten und Sicherungen: eine graue Zeile über alle
    Spalten, damit die Tabelle nicht nur aus ihrem Kopf besteht."""
    code = DOM + _konstante('UMFANG_TEXT') + _funktionsrumpf('ladeZugriffsschluessel') + '''
const fetch = async () => ({ ok: true, json: async () => [] });
ladeZugriffsschluessel().then(() => console.log(JSON.stringify({
    html: elemente['zugriffsschluessel-zeilen'].innerHTML })));
'''
    html = _node(code)['html']
    assert 'colspan="5"' in html
    assert 'Noch kein Zugriffsschlüssel angelegt' in html


def test_die_gruppe_konto_laedt_die_schluessel_neu():
    """Wie die Kostenarten: wer die Gruppe öffnet, sieht den neuen Stand."""
    rumpf = _funktionsrumpf('zeigeEinstellungsgruppe')
    assert "if (gruppe === 'konto') ladeZugriffsschluessel();" in rumpf


def test_zurueck_im_fenster_frischt_die_liste_auf():
    """Den Schlüssel probiert man im Terminal oder im Assistenten aus und
    kommt zurück. Dann soll „zuletzt benutzt“ ohne Neuladen stimmen."""
    assert "window.addEventListener('focus', zugriffsschluesselAuffrischen);" in QUELLE


@braucht_node
@pytest.mark.parametrize('sichtbar, geladen', [(True, 1), (False, 0)])
def test_auffrischen_nur_wenn_die_karte_zu_sehen_ist(sichtbar, geladen):
    code = DOM + _funktionsrumpf('zugriffsschluesselAuffrischen') + f'''
let geladen = 0; const ladeZugriffsschluessel = () => {{ geladen++; }};
document.getElementById('zugriffsschluessel-karte').offsetParent = {'{}' if sichtbar else 'null'};
zugriffsschluesselAuffrischen();
console.log(JSON.stringify({{ geladen }}));
'''
    assert _node(code) == {'geladen': geladen}


def test_der_datenschutzhinweis_steht_im_warnkasten_der_gefahrenzone():
    """Dass ein KI-Assistent alles sieht, soll man nicht überlesen: roter
    Kasten mit Warnzeichen, dieselben Gefahrentöne wie die Gefahrenzone."""
    karte = SEITE[SEITE.index('id="zugriffsschluessel-karte"'):]
    karte = karte[:karte.index('<!-- NK-175')]
    kasten = karte[karte.index('class="warnkasten"'):]
    kasten = kasten[:kasten.index('</div>')]
    assert 'ph-warning-circle' in kasten
    assert 'Achtung' in kasten
    for wort in ('Anbieter', 'lokalen Modell', 'Mieter'):
        assert wort in kasten, wort
    # Der Kasten steht vor dem Anlegen, nicht dahinter.
    assert karte.index('class="warnkasten"') < karte.index('id="zugriffsschluessel-name"')

    css = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')
    regel = css[css.index('.warnkasten {'):]
    regel = regel[:regel.index('}')]
    assert 'var(--danger-bg)' in regel and 'var(--danger-color)' in regel
    assert '.warnkasten h4' in css
