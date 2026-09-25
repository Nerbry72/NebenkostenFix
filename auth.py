"""Anmeldung und Zugangssperre (NK-019).

Bis hierher war jede der 55 Routen ohne Anmeldung erreichbar, inklusive
Dateileser und Export. Wer die Adresse des Servers kannte, konnte Mietvertraege
herunterladen.

Der Ansatz ist deny-by-default: ``before_request`` sperrt jede Route, eine
Positivliste oeffnet gezielt drei Stellen. Die Liste arbeitet mit Endpunkt-
namen, nicht mit Pfaden. Ein Pfadvergleich laesst sich mit ``//api/health``
oder ``/api/health/..%2fexport`` austricksen, ein Endpunktname nicht: den
vergibt Flask erst, nachdem der Pfad aufgeloest ist.

Konten stehen mit Passwort-Hash in der Datenbank.
Wie sie entstehen (NK-127, Entscheidung E-1):

    1. Existiert kein Konto, leitet die Anmeldung auf /einrichtung. Diese
       Route verlangt einen Einmal-Code, den nur der Betreiber sehen kann:
       er steht im Protokoll des Servers (Docker-Log bzw. Windows-Tray).
       Er entsteht beim ersten Aufruf der Einrichtung, gilt genau fuer die
       eine Einrichtung und verfaellt mit ihr.
    2. Das zweite Konto (fuer den Partner) legt der angemeldete Betreiber
       in der Oberflaeche an -- mehr als zwei gibt die Route nicht her,
       Wohnungsverwaltung ist keine Mandantenverwaltung (ZIEL § 8).
    3. Weiter Kontofuehrung bleibt beim CLI, das nur mit lokalem Zugriff
       auf den Server funktioniert und darum als Berechtigung gilt:

    docker compose exec web flask users add vermieter      # selten noetig
    docker compose exec web flask users passwd vermieter   # Passwort vergessen
    docker compose exec web flask users list

Der Sitzungsschluessel (SECRET_KEY) braucht keine .env mehr: fehlt die
Umgebungsvariable, erzeugt die Anwendung einen und legt ihn im Datenordner
neben die Datenbank. Die Umgebungsvariable hat Vorrang, wer sie setzt, weiss
was er tut.
"""

import contextlib
import hmac
import html
import json
import logging
import os
import posixpath
import re
import secrets
import threading
import time
from urllib.parse import urlsplit
from datetime import datetime

import zeit
from functools import wraps

from flask import abort, jsonify, make_response, redirect, request, session, url_for

import anmeldeschutz
import marke
import umzug
from dateisperre import datei_einmalig_anlegen, dateisperre
from models import User, db

# Endpunkte, die ohne Anmeldung erreichbar bleiben. Bewusst kurz.
#   health_check /api/health. Der Docker-Healthcheck hat keine Sitzung.
#   login        Die Anmelderoute selbst. Sonst kann sich niemand anmelden.
#   einrichtung  Der erste Start: ohne Konto existiert kein Weg hinein,
#                die Route ist durch den Einmal-Code gesichert, der nur im
#                Serverprotokoll steht. Ist ein Konto vorhanden, leitet sie
#                zur Anmeldung weiter und nimmt nichts mehr entgegen.
#
# Zwei Eintraege standen bis NK-021 zusaetzlich hier und sind bewusst weg:
#
#   index   app.py:53 hinter '/'. Solange die Oberflaeche offen war, lud sie
#           ohne Anmeldung und zeigte leere Listen, weil jeder /api/-Aufruf
#           darin mit 401 antwortete. Jetzt leitet '/' auf die Anmeldung um.
#           Das ist Kriterium 1 von NK-021.
#   static  Flasks Auslieferer fuer /static/*. Er musste mit, sonst waere die
#           Umleitung ein Feigenblatt: /static/index.html liefert genau
#           dieselbe Oberflaeche wie '/'. Ausserdem stecken in app.js 188 KB
#           Geschaeftslogik samt jedem Routennamen, das geht Fremde nichts an.
#           Die Anmeldeseite braucht /static/ nicht, sie traegt ihr CSS selbst.
PUBLIC_ENDPOINTS = frozenset({
    'health_check',
    'login',
    'einrichtung',
})

# NK-155: was die Anmelde- und Einrichtungsseite vor der Anmeldung laden
# muss -- ihr Stil, das Zeichen, die Schrift. Nichts davon verrät etwas über
# den Bestand. Alles andere unter /static bleibt hinter der Anmeldung.
# umzug.js: die Übernahme eines Umzugspakets auf der Einrichtungsseite (NK-164).
# formular.js: deutsche Hinweise der Formularprüfung auf allen Anmeldeseiten.
OEFFENTLICHE_DATEIEN = ('anmeldung.css', 'umzug.js', 'formular.js')
OEFFENTLICHE_ORDNER = ('marke/', 'vendor/fonts/')


def oeffentliche_datei(name: str | None) -> bool:
    """Ob eine Datei unter /static ohne Anmeldung ausgeliefert wird."""
    if not name or '\\' in name or '..' in name.split('/'):
        return False
    norm = posixpath.normpath(name)
    if norm.startswith(('/', '..')):
        return False
    return norm in OEFFENTLICHE_DATEIEN or norm.startswith(OEFFENTLICHE_ORDNER)


SESSION_USER_KEY = 'user_id'
SESSION_NAME_KEY = 'username'


class AuthConfigError(RuntimeError):
    """Die Anmeldung ist nicht sicher konfigurierbar. Der Start bricht ab."""


BEISPIEL_SCHLUESSEL = frozenset({
    'default-fallback-secret-key', 'change-me', 'changeme', 'secret',
})


def _datenordner():
    """Der Ordner, in dem diese Instanz ihre Daten haelt (NK-132).

    Seit NK-132 bestimmt ``datenordner.datenordner()`` ihn: ``DATA_DIR``,
    sonst der Ordner der SQLite-Datei, sonst (Postgres im Entwicklerstapel)
    der alte Belegordner. Ist nichts davon da, gibt es keinen Ort, an dem ein
    erzeugter Schluessel den Neustart ueberleben wuerde -- darum Abbruch,
    statt still etwas Halbes zu tun.
    """
    import datenordner

    try:
        return str(datenordner.datenordner())
    except datenordner.DatenordnerFehler as fehler:
        raise AuthConfigError(
            "Der Sitzungsschlüssel soll in den Datenordner geschrieben werden, "
            "aber es ist keiner erkennbar. Setzen Sie DATA_DIR, oder setzen "
            "Sie SECRET_KEY als Umgebungsvariable, dann braucht die Anwendung "
            "keinen Ordner.") from fehler


def _pruefe_schluessel(schluessel, herkunft):
    """Gemeinsame Pruefung, egal ob der Schluessel aus der Umgebung oder aus
    der Datei kommt. Ohne echten Schluessel sind Anmeldesitzungen faelschbar:
    wer den Standardwert kennt, baut sich selbst ein angemeldetes Cookie.
    Darum bricht der Start ab, statt auf einen Standardwert zurueckzufallen.
    """
    schluessel = schluessel.strip()
    if not schluessel:
        raise AuthConfigError(
            f"Der Sitzungsschlüssel in {herkunft} ist leer. Löschen Sie die "
            "Datei, damit die Anwendung einen neuen erzeugt, oder setzen Sie "
            "die Umgebungsvariable SECRET_KEY."
        )
    if schluessel in BEISPIEL_SCHLUESSEL:
        raise AuthConfigError(
            f"Der Sitzungsschlüssel in {herkunft} steht noch auf dem "
            "Beispielwert "
            f"'{schluessel}'. Ersetzen Sie ihn durch einen Zufallswert: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(schluessel) < 16:
        raise AuthConfigError(
            f"Der Sitzungsschlüssel in {herkunft} ist mit "
            f"{len(schluessel)} Zeichen zu kurz. Mindestens 16, besser 64: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return schluessel


def _loese_secret_key():
    """Sitzungsschluessel: Umgebung hat Vorrang, sonst Datei, sonst erzeugen.

    Die Reihenfolge ist die der Nutzererwartung (E-1): Wer SECRET_KEY setzt,
    meint es so. Sonst liest die Anwendung die Datei ``secret_key`` im
    Datenordner neben der Datenbank, und nur wenn es die nicht gibt, wird ein
    Schluessel erzeugt und dort abgelegt (Dateirechte 0600: nur der
    Anwendungsbenutzer darf lesen). Ohne Umgebungsvariable und ohne Datei
    startet die Anwendung damit allein, ohne dass jemand eine Kommandozeile
    oeffnet -- genau das war der Haken an F-62.

    Rueckgabe: (schluessel, pfad, neu_erzeugt). pfad ist None, wenn die
    Umgebungsvariable geliefert hat; neu_erzeugt sagt, ob die Datei gerade
    frisch geschrieben wurde -- der Start protokolliert beide Unterschiede.
    """
    secret = (os.environ.get('SECRET_KEY') or '').strip()
    if secret:
        schluessel = _pruefe_schluessel(secret, 'der Umgebungsvariable SECRET_KEY')
        return schluessel, None, False
    ordner = _datenordner()
    pfad = os.path.join(ordner, 'secret_key')
    # F-74: erst vollstaendig schreiben, dann atomar unter den endgueltigen
    # Namen bringen. Ein zweiter Arbeiter, der im selben Augenblick startet,
    # liest so nie eine leere oder halbe Datei.
    inhalt, neu = datei_einmalig_anlegen(pfad, secrets.token_hex(32))
    return _pruefe_schluessel(inhalt, f'der Datei {pfad}'), pfad, neu


def current_user():
    """Der angemeldete Benutzer oder None."""
    user_id = session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        # Konto geloescht oder stillgelegt, waehrend die Sitzung lief.
        session.clear()
        return None
    return user


def _wants_json():
    """True, wenn der Aufrufer eine API-Antwort erwartet, keine Seite."""
    if request.path.startswith('/api/'):
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes
    # Strikt groesser, nicht groesser-gleich. Bei Accept: */* (curl, der
    # Testclient, mancher Browser beim Nachladen) sind beide gleich gewichtet,
    # der Aufrufer hat also gar keinen Wunsch geaeussert. Dann ist eine
    # Umleitung zur Anmeldung die bessere Antwort als ein 401, den niemand
    # liest: /api/ ist oben schon abgefangen, hier geht es um Browserpfade.
    return accept['application/json'] > accept['text/html']


def _sicheres_ziel(roh):
    """Macht aus einem next-Parameter ein Ziel, das im Programm bleibt.

    Der Wert kommt vom Aufrufer, und ein Aufrufer darf sich seinen Link selbst
    bauen. Ohne diese Pruefung wuerde /login?next=https://boese.example nach
    erfolgreicher Anmeldung dorthin leiten, und der Gast haette den Wechsel auf
    eine fremde Seite nicht bemerkt, weil er von der echten Anmeldung kam.

    Zugelassen ist nur ein Pfad auf dieser Anwendung: er beginnt mit genau
    einem Schraegstrich. // waere protokollrelativ (//boese.example) und /\
    lesen manche Browser genauso.
    """
    ziel = (roh or '').strip()
    if not ziel.startswith('/'):
        return '/'
    if ziel.startswith('//') or ziel.startswith('/\\'):
        return '/'
    if ziel.startswith('/login'):
        # Sonst landet man nach dem Anmelden wieder auf dem Anmeldefeld.
        return '/'
    return ziel


def _deny():
    if _wants_json():
        return jsonify({
            'error': 'Nicht angemeldet.',
            'code': 'auth_required'
        }), 401
    # full_path haengt immer ein ? an, auch ohne Parameter. Ohne das rstrip
    # steht nach der Umleitung /login?next=/? in der Adresszeile und danach
    # /? statt /. Funktioniert, sieht aber nach Panne aus.
    ziel = request.full_path
    if ziel.endswith('?'):
        ziel = ziel[:-1]
    return redirect(url_for('login', next=ziel))


def login_required(view):
    """Fuer Routen, die spaeter ausserhalb von before_request laufen."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return _deny()
        return view(*args, **kwargs)
    return wrapper


def _seitenkopf(titel: str) -> str:
    """Kopf der Anmelde-, Einrichtungs- und Passwortseite (NK-155): Marke,
    Schrift und Farben der Anwendung statt Systemschrift und fremdem Blau.
    Die Seiten stehen vor der Anmeldung; ``static`` ist dafuer frei."""
    return (
        '<!doctype html>\n<html lang="de"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{titel} – {marke.PRODUKT}</title>\n'
        '<link rel="icon" href="/static/marke/favicon.svg" type="image/svg+xml">\n'
        '<link rel="icon" href="/static/marke/favicon.ico" sizes="48x48">\n'
        '<link rel="stylesheet" href="/static/vendor/fonts/outfit/outfit.css">\n'
        '<link rel="stylesheet" href="/static/anmeldung.css">\n'
        '<script src="/static/formular.js?v=2"></script>\n'
        '</head><body class="anmeldung">\n'
        '<div class="anmelde-marke"><img src="/static/marke/zeichen.svg" alt="" '
        'width="44" height="44"><span>Nebenkosten<b>Fix</b></span></div>\n')


LOGIN_PAGE = _seitenkopf('Anmeldung') + """<form method="post" class="anmelde-karte">
 <h1>Anmelden</h1>
 <label for="username">Benutzername</label>
 <input id="username" name="username" autocomplete="username" autofocus required>
 <label for="password">Passwort</label>
 <input id="password" name="password" type="password"
        autocomplete="current-password" required>
 <button type="submit">Anmelden</button>
 __FEHLER__
</form></body></html>"""


def _login_page(fehler=None):
    block = f'<p class="fehler">{html.escape(fehler)}</p>' if fehler else ''
    return LOGIN_PAGE.replace('__FEHLER__', block)


# Ersteinrichtung (NK-127, E-1): dieselbe ruige Karte wie die Anmeldung,
# plus der Wegweisung zum Einmal-Code. Der Code selbst steht niemals in der
# Seite -- nur im Serverprotokoll, damit ihn keiner aus dem Netz lesen kann.
ERSTEINRICHTUNG_PAGE = _seitenkopf('Einrichtung') + """<form method="post" class="anmelde-karte">
 <h1>Einrichtung</h1>
 <p class="hinweis">Willkommen! Richten Sie Ihr Konto ein.__CODEHINWEIS__</p>
 <label for="username">Benutzername</label>
 <input id="username" name="username" autocomplete="username" maxlength="40"
        autofocus required>
 <label for="password">Passwort (mindestens 10 Zeichen)</label>
 <input id="password" name="password" type="password" minlength="10"
        autocomplete="new-password" required>
 <label for="password2">Passwort wiederholen</label>
 <input id="password2" name="password2" type="password" minlength="10"
        autocomplete="new-password" required>
 __CODEFELD__
 <button type="submit">Konto anlegen</button>
 __FEHLER__
</form>
__UMZUG__
</body></html>"""

# NK-164: der zweite Weg der Einrichtung -- den Bestand einer anderen
# Installation übernehmen (Umzugspaket .nkfix). Die Konten kommen aus dem
# Paket; angemeldet wird danach mit dem bisherigen Passwort.
UMZUG_KARTE = """<details class="anmelde-karte umzug-karte">
 <summary>Daten aus einer anderen Installation übernehmen</summary>
 <form id="umzug-form" data-desktop="__DESKTOP__">
 <p class="hinweis">Sie haben NebenkostenFix schon auf einem anderen Rechner genutzt?
 Exportieren Sie dort unter <b>Einstellungen → Sicherung → Alles exportieren</b> und
 wählen Sie die <code>.nkfix</code>-Datei hier aus. Danach melden Sie sich mit Ihrem
 bisherigen Konto an.</p>
 <label for="umzug-datei">Umzugspaket (.nkfix)</label>
 <input id="umzug-datei" type="file" accept=".nkfix,.nkbak,.gz">
 <button type="button" id="umzug-auswahl-knopf" class="zweitknopf" hidden>Paket auswählen</button>
 <p class="hilfe" id="umzug-auswahl-name"></p>
 <label for="umzug-passphrase">Passphrase (nur bei verschlüsselten Paketen)</label>
 <input id="umzug-passphrase" type="password" autocomplete="off">
 __UMZUGCODE__
 <progress id="umzug-fortschritt" max="1" value="0" hidden></progress>
 <button type="submit">Daten übernehmen</button>
 <p id="umzug-status" role="status" aria-live="polite"></p>
 <a id="umzug-weiter" class="knopf-link" href="/login" hidden>Zur Anmeldung</a>
 </form>
</details>
<script src="/static/umzug.js"></script>"""

UMZUG_CODE_FELD = """ <label for="umzug-code">Einmal-Code</label>
 <input id="umzug-code" autocomplete="one-time-code" required>"""


CODE_HINWEIS = (' Sie brauchen den Einmal-Code des Servers; er gilt nur für diese '
               'eine Einrichtung.')
CODE_FELD = """ <label for="code">Einmal-Code</label>
 <input id="code" name="code" autocomplete="one-time-code" required>
 <p class="hilfe">Der Einmal-Code steht in der Datei <code>ERSTEINRICHTUNG-CODE.txt</code>
 in Ihrem Datenordner: bei Docker in dem Ordner, den Sie als <code>/data</code> eingebunden
 haben (z. B. <code>daten/</code> neben der <code>docker-compose.yml</code>), auf einer
 Synology in der File Station. Außerdem steht er im Protokoll
 (<code>docker compose logs web</code>, Stichwort „Ersteinrichtung“).
 Er sieht aus wie <code>a3f9-72b1-0c4d-9e21</code>.</p>"""


def _einrichtungsseite(fehler=None, mit_code=True):
    """Die Einrichtungsseite. In der Windows-App (NK-079) ohne Code: wer am
    eigenen Rechner das Programmfenster bedient, ist berechtigt (E-1)."""
    block = f'<p class="fehler">{html.escape(fehler)}</p>' if fehler else ''
    seite = ERSTEINRICHTUNG_PAGE.replace('__FEHLER__', block)
    seite = seite.replace('__CODEHINWEIS__', CODE_HINWEIS if mit_code else '')
    seite = seite.replace('__CODEFELD__', CODE_FELD if mit_code else '')
    umzug_karte = UMZUG_KARTE.replace('__DESKTOP__', '0' if mit_code else '1')
    umzug_karte = umzug_karte.replace('__UMZUGCODE__', UMZUG_CODE_FELD if mit_code else '')
    return seite.replace('__UMZUG__', umzug_karte)


def entwicklung_angemeldet(app) -> bool:
    """Ob die Entwicklerroute fuer die Zuruecksetzung angemeldet ist (NK-123).

    Die Route steht in ``debug_routen.py``, einer Datei, die das
    Auslieferungsabbild nicht enthaelt (NK-040, R-DSGVO-01). Die Oberflaeche
    soll den Knopf deshalb nur zeigen, wenn die Route in der laufenden
    Anwendung existiert -- nicht wegen einer Umgebungsvariablen: die kann
    versehentlich gesetzt sein, wo die Datei fehlt. Im Auslieferungsbuild
    ist die Route nicht angemeldet, der Knopf bleibt verborgen.
    """
    return any(regel.rule == '/api/debug/reset_db'
               for regel in app.url_map.iter_rules())


# Der Einmal-Code der Ersteinrichtung (NK-127, NK-149).
#
# F-73: Bis NK-149 lebte er im Speicher des Prozesses. Mit zwei gunicorn-
# Arbeitern gab es damit zwei Codes, und die Einrichtung scheiterte zufaellig
# je nachdem, welcher Arbeiter das Formular bekam. Jetzt liegt er als Datei
# ``ersteinrichtung_code`` im Datenordner (Rechte 0600, wie der Sitzungs-
# schluessel), alle Arbeiter lesen dieselbe Datei unter einer Dateisperre.
#
# F-75: 64 Bit statt 32, Vergleich in konstanter Zeit, und nach
# EINMAL_CODE_VERSUCHE Fehlversuchen verfaellt der Code; ein neuer steht im
# Protokoll. Raten im LAN lohnt damit nicht mehr.
#
# Jeder Prozess schreibt den gueltigen Code einmal ins eigene Protokoll, auch
# wenn ein anderer Arbeiter ihn erzeugt hat -- nach einem Neustart soll der
# Betreiber ihn im frischen Log finden. Die Zeilen nennen dann denselben Code.
EINMAL_CODE_VERSUCHE = 5
EINMAL_CODE_DATEI = 'ersteinrichtung_code'
# NK-163 (F-91): derselbe Code lesbar für Menschen, ohne Protokoll. Wer eine
# Synology oder einen NAS-Container einrichtet, findet ihn in der File
# Station bzw. im eingebundenen Ordner. Wer den Datenordner lesen kann, ist
# berechtigt (er kann auch die Datenbank lesen); die Datei verschwindet mit
# der Einrichtung.
EINMAL_CODE_TEXTDATEI = 'ERSTEINRICHTUNG-CODE.txt'
EINMAL_CODE_TEXT = (
    'NebenkostenFix -- Einmal-Code für die Einrichtung\n'
    '\n'
    '    {code}\n'
    '\n'
    'Geben Sie diesen Code auf der Einrichtungsseite im Feld „Einmal-Code“ ein.\n'
    'Er gilt nur für die erste Einrichtung. Nach {versuche} Fehlversuchen\n'
    'verfällt er; dann steht hier ein neuer. Nach der Einrichtung wird diese\n'
    'Datei gelöscht.\n'
)

# Nur noch Rueckfall ohne Datenordner (Postgres ohne NAS_MOUNT_PATH) und
# Merker, welcher Code in diesem Prozess schon protokolliert ist.
_ersteinrichtung = {'code': None, 'fehlversuche': 0, 'protokolliert': None}
_ersteinrichtung_sperre = threading.Lock()


def _neuer_einmal_code():
    return secrets.token_hex(8)  # 64 Bit


def _code_anzeige(code):
    return '-'.join(code[i:i + 4] for i in range(0, len(code), 4))


def _code_ablage():
    """Pfad der Code-Datei, oder None ohne erkennbaren Datenordner."""
    try:
        ordner = _datenordner()
    except AuthConfigError:
        return None
    os.makedirs(ordner, exist_ok=True)
    return os.path.join(ordner, EINMAL_CODE_DATEI)


class _CodeZustand:
    """Liest und schreibt den Zustand unter der Sperre, Datei oder Speicher."""

    def __init__(self, pfad):
        self.pfad = pfad

    def __enter__(self):
        if self.pfad is None:
            _ersteinrichtung_sperre.acquire()
            self._sperre = None
            return self
        self._sperre = dateisperre(self.pfad + '.lock')
        self._sperre.__enter__()
        return self

    def __exit__(self, *exc):
        if self._sperre is None:
            _ersteinrichtung_sperre.release()
        else:
            self._sperre.__exit__(*exc)
        return False

    def lesen(self):
        if self.pfad is None:
            if _ersteinrichtung['code'] is None:
                return None
            return {'code': _ersteinrichtung['code'],
                    'fehlversuche': _ersteinrichtung['fehlversuche']}
        try:
            with open(self.pfad, encoding='utf-8') as datei:
                daten = json.load(datei)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None  # unlesbar: neu erzeugen ist sicherer als raten
        if not isinstance(daten, dict) or not re.fullmatch(
                r'[0-9a-f]{16}', str(daten.get('code', ''))):
            return None
        return {'code': daten['code'],
                'fehlversuche': int(daten.get('fehlversuche') or 0)}

    def schreiben(self, zustand):
        if self.pfad is None:
            _ersteinrichtung['code'] = zustand['code']
            _ersteinrichtung['fehlversuche'] = zustand['fehlversuche']
            return
        temp = f'{self.pfad}.{os.getpid()}.tmp'
        kennung = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(kennung, 'w', encoding='utf-8') as datei:
            json.dump(zustand, datei)
        os.replace(temp, self.pfad)
        self._textdatei_schreiben(zustand['code'])

    def _textdatei(self):
        return os.path.join(os.path.dirname(self.pfad), EINMAL_CODE_TEXTDATEI)

    def _textdatei_schreiben(self, code):
        ziel = self._textdatei()
        temp = f'{ziel}.{os.getpid()}.tmp'
        try:
            with open(temp, 'w', encoding='utf-8', newline='\r\n') as datei:
                datei.write(EINMAL_CODE_TEXT.format(code=_code_anzeige(code),
                                                    versuche=EINMAL_CODE_VERSUCHE))
            os.replace(temp, ziel)
        except OSError as fehler:
            # Das Protokoll hat den Code weiterhin; die Datei ist eine Hilfe.
            logging.getLogger(__name__).warning(
                'ERSTEINRICHTUNG-CODE.txt ließ sich nicht schreiben: %s', fehler)

    def loeschen(self):
        if self.pfad is None:
            _ersteinrichtung['code'] = None
            _ersteinrichtung['fehlversuche'] = 0
            return
        # Schon weg (paralleler Arbeiter) ist dasselbe Ergebnis.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.pfad)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._textdatei())


def _code_protokollieren(app, code, grund=None):
    if _ersteinrichtung['protokolliert'] == code:
        return
    _ersteinrichtung['protokolliert'] = code
    zusatz = f' ({grund})' if grund else ''
    app.logger.warning(
        "Ersteinrichtung: Es gibt noch kein Konto. Der Einmal-Code für "
        "die Einrichtung lautet: %s%s  (gültig bis zur ersten Einrichtung "
        "oder bis zu %d Fehlversuchen, nur hier im Protokoll lesbar)",
        _code_anzeige(code), zusatz, EINMAL_CODE_VERSUCHE)


def _einmal_code_legen(app):
    """Erzeugt den Einmal-Code bei Bedarf und schreibt ihn ins Protokoll.

    Nur das Protokoll: Wer an den Server herankommt (Docker-Host, bei der
    Windows-App der eigene Rechner), ist berechtigt, ein Konto anzulegen.
    Wer nur die Website kennt, sieht den Code nirgends.
    """
    with _CodeZustand(_code_ablage()) as ablage:
        zustand = ablage.lesen()
        if zustand is None:
            zustand = {'code': _neuer_einmal_code(), 'fehlversuche': 0}
            ablage.schreiben(zustand)
    _code_protokollieren(app, zustand['code'])
    return zustand['code']


def _einmal_code_pruefen(app, roh):
    """Prueft die Eingabe gegen den geteilten Code und zaehlt Fehlversuche.

    Tolerant bei Gross-/Kleinschreibung, Leer- und Trennzeichen. Nach
    EINMAL_CODE_VERSUCHE Fehlversuchen entsteht ein neuer Code (F-75).
    """
    eingabe = re.sub(r'[\s-]', '', (roh or '')).lower()
    neu = None
    with _CodeZustand(_code_ablage()) as ablage:
        zustand = ablage.lesen()
        if zustand is None:
            zustand = {'code': _neuer_einmal_code(), 'fehlversuche': 0}
            ablage.schreiben(zustand)
        ok = bool(eingabe) and hmac.compare_digest(
            eingabe.encode(), zustand['code'].encode())
        if not ok:
            zustand['fehlversuche'] += 1
            if zustand['fehlversuche'] >= EINMAL_CODE_VERSUCHE:
                zustand = {'code': _neuer_einmal_code(), 'fehlversuche': 0}
                neu = zustand['code']
            ablage.schreiben(zustand)
    if neu:
        _code_protokollieren(
            app, neu, f'neu nach {EINMAL_CODE_VERSUCHE} Fehlversuchen')
    else:
        _code_protokollieren(app, zustand['code'])
    return ok


def _einmal_code_verfallen():
    """Nach der erfolgreichen Einrichtung ist der Code nichts mehr wert."""
    with _CodeZustand(_code_ablage()) as ablage:
        ablage.loeschen()
    _ersteinrichtung['protokolliert'] = None


# --- Web-Haertung (NK-128, F-56, F-57, F-59) --------------------------------

SESSION_AKTIV_KEY = 'aktiv'
SCHREIBENDE_METHODEN = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# Die Oberflaeche braucht Inline-Handler (onclick=) und Inline-Stile; beides
# bleibt erlaubt, aber nur von der eigenen Adresse. Kein fremdes Skript, kein
# Rahmen um die Anwendung, keine Plugins, Formulare nur an sich selbst.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "frame-src 'self' blob:; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")


def _leerlauf_s() -> int:
    """Abmeldung nach so vielen Sekunden ohne Anfrage (Standard 60 min)."""
    roh = (os.environ.get('SITZUNG_LEERLAUF_MIN') or '').strip()
    try:
        minuten = int(roh) if roh else 60
    except ValueError:
        minuten = 60
    return max(1, minuten) * 60


def _hinter_https() -> bool:
    return os.environ.get('BEHIND_HTTPS', '').strip().lower() in ('1', 'true', 'yes')


def _erlaubte_hosts() -> set[str]:
    """Hosts, von denen schreibende Anfragen kommen duerfen (CSRF, F-57)."""
    hosts = {request.host.lower()}
    weitergeleitet = request.headers.get('X-Forwarded-Host')
    if weitergeleitet:
        hosts.add(weitergeleitet.split(',')[0].strip().lower())
    for eintrag in (os.environ.get('ERLAUBTE_URSPRUENGE') or '').split(','):
        eintrag = eintrag.strip().lower()
        if eintrag:
            hosts.add(urlsplit(eintrag).netloc or eintrag)
    return hosts


def fremder_ursprung() -> str | None:
    """Liefert den fremden Ursprung einer schreibenden Anfrage, sonst None.

    Ein Browser schickt bei jeder schreibenden Anfrage ``Origin`` mit (bei
    ``fetch`` auch auf derselben Adresse). Stimmt dessen Host nicht mit dem
    der Anwendung ueberein, kommt die Anfrage von einer fremden Seite, die
    den angemeldeten Browser fernsteuert -- abgelehnt. ``Sec-Fetch-Site:
    cross-site`` ist dasselbe Signal in neueren Browsern. Ohne beide Koepfe
    (Kommandozeile, Tests) gibt es keinen Browser, der verfuehrt werden
    koennte; dann entscheidet der Referer, falls vorhanden.
    """
    if request.method not in SCHREIBENDE_METHODEN:
        return None
    if request.headers.get('Sec-Fetch-Site', '').lower() == 'cross-site':
        return request.headers.get('Origin') or 'cross-site'
    herkunft = request.headers.get('Origin')
    if herkunft == 'null':
        return 'null'  # undurchsichtiger Ursprung (Sandbox, file://)
    if not herkunft:
        herkunft = request.headers.get('Referer')
    if not herkunft:
        return None
    host = urlsplit(herkunft).netloc.lower()
    if host not in _erlaubte_hosts():
        return herkunft
    return None


def sicherheitskoepfe(antwort):
    """Die Koepfe jeder Antwort (F-57). Bestehende Werte bleiben stehen:
    die Dateiauslieferung setzt ihre eigene, strengere CSP (NK-129)."""
    koepfe = antwort.headers
    koepfe.setdefault('Content-Security-Policy', CSP)
    koepfe.setdefault('X-Content-Type-Options', 'nosniff')
    koepfe.setdefault('X-Frame-Options', 'DENY')
    koepfe.setdefault('Referrer-Policy', 'same-origin')
    koepfe.setdefault('Permissions-Policy',
                      'camera=(), microphone=(), geolocation=(), payment=()')
    koepfe.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
    if _hinter_https():
        koepfe.setdefault('Strict-Transport-Security', 'max-age=31536000')
    # Nichts mit Mieterdaten landet in einem geteilten Zwischenspeicher.
    if request.path.startswith('/api/') and 'Cache-Control' not in koepfe:
        koepfe['Cache-Control'] = 'no-store'
    return antwort


def _anmeldeschutz_ordner():
    try:
        ordner = _datenordner()
    except AuthConfigError:
        return None
    os.makedirs(ordner, exist_ok=True)
    return ordner


def _sitzung_beginnen(user):
    session.clear()
    session[SESSION_USER_KEY] = user.id
    session[SESSION_NAME_KEY] = user.username
    session[SESSION_AKTIV_KEY] = int(time.time())
    session.permanent = False


def init_auth(app):
    """Haengt Sperre, Anmeldung, Ersteinrichtung und CLI an die Anwendung."""
    schluessel, schluessel_pfad, neu_erzeugt = _loese_secret_key()
    app.config['SECRET_KEY'] = schluessel
    if schluessel_pfad is None:
        app.logger.info(
            "Sitzungsschluessel aus der Umgebungsvariable SECRET_KEY uebernommen.")
    elif neu_erzeugt:
        app.logger.warning(
            "Sitzungsschluessel neu erzeugt und in der Datei %s gespeichert. "
            "Eine gesetzte Umgebungsvariable SECRET_KEY hat Vorrang; die "
            "Datei gehoert zum Datenbestand und darf nicht verloren gehen.",
            schluessel_pfad)
    else:
        app.logger.info(
            "Sitzungsschluessel aus der Datei %s gelesen. Eine gesetzte "
            "Umgebungsvariable SECRET_KEY hat Vorrang.", schluessel_pfad)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Secure nur setzen, wenn wirklich HTTPS davor haengt. Auf einem nackten
    # http://hostname:6060 wuerde der Browser das Cookie sonst wegwerfen und
    # niemand kaeme mehr hinein.
    app.config['SESSION_COOKIE_SECURE'] = _hinter_https()
    # NK-079: die Windows-App setzt NK_DESKTOP=1, bevor sie app importiert.
    app.config.setdefault('DESKTOP', os.environ.get('NK_DESKTOP') == '1')
    if not _hinter_https() and not app.config.get('DESKTOP'):
        # F-59: Ohne HTTPS geht das Passwort im Klartext durchs Netz. Im LAN
        # des Vermieters oft hingenommen, aber es soll bewusst geschehen.
        app.logger.warning(
            "Die Anwendung läuft ohne HTTPS (BEHIND_HTTPS ist nicht gesetzt). "
            "Passwort und Mieterdaten gehen unverschlüsselt durchs Netz. "
            "Für den Zugriff über das Netzwerk einen Reverse Proxy mit HTTPS "
            "vorschalten und BEHIND_HTTPS=1 setzen (siehe README).")

    @app.after_request
    def _koepfe(antwort):
        return sicherheitskoepfe(antwort)

    @app.before_request
    def _require_login():
        if request.method == 'OPTIONS':
            return None
        fremd = fremder_ursprung()
        if fremd is not None:
            # F-57: Eine fremde Seite steuert den angemeldeten Browser.
            app.logger.warning(
                "Schreibende Anfrage von fremdem Ursprung abgelehnt: %s %s "
                "(Ursprung %s)", request.method, request.path, fremd)
            return jsonify({
                'error': 'Anfrage von einer fremden Seite abgelehnt.',
                'code': 'fremder_ursprung'}), 403
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if (request.endpoint in umzug.VOR_DER_EINRICHTUNG and current_user() is None
                and (app.config.get('DESKTOP') or request.headers.get('X-Einmal-Code')
                     or (request.get_json(silent=True) or {}).get('code'))
                and db.session.query(User.id).first() is None):
            # NK-164: eine frische Installation übernimmt den alten Bestand.
            # Ohne Code bleibt es bei der Sperre; ob der Code stimmt, prüft
            # die Route selbst (umzug._zugang), in der App gilt E-1.
            return None
        if request.endpoint == 'static' and oeffentliche_datei(
                (request.view_args or {}).get('filename')):
            return None
        if app.config.get('DESKTOP') and request.endpoint == 'huelle_passwort':
            # Nur in der Windows-App: hinter dem Start-Token der Huelle.
            return None
        if request.endpoint is None:
            # Unbekannter Pfad. Erst sperren, dann 404: sonst verraet die
            # Antwort einem Fremden, welche Pfade es gibt.
            return _deny()
        if current_user() is None:
            return _deny()
        # Abmeldung nach Leerlauf (F-57). Aeltere Sitzungen ohne Zeitstempel
        # bekommen jetzt einen und laufen ab da.
        jetzt = int(time.time())
        zuletzt = session.get(SESSION_AKTIV_KEY)
        if zuletzt is not None and jetzt - int(zuletzt) > _leerlauf_s():
            session.clear()
            return _deny()
        if zuletzt is None or jetzt - int(zuletzt) >= 60:
            session[SESSION_AKTIV_KEY] = jetzt
        return None

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET':
            if current_user() is not None:
                return redirect('/')
            if db.session.query(User.id).first() is None:
                # Erster Start: statt einer Anmeldung, die niemals gelingen
                # kann, direkt zur Einrichtung (E-1).
                return redirect(url_for('einrichtung'))
            return _login_page()

        data = request.get_json(silent=True) or request.form
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''

        # NK-128 (F-56): Durchprobieren wird teuer und dann gesperrt.
        ordner = _anmeldeschutz_ordner()
        adresse = request.remote_addr
        rest = anmeldeschutz.gesperrt_fuer(ordner, username, adresse)
        if rest:
            minuten = max(1, (rest + 59) // 60)
            text = ('Zu viele Fehlversuche. Die Anmeldung ist für '
                    f'{minuten} Minuten gesperrt.')
            antwort = make_response(
                jsonify({'error': text, 'code': 'anmeldung_gesperrt'})
                if _wants_json() else _login_page(text), 429)
            antwort.headers['Retry-After'] = str(rest)
            return antwort

        user = User.query.filter_by(username=username).first()
        # Immer beide Pruefungen durchlaufen, damit ein falscher Benutzername
        # nicht schneller antwortet als ein falsches Passwort.
        ok = user is not None and user.is_active and user.check_password(password)
        if not ok:
            anzahl = anmeldeschutz.fehlversuch(ordner, username, adresse)
            time.sleep(anmeldeschutz.wartezeit(anzahl))
            if _wants_json():
                return jsonify({'error': 'Benutzername oder Passwort stimmt nicht.'}), 401
            return _login_page('Benutzername oder Passwort stimmt nicht.'), 401

        anmeldeschutz.erfolg(ordner, username, adresse)
        _sitzung_beginnen(user)
        user.last_login_at = zeit.jetzt_utc()
        db.session.commit()

        if _wants_json():
            return jsonify({'username': user.username}), 200
        return redirect(_sicheres_ziel(request.args.get('next')))

    @app.route('/einrichtung', methods=['GET', 'POST'])
    def einrichtung():
        """Erster Start: genau ein Konto, gesichert durch den Einmal-Code.

        Die Route bleibt offen, solange kein Konto existiert, und nimmt
        danach nichts mehr an -- die zweite Einrichtung ist ein Angriffs-
        fall (wer die Website kennt, koennte sich sonst ein Konto bauen).
        """
        hat_konto = db.session.query(User.id).first() is not None
        if hat_konto:
            if _wants_json():
                return jsonify(
                    {'error': 'Es gibt schon ein Konto. Melden Sie sich an.'}), 409
            return redirect(url_for('login'))

        desktop = bool(app.config.get('DESKTOP'))
        if request.method == 'GET':
            if not desktop:
                _einmal_code_legen(app)
            return _einrichtungsseite(mit_code=not desktop)

        data = request.get_json(silent=True) or request.form
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        wiederholung = data.get('password2') or ''

        def ablehnung(text):
            if _wants_json():
                return jsonify({'error': text}), 400
            return _einrichtungsseite(text, mit_code=not desktop), 400

        # NK-079: in der Windows-App gilt der lokale Zugriff als Berechtigung
        # (E-1) -- das Fenster erreicht nur, wer den Start-Token der Huelle hat.
        if not desktop and not _einmal_code_pruefen(app, data.get('code')):
            return ablehnung(
                'Der Einmal-Code stimmt nicht. Er steht im Protokoll des '
                'Servers (Docker: docker compose logs web). Nach '
                f'{EINMAL_CODE_VERSUCHE} Fehlversuchen steht dort ein neuer.')
        if not username:
            return ablehnung('Bitte geben Sie einen Benutzernamen ein.')
        if len(username) > 40:
            return ablehnung(
                'Der Benutzername darf höchstens 40 Zeichen haben.')
        if User.query.filter_by(username=username).first():
            return ablehnung(f"Das Konto '{username}' gibt es schon.")
        if len(password) < 10:
            return ablehnung('Das Passwort muss mindestens 10 Zeichen haben.')
        if password != wiederholung:
            return ablehnung('Die Passwörter stimmen nicht überein.')

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        _einmal_code_verfallen()
        app.logger.info("Ersteinrichtung abgeschlossen: Konto '%s' angelegt.",
                        username)

        _sitzung_beginnen(user)
        if _wants_json():
            return jsonify({'username': username}), 201
        return redirect('/')

    @app.route('/logout', methods=['POST', 'GET'])
    def logout():
        """Abmelden nur per POST (F-57). Ein GET -- ein Link, ein Bild auf
        einer fremden Seite -- beendet keine Sitzung mehr; er fuehrt nur
        dorthin zurueck, wo man hingehoert."""
        if request.method == 'GET':
            if current_user() is None:
                return redirect(url_for('login'))
            return redirect('/')
        session.clear()
        if _wants_json():
            return jsonify({'status': 'abgemeldet'}), 200
        return redirect(url_for('login'))

    @app.route('/api/auth/me', methods=['GET'])
    def auth_me():
        user = current_user()
        return jsonify({
            'username': user.username,
            'last_login_at': zeit.als_ortszeit(user.last_login_at),
            # Nur so viel, wie die Oberflaeche braucht, um den Knopf zu
            # verbergen: ob die Entwicklerroute da ist (NK-123).
            'entwicklung': entwicklung_angemeldet(app),
            # NK-154: die Windows-App erklaert "Passwort vergessen" anders.
            'desktop': bool(app.config.get('DESKTOP')),
            # NK-162: die Oberfläche warnt fünf Minuten vor der Abmeldung.
            'leerlauf_s': _leerlauf_s(),
        }), 200

    @app.route('/api/konto/passwort', methods=['PUT'])
    def konto_passwort_aendern():
        """Eigenes Passwort wechseln (NK-127). Ohne das alte Passwort geht
        nichts: wer eine offene Sitzung uebernimmt, soll damit nicht den
        Zugang dauerhaft uebernehmen koennen.
        """
        user = current_user()
        if user is None:
            return _deny()
        data = request.get_json(silent=True) or {}
        alt = data.get('altes_passwort') or ''
        neu = data.get('neues_passwort') or ''
        if not user.check_password(alt):
            return jsonify({'error': 'Das alte Passwort stimmt nicht.'}), 400
        if len(neu) < 10:
            return jsonify(
                {'error': 'Das neue Passwort muss mindestens 10 Zeichen haben.'}), 400
        user.set_password(neu)
        db.session.commit()
        return jsonify({'status': 'Passwort geändert'}), 200

    @app.route('/api/konten', methods=['GET'])
    def konten_auflisten():
        """Die Konten dieser Instanz fuer die Oberflaeche (NK-127)."""
        zeilen = []
        for user in User.query.order_by(User.username).all():
            zeilen.append({
                'username': user.username,
                'is_active': user.is_active,
                'last_login_at': zeit.als_ortszeit(user.last_login_at)
                                 if user.last_login_at else None,
            })
        return jsonify(zeilen), 200

    @app.route('/api/konten', methods=['POST'])
    def konto_anlegen():
        """Das zweite Konto (E-1, ZIEL § 8): eins fuer Sie, eins fuer den
        Partner, keins darueber hinaus. Keine Mandanten, keine Rollen.
        """
        if db.session.query(User.id).count() >= 2:
            return jsonify(
                {'error': 'Zwei Konten reichen: eins für Sie, eins für den '
                          'Partner. Mehr braucht keine Wohnung.'}), 400
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        if not username:
            return jsonify({'error': 'Bitte einen Benutzernamen angeben.'}), 400
        if len(username) > 40:
            return jsonify(
                {'error': 'Der Benutzername darf höchstens 40 Zeichen haben.'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify(
                {'error': f"Das Konto '{username}' gibt es schon."}), 400
        if len(password) < 10:
            return jsonify(
                {'error': 'Das Passwort muss mindestens 10 Zeichen haben.'}), 400
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'username': username}), 201

    _huelle_routen(app)
    _register_cli(app)
    return app


HUELLE_PASSWORT_PAGE = _seitenkopf('Passwort zurücksetzen') + """<form method="post" class="anmelde-karte">
 <h1>Passwort zurücksetzen</h1>
 <p class="hinweis">Diese Seite gibt es nur im Programmfenster auf diesem Rechner. Wer
 hier sitzt, darf ein Passwort neu setzen.</p>
 <label for="username">Konto</label>
 <select id="username" name="username">__KONTEN__</select>
 <label for="password">Neues Passwort (mindestens 10 Zeichen)</label>
 <input id="password" name="password" type="password" minlength="10" required>
 <label for="password2">Passwort wiederholen</label>
 <input id="password2" name="password2" type="password" minlength="10" required>
 <button type="submit">Passwort speichern</button>
 __MELDUNG__
</form></body></html>"""


def _huelle_routen(app):
    """Routen der Windows-App (NK-079).

    Registriert ist die Route immer, damit Routenkarte und Inventar sie
    kennen. Ausserhalb der App (Docker) sperrt sie ``_require_login`` wie
    jede andere, und angemeldet antwortet sie 404 -- dort setzt man ein
    Passwort mit ``flask users passwd`` zurueck.
    """

    @app.route('/huelle/passwort', methods=['GET', 'POST'])
    def huelle_passwort():
        if not app.config.get('DESKTOP'):
            abort(404)
        konten = User.query.order_by(User.username).all()
        meldung = ''
        if request.method == 'POST':
            name = (request.form.get('username') or '').strip()
            neu = request.form.get('password') or ''
            user = User.query.filter_by(username=name).first()
            if user is None:
                meldung = '<p class="fehler">Dieses Konto gibt es nicht.</p>'
            elif len(neu) < 10:
                meldung = '<p class="fehler">Das Passwort muss mindestens 10 Zeichen haben.</p>'
            elif neu != (request.form.get('password2') or ''):
                meldung = '<p class="fehler">Die Passwörter stimmen nicht überein.</p>'
            else:
                user.set_password(neu)
                user.is_active = True
                db.session.commit()
                anmeldeschutz.zuruecksetzen(_anmeldeschutz_ordner())
                app.logger.info("Passwort in der App zurückgesetzt.")
                meldung = ('<p class="ok">Passwort gespeichert. '
                           '<a href="/login">Zur Anmeldung</a></p>')
        auswahl = ''.join(
            f'<option>{html.escape(k.username)}</option>' for k in konten)
        seite = HUELLE_PASSWORT_PAGE.replace('__KONTEN__', auswahl)
        return seite.replace('__MELDUNG__', meldung)


def _register_cli(app):
    """flask users add|passwd|list|disable. Konten nur ueber die Kommandozeile."""
    import click
    from flask.cli import AppGroup

    users_cli = AppGroup('users', help='Anmeldekonten verwalten (NK-019).')

    @users_cli.command('add')
    @click.argument('username')
    @click.password_option('--password', prompt='Passwort', confirmation_prompt=True)
    def add_user(username, password):
        username = username.strip()
        if User.query.filter_by(username=username).first():
            raise click.ClickException(f"Konto '{username}' gibt es schon.")
        if len(password) < 10:
            raise click.ClickException("Passwort muss mindestens 10 Zeichen haben.")
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Konto '{username}' angelegt.")

    @users_cli.command('passwd')
    @click.argument('username')
    @click.password_option('--password', prompt='Neues Passwort', confirmation_prompt=True)
    def change_password(username, password):
        user = User.query.filter_by(username=username.strip()).first()
        if user is None:
            raise click.ClickException(f"Konto '{username}' gibt es nicht.")
        if len(password) < 10:
            raise click.ClickException("Passwort muss mindestens 10 Zeichen haben.")
        user.set_password(password)
        db.session.commit()
        # Wer lokal das Passwort setzt, soll nicht an einer Sperre haengen.
        anmeldeschutz.zuruecksetzen(_anmeldeschutz_ordner())
        click.echo(f"Passwort von '{username}' geändert.")

    @users_cli.command('list')
    def list_users():
        rows = User.query.order_by(User.username).all()
        if not rows:
            click.echo("Kein Konto angelegt. Anlegen mit: flask users add <name>")
            return
        for user in rows:
            zustand = 'aktiv' if user.is_active else 'stillgelegt'
            letzte = zeit.als_ortszeit(user.last_login_at) \
                if user.last_login_at else 'nie'
            click.echo(f"{user.username}\t{zustand}\tletzte Anmeldung: {letzte}")

    @users_cli.command('disable')
    @click.argument('username')
    def disable_user(username):
        user = User.query.filter_by(username=username.strip()).first()
        if user is None:
            raise click.ClickException(f"Konto '{username}' gibt es nicht.")
        user.is_active = False
        db.session.commit()
        click.echo(f"Konto '{username}' stillgelegt. Laufende Sitzungen enden sofort.")

    app.cli.add_command(users_cli)
