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
// Im Browser ist datumText global; die Sandboxen unten sehen es ebenso.
globalThis.datumText = new Function(appQuelle.match(/const datumText = [^\n]*/)[0] + '; return datumText;')();

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
    documentElement: { style: {}, dataset: {} },
};
global.Chart = class {
    constructor() {}
    destroy() {}
};
// Dunkelmodus: themaAnzeigen liest Tokens und setzt Chart.defaults.
global.Chart.defaults = { elements: { arc: {} } };
global.Chart.instances = {};
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
global.escapeHtml = s => String(s);
// initApp ruft beim Laden alle Listen ab. Seit der Rauchtest am Ende auf
// asynchrone Prüfungen wartet (NK-118), liefen diese Abrufe sonst gegen das
// echte fetch von Node; so bleiben sie still hängen.
global.fetch = () => new Promise(() => {});
global.alert = () => {};
// Phase 65: auswahlKnoepfe fragt nach base-select; ohne Browser gibt es das nicht.
global.CSS = { supports: () => false };
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
// Am Zähler steht der Alltagsname (F-113): „Strom“ statt
// „Allgemeinstrom“. Die Zuordnung kommt aus app.js selbst.
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
        let layoutHinweisGefragt = 0;
        const oeffnen = new Function('document', 'showError', 'generateBillPreview', 'escapeHtml',
            // Der Servervorschlag (NK-186) braucht fetch; hier zählt nur die Vorbelegung.
            'zeitraumVorschlagen',
            // Der Hinweis „Eigenes PDF-Layout aktiv“ fragt den Server selbst.
            'pdfLayoutHinweisLaden',
            'let currentBillingSelection = null;\n'
            + [teil('vorgeschlagenerZeitraum'), teil('pruefeAbrechnungszeitraum'),
               teil('openBillingSelectionModal')].join('\n')
            + '\nreturn openBillingSelectionModal;')(
            dokument, m => meldungen.push(m), (...a) => aufrufe.push(a), s => String(s), () => {},
            () => { layoutHinweisGefragt++; });
        oeffnen({
            tenant_id: 7,
            categories: [
                { category_id: 1, category_name: 'A', suggested_start: '2024-01-01', suggested_end: '2024-12-31', invoice_count: 1 },
                { category_id: 2, category_name: 'B', suggested_start: '2023-07-01', suggested_end: '2024-06-30', invoice_count: 1 },
            ],
        });
        if (layoutHinweisGefragt !== 1) return 'der Dialog fragt den PDF-Aufbau nicht ab';
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
// Achtzehn Pillen: Rechnungen (Eingang/Alle/Nach Kostenart, Liste/Zeitleiste), Einstellungen
// (sieben Gruppen, Phase 54 ergänzt Kostenarten, der PDF-Aufbau die Abrechnung), Statistik
// (fünf Filter), Historie (Nur offene Zahlungen, Phase 47); dieselbe Zahl sichert
// test_ui_konsistenz.py.
pruefe('Achtzehn Auswahlpillen, keine mit Inline-Stil',
    (html.match(/class="filter-pill/g) || []).length === 18
    && !/class="filter-pill[^"]*"[^>]*style=/.test(html));
pruefe('Cache-Buster erhoeht (style.css)', /style\.css\?v=\d+/.test(html));
pruefe('Cache-Buster erhoeht (app.js)', /app\.js\?v=\d+/.test(html));

// --- NK-100: Knopfsockel (K3) und Raster (K6) im Stylesheet ---
const sockel = /\.btn-primary,\s*\n\.btn-secondary,\s*\n\.btn-tint,\s*\n\.btn-gefahr\s*\{/;
pruefe('Knopfsockel bündelt alle vier Klassen (K3)', sockel.test(css));
pruefe('Sockel: feste Höhe aus dem Token (K3)',
    css.includes('height: var(--knopf-hoehe);')
    && css.includes('padding: 0 var(--space-4);'));
pruefe('Sockel: Icon-Regel mit Kindselektor (K3)',
    /\.btn-primary > i,\s*\n\.btn-secondary > i,\s*\n\.btn-tint > i,\s*\n\.btn-gefahr > i\s*\{/.test(css));
pruefe('Raster-Tokens definiert (K6)',
    css.includes('--space-1: 4px;') && css.includes('--space-7: 48px;')
    && css.includes('--knopf-hoehe: 44px;')
    && css.includes('--knopf-hoehe-klein: 32px;')
    && css.includes('--primary-tint: #EEEDFD;'));
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
// „Rechnungen & Belege“ trägt Seitenkopf (Beleg hochladen) und Ansichtskopf (Rechnungen).
pruefe('K1: .kopf-aktionen in allen neun Köpfen mit Knöpfen (global + acht Bereiche)',
    (ui.match(/class="kopf-aktionen"/g) || []).length === 9
    && css.includes('.kopf-aktionen {'));
pruefe('K1: .section-untertitel statt Inline-Stil (elf Köpfe: jede Seite plus Historie)',
    (ui.match(/class="section-untertitel"/g) || []).length === 11
    && !ui.includes('color: var(--text-muted); margin-top: 4px;"')
    && css.includes('.section-untertitel {'));
pruefe('K1: auch „Heute“ beginnt mit einem Seitenkopf',
    html.indexOf('id="tab-dashboard"') < html.indexOf('<h2>Heute</h2>')
    && html.indexOf('<h2>Heute</h2>') < html.indexOf('id="erste-schritte"'));

// --- NK-102: Leerzustand als eine Komponente (K4) ---
const app = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');

// Zähler-Detail: Verbrauch je Zeitraum, bei Zweitarif HT plus NT.
const verbrauchQuelle = (app.match(/function zaehlerVerbrauch\([\s\S]*?\n\}\n/) || [''])[0];
const zaehlerVerbrauch = new Function(verbrauchQuelle + 'return zaehlerVerbrauch;')();
pruefe('Verbrauch eines Eintarifzählers ist die Differenz',
    zaehlerVerbrauch({ value: 100 }, { value: 130.5 }) === 30.5);
pruefe('Verbrauch eines Zweitarifzählers zählt HT und NT',
    zaehlerVerbrauch({ value: 100, value_nt: 40 }, { value: 130, value_nt: 50 }) === 40);
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
// NK-268: Art und Lohnanteil nach § 35a EStG gehen nur gemeinsam an den Server.
pruefe('NK-268: Rechnungsdialog trägt Art und Lohnanteil nach § 35a, nur gemeinsam',
    html.includes('id="invoice-art-35a"') && html.includes('id="invoice-lohnanteil"')
    && app.includes("if ((art35a === '') !== (lohnanteil === '')) {")
    && app.includes("formData.append('art_35a', art35a)")
    && app.includes("formData.append('lohnanteil', lohnanteil)"));

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

// --- NK-261: Soll und Ist der Vorauszahlungen -------------------------------
// Der Wächter ruft ladeVorauszahlungen und saveVorauszahlungSoll mit
// gestubbtem fetch auf: ohne Soll kein Rückstand und keine Erinnerung, der
// jüngste Monat steht oben, ein Rückstand zeigt die Erinnerung, Speichern
// schickt Stichtag und Betrag und lädt neu.
async function vorauszahlungPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const quelltext = funktion('monatsZeilen') + funktion('ladeVorauszahlungen') + funktion('saveVorauszahlungSoll');
    const lauf = (felder, antworten) => {
        const aufrufe = [];
        const meldungen = [];
        const dokument = {
            getElementById(id) {
                if (!(id in felder)) felder[id] = { value: '', innerHTML: '', textContent: '', hidden: false };
                return felder[id];
            },
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            const daten = antworten.shift() ?? {};
            return Promise.resolve({ ok: true, json: () => Promise.resolve(daten) });
        };
        const fns = new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
            'escapeHtml', 'datumText', 'euroText',
            quelltext + '; return { ladeVorauszahlungen, saveVorauszahlungSoll };')(
            dokument, holen, m => meldungen.push(m), async () => new Error('Server'),
            (e, ersatz) => ersatz, t => String(t).replace(/</g, '&lt;'), iso => 'D' + iso,
            v => Number(v).toFixed(2) + ' €');
        return { fns, aufrufe, meldungen, felder };
    };

    const leer = lauf({}, [{ soll: [], monate: [
        { monat: '2024-01', soll: null, ist: '80.00', differenz: null, rueckstand: false, laufend: false },
    ], saldo: '0.00', erinnerung: null }]);
    await leer.fns.ladeVorauszahlungen(7);
    pruefe('NK-261: ohne Soll kein Rückstand und keine Erinnerung',
        leer.aufrufe[0].url === '/api/tenants/7/vorauszahlungen'
        && /Noch kein Soll/.test(leer.felder['vz-soll-liste'].innerHTML)
        && /kein Soll/.test(leer.felder['vz-monate'].innerHTML)
        && leer.felder['vz-saldo'].textContent === 'Kein Rückstand.'
        && leer.felder['vz-erinnerung-block'].hidden === true);

    const offen = lauf({}, [{ soll: [{ id: 4, gueltig_ab: '2024-01-01', betrag: '80.00' }], monate: [
        { monat: '2024-01', soll: '80.00', ist: '0.00', differenz: '80.00', rueckstand: true, laufend: false },
        { monat: '2024-02', soll: '80.00', ist: '0.00', differenz: '80.00', rueckstand: false, laufend: true },
    ], saldo: '80.00', erinnerung: 'Sehr geehrte …' }]);
    await offen.fns.ladeVorauszahlungen(7);
    const zeilen = offen.felder['vz-monate'].innerHTML;
    pruefe('NK-261: der jüngste Monat oben, Rückstand markiert, Erinnerung sichtbar',
        zeilen.indexOf('02/2024') < zeilen.indexOf('01/2024')
        && /dq-status-badge red">Rückstand/.test(zeilen) && /laufend/.test(zeilen)
        && /D2024-01-01/.test(offen.felder['vz-soll-liste'].innerHTML)
        && /Offen sind insgesamt 80\.00 €/.test(offen.felder['vz-saldo'].textContent)
        && offen.felder['vz-erinnerung'].value === 'Sehr geehrte …'
        && offen.felder['vz-erinnerung-block'].hidden === false);

    const ohneTag = lauf({ 'vz-tenant-id': { value: '7' }, 'vz-betrag': { value: '80' } }, []);
    await ohneTag.fns.saveVorauszahlungSoll();
    pruefe('NK-261: ohne Stichtag geht nichts hinaus',
        ohneTag.aufrufe.length === 0 && ohneTag.meldungen.length === 1);

    const gut = lauf({
        'vz-tenant-id': { value: '7' },
        'vz-gueltig-ab': { value: '2024-01-01' },
        'vz-betrag': { value: '80' },
    }, [{ id: 4 }, { soll: [], monate: [], saldo: '0.00', erinnerung: null }]);
    await gut.fns.saveVorauszahlungSoll();
    const post = gut.aufrufe[0] || {};
    pruefe('NK-261: Speichern schickt POST mit Stichtag und Betrag, lädt dann neu',
        post.methode === 'POST' && post.url === '/api/tenants/7/vorauszahlung_soll'
        && post.koerper === JSON.stringify({ gueltig_ab: '2024-01-01', betrag: '80' })
        && gut.aufrufe.length === 2 && gut.aufrufe[1].url === '/api/tenants/7/vorauszahlungen'
        && gut.meldungen.length === 0);

    pruefe('NK-261: Mieterzeile hat den Knopf, die Seite den Dialog',
        appQuelle.includes('vzBtn.onclick = () => openVorauszahlungModal(t);')
        && html.includes('id="vorauszahlung-modal"'));
}

// --- Phase 49: Kaltmiete-Soll und Erinnerung an die Mieterhöhung -------------
// Wie beim VZ-Soll: Laden mit gestubbtem fetch, Speichern schickt Stichtag,
// Betrag und Indexmiete-Flag und lädt neu.
async function kaltmietePruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const quelltext = funktion('monatsZeilen') + funktion('ladeKaltmiete') + funktion('saveKaltmieteSoll');
    const lauf = (felder, antworten) => {
        const aufrufe = [];
        const meldungen = [];
        const dokument = {
            getElementById(id) {
                if (!(id in felder)) felder[id] = { value: '', innerHTML: '', textContent: '', hidden: false, checked: false };
                return felder[id];
            },
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            const daten = antworten.shift() ?? {};
            return Promise.resolve({ ok: true, json: () => Promise.resolve(daten) });
        };
        const fns = new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
            'escapeHtml', 'datumText', 'euroText',
            quelltext + '; return { ladeKaltmiete, saveKaltmieteSoll };')(
            dokument, holen, m => meldungen.push(m), async () => new Error('Server'),
            (e, ersatz) => ersatz, t => String(t).replace(/</g, '&lt;'), iso => 'D' + iso,
            v => Number(v).toFixed(2) + ' €');
        return { fns, aufrufe, meldungen, felder };
    };

    const leer = lauf({}, [{ soll: [], monate: [], saldo: '0.00', erinnerung: null }]);
    await leer.fns.ladeKaltmiete(7);
    pruefe('Phase 49/53: ohne Kaltmiete ein Hinweis statt einer leeren Liste',
        leer.aufrufe[0].url === '/api/tenants/7/miete'
        && /Noch keine Kaltmiete hinterlegt/.test(leer.felder['km-soll-liste'].innerHTML)
        && leer.felder['km-saldo'].textContent === 'Kein Rückstand.'
        && leer.felder['km-erinnerung-block'].hidden === true);

    const voll = lauf({}, [{ soll: [
        { id: 9, gueltig_ab: '2026-10-01', betrag: '700.00', indexmiete: false, geplant: false },
        { id: 12, gueltig_ab: '2027-01-01', betrag: '800.00', indexmiete: true, geplant: true },
    ], monate: [
        { monat: '2026-09', soll: '700.00', ist: '700.00', differenz: '0.00', rueckstand: false, laufend: false },
        { monat: '2026-10', soll: '700.00', ist: '0.00', differenz: '-700.00', rueckstand: false, laufend: true },
    ], saldo: '0.00', erinnerung: 'Guten Tag A, ...' }]);
    await voll.fns.ladeKaltmiete(7);
    pruefe('Phase 49/53: Stichtage mit Betrag, geplante Stufe gekennzeichnet, Indexmiete erläutert',
        /D2026-10-01/.test(voll.felder['km-soll-liste'].innerHTML)
        && /Indexmiete \(§ 557b\)/.test(voll.felder['km-soll-liste'].innerHTML)
        && /geplant<\/span>/.test(voll.felder['km-soll-liste'].innerHTML)
        && voll.felder['km-soll-liste'].innerHTML.includes("serienbuchungAnlegen(7, '800.00', '2027-01-01', 0, 'Miete')")
        && voll.felder['km-soll-liste'].innerHTML.includes('loescheKaltmieteSoll(9, 7)'));

    pruefe('Phase 53: Monattabelle geteilt gebaut, Saldo und Erinnerung gesetzt',
        /09\/2026/.test(voll.felder['km-monate'].innerHTML)
        && /bezahlt/.test(voll.felder['km-monate'].innerHTML)
        && /laufend/.test(voll.felder['km-monate'].innerHTML)
        && /Offen sind insgesamt|Kein Rückstand/.test(voll.felder['km-saldo'].textContent)
        && voll.felder['km-erinnerung'].value === 'Guten Tag A, ...'
        && voll.felder['km-erinnerung-block'].hidden === false);

    const ohneTag = lauf({ 'km-tenant-id': { value: '7' }, 'km-betrag': { value: '750' } }, []);
    await ohneTag.fns.saveKaltmieteSoll();
    pruefe('Phase 49: ohne Stichtag geht nichts hinaus',
        ohneTag.aufrufe.length === 0 && ohneTag.meldungen.length === 1);

    const gut = lauf({
        'km-tenant-id': { value: '7' },
        'km-gueltig-ab': { value: '2025-08-01' },
        'km-betrag': { value: '750' },
        'km-indexmiete': { checked: true },
    }, [{ id: 12 }, { soll: [], monate: [], saldo: '0.00', erinnerung: null }]);
    await gut.fns.saveKaltmieteSoll();
    const post = gut.aufrufe[0] || {};
    pruefe('Phase 49: Speichern schickt POST mit Stichtag, Betrag und Indexmiete, lädt dann neu',
        post.methode === 'POST' && post.url === '/api/tenants/7/kaltmiete_soll'
        && post.koerper === JSON.stringify({ gueltig_ab: '2025-08-01', betrag: '750', indexmiete: true })
        && gut.aufrufe.length === 2 && gut.aufrufe[1].url === '/api/tenants/7/miete'
        && gut.meldungen.length === 0);

    pruefe('Phase 49: Mieterzeile hat den Knopf, die Seite den Dialog',
        appQuelle.includes('kmBtn.onclick = () => openKaltmieteModal(t);')
        && html.includes('id="kaltmiete-modal"'));
}

// Phase 50 (Issue #30): die Hausgeld-Einzelabrechnung prüfen — was der
// Dialog sammelt und was er an den Server schickt, vom Quelltext her.
async function hausgeldPruefungPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const quelltext =
        "const HG_URTEIL = { true: ['Ja', 'chip-ok'], false: ['Nein', 'chip-rot'], null: ['Offen', 'chip-warn'] };"
        + funktion('geldText') + funktion('hausgeldPositionen') + funktion('hausgeldPruefen');

    // Jede Zeile ist ein Tripel [Name, Gesamtbetrag, eigener Betrag].
    const lauf = (zeilen, felder, antwort) => {
        const aufrufe = [];
        const meldungen = [];
        const zellen = klasse => zeilen.map(z => ({
            value: { '.hg-name': z[0], '.hg-gesamt': z[1], '.hg-mein': z[2] }[klasse],
        }));
        const dokument = {
            getElementById(id) {
                if (!(id in felder)) felder[id] = { value: '', innerHTML: '', textContent: '', hidden: false, className: '' };
                return felder[id];
            },
            querySelectorAll: () => zeilen.map((_, i) => ({
                querySelector: klasse => zellen(klasse)[i],
            })),
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            return Promise.resolve({ ok: true, json: () => Promise.resolve(antwort) });
        };
        const fns = new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
            'escapeHtml',
            quelltext + '; return { hausgeldPositionen, hausgeldPruefen };')(
            dokument, holen, m => meldungen.push(m), async () => new Error('Server'),
            (e, ersatz) => ersatz,
            t => String(t).replace(/</g, '&lt;').replace(/>/g, '&gt;'));
        return { fns, aufrufe, meldungen, felder };
    };

    const BERICHT = {
        positionen: [
            { name: 'Müllentsorgung', umlagefaehig: true, betrkv_nr: 8, begruendung: 'Nr. 8',
              eigener_betrag: '300.00', erwartet: '300.00', abweichung: '0.00', stimmt: true, hinweis: null },
            { name: 'Verwaltervergütung', umlagefaehig: false, betrkv_nr: null,
              begruendung: 'Verwaltungskosten … § 1 Abs. 2 BetrKV …',
              eigener_betrag: '750.00', erwartet: '750.00', abweichung: '0.00', stimmt: true, hinweis: null },
        ],
        summe_umlagefaehig: '300.00', summe_eigentuemer: '750.00', summe_offen: '0.00',
        anzahl_umlagefaehig: 1, anzahl_eigentuemer: 1, anzahl_offen: 0,
        summenprobe: { erwartet: '1050.00', angesetzt: '1050.00', abweichung: '0.00', stimmt: true, hinweis: null },
        zeitraum_hinweis: 'Abflussprinzip … BGH … VIII ZR 27/07 …',
        heizkosten_hinweis: 'Die Heizkosten … ordnen Sie diese Rechnung der Wohnung zu … nach Wohnfläche …',
    };

    // Leere Zeilen zählen nicht mit: der Dialog startet mit dreien.
    const leer = lauf([['', '', ''], ['Müll', '2400.00', '300.00'], ['', '', '']], {}, BERICHT);
    pruefe('Phase 50: leere Zeilen gehen nicht mit hinaus',
        leer.fns.hausgeldPositionen().length === 1);

    const ohne = lauf([['', '', '']], {}, BERICHT);
    await ohne.fns.hausgeldPruefen();
    pruefe('Phase 50: ohne Position geht nichts hinaus',
        ohne.aufrufe.length === 0 && ohne.meldungen.length === 1);

    const felder = {
        'hg-eigener-anteil': { value: '125' },
        'hg-gesamtanteile': { value: '1000' },
        'hg-abrechnungssumme': { value: '1050.00' },
    };
    const voll = lauf([['Müllentsorgung', '2400.00', '300.00'],
                       ['Verwaltervergütung', '6000.00', '750.00']], felder, BERICHT);
    await voll.fns.hausgeldPruefen();
    const koerper = voll.aufrufe.length === 1 ? JSON.parse(voll.aufrufe[0].koerper) : {};
    pruefe('Phase 50: die Positionen gehen als POST an /api/hausgeld/pruefen',
        voll.aufrufe.length === 1 && voll.aufrufe[0].url === '/api/hausgeld/pruefen'
        && voll.aufrufe[0].methode === 'POST'
        && koerper.positionen.length === 2
        && koerper.positionen[0].name === 'Müllentsorgung'
        && koerper.eigener_anteil === '125' && koerper.gesamtanteile === '1000'
        && koerper.abrechnungssumme === '1050.00');

    pruefe('Phase 50: das Ergebnis trennt umlagefähig von dem, was beim Eigentümer bleibt',
        voll.felder['hg-ergebnis'].hidden === false
        && voll.felder['hg-summen'].innerHTML.includes('300,00')
        && voll.felder['hg-summen'].innerHTML.includes('750,00'));

    pruefe('Phase 50: jede Zeile trägt die Begründung des Servers, nicht einen eigenen Text',
        voll.felder['hg-bericht'].innerHTML.includes('§ 1 Abs. 2 BetrKV')
        && voll.felder['hg-bericht'].innerHTML.includes('chip-rot')
        && voll.felder['hg-bericht'].innerHTML.includes('chip-ok'));

    pruefe('Phase 50: der Zeitraum-Hinweis (BGH VIII ZR 27/07) steht dabei',
        voll.felder['hg-zeitraum'].textContent.includes('VIII ZR 27/07'));

    // Der Weg fuer die Heizkosten ist der, den der Vermieter sonst nicht
    // findet: eine Rechnung, die der Wohnung zugeordnet ist. Ohne die
    // Zuordnung verteilt der Kern sie nach Flaeche auf alle Wohnungen --
    // rechnerisch sauber, fachlich falsch, ohne Fehlermeldung.
    pruefe('Phase 50: der Dialog sagt, wohin die Heizkosten des Messdienstes gehören',
        voll.felder['hg-heizkosten'].textContent.includes('ordnen Sie')
        && voll.felder['hg-heizkosten'].textContent.includes('Wohnfläche'));

    // Ohne Endsumme entfällt die Summenprobe, statt eine leere Zeile zu zeigen.
    const ohneSumme = lauf([['Müll', '2400.00', '300.00']],
        { 'hg-eigener-anteil': { value: '125' }, 'hg-gesamtanteile': { value: '1000' },
          'hg-abrechnungssumme': { value: '' } },
        { ...BERICHT, summenprobe: null });
    await ohneSumme.fns.hausgeldPruefen();
    const leerKoerper = JSON.parse(ohneSumme.aufrufe[0].koerper);
    pruefe('Phase 50: ohne Endsumme entfällt die Summenprobe',
        leerKoerper.abrechnungssumme === null
        && ohneSumme.felder['hg-summenprobe'].hidden === true);
}

// Phase 57 (Issue #35, Punkt 3): Rechnungen nach Jahr. Geprueft wird das
// Verhalten, nicht nur, dass das Feld da ist: renderInvoices() laeuft gegen
// einen DOM-Stub und muss filtern, zaehlen und summieren.
async function rechnungsJahrPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const quelltext = "const OHNE_DATUM = 'ohne';"
        + funktion('rechnungsJahr') + funktion('rechnungsfilterZuruecksetzen')
        + funktion('geldText');

    const bestand = [
        { id: 1, amount: 100, rechnungsdatum: '2024-03-01', category_name: 'Heizung', property_name: 'Haus', invoice_number: 'A', provider_name: 'P' },
        { id: 2, amount: 250, rechnungsdatum: '2025-06-01', category_name: 'Heizung', property_name: 'Haus', invoice_number: 'B', provider_name: 'P' },
        { id: 3, amount: 50, rechnungsdatum: '2025-09-01', category_name: 'Wasser', property_name: 'Haus', invoice_number: 'C', provider_name: 'P' },
        { id: 4, amount: 7, rechnungsdatum: null, category_name: 'Wasser', property_name: 'Haus', invoice_number: 'D', provider_name: 'P' },
    ];

    const fns = new Function(quelltext + '; return { rechnungsJahr, geldText };')();

    pruefe('Phase 57: das Jahr kommt aus dem Rechnungsdatum, ohne Datum eine eigene Gruppe',
        fns.rechnungsJahr(bestand[0]) === '2024'
        && fns.rechnungsJahr(bestand[1]) === '2025'
        && fns.rechnungsJahr(bestand[3]) === 'ohne'
        && fns.rechnungsJahr({}) === 'ohne');

    // Den Filterteil von renderInvoices nachbilden -- dieselben Zeilen, die
    // die Oberflaeche ausfuehrt, aus der Quelle geschnitten.
    const quelle = appQuelle.match(/function renderInvoices\(\)[\s\S]*?\n\}/)[0];
    pruefe('Phase 57: renderInvoices filtert nach dem Jahr',
        /matchJahr = rechnungsJahr\(i\) === jahrFilterVal/.test(quelle)
        && /return matchSearch && matchCat && matchJahr/.test(quelle));

    pruefe('Phase 57: die Summenzeile folgt dem Filter, nicht dem Bestand',
        /filtered\.reduce/.test(quelle)
        && /summeZeile\.textContent/.test(quelle)
        && !/invoices\.reduce/.test(quelle));

    pruefe('Phase 57: das Auswahlfeld fuellt sich aus dem Bestand, juengstes Jahr zuerst',
        /invoices\.map\(rechnungsJahr\)/.test(quelle)
        && /\.sort\(\)\.reverse\(\)/.test(quelle)
        && /echte\.push\(OHNE_DATUM\)/.test(quelle));

    // Die Summe von Hand nachgerechnet: 2025 sind 250 + 50 = 300.
    const summe2025 = bestand.filter(r => fns.rechnungsJahr(r) === '2025')
        .reduce((z, r) => z + Number(r.amount || 0), 0);
    pruefe('Phase 57: die Jahressumme stimmt (2025: 250 + 50 = 300)',
        summe2025 === 300 && /300/.test(fns.geldText(summe2025)));

    // Zuruecksetzen muss auch das neue Feld raeumen -- sonst bleibt ein
    // unsichtbarer Filter stehen und der Nutzer sucht den Fehler bei sich.
    const geraeumt = {};
    const dokument = { getElementById(id) { geraeumt[id] = { value: 'x' }; return geraeumt[id]; } };
    new Function('document', 'renderInvoices',
        quelltext + '; rechnungsfilterZuruecksetzen();')(dokument, () => {});
    pruefe('Phase 57: „Filter zuruecksetzen" raeumt auch das Jahr',
        geraeumt['invoice-jahr-filter'] && geraeumt['invoice-jahr-filter'].value === ''
        && geraeumt['invoice-search'].value === ''
        && geraeumt['invoice-category-filter'].value === '');

    // Die Zeitleiste zeigt die Jahressumme, die der Server schon rechnet.
    const zeitleiste = appQuelle.match(/function renderInvoiceZeitleiste[\s\S]*?\n\}/)[0];
    pruefe('Phase 57: die Zeitleiste zeigt die Jahressumme des Servers, ohne sie nachzurechnen',
        /zeitleiste-jahressumme/.test(zeitleiste)
        && /zeitleisteBetrag\(jahr\.summe\)/.test(zeitleiste));

    // Und die Oberflaeche traegt die Felder, an denen das alles haengt.
    pruefe('Phase 57: Auswahlfeld und Summenzeile stehen in der Oberflaeche',
        /id="invoice-jahr-filter"[\s\S]*?Alle Jahre/.test(html)
        && /id="invoice-summe"/.test(html));
}

// Phase 62 (Issue #35, Nachtrag): die Zeitleiste folgt der Immobilie aus
// dem Kopf und den Filtern der Liste. Gefahren wird die Adresse gegen einen
// DOM-Stub, das Auffuellen der Auswahlfelder gegen ein Schein-<select>.
// Abwärtskompatibel: Ein Schritt im Rechenweg ist seit Phase 61 ein Paar
// [Text, Betrag], in 0.16 war er ein Text. Die Vorschau der
// Jahresabrechnung zeigte das Paar als "Text,23.70".
async function rechenwegTextPruefen() {
    const m = appQuelle.match(/function rechenwegText\([^)]*\) \{[\s\S]*?\n\}/);
    if (!m) throw new Error('rechenwegText nicht gefunden');
    const euro = appQuelle.match(/const euroText = [^\n]*/)[0];
    const rechenwegText = new Function(euro + '; ' + m[0] + '; return rechenwegText;')();
    pruefe('Rechenweg: Paare aus Text und Betrag werden zum Satz mit Euro-Betrag',
        rechenwegText([['Rechnungsbetrag', '1200.00'], ['anteilig 184 von 366 Tagen', '603.28']])
            .replace(/\u00a0/g, ' ') === 'Rechnungsbetrag 1.200,00 € · anteilig 184 von 366 Tagen 603,28 €');
    pruefe('Rechenweg: alte Schritte (reine Texte aus 0.16) bleiben unverändert',
        rechenwegText(['1.200,00 € Rechnungsbetrag', 'anteilig = 603,28 €'])
            === '1.200,00 € Rechnungsbetrag · anteilig = 603,28 €'
        && rechenwegText(undefined) === '');
    pruefe('Rechenweg: die Vorschau der Jahresabrechnung nutzt rechenwegText',
        /rechenwegText\(zeile\.rechenweg\)/.test(appQuelle)
        && !/\(zeile\.rechenweg \|\| \[\]\)\.join/.test(appQuelle));
}

async function belegDatumPruefen() {
    const m = appQuelle.match(/function belegDatumAnbieten\([^)]*\) \{[\s\S]*?\n\}/);
    if (!m) throw new Error('belegDatumAnbieten nicht gefunden');
    const felder = {
        'invoice-document-id': { value: '7' }, 'invoice-id': { value: '' },
        'invoice-datum-beleg-zeile': { hidden: true },
        'invoice-datum-beleg-anzahl': { textContent: '' },
        'invoice-datum-fuer-beleg': { checked: true },
    };
    const bau = rechnungen => new Function('document', 'invoices', m[0] + '; return belegDatumAnbieten;')(
        { getElementById: id => felder[id] }, rechnungen);
    const sammel = [{ id: 1, invoice_document_id: 7 }, { id: 2, invoice_document_id: 7 },
                    { id: 3, invoice_document_id: 8 }];

    bau(sammel)();
    pruefe('Phase 64: am Sammelbeleg erscheint der Haken, er ist nie vorbelegt',
        !felder['invoice-datum-beleg-zeile'].hidden && !felder['invoice-datum-fuer-beleg'].checked
        && felder['invoice-datum-beleg-anzahl'].textContent.includes('2'));
    felder['invoice-id'].value = '1';
    bau(sammel)();
    pruefe('Phase 64: beim Bearbeiten zählt die eigene Rechnung nicht mit',
        !felder['invoice-datum-beleg-zeile'].hidden
        && felder['invoice-datum-beleg-anzahl'].textContent === 'die andere Rechnung');
    felder['invoice-document-id'].value = '8';
    felder['invoice-id'].value = '3';
    bau(sammel)();
    pruefe('Phase 64: allein auf dem Beleg gibt es keinen Haken',
        felder['invoice-datum-beleg-zeile'].hidden);
    felder['invoice-document-id'].value = '';
    bau(sammel)();
    pruefe('Phase 64: ohne Beleg gibt es keinen Haken', felder['invoice-datum-beleg-zeile'].hidden);

    const umschalter = appQuelle.match(/function toggleInvoiceFileUpload\(\) \{[\s\S]*?\n\}/)[0];
    const speichern = appQuelle.match(/async function saveInvoice\(\) \{[\s\S]*?\n\}/)[0];
    pruefe('Phase 64: der Haken folgt dem gewählten Beleg und geht mit dem Speichern',
        umschalter.includes('belegDatumAnbieten()')
        && /rechnungsdatum_fuer_beleg/.test(speichern)
        && /beleg_datum_gesetzt/.test(speichern));
}

// Phase 65 (Issue #35, Nachtrag): lange Namen in Auswahlfeldern enden mit „…".
// Chromium bindet nur das erste <selectedcontent> eines Feldes. Schreibt die App
// die Optionen per innerHTML neu, muss derselbe Knopf zurück, ein neuer bliebe leer.
async function auswahlKnoepfePruefen() {
    const m = appQuelle.match(/function auswahlKnoepfe\(wurzel\) \{[\s\S]*?\n\}/);
    if (!m) throw new Error('auswahlKnoepfe nicht gefunden');
    const feld = { kinder: [], style: { display: '' }, offsetHeight: 0,
        querySelector() { return this.kinder[0] || null; },
        prepend(k) { this.kinder.unshift(k); } };
    const dok = { createElement: tag => ({ tag, append() {} }) };
    const lauf = new Function('CSS', 'document', m[0] + '; return auswahlKnoepfe;')(
        { supports: () => true }, dok);
    const wurzel = { querySelectorAll: () => [feld] };
    lauf(wurzel);
    const erster = feld.kinder[0];
    pruefe('Phase 65: das Auswahlfeld bekommt einen Knopf', erster && erster.tag === 'button');
    feld.kinder = [];   // wie innerHTML = '<option>…'
    lauf(wurzel);
    pruefe('Phase 65: nach innerHTML kommt derselbe Knopf zurück, kein neuer',
        feld.kinder[0] === erster && feld.kinder.length === 1);
    lauf(wurzel);
    pruefe('Phase 65: ein vorhandener Knopf wird nicht doppelt eingesetzt', feld.kinder.length === 1);
    pruefe('Phase 65: der Beobachter setzt die Knöpfe nach',
        (appQuelle.match(/auswahlKnoepfe\(document\)/g) || []).length >= 2);
    pruefe('Phase 65: der Knopf kürzt mit „…", die offene Liste bricht um',
        /select > button\.auswahl-knopf \{[^}]*text-overflow: ellipsis/.test(css)
        && /::picker\(select\) \{[^}]*max-width:/.test(css)
        && /\n    option \{[^}]*white-space: normal/.test(css));
}

async function fluchtPruefen() {
    // Jede Zeile der Zeitleiste ist ein eigenes Grid: „auto“-Spalten richten sich
    // nach dem Inhalt der Zeile, und Ort und Symbol springen von Zeile zu Zeile.
    const spalten = [...css.matchAll(/\.zeitleiste-eintrag \{[^}]*grid-template-columns: ([^;]+);/g)].map(t => t[1]);
    pruefe('Phase 66: die Zeitleiste hat in jeder Breite feste Spalten für Beleg und Betrag',
        spalten.length >= 2 && spalten.every(w => !/\bauto\b/.test(w)));
    pruefe('Phase 66: Jahres- und Gesamtsumme fluchten mit den Karten',
        /\.zeitleiste-jahr,\s*\.zeitleiste-gesamt \{[^}]*padding-inline:/.test(css));
    // Eine Haken-Zeile ist flex: lose Textstücke neben einem Element werden zu
    // eigenen Spalten. Der Text gehört in genau ein Element.
    const labels = [...(html + appQuelle).matchAll(/<label class="haken-zeile"[^>]*>([\s\S]*?)<\/label>/g)];
    const krumm = labels.map(t => t[1].replace(/<input[^>]*>/, '').trim())
        .filter(t => /</.test(t) && !/^<span>[\s\S]*<\/span>$/.test(t));
    pruefe('Phase 66: der Text einer Haken-Zeile steht in einem Stück', labels.length >= 3 && krumm.length === 0,
        krumm.join(' | '));
}

async function zeitleisteBelegPruefen() {
    const zeile = (appQuelle.match(/function zeitleisteEintragZeile[\s\S]*?\n\}/) || [''])[0];
    pruefe('Phase 67: das PDF-Symbol der Zeitleiste öffnet den Beleg wie in der Liste',
        /docUrl = dateiAdresse\('rechnung', e\.id\)/.test(zeile) && /#page=/.test(zeile)
        && /<a href="\$\{docUrl\}"/.test(zeile));
}

async function zeitleisteFilterPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const felder = {};
    const dokument = { getElementById: id => felder[id] };
    const bau = new Function('document', 'hausFilter',
        funktion('zeitleisteAdresse') + '; return { zeitleisteAdresse };');

    let fns = bau(dokument, null);
    pruefe('Phase 62: ohne Filter holt die Zeitleiste den ganzen Bestand',
        fns.zeitleisteAdresse() === '/api/invoices/zeitleiste');

    Object.assign(felder, {
        'invoice-jahr-filter': { value: '2024' },
        'invoice-category-filter': { value: 'Heizung' },
        'invoice-search': { value: '  Stadtwerke ' },
    });
    fns = bau(dokument, { id: 7 });
    const adresse = new URL(fns.zeitleisteAdresse(), 'http://x');
    pruefe('Phase 62: die Zeitleiste fragt mit Immobilie, Jahr, Kostenart und Suche',
        adresse.pathname === '/api/invoices/zeitleiste'
        && adresse.searchParams.get('property_id') === '7'
        && adresse.searchParams.get('jahr') === '2024'
        && adresse.searchParams.get('kategorie') === 'Heizung'
        && adresse.searchParams.get('suche') === 'Stadtwerke');

    // 0.17.0-Review B2: der Filter zählt nach Rechnungsdatum, der
    // Leistungszeitraum liegt meist ein Jahr davor -- keine Vorbelegung.
    pruefe('0.17.0: der Jahresfilter belegt keinen Leistungszeitraum vor',
        !/invoice-jahr-filter/.test(funktion('openAddInvoiceModal'))
        && !/invoice-jahr-filter/.test(funktion('oeffneRechnungstabelle')));

    // Ein Schein-<select>: options, remove, appendChild, value.
    const feld = {
        options: [{ value: '' }], value: '',
        remove(i) { this.options.splice(i, 1); },
        appendChild(o) { this.options.push(o); },
    };
    const auffuellen = new Function('document', funktion('auswahlNachBestand') + '; return auswahlNachBestand;')(
        { createElement: () => ({}) });
    auffuellen(feld, ['2025', '2024'], j => j);
    feld.value = '2024';
    auffuellen(feld, ['2026', '2025', '2024'], j => j);
    pruefe('Phase 62: ein neues Jahr erscheint, die Wahl bleibt',
        feld.options.map(o => o.value).join() === ',2026,2025,2024' && feld.value === '2024');
    auffuellen(feld, ['2023'], j => j);
    pruefe('Phase 62: eine Wahl ohne Bestand bleibt sichtbar stehen, statt still zu verschwinden',
        feld.options.map(o => o.value).join() === ',2023,2024' && feld.value === '2024');

    const zeichnen = funktion('renderInvoices');
    pruefe('Phase 62: renderInvoices zieht die sichtbare Zeitleiste nach',
        /if \(zeitleisteSichtbar\(\)\) zeitleisteNachladen\(\)/.test(zeichnen));
    const umschalter = appQuelle.match(/async function zeigeInvoiceZeitleiste\(\) \{[\s\S]*?\n\}/)[0];
    pruefe('Phase 62: die Filterleiste bleibt in der Zeitleiste stehen',
        !/invoice-filter'\)\.style\.display = 'none'/.test(umschalter));
}

// Phase 58 (Issue #35, Punkt 1): die Anschriften im Mieterdialog und in den
// Einstellungen. Der Fehler, der hier wehtut, ist der Rest aus dem vorigen
// Mieter: Wer den Dialog fuellt, aber nicht raeumt, schickt die Abrechnung
// an die Adresse des Vormieters. Deshalb wird der Dialog zweimal gefahren --
// einmal mit Mieter, einmal ohne.
async function anschriftenPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };

    const feldStube = () => {
        const felder = {};
        return {
            felder,
            dokument: {
                getElementById(id) {
                    if (!felder[id]) felder[id] = { value: '', textContent: '', style: {} };
                    return felder[id];
                },
            },
        };
    };
    const fenster = { classList: { add() {}, remove() {} }, querySelector: () => ({ textContent: '' }) };

    const dialog = funktion('openAddTenantModal');
    const fahre = mieter => {
        const stube = feldStube();
        new Function('document', 'tenantModal', 'setTimeout', 'editingTenantId', 'mieter',
            dialog + '\nopenAddTenantModal(mieter);')(
            stube.dokument, fenster, () => {}, null, mieter);
        return stube.felder;
    };

    const bestand = fahre({
        id: 7, name: 'Mieter Muster', apartment_id: 1,
        move_in_date: '2025-01-01', move_out_date: '2025-12-31',
        anschrift: 'Musterweg 1\n12345 Musterstadt',
        zustellanschrift: 'Neue Straße 9\n54321 Anderswo',
    });
    pruefe('Phase 58: der Mieterdialog zeigt beide Anschriften des Mieters',
        bestand['tenant-anschrift'].value === 'Musterweg 1\n12345 Musterstadt'
        && bestand['tenant-zustellanschrift'].value === 'Neue Straße 9\n54321 Anderswo');

    const leer = fahre(null);
    pruefe('Phase 58: „Neuer Mieter" raeumt beide Anschriften -- kein Rest vom Vormieter',
        leer['tenant-anschrift'].value === ''
        && leer['tenant-zustellanschrift'].value === '');

    // Immer mitschicken: nur so laesst sich eine Anschrift wieder leeren.
    const speichern = appQuelle.match(/const formData = new FormData\(\);[\s\S]*?fetch\(url/)[0];
    pruefe('Phase 58: beide Anschriften gehen immer mit, auch leer',
        /formData\.append\('anschrift', document\.getElementById\('tenant-anschrift'\)\.value\)/.test(speichern)
        && /formData\.append\('zustellanschrift', document\.getElementById\('tenant-zustellanschrift'\)\.value\)/.test(speichern)
        && !/if \([a-zA-Z]+\) formData\.append\('anschrift'/.test(speichern));
    // Befund vom 17.11.: dasselbe fuer den Auszug -- nur so laesst er sich entfernen.
    pruefe('Mieterdialog: das Auszugsdatum geht immer mit, auch leer',
        /formData\.append\('move_out_date', moveOut\)/.test(speichern)
        && !/if \(moveOut\) formData\.append/.test(speichern));

    const laden = funktion('fetchVermieterdaten');
    const sichern = funktion('saveVermieterdaten');
    pruefe('Phase 58: die Einstellungen laden und speichern die eigene Anschrift',
        /vermieter-anschrift'\)\.value = stand\.anschrift/.test(laden)
        && /vermieter-anschrift'\)\.value/.test(sichern)
        && /JSON\.stringify\(\{ name, iban, art, anschrift \}\)/.test(sichern));

    // Die Felder selbst -- mehrzeilig, weil eine Anschrift mehrzeilig ist.
    pruefe('Phase 58: die drei Felder stehen mehrzeilig in der Oberflaeche',
        /<textarea id="tenant-anschrift"/.test(html)
        && /<textarea id="tenant-zustellanschrift"/.test(html)
        && /<textarea id="vermieter-anschrift"/.test(html));

    pruefe('Phase 58: die Zustelladresse nennt den Grund (§ 556 Abs. 3 BGB)',
        /Zustelladresse ab Auszug/.test(html) && /556 Abs. 3 BGB/.test(html));
}

// Phase 54 (Issue #30): eigene Kostenarten — Tabelle, Nummernvorschlag,
// Nummernmenü und die Nr.-17-Bestätigung, vom Quelltext her geprüft.
async function kategorienPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const quelltext =
        'const KATEGORIE_VERTEILUNGEN = [["qm","Umlage nach Wohnfläche"],["personen","Umlage nach Personen"],["direkt","Nach Verbrauch (eigener Zähler)"],["nur_allgemein","Nur Anteil am Allgemeinverbrauch"],["ignoriert","Wird diesem Mieter nicht berechnet"]];'
        + 'let katalogHilfe = null; let letzteKategorien = [];'
        + funktion('ladeKatalogHilfe') + funktion('nummernVorschlag')
        + funktion('ladeKostenarten') + funktion('kategorieZeile')
        + funktion('openKategorieModal') + funktion('closeKategorieModal') + funktion('saveKategorie');
    const lauf = (felder, antworten) => {
        const aufrufe = [];
        const meldungen = [];
        const dokument = {
            getElementById(id) {
                if (!(id in felder)) felder[id] = { value: '', innerHTML: '', textContent: '', hidden: false, checked: false, dataset: {}, classList: { add() {}, remove() {} } };
                if (!felder[id].dataset) felder[id].dataset = {};
                if (!felder[id].classList) felder[id].classList = { add() {}, remove() {} };
                return felder[id];
            },
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            const daten = antworten.shift() ?? {};
            return Promise.resolve({ ok: true, json: () => Promise.resolve(daten) });
        };
        const fns = new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
            'escapeHtml', 'frage',
            quelltext + '; return { ladeKostenarten, nummernVorschlag, openKategorieModal, saveKategorie };')(
            dokument, holen, m => meldungen.push(m), async () => new Error('Server'),
            (e, ersatz) => ersatz, t => String(t).replace(/</g, '&lt;').replace(/>/g, '&gt;'),
            async () => true);
        return { fns, aufrufe, meldungen, felder };
    };

    const hilfe = {
        vorschlaege: [['hauswart', 14], ['aufzug', 7], ['muell', 8], ['warmwasser', 5]],
        heizstichwoerter: ['warmwasser', 'heiz'],
        nummern: [[1, 'Grundsteuer'], [4, 'Heizung'], [14, 'Kosten für den Hauswart'], [17, 'sonstige Betriebskosten']],
    };

    const vorschlag = lauf({}, []);
    pruefe('Phase 54: der Nummernvorschlag schlägt vor, ohne zu überschreiben — und versagt bei Heiz-Namen',
        vorschlag.fns.nummernVorschlag('Hauswart', hilfe) === 14
        && vorschlag.fns.nummernVorschlag('Aufzugswartung', hilfe) === 7
        && vorschlag.fns.nummernVorschlag('Müllabfuhr', hilfe) === 8
        && vorschlag.fns.nummernVorschlag('Heizkosten', hilfe) === null
        && vorschlag.fns.nummernVorschlag('Eigenbrötlerei', hilfe) === null
        && vorschlag.fns.nummernVorschlag('', hilfe) === null);

    const leer = lauf({}, [[]]);
    await leer.fns.ladeKostenarten();
    pruefe('Phase 54: ohne eigene Kostenart ein Hinweis statt einer leeren Tabelle',
        leer.aufrufe[0].url === '/api/categories'
        && /Noch keine eigene Kostenart/.test(leer.felder['kategorien-liste'].innerHTML));

    const liste = lauf({}, [[{ id: 3, name: 'Hauswart <b>x</b>', betrkv_nr: 14, betrkv_bezeichnung: 'Kosten für den Hauswart', allocation_method: 'qm', requires_meter: true, rechnungen: 2, zaehler_anzahl: 1 }]]);
    await liste.fns.ladeKostenarten();
    pruefe('Phase 54: die Tabelle zeigt Nummer, amtliche Bezeichnung und Zähler — und maskiert den Namen',
        liste.felder['kategorien-liste'].innerHTML.includes('&lt;b&gt;x&lt;/b&gt;')
        && /Nr\. 14 · Kosten für den Hauswart/.test(liste.felder['kategorien-liste'].innerHTML)
        && !/Umlage nach Wohnfläche/.test(liste.felder['kategorien-liste'].innerHTML)
        && /Zähler \(1\)/.test(liste.felder['kategorien-liste'].innerHTML)
        && liste.felder['kategorien-liste'].innerHTML.includes('openKategorieModal(3)')
        && liste.felder['kategorien-liste'].innerHTML.includes('loescheKategorie(3)'));

    const modal = lauf({}, [hilfe]);
    await modal.fns.openKategorieModal(null);
    modal.felder['kategorie-name'].oninput({ target: { value: 'Müllabfuhr' } });
    const vorschlagen = modal.felder['kategorie-nr'].value;
    modal.felder['kategorie-name'].oninput({ target: { value: 'Heizkosten' } });
    const keinHeizVorschlag = modal.felder['kategorie-nr'].value;
    modal.felder['kategorie-nr'].value = '8';
    modal.felder['kategorie-nr'].dataset.gewaehlt = '1';
    modal.felder['kategorie-name'].oninput({ target: { value: 'Gartenpflege' } });
    pruefe('Phase 54: das Nummernmenü kommt aus betrkv, gesperrte Nummern sind disabled, der Vorschlag überschreibt keine gewählte Nummer',
        vorschlagen === '8'
        && keinHeizVorschlag === ''
        && modal.felder['kategorie-nr'].value === '8'
        && modal.felder['kategorie-nr'].innerHTML.includes('Nr. 14 · Kosten für den Hauswart')
        && /value="4" disabled>Nr\. 4 · Heizung \(gesperrt\)/.test(modal.felder['kategorie-nr'].innerHTML));

    const leerName = lauf({ 'kategorie-name': { value: '  ' } }, []);
    await leerName.fns.saveKategorie();
    const ohneNummer = lauf({ 'kategorie-name': { value: 'Gartenpflege' }, 'kategorie-nr': { value: '' } }, []);
    await ohneNummer.fns.saveKategorie();
    pruefe('Phase 54: ohne Name und ohne Nummer geht nichts hinaus',
        leerName.aufrufe.length === 0 && leerName.meldungen.length === 1
        && ohneNummer.aufrufe.length === 0 && ohneNummer.meldungen.length === 1);

    const sonstige = lauf({ 'kategorie-name': { value: 'Eigenbrötlerei' }, 'kategorie-nr': { value: '17' }, 'kategorie-zaehler': { checked: false } }, [{}, []]);
    await sonstige.fns.saveKategorie();
    const koerper = sonstige.aufrufe.length === 2 ? JSON.parse(sonstige.aufrufe[0].koerper) : {};
    pruefe('Phase 54: Nr. 17 geht nur mit Bestätigung (R-KAT-02) hinaus',
        sonstige.aufrufe.length === 2 && sonstige.aufrufe[0].url === '/api/categories'
        && sonstige.aufrufe[0].methode === 'POST' && koerper.betrkv_nr === 17
        && koerper.name === 'Eigenbrötlerei' && koerper.allocation_method === undefined);

    const aenderung = lauf({ 'kategorie-id': { value: '4' }, 'kategorie-name': { value: 'Quartierservice' }, 'kategorie-nr': { value: '14' }, 'kategorie-zaehler': { checked: false } }, [{}, []]);
    await aenderung.fns.saveKategorie();
    pruefe('Phase 54: das Bearbeiten geht als PUT mit der Nummer hinaus',
        aenderung.aufrufe.length === 2 && aenderung.aufrufe[0].url === '/api/categories/4'
        && aenderung.aufrufe[0].methode === 'PUT'
        && JSON.parse(aenderung.aufrufe[0].koerper).name === 'Quartierservice');
}

async function fristenPruefen() {
    const m = appQuelle.match(/async function ladeFristen\(\) \{[\s\S]*?\n\}/);
    if (!m) throw new Error('ladeFristen nicht gefunden');
    const lauf = async (antwort) => {
        const liste = { innerHTML: '' };
        const aufrufe = [];
        const holen = url => {
            aufrufe.push(url);
            return Promise.resolve({ ok: antwort !== null, json: () => Promise.resolve(antwort) });
        };
        await new Function('document', 'fetch', 'serverFehler', 'meldungZu', 'escapeHtml', 'datumText',
            m[0] + '; return ladeFristen();')(
            { getElementById: id => (id === 'fristen-liste' ? liste : null) }, holen,
            async () => new Error('Server'), (e, ersatz) => ersatz,
            t => String(t).replace(/</g, '&lt;'), iso => 'D' + iso);
        return { liste: liste.innerHTML, aufrufe };
    };
    const voll = await lauf({ termine: [
        { datum: '2025-04-01', art: 'vorauszahlung', titel: 'Neue <b>Vorauszahlung', uid: 'v-1@n' },
        { datum: '2025-12-31', art: 'eichfrist', titel: 'Eichfrist endet: W', uid: 'e-1@n' },
    ] });
    pruefe('NK-262: Termine in Reihenfolge, Datum formatiert, Titel maskiert',
        voll.aufrufe[0] === '/api/fristen'
        && voll.liste.indexOf('D2025-04-01') < voll.liste.indexOf('D2025-12-31')
        && voll.liste.includes('Neue &lt;b>Vorauszahlung') && !voll.liste.includes('<b>'));
    const leer = await lauf({ termine: [] });
    pruefe('NK-262: ohne Termine ein Hinweis statt einer leeren Liste',
        /Keine anstehenden Termine/.test(leer.liste));
    const kaputt = await lauf(null);
    pruefe('NK-262: Ladefehler bleibt in der Karte',
        /ließen sich nicht laden/.test(kaputt.liste));
    pruefe('NK-262: Karte mit Download-Link, die Datenqualität lädt die Fristen',
        html.includes('id="fristen-karte"') && html.includes('href="/api/fristen.ics" download')
        && /viewDQ\.style\.display = 'flex';\s*ladeFristen\(\);/.test(appQuelle));
}

// --- NK-263: Mehrjahresblick je Wohnung --------------------------------------
async function mehrjahresblickPruefen() {
    const m = appQuelle.match(/function renderMehrjahresblick\(jahre\) \{[\s\S]*?\n\}/);
    if (!m) throw new Error('renderMehrjahresblick nicht gefunden');
    const lauf = (jahre) => {
        const el = { 'mjb-kopf': { innerHTML: 'alt' }, 'mjb-zeilen': { innerHTML: '' } };
        new Function('document', 'escapeHtml', 'euroText', m[0] + '; renderMehrjahresblick(arguments[3]);')(
            { getElementById: id => el[id] }, t => String(t).replace(/</g, '&lt;'), b => 'E' + b, jahre);
        return { kopf: el['mjb-kopf'].innerHTML, zeilen: el['mjb-zeilen'].innerHTML };
    };
    const voll = lauf([
        { jahr: '2023/24', belegte_tage: 366, jahrestage: 366, je_qm: { '<b>Wasser': '10.00' },
          je_qm_gesamt: '10.00', vorauszahlung: '700.00' },
        { jahr: '2024/25', belegte_tage: 0, jahrestage: 365, je_qm: {}, je_qm_gesamt: null,
          vorauszahlung: '0.00' },
    ]);
    pruefe('NK-263: Jahre als Spalten in Reihenfolge, Kostenart maskiert',
        voll.kopf.indexOf('2023/24') < voll.kopf.indexOf('2024/25')
        && voll.zeilen.includes('&lt;b>Wasser') && !voll.zeilen.includes('<b>'));
    pruefe('NK-263: Werte, Gesamt und Vorauszahlung, das leere Jahr als Lücke',
        voll.zeilen.includes('E10.00') && voll.zeilen.includes('E700.00')
        && voll.zeilen.includes('366 von 366 Tagen') && voll.zeilen.includes('>leer<')
        && /Gesamt<\/th><td[^>]*>E10\.00<\/td><td[^>]*>–</.test(voll.zeilen));
    const leer = lauf([]);
    pruefe('NK-263: ohne Abrechnung ein Hinweis, der alte Kopf verschwindet',
        leer.kopf === '' && /Noch keine Abrechnung/.test(leer.zeilen));
    pruefe('NK-263: Karte in der Wohnungsansicht, die Auswertung füllt sie',
        html.includes('id="mehrjahresblick-karte"')
        && /renderAptCostsChart\(dataA\.cost_distribution\);\s*renderMehrjahresblick\(dataA\.mehrjahresblick\);/.test(appQuelle));
}

// --- NK-267: Jahreswechsel als geführter Ablauf --------------------------------
// Der Block läuft mit einer Attrappe aus Elementen, Speicher und den
// vorhandenen Wegen (Ablesen, Details, Vorjahr); geprüft werden Ablauf,
// Abbrechen und Wiederaufnehmen.
async function jahreswechselPruefen() {
    const m = appQuelle.match(/\n\/\/ --- NK-267[\s\S]*?(?=\n\/\/ --- )/);
    if (!m) throw new Error('NK-267-Block nicht gefunden');
    const element = () => ({ value: '', innerHTML: '', textContent: '', hidden: false, checked: false,
        disabled: false, dataset: {}, attr: {}, klassen: new Set(),
        get classList() {
            const k = this.klassen;
            return { add: n => k.add(n), remove: n => k.delete(n), contains: n => k.has(n),
                     toggle: (n, an) => (an ? k.add(n) : k.delete(n)) };
        },
        setAttribute(n, w) { this.attr[n] = w; }, removeAttribute(n) { delete this.attr[n]; } });
    const seite = (speicher, haeuser) => {
        const el = {};
        const abschnitte = [1, 2, 3, 4].map(n => Object.assign(element(), { dataset: { jwSchritt: String(n) } }));
        const punkte = [1, 2, 3, 4].map(n => Object.assign(element(), { dataset: { schritt: String(n) } }));
        const aufrufe = [];
        const document = {
            getElementById: id => (el[id] = el[id] || element()),
            querySelectorAll: sel => sel === '[data-jw-schritt]' ? abschnitte : sel === '#jw-schritte li' ? punkte : [],
        };
        const berichte = [
            { id: 1, tenant_id: 7, property_id: 5, tenant_name: 'A', apartment_name: 'EG', start_date: '2024-01-01', end_date: '2024-12-31' },
            { id: 2, tenant_id: 7, property_id: 5, tenant_name: 'A', apartment_name: 'EG', start_date: '2025-01-01', end_date: '2025-12-31' },
            { id: 3, tenant_id: 8, property_id: 5, tenant_name: '<b>B', apartment_name: 'OG', start_date: '2025-01-01', end_date: '2025-12-31' },
            { id: 4, tenant_id: 9, property_id: 6, tenant_name: 'C', apartment_name: 'DG', start_date: '2025-01-01', end_date: '2025-12-31' },
        ];
        const umgebung = {
            document, localStorage: speicher, window: {}, properties: haeuser,
            fetchProperties: async () => {}, showError: t => aufrufe.push('fehler:' + t),
            escapeHtml: t => String(t).replace(/</g, '&lt;'), datumText: iso => 'D' + iso,
            fetch: async () => ({ ok: true, json: async () => berichte }),
            serverFehler: async () => new Error('x'), meldungZu: (e, t) => t,
            openAblesen: () => aufrufe.push('ablesen'), ablesenListe: () => aufrufe.push('liste'),
            openReportDetails: id => aufrufe.push('details:' + id),
            rechnungenWieVorjahr: async (haus, jahr) => aufrufe.push(`vorjahr:${haus}:${jahr}`),
        };
        const namen = Object.keys(umgebung);
        const f = new Function(...namen, m[0] + `; return { oeffneJahreswechsel, jwAuswahl, jwSchritt, jwHaken,
            jwAblesen, jwVorjahr, jwAbbrechen, jwAbschliessen };`)(...namen.map(n => umgebung[n]));
        const sichtbar = () => abschnitte.filter(a => !a.hidden).map(a => a.dataset.jwSchritt).join();
        return { f, el, aufrufe, sichtbar, punkte, offen: () => el['jahreswechsel-modal'].klassen.has('active') };
    };
    const speicher = () => { const d = {}; return { d, getItem: k => (k in d ? d[k] : null),
        setItem: (k, w) => { d[k] = String(w); }, removeItem: k => { delete d[k]; } }; };
    const warte = () => new Promise(r => setTimeout(r, 0));
    const haeuser = [{ id: 5, name: 'Haus A', abrechnungsjahr_beginn: '01.07.' }, { id: 6, name: 'Haus B' }];
    const jahr = new Date().getFullYear();

    const sp = speicher();
    const a = seite(sp, haeuser);
    await a.f.oeffneJahreswechsel();
    a.f.jwAblesen();
    pruefe('NK-267: Start bei Schritt 1, Ablesen zum Tag vor dem Jahresbeginn',
        a.offen() && a.sichtbar() === '1' && a.el['jw-wieder'].hidden
        && a.aufrufe.join() === 'ablesen,liste' && a.el['ablesen-property'].value === '5'
        && a.el['ablesen-datum'].value === `${jahr}-06-30` && a.el['jw-stichtag'].textContent === `D${jahr}-06-30`
        && a.el['jw-zurueck'].disabled && a.punkte[0].attr['aria-current'] === 'step');
    a.f.jwHaken('ablesen', true);
    a.f.jwSchritt(1);
    await warte();
    const liste = a.el['jw-abrechnungen'].innerHTML;
    pruefe('NK-267: Schritt 2 zeigt je Mieter der Immobilie die letzte Abrechnung',
        a.sichtbar() === '2' && a.punkte[0].klassen.has('erledigt')
        && liste.includes('openReportDetails(2)') && liste.includes('openReportDetails(3)')
        && !liste.includes('openReportDetails(1)') && !liste.includes('openReportDetails(4)')
        && liste.includes('&lt;b>B') && !liste.includes('<b>'));
    a.f.jwSchritt(1);
    await a.f.jwVorjahr();
    pruefe('NK-267: Schritt 3 füllt die Rechnungen des neuen Jahres wie im Vorjahr',
        a.sichtbar() === '3' && a.aufrufe.includes(`vorjahr:5:${jahr}`));
    a.f.jwAbbrechen();
    const gemerkt = JSON.parse(sp.d['nk-jahreswechsel'] || '{}');
    pruefe('NK-267: Abbrechen schließt den Dialog und behält den Stand',
        !a.offen() && gemerkt.schritt === 3 && gemerkt.erledigt.ablesen === true);

    const b = seite(sp, haeuser);
    await b.f.oeffneJahreswechsel();
    pruefe('NK-267: Wiederaufnehmen nach dem Neuladen an derselben Stelle',
        b.offen() && b.sichtbar() === '3' && !b.el['jw-wieder'].hidden
        && b.el['jw-erledigt-ablesen'].checked && !b.el['jw-erledigt-vorjahr'].checked
        && b.el['jw-immobilie'].value === '5');
    b.f.jwSchritt(1);
    const check = b.el['jw-checkliste'].innerHTML;
    pruefe('NK-267: Checkliste mit Erledigtem und dem Weg zurück zu Offenem',
        b.sichtbar() === '4' && b.el['jw-weiter'].hidden && !b.el['jw-fertig'].hidden
        && /class="erledigt"[^<]*<i[^>]*><\/i> Zähler zum Stichtag abgelesen/.test(check)
        && check.includes('jwGehe(2)') && check.includes('jwGehe(3)') && !check.includes('jwGehe(1)'));
    b.f.jwAbschliessen();
    const verworfen = !('nk-jahreswechsel' in sp.d);
    const c = seite(sp, haeuser);
    await c.f.oeffneJahreswechsel();
    pruefe('NK-267: Schließen verwirft den Stand, der nächste Wechsel beginnt vorn',
        verworfen && !b.offen() && c.sichtbar() === '1' && c.el['jw-wieder'].hidden);

    c.f.jwHaken('ablesen', true);
    c.el['jw-immobilie'].value = '6';
    c.f.jwAuswahl();
    const verloren = speicher();
    verloren.d['nk-jahreswechsel'] = JSON.stringify({ property_id: '99', jahr, schritt: 3, erledigt: {} });
    const d = seite(verloren, haeuser);
    await d.f.oeffneJahreswechsel();
    const gesperrt = { getItem() { throw new Error('gesperrt'); }, setItem() { throw new Error('gesperrt'); },
        removeItem() { throw new Error('gesperrt'); } };
    const e = seite(gesperrt, haeuser);
    await e.f.oeffneJahreswechsel();
    e.f.jwSchritt(1);
    e.f.jwAbschliessen();
    pruefe('NK-267: neue Auswahl beginnt neu, fremder oder gesperrter Speicher stört nicht',
        c.sichtbar() === '1' && !c.el['jw-erledigt-ablesen'].checked && JSON.parse(sp.d['nk-jahreswechsel']).property_id === '6'
        && d.sichtbar() === '1' && d.el['jw-immobilie'].value === '5'
        && e.sichtbar() === '2' && !e.offen());
    pruefe('NK-267: Dialog und Einstieg neben „Jahr abrechnen“',
        html.includes('id="jahreswechsel-modal"')
        && /onclick="oeffneJahreswechsel\(\)"[^>]*>[\s\S]{0,80}Jahreswechsel öffnen\s*<\/button>/.test(html));
}

// --- NK-265: Prüfstand vor dem Festsetzen -------------------------------------
// Der Block läuft mit der echten Kappung (D-116) und Attrappen der Öffner;
// geprüft werden Seite, Knöpfe und dass jeder Knopf die richtige Stelle öffnet.
async function pruefstandPruefen() {
    const m = appQuelle.match(/\n\/\/ --- NK-265[\s\S]*?(?=\n\/\/ --- )/);
    const kappen = appQuelle.match(/function hinweiseKappen\(zeilen\) \{[\s\S]*?\n\}/);
    const anzahl = appQuelle.match(/function anzahlText\([^)]*\) \{[\s\S]*?\n\}/);
    if (!m || !kappen || !anzahl) throw new Error('NK-265-Block oder Helfer nicht gefunden');
    const seite = (befunde) => {
        const el = {};
        const aufrufe = [];
        const umgebung = {
            document: { getElementById: id => (el[id] = el[id] || { value: '', innerHTML: '' }) },
            window: {}, jahrStand: { pruefstand: befunde }, jahrAktuell: 5,
            jahrZeigen: () => aufrufe.push('zeigen'),
            escapeHtml: t => String(t).replace(/</g, '&lt;'),
            openAddInvoiceModal: id => aufrufe.push('rechnung:' + id),
            openHistoryModal: id => aufrufe.push('zaehler:' + id),
            openAddReadingModal: id => aufrufe.push('ablesung:' + id),
            openAddTenantModal: () => aufrufe.push('mieter'),
            openAddPaymentModal: () => aufrufe.push('zahlung'),
            toggleBillingReportField: () => aufrufe.push('umschalten'),
        };
        const namen = Object.keys(umgebung);
        const f = new Function(...namen, kappen[0] + anzahl[0] + m[0]
            + '; return { jahrPruefstandZeigen, jahrPruefstandOeffnen, schritt: () => jahrAktuell };')(
            ...namen.map(n => umgebung[n]));
        f.jahrPruefstandZeigen();
        return { f, el, aufrufe, html: () => el['jahr-pruefstand'].innerHTML };
    };
    const befund = (art, aktion, id) => ({ art, text: `<b>${art}`, tun: `Prüfen Sie ${art}.`, ziel: { aktion, id } });
    const alle = [befund('kosten_je_qm', 'rechnungen', null), befund('zaehlersprung', 'zaehler', 11),
        befund('ohne_beleg', 'rechnung', 21), befund('wechsel_ablesung', 'ablesung', 12),
        befund('leerstand', 'mieter', 31), befund('ohne_vorauszahlung', 'zahlung', 41)];
    const voll = seite(alle);
    const liste = voll.html();
    const sichtbar = liste.split('<details')[0];
    pruefe('NK-265: drei Warnungen sichtbar, drei aufklappbar, Text maskiert, blockiert nichts',
        (sichtbar.match(/jahrPruefstandOeffnen\(/g) || []).length === 3
        && /<summary>3 weitere Hinweise<\/summary>/.test(liste)
        && liste.includes('6 Hinweise vor dem Festsetzen') && liste.includes('Sie können trotzdem festsetzen')
        && liste.includes('&lt;b>leerstand') && !liste.includes('<b>')
        && (liste.match(/<strong>Was tun:<\/strong>/g) || []).length === 6);
    pruefe('NK-265: jede Warnung hat ihren Knopf',
        ['Rechnungen prüfen', 'Zählerstände ansehen', 'Rechnung öffnen', 'Ablesung erfassen',
         'Mieter erfassen', 'Zahlung erfassen'].every(k => liste.includes(`>${k}</button>`)));
    alle.forEach((_, i) => voll.f.jahrPruefstandOeffnen(i));
    pruefe('NK-265: jeder Knopf öffnet die Stelle, die die Warnung behebt',
        voll.f.schritt() === 2
        && voll.aufrufe.join() === 'zeigen,zaehler:11,rechnung:21,ablesung:12,mieter,zahlung,umschalten'
        && voll.el['tenant-apartment'].value === '31' && voll.el['payment-tenant'].value === '41'
        && voll.el['payment-type'].value === 'Nebenkostenvorauszahlung');
    const eine = seite([alle[2]]).html();
    pruefe('NK-265: eine Warnung in der Einzahl, ohne Aufklappen',
        eine.includes('1 Hinweis vor dem Festsetzen') && !eine.includes('<details'));
    const leer = seite([]).html();
    pruefe('NK-265: ohne Befund die Entwarnung',
        /nichts Auffälliges/.test(leer) && !leer.includes('<li'));
    pruefe('NK-265: Prüfstand in Schritt 5, beim Laden und beim Schritt auf 5 gefüllt',
        /data-jahr-schritt="5"[\s\S]{0,300}id="jahr-pruefstand"/.test(html)
        && /jahrFristZeigen\(\);\s*jahrPruefstandZeigen\(\);/.test(appQuelle)
        && /richtung > 0 && jahrAktuell === 4\) await jahrNeuLaden\(\)/.test(appQuelle));
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

// --- NK-212: „Aktive Mieter“ zählt keine Ausgezogenen ---------------
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

// --- NK-219: Zählerliste mit Knopf „Verlauf“ und klarem Stift --------
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

// --- NK-257: Zähler ohne Ablesung bekommt „Ersten Stand erfassen“ ------
// Vorher fehlte der Stift ersatzlos; der erste Stand ging nur über den Kopf.
{
    const m = appQuelle.match(/function renderMeters\([\s\S]*?\n\}/);
    const r = m ? m[0] : '';
    pruefe('NK-257: ohne Ablesung der Knopf „Ersten Stand erfassen“ für diesen Zähler',
        /\} else \{[\s\S]*?ersterBtn\.innerHTML = '[^']*> Ersten Stand erfassen'[\s\S]*?ersterBtn\.onclick = \(\) => openAddReadingModal\(m\.id\)/.test(r));
    pruefe('NK-257: mit Ablesung bleibt der Stift',
        /if \(meterReadings\.length > 0\) \{[\s\S]*?editReadBtn[\s\S]*?\} else \{/.test(r));
}

// --- NK-220: die Einheit kommt vom Server, auch für die Heizung ------
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

// --- NK-221: „Zugestellt am“ startet leer -----------------------------
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

// --- NK-224: der Gruß steht fest im Kopf von „Heute“ ------
// Früher wurde ein globaler Gruß je Tab ein- und ausgeblendet; jetzt trägt
// nur der Seitenkopf von „Heute“ ihn, und die Leiste zeigt den Bereich.
pruefe('NK-224: der Gruß steht im Kopf von „Heute“ und nirgends sonst',
    html.indexOf('id="begruessung"') > html.indexOf('id="tab-dashboard"')
    && html.indexOf('id="begruessung"') < html.indexOf('id="erste-schritte"')
    && !html.includes('class="greeting"'));

// Klick auf einen Reiter schaltet den Leisteneintrag seines
// Bereichs aktiv; die Leiste öffnet die zuletzt gezeigte Seite des Bereichs.
{
    const quelle = (appQuelle.match(/function initTabs\(\)[\s\S]*?\n\}/) || [''])[0]
        + (appQuelle.match(/const letzteSeite = \{\};\nfunction zeigeBereich\([\s\S]*?\n\}/) || [''])[0];
    const element = (daten) => {
        const h = {}; const attr = {}; const klassen = new Set(daten.aktiv ? ['active'] : []);
        return { dataset: daten, hidden: false, style: {},
            classList: { add: k => klassen.add(k), remove: k => klassen.delete(k),
                toggle: (k, an) => an ? klassen.add(k) : klassen.delete(k), contains: k => klassen.has(k) },
            setAttribute: (k, v) => { attr[k] = v; }, removeAttribute: k => { delete attr[k]; },
            attr, addEventListener: (typ, fn) => { h[typ] = fn; },
            klick: () => h.click({ preventDefault() {} }) };
    };
    const reiter = [['dashboard', 'heute'], ['meters', 'haus'], ['tenants', 'haus'], ['invoices', 'kosten']]
        .map(([tab, gruppe]) => element({ tab, gruppe }));
    const leiste = ['heute', 'haus', 'kosten'].map(gruppe => element({ gruppe }));
    const unter = { hidden: true, querySelectorAll: () => reiter };
    const gewechselt = [];
    const init = quelle.includes('zeigeBereich') && new Function('document', 'wechsleZuTab',
        quelle + '; return initTabs;')({
        querySelectorAll: s => s === '.nav-item' ? reiter : s === '.leiste-eintrag' ? leiste
            : s === '.leiste-eintrag, .logo' ? leiste : [],
        querySelector: s => s === '.unter-reiter' ? unter
            : (s.match(/data-gruppe="(\w+)"/) ? reiter.find(r => r.dataset.gruppe === RegExp.$1) : null),
        getElementById: () => null,
    }, tab => gewechselt.push(tab));
    const aktiv = () => leiste.filter(e => e.classList.contains('active')).map(e => e.dataset.gruppe).join();
    const stand = [];
    if (init) {
        init();
        reiter[2].klick(); stand.push(aktiv(), String(unter.hidden));
        reiter[3].klick(); stand.push(aktiv(), String(unter.hidden));
        leiste[1].klick();
    }
    pruefe('der Reiter „Mieter“ macht „Haus“ in der Leiste aktiv, „Rechnungen“ dann „Kosten“',
        stand.join('|') === 'haus|false|kosten|true');
    pruefe('„Haus“ in der Leiste öffnet die zuletzt gezeigte Seite (Mieter)',
        gewechselt.join() === 'tenants' && leiste[1].attr['aria-current'] === undefined);
}

// Die Hilfe hat keinen Reiter: zeigeHilfe nimmt der Leiste die Markierung.
{
    const m = appQuelle.match(/function zeigeHilfe\([\s\S]*?\n\}/);
    let bereich, tourZu = 0;
    const hilfe = { classList: { add() {} }, style: {} };
    if (m) {
        new Function('document', 'window', 'schliesseBegriffBlase', 'hilfeChecklisteLaden', 'ladeUeber', 'zeigeBereich',
            'tourBeenden', m[0] + '; zeigeHilfe();')({
            querySelectorAll: () => [],
            querySelector: () => null,
            getElementById: id => id === 'tab-hilfe' ? hilfe : null,
        }, { scrollTo() {} }, () => {}, () => {}, () => {}, item => { bereich = item; }, () => { tourZu++; });
    }
    pruefe('NK-224: die Hilfe markiert keinen Bereich in der Leiste', !!m && bereich === null);
    // Sonst holt die offene Tour beim Schließen eines Dialogs ihren Reiter zurück.
    pruefe('die Hilfe beendet eine offene Einführungstour', tourZu === 1);
    const versuch = (appQuelle.match(/const versuch = \(\) => \{[\s\S]*?\n    \};/) || [''])[0];
    pruefe('die Einführung startet nicht von selbst über der offenen Hilfe',
        /getElementById\('tab-hilfe'\)\.classList\.contains\('active'\)\) return;/.test(versuch));
}

// die Befehlspalette markiert jedes Suchwort und maskiert den Rest.
{
    const funktion = name => (appQuelle.match(new RegExp('function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const quelle = funktion('escapeHtml') + funktion('befehlMarkiert');
    const markiert = quelle.includes('befehlMarkiert')
        && new Function(quelle + '; return befehlMarkiert;')()('Strom <b>2. OG', ['strom', 'og']);
    pruefe('Suchwörter in <mark>, Text maskiert',
        markiert === '<mark>Strom</mark> &lt;b&gt;2. <mark>OG</mark>');
}

// „Heute“ nennt Zähler ohne Stand im laufenden Jahr, Belege ohne
// Rechnung, fällige Abrechnungen und offene Zahlungen zugestellter Abrechnungen
// (Phase 47); Beispieldaten erzeugen keine Aufgabe.
{
    const quelle = (appQuelle.match(/function heuteAufgaben\(\)[\s\S]*?\n\}/) || [''])[0];
    const jahr = String(new Date().getFullYear());
    const gruppen = quelle && new Function('echterBestand', 'tenants', 'abrechnungsVorschlaege',
        'zaehlerArtName', 'datumText', 'openAddReadingModal', 'openBillingSelectionModal',
        'currentDocuments', 'belegOffen', 'wechsleZuTab', 'zeigeKostenAnsicht',
        'abrechnungsHistorie', 'euroText', 'zahlungZurAbrechnung',
        quelle + '; return heuteAufgaben();')(
        () => ({ properties: [{ id: 1 }], meters: [{ id: 1, category_name: 'Strom', meter_number: 'A1', property_name: 'Haus' },
            { id: 2, category_name: 'Strom', meter_number: 'B2', property_name: 'Haus' }],
        readings: [{ meter_id: 1, reading_date: jahr + '-03-01' }] }),
        [{ id: 7, ist_beispiel: true }],
        [{ tenant_id: 7, tenant_name: 'Beispiel' }, { tenant_id: 8, tenant_name: 'Echt', apartment_name: 'EG' }],
        art => art, d => d, () => {}, () => {},
        [{ id: 5, property_id: 1, description: 'Stadtwerke', property_name: 'Haus', upload_date: '2026-02-01T10:00:00' },
            { id: 6, property_id: 1, description: 'Erledigt', property_name: 'Haus', upload_date: '2026-02-01T10:00:00' },
            { id: 7, property_id: 9, description: 'Beispiel', property_name: 'Beispielhaus', upload_date: '2026-02-01T10:00:00' }],
        d => d.id !== 6, () => {}, () => {},
        [{ id: 3, tenant_id: 8, tenant_name: 'Echt', apartment_name: 'EG', zugestellt_am: '2026-02-01', offen_betrag: '12.00' },
            { id: 4, tenant_id: 8, tenant_name: 'Bezahlt', apartment_name: 'EG', zugestellt_am: '2026-02-01', offen_betrag: '0.00' }],
        b => b + ' €', () => {});
    const stand = (gruppen || []).map(g => g.name + ':' + g.aufgaben.map(a => a.titel + '/' + a.chip).join(',')).join('|');
    pruefe('Heute zeigt nur Zähler ohne Stand, offene Belege, echte fällige Abrechnungen und offene Zahlungen',
        stand === 'Erfassen:Strom B2/fehlt|Belege:Stadtwerke/offen|Abrechnen:Echt (EG)/fällig|Zahlungen:Echt (EG)/offen');
}

// --- Immobilienfilter im Kopf ----------------------------------------------
// Vorher sprang die Auswahl nur zur Immobilie, Mieter und Kosten zeigten weiter
// alles. Jetzt filtert imHaus jede geladene Liste über ihr Verknüpfungsfeld.
{
    const funktion = name => (appQuelle.match(new RegExp('function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const filtere = (filter, liste, merke) => new Function('hausFilter', 'liste', 'merke',
        funktion('gehoertZumHaus') + funktion('imHaus') + '; return [imHaus(liste, merke), hausFilter];')(filter, liste, merke);
    const f = () => ({ id: 1, wohnungen: new Set([11]), zaehler: new Set([21]), mieter: new Set([31]) });
    const ids = l => l.map(x => x.id).join(',');
    pruefe('Hausfilter: ohne Auswahl bleibt jede Liste vollständig',
        ids(filtere(null, [{ id: 1, property_id: 2 }])[0]) === '1');
    const gemischt = [{ id: 1, property_id: 1 }, { id: 2, property_id: 2 }, { id: 3, apartment_id: 11 },
        { id: 4, apartment_id: 12 }, { id: 5, meter_id: 21 }, { id: 6, meter_id: 22 },
        { id: 7, tenant_id: 31 }, { id: 8, tenant_id: 32 }, { id: 9, property_id: null }];
    pruefe('Hausfilter: Immobilie, Wohnung, Zähler und Mieter grenzen ein, Unzugeordnetes bleibt',
        ids(filtere(f(), gemischt)[0]) === '1,3,5,7,9');
    pruefe('Hausfilter: die Immobilie hat Vorrang vor der Wohnung',
        ids(filtere(f(), [{ id: 1, property_id: 2, apartment_id: 11 }])[0]) === '');
    const [, nach] = filtere(f(), [{ id: 11, property_id: 1 }, { id: 12, property_id: 2 }, { id: 13, property_id: 1 }], 'wohnungen');
    pruefe('Hausfilter: neu geladene Wohnungen landen in der Menge, an der die Mieter hängen',
        [...nach.wohnungen].join() === '11,13');
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
            'readings', 'payments', 'abrechnungsHistorie', 'zeigeHeute', 'fuelleHausWahl', 'tourAutostart',
            quelle + '; zeigeErsteSchritte();')(
            { getElementById: hole, createElement: () => ({}) },
            beispiel ? [{ id: 1, ist_beispiel: true }] : [], [], [], [], [], [], [], [], () => {}, () => {},
            () => { el.tourGestartet = true; });
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
    pruefe('die Einführung startet von selbst nur in der leeren App, nicht neben dem Beispielhaus',
        ohne.tourGestartet === true && !mit.tourGestartet);
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

// --- NK-216: unplausibler Zählerstand wird nachgefragt ---------------
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
        /<input type="file" id="ablesen-foto-1" accept="image\/\*" capture="environment"[\s>]/.test(zeilen));
    pruefe('NK-255: die Einheit des Zählers steht am Feld',
        zeilen.includes('>Stand (HT, kWh)</label>') && zeilen.includes('>Stand (NT, kWh)</label>')
        && zeilen.includes('>Stand (m³)</label>')
        && baue({}, 'ablesenZeilen')({}, meters, readings)(9).includes('>Stand</label>'));
    pruefe('NK-255: das Foto-Feld trägt den Stil der App',
        zeilen.includes('<div class="file-upload-wrapper">')
        && zeilen.includes('<label for="ablesen-foto-1" class="file-upload-label">'));

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

// --- NK-255: Einheit am Feld auch im Einzel-Ablesedialog ----------------
{
    const m = appQuelle.match(/function handleReadingMeterChange\([\s\S]*?\n\}/);
    const lauf = (zaehler) => {
        const el = {};
        const hole = id => (el[id] = el[id] || { id, value: '', textContent: '', style: {} });
        hole('reading-meter').value = '1';
        new Function('document', 'meters', m[0] + '; handleReadingMeterChange();')(
            { getElementById: hole }, [zaehler]);
        return el;
    };
    if (!m) {
        pruefe('NK-255: handleReadingMeterChange gibt es', false);
    } else {
        const doppelt = lauf({ id: 1, einheit: 'kWh', has_dual_tariff: true });
        const einfach = lauf({ id: 1, einheit: 'm³', has_dual_tariff: false });
        const ohne = lauf({ id: 1, has_dual_tariff: false });
        pruefe('NK-255: der Ablesedialog nennt die Einheit des Zählers am Feld',
            doppelt['label-reading-value'].textContent === 'Zählerstand (HT, kWh)'
            && doppelt['label-reading-value-nt'].textContent === 'Zählerstand (NT, kWh)'
            && einfach['label-reading-value'].textContent === 'Zählerstand (m³)'
            && ohne['label-reading-value'].textContent === 'Zählerstand');
    }
}

// --- NK-256: Zahlungskarten ohne Nullzeilen -----------------------------
{
    const m = appQuelle.match(/function renderPayments\([\s\S]*?\n\}/);
    if (!m) {
        pruefe('NK-256: renderPayments gibt es', false);
    } else {
        const karten = [];
        const zahlung = (tenant_id, type, amount) => ({ tenant_id, tenant_name: 'M' + tenant_id, type, amount,
            payment_date: '2026-01-01' });
        new Function('paymentsGrid', 'payments', 'document', 'escapeHtml', 'leerzustand', m[0] + '; renderPayments();')(
            { replaceChildren() {}, appendChild: k => karten.push(k.innerHTML) },
            [zahlung(1, 'Nebenkostenvorauszahlung', 200), zahlung(2, 'Miete', 700), zahlung(2, 'Nebenkostenvorauszahlung', 150),
             zahlung(3, 'Kaution', 2100)],
            { createElement: () => ({}) }, s => String(s), () => '');
        const [nurNk, beides, nurKaution] = karten;
        pruefe('NK-256: ohne Mietzahlung keine Zeile „Miete“, mit Zahlung schon',
            karten.length === 3 && !nurNk.includes('Miete:') && nurNk.includes('Nebenkosten:')
            && beides.includes('Miete:') && beides.includes('Nebenkosten:') && beides.includes('Gesamt (mtl.)'));
        pruefe('NK-256: nur Kaution ergibt keine Monatszeilen mit 0,00 €',
            karten.length === 3 && !nurKaution.includes('Miete:') && !nurKaution.includes('Nebenkosten:')
            && !nurKaution.includes('Gesamt (mtl.)') && nurKaution.includes('Kaution:'));
    }
}

// --- NK-254: Wohnungsvergleich erst ab zwei Wohnungen mit Daten ---------------
{
    const m = appQuelle.match(/function renderBuildingComparison\([\s\S]*?\n\}/);
    const lauf = daten => {
        const karte = { hidden: false };
        const el = {
            'chart-building-comparison': { getContext: () => ({ canvas: {} }) },
            'chart-comparison-title': { closest: () => karte },
            'chart-building-comparison-leer': {},
        };
        let gezeichnet = 0;
        new Function('document', 'Chart', 'DIAGRAMM_FARBE', 'chartBuildingComparisonInstance', 'daten',
            m[0] + '; renderBuildingComparison(daten);')(
            { getElementById: id => el[id] },
            class { constructor() { gezeichnet++; } destroy() {} }, {}, null, daten);
        return { karte, gezeichnet };
    };
    if (!m) {
        pruefe('NK-254: renderBuildingComparison gibt es', false);
    } else {
        const zeile = (apartment, category) => ({ apartment, category, consumption: 10, unit: 'kWh' });
        const keine = lauf([]);
        const eine = lauf([zeile('WE 1', 'Strom'), zeile('WE 1', 'Wasser')]);
        const zwei = lauf([zeile('WE 1', 'Strom'), zeile('WE 2', 'Strom')]);
        pruefe('NK-254: Wohnungsvergleich bei keiner und einer Wohnung ausgeblendet',
            keine.karte.hidden === true && eine.karte.hidden === true && eine.gezeichnet === 0);
        pruefe('NK-254: Wohnungsvergleich bei zwei Wohnungen gezeichnet',
            zwei.karte.hidden === false && zwei.gezeichnet === 1);
    }
}

// --- NK-260: KPI-Kacheln ohne Inline-Styles ---------------------------
// Vorher trugen die Kacheln Farbe, Abstand und Hover (onmouseenter) im Markup.
{
    const m = appQuelle.match(/function renderBuildingVitalSigns\([\s\S]*?\n\}/);
    const lauf = (trend, offen) => {
        const container = { innerHTML: '' };
        new Function('document', 'window', 'escapeHtml', 'kpis', m[0] + '; renderBuildingVitalSigns(kpis);')(
            { getElementById: () => container },
            { wrapInterpolated: s => s }, s => String(s),
            { cashflow_ytd: -50, total_costs_last_year: 1200, general_power: 300, general_power_trend: trend,
              open_tasks: offen, reference_year: 2025 });
        return container.innerHTML;
    };
    if (!m) {
        pruefe('NK-260: renderBuildingVitalSigns gibt es', false);
    } else {
        const hoch = lauf(5, 2), gleich = lauf(0, 0);
        pruefe('NK-260: Kacheln ohne style= und ohne onmouseenter/onmouseleave',
            !/style=|onmouse/.test(hoch + gleich) && (hoch.match(/class="dashboard-card glass-panel kpi-karte/g) || []).length === 4);
        pruefe('NK-260: Trend und offene Abrechnungen färben über Klassen',
            hoch.includes('kpi-trend kpi-trend--hoch') && hoch.includes('kpi-wert--offen')
            && gleich.includes('kpi-trend kpi-trend--gleich') && gleich.includes('kpi-wert--erledigt'));
        const css = fs.readFileSync(path.join(__dirname, '..', 'static', 'style.css'), 'utf8');
        pruefe('NK-260: Hover der klickbaren Kacheln steht im Stylesheet',
            /\.kpi-clickable:hover\s*\{[^}]*background: var\(--surface-alt\)/.test(css)
            // Aufsteigen nur in @keyframes, kein Anheben beim Hover
            && !/translateY/.test(css.replace(/@keyframes[^{]*\{(?:[^{}]*\{[^}]*\})*\s*\}/g, ''))
            && /\.kpi-karte\s*\{[^}]*border-left:\s*4px solid var\(--kpi-farbe/.test(css));
    }
}

// --- NK-230: Wie im Vorjahr füllen ---------------------------------------
// Die Rechnungen des Vorjahres kommen als Zeilen ohne Betrag; getippte Zeilen
// bleiben, leere machen Platz. Ohne Betrag wird eine solche Zeile nicht
// gespeichert und so markiert.
async function vorjahrPruefen() {
    const funktion = name => (appQuelle.match(new RegExp('(?:async )?function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const konstante = name => (appQuelle.match(new RegExp('const ' + name + ' = [^\\n]*')) || [''])[0];
    pruefe('NK-230: Knopf „Wie im Vorjahr füllen“ in der Tabelle und in Schritt 2',
        /onclick="rtVorjahrFuellen\(\)"[^>]*>[\s\S]{0,80}Wie im Vorjahr füllen\s*<\/button>/.test(html)
        && /onclick="jahrVorjahrFuellen\(\)"[^>]*>[\s\S]{0,80}Wie im Vorjahr füllen\s*<\/button>/.test(html));
    if (!funktion('rtVorjahrFuellen') || !konstante('RT_OHNE_BETRAG')) {
        pruefe('NK-230: rtVorjahrFuellen gibt es', false);
        return;
    }
    // Eine kleine Tabellen-Attrappe: tr > td > input, wie rtZeilenAnlegen sie baut.
    const knoten = tag => ({
        tag, kinder: [], dataset: {}, value: '', textContent: '', className: '',
        classList: { add() {}, toggle() {} }, setAttribute() {}, focus() {},
        appendChild(k) { k.eltern = this; this.kinder.push(k); return k; },
        remove() { this.eltern.kinder.splice(this.eltern.kinder.indexOf(this), 1); },
        get lastElementChild() { return this.kinder[this.kinder.length - 1]; },
        alle() { return this.kinder.flatMap(k => [k, ...k.alle()]); },
        querySelectorAll(sel) { return this.alle().filter(k => k.tag === sel); },
        querySelector(sel) {
            const spalte = (sel.match(/data-spalte="(\w+)"/) || [])[1];
            return this.alle().find(k => spalte ? k.dataset.spalte === spalte : k.className.split(' ').includes(sel.slice(1)));
        },
    });
    const rumpf = knoten('tbody');
    const el = { 'rt-zeilen': rumpf, 'rt-jahr': { value: '2025' }, 'rt-meldung': { textContent: '' },
        'rt-immobilie': { value: '5', selectedIndex: 0, options: [{ text: 'Haus' }] } };
    const doc = { getElementById: id => el[id], createElement: knoten,
        querySelectorAll: sel => sel === '#rt-zeilen tr' ? rumpf.kinder.slice() : [] };
    const aufrufe = [];
    const antworten = [];
    const holen = async (url, opt) => { aufrufe.push({ url, opt }); return antworten.shift(); };
    const quelle = konstante('RT_SPALTEN') + konstante('RT_OHNE_BETRAG') + funktion('anzahlText')
        + funktion('rtDatum') + funktion('rtZeilenAnlegen') + funktion('rtZeilenLesen')
        + funktion('rtVorjahrFuellen') + funktion('rtSenden');
    const t = new Function('document', 'fetch', 'serverFehler', 'meldungZu', 'showError', 'showSuccess',
        'importNachladen', quelle + '; return { rtZeilenAnlegen, rtZeilenLesen, rtVorjahrFuellen, rtSenden };')(
        doc, holen, async () => new Error('kaputt'), (e, x) => x, () => {}, () => {}, () => {});

    t.rtZeilenAnlegen(2);
    rumpf.kinder[0].querySelector('[data-spalte="kostenart"]').value = 'Wasser';
    rumpf.kinder[0].querySelector('[data-spalte="betrag"]').value = '5';
    const vorlage = (kostenart, wohnung) => ({ kostenart, von: '01.01.2025', bis: '31.12.2025',
        anbieter: '', wohnung, betrag: '', rechnungsnummer: '', rechnungsdatum: '' });
    antworten.push({ ok: true, json: async () => ({ zeilen: [vorlage('Grundsteuer', ''), vorlage('Hauswart', 'EG')], heizung: 1 }) });
    await t.rtVorjahrFuellen();
    const wert = (i, spalte) => rumpf.kinder[i].querySelector(`[data-spalte="${spalte}"]`).value;
    const status = i => rumpf.kinder[i].querySelector('.rt-status').textContent;
    pruefe('NK-230: das Vorjahr kommt für Immobilie und Jahr der Tabelle',
        aufrufe[0].url === '/api/import/rechnungen/vorjahr?property_id=5&jahr=2025');
    pruefe('NK-230: getippte Zeilen bleiben, leere machen Platz, Vorjahr ohne Betrag markiert',
        wert(0, 'kostenart') === 'Wasser' && wert(1, 'kostenart') === 'Grundsteuer'
        && wert(2, 'kostenart') === 'Hauswart' && wert(2, 'wohnung') === 'EG' && wert(1, 'betrag') === ''
        && wert(1, 'von') === '01.01.2025' && status(1).includes('nicht gespeichert')
        && rumpf.kinder.length === 6 && wert(3, 'kostenart') === '');
    pruefe('NK-230: die Meldung nennt Anzahl, Jahr und die Heizkosten im Dialog',
        el['rt-meldung'].textContent.includes('2 Rechnungen aus 2024')
        && el['rt-meldung'].textContent.includes('Heizkostenrechnung'));

    rumpf.kinder[1].querySelector('[data-spalte="betrag"]').value = '1.300,00';
    antworten.push({ ok: true, json: async () => ({ fehler: [], hinweise: [], zeilen: 2 }) });
    await t.rtSenden(false);
    const gesendet = JSON.parse(aufrufe[1].opt.body).zeilen.filter(z => Object.keys(z).length);
    pruefe('NK-230: eine vorbelegte Zeile ohne Betrag wird nicht gesendet und bleibt markiert',
        gesendet.length === 2 && gesendet.map(z => z.kostenart).join() === 'Wasser,Grundsteuer'
        && status(2).includes('nicht gespeichert') && !status(1).includes('nicht gespeichert'));
}

async function zaehlerPflegePruefen() {
    const funktion = name => (appQuelle.match(new RegExp('(?:async )?function ' + name + '\\([\\s\\S]*?\\n\\}')) || [''])[0];
    const namen = ['eichfristVorschlag', 'saveMeter', 'openWechselModal', 'saveWechsel'];
    if (namen.some(n => !funktion(n))) {
        pruefe('NK-258: ' + namen.join(', ') + ' gibt es', false);
        return;
    }
    pruefe('NK-258: Zählerliste hat Bearbeiten und Wechsel, der Wechsel nur am eingebauten Zähler',
        /onclick = \(\) => openEditMeterModal\(m\.id\)/.test(appQuelle)
        && /if \(!m\.ersetzt_durch\) \{[\s\S]{0,800}openWechselModal\(m\.id\)/.test(appQuelle));
    // Felder entstehen beim ersten Zugriff; .value, .checked und .hidden sind frei setzbar.
    const el = {};
    const feld = id => (el[id] = el[id] || { value: '', checked: false, hidden: false, textContent: '',
        classList: { add() { this.aktiv = true; }, remove() { this.aktiv = false; } } });
    const nt = [feld('nt-1'), feld('nt-2')];
    const doc = { getElementById: feld, querySelectorAll: sel => sel === '#wechsel-modal .wechsel-nt' ? nt : [] };
    const aufrufe = [], antworten = [], meldungen = [];
    const holen = async (url, opt = {}) => { aufrufe.push({ url, opt }); return antworten.shift(); };
    const nachfrage = async (url, method, fd) => { aufrufe.push({ url, opt: { method, body: fd } }); return antworten.shift(); };
    const geladen = [];
    const zaehlerListe = [{ id: 7, meter_number: 'W-7', ort: 'Keller', has_dual_tariff: true }];
    class Formular { constructor() { this.felder = {}; } append(k, v) { this.felder[k] = v; } }
    const t = new Function('document', 'fetch', 'sendeMitNachfrage', 'serverFehler', 'meldungZu', 'showError',
        'closeAddMeterModal', 'closeWechselModal', 'fetchMeters', 'fetchReadings', 'meters', 'FormData',
        namen.map(funktion).join('\n') + '; return { ' + namen.join(', ') + ' };')(
        doc, holen, nachfrage, async () => new Error('kaputt'), (e, x) => x, x => meldungen.push(x),
        () => {}, () => feld('wechsel-modal').classList.remove(), () => geladen.push('zaehler'),
        () => geladen.push('staende'), zaehlerListe, Formular);

    feld('meter-eichjahr').value = '2020';
    await t.eichfristVorschlag();
    pruefe('R-EICH-01: ohne Zählerart kein Vorschlag', aufrufe.length === 0);
    feld('meter-eichart').value = 'kaltwasser';
    antworten.push({ ok: true, json: async () => ({ geeicht_bis: '2026-12-31' }) });
    await t.eichfristVorschlag();
    pruefe('R-EICH-01: der Vorschlag kommt vom Server und landet in „geeicht bis“',
        aufrufe[0].url === '/api/eichfrist?eichjahr=2020&art=kaltwasser'
        && el['meter-geeicht-bis'].value === '2026-12-31');

    Object.assign(feld('meter-category'), { value: '3' });
    Object.assign(feld('meter-property'), { value: '1' });
    Object.assign(feld('meter-number'), { value: ' W-7a ' });
    Object.assign(feld('meter-ort'), { value: 'Bad' });
    Object.assign(feld('meter-id'), { value: '7' });
    antworten.push({ ok: true });
    await t.saveMeter();
    const put = JSON.parse(aufrufe[1].opt.body);
    pruefe('NK-258: Bearbeiten speichert per PUT ohne Immobilie und Wohnung',
        aufrufe[1].url === '/api/meters/7' && aufrufe[1].opt.method === 'PUT'
        && put.meter_number === 'W-7a' && put.ort === 'Bad' && put.geeicht_bis === '2026-12-31'
        && !('property_id' in put) && !('apartment_id' in put));
    feld('meter-id').value = '';
    antworten.push({ ok: true });
    await t.saveMeter();
    const post = JSON.parse(aufrufe[2].opt.body);
    pruefe('NK-258: Anlegen bleibt ein POST mit Immobilie',
        aufrufe[2].url === '/api/meters' && aufrufe[2].opt.method === 'POST' && post.property_id === 1);

    pruefe('NK-258: nach dem Speichern lädt die Zählerliste neu', geladen.join() === 'zaehler,zaehler');
    geladen.length = 0;
    t.openWechselModal(7);
    pruefe('NK-258: der Wechseldialog zeigt beim Zweitarif die NT-Felder und übernimmt den Ort',
        el['wechsel-meter-id'].value === 7 && el['wechsel-ort'].value === 'Keller'
        && nt.every(n => !n.hidden) && el['wechsel-modal'].classList.aktiv);
    Object.assign(feld('wechsel-datum'), { value: '2024-07-01' });
    Object.assign(feld('wechsel-endstand'), { value: '400' });
    Object.assign(feld('wechsel-nummer'), { value: 'W-8' });
    antworten.push(null);
    await t.saveWechsel();
    pruefe('NK-258: bei Nein auf die Rückfrage bleibt der Dialog offen',
        el['wechsel-modal'].classList.aktiv && geladen.length === 0);
    antworten.push({ ok: true, status: 201 });
    await t.saveWechsel();
    const wechsel = aufrufe[4];
    pruefe('NK-258: der Wechsel geht über sendeMitNachfrage und lädt Zähler und Stände neu',
        wechsel.url === '/api/meters/7/wechsel' && wechsel.opt.method === 'POST'
        && wechsel.opt.body.felder.meter_number === 'W-8' && wechsel.opt.body.felder.endstand === '400'
        && wechsel.opt.body.felder.ort === 'Keller'
        && !el['wechsel-modal'].classList.aktiv && geladen.join() === 'zaehler,staende');
    pruefe('NK-258: keine Fehlermeldung im glatten Lauf', meldungen.length === 0);
}

// --- Zugriffsschlüssel: Karte, Anlegen, Liste, Löschen ----------------------
// Unter Einstellungen → Konto legt man Schlüssel für Programme ohne Browser
// an. Der Rauchtest geht den Weg einmal ganz, mit gestubbtem fetch und einem
// erfundenen Namen: die Karte steht in der Gruppe „Konto“ und ist mit Konto
// zu sehen, ein Schlüssel geht als POST hinaus, die Box zeigt ihn einmal, die
// Liste nennt ihn maskiert mit Knopf „Löschen“, und der Knopf löscht genau
// diesen Schlüssel erst nach der Rückfrage per DELETE.
async function zugriffsschluesselPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const umfangText = appQuelle.match(/const UMFANG_TEXT = [^\n]*\n/);
    if (!umfangText) throw new Error('UMFANG_TEXT nicht gefunden');
    const quelltext = umfangText[0] + funktion('ladeZugriffsschluessel')
        + funktion('zugriffsschluesselAnlegen') + funktion('zugriffsschluesselWiderrufen');
    // Anlegen und Löschen laden die Liste ohne await nach: erst warten, bis
    // alle Mikroaufgaben durch sind.
    const ruhe = () => new Promise(r => setImmediate(r));
    const lauf = (felder, antworten, ja = true) => {
        const aufrufe = [], fehlerMeldungen = [], erfolge = [], fragen = [];
        const dokument = {
            getElementById(id) {
                if (!(id in felder)) felder[id] = {};
                const f = felder[id];
                if (!('value' in f)) f.value = '';
                if (!('innerHTML' in f)) f.innerHTML = '';
                if (!('hidden' in f)) f.hidden = false;
                f.focus = () => { f.fokus = true; };
                f.select = () => { f.markiert = true; };
                return f;
            },
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            const [status, daten] = antworten.shift() || [200, {}];
            return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(daten) });
        };
        const fns = new Function('document', 'fetch', 'showError', 'showSuccess', 'serverFehler',
            'meldungZu', 'escapeHtml', 'frage',
            quelltext + '; return { ladeZugriffsschluessel, zugriffsschluesselAnlegen, zugriffsschluesselWiderrufen };')(
            dokument, holen, m => fehlerMeldungen.push(m), m => erfolge.push(m),
            async () => new Error('Server'), (e, ersatz) => ersatz,
            t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
            async (text, knopf, gefahr, titel) => { fragen.push({ text, knopf, gefahr, titel }); return ja; });
        return { fns, aufrufe, fehlerMeldungen, erfolge, fragen, felder };
    };

    // 1. Die Karte: in den Einstellungen, Gruppe „Konto“, mit Feldern und Knopf.
    const karteAnfang = html.indexOf('id="zugriffsschluessel-karte"');
    const karte = karteAnfang < 0 ? '' : html.slice(karteAnfang, html.indexOf('id="zugriffsschluessel-neu"', karteAnfang) + 200);
    pruefe('Zugriffsschlüssel: die Karte steht unter Einstellungen in der Gruppe „Konto“',
        karteAnfang > html.indexOf('id="tab-settings"') && html.indexOf('id="tab-settings"') > 0
        && /<div data-gruppe="konto" class="dashboard-card glass-panel" id="zugriffsschluessel-karte">/.test(html)
        && /<h3>Zugriffsschlüssel<\/h3>/.test(karte));
    pruefe('Zugriffsschlüssel: Name, Umfang und „Schlüssel anlegen“ stehen in der Karte, die Box ist zu',
        /<input type="text" id="zugriffsschluessel-name" maxlength="60"/.test(karte)
        && /<option value="lesen">Nur lesen<\/option>/.test(karte)
        && /<option value="erfassen">Lesen und erfassen<\/option>/.test(karte)
        && /onclick="zugriffsschluesselAnlegen\(\)">Schlüssel anlegen<\/button>/.test(karte)
        && /id="zugriffsschluessel-neu" hidden>/.test(karte));
    pruefe('Zugriffsschlüssel: die Gruppe „Konto“ lädt die Liste',
        /if \(gruppe === 'konto'\) ladeZugriffsschluessel\(\);/.test(funktion('zeigeEinstellungsgruppe')));

    // Mit Konto ist die Karte zu sehen, im offenen Modus nicht (NK-201).
    const anfang = appQuelle.indexOf('async function zeigeAngemeldetenBenutzer() {');
    if (anfang < 0) throw new Error('zeigeAngemeldetenBenutzer nicht gefunden');
    let tiefe = 0, ende = -1;
    for (let i = anfang; i < appQuelle.length; i++) {
        if (appQuelle[i] === '{') tiefe++;
        else if (appQuelle[i] === '}') { tiefe--; if (!tiefe) { ende = i + 1; break; } }
    }
    const kopf = async (daten) => {
        const teile = {};
        await new Function('document', 'fetch', 'showError', 'serverFehler', 'meldungZu',
            appQuelle.slice(anfang, ende) + '; return zeigeAngemeldetenBenutzer();')(
            { getElementById(id) { if (!(id in teile)) teile[id] = { textContent: '', hidden: undefined }; return teile[id]; } },
            () => Promise.resolve({ ok: true, json: () => Promise.resolve(daten) }),
            () => {}, async () => new Error('Server'), (e, e2) => e2);
        return teile;
    };
    const mitKonto = await kopf({ username: 'testkonto', ohne_anmeldung: false, leerlauf_s: null, desktop: false });
    const offen = await kopf({ username: null, ohne_anmeldung: true, leerlauf_s: null, desktop: false });
    pruefe('Zugriffsschlüssel: mit Konto ist die Karte zu sehen, im offenen Modus nicht',
        mitKonto['zugriffsschluessel-karte'].hidden === false
        && offen['zugriffsschluessel-karte'].hidden === true);

    // 2. Leere Liste.
    const leer = lauf({}, [[200, []]]);
    await leer.fns.ladeZugriffsschluessel();
    pruefe('Zugriffsschlüssel: ohne Schlüssel ein Hinweis statt einer leeren Tabelle',
        leer.aufrufe.length === 1 && leer.aufrufe[0].url === '/api/zugriffsschluessel'
        && leer.aufrufe[0].methode === 'GET'
        && leer.felder['zugriffsschluessel-zeilen'].innerHTML.includes('Noch kein Zugriffsschlüssel angelegt.'));

    // 3. Ohne Namen geht nichts hinaus.
    const ohneName = lauf({ 'zugriffsschluessel-name': { value: '   ' } }, []);
    await ohneName.fns.zugriffsschluesselAnlegen();
    pruefe('Zugriffsschlüssel: ohne Namen keine Anfrage, eine Meldung',
        ohneName.aufrufe.length === 0 && ohneName.fehlerMeldungen.length === 1);

    // 4. Anlegen mit erfundenem Namen; die Liste zeigt ihn danach.
    const name = 'Testprogramm <Laptop>';
    const klartext = 'nkf_BEISPIEL-nur-im-Rauchtest';
    const zeile = { id: 7, name, umfang: 'erfassen', konto: 'testkonto', angelegt_am: '01.01.2026 10:00', zuletzt_benutzt: null };
    const neu = lauf({ 'zugriffsschluessel-name': { value: '  ' + name + '  ' }, 'zugriffsschluessel-umfang': { value: 'erfassen' },
        'zugriffsschluessel-neu': { hidden: true } }, [[201, { ...zeile, schluessel: klartext }], [200, [zeile]]]);
    await neu.fns.zugriffsschluesselAnlegen();
    await ruhe();
    const post = neu.aufrufe[0] || {};
    pruefe('Zugriffsschlüssel: Anlegen schickt POST /api/zugriffsschluessel mit Name und Umfang',
        post.url === '/api/zugriffsschluessel' && post.methode === 'POST'
        && post.koerper === JSON.stringify({ name, umfang: 'erfassen' }));
    pruefe('Zugriffsschlüssel: die Box zeigt den Schlüssel einmal, markiert, das Namensfeld ist leer',
        neu.felder['zugriffsschluessel-neu'].hidden === false
        && neu.felder['zugriffsschluessel-wert'].value === klartext
        && neu.felder['zugriffsschluessel-wert'].fokus === true
        && neu.felder['zugriffsschluessel-wert'].markiert === true
        && neu.felder['zugriffsschluessel-name'].value === ''
        && neu.erfolge.length === 1 && neu.fehlerMeldungen.length === 0);
    const zeilen = neu.felder['zugriffsschluessel-zeilen'].innerHTML;
    pruefe('Zugriffsschlüssel: nach dem Anlegen steht der Name maskiert in der Liste, mit Umfang, Konto und „nie“',
        neu.aufrufe.length === 2 && neu.aufrufe[1].url === '/api/zugriffsschluessel' && neu.aufrufe[1].methode === 'GET'
        && zeilen.includes('Testprogramm &lt;Laptop&gt;') && !zeilen.includes('<Laptop>')
        && zeilen.includes('Lesen und erfassen') && zeilen.includes('testkonto') && zeilen.includes('>nie<'));
    pruefe('Zugriffsschlüssel: die Liste zeigt den Klartext nicht, nur den Knopf „Löschen“ der Zeile',
        !zeilen.includes(klartext) && /zugriffsschluesselWiderrufen\(7\)">Löschen<\/button>/.test(zeilen));

    // 5. Der Knopf der Zeile löscht genau diesen Schlüssel, erst nach der Rückfrage.
    const knopfId = Number((zeilen.match(/zugriffsschluesselWiderrufen\((\d+)\)/) || [])[1]);
    const nein = lauf({}, [], false);
    await nein.fns.zugriffsschluesselWiderrufen(knopfId);
    pruefe('Zugriffsschlüssel: bei Nein auf die Rückfrage geht keine Anfrage hinaus',
        nein.fragen.length === 1 && nein.aufrufe.length === 0);
    const weg = lauf({}, [[200, { status: 'widerrufen' }], [200, []]]);
    await weg.fns.zugriffsschluesselWiderrufen(knopfId);
    await ruhe();
    const frageLoeschen = weg.fragen[0] || {};
    pruefe('Zugriffsschlüssel: Löschen fragt mit rotem Knopf „Löschen“ nach',
        weg.fragen.length === 1 && frageLoeschen.knopf === 'Löschen' && frageLoeschen.gefahr === true
        && frageLoeschen.titel === 'Zugriffsschlüssel löschen?');
    pruefe('Zugriffsschlüssel: Löschen schickt DELETE für genau diesen Schlüssel und lädt die Liste neu',
        weg.aufrufe.length === 2 && weg.aufrufe[0].url === '/api/zugriffsschluessel/7'
        && weg.aufrufe[0].methode === 'DELETE' && weg.aufrufe[1].methode === 'GET'
        && weg.felder['zugriffsschluessel-zeilen'].innerHTML.includes('Noch kein Zugriffsschlüssel angelegt.')
        && weg.erfolge.length === 1 && weg.fehlerMeldungen.length === 0);
}

// PDF-Aufbau (Einstellungen → Abrechnung): der Bereich lädt das Layout per
// GET, zeichnet jede Zeile nur mit textContent (ein innerHTML wirft hier),
// hält das Deckblatt vorn und Pflichtteile an, verschiebt per Pfeil und per
// Ziehen, speichert per PUT, stellt per DELETE den Standard her, zeigt die
// Vorschau aus POST …/vorschau über die Hülle und nennt Fehler des Servers.
// Der Katalog kommt aus nebenkostenfix/pdf_layout.py, damit Pflicht und
// feste Stelle hier nicht von Hand nachgebaut sind.
async function pdfLayoutPruefen() {
    const funktion = name => {
        const m = appQuelle.match(new RegExp(`(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    const adresse = appQuelle.match(/const PDF_LAYOUT_ADRESSE = [^\n]*\n/);
    if (!adresse) throw new Error('PDF_LAYOUT_ADRESSE nicht gefunden');
    const gruppen = appQuelle.match(/const EINSTELLUNGS_GRUPPEN = [^\n]*\n/);
    if (!gruppen) throw new Error('EINSTELLUNGS_GRUPPEN nicht gefunden');
    const nichtGeladen = appQuelle.match(/const PDF_LAYOUT_NICHT_GELADEN = [^\n]*\n/);
    if (!nichtGeladen) throw new Error('PDF_LAYOUT_NICHT_GELADEN nicht gefunden');
    const ladeTexte = appQuelle.match(/const PDF_LAYOUT_LADEFEHLER = [^\n]*\nconst PDF_LAYOUT_SERVERFEHLER = [^\n]*\n/);
    if (!ladeTexte) throw new Error('PDF_LAYOUT_LADEFEHLER/PDF_LAYOUT_SERVERFEHLER nicht gefunden');
    const quelltext = adresse[0] + gruppen[0] + nichtGeladen[0] + ladeTexte[0] + 'let pdfLayoutStand = null;\n'
        + ['pdfLayoutAusAntwort', 'pdfLayoutZiehen',
        'pdfLayoutTitel', 'pdfLayoutHinweisZeigen', 'ladePdfLayout', 'pdfLayoutHinweisLaden', 'pdfLayoutKnopf',
        'pdfLayoutZeile', 'pdfLayoutZeichnen', 'pdfLayoutSchieben', 'pdfLayoutDaten', 'pdfLayoutSpeichern',
        'pdfLayoutStandard', 'pdfLayoutVorschau', 'pdfLayoutGeaendert', 'pdfLayoutVerlassen',
        'pdfLayoutVorDemVerlassen', 'zeigeEinstellungsgruppe', 'zeigeServerKarte', 'abmelden'].map(funktion).join('\n');
    const ladeText = new Function(ladeTexte[0] + 'return { PDF_LAYOUT_LADEFEHLER, PDF_LAYOUT_SERVERFEHLER };')();
    // Für die Fehlerfälle die echten Helfer aus app.js: eine Notseite ohne
    // JSON oder ein abgerissenes Netz sollen die Ersatztexte zeigen.
    const echteHelfer = new Function(funktion('serverFehler') + '\n' + funktion('meldungZu')
        + '\nreturn { serverFehler, meldungZu };')();
    const OHNE_JSON = Symbol('ohne JSON');
    const NETZ_WEG = Symbol('Netz weg');

    const pyQuelle = fs.readFileSync(path.join(__dirname, '..', 'nebenkostenfix', 'pdf_layout.py'), 'utf8');
    const katalog = [...pyQuelle.matchAll(/Block\('(\w+)', '([^']*)'(, pflicht=True)?(, stelle=0)?\)/g)]
        .map(m => ({ block: m[1], titel: m[2], pflicht: !!m[3], fest: !!m[4] }));
    const standardIds = katalog.map(b => b.block);
    const orte = [{ ort: 'zahlung', titel: 'Beim Zahlungshinweis am Ende' },
        { ort: 'deckblatt', titel: 'Auf dem Deckblatt' }, { ort: 'aus', titel: 'Kein GiroCode' }];
    const antwort = (ids, eigen, girocode = 'zahlung') => ({
        layout: { bloecke: ids.map(b => ({ block: b, an: true })), girocode },
        ist_standard: !eigen, bloecke: katalog, girocode_orte: orte,
    });
    pruefe('PDF-Aufbau: der Katalog aus pdf_layout.py ist lesbar, Deckblatt fest vorn, Belegliste frei',
        katalog.length >= 6 && katalog[0].block === 'deckblatt' && katalog[0].fest && katalog[0].pflicht
        && katalog.some(b => b.block === 'belegliste' && !b.pflicht && !b.fest));

    let fokussiert = null, fokusOptionen = null, gescrollt = null;
    const element = tag => {
        const el = {
            tag, kinder: [], attribute: {}, textContent: '', hidden: false, disabled: false, value: '',
            hoerer: {}, klassen: new Set(), dataset: {}, style: {},
            setAttribute(n, w) { el.attribute[n] = String(w); },
            getAttribute(n) { return n in el.attribute ? el.attribute[n] : null; },
            appendChild(k) { el.kinder.push(k); return k; },
            replaceChildren(...k) { el.kinder = k; },
            addEventListener(t, f) { el.hoerer[t] = f; },
            focus(optionen) { fokussiert = el; fokusOptionen = optionen || null; },
            scrollIntoView() { gescrollt = el; },
        };
        el.classList = {
            add: k => el.klassen.add(k), remove: k => el.klassen.delete(k), contains: k => el.klassen.has(k),
            toggle: (k, an) => { if (an) el.klassen.add(k); else el.klassen.delete(k); },
        };
        Object.defineProperty(el, 'innerHTML', { get: () => '', set: () => { throw new Error('innerHTML im PDF-Aufbau'); } });
        return el;
    };
    // Die Zeilenvorlage aus index.html: querySelector kennt nur Klassen, die dort wirklich stehen.
    const vorlageAnfang = html.indexOf('<template id="pdf-layout-vorlage">');
    const vorlageText = vorlageAnfang < 0 ? '' : html.slice(vorlageAnfang, html.indexOf('</template>', vorlageAnfang));
    const vorlageKlassen = new Set([...vorlageText.matchAll(/class="([^"]*)"/g)].flatMap(m => m[1].split(/\s+/)));
    pruefe('PDF-Aufbau: die Zeilenvorlage hat Kästchen, Titel, Marke und zwei Pfeilknöpfe im Markup',
        /<input type="checkbox" class="pdf-layout-haken">/.test(vorlageText)
        && ['pdf-layout-griff', 'pdf-layout-titel', 'pdf-layout-marke', 'pdf-layout-hoch', 'pdf-layout-runter']
            .every(k => vorlageKlassen.has(k)));
    const zeilenKopie = () => {
        const zeile = element('li');
        const teile = {};
        for (const k of ['griff', 'haken', 'titel', 'marke', 'hoch', 'runter']) teile['.pdf-layout-' + k] = element(k);
        zeile.teile = teile;
        zeile.querySelector = sel => {
            if (!vorlageKlassen.has(sel.slice(1)) || !teile[sel]) throw new Error(`${sel} fehlt in der Vorlage`);
            return teile[sel];
        };
        return zeile;
    };
    const lauf = (antworten, ja = true, echt = false) => {
        const felder = {}, aufrufe = [], fehlerMeldungen = [], erfolge = [], geoeffnet = [], fragen = [];
        felder['pdf-layout-vorlage'] = { content: { firstElementChild: { cloneNode: () => zeilenKopie() } } };
        // Wie in index.html: die Ladefehler-Meldung ist zunächst verborgen.
        felder['pdf-layout-ladefehler'] = element('div');
        felder['pdf-layout-ladefehler'].hidden = true;
        // Reiter und Karten der Einstellungen, für zeigeEinstellungsgruppe.
        const reiter = ['vermieter', 'abrechnung', 'sicherung'].map(g => {
            const knopf = element('button');
            knopf.dataset.gruppe = g;
            if (g === 'abrechnung') knopf.classList.add('active');
            return knopf;
        });
        const karten = ['vermieter', 'abrechnung', 'sicherung'].map(g => {
            const karte = element('div');
            karte.dataset.gruppe = g;
            if (g !== 'abrechnung') karte.classList.add('gruppe-aus');
            return karte;
        });
        const dokument = {
            getElementById: id => felder[id] || (felder[id] = element('div')),
            createElement: element,
            querySelectorAll: sel => (sel.includes('.dashboard-card') ? karten : reiter),
        };
        // Reihenfolge von Rückfragen, Anfragen und Seitenwechseln (Abmelden fragt vor dem POST).
        const ablauf = [];
        const fenster = {
            location: { pathname: '/', search: '', assign: ziel => ablauf.push('wechsel ' + ziel) },
        };
        const holen = (url, opt = {}) => {
            aufrufe.push({ url, methode: opt.method || 'GET', koerper: opt.body });
            ablauf.push((opt.method || 'GET') + ' ' + url);
            const [status, daten] = antworten.shift() || [200, {}];
            if (status === NETZ_WEG) return Promise.reject(new TypeError('Failed to fetch'));
            const json = daten === OHNE_JSON
                ? () => Promise.reject(new SyntaxError('Unexpected token < in JSON'))
                : () => Promise.resolve(daten);
            return Promise.resolve({ ok: status < 400, status, json, blob: () => Promise.resolve({ art: 'pdf' }) });
        };
        const helfer = echt ? echteHelfer : {
            serverFehler: async a => { const d = await a.json(); const f = new Error(d.error || 'Server'); f.vomServer = !!d.error; return f; },
            meldungZu: (e, ersatz) => (e && e.vomServer ? e.message : ersatz),
        };
        const tabs = [];
        const fns = new Function('document', 'fetch', 'showError', 'showSuccess', 'serverFehler', 'meldungZu',
            'frage', 'huelle', 'ladeKostenarten', 'ladeZugriffsschluessel', 'wechsleZuTab', 'startwahlServer', 'window',
            quelltext + '; return { ladePdfLayout, pdfLayoutHinweisLaden, pdfLayoutSpeichern,'
            + ' pdfLayoutStandard, pdfLayoutVorschau, zeigeEinstellungsgruppe, zeigeServerKarte,'
            + ' pdfLayoutVorDemVerlassen, abmelden, stand: () => pdfLayoutStand };')(
            dokument, holen, m => fehlerMeldungen.push(m), m => erfolge.push(m),
            helfer.serverFehler, helfer.meldungZu, async (...f) => { fragen.push(f); ablauf.push('frage'); return ja; },
            { blobOeffnen: async (blob, name) => { geoeffnet.push({ blob, name }); }, kann: () => false },
            () => {}, () => {}, t => tabs.push(t), () => { throw new Error('Startwahl ist zu'); }, fenster);
        const zeilen = () => felder['pdf-layout-liste'].kinder;
        const reihenfolge = () => zeilen().map(z => z.teile['.pdf-layout-titel'].textContent);
        const aktiveGruppe = () => reiter.filter(k => k.klassen.has('active')).map(k => k.dataset.gruppe).join(',');
        return { fns, felder, aufrufe, fehlerMeldungen, erfolge, geoeffnet, fragen, zeilen, reihenfolge, aktiveGruppe,
            tabs, stand: fns.stand, fenster, ablauf, dokument };
    };
    const ruhe = () => new Promise(r => setTimeout(r, 0));
    const titel = id => katalog.find(b => b.block === id).titel;

    // 1. Die Karte steht unter Einstellungen → Abrechnung.
    const karteAnfang = html.indexOf('id="pdf-layout-karte"');
    // Bis zum Ende der Karte (dahinter beginnt die Kontoverwaltung).
    const karteEnde = html.indexOf('<!-- NK-127 (E-1)', karteAnfang);
    const karte = karteAnfang < 0 || karteEnde < 0 ? '' : html.slice(karteAnfang, karteEnde);
    pruefe('PDF-Aufbau: Reiter „Abrechnung“ und die Karte in dieser Gruppe der Einstellungen',
        /<button type="button" class="filter-pill" role="tab" data-gruppe="abrechnung"/.test(html)
        && /<div data-gruppe="abrechnung" class="dashboard-card glass-panel" id="pdf-layout-karte">/.test(html)
        && karteAnfang > html.indexOf('id="tab-settings"')
        && /if \(gruppe === 'abrechnung'\) ladePdfLayout\(\);/.test(funktion('zeigeEinstellungsgruppe')));
    pruefe('PDF-Aufbau: Liste, GiroCode-Auswahl und die drei Knöpfe stehen in der Karte',
        /<ol class="pdf-layout-liste" id="pdf-layout-liste"/.test(karte)
        && /<select id="pdf-layout-girocode"><\/select>/.test(karte)
        && /onclick="pdfLayoutSpeichern\(\)">Speichern<\/button>/.test(karte)
        && /onclick="pdfLayoutVorschau\(\)">[\s\S]*?Vorschau ansehen<\/button>/.test(karte)
        && /onclick="pdfLayoutStandard\(\)">Aufbau zurücksetzen<\/button>/.test(karte)
        && !karte.includes('wiederherstellen')
        && /id="pdf-layout-eigen" role="status" hidden>Eigenes PDF-Layout aktiv</.test(karte));
    const dialog = html.slice(html.indexOf('id="billing-selection-modal"'), html.indexOf('id="billing-selection-body"'));
    pruefe('PDF-Aufbau: der Dialog „Abrechnung erstellen“ hat den Hinweis, zunächst verborgen',
        /id="billing-pdf-layout-hinweis" role="status" hidden>/.test(dialog) && dialog.includes('Eigenes PDF-Layout aktiv'));
    const freiDialog = html.slice(html.indexOf('id="billing-frei-modal"'), html.indexOf('id="frei-mieter"'));
    pruefe('PDF-Aufbau: auch der Dialog „Abrechnung frei erstellen“ hat den Hinweis, zunächst verborgen',
        /id="frei-pdf-layout-hinweis" role="status" hidden>/.test(freiDialog) && freiDialog.includes('Eigenes PDF-Layout aktiv')
        && /pdfLayoutHinweisLaden\(\);/.test(funktion('openFreieAbrechnung')));
    pruefe('PDF-Aufbau: die Karte hat Pflichterklärung, Ansage für Bildschirmleser und eine Ladefehler-Meldung',
        /<span id="pdf-layout-pflicht-text">[^<]+<\/span>/.test(karte)
        && /<p class="sr-only" id="pdf-layout-ansage" aria-live="polite"><\/p>/.test(karte)
        && /id="pdf-layout-ladefehler" role="alert" hidden>[\s\S]*?onclick="ladePdfLayout\(\)">Aktualisieren<\/button>/.test(karte));

    // 2. Laden: Standard, ohne Hinweis; Deckblatt fest, Pflicht nicht abschaltbar.
    const a = lauf([[200, antwort(standardIds, false)]]);
    await a.fns.ladePdfLayout();
    const z = a.zeilen();
    const haken = i => z[i].teile['.pdf-layout-haken'];
    pruefe('PDF-Aufbau: Laden fragt GET /api/einstellungen/pdf-layout und zeigt jede Zeile mit Titel',
        a.aufrufe.length === 1 && a.aufrufe[0].url === '/api/einstellungen/pdf-layout' && a.aufrufe[0].methode === 'GET'
        && JSON.stringify(a.reihenfolge()) === JSON.stringify(standardIds.map(titel)));
    pruefe('PDF-Aufbau: im Standard bleiben beide Hinweise zu',
        a.felder['pdf-layout-eigen'].hidden === true && a.felder['billing-pdf-layout-hinweis'].hidden === true);
    const belegIndex = standardIds.indexOf('belegliste');
    pruefe('PDF-Aufbau: Pflichtteile sind nicht abschaltbar, Belegliste schon',
        katalog.every((b, i) => haken(i).disabled === b.pflicht) && haken(belegIndex).disabled === false);
    pruefe('PDF-Aufbau: das Deckblatt lässt sich weder ziehen noch verschieben, der zweite Teil nicht davor',
        z[0].draggable === false && z[0].knoepfe['-1'].disabled && z[0].knoepfe['1'].disabled
        && z[1].knoepfe['-1'].disabled && !z[1].knoepfe['1'].disabled && z[1].draggable === true);
    pruefe('PDF-Aufbau: die Pfeile tragen ein aria-label mit dem Titel',
        z[1].knoepfe['-1'].attribute['aria-label'] === `${titel(standardIds[1])} nach oben schieben`
        && z[1].knoepfe['1'].attribute['aria-label'] === `${titel(standardIds[1])} nach unten schieben`);
    const beschrieben = i => (z[i].teile['.pdf-layout-haken'].attribute['aria-describedby'] || '').split(' ');
    pruefe('PDF-Aufbau: bei Pflichtteilen verweist das Kästchen per aria-describedby auf Marke und Erklärung',
        katalog.every((b, i) => (b.pflicht
            ? beschrieben(i).includes('pdf-layout-pflicht-text')
                && beschrieben(i).includes(z[i].teile['.pdf-layout-marke'].id)
                && !!z[i].teile['.pdf-layout-marke'].id
            : !('aria-describedby' in z[i].teile['.pdf-layout-haken'].attribute))
            // Die Marke ist nur Text; eine Beschreibung an ihr liest niemand vor.
            && !('aria-describedby' in z[i].teile['.pdf-layout-marke'].attribute))
        && new Set(katalog.map((b, i) => z[i].teile['.pdf-layout-marke'].id)).size === katalog.length);

    // 3. Pfeil nach unten: der Teil wandert, der Fokus bleibt bei ihm, die neue Stelle wird angesagt.
    z[1].knoepfe['1'].onclick();
    const nachPfeil = a.zeilen();
    pruefe('PDF-Aufbau: der Pfeil nach unten tauscht mit dem nächsten Teil, der Fokus folgt',
        a.reihenfolge()[2] === titel(standardIds[1]) && a.reihenfolge()[1] === titel(standardIds[2])
        && fokussiert === nachPfeil[2].knoepfe['1']);
    pruefe('PDF-Aufbau: nach dem Pfeil sagt die Live-Region die neue Stelle an',
        a.felder['pdf-layout-ansage'].textContent
            === `${titel(standardIds[1])} steht jetzt an Stelle 3 von ${standardIds.length}.`);

    // 4. Ziehen: die letzte Zeile auf Platz 2; auf das Deckblatt geht nichts.
    const daten = {};
    const transfer = { setData: (t, w) => { daten[t] = w; }, getData: t => daten[t] };
    const ereignis = { preventDefault() {}, dataTransfer: transfer };
    const letzte = nachPfeil.length - 1;
    const letzterTitel = a.reihenfolge()[letzte];
    nachPfeil[letzte].hoerer.dragstart(ereignis);
    nachPfeil[1].hoerer.drop(ereignis);
    const nachZiehen = a.reihenfolge();
    a.zeilen()[3].hoerer.dragstart(ereignis);
    a.zeilen()[0].hoerer.drop(ereignis);
    pruefe('PDF-Aufbau: Ziehen legt den Teil an die Zielstelle, das Deckblatt bleibt vorn',
        nachZiehen[1] === letzterTitel && JSON.stringify(a.reihenfolge()) === JSON.stringify(nachZiehen)
        && a.reihenfolge()[0] === titel('deckblatt'));

    // 5. Belegliste aus, GiroCode aufs Deckblatt, Speichern per PUT.
    const gesendet = standardIds.map(id => ({ block: id, an: id !== 'belegliste' }));
    const gespeichert = antwort(standardIds, true, 'deckblatt');
    gespeichert.layout.bloecke = gesendet;
    const speichern = lauf([[200, antwort(standardIds, false)], [200, gespeichert]]);
    await speichern.fns.ladePdfLayout();
    const belegHaken = speichern.zeilen()[belegIndex].teile['.pdf-layout-haken'];
    belegHaken.checked = false;
    belegHaken.onchange();
    speichern.felder['pdf-layout-girocode'].value = 'deckblatt';
    speichern.felder['pdf-layout-girocode'].onchange();
    await speichern.fns.pdfLayoutSpeichern();
    const put = speichern.aufrufe[1] || {};
    const erwartet = JSON.stringify({ bloecke: gesendet, girocode: 'deckblatt' });
    pruefe('PDF-Aufbau: Speichern schickt PUT mit Reihenfolge, An/Aus und GiroCode-Ort',
        put.url === '/api/einstellungen/pdf-layout' && put.methode === 'PUT' && put.koerper === erwartet
        && speichern.erfolge.length === 1 && speichern.fehlerMeldungen.length === 0);
    pruefe('PDF-Aufbau: nach dem Speichern eines eigenen Layouts sind beide Hinweise zu sehen',
        speichern.felder['pdf-layout-eigen'].hidden === false
        && speichern.felder['billing-pdf-layout-hinweis'].hidden === false);

    // 6. Fehler des Servers erscheinen wörtlich.
    const fehlerLauf = lauf([[200, antwort(standardIds, false)], [400, { error: 'Unbekannter Block „probe“.' }]]);
    await fehlerLauf.fns.ladePdfLayout();
    await fehlerLauf.fns.pdfLayoutSpeichern();
    pruefe('PDF-Aufbau: eine Meldung des Servers beim Speichern erscheint wörtlich',
        fehlerLauf.fehlerMeldungen.length === 1 && fehlerLauf.fehlerMeldungen[0] === 'Unbekannter Block „probe“.');

    // 7. Ein unbekannter Block kommt nur als Text in die Seite.
    const fremd = '<img src=x onerror=alert(1)>';
    const fremdLauf = lauf([[200, antwort([...standardIds, fremd], true)]]);
    await fremdLauf.fns.ladePdfLayout();
    pruefe('PDF-Aufbau: ein unbekannter Blockname steht als Text in der Liste, ohne HTML',
        fremdLauf.reihenfolge().includes(fremd) && fremdLauf.fehlerMeldungen.length === 0);

    // 8. Aufbau zurücksetzen: erst die Rückfrage, dann DELETE.
    const nein = lauf([[200, antwort(standardIds, true)]], false);
    await nein.fns.ladePdfLayout();
    await nein.fns.pdfLayoutStandard();
    const ja = lauf([[200, antwort(standardIds, true)], [200, antwort(standardIds, false)]]);
    await ja.fns.ladePdfLayout();
    await ja.fns.pdfLayoutStandard();
    pruefe('PDF-Aufbau: Aufbau zurücksetzen fragt nach, schickt dann DELETE und schließt den Hinweis',
        nein.aufrufe.length === 1 && ja.aufrufe.length === 2 && ja.aufrufe[1].methode === 'DELETE'
        && ja.aufrufe[1].url === '/api/einstellungen/pdf-layout' && ja.felder['pdf-layout-eigen'].hidden === true
        && nein.fragen.length === 1 && nein.fragen[0][1] === 'Aufbau zurücksetzen');
    pruefe('PDF-Aufbau: die Rückfrage zu „Aufbau zurücksetzen“ hat den roten Knopf (gefahr) wie andere zerstörende Rückfragen',
        nein.fragen[0][2] === true && nein.fragen[0][3] === 'Aufbau zurücksetzen?');

    // 8a. Ungespeicherte Änderungen: beim Verlassen der Gruppe fragen, nie still verwerfen.
    const ohneAenderung = lauf([[200, antwort(standardIds, false)]], false);
    await ohneAenderung.fns.ladePdfLayout();
    ohneAenderung.fns.zeigeEinstellungsgruppe('vermieter');
    pruefe('PDF-Aufbau: ohne Änderung wechselt die Gruppe sofort und ohne Rückfrage',
        ohneAenderung.fragen.length === 0 && ohneAenderung.aktiveGruppe() === 'vermieter');
    const bleiben = lauf([[200, antwort(standardIds, false)]], false);
    await bleiben.fns.ladePdfLayout();
    const bleibHaken = bleiben.zeilen()[belegIndex].teile['.pdf-layout-haken'];
    bleibHaken.checked = false;
    bleibHaken.onchange();
    bleiben.fns.zeigeEinstellungsgruppe('vermieter');
    await ruhe();
    const nachAbbruch = bleiben.stand();
    pruefe('PDF-Aufbau: Abbrechen bei der Rückfrage lässt die Gruppe „Abrechnung“ stehen und behält die Änderung',
        bleiben.fragen.length === 1 && bleiben.fragen[0][1] === 'Verwerfen' && bleiben.aktiveGruppe() === 'abrechnung'
        && nachAbbruch && nachAbbruch.bloecke[belegIndex].an === false);
    bleiben.fns.zeigeEinstellungsgruppe('abrechnung');
    await ruhe();
    pruefe('PDF-Aufbau: erneutes Öffnen der Gruppe lädt nicht neu und überschreibt die Änderung nicht',
        bleiben.aufrufe.length === 1 && bleiben.stand().bloecke[belegIndex].an === false
        && bleiben.zeilen()[belegIndex].teile['.pdf-layout-haken'].checked === false);
    const verwerfen = lauf([[200, antwort(standardIds, false)], [200, antwort(standardIds, false)]], true);
    await verwerfen.fns.ladePdfLayout();
    const wegHaken = verwerfen.zeilen()[belegIndex].teile['.pdf-layout-haken'];
    wegHaken.checked = false;
    wegHaken.onchange();
    verwerfen.fns.zeigeEinstellungsgruppe('vermieter');
    await ruhe();
    const nachVerwerfen = verwerfen.aktiveGruppe();
    verwerfen.fns.zeigeEinstellungsgruppe('abrechnung');
    await ruhe();
    pruefe('PDF-Aufbau: „Verwerfen“ wechselt die Gruppe, beim Wiederkommen gilt der gespeicherte Stand',
        verwerfen.fragen.length === 1 && nachVerwerfen === 'vermieter' && verwerfen.aufrufe.length === 2
        && verwerfen.stand().bloecke[belegIndex].an === true);

    // 8c. Neuladen oder Schließen der Seite: der Browser fragt nur bei ungespeicherten Änderungen.
    const seiteVerlassen = l => {
        const e = { abgewehrt: false, returnValue: undefined, preventDefault() { e.abgewehrt = true; } };
        l.fns.pdfLayoutVorDemVerlassen(e);
        return e;
    };
    const unload = lauf([[200, antwort(standardIds, false)]]);
    const vorDemLaden = seiteVerlassen(unload);
    await unload.fns.ladePdfLayout();
    const ohneAenderungUnload = seiteVerlassen(unload);
    const unloadHaken = unload.zeilen()[belegIndex].teile['.pdf-layout-haken'];
    unloadHaken.checked = false;
    unloadHaken.onchange();
    const mitAenderungUnload = seiteVerlassen(unload);
    pruefe('PDF-Aufbau: beim Verlassen der Seite fragt der Browser nur bei ungespeicherten Änderungen',
        !vorDemLaden.abgewehrt && !ohneAenderungUnload.abgewehrt
        && mitAenderungUnload.abgewehrt && mitAenderungUnload.returnValue === '');

    // 8e. Seitenwechsel, die die App selbst auslöst, hält der Browser nicht mit „Seite verlassen?“ auf.
    const mitAenderung = async (ja = true) => {
        const l = lauf([[200, antwort(standardIds, false)], [200, {}]], ja);
        await l.fns.ladePdfLayout();
        const h = l.zeilen()[belegIndex].teile['.pdf-layout-haken'];
        h.checked = false;
        h.onchange();
        return l;
    };
    const abmeldenNein = await mitAenderung(false);
    await abmeldenNein.fns.abmelden();
    pruefe('PDF-Aufbau: Abmelden mit ungespeichertem Aufbau fragt vorher; „Abbrechen“ meldet nicht ab',
        abmeldenNein.fragen.length === 1 && abmeldenNein.fragen[0][1] === 'Verwerfen' && abmeldenNein.fragen[0][2] === true
        && !abmeldenNein.aufrufe.some(a => a.url === '/logout')
        && !abmeldenNein.ablauf.some(s => s.startsWith('wechsel ')));
    const abmeldenJa = await mitAenderung(true);
    await abmeldenJa.fns.abmelden();
    pruefe('PDF-Aufbau: Abmelden fragt vor dem POST /logout, danach hält der Browser den Wechsel nicht auf',
        JSON.stringify(abmeldenJa.ablauf.slice(1)) === JSON.stringify(['frage', 'POST /logout', 'wechsel /login?abgemeldet=1'])
        && !seiteVerlassen(abmeldenJa).abgewehrt);
    const abmeldenOhne = lauf([[200, antwort(standardIds, false)], [200, {}]]);
    await abmeldenOhne.fns.ladePdfLayout();
    await abmeldenOhne.fns.abmelden();
    pruefe('PDF-Aufbau: Abmelden ohne Änderung fragt nicht',
        abmeldenOhne.fragen.length === 0
        && JSON.stringify(abmeldenOhne.ablauf.slice(1)) === JSON.stringify(['POST /logout', 'wechsel /login?abgemeldet=1']));
    const leerlauf = await mitAenderung();
    leerlauf.fenster.nkLetzteAnfrage = 0;
    new Function('document', 'window', 'entwurfSichern',
        'let letzteBedienung = 0; let leerlaufStill = false; const leerlaufMs = 1000; const LEERLAUF_WARNUNG_MS = 1;\n'
        + funktion('leerlaufPruefen') + '\nreturn leerlaufPruefen;')(leerlauf.dokument, leerlauf.fenster, () => {})();
    pruefe('PDF-Aufbau: die Leerlauf-Abmeldung mit ungespeichertem Aufbau löst kein „Seite verlassen?“ aus',
        leerlauf.ablauf.some(s => s.startsWith('wechsel /login')) && !seiteVerlassen(leerlauf).abgewehrt);
    const sperre = await mitAenderung();
    const huellQuelle = appQuelle.match(/\(function \(\) \{\n    const echtesFetch[\s\S]*?\n\}\)\(\);/);
    if (!huellQuelle) throw new Error('fetch-Umhüllung nicht gefunden');
    sperre.fenster.fetch = () => Promise.resolve({
        status: 401, clone: () => ({ json: () => Promise.resolve({ code: 'auth_required' }) }),
    });
    new Function('window', huellQuelle[0])(sperre.fenster);
    await sperre.fenster.fetch('/api/probe');
    pruefe('PDF-Aufbau: die Umleitung bei 401 mit ungespeichertem Aufbau löst kein „Seite verlassen?“ aus',
        sperre.ablauf.some(s => s.startsWith('wechsel /login')) && !seiteVerlassen(sperre).abgewehrt);

    // 8d. Weg zur Serverkarte mit ungespeichertem Aufbau: erst die Antwort, dann Scrollen und Fokus.
    const serverWeg = async ja => {
        const l = lauf([[200, antwort(standardIds, false)]], ja);
        await l.fns.ladePdfLayout();
        const h = l.zeilen()[belegIndex].teile['.pdf-layout-haken'];
        h.checked = false;
        h.onchange();
        fokussiert = null; fokusOptionen = null; gescrollt = null;
        l.fns.zeigeServerKarte();
        const sofort = [fokussiert, gescrollt];
        await ruhe();
        return { l, sofort, fokus: fokussiert, optionen: fokusOptionen, scroll: gescrollt };
    };
    const serverNein = await serverWeg(false);
    pruefe('PDF-Aufbau: „Abbrechen“ auf dem Weg zur Serverkarte lässt Gruppe und Fokus, scrollt nicht',
        serverNein.l.fragen.length === 1 && serverNein.l.aktiveGruppe() === 'abrechnung'
        && serverNein.fokus === null && serverNein.scroll === null
        && serverNein.l.stand().bloecke[belegIndex].an === false);
    const serverJa = await serverWeg(true);
    pruefe('PDF-Aufbau: nach „Verwerfen“ zeigt der Weg die Serverkarte oben und legt den Fokus ins Adressfeld',
        serverJa.sofort[0] === null && serverJa.sofort[1] === null
        && serverJa.l.aktiveGruppe() === 'sicherung' && serverJa.scroll === serverJa.l.felder['server-karte']
        && serverJa.fokus === serverJa.l.felder['server-adresse']
        && !!serverJa.optionen && serverJa.optionen.preventScroll === true);
    const serverOhne = lauf([[200, antwort(standardIds, false)]]);
    await serverOhne.fns.ladePdfLayout();
    fokussiert = null; gescrollt = null;
    serverOhne.fns.zeigeServerKarte();
    pruefe('PDF-Aufbau: ohne Änderung führt der Weg zur Serverkarte sofort und ohne Rückfrage',
        serverOhne.fragen.length === 0 && serverOhne.aktiveGruppe() === 'sicherung'
        && fokussiert === serverOhne.felder['server-adresse'] && gescrollt === serverOhne.felder['server-karte']
        && JSON.stringify(serverOhne.tabs) === JSON.stringify(['settings']));

    // 8b. Server antwortet 500 ohne JSON, Netz weg, Notseite statt JSON: verständliche Meldung, kein Hängen.
    // Die Karte sagt den Fehler an (role="alert"); eine zweite Meldung unten rechts gibt es nicht.
    const kartenText = l => l.felder['pdf-layout-ladefehler-text'].textContent;
    const laden500 = lauf([[500, OHNE_JSON]], true, true);
    await laden500.fns.ladePdfLayout();
    pruefe('PDF-Aufbau: 500 ohne JSON beim Laden nennt den Server in der Karte und meldet sich nur dort',
        laden500.fehlerMeldungen.length === 0 && kartenText(laden500) === ladeText.PDF_LAYOUT_SERVERFEHLER
        && /Server/.test(kartenText(laden500))
        && laden500.felder['pdf-layout-ladefehler'].hidden === false && laden500.zeilen().length === 0);
    const laden500Text = lauf([[500, { error: 'Die Datenbank ist gesperrt.' }]], true, true);
    await laden500Text.fns.ladePdfLayout();
    pruefe('PDF-Aufbau: eine Meldung des Servers beim Laden steht wörtlich in der Karte',
        laden500Text.fehlerMeldungen.length === 0 && kartenText(laden500Text) === 'Die Datenbank ist gesperrt.');
    const netzWeg = lauf([[NETZ_WEG], [200, antwort(standardIds, false)]], true, true);
    await netzWeg.fns.ladePdfLayout();
    const netzMeldung = netzWeg.felder['pdf-layout-ladefehler'].hidden;
    const netzText = kartenText(netzWeg);
    await netzWeg.fns.ladePdfLayout();
    pruefe('PDF-Aufbau: ohne Netz nennt die Karte die Verbindung; erneutes Laden räumt die Meldung weg',
        netzMeldung === false && netzText === ladeText.PDF_LAYOUT_LADEFEHLER && /Verbindung/.test(netzText)
        && netzWeg.fehlerMeldungen.length === 0
        && netzWeg.felder['pdf-layout-ladefehler'].hidden === true && netzWeg.zeilen().length === standardIds.length);
    // Zweimal derselbe Fehler: während des zweiten Ladens ist die Meldung verborgen,
    // danach erscheint sie neu und role="alert" sagt sie wieder an.
    const zweimal = lauf([[NETZ_WEG], [NETZ_WEG]], true, true);
    await zweimal.fns.ladePdfLayout();
    const ersterFehler = zweimal.felder['pdf-layout-ladefehler'].hidden;
    const zweitesLaden = zweimal.fns.ladePdfLayout();
    const waehrendLaden = zweimal.felder['pdf-layout-ladefehler'].hidden;
    await zweitesLaden;
    pruefe('PDF-Aufbau: ein zweiter gleicher Ladefehler nach „Aktualisieren“ erscheint neu (vorher verborgen)',
        ersterFehler === false && waehrendLaden === true
        && zweimal.felder['pdf-layout-ladefehler'].hidden === false
        && kartenText(zweimal) === ladeText.PDF_LAYOUT_LADEFEHLER && zweimal.fehlerMeldungen.length === 0);
    const notseite = lauf([[200, OHNE_JSON]], true, true);
    await notseite.fns.ladePdfLayout();
    pruefe('PDF-Aufbau: eine Antwort ohne JSON trotz 200 gilt als Ladefehler',
        kartenText(notseite) === ladeText.PDF_LAYOUT_LADEFEHLER && notseite.fehlerMeldungen.length === 0
        && notseite.felder['pdf-layout-ladefehler'].hidden === false);
    const ladeKarte = karte.match(/id="pdf-layout-ladefehler" role="alert" hidden>\s*<p class="karten-text" id="pdf-layout-ladefehler-text">([^<]*)<\/p>/);
    pruefe('PDF-Aufbau: der Vorgabetext der Ladefehler-Meldung in index.html ist der Text für Verbindungsfehler',
        !!ladeKarte && ladeKarte[1] === ladeText.PDF_LAYOUT_LADEFEHLER);
    await laden500.fns.pdfLayoutSpeichern();
    await laden500.fns.pdfLayoutVorschau();
    pruefe('PDF-Aufbau: Speichern und Vorschau ohne geladenen Aufbau melden sich, statt stumm zu bleiben',
        laden500.fehlerMeldungen.length === 2 && laden500.aufrufe.length === 1
        && laden500.fehlerMeldungen.every(m => m === laden500.fehlerMeldungen[0] && /nicht geladen/.test(m)));
    const fehler500 = lauf([[200, antwort(standardIds, false)], [500, OHNE_JSON], [500, OHNE_JSON], [500, OHNE_JSON]],
        true, true);
    await fehler500.fns.ladePdfLayout();
    await fehler500.fns.pdfLayoutSpeichern();
    await fehler500.fns.pdfLayoutVorschau();
    await fehler500.fns.pdfLayoutStandard();
    pruefe('PDF-Aufbau: 500 ohne JSON bei Speichern, Vorschau und Zurücksetzen zeigt je einen Ersatztext',
        JSON.stringify(fehler500.fehlerMeldungen) === JSON.stringify([
            'Der PDF-Aufbau konnte nicht gespeichert werden.', 'Die Vorschau konnte nicht erstellt werden.',
            'Der PDF-Aufbau konnte nicht zurückgesetzt werden.'])
        && fehler500.geoeffnet.length === 0 && fehler500.felder['btn-pdf-layout-vorschau'].disabled === false
        && fehler500.zeilen().length === standardIds.length);
    const hinweisZu = l => ['billing-pdf-layout-hinweis', 'frei-pdf-layout-hinweis'].forEach(id => {
        l.felder[id] = element('p');
        l.felder[id].hidden = true;
    });
    const hinweis500 = lauf([[500, OHNE_JSON]], true, true);
    hinweisZu(hinweis500);
    await hinweis500.fns.pdfLayoutHinweisLaden();
    const hinweisNetz = lauf([[NETZ_WEG]], true, true);
    hinweisZu(hinweisNetz);
    await hinweisNetz.fns.pdfLayoutHinweisLaden();
    pruefe('PDF-Aufbau: der Hinweis in den Abrechnungsdialogen bleibt bei Fehlern still und zu',
        hinweis500.fehlerMeldungen.length === 0 && hinweisNetz.fehlerMeldungen.length === 0
        && [hinweis500, hinweisNetz].every(l => l.felder['billing-pdf-layout-hinweis'].hidden === true
            && l.felder['frei-pdf-layout-hinweis'].hidden === true));

    // 9. Vorschau: POST …/vorschau mit dem ungespeicherten Stand, Öffnen über die Hülle.
    const vorschau = lauf([[200, antwort(standardIds, false)], [200, {}]]);
    await vorschau.fns.ladePdfLayout();
    await vorschau.fns.pdfLayoutVorschau();
    const post = vorschau.aufrufe[1] || {};
    pruefe('PDF-Aufbau: Vorschau schickt POST …/vorschau und öffnet die PDF über die Hülle',
        post.url === '/api/einstellungen/pdf-layout/vorschau' && post.methode === 'POST'
        && post.koerper === JSON.stringify({ bloecke: standardIds.map(id => ({ block: id, an: true })), girocode: 'zahlung' })
        && vorschau.geoeffnet.length === 1 && vorschau.geoeffnet[0].name === 'Layout-Vorschau.pdf'
        && vorschau.felder['btn-pdf-layout-vorschau'].disabled === false);
    const vorschauFehler = lauf([[200, antwort(standardIds, false)], [400, { error: 'Der Block „Übersicht“ steht doppelt im Layout.' }]]);
    await vorschauFehler.fns.ladePdfLayout();
    await vorschauFehler.fns.pdfLayoutVorschau();
    pruefe('PDF-Aufbau: bei einem Fehler der Vorschau öffnet sich nichts, die Meldung erscheint',
        vorschauFehler.geoeffnet.length === 0
        && vorschauFehler.fehlerMeldungen[0] === 'Der Block „Übersicht“ steht doppelt im Layout.');

    // 10. Der Dialog „Abrechnung erstellen“ fragt nur den Hinweis ab.
    const hinweis = lauf([[200, antwort(standardIds, true)]]);
    await hinweis.fns.pdfLayoutHinweisLaden();
    pruefe('PDF-Aufbau: der Dialog zeigt „Eigenes PDF-Layout aktiv“, wenn eins gespeichert ist',
        hinweis.felder['billing-pdf-layout-hinweis'].hidden === false && hinweis.fehlerMeldungen.length === 0);
    pruefe('PDF-Aufbau: auch der Dialog „Abrechnung frei erstellen“ zeigt den Hinweis',
        hinweis.felder['frei-pdf-layout-hinweis'].hidden === false);
}

// Beleg-Erhalt: Bearbeiten einer Rechnung hing ihren Beleg still auf eine fremde
// PDF um. Eine Datei aus einem früheren Dialog blieb im Dateifeld liegen,
// weder Öffnen noch Verwerfen leerte es. Die Belegauswahl kennt nur
// Sammelbelege, beim Einzelbeleg blieb sie leer, und Speichern schickte die
// liegengebliebene Datei mit. Der Wächter fährt die Schritte 1 bis 4 aus dem
// Befund mit den echten Funktionen aus app.js nach.
async function belegUmhaengenPruefen() {
    const quelle = name => {
        const m = appQuelle.match(new RegExp(`(?:async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`));
        if (!m) throw new Error(`${name} nicht gefunden`);
        return m[0];
    };
    // defineProperties statt Object.assign: Getter und Setter bleiben welche.
    const element = (mehr = {}) => Object.defineProperties({
        value: '', textContent: '', hidden: false, required: false, disabled: false, checked: false,
        style: {}, dataset: {}, parentElement: null,
        classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
        replaceChildren() {}, insertAdjacentHTML() {}, append() {}, setAttribute() {},
        querySelector: () => element(), closest: () => null,
    }, Object.getOwnPropertyDescriptors(mehr));
    // Ein <select> wie im Browser: ein Wert ohne passende Option wird ''.
    const auswahl = () => {
        let html = '';
        let wert = '';
        return element({
            get innerHTML() { return html; },
            set innerHTML(h) { html = h; wert = ''; },
            insertAdjacentHTML(_ort, h) { html += h; },
            replaceChildren() { html = ''; wert = ''; },
            get value() { return wert; },
            set value(v) {
                const da = [...html.matchAll(/value="([^"]*)"/g)].map(t => t[1]);
                wert = da.includes(String(v)) ? String(v) : '';
            },
        });
    };
    // Ein Dateifeld wie im Browser: value = '' leert die gewählten Dateien.
    const dateiFeld = () => {
        let dateien = [];
        return element({
            get files() { return dateien; },
            set files(f) { dateien = [...f]; },
            get value() { return dateien.length ? `C:\\fakepath\\${dateien[0].name}` : ''; },
            set value(v) { if (v === '') dateien = []; },
        });
    };
    const felder = {};
    for (const id of ['invoice-category', 'invoice-property', 'invoice-provider', 'invoice-document-id']) {
        felder[id] = auswahl();
    }
    felder['invoice-file'] = dateiFeld();
    const dokument = {
        getElementById: id => (felder[id] = felder[id] || element()),
        querySelector: () => element(),
        body: element(),
    };
    const gesendet = [];
    class FormDataAttrappe {
        constructor() { this.teile = []; }
        append(k, v) { this.teile.push([k, v]); }
        has(k) { return this.teile.some(t => t[0] === k); }
        get(k) { const t = this.teile.find(e => e[0] === k); return t ? t[1] : null; }
    }
    const belegA = { name: 'beleg-a.pdf' };
    const dateiB = { name: 'beleg-b.pdf' };
    const dateiC = { name: 'beleg-c.pdf' };
    const rechnungen = [
        { id: 1, category_id: 3, property_id: 2, provider_id: 4, amount: 80, invoice_number: 'S-1',
          start_date: '2024-01-01', end_date: '2024-12-31', invoice_document_id: 11,
          document_path: 'Testhaus/beleg-a.pdf', filename: belegA.name },
        { id: 2, category_id: 3, property_id: 2, provider_id: 4, amount: 50, invoice_number: 'S-2',
          start_date: '2024-01-01', end_date: '2024-12-31', invoice_document_id: 12,
          document_path: 'Testhaus/sammel.pdf', filename: 'sammel.pdf', document_pages: '2' },
        { id: 3, category_id: 3, property_id: 2, provider_id: 4, amount: 20, invoice_number: 'S-3',
          start_date: '2024-01-01', end_date: '2024-12-31', invoice_document_id: null,
          document_path: null, filename: null },
    ];
    const fns = new Function('document', 'categories', 'properties', 'providers', 'currentDocuments', 'invoices',
        'escapeHtml', 'zaehlerArtName', 'anbieterHinweisAktualisieren', 'populateInvoiceApartments',
        'populateInvoiceHeizung', 'toggleInvoiceHeizkosten', 'toggleInvoiceDescription', 'belegDatumAnbieten',
        'FormData', 'fetch', 'showError', 'showSuccess', 'serverFehler', 'meldungZu',
        'closeAddInvoiceModal', 'fetchInvoices',
        'let neueDatei = null, neueDateiAdresse = "", eingangRechnung = null, kostenAnsicht = "alle";\n'
        + quelle('openAddInvoiceModal') + quelle('toggleInvoiceFileUpload') + quelle('verwirfNeueDatei')
        + quelle('saveInvoice')
        + '; return { openAddInvoiceModal, verwirfNeueDatei, saveInvoice,'
        + ' setzeNeueDatei: d => { neueDatei = d; eingangRechnung = "neu"; } };')(
        dokument, [{ id: 3, name: 'Wartung' }], [{ id: 2, name: 'Testhaus' }],
        [{ id: 4, name: 'Kehrbezirk Probe' }],
        [{ id: 12, description: 'Sammelbeleg', property_name: 'Testhaus' }], rechnungen,
        s => String(s), n => n, () => {}, () => {}, async () => {}, () => {}, () => {}, () => {},
        FormDataAttrappe,
        async (url, opt) => { gesendet.push({ url, methode: opt.method, daten: opt.body }); return { ok: true, json: async () => ({ id: 1 }) }; },
        m => { throw new Error('showError: ' + m); }, () => {}, async r => r, (e, t) => t, () => {}, () => {});
    const spalte = element();
    const datei = felder['invoice-file'];
    const hinweis = () => felder['invoice-beleg-vorhanden'] || element({ hidden: true });

    // Schritt 1+2: B liegt im Dateifeld, „Datei verwerfen“ leert es mit.
    fns.setzeNeueDatei(dateiB);
    datei.files = [dateiB];
    fns.verwirfNeueDatei();
    pruefe('Beleg-Erhalt: „Datei verwerfen“ leert auch das Dateifeld des Rechnungsdialogs',
        datei.files.length === 0);

    // Schritt 3: R1 (Einzelbeleg A) öffnen, während B noch im Feld liegt.
    datei.files = [dateiB];
    await fns.openAddInvoiceModal(1, spalte);
    pruefe('Beleg-Erhalt: Bearbeiten leert das Dateifeld beim Öffnen', datei.files.length === 0);
    pruefe('Beleg-Erhalt: der Dialog zeigt den vorhandenen Einzelbeleg und dass er bleibt',
        hinweis().hidden === false && hinweis().textContent.includes(belegA.name)
        && /bleibt/.test(hinweis().textContent));

    // Schritt 4: speichern schickt keine Datei, der Beleg bleibt.
    gesendet.length = 0;
    await fns.saveInvoice();
    const ohne = gesendet[0] || { daten: new FormDataAttrappe() };
    pruefe('Beleg-Erhalt: Speichern ohne neue Datei schickt keine Datei mit',
        ohne.methode === 'PUT' && ohne.url === '/api/invoices/1'
        && !ohne.daten.has('file') && !ohne.daten.has('beleg_ersetzen'));

    // Bewusst ersetzen: wer im offenen Dialog eine Datei wählt, ersetzt ausdrücklich.
    await fns.openAddInvoiceModal(1, spalte);
    datei.files = [dateiC];
    gesendet.length = 0;
    await fns.saveInvoice();
    const mit = gesendet[0] || { daten: new FormDataAttrappe() };
    pruefe('Beleg-Erhalt: eine bewusst gewählte Datei ersetzt den Beleg ausdrücklich',
        mit.daten.get('file') === dateiC && String(mit.daten.get('beleg_ersetzen')) === 'true');

    // Sammelbeleg: die Auswahl zeigt ihn, kein Hinweis auf einen Einzelbeleg.
    datei.files = [dateiB];
    await fns.openAddInvoiceModal(2, spalte);
    pruefe('Beleg-Erhalt: am Sammelbeleg steht die Auswahl, das Dateifeld ist leer',
        felder['invoice-document-id'].value === '12' && datei.files.length === 0 && hinweis().hidden === true);

    // Rechnung ohne Beleg und neue Rechnung: leeres Feld, kein Hinweis.
    datei.files = [dateiB];
    await fns.openAddInvoiceModal(3, spalte);
    pruefe('Beleg-Erhalt: ohne Beleg kein Hinweis, das Dateifeld ist leer',
        datei.files.length === 0 && hinweis().hidden === true);
    datei.files = [dateiB];
    await fns.openAddInvoiceModal(null, spalte);
    pruefe('Beleg-Erhalt: auch eine neue Rechnung beginnt mit leerem Dateifeld',
        datei.files.length === 0 && hinweis().hidden === true);
}

(async () => {
    // NK-201/NK-204/NK-118/NK-216/NK-217/NK-226/NK-227/NK-230/NK-258/NK-261/
    // NK-262/NK-263/NK-267/NK-265 und Phase 54 (eigene Kostenarten): jede
    // Prüfung läuft, eine fehlgeschlagene bricht den Lauf nicht ab.
    const schritte = [
        ['warnLeistePruefen', 'NK-201: Warnleisten-Prüfung'],
        ['ausschalterPruefen', 'NK-204: Ausschalter-Prüfung'],
        ['haushaltPruefen', 'NK-118: Haushaltsprüfung'],
        ['nachfragePruefen', 'NK-216: Nachfrage-Prüfung'],
        ['korrekturPruefen', 'NK-217: Korrektur-Prüfung'],
        ['serienPruefen', 'NK-226: Serienbuchung-Prüfung'],
        ['ablesenPruefen', 'NK-227: Ablesen-Prüfung'],
        ['vorjahrPruefen', 'NK-230: Vorjahr-Prüfung'],
        ['zaehlerPflegePruefen', 'NK-258: Zählerpflege-Prüfung'],
        ['vorauszahlungPruefen', 'NK-261: Vorauszahlung-Prüfung'],
        ['kaltmietePruefen', 'Phase 49: Kaltmiete-Prüfung'],
        ['fristenPruefen', 'NK-262: Fristen-Prüfung'],
        ['mehrjahresblickPruefen', 'NK-263: Mehrjahresblick-Prüfung'],
        ['jahreswechselPruefen', 'NK-267: Jahreswechsel-Prüfung'],
        ['pruefstandPruefen', 'NK-265: Prüfstand-Prüfung'],
        ['kategorienPruefen', 'Phase 54: Kostenarten-Prüfung'],
        ['hausgeldPruefungPruefen', 'Phase 50: Hausgeld-Prüfung'],
        ['rechnungsJahrPruefen', 'Phase 57: Jahresfilter-Prüfung'],
        ['zeitleisteFilterPruefen', 'Phase 62: Zeitleistenfilter-Prüfung'],
        ['rechenwegTextPruefen', 'Rechenweg-Text-Prüfung'],
        ['belegDatumPruefen', 'Phase 64: Belegdatum-Prüfung'],
        ['auswahlKnoepfePruefen', 'Phase 65: Auswahlknopf-Prüfung'],
        ['fluchtPruefen', 'Phase 66: Fluchtlinien-Prüfung'],
        ['zeitleisteBelegPruefen', 'Phase 67: Beleg-Link in der Zeitleiste'],
        ['anschriftenPruefen', 'Phase 58: Anschriften-Prüfung'],
        ['zugriffsschluesselPruefen', 'Zugriffsschlüssel-Prüfung'],
        ['pdfLayoutPruefen', 'PDF-Aufbau-Prüfung'],
        ['belegUmhaengenPruefen', 'Beleg-Erhalt: Beleg-Umhängen-Prüfung'],
    ];
    for (const [name, label] of schritte) {
        try {
            await eval(name)();
        } catch (e) {
            pruefe(label + ' lief durch — ' + e.message, false);
        }
    }
    process.exit(fehler ? 1 : 0);
})();
