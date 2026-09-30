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
global.document = {
    getElementById: () => erzeugeElement(),
    createElement: () => erzeugeElement(),
    addEventListener() {},
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

try {
    new Function(appQuelle).call(global.window);
    pruefe('app.js laesst sich ohne Browser ausfuehren', true);
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
pruefe('BetrKV-Katalog gelesen (18 Kostenarten, NK-117)', katalog.length === 18);

const dialogFehler = (() => {
    try {
        const fnMatch = appQuelle.match(/function openAddMeterModal\(\) \{[\s\S]*?\n\}/);
        if (!fnMatch) return 'openAddMeterModal nicht gefunden';

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
        new Function('categories', 'properties', 'document', fnMatch[0] + '; openAddMeterModal();')(
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
        for (const k of katalog) {
            const n = namen.filter(n => n === k.name).length;
            if (n !== 1) return `„${k.name}“ ${n}mal in der Auswahl`;
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
const dialogNamen = katalog.map(k => k.name);
for (const muss of ['Beleuchtung (Allgemeinstrom)', 'Heizung']) {
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
            'let currentBillingSelection = null;\n'
            + [teil('vorgeschlagenerZeitraum'), teil('pruefeAbrechnungszeitraum'),
               teil('openBillingSelectionModal')].join('\n')
            + '\nreturn openBillingSelectionModal;')(
            dokument, m => meldungen.push(m), (...a) => aufrufe.push(a), s => String(s));
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
pruefe('Fuenf Auswahlpillen ohne Inline-Farben',
    (html.match(/class="filter-pill/g) || []).length === 5);
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
pruefe('K1: .kopf-aktionen in allen fünf Köpfen (global + vier Bereiche)',
    (ui.match(/class="kopf-aktionen"/g) || []).length === 5
    && css.includes('.kopf-aktionen {'));
pruefe('K1: .section-untertitel statt Inline-Stil (vier Köpfe)',
    (ui.match(/class="section-untertitel"/g) || []).length === 4
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
pruefe('B8: der Kopf nennt fünf Pflicht- und einen optionalen Schritt',
    html.includes('Fünf Schritte bis zur ersten Abrechnung, dazu ein optionaler.'));
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
pruefe('K5: bei ≤ 720 px rutscht der Knopf unter den Text',
    /\.erste-schritte-liste \.schritt \.btn-primary\s*\{[^}]*grid-column: 2;/m.test(css));
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

haushaltPruefen()
    .catch(e => pruefe('NK-118: Haushaltsprüfung lief durch — ' + e.message, false))
    .then(() => process.exit(fehler ? 1 : 0));
