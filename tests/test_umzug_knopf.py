"""Der Knopf „Paket auswählen“ (Einrichtung und Einstellungen) im Verhalten.

Im Browser öffnet er das versteckte Dateifeld, in der Desktop-App den Dialog
der Hülle. Eine neue Datei verwirft den Pfad, ein neuer Pfad hat Vorrang vor
der Datei: Es gilt immer genau eine Quelle. Node-Proben mit DOM-Ersatz.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
UMZUG_JS = (WURZEL / 'static' / 'umzug.js').read_text(encoding='utf-8')
APP_JS = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')

# Elemente mit Klickzähler, Ereignissen und einem Dateifeld, dessen files
# beim Leeren von value nicht verschwinden: So zeigt die Probe, dass der Pfad
# auch dann Vorrang hat.
_DOM = '''
    const elemente = {};
    function el(id) {
        if (!elemente[id]) elemente[id] = {
            id, value: '', files: [], textContent: '', hidden: false, className: '',
            disabled: false, klicks: 0, horcher: {},
            click() { this.klicks++; },
            focus() {},
            addEventListener(art, fn) { this.horcher[art] = fn; },
            querySelector() { return el('umzug-absenden'); },
        };
        return elemente[id];
    }
    const document = {readyState: 'complete', getElementById: el};
    const window = {};
    let dialogPfad = 'C:\\\\Pakete\\\\alt.nkfix';
    const hulle = {paket_waehlen: async () => dialogPfad};
    const quellen = [];
'''


def _node(probe):
    node = shutil.which('node')
    if not node:
        pytest.skip('node fehlt')
    ausgabe = subprocess.run([node, '-e', probe], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(ausgabe.stdout)


def _funktion(name):
    anfang = APP_JS.index(f'async function {name}(') if f'async function {name}(' in APP_JS \
        else APP_JS.index(f'function {name}(')
    return APP_JS[anfang:APP_JS.index('\n}\n', anfang) + 3]


def test_einrichtung_knopf_browser_und_desktop():
    probe = _DOM + UMZUG_JS + '''
        const p = window.umzugPaket;
        p.hochladen = async () => 'kennung-1';
        p.uebernehmen = async q => { quellen.push(q); return {zeilen: 1, belege: 0}; };
        const knopf = el('umzug-auswahl-knopf'), datei = el('umzug-datei'), name = el('umzug-auswahl-name');
        const senden = () => el('umzug-form').horcher.submit({preventDefault() {}});
        (async () => {
            const schritte = [];
            await knopf.horcher.click();                       // Browser: Dateifeld
            datei.files = [{name: 'neu.nkfix'}];
            datei.horcher.change();
            schritte.push([datei.klicks, name.textContent]);
            await senden();
            window.pywebview = {api: hulle};                    // Desktop: Dialog der Hülle
            await knopf.horcher.click();
            schritte.push([datei.klicks, name.textContent, datei.value]);
            await senden();                                     // Pfad vor Datei
            datei.horcher.change();                             // neue Datei verwirft den Pfad
            schritte.push(name.textContent);
            await senden();
            console.log(JSON.stringify([schritte, quellen]));
        })();
    '''
    schritte, quellen = _node(probe)
    assert schritte == [[1, 'neu.nkfix'], [1, 'C:\\Pakete\\alt.nkfix', ''], 'neu.nkfix']
    assert quellen == [{'hochgeladen': 'kennung-1'}, {'pfad': 'C:\\Pakete\\alt.nkfix'},
                       {'hochgeladen': 'kennung-1'}]


def test_einstellungen_knopf_browser_und_desktop():
    probe = _DOM + '''
        const setTimeout = () => {};
        const showError = m => { throw new Error(m); };
        const meldungZu = e => String(e);
        const umzugHinweis = m => new Error(m);
        let umzugPfad = null;
        window.umzugPaket = {
            desktop: () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.paket_waehlen),
            desktopWaehlen: () => window.pywebview.api.paket_waehlen(),
            hochladen: async () => 'kennung-2',
            pruefen: async () => ({einspielbar: true}),
            uebernehmen: async q => { quellen.push(q); return {zeilen: 1, belege: 0}; },
            anzahl: n => String(n), lesbar: n => String(n),
        };
        ''' + _funktion('umzugPaketWaehlen') + _funktion('umzugDateiGewaehlt') + _funktion('umzugUebernehmen') + '''
        el('umzug-bestaetigung').value = 'ERSETZEN';
        const datei = el('umzug-datei-einstellungen'), name = el('umzug-auswahl-einstellungen');
        (async () => {
            const schritte = [];
            await umzugPaketWaehlen();                          // Browser: Dateifeld
            datei.files = [{name: 'neu.nkfix'}];
            umzugDateiGewaehlt(datei);
            schritte.push([datei.klicks, name.textContent]);
            await umzugUebernehmen();
            window.pywebview = {api: hulle};                    // Desktop: Dialog der Hülle
            await umzugPaketWaehlen();
            schritte.push([datei.klicks, name.textContent, datei.value]);
            await umzugUebernehmen();                           // Pfad vor Datei
            umzugDateiGewaehlt(datei);                          // neue Datei verwirft den Pfad
            schritte.push(name.textContent);
            await umzugUebernehmen();
            console.log(JSON.stringify([schritte, quellen]));
        })();
    '''
    schritte, quellen = _node(probe)
    assert schritte == [[1, 'neu.nkfix'], [1, 'C:\\Pakete\\alt.nkfix', ''], 'neu.nkfix']
    assert quellen == [{'hochgeladen': 'kennung-2'}, {'pfad': 'C:\\Pakete\\alt.nkfix'},
                       {'hochgeladen': 'kennung-2'}]
