"""Rundgang als neuer Nutzer, als Prüfung (NK-157, F-89).

    python scripts/rundgang.py --ausgabe rundgang-bilder [--chromium /pfad/chrome] [--readme ordner]

Startet NebenkostenFix mit einem leeren Datenordner (waitress, freier Port),
fährt mit Chromium durch die Anwendung, wie es ein neuer Nutzer täte, und
bricht mit Exit 1 ab, wenn eines davon auftritt:

- ein JavaScript-Fehler oder eine CSP-Meldung in der Konsole,
- waagerechter Überlauf der Seite oder eines offenen Dialogs,
- ein Knopf, der über den rechten Rand hinausragt,
- ein Bereich, der leer ist, ohne einen Leerzustand zu zeigen.

Der Weg: Einrichtung (Einmal-Code aus dem Datenordner) → alle neun Bereiche
leer → Beispielimmobilie → alle Bereiche gefüllt → jeder Dialog einmal
offen → Einstellungsgruppen. In 1440, 768 und 390 px Breite. Aufnahmen
landen in ``--ausgabe``; die CI legt sie als Artefakt ab. Die Aufnahmen sind
ein Hinweis für Menschen, kein Abbruchgrund.

Entstanden aus dem Handrundgang vom 25.09.2026, der sechs Fehler fand, die
kein Wächter sah (NK-154).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
# Abstand zwischen jeder sichtbaren Trennlinie eines Abschnittskopfs und dem
# Element davor, in px.
TRENNLINIEN_JS = """() => [...document.querySelectorAll('.section-header-getrennt')]
    .filter(k => k.offsetParent && k.previousElementSibling?.offsetParent)
    .map(k => [k.innerText.split('\\n')[0],
               k.getBoundingClientRect().top - k.previousElementSibling.getBoundingClientRect().bottom])"""
BEREICHE = ['dashboard', 'properties', 'tenants', 'meters', 'invoices',
            'billing', 'payments', 'reports', 'settings']
BREITEN = [(1440, 900), (768, 1024), (390, 844)]
EINSTELLUNGS_GRUPPEN = ['vermieter', 'kostenarten', 'sicherung', 'konto', 'updates', 'datenschutz']
# Jeder Dialog einmal (Ausdruck in app.js). ``__rg`` legt AUSWAHL_JS mit
# Haus, Mieter, Zähler und Anlage der Beispielimmobilie an.
DIALOGE = {
    'immobilie': 'openAddPropertyModal()',
    'wohnung': 'openAddApartmentModal()',
    'mieter': 'openAddTenantModal()',
    'zaehler': 'openAddMeterModal()',
    'ablesung': 'openAddReadingModal()',
    'rechnung': 'openAddInvoiceModal()',
    'beleg': 'openAddDocumentModal()',
    'zahlung': 'openAddPaymentModal()',
    'freie-abrechnung': 'openFreieAbrechnung()',
    'import': "oeffneImport('rechnungen')",  # NK-161
    'rechnungstabelle': 'oeffneRechnungstabelle()',  # NK-161
    'jahresassistent': 'oeffneJahrAssistent()',  # NK-160
    'anschreiben': 'openAnschreibenModal(__rg.haus.id)',  # #41
    'kostenprofil': 'openCostProfileModal(__rg.mieter.id, __rg.mieter.name)',
    'zaehler-bearbeiten': 'openEditMeterModal(__rg.zaehler.id)',
    'zaehler-verlauf': 'openHistoryModal(__rg.zaehler.id)',
    'zaehlerwechsel': 'openWechselModal(__rg.zaehler.id)',
    'hausgeld': 'openHausgeldModal()',
    'heizungsanlage': 'openHeizungsanlageModal(__rg.anlage)',
    'haushalt': 'openHouseholdModal(__rg.mieter)',
    'kaltmiete': 'openKaltmieteModal(__rg.mieter)',
    'vorauszahlung': 'openVorauszahlungModal(__rg.mieter)',
    'zahlung-details': 'openPaymentDetailsModal(__rg.mieter.id)',
    # letzteKategorien hat die Einstellungsgruppe „kostenarten“ geladen.
    'kostenart': 'openKategorieModal(letzteKategorien[0].id)',
}
AUSWAHL_JS = """async () => {
  const lade = async pfad => (await fetch(pfad)).json();
  const haus = (await lade('/api/properties'))[0];
  window.__rg = { haus, mieter: (await lade('/api/tenants'))[0],
                  zaehler: (await lade('/api/meters'))[0],
                  anlage: (await fetchHeizungsanlagen(haus.id))[0] };
}"""
# #41 warf keinen JS-Fehler: der Fehler landete im catch als rote Meldung,
# der Dialog blieb zu. Alte Meldungen markiert DIALOG_VORHER_JS.
DIALOG_VORHER_JS = """() => {
  document.querySelectorAll('.toast').forEach(t => { t.dataset.rundgangAlt = '1'; });
  return [...document.querySelectorAll('.modal-overlay.active')].map(m => m.id);
}"""
DIALOG_NACHHER_JS = """(vorher) => {
  const befunde = [];
  const offen = [...document.querySelectorAll('.modal-overlay.active')].map(m => m.id);
  if (!offen.some(id => !vorher.includes(id))) befunde.push('Dialog geht nicht auf');
  for (const t of document.querySelectorAll('.toast-fehler:not([data-rundgang-alt])'))
    befunde.push(`rote Meldung „${t.innerText.trim().slice(0, 120)}“`);
  return befunde;
}"""

# --readme: Bilder für README (1440×900) und Microsoft Store (1920×1080) aus
# der Beispielimmobilie. Name → Bereich, None ist die Hilfe.
README_BILDER = {'uebersicht': 'dashboard', 'abrechnung': 'billing', 'hilfe': None}
STORE_BILDER = {'1-heute': 'dashboard', '2-rechnungen': 'invoices', '3-zaehler': 'meters',
                '4-abrechnungen': 'billing', '5-statistiken': 'reports', '6-hilfe': None}

RUECKFRAGE_BEJAHEN = ("() => { if (document.getElementById('frage-modal')"
                      ".classList.contains('active')) frageAntwort(true); }")

# Prüft im Browser: Überlauf, abgeschnittene Knöpfe, leerer Bereich.
PRUEFUNG_JS = """
(bereich) => {
  const befunde = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > doc.clientWidth + 1) {
    befunde.push(`waagerechter Überlauf: ${doc.scrollWidth} > ${doc.clientWidth}`);
  }
  const breite = window.innerWidth;
  // Ein Knopf in einem Behälter, der selbst waagerecht rollt (Tabelle in
  // der Karte), ist erreichbar; abgeschnitten ist nur, was die Seite verliert.
  const rolltWaagerecht = (el) => {
    for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      const x = getComputedStyle(e).overflowX;
      if ((x === 'auto' || x === 'scroll') && e.scrollWidth > e.clientWidth) return true;
    }
    return false;
  };
  for (const knopf of document.querySelectorAll('button, a.btn-primary, a.btn-secondary')) {
    if (!knopf.offsetParent) continue;
    const r = knopf.getBoundingClientRect();
    if (r.width > 0 && r.right > breite + 1 && !rolltWaagerecht(knopf)) {
      const name = knopf.getAttribute('aria-label') || knopf.title || knopf.textContent.trim();
      befunde.push(`Knopf ragt über den Rand: „${name.slice(0, 40)}“`);
    }
  }
  // Kaputte Werte, die kein Wächter sieht: ein falsch geparstes Datum, eine
  // Rechnung mit undefined (Fund „Invalid Date“ in der Historie, NK-159).
  const sichtbar = document.body.innerText;
  for (const muster of ['Invalid Date', 'NaN', 'undefined', '[object Object]']) {
    if (sichtbar.includes(muster)) befunde.push(`sichtbarer Text enthält „${muster}“`);
  }
  // Formulare im Hausstil: gerechnete Stile, fängt auch Felder aus app.js
  // und Regeln, die die Hausregel später aushebeln.
  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (!el.offsetParent || el.type === 'hidden') continue;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    const name = el.id || el.name || el.className;
    if (el.type === 'file' && r.width > 1) befunde.push(`sichtbarer nativer Dateiwähler #${name}`);
    else if ((el.type === 'checkbox' || el.type === 'radio') && s.appearance !== 'none')
      befunde.push(`Kästchen im Systemstil #${name}`);
    else if (!['file', 'checkbox', 'radio', 'range'].includes(el.type)
             && !el.closest('.befehl-eingabe')
             && (parseFloat(s.borderTopLeftRadius) === 0 || r.height < 40))
      befunde.push(`Feld ohne Hausstil #${name}`);
  }
  if (bereich) {
    const sektion = document.getElementById('tab-' + bereich);
    if (sektion) {
      const inhalt = [...sektion.children].filter(k => !k.classList.contains('section-header')
        && k.offsetParent !== null && k.innerText.trim().length > 0);
      if (inhalt.length === 0) befunde.push('leerer Bereich ohne Leerzustand');
    }
  }
  return befunde;
}
"""


ZAEHLER_AKTIONEN_JS = """() => {
  const knoepfe = [...document.querySelectorAll('#meters-container button')].filter(k => k.offsetParent);
  if (knoepfe.length === 0) return ['keine Zähleraktion sichtbar'];
  return knoepfe.filter(k => { const r = k.getBoundingClientRect();
      return r.left < 0 || r.right > window.innerWidth; })
    .map(k => `Aktion „${k.title || k.textContent.trim()}“ liegt außerhalb des Bilds`);
}"""

# NK-253: am Handy stapelten sich die Kopfknöpfe; ein Menüknopf neben dem Titel
# trägt sie. Prüft den Kopf eines Bereichs mit mindestens zwei Aktionen.
KOPF_MENUE_JS = """(bereich) => {
  const kopf = document.querySelector(`#tab-${bereich} .section-header:has(.kopf-aktionen)`);
  const aktionen = kopf && [...kopf.querySelectorAll('.kopf-aktionen button')];
  if (!kopf || aktionen.length < 2) return [];
  const titel = kopf.querySelector('h2').getBoundingClientRect();
  const knopf = kopf.querySelector('.kopf-menue-knopf');
  if (!knopf || !knopf.offsetParent) return [`Kopf mit ${aktionen.length} Aktionen ohne Menüknopf`];
  const befunde = [];
  const k = knopf.getBoundingClientRect();
  if (k.top >= titel.bottom || k.bottom <= titel.top) befunde.push('Menüknopf steht nicht neben dem Titel');
  if (aktionen.some(a => a.offsetParent)) befunde.push('Aktionen stehen vor dem Öffnen im Kopf');
  knopf.click();
  const fehlen = aktionen.filter(a => { const r = a.getBoundingClientRect();
    return !a.offsetParent || r.left < 0 || r.right > window.innerWidth; });
  if (fehlen.length) befunde.push(`offenes Menü zeigt ${aktionen.length - fehlen.length} von ${aktionen.length} Aktionen`);
  knopf.click();
  if (aktionen.some(a => a.offsetParent)) befunde.push('Menü schließt beim zweiten Tippen nicht');
  return befunde;
}"""

# NK-254: ein Vergleich mit nur einer Wohnung sagt nichts; dann keine Karte.
VERGLEICH_JS = """() => {
  const karte = document.getElementById('chart-comparison-title').closest('.dashboard-card');
  const diagramm = Chart.getChart(document.getElementById('chart-building-comparison'));
  const wohnungen = diagramm ? diagramm.data.labels.length : 0;
  return karte.offsetParent && wohnungen < 2 ? [`Wohnungsvergleich mit ${wohnungen} Wohnung(en) sichtbar`] : [];
}"""

# NK-256: Zahlungskarten zeigten „Miete: 0,00 €“ für Mieter ohne Mietzahlung.
ZAHLUNG_NULLZEILEN_JS = """() => [...document.querySelectorAll('#payments-grid .property-card')].flatMap(karte =>
  [...karte.querySelectorAll('.prop-meta > div')]
    .filter(z => /(^|[^\\d.])0,00\\s€/.test(z.textContent))
    .map(z => `Zahlungskarte „${karte.querySelector('.prop-title').textContent}“: `
      + `${z.textContent.replace(/\\s+/g, ' ').trim()}`))"""

# NK-257: ein Zähler ohne Ablesung hatte keinen Weg zum ersten Stand außer
# über den Kopf; mit Ablesung bleibt der Stift.
ERSTER_STAND_JS = """() => [...document.querySelectorAll('#meters-container tr:not(.zaehler-kopf)')].flatMap(z => {
  const art = z.querySelector('[data-label="Kategorie"]').textContent.trim();
  const ohne = z.querySelector('[data-label="Letzter Stand"]').textContent.trim() === '-';
  const erster = [...z.querySelectorAll('button')].some(k => k.textContent.includes('Ersten Stand erfassen'));
  const stift = !!z.querySelector('button[title="Letzten Stand bearbeiten"]');
  if (ohne && (!erster || stift)) return [`Zähler ${art} ohne Ablesung ohne „Ersten Stand erfassen“`];
  if (!ohne && (erster || !stift)) return [`Zähler ${art} mit Ablesung ohne Stift`];
  return [];
})"""


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def server_starten(datenordner: Path, port: int) -> subprocess.Popen:
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ('DATABASE_URL', 'NAS_MOUNT_PATH', 'SECRET_KEY',
                             'LOCAL_PDF_PATH', 'LOCAL_TEMP_PATH', 'ENABLE_DEBUG_RESET')}
    umgebung['DATA_DIR'] = str(datenordner)
    code = ('import sys; sys.path.insert(0, %r)\n'
            'import app\nfrom waitress import serve\n'
            'serve(app.app, host="127.0.0.1", port=%d, threads=8)\n') % (str(WURZEL), port)
    prozess = subprocess.Popen(  # noqa: S603 -- eigenes Python, feste Argumente
        [sys.executable, '-c', code], cwd=WURZEL, env=umgebung,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    frist = time.monotonic() + 60
    while time.monotonic() < frist:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=2):  # nosec B310
                return prozess
        except OSError:
            if prozess.poll() is not None:
                raise SystemExit('Server brach ab:\n' + prozess.stderr.read().decode())
            time.sleep(0.5)
    prozess.kill()
    raise SystemExit('Server kam nicht hoch.')


def stapel_stelle(stapel: str) -> str:
    """Die erste Stelle aus eigenem Code im Stapel, als `` (app.js:5011)``.

    Fremdcode unter ``static/vendor/`` zählt nicht: der Fehler liegt fast
    immer beim Aufrufer.
    """
    for zeile in stapel.splitlines()[1:]:
        treffer = re.search(r'/static/([\w.-]+\.js)(?:\?[^:]*)?:(\d+)', zeile)
        if treffer:
            return f' ({treffer.group(1)}:{treffer.group(2)})'
    return ''


class Rundgang:
    def __init__(self, seite, basis: str, ausgabe: Path, breite: int):
        self.seite = seite
        self.basis = basis
        self.ausgabe = ausgabe
        self.breite = breite
        self.befunde: list[str] = []
        self.schritt = 'start'
        seite.on('console', self._konsole)
        seite.on('pageerror', self._seitenfehler)

    def _seitenfehler(self, fehler):
        stelle = stapel_stelle(getattr(fehler, 'stack', '') or '')
        self.befunde.append(f'{self.breite}px {self.schritt}: JS-Fehler: {fehler.message}{stelle}')

    def _konsole(self, meldung):
        text = meldung.text
        if meldung.type == 'error' or 'Content Security Policy' in text:
            self.befunde.append(f'{self.breite}px {self.schritt}: Konsole: {text[:200]}')

    def aufnahme(self, name: str):
        self.schritt = name
        self.seite.screenshot(path=str(self.ausgabe / f'{self.breite}-{name}.png'), full_page=True)

    def pruefen(self, wo: str, bereich: str | None = None):
        for befund in self.seite.evaluate(PRUEFUNG_JS, bereich):
            self.befunde.append(f'{self.breite}px {wo}: {befund}')

    def dialog(self, name: str, aufruf: str):
        vorher = self.seite.evaluate(DIALOG_VORHER_JS)
        self.seite.evaluate(f"async () => {{ await {aufruf}; }}")
        self.seite.wait_for_timeout(500)
        self.aufnahme(f'dialog-{name}')
        self.pruefen(f'dialog/{name}')
        for befund in self.seite.evaluate(DIALOG_NACHHER_JS, vorher):
            self.befunde.append(f'{self.breite}px dialog/{name}: {befund}')

    def formulare(self):
        """Formulare im Hausstil, hell und dunkel: Verschlüsselung per Klick an
        (Passphrase sichtbar), Kästchenliste der Hilfe, Dateiwähler im Dialog."""
        for thema in ('light', 'dark'):
            self.seite.evaluate("(t) => themaAnzeigen(t)", thema)
            self.seite.evaluate("() => wechsleZuTab('settings')")
            self.seite.evaluate("(g) => zeigeEinstellungsgruppe(g)", 'sicherung')
            self.seite.wait_for_timeout(300)
            for haken in ('#sicherung-verschluesseln', '#umzug-verschluesseln'):
                self.seite.check(haken)
            self.aufnahme(f'formulare-sicherung-{thema}')
            self.pruefen(f'formulare/sicherung-{thema}')
            for haken in ('#sicherung-verschluesseln', '#umzug-verschluesseln'):
                self.seite.uncheck(haken)
            self.seite.evaluate("() => zeigeHilfe()")
            self.seite.wait_for_timeout(300)
            self.aufnahme(f'formulare-hilfe-{thema}')
            self.pruefen(f'formulare/hilfe-{thema}')
            for name in ('beleg', 'rechnung'):
                self.dialog(f'{name}-{thema}', DIALOGE[name])
                self.seite.keyboard.press('Escape')
                self.seite.wait_for_timeout(200)
                self.seite.evaluate(RUECKFRAGE_BEJAHEN)
                self.seite.wait_for_timeout(200)
        self.seite.evaluate("() => themaAnzeigen('light')")

    def handy(self):
        """Funde der Bestandsaufnahme 0.13.0 am Handy (NK-252 ff.), mit Beispielhaus."""
        self.schritt = 'handy-zaehler'
        self.seite.evaluate("(b) => wechsleZuTab(b)", 'meters')
        self.seite.wait_for_timeout(700)
        # NK-252: die Tabelle rollte in ihrer Karte, die Aktionen lagen rechts außerhalb.
        for befund in self.seite.evaluate(ZAEHLER_AKTIONEN_JS):
            self.befunde.append(f'{self.breite}px handy/zaehler: {befund}')
        for befund in self.seite.evaluate(ERSTER_STAND_JS):
            self.befunde.append(f'{self.breite}px handy/zaehler: {befund}')
        for bereich in BEREICHE:
            self.schritt = f'handy-kopf-{bereich}'
            self.seite.evaluate("(b) => wechsleZuTab(b)", bereich)
            self.seite.wait_for_timeout(300)
            for befund in self.seite.evaluate(KOPF_MENUE_JS, bereich):
                self.befunde.append(f'{self.breite}px handy/{bereich}: {befund}')
        self.schritt = 'handy-vergleich'
        self.seite.evaluate("(b) => wechsleZuTab(b)", 'reports')
        self.seite.wait_for_timeout(1500)
        for befund in self.seite.evaluate(VERGLEICH_JS):
            self.befunde.append(f'{self.breite}px handy/reports: {befund}')
        self.schritt = 'handy-zahlungen'
        self.seite.evaluate("(b) => wechsleZuTab(b)", 'payments')
        self.seite.wait_for_timeout(700)
        for befund in self.seite.evaluate(ZAHLUNG_NULLZEILEN_JS):
            self.befunde.append(f'{self.breite}px handy/payments: {befund}')

    def bereich(self, name: str, zustand: str):
        self.schritt = f'{zustand}-{name}'
        self.seite.evaluate("(b) => wechsleZuTab(b)", name)
        self.seite.wait_for_timeout(700)
        self.aufnahme(f'{zustand}-{name}')
        self.pruefen(f'{zustand}/{name}', name)
        # Fund 0.9.1: die Trennlinie vor „Historie“ klebte an der Karte darüber.
        for kopf, luecke in self.seite.evaluate(TRENNLINIEN_JS):
            if luecke < 16:
                self.befunde.append(f'{self.breite}px {zustand}/{name}: „{kopf}“ nur {luecke:.0f}px '
                                    'unter dem Inhalt darüber')


def schaufenster(seite, ordner: Path, bilder: dict[str, str | None]) -> None:
    """Aufnahmen im Bildausschnitt, ohne Einführungstour, von oben."""
    ordner.mkdir(parents=True, exist_ok=True)
    for name, bereich in bilder.items():
        seite.evaluate("(b) => { tourBeenden(); b ? wechsleZuTab(b) : zeigeHilfe(); window.scrollTo(0, 0); }",
                       bereich)
        seite.wait_for_timeout(1500)  # Diagramme gezeichnet, Aufsteigen vorbei
        seite.screenshot(path=str(ordner / f'{name}.png'))


def rundgang(chromium: str | None, ausgabe: Path, readme: Path | None = None) -> list[str]:
    from playwright.sync_api import sync_playwright

    ausgabe.mkdir(parents=True, exist_ok=True)
    datenordner = Path(tempfile.mkdtemp(prefix='nk-rundgang-'))
    port = _freier_port()
    basis = f'http://127.0.0.1:{port}'
    server = server_starten(datenordner, port)
    befunde: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium) if chromium \
                else pw.chromium.launch()
            for nummer, (breite, hoehe) in enumerate(BREITEN):
                kontext = browser.new_context(viewport={'width': breite, 'height': hoehe},
                                              locale='de-DE', timezone_id='Europe/Berlin')
                seite = kontext.new_page()
                seite.on('dialog', lambda d: d.accept())
                gang = Rundgang(seite, basis, ausgabe, breite)
                if nummer == 0:
                    seite.goto(basis + '/')
                    seite.wait_for_timeout(500)
                    gang.aufnahme('einrichtung')
                    gang.pruefen('einrichtung')
                    # Fund 0.9.1: Die offene Hinweisblase liest beim Tippen neu und
                    # zeigte dann den Systemtext statt des deutschen Hinweises.
                    seite.click('#password')
                    seite.keyboard.type('a')
                    seite.click('button[type=submit]')
                    seite.press('#password', 'b')
                    hinweis = seite.eval_on_selector('#password', 'e => e.validationMessage')
                    if '(bisher 2)' not in hinweis:
                        befunde.append(f'einrichtung: Hinweis beim Tippen „{hinweis}“')
                    seite.fill('#password', '')
                    code = json.loads((datenordner / 'ersteinrichtung_code').read_text())['code']
                    seite.fill('#username', 'rundgang')
                    seite.fill('#password', 'rundgang-passwort-1')
                    seite.fill('#password2', 'rundgang-passwort-1')
                    seite.fill('#code', code)
                    seite.click('button[type=submit]')
                    seite.wait_for_timeout(1500)
                    # NK-174: erst der Haftungshinweis, weiter nur mit „Verstanden“.
                    gang.schritt = 'haftung'
                    if seite.is_visible('#haftung-modal'):
                        gang.aufnahme('haftung')
                        gang.pruefen('haftung')
                        seite.click('#haftung-modal [data-autofokus]')
                        seite.wait_for_timeout(500)
                    else:
                        befunde.append('haftung: der Hinweis erscheint nach der Einrichtung nicht')
                    for bereich in BEREICHE:
                        gang.bereich(bereich, 'leer')
                    seite.evaluate("() => beispielAnlegen(null)")
                    seite.wait_for_timeout(3000)
                else:
                    seite.goto(basis + '/login')
                    seite.fill('#username', 'rundgang')
                    seite.fill('#password', 'rundgang-passwort-1')
                    seite.click('button[type=submit]')
                    seite.wait_for_timeout(1500)
                for bereich in BEREICHE:
                    gang.bereich(bereich, 'gefuellt')
                if readme and nummer == 0:
                    gang.schritt = 'readme'
                    schaufenster(seite, readme, README_BILDER)
                    seite.set_viewport_size({'width': 1920, 'height': 1080})
                    schaufenster(seite, readme / 'store', STORE_BILDER)
                    seite.set_viewport_size({'width': breite, 'height': hoehe})
                if breite < 720:
                    gang.handy()
                # NK-158: die Hilfe hat keinen Eintrag in der Seitenleiste.
                gang.schritt = 'hilfe'
                seite.evaluate("() => zeigeHilfe()")
                seite.wait_for_timeout(500)
                gang.aufnahme('hilfe')
                gang.pruefen('hilfe', 'hilfe')
                for gruppe in EINSTELLUNGS_GRUPPEN:
                    seite.evaluate("() => wechsleZuTab('settings')")
                    seite.evaluate("(g) => zeigeEinstellungsgruppe(g)", gruppe)
                    seite.wait_for_timeout(300)
                    gang.aufnahme(f'einstellungen-{gruppe}')
                    gang.pruefen(f'einstellungen/{gruppe}')
                seite.evaluate(AUSWAHL_JS)
                for name, aufruf in DIALOGE.items():
                    gang.dialog(name, aufruf)
                    seite.keyboard.press('Escape')
                    seite.wait_for_timeout(200)
                    # Fragt die App „Eingaben verwerfen?“, bejahen -- wie
                    # früher der Browserdialog über seite.on('dialog').
                    seite.evaluate(RUECKFRAGE_BEJAHEN)
                    seite.wait_for_timeout(200)
                gang.formulare()
                # Die Rückfrage selbst (frage-modal statt confirm()).
                gang.schritt = 'rueckfrage'
                seite.evaluate("() => { frageLoeschen('Möchten Sie diese Rechnung wirklich löschen?'); }")
                seite.wait_for_timeout(300)
                gang.aufnahme('dialog-rueckfrage')
                gang.pruefen('dialog/rueckfrage')
                seite.keyboard.press('Escape')
                seite.wait_for_timeout(200)
                # Die festgesetzte Beispiel-Abrechnung ansehen: der Schnappschuss
                # liefert Beträge als Text (json_sicher), nicht als Zahl.
                gang.schritt = 'abrechnung-ansehen'
                seite.evaluate("async () => { const b = await (await fetch('/api/billing/reports')).json();"
                               " await openReportDetails(b[0].id); }")
                seite.wait_for_timeout(500)
                gang.aufnahme('abrechnung-ansehen')
                gang.pruefen('abrechnung-ansehen')
                seite.keyboard.press('Escape')
                befunde += gang.befunde
                kontext.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=20)
    return befunde


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument('--ausgabe', type=Path, default=Path('rundgang-bilder'))
    zerleger.add_argument('--chromium', help='Pfad zu Chromium (sonst der von Playwright)')
    zerleger.add_argument('--readme', type=Path,
                          help='Ordner für README- und Store-Bilder (store/) aus der Beispielimmobilie')
    argumente = zerleger.parse_args(argv)
    befunde = rundgang(argumente.chromium, argumente.ausgabe, argumente.readme)
    bericht = {'befunde': befunde, 'bilder': len(list(argumente.ausgabe.glob('*.png')))}
    (argumente.ausgabe / 'bericht.json').write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2), encoding='utf-8')
    for befund in befunde:
        print('BEFUND', befund)
    print(f'{bericht["bilder"]} Aufnahmen, {len(befunde)} Befunde')
    return 1 if befunde else 0


if __name__ == '__main__':
    sys.exit(main())
