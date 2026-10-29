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
import re
import secrets
import ssl
import sys
import tempfile
import threading
import time
import http.client
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from nebenkostenfix import aktualisierung
from nebenkostenfix import marke
from nebenkostenfix import windows_ordner
from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION

protokoll = logging.getLogger(__name__)

COOKIE = 'nk_huelle'
TITEL = marke.PRODUKT
# Was Bruecke.oeffnen dem Standardprogramm übergibt. Alles andere geht in den
# Speichern-Dialog: der Name stammt aus dem Upload, eine .exe startet nie.
OEFFNEN_ERLAUBT = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic'}


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

def _meldung(text: str, frage: bool = False, hinweis: bool = False) -> bool:
    """Meldung im Stil des Systems; unter Windows eine MessageBox."""
    if sys.platform == 'win32':  # pragma: no cover - Windows
        import ctypes
        # JA/NEIN + Frage, Hinweis (i) bzw. Fehler
        stil = 0x04 | 0x20 if frage else (0x40 if hinweis else 0x10)
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
        self._neustart = None
        self._basis = None  # der lokale Server, sobald er läuft

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
        # Nur der letzte Teil, ohne ':' (ADS-Streams) und Steuerzeichen;
        # '.' und ' ' am Rand weg, damit '..' nicht aus dem Ordner führt.
        letzter = re.split(r'[\\/]', str(dateiname))[-1]  # beide Trenner, auf jedem System
        name = re.sub(r'[^\w.\- ]', '_', letzter).strip(' .') or 'datei'
        if Path(name).suffix.lower() not in OEFFNEN_ERLAUBT:
            # Altbestand mit fremdem Typ bleibt erreichbar, startet aber nicht.
            return self.speichern(name, inhalt_base64)
        ordner = Path(tempfile.gettempdir()) / TITEL
        ordner.mkdir(exist_ok=True)
        pfad = ordner / name
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

    def server_verbinden(self, adresse: str):
        """Karte „Mit einem Server verbinden“ (#45): erst prüfen, dann nur
        ``[Server] Adresse`` eintragen und neu starten. Scheitert die
        Prüfung, bleibt die INI, wie sie ist. Der Datenordner bleibt immer."""
        if not _fenster_bei(self._fenster, self._basis):
            # Eine fremde Seite im Fenster soll die App nicht still umstellen.
            return {'ok': False, 'meldung': FREMDE_SEITE}
        ok, meldung, endadresse = server_pruefen(adresse)
        if not ok:
            return {'ok': False, 'meldung': meldung}
        windows_ordner.einstellungen_schreiben(server=endadresse)
        if self._neustart:
            # Kurz warten, damit die Oberfläche „startet jetzt neu“ zeigen kann.
            zeitgeber = threading.Timer(NEUSTART_NACH, self._neustart)
            zeitgeber.daemon = True
            zeitgeber.start()
        return {'ok': True, 'adresse': endadresse}


# --- Servermodus (#45): die App als Fenster auf einen NebenkostenFix-Server ---

NICHT_ERREICHBAR = ('Der Server ist nicht erreichbar. Stimmt die Adresse, und ist der '
                    'Server eingeschaltet?')
KEIN_NK = 'Unter dieser Adresse antwortet kein NebenkostenFix.'
ZERTIFIKAT = ('Das Zertifikat des Servers ist nicht vertrauenswürdig. Die Verbindung '
              'wurde nicht aufgebaut.')
VERSCHLUESSELUNG = ('Eine verschlüsselte Verbindung ist nicht möglich. Läuft der Server '
                    'ohne https? Dann tragen Sie die Adresse mit http:// ein.')
WEITERLEITUNG = ('Der Server leitet auf eine andere Adresse weiter ({ziel}). Bitte tragen '
                 'Sie diese Adresse direkt ein.')
OHNE_PFAD = 'Bitte nur die Adresse ohne Pfad eintragen, zum Beispiel https://server:8080.'
FREMDE_SEITE = 'Die Verbindung lässt sich nur in den Einstellungen dieser App ändern.'
STANDARDPORT = {'http': 80, 'https': 443}
ZURUECK_FRAGE = ('Zurück zu den Daten auf diesem Rechner? Die Verbindung zum Server wird '
                 'getrennt. Auf dem Server und auf diesem Rechner geht nichts verloren.')
NEUSTART_NACH = 1.5  # Sekunden
RUECKSPRUENGE = 3  # binnen 10 Sekunden, danach die Offline-Seite
UPDATE_FRAGE = ('Eine neue Version von NebenkostenFix ist verfügbar ({version}). Jetzt '
                'installieren? Die App startet danach neu.')


def neustart_umgebung(umgebung=None) -> dict:
    """Die Umgebung des neuen Prozesses: ohne das, was ``anwendung_laden``
    für diesen Lauf gesetzt hat."""
    umgebung = dict(os.environ if umgebung is None else umgebung)
    for name in ('NK_DESKTOP', 'DATA_DIR', 'BACKUP_ZIELE'):
        umgebung.pop(name, None)
    umgebung['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return umgebung


def neu_starten() -> None:
    """Nach dem Schließen des Fensters dieselbe App noch einmal starten."""
    # Bandit-Ausnahme (B404): nur das eigene Programm, feste Argumente
    import subprocess  # nosec B404
    befehl = [sys.executable]
    if not getattr(sys, 'frozen', False):
        befehl.append(str(Path(__file__).resolve()))  # aus den Quellen
    # Bandit-Ausnahme (B603): das eigene Programm, keine Eingabe von außen
    subprocess.Popen(befehl, env=neustart_umgebung(), close_fds=True)  # nosec B603


def adresse_normieren(text) -> str | None:
    """``schema://host[:port]`` oder None. Ohne Schema gilt https; kein Pfad,
    weil die Oberfläche absolute Pfade (``/api/...``) nutzt."""
    text = str(text or '').strip()
    if not text:
        return None
    if '://' not in text:
        text = 'https://' + text
    try:
        teile = urllib.parse.urlsplit(text)
        port = teile.port
    except ValueError:
        return None
    schema = teile.scheme.lower()
    if schema not in STANDARDPORT or not teile.hostname or '@' in teile.netloc \
            or not re.fullmatch(r'[\w.\-:\[\]%]+', teile.netloc) \
            or teile.path not in ('', '/') or teile.query or teile.fragment:
        return None
    host = teile.hostname
    if ':' in host:
        host = f'[{host}]'  # IPv6
    return f'{schema}://{host}' + (f':{port}' if port is not None else '')


def _ursprung(url) -> tuple | None:
    try:
        teile = urllib.parse.urlsplit(str(url or ''))
        schema = teile.scheme.lower()
        port = teile.port or STANDARDPORT.get(schema)
    except ValueError:
        return None
    if schema not in STANDARDPORT or not teile.hostname:
        return None
    return schema, teile.hostname.lower(), port


def _gleicher_ursprung(url, basis) -> bool:
    eigen = _ursprung(url)
    return eigen is not None and eigen == _ursprung(basis)


def _fenster_bei(fenster, basis) -> bool:
    """Zeigt das Fenster gerade eine Seite von ``basis``? Grundlage jeder
    Brückenmethode, die mehr kann als ein Browser."""
    try:
        jetzt = fenster.get_current_url()
    except Exception:  # noqa: BLE001 -- ohne Adresse kein Zugriff
        protokoll.debug('Adresse des Fensters nicht lesbar', exc_info=True)
        jetzt = None
    if _gleicher_ursprung(jetzt, basis):
        return True
    protokoll.warning('Brücke verweigert: Seite %s gehört nicht zu %s', jetzt, basis)
    return False


def _nach_https(basis: str, ziel: str) -> str | None:
    """Die eine Weiterleitung, die die Prüfung übernimmt: http://host →
    https://host, gleicher Host, beide Male der Standardport."""
    alt, neu = _ursprung(basis), _ursprung(ziel)
    if alt and neu and alt == ('http', neu[1], 80) and neu[0] == 'https' and neu[2] == 443:
        host = neu[1]
        return f'https://[{host}]' if ':' in host else f'https://{host}'
    return None


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen kommen als HTTPError an, statt still gefolgt zu werden."""

    def redirect_request(self, *args, **kwargs):
        return None


def _ssl_meldung(grund) -> str | None:
    if isinstance(grund, ssl.SSLCertVerificationError):
        return ZERTIFIKAT
    if isinstance(grund, ssl.SSLError):
        return VERSCHLUESSELUNG
    return None


def server_pruefen(adresse, zeit: float = 5, _weiter: bool = True):
    """``(ok, meldung, endadresse)``: antwortet unter der Adresse ein
    NebenkostenFix? ``/api/health`` ist seit 0.9.0 gleich."""
    basis = adresse_normieren(adresse)
    if basis is None:
        return False, OHNE_PFAD, None
    oeffner = urllib.request.build_opener(_KeineWeiterleitung)
    try:
        # Bandit-Ausnahme (B310): adresse_normieren lässt nur http und https zu
        with oeffner.open(basis + '/api/health', timeout=zeit) as antwort:  # nosec B310
            inhalt = json.loads(antwort.read(65536))
    except urllib.error.HTTPError as fehler:  # vor URLError: Unterklasse davon
        if 300 <= fehler.code < 400:
            ziel = urllib.parse.urljoin(basis + '/api/health',
                                        fehler.headers.get('Location') or '')
            https = _nach_https(basis, ziel)
            if https and _weiter:
                return server_pruefen(https, zeit, _weiter=False)
            return False, WEITERLEITUNG.format(ziel=ziel[:200]), None
        return False, KEIN_NK, None
    except urllib.error.URLError as fehler:
        return False, _ssl_meldung(fehler.reason) or NICHT_ERREICHBAR, None
    except ssl.SSLError as fehler:  # vor OSError: Unterklasse davon
        return False, _ssl_meldung(fehler), None
    except OSError:  # auch TimeoutError
        return False, NICHT_ERREICHBAR, None
    except (ValueError, http.client.HTTPException):  # kein JSON, kaputte Antwort
        return False, KEIN_NK, None
    if not (isinstance(inhalt, dict) and inhalt.get('status') == 'ok' and 'message' in inhalt):
        return False, KEIN_NK, None
    return True, None, basis


class ServerBruecke:
    """Die Brücke im Servermodus: nur Speichern, Öffnen und die Projektseite.

    Mit Absicht keine Unterklasse von ``Bruecke`` -- pywebview gäbe sonst
    Ordnerwahl, Umzug und Umschalten an eine Seite, die vom Server kommt.
    Jede Methode prüft zuerst, ob das Fenster noch dort ist.
    """

    def __init__(self, basis: str):
        self._fenster = None
        self._basis = basis

    def _innen(self) -> Bruecke | None:
        if not _fenster_bei(self._fenster, self._basis):
            return None
        innen = Bruecke()
        innen._fenster = self._fenster
        return innen

    def speichern(self, dateiname: str, inhalt_base64: str):
        innen = self._innen()
        return innen.speichern(dateiname, inhalt_base64) if innen else None

    def oeffnen(self, dateiname: str, inhalt_base64: str, seite=None):
        innen = self._innen()
        return innen.oeffnen(dateiname, inhalt_base64, seite) if innen else None

    def extern_oeffnen(self, adresse: str):
        innen = self._innen()
        return innen.extern_oeffnen(adresse) if innen else False


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

    def neustart():
        zustand['neustart'] = True
        fenster.destroy()

    bruecke._neustart = neustart

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
            bruecke._basis = zustand['basis']
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
    if zustand.get('neustart'):
        neu_starten()
    return 0


def offline_seite(meldung: str, adresse: str) -> str:
    """Servermodus ohne Verbindung. Keine Knöpfe: der Weg führt über das Menü."""
    schleife = ''
    if adresse.startswith('http://'):
        schleife = ('<p>Sie werden immer wieder zur Anmeldung geschickt? Dann erwartet der '
                    'Server https. Tragen Sie die Adresse mit https:// ein.</p>')
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8"><style>'
        'body{font-family:"Segoe UI",system-ui,sans-serif;background:#F3F4F6;color:#111827;'
        'padding:48px;line-height:1.6}h1{font-size:22px}</style></head><body>'
        '<h1>Keine Verbindung zum Server</h1>'
        f'<p>{html.escape(meldung)} Versuchen Sie es über <em>Datei → Neu laden</em> erneut. '
        'Mit <em>Datei → Auf diesem Rechner arbeiten …</em> kommen Sie zurück zu Ihren '
        f'lokalen Daten.</p>{schleife}'
        f'<p><code>{html.escape(adresse)}</code></p></body></html>')


def update_anbieten(fenster) -> None:
    """App-Update im Servermodus (#45): ohne lokalen Server fragt das Fenster
    selbst. Gemerkt wird nur im lokalen App-Ordner, nie im Datenordner."""
    try:
        gefunden = aktualisierung.automatisch(SOFTWARE_VERSION, True,
                                              ordner=windows_ordner.lokaler_ordner())
    except Exception:  # noqa: BLE001 -- still wie die Suche beim Start (NK-175)
        protokoll.exception('Update-Suche im Servermodus gescheitert')
        return
    if not gefunden or not gefunden.get('installierbar'):
        return
    if not fenster.create_confirmation_dialog(TITEL, UPDATE_FRAGE.format(version=gefunden['version'])):
        return
    try:
        aktualisierung.installer_starten(aktualisierung.installer_laden(SOFTWARE_VERSION))
    except (aktualisierung.AktualisierungsFehler, OSError, ValueError) as fehler:
        _meldung(f'Das Update konnte nicht installiert werden. {fehler}')


def server_titel(adresse) -> str:
    """Fenstertitel im Servermodus, auch für eine von Hand eingetragene Adresse."""
    basis = adresse_normieren(adresse) or str(adresse)
    host = urllib.parse.urlsplit(basis).netloc or basis
    return f'{TITEL} – verbunden mit {host}' + (
        ' (unverschlüsselt)' if basis.startswith('http://') else '')


def server_fenster_starten(adresse: str) -> int:
    """Servermodus (#45): kein lokaler Server, der Datenordner bleibt zu."""
    import webview
    from webview.menu import Menu, MenuAction, MenuSeparator

    instanz = EineInstanz(windows_ordner.lokaler_ordner())
    if not instanz.erwerben():
        # Ohne eintragen: der zweite Start weckt niemanden, er meldet sich.
        _meldung(f'{TITEL} läuft bereits.')
        return 1

    bruecke = ServerBruecke(adresse)
    zustand = {'basis': None, 'spruenge': []}
    fenster = webview.create_window(
        server_titel(adresse), html=startseite(), js_api=bruecke,
        width=1440, height=900, min_size=(1024, 700), text_select=True)
    bruecke._fenster = fenster

    def laden():
        ok, meldung, endadresse = server_pruefen(adresse)
        zustand['spruenge'] = []
        if ok:
            zustand['basis'] = bruecke._basis = endadresse
            fenster.set_title(server_titel(endadresse))  # http → https übernommen
            fenster.load_url(endadresse + '/')
        else:
            zustand['basis'] = None
            fenster.load_html(offline_seite(meldung, adresse))

    def beim_laden(*_):
        # Zweite Linie hinter der Ursprungsprüfung der Brücke: fremde Seiten
        # bleiben nicht im Fenster.
        if not zustand['basis']:
            return
        try:
            jetzt = fenster.get_current_url()
        except Exception:  # noqa: BLE001 -- Fenster schon zu
            protokoll.debug('Adresse des Fensters nicht lesbar', exc_info=True)
            return
        if jetzt and not _gleicher_ursprung(jetzt, zustand['basis']):
            protokoll.warning('Fremde Seite %s, zurück zu %s', jetzt, zustand['basis'])
            # Leitet „/“ selbst weiter (Anmelde-Proxy), käme sie immer wieder.
            zeit = time.monotonic()
            zustand['spruenge'] = [t for t in zustand['spruenge'] if zeit - t < 10] + [zeit]
            if len(zustand['spruenge']) > RUECKSPRUENGE:
                zustand['basis'] = None
                fenster.load_html(offline_seite(WEITERLEITUNG.format(ziel=str(jetzt)[:200]),
                                                adresse))
                return
            fenster.load_url(zustand['basis'] + '/')

    fenster.events.loaded += beim_laden

    def zurueck():
        # Python-Rückruf aus dem Menü: die Server-Seite erreicht ihn nicht.
        if fenster.create_confirmation_dialog(TITEL, ZURUECK_FRAGE):
            windows_ordner.einstellungen_schreiben(server=None)
            zustand['neustart'] = True
            fenster.destroy()

    def ueber():
        _meldung(f'{TITEL} {SOFTWARE_VERSION}. Verbunden mit {zustand["basis"] or adresse}.',
                 hinweis=True)

    # Kein evaluate_js in die Seite (fremder Code, womöglich andere Version),
    # kein „Passwort vergessen“ (lokale Route).
    menue = [
        Menu('Datei', [
            MenuAction('Drucken', lambda: fenster.evaluate_js('window.print()')),
            MenuAction('Neu laden', lambda: threading.Thread(target=laden, daemon=True).start()),
            MenuSeparator(),
            MenuAction('Auf diesem Rechner arbeiten …', zurueck),
            MenuSeparator(),
            MenuAction('Beenden', fenster.destroy),
        ]),
        Menu('Hilfe', [MenuAction(f'Über {marke.PRODUKT}', ueber)]),
    ]

    def hochfahren():
        laden()
        # Das Update kommt von der Projektseite, nicht vom Server: auch offline.
        threading.Thread(target=update_anbieten, args=(fenster,), daemon=True).start()

    speicher = windows_ordner.lokaler_ordner() / 'WebView2'
    try:
        webview.start(hochfahren, menu=menue, private_mode=False, storage_path=str(speicher))
    finally:
        instanz.freigeben()
    if zustand.get('neustart'):
        neu_starten()
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
    if not argumente.datenordner:
        # Servermodus (#45) vor jeder Frage nach dem Datenordner: er wird
        # weder geöffnet noch angelegt. --datenordner heißt immer lokal.
        server = windows_ordner.einstellungen_lesen()['server']
        if server:
            return server_fenster_starten(server)
    ordner = datenordner_bestimmen(vorgabe=argumente.datenordner)
    return fenster_starten(ordner)


if __name__ == '__main__':
    sys.exit(main())
