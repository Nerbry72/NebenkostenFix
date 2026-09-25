"""Probe zu Tor 0.8-P Punkt 1: Einrichtung ohne Terminal, Abrechnung mit Heizung.

Startet die Anwendung so, wie sie ausgeliefert wird -- gunicorn mit ZWEI
Arbeitern (F-73/F-74 zeigten sich nur dort) -- gegen einen frischen,
leeren Datenordner ohne SECRET_KEY und ohne Konto. Danach fuehrt ein
kopfloser Chromium durch:

    1. / -> Anmeldung -> Einrichtung (ohne Konto)
    2. Einmal-Code aus dem Serverprotokoll lesen (wie der Betreiber im
       Docker-Log), Konto im Formular anlegen
    3. 30 Aufrufe mit der Sitzung: jeder Arbeiter muss sie annehmen
    4. Das Musterhaus aus NK-125 anlegen (dieselbe HTTP-Schnittstelle, die
       die Oberflaeche benutzt, mit der Sitzung des Browsers)
    5. In der Oberflaeche: "Abrechnung frei erstellen" fuer Anna, Zeitraum
       2024, Vorschau, Festsetzung
    6. Pruefen: Summe 3.864,00 EUR wie die Handrechnung (NK-125)

Aufruf (Entwicklung, braucht gunicorn und Playwright):

    python scripts/probe_ersteinrichtung.py [--workers 2] [--chromium PFAD]

Ausgabe: eine Zeile je Schritt, Rueckgabewert 0 bei Erfolg. Kein Schritt
fasst Daten ausserhalb des temporaeren Ordners an.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
CODE = re.compile(r'\b([0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4})\b')


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def warte_auf_gesundheit(basis: str, prozess, frist_s: float = 60) -> float:
    import urllib.request

    start = time.monotonic()
    while time.monotonic() - start < frist_s:
        if prozess.poll() is not None:
            raise SystemExit('Server ist beim Start beendet.')
        try:
            with urllib.request.urlopen(basis + '/api/health', timeout=2) as a:
                if a.status == 200:
                    return time.monotonic() - start
        except OSError:
            time.sleep(0.3)
    raise SystemExit('Server nicht gesund binnen Frist.')


def schritt(text: str) -> None:
    print(f'[probe] {text}', flush=True)


def musterhaus(anfrage, basis: str) -> dict:
    """Das Musterhaus aus tests/test_musterabrechnung.py, per HTTP."""
    def post(pfad, daten):
        antwort = anfrage.post(basis + pfad, data=json.dumps(daten),
                               headers={'Content-Type': 'application/json'})
        if antwort.status not in (200, 201):
            raise SystemExit(f'{pfad}: {antwort.status} {antwort.text()}')
        return antwort.json()

    kategorien = {k['name']: k['id'] for k in
                  anfrage.get(basis + '/api/categories').json()}
    prop = post('/api/properties', {'name': 'Musterweg 1'})['id']
    w = [post('/api/apartments', {'property_id': prop, 'name': n, 'sqm': 50,
                                  **({'eigennutzung': True} if n == 'Dachgeschoss' else {})})['id']
         for n in ('Erdgeschoss', 'Obergeschoss', 'Dachgeschoss', 'Kellerwohnung')]
    anlage = post(f'/api/properties/{prop}/heizungsanlagen', {
        'name': 'Zentralheizung', 'versorgt': 'verbunden',
        'verbrauchsanteil_prozent': 70, 'sonderfall_70': True,
        'warmwasser_weg': 'formel', 'warmwasser_volumen_m3': 100,
        'warmwasser_temperatur_c': 50, 'brennstoff_menge': 40000})['id']
    anna = post('/api/tenants', {'apartment_id': w[0], 'name': 'Anna Muster',
                                 'move_in_date': '2024-01-01'})['id']
    bernd = post('/api/tenants', {'apartment_id': w[1], 'name': 'Bernd Muster',
                                  'move_in_date': '2024-07-01'})['id']
    post(f'/api/tenants/{anna}/haushaltsgroessen',
         {'gueltig_ab': '2024-01-01', 'personenanzahl': 2})
    post(f'/api/tenants/{bernd}/haushaltsgroessen',
         {'gueltig_ab': '2024-07-01', 'personenanzahl': 2})

    def zaehler(wohnung, kategorie, nummer, staende):
        meter = post('/api/meters', {
            'category_id': kategorien[kategorie], 'property_id': prop,
            'apartment_id': wohnung, 'meter_number': nummer,
            'heizungsanlage_id': anlage})['id']
        for datum, wert, art in staende:
            lesung = {'meter_id': meter, 'reading_date': datum, 'value': wert}
            if art:
                lesung['ablesungsart'] = art
            post('/api/readings', lesung)

    z = 'zwischenablesung'
    zaehler(w[0], 'Heizung', 'W-W1', [('2024-01-01', 10000, None), ('2025-01-01', 16000, None)])
    zaehler(w[1], 'Heizung', 'W-W2', [('2024-01-01', 20000, None), ('2024-07-01', 20800, z),
                                      ('2025-01-01', 22000, None)])
    zaehler(w[2], 'Heizung', 'W-W3', [('2024-01-01', 30000, None), ('2025-01-01', 31000, None)])
    zaehler(w[3], 'Heizung', 'W-W4', [('2024-01-01', 40000, None), ('2025-01-01', 41000, None)])
    zaehler(w[0], 'Warmwasser', 'WW-W1', [('2024-01-01', 1000, None), ('2025-01-01', 1060, None)])
    zaehler(w[1], 'Warmwasser', 'WW-W2', [('2024-01-01', 2000, None), ('2024-07-01', 2012, z),
                                          ('2025-01-01', 2030, None)])
    zaehler(w[2], 'Warmwasser', 'WW-W3', [('2024-01-01', 3000, None), ('2025-01-01', 3006, None)])
    zaehler(w[3], 'Warmwasser', 'WW-W4', [('2024-01-01', 4000, None), ('2025-01-01', 4004, None)])
    post('/api/invoices', {
        'category_id': kategorien['Heizung'], 'property_id': prop,
        'start_date': '2024-01-01', 'end_date': '2024-12-31', 'amount': 8000,
        'invoice_number': 'GAS-2024', 'heizungsanlage_id': anlage,
        'heizkostenart': 'brennstoff', 'co2_kosten': 1000, 'co2_emission_kg': 10000})
    post('/api/invoices', {
        'category_id': kategorien['Grundsteuer'], 'property_id': prop,
        'start_date': '2024-01-01', 'end_date': '2024-12-31', 'amount': 1200,
        'invoice_number': 'GST-2024'})
    return {'anna': anna, 'bernd': bernd}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--chromium', default=os.environ.get(
        'NK_CHROMIUM', '/opt/pw-browsers/chromium'))
    parser.add_argument('--server', choices=('gunicorn', 'waitress'),
                        default='gunicorn')
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    ordner = Path(tempfile.mkdtemp(prefix='nk-probe-'))
    (ordner / 'belege').mkdir()
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ('SECRET_KEY', 'NAS_MOUNT_PATH', 'DATABASE_URL',
                             'DATA_DIR', 'ENABLE_DEBUG_RESET')}
    umgebung.update({
        'DATA_DIR': str(ordner),
        'DATABASE_URL': f'sqlite:///{ordner}/nebenkosten.db',
        'NAS_MOUNT_PATH': str(ordner / 'belege'),
        'LOG_DATEI': '',
    })
    port = freier_port()
    basis = f'http://127.0.0.1:{port}'
    protokoll = open(ordner / 'server.log', 'w+', encoding='utf-8')
    if args.server == 'gunicorn':
        befehl = [sys.executable, '-m', 'gunicorn', '--bind', f'127.0.0.1:{port}',
                  '--workers', str(args.workers), 'app:app']
    else:
        befehl = [sys.executable, '-m', 'waitress', '--listen',
                  f'127.0.0.1:{port}', '--threads', '8', 'app:app']
    prozess = subprocess.Popen(befehl, cwd=WURZEL, env=umgebung,
                               stdout=protokoll, stderr=subprocess.STDOUT,
                               start_new_session=True)
    try:
        dauer = warte_auf_gesundheit(basis, prozess)
        schritt(f'Server ({args.server}, {args.workers} Arbeiter) gesund nach {dauer:.1f} s')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=args.chromium)
            seite = browser.new_page(viewport={'width': 1440, 'height': 900})
            seite.set_default_timeout(20000)
            # NK-128: die CSP darf die Oberflaeche nicht brechen -- jede
            # Verletzung meldet der Browser auf der Konsole.
            csp_verstoesse = []
            seite.on('console', lambda m: csp_verstoesse.append(m.text)
                     if 'Content Security Policy' in m.text else None)
            seite.goto(basis + '/')
            if '/einrichtung' not in seite.url:
                raise SystemExit(f'Ohne Konto nicht auf der Einrichtung: {seite.url}')
            schritt('Ohne Konto fuehrt / zur Einrichtung')
            protokoll.flush()
            text = (ordner / 'server.log').read_text(encoding='utf-8')
            codes = sorted(set(CODE.findall(text)))
            if len(codes) != 1:
                raise SystemExit(f'Protokoll nennt {len(codes)} Codes statt einem: {codes}')
            schritt(f'Protokoll nennt genau einen Einmal-Code ({len(CODE.findall(text))} Zeilen)')
            seite.fill('#username', 'probe')
            seite.fill('#password', 'probe-passwort-1')
            seite.fill('#password2', 'probe-passwort-1')
            seite.fill('#code', codes[0])
            seite.click('button[type="submit"]')
            seite.wait_for_url(basis + '/')
            schritt('Konto ueber das Formular angelegt, angemeldet')
            fehlschlaege = 0
            for _ in range(30):
                if seite.request.get(basis + '/api/auth/me').status != 200:
                    fehlschlaege += 1
            if fehlschlaege:
                raise SystemExit(f'{fehlschlaege}/30 Aufrufe ohne gueltige Sitzung (F-74?)')
            schritt('30 Aufrufe mit der Sitzung, alle angenommen')
            if not (ordner / 'secret_key').exists():
                raise SystemExit('Kein secret_key im Datenordner')
            schritt('secret_key im Datenordner angelegt')

            ids = musterhaus(seite.request, basis)
            schritt('Musterhaus mit Heizungsanlage, Zaehlern und Rechnungen angelegt')

            seite.reload()
            seite.click('.nav-item[data-tab="billing"]')
            seite.click('#btn-freie-abrechnung')
            seite.wait_for_selector('#billing-frei-modal.active')
            seite.select_option('#frei-mieter', str(ids['anna']))
            seite.fill('#frei-period-start', '2024-01-01')
            seite.fill('#frei-period-end', '2024-12-31')
            seite.click('#btn-frei-weiter')
            seite.wait_for_selector('#billing-preview-modal.active')
            vorschau = seite.inner_text('#billing-preview-modal')
            if '3864,00' not in vorschau.replace('.', ''):
                raise SystemExit('Vorschau zeigt nicht 3.864,00: ' + vorschau[:400])
            schritt('Vorschau zeigt 3.864,00 EUR fuer Anna (Handrechnung NK-125)')
            seite.wait_for_selector('#btn-generate-pdf:enabled')
            with seite.expect_response(lambda a: '/api/billing/finalize' in a.url) as info:
                seite.click('#btn-generate-pdf')
            if info.value.status != 201:
                raise SystemExit(f'Festsetzung: {info.value.status} {info.value.text()}')
            berichte = seite.request.get(basis + '/api/billing/reports').json()
            if not any(b['tenant_id'] == ids['anna'] for b in berichte):
                raise SystemExit('Festgesetzte Abrechnung fehlt in der Liste')
            schritt('Abrechnung in der Oberflaeche festgesetzt, PDF erzeugt')
            # Die Vorschau bleibt nach der Festsetzung offen (finalizeBill).
            seite.click('#billing-preview-modal .modal-footer button.btn-secondary')
            for reiter in ('dashboard', 'properties', 'tenants', 'meters',
                           'invoices', 'billing', 'payments', 'reports',
                           'settings'):
                seite.click(f'.nav-item[data-tab="{reiter}"]')
                seite.wait_for_timeout(300)
            if csp_verstoesse:
                raise SystemExit('CSP-Verstoesse: ' + ' | '.join(csp_verstoesse[:5]))
            schritt('Alle neun Bereiche geoeffnet, keine CSP-Verletzung')
            browser.close()
        schritt('ERGEBNIS: bestanden')
        return 0
    finally:
        try:
            os.killpg(prozess.pid, signal.SIGTERM)
        except ProcessLookupError:
            print('[probe] Server war schon beendet', flush=True)
        prozess.wait(timeout=20)
        protokoll.close()


if __name__ == '__main__':
    sys.exit(main())
