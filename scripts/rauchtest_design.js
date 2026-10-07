// ---------------------------------------------------------------------------
// DOM-Rauchtest fuer die Design-System-Aenderungen (NK-067, Phase 5)
//
// Geprueft wird ohne Browser, mit minimalen DOM-Stubs:
//  1. Die Palette DIAGRAMM_FARBE existiert und wird fuer Diagramme genutzt.
//  2. Der Auswahlpillen-Handler setzt den Zustand nur ueber die Klasse
//     .active, nicht mehr ueber Inline-Styles (sonst uebermalt er die CSS-
//     Regel .filter-pill.active).
//  3. Die neuen Klassen (.filter-pill, .gefahrenzone, .btn-gefahr, .btn-tint)
//     sind im Stylesheet definiert.
//  4. Die Zustandstoene --success-bg/--danger-bg/--warning-bg existieren.
//
// Seit der Design-Nacharbeit (NK-099 … NK-104, D-62) fängt der Rauchtest
// zusaetzlich JEDE Befundursache der Vorher-Analyse einzeln — die
// Landkarte von Befund zu Wächter:
//
//   B1  riesiges Icon im Leerzustands-Knopf   → „B1: die .empty-state i-Regel…“
//   B2  Primärknopf nicht zentriert          → „Sockel: …inline-flex…“ (K3)
//   B3  Leerzustand klebt in der ersten Rasterzelle → „B3: …grid-column…“
//   B4  Leerzustände handgeschrieben         → „K4: keine …Kopie mehr…“
//   B5  Primärknopf wandert, zwei übereinander → „K2/K1: …Primärknopf…“
//   B6  Knöpfe rechts angeschnitten          → „B6: .main-content darf schrumpfen…“
//   B7  Erste-Schritte-Regeln greifen nicht  → „B7: die Liste trägt ihre Klasse…“
//   B8  „fünf Schritte“ gegen sechs; Pille im Titel → „B8: …“ (zwei Wächter)
//   B9  Fremdblau und Rückfallgrün           → „B9: …“ (zwei Wächter)
//   B10 Knöpfe verschieden hoch               → „Knopfsockel bündelt…“ + Messrundgang
// ---------------------------------------------------------------------------
const fs = require('fs');
const path = require('path');

let fehler = 0;
function pruefe(name, bedingung) {
    console.log((bedingung ? 'ok   ' : 'FEHL ') + name);
    if (!bedingung) fehler++;
}

// --- 1+2: app.js laden mit minimalem window/document ---
const appQuelle = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');

const elemente = [];
function erzeugeElement() {
    const klassen = new Set();
    const el = {
        classList: {
            add: (...n) => n.forEach(x => klassen.add(x)),
            remove: (...n) => n.forEach(x => klassen.delete(x)),
            contains: n => klassen.has(n),
        },
        style: {},
        innerHTML: '',
        label: '',
        addEventListener() {},
        appendChild() {},
        replaceChildren() {},
        insertAdjacentHTML() {},
        querySelectorAll() { return []; },
        querySelector() { return null; },
        classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
        cloneNode() { return erzeugeElement(); },
        getContext() { return {}; },
    };
    elemente.push(el);
    return el;
}

global.window = { fetch: () => Promise.resolve({ ok: true }), addEventListener() {}, querySelectorAll: () => [], querySelector: () => null };
// Wie im Browser: app.js steht am Ende von <body>, beim Ausführen ist das
// Dokument noch 'loading', initApp läuft erst nach DOMContentLoaded, also
// nachdem die ganze Datei ausgewertet ist (sonst greift initApp auf
// Konstanten weiter unten zu, die noch nicht initialisiert sind).
const domBereit = [];
global.document = {
    readyState: 'loading',
    getElementById: () => erzeugeElement(),
    createElement: () => erzeugeElement(),
    addEventListener(typ, fn) { if (typ === 'DOMContentLoaded') domBereit.push(fn); },
    querySelectorAll: () => [],
    querySelector: () => null,
    body: erzeugeElement(),
    documentElement: { style: {} },
};
global.Chart = class {
    constructor() {}
    destroy() {}
};
global.escapeHtml = s => String(s);
// initApp ruft beim Laden alle Listen ab. Seit der Rauchtest am Ende auf
// asynchrone Prüfungen wartet (NK-118), liefen diese Abrufe sonst gegen das
// echte fetch von Node; so bleiben sie still hängen.
global.fetch = () => new Promise(() => {});
global.alert = () => {};
// app.js beobachtet Dialoge und Listen mit MutationObserver (Fokusfalle,
// Hilfe-Knöpfe). Ohne Browser reicht ein Beobachter, der nichts meldet.
global.MutationObserver = class {
    observe() {}
    disconnect() {}
};

try {
    new Function(appQuelle).call(global.window);
    domBereit.forEach(fn => fn());
    pruefe('app.js laesst sich ohne Browser ausfuehren', domBereit.length === 1);
} catch (e) {
    pruefe('app.js laesst sich ohne Browser ausfuehren — ' + e.message, false);
}

const quelle = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
pruefe('DIAGRAMM_FARBE ist definiert (eine Stelle fuer Kategorienfarben)',
    /const DIAGRAMM_FARBE = \{/.test(quelle));
pruefe('Pillen-Handler setzt Inline-Styles nicht mehr',
    !/e\.target\.style\.background = '#3B82F6'/.test(quelle));
pruefe('Kein Pflicht-Style mehr an den Pills (Zustand nur ueber Klasse)',
    !/p\.style\.background = 'white'/.test(quelle));

// --- 3+4: Stylesheet ---
const css = fs.readFileSync(path.join(__dirname, '..', 'static', 'style.css'), 'utf8');
for (const klasse of ['.filter-pill', '.gefahrenzone', '.btn-gefahr', '.btn-tint']) {
    pruefe(`Stylesheet definiert ${klasse}`, css.includes(klasse));
}
for (const ton of ['--success-bg', '--danger-bg', '--warning-bg']) {
    pruefe(`Stylesheet definiert ${ton}`, css.includes(ton + ':'));
}

// --- 5: Zähler-Dialog bietet jede Kostenart an (NK-105, D-63) -------------
// Fehlermeldung: „Beim Zähler-Anlegen gibt es nur die Kategorie
// Wasserversorgung.“ Ursache war der requires_meter-Filter im Dialog. Der
// Wächter ruft openAddMeterModal mit dem echten Katalog auf und zählt die
// Optionen: 18 Stück (NK-117: Nr. 3 zweimal), jede Bezeichnung genau einmal.
// Am Zähler steht der Alltagsname (F-113): „Strom“ statt „Beleuchtung
// (Allgemeinstrom)“. Die Zuordnung kommt aus app.js selbst.
function katalog_aus_quelle() {
    const betrkvQuelle = fs.readFileSync(path.join(__dirname, '..', 'nebenkostenfix', 'betrkv.py'), 'utf8');
    const zeilen = [];
    const muster = /\{'nr': (\d+), 'name': '([^']+)', 'verteilung': '(\w+)', 'zaehler': (True|False)\}/g;
    let treffer;
    while ((treffer = muster.exec(betrkvQuelle)) !== null) {
        zeilen.push({
            nr: parseInt(treffer[1], 10),
            name: treffer[2],
            verteilung: treffer[3],
        });
    }
    return zeilen;
}

const katalog = katalog_aus_quelle();
const anzeigeQuelle = (appQuelle.match(/const ZAEHLER_ANZEIGENAMEN = [^\n]*\n/) || [''])[0]
    + (appQuelle.match(/function zaehlerArtName\(name\) \{[\s\S]*?\n\}\n/) || [''])[0];
const anzeigeName = new Function(anzeigeQuelle + 'return typeof zaehlerArtName === "function" ? zaehlerArtName : n => n;')();
const dialogNamen = katalog.map(k => anzeigeName(k.name));
pruefe('BetrKV-Katalog gelesen (18 Kostenarten, NK-117)', katalog.length === 18);

const dialogFehler = (() => {
    try {
        const fnMatch = appQuelle.match(/function openAddMeterModal\(\) \{[\s\S]*?\n\}/);
        if (!fnMatch) return 'openAddMeterModal nicht gefunden';
        if (!anzeigeQuelle) return 'zaehlerArtName nicht gefunden';

        const kategorien = katalog.map((k, i) => ({
            id: i + 1,
            name: k.name,
            allocation_method: k.verteilung,
            betrkv_nr: k.nr,
            requires_meter: k.verteilung === 'METER_READING' && k.nr === 2,
        }));

        const auswahl = {
            kinder: [],
            replaceChildren() { this.kinder = []; },
            appendChild(k) { this.kinder.push(k); },
        };
        const dokument = {
            getElementById(id) {
                if (id === 'meter-category') return auswahl;
                return erzeugeElement();
            },
            createElement(tag) { return { tag, label: '', innerHTML: '' }; },
        };
        new Function('categories', 'properties', 'document', anzeigeQuelle + fnMatch[0] + '; openAddMeterModal();')(
            kategorien, [], dokument);

        // Optionen aus den Gruppen ziehen — innerHTML der optgroups bleibt
        // beim Stub uninterpretiert, die <option>-Texte werden gezogen.
        const namen = [];
        for (const kind of auswahl.kinder) {
            for (const m of kind.innerHTML.matchAll(/<option[^>]*>([^<]+)<\/option>/g)) {
                namen.push(m[1]);
            }
        }
        if (namen.length !== katalog.length) {
            return `erwartet ${katalog.length} Optionen, gefunden ${namen.length}`;
        }
        for (const name of dialogNamen) {
            const n = namen.filter(n => n === name).length;
            if (n !== 1) return `„${name}“ ${n}mal in der Auswahl`;
        }
        const gruppen = auswahl.kinder.map(k => k.label);
        if (!gruppen.includes('Üblich mit Zähler') || !gruppen.includes('Weitere Kostenarten')) {
            return `Gruppen fehlen: ${gruppen.join(', ')}`;
        }
        return null;
    } catch (e) {
        return e.message;
    }
})();
pruefe('Zähler-Dialog bietet alle 18 Kostenarten, jede genau einmal (NK-105)',
    dialogFehler === null);
if (dialogFehler) console.error('   ' + dialogFehler);
for (const muss of ['Strom', 'Heizung']) {
    pruefe(`Zähler-Dialog nennt „${muss}“`, dialogNamen.includes(muss)
        && dialogFehler === null);
}

// --- 6: Bezeichnungsfeld der Rechnung bei Nr. 17 (NK-113) -----------------
// Befund aus dem Live-Abgleich: das Feld wurde über den Namen „sonstiges“
// gesucht und blieb seit dem Katalog verborgen. Der Wächter ruft
// toggleInvoiceDescription für jede Kostenart auf: sichtbar genau bei Nr. 17.
const beschreibungFehler = (() => {
    try {
        const fnMatch = appQuelle.match(/function toggleInvoiceDescription\(\) \{[\s\S]*?\n\}/);
        if (!fnMatch) return 'toggleInvoiceDescription nicht gefunden';
        const nrMatch = appQuelle.match(/const BETRKV_NR_SONSTIGE = (\d+);/);
        if (!nrMatch) return 'BETRKV_NR_SONSTIGE nicht gefunden';
        const kategorien = katalog.map((k, i) => ({ id: i + 1, name: k.name, betrkv_nr: k.nr }));
        const sichtbar = [];
        for (const k of kategorien) {
            const gruppe = { style: { display: 'none' } };
            const dokument = {
                getElementById(id) {
                    if (id === 'invoice-category') return { value: String(k.id) };
                    if (id === 'group-invoice-description') return gruppe;
                    return null;
                },
            };
            new Function('categories', 'document', nrMatch[0] + fnMatch[0] + '; toggleInvoiceDescription();')(
                kategorien, dokument);
            if (gruppe.style.display === 'block') sichtbar.push(k.betrkv_nr);
        }
        if (sichtbar.length !== 1 || sichtbar[0] !== 17) {
            return `sichtbar bei Nr. [${sichtbar.join(', ')}], erwartet [17]`;
        }
        return null;
    } catch (e) {
        return e.message;
    }
})();
pruefe('Rechnungsdialog zeigt die Bezeichnung genau bei Nr. 17 (NK-113)',
    beschreibungFehler === null);
if (beschreibungFehler) console.error('   ' + beschreibungFehler);

// --- 7: Abrechnungszeitraum frei wählbar (NK-119) --------------------------
// Befund der Oberflächenlücke aus dem Live-Abgleich: der Dialog nahm den
// Zeitraum stumm aus den Kategorien. Der Wächter spielt den Dialog mit
// Stubs durch: Vorbelegung, Folgen der Auswahl, Handeingabe, Prüfung.
const zeitraumFehler = (() => {
    try {
        const teil = name => {
            const m = appQuelle.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`));
            if (!m) throw new Error(`${name} nicht gefunden`);
            return m[0];
        };
        const felder = {
            'billing-period-start': { value: '' },
            'billing-period-end': { value: '' },
            'btn-proceed-preview': {},
            'billing-selection-modal': { classList: { add() {}, remove() {} } },
        };
        const kaestchen = [{ value: '1', checked: true }, { value: '2', checked: true }];
        felder['billing-selection-body'] = {
            innerHTML: '',
            querySelectorAll: () => kaestchen,
        };
        const dokument = {
            getElementById: id => felder[id],
            querySelectorAll: () => kaestchen.filter(k => k.checked),
        };
        const meldungen = [];
        const aufrufe = [];
        const oeffnen = new Function('document', 'showError', 'generateBillPreview', 'escapeHtml',
            // Der Servervorschlag (NK-186) braucht fetch; hier zählt nur die Vorbelegung.
            'zeitraumVorschlagen',
            'let currentBillingSelection = null;\n'
            + [teil('vorgeschlagenerZeitraum'), teil('pruefeAbrechnungszeitraum'),
               teil('openBillingSelectionModal')].join('\n')
            + '\nreturn openBillingSelectionModal;')(
            dokument, m => meldungen.push(m), (...a) => aufrufe.push(a), s => String(s), () => {});
        oeffnen({
            tenant_id: 7,
            categories: [
                { category_id: 1, category_name: 'A', suggested_start: '2024-01-01', suggested_end: '2024-12-31', invoice_count: 1 },
                { category_id: 2, category_name: 'B', suggested_start: '2023-07-01', suggested_end: '2024-06-30', invoice_count: 1 },
            ],
        });
        const beginn = felder['billing-period-start'];
        const ende = felder['billing-period-end'];
        if (beginn.value !== '2023-07-01' || ende.value !== '2024-12-31') {
            return `Vorbelegung ${beginn.value}–${ende.value}, erwartet 2023-07-01–2024-12-31`;
        }
        kaestchen[1].checked = false;
        kaestchen[1].onchange();
        if (beginn.value !== '2024-01-01') return `folgt der Auswahl nicht: ${beginn.value}`;
        beginn.value = '2024-03-15';
        beginn.oninput();
        kaestchen[1].checked = true;
        kaestchen[1].onchange();
        if (beginn.value !== '2024-03-15') return 'überschreibt die Handeingabe';
        ende.value = '2024-03-14';
        felder['btn-proceed-preview'].onclick();
        if (aufrufe.length || !meldungen.some(m => m.includes('nach seinem Ende'))) {
            return 'Beginn nach Ende nicht abgewiesen';
        }
        ende.value = '';
        felder['btn-proceed-preview'].onclick();
        if (aufrufe.length || !meldungen.some(m => m.includes('Beginn und Ende'))) {
            return 'leeres Ende nicht abgewiesen';
        }
        ende.value = '2024-09-30';
        felder['btn-proceed-preview'].onclick();
        const erwartet = JSON.stringify([7, '2024-03-15', '2024-09-30', [1, 2]]);
        if (JSON.stringify(aufrufe[0]) !== erwartet) {
            return `Vorschau mit ${JSON.stringify(aufrufe[0])}, erwartet ${erwartet}`;
        }
        return null;
    } catch (e) {
        return e.message;
    }
})();
pruefe('NK-119: Zeitraum vorbelegt, folgt der Auswahl, Handeingabe gilt, Beginn ≤ Ende geprüft'
    + (zeitraumFehler ? ' — ' + zeitraumFehler : ''), !zeitraumFehler);

// --- index.html nutzt die Klassen ---
const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'index.html'), 'utf8');
pruefe('Gefahrenzone traegt die Klasse statt Inline-Farben',
    html.includes('dashboard-card glass-panel gefahrenzone'));
pruefe('Datenbank-Knopf ist .btn-gefahr', html.includes('class="btn-gefahr"'));
pruefe('Detailliertes PDF ist .btn-tint', html.includes('btn-secondary btn-tint'));
// Zwölf Pillen: Rechnungen (Liste/Zeitleiste), Einstellungen (fünf Gruppen),
// Statistik (fünf Filter); dieselbe Zahl sichert test_ui_konsistenz.py.
pruefe('Zwölf Auswahlpillen, keine mit Inline-Stil',
    (html.match(/class="filter-pill/g) || []).length === 12
    && !/class="filter-pill[^"]*"[^>]*style=/.test(html));
pruefe('Cache-Buster erhoeht (style.css)', /style\.css\?v=\d+/.test(html));
pruefe('Cache-Buster erhoeht (app.js)', /app\.js\?v=\d+/.test(html));

// --- NK-100: Knopfsockel (K3) und Raster (K6) im Stylesheet ---
const sockel = /\.btn-primary,\s*\n\.btn-secondary,\s*\n\.btn-tint,\s*\n\.btn-gefahr\s*\{/;
pruefe('Knopfsockel bündelt alle vier Klassen (K3)', sockel.test(css));
pruefe('Sockel: feste Höhe aus dem Token (K3)',
    css.includes('height: var(--knopf-hoehe);')
    && css.includes('padding: 0 var(--space-5);'));
pruefe('Sockel: Icon-Regel mit Kindselektor (K3)',
    /\.btn-primary > i,\s*\n\.btn-secondary > i,\s*\n\.btn-tint > i,\s*\n\.btn-gefahr > i\s*\{/.test(css));
pruefe('Raster-Tokens definiert (K6)',
    css.includes('--space-1: 4px;') && css.includes('--space-7: 48px;')
    && css.includes('--knopf-hoehe: 44px;')
    && css.includes('--knopf-hoehe-klein: 32px;')
    && css.includes('--primary-tint: rgba(79, 70, 229, 0.08);'));
pruefe('B9: fremdes Blau aus dem Stylesheet vertrieben',
    !css.includes('rgba(37, 99, 235'));
pruefe('B9: Haken-Grün ohne Rückfallliteral',
    !css.includes('var(--success-color, #16a34a)'));
pruefe('B6: .main-content darf schrumpfen (min-width: 0)',
    /\.main-content\s*\{[^}]*min-width:\s*0/m.test(css));

// --- NK-101: Seitenkopf-Kanon (K1, K2) ---
// Kommentare sind kein UI: erst entfernen, dann zählen.
const ui = html.replace(/<!--[\s\S]*?-->/g, '');
const kopfBis = ui.indexOf('</header>');
pruefe('K2: der globale Kopf trägt keinen Primärknopf',
    ui.slice(0, kopfBis).indexOf('btn-primary') === -1);
pruefe('K2: „Immobilie anlegen“ genau einmal in der Seite',
    (ui.match(/Immobilie anlegen/g) || []).length === 1);
pruefe('K1: Immobilien-Seitenkopf trägt den Primärknopf',
    ui.indexOf('Immobilie anlegen') > ui.indexOf('id="tab-properties"'));
pruefe('K1: .kopf-aktionen in allen acht Köpfen mit Knöpfen (global + sieben Bereiche)',
    (ui.match(/class="kopf-aktionen"/g) || []).length === 8
    && css.includes('.kopf-aktionen {'));
pruefe('K1: .section-untertitel statt Inline-Stil (fünf Köpfe)',
    (ui.match(/class="section-untertitel"/g) || []).length === 5
    && !ui.includes('color: var(--text-muted); margin-top: 4px;"')
    && css.includes('.section-untertitel {'));
pruefe('K1: auch die Übersicht beginnt mit einem Seitenkopf',
    html.indexOf('id="tab-dashboard"') < html.indexOf('<h2>Übersicht</h2>')
    && html.indexOf('<h2>Übersicht</h2>') < html.indexOf('id="erste-schritte"'));

// --- NK-102: Leerzustand als eine Komponente (K4) ---
const app = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
pruefe('K4: der Erzeuger leerzustand() existiert genau einmal',
    (app.match(/function leerzustand\(/g) || []).length === 1);
pruefe('K4: keine handgeschriebene empty-state-Kopie mehr',
    (app.match(/className = ['"]empty-state/g) || []).length === 0
    && (app.match(/class="empty-state"/g) || []).length === 0);
pruefe('K4: der Knopf im Leerzustand ist immer primär',
    !/leerzustand\([\s\S]{0,400}?btn-secondary/.test(app)
    && app.includes("label: 'Immobilien öffnen'"));
pruefe('B1: die .empty-state i-Regel ist weg, das Icon hat eine Klasse',
    !css.includes('.empty-state i {')
    && css.includes('.leer-icon {')
    && app.includes('leer-icon"'));
pruefe('B3: der Leerzustand füllt das Raster über alle Spalten',
    css.includes('grid-column: 1 / -1;'));
pruefe('K4: leere Rechnungsliste blendet die Filterleiste aus',
    html.includes('id="invoice-filter"')
    && app.includes("leiste.hidden = invoices.length === 0;")
    && css.includes('.controls-bar[hidden]'));

// --- NK-103: Erste Schritte neu gesetzt (K5) ---
pruefe('B7: die Liste trägt ihre Klasse — die Regeln greifen',
    html.includes('id="erste-schritte-liste" class="erste-schritte-liste"'));
// NK-159 hat „vorher ausprobieren“ als zweiten optionalen Schritt ergänzt.
pruefe('B8: der Kopf nennt fünf Pflicht- und zwei optionale Schritte',
    html.includes('Fünf Schritte bis zur ersten Abrechnung, dazu zwei optionale:'));
pruefe('K5: Fortschritt „x von 5 erledigt“ mit Balken',
    html.includes('id="erste-schritte-stand"')
    && html.includes('id="erste-schritte-balken"')
    && app.includes('`${erledigtPflicht} von 5 erledigt`'));
pruefe('K5: Zeilenraster 32px | 1fr | auto, mindestens 64 px hoch',
    css.includes('grid-template-columns: 32px 1fr auto;')
    && css.includes('min-height: 64px;')
    && css.includes('.erste-schritte-liste .schritt + .schritt {'));
pruefe('K5: der aktuelle Schritt trägt die 3-px-Primärleiste',
    /\.erste-schritte-liste \.schritt\.aktuell\s*\{[^}]*inset 3px 0 0 var\(--primary\)/m.test(css));
pruefe('K5: bei ≤ 720 px rutscht der Knopf unter den Text, auch der Zweitknopf (NK-223)',
    /\.erste-schritte-liste \.schritt \.btn-primary,\s*\.erste-schritte-liste \.schritt \.btn-secondary\s*\{[^}]*grid-column: 2;/m.test(css));
pruefe('B8: die Pille „optional“ steht hinter dem Titel, auf der Grundlinie',
    app.includes('<div class="schritt-titel-zeile"><strong>${s.titel}</strong>${hinweis}</div>')
    && css.includes('.schritt-titel-zeile {'));

// --- NK-118: Haushaltsgröße im Mieterdialog ---------------------------------
// Befund aus dem Live-Abgleich: die Oberfläche bot keinen Weg zur
// Haushaltsgröße. Der Wächter ruft loadHouseholdSizes und saveHouseholdSize
// mit gestubbtem fetch auf: Leerzeile mit der Vorgabe, eine Zeile je
// Stichtag mit Löschknopf, 0 Personen gehen nicht hinaus, POST mit Körper.
async function haushaltPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`async function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const quelltext = funktion('loadHouseholdSizes') + funktion('saveHouseholdSize')
        + funktion('deleteHouseholdSize');
    const lauf = (felder, antworten) => {
        const aufrufe = [];
        const meldungen = [];
        const liste = {
            zeilen: [],
            replaceChildren() { this.zeilen = []; },
            appendChild(z) { this.zeilen.push(z); },
        };
        const knoten = tag => ({
            tag, style: {}, kinder: [], textContent: '',
            appendChild(k) { this.kinder.push(k); },
        });
        const dokument = {
            getElementById(id) {
                if (id === 'household-list') return liste;
                if (!(id in felder)) felder[id] = { value: '' };
                return felder[id];
            },
            createElement: knoten,
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            const daten = antworten.shift() ?? [];
            return Promise.resolve({ ok: true, json: () => Promise.resolve(daten) });
        };
        const fns = new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu', 'confirm',
            quelltext + '; return { loadHouseholdSizes, saveHouseholdSize };')(
            dokument, holen, m => meldungen.push(m), async () => new Error('Server'),
            (e, ersatz) => ersatz, () => true);
        return { fns, aufrufe, meldungen, liste };
    };

    const leer = lauf({}, [[]]);
    await leer.fns.loadHouseholdSizes(7);
    pruefe('NK-118: ohne Eintrag nennt die Liste die Vorgabe von einer Person',
        leer.liste.zeilen.length === 1
        && /eine Person/.test(leer.liste.zeilen[0].kinder[0].textContent)
        && leer.aufrufe[0].url === '/api/tenants/7/haushaltsgroessen');

    const zwei = lauf({}, [[
        { id: 1, gueltig_ab: '2024-01-01', personenanzahl: 2 },
        { id: 2, gueltig_ab: '2025-03-01', personenanzahl: 3 },
    ]]);
    await zwei.fns.loadHouseholdSizes(7);
    pruefe('NK-118: eine Zeile je Stichtag, jede mit Löschknopf',
        zwei.liste.zeilen.length === 2
        && zwei.liste.zeilen.every(z => z.kinder[2].kinder[0].title === 'Stichtag löschen')
        && zwei.liste.zeilen[1].kinder[1].textContent === 3);

    const null_ = lauf({
        'household-tenant-id': { value: '7' },
        'household-gueltig-ab': { value: '2025-01-01' },
        'household-personen': { value: '0' },
    }, []);
    await null_.fns.saveHouseholdSize();
    pruefe('NK-118: 0 Personen werden vor dem Senden abgewiesen',
        null_.aufrufe.length === 0 && null_.meldungen.length === 1);

    const ohneTag = lauf({
        'household-tenant-id': { value: '7' },
        'household-personen': { value: '2' },
    }, []);
    await ohneTag.fns.saveHouseholdSize();
    pruefe('NK-118: ohne Stichtag geht nichts hinaus',
        ohneTag.aufrufe.length === 0 && ohneTag.meldungen.length === 1);

    const gut = lauf({
        'household-tenant-id': { value: '7' },
        'household-gueltig-ab': { value: '2025-01-01' },
        'household-personen': { value: '2' },
    }, [{ id: 3 }, [{ id: 3, gueltig_ab: '2025-01-01', personenanzahl: 2 }]]);
    await gut.fns.saveHouseholdSize();
    const post = gut.aufrufe[0] || {};
    pruefe('NK-118: Speichern schickt POST mit Stichtag und Personenzahl, lädt dann neu',
        post.methode === 'POST'
        && post.url === '/api/tenants/7/haushaltsgroessen'
        && post.koerper === JSON.stringify({ gueltig_ab: '2025-01-01', personenanzahl: 2 })
        && gut.aufrufe.length === 2 && gut.aufrufe[1].methode === 'GET'
        && gut.liste.zeilen.length === 1 && gut.meldungen.length === 0);
}

// --- NK-201: Warnleiste im offenen Modus -------------------------------------
// Der Rauchtest gibt die Antwort von /api/auth/me vor: offen in Docker zeigt
// die Warnleiste, offen in der Windows-App bleibt sie verborgen.
async function warnLeistePruefen() {
    // Funktion mit Klammernzaehler herausschneiden — der Rueckgabewert am
    // Ende der Funktion hat die gleiche Zeile wie ihre schliessende Klammer,
    // eine Regexp auf "\n}" waere hier zu fahrlaessig.
    const anfang = appQuelle.indexOf('async function zeigeAngemeldetenBenutzer() {');
    if (anfang < 0) throw new Error('zeigeAngemeldetenBenutzer nicht gefunden');
    let tiefe = 0, ende = -1;
    for (let i = anfang; i < appQuelle.length; i++) {
        if (appQuelle[i] === '{') tiefe++;
        else if (appQuelle[i] === '}') { tiefe--; if (!tiefe) { ende = i + 1; break; } }
    }
    const quelltext = appQuelle.slice(anfang, ende);
    const lauf = (daten) => {
        const teile = {};
        const dokument = {
            getElementById(id) {
                if (!(id in teile)) teile[id] = { textContent: '', hidden: undefined };
                return teile[id];
            },
        };
        const holen = () => Promise.resolve({ ok: true, json: () => Promise.resolve(daten) });
        return new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
            quelltext + '; return zeigeAngemeldetenBenutzer();')(
            dokument, holen, () => {}, async () => new Error('Server'), (e, e2) => e2)
            .then(() => teile);
    };
    const docker = await lauf({ username: null, ohne_anmeldung: true, leerlauf_s: null, desktop: false });
    pruefe('NK-201: offen in Docker zeigt die Warnleiste',
        docker['ohne-anmeldung-hinweis'].hidden === false
        && docker['konto-anmeldung-einschalten-bereich'].hidden === false
        && docker['kopf-abmelden'].hidden === true
        && docker['konto-liste'].hidden === true);
    const windows = await lauf({ username: null, ohne_anmeldung: true, leerlauf_s: null, desktop: true });
    pruefe('NK-201: offen in der Windows-App bleibt die Warnleiste verborgen',
        windows['ohne-anmeldung-hinweis'].hidden === true
        && windows['kopf-abmelden'].hidden === true);
}

// --- NK-204: Ausschalter schickt das Feld so, wie der Server es liest --------
// Befund: der Knopf „Anmeldung ausschalten" schickte `passwort`, der Server
// liest `password` — der Knopf scheiterte immer mit 403. Hier geht der ganze
// Weg: Konto vorhanden, Passwort eingegeben, Knopf drücken, Anfrage geht mit
// "password" raus.
async function ausschalterPruefen() {
    const anfang = appQuelle.indexOf('async function anmeldungAusschalten() {');
    if (anfang < 0) throw new Error('anmeldungAusschalten nicht gefunden');
    let tiefe = 0, ende = -1;
    for (let i = anfang; i < appQuelle.length; i++) {
        if (appQuelle[i] === '{') tiefe++;
        else if (appQuelle[i] === '}') { tiefe--; if (!tiefe) { ende = i + 1; break; } }
    }
    const quelltext = appQuelle.slice(anfang, ende);
    const aufrufe = [];
    const dokument = {
        getElementById() { return { value: 'meinlangespasswort' }; },
    };
    const fns = new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
        quelltext + '; return anmeldungAusschalten();')(
        dokument, (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            return Promise.resolve({ ok: true });
        }, () => {}, async () => new Error('Server'), (e, ersatz) => ersatz);
    await fns;
    const aufruf = aufrufe[0] || {};
    pruefe('NK-204: Ausschalter schickt POST /api/anmeldung/aus mit "password"',
        aufruf.methode === 'POST'
        && aufruf.url === '/api/anmeldung/aus'
        && aufruf.koerper === JSON.stringify({ password: 'meinlangespasswort' }));
}

// --- NK-214 (B7): die Warnung im offenen Modus verdeckt nichts ------------
// Vorher lag sie fest oben (position: fixed, z-index 1300) über Kopf,
// Knöpfen und Dialogtiteln.
{
    const band = (css.match(/\.hinweis-leiste\.hinweis-band\s*\{([^}]*)\}/) || [, ''])[1];
    pruefe('NK-214: das Band steht im Fluss, ohne eigene Ebene',
        /position:\s*relative/.test(band) && /z-index:\s*auto/.test(band)
        && /transform:\s*none/.test(band));
    const stelle = html.indexOf('id="ohne-anmeldung-hinweis"');
    pruefe('NK-214: die Warnung ist ein Band unter dem Kopf',
        stelle > html.indexOf('</header>') && stelle < html.indexOf('id="tab-dashboard"')
        && /id="ohne-anmeldung-hinweis" class="hinweis-leiste hinweis-band"/.test(html));
}

// --- NK-212 (B5): „Aktive Mieter“ zählt keine Ausgezogenen ---------------
// Vorher zählte die Kachel jeden Mieter, auch wer vor Jahren auszog.
{
    const m = appQuelle.match(/function istAktiverMieter\([\s\S]*?\n\}/);
    const aktiv = m && new Function(m[0] + '; return istAktiverMieter;')();
    const heute = '2026-10-07';
    pruefe('NK-212: aktiv ohne Auszug, am Auszugstag und danach nicht mehr',
        !!aktiv
        && aktiv({ move_out_date: null }, heute)
        && aktiv({ move_out_date: '2026-10-07' }, heute)
        && !aktiv({ move_out_date: '2026-10-06' }, heute)
        && !aktiv({ move_out_date: null, ist_beispiel: true }, heute));
    pruefe('NK-212: die Kachel zählt mit istAktiverMieter',
        /statTenantsCount\.textContent = tenants\.filter\(t => istAktiverMieter\(t, heute\)\)/.test(appQuelle));
}

// --- NK-219 (V2): Zählerliste mit Knopf „Verlauf“ und klarem Stift --------
// Vorher war der Verlauf nur per Klick auf die Zeile zu finden, der Stift
// hieß „Ablesung bearbeiten“ und die Zählernummer kam roh ins HTML.
{
    const m = appQuelle.match(/function renderMeters\([\s\S]*?\n\}/);
    const r = m ? m[0] : '';
    pruefe('NK-219: die Zählernummer wird maskiert',
        /tdNum\.innerHTML = escapeHtml\(m\.meter_number\)/.test(r)
        && !/tdNum\.innerHTML = m\.meter_number/.test(r));
    pruefe('NK-219: eigener Knopf „Verlauf“ öffnet den Verlauf',
        /verlaufBtn\.innerHTML = '[^']*> Verlauf'/.test(r)
        && /verlaufBtn\.onclick = \(\) => openHistoryModal\(m\.id\)/.test(r));
    pruefe('NK-219: der Stift heißt „Letzten Stand bearbeiten“',
        /editReadBtn\.title = "Letzten Stand bearbeiten"/.test(r));
    pruefe('NK-219: Verlauf, Stift und Papierkorb bleiben in einer Zeile',
        /tdActions\.style\.whiteSpace = 'nowrap'/.test(r));
}

// --- NK-220 (V3): die Einheit kommt vom Server, auch für die Heizung ------
// Vorher riet getReadingHtml aus dem Namen; ein Wärmezähler bekam keine.
{
    const m = appQuelle.match(/function getReadingHtml\([\s\S]*?\n\}/);
    const esc = appQuelle.match(/function escapeHtml\([\s\S]*?\n\}/);
    const zeige = m && esc && new Function('dateiAdresse',
        esc[0] + m[0] + '; return getReadingHtml;')(() => '');
    const stand = { id: 1, value: 1234.5, value_nt: null, reading_date: '2025-12-31' };
    const html = einheit => zeige({ ...stand }, einheit);
    pruefe('NK-220: die Einheit des Servers steht hinter dem Stand',
        !!zeige && html('kWh').includes('1.234,5 kWh</strong>')
        && html('m³').includes('1.234,5 m³</strong>'));
    pruefe('NK-220: ohne Einheit kein Rest',
        !!zeige && html(undefined).includes('1.234,5</strong>'));
    pruefe('NK-220: Liste und Verlauf geben die Einheit des Zählers mit',
        /getReadingHtml\(latest, m\.einheit\)/.test(appQuelle)
        && /getReadingHtml\(r, meter\.einheit\)/.test(appQuelle)
        && !/getReadingHtml\([^)]*category_name\)/.test(appQuelle));
}

// --- NK-221 (V4): „Zugestellt am“ startet leer -----------------------------
// Vorher stand dort das heutige Datum und wurde ungelesen gespeichert.
{
    const m = appQuelle.match(/function berichtZustellungsBlock\([\s\S]*?\n\}/);
    const block = m && new Function(m[0] + '; return berichtZustellungsBlock;')();
    const html = block ? block(7, { zugestellt_am: null }) : '';
    const feld = html.match(/<input[^>]*id="zustellung-datum-7"[^>]*>/);
    pruefe('NK-221: das Datumsfeld „Zugestellt am“ startet leer',
        !!feld && /type="date"/.test(feld[0]) && !/value=/.test(feld[0]));
    const melden = appQuelle.match(/async function zustellungMelden\([\s\S]*?\n\}/);
    pruefe('NK-221: ohne Datum wird nichts gemeldet',
        !!melden && /if \(!datum\) \{ showError\([^)]*\); return; \}/.test(melden[0]));
}

// --- NK-224: der Gruß steht nur auf der Übersicht ---------------------
// Vorher stand „Willkommen …“ über jedem Tab, obwohl jede Seite ihre eigene
// Überschrift trägt.
{
    const m = appQuelle.match(/function initTabs\(\)[\s\S]*?\n\}/);
    const reiter = ['dashboard', 'meters', 'invoices'].map(name => {
        const h = {};
        return { dataset: { tab: name }, classList: { add() {}, remove() {} },
            addEventListener: (typ, fn) => { h[typ] = fn; },
            klick: () => h.click({ preventDefault() {} }) };
    });
    const gruss = { hidden: false };
    const init = m && new Function('document', m[0] + '; return initTabs;')({
        querySelectorAll: s => s === '.nav-item' ? reiter : [],
        querySelector: s => s === '.greeting' ? gruss : null,
        getElementById: () => null,
    });
    const sichtbar = [];
    if (init) {
        init();
        for (const r of [reiter[1], reiter[0], reiter[2]]) { r.klick(); sichtbar.push(!gruss.hidden); }
    }
    pruefe('NK-224: der Gruß verschwindet auf anderen Tabs und kommt auf der Übersicht zurück',
        sichtbar.join() === 'false,true,false');
}

// --- NK-225: „0 von 5“ trotz Beispielhaus wird erklärt -----------------
{
    const funktion = name => (appQuelle.match(new RegExp('function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const quelle = funktion('echterBestand') + funktion('zeigeErsteSchritte');
    const lauf = beispiel => {
        const el = {};
        const hole = id => (el[id] = el[id] || { id, hidden: beispiel, style: {},  // Start = Gegenteil der Erwartung
            replaceChildren() {}, appendChild() {} });
        new Function('document', 'properties', 'allApartments', 'tenants', 'invoices', 'meters',
            'readings', 'payments', 'abrechnungsHistorie', quelle + '; zeigeErsteSchritte();')(
            { getElementById: hole, createElement: () => ({}) },
            beispiel ? [{ id: 1, ist_beispiel: true }] : [], [], [], [], [], [], [], []);
        return el;
    };
    const mit = lauf(true), ohne = lauf(false);
    pruefe('NK-225: mit Beispielhaus steht „Die Beispielimmobilie zählt nicht mit.“ neben dem Stand',
        mit['erste-schritte-stand'].textContent === '0 von 5 erledigt'
        && !!mit['erste-schritte-beispiel'] && mit['erste-schritte-beispiel'].hidden === false
        && html.includes('id="erste-schritte-beispiel"')
        && /id="erste-schritte-beispiel"[^>]*>Die Beispielimmobilie zählt nicht mit\.</.test(html));
    pruefe('NK-225: ohne Beispielhaus kein Hinweis',
        !!ohne['erste-schritte-beispiel'] && ohne['erste-schritte-beispiel'].hidden === true);
}

// --- NK-226: Vorschlag zur Anpassung der Vorauszahlung -----------------
// Die Vorschau nennt den Vorschlag, die Details bieten die Serienbuchung an.
// Gebucht wird erst im Zahlungsdialog, und schon gebuchte Zahlungen ab dem
// Wirksamwerden werden genannt.
{
    const funktion = name => (appQuelle.match(new RegExp('function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const esc = funktion('escapeHtml');
    const block = funktion('vorauszahlungsBlock') && new Function(
        esc + funktion('vorauszahlungsBlock') + '; return vorauszahlungsBlock;')();
    const v = { ab: '2026-05-01', bisher: '80.00', neu: '150.00', kosten: '1800.00',
        monate: '12.00', kuenftige: 0, aenderung: true };
    const details = block ? block(v, 7) : '';
    const vorschau = block ? block(v, null) : '';
    pruefe('NK-226: der Vorschlag nennt neue und bisherige Höhe und die Grundlage',
        details.includes('150,00 € im Monat statt 80,00 €')
        && details.includes('1800,00 € Kosten über 12 Monate'));
    pruefe('NK-226: den Knopf „Serienbuchung anlegen“ gibt es nur in den Details',
        details.includes('serienbuchungAnlegen(7, \'150.00\', \'2026-05-01\', 0)')
        && details.includes('Serienbuchung anlegen') && !vorschau.includes('serienbuchungAnlegen('));
    pruefe('NK-226: schon gebuchte Zahlungen ab dem Wirksamwerden werden genannt',
        !!block && block({ ...v, kuenftige: 2 }, 7).includes('schon 2 Vorauszahlungen gebucht')
        && !details.includes('schon 0'));
    pruefe('NK-226: ohne Vorschlag steht der Grund, ohne Änderung nichts',
        !!block && block({ grund: 'Kein <b>Grund' }, 7).includes('Kein Vorschlag: Kein &lt;b&gt;Grund')
        && block({ ...v, aenderung: false }, 7) === '' && block(undefined, 7) === '');
    pruefe('NK-226: Vorschau und Details zeigen den Block',
        /html \+= vorauszahlungsBlock\(data\.vorauszahlung, null\)/.test(appQuelle)
        && /vorauszahlungsBlock\(umschlag\.vorauszahlung, umschlag\.tenant_id\)/.test(appQuelle));
}

// Die Nachfrage bei schon gebuchten Zahlungen kommt im eigenen Dialog (frage).
async function serienPruefen() {
    const funktion = name => (appQuelle.match(new RegExp('(?:async )?function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const lauf = async (kuenftige, ja) => {
        const el = {}, offen = [];
        if (!funktion('serienbuchungAnlegen')) return { el, offen };
        const hole = id => (el[id] = el[id] || { value: '', checked: false,
            classList: { remove: k => offen.push(id + '-' + k) } });
        await new Function('document', 'openAddPaymentModal', 'togglePaymentRecurring',
            'toggleBillingReportField', 'frage',
            funktion('serienbuchungAnlegen') + '; return serienbuchungAnlegen(7, "150.00", "2026-05-01", ' + kuenftige + ');')(
            { getElementById: hole }, () => offen.push('dialog'), () => {}, () => {}, async () => ja);
        return { el, offen };
    };
    const frei = await lauf(0, false);
    pruefe('NK-226: „Serienbuchung anlegen“ füllt den Zahlungsdialog vor',
        frei.offen.includes('dialog') && frei.offen.includes('report-details-modal-active')
        && !!frei.el['payment-tenant']
        && frei.el['payment-tenant'].value === '7' && frei.el['payment-amount'].value === '150.00'
        && frei.el['payment-date'].value === '2026-05-01'
        && frei.el['payment-type'].value === 'Nebenkostenvorauszahlung'
        && frei.el['payment-recurring'].checked === true);
    pruefe('NK-226: bei schon gebuchten Zahlungen und „Nein“ öffnet sich nichts',
        !(await lauf(2, false)).offen.includes('dialog') && (await lauf(2, true)).offen.includes('dialog'));
    pruefe('NK-226: kein Browserdialog', !/confirm\(/.test(funktion('serienbuchungAnlegen')));
}

// --- NK-216 (F1): unplausibler Zählerstand wird nachgefragt ---------------
// 409 mit nachfrage: die App fragt im eigenen Dialog und schickt bei Ja
// dasselbe mit `trotzdem` noch einmal; bei Nein geht nichts mehr hinaus.
async function nachfragePruefen() {
    const m = appQuelle.match(/async function sendeMitNachfrage\([\s\S]*?\n\}/);
    const lauf = async (antworten, ja) => {
        const aufrufe = [], fragen = [];
        const holen = (url, opt) => {
            aufrufe.push({ url, methode: opt.method, trotzdem: opt.body.felder.trotzdem });
            const [status, daten] = antworten.shift();
            return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(daten) });
        };
        const formular = { felder: {}, append(k, v) { this.felder[k] = v; } };
        const senden = new Function('fetch', 'frage', m[0] + '; return sendeMitNachfrage;')(
            holen, async text => { fragen.push(text); return ja; });
        const res = await senden('/api/readings/3', 'PUT', formular);
        return { res, aufrufe, fragen };
    };
    pruefe('NK-216: sendeMitNachfrage gibt es', !!m);
    if (!m) return;
    const frage409 = [409, { error: 'Der Stand 5 ist kleiner als der vorige.', nachfrage: true }];

    const ja = await lauf([frage409, [200, { id: 3 }]], true);
    pruefe('NK-216: bei Ja geht dieselbe Anfrage mit trotzdem noch einmal',
        ja.fragen[0] === 'Der Stand 5 ist kleiner als der vorige.'
        && ja.aufrufe.length === 2 && ja.aufrufe[1].methode === 'PUT'
        && ja.aufrufe[0].trotzdem === undefined && ja.aufrufe[1].trotzdem === '1'
        && ja.res.ok);

    const nein = await lauf([frage409], false);
    pruefe('NK-216: bei Nein bleibt es bei einer Anfrage',
        nein.aufrufe.length === 1 && nein.res === null);

    const glatt = await lauf([[201, { id: 4 }]], true);
    pruefe('NK-216: ohne 409 keine Frage',
        glatt.fragen.length === 0 && glatt.aufrufe.length === 1 && glatt.res.status === 201);

    pruefe('NK-216: saveReading speichert über sendeMitNachfrage',
        /const res = await sendeMitNachfrage\(url, method, formData\);\s*if \(!res\) return;/.test(appQuelle));
}

async function korrekturPruefen() {
    const funktion = name => (appQuelle.match(new RegExp(
        '(async )?function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const euro = (appQuelle.match(/const euroText = .*;/) || [''])[0];
    const korrektur = funktion('korrekturErstellen'), text = funktion('korrekturVorschauText');
    pruefe('NK-217: Korrektur mit Vorschau gibt es', !!(korrektur && text && euro));
    if (!korrektur || !text || !euro) return;
    const lauf = async (vorschau, ja) => {
        const aufrufe = [], fragen = [], meldungen = [];
        const holen = (url, opt) => {
            aufrufe.push(url + ' ' + ((opt && opt.method) || 'GET'));
            const daten = url.endsWith('/vorschau') ? vorschau : { message: 'Korrektur erstellt' };
            return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(daten) });
        };
        const tue = async () => {};
        const k = new Function('fetch', 'frage', 'showSuccess', 'showError', 'serverFehler', 'meldungZu',
            'fetchBillingHistory', 'openReportDetails',
            euro + text + korrektur + '; return korrekturErstellen;')(
            holen, async t => { fragen.push(t); return ja; }, m => meldungen.push(m),
            m => meldungen.push('FEHLER ' + m), tue, (e, x) => x, tue, tue);
        await k(7);
        return { aufrufe, fragen, meldungen };
    };
    const geaendert = {
        unveraendert: false,
        positionen: [{ kostenart: 'Wasser', alt: '1200.00', neu: '1066.67' },
                     { kostenart: 'Grundsteuer', alt: '100.00', neu: '100.00' }],
        summe: { alt: '1300.00', neu: '1166.67' }, saldo: { alt: '1000.00', neu: '866.67' },
    };
    const ja = await lauf(geaendert, true);
    const f = (ja.fragen[0] || '').replace(/\u00a0/g, ' ');
    pruefe('NK-217: der Dialog zeigt alt → neu, nur geänderte Positionen',
        f.includes('Wasser: 1.200,00 € → 1.066,67 €') && f.includes('Summe: 1.300,00 € → 1.166,67 €')
        && f.includes('Saldo: 1.000,00 € → 866,67 €') && !f.includes('Grundsteuer'));
    pruefe('NK-217: erst Vorschau, dann Korrektur',
        ja.aufrufe.join('|') === '/api/billing/reports/7/korrektur/vorschau GET|/api/billing/reports/7/korrektur POST');
    const nein = await lauf(geaendert, false);
    pruefe('NK-217: bei Nein keine Korrektur', nein.aufrufe.length === 1);
    const gleich = await lauf({ ...geaendert, unveraendert: true }, true);
    pruefe('NK-217: unverändert fragt nicht und legt nichts an',
        gleich.fragen.length === 0 && gleich.aufrufe.length === 1 && gleich.meldungen.length === 1);
    // Review PR 26 (1): gleich nach heutigem Regelstand -- der Server haelt es
    // fest, sonst stuende der Hinweis fuer immer da.
    const erledigt = await lauf({ ...geaendert, unveraendert: true, veraltet: true }, true);
    pruefe('NK-217: unverändert bei älterem Regelstand erledigt den Hinweis ohne Frage',
        erledigt.fragen.length === 0
        && erledigt.aufrufe.join('|') === '/api/billing/reports/7/korrektur/vorschau GET|/api/billing/reports/7/korrektur POST'
        && erledigt.meldungen.join('|') === 'Korrektur erstellt');
    pruefe('NK-217: Liste und Details zeigen den älteren Regelstand',
        /const regelstandBlock = r\.veraltet \? regelstandHinweis\(r\.id, r\.regelstand_aenderungen\) : '';/.test(appQuelle)
        && /const regelstandBlock = umschlag\.veraltet \? regelstandHinweis\(id, umschlag\.regelstand_aenderungen\) : '';/.test(appQuelle)
        && (appQuelle.match(/\$\{regelstandBlock\}/g) || []).length === 2);

    // NK-229 (R-DOC-03): Richtung und Fristwarnung im Dialog, der Hinweis klappt auf.
    const richtung = await lauf({ ...geaendert, richtung: 'zulasten',
        frist_warnung: 'Die Frist für Nachforderungen endete am 01.01.2026.' }, false);
    const r = richtung.fragen[0] || '';
    pruefe('NK-229: der Dialog nennt die Richtung und warnt nach Fristende',
        r.includes('zulasten des Mieters') && r.includes('Die Frist für Nachforderungen endete am 01.01.2026.'));
    const zugunsten = (await lauf({ ...geaendert, richtung: 'zugunsten', frist_warnung: null }, false)).fragen[0] || '';
    pruefe('NK-229: zugunsten ohne Warnung',
        zugunsten.includes('zugunsten des Mieters') && !zugunsten.includes('Frist'));
    const hinweis = funktion('regelstandHinweis');
    pruefe('NK-229: regelstandHinweis gibt es', !!hinweis);
    if (!hinweis) return;
    const h = new Function(funktion('escapeHtml') + hinweis + '; return regelstandHinweis;')()(7, ['Neu <b>gerechnet</b>.']);
    pruefe('NK-229: der Hinweis klappt auf, nennt die Änderung maskiert und führt zur Vorschau',
        /^<details class="regelstand-hinweis"/.test(h.trim()) && h.includes('Nach älterem Regelstand erstellt</summary>')
        && h.includes('<li>Neu &lt;b&gt;gerechnet&lt;/b&gt;.</li>') && h.includes('verpflichtet nicht zur Korrektur')
        && /onclick="korrekturErstellen\(7\)">Unterschied ansehen<\/button>/.test(h));
    const ohne = new Function(funktion('escapeHtml') + hinweis + '; return regelstandHinweis;')()(7, []);
    pruefe('NK-229: ohne Änderungstext keine leere Liste', !ohne.includes('<ul'));
}

// --- NK-227: Ablesen am Handy zum Stichtag ------------------------------
// Alle Zähler der Immobilie mit letztem Stand und Kamerafoto; jede ausgefüllte
// Zeile geht einzeln über POST /api/readings, die Nachfrage kommt je Zeile.
async function ablesenPruefen() {
    const funktion = name => (appQuelle.match(new RegExp('(?:async )?function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const quelle = 'const ZAEHLER_ANZEIGENAMEN = {};' + funktion('escapeHtml') + funktion('zaehlerArtName') + funktion('ablesenZeilen')
        + funktion('closeAblesen') + funktion('ablesenSpeichern');
    pruefe('NK-227: Knopf „Alle Stände erfassen“ im Zähler-Tab und der Dialog',
        /onclick="openAblesen\(\)"[^>]*>[\s\S]{0,80}Alle Stände erfassen\s*<\/button>/.test(html)
        && html.includes('id="ablesen-modal"') && html.includes('id="ablesen-datum"'));
    if (!funktion('ablesenZeilen') || !funktion('ablesenSpeichern')) {
        pruefe('NK-227: ablesenZeilen und ablesenSpeichern gibt es', false);
        return;
    }
    const meters = [
        { id: 1, property_id: 5, apartment_name: 'EG', category_name: 'Strom', meter_number: '<b>S1',
          einheit: 'kWh', has_dual_tariff: true },
        { id: 2, property_id: 5, is_main_meter: true, category_name: 'Wasser', meter_number: 'W1',
          einheit: 'm³', has_dual_tariff: false },
        { id: 3, property_id: 9, apartment_name: 'OG', category_name: 'Wasser', meter_number: 'X',
          has_dual_tariff: false },
    ];
    const readings = [
        { meter_id: 1, reading_date: '2024-12-31', value: 900, value_nt: 400 },
        { meter_id: 1, reading_date: '2025-12-31', value: 1234.5, value_nt: 500 },
    ];
    const baue = (doc, extra) => new Function('document', 'meters', 'readings', 'FormData',
        'sendeMitNachfrage', 'serverFehler', 'meldungZu', 'showError', 'fetchReadings',
        quelle + '; return ' + extra + ';');
    const zeilen = baue({}, 'ablesenZeilen')({}, meters, readings)(5);
    pruefe('NK-227: die Liste zeigt die Zähler der Immobilie mit letztem Stand',
        zeilen.includes('id="ablesen-wert-1"') && zeilen.includes('id="ablesen-wert-2"')
        && !zeilen.includes('ablesen-wert-3')
        && zeilen.includes('zuletzt HT 1.234,5 kWh, NT 500 kWh am 31.12.2025')
        && zeilen.includes('noch kein Stand') && zeilen.includes('&lt;b&gt;S1'));
    pruefe('NK-227: NT-Feld nur beim Doppeltarif',
        zeilen.includes('id="ablesen-nt-1"') && !zeilen.includes('id="ablesen-nt-2"'));
    pruefe('NK-227: das Foto kommt direkt von der Kamera',
        /<input type="file" id="ablesen-foto-1" accept="image\/\*" capture="environment">/.test(zeilen));

    const lauf = async (werte, antworten) => {
        const el = {}, gesendet = [], fehler = [];
        let neuGeladen = 0;
        const hole = id => (el[id] = el[id] || { id, value: werte[id] !== undefined ? werte[id] : '',
            files: [], textContent: '', classList: { remove: k => { el[id].zu = k; } } });
        hole('ablesen-datum').value = '2026-01-01';
        hole('ablesen-property').value = '5';
        function Formular() { this.felder = {}; }
        Formular.prototype.append = function (k, v) { this.felder[k] = String(v); };
        const senden = (url, methode, fd) => { gesendet.push({ url, methode, ...fd.felder });
            return Promise.resolve(antworten.shift()); };
        await baue({}, 'ablesenSpeichern')({ getElementById: id => hole(id) }, meters, readings, Formular, senden,
            async () => new Error('kaputt'), (e, t) => t, t => fehler.push(t), () => neuGeladen++)();
        return { el, gesendet, fehler, neuGeladen };
    };
    const ok = { ok: true, status: 201 };
    const beide = await lauf({ 'ablesen-wert-1': '1300', 'ablesen-nt-1': '520', 'ablesen-wert-2': '42' }, [ok, ok]);
    pruefe('NK-227: jede ausgefüllte Zeile geht einzeln über POST /api/readings',
        beide.gesendet.length === 2 && beide.gesendet.every(g => g.url === '/api/readings' && g.methode === 'POST')
        && beide.gesendet[0].meter_id === '1' && beide.gesendet[0].value === '1300'
        && beide.gesendet[0].value_nt === '520' && beide.gesendet[0].reading_date === '2026-01-01'
        && beide.gesendet[1].meter_id === '2' && !('value_nt' in beide.gesendet[1])
        && beide.el['ablesen-modal'].zu === 'active' && beide.neuGeladen === 1);
    const leer = await lauf({ 'ablesen-wert-2': '42' }, [ok]);
    pruefe('NK-227: leere Zeilen werden übersprungen',
        leer.gesendet.length === 1 && leer.gesendet[0].meter_id === '2');
    const nein = await lauf({ 'ablesen-wert-1': '1', 'ablesen-wert-2': '42' }, [null, ok]);
    pruefe('NK-227: „Nein“ auf die Nachfrage lässt die Zeile stehen, der Dialog bleibt offen',
        nein.gesendet.length === 2 && nein.el['ablesen-wert-1'].value === '1'
        && nein.el['ablesen-meldung-1'].textContent === 'Nicht gespeichert.'
        && nein.el['ablesen-wert-2'].value === '' && !nein.el['ablesen-modal']);
    const nichts = await lauf({}, []);
    pruefe('NK-227: ohne Eintrag ein Hinweis statt Stille',
        nichts.gesendet.length === 0 && nichts.fehler.length === 1);
}


// --- NK-228: Sprünge gegenüber dem Vorjahr in Schritt 2 -------------------
{
    const funktion = name => (appQuelle.match(new RegExp('function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const euro = (appQuelle.match(/const euroText = .*\n/) || [''])[0];
    const ziel = {};
    new Function('document', 'jahrStand', euro + funktion('escapeHtml') + funktion('anzahlText')
        + funktion('jahrKostenartenZeigen') + '; jahrKostenartenZeigen();')(
        { getElementById: () => ziel },
        { jahr: 2025, kostenarten: [
            { name: 'Grundsteuer', zustand: 'erfasst', anzahl: 1, summe: 1450, summe_vorjahr: 1000, aenderung: 45, sprung: true },
            { name: 'Müll', zustand: 'erfasst', anzahl: 1, summe: 700, summe_vorjahr: 1000, aenderung: -30, sprung: true },
            { name: 'Wasser', zustand: 'erfasst', anzahl: 1, summe: 1100, summe_vorjahr: 1000, aenderung: 10, sprung: false },
        ] });
    const zeilen = (ziel.innerHTML || '').split('<tr').slice(2);
    pruefe('NK-228: Schritt 2 markiert den Sprung mit Richtung und rät zum Anschreiben',
        zeilen.length === 3
        && zeilen[0].includes('jahr-sprung') && zeilen[0].includes('+45 % gegenüber dem Vorjahr')
        && zeilen[0].includes('Anschreiben (Schritt 5)')
        && zeilen[1].includes('−30 % gegenüber dem Vorjahr')
        && !zeilen[2].includes('jahr-sprung') && !zeilen[2].includes('gegenüber dem Vorjahr'));
}

warnLeistePruefen()
    .catch(e => pruefe('NK-201: Warnleisten-Prüfung lief durch — ' + e.message, false))
    .then(() => ausschalterPruefen()
        .catch(e => pruefe('NK-204: Ausschalter-Prüfung lief durch — ' + e.message, false))
        .then(() => haushaltPruefen()
            .catch(e => pruefe('NK-118: Haushaltsprüfung lief durch — ' + e.message, false))
            .then(() => nachfragePruefen()
                .catch(e => pruefe('NK-216: Nachfrage-Prüfung lief durch — ' + e.message, false))
                .then(() => korrekturPruefen()
                    .catch(e => pruefe('NK-217: Korrektur-Prüfung lief durch — ' + e.message, false))
                    .then(() => serienPruefen()
                        .catch(e => pruefe('NK-226: Serienbuchung-Prüfung lief durch — ' + e.message, false))
                        .then(() => ablesenPruefen()
                            .catch(e => pruefe('NK-227: Ablesen-Prüfung lief durch — ' + e.message, false))
                            .then(() => process.exit(fehler ? 1 : 0))))))));
