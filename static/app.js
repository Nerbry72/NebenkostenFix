// ---------------------------------------------------------------------------
// Zentrale fetch-Umhuellung und Sitzungsanzeige (NK-021)
//
// Seit NK-019 antwortet jede API-Route ohne Sitzung mit 401. Diese Datei hat
// 52 fetch-Aufrufe und keinen einzigen davon behandelt 401. Ohne die
// Umhuellung waere das Ergebnis still kaputt: die Oberflaeche laedt, jede
// Liste bleibt leer, und nichts sagt, warum.
//
// Ueberschrieben wird window.fetch statt eines eigenen api()-Helfers. Ein
// Helfer muesste an 52 Stellen eingesetzt werden, und die 53. vergisst
// jemand. So geht jeder Aufruf darueber, auch jeder kuenftige.
// ---------------------------------------------------------------------------
(function () {
    const echtesFetch = window.fetch.bind(window);
    let leitetSchonUm = false;

    function zurAnmeldung() {
        // Nur einmal. Laufen zehn Aufrufe parallel in den 401, soll der
        // Browser nicht zehnmal navigieren.
        if (leitetSchonUm) return;
        leitetSchonUm = true;
        // NK-162: eine offene Eingabe überlebt die Abmeldung.
        if (window.entwurfSichern) window.entwurfSichern();
        const ziel = window.location.pathname + window.location.search;
        window.location.assign('/login?next=' + encodeURIComponent(ziel));
    }

    window.nkLetzteAnfrage = Date.now();
    window.fetch = async function (...argumente) {
        const antwort = await echtesFetch(...argumente);
        if (antwort.status !== 401) window.nkLetzteAnfrage = Date.now();
        if (antwort.status === 401 || antwort.status === 403) {
            // Nur die Sperre selbst leitet um. POST /login antwortet auf
            // falsche Zugangsdaten ebenfalls mit 401, das gehoert der
            // Anmeldeseite und wuerde sonst eine Schleife ausloesen.
            // Unterschieden wird am Feld code, das nur die Sperre setzt.
            let rumpf = null;
            try {
                rumpf = await antwort.clone().json();
            } catch (e) {
                rumpf = null;
            }
            if (rumpf && rumpf.code === 'auth_required') {
                zurAnmeldung();
            }
        }
        return antwort;
    };
})();

// ---------------------------------------------------------------------------
// Größere Schrift (NK-162, F-91): 100, 115 oder 130 %, im Browser gemerkt.
// zoom statt font-size: die Oberfläche misst in px, zoom vergrößert alles
// gleichmäßig und bricht den Umbruch wie bei einem schmaleren Fenster.
// ---------------------------------------------------------------------------
const SCHRIFTGROESSEN = [1, 1.15, 1.3];

function schriftgroesseAnwenden(faktor) {
    document.documentElement.style.zoom = faktor === 1 ? '' : String(faktor);
    // Für die Regeln, die mit vergrößerter Schrift früher umbrechen (style.css).
    if (faktor === 1) delete document.documentElement.dataset.schrift;
    else document.documentElement.dataset.schrift = String(faktor);
}

(function () {
    try {
        const faktor = Number(localStorage.getItem('nk-schrift') || '1');
        if (SCHRIFTGROESSEN.includes(faktor)) schriftgroesseAnwenden(faktor);
    } catch (e) {
        // ohne Speicher (privater Modus) bleibt es bei 100 %
    }
})();

function schriftgroesseWaehlen(wert) {
    const faktor = Number(wert);
    if (!SCHRIFTGROESSEN.includes(faktor)) return;
    schriftgroesseAnwenden(faktor);
    try {
        localStorage.setItem('nk-schrift', String(faktor));
    } catch (e) {
        // gilt dann nur bis zum Neuladen
    }
}
window.schriftgroesseWaehlen = schriftgroesseWaehlen;

function schriftgroesseZeigen() {
    let faktor = 1;
    try {
        faktor = Number(localStorage.getItem('nk-schrift') || '1');
    } catch (e) {
        faktor = 1;
    }
    document.querySelectorAll('input[name="schriftgroesse"]').forEach(feld => {
        feld.checked = Number(feld.value) === faktor;
    });
}

// ---------------------------------------------------------------------------
// Kategorien-Palette der Diagramme und Zustandspunkte (NK-067-Abnahme)
//
// Canvas-Zeichnungen (Chart.js) koennen keine CSS-Variablen lesen; die
// Kategorienfarben fuer Diagramme, Pillen und Kartenränder stehen deshalb
// hier an genau einer Stelle statt verstreut in den Renderfunktionen.
// ---------------------------------------------------------------------------
const DIAGRAMM_FARBE = {
    blau: '#3B82F6',
    gruen: '#10B981',
    gelb: '#F59E0B',
    lila: '#8B5CF6',
    rot: '#EF4444',
    grau: '#9CA3AF',
};

async function abmelden() {
    try {
        // Accept ausdruecklich setzen. Ohne den Kopf schickt der Browser
        // Accept: */*, der Server sieht keinen Wunsch und leitet auf die
        // Anmeldeseite um statt zu antworten. Das funktioniert auch, ist aber
        // ein Umweg ueber eine Seite, die hier niemand ansieht.
        await fetch('/logout', {
            method: 'POST',
            headers: { 'Accept': 'application/json' }
        });
    } catch (e) {
        // Netz weg. Die Sitzung liegt beim Server, also trotzdem hingehen:
        // dort faellt der naechste Aufruf sowieso in die Sperre.
    }
    window.location.assign('/login');
}
window.abmelden = abmelden;

async function zeigeAngemeldetenBenutzer() {
    try {
        const antwort = await fetch('/api/auth/me');
        if (!antwort.ok) return;
        const daten = await antwort.json();
        const feld = document.getElementById('angemeldeterBenutzer');
        if (feld) feld.textContent = daten.username;
        // NK-123: die Gefahrenzone gehoert nur in den Entwicklungsstapel.
        // Sie bleibt im HTML verborgen, bis /api/auth/me meldet, dass die
        // Entwicklerroute angemeldet ist -- im Auslieferungsbuild bleibt
        // sie verborgen, gleich, was irgendeine Umgebungsvariable sagt.
        const zone = document.getElementById('gefahrenzone');
        if (zone) zone.hidden = !daten.entwicklung;
        // NK-154: in der Windows-App steht „Passwort vergessen“ im Menü --
        // kein Serverbefehl für jemanden ohne Server.
        const vergessen = document.getElementById('konto-passwort-vergessen');
        if (vergessen && daten.desktop) {
            vergessen.textContent = 'Haben Sie Ihr Passwort vergessen, setzen Sie es über das Menü ' +
                '„Hilfe“ → „Passwort vergessen …“ dieses Programmfensters neu.';
        }
    } catch (e) {
        // Kein Grund, die Oberflaeche daran scheitern zu lassen.
    }
}

window.wrapInterpolated = (valStr, isInterpolated, infoObj) => {
    if (!isInterpolated) return valStr;
    let ttStr = `Wert wurde interpoliert.`;
    if (infoObj) {
        if (infoObj.target_days) {
            ttStr += `<br>Ziel-Zeitraum: ${infoObj.target_days} Tage`;
        }
        if (infoObj.basis_readings && infoObj.basis_readings.length > 0) {
            ttStr += `<br>Basis-Ablesungen (stückweise):<br>`;
            infoObj.basis_readings.forEach(r => {
                const rDate = new Date(r.date).toLocaleDateString('de-DE');
                ttStr += `- ${rDate} (${r.total.toFixed(1)} ${escapeHtml(infoObj.unit)})<br>`;
            });
        } else if (infoObj.r_start && infoObj.r_end) {
            const rStart = new Date(infoObj.r_start.date).toLocaleDateString('de-DE');
            const rEnd = new Date(infoObj.r_end.date).toLocaleDateString('de-DE');
            ttStr += `<br>Basis-Ablesungen:<br>
- ${rStart} (${infoObj.r_start.total.toFixed(1)} ${escapeHtml(infoObj.unit)})<br>
- ${rEnd} (${infoObj.r_end.total.toFixed(1)} ${escapeHtml(infoObj.unit)})`;
        }
    }
    let clickAttr = '';
    if (infoObj && infoObj.meter_id && infoObj.target_start_date && infoObj.target_end_date) {
        clickAttr = `onclick="openInterpolationAudit(${infoObj.meter_id}, '${infoObj.target_start_date}', '${infoObj.target_end_date}')"`;
    }
    
    return `<span class="interpolated-wrapper">
        <span class="interpolated-value"><b style="color:var(--primary);margin-right:4px;font-size:1.1em;">~</b> ${valStr}</span>
        <span class="math-icon" ${clickAttr}><i class="ph ph-calculator" aria-hidden="true"></i></span>
        <div class="glass-tooltip">${ttStr}</div>
    </span>`;
};

function getMeterConsumptionForPeriod(meterReadings, startDate, endDate) {
    if (!meterReadings || meterReadings.length < 2) return 0;
    
    const sorted = [...meterReadings]
        .map(r => ({ ...r, dateObj: new Date(r.reading_date) }))
        .sort((a,b) => a.dateObj - b.dateObj);
        
    let rStart = null;
    let rEnd = null;
    for (let i = 0; i < sorted.length; i++) {
        if (sorted[i].dateObj <= startDate) rStart = sorted[i];
        if (sorted[i].dateObj >= endDate && !rEnd) rEnd = sorted[i];
    }
    
    if (!rStart) rStart = sorted[0];
    if (!rEnd) rEnd = sorted[sorted.length - 1];
    
    if (rStart.id === rEnd.id) return 0;
    
    const totalDays = (rEnd.dateObj - rStart.dateObj) / (1000 * 60 * 60 * 24);
    const rStartVal = rStart.value + (rStart.value_nt || 0);
    const rEndVal = rEnd.value + (rEnd.value_nt || 0);
    
    if (totalDays <= 0) return 0;
    
    const daily = (rEndVal - rStartVal) / totalDays;
    const targetDays = (endDate - startDate) / (1000 * 60 * 60 * 24);
    return Math.max(0, daily * targetDays);
}

function initApp() {
    zeigeAngemeldetenBenutzer();
    initTabs();
    initModalBedienung();
    initBarrierearm();
    fetchProperties();
    fetchTenants();
    fetchAllApartments();
    fetchCategories();
    fetchMeters();
    fetchReadings();
    fetchInvoices();
    fetchDocuments();
    fetchProviders();
    fetchVermieterdaten();
    ladeKonten();
    ladeSicherungsStatus();
    ladeUmzug();
    ladeGesperrteMieter();
    ladeUpdateEinstellung();
    ladeBegriffe();
    fetchBillingSuggestions();
    fetchBillingHistory();
    fetchPayments();
    zeigeEinstellungsgruppe(gemerkteEinstellungsgruppe());
    startHinweise();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

// --- Global State ---
let properties = [];
let apartments = [];
let tenants = [];
let allApartments = [];
let currentPropertyId = null;
let categories = [];
let meters = [];
let readings = [];
let invoices = [];
let providers = [];
let payments = [];

// --- Utility ---
// --- Die Huelle: Fenster, Downloads, Druck an EINER Stelle (NK-152, F-81) ---
//
// Im Browser (Docker-Weg) verhaelt sich alles wie gewohnt: neuer Tab,
// Download ueber ein <a download>, Druckdialog des Browsers. In der Windows-
// App (pywebview, NK-079) gibt es keinen neuen Tab und keinen Download-
// Ordner des Browsers; dort nimmt die Bruecke der Huelle (window.pywebview.api)
// die Datei entgegen: nativer Speichern-Dialog bzw. Standardprogramm.
// Wer ein neues Fenster, einen Download oder den Druck anstoesst, geht ueber
// diese Funktionen -- tests/test_huelle.py verbietet direkte Aufrufe.
const huelle = {
    aktiv() {
        return !!(window.pywebview && window.pywebview.api);
    },

    async _base64(blob) {
        return await new Promise((fertig, fehler) => {
            const leser = new FileReader();
            leser.onload = () => fertig(String(leser.result).split(',', 2)[1] || '');
            leser.onerror = () => fehler(leser.error);
            leser.readAsDataURL(blob);
        });
    },

    _dateiname(antwort, ersatz) {
        const kopf = antwort.headers.get('Content-Disposition') || '';
        const utf8 = kopf.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8) return decodeURIComponent(utf8[1]);
        const einfach = kopf.match(/filename="?([^";]+)"?/i);
        return einfach ? einfach[1] : ersatz;
    },

    // Einen fertigen Blob speichern (Exporte, die im Browser entstehen).
    async blobSpeichern(blob, dateiname) {
        if (this.aktiv()) {
            await window.pywebview.api.speichern(dateiname, await this._base64(blob));
            return;
        }
        const adresse = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = adresse;
        link.download = dateiname;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(adresse), 1000);
    },

    // Große Dateien (Umzugspaket, NK-164): im Browser direkt über einen Link,
    // ohne den ganzen Inhalt als Blob in den Speicher zu holen.
    async direktHerunterladen(adresse, dateiname) {
        if (this.aktiv()) {
            await this.herunterladen(adresse, dateiname);
            return;
        }
        const link = document.createElement('a');
        link.href = adresse;
        link.download = dateiname;
        document.body.appendChild(link);
        link.click();
        link.remove();
    },

    // Eine Adresse der Anwendung als Datei speichern.
    async herunterladen(adresse, dateiname) {
        const antwort = await fetch(adresse);
        if (!antwort.ok) throw await serverFehler(antwort);
        const name = dateiname || this._dateiname(antwort, 'download');
        await this.blobSpeichern(await antwort.blob(), name);
    },

    // PDF, Foto oder Vertrag ansehen: neuer Tab bzw. Standardprogramm.
    async oeffnen(adresse) {
        if (!this.aktiv()) {
            window.open(adresse, '_blank', 'noopener');
            return;
        }
        // Projektseite, Ko-fi: im Standardbrowser, nicht im Fenster (NK-175).
        if (/^https:\/\/(github\.com|ko-fi\.com)\//.test(adresse)) {
            await window.pywebview.api.extern_oeffnen(adresse);
            return;
        }
        try {
            const antwort = await fetch(adresse);
            if (!antwort.ok) throw await serverFehler(antwort);
            const name = this._dateiname(antwort, 'datei');
            // fetch verwirft den Anker #page=N; die Brücke braucht die Seite selbst.
            const seite = adresse.match(/#page=(\d+)/);
            await window.pywebview.api.oeffnen(name, await this._base64(await antwort.blob()),
                seite ? Number(seite[1]) : null);
        } catch (e) {
            showError(meldungZu(e, 'Die Datei konnte nicht geöffnet werden.'));
        }
    },

    drucken() {
        window.print();
    },

    // Ordnerwahl fuer Sicherungen (nur in der App, F-76 unter Windows).
    async ordnerWaehlen() {
        if (!this.aktiv()) return null;
        return await window.pywebview.api.ordner_waehlen();
    },
};
window.huelle = huelle;

// Links mit target="_blank" oder download landen in der App bei der Huelle.
// Im Browser bleibt der Klick unberuehrt.
document.addEventListener('click', ereignis => {
    const link = ereignis.target.closest && ereignis.target.closest('a[target="_blank"], a[download]');
    if (!link || !huelle.aktiv()) return;
    ereignis.preventDefault();
    if (link.hasAttribute('download')) {
        huelle.herunterladen(link.href, link.getAttribute('download') || '')
            .catch(e => showError(meldungZu(e, 'Der Download ist fehlgeschlagen.')));
    } else {
        huelle.oeffnen(link.href);
    }
}, true);

// Adresse einer abgelegten Datei: nur Art und Kennung des Datensatzes, nie
// ein Pfad (NK-129). Der Server sucht den Pfad in der Datenbank und liefert
// mit festem Typ aus. Die Kennung ist eine Zahl -- kein Zeichen kann aus
// einem onclick="window.open('…')" ausbrechen (F-83).
function dateiAdresse(art, kennung) {
    return `/api/dateien/${encodeURIComponent(art)}/${Number(kennung)}`;
}

function escapeHtml(unsafe) {
    if (unsafe == null) return '';
    return unsafe.toString()
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

let editingPropertyId = null;
let editingApartmentId = null;
let editingTenantId = null;

// DOM Elements - General
const propertiesGrid = document.getElementById('properties-grid');
const statPropertiesCount = document.getElementById('stat-properties-count');
const propertyModal = document.getElementById('property-modal');

// DOM Elements - Apartments
const apartmentModal = document.getElementById('apartment-modal');
const propertyDetailsView = document.getElementById('property-details-view');
const apartmentsList = document.getElementById('apartments-list');
const detailPropTitle = document.getElementById('detail-prop-title');
const detailPropSqm = document.getElementById('detail-prop-sqm');

// DOM Elements - Tenants
const tenantModal = document.getElementById('tenant-modal');
const tenantsList = document.getElementById('tenants-list');
const statTenantsCount = document.getElementById('stat-tenants-count');
const statRevenueYtd = document.getElementById('stat-revenue-ytd');

// DOM Elements - Payments
const paymentModal = document.getElementById('payment-modal');
const paymentsGrid = document.getElementById('payments-grid');
const paymentDetailsModal = document.getElementById('payment-details-modal');
const paymentDetailsList = document.getElementById('payment-details-list');
const paymentDetailsTitle = document.getElementById('payment-details-title');

// Tab Navigation
function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navItems.forEach(nav => nav.classList.remove('active'));
            tabContents.forEach(tab => tab.classList.remove('active'));
            tabContents.forEach(tab => tab.style.display = 'none');
            
            item.classList.add('active');
            const targetId = 'tab-' + item.dataset.tab;
            const targetTab = document.getElementById(targetId);
            if (targetTab) {
                targetTab.classList.add('active');
                targetTab.style.display = 'block';
                
                if (item.dataset.tab === 'billing') {
                    fetchBillingSuggestions();
                    fetchBillingHistory();
                }
                if (item.dataset.tab === 'settings') {
                    zeigeEinstellungsgruppe(gemerkteEinstellungsgruppe());
                    fetchVermieterdaten();
                    ladeKonten();
                    ladeSicherungsStatus();
                    ladeUmzug();
                    ladeGesperrteMieter();
                    ladeUpdateEinstellung();
                }
                if (item.dataset.tab === 'reports') fetchAnalytics();
            }
        });
    });
    
    tabContents.forEach(tab => {
        if (!tab.classList.contains('active')) {
            tab.style.display = 'none';
        }
    });
}

// --- Erste Schritte (NK-072) ---
// Führung des ersten Starts: von der Immobilie bis zur ersten Abrechnung.
// Was erledigt ist, wird aus den Bestandszahlen abgelesen; Zähler sind nur
// nötig, wenn nach Verbrauch umgelegt wird, und zählen darum als optionaler
// Schritt. Sind alle Pflichtschritte erledigt, verschwindet das Panel.
// Aufgerufen wird nach jedem Laden, das eine dieser Zahlen ändert.

// Wie viele Abrechnungen schon erstellt sind; fetchBillingHistory pflegt sie.
let anzahlAbrechnungen = 0;
let abrechnungsHistorie = [];

// NK-159: was zum Beispielhaus gehört, zählt in keiner Kennzahl und in
// keinem Schritt der Führung.
function echterBestand() {
    const haeuser = new Set(properties.filter(p => p.ist_beispiel).map(p => p.id));
    const mieter = new Set(tenants.filter(t => t.ist_beispiel).map(t => t.id));
    const zaehler = new Set(meters.filter(m => haeuser.has(m.property_id)).map(m => m.id));
    return {
        properties: properties.filter(p => !p.ist_beispiel),
        apartments: allApartments.filter(a => !haeuser.has(a.property_id)),
        tenants: tenants.filter(t => !t.ist_beispiel),
        invoices: invoices.filter(i => !haeuser.has(i.property_id)),
        meters: meters.filter(m => !haeuser.has(m.property_id)),
        readings: readings.filter(r => !zaehler.has(r.meter_id)),
        payments: payments.filter(z => !z.ist_beispiel),
        abrechnungen: abrechnungsHistorie.filter(h => !mieter.has(h.tenant_id)).length,
    };
}

function wechsleZuTab(tabName) {
    if (tabName === 'hilfe') {
        zeigeHilfe();
        return;
    }
    const item = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
    if (item) item.click();
}

// --- Hilfe (NK-158, F-88) ------------------------------------------------------
// Die Begriffe kommen aus docs/glossar.md § 8 (static/hilfe-begriffe.json,
// erzeugt von scripts/hilfe_begriffe.py). Jedes „?“ an einem Fachbegriff
// öffnet eine kleine Blase mit dem einen Satz; „Hilfe öffnen“ im Kopf zeigt
// Grundlagen, Checkliste und alle Begriffe.

let hilfeBegriffe = {};

async function ladeBegriffe() {
    try {
        const res = await fetch('/static/hilfe-begriffe.json');
        if (!res.ok) return;
        const liste = await res.json();
        hilfeBegriffe = Object.fromEntries(liste.map(b => [b.schluessel, b]));
        document.querySelectorAll('.begriff-hilfe').forEach(knopf => {
            const begriff = hilfeBegriffe[knopf.dataset.begriff];
            if (begriff) knopf.setAttribute('aria-label', `Was heißt „${begriff.begriff}“?`);
        });
        const dl = document.getElementById('hilfe-begriffe-liste');
        dl.innerHTML = liste.slice().sort((a, b) => a.begriff.localeCompare(b.begriff, 'de'))
            .map(b => `<dt id="begriff-${escapeHtml(b.schluessel)}">${escapeHtml(b.begriff)}</dt><dd>${escapeHtml(b.satz)}</dd>`)
            .join('');
    } catch (e) {
        console.error('Hilfebegriffe nicht geladen', e);
    }
}

// „Über NebenkostenFix“ (NK-179): Adressen aus marke.py, einmal je Sitzung.
let ueberGeladen = false;

async function ladeUeber() {
    if (ueberGeladen) return;
    try {
        const res = await fetch('/api/ueber');
        if (!res.ok) return;
        const ueber = await res.json();
        document.getElementById('ueber-stand').textContent = `Version ${ueber.version} · ${ueber.weg}`;
        for (const [id, schluessel] of [['ueber-projektseite', 'projektseite'], ['ueber-neuigkeiten', 'neuigkeiten'],
            ['ueber-fehler-melden', 'fehler_melden'], ['ueber-unterstuetzen', 'unterstuetzen'], ['ueber-lizenz', 'lizenz']]) {
            document.getElementById(id).href = ueber[schluessel];
        }
        document.getElementById('ueber-haftung').innerHTML = ueber.haftung.map(satz => `<p>${escapeHtml(satz)}</p>`).join('');
        ueberGeladen = true;
    } catch (e) {
        console.error('Über-Angaben nicht geladen', e);
    }
}

function zeigeHilfe(abschnitt) {
    schliesseBegriffBlase();
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    const hilfe = document.getElementById('tab-hilfe');
    hilfe.classList.add('active');
    hilfe.style.display = 'block';
    hilfeChecklisteLaden();
    ladeUeber();
    const ziel = abschnitt && document.getElementById(abschnitt);
    if (ziel) {
        ziel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
        window.scrollTo({ top: 0 });
    }
}
window.zeigeHilfe = zeigeHilfe;

function hilfeChecklisteLaden() {
    let stand = {};
    try {
        stand = JSON.parse(localStorage.getItem('nk-hilfe-checkliste') || '{}');
    } catch (e) {
        stand = {};  // ohne Speicher (privater Modus) beginnt die Liste leer
    }
    document.querySelectorAll('#hilfe-checkliste input').forEach(haken => {
        haken.checked = !!stand[haken.dataset.punkt];
        haken.onchange = () => {
            stand[haken.dataset.punkt] = haken.checked;
            try {
                localStorage.setItem('nk-hilfe-checkliste', JSON.stringify(stand));
            } catch (e) {
                // nur Bequemlichkeit: ohne Speicher gilt der Haken bis zum Neuladen
            }
        };
    });
}

function schliesseBegriffBlase() {
    const blase = document.getElementById('begriff-blase');
    if (blase) blase.hidden = true;
}

document.addEventListener('click', ereignis => {
    const knopf = ereignis.target.closest && ereignis.target.closest('.begriff-hilfe');
    const blase = document.getElementById('begriff-blase');
    if (!blase) return;
    if (!knopf) {
        if (!blase.contains(ereignis.target)) schliesseBegriffBlase();
        return;
    }
    ereignis.preventDefault();
    ereignis.stopPropagation();
    const begriff = hilfeBegriffe[knopf.dataset.begriff];
    if (!begriff) return;
    document.getElementById('begriff-blase-titel').textContent = begriff.begriff;
    document.getElementById('begriff-blase-text').textContent = begriff.satz;
    blase.hidden = false;
    const rahmen = knopf.getBoundingClientRect();
    const breite = Math.min(320, window.innerWidth - 24);
    blase.style.width = `${breite}px`;
    blase.style.left = `${Math.max(12, Math.min(rahmen.left, window.innerWidth - breite - 12))}px`;
    blase.style.top = `${rahmen.bottom + 8}px`;
}, true);

document.addEventListener('keydown', ereignis => {
    if (ereignis.key === 'Escape') schliesseBegriffBlase();
});
window.addEventListener('scroll', schliesseBegriffBlase, true);

// „Was bedeutet das für den Mieter?“ -- das Ergebnis in einem Satz (NK-158).
function mieterErklaerung(daten) {
    const euro = betrag => Math.abs(betrag).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
    const kosten = euro(daten.total_amount);
    const voraus = euro(daten.prepaid_amount);
    if (daten.balance > 0.004) {
        return `Der Mieter muss ${euro(daten.balance)} nachzahlen: Auf ihn entfallen ${kosten} Kosten, ` +
            `vorausgezahlt hat er ${voraus}.`;
    }
    if (daten.balance < -0.004) {
        return `Der Mieter bekommt ${euro(daten.balance)} zurück: Er hat ${voraus} vorausgezahlt, ` +
            `auf ihn entfallen nur ${kosten} Kosten.`;
    }
    return `Kosten (${kosten}) und Vorauszahlungen (${voraus}) gleichen sich aus: Es bleibt weder ` +
        'eine Nachzahlung noch ein Guthaben.';
}

function mieterErklaerungHtml(daten) {
    return '<div class="mieter-erklaerung"><strong>Was bedeutet das für den Mieter?</strong>' +
        `<p>${escapeHtml(mieterErklaerung(daten))}</p></div>`;
}

function zeigeErsteSchritte() {
    const panel = document.getElementById('erste-schritte');
    const liste = document.getElementById('erste-schritte-liste');
    if (!panel || !liste) return;

    // NK-159: das Beispielhaus zählt nicht als erledigter Schritt -- wer es
    // ausprobiert, soll die Führung für die eigenen Daten behalten.
    const echt = echterBestand();
    const beispielDa = properties.some(p => p.ist_beispiel);
    const schritte = [
        { titel: 'Erst ausprobieren', beschreibung: beispielDa
            ? 'Das Beispielhaus zeigt eine fertige Abrechnung des Vorjahres mit PDF. Es zählt in keiner Kennzahl; löschen Sie es, wenn Sie es nicht mehr brauchen.'
            : 'Ein fertiges Beispielhaus mit Rechnungen, Vorauszahlungen und einer Abrechnung als PDF — so sieht das Ziel aus.',
          erledigt: beispielDa, pflicht: false, nummer: 0, immerKnopf: true,
          aktionsText: beispielDa ? 'Beispiel löschen' : 'Beispiel anlegen',
          aktion: beispielDa ? 'beispielLoeschen(this)' : 'beispielAnlegen(this)' },
        { titel: 'Immobilie anlegen', beschreibung: 'Das Haus, dessen Kosten Sie umlegen wollen.', erledigt: echt.properties.length > 0, pflicht: true, aktionsText: 'Immobilie anlegen', aktion: 'openAddPropertyModal()' },
        { titel: 'Wohnung anlegen', beschreibung: 'Jede vermietete Wohnung — über den Knopf auf der Immobilien-Karte.', erledigt: echt.apartments.length > 0, pflicht: true, aktionsText: 'Immobilien öffnen', aktion: "wechsleZuTab('properties')" },
        { titel: 'Mieter anlegen', beschreibung: 'Wer in der Wohnung wohnt und abgerechnet wird.', erledigt: echt.tenants.length > 0, pflicht: true, aktionsText: 'Mieter anlegen', aktion: 'openAddTenantModal()' },
        { titel: 'Rechnungen erfassen', beschreibung: 'Die Kosten des Jahres: Gas, Strom, Müll, Versicherung und mehr.', erledigt: echt.invoices.length > 0, pflicht: true, aktionsText: 'Rechnungen öffnen', aktion: "wechsleZuTab('invoices')" },
        { titel: 'Zähler & Ablesungen erfassen', beschreibung: 'Nur nötig, wenn Kosten nach Verbrauch umgelegt werden — etwa Strom oder Wasser mit eigenem Zähler.', erledigt: echt.meters.length > 0 && echt.readings.length > 0, pflicht: false, aktionsText: 'Zähler öffnen', aktion: "wechsleZuTab('meters')" },
        { titel: 'Erste Abrechnung erstellen', beschreibung: 'Am Jahresende oder beim Auszug. Der Assistent prüft vorher, was fehlt.', erledigt: echt.abrechnungen > 0, pflicht: true, aktionsText: 'Jahr abrechnen', aktion: 'oeffneJahrAssistent()' },
    ];

    const offen = schritte.filter(s => !s.erledigt);
    panel.hidden = !offen.some(s => s.pflicht);
    if (panel.hidden) return;

    // K5 (NK-103): Fortschritt „x von 5 erledigt“ mit schmalem Balken —
    // nur die fünf Pflichtschritte zählen, der optionale nicht (B8).
    const erledigtPflicht = schritte.filter(s => s.erledigt && s.pflicht).length;
    const stand = document.getElementById('erste-schritte-stand');
    const balken = document.getElementById('erste-schritte-balken');
    if (stand) stand.textContent = `${erledigtPflicht} von 5 erledigt`;
    if (balken) balken.style.width = `${Math.round(erledigtPflicht / 5 * 100)}%`;

    // Der hervorgehobene Schritt ist immer der erste offene Pflichtschritt --
    // ein optionaler Schritt (Zähler) lenkt die Führung nicht ab.
    const naechster = offen.find(s => s.pflicht);
    liste.replaceChildren();
    schritte.forEach((s, i) => {
        const li = document.createElement('li');
        li.className = 'schritt' + (s.erledigt ? ' erledigt' : '') +
            (s === naechster ? ' aktuell' : '') + (s.pflicht ? '' : ' optional');
        const marke = s.erledigt
            ? '<i class="ph ph-check-circle" aria-hidden="true"></i>'
            : (s.nummer !== undefined ? s.nummer : i);
        // K5: die Pille „optional“ steht hinter dem Titel, auf dessen
        // Grundlinie — nicht im Titel (B8).
        const hinweis = s.pflicht ? '' : '<span class="schritt-hinweis">optional</span>';
        const knopf = s === naechster
            ? `<button type="button" class="btn-primary" onclick="${s.aktion}">${s.aktionsText}</button>`
            : (s.immerKnopf
                ? `<button type="button" class="btn-secondary" onclick="${s.aktion}">${s.aktionsText}</button>`
                : '');
        li.innerHTML = `
            <span class="schritt-marke" aria-hidden="true">${marke}</span>
            <div class="schritt-text">
                <div class="schritt-titel-zeile"><strong>${s.titel}</strong>${hinweis}</div>
                <span>${s.beschreibung}</span>
            </div>
            ${knopf}`;
        liste.appendChild(li);
    });
}

// Modals mit der Tastatur verlassen (NK-067): Escape schließt alle offenen
// Ebenen; ein Klick ins Leere (auf die Abdeckung selbst) schließt die eine.
// mousedown statt click, damit ein Textmarkieren, das auf der Abdeckung
// endet, das Dialog nicht versehentlich zuklappt.
// NK-162: Tastatur und Fokus in jedem Dialog -- der Fokus springt beim
// Öffnen ins erste Feld, Tab bleibt im Dialog, beim Schließen kehrt er zum
// Auslöser zurück. Wer Eingaben gemacht hat, wird vor dem Schließen gefragt
// (Escape, Klick daneben, X, Abbrechen); Speichern schließt ohne Frage.
const dialogAusloeser = new WeakMap();

// Rückfrage im Design der App statt des Browserdialogs: die Windows-App zeigte sonst
// ein Systemfenster „127.0.0.1 sagt …“. Escape, Klick daneben, X und
// Abbrechen heißen „nein“ -- jedes Schließen ohne den Hauptknopf.
function frage(text, ja = 'Weiter', gefahr = false, titel = 'Bitte bestätigen') {
    const overlay = document.getElementById('frage-modal');
    const knopf = document.getElementById('frage-ja');
    document.getElementById('frage-titel').textContent = titel;
    document.getElementById('frage-text').textContent = text;
    knopf.textContent = ja;
    knopf.className = gefahr ? 'btn-gefahr' : 'btn-primary';
    overlay.dataset.antwort = '';
    overlay.classList.add('active');
    return new Promise(erledigt => {
        const wache = new MutationObserver(() => {
            if (overlay.classList.contains('active')) return;
            wache.disconnect();
            erledigt(overlay.dataset.antwort === 'ja');
        });
        wache.observe(overlay, { attributes: true, attributeFilter: ['class'] });
    });
}

function frageLoeschen(text) {
    return frage(text, 'Löschen', true, 'Löschen bestätigen');
}

function frageAntwort(ja) {
    const overlay = document.getElementById('frage-modal');
    overlay.dataset.antwort = ja ? 'ja' : '';
    overlay.classList.remove('active');
}
window.frageAntwort = frageAntwort;

async function darfDialogSchliessen(overlay) {
    if (overlay.dataset.geaendert !== '1') return true;
    const ja = await frage('Ihre Eingaben in diesem Dialog sind noch nicht gespeichert. Trotzdem schließen?',
        'Verwerfen', true, 'Eingaben verwerfen?');
    if (ja) overlay.dataset.geaendert = '';
    return ja;
}

async function schliessenNachFrage(overlay) {
    // data-fest: nur der eigene Knopf schließt (Haftungshinweis, NK-174).
    if (overlay.dataset.fest) return;
    if (await darfDialogSchliessen(overlay)) overlay.classList.remove('active');
}

function fokussierbar(bereich) {
    return [...bereich.querySelectorAll(
        'input:not([type="hidden"]), select, textarea, button, a[href], [tabindex]:not([tabindex="-1"])')]
        .filter(el => !el.disabled && el.offsetParent !== null);
}

function ersterFokus(overlay) {
    const modal = overlay.querySelector('.modal') || overlay;
    const felder = fokussierbar(modal.querySelector('.modal-body') || modal)
        .filter(el => ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName));
    const ziel = felder[0] || fokussierbar(modal)[0];
    if (ziel && !modal.contains(document.activeElement)) ziel.focus();
}

function initModalBedienung() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            // Nur der oberste Dialog: über dem Jahresassistenten liegen oft
            // der Rechnungs- oder Ablesedialog (NK-160).
            const oben = [...document.querySelectorAll('.modal-overlay.active')].pop();
            if (oben) schliessenNachFrage(oben);
        }
        if (e.key === 'Tab') {
            const offen = [...document.querySelectorAll('.modal-overlay.active')].pop();
            if (!offen) return;
            const felder = fokussierbar(offen.querySelector('.modal') || offen);
            if (!felder.length) return;
            const erstes = felder[0];
            const letztes = felder[felder.length - 1];
            if (!offen.contains(document.activeElement)) {
                e.preventDefault();
                erstes.focus();
            } else if (e.shiftKey && document.activeElement === erstes) {
                e.preventDefault();
                letztes.focus();
            } else if (!e.shiftKey && document.activeElement === letztes) {
                e.preventDefault();
                erstes.focus();
            }
        }
    });
    // X und „Abbrechen“ fragen nach, bevor ihr eigener Handler schließt.
    document.addEventListener('click', (e) => {
        const knopf = e.target.closest && e.target.closest('.modal-overlay.active button');
        if (!knopf) return;
        const schliesst = knopf.querySelector('.ph-x') || knopf.textContent.trim() === 'Abbrechen';
        if (!schliesst) return;
        const overlay = knopf.closest('.modal-overlay');
        if (overlay.dataset.geaendert !== '1') return;
        e.preventDefault();
        e.stopPropagation();
        // Nach „Verwerfen“ denselben Knopf noch einmal auslösen; dann ist
        // nichts mehr geändert und sein eigener Handler schließt.
        darfDialogSchliessen(overlay).then(ja => { if (ja) knopf.click(); });
    }, true);
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('mousedown', (e) => {
            if (e.target === overlay) schliessenNachFrage(overlay);
        });
        const modal = overlay.querySelector('.modal');
        if (modal) {
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            const titel = modal.querySelector('h2');
            if (titel) {
                if (!titel.id) titel.id = `${overlay.id}-titel`;
                modal.setAttribute('aria-labelledby', titel.id);
            }
        }
        // Nur Eingaben des Menschen zählen; das Vorbelegen beim Öffnen nicht.
        overlay.addEventListener('input', () => { overlay.dataset.geaendert = '1'; });
        new MutationObserver(() => {
            const aktiv = overlay.classList.contains('active');
            if (aktiv && overlay.dataset.offen !== '1') {
                overlay.dataset.offen = '1';
                overlay.dataset.geaendert = '';
                dialogAusloeser.set(overlay, document.activeElement);
                setTimeout(() => ersterFokus(overlay), 60);
            } else if (!aktiv && overlay.dataset.offen === '1') {
                overlay.dataset.offen = '';
                overlay.dataset.geaendert = '';
                const zurueck = dialogAusloeser.get(overlay);
                if (zurueck && document.contains(zurueck) && zurueck.focus) zurueck.focus();
            }
        }).observe(overlay, { attributes: true, attributeFilter: ['class'] });
    });
}

// NK-162: jeder Symbolknopf hat einen Namen für Screenreader -- auch die,
// die app.js erst zur Laufzeit baut (Bearbeiten, Löschen in Listen).
const SYMBOL_NAMEN = {
    'ph-x': 'Schließen', 'ph-trash': 'Löschen', 'ph-pencil-simple': 'Bearbeiten',
    'ph-eye': 'Ansehen', 'ph-download-simple': 'Herunterladen', 'ph-plus': 'Anlegen',
    'ph-file-pdf': 'PDF ansehen', 'ph-clock-counter-clockwise': 'Verlauf ansehen',
};

function symbolknoepfeBenennen(wurzel) {
    wurzel.querySelectorAll('button, a.btn-icon').forEach(knopf => {
        if (knopf.getAttribute('aria-label') || knopf.textContent.trim()) return;
        if (knopf.title) {
            knopf.setAttribute('aria-label', knopf.title);
            return;
        }
        const symbol = knopf.querySelector('i');
        const klasse = symbol && [...symbol.classList].find(k => SYMBOL_NAMEN[k]);
        if (klasse) knopf.setAttribute('aria-label', SYMBOL_NAMEN[klasse]);
    });
}

// NK-162: mit beschrifteter Seitenleiste und größerer Schrift wird der
// Inhalt auf dem Tablet schmal. Jede Tabelle in einer Karte rollt dann in
// sich, statt die Seite zu verbreitern -- gleich, wo sie gebaut wurde.
function tabellenEinrollen(wurzel) {
    wurzel.querySelectorAll('.dashboard-card table, .glass-panel table, .modal table').forEach(tabelle => {
        const eltern = tabelle.parentElement;
        if (!eltern || eltern.classList.contains('tabellen-rolle')) return;
        const x = getComputedStyle(eltern).overflowX;
        if (x === 'auto' || x === 'scroll') return;
        const rolle = document.createElement('div');
        rolle.className = 'tabellen-rolle';
        eltern.insertBefore(rolle, tabelle);
        rolle.appendChild(tabelle);
    });
}

function initBarrierearm() {
    document.querySelectorAll('.nav-item').forEach(eintrag => {
        const name = eintrag.textContent.trim();
        eintrag.setAttribute('aria-label', name);
        eintrag.title = name;
    });
    symbolknoepfeBenennen(document);
    tabellenEinrollen(document);
    let geplant = false;
    new MutationObserver(() => {
        if (geplant) return;
        geplant = true;
        requestAnimationFrame(() => {
            geplant = false;
            symbolknoepfeBenennen(document);
            tabellenEinrollen(document);
        });
    }).observe(document.body, { childList: true, subtree: true });
    schriftgroesseZeigen();
    initLeerlauf();
    entwurfAnbieten();
}

// --- Leerlauf-Abmeldung (NK-162) --------------------------------------------
// Vorher ging eine offene Eingabe verloren: nach SITZUNG_LEERLAUF_MIN ohne
// Anfrage antwortete der Server mit 401, die Seite sprang zur Anmeldung.
// Jetzt: wer tippt oder klickt, gilt als da (die Sitzung wird still
// verlängert); fünf Minuten vor der Abmeldung steht ein Hinweis mit
// „Angemeldet bleiben“; und eine offene Eingabe wird vor der Umleitung im
// Sitzungsspeicher gesichert und nach der Anmeldung angeboten.
const LEERLAUF_WARNUNG_MS = 5 * 60 * 1000;
let leerlaufMs = 60 * 60 * 1000;
let letzteBedienung = Date.now();

async function initLeerlauf() {
    try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
            const ich = await res.json();
            if (ich.leerlauf_s) leerlaufMs = ich.leerlauf_s * 1000;
        }
    } catch (e) {
        // Standard 60 Minuten
    }
    const bedient = () => {
        letzteBedienung = Date.now();
        // Wer arbeitet, soll nicht mitten im Tippen abgemeldet werden: ist die
        // letzte Anfrage länger her, hält eine stille Anfrage die Sitzung.
        if (Date.now() - window.nkLetzteAnfrage > Math.min(LEERLAUF_WARNUNG_MS, leerlaufMs / 2)) {
            window.nkLetzteAnfrage = Date.now();
            fetch('/api/auth/me').catch(() => {});
        }
    };
    ['keydown', 'pointerdown'].forEach(art => document.addEventListener(art, bedient, true));
    setInterval(leerlaufPruefen, 15000);
}

function leerlaufPruefen() {
    const hinweis = document.getElementById('leerlauf-hinweis');
    if (!hinweis) return;
    const still = Date.now() - Math.max(window.nkLetzteAnfrage, letzteBedienung);
    const rest = leerlaufMs - still;
    if (rest <= 0) {
        entwurfSichern();
        window.location.assign('/login?next=' + encodeURIComponent(window.location.pathname));
        return;
    }
    if (rest <= LEERLAUF_WARNUNG_MS) {
        const minuten = Math.max(1, Math.ceil(rest / 60000));
        document.getElementById('leerlauf-text').textContent =
            `Sie werden in ${minuten} ${minuten === 1 ? 'Minute' : 'Minuten'} abgemeldet, weil nichts passiert ist.`;
        hinweis.hidden = false;
    } else {
        hinweis.hidden = true;
    }
}

async function angemeldetBleiben() {
    letzteBedienung = Date.now();
    try {
        await fetch('/api/auth/me');
    } catch (e) {
        // Netz weg: der nächste Versuch klärt es
    }
    document.getElementById('leerlauf-hinweis').hidden = true;
}
window.angemeldetBleiben = angemeldetBleiben;

function entwurfSichern() {
    const offen = [...document.querySelectorAll('.modal-overlay.active')].pop();
    if (!offen || !offen.id) return;
    const werte = {};
    offen.querySelectorAll('input[id], select[id], textarea[id]').forEach(feld => {
        if (['password', 'file', 'hidden'].includes(feld.type)) return;
        werte[feld.id] = (feld.type === 'checkbox' || feld.type === 'radio') ? feld.checked : feld.value;
    });
    const titel = offen.querySelector('h2');
    try {
        sessionStorage.setItem('nk-entwurf', JSON.stringify({
            dialog: offen.id, titel: titel ? titel.textContent.trim() : '', werte, zeit: Date.now() }));
    } catch (e) {
        // ohne Sitzungsspeicher kein Entwurf
    }
}
window.entwurfSichern = entwurfSichern;

function entwurfLesen() {
    try {
        const entwurf = JSON.parse(sessionStorage.getItem('nk-entwurf') || 'null');
        if (entwurf && Date.now() - entwurf.zeit < 24 * 3600 * 1000) return entwurf;
    } catch (e) {
        return null;
    }
    return null;
}

function entwurfAnbieten() {
    const entwurf = entwurfLesen();
    const hinweis = document.getElementById('entwurf-hinweis');
    if (!entwurf || !hinweis || !document.getElementById(entwurf.dialog)) return;
    document.getElementById('entwurf-titel').textContent = entwurf.titel || 'einem Dialog';
    hinweis.hidden = false;
}

function entwurfWiederherstellen() {
    const entwurf = entwurfLesen();
    entwurfVerwerfen();
    if (!entwurf) return;
    const overlay = document.getElementById(entwurf.dialog);
    overlay.classList.add('active');
    for (const [id, wert] of Object.entries(entwurf.werte)) {
        const feld = document.getElementById(id);
        if (!feld) continue;
        if (feld.type === 'checkbox' || feld.type === 'radio') feld.checked = !!wert;
        else feld.value = wert;
    }
    // Nach dem Beobachter des Dialogs, der beim Öffnen zurücksetzt (Mikroaufgabe).
    setTimeout(() => { overlay.dataset.geaendert = '1'; }, 0);
    showSuccess('Ihre Eingabe ist wiederhergestellt. Prüfen Sie die Auswahlfelder, bevor Sie speichern.');
}
window.entwurfWiederherstellen = entwurfWiederherstellen;

function entwurfVerwerfen() {
    try {
        sessionStorage.removeItem('nk-entwurf');
    } catch (e) {
        // nichts zu tun
    }
    const hinweis = document.getElementById('entwurf-hinweis');
    if (hinweis) hinweis.hidden = true;
}
window.entwurfVerwerfen = entwurfVerwerfen;

// API Calls - Properties
async function fetchProperties() {
    try {
        const response = await fetch('/api/properties');
        if (!response.ok) throw await serverFehler(response);
        properties = await response.json();
        updateDashboard();
        zeigeErsteSchritte();
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Laden der Immobilien.'));
    }
}

async function saveProperty() {
    const nameInput = document.getElementById('prop-name');
    const standaloneInput = document.getElementById('prop-standalone');
    const name = nameInput.value.trim();
    const isStandalone = standaloneInput.checked;
    
    if (!name) {
        showError('Bitte geben Sie einen Namen für die Immobilie ein.');
        return;
    }
    
    try {
        const method = editingPropertyId ? 'PUT' : 'POST';
        const url = editingPropertyId ? `/api/properties/${editingPropertyId}` : '/api/properties';
        
        const response = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: name, is_standalone: isStandalone })
        });
        
        if (!response.ok) throw await serverFehler(response);
        
        closeAddPropertyModal();
        fetchProperties();
        fetchTenants(); 
        fetchAllApartments();
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Speichern der Immobilie.'));
    }
}

async function deleteProperty(id) {
    const haus = properties.find(p => p.id === id);
    if (haus && haus.ist_beispiel) {
        // NK-159: das Beispiel geht ganz, ohne Aufbewahrungssperre.
        await beispielLoeschen(null);
        return;
    }
    if (!await frageLoeschen('Möchten Sie diese Immobilie samt aller Wohnungen und Mieter wirklich löschen?')) return;
    try {
        const response = await fetch(`/api/properties/${id}`, { method: 'DELETE' });
        if (!response.ok) throw await serverFehler(response);
        fetchProperties();
        fetchTenants(); 
        fetchAllApartments();
        if (currentPropertyId === id) {
            propertyDetailsView.style.display = 'none';
            currentPropertyId = null;
        }
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Löschen der Immobilie.'));
    }
}

// K4 (NK-102): der einzige Erzeuger des Leerzustands. Alle Bereiche
// hängen hier ab — acht handgeschriebene Kopien sind verschwunden (B4),
// der Knopf heißt stets „nächster sinnvoller Schritt“ und ist primär.
function leerzustand({ icon, titel, text, aktion = null }) {
    // Knopftexte stehen in ${}-Ausdrücken, damit der Beschriftungs-Prüfer
    // den Knopf als dynamischen Text erkennt (Glossar Par. 6).
    const iconImKnopf = aktion && aktion.icon
        ? `<i class="ph ${aktion.icon}" aria-hidden="true"></i> `
        : '';
    const knopf = aktion
        ? `<button type="button" class="btn-primary" onclick="${aktion.fn}">${iconImKnopf}${aktion.label}</button>`
        : '';
    return `<div class="empty-state glass-panel">` +
        `<div class="empty-state-inhalt">` +
        `<i class="ph ${icon} leer-icon" aria-hidden="true"></i>` +
        `<h3>${titel}</h3>` +
        `<p>${text}</p>` + knopf +
        `</div></div>`;
}

function updateDashboard() {
    statPropertiesCount.textContent = properties.filter(p => !p.ist_beispiel).length;
    // NK-156: „zurück“ nur, wenn es schon etwas gibt, zu dem man zurückkommt.
    const begruessung = document.getElementById('begruessung');
    if (begruessung) {
        begruessung.textContent = properties.length
            ? 'Willkommen zurück!' : 'Willkommen bei NebenkostenFix!';
    }
    
    if (statRevenueYtd) {
        const currentYear = new Date().getFullYear().toString();
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        let actualMiete = 0;
        let actualVorauszahlung = 0;
        let actualNachzahlung = 0;
        
        let forecastedTotal = 0;
        
        payments.filter(p => !p.ist_beispiel && p.payment_date && p.payment_date.startsWith(currentYear)).forEach(p => {
            const pDate = new Date(p.payment_date);
            if (pDate <= today) {
                if (p.type === 'Miete') actualMiete += p.amount;
                else if (p.type === 'Nebenkostenvorauszahlung') actualVorauszahlung += p.amount;
                else if (p.type === 'Nebenkostenzahlung') actualNachzahlung += p.amount;
            } else {
                forecastedTotal += p.amount;
            }
        });
        
        const actualTotal = actualMiete + actualVorauszahlung + actualNachzahlung;
        statRevenueYtd.textContent = actualTotal.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
        statRevenueYtd.title = `Tatsächlicher Umsatz ${currentYear}: ${actualMiete.toLocaleString('de-DE',{style:'currency',currency:'EUR'})} Miete | ${actualVorauszahlung.toLocaleString('de-DE',{style:'currency',currency:'EUR'})} VZ | ${actualNachzahlung.toLocaleString('de-DE',{style:'currency',currency:'EUR'})} NZ`;
        statRevenueYtd.style.cursor = 'help';
        
        const statRevenueForecast = document.getElementById('stat-revenue-forecast');
        if (statRevenueForecast) {
            if (forecastedTotal > 0) {
                statRevenueForecast.textContent = `+ ${forecastedTotal.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })} prognostiziert`;
            } else {
                statRevenueForecast.textContent = '';
            }
        }
    }
    
    propertiesGrid.replaceChildren();

    if (properties.length === 0) {
        propertiesGrid.innerHTML = leerzustand({
            icon: 'ph-house',
            titel: 'Noch keine Immobilie angelegt',
            text: 'Legen Sie das Haus an, dessen Kosten Sie umlegen wollen — zum Beispiel Ihr Mehrfamilienhaus.',
            aktion: { label: 'Immobilie anlegen', fn: 'openAddPropertyModal()', icon: 'ph-plus' },
        });
        return;
    }
    
    properties.forEach(prop => {
        const card = document.createElement('div');
        card.className = 'property-card glass-panel';
        card.style.cursor = 'pointer';
        card.onclick = () => showPropertyDetails(prop);
        
        const header = document.createElement('div');
        header.className = 'prop-header';
        
        const iconDiv = document.createElement('div');
        iconDiv.className = 'prop-icon';
        const icon = document.createElement('i');
        icon.className = prop.is_standalone ? 'ph ph-door' : 'ph ph-buildings';
        iconDiv.appendChild(icon);
        
        const actionsDiv = document.createElement('div');
        actionsDiv.style.display = 'flex';
        actionsDiv.style.gap = '8px';
        
        const editBtn = document.createElement('button');
        editBtn.className = 'btn-icon';
        editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
        editBtn.onclick = (e) => { e.stopPropagation(); openAddPropertyModal(prop); };
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn-icon';
        deleteBtn.innerHTML = '<i class="ph ph-trash"></i>';
        deleteBtn.onclick = (e) => { e.stopPropagation(); deleteProperty(prop.id); };
        
        actionsDiv.appendChild(editBtn);
        actionsDiv.appendChild(deleteBtn);
        
        header.appendChild(iconDiv);
        header.appendChild(actionsDiv);
        
        const title = document.createElement('h3');
        title.className = 'prop-title';
        title.textContent = prop.name;
        if (prop.ist_beispiel) {
            const marke = document.createElement('span');
            marke.className = 'badge-beispiel';
            marke.textContent = 'Beispiel';
            title.appendChild(marke);
        }
        
        const meta = document.createElement('div');
        meta.className = 'prop-meta';
        const metaItem = document.createElement('span');
        metaItem.innerHTML = `<i class="ph ph-info"></i> ${prop.is_standalone ? ' Einzelwohnung' : ' Mehrfamilienhaus'}`;
        meta.appendChild(metaItem);
        
        card.appendChild(header);
        card.appendChild(title);
        card.appendChild(meta);
        
        propertiesGrid.appendChild(card);
    });
}

// API Calls - Apartments
async function fetchAllApartments() {
    try {
        const response = await fetch('/api/apartments');
        if (!response.ok) throw await serverFehler(response);
        allApartments = await response.json();
        populateApartmentDropdown();
        zeigeErsteSchritte();
    } catch (e) {
        console.error(e);
    }
}

function populateApartmentDropdown() {
    const select = document.getElementById('tenant-apartment');
    select.replaceChildren();
    
    const defaultOpt = document.createElement('option');
    defaultOpt.value = "";
    defaultOpt.textContent = "Bitte wählen...";
    select.appendChild(defaultOpt);
    
    allApartments.forEach(apt => {
        const opt = document.createElement('option');
        opt.value = apt.id;
        opt.textContent = apt.property_name + " - " + apt.name + " (" + apt.sqm + " m²)";
        select.appendChild(opt);
    });
}

async function showPropertyDetails(prop) {
    currentPropertyId = prop.id;
    detailPropTitle.textContent = "Wohnungen in " + prop.name;
    propertyDetailsView.style.display = 'block';
    
    try {
        const response = await fetch(`/api/properties/${prop.id}/apartments`);
        if (!response.ok) throw await serverFehler(response);
        const apartments = await response.json();
        
        let totalSqm = 0;
        apartmentsList.replaceChildren();
        if (apartments.length === 0) {
            const empty = document.createElement('div');
            empty.textContent = 'Noch keine Wohnungen angelegt. Legen Sie die erste mit dem Knopf „Wohnung anlegen“ oben an.';
            empty.style.color = "var(--text-muted)";
            apartmentsList.appendChild(empty);
        } else {
            apartments.forEach(apt => {
                totalSqm += apt.sqm;
                
                const item = document.createElement('div');
                item.style.padding = '12px';
                item.style.background = 'rgba(255,255,255,0.4)';
                item.style.borderRadius = '8px';
                item.style.display = 'flex';
                item.style.justifyContent = 'space-between';
                item.style.alignItems = 'center';
                
                const infoDiv = document.createElement('div');
                infoDiv.innerHTML = `<strong>${escapeHtml(apt.name)}</strong> <span style="color:var(--text-muted)">(${apt.sqm} m²)</span>`;
                
                const actionsDiv = document.createElement('div');
                actionsDiv.style.display = 'flex';
                actionsDiv.style.gap = '8px';
                
                const editBtn = document.createElement('button');
                editBtn.className = 'btn-icon';
                editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
                editBtn.onclick = () => openAddApartmentModal(apt);
                
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn-icon';
                deleteBtn.innerHTML = '<i class="ph ph-trash"></i>';
                deleteBtn.onclick = () => deleteApartment(apt.id);
                
                actionsDiv.appendChild(editBtn);
                actionsDiv.appendChild(deleteBtn);
                
                item.appendChild(infoDiv);
                item.appendChild(actionsDiv);
                apartmentsList.appendChild(item);
            });
        }
        
        if (detailPropSqm) {
            detailPropSqm.textContent = "Gesamtfläche: " + totalSqm.toFixed(2) + " m²";
        }

        // NK-125: die Heizungsanlagen der Immobilie über der Wohnungsliste.
        await renderHeizungsanlagen(prop.id);
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Laden der Wohnungen.'));
    }
}

// --- Heizungsanlagen (NK-125): die Anlage als eigene Sache ---

let aktuelleHeizungsanlagen = [];

const HEIZKOSTENARTEN_TEXT = {
    brennstoff: 'Brennstoff und seine Lieferung',
    betriebsstrom: 'Betriebsstrom',
    bedienung: 'Bedienung, Überwachung und Pflege der Anlage',
    pruefung: 'Prüfung der Betriebsbereitschaft und Betriebssicherheit',
    reinigung: 'Reinigung der Anlage und des Betriebsraums',
    messung: 'Messungen nach dem Bundes-Immissionsschutzgesetz',
    anmietung_erfassung: 'Anmietung der Ausstattung zur Verbrauchserfassung',
    verwendung_erfassung: 'Verwendung der Verbrauchserfassung, Eichung, Abrechnung'
};

const VERSORGUNG_TEXT = {
    heizung: 'Nr. 4 — Heizung',
    warmwasser: 'Nr. 5 — Warmwasser',
    verbunden: 'Nr. 6 — Heizung und Warmwasser (verbundene Anlage)'
};

const WW_WEG_TEXT = {
    zaehler: 'gemessen mit Wärmemengenzähler',
    formel: 'berechnet nach der Formel des § 9 Abs. 2 Satz 4',
    ersatz: 'Ersatzmaßstab (§ 9 Abs. 2 Satz 5)'
};

async function fetchHeizungsanlagen(propertyId) {
    const response = await fetch(`/api/properties/${propertyId}/heizungsanlagen`);
    if (!response.ok) throw await serverFehler(response);
    return response.json();
}

async function renderHeizungsanlagen(propertyId) {
    const list = document.getElementById('anlagen-list');
    if (!list) return;
    aktuelleHeizungsanlagen = await fetchHeizungsanlagen(propertyId);
    list.replaceChildren();

    if (aktuelleHeizungsanlagen.length === 0) return;

    const kopf = document.createElement('div');
    kopf.innerHTML = '<strong>Heizungsanlagen</strong> <span style="color:var(--text-muted)">(die Anlage trägt den Verbrauchsanteil des § 7 Abs. 1 HeizkostenV und ihre Rechnungen)</span>';
    list.appendChild(kopf);

    aktuelleHeizungsanlagen.forEach(anlage => {
        const item = document.createElement('div');
        item.style.padding = '12px';
        item.style.background = 'rgba(255,255,255,0.4)';
        item.style.borderRadius = '8px';
        item.style.display = 'flex';
        item.style.justifyContent = 'space-between';
        item.style.alignItems = 'center';

        let beschreibung = `${VERSORGUNG_TEXT[anlage.versorgt] || anlage.versorgt}, ` +
            `${anlage.verbrauchsanteil_prozent} vom Hundert nach Verbrauch`;
        if (anlage.sonderfall_70) beschreibung += ', Sonderfall § 7 Abs. 1 Satz 2';
        if (anlage.warmwasser_weg) {
            beschreibung += `, Warmwasser ${WW_WEG_TEXT[anlage.warmwasser_weg] || anlage.warmwasser_weg}`;
        }

        const infoDiv = document.createElement('div');
        infoDiv.innerHTML = `<strong>${escapeHtml(anlage.name)}</strong> <span style="color:var(--text-muted)">— ${escapeHtml(beschreibung)}</span>`;

        const actionsDiv = document.createElement('div');
        actionsDiv.style.display = 'flex';
        actionsDiv.style.gap = '8px';

        const editBtn = document.createElement('button');
        editBtn.className = 'btn-icon';
        editBtn.title = 'Anlage bearbeiten';
        editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
        editBtn.onclick = () => openHeizungsanlageModal(anlage);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn-icon';
        deleteBtn.title = 'Anlage löschen';
        deleteBtn.innerHTML = '<i class="ph ph-trash"></i>';
        deleteBtn.onclick = () => deleteHeizungsanlage(anlage);

        actionsDiv.appendChild(editBtn);
        actionsDiv.appendChild(deleteBtn);

        item.appendChild(infoDiv);
        item.appendChild(actionsDiv);
        list.appendChild(item);
    });
}

function toggleVerbundenBlock() {
    const versorgt = document.getElementById('heizung-versorgt').value;
    const block = document.getElementById('heizung-verbunden-block');
    block.style.display = versorgt === 'verbunden' ? 'block' : 'none';
    toggleWwWeg();
}

function toggleWwWeg() {
    const weg = document.getElementById('heizung-ww-weg').value;
    document.getElementById('gruppe-ww-zaehler').style.display = weg === 'zaehler' ? 'block' : 'none';
    document.getElementById('gruppe-ww-formel').style.display = weg === 'formel' ? 'block' : 'none';
}

function toggleSonderfall() {
    const sonderfall = document.getElementById('heizung-sonderfall').checked;
    const anteil = document.getElementById('heizung-anteil');
    if (sonderfall) anteil.value = '70';
    anteil.disabled = sonderfall;
}

function openHeizungsanlageModal(anlage) {
    const modal = document.getElementById('heizungsanlage-modal');
    document.getElementById('heizung-id').value = anlage ? anlage.id : '';
    document.getElementById('heizung-property-id').value = currentPropertyId;
    document.getElementById('heizung-name').value = anlage ? anlage.name : '';
    document.getElementById('heizung-versorgt').value = anlage ? anlage.versorgt : 'heizung';
    document.getElementById('heizung-anteil').value = anlage ? anlage.verbrauchsanteil_prozent : '55';
    document.getElementById('heizung-sonderfall').checked = anlage ? anlage.sonderfall_70 : false;
    document.getElementById('heizung-ww-weg').value = (anlage && anlage.warmwasser_weg) ? anlage.warmwasser_weg : 'zaehler';
    document.getElementById('heizung-ww-kwh').value = (anlage && anlage.warmwasser_kwh != null) ? anlage.warmwasser_kwh : '';
    document.getElementById('heizung-ww-volumen').value = (anlage && anlage.warmwasser_volumen_m3 != null) ? anlage.warmwasser_volumen_m3 : '';
    document.getElementById('heizung-ww-temperatur').value = (anlage && anlage.warmwasser_temperatur_c != null) ? anlage.warmwasser_temperatur_c : '';
    document.getElementById('heizung-brennstoff').value = (anlage && anlage.brennstoff_menge != null) ? anlage.brennstoff_menge : '';
    document.getElementById('heizung-heizwert').value = (anlage && anlage.heizwert_kwh != null) ? anlage.heizwert_kwh : '';
    toggleSonderfall();
    toggleVerbundenBlock();
    modal.classList.add('active');
}

async function saveHeizungsanlage() {
    const id = document.getElementById('heizung-id').value;
    const propertyId = document.getElementById('heizung-property-id').value;
    const nutzdaten = {
        name: document.getElementById('heizung-name').value.trim(),
        versorgt: document.getElementById('heizung-versorgt').value,
        verbrauchsanteil_prozent: parseInt(document.getElementById('heizung-anteil').value, 10),
        sonderfall_70: document.getElementById('heizung-sonderfall').checked,
        warmwasser_weg: document.getElementById('heizung-ww-weg').value,
        warmwasser_kwh: document.getElementById('heizung-ww-kwh').value || null,
        warmwasser_volumen_m3: document.getElementById('heizung-ww-volumen').value || null,
        warmwasser_temperatur_c: document.getElementById('heizung-ww-temperatur').value || null,
        brennstoff_menge: document.getElementById('heizung-brennstoff').value || null,
        heizwert_kwh: document.getElementById('heizung-heizwert').value || null
    };

    try {
        const url = id ? `/api/heizungsanlagen/${id}` : `/api/properties/${propertyId}/heizungsanlagen`;
        const methode = id ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: methode,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(nutzdaten)
        });
        if (!response.ok) throw await serverFehler(response);
        document.getElementById('heizungsanlage-modal').classList.remove('active');
        const prop = properties.find(p => p.id == propertyId);
        if (prop) await showPropertyDetails(prop);
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Speichern der Anlage.'));
    }
}

async function deleteHeizungsanlage(anlage) {
    if (!await frageLoeschen(`Anlage „${anlage.name}" löschen?`)) return;
    try {
        const response = await fetch(`/api/heizungsanlagen/${anlage.id}`, { method: 'DELETE' });
        if (!response.ok) throw await serverFehler(response);
        const prop = properties.find(p => p.id == currentPropertyId);
        if (prop) await showPropertyDetails(prop);
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Löschen der Anlage.'));
    }
}

async function saveApartment() {
    if (!currentPropertyId) return;
    
    const name = document.getElementById('apt-name').value.trim();
    const sqm = parseFloat(document.getElementById('apt-sqm').value);
    // NK-124: die Fachfelder der Wohnung wandern mit.
    const nutzungsart = document.getElementById('apt-nutzungsart').value;
    const eigennutzung = document.getElementById('apt-eigennutzung').checked;
    const selbstversorger = document.getElementById('apt-selbstversorger').checked;
    
    if (!name || isNaN(sqm) || sqm < 0.01 || sqm > 500) {
        showError('Bitte geben Sie einen Namen und eine gültige Wohnfläche in m² (0,01 - 500) ein.');
        return;
    }
    
    try {
        const method = editingApartmentId ? 'PUT' : 'POST';
        const url = editingApartmentId ? `/api/apartments/${editingApartmentId}` : '/api/apartments';
        
        const response = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, sqm, property_id: currentPropertyId, nutzungsart, eigennutzung, selbstversorger })
        });
        
        if (!response.ok) throw await serverFehler(response);
        
        closeAddApartmentModal();
        showPropertyDetails({ id: currentPropertyId, name: detailPropTitle.textContent.replace('Wohnungen in ', '') });
        fetchAllApartments();
        fetchTenants(); // In case apartment name changed, update the UI in tenants list
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Speichern der Wohnung.'));
    }
}

async function deleteApartment(id) {
    if (!await frageLoeschen('Möchten Sie diese Wohnung samt aller Mieter wirklich löschen?')) return;
    try {
        const response = await fetch(`/api/apartments/${id}`, { method: 'DELETE' });
        if (!response.ok) throw await serverFehler(response);
        showPropertyDetails({ id: currentPropertyId, name: detailPropTitle.textContent.replace('Wohnungen in ', '') });
        fetchAllApartments();
        fetchTenants();
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Löschen der Wohnung.'));
    }
}


// API Calls - Tenants
async function fetchTenants() {
    try {
        const response = await fetch('/api/tenants');
        if (!response.ok) throw await serverFehler(response);
        tenants = await response.json();
        
        statTenantsCount.textContent = tenants.filter(t => !t.ist_beispiel).length;
        zeigeErsteSchritte();
        
        const container = document.getElementById('tenants-container');
        if (!container) return; // Guard clause
        container.replaceChildren();
        
        if (tenants.length === 0) {
            if (allApartments.length === 0) {
                // K4: fehlt die Voraussetzung, führt der Knopf dorthin —
                // ebenfalls als Primärknopf.
                container.innerHTML = leerzustand({
                    icon: 'ph-users',
                    titel: 'Noch keine Mieter angelegt',
                    text: 'Mieter ziehen in eine Wohnung ein — legen Sie zuerst eine Wohnung an.',
                    aktion: { label: 'Immobilien öffnen', fn: "wechsleZuTab('properties')" },
                });
            } else {
                container.innerHTML = leerzustand({
                    icon: 'ph-users',
                    titel: 'Noch keine Mieter angelegt',
                    text: 'Erfassen Sie, wer in welcher Wohnung wohnt — das ist die Grundlage jeder Abrechnung.',
                    aktion: { label: 'Mieter anlegen', fn: 'openAddTenantModal()', icon: 'ph-plus' },
                });
            }
            return;
        }
        
        // Group tenants by property_name
        const grouped = {};
        tenants.forEach(t => {
            const prop = t.property_name || 'Unbekannt';
            if (!grouped[prop]) grouped[prop] = [];
            grouped[prop].push(t);
        });
        
        // Render a box for each property
        Object.keys(grouped).forEach(propName => {
            const box = document.createElement('div');
            box.className = 'glass-panel';
            box.style.padding = '24px';
            
            const title = document.createElement('h3');
            title.textContent = propName;
            title.style.marginBottom = '16px';
            title.style.borderBottom = '2px solid rgba(79, 70, 229, 0.2)';
            title.style.paddingBottom = '8px';
            box.appendChild(title);
            
            const table = document.createElement('table');
            table.style.width = '100%';
            table.style.borderCollapse = 'collapse';
            table.style.textAlign = 'left';
            
            const thead = document.createElement('thead');
            thead.innerHTML = `
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <th style="padding: 12px 8px;">Name</th>
                    <th style="padding: 12px 8px;">Wohnung</th>
                    <th style="padding: 12px 8px;">Einzug</th>
                    <th style="padding: 12px 8px;">Auszug</th>
                    <th style="padding: 12px 8px;">Mietvertrag</th>
                    <th style="padding: 12px 8px;">Aktionen</th>
                </tr>
            `;
            table.appendChild(thead);
            
            const tbody = document.createElement('tbody');
            
            grouped[propName].forEach(t => {
                const tr = document.createElement('tr');
                tr.style.borderBottom = "1px solid var(--border-color)";
                
                const tdName = document.createElement('td');
                tdName.style.padding = "12px 8px";
                tdName.textContent = t.name;
                
                const tdApt = document.createElement('td');
                tdApt.style.padding = "12px 8px";
                tdApt.textContent = t.apartment_name;
                
                const tdIn = document.createElement('td');
                tdIn.style.padding = "12px 8px";
                tdIn.textContent = new Date(t.move_in_date).toLocaleDateString('de-DE');
                
                const tdOut = document.createElement('td');
                tdOut.style.padding = "12px 8px";
                tdOut.textContent = t.move_out_date ? new Date(t.move_out_date).toLocaleDateString('de-DE') : '-';
                
                const tdContract = document.createElement('td');
                tdContract.style.padding = "12px 8px";
                if (t.contract_path) {
                    const contractBtn = document.createElement('button');
                    contractBtn.className = 'btn-icon';
                    contractBtn.innerHTML = '<i class="ph ph-file-text"></i> Ansehen';
                    contractBtn.style.fontSize = '0.85rem';
                    contractBtn.style.color = 'var(--primary-color)';
                    contractBtn.onclick = () => huelle.oeffnen(`/api/tenants/${t.id}/contract`);
                    tdContract.appendChild(contractBtn);
                } else {
                    tdContract.textContent = '-';
                }
                
                const tdActions = document.createElement('td');
                tdActions.style.padding = "12px 8px";
                tdActions.style.display = "flex";
                tdActions.style.gap = "8px";
                
                const editBtn = document.createElement('button');
                editBtn.className = 'btn-icon';
                editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
                editBtn.onclick = () => openAddTenantModal(t);
                
                const profileBtn = document.createElement('button');
                profileBtn.className = 'btn-icon';
                profileBtn.innerHTML = '<i class="ph ph-sliders"></i>';
                profileBtn.title = 'Kostenprofil';
                profileBtn.onclick = () => openCostProfileModal(t.id, t.name);

                const householdBtn = document.createElement('button');
                householdBtn.className = 'btn-icon';
                householdBtn.innerHTML = '<i class="ph ph-users-three"></i>';
                householdBtn.title = 'Haushaltsgröße';
                householdBtn.onclick = () => openHouseholdModal(t);

                // NK-078: Auskunft als ZIP -- JSON mit allen Zeilen zum
                // Mietverhaeltnis und die Dateien dazu.
                const exportBtn = document.createElement('button');
                exportBtn.className = 'btn-icon';
                exportBtn.innerHTML = '<i class="ph ph-download-simple"></i>';
                exportBtn.title = 'Auskunft über dieses Mietverhältnis herunterladen';
                exportBtn.onclick = () => exportiereMieter(t.id);

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn-icon';
                deleteBtn.innerHTML = '<i class="ph ph-trash"></i>';
                deleteBtn.onclick = () => deleteTenant(t.id);
                
                tdActions.appendChild(editBtn);
                tdActions.appendChild(profileBtn);
                tdActions.appendChild(householdBtn);
                tdActions.appendChild(exportBtn);
                tdActions.appendChild(deleteBtn);
                
                tr.appendChild(tdName);
                tr.appendChild(tdApt);
                tr.appendChild(tdIn);
                tr.appendChild(tdOut);
                tr.appendChild(tdContract);
                tr.appendChild(tdActions);
                
                tbody.appendChild(tr);
            });
            
            table.appendChild(tbody);
            box.appendChild(table);
            container.appendChild(box);
        });
        
    } catch (error) {
        console.error(error);
    }
}

async function saveTenant() {
    const name = document.getElementById('tenant-name').value.trim();
    const aptId = document.getElementById('tenant-apartment').value;
    const moveIn = document.getElementById('tenant-move-in').value;
    const moveOut = document.getElementById('tenant-move-out').value;
    const lastBilled = document.getElementById('tenant-last-billed').value;
    
    if (!name || !aptId || !moveIn) {
        showError('Name, Wohnung und Einzugsdatum sind erforderlich.');
        return;
    }
    
    try {
        const method = editingTenantId ? 'PUT' : 'POST';
        const url = editingTenantId ? `/api/tenants/${editingTenantId}` : '/api/tenants';
        
        const formData = new FormData();
        formData.append('name', name);
        formData.append('apartment_id', parseInt(aptId));
        formData.append('move_in_date', moveIn);
        if (moveOut) formData.append('move_out_date', moveOut);
        if (lastBilled) formData.append('last_billed_until', lastBilled);
        
        const fileInput = document.getElementById('tenant-contract-file');
        if (fileInput.files.length > 0) {
            formData.append('contract_file', fileInput.files[0]);
        }
        
        const response = await fetch(url, {
            method: method,
            body: formData
        });
        
        if (!response.ok) throw await serverFehler(response);
        
        closeAddTenantModal();
        fetchTenants();
    } catch (error) {
        showError(meldungZu(error, 'Fehler beim Speichern des Mieters.'));
    }
}

async function deleteTenant(id) {
    if (!await frageLoeschen(
        'Möchten Sie dieses Mietverhältnis wirklich löschen?\n\n' +
        'Sofort gelöscht werden Mietvertrag und Kostenprofile. Festgesetzte ' +
        'Abrechnungen und Zahlungen unterliegen der Aufbewahrungspflicht ' +
        '(§ 147 AO, § 257 HGB, bis zu 10 Jahre): Sie bleiben gesperrt und ' +
        'unsichtbar gespeichert und werden nach Fristablauf automatisch gelöscht. ' +
        'Lassen Sie im Zweifel fachlich prüfen, welche Frist für Sie gilt.\n\n' +
        'Zähler und Lesungen bleiben für die Nachmieter erhalten.')) return;
    try {
        const response = await fetch(`/api/tenants/${id}`, { method: 'DELETE' });
        if (!response.ok) throw await serverFehler(response);
        const bericht = await response.json();
        const dateien = bericht.geloeschte_dateien || [];
        const fehlend = bericht.fehlende_dateien || [];
        if (bericht.gesperrt_bis) {
            showSuccess(bericht.message);
        } else if (fehlend.length) {
            showError(`Mieter gelöscht. ${fehlend.length} Datei(en) waren im Belegordner nicht mehr vorhanden.`);
        } else if (dateien.length) {
            showSuccess(`Mieter gelöscht, ${dateien.length} Datei(en) mitgelöscht.`);
        } else {
            showSuccess('Mieter gelöscht.');
        }
        fetchTenants();
        ladeGesperrteMieter();
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Löschen des Mieters.'));
    }
}

// NK-156 (K8): Einstellungen in Gruppen. Eine eigene Klasse statt
// ``hidden``, damit die Gruppe nie eine Karte zeigt, die aus anderem Grund
// verborgen ist (Gefahrenzone nur im Entwicklungsstapel).
const EINSTELLUNGS_GRUPPEN = ['vermieter', 'sicherung', 'konto', 'updates', 'datenschutz'];

function zeigeEinstellungsgruppe(gruppe) {
    if (!EINSTELLUNGS_GRUPPEN.includes(gruppe)) gruppe = 'vermieter';
    document.querySelectorAll('#tab-settings .dashboard-card[data-gruppe]').forEach(karte => {
        karte.classList.toggle('gruppe-aus', karte.dataset.gruppe !== gruppe);
    });
    document.querySelectorAll('.einstellungs-gruppen [data-gruppe]').forEach(knopf => {
        const aktiv = knopf.dataset.gruppe === gruppe;
        knopf.classList.toggle('active', aktiv);
        knopf.setAttribute('aria-selected', aktiv ? 'true' : 'false');
    });
    try {
        sessionStorage.setItem('nk-einstellungsgruppe', gruppe);
    } catch (e) {
        // ohne Sitzungsspeicher (privater Modus) beginnt die Seite bei „Vermieter“
    }
}
window.zeigeEinstellungsgruppe = zeigeEinstellungsgruppe;

function gemerkteEinstellungsgruppe() {
    try {
        return sessionStorage.getItem('nk-einstellungsgruppe') || 'vermieter';
    } catch (e) {
        return 'vermieter';
    }
}

// NK-174, NK-175: erst der Haftungshinweis (einmal je Fassung), danach die
// Suche beim Start. Die Suche ist still: kein Netz, kein Fenster.
async function startHinweise() {
    try {
        const res = await fetch('/api/haftung');
        if (res.ok) {
            const stand = await res.json();
            if (!stand.bestaetigt) await haftungZeigen(stand);
        }
    } catch (e) {
        console.error('Haftungshinweis nicht ladbar', e);
    }
    try {
        const res = await fetch('/api/aktualisierung/automatisch');
        if (!res.ok) return;
        const ergebnis = await res.json();
        if (ergebnis.neu) updateHinweisZeigen(ergebnis);
    } catch (e) {
        // still: die Suche beim Start meldet nie einen Fehler
    }
}

function haftungZeigen(stand) {
    const overlay = document.getElementById('haftung-modal');
    document.getElementById('haftung-titel').textContent = stand.titel;
    const text = document.getElementById('haftung-text');
    text.innerHTML = stand.text.map(satz => `<p>${escapeHtml(satz)}</p>`).join('');
    overlay.dataset.version = stand.version;
    overlay.classList.add('active');
    return new Promise(erledigt => {
        const wache = new MutationObserver(() => {
            if (overlay.classList.contains('active')) return;
            wache.disconnect();
            erledigt();
        });
        wache.observe(overlay, { attributes: true, attributeFilter: ['class'] });
    });
}

async function haftungBestaetigen() {
    const overlay = document.getElementById('haftung-modal');
    try {
        const res = await fetch('/api/haftung', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: Number(overlay.dataset.version) })
        });
        if (!res.ok) throw await serverFehler(res);
        overlay.classList.remove('active');
    } catch (e) {
        showError(meldungZu(e, 'Der Hinweis konnte nicht gespeichert werden.'));
    }
}
window.haftungBestaetigen = haftungBestaetigen;

function updateHinweisZeigen(ergebnis) {
    document.getElementById('update-titel').textContent = `Version ${ergebnis.version} ist da`;
    document.getElementById('update-text').textContent =
        ergebnis.text + (ergebnis.hinweise ? '\n\n' + ergebnis.hinweise : '');
    document.getElementById('update-notizen').href = ergebnis.notizen;
    document.getElementById('update-jetzt').style.display = ergebnis.installierbar ? '' : 'none';
    document.getElementById('update-modal').classList.add('active');
}

function updateSpaeter() {
    document.getElementById('update-modal').classList.remove('active');
}
window.updateSpaeter = updateSpaeter;

function updateJetzt() {
    updateSpaeter();
    updateInstallieren();
}
window.updateJetzt = updateJetzt;

async function ladeUpdateEinstellung() {
    const feld = document.getElementById('update-automatisch');
    if (!feld) return;
    try {
        const res = await fetch('/api/aktualisierung/einstellung');
        if (!res.ok) throw await serverFehler(res);
        const stand = await res.json();
        feld.checked = stand.automatisch;
        if (stand.paketmodus) {
            // Store-Paket: der Store aktualisiert, die App sucht nicht selbst.
            document.getElementById('update-automatisch-zeile').style.display = 'none';
            document.getElementById('update-erklaerung').textContent =
                'Diese Installation stammt aus dem Microsoft Store. Er installiert neue Versionen automatisch.';
        }
    } catch (e) {
        console.error('Update-Einstellung nicht ladbar', e);
    }
}
window.ladeUpdateEinstellung = ladeUpdateEinstellung;

async function updateAutomatischSetzen(feld) {
    try {
        const res = await fetch('/api/aktualisierung/einstellung', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ automatisch: feld.checked })
        });
        if (!res.ok) throw await serverFehler(res);
        feld.checked = (await res.json()).automatisch;
    } catch (e) {
        feld.checked = !feld.checked;
        showError(meldungZu(e, 'Die Einstellung konnte nicht gespeichert werden.'));
    }
}
window.updateAutomatischSetzen = updateAutomatischSetzen;

// NK-081, NK-175: auf Knopfdruck. Docker bekommt einen Hinweis auf das neue
// Abbild, die Windows-App einen Knopf, der den geprueften Installer startet.
async function nachUpdatesSuchen() {
    const stand = document.getElementById('update-stand');
    const knopf = document.getElementById('btn-update-installieren');
    stand.textContent = 'Suche nach Updates …';
    knopf.style.display = 'none';
    try {
        const res = await fetch('/api/aktualisierung');
        if (!res.ok) throw await serverFehler(res);
        const ergebnis = await res.json();
        stand.textContent = ergebnis.text + (ergebnis.neu && ergebnis.hinweise ? ' ' + ergebnis.hinweise : '');
        if (ergebnis.installierbar) knopf.style.display = '';
    } catch (e) {
        stand.textContent = meldungZu(e, 'Die Suche nach Updates ist fehlgeschlagen.');
    }
}
window.nachUpdatesSuchen = nachUpdatesSuchen;

async function updateInstallieren() {
    if (!await frage(
        'Das Update wird geladen und geprüft. Vorher sichert die Anwendung Ihre Daten. ' +
        'Dann schließt sie sich kurz und startet mit der neuen Version neu.',
        'Installieren'
    )) return;
    const stand = document.getElementById('update-stand');
    stand.textContent = 'Update wird geladen …';
    try {
        const res = await fetch('/api/aktualisierung/installieren', { method: 'POST' });
        if (!res.ok) throw await serverFehler(res);
        stand.textContent = (await res.json()).text;
    } catch (e) {
        stand.textContent = meldungZu(e, 'Das Update konnte nicht installiert werden.');
    }
}
window.updateInstallieren = updateInstallieren;

// NK-153: gesperrte Mietverhaeltnisse (geloescht, Aufbewahrung laeuft) --
// nur hier sichtbar, mit Auskunft nach Art. 15.
async function ladeGesperrteMieter() {
    const ziel = document.getElementById('gesperrte-mieter');
    if (!ziel) return;
    try {
        const res = await fetch('/api/tenants?gesperrte=1');
        if (!res.ok) throw await serverFehler(res);
        const liste = await res.json();
        if (!liste.length) {
            ziel.innerHTML = '<p style="color: var(--text-muted); margin: 0;">Keine gesperrten Mietverhältnisse.</p>';
            return;
        }
        ziel.innerHTML = '<table style="width: 100%; border-collapse: collapse; text-align: left;">' +
            '<thead><tr><th style="padding: 8px;">Mieter</th><th style="padding: 8px;">Wohnung</th>' +
            '<th style="padding: 8px;">Gesperrt bis</th><th style="padding: 8px;"></th></tr></thead><tbody>' +
            liste.map(t => `<tr>
                <td style="padding: 8px;">${escapeHtml(t.name)}</td>
                <td style="padding: 8px;">${escapeHtml(t.apartment_name)} (${escapeHtml(t.property_name)})</td>
                <td style="padding: 8px;">${escapeHtml(new Date(t.gesperrt_bis).toLocaleDateString('de-DE'))}</td>
                <td style="padding: 8px;"><button class="btn-secondary" onclick="exportiereMieter(${Number(t.id)})"
                    title="Auskunft nach Art. 15 DSGVO als ZIP">Auskunft herunterladen</button></td>
            </tr>`).join('') + '</tbody></table>';
    } catch (e) {
        console.error('Gesperrte Mietverhältnisse nicht ladbar', e);
    }
}
window.ladeGesperrteMieter = ladeGesperrteMieter;

async function exportiereMieter(id) {
    try {
        const response = await fetch(`/api/tenants/${id}/export`);
        if (!response.ok) throw await serverFehler(response);
        await huelle.blobSpeichern(await response.blob(), `mieter-export-${id}.zip`);
        showSuccess('Auskunft heruntergeladen.');
    } catch (e) {
        showError(meldungZu(e, 'Die Auskunft konnte nicht erstellt werden.'));
    }
}

// Modal Logic
function openAddPropertyModal(prop = null) {
    if (prop && prop.id) {
        editingPropertyId = prop.id;
        document.getElementById('prop-name').value = prop.name;
        document.getElementById('prop-standalone').checked = prop.is_standalone;
        propertyModal.querySelector('h2').textContent = 'Immobilie bearbeiten';
    } else {
        editingPropertyId = null;
        document.getElementById('prop-name').value = '';
        document.getElementById('prop-standalone').checked = false;
        propertyModal.querySelector('h2').textContent = 'Neue Immobilie';
    }
    propertyModal.classList.add('active');
}

function closeAddPropertyModal() { propertyModal.classList.remove('active'); }

function openAddApartmentModal(apt = null) {
    if (apt && apt.id) {
        editingApartmentId = apt.id;
        document.getElementById('apt-name').value = apt.name;
        document.getElementById('apt-sqm').value = apt.sqm;
        document.getElementById('apt-nutzungsart').value = apt.nutzungsart || 'wohnen';
        document.getElementById('apt-eigennutzung').checked = !!apt.eigennutzung;
        document.getElementById('apt-selbstversorger').checked = !!apt.selbstversorger;
        apartmentModal.querySelector('h2').textContent = 'Wohnung bearbeiten';
    } else {
        editingApartmentId = null;
        document.getElementById('apt-name').value = '';
        document.getElementById('apt-sqm').value = '';
        document.getElementById('apt-nutzungsart').value = 'wohnen';
        document.getElementById('apt-eigennutzung').checked = false;
        document.getElementById('apt-selbstversorger').checked = false;
        apartmentModal.querySelector('h2').textContent = 'Neue Wohnung';
    }
    apartmentModal.classList.add('active');
}

function closeAddApartmentModal() { apartmentModal.classList.remove('active'); }

function openAddTenantModal(tenant = null) {
    if (tenant && tenant.id) {
        editingTenantId = tenant.id;
        document.getElementById('tenant-name').value = tenant.name;
        
        // Ensure the dropdown shows the correct option
        setTimeout(() => {
            document.getElementById('tenant-apartment').value = tenant.apartment_id;
        }, 50);
        
        const moveInDate = new Date(tenant.move_in_date);
        document.getElementById('tenant-move-in').value = moveInDate.toISOString().split('T')[0];
        
        if (tenant.move_out_date) {
            const moveOutDate = new Date(tenant.move_out_date);
            document.getElementById('tenant-move-out').value = moveOutDate.toISOString().split('T')[0];
        } else {
            document.getElementById('tenant-move-out').value = '';
        }
        
        if (tenant.last_billed_until) {
            const lastBilledDate = new Date(tenant.last_billed_until);
            document.getElementById('tenant-last-billed').value = lastBilledDate.toISOString().split('T')[0];
        } else {
            document.getElementById('tenant-last-billed').value = '';
        }
        
        document.getElementById('tenant-contract-file').value = '';
        document.getElementById('tenant-contract-name').textContent = 'Datei auswählen...';
        const info = document.getElementById('tenant-contract-info');
        if (tenant.contract_path) {
            info.textContent = 'Es ist bereits ein Mietvertrag hinterlegt. Ein neuer Upload überschreibt diesen.';
            info.style.display = 'block';
        } else {
            info.style.display = 'none';
        }
        
        tenantModal.querySelector('h2').textContent = 'Mieter bearbeiten';
    } else {
        editingTenantId = null;
        document.getElementById('tenant-name').value = '';
        document.getElementById('tenant-move-in').value = '';
        document.getElementById('tenant-move-out').value = '';
        document.getElementById('tenant-last-billed').value = '';
        document.getElementById('tenant-apartment').value = '';
        document.getElementById('tenant-contract-file').value = '';
        document.getElementById('tenant-contract-name').textContent = 'Datei auswählen...';
        document.getElementById('tenant-contract-info').style.display = 'none';
        
        tenantModal.querySelector('h2').textContent = 'Neuer Mieter';
    }
    tenantModal.classList.add('active');
}

function closeAddTenantModal() { tenantModal.classList.remove('active'); }

// --- Fehlermeldungen vom Server (NK-030) ------------------------------------
//
// Der Server antwortet auf jeden Fehler mit einem deutschen Satz im Feld
// `error`: die Eingabepruefung sagt, welches Feld nicht stimmt (NK-028), das
// Groessenlimit nennt die erlaubte Groesse (NK-029), und ein unvorhergesehener
// Fehler nennt eine Vorgangsnummer, die im Protokoll wiederzufinden ist.
// Vorher warf diese Datei an rund dreissig Stellen `new Error('Failed ...')`
// und der catch-Block zeigte einen festen Satz -- der genaue Grund kam nie auf
// den Schirm, und die Vorgangsnummer war fuer den Nutzer nicht zu erfahren.

async function serverFehler(antwort) {
    // Der Rumpf ist nur einmal lesbar; an dieser Stelle ist er es noch, weil
    // der Aufrufer wegen !ok nichts daraus gelesen hat.
    try {
        const daten = await antwort.json();
        if (daten && daten.error) {
            const fehler = new Error(daten.error);
            fehler.vomServer = true;
            return fehler;
        }
    } catch (e) {
        // Kein JSON -- etwa die Notseite bei einem Fehler vor der Anwendung.
    }
    return new Error('HTTP ' + antwort.status);
}

function meldungZu(fehler, ersatz) {
    // Nur ein Satz, den der Server geschickt hat, ist fuer den Nutzer gemacht.
    // Ein abgerissenes Netz wirft einen englischen TypeError, und "Failed to
    // fetch" hilft niemandem weiter -- dafuer steht der Ersatztext da.
    return fehler && fehler.vomServer ? fehler.message : ersatz;
}

/* Meldungen (NK-067): beide Arten laufen über zeigeMeldung() in den Stapel
   unten rechts. Sechs Sekunden statt drei -- drei waren zu kurz zum Lesen. */
function zeigeMeldung(message, art) {
    let stapel = document.getElementById('toast-stapel');
    if (!stapel) {
        stapel = document.createElement('div');
        stapel.id = 'toast-stapel';
        stapel.className = 'toast-stapel';
        document.body.appendChild(stapel);
    }
    const meldung = document.createElement('div');
    meldung.className = 'toast toast-' + art;
    meldung.setAttribute('role', 'alert');
    meldung.textContent = message;
    stapel.appendChild(meldung);
    setTimeout(() => meldung.remove(), 6000);
}

function showError(message) {
    zeigeMeldung(message, 'fehler');
}

function showSuccess(message) {
    zeigeMeldung(message, 'erfolg');
}

// --- Phase 4 Fetch Functions ---
async function fetchCategories() {
    try {
        const res = await fetch('/api/categories');
        categories = await res.json();
    } catch(e) { console.error(e); }
}

async function fetchMeters() {
    try {
        const res = await fetch('/api/meters');
        meters = await res.json();
        renderMeters();
        zeigeErsteSchritte();
    } catch(e) { console.error(e); }
}

async function fetchReadings() {
    try {
        const res = await fetch('/api/readings');
        readings = await res.json();
        renderMeters(); // readings are shown inside meters
        zeigeErsteSchritte();
    } catch(e) { console.error(e); }
}

async function fetchInvoices() {
    try {
        const res = await fetch('/api/invoices');
        invoices = await res.json();
        renderInvoices();
        zeigeErsteSchritte();
    } catch(e) { console.error(e); }
}

// ---- Zeitleiste der Rechnungen (NK-144) -------------------------------
// Chronologisch nach Ausstellungsdatum (rechnungsdatum), nicht nach
// Erfassung oder Zeitraum. Altbestand ohne Datum zeigt eine eigene
// Gruppe am Ende -- aus einem NULL wird nichts geraten (D-57).

function zeigeInvoiceListe() {
    pilleInvoiceAnsicht('pills-invoice-liste');
    document.getElementById('invoices-container').style.display = 'flex';
    document.getElementById('invoice-filter').style.display = 'flex';
    document.getElementById('invoices-zeitleiste').style.display = 'none';
}

async function zeigeInvoiceZeitleiste() {
    pilleInvoiceAnsicht('pills-invoice-zeitleiste');
    document.getElementById('invoices-container').style.display = 'none';
    document.getElementById('invoice-filter').style.display = 'none';
    const ziel = document.getElementById('invoices-zeitleiste');
    ziel.style.display = 'block';
    try {
        const res = await fetch('/api/invoices/zeitleiste');
        if (!res.ok) throw await serverFehler(res);
        renderInvoiceZeitleiste(await res.json(), ziel);
    } catch (fehler) {
        console.error(fehler);
        zeigeMeldung(meldungZu(fehler,
            'Die Zeitleiste konnte nicht geladen werden.'), 'fehler');
    }
}

function pilleInvoiceAnsicht(aktiveId) {
    for (const id of ['pills-invoice-liste', 'pills-invoice-zeitleiste']) {
        const pille = document.getElementById(id);
        if (pille) pille.classList.toggle('active', id === aktiveId);
    }
}

function zeitleisteDatum(iso) {
    // Ohne Date-Objekt: '2025-04-10' direkt als '10.04.2025' ausgeben,
    // damit die Zeitzonen-Rechnung nichts verschiebt.
    const teile = (iso || '').split('-');
    return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : '';
}

function zeitleisteBetrag(zahl) {
    return Number(zahl).toLocaleString('de-DE',
        { style: 'currency', currency: 'EUR' });
}

function zeitleisteEintragZeile(e) {
    const wer = [e.provider_name, e.kategorie_name]
        .filter(Boolean).join(' · ');
    const beleg = e.hat_beleg
        ? '<i class="ph ph-file-pdf" title="Beleg vorhanden"></i>'
        : `<i class="ph ph-file-x" title="Kein Beleg erfasst"></i>`;
    return '<div class="zeitleiste-eintrag">' +
        `<span class="zeitleiste-datum">${escapeHtml(zeitleisteDatum(e.rechnungsdatum))}</span>` +
        `<span class="zeitleiste-wer">${escapeHtml(wer || 'Ohne Anbieter')}` +
            (e.invoice_number
                ? ` <span class="zeitleiste-nr">Nr. ${escapeHtml(e.invoice_number)}</span>` : '') +
        '</span>' +
        `<span class="zeitleiste-ort">${escapeHtml(e.property_name || '')}</span>` +
        `<span class="zeitleiste-beleg">${beleg}</span>` +
        `<span class="zeitleiste-betrag">${zeitleisteBetrag(e.amount)}</span>` +
        '</div>';
}

function zeitleisteKarte(titel, summe, rechnungen) {
    return '<div class="dashboard-card zeitleiste-gruppe">' +
        '<div class="zeitleiste-kopf">' +
        `<h3>${escapeHtml(titel)}</h3>` +
        `<span class="zeitleiste-summe">${zeitleisteBetrag(summe)}</span>` +
        '</div>' +
        rechnungen.map(zeitleisteEintragZeile).join('') +
        '</div>';
}

function renderInvoiceZeitleiste(daten, ziel) {
    const teile = [];
    for (const jahr of daten.jahre || []) {
        teile.push(`<h2 class="zeitleiste-jahr">${jahr.jahr}</h2>`);
        for (const monat of jahr.monate || []) {
            teile.push(zeitleisteKarte(
                `${monat.label} ${jahr.jahr}`, monat.summe, monat.rechnungen));
        }
    }
    if (daten.ohne_datum) {
        teile.push('<h2 class="zeitleiste-jahr">Ohne Rechnungsdatum</h2>');
        teile.push(zeitleisteKarte('Altbestand ohne Datum',
            daten.ohne_datum.summe, daten.ohne_datum.rechnungen));
    }
    if (teile.length === 0) {
        ziel.innerHTML = leerzustand({
            icon: 'ph-receipt',
            titel: 'Noch keine Rechnungen erfasst',
            text: 'Sobald Sie Rechnungen erfassen, erscheinen sie hier '
                + 'chronologisch nach Ausstellungsdatum.',
            aktion: { label: 'Rechnung erfassen', fn: 'openAddInvoiceModal()', icon: 'ph-plus' },
        });
        return;
    }
    teile.push('<p class="zeitleiste-gesamt">Zusammen ' +
        `${zeitleisteBetrag(daten.gesamt)}</p>`);
    ziel.innerHTML = teile.join('');
}

function getReadingHtml(r, categoryName) {
    let unit = '';
    if (categoryName) {
        const lower = categoryName.toLowerCase();
        if (lower.includes('strom')) unit = ' kWh';
        else if (lower.includes('gas') || lower.includes('wasser')) unit = ' m³';
    }

    const fmt = new Intl.NumberFormat('de-DE');
    const formatVal = (val) => val !== null && val !== undefined ? fmt.format(val) : '';

    let valStr = `<strong>${formatVal(r.value)}${escapeHtml(unit)}</strong>`;
    if (r.value_nt !== null && r.value_nt !== undefined) {
        valStr = `<strong><span style="color: var(--text-muted); font-size: 0.85em; font-weight: normal;">HT:</span> ${formatVal(r.value)}${escapeHtml(unit)} <span style="color: var(--text-muted); font-size: 0.85em; font-weight: normal; margin-left: 8px;">NT:</span> ${formatVal(r.value_nt)}${escapeHtml(unit)}</strong>`;
    }
    
    let html = `${valStr} <br><small style="color:var(--text-muted)">${new Date(r.reading_date).toLocaleDateString('de-DE')}</small>`;
    
    if (r.document_path) {
        const imgUrl = dateiAdresse('ablesung', r.id);
        html += ` <div class="image-hover-container" onclick="event.stopPropagation(); huelle.oeffnen('${imgUrl}');" title="Klicken, um Foto im neuen Tab zu öffnen">
                    <i class="ph ph-image" style="color: var(--primary);"></i>
                    <img src="${imgUrl}" class="image-hover-preview">
                  </div>`;
    }
    
    if (r.is_official_invoice) {
        if (r.plausibility_status === 'success') {
            html += ` <i class="ph ph-check-circle" style="color: var(--success-color); margin-left: 4px; font-size: 1.1em; vertical-align: middle;" title="${escapeHtml(r.plausibility_message)}"></i>`;
        } else if (r.plausibility_status === 'warning') {
            html += ` <i class="ph ph-warning-circle" style="color: var(--danger-color); margin-left: 4px; font-size: 1.1em; vertical-align: middle;" title="${escapeHtml(r.plausibility_message)}"></i>`;
        }
    }
    
    return html;
}

// --- Render Meters ---
function renderMeters() {
    const container = document.getElementById('meters-container');
    if (!container) return;
    container.replaceChildren();
    
    if (meters.length === 0) {
        container.innerHTML = leerzustand({
            icon: 'ph-gauge',
            titel: 'Noch keine Zähler angelegt',
            text: 'Zähler brauchen Sie für Kosten, die nach Verbrauch umgelegt werden — zum Beispiel Strom oder Wasser.',
            aktion: { label: 'Zähler anlegen', fn: 'openAddMeterModal()', icon: 'ph-plus' },
        });
        return;
    }
    
    const grouped = {};
    meters.forEach(m => {
        if (!grouped[m.property_name]) grouped[m.property_name] = [];
        grouped[m.property_name].push(m);
    });
    
    Object.keys(grouped).forEach(propName => {
        const box = document.createElement('div');
        box.className = 'glass-panel';
        box.style.padding = '24px';
        
        const title = document.createElement('h3');
        title.textContent = propName;
        title.style.marginBottom = '16px';
        title.style.borderBottom = '2px solid rgba(79, 70, 229, 0.2)';
        title.style.paddingBottom = '8px';
        box.appendChild(title);
        
        const table = document.createElement('table');
        table.style.width = '100%';
        table.style.borderCollapse = 'collapse';
        table.style.textAlign = 'left';
        table.innerHTML = `
            <tr style="border-bottom: 1px solid var(--border-color);">
                <th style="padding: 12px 8px;">Kategorie</th>
                <th style="padding: 12px 8px;">Zählernummer</th>
                <th style="padding: 12px 8px;">Wohnung</th>
                <th style="padding: 12px 8px;">Letzter Stand</th>
                <th style="padding: 12px 8px;">Aktionen</th>
            </tr>
        `;
        
        grouped[propName].sort((a, b) => {
            if (a.is_official === b.is_official) return 0;
            return a.is_official ? -1 : 1;
        }).forEach(m => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = "1px solid var(--border-color)";
            tr.style.cursor = "pointer";
            tr.onclick = () => openHistoryModal(m.id);
            
            const tdCat = document.createElement('td');
            tdCat.style.padding = "12px 8px";
            tdCat.textContent = m.category_name;
            
            const tdNum = document.createElement('td');
            tdNum.style.padding = "12px 8px";
            tdNum.innerHTML = m.meter_number + (
                m.is_official 
                ? ' <span style="font-size: 13px; padding: 2px 6px; background: var(--primary); color: white; border-radius: 4px; margin-left: 8px;" title="Offizieller Zähler des Versorgers"><i class="ph ph-check-circle"></i> Versorger</span>' 
                : ' <span style="font-size: 13px; padding: 2px 6px; background: var(--border-color); color: var(--text-color); border-radius: 4px; margin-left: 8px;" title="Privater Zwischenzähler">Privat</span>'
            );
            
            const tdApt = document.createElement('td');
            tdApt.style.padding = "12px 8px";
            tdApt.textContent = m.is_main_meter ? "Allgemein" : (m.apartment_name || "-");
            
            // Find latest reading
            const meterReadings = readings.filter(r => r.meter_id === m.id).sort((a,b) => new Date(b.reading_date) - new Date(a.reading_date));
            const tdRead = document.createElement('td');
            tdRead.style.padding = "12px 8px";
            tdRead.className = "tabular-nums";
            if (meterReadings.length > 0) {
                const latest = meterReadings[0];
                tdRead.innerHTML = getReadingHtml(latest, m.category_name);
            } else {
                tdRead.textContent = "-";
            }
            
            const tdActions = document.createElement('td');
            tdActions.style.padding = "12px 8px";
            tdActions.onclick = (e) => e.stopPropagation();
            
            if (meterReadings.length > 0) {
                const latest = meterReadings[0];
                const editReadBtn = document.createElement('button');
                editReadBtn.className = 'btn-icon';
                editReadBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
                editReadBtn.title = "Letzten Zählerstand bearbeiten";
                editReadBtn.style.marginRight = "8px";
                editReadBtn.onclick = () => openAddReadingModal(null, latest.id);
                tdActions.appendChild(editReadBtn);
            }
            
            const delBtn = document.createElement('button');
            delBtn.className = 'btn-icon';
            delBtn.innerHTML = '<i class="ph ph-trash"></i>';
            delBtn.onclick = () => deleteMeter(m.id);
            tdActions.appendChild(delBtn);
            
            tr.appendChild(tdCat);
            tr.appendChild(tdNum);
            tr.appendChild(tdApt);
            tr.appendChild(tdRead);
            tr.appendChild(tdActions);
            table.appendChild(tr);
        });
        
        box.appendChild(table);
        container.appendChild(box);
    });
}

// --- Accordion Logic & Invoices ---
function toggleAccordion(accId) {
    const acc = document.getElementById(accId);
    if (acc) {
        acc.classList.toggle('open');
    }
}

function getCategoryIcon(catName) {
    const lower = catName.toLowerCase();
    if (lower.includes('strom')) return 'ph-lightning';
    if (lower.includes('wasser')) return 'ph-drop';
    if (lower.includes('steuer') || lower.includes('gebäude') || lower.includes('versicherung')) return 'ph-buildings';
    if (lower.includes('müll')) return 'ph-trash';
    if (lower.includes('hausmeister')) return 'ph-wrench';
    return 'ph-receipt';
}

// NK-156 (K4): der Leerzustand „Keine Treffer“ führt zurück zur ganzen Liste.
function rechnungsfilterZuruecksetzen() {
    const suche = document.getElementById('invoice-search');
    const kategorie = document.getElementById('invoice-category-filter');
    if (suche) suche.value = '';
    if (kategorie) kategorie.value = '';
    renderInvoices();
}
window.rechnungsfilterZuruecksetzen = rechnungsfilterZuruecksetzen;

function renderInvoices() {
    const container = document.getElementById('invoices-container');
    if (!container) return;
    container.replaceChildren();
    
    // Populate Category Dropdown if needed
    const catSelect = document.getElementById('invoice-category-filter');
    if (catSelect && catSelect.options.length <= 1) {
        const uniqueCats = [...new Set(invoices.map(i => i.category_name))].sort();
        uniqueCats.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            catSelect.appendChild(opt);
        });
    }
    
    // Read filters
    const searchInput = document.getElementById('invoice-search');
    const searchVal = searchInput ? searchInput.value.toLowerCase() : '';
    const catFilterVal = catSelect ? catSelect.value : '';
    
    // Filter invoices
    let filtered = invoices.filter(i => {
        let matchSearch = true;
        if (searchVal) {
            const num = (i.invoice_number || '').toLowerCase();
            const prov = (i.provider_name || '').toLowerCase();
            matchSearch = num.includes(searchVal) || prov.includes(searchVal);
        }
        let matchCat = true;
        if (catFilterVal) {
            matchCat = i.category_name === catFilterVal;
        }
        return matchSearch && matchCat;
    });
    
    if (filtered.length === 0) {
        // K4: zu leerem Bestand gehört keine Filterleiste; bei „Keine
        // Treffer" bleibt sie stehen.
        const leiste = document.getElementById('invoice-filter');
        if (leiste) leiste.hidden = invoices.length === 0;
        if (invoices.length === 0) {
            container.innerHTML = leerzustand({
                icon: 'ph-receipt',
                titel: 'Noch keine Rechnungen erfasst',
                text: 'Erfassen Sie die Kosten des Jahres — jede Rechnung des Anbieters ist ein eigener Eintrag.',
                aktion: { label: 'Rechnung erfassen', fn: 'openAddInvoiceModal()', icon: 'ph-plus' },
            });
        } else {
            container.innerHTML = leerzustand({
                icon: 'ph-magnifying-glass',
                titel: 'Keine Rechnungen gefunden',
                text: 'Für diese Suche oder diesen Filter gibt es keine Treffer.',
                aktion: { label: 'Filter zurücksetzen', fn: 'rechnungsfilterZuruecksetzen()', icon: 'ph-x-circle' },
            });
        }
        return;
    }
    const leiste = document.getElementById('invoice-filter');
    if (leiste) leiste.hidden = false;

    // Group by property
    const groupedByProp = {};
    filtered.forEach(i => {
        if (!groupedByProp[i.property_name]) groupedByProp[i.property_name] = [];
        groupedByProp[i.property_name].push(i);
    });
    
    Object.keys(groupedByProp).forEach(propName => {
        const box = document.createElement('div');
        box.className = 'glass-panel';
        box.style.padding = '24px';
        
        const title = document.createElement('h3');
        title.textContent = propName;
        title.style.marginBottom = '16px';
        title.style.borderBottom = '2px solid rgba(79, 70, 229, 0.2)';
        title.style.paddingBottom = '8px';
        box.appendChild(title);
        
        // Group by category within property
        const catGrouped = {};
        groupedByProp[propName].forEach(i => {
            if (!catGrouped[i.category_name]) catGrouped[i.category_name] = [];
            catGrouped[i.category_name].push(i);
        });
        
        // Render Accordions
        Object.keys(catGrouped).sort().forEach(catName => {
            const catInvoices = catGrouped[catName];
            const accId = `acc-${propName.replace(/\W/g, '')}-${catName.replace(/\W/g, '')}`;
            const icon = getCategoryIcon(catName);
            
            const accDiv = document.createElement('div');
            accDiv.className = 'accordion';
            accDiv.id = accId;
            
            // Header
            accDiv.innerHTML = `
                <div class="accordion-header" onclick="toggleAccordion('${accId}')">
                    <div class="accordion-header-left">
                        <i class="ph ${icon} accordion-icon"></i>
                        <span>${escapeHtml(catName)}</span>
                        <span class="accordion-badge">${catInvoices.length} Einträge</span>
                    </div>
                    <i class="ph ph-caret-down accordion-chevron"></i>
                </div>
                <div class="accordion-content">
                    <table class="table-zebra" style="width: 100%; border-collapse: collapse; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-color); background: var(--bg-hover);">
                                <th style="padding: 12px 16px;">Von</th>
                                <th style="padding: 12px 16px;">Bis</th>
                                <th style="padding: 12px 16px;">Rechnungsnr.</th>
                                <th style="padding: 12px 16px;">Anbieter</th>
                                <th style="padding: 12px 16px;" class="text-right">Betrag</th>
                                <th style="padding: 12px 16px;">Beleg</th>
                                <th style="padding: 12px 16px;" class="text-right">Aktionen</th>
                            </tr>
                        </thead>
                        <tbody id="tbody-${accId}"></tbody>
                    </table>
                </div>
            `;
            box.appendChild(accDiv);
            
            const tbody = box.querySelector(`#tbody-${accId}`);
            
            catInvoices.forEach(inv => {
                const tr = document.createElement('tr');
                tr.style.borderBottom = "1px solid var(--border-color)";
                
                const dateOpts = { day: '2-digit', month: '2-digit', year: 'numeric' };
                
                const tdDateFrom = document.createElement('td');
                tdDateFrom.style.padding = "12px 16px";
                tdDateFrom.textContent = new Date(inv.start_date).toLocaleDateString('de-DE', dateOpts);
                
                const tdDateTo = document.createElement('td');
                tdDateTo.style.padding = "12px 16px";
                tdDateTo.textContent = new Date(inv.end_date).toLocaleDateString('de-DE', dateOpts);
                
                const tdNum = document.createElement('td');
                tdNum.style.padding = "12px 16px";
                tdNum.textContent = inv.invoice_number || '-';
                
                const tdProvider = document.createElement('td');
                tdProvider.style.padding = "12px 16px";
                tdProvider.textContent = inv.provider_name || '-';
                
                const tdAmt = document.createElement('td');
                tdAmt.style.padding = "12px 16px";
                tdAmt.className = "text-right";
                tdAmt.innerHTML = `<strong>${inv.amount.toFixed(2)} €</strong>`;
                
                const tdDoc = document.createElement('td');
                tdDoc.style.padding = "12px 16px";
                if (inv.document_path) {
                    let docUrl = dateiAdresse('rechnung', inv.id);
                    let docLabel = inv.filename ? inv.filename : 'Beleg';
                    if (inv.document_pages) {
                        docLabel += ` (S. ${inv.document_pages})`;
                        const pageMatch = inv.document_pages.match(/\d+/);
                        if (pageMatch) {
                            docUrl += `#page=${pageMatch[0]}`;
                        }
                    }
                    tdDoc.innerHTML = `<a href="${docUrl}" target="_blank" style="color: var(--primary-color); text-decoration: none;"><i class="ph ph-file-pdf" style="font-size: 1.2rem;"></i> ${escapeHtml(docLabel)}</a>`;
                } else {
                    tdDoc.textContent = "-";
                }
                
                tr.appendChild(tdDateFrom);
                tr.appendChild(tdDateTo);
                tr.appendChild(tdNum);
                tr.appendChild(tdProvider);
                tr.appendChild(tdAmt);
                tr.appendChild(tdDoc);
                
                const tdActions = document.createElement('td');
                tdActions.style.padding = "12px 16px";
                tdActions.className = "text-right";
                
                const editBtn = document.createElement('button');
                editBtn.className = 'btn-icon';
                editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
                editBtn.title = "Rechnung bearbeiten";
                editBtn.style.marginRight = "8px";
                editBtn.onclick = () => openAddInvoiceModal(inv.id);
                tdActions.appendChild(editBtn);
                
                const delBtn = document.createElement('button');
                delBtn.className = 'btn-icon';
                delBtn.innerHTML = '<i class="ph ph-trash"></i>';
                delBtn.title = "Rechnung löschen";
                delBtn.onclick = () => deleteInvoice(inv.id);
                tdActions.appendChild(delBtn);
                
                tr.appendChild(tdActions);
                tbody.appendChild(tr);
            });
        });
        
        container.appendChild(box);
    });
}

// --- Tenant Cost Profile Logic ---
async function openCostProfileModal(tenantId, tenantName) {
    document.getElementById('profile-tenant-name').textContent = tenantName;
    document.getElementById('profile-tenant-id').value = tenantId;
    
    let currentProfile = {};
    try {
        const res = await fetch(`/api/tenants/${tenantId}/profiles`);
        if (res.ok) currentProfile = await res.json();
    } catch(e) { console.error(e); }
    
    const container = document.getElementById('cost-profile-categories');
    container.innerHTML = '';
    
    categories.forEach(cat => {
        const val = currentProfile[cat.id] || 'qm';
        
        container.innerHTML += `
            <div class="form-group" style="background: var(--bg-hover); padding: 12px; border-radius: 8px;">
                <label style="margin-bottom: 8px;">${escapeHtml(cat.name)}
                    <i class="ph ph-question feld-hilfe" title="Wählen Sie, wie diese Kostenart auf die Wohnungen verteilt wird. Nach Verbrauch (eigener Zähler) weist die ganze Rechnung der Wohnung zu, deren Zähler sie betrifft."></i></label>
                <select id="profile-cat-${cat.id}" title="Wie wird diese Kostenart umgelegt?" style="width: 100%; padding: 8px; border-radius: 6px; border: 1px solid var(--border-color); background: rgba(255,255,255,0.8);">
                    <option value="qm" ${val === 'qm' ? 'selected' : ''}>Umlage nach Wohnfläche</option>
                    <option value="personen" ${val === 'personen' ? 'selected' : ''}>Umlage nach Personen</option>
                    <option value="direkt" ${val === 'direkt' ? 'selected' : ''}>Nach Verbrauch (eigener Zähler)</option>
                    <option value="nur_allgemein" ${val === 'nur_allgemein' ? 'selected' : ''}>Nur Anteil am Allgemeinverbrauch</option>
                    <option value="ignoriert" ${val === 'ignoriert' ? 'selected' : ''}>Wird diesem Mieter nicht berechnet</option>
                </select>
            </div>
        `;
    });
    
    document.getElementById('cost-profile-modal').classList.add('active');
}

function closeCostProfileModal() {
    document.getElementById('cost-profile-modal').classList.remove('active');
}

async function saveCostProfile() {
    const tenantId = document.getElementById('profile-tenant-id').value;
    
    const data = {};
    categories.forEach(cat => {
        const select = document.getElementById(`profile-cat-${cat.id}`);
        if (select) {
            data[cat.id] = select.value;
        }
    });
    
    try {
        const res = await fetch(`/api/tenants/${tenantId}/profiles`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw await serverFehler(res);
        closeCostProfileModal();
        // Optional: show a quick success toast if you had one.
    } catch(e) {
        showError(meldungZu(e, 'Fehler beim Speichern des Profils.'));
    }
}

// --- Haushaltsgröße (NK-118) ---
// Personenzahl je Stichtag über die Routen aus NK-055 (D-35, D-39). Ein
// Eintrag mit vorhandenem Stichtag berichtigt diesen (die Route antwortet
// 200 statt 201); ein Stichtag vor dem Einzug weist die Route ab.
async function openHouseholdModal(tenant) {
    document.getElementById('household-tenant-name').textContent = tenant.name;
    document.getElementById('household-tenant-id').value = tenant.id;
    document.getElementById('household-personen').value = 1;
    const eintraege = await loadHouseholdSizes(tenant.id);
    // Ohne Eintrag ist der Einzug der naheliegende erste Stichtag.
    document.getElementById('household-gueltig-ab').value =
        eintraege.length === 0 ? String(tenant.move_in_date || '').slice(0, 10) : '';
    document.getElementById('household-modal').classList.add('active');
}

function closeHouseholdModal() {
    document.getElementById('household-modal').classList.remove('active');
}

async function loadHouseholdSizes(tenantId) {
    const liste = document.getElementById('household-list');
    liste.replaceChildren();
    let eintraege = [];
    try {
        const res = await fetch(`/api/tenants/${tenantId}/haushaltsgroessen`);
        if (!res.ok) throw await serverFehler(res);
        eintraege = await res.json();
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Laden der Haushaltsgröße.'));
        return [];
    }
    if (eintraege.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 3;
        td.style.padding = '8px';
        td.style.color = 'var(--text-muted)';
        td.textContent = 'Noch keine Angabe — ohne Eintrag zählt der Haushalt als eine Person.';
        tr.appendChild(td);
        liste.appendChild(tr);
        return eintraege;
    }
    eintraege.forEach(h => {
        const tr = document.createElement('tr');
        const tdDatum = document.createElement('td');
        tdDatum.style.padding = '8px';
        tdDatum.textContent = new Date(h.gueltig_ab).toLocaleDateString('de-DE');
        const tdAnzahl = document.createElement('td');
        tdAnzahl.style.padding = '8px';
        tdAnzahl.style.textAlign = 'right';
        tdAnzahl.textContent = h.personenanzahl;
        const tdAktion = document.createElement('td');
        const delBtn = document.createElement('button');
        delBtn.className = 'btn-icon';
        delBtn.innerHTML = '<i class="ph ph-trash"></i>';
        delBtn.title = 'Stichtag löschen';
        delBtn.onclick = () => deleteHouseholdSize(h.id, tenantId);
        tdAktion.appendChild(delBtn);
        tr.appendChild(tdDatum);
        tr.appendChild(tdAnzahl);
        tr.appendChild(tdAktion);
        liste.appendChild(tr);
    });
    return eintraege;
}

async function saveHouseholdSize() {
    const tenantId = document.getElementById('household-tenant-id').value;
    const gueltigAb = document.getElementById('household-gueltig-ab').value;
    const personen = parseInt(document.getElementById('household-personen').value, 10);
    if (!gueltigAb) {
        showError('Bitte geben Sie den Stichtag an, ab dem die Personenzahl gilt.');
        return;
    }
    if (!Number.isInteger(personen) || personen < 1) {
        showError('Im Haushalt lebt mindestens eine Person.');
        return;
    }
    try {
        const res = await fetch(`/api/tenants/${tenantId}/haushaltsgroessen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gueltig_ab: gueltigAb, personenanzahl: personen })
        });
        if (!res.ok) throw await serverFehler(res);
        document.getElementById('household-gueltig-ab').value = '';
        document.getElementById('household-personen').value = 1;
        await loadHouseholdSizes(tenantId);
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Speichern der Haushaltsgröße.'));
    }
}

async function deleteHouseholdSize(id, tenantId) {
    if (!await frageLoeschen('Möchten Sie diesen Stichtag wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/haushaltsgroessen/${id}`, { method: 'DELETE' });
        if (!res.ok) throw await serverFehler(res);
        await loadHouseholdSizes(tenantId);
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Löschen des Stichtags.'));
    }
}

// --- Meter Modal ---
function openAddMeterModal() {
    const catSelect = document.getElementById('meter-category');
    catSelect.replaceChildren();
    // NK-105 (D-63): ein Zaehler ist fuer JEDE Kostenart moeglich. Das alte
    // Pflichtkennzeichen aus dem Katalog wurde hier als Erlaubnis gelesen —
    // davon gab es nur fuer Wasserversorgung eines, und nur das war waehlbar.
    // Reihenfolge nach BetrKV-Nummer; Verbrauchsarten (METER_READING) und
    // Allgemeinstrom (Nr. 11, der uebliche Allgemeinstromzaehler) vorn in
    // ihrer eigenen Gruppe, alles Weitere darunter.
    const sortiert = [...categories].sort((a, b) => (a.betrkv_nr ?? 999) - (b.betrkv_nr ?? 999));
    const ueblich = [];
    const weitere = [];
    for (const c of sortiert) {
        (c.allocation_method === 'METER_READING' || c.betrkv_nr === 11 ? ueblich : weitere).push(c);
    }
    if (ueblich.length) {
        const gruppe = document.createElement('optgroup');
        gruppe.label = 'Üblich mit Zähler';
        gruppe.innerHTML = ueblich.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
        catSelect.appendChild(gruppe);
    }
    if (weitere.length) {
        const gruppe = document.createElement('optgroup');
        gruppe.label = 'Weitere Kostenarten';
        gruppe.innerHTML = weitere.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
        catSelect.appendChild(gruppe);
    }
    
    const propSelect = document.getElementById('meter-property');
    propSelect.replaceChildren();
    propSelect.insertAdjacentHTML('beforeend', `<option value="">Bitte wählen...</option>`);
    properties.forEach(p => {
        propSelect.insertAdjacentHTML('beforeend', `<option value="${p.id}">${escapeHtml(p.name)}</option>`);
    });
    
    document.getElementById('meter-apartment').replaceChildren();
    document.getElementById('meter-apartment').insertAdjacentHTML('beforeend', `<option value="">Allgemein (Hausanschluss)</option>`);
    document.getElementById('meter-number').value = '';
    document.getElementById('meter-dual-tariff').checked = false;
    document.getElementById('meter-is-official').checked = false;
    // NK-125: noch keine Immobilie gewaehlt, also keine Anlage im Auswahlfeld.
    const anlageSelect = document.getElementById('meter-heizungsanlage');
    anlageSelect.replaceChildren();
    anlageSelect.insertAdjacentHTML('beforeend', `<option value="">— keine (misst keine Wärme) —</option>`);
    document.getElementById('meter-modal').classList.add('active');
}

function updateMeterApartments() {
    const propId = document.getElementById('meter-property').value;
    const aptSelect = document.getElementById('meter-apartment');
    aptSelect.replaceChildren();
    aptSelect.insertAdjacentHTML('beforeend', `<option value="">Allgemein (Hausanschluss)</option>`);
    
    if (propId) {
        const apts = allApartments.filter(a => a.property_name === properties.find(p => p.id == propId)?.name);
        apts.forEach(a => {
            aptSelect.insertAdjacentHTML('beforeend', `<option value="${a.id}">${escapeHtml(a.name)}</option>`);
        });
    }

    // NK-125: welche Anlage dieser Immobilie der Zaehler misst (D-45).
    const anlageSelect = document.getElementById('meter-heizungsanlage');
    anlageSelect.replaceChildren();
    anlageSelect.insertAdjacentHTML('beforeend', `<option value="">— keine (misst keine Wärme) —</option>`);
    if (propId) {
        fetchHeizungsanlagen(propId).then(anlagen => {
            anlagen.forEach(a => {
                anlageSelect.insertAdjacentHTML('beforeend', `<option value="${a.id}">${escapeHtml(a.name)}</option>`);
            });
        }).catch(e => console.error('Heizungsanlagen konnten nicht geladen werden', e));
    }
}

function closeAddMeterModal() { document.getElementById('meter-modal').classList.remove('active'); }

async function saveMeter() {
    const catId = document.getElementById('meter-category').value;
    const propId = document.getElementById('meter-property').value;
    const aptId = document.getElementById('meter-apartment').value;
    const num = document.getElementById('meter-number').value.trim();
    
    if (!catId || !propId || !num) {
        showError('Bitte füllen Sie alle Pflichtfelder aus.');
        return;
    }
    
    try {
        const anlageId = document.getElementById('meter-heizungsanlage').value;
        const res = await fetch('/api/meters', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                category_id: parseInt(catId),
                property_id: parseInt(propId),
                apartment_id: aptId ? parseInt(aptId) : null,
                is_main_meter: aptId === "",
                meter_number: num,
                has_dual_tariff: document.getElementById('meter-dual-tariff').checked,
                is_official: document.getElementById('meter-is-official').checked,
                // NK-125: welche Anlage dieser Immobilie der Zaehler misst.
                heizungsanlage_id: anlageId ? parseInt(anlageId) : null
            })
        });
        if (!res.ok) throw await serverFehler(res);
        closeAddMeterModal();
        fetchMeters();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Speichern.')); }
}

async function deleteMeter(id) {
    if(!await frageLoeschen('Zähler wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/meters/${id}`, {method:'DELETE'});
        if(!res.ok) throw await serverFehler(res);
        fetchMeters();
        fetchReadings();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Löschen')); }
}

// --- History Modal ---
function openHistoryModal(meterId) {
    const meter = meters.find(m => m.id === meterId);
    if(!meter) return;
    
    document.getElementById('history-modal-title').textContent = `Historie: ${meter.meter_number} (${meter.category_name})`;
    
    const table = document.getElementById('history-table');
    table.replaceChildren();
    table.innerHTML = `
        <tr style="border-bottom: 1px solid var(--border-color);">
            <th style="padding: 12px 8px;">Datum & Stand</th>
            <th style="padding: 12px 8px;">Aktionen</th>
        </tr>
    `;
    
    const meterReadings = readings.filter(r => r.meter_id === meterId).sort((a,b) => new Date(b.reading_date) - new Date(a.reading_date));
    
    meterReadings.forEach(r => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid var(--border-color)";
        
        const tdRead = document.createElement('td');
        tdRead.style.padding = "12px 8px";
        tdRead.className = "tabular-nums";
        tdRead.innerHTML = getReadingHtml(r, meter.category_name);
        
        const tdActions = document.createElement('td');
        tdActions.style.padding = "12px 8px";
        
        const editBtn = document.createElement('button');
        editBtn.className = 'btn-icon';
        editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i>';
        editBtn.style.marginRight = "8px";
        editBtn.onclick = () => {
            closeHistoryModal();
            openAddReadingModal(null, r.id);
        };
        
        const delBtn = document.createElement('button');
        delBtn.className = 'btn-icon';
        delBtn.innerHTML = '<i class="ph ph-trash"></i>';
        delBtn.onclick = () => deleteReading(r.id);
        
        tdActions.appendChild(editBtn);
        tdActions.appendChild(delBtn);
        
        tr.appendChild(tdRead);
        tr.appendChild(tdActions);
        table.appendChild(tr);
    });
    
    if (meterReadings.length === 0) {
        table.innerHTML += `<tr><td colspan="2" style="padding: 12px 8px;">Keine Zählerstände vorhanden.</td></tr>`;
    }
    
    document.getElementById('history-modal').classList.add('active');
}

function closeHistoryModal() {
    document.getElementById('history-modal').classList.remove('active');
}

async function deleteReading(id) {
    if(!await frageLoeschen('Zählerstand wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/readings/${id}`, {method:'DELETE'});
        if(!res.ok) throw await serverFehler(res);
        fetchReadings();
        fetchMeters(); 
        closeHistoryModal();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Löschen')); }
}

function handleReadingMeterChange() {
    const meterId = document.getElementById('reading-meter').value;
    const meter = meters.find(m => m.id == meterId);
    if (meter && meter.has_dual_tariff) {
        document.getElementById('label-reading-value').textContent = 'Zählerstand (HT)';
        document.getElementById('group-reading-value-nt').style.display = 'block';
    } else {
        document.getElementById('label-reading-value').textContent = 'Zählerstand';
        document.getElementById('group-reading-value-nt').style.display = 'none';
        document.getElementById('reading-value-nt').value = '';
    }
}

// --- Reading Modals & Save ---
function openAddReadingModal(meterId = null, editReadingId = null) {
    const meterSelect = document.getElementById('reading-meter');
    meterSelect.replaceChildren();
    meters.forEach(m => {
        const label = `${m.property_name} - ${m.is_main_meter ? 'Allgemein' : m.apartment_name} - ${m.category_name} (${m.meter_number})`;
        meterSelect.insertAdjacentHTML('beforeend', `<option value="${m.id}">${escapeHtml(label)}</option>`);
    });
    
    document.getElementById('reading-id').value = editReadingId || '';
    
    if (editReadingId) {
        const r = readings.find(r => r.id === editReadingId);
        if (r) {
            meterSelect.value = r.meter_id;
            meterSelect.disabled = true;
            document.getElementById('reading-date').value = r.reading_date.split('T')[0];
            document.getElementById('reading-value').value = r.value;
            document.getElementById('reading-value-nt').value = r.value_nt || '';
            // NK-124: die Ablesungsart (NK-051) zeigen und aenderbar machen.
            document.getElementById('reading-ablesungsart').value = r.ablesungsart || 'ablesung';
            document.getElementById('reading-is-official').checked = r.is_official_invoice || false;
            document.getElementById('group-reading-provider').style.display = r.is_official_invoice ? 'block' : 'none';
            if (r.provider_id) document.getElementById('reading-provider').value = r.provider_id;
            document.getElementById('plausibility-alert').style.display = 'none';
            document.getElementById('reading-file').value = '';
            document.getElementById('reading-file-name').textContent = r.document_path ? 'Neues Bild hochladen (überschreibt altes)' : 'Datei auswählen...';
            document.querySelector('#reading-modal .modal-header h2').textContent = 'Zählerstand bearbeiten';
        }
    } else {
        meterSelect.disabled = false;
        if (meterId) meterSelect.value = meterId;
        document.getElementById('reading-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('reading-value').value = '';
        document.getElementById('reading-value-nt').value = '';
        document.getElementById('reading-ablesungsart').value = 'ablesung';
        document.getElementById('reading-is-official').checked = false;
        document.getElementById('group-reading-provider').style.display = 'none';
        document.getElementById('reading-provider').value = '';
        document.getElementById('plausibility-alert').style.display = 'none';
        document.getElementById('reading-file').value = '';
        document.getElementById('reading-file-name').textContent = 'Datei auswählen...';
        document.querySelector('#reading-modal .modal-header h2').textContent = 'Zählerstand erfassen';
    }
    
    handleReadingMeterChange();
    
    document.getElementById('reading-modal').classList.add('active');
}

function closeAddReadingModal() { document.getElementById('reading-modal').classList.remove('active'); }

async function saveReading() {
    const editId = document.getElementById('reading-id').value;
    const meterId = document.getElementById('reading-meter').value;
    const date = document.getElementById('reading-date').value;
    const val = document.getElementById('reading-value').value;
    const val_nt = document.getElementById('reading-value-nt').value;
    const fileInput = document.getElementById('reading-file');
    
    if (!meterId || !date || !val) {
        showError('Pflichtfelder fehlen.');
        return;
    }
    
    const formData = new FormData();
    formData.append('meter_id', meterId);
    formData.append('reading_date', date);
    formData.append('value', val);
    const isOfficial = document.getElementById('reading-is-official').checked;
    formData.append('is_official_invoice', isOfficial);
    
    if (isOfficial) {
        const providerId = document.getElementById('reading-provider').value;
        if (!providerId) {
            showError('Bitte einen Anbieter für den offiziellen Stand auswählen.');
            return;
        }
        formData.append('provider_id', providerId);
    }
    
    if (val_nt) formData.append('value_nt', val_nt);
    // NK-124: die Ablesungsart geht mit — nur "zwischenablesung" markiert
    // den Stand zum Datum eines Mieterwechsels oder der Eigenutzung.
    formData.append('ablesungsart', document.getElementById('reading-ablesungsart').value);
    
    if (fileInput.files.length > 0) {
        formData.append('file', fileInput.files[0]);
    }
    
    try {
        const url = editId ? `/api/readings/${editId}` : '/api/readings';
        const method = editId ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method: method,
            body: formData
        });
        if(!res.ok) throw await serverFehler(res);
        closeAddReadingModal();
        fetchReadings();
        if(editId) fetchMeters(); // Refresh table
    } catch(e) {
        showError(meldungZu(e, 'Fehler beim Speichern.'));
    }
}

// --- Plausibility Check ---
let plausibilityTimeout;
function triggerPlausibilityCheck() {
    clearTimeout(plausibilityTimeout);
    plausibilityTimeout = setTimeout(checkPlausibility, 500);
}

document.getElementById('reading-value').addEventListener('input', triggerPlausibilityCheck);
document.getElementById('reading-date').addEventListener('change', triggerPlausibilityCheck);
document.getElementById('reading-is-official').addEventListener('change', triggerPlausibilityCheck);

async function checkPlausibility() {
    const isOfficial = document.getElementById('reading-is-official').checked;
    const alertBox = document.getElementById('plausibility-alert');
    const meterId = document.getElementById('reading-meter').value;
    const date = document.getElementById('reading-date').value;
    const val = document.getElementById('reading-value').value;
    
    if (!isOfficial || !meterId || !date || val === '') {
        alertBox.style.display = 'none';
        return;
    }
    
    try {
        const res = await fetch('/api/readings/check_plausibility', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meter_id: meterId, reading_date: date, value: val })
        });
        const data = await res.json();
        
        if (data.status === 'warning') {
            alertBox.style.display = 'block';
            alertBox.style.backgroundColor = 'var(--danger-bg)';
            alertBox.style.color = 'var(--danger-color)';
            alertBox.style.border = '1px solid rgba(220, 38, 38, 0.3)';
            alertBox.innerHTML = `<i class="ph ph-warning-circle" style="margin-right: 6px;"></i> ${escapeHtml(data.message)}`;
        } else if (data.status === 'success') {
            alertBox.style.display = 'block';
            alertBox.style.backgroundColor = 'var(--success-bg)';
            alertBox.style.color = 'var(--success-color)';
            alertBox.style.border = '1px solid rgba(34, 197, 94, 0.3)';
            alertBox.innerHTML = `<i class="ph ph-check-circle" style="margin-right: 6px;"></i> ${escapeHtml(data.message)}`;
        } else {
            alertBox.style.display = 'none';
        }
    } catch(e) {
        console.error('Plausibility check failed', e);
    }
}

// --- Invoice Modals & Save ---
function populateInvoiceApartments() {
    const propId = parseInt(document.getElementById('invoice-property').value);
    const aptSelect = document.getElementById('invoice-apartment');
    aptSelect.innerHTML = '<option value="">Gesamtes Gebäude (Standard)</option>';
    if (propId) {
        const propName = properties.find(p => p.id === propId)?.name;
        const apts = allApartments.filter(a => a.property_name === propName);
        apts.forEach(a => {
            aptSelect.insertAdjacentHTML('beforeend', `<option value="${a.id}">${escapeHtml(a.name)}</option>`);
        });
    }
}

// NK-125: die Anlagen der gewählten Immobilie in den Rechnungsdialog, und
// der Posten des § 7 Abs. 2 erscheint erst, wenn eine Anlage gewählt ist.
async function populateInvoiceHeizung(editAnlageId = null) {
    const propId = parseInt(document.getElementById('invoice-property').value);
    const anlageSelect = document.getElementById('invoice-heizungsanlage');
    const artSelect = document.getElementById('invoice-heizkostenart');
    anlageSelect.replaceChildren();
    anlageSelect.insertAdjacentHTML('beforeend', '<option value="">— keine Heizkostenrechnung —</option>');
    artSelect.replaceChildren();
    artSelect.insertAdjacentHTML('beforeend', '<option value="">— kein Posten —</option>');
    Object.entries(HEIZKOSTENARTEN_TEXT).forEach(([schluessel, text]) => {
        artSelect.insertAdjacentHTML('beforeend', `<option value="${schluessel}">${text}</option>`);
    });
    artSelect.disabled = true;
    document.getElementById('gruppe-invoice-co2').style.display = 'none';
    if (!propId) return;

    try {
        const anlagen = await fetchHeizungsanlagen(propId);
        anlagen.forEach(a => {
            anlageSelect.insertAdjacentHTML('beforeend',
                `<option value="${a.id}">${escapeHtml(a.name)}</option>`);
        });
        if (editAnlageId) anlageSelect.value = editAnlageId;
    } catch (error) {
        console.error('Heizungsanlagen konnten nicht geladen werden', error);
    }
}

function toggleInvoiceHeizkosten() {
    const anlageWahl = document.getElementById('invoice-heizungsanlage').value;
    const artSelect = document.getElementById('invoice-heizkostenart');
    artSelect.disabled = !anlageWahl;
    document.getElementById('gruppe-invoice-co2').style.display = anlageWahl ? 'block' : 'none';
}

async function openAddInvoiceModal(editInvoiceId = null) {
    const catSelect = document.getElementById('invoice-category');
    catSelect.replaceChildren();
    categories.forEach(c => {
        catSelect.insertAdjacentHTML('beforeend', `<option value="${c.id}">${escapeHtml(c.name)}</option>`);
    });
    
    const propSelect = document.getElementById('invoice-property');
    propSelect.replaceChildren();
    properties.forEach(p => {
        propSelect.insertAdjacentHTML('beforeend', `<option value="${p.id}">${escapeHtml(p.name)}</option>`);
    });
    // NK-125: bei Immobilienwechsel die Anlagen des Rechnungsdialogs wechseln.
    propSelect.onchange = async () => {
        populateInvoiceApartments();
        await populateInvoiceHeizung();
        document.getElementById('invoice-heizkostenart').value = '';
        toggleInvoiceHeizkosten();
    };
    
    // Providers dropdown
    const provSelect = document.getElementById('invoice-provider');
    if (provSelect) {
        provSelect.innerHTML = '<option value="">--- Anbieter wählen ---</option>';
        providers.forEach(p => {
            provSelect.innerHTML += `<option value="${p.id}">${escapeHtml(p.name)}</option>`;
        });
    }

    // Populate Document Dropdown
    const docSelect = document.getElementById('invoice-document-id');
    docSelect.innerHTML = '<option value="">-- Neuen Beleg hochladen (Einzelrechnung) --</option>';
    currentDocuments.forEach(d => {
        docSelect.innerHTML += `<option value="${d.id}">${escapeHtml(d.description)} (${escapeHtml(d.property_name)})</option>`;
    });

    document.getElementById('invoice-id').value = editInvoiceId || '';
    const fileInput = document.getElementById('invoice-file');
    const fileNameSpan = document.getElementById('invoice-file-name');
    
    if (editInvoiceId) {
        const i = invoices.find(inv => inv.id === editInvoiceId);
        if (i) {
            catSelect.value = i.category_id;
            propSelect.value = i.property_id;
            document.getElementById('invoice-amount').value = i.amount;
            document.getElementById('invoice-number').value = i.invoice_number || '';
            document.getElementById('invoice-description').value = i.description || '';
            document.getElementById('invoice-start').value = i.start_date.split('T')[0];
            document.getElementById('invoice-end').value = i.end_date.split('T')[0];
            // NK-124: das Datum des Belegs (NK-058) zeigen und aenderbar machen.
            document.getElementById('invoice-rechnungsdatum').value = i.rechnungsdatum || '';
            // NK-124: die Tarifpreise (NK-055) gehoeren zusammen.
            document.getElementById('invoice-preis-ht').value = i.preis_ht ?? '';
            document.getElementById('invoice-preis-nt').value = i.preis_nt ?? '';
            document.getElementById('invoice-pages').value = i.document_pages || '';
            // NK-125: Anlage, Posten und CO2-Angaben des Belegs.
            await populateInvoiceHeizung(i.heizungsanlage_id || null);
            document.getElementById('invoice-heizkostenart').value = i.heizkostenart || '';
            document.getElementById('invoice-co2-kosten').value = i.co2_kosten ?? '';
            document.getElementById('invoice-co2-emission').value = i.co2_emission_kg ?? '';
            toggleInvoiceHeizkosten();
            
            if (provSelect && i.provider_id) provSelect.value = i.provider_id;
            if (i.invoice_document_id) {
                docSelect.value = i.invoice_document_id;
            } else {
                docSelect.value = '';
            }
            populateInvoiceApartments();
            document.getElementById('invoice-apartment').value = i.apartment_id || '';
            document.querySelector('#invoice-modal h2').textContent = 'Rechnung bearbeiten';
            fileNameSpan.textContent = 'Neuen Beleg hochladen (optional)';
            fileInput.required = false;
        }
    } else {
        document.getElementById('invoice-amount').value = '';
        document.getElementById('invoice-number').value = '';
        document.getElementById('invoice-description').value = '';
        const year = new Date().getFullYear();
        document.getElementById('invoice-start').value = `${year}-01-01`;
        document.getElementById('invoice-end').value = `${year}-12-31`;
        document.getElementById('invoice-rechnungsdatum').value = '';
        document.getElementById('invoice-preis-ht').value = '';
        document.getElementById('invoice-preis-nt').value = '';
        document.getElementById('invoice-pages').value = '';
        if (provSelect) provSelect.value = '';
        docSelect.value = '';
        await populateInvoiceHeizung();
        document.getElementById('invoice-heizkostenart').value = '';
        document.getElementById('invoice-co2-kosten').value = '';
        document.getElementById('invoice-co2-emission').value = '';
        toggleInvoiceHeizkosten();
        if (propSelect.value) populateInvoiceApartments();
        document.getElementById('invoice-apartment').value = '';
        document.querySelector('#invoice-modal h2').textContent = 'Rechnung erfassen';
        fileInput.required = false;
        fileNameSpan.textContent = 'Datei auswählen...';
    }
    
    toggleInvoiceDescription();
    toggleInvoiceFileUpload();
    
    document.getElementById('invoice-modal').classList.add('active');
}

function toggleInvoiceFileUpload() {
    const docId = document.getElementById('invoice-document-id').value;
    if (docId) {
        document.getElementById('group-invoice-file').style.display = 'none';
        document.getElementById('group-invoice-pages').style.display = 'block';
    } else {
        document.getElementById('group-invoice-file').style.display = 'block';
        document.getElementById('group-invoice-pages').style.display = 'none';
    }
}

function openAddInvoiceForDoc(docId) {
    openAddInvoiceModal();
    const docSelect = document.getElementById('invoice-document-id');
    if (docSelect.querySelector(`option[value="${docId}"]`)) {
        docSelect.value = docId;
    }
    toggleInvoiceFileUpload();
}

// --- Document Manager Logic ---
let currentDocuments = [];

async function fetchDocuments() {
    try {
        const res = await fetch('/api/invoice_documents');
        currentDocuments = await res.json();
        renderDocuments();
    } catch(e) { console.error('Belegabruf fehlgeschlagen', e); }
}

function renderDocuments() {
    const container = document.getElementById('documents-container');
    if (!container) return;
    
    if (currentDocuments.length === 0) {
        container.innerHTML = leerzustand({
            icon: 'ph-file-pdf',
            titel: 'Noch keine Belege hochgeladen',
            text: 'Hier gehört der Beleg des Anbieters hinein — zum Beispiel die Jahresabrechnung der Stadtwerke.',
            aktion: { label: 'Beleg hochladen', fn: 'openAddDocumentModal()', icon: 'ph-upload-simple' },
        });
        return;
    }
    
    let html = `<table style="width: 100%; border-collapse: collapse; text-align: left;">
        <thead>
            <tr style="border-bottom: 1px solid var(--border-color);">
                <th style="padding: 12px;">Immobilie</th>
                <th style="padding: 12px;">Beschreibung</th>
                <th style="padding: 12px;">Upload-Datum</th>
                <th style="padding: 12px; text-align: right;">Aktionen</th>
            </tr>
        </thead>
        <tbody>`;
        
    currentDocuments.forEach(d => {
        const imgUrl = dateiAdresse('dokument', d.id);
        html += `
            <tr style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 12px;">${escapeHtml(d.property_name)}</td>
                <td style="padding: 12px;">
                    <a href="${imgUrl}" target="_blank" style="color: var(--primary-color); text-decoration: none; font-weight: bold;">
                        <i class="ph ph-file-pdf"></i> ${escapeHtml(d.description)}
                    </a>
                </td>
                <td style="padding: 12px;">${new Date(d.upload_date).toLocaleDateString('de-DE')}</td>
                <td style="padding: 12px; text-align: right;">
                    <button class="btn-secondary" style="padding: 6px 12px; font-size: 14px; margin-right: 8px;" onclick="openAddInvoiceForDoc(${d.id})">
                        <i class="ph ph-plus"></i> Rechnung erfassen
                    </button>
                    <button class="btn-icon" title="Beleg bearbeiten" onclick="openAddDocumentModal(${d.id})" style="margin-right: 4px;"><i class="ph ph-pencil-simple"></i></button>
                    <button class="btn-icon" title="Beleg löschen" onclick="deleteDocument(${d.id})"><i class="ph ph-trash"></i></button>
                </td>
            </tr>
        `;
    });
    
    html += `</tbody></table>`;
    container.innerHTML = `<div class="glass-panel" style="padding: 24px;">${html}</div>`;
}

function openAddDocumentModal(editDocId = null) {
    const propSelect = document.getElementById('doc-property');
    propSelect.innerHTML = '';
    properties.forEach(p => {
        propSelect.innerHTML += `<option value="${p.id}">${escapeHtml(p.name)}</option>`;
    });
    
    document.getElementById('doc-id').value = editDocId || '';
    const fileInput = document.getElementById('doc-file');
    const fileNameSpan = document.getElementById('doc-file-name');
    
    if (editDocId) {
        const d = currentDocuments.find(doc => doc.id === editDocId);
        if (d) {
            propSelect.value = d.property_id;
            document.getElementById('doc-description').value = d.description || '';
            document.querySelector('#document-modal h2').textContent = 'Sammelrechnung bearbeiten';
            fileNameSpan.textContent = 'Neues PDF auswählen (optional)';
            fileInput.required = false;
        }
    } else {
        document.getElementById('doc-description').value = '';
        fileInput.value = '';
        fileNameSpan.textContent = 'PDF auswählen...';
        document.querySelector('#document-modal h2').textContent = 'Beleg hochladen (Sammelrechnung)';
        fileInput.required = true;
    }
    
    document.getElementById('document-modal').classList.add('active');
}

function closeAddDocumentModal() {
    document.getElementById('document-modal').classList.remove('active');
}

async function saveDocument() {
    const docId = document.getElementById('doc-id').value;
    const propId = document.getElementById('doc-property').value;
    const desc = document.getElementById('doc-description').value;
    const fileInput = document.getElementById('doc-file');
    
    if (!docId && fileInput.files.length === 0) {
        showError('Bitte wählen Sie eine Datei aus.');
        return;
    }
    
    const btn = document.getElementById('btn-save-doc');
    btn.disabled = true;
    btn.textContent = docId ? 'Speichert...' : 'Wird hochgeladen...';
    
    const formData = new FormData();
    formData.append('property_id', propId);
    formData.append('description', desc);
    if (fileInput.files.length > 0) {
        formData.append('file', fileInput.files[0]);
    }
    
    try {
        const url = docId ? `/api/invoice_documents/${docId}` : '/api/invoice_documents';
        const method = docId ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method: method,
            body: formData
        });
        if (!res.ok) throw await serverFehler(res);
        closeAddDocumentModal();
        fetchDocuments();
    } catch(e) {
        showError(meldungZu(e, 'Fehler beim Speichern.'));
    } finally {
        btn.disabled = false;
        btn.textContent = docId ? 'Speichern' : 'Hochladen';
    }
}

function closeAddInvoiceModal() { document.getElementById('invoice-modal').classList.remove('active'); }

// NK-113: Die Bezeichnung gehört zu Nr. 17 (sonstige Betriebskosten) — erkannt
// an der Katalognummer, nicht am Namen. Der alte Namensvergleich auf
// „sonstiges“ verfehlte seit dem Katalog (NK-044) „Sonstige Betriebskosten“.
const BETRKV_NR_SONSTIGE = 17;

function toggleInvoiceDescription() {
    const catSelect = document.getElementById('invoice-category');
    const kategorie = categories.find(c => String(c.id) === catSelect.value);
    const descGroup = document.getElementById('group-invoice-description');

    if (kategorie && kategorie.betrkv_nr === BETRKV_NR_SONSTIGE) {
        descGroup.style.display = 'block';
    } else {
        descGroup.style.display = 'none';
    }
}

async function saveInvoice() {
    const invId = document.getElementById('invoice-id').value;
    const catId = document.getElementById('invoice-category').value;
    const propId = document.getElementById('invoice-property').value;
    const amount = document.getElementById('invoice-amount').value;
    const invoiceNumber = document.getElementById('invoice-number').value;
    const description = document.getElementById('invoice-description').value;
    const providerId = document.getElementById('invoice-provider').value;
    const start = document.getElementById('invoice-start').value;
    const end = document.getElementById('invoice-end').value;
    const docId = document.getElementById('invoice-document-id').value;
    const docPages = document.getElementById('invoice-pages').value;
    const aptId = document.getElementById('invoice-apartment').value;
    const fileInput = document.getElementById('invoice-file');
    
    if (!catId || !propId || !amount || !start || !end || !providerId) {
        showError('Pflichtfelder fehlen.');
        return;
    }
    
    const formData = new FormData();
    formData.append('category_id', catId);
    formData.append('property_id', propId);
    formData.append('amount', amount);
    formData.append('invoice_number', invoiceNumber);
    formData.append('description', description);
    formData.append('provider_id', providerId);
    formData.append('start_date', start);
    formData.append('end_date', end);
    // NK-124: das Ausstellungsdatum des Belegs, freiwillig wie im Modell.
    const rechnungsdatum = document.getElementById('invoice-rechnungsdatum').value;
    if (rechnungsdatum) formData.append('rechnungsdatum', rechnungsdatum);
    // NK-124: die Tarifpreise wandern nur zusammen (dieselbe Regel wie der
    // CHECK in der Datenbank: ein Preis ohne Partner waere gelogen).
    const preisHt = document.getElementById('invoice-preis-ht').value;
    const preisNt = document.getElementById('invoice-preis-nt').value;
    if ((preisHt === '') !== (preisNt === '')) {
        showError('Die Tarifpreise gehören zusammen: tragen Sie Hoch- und Niedertarif ein oder keinen von beiden.');
        return;
    }
    if (preisHt !== '') formData.append('preis_ht', preisHt);
    if (preisNt !== '') formData.append('preis_nt', preisNt);
    // NK-125: Anlage und Posten gehoeren zusammen (D-44); die CO2-Angaben
    // des Belegs kommen dazu, sobald eine Anlage gewaehlt ist.
    const heizungsanlageId = document.getElementById('invoice-heizungsanlage').value;
    const heizkostenart = document.getElementById('invoice-heizkostenart').value;
    if ((heizungsanlageId === '') !== (heizkostenart === '')) {
        showError('Heizkostenrechnung braucht beides: die Anlage und den Posten des § 7 Abs. 2 HeizkostenV.');
        return;
    }
    if (heizungsanlageId) {
        formData.append('heizungsanlage_id', heizungsanlageId);
        formData.append('heizkostenart', heizkostenart);
        const co2Kosten = document.getElementById('invoice-co2-kosten').value;
        const co2Emission = document.getElementById('invoice-co2-emission').value;
        if ((co2Kosten === '') !== (co2Emission === '')) {
            showError('Die CO2-Angaben gehören zusammen: tragen Sie Kosten und Emissionen ein oder keine von beiden.');
            return;
        }
        if (co2Kosten !== '') formData.append('co2_kosten', co2Kosten);
        if (co2Emission !== '') formData.append('co2_emission_kg', co2Emission);
    }
    formData.append('document_pages', docPages);
    if (aptId) formData.append('apartment_id', aptId);
    
    if (docId) {
        formData.append('invoice_document_id', docId);
    } else if (fileInput.files.length > 0) {
        formData.append('file', fileInput.files[0]);
    }
    
    const btn = document.getElementById('btn-save-invoice');
    btn.disabled = true;
    btn.textContent = 'Speichert...';
    
    try {
        const url = invId ? `/api/invoices/${invId}` : '/api/invoices';
        const method = invId ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method: method,
            body: formData
        });
        if(!res.ok) throw await serverFehler(res);
        closeAddInvoiceModal();
        fetchInvoices();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Speichern.')); }
    finally {
        btn.disabled = false;
        btn.textContent = 'Rechnung speichern';
    }
}

async function deleteDocument(id) {
    if(!await frageLoeschen('Sammelrechnung wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/invoice_documents/${id}`, { method: 'DELETE' });
        if(!res.ok) throw await serverFehler(res);
        fetchDocuments();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Löschen des Belegs.')); }
}

async function deleteInvoice(id) {
    if(!await frageLoeschen('Möchten Sie diese Rechnung wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/invoices/${id}`, { method: 'DELETE' });
        if(!res.ok) throw await serverFehler(res);
        fetchInvoices();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Löschen.')); }
}

// --- Providers ---
async function fetchProviders() {
    try {
        const res = await fetch('/api/providers');
        providers = await res.json();
        renderProviders();
        populateProviderSelects();
    } catch(e) { console.error('Anbieter konnten nicht geladen werden', e); }
}

function renderProviders() {
    const tbody = document.getElementById('providers-table-body');
    if (!tbody) return;
    tbody.replaceChildren();
    
    providers.forEach(p => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid var(--border-color)";
        tr.innerHTML = `
            <td style="padding: 12px 8px;">${escapeHtml(p.name)}</td>
            <td style="padding: 12px 8px;">
                <button class="btn-icon" style="color: var(--danger-color);" onclick="deleteProvider(${p.id})"><i class="ph ph-trash"></i></button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function populateProviderSelects() {
    const selects = [document.getElementById('reading-provider'), document.getElementById('invoice-provider')];
    selects.forEach(sel => {
        if (!sel) return;
        const currentVal = sel.value;
        sel.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = '--- Anbieter wählen ---';
        sel.appendChild(emptyOpt);
        
        providers.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            sel.appendChild(opt);
        });
        if (currentVal) sel.value = currentVal;
    });
}

async function addProvider() {
    const input = document.getElementById('new-provider-name');
    const name = input.value.trim();
    if (!name) return;
    
    try {
        const res = await fetch('/api/providers', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name})
        });
        if(!res.ok) throw await serverFehler(res);
        input.value = '';
        fetchProviders();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Speichern des Anbieters.')); }
}

async function deleteProvider(id) {
    if(!await frageLoeschen('Anbieter wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/providers/${id}`, { method: 'DELETE' });
        if(!res.ok) throw await serverFehler(res);
        fetchProviders();
    } catch(e) { showError(meldungZu(e, 'Fehler beim Löschen (Evtl. noch in Verwendung).')); }
}

// --- Vermieterdaten (NK-124) ---

async function fetchVermieterdaten() {
    "Der Ausweis des Vermieters in der Einstellungs-Liste zeigen."
    try {
        const res = await fetch('/api/vermieter');
        if (!res.ok) throw await serverFehler(res);
        const stand = await res.json();
        document.getElementById('vermieter-name').value = stand.name || '';
        document.getElementById('vermieter-iban').value = stand.iban || '';
        const quelle = [];
        if (stand.name_quelle === 'umgebung') quelle.push('Name aus der Umgebungsvariable VERMIETER_NAME');
        if (stand.iban_quelle === 'umgebung') quelle.push('IBAN aus der Umgebungsvariable VERMIETER_IBAN');
        document.getElementById('vermieter-quelle').textContent = quelle.join(' · ');
        zeigeVermieterLogo(stand.logo);
        const hinweis = document.getElementById('vermieter-girocode-hinweis');
        if (stand.girocode_bereit) {
            hinweis.innerHTML = '<i class="ph ph-check-circle" style="color: var(--success-color);"></i> GiroCode aktiv';
        } else {
            hinweis.innerHTML = '<i class="ph ph-info"></i> Kein GiroCode (Name oder IBAN fehlt)';
        }
    } catch (e) {
        console.error('Fehler beim Laden der Vermieterdaten', e);
    }
}

// NK-155: Logo des Vermieters für das Deckblatt.
function zeigeVermieterLogo(vorhanden) {
    const vorschau = document.getElementById('vermieter-logo-vorschau');
    const loeschen = document.getElementById('btn-vermieter-logo-loeschen');
    if (!vorschau) return;
    vorschau.hidden = !vorhanden;
    loeschen.hidden = !vorhanden;
    if (vorhanden) vorschau.src = '/api/vermieter/logo?stand=' + Date.now();
}

async function vermieterLogoHochladen(feld) {
    const datei = feld.files && feld.files[0];
    feld.value = '';
    if (!datei) return;
    const formular = new FormData();
    formular.append('logo', datei);
    try {
        const res = await fetch('/api/vermieter/logo', { method: 'POST', body: formular });
        if (!res.ok) throw await serverFehler(res);
        zeigeVermieterLogo(true);
        showSuccess('Logo gespeichert. Es erscheint auf dem Deckblatt der nächsten Abrechnung.');
    } catch (e) {
        showError(meldungZu(e, 'Das Logo konnte nicht gespeichert werden.'));
    }
}
window.vermieterLogoHochladen = vermieterLogoHochladen;

async function vermieterLogoLoeschen() {
    try {
        const res = await fetch('/api/vermieter/logo', { method: 'DELETE' });
        if (!res.ok) throw await serverFehler(res);
        zeigeVermieterLogo(false);
        showSuccess('Logo gelöscht.');
    } catch (e) {
        showError(meldungZu(e, 'Das Logo konnte nicht gelöscht werden.'));
    }
}
window.vermieterLogoLoeschen = vermieterLogoLoeschen;

async function saveVermieterdaten() {
    const name = document.getElementById('vermieter-name').value.trim();
    const iban = document.getElementById('vermieter-iban').value.trim();
    try {
        const res = await fetch('/api/vermieter', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, iban })
        });
        if (!res.ok) throw await serverFehler(res);
        showSuccess('Vermieterdaten gespeichert.');
        fetchVermieterdaten();
    } catch (e) {
        showError(meldungZu(e, 'Die Vermieterdaten konnten nicht gespeichert werden.'));
    }
}

// --- Konto und Ersteinrichtung (NK-127, E-1) ---
// Ein Konto entsteht im Einrichtungsassistenten (serverseitige Seite unter
// /einrichtung, gesichert durch den Einmal-Code aus dem Serverprotokoll).
// Hier in den Einstellungen sehen Sie die Konten, ändern Ihr Passwort und
// legen gegebenenfalls das zweite an.

async function ladeKonten() {
    try {
        const res = await fetch('/api/konten');
        if (!res.ok) throw await serverFehler(res);
        const konten = await res.json();
        const tbody = document.getElementById('konto-zeilen');
        tbody.innerHTML = konten.map(k => `<tr>
            <td style="padding: 8px;">${escapeHtml(k.username)}</td>
            <td style="padding: 8px;">${k.last_login_at ? escapeHtml(k.last_login_at) : 'nie'}</td>
            <td style="padding: 8px;">${k.is_active ? 'aktiv' : 'stillgelegt'}</td>
        </tr>`).join('');
        // Der Bereich zum Anlegen des zweiten Kontos verschwindet, sobald
        // zwei existieren -- der Server nimm es sowieso nicht mehr an.
        document.getElementById('zweites-konto-bereich').style.display =
            konten.length < 2 ? '' : 'none';
        document.getElementById('konto-hinweis').textContent =
            konten.length < 2 ? 'Platz für ein zweites Konto' : '';
    } catch (e) {
        console.error('Fehler beim Laden der Konten', e);
    }
}

async function passwortAendern() {
    const alt = document.getElementById('konto-alt').value;
    const neu = document.getElementById('konto-neu').value;
    const neu2 = document.getElementById('konto-neu2').value;
    if (neu !== neu2) {
        showError('Die Passwörter stimmen nicht überein.');
        return;
    }
    if (neu.length < 10) {
        showError('Das neue Passwort muss mindestens 10 Zeichen haben.');
        return;
    }
    try {
        const res = await fetch('/api/konto/passwort', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ altes_passwort: alt, neues_passwort: neu })
        });
        if (!res.ok) throw await serverFehler(res);
        showSuccess('Passwort geändert.');
        ['konto-alt', 'konto-neu', 'konto-neu2'].forEach(id =>
            document.getElementById(id).value = '');
        ladeKonten();
    } catch (e) {
        showError(meldungZu(e, 'Das Passwort konnte nicht geändert werden.'));
    }
}

async function zweitesKontoAnlegen() {
    const name = document.getElementById('konto-neu-name').value.trim();
    const passwort = document.getElementById('konto-neu-passwort').value;
    if (!name) {
        showError('Bitte geben Sie einen Benutzernamen ein.');
        return;
    }
    if (passwort.length < 10) {
        showError('Das Passwort muss mindestens 10 Zeichen haben.');
        return;
    }
    try {
        const res = await fetch('/api/konten', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: name, password: passwort })
        });
        if (!res.ok) throw await serverFehler(res);
        showSuccess(`Konto '${name}' angelegt.`);
        document.getElementById('konto-neu-name').value = '';
        document.getElementById('konto-neu-passwort').value = '';
        ladeKonten();
    } catch (e) {
        showError(meldungZu(e, 'Das Konto konnte nicht angelegt werden.'));
    }
}

// --- Sicherung und Wiederherstellung (NK-077, Kern seit NK-025) ---
//
// Die Erinnerung folgt der letzten Sicherung, die der Server kennt: keine ->
// rot, aelter als 30 Tage -> gelb, sonst gruen. Das Ziel bleibt frei waehlbar;
// der Server merkt sich das zuletzt gewaehlte und schlaegt es beim naechsten
// Mal vor.

let letztesSicherungsziel = null;

async function ladeSicherungsStatus() {
    try {
        const res = await fetch('/api/backup/status');
        if (!res.ok) throw await serverFehler(res);
        const status = await res.json();
        const box = document.getElementById('sicherung-erinnerung');
        box.style.display = '';
        const stufen = {
            rot:    { hintergrund: 'rgba(220, 53, 69, 0.14)', rand: 'rgba(220, 53, 69, 0.55)' },
            gelb:   { hintergrund: 'rgba(255, 193, 7, 0.14)', rand: 'rgba(255, 193, 7, 0.55)' },
            gruen:  { hintergrund: 'rgba(40, 167, 69, 0.14)', rand: 'rgba(40, 167, 69, 0.55)' },
        };
        const farbe = stufen[status.erinnerung.stufe] || stufen.gruen;
        box.style.background = farbe.hintergrund;
        box.style.border = `1px solid ${farbe.rand}`;
        box.textContent = status.erinnerung.text;
        const eingabe = document.getElementById('sicherung-ziel');
        // F-76: nur freigegebene Verzeichnisse (Datenordner, BACKUP_ZIELE).
        const erlaubt = status.erlaubte_ziele || [];
        document.getElementById('sicherung-ziele').innerHTML =
            erlaubt.map(z => `<option value="${escapeHtml(z)}"></option>`).join('');
        document.getElementById('sicherung-erlaubt').textContent = erlaubt.length
            ? `Freigegebene Verzeichnisse (auch Unterordner): ${erlaubt.join(', ')}`
            : '';
        // NK-152: in der App gibt es den Ordner-Dialog.
        const ordnerKnopf = document.getElementById('btn-sicherung-ordner');
        if (ordnerKnopf) ordnerKnopf.style.display = huelle.aktiv() ? '' : 'none';
        // NK-130: Hinweis zur Festplattenverschluesselung, mit Pruefergebnis.
        const platte = document.getElementById('sicherung-festplatte');
        if (platte && status.festplatte) {
            platte.style.display = '';
            platte.textContent = `${status.festplatte.text} ${status.festplatte.hinweis}`;
        }
        letztesSicherungsziel = status.zuletzt_gewaehltes_ziel || status.standardziel;
        if (!eingabe.value) eingabe.value = letztesSicherungsziel;
        ladeSicherungen(eingabe.value);
    } catch (e) {
        console.error('Fehler beim Laden des Sicherungsstands', e);
    }
}

async function ladeSicherungen(ziel) {
    const tbody = document.getElementById('sicherung-zeilen');
    try {
        const res = await fetch(`/api/backup/liste?ziel=${encodeURIComponent(ziel || '')}`);
        if (!res.ok) throw await serverFehler(res);
        const liste = await res.json();
        if (!liste.sicherungen.length) {
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 8px; color: var(--text-muted);">Noch keine Sicherung im gewählten Verzeichnis.</td></tr>';
            return;
        }
        tbody.innerHTML = liste.sicherungen.map(s => `<tr>
            <td style="padding: 8px;">${escapeHtml(s.name)}${s.verschluesselt ? ' <i class="ph ph-lock-simple" title="Verschlüsselt, Passphrase nötig"></i>' : ''}${s.einspielbar ? '' : ' <i class="ph ph-warning" title="Der Schemastand ist neuer als diese Fassung" aria-label="Nicht einspielbar"></i>'}</td>
            <td style="padding: 8px;">${escapeHtml(formatiereZeitpunkt(s.erstellt_am))}</td>
            <td style="padding: 8px;">${escapeHtml(s.groesse)}</td>
            <td style="padding: 8px;">${s.belege}</td>
            <td style="padding: 8px;"><button class="btn-secondary" onclick="sicherungEinspielen(this)">${s.einspielbar ? 'Einspielen' : 'Ansehen'}</button></td>
        </tr>`).join('');
        tbody.querySelectorAll('button').forEach((knopf, i) => {
            knopf.dataset.ziel = liste.ziel;
            knopf.dataset.name = liste.sicherungen[i].name;
            knopf.dataset.verschluesselt = liste.sicherungen[i].verschluesselt ? '1' : '';
        });
    } catch (e) {
        console.error('Fehler beim Laden der Sicherungen', e);
        tbody.innerHTML = `<tr><td colspan="5" style="padding: 8px; color: var(--text-muted);">${escapeHtml(meldungZu(e, 'Die Sicherungen konnten nicht geladen werden.'))}</td></tr>`;
    }
}

function formatiereZeitpunkt(iso) {
    const zeit = new Date(iso);
    return isNaN(zeit) ? iso : zeit.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' });
}

async function sicherungsordnerWaehlen() {
    const ordner = await huelle.ordnerWaehlen();
    if (!ordner) return;
    document.getElementById('sicherung-ziel').value = ordner;
    ladeSicherungsStatus();
    ladeSicherungen(ordner);
}
window.sicherungsordnerWaehlen = sicherungsordnerWaehlen;

async function sicherungErstellen() {
    const ziel = document.getElementById('sicherung-ziel').value.trim();
    const auftrag = { ziel };
    if (document.getElementById('sicherung-verschluesseln').checked) {
        const eins = document.getElementById('sicherung-passphrase').value;
        const zwei = document.getElementById('sicherung-passphrase2').value;
        if (eins !== zwei) {
            showError('Die beiden Passphrasen stimmen nicht überein.');
            return;
        }
        auftrag.passphrase = eins;
    }
    try {
        const res = await fetch('/api/backup/erstellen', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(auftrag)
        });
        if (!res.ok) throw await serverFehler(res);
        const bericht = await res.json();
        showSuccess(`Sicherung '${bericht.name}' erstellt (${bericht.groesse}, ${bericht.belege} Belege${bericht.verschluesselt ? ', verschlüsselt' : ''}).`);
        document.getElementById('sicherung-passphrase').value = '';
        document.getElementById('sicherung-passphrase2').value = '';
        ladeSicherungsStatus();
    } catch (e) {
        showError(meldungZu(e, 'Die Sicherung konnte nicht erstellt werden.'));
    }
}

async function sicherungEinspielen(knopf) {
    // F-76: das Archiv geht nur als Name aus dem gelisteten Verzeichnis.
    const ziel = knopf.dataset.ziel;
    const name = knopf.dataset.name;
    let passphrase = null;
    if (knopf.dataset.verschluesselt) {
        passphrase = await fragePassphrase('Sicherung entschlüsseln',
            `Die Sicherung '${name}' ist verschlüsselt. Geben Sie die Passphrase ein, mit der sie erstellt wurde.`);
        if (passphrase === null) return;
    }
    if (!await frage(
        `Sicherung '${name}' einspielen?\n\n` +
        'Datenbank und Belege werden vollständig durch den Inhalt des Archivs ersetzt. ' +
        'Der heutige Stand wird vorher selbst gesichert. Weiter?', 'Einspielen')) {
        return;
    }
    try {
        const res = await fetch('/api/backup/einspielen', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ziel, name, passphrase })
        });
        if (!res.ok) throw await serverFehler(res);
        const bericht = await res.json();
        if (bericht.warnung) {
            showError(bericht.warnung);
        } else {
            showSuccess('Sicherung eingespielt. Alle Daten stehen auf dem Stand des Archivs.');
        }
        if (bericht.sicherheitskopie) {
            console.info('Der vorherige Stand liegt in', bericht.sicherheitskopie);
        }
        // Die Ansicht zeigt noch die alten Daten -- die Seite holt sich nach
        // dem Austausch alles frisch.
        setTimeout(() => location.reload(), 2500);
    } catch (e) {
        showError(meldungZu(e, 'Das Einspielen ist abgebrochen. Ihre Daten sind unverändert.'));
    }
}

// --- Umzugspaket (NK-164) ---------------------------------------------------
// Exportieren: im Browser ein Download (Klartext direkt als Link, damit auch
// Gigabytes nicht durch den Speicher müssen; verschlüsselt per POST), in der
// App an den Ort aus dem Speichern-Dialog. Übernehmen: hochladen in Stücken
// (static/umzug.js), aus dem Importordner (Docker) oder über den Datei-Dialog
// der App.

let umzugPfad = null;

function umzugHinweis(text) {
    const fehler = new Error(text);
    fehler.vomServer = true;  // eigener Satz, für Menschen gemacht
    return fehler;
}

async function ladeUmzug() {
    const desktop = window.umzugPaket && window.umzugPaket.desktop();
    document.getElementById('umzug-datei-einstellungen').hidden = !!desktop;
    document.getElementById('btn-umzug-auswahl').hidden = !desktop;
    const gruppe = document.getElementById('umzug-importordner-gruppe');
    if (desktop) {
        gruppe.hidden = true;
        return;
    }
    try {
        const res = await fetch('/api/umzug/importordner');
        if (!res.ok) throw await serverFehler(res);
        const daten = await res.json();
        const auswahl = document.getElementById('umzug-importordner');
        auswahl.innerHTML = '<option value="">— kein Paket aus dem Importordner —</option>' +
            daten.pakete.map(paket => `<option value="${escapeHtml(paket.name)}">` +
                `${escapeHtml(paket.name)} (${escapeHtml(paket.groesse)}${paket.verschluesselt ? ', verschlüsselt' : ''})</option>`).join('');
        gruppe.hidden = daten.pakete.length === 0;
        document.getElementById('umzug-importordner-hinweis').textContent =
            `Große Pakete können Sie auch direkt in den Ordner ${daten.ordner} legen.`;
    } catch (e) {
        gruppe.hidden = true;
    }
}

async function umzugExportieren() {
    let passphrase = null;
    if (document.getElementById('umzug-verschluesseln').checked) {
        const eins = document.getElementById('umzug-export-pass1').value;
        if (eins !== document.getElementById('umzug-export-pass2').value) {
            showError('Die beiden Passphrasen stimmen nicht überein.');
            return;
        }
        passphrase = eins;
    }
    const knopf = document.getElementById('btn-umzug-export');
    knopf.disabled = true;
    try {
        const name = `NebenkostenFix-${new Date().toISOString().slice(0, 10)}.nkfix`;
        if (window.umzugPaket.desktop()) {
            const pfad = await window.umzugPaket.desktopSpeichernUnter(name);
            if (!pfad) return;
            const res = await fetch('/api/umzug/export', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pfad, passphrase }),
            });
            if (!res.ok) throw await serverFehler(res);
            const bericht = await res.json();
            showSuccess(`Umzugspaket gespeichert: ${bericht.pfad} (${bericht.groesse}).`);
            return;
        }
        if (!passphrase) {
            // Klartext: der Browser lädt direkt, ohne den Umweg über den Speicher.
            await huelle.direktHerunterladen('/api/umzug/export', name);
            showSuccess('Das Umzugspaket wird erstellt und heruntergeladen. Bei vielen Belegen dauert das einen Moment.');
            return;
        }
        const res = await fetch('/api/umzug/export', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ passphrase }),
        });
        if (!res.ok) throw await serverFehler(res);
        await huelle.blobSpeichern(await res.blob(), name);
        showSuccess('Verschlüsseltes Umzugspaket heruntergeladen.');
    } catch (e) {
        showError(meldungZu(e, 'Das Umzugspaket konnte nicht erstellt werden.'));
    } finally {
        knopf.disabled = false;
        document.getElementById('umzug-export-pass1').value = '';
        document.getElementById('umzug-export-pass2').value = '';
    }
}
window.umzugExportieren = umzugExportieren;

async function umzugPaketWaehlen() {
    try {
        umzugPfad = await window.umzugPaket.desktopWaehlen();
        document.getElementById('umzug-auswahl-einstellungen').textContent = umzugPfad || '';
    } catch (e) {
        showError('Der Datei-Dialog ließ sich nicht öffnen.');
    }
}
window.umzugPaketWaehlen = umzugPaketWaehlen;

async function umzugUebernehmen() {
    const meldung = document.getElementById('umzug-meldung');
    const balken = document.getElementById('umzug-fortschritt-einstellungen');
    const bestaetigung = document.getElementById('umzug-bestaetigung').value.trim();
    if (bestaetigung !== 'ERSETZEN') {
        showError('Bitte geben Sie zur Bestätigung „ERSETZEN“ ein. Die Übernahme ersetzt alle Daten.');
        return;
    }
    const knopf = document.getElementById('btn-umzug-uebernehmen');
    knopf.disabled = true;
    try {
        let quelle;
        const datei = document.getElementById('umzug-datei-einstellungen').files[0];
        const ausOrdner = document.getElementById('umzug-importordner').value;
        if (window.umzugPaket.desktop()) {
            if (!umzugPfad) throw umzugHinweis('Bitte wählen Sie zuerst das Paket aus.');
            quelle = { pfad: umzugPfad };
        } else if (datei) {
            balken.hidden = false;
            const kennung = await window.umzugPaket.hochladen(datei, {
                fortschritt(ab, gesamt) {
                    balken.value = ab / gesamt;
                    meldung.textContent = `Hochgeladen: ${window.umzugPaket.lesbar(ab)} von ${window.umzugPaket.lesbar(gesamt)}`;
                },
            });
            quelle = { hochgeladen: kennung };
        } else if (ausOrdner) {
            quelle = { importordner: ausOrdner };
        } else {
            throw umzugHinweis('Bitte wählen Sie zuerst das Paket aus.');
        }
        const vorschau = await window.umzugPaket.pruefen(quelle);
        if (!vorschau.einspielbar) throw umzugHinweis(vorschau.hinweis || 'Das Paket passt nicht zu dieser Version.');
        meldung.textContent = 'Das Paket wird geprüft und übernommen …';
        const bericht = await window.umzugPaket.uebernehmen(quelle, {
            passphrase: document.getElementById('umzug-uebernahme-passphrase').value,
            bestaetigung,
        });
        meldung.textContent = `Übernommen: ${window.umzugPaket.anzahl(bericht.zeilen, 'Datensatz', 'Datensätze')} und ` +
            `${window.umzugPaket.anzahl(bericht.belege, 'Beleg', 'Belege')}. ` +
            'Sie werden gleich zur Anmeldung geleitet — melden Sie sich mit dem Konto aus dem Paket an.';
        setTimeout(() => { location.href = '/login'; }, 3500);
    } catch (e) {
        meldung.textContent = '';
        showError(meldungZu(e, 'Die Übernahme ist abgebrochen. Ihre Daten sind unverändert.'));
        knopf.disabled = false;
    } finally {
        balken.hidden = true;
    }
}
window.umzugUebernehmen = umzugUebernehmen;

// --- Import aus Excel/CSV (NK-161, F-90) ------------------------------------
// Drei Schritte in einem Dialog: Datei (mit Vorlage), Zuordnung der Spalten,
// Probelauf. „Daten importieren“ gibt es erst, wenn der Probelauf keinen
// Fehler fand -- die Übernahme ist alles oder nichts (tabellenimport.py).

let importArten = [];

function anzahlText(n, einzahl, mehrzahl) {
    return `${n} ${n === 1 ? einzahl : mehrzahl}`;
}

const IMPORT_NAMEN = {
    immobilien: ['Immobilie', 'Immobilien'], wohnungen: ['Wohnung', 'Wohnungen'],
    mieter: ['Mieter', 'Mieter'], rechnungen: ['Rechnung', 'Rechnungen'],
    anbieter: ['Anbieter', 'Anbieter'], zahlungen: ['Zahlung', 'Zahlungen'],
    zaehlerstaende: ['Zählerstand', 'Zählerstände'],
};

function angelegtText(angelegt) {
    return Object.entries(angelegt || {})
        .map(([art, n]) => anzahlText(n, ...(IMPORT_NAMEN[art] || [art, art]))).join(', ');
}
let importStand = null;  // {art, gelesen, bericht}

async function oeffneImport(art) {
    try {
        if (!importArten.length) {
            const res = await fetch('/api/import/arten');
            if (!res.ok) throw await serverFehler(res);
            importArten = await res.json();
            document.getElementById('import-art').innerHTML = importArten.map(a =>
                `<option value="${escapeHtml(a.art)}">${escapeHtml(a.titel)}</option>`).join('');
        }
    } catch (e) {
        showError(meldungZu(e, 'Der Import ließ sich nicht öffnen.'));
        return;
    }
    document.getElementById('import-art').value = art || 'rechnungen';
    document.getElementById('import-datei').value = '';
    importSchritt('datei');
    importArtGewaehlt();
    document.getElementById('import-modal').classList.add('active');
}
window.oeffneImport = oeffneImport;

function schliesseImport() {
    document.getElementById('import-modal').classList.remove('active');
    importStand = null;
}
window.schliesseImport = schliesseImport;

function importSchritt(name) {
    for (const schritt of ['datei', 'zuordnung', 'ergebnis']) {
        document.getElementById(`import-schritt-${schritt}`).hidden = schritt !== name;
    }
    const weiter = document.getElementById('import-weiter');
    weiter.disabled = false;
    weiter.textContent = { datei: 'Weiter', zuordnung: 'Tabelle prüfen', ergebnis: 'Daten importieren' }[name];
    document.getElementById('import-zuordnung-aendern').hidden = name !== 'ergebnis';
    document.getElementById('import-art').disabled = name !== 'datei';
}

function importArtGewaehlt() {
    const art = document.getElementById('import-art').value;
    const beschreibung = importArten.find(a => a.art === art);
    document.getElementById('import-erklaerung').textContent = beschreibung ? beschreibung.erklaerung : '';
    document.getElementById('import-vorlage-xlsx').href = `/api/import/vorlage/${art}.xlsx`;
    document.getElementById('import-vorlage-csv').href = `/api/import/vorlage/${art}.csv`;
}
window.importArtGewaehlt = importArtGewaehlt;

function importZuordnungAendern() {
    importSchritt('zuordnung');
}
window.importZuordnungAendern = importZuordnungAendern;

function importZuordnungLesen() {
    const zuordnung = {};
    document.querySelectorAll('#import-zuordnung select').forEach(auswahl => {
        if (auswahl.value !== '') zuordnung[auswahl.dataset.feld] = Number(auswahl.value);
    });
    return zuordnung;
}

function importZuordnungZeigen(art, gelesen) {
    const beschreibung = importArten.find(a => a.art === art);
    const optionen = ['<option value="">— nicht übernehmen —</option>'].concat(
        gelesen.kopf.map((name, i) => `<option value="${escapeHtml(String(i))}">${escapeHtml(name || `Spalte ${i + 1}`)}</option>`));
    const liste = optionen.join('');
    const ziel = document.getElementById('import-zuordnung');
    ziel.innerHTML = beschreibung.felder.map(feld => `
        <div class="form-group">
            <label for="import-feld-${escapeHtml(feld.schluessel)}">${escapeHtml(feld.titel)}${feld.pflicht ? ' <span class="pflicht-marke" title="Pflichtfeld">*</span>' : ''}</label>
            <select id="import-feld-${escapeHtml(feld.schluessel)}" data-feld="${escapeHtml(feld.schluessel)}" title="${escapeHtml(feld.hinweis)}">${liste}</select>
        </div>`).join('');
    for (const [feld, index] of Object.entries(gelesen.zuordnung)) {
        const auswahl = ziel.querySelector(`select[data-feld="${feld}"]`);
        if (auswahl) auswahl.value = String(index);
    }
    document.getElementById('import-gelesen').textContent =
        `${gelesen.zeilen} Zeilen gelesen. Ordnen Sie jedem Feld die passende Spalte Ihrer Tabelle zu; ` +
        'Felder mit * brauchen eine Spalte.';
    const html = '<thead><tr class="tabellen-kopfzeile">' +
        gelesen.kopf.map(k => `<th class="zelle">${escapeHtml(k)}</th>`).join('') + '</tr></thead>';
    const rows = gelesen.beispiel.map(z =>
        '<tr>' + z.map(w => `<td class="zelle">${escapeHtml(w)}</td>`).join('') + '</tr>').join('');
    document.getElementById('import-beispiel').innerHTML = html + `<tbody>${rows}</tbody>`;
}

function importBerichtZeigen(bericht) {
    const fehler = bericht.fehler || [];
    const hinweise = bericht.hinweise || [];
    const angelegt = angelegtText(bericht.angelegt);
    document.getElementById('import-zusammenfassung').textContent = fehler.length
        ? `${bericht.fehlerfrei} von ${anzahlText(bericht.zeilen, 'Zeile', 'Zeilen')} in Ordnung, ` +
          `${anzahlText(fehler.length, 'Zeile hat', 'Zeilen haben')} Fehler. ` +
          'Korrigieren Sie die Tabelle und wählen Sie sie neu, oder ändern Sie die Zuordnung. Übernommen wird erst, wenn alles stimmt.'
        : `${bericht.zeilen === 1 ? 'Die Zeile ist' : `Alle ${bericht.zeilen} Zeilen sind`} in Ordnung (${angelegt || 'nichts Neues'}). ` +
          'Mit „Daten importieren“ übernehmen Sie sie in einem Zug.';
    const zeilen = fehler.map(f => ({...f, art: 'Fehler'})).concat(hinweise.map(h => ({...h, art: 'Hinweis'})))
        .sort((a, b) => a.zeile - b.zeile);
    document.getElementById('import-befunde').innerHTML = zeilen.length
        ? '<thead><tr class="tabellen-kopfzeile"><th class="zelle">Zeile</th><th class="zelle">Art</th><th class="zelle">Meldung</th></tr></thead><tbody>' +
          zeilen.map(z => `<tr><td class="zelle">${escapeHtml(String(z.zeile))}</td><td class="zelle${z.art === 'Fehler' ? ' import-befund-fehler' : ''}">${escapeHtml(z.art)}</td><td class="zelle">${escapeHtml(z.meldung)}</td></tr>`).join('') +
          '</tbody>'
        : '';
    document.getElementById('import-weiter').disabled = fehler.length > 0 || !bericht.zeilen;
}

async function importWeiter() {
    const art = document.getElementById('import-art').value;
    const knopf = document.getElementById('import-weiter');
    knopf.disabled = true;
    try {
        if (!document.getElementById('import-schritt-datei').hidden) {
            const datei = document.getElementById('import-datei').files[0];
            if (!datei) {
                showError('Bitte wählen Sie zuerst Ihre Tabelle aus.');
                knopf.disabled = false;
                return;
            }
            const daten = new FormData();
            daten.append('datei', datei);
            const res = await fetch(`/api/import/${art}/lesen`, { method: 'POST', body: daten });
            if (!res.ok) throw await serverFehler(res);
            importStand = { art, gelesen: await res.json() };
            importZuordnungZeigen(art, importStand.gelesen);
            importSchritt('zuordnung');
            return;
        }
        const auftrag = { kennung: importStand.gelesen.kennung, zuordnung: importZuordnungLesen() };
        if (!document.getElementById('import-schritt-zuordnung').hidden) {
            const res = await fetch(`/api/import/${art}/pruefen`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(auftrag) });
            if (!res.ok) throw await serverFehler(res);
            importSchritt('ergebnis');
            importBerichtZeigen(await res.json());
            return;
        }
        const res = await fetch(`/api/import/${art}/uebernehmen`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(auftrag) });
        const bericht = await res.json();
        if (!res.ok || !bericht.uebernommen) {
            if (bericht.fehler) {
                importBerichtZeigen(bericht);
                return;
            }
            throw await serverFehler(res);
        }
        showSuccess(`Importiert: ${angelegtText(bericht.angelegt)}.`);
        schliesseImport();
        importNachladen();
    } catch (e) {
        showError(meldungZu(e, 'Der Import ist abgebrochen. Es wurde nichts übernommen.'));
        knopf.disabled = false;
    }
}
window.importWeiter = importWeiter;

function importNachladen() {
    fetchProperties();
    fetchAllApartments();
    fetchTenants();
    fetchProviders();
    fetchInvoices();
    fetchMeters();
    fetchReadings();
    fetchPayments();
    fetchBillingSuggestions();
}

// --- Rechnungen als Tabelle (NK-161) -----------------------------------------

const RT_SPALTEN = ['kostenart', 'betrag', 'von', 'bis', 'rechnungsdatum', 'rechnungsnummer', 'anbieter', 'wohnung'];

function rtDatum(tag, monat, jahr) {
    return `${String(tag).padStart(2, '0')}.${String(monat).padStart(2, '0')}.${jahr}`;
}

async function oeffneRechnungstabelle() {
    await Promise.all([fetchCategories(), fetchProviders(), fetchAllApartments()]);
    const auswahl = document.getElementById('rt-immobilie');
    auswahl.innerHTML = properties.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
    if (!properties.length) {
        showError('Legen Sie zuerst eine Immobilie an.');
        return;
    }
    document.getElementById('rt-kostenarten').innerHTML = categories.map(k =>
        `<option value="${escapeHtml(k.name)}"></option>`).join('');
    document.getElementById('rt-anbieter').innerHTML = providers.map(a =>
        `<option value="${escapeHtml(a.name)}"></option>`).join('');
    const jahr = document.getElementById('rt-jahr');
    if (!jahr.value) jahr.value = new Date().getFullYear() - 1;
    document.getElementById('rt-zeilen').innerHTML = '';
    document.getElementById('rt-meldung').textContent = '';
    rtImmobilieGewaehlt();
    rtZeilenAnlegen(10);
    document.getElementById('rechnungstabelle-modal').classList.add('active');
    const erstes = document.querySelector('#rt-zeilen input');
    if (erstes) erstes.focus();
}
window.oeffneRechnungstabelle = oeffneRechnungstabelle;

function schliesseRechnungstabelle() {
    // Die Rückfrage bei ungespeicherten Zeilen stellt die Dialogbedienung (NK-162).
    document.getElementById('rechnungstabelle-modal').classList.remove('active');
}
window.schliesseRechnungstabelle = schliesseRechnungstabelle;

function rtImmobilieGewaehlt() {
    const haus = Number(document.getElementById('rt-immobilie').value);
    document.getElementById('rt-wohnungen').innerHTML = allApartments
        .filter(a => a.property_id === haus)
        .map(a => `<option value="${escapeHtml(a.name)}"></option>`).join('');
}
window.rtImmobilieGewaehlt = rtImmobilieGewaehlt;

function rtJahrGewaehlt() {
    // Leere Zeiträume der neuen Jahreszahl anpassen; getippte bleiben.
    const jahr = document.getElementById('rt-jahr').value;
    document.querySelectorAll('#rt-zeilen tr').forEach(zeile => {
        const von = zeile.querySelector('[data-spalte="von"]');
        const bis = zeile.querySelector('[data-spalte="bis"]');
        if (von.dataset.vorgabe === '1') von.value = rtDatum(1, 1, jahr);
        if (bis.dataset.vorgabe === '1') bis.value = rtDatum(31, 12, jahr);
    });
}
window.rtJahrGewaehlt = rtJahrGewaehlt;

function rtZeilenAnlegen(anzahl) {
    const jahr = document.getElementById('rt-jahr').value;
    const rumpf = document.getElementById('rt-zeilen');
    const listen = { kostenart: 'rt-kostenarten', anbieter: 'rt-anbieter', wohnung: 'rt-wohnungen' };
    const namen = { kostenart: 'Kostenart', betrag: 'Betrag', von: 'Von', bis: 'Bis',
                    rechnungsdatum: 'Rechnungsdatum', rechnungsnummer: 'Nummer',
                    anbieter: 'Anbieter', wohnung: 'Nur Wohnung' };
    for (let i = 0; i < anzahl; i++) {
        const zeile = document.createElement('tr');
        for (const spalte of RT_SPALTEN) {
            const zelle = document.createElement('td');
            const feld = document.createElement('input');
            feld.type = 'text';
            feld.className = `rt-${spalte}`;
            feld.dataset.spalte = spalte;
            feld.autocomplete = 'off';
            feld.setAttribute('aria-label', namen[spalte]);
            if (listen[spalte]) feld.setAttribute('list', listen[spalte]);
            if (spalte === 'betrag') feld.inputMode = 'decimal';
            if (spalte === 'von' || spalte === 'bis') {
                feld.value = spalte === 'von' ? rtDatum(1, 1, jahr) : rtDatum(31, 12, jahr);
                feld.dataset.vorgabe = '1';
            }
            zelle.appendChild(feld);
            zeile.appendChild(zelle);
        }
        const status = document.createElement('td');
        status.className = 'rt-status';
        zeile.appendChild(status);
        rumpf.appendChild(zeile);
    }
}
window.rtZeilenAnlegen = rtZeilenAnlegen;

// Tastatur wie in Excel: Enter und Pfeil runter in dieselbe Spalte der
// nächsten Zeile (am Ende kommt eine neue dazu), Pfeil hoch zurück.
document.addEventListener('keydown', ereignis => {
    const feld = ereignis.target;
    if (!(feld instanceof HTMLInputElement) || !feld.closest('#rt-zeilen')) return;
    if (feld.dataset.spalte === 'von' || feld.dataset.spalte === 'bis') feld.dataset.vorgabe = '';
    const runter = ereignis.key === 'Enter' || ereignis.key === 'ArrowDown';
    const hoch = ereignis.key === 'ArrowUp';
    if (!runter && !hoch) return;
    ereignis.preventDefault();
    const zeile = feld.closest('tr');
    let ziel = hoch ? zeile.previousElementSibling : zeile.nextElementSibling;
    if (!ziel && runter) {
        rtZeilenAnlegen(1);
        ziel = zeile.nextElementSibling;
    }
    if (ziel) ziel.querySelector(`[data-spalte="${feld.dataset.spalte}"]`).focus();
});

function rtZeilenLesen() {
    const haus = document.getElementById('rt-immobilie');
    const name = haus.options[haus.selectedIndex] ? haus.options[haus.selectedIndex].text : '';
    return [...document.querySelectorAll('#rt-zeilen tr')].map(zeile => {
        const werte = {};
        zeile.querySelectorAll('input').forEach(feld => { werte[feld.dataset.spalte] = feld.value.trim(); });
        const leer = ['kostenart', 'betrag', 'rechnungsnummer', 'anbieter', 'rechnungsdatum', 'wohnung']
            .every(s => !werte[s]);
        // Eine Zeile nur mit dem vorbelegten Zeitraum ist leer.
        return leer ? {} : { immobilie: name, ...werte };
    });
}

async function rtSenden(speichern) {
    const zeilen = rtZeilenLesen();
    const meldung = document.getElementById('rt-meldung');
    if (!zeilen.some(z => Object.keys(z).length)) {
        showError('Die Tabelle ist leer. Tragen Sie mindestens eine Rechnung ein.');
        return;
    }
    try {
        const res = await fetch('/api/import/rechnungen/tabelle', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ zeilen, uebernehmen: speichern }) });
        const bericht = await res.json();
        if (!bericht.fehler) throw await serverFehler(res);
        const zeilenElemente = [...document.querySelectorAll('#rt-zeilen tr')];
        zeilenElemente.forEach((zeile, i) => {
            const status = zeile.querySelector('.rt-status');
            const fehler = bericht.fehler.filter(f => f.zeile === i + 1);
            const hinweise = (bericht.hinweise || []).filter(h => h.zeile === i + 1);
            zeile.classList.toggle('zeile-fehler', fehler.length > 0);
            status.className = 'rt-status' + (fehler.length ? ' fehler' : '');
            status.textContent = fehler.concat(hinweise).map(f => f.meldung).join(' ');
            if (!fehler.length && Object.keys(zeilen[i]).length) {
                status.classList.add('ok');
                if (!hinweise.length) status.textContent = 'in Ordnung';
            }
        });
        if (bericht.fehler.length) {
            meldung.textContent = `${anzahlText(bericht.fehler.length, 'Zeile hat', 'Zeilen haben')} Fehler (rot markiert). Gespeichert wird erst, wenn alle stimmen.`;
            return;
        }
        if (!speichern) {
            meldung.textContent = `${anzahlText(bericht.zeilen, 'Rechnung ist', 'Rechnungen sind')} in Ordnung.`;
            return;
        }
        showSuccess(`${anzahlText(bericht.zeilen, 'Rechnung', 'Rechnungen')} gespeichert.`);
        document.getElementById('rechnungstabelle-modal').classList.remove('active');
        importNachladen();
    } catch (e) {
        showError(meldungZu(e, 'Die Rechnungen konnten nicht gespeichert werden.'));
    }
}
window.rtSenden = rtSenden;

// --- Jahresabrechnungs-Assistent (NK-160) ------------------------------------
// Fünf Schritte: Jahr und Immobilie -> Rechnungen (mit Vorjahr) ->
// Ablesungen -> Vorschau aller Mieter -> Anschreiben, Festsetzen, Frist.
// Der Stand kommt aus /api/jahresabrechnung, gerechnet wird über
// /api/billing/generate, festgesetzt über /api/billing/finalize.

let jahrStand = null;
let jahrAktuell = 1;
let jahrVorschau = {};

const euroText = betrag => Number(betrag || 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
const datumText = iso => iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('de-DE') : '—';

async function oeffneJahrAssistent() {
    await fetchProperties();
    if (!properties.length) {
        showError('Legen Sie zuerst eine Immobilie an.');
        return;
    }
    const auswahl = document.getElementById('jahr-immobilie');
    const echte = properties.filter(p => !p.ist_beispiel);
    auswahl.innerHTML = (echte.length ? echte : properties).concat(echte.length ? properties.filter(p => p.ist_beispiel) : [])
        .map(p => `<option value="${escapeHtml(String(p.id))}">${escapeHtml(p.name)}</option>`).join('');
    const jahr = document.getElementById('jahr-jahr');
    jahr.max = new Date().getFullYear();
    jahr.value = new Date().getFullYear() - 1;
    jahrStand = null;
    jahrVorschau = {};
    jahrAktuell = 1;
    jahrZeigen();
    document.getElementById('jahr-modal').classList.add('active');
}
window.oeffneJahrAssistent = oeffneJahrAssistent;

function schliesseJahrAssistent() {
    document.getElementById('jahr-modal').classList.remove('active');
    fetchBillingHistory();
    fetchBillingSuggestions();
}
window.schliesseJahrAssistent = schliesseJahrAssistent;

function jahrZeigen() {
    document.querySelectorAll('[data-jahr-schritt]').forEach(abschnitt => {
        abschnitt.hidden = Number(abschnitt.dataset.jahrSchritt) !== jahrAktuell;
    });
    document.querySelectorAll('#jahr-schritte li').forEach(punkt => {
        const nummer = Number(punkt.dataset.schritt);
        punkt.classList.toggle('aktuell', nummer === jahrAktuell);
        punkt.classList.toggle('erledigt', nummer < jahrAktuell);
        if (nummer === jahrAktuell) punkt.setAttribute('aria-current', 'step');
        else punkt.removeAttribute('aria-current');
    });
    document.getElementById('jahr-zurueck').disabled = jahrAktuell === 1;
    document.getElementById('jahr-weiter').hidden = jahrAktuell === 5;
}

async function jahrSchritt(richtung) {
    const knopf = document.getElementById('jahr-weiter');
    knopf.disabled = true;
    try {
        if (richtung > 0 && jahrAktuell === 1 && !(await jahrNeuLaden())) return;
        if (richtung > 0 && jahrAktuell === 3) await jahrVorschauLaden();
        jahrAktuell = Math.min(5, Math.max(1, jahrAktuell + richtung));
        jahrZeigen();
    } finally {
        knopf.disabled = false;
    }
}
window.jahrSchritt = jahrSchritt;

async function jahrNeuLaden() {
    const haus = document.getElementById('jahr-immobilie').value;
    const jahr = document.getElementById('jahr-jahr').value;
    try {
        const res = await fetch(`/api/jahresabrechnung?property_id=${encodeURIComponent(haus)}&jahr=${encodeURIComponent(jahr)}`);
        if (!res.ok) throw await serverFehler(res);
        jahrStand = await res.json();
    } catch (e) {
        showError(meldungZu(e, 'Der Stand des Jahres ließ sich nicht laden.'));
        return false;
    }
    jahrKostenartenZeigen();
    jahrAblesungenZeigen();
    jahrFristZeigen();
    return true;
}
window.jahrNeuLaden = jahrNeuLaden;

function jahrKostenartenZeigen() {
    const hinweise = {
        erfasst: k => `${anzahlText(k.anzahl, 'Rechnung', 'Rechnungen')} erfasst`,
        fehlt: k => `Im Vorjahr ${euroText(k.summe_vorjahr)} — fehlt eine Rechnung?`,
        offen: () => 'Keine Rechnung erfasst. Fällt die Kostenart bei Ihnen an?',
    };
    const rows = jahrStand.kostenarten.map(k => {
        const diesesJahr = k.anzahl ? euroText(k.summe) : '—';
        const vorjahr = k.summe_vorjahr === null ? '—' : euroText(k.summe_vorjahr);
        const symbol = k.zustand === 'erfasst' ? 'ph-check-circle' : 'ph-warning-circle';
        return `<tr class="jahr-${escapeHtml(k.zustand)}">
        <td class="zelle"><i class="ph ${escapeHtml(symbol)}" aria-hidden="true"></i> ${escapeHtml(k.name)}</td>
        <td class="zelle">${escapeHtml(diesesJahr)}</td>
        <td class="zelle">${escapeHtml(vorjahr)}</td>
        <td class="zelle">${escapeHtml(hinweise[k.zustand](k))}</td></tr>`;
    }).join('');
    document.getElementById('jahr-kostenarten').innerHTML =
        `<thead><tr class="tabellen-kopfzeile"><th class="zelle">Kostenart</th><th class="zelle">${escapeHtml(String(jahrStand.jahr))}</th>` +
        `<th class="zelle">Vorjahr</th><th class="zelle">Hinweis</th></tr></thead><tbody>${rows}</tbody>`;
}

function jahrAblesungenZeigen() {
    const text = document.getElementById('jahr-ablesungen-text');
    const tabelle = document.getElementById('jahr-ablesungen');
    if (!jahrStand.ablesungen.length) {
        text.textContent = 'Dieses Haus hat keine Zähler: die Kosten werden nach Fläche oder Personen verteilt. Hier ist nichts zu tun.';
        tabelle.innerHTML = '';
        return;
    }
    const offen = jahrStand.ablesungen.filter(z => !z.stichtag_ok || z.wechsel_fehlen.length).length;
    text.textContent = offen
        ? `Bei ${anzahlText(offen, 'Zähler fehlt', 'Zählern fehlt')} ein Stand zum Jahresende oder zu einem Mieterwechsel.`
        : 'Alle Zähler sind zum Jahresende und zu jedem Mieterwechsel abgelesen.';
    const zeilen = jahrStand.ablesungen.map(z => {
        const fehlt = [];
        if (!z.stichtag_ok) fehlt.push(`Stand zum ${datumText(jahrStand.bis)}`);
        z.wechsel_fehlen.forEach(tag => fehlt.push(`Zwischenablesung zum ${datumText(tag)}`));
        const status = fehlt.length ? fehlt.join(', ') : 'in Ordnung';
        const knopf = fehlt.length
            ? '<button type="button" class="btn-secondary btn-klein" onclick="openAddReadingModal(' + Number(z.id) + ')">Ablesung erfassen</button>'
            : '';
        return `<tr><td class="zelle">${escapeHtml(z.nummer)}</td><td class="zelle">${escapeHtml(z.kostenart)}</td>` +
            `<td class="zelle">${escapeHtml(z.wohnung)}</td><td class="zelle">${escapeHtml(datumText(z.letzte))}</td>` +
            `<td class="zelle">${escapeHtml(status)}</td>` +
            `<td class="zelle">${knopf}</td></tr>`;
    });
    const rows = zeilen.join('');
    tabelle.innerHTML = '<thead><tr class="tabellen-kopfzeile"><th class="zelle">Zähler</th><th class="zelle">Kostenart</th>' +
        '<th class="zelle">Wohnung</th><th class="zelle">Letzte Ablesung</th><th class="zelle">Es fehlt</th><th class="zelle"></th></tr></thead>' +
        `<tbody>${rows}</tbody>`;
}

function jahrFristZeigen() {
    const ende = datumText(jahrStand.frist_ende);
    document.getElementById('jahr-frist').textContent = jahrStand.frist_ueberschritten
        ? `Die Frist für ${jahrStand.jahr} endete am ${ende}. Eine Nachzahlung können Sie nicht mehr verlangen; ein Guthaben müssen Sie trotzdem auszahlen.`
        : `Die Abrechnungen für ${jahrStand.jahr} müssen bis zum ${ende} bei Ihren Mietern sein (noch ${anzahlText(jahrStand.frist_tage, 'Tag', 'Tage')}, § 556 Abs. 3 BGB).`;
}

async function jahrVorschauLaden() {
    const ziel = document.getElementById('jahr-vorschau');
    ziel.innerHTML = '<p class="karten-text">Die Vorschau wird gerechnet …</p>';
    jahrVorschau = {};
    const karten = [];
    for (const m of jahrStand.mieter) {
        const mieterKopf = `<strong>${escapeHtml(m.name)}</strong> · ${escapeHtml(m.wohnung)} · ${escapeHtml(datumText(m.von))} – ${escapeHtml(datumText(m.bis))}`;
        if (m.abrechnung_id) {
            karten.push(`<div class="jahr-mieter"><div>${mieterKopf}</div><p class="karten-text">Schon abgerechnet.</p></div>`);
            continue;
        }
        try {
            const res = await fetch('/api/billing/generate', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tenant_id: m.id, start_date: m.von, end_date: m.bis }) });
            if (!res.ok) throw await serverFehler(res);
            const daten = await res.json();
            jahrVorschau[m.id] = daten;
            const positionen = daten.line_items.map(zeile => {
                const weg = (zeile.rechenweg || []).join(' · ');
                const rechenwegHtml = weg ? '<br><span class="text-muted">' + escapeHtml(weg) + '</span>' : '';
                return `<li><strong>${escapeHtml(zeile.category)}</strong>: ${escapeHtml(euroText(zeile.tenant_cost))}${rechenwegHtml}</li>`;
            }).join('');
            const warnungen = (daten.warnings || []).map(w => `<li>${escapeHtml(typeof w === 'string' ? w : (w.text || w.message || ''))}</li>`).join('');
            const warnListe = warnungen ? '<ul class="jahr-warnungen">' + warnungen + '</ul>' : '';
            const erklaerungHtml = mieterErklaerungHtml(daten);
            karten.push(`<div class="jahr-mieter">
                <label class="haken-zeile"><input type="checkbox" class="jahr-auswahl" data-mieter="${Number(m.id)}" checked> ${mieterKopf}</label>
                <p class="karten-text">Kosten ${escapeHtml(euroText(daten.total_amount))} · Vorauszahlungen ${escapeHtml(euroText(daten.prepaid_amount))}</p>
                ${erklaerungHtml}
                ${warnListe}
                <details><summary>Rechenweg je Position</summary><ul class="jahr-positionen">${positionen}</ul></details>
            </div>`);
        } catch (e) {
            karten.push(`<div class="jahr-mieter"><div>${mieterKopf}</div><p class="import-befund-fehler">${escapeHtml(meldungZu(e, 'Diese Abrechnung ließ sich nicht rechnen.'))}</p></div>`);
        }
    }
    ziel.innerHTML = karten.length ? karten.join('') : '<p class="karten-text">In diesem Jahr hat hier niemand gewohnt.</p>';
}

function jahrAnschreiben() {
    if (jahrStand) openAnschreibenModal(jahrStand.property_id);
}
window.jahrAnschreiben = jahrAnschreiben;

async function jahrFestsetzen() {
    const gewaehlt = [...document.querySelectorAll('.jahr-auswahl:checked')].map(h => Number(h.dataset.mieter));
    const ergebnis = document.getElementById('jahr-ergebnis');
    if (!gewaehlt.length) {
        showError('Es ist keine Abrechnung ausgewählt (Schritt 4).');
        return;
    }
    const knopf = document.getElementById('jahr-festsetzen');
    knopf.disabled = true;
    const fehler = [];
    try {
        for (const id of gewaehlt) {
            const m = jahrStand.mieter.find(x => x.id === id);
            for (const detailliert of [true, false]) {
                const res = await fetch('/api/billing/finalize', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tenant_id: id, start_date: m.von, end_date: m.bis, detailed: detailliert }) });
                if (!res.ok) {
                    fehler.push(`${m.name}: ${meldungZu(await serverFehler(res), 'nicht erstellt')}`);
                    break;
                }
            }
        }
        await jahrNeuLaden();
        const liste = jahrStand.mieter.filter(m => m.abrechnung_id).map(m => {
            const pdfLinks = (m.detailliert ? '<a href="' + dateiAdresse('abrechnung-detailliert', m.abrechnung_id) + '" target="_blank">PDF ansehen (detailliert)</a>' : '') +
                (m.einfach ? ' · <a href="' + dateiAdresse('abrechnung', m.abrechnung_id) + '" target="_blank">PDF ansehen (einfach)</a>' : '');
            const zustellung = m.zugestellt_am
                ? 'zugestellt am ' + escapeHtml(datumText(m.zugestellt_am))
                : '<button type="button" class="btn-tint btn-klein" onclick="openReportDetails(' + Number(m.abrechnung_id) + ')">Zustellung melden</button>';
            return `<li><strong>${escapeHtml(m.name)}</strong> (${escapeHtml(m.wohnung)}) ${pdfLinks} · ${zustellung}</li>`;
        }).join('');
        ergebnis.innerHTML = `<h4 class="abstand-unten-klein">Erstellte Abrechnungen</h4><ul class="jahr-ergebnis-liste">${liste}</ul>` +
            (fehler.length ? `<p class="import-befund-fehler">${escapeHtml(fehler.join(' '))}</p>` : '') +
            '<p class="karten-text">Schicken Sie die Abrechnungen Ihren Mietern und melden Sie danach die Zustellung: ' +
            'dann behält NebenkostenFix die Einwendungsfrist im Blick.</p>';
        if (!fehler.length) showSuccess(`${anzahlText(gewaehlt.length, 'Abrechnung', 'Abrechnungen')} erstellt.`);
        fetchBillingHistory();
    } finally {
        knopf.disabled = false;
    }
}
window.jahrFestsetzen = jahrFestsetzen;

// --- Anschreiben-Vorlage des Objekts (NK-124, Backend seit NK-064) ---

let anschreibenPropertyId = null;
let anschreibenIstVorgabe = true;

async function openAnschreibenModal(propertyId) {
    if (!propertyId) return;
    anschreibenPropertyId = propertyId;
    try {
        const res = await fetch(`/api/properties/${propertyId}/anschreiben`);
        if (!res.ok) throw await serverFehler(res);
        const vorlage = await res.json();
        document.getElementById('anschreiben-text').value = vorlage.text || '';
        document.getElementById('anschreiben-status').textContent = vorlage.ist_vorgabe
            ? 'Sie sehen den Vorschlagstext der Software. Speichern Sie eigenen Text, um ihn zu überschreiben.'
            : 'Dies ist der eigene Text dieses Objekts.';
        anschreibenIstVorgabe = !!vorlage.ist_vorgabe;
        const platzhalter = document.getElementById('anschreiben-platzhalter');
        platzhalter.textContent = (vorlage.platzhalter || []).map(p => `{${p}}`).join('  ');
        document.getElementById('anschreiben-modal').classList.add('active');
    } catch (e) {
        showError(meldungZu(e, 'Die Anschreiben-Vorlage konnte nicht geladen werden.'));
    }
}

async function saveAnschreibenVorlage() {
    const text = document.getElementById('anschreiben-text').value;
    if (!text.trim()) { showError('Die Vorlage braucht einen Text. Wer nichts sagen will, kehr zum Vorschlagstext zurück.'); return; }
    try {
        const res = await fetch(`/api/properties/${anschreibenPropertyId}/anschreiben`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ text })
        });
        if (!res.ok) throw await serverFehler(res);
        showSuccess('Anschreiben-Vorlage gespeichert.');
        document.getElementById('anschreiben-modal').classList.remove('active');
    } catch (e) {
        showError(meldungZu(e, 'Die Anschreiben-Vorlage konnte nicht gespeichert werden.'));
    }
}

async function loescheAnschreibenVorlage() {
    if (anschreibenIstVorgabe) { showSuccess('Es steht bereits der Vorschlagstext der Software.'); return; }
    try {
        const res = await fetch(`/api/properties/${anschreibenPropertyId}/anschreiben`, { method: 'DELETE' });
        if (!res.ok) throw await serverFehler(res);
        const vorlage = await res.json();
        document.getElementById('anschreiben-text').value = vorlage.text || '';
        document.getElementById('anschreiben-status').textContent = 'Sie sehen den Vorschlagstext der Software. Speichern Sie eigenen Text, um ihn zu überschreiben.';
        anschreibenIstVorgabe = true;
        showSuccess('Eigener Text gelöscht — wieder der Vorschlagstext.');
    } catch (e) {
        showError(meldungZu(e, 'Die Anschreiben-Vorlage konnte nicht gelöscht werden.'));
    }
}

// --- Billing Logic ---
async function fetchBillingSuggestions() {
    try {
        const res = await fetch('/api/billing/suggestions');
        const suggestions = await res.json();
        
        const container = document.getElementById('billing-suggestions-container');
        if (!container) return;
        
        container.innerHTML = '';
        
        if (suggestions.length === 0) {
            // K4: „Keine Abrechnungen fällig“ ist ein vollwertiger Leerzustand.
            // NK-154: ohne Mieter kein grüner Haken -- „nichts fällig“ läse
            // ein Anfänger als „alles erledigt“. Der Knopf nennt den nächsten
            // Schritt.
            let mieterDa = tenants.length > 0;
            if (!mieterDa) {
                try {
                    const antwort = await fetch('/api/tenants');
                    mieterDa = antwort.ok && (await antwort.json()).length > 0;
                } catch (e) {
                    console.error('Mieter nicht ladbar', e);
                }
            }
            container.innerHTML = mieterDa ? leerzustand({
                icon: 'ph-check-circle',
                titel: 'Keine Abrechnung fällig',
                text: 'Für jeden Mieter ist die letzte Abrechnung erstellt, oder es fehlen noch ' +
                    'Rechnungen für den nächsten Zeitraum. Eine Abrechnung für einen frei gewählten ' +
                    'Zeitraum geht jederzeit.',
                aktion: { label: 'Abrechnung frei erstellen', fn: 'openFreieAbrechnung()', icon: 'ph-files' },
            }) : leerzustand({
                icon: 'ph-users',
                titel: 'Noch keine Mieter',
                text: 'Abgerechnet wird je Mieter. Legen Sie zuerst Immobilie, Wohnung und Mieter an ' +
                    '— die Übersicht zeigt Schritt für Schritt, was noch fehlt.',
                aktion: { label: 'Übersicht öffnen', fn: "wechsleZuTab('dashboard')", icon: 'ph-squares-four' },
            });
            return;
        }
        
        suggestions.forEach(s => {
            const card = document.createElement('div');
            // NK-159: auf schmalen Fenstern rutschen die Knöpfe unter den Text
            // (Fund des Rundgangs mit der Beispielabrechnung, 390 px).
            card.className = 'dashboard-card historie-zeile';
            
            const startFmt = new Date(s.suggested_start).toLocaleDateString('de-DE');
            const endFmt = new Date(s.suggested_end).toLocaleDateString('de-DE');
            
            card.innerHTML = `
                <div>
                    <h3 style="margin:0; font-size: 1.1rem;">${escapeHtml(s.tenant_name)} <span style="font-size: 0.9rem; color: var(--text-muted); font-weight: normal;">(${escapeHtml(s.apartment_name)})</span></h3>
                    <p style="margin: 8px 0 0 0; color: var(--text-muted);">
                        Es liegen unberechnete Kosten vor.
                    </p>
                </div>
                <div>
                    <button class="btn-primary" type="button">Offene Kosten abrechnen</button>
                </div>
            `;
            // Kein JSON im onclick-Attribut: ein Mietername mit Apostroph
            // brach dort aus dem Attribut aus (NK-149, F-78).
            card.querySelector('button').addEventListener(
                'click', () => openBillingSelectionModal(s));
            container.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to load billing suggestions', e);
    }
}

async function fetchBillingHistory() {
    try {
        const res = await fetch('/api/billing/reports');
        if (!res.ok) throw await serverFehler(res);
        const history = await res.json();
        anzahlAbrechnungen = history.length;
        abrechnungsHistorie = history;
        zeigeErsteSchritte();
        
        const container = document.getElementById('billing-history-container');
        if (!container) return;
        
        container.innerHTML = '';
        
        if (history.length === 0) {
            container.innerHTML = leerzustand({
                icon: 'ph-file-text',
                titel: 'Noch keine Abrechnung erstellt',
                text: 'Für eine Abrechnung braucht es Mieter mit Kostenprofil und erfasste Rechnungen des Zeitraums. Die Vorschläge oben zeigen, was bereit ist.',
                aktion: { label: 'Abrechnung frei erstellen', fn: 'openFreieAbrechnung()', icon: 'ph-files' },
            });
            return;
        }
        
        history.forEach(r => {
            const card = document.createElement('div');
            // NK-159: auf schmalen Fenstern rutschen die Knöpfe unter den Text
            // (Fund des Rundgangs mit der Beispielabrechnung, 390 px).
            card.className = 'dashboard-card historie-zeile';
            
            const startFmt = new Date(r.start_date).toLocaleDateString('de-DE');
            const endFmt = new Date(r.end_date).toLocaleDateString('de-DE');
            // Der Server schickt das Datum schon deutsch formatiert (zeit.als_ortszeit);
            // new Date('25.09.2026') ergäbe „Invalid Date“ (Fund im Beispiel, NK-159).
            const createdFmt = r.created_at || '';
            
            // Build PDF link buttons dynamically
            let pdfButtons = '';
            if (r.document_path) {
                pdfButtons += `<a href="${dateiAdresse('abrechnung', r.id)}" class="btn-secondary" target="_blank" style="text-decoration: none; display: flex; align-items: center; gap: 6px; font-size: 0.9rem;" title="Einfache PDF ansehen">
                    PDF ansehen (einfach)
                </a>`;
            } else {
                pdfButtons += `<button class="btn-secondary" onclick="generateMissingPdf(${r.tenant_id}, '${r.start_date}', '${r.end_date}', false, this)" style="font-size: 0.9rem; border-style: dashed;" title="Einfache PDF nachträglich erstellen">
                    PDF erstellen (einfach)
                </button>`;
            }
            if (r.document_path_detailed) {
                pdfButtons += `<a href="${dateiAdresse('abrechnung-detailliert', r.id)}" class="btn-secondary" target="_blank" style="text-decoration: none; display: flex; align-items: center; gap: 6px; background: rgba(79, 70, 229, 0.1); color: var(--primary); border: 1px solid rgba(79, 70, 229, 0.3); font-size: 0.9rem;" title="Detaillierte PDF ansehen">
                    PDF ansehen (detailliert)
                </a>`;
            } else {
                pdfButtons += `<button class="btn-secondary" onclick="generateMissingPdf(${r.tenant_id}, '${r.start_date}', '${r.end_date}', true, this)" style="font-size: 0.9rem; background: rgba(79, 70, 229, 0.05); color: var(--primary); border: 1px dashed rgba(79, 70, 229, 0.3);" title="Detaillierte PDF nachträglich erstellen">
                    PDF erstellen (detailliert)
                </button>`;
            }
            
            card.innerHTML = `
                <div>
                    <h3 style="margin:0; font-size: 1.1rem;">${escapeHtml(r.tenant_name)} <span style="font-size: 0.9rem; color: var(--text-muted); font-weight: normal;">(${escapeHtml(r.apartment_name)} - ${escapeHtml(r.property_name)})</span></h3>
                    <p style="margin: 8px 0 0 0; color: var(--text-muted);">
                        Zeitraum: ${startFmt} - ${endFmt} | Erstellt am: ${createdFmt}
                    </p>
                </div>
                <div class="historie-knoepfe">
                    <button class="btn-primary" onclick="openReportDetails(${r.id})" title="Einzelheiten und Belege dieser Abrechnung ansehen">
                        Abrechnung ansehen
                    </button>
                    ${pdfButtons}
                    <button class="btn-icon" onclick="deleteBillingReport(${r.id})" style="color: var(--danger-color);" title="Abrechnung löschen">
                        <i class="ph ph-trash"></i>
                    </button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to load billing history', e);
    }
}

async function deleteBillingReport(id) {
    if (!await frageLoeschen('Möchten Sie diese Abrechnung wirklich löschen? Die PDF-Datei und alle Historien-Einträge werden unwiderruflich entfernt.')) return;
    
    try {
        const res = await fetch(`/api/billing/reports/${id}`, { method: 'DELETE' });
        if (!res.ok) throw await serverFehler(res);
        fetchBillingHistory();
        fetchBillingSuggestions(); // Might unlock new suggestions
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Fehler beim Löschen der Abrechnung.'));
    }
}

async function generateMissingPdf(tenantId, startDate, endDate, isDetailed, btnElement) {
    const label = isDetailed ? 'Detaillierte' : 'Einfache';
    btnElement.disabled = true;
    btnElement.textContent = 'Generiert...';
    
    try {
        const res = await fetch('/api/billing/finalize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tenant_id: tenantId,
                start_date: startDate,
                end_date: endDate,
                detailed: isDetailed
            })
        });
        
        if (!res.ok) throw await serverFehler(res);
        
        showSuccess(`${label} PDF erfolgreich erstellt!`);
        fetchBillingHistory();
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Die PDF konnte nicht erstellt werden.'));
        btnElement.disabled = false;
        btnElement.textContent = `PDF ${isDetailed ? 'erstellen (detailliert)' : 'erstellen (einfach)'}`;
    }
}

// --- NK-124: Zustellung, Frist, Korrektur und Versionen im Detaildialog ---

function berichtZustellungsBlock(id, umschlag) {
    "Der Block zur Zustellung (R-FRIST-02): was gemeldet ist, oder der Weg dorthin."
    if (umschlag.zugestellt_am) {
        return `
            <div class="dashboard-card glass-panel" style="margin-bottom: 20px; padding: 16px;">
                <h4 style="margin: 0 0 8px 0; display: flex; align-items: center; gap: 8px;">
                    <i class="ph ph-check-circle" style="color: var(--success-color);"></i> Zustellung gemeldet
                </h4>
                <p style="margin: 0; color: var(--text-muted);">
                    Zugestellt am ${new Date(umschlag.zugestellt_am).toLocaleDateString('de-DE')}
                    · Einwendungsfrist des Mieters bis ${new Date(umschlag.einwendungsfrist_ende).toLocaleDateString('de-DE')}
                    · Nachforderungsfrist endete ${new Date(umschlag.frist_ende).toLocaleDateString('de-DE')}
                </p>
            </div>`;
    }
    return `
        <div class="dashboard-card glass-panel" style="margin-bottom: 20px; padding: 16px;">
            <h4 style="margin: 0 0 8px 0; display: flex; align-items: center; gap: 8px;">
                <i class="ph ph-clock-counter-clockwise"></i> Zustellung melden
            </h4>
            <p style="margin: 0 0 12px 0; color: var(--text-muted); font-size: 0.9rem;">
                Tragen Sie nach, wann die Abrechnung beim Mieter war — massgeblich
                ist der Zugang, nicht das Erstellungsdatum.
            </p>
            <div style="display: flex; gap: 12px; align-items: end; flex-wrap: wrap;">
                <div class="form-group" style="margin: 0;">
                    <label for="zustellung-datum-${id}">Zugestellt am</label>
                    <input type="date" id="zustellung-datum-${id}" value="${new Date().toISOString().split('T')[0]}">
                </div>
                <button class="btn-primary" onclick="zustellungMelden(${id})">Zustellung speichern</button>
            </div>
        </div>`;
}

async function zustellungMelden(id) {
    const datum = document.getElementById(`zustellung-datum-${id}`).value;
    if (!datum) { showError('Bitte ein Datum für die Zustellung angeben.'); return; }
    try {
        const res = await fetch(`/api/billing/reports/${id}/zustellung`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ zugestellt_am: datum })
        });
        if (!res.ok) throw await serverFehler(res);
        const antwort = await res.json();
        showSuccess(antwort.warnung ? `${antwort.message} ${antwort.warnung}` : antwort.message);
        await fetchBillingHistory();
        openReportDetails(id);
    } catch (e) {
        showError(meldungZu(e, 'Die Zustellung konnte nicht gespeichert werden.'));
    }
}

function berichtVersionenBlock(id, umschlag) {
    "Die Versionen der Abrechnung samt dem Weg zur Korrektur (R-DOC-02)."
    const versionen = umschlag.versionen || [];
    let liste = '';
    if (versionen.length > 0) {
        liste = `<p style="margin: 0 0 8px 0; color: var(--text-muted); font-size: 0.9rem;">`
            + versionen.map(v =>
                `Version ${v.nummer} · ${new Date(v.erstellt_am).toLocaleDateString('de-DE')}`
            ).join(' · ')
            + `</p>`;
    }
    return `
        <div class="dashboard-card glass-panel" style="margin-bottom: 20px; padding: 16px;">
            <h4 style="margin: 0 0 8px 0; display: flex; align-items: center; gap: 8px;">
                <i class="ph ph-clock"></i> Versionen
            </h4>
            ${liste}
            <p style="margin: 0 0 12px 0; color: var(--text-muted); font-size: 0.9rem;">
                Die Korrektur rechnet gegen die heutigen Daten, bleibt als neue
                Version stehen und erzeugt die PDFs neu.
            </p>
            <button class="btn-secondary" onclick="korrekturErstellen(${id})">
                <i class="ph ph-pencil-simple"></i> Korrektur erstellen
            </button>
        </div>`;
}

async function korrekturErstellen(id) {
    if (!await frage('Eine Korrektur rechnet diese Abrechnung gegen die aktuellen Daten neu und legt eine neue Version an. Fortfahren?', 'Erstellen')) return;
    try {
        const res = await fetch(`/api/billing/reports/${id}/korrektur`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({})
        });
        if (!res.ok) throw await serverFehler(res);
        const antwort = await res.json();
        showSuccess(antwort.message);
        await fetchBillingHistory();
        openReportDetails(id);
    } catch (e) {
        showError(meldungZu(e, 'Die Korrektur konnte nicht erstellt werden.'));
    }
}

async function openReportDetails(id) {
    try {
        const res = await fetch(`/api/billing/reports/${id}/details`);
        if (!res.ok) throw await serverFehler(res);
        const umschlag = await res.json();
        // NK-124: das Ergebnis steckt im Schnappschuss ("ergebnis"); beim
        // Altbestand ohne Version ist die Antwort selbst das Ergebnis.
        const data = umschlag.ergebnis || umschlag;
        // Der Schnappschuss hält Beträge als Text ("828.32", json_sicher),
        // damit sie exakt bleiben; .toFixed gibt es nur an Zahlen.
        const formatiereBetrag = w => Number(w || 0).toFixed(2).replace('.', ',');
        
        const modal = document.getElementById('report-details-modal');
        const body = document.getElementById('report-details-body');
        
        // NK-124: Zustellung, Frist und Versionen gehoeren an diesen Ort.
        // Der Vermieter sieht den Stand und meldet den Zugang nach.
        const zustellungsBlock = berichtZustellungsBlock(id, umschlag);
        const versionenBlock = berichtVersionenBlock(id, umschlag);
        
        let html = `
            <div style="margin-bottom: 24px;">
                <h3 style="margin: 0 0 8px 0; font-size: 1.25rem;">Details zur Abrechnung</h3>
                <p style="color: var(--text-muted); margin: 0;">Zeitraum: ${new Date(umschlag.start_date || data.start_date).toLocaleDateString('de-DE')} - ${new Date(umschlag.end_date || data.end_date).toLocaleDateString('de-DE')}</p>
                ${umschlag.version ? `<p style="color: var(--text-muted); margin: 4px 0 0 0; font-size: 0.9rem;">Version ${umschlag.version} · erstellt mit Software ${escapeHtml(umschlag.software_version || '')}, Regelstand ${escapeHtml(umschlag.regel_version || '')}</p>` : ''}
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;">
                <a class="btn-secondary" href="/api/billing/reports/${id}/belege" download
                   title="Alle Belege dieser Abrechnung als ZIP für den Mieter (§ 556 Abs. 4 BGB)">
                    <i class="ph ph-file-zip"></i> Belege herunterladen
                </a>
                <a class="btn-secondary" href="/api/billing/reports/${id}/positionen.csv" download
                   title="Die Positionen als Tabelle für Excel oder LibreOffice">
                    <i class="ph ph-file-csv"></i> Positionen als CSV herunterladen
                </a>
            </div>
            ${zustellungsBlock}
            ${versionenBlock}
            <table class="data-table" style="width: 100%; border-collapse: collapse; text-align: left;">
                <thead>
                    <tr style="background-color: var(--bg-hover);">
                        <th style="padding: 12px 8px; font-weight: 600; font-size: 0.9rem;">Kostenart</th>
                        <th style="padding: 12px 8px; font-weight: 600; font-size: 0.9rem;">Rechnungszeitraum</th>
                        <th style="padding: 12px 8px; font-weight: 600; font-size: 0.9rem;">Umlage-Details</th>
                        <th style="padding: 12px 8px; font-weight: 600; font-size: 0.9rem; text-align: right;">Betrag (€)</th>
                        <th style="padding: 12px 8px; font-weight: 600; font-size: 0.9rem; text-align: center;">Belege</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        data.line_items.forEach(item => {
            let belegHtml = '-';
            if (item.doc_path && item.doc_name && item.invoice_id) {
                belegHtml = `<a href="${dateiAdresse('rechnung', item.invoice_id)}" target="_blank" style="color: var(--primary-color); text-decoration: underline;" title="${escapeHtml(item.doc_name)}">Beleg ansehen</a>`;
            }
            
            const hasSub = item.sub_items && item.sub_items.length > 0;
            
            let itemDesc = escapeHtml(item.description);
            if (!hasSub && item.meter_details) {
                const md = item.meter_details;
                if (item.billing_type === 'direkt' && md.tenant_meter && md.tenant_meter.is_interpolated) {
                    itemDesc = window.wrapInterpolated(itemDesc, true, md.tenant_meter);
                } else if (item.billing_type === 'nur_allgemein' && md.main_meter && md.main_meter.is_interpolated) {
                    itemDesc = window.wrapInterpolated(itemDesc, true, md.main_meter);
                }
            }
            
            html += `
                <tr style="border-bottom: ${hasSub ? 'none' : '1px solid var(--border-color)'};">
                    <td style="font-weight: 500; padding: 12px 8px;">${escapeHtml(item.category)}</td>
                    <td style="color: var(--text-muted); font-size: 0.9rem; white-space: nowrap; padding: 12px 8px;">${escapeHtml(item.period)}</td>
                    <td style="color: var(--text-muted); font-size: 0.875rem; padding: 12px 8px;">${hasSub ? '' : itemDesc}</td>
                    <td style="font-weight: 600; text-align: right; white-space: nowrap; padding: 12px 8px;">${formatiereBetrag(item.tenant_cost)} €</td>
                    <td style="text-align: center; padding: 12px 8px;">${belegHtml}</td>
                </tr>
            `;
            
            if (hasSub) {
                item.sub_items.forEach((sub, idx) => {
                    const isLast = idx === item.sub_items.length - 1;
                    const icon = sub.type === 'eigenverbrauch' ? '<i class="ph ph-door" style="margin-right: 6px; font-size: 1.1em; color: var(--primary);"></i>' : '<i class="ph ph-house" style="margin-right: 6px; font-size: 1.1em; color: var(--text-muted);"></i>';
                    
                    let subDesc = escapeHtml(sub.description);
                    if (item.meter_details) {
                        const md = item.meter_details;
                        if (sub.type === 'eigenverbrauch' && md.tenant_meter && md.tenant_meter.is_interpolated) {
                            subDesc = window.wrapInterpolated(subDesc, true, md.tenant_meter);
                        } else if (sub.type === 'allgemein') {
                            const isAllg = (md.main_meter && md.main_meter.is_interpolated) || (md.tenant_meter && md.tenant_meter.is_interpolated);
                            if (isAllg && md.main_meter) {
                                subDesc = window.wrapInterpolated(subDesc, true, md.main_meter);
                            }
                        }
                    }
                    
                    html += `
                        <tr style="border-bottom: ${isLast ? '1px solid var(--border-color)' : 'none'}; background-color: var(--bg-hover);">
                            <td colspan="2" style="padding: 4px 8px;"></td>
                            <td style="color: var(--text-muted); font-size: 0.85rem; padding: 4px 8px; padding-left: 24px;">
                                <div style="display: flex; align-items: center;">
                                    ${icon} ${subDesc}
                                </div>
                            </td>
                            <td style="color: var(--text-muted); font-size: 0.85rem; text-align: right; padding: 4px 8px;">${formatiereBetrag(sub.cost)} €</td>
                            <td></td>
                        </tr>
                    `;
                });
            }
        });
        
        html += `
                <tr style="border-top: 2px solid var(--text-color);">
                    <td colspan="3" style="font-weight: 700; text-align: right; padding: 12px 8px;">Gesamtkosten der Periode:</td>
                    <td style="font-weight: 700; text-align: right; padding: 12px 8px;">${formatiereBetrag(data.total_amount)} €</td>
                    <td></td>
                </tr>
                <tr>
                    <td colspan="3" style="font-weight: 700; text-align: right; padding: 12px 8px;">Abzüglich geleistete Vorauszahlungen:</td>
                    <td style="font-weight: 700; text-align: right; padding: 12px 8px; color: var(--danger-color);">- ${formatiereBetrag(data.prepaid_amount)} €</td>
                    <td></td>
                </tr>
                <tr style="background: var(--bg-hover);">
                    <td colspan="3" style="font-weight: 800; text-align: right; padding: 16px 8px; font-size: 1.1em;">
                        ${data.balance > 0 ? 'Nachzahlung des Mieters:' : (data.balance < 0 ? 'Guthaben des Mieters:' : 'Saldobetrag:')}
                    </td>
                    <td style="font-weight: 800; text-align: right; padding: 16px 8px; font-size: 1.1em; color: var(--primary-color);">
                        ${formatiereBetrag(data.balance)} €
                    </td>
                    <td></td>
                </tr>
            </tbody></table>
        `;
        html += mieterErklaerungHtml(data);
        
        body.innerHTML = html;
        modal.classList.add('active');
        
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Fehler beim Laden der Abrechnungsdetails.'));
    }
}

let currentBillingSelection = null;

// Vorbelegung des Abrechnungszeitraums (NK-119): frühester Beginn und
// spätestes Ende der ausgewählten Kategorien. Ohne Auswahl keine Vorbelegung.
function vorgeschlagenerZeitraum(categories, ids) {
    const gewaehlt = categories.filter(c => ids.includes(c.category_id));
    if (gewaehlt.length === 0) return null;
    const beginn = gewaehlt.map(c => String(c.suggested_start).slice(0, 10)).sort()[0];
    const ende = gewaehlt.map(c => String(c.suggested_end).slice(0, 10)).sort().reverse()[0];
    return [beginn, ende];
}

// Prüfung vor dem Senden (NK-119). Überschneidungen mit festgesetzten
// Abrechnungen prüft der Server (D-55) und meldet sie in der Vorschau.
/* NK-142: Der freie Weg zur Abrechnung, falls die Vorschlagskarte fehlt
   (kein Vorschlag, ausgezogener Mieter, Sonderfall). Dieselbe Vorschau,
   dieselbe Festsetzung wie beim Vorschlagsweg -- nur ohne Vorarbeit. */
function openFreieAbrechnung() {
    const auswahl = document.getElementById('frei-mieter');
    auswahl.replaceChildren();
    const wohnungVon = id => {
        const w = allApartments.find(a => a.id === id);
        return w ? w.name : '';
    };
    [...tenants]
        .sort((a, b) => a.name.localeCompare(b.name, 'de'))
        .forEach(t => {
            const wohnung = wohnungVon(t.apartment_id);
            const text = wohnung ? `${t.name} (${wohnung})` : t.name;
            auswahl.insertAdjacentHTML('beforeend',
                `<option value="${t.id}">${escapeHtml(text)}</option>`);
        });
    if (tenants.length === 0) {
        auswahl.insertAdjacentHTML('beforeend',
            '<option value="">Kein Mietverhältnis vorhanden</option>');
    }

    // Vorbelegt: das vergangene Kalenderjahr, der haeufigste Fall.
    const jahr = new Date().getFullYear() - 1;
    document.getElementById('frei-period-start').value = `${jahr}-01-01`;
    document.getElementById('frei-period-end').value = `${jahr}-12-31`;

    document.getElementById('billing-frei-modal').classList.add('active');
}

function starteFreieAbrechnung() {
    const auswahl = document.getElementById('frei-mieter');
    const tenantId = parseInt(auswahl.value);
    if (!tenantId) {
        showError('Bitte wählen Sie ein Mietverhältnis aus.');
        return;
    }
    const beginn = document.getElementById('frei-period-start').value;
    const ende = document.getElementById('frei-period-end').value;
    const fehlerText = pruefeAbrechnungszeitraum(beginn, ende);
    if (fehlerText) {
        showError(fehlerText);
        return;
    }
    document.getElementById('billing-frei-modal').classList.remove('active');
    // Ohne Kategorien rechnet der Kern alle Kostenarten mit Rechnungen im
    // Zeitraum -- genau der Unterschied zum Vorschlagsweg.
    generateBillPreview(tenantId, beginn, ende);
}

function pruefeAbrechnungszeitraum(beginn, ende) {
    if (!beginn || !ende) return 'Bitte Beginn und Ende des Abrechnungszeitraums angeben.';
    if (beginn > ende) return 'Der Beginn des Abrechnungszeitraums liegt nach seinem Ende.';
    return null;
}

function openBillingSelectionModal(suggestion) {
    currentBillingSelection = suggestion;
    const modal = document.getElementById('billing-selection-modal');
    const body = document.getElementById('billing-selection-body');
    
    let html = `<p style="margin-bottom: 16px;">Bitte wählen Sie die Kategorien aus, die in diese Abrechnung einfließen sollen:</p>`;
    
    suggestion.categories.forEach(cat => {
        const startFmt = new Date(cat.suggested_start).toLocaleDateString('de-DE');
        const endFmt = new Date(cat.suggested_end).toLocaleDateString('de-DE');
        
        html += `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 8px; background: var(--bg-hover);">
                <label style="display: flex; align-items: center; gap: 12px; cursor: pointer; flex: 1;">
                    <input type="checkbox" class="category-select-cb" value="${cat.category_id}" checked style="width: 18px; height: 18px;">
                    <div>
                        <div style="font-weight: bold;">${escapeHtml(cat.category_name)}</div>
                        <div style="font-size: 0.85rem; color: var(--text-muted);">${startFmt} - ${endFmt} (${cat.invoice_count} Rechnungen)</div>
                    </div>
                </label>
            </div>
        `;
    });
    
    body.innerHTML = html;

    // Zeitraumfelder: folgen der Auswahl, bis sie von Hand geändert werden.
    const beginnFeld = document.getElementById('billing-period-start');
    const endeFeld = document.getElementById('billing-period-end');
    const ausgewaehlteIds = () => Array.from(document.querySelectorAll('.category-select-cb:checked'))
        .map(cb => parseInt(cb.value));
    let vonHand = false;
    const vorbelegen = () => {
        if (vonHand) return;
        const zeitraum = vorgeschlagenerZeitraum(suggestion.categories, ausgewaehlteIds());
        if (zeitraum) [beginnFeld.value, endeFeld.value] = zeitraum;
    };
    beginnFeld.oninput = () => { vonHand = true; };
    endeFeld.oninput = () => { vonHand = true; };
    body.querySelectorAll('.category-select-cb').forEach(cb => { cb.onchange = vorbelegen; });
    vorbelegen();

    document.getElementById('btn-proceed-preview').onclick = () => {
        const selectedCategoryIds = ausgewaehlteIds();
        if (selectedCategoryIds.length === 0) {
            showError('Bitte wählen Sie mindestens eine Kategorie aus.');
            return;
        }
        const beginn = beginnFeld.value;
        const ende = endeFeld.value;
        const fehlerText = pruefeAbrechnungszeitraum(beginn, ende);
        if (fehlerText) {
            showError(fehlerText);
            return;
        }

        document.getElementById('billing-selection-modal').classList.remove('active');
        generateBillPreview(suggestion.tenant_id, beginn, ende, selectedCategoryIds);
    };
    
    modal.classList.add('active');
}

async function generateBillPreview(tenantId, startDate, endDate, categoryIds = null) {
    try {
        const payload = { tenant_id: tenantId, start_date: startDate, end_date: endDate };
        if (categoryIds) payload.category_ids = categoryIds;
        
        // Fetch preflight check
        const pfRes = await fetch('/api/billing/preflight', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const pfData = await pfRes.json();
        
        // Fetch actual bill
        const res = await fetch('/api/billing/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) {
            let errMsg = 'Fehler beim Generieren der Abrechnung.';
            try {
                const errData = await res.json();
                if (errData.error) errMsg = errData.error;
            } catch(e) {}
            showError(errMsg);
            return;
        }
        const data = await res.json();
        
        const modal = document.getElementById('billing-preview-modal');
        const body = document.getElementById('billing-preview-body');
        
        let html = `
            <div style="margin-bottom: 24px;">
                <h3 style="margin:0;">Abrechnung für ${escapeHtml(data.tenant_name)}</h3>
                <p style="color: var(--text-muted); margin: 4px 0;">${escapeHtml(data.property)} - ${escapeHtml(data.apartment)}</p>
                <p style="color: var(--text-muted); margin: 4px 0;">Zeitraum: ${new Date(data.start_date).toLocaleDateString('de-DE')} bis ${new Date(data.end_date).toLocaleDateString('de-DE')}</p>
            </div>
        `;
        
        // Preflight Panel
        if (pfData.overall !== 'no_meters' && pfData.checks && pfData.checks.length > 0) {
            let pfColor = 'var(--success-color)';
            let pfIcon = 'ph-check-circle';
            let pfTitle = 'Zählerstände: Ausgezeichnet (Alle Ablesungen innerhalb von 7 Tagen zum Stichtag)';
            let pfBg = 'rgba(16, 185, 129, 0.1)';
            let pfBorder = 'rgba(16, 185, 129, 0.3)';
            
            if (pfData.overall === 'warning') {
                pfColor = 'var(--danger-color)';
                pfIcon = 'ph-warning-circle';
                pfTitle = 'Zählerstände: Warnung (Große Lücken oder fehlende Daten)';
                pfBg = 'var(--danger-bg)';
                pfBorder = 'rgba(220, 38, 38, 0.3)';
            } else if (pfData.overall === 'acceptable') {
                pfColor = 'var(--warning-color)';
                pfIcon = 'ph-info';
                pfTitle = 'Zählerstände: Akzeptabel (Einige Ablesungen bis zu 14 Tage Toleranz)';
                pfBg = 'var(--warning-bg)';
                pfBorder = 'rgba(217, 119, 6, 0.3)';
            }
            
            html += `
            <div style="background: ${pfBg}; border: 1px solid ${pfBorder}; border-radius: 8px; padding: 12px; margin-bottom: 24px;">
                <details>
                    <summary style="cursor: pointer; font-weight: bold; color: ${pfColor}; margin-bottom: 4px; display: flex; align-items: center; gap: 8px;">
                        <i class="ph ${pfIcon}" style="font-size: 1.2rem;"></i>
                        ${pfTitle} [Details einblenden]
                    </summary>
                    <div style="margin-top: 12px; display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));">
            `;
            
            pfData.checks.forEach(c => {
                let statusIcon = '<i class="ph ph-check-circle" style="color: var(--success-color);"></i>';
                if (c.status === 'warning' || c.status === 'no_data') statusIcon = '<i class="ph ph-warning-circle" style="color: var(--danger-color);"></i>';
                else if (c.status === 'acceptable') statusIcon = '<i class="ph ph-info" style="color: var(--warning-color);"></i>';
                
                let valStr = "";
                if (c.status !== 'no_data') {
                    let interpTag = "";
                    if (c.is_interpolated) {
                        const ttStr = `Zählerstand muss aufgrund<br>der Abweichung interpoliert werden.`;
                        interpTag = `<span class="interpolated-wrapper" style="margin-left: 8px;">
                            <span class="math-icon math-icon-primaer"><i class="ph ph-calculator" aria-hidden="true"></i></span>
                            <div class="glass-tooltip">${ttStr}</div>
                        </span>`;
                    }
                    valStr = `<div style="font-size: 0.85rem; color: var(--text-muted); display: flex; align-items: center; margin-top: 4px;">Abweichung: Start ${c.start_offset_days}T, Ende ${c.end_offset_days}T ${interpTag}</div>`;
                } else {
                    valStr = `<div style="font-size: 0.85rem; color: var(--danger-color); margin-top: 4px;">Keine ausreichenden Daten</div>`;
                }
                
                html += `
                        <div style="background: white; border: 1px solid var(--border-color); padding: 8px; border-radius: 4px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="font-weight: 500; font-size: 0.9rem;">${escapeHtml(c.category)} (${escapeHtml(c.meter_type)})</div>
                                ${statusIcon}
                            </div>
                            <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Zähler: ${escapeHtml(c.meter_number || 'N/A')}</div>
                            ${valStr}
                        </div>
                `;
            });
            
            html += `
                    </div>
                </details>
            </div>
            `;
        }
        
        // Old warnings logic fallback for non-meter stuff
        if (data.warnings && data.warnings.length > 0) {
            const otherWarnings = data.warnings.filter(w => !w.includes('interpoliert'));
            if (otherWarnings.length > 0) {
                html += `<div style="background: var(--danger-bg); border: 1px solid rgba(220, 38, 38, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 24px;">`;
                otherWarnings.forEach(w => {
                    html += `<div style="color: var(--danger-color); font-size: 0.95rem; margin-bottom: 4px;">${escapeHtml(w)}</div>`;
                });
                html += `</div>`;
            }
        }
        
        html += `
            <table class="data-table" style="width: 100%;">
                <thead>
                    <tr>
                        <th>Kostenart</th>
                        <th>Rechnungszeitraum</th>
                        <th>Umlage-Details</th>
                        <th style="text-align: right;">Betrag</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        if (data.line_items.length === 0) {
            html += `<tr><td colspan="4" style="text-align: center;">Keine Kosten in diesem Zeitraum gefunden.</td></tr>`;
        }
        
        data.line_items.forEach(item => {
            let detailsHtml = escapeHtml(item.description);
            
            // Inject meter details if available
            if (item.meter_details) {
                const md = item.meter_details;
                let mdStr = `<div style="margin-top: 8px; font-size: 13px; background: var(--bg-color); padding: 8px; border-radius: 4px; border: 1px dashed #d1d5db;">`;
                if (md.tenant_meter && md.tenant_meter.status !== 'no_data') {
                    let tCons = md.tenant_consumption !== null ? md.tenant_consumption.toFixed(1) : 'N/A';
                    if (tCons !== 'N/A') tCons = window.wrapInterpolated(tCons, md.tenant_meter.is_interpolated, md.tenant_meter);
                    mdStr += `<div><span style="font-weight:bold;">Ihr Wohnungszähler:</span> ${tCons} ${escapeHtml(md.unit)}</div>`;
                }
                if (md.main_meter && md.main_meter.status !== 'no_data') {
                    let mCons = md.main_consumption !== null ? md.main_consumption.toFixed(1) : 'N/A';
                    if (mCons !== 'N/A') mCons = window.wrapInterpolated(mCons, md.main_meter.is_interpolated, md.main_meter);
                    
                    let aCons = md.allgemein_consumption !== null ? md.allgemein_consumption.toFixed(1) : 'N/A';
                    const isAllgInterpolated = md.main_meter.is_interpolated || (md.tenant_meter && md.tenant_meter.is_interpolated);
                    if (aCons !== 'N/A') aCons = window.wrapInterpolated(aCons, isAllgInterpolated, md.main_meter);
                    
                    mdStr += `<div><span style="font-weight:bold;">Hauptzähler:</span> ${mCons} ${escapeHtml(md.unit)}</div>`;
                    mdStr += `<div><span style="font-weight:bold;">Allgemeinverbrauch:</span> ${aCons} ${escapeHtml(md.unit)}</div>`;
                }
                mdStr += `</div>`;
                detailsHtml += mdStr;
            }
            
            html += `
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="font-weight: 500; padding: 12px 8px; vertical-align: top;">${escapeHtml(item.category)}</td>
                    <td style="color: var(--text-muted); font-size: 0.9rem; white-space: nowrap; padding: 12px 8px; vertical-align: top;">${escapeHtml(item.period)}</td>
                    <td style="color: var(--text-muted); font-size: 0.875rem; padding: 12px 8px; vertical-align: top;">${detailsHtml}</td>
                    <td style="text-align: right; font-weight: 500; padding: 12px 8px; vertical-align: top;">€${item.tenant_cost.toFixed(2).replace('.', ',')}</td>
                </tr>
            `;
        });
        
        html += `
                </tbody>
                <tfoot>
                    <tr style="border-top: 2px solid var(--border-color);">
                        <td colspan="3" style="text-align: right; padding: 12px 8px;">Gesamtkosten der Periode:</td>
                        <td style="text-align: right; font-weight: bold; padding: 12px 8px;">€${data.total_amount.toFixed(2).replace('.', ',')}</td>
                    </tr>
                    <tr>
                        <td colspan="3" style="text-align: right; padding: 12px 8px;">Abzüglich geleistete Vorauszahlungen:</td>
                        <td style="text-align: right; color: var(--danger-color); padding: 12px 8px;">- €${data.prepaid_amount.toFixed(2).replace('.', ',')}</td>
                    </tr>
                    <tr style="background: var(--bg-hover);">
                        <td colspan="3" style="text-align: right; font-size: 1.1rem; font-weight: bold; padding: 16px 8px;">
                            ${data.balance > 0 ? 'Nachzahlung des Mieters' : (data.balance < 0 ? 'Guthaben des Mieters' : 'Saldobetrag')}
                        </td>
                        <td style="text-align: right; font-size: 1.1rem; font-weight: bold; color: var(--primary-color); padding: 16px 8px;">€${data.balance.toFixed(2).replace('.', ',')}</td>
                    </tr>
                </tfoot>
            </table>
        `;
        html += mieterErklaerungHtml(data);
        
        body.innerHTML = html;
        
        document.getElementById('btn-generate-pdf').onclick = () => finalizeBill(tenantId, startDate, endDate, categoryIds, false);
        const btnSimple = document.getElementById('btn-generate-pdf');
        if (btnSimple) {
            btnSimple.disabled = false;
            btnSimple.style.opacity = '1';
            btnSimple.style.cursor = 'pointer';
            btnSimple.innerHTML = 'PDF erstellen &amp; abschließen';
        }
        
        const btnDetailed = document.getElementById('btn-generate-detailed-pdf');
        if (btnDetailed) {
            btnDetailed.onclick = () => finalizeBill(tenantId, startDate, endDate, categoryIds, true);
            btnDetailed.disabled = false;
            btnDetailed.style.opacity = '1';
            btnDetailed.style.cursor = 'pointer';
            btnDetailed.innerHTML = '<i class="ph ph-file-magnifying-glass"></i> PDF erstellen (detailliert)';
        }
        
        modal.classList.add('active');
        
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Fehler bei der Vorschau-Generierung.'));
    }
}

async function finalizeBill(tenantId, startDate, endDate, categoryIds = null, isDetailed = false) {
    const btnId = isDetailed ? 'btn-generate-detailed-pdf' : 'btn-generate-pdf';
    const btn = document.getElementById(btnId);
    const originalText = btn.innerHTML;
    
    // Disable both buttons during processing
    const allBtns = [document.getElementById('btn-generate-pdf'), document.getElementById('btn-generate-detailed-pdf')];
    allBtns.forEach(b => { if(b) b.disabled = true; });
    
    btn.textContent = 'PDF wird erstellt...';
    
    try {
        const payload = { 
            tenant_id: tenantId, 
            start_date: startDate, 
            end_date: endDate,
            detailed: isDetailed
        };
        if (categoryIds) payload.category_ids = categoryIds;
        
        const res = await fetch('/api/billing/finalize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) throw await serverFehler(res);
        const data = await res.json();
        
        showSuccess(`Erfolg: ${data.message}`);
        
        // Keep modal open — disable the used button with a checkmark
        btn.innerHTML = '<i class="ph ph-check-circle" aria-hidden="true"></i> ' +
            (isDetailed ? 'PDF erstellt (detailliert)' : 'PDF erstellt (einfach)');
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.cursor = 'not-allowed';
        
        // Re-enable the OTHER button so user can generate it too
        const otherBtnId = isDetailed ? 'btn-generate-pdf' : 'btn-generate-detailed-pdf';
        const otherBtn = document.getElementById(otherBtnId);
        if (otherBtn) otherBtn.disabled = false;
        
        // Refresh history in background
        fetchBillingSuggestions();
        fetchBillingHistory();
        fetchDocuments();
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Die Abrechnung konnte nicht abgeschlossen werden.'));
        // Restore buttons on error
        allBtns.forEach(b => { if(b) b.disabled = false; });
        btn.innerHTML = originalText;
    }
}

// --- Analytics & Reports ---
let chartBuildingTimeseriesInstance = null;
let chartBuildingComparisonInstance = null;
let chartConsumptionTrendInstance = null;
let chartAptCostsInstance = null;
let chartFinanceDistributionInstance = null;
let chartFinanceCashflowInstance = null;
let currentAnalyticsView = 'general';

function populateAnalyticsPropertySelect() {
    const sel = document.getElementById('analytics-property-select');
    if (sel.options.length === properties.length) return;
    
    const gewaehlt = sel.value;
    sel.replaceChildren();
    properties.forEach(p => {
        sel.insertAdjacentHTML('beforeend', `<option value="${p.id}">${escapeHtml(p.name)}</option>`);
    });
    // Die gewaehlte Immobilie bleibt gewaehlt, auch wenn spaeter eine
    // neue dazu kam (NK-141).
    if (gewaehlt && properties.some(p => String(p.id) === gewaehlt)) {
        sel.value = gewaehlt;
    }
}


async function fetchAnalytics() {
    populateAnalyticsPropertySelect();
    const propIdStr = document.getElementById('analytics-property-select').value;
    // NK-154: ohne Immobilie keine leere Seite, sondern ein Leerzustand mit
    // dem Weg zur Beispielimmobilie.
    const leer = document.getElementById('analytics-leer');
    const ohneImmobilie = !propIdStr;
    if (leer) {
        leer.hidden = !ohneImmobilie;
        leer.innerHTML = ohneImmobilie ? leerzustand({
            icon: 'ph-chart-line-up',
            titel: 'Noch keine Statistik',
            text: 'Statistiken entstehen aus Ihren Immobilien, Zählern und Rechnungen. ' +
                'Legen Sie eine Beispielimmobilie an, um zu sehen, wie das aussieht — ' +
                'oder legen Sie unter „Immobilien“ Ihre eigene an.',
            aktion: { label: 'Beispielimmobilie anlegen', fn: 'beispielAnlegen(this)', icon: 'ph-sparkle' },
        }) : '';
    }
    const sichtbarAls = { 'analytics-auswahl': 'flex', 'analytics-nav': 'flex', 'analytics-trenner': 'block' };
    for (const [kennung, art] of Object.entries(sichtbarAls)) {
        const element = document.getElementById(kennung);
        if (element) element.style.display = ohneImmobilie ? 'none' : art;
    }
    if (ohneImmobilie) {
        for (const kennung of ['analytics-view-general', 'analytics-view-apartment',
            'analytics-view-dataquality', 'analytics-view-finanzen']) {
            const ansicht = document.getElementById(kennung);
            if (ansicht) ansicht.style.display = 'none';
        }
        return;
    }
    const propId = parseInt(propIdStr);
    
    if (currentAnalyticsView !== 'general' && currentAnalyticsView !== 'dataquality' && currentAnalyticsView !== 'finanzen') {
        const apt = allApartments.find(a => a.id === currentAnalyticsView);
        if (!apt || apt.property_id !== propId) {
            currentAnalyticsView = 'general';
        }
    }
    
    const navContainer = document.getElementById('analytics-nav');
    navContainer.replaceChildren();
    
    const btnGen = document.createElement('button');
    btnGen.className = currentAnalyticsView === 'general' ? 'btn-primary' : 'btn-secondary';
    btnGen.textContent = 'Gebäudeübersicht';
    btnGen.onclick = () => { currentAnalyticsView = 'general'; fetchAnalytics(); };
    navContainer.appendChild(btnGen);
    
    const apts = allApartments.filter(a => a.property_id === propId);
    apts.forEach(apt => {
        const btnApt = document.createElement('button');
        btnApt.className = currentAnalyticsView === apt.id ? 'btn-primary' : 'btn-secondary';
        btnApt.textContent = apt.name;
        btnApt.onclick = () => { currentAnalyticsView = apt.id; fetchAnalytics(); };
        navContainer.appendChild(btnApt);
    });
    
    // Finanzen pill
    const btnFin = document.createElement('button');
    btnFin.className = currentAnalyticsView === 'finanzen' ? 'btn-primary' : 'btn-secondary';
    btnFin.innerHTML = '<i class="ph ph-coins" aria-hidden="true"></i> Finanzen';
    btnFin.onclick = () => { currentAnalyticsView = 'finanzen'; fetchAnalytics(); };
    navContainer.appendChild(btnFin);
    
    // Datenqualität pill
    const btnDQ = document.createElement('button');
    btnDQ.className = currentAnalyticsView === 'dataquality' ? 'btn-primary' : 'btn-secondary';
    btnDQ.innerHTML = '<i class="ph ph-clipboard-text" aria-hidden="true"></i> Datenqualität';
    btnDQ.onclick = () => { currentAnalyticsView = 'dataquality'; fetchAnalytics(); };
    navContainer.appendChild(btnDQ);
    
    const viewGen = document.getElementById('analytics-view-general');
    const viewApt = document.getElementById('analytics-view-apartment');
    const viewDQ = document.getElementById('analytics-view-dataquality');
    const viewFin = document.getElementById('analytics-view-finanzen');
    
    // Hide all views first
    viewGen.style.display = 'none';
    viewApt.style.display = 'none';
    viewDQ.style.display = 'none';
    viewFin.style.display = 'none';
    
    if (currentAnalyticsView === 'general') {
        viewGen.style.display = 'flex';
        const resB = await fetch(`/api/analytics/building/${propId}`);
        const dataB = await resB.json();
        renderBuildingVitalSigns(dataB.kpis);
        renderConsumptionTrend(dataB.timeseries_data);
        renderTenantOverview(propId);
        renderBuildingComparison(dataB.apartment_comparison);
    } else if (currentAnalyticsView === 'finanzen') {
        viewFin.style.display = 'flex';
        const resB = await fetch(`/api/analytics/building/${propId}`);
        const dataB = await resB.json();
        renderBuildingTimeseries(dataB.timeseries_data);
        renderFinanceCharts(dataB.cashflow);
    } else if (currentAnalyticsView === 'dataquality') {
        viewDQ.style.display = 'flex';
        const resDQ = await fetch(`/api/analytics/data-quality/${propId}`);
        const dataDQ = await resDQ.json();
        renderDataQuality(dataDQ);
    } else {
        viewApt.style.display = 'block';
        const resA = await fetch(`/api/analytics/apartment/${currentAnalyticsView}`);
        const dataA = await resA.json();
        renderAptConsumptionChart(dataA.own_consumption);
        renderAptCostsChart(dataA.cost_distribution);
    }
}

/* NK-141: Die Beispielimmobilie gibt der leeren Uebersicht etwas zu sehen.
   Nach dem Anlegen wandert die Auswahl auf das neue Haus, die Ansicht laedt
   neu. Gibt es sie schon (409), nimmt die Antwort trotzdem ihre Nummer mit. */
async function beispielAnlegen(knopf) {
    if (knopf) knopf.disabled = true;
    try {
        const res = await fetch('/api/analytics/beispiel-immobilie', { method: 'POST' });
        const bericht = await res.json();
        if (!res.ok) {
            if (!bericht.property_id) throw await serverFehler(res);
            zeigeMeldung(bericht.error || 'Die Beispielimmobilie existiert bereits.', 'fehler');
        } else {
            zeigeMeldung(bericht.abrechnung
                ? 'Beispielhaus angelegt, mit fertiger Abrechnung des Vorjahres unter „Abrechnungen“.'
                : 'Beispielhaus angelegt.', 'erfolg');
        }
        // NK-154: alle Bestände neu laden -- sonst zählt die Übersicht
        // „2 ausstehende Abrechnungen“ und die Mieterübersicht darunter
        // meldet aus der alten Liste „keine Mieter“.
        await Promise.all([fetchProperties(), fetchAllApartments(), fetchTenants(), fetchMeters(),
            fetchInvoices(), fetchPayments(), fetchBillingHistory(), fetchReadings()]);
        populateAnalyticsPropertySelect();
        document.getElementById('analytics-property-select').value = String(bericht.property_id);
        await fetchAnalytics();
    } catch (fehler) {
        console.error(fehler);
        zeigeMeldung(meldungZu(fehler, 'Beispielimmobilie konnte nicht angelegt werden.'), 'fehler');
    } finally {
        if (knopf) knopf.disabled = false;
    }
}

async function beispielLoeschen(knopf) {
    if (!await frageLoeschen('Das Beispielhaus mit allen Wohnungen, Mietern, Rechnungen, Zahlungen und der '
        + 'Beispielabrechnung löschen? Ihre eigenen Daten bleiben unberührt.')) return;
    if (knopf) knopf.disabled = true;
    try {
        const res = await fetch('/api/analytics/beispiel-immobilie', { method: 'DELETE' });
        if (!res.ok) throw await serverFehler(res);
        zeigeMeldung('Das Beispiel ist gelöscht.', 'erfolg');
        importNachladen();
        fetchBillingHistory();
        fetchDocuments();
        if (currentPropertyId && !properties.some(p => p.id === currentPropertyId && !p.ist_beispiel)) {
            propertyDetailsView.style.display = 'none';
            currentPropertyId = null;
        }
    } catch (fehler) {
        zeigeMeldung(meldungZu(fehler, 'Das Beispiel konnte nicht gelöscht werden.'), 'fehler');
    } finally {
        if (knopf) knopf.disabled = false;
    }
}
window.beispielLoeschen = beispielLoeschen;

function renderConsumptionTrend(timeseries_data) {
    const container = document.getElementById('chart-consumption-trend');
    if (!container) return;
    
    // Use the container itself, but style it appropriately
    container.replaceChildren();
    container.style.height = 'auto';
    container.style.display = 'grid';
    container.style.gridTemplateColumns = 'repeat(auto-fill, minmax(280px, 1fr))';
    container.style.gap = '16px';
    
    const withConsumption = timeseries_data.filter(d => d.consumption > 0);
    
    if (withConsumption.length === 0) {
        container.style.display = 'flex';
        container.style.alignItems = 'center';
        container.style.justifyContent = 'center';
        container.style.minHeight = '120px';
        const empty = document.createElement('div');
        empty.style.cssText = 'text-align: center; color: var(--text-muted);';
        const emptyIcon = document.createElement('i');
        emptyIcon.className = 'ph ph-chart-line-up';
        emptyIcon.style.cssText = 'font-size: 48px; opacity: 0.4; display: block; margin-bottom: 12px;';
        empty.appendChild(emptyIcon);
        const emptyText = document.createElement('p');
        emptyText.textContent = 'Noch keine Verbrauchsdaten vorhanden.';
        empty.appendChild(emptyText);
        container.appendChild(empty);
        return;
    }
    
    // Aggregate all consumption into one view (readings are consecutive, not overlapping)
    const totals = {};
    const allPeriods = [];
    withConsumption.forEach(d => {
        if (!totals[d.category]) {
            totals[d.category] = { consumption: 0, unit: d.unit };
        }
        totals[d.category].consumption += d.consumption;
        if (d.period) {
            d.period.split(' | ').forEach(p => {
                if (!allPeriods.includes(p)) allPeriods.push(p);
            });
        }
    });
    
    const categoryConfig = {
        'Strom': { icon: 'ph-lightning', color: DIAGRAMM_FARBE.gelb, label: 'Strom' },
        'Gas': { icon: 'ph-flame', color: DIAGRAMM_FARBE.rot, label: 'Gas' },
        'Wasser': { icon: 'ph-drop', color: DIAGRAMM_FARBE.blau, label: 'Wasser' },
    };
    
    const parseDe = s => { const p = s.trim().split('.'); return new Date(p[2], p[1]-1, p[0]); };
    
    // Build a single card
    const data = totals;
    
    const card = document.createElement('div');
    card.className = 'dq-meter-card';
    card.style.borderLeftColor = 'var(--primary)';
    
    // Find widest date range across all periods
    let earliest = null, latest = null;
    let earliestStr = '', latestStr = '';
    allPeriods.forEach(p => {
        const parts = p.split(' - ');
        if (parts.length === 2) {
            const d1 = parseDe(parts[0]);
            const d2 = parseDe(parts[1]);
            if (!earliest || d1 < earliest) { earliest = d1; earliestStr = parts[0].trim(); }
            if (!latest || d2 > latest) { latest = d2; latestStr = parts[1].trim(); }
        }
    });
    
    // Header with date range
    const header = document.createElement('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;';
    
    const title = document.createElement('div');
    title.className = 'dq-meter-title';
    title.style.display = 'flex';
    title.style.alignItems = 'center';
    title.style.gap = '6px';
    const calIcon = document.createElement('i');
    calIcon.className = 'ph ph-calendar';
    calIcon.style.color = 'var(--primary)';
    title.appendChild(calIcon);
    if (earliestStr && latestStr) {
        title.appendChild(document.createTextNode(`${earliestStr} – ${latestStr}`));
    } else {
        title.appendChild(document.createTextNode('Gesamtzeitraum'));
    }
    header.appendChild(title);
    card.appendChild(header);
    
    // Consumption metrics
    const metricsGrid = document.createElement('div');
    metricsGrid.style.cssText = 'display: flex; flex-direction: column; gap: 10px;';
    
    ['Strom', 'Gas', 'Wasser'].forEach(cat => {
        const cfg = categoryConfig[cat];
        const catData = data[cat];
        
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; align-items: center; gap: 10px;';
        
        // Icon
        const iconWrap = document.createElement('div');
        iconWrap.style.cssText = `width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background: ${cfg.color}15; flex-shrink: 0;`;
        const icon = document.createElement('i');
        icon.className = `ph ${cfg.icon}`;
        icon.style.cssText = `color: ${cfg.color}; font-size: 16px;`;
        iconWrap.appendChild(icon);
        row.appendChild(iconWrap);
        
        // Label
        const label = document.createElement('span');
        label.style.cssText = 'flex: 1; font-size: 13px; color: var(--text-muted);';
        label.textContent = cfg.label;
        row.appendChild(label);
        
        // Value
        const value = document.createElement('span');
        value.style.cssText = 'font-weight: 600; font-size: 15px; font-variant-numeric: tabular-nums;';
        if (catData) {
            value.textContent = `${catData.consumption.toLocaleString('de-DE')} ${catData.unit}`;
            value.style.color = cfg.color;
        } else {
            value.textContent = '—';
            value.style.color = 'var(--text-muted)';
            value.style.opacity = '0.5';
        }
        row.appendChild(value);
        
        metricsGrid.appendChild(row);
    });
    
    card.appendChild(metricsGrid);
    container.appendChild(card);
}

async function renderTenantOverview(propId) {
    const grid = document.getElementById('tenant-overview-grid');
    if (!grid) return;
    grid.replaceChildren();
    
    // Filter tenants for this property
    const propTenants = tenants.filter(t => {
        const apt = allApartments.find(a => a.id === t.apartment_id);
        return apt && apt.property_id === propId;
    });
    
    if (propTenants.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 24px;';
        empty.textContent = 'Keine Mieter für dieses Gebäude registriert.';
        grid.appendChild(empty);
        return;
    }
    
    // Fetch profiles for each tenant
    const profilePromises = propTenants.map(t =>
        fetch(`/api/tenants/${t.id}/profiles`).then(r => r.json()).catch(() => ({}))
    );
    
    // Fetch categories once
    let categories = [];
    try {
        const catRes = await fetch('/api/categories');
        categories = await catRes.json();
    } catch(e) { /* ignore */ }
    
    const catMap = {};
    categories.forEach(c => { catMap[c.id] = c.name; });
    
    const allProfiles = await Promise.all(profilePromises);
    
    const billingTypeLabels = {
        'direkt': 'Direkt',
        'nur_allgemein': 'Allgemein',
        'qm': 'nach m²',
        'personen': 'nach Personen',
        'ignoriert': 'Ignoriert'
    };
    
    const billingTypeColors = {
        'direkt': DIAGRAMM_FARBE.gruen,
        'nur_allgemein': DIAGRAMM_FARBE.blau,
        'qm': DIAGRAMM_FARBE.lila,
        'personen': DIAGRAMM_FARBE.gelb,
        'ignoriert': DIAGRAMM_FARBE.grau
    };
    
    propTenants.forEach((tenant, idx) => {
        const card = document.createElement('div');
        card.className = 'dq-meter-card';
        card.style.borderLeftColor = tenant.move_out_date ? DIAGRAMM_FARBE.grau : DIAGRAMM_FARBE.gruen;
        
        // Header
        const header = document.createElement('div');
        header.className = 'dq-meter-header';
        
        const titleWrap = document.createElement('div');
        
        const name = document.createElement('div');
        name.className = 'dq-meter-title';
        name.style.display = 'flex';
        name.style.alignItems = 'center';
        name.style.gap = '6px';
        const icon = document.createElement('i');
        icon.className = 'ph ph-user';
        icon.style.color = 'var(--primary)';
        name.appendChild(icon);
        name.appendChild(document.createTextNode(tenant.name));
        titleWrap.appendChild(name);
        
        const subtitle = document.createElement('div');
        subtitle.className = 'dq-meter-subtitle';
        subtitle.textContent = tenant.apartment_name || '—';
        titleWrap.appendChild(subtitle);
        
        header.appendChild(titleWrap);
        
        // Active/Inactive badge
        const badge = document.createElement('span');
        if (tenant.move_out_date) {
            badge.className = 'dq-status-badge none';
            badge.textContent = 'Ausgezogen';
        } else {
            badge.className = 'dq-status-badge green';
            badge.textContent = 'Aktiv';
        }
        header.appendChild(badge);
        
        card.appendChild(header);
        
        // Details
        const details = document.createElement('div');
        details.className = 'dq-meter-details';
        
        const addRow = (label, value) => {
            const row = document.createElement('div');
            row.className = 'dq-meter-detail';
            const l = document.createElement('span');
            l.textContent = label;
            row.appendChild(l);
            const v = document.createElement('span');
            v.textContent = value;
            row.appendChild(v);
            details.appendChild(row);
        };
        
        // Move-in date
        const moveIn = new Date(tenant.move_in_date);
        addRow('Einzug', moveIn.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }));
        
        if (tenant.move_out_date) {
            const moveOut = new Date(tenant.move_out_date);
            addRow('Auszug', moveOut.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }));
        }
        
        // Duration
        const now = tenant.move_out_date ? new Date(tenant.move_out_date) : new Date();
        const diffMs = now - moveIn;
        const years = Math.floor(diffMs / (365.25 * 24 * 60 * 60 * 1000));
        const months = Math.floor((diffMs % (365.25 * 24 * 60 * 60 * 1000)) / (30.44 * 24 * 60 * 60 * 1000));
        const durationStr = years > 0 ? `${years} J, ${months} M` : `${months} Monate`;
        addRow('Wohndauer', durationStr);
        
        card.appendChild(details);
        
        // Billing profiles as pills
        const profiles = allProfiles[idx] || {};
        const profileKeys = Object.keys(profiles).filter(k => profiles[k] !== 'ignoriert');
        
        if (profileKeys.length > 0) {
            const pillContainer = document.createElement('div');
            pillContainer.style.cssText = 'display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color);';
            
            profileKeys.forEach(catId => {
                const bt = profiles[catId];
                const catName = catMap[parseInt(catId)] || `Kat. ${catId}`;
                
                const pill = document.createElement('span');
                pill.style.cssText = `
                    display: inline-flex; align-items: center; gap: 4px;
                    padding: 3px 8px; border-radius: 12px; font-size: 13px; font-weight: 500;
                    background: ${billingTypeColors[bt] || DIAGRAMM_FARBE.grau}15;
                    color: ${billingTypeColors[bt] || DIAGRAMM_FARBE.grau};
                    border: 1px solid ${billingTypeColors[bt] || DIAGRAMM_FARBE.grau}30;
                `;
                pill.textContent = `${catName}: ${billingTypeLabels[bt] || bt}`;
                pillContainer.appendChild(pill);
            });
            
            card.appendChild(pillContainer);
        }
        
        grid.appendChild(card);
    });
}

function renderDataQuality(data) {
    const grid = document.getElementById('dq-meter-grid');
    const warningsContainer = document.getElementById('dq-warnings-container');
    const warningsSection = document.getElementById('dq-warnings-section');
    const summaryBar = document.getElementById('dq-summary-bar');
    
    grid.replaceChildren();
    warningsContainer.replaceChildren();
    summaryBar.replaceChildren();
    
    // --- Summary counts ---
    const counts = { green: 0, yellow: 0, red: 0, none: 0 };
    data.meters.forEach(m => { counts[m.status] = (counts[m.status] || 0) + 1; });
    
    const statusLabels = {
        green: 'Aktuell (< 90 Tage)',
        yellow: 'Veraltet (< 180 Tage)',
        red: 'Dringend (≥ 180 Tage)',
        none: 'Keine Ablesungen'
    };
    
    Object.entries(counts).forEach(([status, count]) => {
        if (count === 0) return;
        const item = document.createElement('div');
        item.className = 'dq-summary-item';
        
        const dot = document.createElement('span');
        dot.className = `dq-summary-dot ${status}`;
        item.appendChild(dot);
        
        const label = document.createElement('span');
        label.textContent = `${count} ${statusLabels[status]}`;
        item.appendChild(label);
        
        summaryBar.appendChild(item);
    });
    
    // --- Warnings ---
    if (data.warnings && data.warnings.length > 0) {
        warningsSection.style.display = 'block';
        data.warnings.forEach(w => {
            const card = document.createElement('div');
            card.className = 'dq-warning-card';
            
            const icon = document.createElement('i');
            icon.className = 'ph ph-warning-circle dq-warning-icon';
            card.appendChild(icon);
            
            const textWrap = document.createElement('div');
            
            const msg = document.createElement('div');
            msg.className = 'dq-warning-text';
            msg.textContent = w.message;
            textWrap.appendChild(msg);
            
            const meta = document.createElement('div');
            meta.className = 'dq-warning-meta';
            meta.textContent = `${w.tenant_name} · ${w.apartment_name} · ${w.category_name}`;
            textWrap.appendChild(meta);
            
            card.appendChild(textWrap);
            warningsContainer.appendChild(card);
        });
    } else {
        warningsSection.style.display = 'none';
    }
    
    // --- Meter cards ---
    if (data.meters.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'dq-empty-state';
        
        const emptyIcon = document.createElement('i');
        emptyIcon.className = 'ph ph-check-circle';
        empty.appendChild(emptyIcon);
        
        const emptyText = document.createElement('p');
        emptyText.textContent = 'Keine Zähler für dieses Gebäude registriert.';
        empty.appendChild(emptyText);
        
        grid.appendChild(empty);
        return;
    }
    
    // Sort: red first, then yellow, then none, then green
    const statusOrder = { red: 0, yellow: 1, none: 2, green: 3 };
    const sorted = [...data.meters].sort((a, b) => 
        (statusOrder[a.status] ?? 4) - (statusOrder[b.status] ?? 4)
    );
    
    const categoryIcons = {
        'Strom': 'ph-lightning',
        'Wasser': 'ph-drop',
        'Gas': 'ph-flame',
        'Abwasser': 'ph-pipe',
    };
    
    const statusText = {
        green: 'Aktuell',
        yellow: 'Veraltet',
        red: 'Dringend',
        none: 'Keine Daten'
    };
    
    sorted.forEach(m => {
        const card = document.createElement('div');
        card.className = `dq-meter-card status-${m.status}`;
        
        // Header
        const header = document.createElement('div');
        header.className = 'dq-meter-header';
        
        const titleWrap = document.createElement('div');
        
        const title = document.createElement('div');
        title.className = 'dq-meter-title';
        const iconClass = categoryIcons[m.category_name] || 'ph-gauge';
        const titleIcon = document.createElement('i');
        titleIcon.className = `ph ${iconClass}`;
        titleIcon.style.marginRight = '6px';
        title.appendChild(titleIcon);
        const titleText = document.createTextNode(m.category_name);
        title.appendChild(titleText);
        if (m.is_main_meter) {
            const mainBadge = document.createElement('span');
            mainBadge.textContent = ' (Hauptzähler)';
            mainBadge.style.color = 'var(--text-muted)';
            mainBadge.style.fontWeight = '400';
            mainBadge.style.fontSize = '13px';
            title.appendChild(mainBadge);
        }
        titleWrap.appendChild(title);
        
        const subtitle = document.createElement('div');
        subtitle.className = 'dq-meter-subtitle';
        subtitle.textContent = m.apartment_name ? `${m.apartment_name} · ${m.meter_number}` : m.meter_number;
        titleWrap.appendChild(subtitle);
        
        header.appendChild(titleWrap);
        
        // Status badge
        const badge = document.createElement('span');
        badge.className = `dq-status-badge ${m.status}`;
        badge.textContent = statusText[m.status];
        header.appendChild(badge);
        
        card.appendChild(header);
        
        // Details
        const details = document.createElement('div');
        details.className = 'dq-meter-details';
        
        const addDetail = (label, value) => {
            const row = document.createElement('div');
            row.className = 'dq-meter-detail';
            const labelSpan = document.createElement('span');
            labelSpan.textContent = label;
            row.appendChild(labelSpan);
            const valueSpan = document.createElement('span');
            valueSpan.textContent = value;
            row.appendChild(valueSpan);
            details.appendChild(row);
        };
        
        if (m.last_reading_date) {
            const dateStr = new Date(m.last_reading_date).toLocaleDateString('de-DE', {
                day: '2-digit', month: '2-digit', year: 'numeric'
            });
            addDetail('Letzte Ablesung', dateStr);
            addDetail('Tage seitdem', `${m.days_since_reading} Tage`);
        } else {
            addDetail('Letzte Ablesung', '—');
        }
        
        addDetail('Ablesungen gesamt', String(m.reading_count));
        
        card.appendChild(details);
        grid.appendChild(card);
    });
}

function renderFinanceCharts(cashflowData) {
    const ctxDist = document.getElementById('chart-finance-distribution').getContext('2d');
    if (chartFinanceDistributionInstance) chartFinanceDistributionInstance.destroy();
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    let sumMiete = 0; let sumVZ = 0; let sumNachzahlung = 0; let sumKaution = 0;
    payments.forEach(p => {
        const pDate = new Date(p.payment_date);
        if (pDate <= today) {
            if (p.type === 'Miete') sumMiete += p.amount;
            else if (p.type === 'Nebenkostenvorauszahlung') sumVZ += p.amount;
            else if (p.type === 'Nebenkostenzahlung') sumNachzahlung += p.amount;
            else if (p.type === 'Kaution') sumKaution += p.amount;
        }
    });
    
    chartFinanceDistributionInstance = new Chart(ctxDist, {
        type: 'doughnut',
        data: {
            labels: ['Miete', 'Vorauszahlungen', 'Nachzahlungen', 'Kaution'],
            datasets: [{
                data: [sumMiete, sumVZ, sumNachzahlung, sumKaution],
                backgroundColor: [DIAGRAMM_FARBE.blau, DIAGRAMM_FARBE.gruen, DIAGRAMM_FARBE.gelb, DIAGRAMM_FARBE.lila]
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.label + ': ' + context.raw.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
                        }
                    }
                }
            }
        }
    });

    const ctxCashflow = document.getElementById('chart-finance-cashflow').getContext('2d');
    if (chartFinanceCashflowInstance) chartFinanceCashflowInstance.destroy();
    
    const years = cashflowData.map(d => d.year);
    
    chartFinanceCashflowInstance = new Chart(ctxCashflow, {
        type: 'bar',
        data: {
            labels: years,
            datasets: [
                {
                    label: 'Einnahmen (erhalten)',
                    data: cashflowData.map(d => d.in_actual || 0),
                    backgroundColor: DIAGRAMM_FARBE.gruen,
                    stack: 'income'
                },
                {
                    label: 'Einnahmen (ausstehend)',
                    data: cashflowData.map(d => d.in_forecast || 0),
                    backgroundColor: "rgba(16, 185, 129, 0.35)",
                    borderColor: DIAGRAMM_FARBE.gruen,
                    borderWidth: 1,
                    borderDash: [4, 4],
                    stack: 'income'
                },
                {
                    label: 'Ausgaben (bezahlt)',
                    data: cashflowData.map(d => d.out_actual || 0),
                    backgroundColor: DIAGRAMM_FARBE.rot,
                    stack: 'expenses'
                },
                {
                    label: 'Ausgaben (ausstehend)',
                    data: cashflowData.map(d => d.out_forecast || 0),
                    backgroundColor: "rgba(239, 68, 68, 0.35)",
                    borderColor: DIAGRAMM_FARBE.rot,
                    borderWidth: 1,
                    borderDash: [4, 4],
                    stack: 'expenses'
                }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { stacked: true },
                y: {
                    stacked: true,
                    ticks: {
                        callback: function(value) {
                            return value.toLocaleString('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.raw.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
                        }
                    }
                }
            }
        }
    });
}

function renderBuildingVitalSigns(kpis) {
    const container = document.getElementById('kpis-container');
    if (!container) return;
    
    let trendIcon = kpis.general_power_trend > 0 ? '<i class="ph ph-trend-up"></i>' : '<i class="ph ph-trend-down"></i>';
    let trendColor = kpis.general_power_trend > 0 ? 'color: var(--danger-color)' : 'color: var(--success-color)';
    if (kpis.general_power_trend === 0) {
        trendIcon = '<i class="ph ph-minus"></i>';
        trendColor = 'color: var(--text-muted)';
    }

    const costsPeriod = kpis.costs_period ? kpis.costs_period : kpis.reference_year;
    const powerPeriod = kpis.power_period ? kpis.power_period : kpis.reference_year;

    container.innerHTML = `
        <div class="dashboard-card glass-panel" style="padding: 20px; border-left: 4px solid var(--success-color);">
            <div style="font-size: 0.9em; color: var(--text-muted); margin-bottom: 8px;">Überschuss im laufenden Jahr (${new Date().getFullYear()})</div>
            <div style="font-size: 1.8em; font-weight: 600; color: ${kpis.cashflow_ytd >= 0 ? 'var(--success-color)' : 'var(--danger-color)'}">
                ${kpis.cashflow_ytd.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}
            </div>
        </div>
        <div class="dashboard-card glass-panel kpi-clickable" id="kpi-costs-card" onclick="openCostsHistory()" style="padding: 20px; border-left: 4px solid var(--primary-color); cursor: pointer; transition: transform 0.15s, box-shadow 0.15s;" onmouseenter="this.style.transform='translateY(-2px)';this.style.boxShadow='0 4px 12px rgba(0,0,0,0.1)'" onmouseleave="this.style.transform='none';this.style.boxShadow='none'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 0.9em; color: var(--text-muted); margin-bottom: 4px;">Betriebskosten</div>
                <i class="ph ph-clock-counter-clockwise" style="color: var(--text-muted); font-size: 1.1em;" title="Verlauf anzeigen"></i>
            </div>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">${escapeHtml(costsPeriod)}</div>
            <div style="font-size: 1.8em; font-weight: 600; color: var(--text-color)">
                ${kpis.total_costs_last_year.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}
            </div>
        </div>
        <div class="dashboard-card glass-panel kpi-clickable" id="kpi-power-card" onclick="openPowerHistory()" style="padding: 20px; border-left: 4px solid var(--warning-color); cursor: pointer; transition: transform 0.15s, box-shadow 0.15s;" onmouseenter="this.style.transform='translateY(-2px)';this.style.boxShadow='0 4px 12px rgba(0,0,0,0.1)'" onmouseleave="this.style.transform='none';this.style.boxShadow='none'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 0.9em; color: var(--text-muted); margin-bottom: 4px;">Allgemeinstrom</div>
                <i class="ph ph-clock-counter-clockwise" style="color: var(--text-muted); font-size: 1.1em;" title="Verlauf anzeigen"></i>
            </div>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">${escapeHtml(powerPeriod)}</div>
            <div style="font-size: 1.8em; font-weight: 600; color: var(--text-color); display: flex; align-items: baseline; gap: 8px;">
                ${window.wrapInterpolated(kpis.general_power.toLocaleString('de-DE'), kpis.general_power_is_interpolated !== false)} <span style="font-size: 13px; font-weight: 400;">kWh</span>
                <span style="font-size: 13px; ${trendColor}">${trendIcon} ${Math.abs(kpis.general_power_trend).toLocaleString('de-DE')}%</span>
            </div>
        </div>
        <div class="dashboard-card glass-panel" style="padding: 20px; border-left: 4px solid var(--danger-color);">
            <div style="font-size: 0.9em; color: var(--text-muted); margin-bottom: 8px;">Ausstehende Abrechnungen</div>
            <div style="font-size: 1.8em; font-weight: 600; color: ${kpis.open_tasks > 0 ? 'var(--danger-color)' : 'var(--success-color)'}">
                ${kpis.open_tasks}
            </div>
        </div>
    `;
    
    // Store KPI data globally for onclick access
    window._kpiCostsHistory = kpis.costs_history;
    window._kpiPowerHistory = kpis.power_history;
}

function openCostsHistory() {
    showKpiHistoryModal('Betriebskosten – Jahresverlauf', window._kpiCostsHistory, '€');
}

function openPowerHistory() {
    showKpiHistoryModal('Allgemeinstrom – Jahresverlauf', window._kpiPowerHistory, 'kWh');
}

function showKpiHistoryModal(title, historyData, unit) {
    const modal = document.getElementById('kpi-history-modal');
    document.getElementById('kpi-history-modal-title').textContent = title;
    const content = document.getElementById('kpi-history-modal-content');
    
    if (!historyData || historyData.length === 0) {
        content.innerHTML = '<p style="color: var(--text-muted); text-align: center;">Keine historischen Daten vorhanden.</p>';
        modal.classList.add('active');
        return;
    }
    
    let rows = '';
    historyData.forEach((entry, idx) => {
        const isLast = idx === historyData.length - 1;
        const bgColor = isLast ? 'background: rgba(99, 102, 241, 0.08);' : '';
        const fontWeight = isLast ? 'font-weight: 600;' : '';
        const valueStr = unit === '€'
            ? entry.value.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})
            : entry.value.toLocaleString('de-DE') + ' ' + (entry.unit || unit);
        const period = entry.period || entry.year;
        rows += `
            <tr style="${bgColor}">
                <td style="padding: 10px 12px; ${fontWeight}">${escapeHtml(entry.year)}</td>
                <td style="padding: 10px 12px; color: var(--text-muted); font-size: 0.85em;">${escapeHtml(period)}</td>
                <td style="padding: 10px 12px; text-align: right; ${fontWeight}">${escapeHtml(valueStr)}</td>
            </tr>
        `;
    });
    
    content.innerHTML = `
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="border-bottom: 2px solid var(--border-color);">
                    <th style="padding: 8px 12px; text-align: left; font-size: 0.85em; color: var(--text-muted);">Jahr</th>
                    <th style="padding: 8px 12px; text-align: left; font-size: 0.85em; color: var(--text-muted);">Zeitraum</th>
                    <th style="padding: 8px 12px; text-align: right; font-size: 0.85em; color: var(--text-muted);">Wert</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
    modal.classList.add('active');
}

let cachedTimeseriesData = [];
function renderBuildingTimeseries(timeseries_data) {
    cachedTimeseriesData = timeseries_data;
    
    const pills = document.querySelectorAll('#chart-building-filters .filter-pill');
    pills.forEach(pill => {
        const newPill = pill.cloneNode(true);
        pill.parentNode.replaceChild(newPill, pill);
        newPill.addEventListener('click', (e) => {
            // Zustand nur ueber die Klasse (CSS .filter-pill.active), nicht
            // ueber Inline-Styles — sonst uebermalt der Code das Design-System.
            document.querySelectorAll('#chart-building-filters .filter-pill').forEach(p => {
                p.classList.remove('active');
            });
            e.target.classList.add('active');
            drawTimeseriesChart(e.target.dataset.filter);
        });
    });
    
    drawTimeseriesChart('Alle Kosten');
}

function drawTimeseriesChart(filter) {
    const ctx = document.getElementById('chart-building-timeseries').getContext('2d');
    if (chartBuildingTimeseriesInstance) chartBuildingTimeseriesInstance.destroy();
    
    const bucketColors = {
        'Strom': DIAGRAMM_FARBE.gelb,
        'Gas': DIAGRAMM_FARBE.rot,
        'Wasser': DIAGRAMM_FARBE.blau,
        'Sonstige Kosten': DIAGRAMM_FARBE.lila
    };
    
    let filteredData = cachedTimeseriesData;
    let showCost = true;
    let yAxisTitle = 'Kosten in €';
    let tooltipUnit = '€';
    let isStacked = false;
    
    if (filter === 'Alle Kosten') {
        isStacked = true;
    } else {
        filteredData = cachedTimeseriesData.filter(d => d.category === filter);
    }
    
    const yearsSet = new Set();
    filteredData.forEach(d => yearsSet.add(d.year));
    const years = Array.from(yearsSet).sort();
    
    // Build multi-line labels with date ranges
    const labels = years.map(y => {
        const entries = filteredData.filter(d => d.year === y);
        const period = entries.find(e => e.period)?.period || '';
        if (period && period !== String(y)) {
            // Show compact period: "01.01.24 - 31.12.24"
            const parts = period.split(' - ');
            if (parts.length === 2) {
                return [String(y), parts[0].substring(0, 6) + '-' + parts[1].substring(0, 6)];
            }
        }
        return String(y);
    });
    
    // Store period data for tooltips
    const periodMap = {};
    filteredData.forEach(d => {
        if (d.period) periodMap[d.year + '_' + d.category] = d.period;
    });
    
    const categoriesSet = new Set();
    filteredData.forEach(d => categoriesSet.add(d.category));
    
    const datasets = [];
    
    categoriesSet.forEach(cat => {
        const data = years.map(y => {
            const entry = filteredData.find(d => d.year === y && d.category === cat);
            if (!entry) return 0;
            return showCost ? entry.cost : entry.consumption;
        });
        
        datasets.push({
            label: cat,
            data: data,
            backgroundColor: bucketColors[cat] || DIAGRAMM_FARBE.grau
        });
    });
    
    chartBuildingTimeseriesInstance = new Chart(ctx, {
        type: 'bar',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { stacked: isStacked },
                y: {
                    stacked: isStacked,
                    title: { display: true, text: yAxisTitle },
                    ticks: {
                        callback: function(value) {
                            if (showCost) return value.toLocaleString('de-DE', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0});
                            return value.toLocaleString('de-DE');
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: function(contexts) {
                            const idx = contexts[0].dataIndex;
                            const year = years[idx];
                            const cat = contexts[0].dataset.label;
                            const period = periodMap[year + '_' + cat] || periodMap[year + '_' + Object.keys(periodMap).find(k => k.startsWith(year + '_'))?.split('_')[1]] || year;
                            return 'Zeitraum: ' + period;
                        },
                        label: function(context) {
                            const val = context.raw;
                            if (showCost) {
                                return context.dataset.label + ': ' + val.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'});
                            }
                            return context.dataset.label + ': ' + val.toLocaleString('de-DE') + ' ' + tooltipUnit;
                        }
                    }
                }
            }
        }
    });
}

function renderBuildingComparison(apartment_comparison) {
    const ctx = document.getElementById('chart-building-comparison').getContext('2d');
    if (chartBuildingComparisonInstance) chartBuildingComparisonInstance.destroy();
    
    const titleEl = document.getElementById('chart-comparison-title');
    // Leerhinweis neben der Zeichenfläche, nicht an ihrer Stelle: kommen
    // später Daten, muss die Fläche noch da sein (NK-157).
    const leerHinweis = document.getElementById('chart-building-comparison-leer');
    const leer = !apartment_comparison || apartment_comparison.length === 0;
    ctx.canvas.hidden = leer;
    leerHinweis.hidden = !leer;

    if (leer) {
        titleEl.textContent = 'Wohnungsvergleich';
        return;
    }
    
    // Show reading period range in title
    const periods = apartment_comparison.filter(d => d.period).map(d => d.period);
    if (periods.length > 0) {
        titleEl.textContent = 'Wohnungsvergleich (Ablesung)';
    } else {
        titleEl.textContent = 'Wohnungsvergleich';
    }
    
    const bucketColors = {
        'Strom': DIAGRAMM_FARBE.gelb,
        'Gas': DIAGRAMM_FARBE.rot,
        'Wasser': DIAGRAMM_FARBE.blau,
        'Sonstige Kosten': DIAGRAMM_FARBE.lila
    };
    
    const aptsSet = new Set();
    const categoriesSet = new Set();
    
    apartment_comparison.forEach(d => {
        aptsSet.add(d.apartment);
        categoriesSet.add(d.category);
    });
    
    const apartments = Array.from(aptsSet).sort();
    const datasets = [];
    
    // Build period lookup for tooltips
    const aptPeriodMap = {};
    apartment_comparison.forEach(d => {
        if (d.period) aptPeriodMap[d.apartment + '_' + d.category] = d.period;
    });
    
    categoriesSet.forEach(cat => {
        const data = apartments.map(apt => {
            const entry = apartment_comparison.find(d => d.apartment === apt && d.category === cat);
            return entry ? entry.consumption : 0;
        });
        
        const sampleEntry = apartment_comparison.find(d => d.category === cat);
        const unit = sampleEntry ? sampleEntry.unit : '';
        
        datasets.push({
            label: cat + ` (${unit})`,
            data: data,
            backgroundColor: bucketColors[cat] || DIAGRAMM_FARBE.grau
        });
    });
    
    chartBuildingComparisonInstance = new Chart(ctx, {
        type: 'bar',
        data: { labels: apartments, datasets: datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { stacked: false },
                y: {
                    stacked: false,
                    title: { display: true, text: 'Verbrauch' },
                    ticks: {
                        callback: function(value) {
                            return value.toLocaleString('de-DE');
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: function(contexts) {
                            const apt = apartments[contexts[0].dataIndex];
                            const cat = contexts[0].dataset.label.split(' (')[0];
                            const period = aptPeriodMap[apt + '_' + cat] || '';
                            return period ? apt + ' (' + period + ')' : apt;
                        },
                        label: function(context) {
                            return context.dataset.label + ': ' + context.raw.toLocaleString('de-DE');
                        }
                    }
                }
            }
        }
    });
}

function renderAptConsumptionChart(ownConsumptionData) {
    const container = document.getElementById('apt-consumption-cards');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!ownConsumptionData || ownConsumptionData.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); text-align: center; width: 100%; grid-column: 1 / -1; padding: 20px;">Keine Verbrauchsdaten vorhanden.</div>';
        return;
    }
    
    const sortedData = [...ownConsumptionData].sort((a, b) => {
        const parseDate = str => {
            const parts = str.split(' - ')[0].split('.');
            return new Date(parts[2], parts[1] - 1, parts[0]);
        };
        return parseDate(a.period) - parseDate(b.period);
    });
    
    const groupedData = {};
    sortedData.forEach(d => {
        if (!groupedData[d.category]) {
            groupedData[d.category] = {
                category: d.category,
                unit: d.unit,
                totalValue: 0,
                periods: []
            };
        }
        groupedData[d.category].totalValue += d.value;
        groupedData[d.category].periods.push({
            period: d.period,
            value: d.value
        });
    });
    
    // NK-156: Phosphor statt Emoji (K3/K9, einheitliche Symbole).
    const getIcon = (cat) => {
        const c = cat.toLowerCase();
        const klasse = c.includes('gas') || c.includes('heiz') ? 'ph-flame' : getCategoryIcon(cat);
        return `<i class="ph ${klasse}" aria-hidden="true"></i>`;
    };
    
    Object.values(groupedData).forEach(group => {
        const card = document.createElement('div');
        card.style.cssText = 'background-color: white; border-radius: 12px; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); border: 1px solid var(--border-color); padding: 20px; display: flex; flex-direction: column; justify-content: center;';
        
        const header = document.createElement('div');
        header.style.cssText = 'color: var(--text-muted); font-weight: 500; font-size: 14px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;';
        header.innerHTML = `<span class="verbrauch-symbol">${getIcon(group.category)}</span><span>${escapeHtml(group.category)}</span>`;
        
        const valueDiv = document.createElement('div');
        valueDiv.style.cssText = 'color: var(--text-main); font-size: 30px; font-weight: 700; text-align: center; margin: 10px 0;';
        const latestValue = group.periods[group.periods.length - 1].value;
        valueDiv.innerText = `${latestValue.toLocaleString('de-DE')} ${escapeHtml(group.unit)}`;
        
        const footer = document.createElement('div');
        footer.style.cssText = 'color: var(--text-muted); font-size: 13px; margin-top: 12px; text-align: center; display: flex; flex-direction: column; gap: 4px;';
        
        if (group.periods.length === 1) {
            footer.innerText = `Ablesezeitraum: ${group.periods[0].period}`;
        } else {
            let periodsHtml = '<div style="font-weight: 500; margin-bottom: 4px;">Zeiträume:</div>';
            group.periods.forEach(p => {
                periodsHtml += `<div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 2px;">
                    <span>${escapeHtml(p.period)}</span>
                    <span style="font-weight: 500;">${p.value.toLocaleString('de-DE')} ${escapeHtml(group.unit)}</span>
                </div>`;
            });
            footer.innerHTML = periodsHtml;
            footer.style.textAlign = 'left';
        }
        
        card.appendChild(header);
        card.appendChild(valueDiv);
        card.appendChild(footer);
        container.appendChild(card);
    });
}

function renderAptCostsChart(costDistribution) {
    const ctx = document.getElementById('chart-apt-costs').getContext('2d');
    const canvas = document.getElementById('chart-apt-costs');
    const emptyState = document.getElementById('chart-apt-costs-empty');
    if (chartAptCostsInstance) chartAptCostsInstance.destroy();
    
    let total = 0;
    Object.values(costDistribution).forEach(v => total += v);
    
    if (total === 0) {
        canvas.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }
    
    canvas.style.display = 'block';
    emptyState.style.display = 'none';
    
    const labels = Object.keys(costDistribution);
    const data = Object.values(costDistribution);
    const colors = [DIAGRAMM_FARBE.rot, DIAGRAMM_FARBE.blau, DIAGRAMM_FARBE.gruen,
        DIAGRAMM_FARBE.gelb, DIAGRAMM_FARBE.lila];
    
    chartAptCostsInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors.slice(0, labels.length)
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.label + ': ' + context.raw.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
                        }
                    }
                }
            }
        }
    });
}

// --- Danger Zone ---
async function resetDatabase() {
    const confirm1 = await frageLoeschen("Achtung\n\nMöchten Sie wirklich die gesamte Datenbank löschen und auf den Werkszustand zurücksetzen?");
    if (!confirm1) return;
    
    const confirm2 = await frageLoeschen("Sind Sie wirklich sicher?\nAlle Zählerstände, Rechnungen, Immobilien und Mieter gehen unwiderruflich verloren. Dies kann nicht rückgängig gemacht werden!");
    if (!confirm2) return;
    
    // NK-123: die Route verlangt das Geheimnis im Kopf der Anfrage
    // (X-Debug-Secret, NK-001). Ohne ihn antwortet sie mit 401.
    const geheimnis = await fragePassphrase('Entwickler-Geheimnis',
        'X-Debug-Secret; steht in der Umgebungsdatei als DEBUG_RESET_SECRET.', false, 'Geheimnis');
    if (geheimnis === null) return;
    
    try {
        const res = await fetch('/api/debug/reset_db', {
            method: 'POST',
            headers: { 'X-Debug-Secret': geheimnis }
        });
        const data = await res.json().catch(() => ({}));
        
        if (res.ok) {
            showSuccess("Erfolg: " + data.message);
            window.location.reload();
        } else if (res.status === 404) {
            showError("Zurücksetzen ist in diesem Build nicht vorhanden (Entwicklerroute fehlt).");
        } else if (res.status === 401) {
            showError("Geheimnis falsch -- die Datenbank wurde nicht verändert.");
        } else {
            showError("Fehler beim Zurücksetzen der Datenbank.");
        }
    } catch (e) {
        console.error(e);
        showError("Netzwerkfehler beim Zurücksetzen.");
    }
}

// --- Passphrase-Dialog (NK-130) ---
let passphraseErledigt = null;

function fragePassphrase(titel, text, mitWiederholung = false, feld = 'Passphrase') {
    document.getElementById('passphrase-titel').textContent = titel;
    document.querySelector('label[for="passphrase-eingabe"]').textContent = feld;
    document.getElementById('passphrase-text').textContent = text;
    document.getElementById('passphrase-eingabe').value = '';
    document.getElementById('passphrase-wiederholung').value = '';
    document.getElementById('passphrase-wiederholung-gruppe').style.display =
        mitWiederholung ? '' : 'none';
    document.getElementById('passphrase-modal').classList.add('active');
    document.getElementById('passphrase-eingabe').focus();
    return new Promise(erledigt => { passphraseErledigt = erledigt; });
}

function passphraseAntwort(wert) {
    document.getElementById('passphrase-modal').classList.remove('active');
    const erledigt = passphraseErledigt;
    passphraseErledigt = null;
    if (erledigt) erledigt(wert);
}

function passphraseBestaetigen() {
    const eins = document.getElementById('passphrase-eingabe').value;
    const gruppe = document.getElementById('passphrase-wiederholung-gruppe');
    if (gruppe.style.display !== 'none' &&
        eins !== document.getElementById('passphrase-wiederholung').value) {
        showError('Die beiden Passphrasen stimmen nicht überein.');
        return;
    }
    passphraseAntwort(eins);
}
window.passphraseAntwort = passphraseAntwort;
window.passphraseBestaetigen = passphraseBestaetigen;

// --- Export Data ---
async function exportData() {
    try {
        const btn = document.querySelector('button[onclick="exportData()"]');
        const oldHtml = btn.innerHTML;
        btn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Daten werden exportiert...';
        btn.disabled = true;

        // NK-130: der Export verlaesst den Rechner -- verschluesselt
        // empfohlen. Leer lassen heisst Klartext (JSON).
        const passphrase = await fragePassphrase('Daten exportieren',
            'Geben Sie eine Passphrase ein, um den Export zu verschlüsseln (empfohlen, ' +
            'mindestens 12 Zeichen). Ohne Passphrase entsteht eine lesbare JSON-Datei.', true);
        if (passphrase === null) {
            btn.innerHTML = oldHtml;
            btn.disabled = false;
            return;
        }
        let blob;
        let dateiname;
        const heute = new Date().toISOString().split('T')[0];
        if (passphrase) {
            const res = await fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ passphrase })
            });
            if (!res.ok) throw await serverFehler(res);
            blob = await res.blob();
            dateiname = `nebenkosten-export-${heute}.nkexp`;
        } else {
            const res = await fetch('/api/export');
            if (!res.ok) throw await serverFehler(res);
            const data = await res.json();
            blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            dateiname = `nebenkosten-export-${heute}.json`;
        }
        await huelle.blobSpeichern(blob, dateiname);

        btn.innerHTML = oldHtml;
        btn.disabled = false;
    } catch(e) {
        showError(meldungZu(e, 'Fehler beim Exportieren der Daten.'));
        console.error(e);
        const btn = document.querySelector('button[onclick="exportData()"]');
        if(btn) {
            btn.innerHTML = '<i class="ph ph-download-simple"></i> Daten exportieren';
            btn.disabled = false;
        }
    }
}

// --- Payments ---
async function fetchPayments() {
    try {
        const res = await fetch('/api/payments');
        if (!res.ok) throw await serverFehler(res);
        payments = await res.json();
        renderPayments();
        updateDashboard();
    } catch (e) {
        console.error(e);
    }
}

function renderPayments() {
    if (!paymentsGrid) return;
    paymentsGrid.replaceChildren();
    
    if (payments.length === 0) {
        paymentsGrid.innerHTML = leerzustand({
            icon: 'ph-coins',
            titel: 'Noch keine Zahlungen erfasst',
            text: 'Erfassen Sie, was Mieter gezahlt haben — Miete, Nebenkostenvorauszahlung oder Kaution.',
            aktion: { label: 'Zahlung erfassen', fn: 'openAddPaymentModal()', icon: 'ph-plus' },
        });
        return;
    }
    
    // Group by tenant
    const tenantGroups = {};
    payments.forEach(p => {
        if (!tenantGroups[p.tenant_id]) {
            tenantGroups[p.tenant_id] = {
                tenant_id: p.tenant_id,
                tenant_name: p.tenant_name,
                payments: [],
                latestMiete: 0,
                latestNK: 0,
                kaution: 0
            };
        }
        tenantGroups[p.tenant_id].payments.push(p);
    });
    
    Object.values(tenantGroups).forEach(group => {
        // Sort payments by date descending
        group.payments.sort((a, b) => new Date(b.payment_date) - new Date(a.payment_date));
        
        const mietePayments = group.payments.filter(p => p.type === 'Miete');
        if (mietePayments.length > 0) group.latestMiete = mietePayments[0].amount;
        
        const nkPayments = group.payments.filter(p => p.type === 'Nebenkostenvorauszahlung');
        if (nkPayments.length > 0) group.latestNK = nkPayments[0].amount;
        
        const kautionPayments = group.payments.filter(p => p.type === 'Kaution');
        if (kautionPayments.length > 0) group.kaution = kautionPayments[0].amount;
        
        const totalMonthly = group.latestMiete + group.latestNK;
        
        const card = document.createElement('div');
        card.className = 'property-card glass-panel';
        
        card.innerHTML = `
            <div class="prop-header">
                <div class="prop-icon"><i class="ph ph-user"></i></div>
                <button class="btn-icon" onclick="openPaymentDetailsModal(${group.tenant_id})" title="Details & Bearbeiten">
                    <i class="ph ph-list-magnifying-glass"></i>
                </button>
            </div>
            <h3 class="prop-title">${escapeHtml(group.tenant_name)}</h3>
            <div class="prop-meta" style="flex-direction: column; align-items: flex-start; gap: 8px;">
                <div style="display: flex; justify-content: space-between; width: 100%;">
                    <span>Miete:</span>
                    <strong>${group.latestMiete.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; width: 100%;">
                    <span>Nebenkosten:</span>
                    <strong>${group.latestNK.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}</strong>
                </div>
                ${group.kaution > 0 ? `
                <div style="display: flex; justify-content: space-between; width: 100%; color: var(--text-muted); font-size: 13px;">
                    <span>Kaution:</span>
                    <span>${group.kaution.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}</span>
                </div>
                ` : ''}
                <hr style="width: 100%; border: 0; border-top: 1px solid var(--border-color); margin: 4px 0;">
                <div style="display: flex; justify-content: space-between; width: 100%; color: var(--text-color);">
                    <span><strong>Gesamt (mtl.):</strong></span>
                    <strong style="color: var(--primary-color);">${totalMonthly.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}</strong>
                </div>
            </div>
        `;
        paymentsGrid.appendChild(card);
    });
}

function openPaymentDetailsModal(tenantId) {
    // Speichere tenantId global für den Fall, dass alle Zahlungen gelöscht werden, 
    // damit wir referenz haben für refreshs.
    paymentDetailsModal.dataset.tenantId = tenantId;
    
    const tenantPayments = payments.filter(p => p.tenant_id === tenantId);
    tenantPayments.sort((a, b) => new Date(b.payment_date) - new Date(a.payment_date));
    
    if (tenantPayments.length > 0) {
        paymentDetailsTitle.textContent = `Einnahmen: ${tenantPayments[0].tenant_name}`;
    }
    
    paymentDetailsList.replaceChildren();
    document.getElementById('payment-select-all').checked = false;
    toggleDeleteSelectedButton();
    
    if (tenantPayments.length === 0) {
        paymentDetailsList.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 24px;">Keine Zahlungen vorhanden.</td></tr>';
    } else {
        tenantPayments.forEach(p => {
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            
            // Allow row click to toggle checkbox
            tr.onclick = (e) => {
                if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'BUTTON' && e.target.tagName !== 'I') {
                    const cb = tr.querySelector('.payment-row-cb');
                    if (cb) {
                        cb.checked = !cb.checked;
                        toggleDeleteSelectedButton();
                    }
                }
            };

            const pDate = new Date(p.payment_date);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const isFuture = pDate > today;
            
            if (isFuture) {
                tr.style.opacity = '0.6';
                tr.style.fontStyle = 'italic';
                tr.title = 'Diese Einnahme liegt in der Zukunft (Prognose)';
            }

            const dateStr = p.payment_date ? new Date(p.payment_date).toLocaleDateString('de-DE') : '-';
            tr.innerHTML = `
                <td style="text-align: center;"><input type="checkbox" class="payment-row-cb" value="${p.id}" onchange="toggleDeleteSelectedButton()"></td>
                <td style="padding: 12px 16px;">${dateStr}${isFuture ? ' <i class="ph ph-clock text-secondary" style="font-size: 0.9em; margin-left: 4px;" title="Zukunft"></i>' : ''}</td>
                <td><span class="badge ${p.type === 'Miete' ? 'badge-primary' : (p.type === 'Nebenkostenvorauszahlung' ? 'badge-info' : 'badge-secondary')}" style="font-size: 0.85em; padding: 4px 8px;">${escapeHtml(p.type)}</span></td>
                <td style="text-align: right; font-weight: 500;">${p.amount.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'})}</td>
                <td style="text-align: center; width: 60px;">
                    <button class="btn-icon" onclick="deletePayment(${p.id})" title="Löschen"><i class="ph ph-trash" style="color: var(--danger-color);"></i></button>
                </td>
            `;
            paymentDetailsList.appendChild(tr);
        });
    }
    
    paymentDetailsModal.classList.add('active');
}

function toggleAllPaymentSelection(masterCheckbox) {
    const checkboxes = document.querySelectorAll('.payment-row-cb');
    checkboxes.forEach(cb => cb.checked = masterCheckbox.checked);
    toggleDeleteSelectedButton();
}

function toggleDeleteSelectedButton() {
    const checkboxes = document.querySelectorAll('.payment-row-cb:checked');
    const btn = document.getElementById('btn-delete-selected-payments');
    if (checkboxes.length > 0) {
        btn.style.display = 'inline-flex';
        btn.innerHTML = `<i class="ph ph-trash"></i> ${checkboxes.length} markierte löschen`;
    } else {
        btn.style.display = 'none';
    }
}

async function deleteSelectedPayments() {
    const checkboxes = document.querySelectorAll('.payment-row-cb:checked');
    if (checkboxes.length === 0) return;
    
    if (!await frageLoeschen(`Möchten Sie wirklich ${checkboxes.length} Zahlungen löschen?`)) return;
    
    const ids = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    try {
        const btn = document.getElementById('btn-delete-selected-payments');
        btn.disabled = true;
        btn.textContent = 'Lösche...';
        
        const res = await fetch('/api/payments/bulk', {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ids })
        });
        
        if (!res.ok) throw await serverFehler(res);
        
        showSuccess(`${ids.length} Zahlungen erfolgreich gelöscht.`);
        
        // Refresh
        await fetchPayments();
        
        // Re-render modal
        const tenantId = parseInt(paymentDetailsModal.dataset.tenantId);
        if (tenantId) openPaymentDetailsModal(tenantId);
        
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Fehler beim Löschen der Zahlungen.'));
    } finally {
        const btn = document.getElementById('btn-delete-selected-payments');
        btn.disabled = false;
    }
}

function closePaymentDetailsModal() {
    paymentDetailsModal.classList.remove('active');
}

function openAddPaymentModal() {
    const tenantSelect = document.getElementById('payment-tenant');
    tenantSelect.replaceChildren();
    const def = document.createElement('option');
    def.value = '';
    def.textContent = 'Bitte wählen...';
    tenantSelect.appendChild(def);
    
    tenants.forEach(t => {
        const apt = allApartments.find(a => a.id === t.apartment_id);
        const aptName = apt ? apt.name : `Apt: ${t.apartment_id}`;
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `${t.name} (${aptName})`;
        tenantSelect.appendChild(opt);
    });
    
    document.getElementById('payment-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('payment-amount').value = '';
    document.getElementById('payment-type').value = 'Miete';
    
    document.getElementById('payment-recurring').checked = false;
    document.getElementById('payment-end-date').value = '';
    togglePaymentRecurring();
    toggleBillingReportField();
    
    // Add event listener to tenant select to refetch reports if needed
    tenantSelect.onchange = toggleBillingReportField;
    
    paymentModal.classList.add('active');
}

function closeAddPaymentModal() {
    paymentModal.classList.remove('active');
}

async function toggleBillingReportField() {
    const typeSelect = document.getElementById('payment-type').value;
    const group = document.getElementById('group-billing-report');
    const tenantId = document.getElementById('payment-tenant').value;
    const reportSelect = document.getElementById('payment-billing-report');
    const recurringCheckbox = document.getElementById('payment-recurring');
    
    if (typeSelect === 'Nebenkostenzahlung') {
        recurringCheckbox.checked = false;
        recurringCheckbox.disabled = true;
        togglePaymentRecurring();
        
        group.style.display = 'block';
        reportSelect.innerHTML = '<option value="">Lade Abrechnungen...</option>';
        if (tenantId) {
            try {
                const res = await fetch(`/api/tenants/${tenantId}/billing_reports`);
                const reports = await res.json();
                reportSelect.innerHTML = '<option value="">Bitte wählen...</option>';
                reports.forEach(r => {
                    const opt = document.createElement('option');
                    opt.value = r.id;
                    opt.textContent = `Abrechnung ${r.start_date} bis ${r.end_date}`;
                    reportSelect.appendChild(opt);
                });
                
                reportSelect.onchange = async () => {
                    const selectedId = reportSelect.value;
                    if (selectedId) {
                        try {
                            const detailsRes = await fetch(`/api/billing/reports/${selectedId}/details`);
                            const umschlag = await detailsRes.json();
                            // Der Saldo steckt im Schnappschuss ("ergebnis") und ist Text.
                            const saldo = Number((umschlag.ergebnis || umschlag).balance);
                            if (saldo) {
                                document.getElementById('payment-amount').value = saldo.toFixed(2);
                            }
                        } catch(e) {
                            console.error('Failed to load balance', e);
                        }
                    }
                };
            } catch (e) {
                reportSelect.innerHTML = '<option value="">Fehler beim Laden</option>';
            }
        } else {
            reportSelect.innerHTML = '<option value="">Bitte erst Mieter wählen</option>';
        }
    } else {
        recurringCheckbox.disabled = false;
        group.style.display = 'none';
        reportSelect.value = '';
        reportSelect.onchange = null;
    }
}

function togglePaymentRecurring() {
    const isRecurring = document.getElementById('payment-recurring').checked;
    const endDateGroup = document.getElementById('group-payment-end-date');
    const dateLabel = document.getElementById('label-payment-date');
    
    if (isRecurring) {
        endDateGroup.style.display = 'block';
        dateLabel.textContent = 'Startmonat';
    } else {
        endDateGroup.style.display = 'none';
        dateLabel.textContent = 'Datum';
        document.getElementById('payment-end-date').value = '';
    }
}

async function savePayment() {
    const tenantId = document.getElementById('payment-tenant').value;
    const amount = document.getElementById('payment-amount').value;
    const date = document.getElementById('payment-date').value;
    const type = document.getElementById('payment-type').value;
    const isRecurring = document.getElementById('payment-recurring').checked;
    const endDate = document.getElementById('payment-end-date').value;
    const billingReportId = document.getElementById('payment-billing-report').value;
    
    if (!tenantId || !amount || !date) {
        showError('Bitte alle Felder ausfüllen.');
        return;
    }
    
    try {
        const res = await fetch('/api/payments', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                tenant_id: tenantId,
                amount: parseFloat(amount),
                payment_date: date,
                type: type,
                is_recurring: isRecurring,
                end_date: endDate || null,
                billing_report_id: billingReportId || null
            })
        });
        if (!res.ok) throw await serverFehler(res);
        closeAddPaymentModal();
        showSuccess('Zahlung erfolgreich erfasst.');
        fetchPayments();
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Speichern der Zahlung.'));
    }
}

async function deletePayment(id) {
    if (!await frageLoeschen('Zahlung wirklich löschen?')) return;
    try {
        const res = await fetch(`/api/payments/${id}`, { method: 'DELETE' });
        if (!res.ok) throw await serverFehler(res);
        showSuccess('Zahlung gelöscht.');
        
        // Remove from local array to update the details modal immediately without closing it
        payments = payments.filter(p => p.id !== id);
        renderPayments();
        updateDashboard();
        
        // If details modal is open, re-render it
        if (paymentDetailsModal.classList.contains('active')) {
            const tenantId = parseInt(paymentDetailsModal.dataset.tenantId);
            if (tenantId) openPaymentDetailsModal(tenantId);
        }
        
    } catch (e) {
        showError(meldungZu(e, 'Fehler beim Löschen der Zahlung.'));
    }
}

// --- Ebene 2: Interpolation Audit ---
async function openInterpolationAudit(meter_id, start_date, end_date) {
    // Prevent event bubbling if clicked from a card
    if (window.event) window.event.stopPropagation();
    
    try {
        const res = await fetch(`/api/billing/interpolation-audit?meter_id=${meter_id}&start_date=${start_date}&end_date=${end_date}`);
        if (!res.ok) throw await serverFehler(res);
        const data = await res.json();
        
        const modal = document.getElementById('interpolation-audit-modal');
        const body = document.getElementById('interpolation-audit-body');
        
        // Parse dates
        const parseD = (s) => new Date(s);
        const tStart = parseD(data.target_start_date);
        const tEnd = parseD(data.target_end_date);
        const basis = data.basis_readings || [];
        
        if (basis.length < 2) {
            body.innerHTML = '<p>Nicht genügend Basis-Ablesungen gefunden.</p>';
            modal.classList.add('active');
            return;
        }
        
        const rStart = parseD(basis[0].date);
        const rEnd = parseD(basis[basis.length - 1].date);
        
        // Total global span
        const totalSpan = (rEnd - rStart) / (1000 * 60 * 60 * 24);
        
        // Calculate percentages for timeline (0% = rStart, 100% = rEnd)
        const getPct = (d) => {
            const days = (parseD(d) - rStart) / (1000 * 60 * 60 * 24);
            return Math.min(100, Math.max(0, (days / totalSpan) * 100));
        };
        
        const targetStartPct = getPct(data.target_start_date);
        const targetEndPct = getPct(data.target_end_date);
        const targetWidth = targetEndPct - targetStartPct;
        
        let timelineHtml = `
        <div style="margin-bottom: 24px;">
            <h3>Visuelle Timeline</h3>
            <div class="timeline-container">
                <div class="timeline-axis"></div>
                <!-- Global Reading Span (Grau) -->
                <div class="timeline-bar-reading" style="left: 0%; width: 100%;"></div>
                
                <!-- Basis Readings Markers -->
                ${basis.map(r => {
                    const pct = getPct(r.date);
                    return `
                    <div class="timeline-marker" style="left: ${pct}%;">
                        <div>${new Date(r.date).toLocaleDateString('de-DE')}</div>
                        <div style="font-weight:600;">${r.total.toFixed(1)} ${escapeHtml(data.unit)}</div>
                    </div>`;
                }).join('')}
                
                <!-- Target Span (Blau) -->
                <div class="timeline-bar-target" style="left: ${targetStartPct}%; width: ${targetWidth}%;" title="Abrechnungszeitraum"></div>
                
                <!-- Target Span Marker -->
                <div class="timeline-marker" style="left: ${targetStartPct}%; top: 60px; color: var(--primary);">
                    <div>Start Abrechnung</div>
                    <div style="font-weight:600;">${new Date(data.target_start_date).toLocaleDateString('de-DE')}</div>
                </div>
                <div class="timeline-marker" style="left: ${targetEndPct}%; top: 60px; color: var(--primary);">
                    <div>Ende Abrechnung</div>
                    <div style="font-weight:600;">${new Date(data.target_end_date).toLocaleDateString('de-DE')}</div>
                </div>
                
                <!-- Overlaps -->
                `;
                
        // Calculate overlaps for visual and table
        let tableRows = '';
        let stepCount = 1;
        let totalConsumption = 0;
        
        for (let i = 0; i < basis.length - 1; i++) {
            const b1 = basis[i];
            const b2 = basis[i+1];
            const d1 = parseD(b1.date);
            const d2 = parseD(b2.date);
            
            // intervalDays matches python's (r2.reading_date - r1.reading_date).days
            const intervalDays = (d2 - d1) / (1000 * 60 * 60 * 24);
            const intervalConsumption = b2.total - b1.total;
            const dailyRate = intervalDays > 0 ? intervalConsumption / intervalDays : 0;
            
            const overlapStart = new Date(Math.max(tStart, d1));
            // Python's target_end_date internally adds +1 day for inclusive range matching
            const pythonTargetEnd = new Date(tEnd.getTime() + (1000 * 60 * 60 * 24));
            const overlapEnd = new Date(Math.min(pythonTargetEnd, d2));
            const overlapDays = (overlapEnd - overlapStart) / (1000 * 60 * 60 * 24);
            
            if (overlapDays > 0) {
                const partConsumption = dailyRate * overlapDays;
                totalConsumption += partConsumption;
                
                const ovStartPct = getPct(overlapStart);
                const ovEndPct = getPct(overlapEnd);
                const ovWidth = ovEndPct - ovStartPct;
                
                timelineHtml += `
                <div class="timeline-bar-overlap" style="left: ${ovStartPct}%; width: ${ovWidth}%;" title="Überlappung: ${overlapDays} Tage"></div>
                `;
                
                tableRows += `
                <tr>
                    <td>${stepCount++}. Intervall<br><span style="font-size:0.85em;color:var(--text-muted);">${d1.toLocaleDateString('de-DE')} bis ${d2.toLocaleDateString('de-DE')}</span></td>
                    <td>${intervalConsumption.toFixed(2)} ${escapeHtml(data.unit)} / ${intervalDays} Tage<br><b>= ${dailyRate.toFixed(4)} ${escapeHtml(data.unit)}/Tag</b></td>
                    <td>${overlapDays} Tage<br><span style="font-size:0.85em;color:var(--text-muted);">(${overlapStart.toLocaleDateString('de-DE')} - ${(new Date(overlapEnd.getTime() - (1000 * 60 * 60 * 24))).toLocaleDateString('de-DE')})</span></td>
                    <td style="font-weight:600; text-align:right;">${partConsumption.toFixed(2)} ${escapeHtml(data.unit)}</td>
                </tr>
                `;
            }
        }
        
        // Add fallback for missing days just like python does!
        const totalCoveredDays = Array.from(timelineHtml.matchAll(/Überlappung: (\d+) Tage/g)).reduce((sum, match) => sum + parseInt(match[1]), 0);
        const missingDays = data.target_days - totalCoveredDays;
        
        if (missingDays > 0 && basis.length >= 2) {
            const firstR = basis[0];
            const lastR = basis[basis.length - 1];
            const globalDays = (parseD(lastR.date) - parseD(firstR.date)) / (1000 * 60 * 60 * 24);
            if (globalDays > 0) {
                const globalRate = (lastR.total - firstR.total) / globalDays;
                const fallbackConsumption = globalRate * missingDays;
                totalConsumption += fallbackConsumption;
                
                tableRows += `
                <tr style="background:var(--warning-bg);">
                    <td>Fallback-Schätzung<br><span style="font-size:0.85em;color:var(--text-muted);">Für Randtage</span></td>
                    <td>Globale Rate<br><b>= ${globalRate.toFixed(4)} ${escapeHtml(data.unit)}/Tag</b></td>
                    <td>${missingDays} fehlende Tage</td>
                    <td style="font-weight:600; text-align:right; color:var(--warning-color);">+ ${fallbackConsumption.toFixed(2)} ${escapeHtml(data.unit)}</td>
                </tr>
                `;
            }
        }
        
        timelineHtml += `
            </div>
            <div style="margin-top: 60px; font-size: 0.85em; color: var(--text-muted);">
                <b>Legende:</b> 
                <span style="display:inline-block; width:12px; height:12px; background:#d1d5db; margin-left:8px; border-radius:2px;"></span> Ablesezeitraum
                <span style="display:inline-block; width:12px; height:12px; background:var(--primary); margin-left:8px; border-radius:2px;"></span> Abrechnungszeitraum
                <span style="display:inline-block; width:12px; height:12px; border: 1px solid var(--secondary); background: repeating-linear-gradient(45deg, rgba(16,185,129,0.4), rgba(16,185,129,0.4) 3px, rgba(16,185,129,0.7) 3px, rgba(16,185,129,0.7) 6px); margin-left:8px; border-radius:2px;"></span> Verrechnete Überlappung
            </div>
        </div>`;
        
        let tableHtml = `
        <h3>Step-by-Step Berechnung (Stückweise Interpolation)</h3>
        <table class="audit-table">
            <thead>
                <tr>
                    <th>Ablese-Intervall</th>
                    <th>Tagesrate berechnen</th>
                    <th>Tage in der Abrechnung</th>
                    <th style="text-align:right;">Teil-Verbrauch</th>
                </tr>
            </thead>
            <tbody>
                ${tableRows}
                <tr style="background:var(--bg-color); font-size: 1.1em;">
                    <td colspan="3" style="text-align:right; font-weight:600;">Gesamtsumme (Interpoliert):</td>
                    <td style="font-weight:600; color:var(--primary); text-align:right;">${totalConsumption.toFixed(2)} ${escapeHtml(data.unit)}</td>
                </tr>
            </tbody>
        </table>
        `;
        
        body.innerHTML = timelineHtml + tableHtml;
        modal.classList.add('active');
        
    } catch (e) {
        console.error(e);
        showError(meldungZu(e, 'Fehler beim Laden des Berechnungsprotokolls.'));
    }
}
