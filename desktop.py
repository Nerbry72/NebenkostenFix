"""Die Windows-App: eigenes Fenster statt Browser (NK-079, E-7 → D-92, D-84).

Zweiter Einstieg neben gunicorn (Docker). Ablauf:

  1. Datenordner bestimmen: Einstellung des Installers
     (``%LOCALAPPDATA%\\Nebenkostenabrechnung\\einstellungen.ini``), sonst
     ``Dokumente\\Nebenkostenabrechnung`` über die Windows-Schnittstelle für
     bekannte Ordner. Liegt er in OneDrive, fragt die App, ob die Daten
     stattdessen lokal liegen sollen (F-82). Eine Schreibprobe erkennt den
     überwachten Ordnerzugriff und erklärt ihn.
  2. Eine Instanz: läuft die App schon, holt der zweite Start das Fenster
     nach vorn und beendet sich.
  3. ``NK_DESKTOP=1`` und ``DATA_DIR`` setzen, erst dann ``app`` importieren
     (Schema, Einrichtung ohne Einmal-Code, Passwortseite der Hülle).
  4. waitress in einem Thread, nur auf 127.0.0.1, freier Port. Davor ein
     Start-Token je Sitzung (``HuellenSchutz``): nur das Fenster kennt ihn,
     andere lokale Programme und Browser-Tabs bekommen 403.
  5. pywebview-Fenster (Edge WebView2) mit Menü und Brücke für Speichern,
     Öffnen und Ordnerwahl (NK-152).
  6. Fenster zu → Server anhalten, WAL-Checkpoint, Sperre frei.

``--selbsttest`` fährt dieselben Schritte ohne Fenster gegen einen frischen
Datenordner und prüft Einrichtung, eine Abrechnung und das PDF -- für die CI
und für das gebaute Paket (NK-150, NK-135).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hmac
import html
import json
import logging
import os
import secrets
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from nebenkostenfix import aktualisierung
from nebenkostenfix import marke
from nebenkostenfix import windows_ordner

protokoll = logging.getLogger(__name__)

COOKIE = 'nk_huelle'
TITEL = marke.PRODUKT


# --- Start-Token (Zugriff nur aus dem Fenster) -------------------------------

class HuellenSchutz:
    """WSGI-Vorschaltung: jede Anfrage braucht das Cookie mit dem Token.

    ``/huelle/start?t=<token>`` setzt es (HttpOnly, SameSite=Strict) und
    leitet auf ``/`` weiter -- das ist die erste Adresse des Fensters.
    ``/huelle/nach-vorne`` mit dem Token im Kopf holt das Fenster nach vorn
    (zweiter Programmstart).
    """

    def __init__(self, anwendung, token: str, nach_vorne=None):
        self.anwendung = anwendung
        self.token = token
        self.nach_vorne = nach_vorne

    def _passt(self, wert: str | None) -> bool:
        return bool(wert) and hmac.compare_digest(wert.encode(), self.token.encode())

    def __call__(self, umgebung, antworten):
        pfad = umgebung.get('PATH_INFO', '')
        if pfad == '/huelle/start':
            parameter = urllib.parse.parse_qs(umgebung.get('QUERY_STRING', ''))
            if self._passt((parameter.get('t') or [''])[0]):
                antworten('302 Found', [
                    ('Location', '/'),
                    ('Set-Cookie', f'{COOKIE}={self.token}; HttpOnly; '
                                   'SameSite=Strict; Path=/'),
                    ('Cache-Control', 'no-store')])
                return [b'']
            return self._verboten(antworten)
        if pfad == '/huelle/nach-vorne':
            if self._passt(umgebung.get('HTTP_X_HUELLE_TOKEN')):
                if self.nach_vorne:
                    self.nach_vorne()
                antworten('204 No Content', [])
                return [b'']
            return self._verboten(antworten)
        cookies = {}
        for teil in (umgebung.get('HTTP_COOKIE') or '').split(';'):
            name, _, wert = teil.strip().partition('=')
            cookies[name] = wert
        if not self._passt(cookies.get(COOKIE)):
            return self._verboten(antworten)
        return self.anwendung(umgebung, antworten)

    @staticmethod
    def _verboten(antworten):
        text = f'Nur aus dem Programmfenster von {TITEL} erreichbar.'
        antworten('403 Forbidden', [('Content-Type', 'text/plain; charset=utf-8')])
        return [text.encode('utf-8')]


# --- Eine Instanz -------------------------------------------------------------

class EineInstanz:
    """Sperre im lokalen Anwendungsordner; der Inhaber schreibt Port und Token
    daneben, damit ein zweiter Start ihn bitten kann, nach vorn zu kommen."""

    def __init__(self, ordner: Path):
        ordner.mkdir(parents=True, exist_ok=True)
        self.sperrdatei = ordner / 'instanz.lock'
        self.infodatei = ordner / 'instanz.json'
        self._datei = None

    def erwerben(self) -> bool:
        self._datei = open(self.sperrdatei, 'a+b')
        try:
            if sys.platform == 'win32':  # pragma: no cover - Windows
                import msvcrt
                self._datei.seek(0)
                msvcrt.locking(self._datei.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self._datei.close()
            self._datei = None
            return False

    def eintragen(self, port: int, token: str) -> None:
        kennung = os.open(self.infodatei, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(kennung, 'w', encoding='utf-8') as datei:
            json.dump({'port': port, 'token': token}, datei)

    def anderen_wecken(self) -> bool:
        try:
            info = json.loads(self.infodatei.read_text(encoding='utf-8'))
            anfrage = urllib.request.Request(
                f"http://127.0.0.1:{int(info['port'])}/huelle/nach-vorne",
                method='POST', headers={'X-Huelle-Token': info['token']})
            # Bandit-Ausnahme (B310): feste http-Adresse auf 127.0.0.1
            with urllib.request.urlopen(anfrage, timeout=5):  # nosec B310
                return True
        except (OSError, ValueError, KeyError):
            return False

    def freigeben(self) -> None:
        with contextlib.suppress(OSError):
            self.infodatei.unlink()
        if self._datei is not None:
            self._datei.close()
            self._datei = None


# --- Datenordner --------------------------------------------------------------

def _meldung(text: str, frage: bool = False) -> bool:
    """Meldung im Stil des Systems; unter Windows eine MessageBox."""
    if sys.platform == 'win32':  # pragma: no cover - Windows
        import ctypes
        stil = 0x04 | 0x20 if frage else 0x10  # JA/NEIN + Frage bzw. Fehler
        return ctypes.windll.user32.MessageBoxW(None, text, TITEL, stil) == 6
    protokoll.warning('%s', text)
    return False


def datenordner_bestimmen(fragen: bool = True, vorgabe: str | None = None) -> Path:
    einstellungen = windows_ordner.einstellungen_lesen()
    ordner = Path(vorgabe or einstellungen['datenordner']
                  or windows_ordner.vorgabe_datenordner())
    if fragen and windows_ordner.liegt_in_onedrive(ordner) \
            and not einstellungen['onedrive_bestaetigt']:
        lokal = windows_ordner.lokaler_ausweich()
        if _meldung(
                f'Ihr Datenordner „{ordner}“ liegt in OneDrive und würde in die '
                'Cloud synchronisiert. Das kann die Datenbank beschädigen, und die '
                'Daten Ihrer Mieter lägen bei Microsoft.\n\n'
                f'Sollen die Daten stattdessen lokal unter „{lokal}“ liegen? '
                '(Empfohlen. Sicherungen können Sie weiter nach „Dokumente“ legen.)',
                frage=True):
            ordner = lokal
            windows_ordner.einstellungen_schreiben(datenordner=ordner)
        else:
            windows_ordner.einstellungen_schreiben(onedrive_bestaetigt=True)
    return ordner


def extern_erlaubt(adresse: str) -> bool:
    return any(adresse == ziel or adresse.startswith(ziel + '/')
               for ziel in (marke.REPO_URL, marke.KOFI_URL))


# --- Brücke für das Fenster (NK-152) ---------------------------------------

class Bruecke:
    """Was die Oberfläche über window.pywebview.api aufruft."""

    def __init__(self):
        # Mit Unterstrich: pywebview durchsucht nach jedem Seitenaufbau alle
        # öffentlichen Attribute der Brücke rekursiv. Das Fenster samt seinen
        # .NET-Objekten blockierte dabei die Oberfläche (0.9.0).
        self._fenster = None

    def speichern(self, dateiname: str, inhalt_base64: str):
        import webview
        ziel = self._fenster.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=Path(dateiname).name)
        if not ziel:
            return None
        pfad = ziel if isinstance(ziel, str) else ziel[0]
        Path(pfad).write_bytes(base64.b64decode(inhalt_base64))
        return pfad

    def oeffnen(self, dateiname: str, inhalt_base64: str, seite=None):
        ordner = Path(tempfile.gettempdir()) / TITEL
        ordner.mkdir(exist_ok=True)
        pfad = ordner / Path(dateiname).name
        pfad.write_bytes(base64.b64decode(inhalt_base64))
        if seite and pfad.suffix.lower() == '.pdf':
            # os.startfile kennt keinen Anker #page=N; eine Weiterleitung im
            # Standardbrowser nimmt ihn mit (Fund 0.9.2).
            ziel = f'{pfad.as_uri()}#page={int(seite)}'
            pfad = pfad.with_suffix('.html')
            pfad.write_text(f'<meta http-equiv="refresh" content="0; url={html.escape(ziel)}">',
                            encoding='utf-8')
        if sys.platform == 'win32':  # pragma: no cover - Windows
            # Bandit-Ausnahme (B606): Standardprogramm des Nutzers, kein Befehl
            os.startfile(pfad)  # nosec B606
        return str(pfad)

    def extern_oeffnen(self, adresse: str):
        """Projektseite und Ko-fi im Standardbrowser (NK-175, NK-179).
        Nur diese Adressen: eine Seite im Fenster soll keine beliebige
        Adresse aufrufen lassen koennen."""
        if not extern_erlaubt(adresse):
            return False
        import webbrowser
        return webbrowser.open(adresse)

    # NK-164: Umzugspaket. Große Pakete gehen nicht als base64 durch die
    # Brücke: der Dialog gibt einen Pfad frei, den der Server dann annimmt
    # (umzug.freigeben, wie die Ordnerwahl bei Sicherungen, F-76).
    def paket_waehlen(self):
        import webview

        from nebenkostenfix import umzug
        auswahl = self._fenster.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('NebenkostenFix Paket (*.nkfix;*.nkbak;*.tar.gz)', 'Alle Dateien (*.*)'))
        if not auswahl:
            return None
        return umzug.freigeben(auswahl if isinstance(auswahl, str) else auswahl[0])

    def paket_speichern_unter(self, dateiname: str):
        import webview

        from nebenkostenfix import umzug
        ziel = self._fenster.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=Path(dateiname).name)
        if not ziel:
            return None
        return umzug.freigeben(ziel if isinstance(ziel, str) else ziel[0])

    def ordner_waehlen(self):
        import webview
        auswahl = self._fenster.create_file_dialog(webview.FOLDER_DIALOG)
        if not auswahl:
            return None
        ordner = auswahl if isinstance(auswahl, str) else auswahl[0]
        # Was der Nutzer im Dialog des Systems waehlt, ist freigegeben (F-76):
        # der Weg fuehrt nur ueber das Fenster, nie ueber eine Anfrage.
        ziele = windows_ordner.einstellungen_lesen()['sicherungsziele']
        if ordner not in ziele:
            ziele.append(ordner)
            windows_ordner.einstellungen_schreiben(sicherungsziele=ziele)
        os.environ['BACKUP_ZIELE'] = os.pathsep.join(ziele)
        return ordner


# --- Server -------------------------------------------------------------------

def anwendung_laden(datenordner: Path):
    os.environ['NK_DESKTOP'] = '1'
    os.environ['DATA_DIR'] = str(datenordner)
    os.environ.pop('DATABASE_URL', None)
    ziele = windows_ordner.einstellungen_lesen()['sicherungsziele']
    if ziele:
        os.environ['BACKUP_ZIELE'] = os.pathsep.join(ziele)
    import app as app_modul  # noqa: E402 -- erst nach der Umgebung
    return app_modul


def server_starten(wsgi):
    from waitress import create_server
    server = create_server(wsgi, host='127.0.0.1', port=0, threads=8,
                           ident=TITEL, clear_untrusted_proxy_headers=True)
    faden = threading.Thread(target=server.run, name='waitress', daemon=True)
    faden.start()
    return server, faden


def anhalten(server, app_modul) -> None:
    """Server zu, WAL in die Datenbank zurueckschreiben, Griffe schliessen."""
    # Schon zu (zweiter Aufruf) ist dasselbe Ergebnis.
    with contextlib.suppress(OSError):
        server.close()
    with app_modul.app.app_context():
        from sqlalchemy import text
        with app_modul.db.engine.connect() as verbindung:
            verbindung.execute(text('PRAGMA wal_checkpoint(TRUNCATE)'))
        app_modul.db.session.remove()
        app_modul.db.engine.dispose()


# --- Umzugsprobe (CI, gebautes Paket, NK-164) -------------------------------

def umzug_probe(datenordner: Path, paket: Path, bericht_datei: str | None = None) -> int:
    """Übernimmt ein Paket (etwa unter Linux gebaut) in der gebauten App."""
    datenordner.mkdir(parents=True, exist_ok=True)
    app_modul = anwendung_laden(datenordner)
    from nebenkostenfix import umzug
    try:
        bericht = umzug.uebernehmen(app_modul.app, paket)
        ergebnis = umzug.bestandsbericht(app_modul.app)
        ergebnis['quelle'] = bericht.get('quelle')
        ergebnis['schemastand_nachher'] = bericht.get('schemastand_nachher')
        code = 0
    except Exception as fehler:  # noqa: BLE001 -- die Probe berichtet jeden Abbruch
        protokoll.exception('Umzugsprobe gescheitert')
        ergebnis, code = {'fehler': f'{type(fehler).__name__}: {fehler}'}, 1
    text = json.dumps(ergebnis, ensure_ascii=False)
    if bericht_datei:
        Path(bericht_datei).write_text(text, encoding='utf-8')
    return code


# --- Selbsttest (CI, gebautes Paket) ---------------------------------------

def selbsttest(datenordner: Path, bericht_datei: str | None = None) -> int:
    beginn = time.monotonic()
    app_modul = anwendung_laden(datenordner)
    token = secrets.token_urlsafe(32)
    server, _ = server_starten(HuellenSchutz(app_modul.app, token))
    basis = f'http://127.0.0.1:{server.effective_port}'
    oeffner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    bericht = {'port': server.effective_port}

    def ruf(methode, pfad, daten=None, roh=False):
        kopf = {'Content-Type': 'application/json'} if daten is not None else {}
        anfrage = urllib.request.Request(
            basis + pfad, method=methode, headers=kopf,
            data=json.dumps(daten).encode() if daten is not None else None)
        with oeffner.open(anfrage, timeout=60) as antwort:
            inhalt = antwort.read()
            return inhalt if roh else (json.loads(inhalt) if inhalt[:1] in b'{[' else {})

    try:
        try:
            # Bandit-Ausnahme (B310): feste http-Adresse auf 127.0.0.1
            urllib.request.urlopen(basis + '/api/health', timeout=10)  # nosec B310
            bericht['ohne_schluessel'] = 'erreichbar'
        except urllib.error.HTTPError as fehler:
            bericht['ohne_schluessel'] = fehler.code
        ruf('GET', f'/huelle/start?t={token}')
        bericht['health'] = ruf('GET', '/api/health').get('status')
        kennwort = secrets.token_urlsafe(16)
        ruf('POST', '/einrichtung', {'username': 'selbsttest', 'password': kennwort,
                                     'password2': kennwort})
        # Die Startseite nach der Einrichtung: sie las static/ relativ zum
        # Arbeitsverzeichnis und brach in der installierten App ab (0.9.0).
        bericht['startseite'] = b'app.js' in ruf('GET', '/', roh=True)
        haus = ruf('POST', '/api/properties', {'name': 'Selbsttest-Haus'})['id']
        wohnung = ruf('POST', '/api/apartments', {'property_id': haus, 'name': 'EG', 'sqm': 50})['id']
        ruf('POST', '/api/apartments', {'property_id': haus, 'name': 'OG', 'sqm': 50})
        mieter = ruf('POST', '/api/tenants', {'apartment_id': wohnung, 'name': 'Anna Mieterin',
                                              'move_in_date': '2024-01-01'})['id']
        kategorien = {k['name']: k['id'] for k in ruf('GET', '/api/categories')}
        steuer = kategorien['Grundsteuer']
        ruf('POST', f'/api/tenants/{mieter}/profiles', {str(steuer): 'qm'})
        ruf('POST', '/api/invoices', {'category_id': steuer, 'property_id': haus,
                                      'amount': 1200, 'start_date': '2025-01-01',
                                      'end_date': '2025-12-31', 'invoice_number': 'ST-1'})
        auftrag = {'tenant_id': mieter, 'start_date': '2025-01-01', 'end_date': '2025-12-31'}
        bericht['summe'] = ruf('POST', '/api/billing/generate', auftrag).get('total_amount')
        ruf('POST', '/api/billing/finalize', auftrag)
        bericht_id = ruf('GET', '/api/billing/reports')[0]['id']
        pdf = ruf('GET', f'/api/billing/reports/{bericht_id}/download', roh=True)
        bericht['pdf_bytes'] = len(pdf)
        bericht['pdf_ok'] = pdf.startswith(b'%PDF')
    finally:
        anhalten(server, app_modul)
    bericht['wal_nach_checkpoint'] = (datenordner / 'nebenkosten.db-wal').exists() and \
        (datenordner / 'nebenkosten.db-wal').stat().st_size
    bericht['sekunden'] = round(time.monotonic() - beginn, 2)
    ok = (bericht['ohne_schluessel'] == 403 and bericht['health'] == 'ok'
          and bericht['startseite']
          and abs(float(bericht['summe'] or 0) - 600.0) < 0.01 and bericht['pdf_ok'])
    bericht['ergebnis'] = 'bestanden' if ok else 'fehlgeschlagen'
    bericht['eingefroren'] = bool(getattr(sys, 'frozen', False))
    bericht['paketmodus'] = aktualisierung.paketmodus()
    text = json.dumps(bericht, ensure_ascii=False)
    # Der Bericht ist die Ausgabe des Kommandos (wie bei einem CLI-Werkzeug),
    # kein Fehlerkanal; Fehler des Laufs stehen im Protokoll der Anwendung.
    sys.stdout.write(text + '\n')
    if bericht_datei:
        # Das gebaute Paket hat kein Konsolenfenster (--windowed); die CI
        # liest den Bericht aus dieser Datei.
        Path(bericht_datei).write_text(text, encoding='utf-8')
    return 0 if ok else 1


# --- Fenster ------------------------------------------------------------------

def startseite() -> str:
    """Was das Fenster zeigt, solange die Anwendung hochfährt (NK-155).

    Das Fenster erscheint sofort; Datenbank, Wanderung und Server kommen
    danach. Ohne diese Seite sähe der Nutzer eine Sekunde lang nichts und
    klickte das Symbol ein zweites Mal an. Eigenständig (keine Schrift und
    kein Stil vom Server, der läuft ja noch nicht).
    """
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        f'<title>{TITEL}</title><style>'
        'body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;'
        'justify-content:center;gap:20px;font-family:"Segoe UI",system-ui,sans-serif;'
        'background:#F3F4F6;color:#111827}'
        '.name{font-size:28px;font-weight:600}.name b{color:#4F46E5}'
        '.text{color:#4B5563;font-size:16px}'
        '.balken{width:180px;height:4px;border-radius:2px;background:#E0E7FF;overflow:hidden}'
        '.balken span{display:block;width:40%;height:100%;background:#4F46E5;'
        'animation:lauf 1.2s ease-in-out infinite}'
        '@keyframes lauf{0%{transform:translateX(-100%)}100%{transform:translateX(250%)}}'
        '</style></head><body>'
        f'{marke.zeichen_svg(96)}'
        '<div class="name">Nebenkosten<b>Fix</b></div>'
        '<div class="text">wird gestartet …</div>'
        '<div class="balken"><span></span></div>'
        '</body></html>')


def fehlerseite(text: str) -> str:
    """Scheitert der Start nach dem Öffnen des Fensters, steht es dort."""
    import html
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8"><style>'
        'body{font-family:"Segoe UI",system-ui,sans-serif;background:#F3F4F6;color:#111827;'
        'padding:48px;line-height:1.6}h1{font-size:22px}</style></head><body>'
        f'<h1>{TITEL} konnte nicht starten</h1><p>{html.escape(text)}</p>'
        '<p>Die Einzelheiten stehen in <code>konsole.log</code> im lokalen Anwendungsordner. '
        'Ihre Daten sind nicht verändert.</p></body></html>')


def fenster_starten(datenordner: Path) -> int:  # pragma: no cover - braucht GUI
    import webview
    from webview.menu import Menu, MenuAction, MenuSeparator

    instanz = EineInstanz(windows_ordner.lokaler_ordner())
    if not instanz.erwerben():
        if instanz.anderen_wecken():
            return 0
        _meldung(f'{TITEL} läuft bereits.')
        return 1

    fehler = windows_ordner.schreibprobe(datenordner)
    if fehler:
        _meldung(fehler)
        instanz.freigeben()
        return 1

    bruecke = Bruecke()
    zustand = {}

    # Zuerst das Fenster mit der Startseite, dann im Hintergrund hochfahren.
    fenster = webview.create_window(
        TITEL, html=startseite(), js_api=bruecke,
        width=1440, height=900, min_size=(1024, 700), text_select=True)
    bruecke._fenster = fenster

    def nach_vorne():
        fenster.restore()
        fenster.show()

    def hochfahren():
        try:
            app_modul = anwendung_laden(datenordner)
            token = secrets.token_urlsafe(32)
            server, _ = server_starten(HuellenSchutz(app_modul.app, token, nach_vorne))
            zustand.update(server=server, app_modul=app_modul,
                           basis=f'http://127.0.0.1:{server.effective_port}')
            instanz.eintragen(server.effective_port, token)
            fenster.load_url(f"{zustand['basis']}/huelle/start?t={token}")
        except Exception as ausnahme:
            protokoll.exception('Start der Anwendung gescheitert')
            fenster.load_html(fehlerseite(str(ausnahme)))

    def passwort_seite():
        if 'basis' in zustand:
            fenster.load_url(f"{zustand['basis']}/huelle/passwort")

    menue = [
        Menu('Datei', [
            MenuAction('Drucken', lambda: fenster.evaluate_js('window.print()')),
            MenuSeparator(),
            MenuAction('Beenden', fenster.destroy),
        ]),
        Menu('Hilfe', [
            MenuAction('Passwort vergessen …', passwort_seite),
            # Bandit-Ausnahme (B606): oeffnet den Datenordner im Explorer
            MenuAction('Datenordner anzeigen',
                       lambda: os.startfile(datenordner)),  # nosec B606
            MenuSeparator(),
            # NK-179: springt in der Oberfläche zu „Über NebenkostenFix“.
            MenuAction(f'Über {marke.PRODUKT}',
                       lambda: fenster.evaluate_js("zeigeHilfe('hilfe-ueber')")),
        ]),
    ]
    speicher = windows_ordner.lokaler_ordner() / 'WebView2'
    try:
        webview.start(hochfahren, menu=menue, private_mode=False, storage_path=str(speicher))
    finally:
        if 'server' in zustand:
            anhalten(zustand['server'], zustand['app_modul'])
        instanz.freigeben()
    return 0


def _ausgaben_umleiten() -> None:
    """Ohne Konsolenfenster (PyInstaller --windowed) gibt es kein stdout;
    Ausgaben gehen dann in eine Datei im lokalen Anwendungsordner."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    ordner = windows_ordner.lokaler_ordner()
    ordner.mkdir(parents=True, exist_ok=True)
    datei = open(ordner / 'konsole.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stdout or datei
    sys.stderr = sys.stderr or datei


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=TITEL)
    zerleger.add_argument('--selbsttest', action='store_true',
                          help='Ohne Fenster gegen einen frischen Datenordner prüfen.')
    zerleger.add_argument('--datenordner', help='Datenordner für diesen Start.')
    zerleger.add_argument('--bericht', help='Selbsttest: Bericht als JSON in diese Datei.')
    zerleger.add_argument('--umzug-uebernehmen', metavar='PAKET',
                          help='Ein Umzugspaket in --datenordner übernehmen und den Bestand '
                               'in --bericht schreiben (plattformübergreifende Probe der CI, NK-164).')
    zerleger.add_argument('--datenordner-zeigen', action='store_true',
                          help='Nur den Datenordner bestimmen und in --bericht schreiben '
                               '(für die Update-Probe der CI).')
    argumente = zerleger.parse_args(argv)
    _ausgaben_umleiten()
    if argumente.datenordner_zeigen:
        ordner = datenordner_bestimmen(fragen=False)
        text = json.dumps({'datenordner': str(ordner),
                           'paketmodus': aktualisierung.paketmodus(),
                           'einstellungen': str(windows_ordner.einstellungen_datei()),
                           'ausweich': str(windows_ordner.lokaler_ausweich())},
                          ensure_ascii=False)
        sys.stdout.write(text + '\n')
        if argumente.bericht:
            Path(argumente.bericht).write_text(text, encoding='utf-8')
        return 0
    if argumente.umzug_uebernehmen:
        return umzug_probe(Path(argumente.datenordner or tempfile.mkdtemp(prefix='nk-umzug-')),
                           Path(argumente.umzug_uebernehmen), argumente.bericht)
    if argumente.selbsttest:
        ordner = Path(argumente.datenordner or tempfile.mkdtemp(prefix='nk-selbsttest-'))
        return selbsttest(ordner, argumente.bericht)
    ordner = datenordner_bestimmen(vorgabe=argumente.datenordner)
    return fenster_starten(ordner)


if __name__ == '__main__':
    sys.exit(main())
