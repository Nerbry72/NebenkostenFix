"""Befunde aus dem Review vor 0.15.0, je einer mit Test.

* Immobilienfilter: schneller Wechsel ließ die ältere Auswahl gewinnen.
* Zahlungen von heute fehlten in der Summe (Datum als UTC-Mitternacht).
* Anmeldung: zweiter Klick während des Wischens schickte zweimal ab,
  der Einflug blieb nach Fehlschlag vorgemerkt.
* Knopf mit doppeltem class-Attribut, Rahmen in Hintergrundfarbe,
  unmaskierter Spaltentitel, Datumsangaben ohne datumText.
* Die PDF-Vorschau lud vor dem ersten Bild alle Seiten.
* Die PDF-Tabellen nutzten Hex-Werte statt der Farbkonstanten.

*Hätte die Befunde gefunden:* jeder Test hier (gegen den Stand davor rot).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
STIL = (WURZEL / 'static' / 'style.css').read_text(encoding='utf-8')
FORMULAR = (WURZEL / 'static' / 'formular.js').read_text(encoding='utf-8')

braucht_node = pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')


def _funktionsrumpf(name: str) -> str:
    treffer = re.search(rf'^(async )?function {name}\(', QUELLE, re.M)
    assert treffer, f'function {name} fehlt in app.js'
    return QUELLE[treffer.start():QUELLE.index('\n}', treffer.start()) + 2]


def _konstante(name: str) -> str:
    beginn = QUELLE.index(f'const {name} =')
    return QUELLE[beginn:QUELLE.index('\n', beginn) + 1]


def _node(code: str, tz: str | None = None):
    umgebung = dict(os.environ, TZ=tz) if tz else None
    lauf = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=30,
                          env=umgebung, check=False)
    assert lauf.returncode == 0, lauf.stderr
    return json.loads(lauf.stdout.strip().splitlines()[-1])


@braucht_node
def test_datenqualitaet_zeigt_prozentprofile_mit_satz_und_farbe():
    farben = QUELLE[QUELLE.index('const DIAGRAMM_FARBE ='):]
    farben = farben[:farben.index('\n};') + 3]
    code = farben + r'''
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.textContent = ''; }
    appendChild(child) { this.children.push(child); }
    replaceChildren() { this.children = []; }
}
const grid = new Element('grid');
const document = {
    getElementById: () => grid,
    createElement: tag => new Element(tag),
    createTextNode: text => Object.assign(new Element('text'), {textContent: text})
};
const tenants = [{id: 1, name: 'Mieter', apartment_id: 1, move_in_date: '2025-01-01'}];
const allApartments = [{id: 1, property_id: 1}];
const fetch = async url => ({json: async () => url === '/api/categories'
    ? [{id: 1, name: 'Müll'}, {id: 2, name: 'Steuer'}, {id: 3, name: 'Entfällt'}, {id: 4, name: 'Null'}]
    : {1: {billing_type: 'prozent', percentage: '30.25'}, 2: 'qm',
       3: {billing_type: 'ignoriert'}, 4: {billing_type: 'prozent', percentage: '0.00'}}});
''' + _funktionsrumpf('renderTenantOverview') + r'''
renderTenantOverview(1).then(() => {
    const alle = element => [element, ...element.children.flatMap(alle)];
    const pillen = alle(grid).filter(e => e.tag === 'span' && e.textContent.includes(':'));
    console.log(JSON.stringify(pillen.map(e => ({text: e.textContent, style: e.style.cssText}))));
});
'''
    pillen = _node(code)
    assert [p['text'] for p in pillen] == [
        'Müll: nach Prozentsatz · 30,25 %', 'Steuer: nach m²', 'Null: nach Prozentsatz · 0 %']
    assert '#2E7D6B' in pillen[0]['style']


@braucht_node
def test_hausfilter_schneller_wechsel_letzte_wahl_gewinnt():
    """Haus 1 antwortet langsam, Haus 2 schnell: am Ende gilt Haus 2."""
    code = (
        'let hausFilter = null; let hausFilterLauf = 0; let properties = [];\n'
        'const gespeichert = []; const localStorage = { setItem: (k, v) => gespeichert.push(v) };\n'
        'const gehoertZumHaus = (x, f) => x.property_id === f.id;\n'
        'const serverFehler = async () => new Error(); const meldungZu = (e, t) => t; const showError = () => {};\n'
        'const propertyDetailsView = { style: { display: "none" } };\n'
        'const document = { querySelector: () => null }; const fetchAnalytics = () => {};\n'
        'let geladen = 0; const ladeHausListen = async () => { geladen++; };\n'
        'const daten = [{ id: 1, property_id: 1 }, { id: 2, property_id: 2 }];\n'
        'let abrufe = 0;\n'
        'const fetch = () => { const ms = abrufe++ < 3 ? 60 : 5;\n'
        '  return new Promise(r => setTimeout(() => r({ ok: true, json: async () => daten }), ms)); };\n'
        + _funktionsrumpf('imHaus') + '\n' + _funktionsrumpf('hausFilterSetzen') + '\n'
        + '(async () => { await Promise.all([hausFilterSetzen(1), hausFilterSetzen(2)]);\n'
        '  console.log(JSON.stringify({ id: hausFilter.id, gespeichert, wohnungen: [...hausFilter.wohnungen] })); })();'
    )
    ergebnis = _node(code)
    assert ergebnis['id'] == 2
    assert ergebnis['gespeichert'] == ['2']
    assert ergebnis['wohnungen'] == [2]


@braucht_node
@pytest.mark.parametrize('datum, erwartet', [
    ('2026-10-15', False),            # heute zählt mit
    ('2026-10-15T23:30:00', False),
    ('2026-10-14', False),
    ('2026-10-16', True),
    ('', False),
])
def test_zahlung_von_heute_ist_nicht_in_der_zukunft(datum, erwartet):
    """Kurz nach Mitternacht in Berlin ist es in UTC noch gestern."""
    code = (
        'const Echt = Date;\n'
        'Date = class extends Echt { constructor(...a) { super(...(a.length ? a : [Echt.UTC(2026, 9, 14, 22, 30)])); } };\n'
        + _konstante('nachHeute')
        + f'console.log(JSON.stringify(nachHeute({json.dumps(datum)})));'
    )
    assert _node(code, tz='Europe/Berlin') is erwartet


def test_zahlungsfenster_rechnet_mit_ortsdatum():
    rumpf = _funktionsrumpf('openPaymentDetailsModal')
    assert rumpf.count('nachHeute(p.payment_date)') == 2
    assert 'new Date(p.payment_date)' not in rumpf


@braucht_node
def test_anmeldung_schickt_nur_einmal_ab_und_vergisst_einflug_nach_fehlschlag():
    code = r'''
const h = {}; const an = (t, f) => (h[t] = h[t] || []).push(f);
const klassen = new Set();
let karte = true;
const document = { addEventListener: an, body: { classList: {
    add: k => klassen.add(k), remove: k => klassen.delete(k), contains: k => klassen.has(k) } },
    querySelector: () => (karte ? {} : null) };
const window = { addEventListener: (t, f) => an('w' + t, f) };
const speicher = new Map();
const sessionStorage = { setItem: (k, v) => speicher.set(k, v), removeItem: k => speicher.delete(k) };
const matchMedia = () => ({ matches: false });
const uhr = []; const setTimeout = f => uhr.push(f);
let abgeschickt = 0;
const ereignis = () => ({ target: form, submitter: null, defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; } });
const feuern = (t, e) => (h[t] || []).forEach(f => f(e));
const form = { classList: { contains: k => k === 'anmelde-karte' },
    requestSubmit() { const e = ereignis(); feuern('submit', e); if (!e.defaultPrevented) abgeschickt++; } };
''' + FORMULAR + r'''
const erster = ereignis(); feuern('submit', erster);
const zweiter = ereignis(); feuern('submit', zweiter);
if (!zweiter.defaultPrevented) abgeschickt++;   // der Browser schickte nativ ab
uhr.forEach(f => f());
const vorgemerkt = speicher.has('nk-einflug');
feuern('wpageshow', {});
console.log(JSON.stringify({ abgeschickt, vorgemerkt, nachFehlschlag: speicher.has('nk-einflug') }));
'''
    ergebnis = _node(code)
    assert ergebnis['abgeschickt'] == 1
    assert ergebnis['vorgemerkt'] is True
    assert ergebnis['nachFehlschlag'] is False


def test_kein_element_mit_zwei_class_attributen():
    doppelt = re.compile(r'<[a-zA-Z][^<>]*?\sclass="[^"]*"[^<>]*?\sclass="')
    for name, text in (('app.js', QUELLE), ('index.html', SEITE)):
        treffer = doppelt.search(text)
        assert treffer is None, f'{name}: {treffer.group(0)[:120]}'


def test_belege_haengen_immer_an_einer_immobilie():
    """gehoertZumHaus zeigt Einträge ohne Immobilie immer; bei Belegen kommt
    das nicht vor, deshalb zählt die Kachel „Belege“ auf Heute ohne Sonderfall."""
    from nebenkostenfix.models import InvoiceDocument
    assert InvoiceDocument.__table__.c.property_id.nullable is False


def test_rahmen_heben_sich_vom_hintergrund_ab():
    for token in ('--success-border', '--warning-border'):
        assert STIL.count(f'{token}:') == 2, token   # hell und dunkel
    for alt in ("rand: 'var(--success-bg)'", "pfBorder = 'var(--success-bg)'",
                "pfBorder = 'var(--warning-bg)'", "border = '1px solid var(--success-bg)'",
                'border: 1px solid var(--warning-bg)'):
        assert alt not in QUELLE, alt


@braucht_node
def test_spaltentitel_wird_maskiert():
    code = (_funktionsrumpf('escapeHtml') + _funktionsrumpf('sortierKopf')
            + 'console.log(JSON.stringify(sortierKopf(\'<b>"x"</b>\', "text")));')
    kopf = _node(code)
    assert '<b>' not in kopf and '"x"' not in kopf


def test_datumsangaben_ohne_utc_verschiebung():
    for alt in ('new Date(inv.start_date)', 'new Date(inv.end_date)',
                'new Date(m.last_reading_date)', 'new Date(z.bis)'):
        assert alt not in QUELLE, alt


def test_pdf_vorschau_laedt_vorab_nur_die_erste_seite():
    rumpf = _funktionsrumpf('zeichnePdf')
    vorab = rumpf[:rumpf.index('const zeichnen =')]
    assert re.findall(r'getPage\([^)]*\)', vorab) == ['getPage(1)']
    assert 'getPage(i + 1)' in rumpf[rumpf.index('const zeichnen ='):]


def test_pdf_tabellen_nutzen_farbkonstanten():
    quelle = (WURZEL / 'nebenkostenfix' / 'pdf_generator.py').read_text(encoding='utf-8')
    assert "HexColor('#" not in quelle
