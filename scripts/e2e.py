#!/usr/bin/env python3
"""Der Weg von null zur laufenden Instanz, einmal wirklich gefahren (NK-031).

Die Zusage lautet: ein Fremder hat anhand der README in unter
15 Minuten eine laufende Instanz mit Login. Dieses Skript fahert genau diesen
Weg nach -- auspacken, konfigurieren, bauen, hochfahren, anmelden, abrechnen,
herunterfahren -- und stoppt die Zeit dabei.

Warum es nicht in ``make check`` haengt: ein Bau aus dem leeren Cache dauert
Minuten. Ein Testtor, das jeder vor jedem Commit laufen laesst, darf das nicht
kosten. ``make e2e`` ist ein eigenes Ziel und laeuft, wenn jemand die Zusage
nachpruefen will.

Warum es nicht im Container laeuft: ``Makefile:11`` schiebt jedes Ziel mit
``$(COMPOSE) exec -T web`` in den schon laufenden Dev-Container. Ein Test, der
den Bau eines Abbilds misst, kann nicht in dem Abbild sitzen, das er baut.
Dieses Skript laeuft deshalb auf dem Wirt und bricht ab, wenn es sich in einem
Container wiederfindet.

Gefahren wird gegen einen **eigenen Stapel**: Projektname ``nk-e2e``, eigener
Port, eigenes Arbeitsverzeichnis unter ``/tmp``. Port 6060 (Standardinstanz)
ist fest gesperrt, nicht nur Vorgabe -- ein Zahlendreher in
``--port`` darf die Live-Instanz nicht treffen.

Der Quellbaum kommt aus ``git archive HEAD``, nicht aus dem Arbeitsverzeichnis.
Das ist genau das, was ein Fremder mit ``git clone`` bekaeme: ohne ``.git``,
ohne ``.env``, ohne ``data/``, ohne alles, was nur hier herumliegt. Ein
unsauberer Arbeitsbaum wird gemeldet, denn dann misst der Lauf etwas anderes
als das, was man gerade geschrieben hat.

    python3 scripts/e2e.py              # ganzer Lauf, frischer Bau
    python3 scripts/e2e.py --cache      # Wiederholung, Docker-Cache erlaubt
    python3 scripts/e2e.py --behalten   # Arbeitsbaum stehen lassen

Rueckgabe 0, wenn jeder Schritt sitzt **und** die Gesamtzeit unter der Marke
bleibt, sonst 1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# Zusage: "in unter 15 Minuten eine laufende Instanz mit Login".
MARKE_SEKUNDEN = 15 * 60

PROJEKTNAME = 'nk-e2e'
STANDARD_PORT = 6062

# Nicht Vorgabe, sondern Sperre. Wer hier eine Zahl aendert, faehrt einen
# Testlauf gegen eine Instanz mit echten Daten.
GESPERRTE_PORTS = {
    6060: 'die Standardinstanz (docker-compose.yml)',
}

# Praefix des Arbeitsverzeichnisses. Aufgeraeumt wird nur, was damit anfaengt.
TEMP_PRAEFIX = 'nk-e2e-'

KONTO = 'e2e-vermieter'

# Das Konto wird am Ende mit dem ganzen Stapel weggeworfen. Trotzdem nicht
# "geheim123": das Skript prueft damit auch die Mindestlaenge von zehn Zeichen.
PASSWORT = 'e2e-probelauf-2026'

# Das Abbild, das docker-compose.yml nennt; der Lauf baut es lokal unter
# einem eigenen Etikett (NK-076).
ABBILD = 'ghcr.io/nerbry72/nebenkostenfix'
ABBILD_VERSION = 'e2e'

CODE_MUSTER = re.compile(r'\b([0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4})\b')

# Ein Beleg, den die Upload-Pruefung als PDF erkennt (erste Bytes, NK-129).
PDF = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n'


class Abbruch(Exception):
    """Ein Schritt ist gescheitert. Die Meldung geht so an den Nutzer."""


class HttpFehler(Abbruch):
    """Der Server hat mit einem Fehlerstatus geantwortet. ``status`` traegt
    ihn, damit ein Schritt eine erwartete Sperre von einem Fehler trennt."""

    def __init__(self, meldung: str, status: int):
        super().__init__(meldung)
        self.status = status


# --- Teile, die sich ohne Docker pruefen lassen ------------------------------

def port_pruefen(port: int) -> None:
    """Sperrt die zwei Ports, hinter denen echte Daten liegen."""
    if port in GESPERRTE_PORTS:
        raise Abbruch(
            f'Port {port} ist gesperrt: dort laeuft {GESPERRTE_PORTS[port]}.\n'
            f'Der e2e-Lauf braucht einen eigenen Port, Vorgabe {STANDARD_PORT}.')
    if not 1024 <= port <= 65535:
        raise Abbruch(f'Port {port} liegt ausserhalb von 1024-65535.')


def port_frei(port: int) -> bool:
    """True, wenn auf dem Wirt gerade niemand auf diesem Port horcht."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) != 0


def marke_gehalten(dauer: float, marke: float = MARKE_SEKUNDEN) -> bool:
    """Die eine Frage der Zusage. Gerundet wird nicht."""
    return dauer <= marke


def zeit(sekunden: float) -> str:
    """'7 min 03 s' -- Minuten, weil die Marke in Minuten steht."""
    minuten, rest = divmod(int(round(sekunden)), 60)
    if minuten:
        return f'{minuten} min {rest:02d} s'
    return f'{rest} s'


def umgebung_bauen(port: int, puid: int, pgid: int, version: str) -> str:
    """Die optionale .env, die ein Fremder nur braucht, wenn er etwas aendert.

    Seit NK-076 ist keine .env noetig: der Sitzungsschluessel entsteht im
    Datenordner, das Konto in der Einrichtung. Der Lauf setzt nur, was sich
    von der Vorgabe unterscheidet -- einen freien Port, den Nutzer des Wirts
    (damit er seinen Arbeitsbaum hinterher loeschen darf) und das eben
    gebaute Abbild.
    """
    return (f'APP_PORT={port}\nPUID={puid}\nPGID={pgid}\n'
            f'NK_VERSION={version}\n')


def formular(felder: dict, dateiname: str, inhalt: bytes) -> tuple[bytes, str]:
    """multipart/form-data mit einer Datei im Feld ``file``, wie es die
    Oberflaeche beim Beleg schickt. urllib baut das nicht selbst."""
    grenze = f'nk-e2e-{secrets.token_hex(8)}'
    teile = [f'--{grenze}\r\nContent-Disposition: form-data; name="{name}"'
             f'\r\n\r\n{wert}\r\n'.encode() for name, wert in felder.items()]
    teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="file"; '
                 f'filename="{dateiname}"\r\nContent-Type: application/pdf'
                 f'\r\n\r\n'.encode() + inhalt + b'\r\n')
    teile.append(f'--{grenze}--\r\n'.encode())
    return b''.join(teile), f'multipart/form-data; boundary={grenze}'


def tabelle(schritte: list[tuple[str, float]], gesamt: float,
            marke: float = MARKE_SEKUNDEN) -> str:
    """Die Schlussabrechnung: was wie lange gedauert hat, und ob es reicht."""
    breite = max((len(name) for name, _ in schritte), default=10)
    zeilen = ['', 'Zeit von null zur laufenden Instanz', '']
    for name, dauer in schritte:
        zeilen.append(f'  {name:<{breite}}  {zeit(dauer):>12}')
    zeilen.append('  ' + '-' * (breite + 14))
    zeilen.append(f'  {"gesamt":<{breite}}  {zeit(gesamt):>12}')
    zeilen.append('')
    if marke_gehalten(gesamt, marke):
        uebrig = marke - gesamt
        zeilen.append(f'  Marke {zeit(marke)} gehalten, {zeit(uebrig)} uebrig.')
    else:
        zeilen.append(f'  Marke {zeit(marke)} GERISSEN um {zeit(gesamt - marke)}.')
    return '\n'.join(zeilen)


# --- Der Lauf selbst ---------------------------------------------------------

class Lauf:
    """Ein e2e-Durchgang. Haelt Arbeitsverzeichnis, Port und Zeitnahme."""

    def __init__(self, port: int, cache: bool, behalten: bool):
        self.port = port
        self.cache = cache
        self.behalten = behalten
        self.arbeit: Path | None = None
        self.schritte: list[tuple[str, float]] = []
        self.oeffner = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()))
        # Fuer Aufrufe mit Zugriffsschluessel: kein Keksglas, damit keine
        # Sitzung aus dem Login mitreist.
        self.ohne_sitzung = urllib.request.build_opener()

    # -- Werkzeug --

    def _docker(self, *args: str, eingabe: str | None = None,
                pruefen: bool = True) -> subprocess.CompletedProcess:
        befehl = ['docker', 'compose', '-p', PROJEKTNAME, *args]
        return subprocess.run(
            befehl, cwd=self.arbeit, input=eingabe, text=True,
            capture_output=True, check=pruefen)

    def _url(self, pfad: str) -> str:
        return f'http://127.0.0.1:{self.port}{pfad}'

    def _ruf(self, methode: str, pfad: str, nutzlast=None, roh: bool = False,
             schluessel: str | None = None, datei: tuple[bytes, str] | None = None):
        """Ein API-Aufruf mit der Sitzung aus dem Login -- oder, mit
        ``schluessel``, ohne Cookie nur mit dem Zugriffsschluessel. ``datei``
        ist ein fertiges Formular aus ``formular()``."""
        daten = None
        kopf = {}
        if nutzlast is not None:
            daten = json.dumps(nutzlast).encode()
            kopf['Content-Type'] = 'application/json'
        if datei is not None:
            daten, kopf['Content-Type'] = datei
        oeffner = self.oeffner
        if schluessel is not None:
            kopf['Authorization'] = f'Bearer {schluessel}'
            oeffner = self.ohne_sitzung
        anfrage = urllib.request.Request(
            self._url(pfad), data=daten, headers=kopf, method=methode)
        try:
            with oeffner.open(anfrage, timeout=120) as antwort:
                inhalt = antwort.read()
                if roh:
                    return inhalt
                # /login antwortet auf JSON mit JSON, auf ein Formular mit
                # einer Weiterleitung auf HTML. Nur das erste wird gelesen.
                if 'json' not in antwort.headers.get('Content-Type', ''):
                    return {}
                return json.loads(inhalt) if inhalt else {}
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode('utf-8', 'replace')[:500]
            raise HttpFehler(
                f'{methode} {pfad} antwortet {fehler.code}: {text}',
                fehler.code) from fehler

    def _erwarte(self, status: int, methode: str, pfad: str, schluessel: str,
                 nutzlast=None) -> None:
        """Der Aufruf muss mit genau diesem Status scheitern."""
        try:
            self._ruf(methode, pfad, nutzlast, schluessel=schluessel)
        except HttpFehler as fehler:
            if fehler.status == status:
                return
            raise
        raise Abbruch(f'{methode} {pfad} mit Zugriffsschluessel ging durch, '
                      f'erwartet war {status}.')

    def _schritt(self, name: str, arbeit) -> None:
        start = time.monotonic()
        print(f'  ... {name}', flush=True)
        ergebnis = arbeit()
        dauer = time.monotonic() - start
        self.schritte.append((name, dauer))
        if ergebnis:
            print(f'      {ergebnis}', flush=True)

    # -- Die Schritte, in der Reihenfolge der README --

    def baum_auspacken(self) -> str:
        """README Schritt 1: das Verzeichnis holen."""
        self.arbeit = Path(tempfile.mkdtemp(prefix=TEMP_PRAEFIX))
        archiv = subprocess.run(
            ['git', 'archive', '--format=tar', 'HEAD'],
            cwd=WURZEL, capture_output=True, check=True)
        subprocess.run(['tar', '-x', '-C', str(self.arbeit)],
                       input=archiv.stdout, check=True)
        anzahl = sum(1 for _ in self.arbeit.rglob('*'))
        return f'{anzahl} Eintraege nach {self.arbeit}'

    def umgebung_anlegen(self) -> str:
        """Optionale .env: Port, Nutzer, Abbild (kein Schluessel, NK-076)."""
        inhalt = umgebung_bauen(self.port, os.getuid(), os.getgid(), ABBILD_VERSION)
        ziel = self.arbeit / '.env'
        ziel.write_text(inhalt, encoding='utf-8')
        ziel.chmod(0o600)
        return f'.env geschrieben, APP_PORT={self.port}, ohne SECRET_KEY'

    def stapel_hoch(self) -> str:
        """Abbild bauen (so wie es die Registry liefert) und hochfahren.

        Gebaut wird mit ``docker build`` statt ``compose build``, damit ein
        TLS-pruefender Proxy (Firma, CI) sein Zertifikat als Build-Secret
        bekommen kann: NK_BUILD_CA=<pfad> (siehe Dockerfile).
        """
        befehl = ['docker', 'build', '-t', f'{ABBILD}:{ABBILD_VERSION}']
        if not self.cache:
            # Ein Fremder auf einer frischen Maschine hat keinen Cache, und
            # genau dessen Zeit misst die Marke.
            befehl.append('--no-cache')
        ca = os.environ.get('NK_BUILD_CA')
        if ca:
            befehl += ['--secret', f'id=ca,src={ca}', '--network=host']
            for name in ('HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'):
                if os.environ.get(name):
                    befehl += ['--build-arg', f'{name}={os.environ[name]}']
        subprocess.run([*befehl, '.'], cwd=self.arbeit, check=True,
                       capture_output=True, text=True)
        self._docker('up', '-d', '--no-build')
        return 'Stapel laeuft'

    def gesundheit_abwarten(self) -> str:
        """README Schritt 5: nachsehen, ob es laeuft."""
        frist = time.monotonic() + 300
        letzter = 'keine Antwort'
        while time.monotonic() < frist:
            try:
                with urllib.request.urlopen(
                        self._url('/api/health'), timeout=5) as antwort:
                    if antwort.status == 200:
                        daten = json.loads(antwort.read())
                        if daten.get('status') == 'ok':
                            return f'/api/health: {daten.get("message", "")}'
                        letzter = f'status={daten.get("status")!r}'
            except (urllib.error.URLError, OSError, ValueError) as fehler:
                letzter = str(fehler)
            time.sleep(2)
        protokoll = self._docker('logs', '--tail', '30', 'web', pruefen=False)
        raise Abbruch(
            f'/api/health antwortet nach 5 Minuten nicht ({letzter}).\n'
            f'Letzte Protokollzeilen:\n{protokoll.stdout}{protokoll.stderr}')

    def konto_anlegen(self) -> str:
        """README: Einrichtung im Browser mit dem Code aus dem Protokoll.

        Kein Terminal im Container, kein ``flask users add`` (E-1, NK-127):
        /einrichtung aufrufen, den Einmal-Code aus ``docker compose logs``
        lesen, das Formular abschicken.
        """
        self._ruf('GET', '/einrichtung')
        protokoll = self._docker('logs', 'web', pruefen=False)
        codes = sorted(set(CODE_MUSTER.findall(protokoll.stdout + protokoll.stderr)))
        if len(codes) != 1:
            raise Abbruch(f'Das Protokoll nennt {len(codes)} Einmal-Codes statt einem.')
        self._ruf('POST', '/einrichtung', {
            'username': KONTO, 'password': PASSWORT, 'password2': PASSWORT,
            'code': codes[0]})
        self._ruf('POST', '/logout')
        return f'Konto {KONTO} ueber die Einrichtung angelegt (Code aus dem Protokoll)'

    def anmelden(self) -> str:
        """README Schritt 7: anmelden. Danach traegt der Oeffner die Sitzung."""
        gesperrt = False
        try:
            self._ruf('GET', '/api/properties')
        except Abbruch:
            gesperrt = True
        if not gesperrt:
            raise Abbruch(
                '/api/properties antwortet ohne Anmeldung. Die Zugangssperre '
                'aus NK-019 greift nicht -- das ist ein Leck, kein Testfehler.')

        self._ruf('POST', '/login', {'username': KONTO, 'password': PASSWORT})
        wer = self._ruf('GET', '/api/auth/me')
        if wer.get('username') != KONTO:
            raise Abbruch(f'/api/auth/me meldet {wer!r} statt {KONTO}.')
        return f'angemeldet als {KONTO}, vorher war /api/properties gesperrt'

    def abrechnung_erzeugen(self) -> str:
        """Das, wofuer die Instanz da ist: Stammdaten, Rechnung, PDF."""
        haus = self._ruf('POST', '/api/properties',
                         {'name': 'E2E-Haus', 'is_standalone': False})['id']
        oben = self._ruf('POST', '/api/apartments',
                         {'property_id': haus, 'name': 'Oben', 'sqm': 50})['id']
        self._ruf('POST', '/api/apartments',
                  {'property_id': haus, 'name': 'Unten', 'sqm': 50})
        mieter = self._ruf('POST', '/api/tenants', {
            'apartment_id': oben,
            'name': 'Erika Mustermann',
            'move_in_date': '2024-06-01',
        })['id']

        kategorien = self._ruf('GET', '/api/categories')
        grundsteuer = next(
            (k['id'] for k in kategorien if k['name'] == 'Grundsteuer'), None)
        if grundsteuer is None:
            raise Abbruch(
                'Die Startbestueckung hat keine Kostenart "Grundsteuer". '
                f'Vorhanden: {[k["name"] for k in kategorien]}')

        # Umlage nach Quadratmetern: 50 von 100 qm, also die Haelfte.
        self._ruf('POST', f'/api/tenants/{mieter}/profiles',
                  {str(grundsteuer): 'qm'})
        self._ruf('POST', '/api/invoices', {
            'category_id': grundsteuer,
            'property_id': haus,
            'amount': 1200.0,
            'start_date': '2025-01-01',
            'end_date': '2025-12-31',
            'invoice_number': 'E2E-1',
        })

        auftrag = {
            'tenant_id': mieter,
            'start_date': '2025-01-01',
            'end_date': '2025-12-31',
            'category_ids': [grundsteuer],
        }
        rechnung = self._ruf('POST', '/api/billing/generate', auftrag)
        summe = rechnung.get('total_amount')
        if not summe:
            raise Abbruch(f'/api/billing/generate liefert keine Summe: {rechnung!r}')
        # 1200 Euro auf 100 qm, davon 50 qm ein volles Jahr = 600 Euro.
        if abs(summe - 600.0) > 1.0:
            raise Abbruch(
                f'Die Abrechnung sagt {summe} Euro, erwartet waren 600 '
                '(1200 Euro Grundsteuer, halbe Flaeche, volles Jahr).')

        self._ruf('POST', '/api/billing/finalize', auftrag)
        berichte = self._ruf('GET', '/api/billing/reports')
        if not berichte:
            raise Abbruch('Nach finalize steht kein Bericht in /api/billing/reports.')
        pdf = self._ruf('GET', f'/api/billing/reports/{berichte[0]["id"]}/download',
                        roh=True)
        if not pdf.startswith(b'%PDF'):
            raise Abbruch(f'Der Download ist kein PDF: {pdf[:40]!r}')
        return f'{summe:.2f} Euro, PDF mit {len(pdf)} Bytes heruntergeladen'

    def zugriffsschluessel(self) -> str:
        """Der Weg eines MCP-Servers (#47): ohne Browser und ohne Cookie, nur
        mit Zugriffsschluessel. Gegen waitress im gebauten Abbild, nicht
        gegen den Testclient -- hier zeigt sich, ob Header und Upload
        wirklich durchkommen."""
        def anlegen(name, umfang):
            return self._ruf('POST', '/api/zugriffsschluessel',
                             {'name': name, 'umfang': umfang})['schluessel']
        lesen = anlegen('E2E lesen', 'lesen')
        erfassen = anlegen('E2E erfassen', 'erfassen')

        # Lesen und pruefen
        wer = self._ruf('GET', '/api/auth/me', schluessel=lesen)
        if wer.get('username') != KONTO or (wer.get('schluessel') or {}).get('umfang') != 'lesen':
            raise Abbruch(f'/api/auth/me mit Schluessel meldet {wer!r}.')
        haus = next(h['id'] for h in self._ruf('GET', '/api/properties', schluessel=lesen)
                    if h['name'] == 'E2E-Haus')
        mieter = next(m['id'] for m in self._ruf('GET', '/api/tenants', schluessel=lesen)
                      if m['name'] == 'Erika Mustermann')
        kategorien = {k['name']: k['id']
                      for k in self._ruf('GET', '/api/categories', schluessel=lesen)}
        vorpruefung = self._ruf('POST', '/api/billing/preflight', {
            'tenant_id': mieter, 'start_date': '2025-01-01', 'end_date': '2025-12-31',
            'category_ids': [kategorien['Grundsteuer']]}, schluessel=lesen)
        if 'overall' not in vorpruefung:
            raise Abbruch(f'Die Vorpruefung liefert kein Ergebnis: {vorpruefung!r}')

        # Erfassen: eine Rechnung mit Beleg, ein Sammelbeleg mit Rechnung
        rechnung = {'category_id': kategorien['Wasserversorgung'], 'property_id': haus,
                    'amount': '310.00', 'start_date': '2026-01-01', 'end_date': '2026-03-31'}
        self._erwarte(403, 'POST', '/api/invoices', lesen, rechnung)
        mit_beleg = self._ruf('POST', '/api/invoices', schluessel=erfassen,
                              datei=formular(rechnung, 'e2e-stadtwerke.pdf', PDF))['id']
        sammel = self._ruf('POST', '/api/invoice_documents', schluessel=erfassen,
                           datei=formular({'property_id': haus}, 'e2e-sammel.pdf', PDF))['id']
        self._ruf('POST', '/api/invoices', {**rechnung, 'invoice_document_id': sammel},
                  schluessel=erfassen)
        belege = self._ruf('GET', '/api/invoice_documents', schluessel=lesen)
        if sammel not in [b['id'] for b in belege]:
            raise Abbruch(f'Der Sammelbeleg {sammel} fehlt in /api/invoice_documents.')

        # Zaehlerstand und Zahlung. Den Zaehler legt der Mensch an.
        zaehler = self._ruf('POST', '/api/meters', {
            'category_id': kategorien['Wasserversorgung'], 'property_id': haus,
            'is_main_meter': True, 'meter_number': 'E2E-W1'})['id']
        self._ruf('POST', '/api/readings', {'meter_id': zaehler,
                  'reading_date': '2026-01-01', 'value': '100'}, schluessel=erfassen)
        self._ruf('POST', '/api/payments', {
            'tenant_id': mieter, 'amount': '80.00', 'type': 'Nebenkostenvorauszahlung',
            'payment_date': '2026-01-03'}, schluessel=erfassen)

        # Eine Serie einen Tag nach dem Stichtag laesst das Soll stehen: die
        # Vereinbarung aendert nur der Mensch (Review zu #48).
        self._ruf('POST', f'/api/tenants/{mieter}/vorauszahlung_soll',
                  {'gueltig_ab': '2026-01-01', 'betrag': '80.00'})
        serie = self._ruf('POST', '/api/payments', {
            'tenant_id': mieter, 'amount': '1.00', 'type': 'Nebenkostenvorauszahlung',
            'payment_date': '2026-01-02', 'end_date': '2026-02-28', 'is_recurring': True},
            schluessel=erfassen)
        soll = self._ruf('GET', f'/api/tenants/{mieter}/vorauszahlungen',
                         schluessel=lesen)['soll']
        if not serie.get('soll_unveraendert') or \
                [(s['gueltig_ab'], s['betrag']) for s in soll] != [('2026-01-01', '80.00')]:
            raise Abbruch(f'Die Serie mit Schluessel hat das Soll veraendert: {soll!r}')

        # Was nur die Oberflaeche darf
        self._erwarte(403, 'DELETE', f'/api/invoices/{mit_beleg}', erfassen)
        self._erwarte(403, 'GET', '/api/export', erfassen)
        self._erwarte(403, 'POST', '/api/billing/finalize', erfassen, {
            'tenant_id': mieter, 'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self._erwarte(403, 'GET', '/api/zugriffsschluessel', erfassen)

        # Widerrufen
        for eintrag in self._ruf('GET', '/api/zugriffsschluessel'):
            self._ruf('DELETE', f'/api/zugriffsschluessel/{eintrag["id"]}')
        self._erwarte(401, 'GET', '/api/properties', erfassen)
        return ('lesen, pruefen, Rechnung mit Beleg, Sammelbeleg, Zaehlerstand, '
                'Zahlung, Soll bleibt; Sperren 403, nach dem Widerruf 401')

    def _bindziele(self) -> list[str]:
        """Wohin docker-compose.yml die Bind-Mounts im Container legt.

        Nicht geraten, sondern nachgeschlagen: ``./belege`` haengt unter
        ``/mnt/belege``, nicht unter ``/app/belege``. Ein geratener Pfad
        laesst das chown still danebengreifen, und der Baum bleibt liegen.
        Wer die Mounts in der Compose-Datei umbaut, soll das hier nicht
        nachziehen muessen.
        """
        try:
            roh = self._docker('config', '--format', 'json').stdout
            dienste = json.loads(roh)['services']
        except (subprocess.CalledProcessError, ValueError, KeyError) as fehler:
            print(f'      Bind-Ziele nicht lesbar: {fehler}')
            return []
        ziele = []
        for dienst in dienste.values():
            for mount in dienst.get('volumes', []):
                if mount.get('type') == 'bind' and mount.get('target'):
                    ziele.append(mount['target'])
        return ziele

    def stapel_runter(self) -> str:
        """Was hochgefahren wurde, faehrt auch wieder herunter.

        Vorher die Besitzrechte zurueckgeben: der Datenordner gehoert dem
        Nutzer im Container (PUID), der Lauf setzt ihn auf den Wirtsnutzer --
        bei root als Wirt bleibt es root. Ohne diesen Schritt kann der Lauf sein eigenes
        Arbeitsverzeichnis hinterher nicht mehr loeschen (F-17). Das chown
        laeuft im Container, wo root zu sein nichts kostet -- auf dem Wirt
        braeuchte es sudo, und danach fragt ein Testskript nicht.
        """
        wer = f'{os.getuid()}:{os.getgid()}'
        ziele = self._bindziele()
        if ziele:
            # Die Anwendung laeuft seit NK-076 nicht mehr als root; das chown
            # braucht ihn aber, also ausdruecklich -u 0.
            chown = self._docker('exec', '-T', '-u', '0', 'web', 'chown', '-R', wer,
                                 *ziele, pruefen=False)
            if chown.returncode != 0:
                print(f'      chown misslungen: {chown.stderr.strip()}')
        # Ohne -v: der Stapel hat keine benannten Volumes, die Daten liegen im
        # Arbeitsverzeichnis und gehen mit ihm.
        self._docker('down', '--remove-orphans', pruefen=False)
        return 'Stapel gestoppt'

    # -- Rahmen --

    def aufraeumen(self) -> None:
        if self.arbeit is None:
            return
        if self.behalten:
            print(f'\nArbeitsbaum bleibt stehen: {self.arbeit}')
            return
        # Nur wegwerfen, was dieser Lauf selbst angelegt hat.
        if not (self.arbeit.name.startswith(TEMP_PRAEFIX)
                and self.arbeit.parent == Path(tempfile.gettempdir())):
            return
        # Kein ignore_errors: genau das hat F-17 verdeckt -- der Baum blieb
        # liegen, der Lauf meldete Erfolg. Ein Rest ist eine Meldung wert.
        try:
            shutil.rmtree(self.arbeit)
        except OSError as fehler:
            print(f'\nArbeitsbaum liess sich nicht entfernen: {fehler}\n'
                  f'Rest: {self.arbeit}', file=sys.stderr)

    def fahren(self) -> int:
        beginn = time.monotonic()
        try:
            self._schritt('1 Baum auspacken', self.baum_auspacken)
            self._schritt('2 .env (optional) anlegen', self.umgebung_anlegen)
            self._schritt('3 bauen und starten', self.stapel_hoch)
            self._schritt('4 auf /api/health warten', self.gesundheit_abwarten)
            self._schritt('5 Einrichtung im Browser', self.konto_anlegen)
            self._schritt('6 anmelden', self.anmelden)
            self._schritt('7 Abrechnung erzeugen', self.abrechnung_erzeugen)
            self._schritt('8 Zugriffsschluessel', self.zugriffsschluessel)
        finally:
            gesamt = time.monotonic() - beginn
            if self.arbeit is not None:
                self._schritt('9 herunterfahren', self.stapel_runter)

        print(tabelle(self.schritte, gesamt))
        return 0 if marke_gehalten(gesamt) else 1


def vorbedingungen(port: int) -> None:
    """Was stimmen muss, bevor irgendetwas gebaut wird."""
    if Path('/.dockerenv').exists():
        raise Abbruch(
            'Dieses Skript laeuft auf dem Wirt, nicht im Container: es baut '
            'das Abbild, in dem es sonst selbst saesse. Aufruf: make e2e')

    port_pruefen(port)
    if not port_frei(port):
        raise Abbruch(
            f'Auf Port {port} horcht schon jemand. Anderen Port waehlen: '
            f'python3 scripts/e2e.py --port {port + 1}')

    for werkzeug in ('docker', 'git', 'tar'):
        if shutil.which(werkzeug) is None:
            raise Abbruch(f'{werkzeug} ist nicht installiert.')

    laeuft = subprocess.run(
        ['docker', 'compose', '-p', PROJEKTNAME, 'ps', '-q'],
        capture_output=True, text=True, check=False)
    if laeuft.stdout.strip():
        raise Abbruch(
            f'Es laeuft schon ein Stapel "{PROJEKTNAME}". Erst herunterfahren:\n'
            f'  docker compose -p {PROJEKTNAME} down')

    dreckig = subprocess.run(
        ['git', 'status', '--porcelain'],
        cwd=WURZEL, capture_output=True, text=True, check=True)
    if dreckig.stdout.strip():
        print('Hinweis: der Arbeitsbaum hat Aenderungen, die nicht committet '
              'sind. Gefahren wird HEAD, also ohne sie.\n')


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(
        description='Von null zur laufenden Instanz, mit Stoppuhr (NK-031).')
    zerleger.add_argument('--port', type=int, default=STANDARD_PORT,
                          help=f'Port des Testlaufs (Vorgabe {STANDARD_PORT}). '
                               '6060 ist gesperrt.')
    zerleger.add_argument('--cache', action='store_true',
                          help='Docker-Cache benutzen. Schneller, misst aber '
                               'nicht mehr den Weg eines Fremden.')
    zerleger.add_argument('--behalten', action='store_true',
                          help='Arbeitsbaum nach dem Lauf stehen lassen.')
    argumente = zerleger.parse_args(argv)

    lauf = None
    try:
        vorbedingungen(argumente.port)
        print(f'e2e-Lauf, Projekt {PROJEKTNAME}, Port {argumente.port}, '
              f'Bau {"mit" if argumente.cache else "ohne"} Cache\n')
        lauf = Lauf(argumente.port, argumente.cache, argumente.behalten)
        return lauf.fahren()
    except Abbruch as fehler:
        print(f'\ne2e abgebrochen: {fehler}', file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as fehler:
        print(f'\ne2e abgebrochen: {" ".join(fehler.cmd)} endete mit '
              f'{fehler.returncode}\n{fehler.stdout}{fehler.stderr}',
              file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nAbgebrochen.', file=sys.stderr)
        return 130
    finally:
        if lauf is not None:
            lauf.aufraeumen()


if __name__ == '__main__':
    sys.exit(main())
