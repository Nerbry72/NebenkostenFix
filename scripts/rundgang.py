"""Rundgang als neuer Nutzer, als Prüfung (NK-157, F-89).

    python scripts/rundgang.py --ausgabe rundgang-bilder [--chromium /pfad/chrome]

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
BEREICHE = ['dashboard', 'properties', 'tenants', 'meters', 'invoices',
            'billing', 'payments', 'reports', 'settings']
BREITEN = [(1440, 900), (768, 1024), (390, 844)]
EINSTELLUNGS_GRUPPEN = ['vermieter', 'sicherung', 'konto', 'lizenz', 'datenschutz']
# Dialoge, die ohne Auswahl aufgehen (Ausdruck in app.js).
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
}

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

    def bereich(self, name: str, zustand: str):
        self.schritt = f'{zustand}-{name}'
        self.seite.evaluate("(b) => wechsleZuTab(b)", name)
        self.seite.wait_for_timeout(700)
        self.aufnahme(f'{zustand}-{name}')
        self.pruefen(f'{zustand}/{name}', name)


def rundgang(chromium: str | None, ausgabe: Path) -> list[str]:
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
                    code = json.loads((datenordner / 'ersteinrichtung_code').read_text())['code']
                    seite.fill('#username', 'rundgang')
                    seite.fill('#password', 'rundgang-passwort-1')
                    seite.fill('#password2', 'rundgang-passwort-1')
                    seite.fill('#code', code)
                    seite.click('button[type=submit]')
                    seite.wait_for_timeout(1500)
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
                for name, aufruf in DIALOGE.items():
                    seite.evaluate(f"async () => {{ await {aufruf}; }}")
                    seite.wait_for_timeout(500)
                    gang.aufnahme(f'dialog-{name}')
                    gang.pruefen(f'dialog/{name}')
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
    argumente = zerleger.parse_args(argv)
    befunde = rundgang(argumente.chromium, argumente.ausgabe)
    bericht = {'befunde': befunde, 'bilder': len(list(argumente.ausgabe.glob('*.png')))}
    (argumente.ausgabe / 'bericht.json').write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2), encoding='utf-8')
    for befund in befunde:
        print('BEFUND', befund)
    print(f'{bericht["bilder"]} Aufnahmen, {len(befunde)} Befunde')
    return 1 if befunde else 0


if __name__ == '__main__':
    sys.exit(main())
