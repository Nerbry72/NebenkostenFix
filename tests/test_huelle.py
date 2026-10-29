"""NK-152: Oberfläche hüllenfest (F-81).

Fenster, Downloads und Druck laufen über die eine Hilfsfunktion ``huelle``
in static/app.js. Im Browser verhält sie sich wie bisher, in der Windows-App
nimmt sie die Brücke der Hülle. Der Wächter verbietet neue direkte Aufrufe.
"""

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
APP_JS = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
INDEX = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')


def _huelle_block():
    anfang = APP_JS.index('const huelle = {')
    ende = APP_JS.index('window.huelle = huelle;')
    return APP_JS[anfang:ende]


def _ohne_huelle():
    return APP_JS.replace(_huelle_block(), '')


def test_kein_direktes_window_open_ausserhalb_der_huelle():
    rest = re.sub(r'//.*', '', _ohne_huelle())
    assert 'window.open(' not in rest


def test_kein_blob_download_ausserhalb_der_huelle():
    rest = _ohne_huelle()
    assert 'URL.createObjectURL' not in rest
    assert not re.search(r'\.download\s*=', rest)


def test_drucken_nur_ueber_die_huelle():
    assert 'window.print' not in _ohne_huelle()
    assert 'window.print' not in INDEX
    assert INDEX.count('huelle.drucken()') == 2


def test_die_huelle_nutzt_die_bruecke_der_app():
    block = _huelle_block()
    for methode in ('speichern(', 'oeffnen(', 'ordner_waehlen('):
        assert f'window.pywebview.api.{methode}' in block


def test_links_mit_target_blank_gehen_in_der_app_an_die_huelle():
    assert "closest('a[target=\"_blank\"], a[download]')" in APP_JS


def test_ordnerwahl_nur_in_der_app_sichtbar():
    assert 'id="btn-sicherung-ordner" style="display: none;"' in INDEX
    assert "ordnerKnopf.style.display = huelle.kann('ordner_waehlen') ? '' : 'none'" in APP_JS


def test_die_huelle_gibt_die_pdf_seite_an_die_app_weiter():
    """Fund 0.9.2: fetch verwirft den Anker #page=N, die Brücke bekam nur die
    Datei. Die Hülle muss die Seite selbst mitgeben."""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('node fehlt')
    probe = '''
        let aufruf = null;
        const window = {pywebview: {api: {oeffnen: async (...a) => { aufruf = a; }}}};
        const fetch = async () => ({ok: true, headers: {get: () => 'inline; filename="r.pdf"'},
                                   blob: async () => null});
        const showError = m => { throw new Error(m); };
        const meldungZu = e => String(e);
        ''' + _huelle_block() + '''
        huelle._base64 = async () => 'QQ==';
        (async () => {
            const ergebnis = [];
            for (const adresse of ['http://h/api/dateien/rechnung/5#page=3', 'http://h/api/dateien/rechnung/5']) {
                await huelle.oeffnen(adresse);
                ergebnis.push(aufruf);
            }
            console.log(JSON.stringify(ergebnis));
        })();
    '''
    ausgabe = subprocess.run([node, '-e', probe], capture_output=True, text=True, timeout=30, check=True)
    mit, ohne = json.loads(ausgabe.stdout)
    assert mit == ['r.pdf', 'QQ==', 3]
    assert ohne == ['r.pdf', 'QQ==', None]


# --- #45: Servermodus ------------------------------------------------------

# Diese drei kann jede Brücke, auch die kleine im Servermodus.
_GRUNDMETHODEN = {'speichern', 'oeffnen', 'extern_oeffnen'}


def test_brueckenaufrufe_brauchen_kann():
    """Die Server-Brücke kennt nur speichern, oeffnen und extern_oeffnen. Jeder
    andere Aufruf muss vorher fragen, sonst wirft er im Servermodus."""
    for treffer in re.finditer(r'window\.pywebview\.api\.(\w+)\(', APP_JS):
        name = treffer.group(1)
        if name in _GRUNDMETHODEN:
            continue
        davor = APP_JS[max(0, treffer.start() - 400):treffer.start()]
        assert f"kann('{name}')" in davor, name


def test_verbindungskarte_nur_mit_server_verbinden():
    karte = INDEX.index('id="server-karte"')
    assert INDEX.index('id="umzug-karte"') > karte
    kopf = INDEX[INDEX.rindex('<div', 0, karte):INDEX.index('>', karte)]
    assert 'data-gruppe="sicherung"' in kopf
    assert 'style="display: none;"' in kopf
    assert "serverKarte.style.display = huelle.kann('server_verbinden') ? '' : 'none'" in APP_JS
    # Ohne den Haken bleibt der Knopf aus.
    knopf = INDEX[INDEX.index('id="btn-server-verbinden"'):]
    assert knopf[:knopf.index('>')].count('disabled') == 1
    # Konzept Abschnitt 7: „Verbinden“. „prüfen“ hieße Probelauf ohne Änderung (Glossar),
    # der Knopf schreibt aber die INI und startet neu.
    assert knopf[:knopf.index('</button>')].rstrip().endswith('> Verbinden')


def _node(probe):
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('node fehlt')
    ausgabe = subprocess.run([node, '-e', probe], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(ausgabe.stdout)


def test_kann_prueft_die_methode_der_bruecke():
    probe = '''
        let aufrufe = [];
        const window = {pywebview: {api: {
            oeffnen: async () => {}, speichern: async () => {}, extern_oeffnen: async () => {},
        }}};
        const showError = m => { throw new Error(m); };
        const meldungZu = e => String(e);
        ''' + _huelle_block() + '''
        (async () => {
            const klein = [huelle.aktiv(), huelle.kann('oeffnen'), huelle.kann('ordner_waehlen'),
                           await huelle.ordnerWaehlen(), await huelle.serverVerbinden('https://x')];
            window.pywebview.api.server_verbinden = async a => { aufrufe.push(a); return {ok: true}; };
            const gross = [huelle.kann('server_verbinden'), await huelle.serverVerbinden('https://x')];
            delete window.pywebview;
            const browser = [huelle.kann('oeffnen'), huelle.kann('server_verbinden')];
            console.log(JSON.stringify([klein, gross, browser, aufrufe]));
        })();
    '''
    klein, gross, browser, aufrufe = _node(probe)
    assert klein == [True, True, False, None, None]
    assert gross == [True, {'ok': True}]
    assert browser == [False, False]
    assert aufrufe == ['https://x']


def _funktion(name):
    anfang = APP_JS.index(f'function {name}(')
    ende = APP_JS.index('\n}\n', anfang) + 3
    return APP_JS[anfang:ende]


def test_leerzustand_zweite_aktion():
    probe = _funktion('leerzustand') + '''
        const basis = {icon: 'ph-x', titel: 'T', text: 'X',
                       aktion: {label: 'Eins', fn: 'a()', icon: 'ph-plus'}};
        console.log(JSON.stringify([
            leerzustand(basis),
            leerzustand({...basis, aktion2: {label: 'Zwei', fn: 'b()', icon: 'ph-plugs-connected'}}),
        ]));
    '''
    einfach, doppelt = _node(probe)
    assert einfach.count('<button') == 1 and 'btn-primary' in einfach and 'btn-secondary' not in einfach
    assert doppelt.count('<button') == 2
    assert 'class="btn-secondary" onclick="b()"' in doppelt
    assert doppelt.index('Eins') < doppelt.index('Zwei')
    assert "aktion2: huelle.kann('server_verbinden')" in APP_JS
