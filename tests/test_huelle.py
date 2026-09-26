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
    assert "ordnerKnopf.style.display = huelle.aktiv() ? '' : 'none'" in APP_JS


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
