"""Updates über GitHub Releases (NK-081, NK-175, D-101).

Jedes Release hängt ein signiertes ``update.json`` an (``release.yml``). Die
App lädt es von ``UPDATE_QUELLE`` -- beim Start im Hintergrund, höchstens
einmal in 24 Stunden (``automatisch``), oder auf Knopfdruck (``suchen``).
Ein verändertes oder fremdes Manifest wird verworfen, bevor irgendetwas
geladen wird: die Signatur (Ed25519 über die kanonische Form von ``daten``)
prüft der öffentliche Herausgeberschlüssel unten. Seit NK-176 gibt es keine
Lizenz mehr; jedes Update ist für alle da.

Manifest (JSON)::

    {"format": "nk-update-1",
     "daten": {"version": "0.10.0", "veroeffentlicht": "2026-10-15",
               "hinweise": "Kurz, was neu ist.",
               "notizen": "https://github.com/…/releases/tag/v0.10.0",
               "windows": {"url": "https://…/NebenkostenFix-0.10.0-Setup.exe",
                           "sha256": "…"},
               "docker": "ghcr.io/nerbry72/nebenkostenfix:0.10.0"},
     "signatur": "…"}

Drei Wege:

- **Docker:** nur der Hinweis auf das neue Abbild; aktualisiert wird per Tag
  (``docker compose pull`` und ``up -d``). Vor jeder Wanderung sichert die
  Anwendung automatisch (``app.vor_der_wanderung_sichern``).
- **Windows-App (EXE):** lädt den Installer über https, prüft die Prüfsumme
  aus dem signierten Manifest, sichert die Daten und startet ihn still. Er
  installiert über die bestehende Installation (gleiche AppId) und schließt
  die App dabei sauber (Restart Manager).
- **Microsoft Store (MSIX, NK-173):** der Store aktualisiert; hier ist alles
  aus (``paketmodus``).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
# Bandit-Ausnahme (B404): nur installer_starten, feste Argumente
import subprocess  # nosec B404
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

import marke

FORMAT = 'nk-update-1'
# ``NK_UPDATE_QUELLE`` überschreibt sie (Probe im Windows-Job mit lokalem
# Manifest, NK-175).
UPDATE_QUELLE = f'{marke.REPO_URL}/releases/latest/download/update.json'
MAX_MANIFEST = 64 * 1024
MAX_INSTALLER = 500 * 1024 * 1024
# Beim Start: kurz fragen und still bleiben, wenn niemand antwortet.
AUTOMATISCH_ZEIT_S = 5
AUTOMATISCH_ABSTAND = timedelta(hours=24)

# Öffentlicher Ed25519-Schlüssel des Herausgebers (32 Byte, base64). Fabi
# erzeugt das Paar einmal offline (``scripts/update_signieren.py schluessel``),
# der private Teil liegt nur als Actions-Secret ``UPDATE_SCHLUESSEL`` bei
# GitHub. Solange das hier leer ist, nimmt die App kein Manifest an.
HERAUSGEBER_SCHLUESSEL = 'D2DuitCVsfZ2Cr+Vk8mRI4NhS8mvgRMXlQMLia7H7XY='


class AktualisierungsFehler(Exception):
    """Suche oder Download gescheitert; die installierte Version bleibt."""


def kanonisch(daten: dict) -> bytes:
    """JSON mit sortierten Schlüsseln, ohne Leerraum, UTF-8 -- so prüft dieselbe
    Signatur, egal wie die Datei eingerückt ist."""
    return json.dumps(daten, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def schluessel_laden(oeffentlich: str | None = None) -> Ed25519PublicKey:
    roh = HERAUSGEBER_SCHLUESSEL if oeffentlich is None else oeffentlich
    if not roh:
        raise AktualisierungsFehler(
            'Diese Fassung enthält noch keinen Herausgeberschlüssel und kann '
            'Updates nicht prüfen. Neue Versionen finden Sie auf der Projektseite.')
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(roh, validate=True))
    except (ValueError, binascii.Error) as fehler:
        raise AktualisierungsFehler('Der eingebaute Herausgeberschlüssel ist beschädigt.') \
            from fehler


def signieren(daten: dict, privat: Ed25519PrivateKey, art: str = FORMAT) -> dict:
    """Für ``scripts/update_signieren.py`` und für Tests."""
    return {'format': art, 'daten': daten,
            'signatur': base64.b64encode(privat.sign(kanonisch(daten))).decode('ascii')}


def signatur_pruefen(umschlag: dict, art: str = FORMAT,
                     oeffentlich: str | None = None) -> dict:
    """Prüft Format und Signatur eines Umschlags; liefert ``daten``."""
    if not isinstance(umschlag, dict) or umschlag.get('format') != art:
        raise AktualisierungsFehler('Das Manifest hat nicht das erwartete Format.')
    daten = umschlag.get('daten')
    if not isinstance(daten, dict):
        raise AktualisierungsFehler('Das Manifest enthält keine Daten.')
    try:
        signatur = base64.b64decode(umschlag.get('signatur') or '', validate=True)
    except (ValueError, binascii.Error) as fehler:
        raise AktualisierungsFehler('Die Signatur ist unlesbar.') from fehler
    try:
        schluessel_laden(oeffentlich).verify(signatur, kanonisch(daten))
    except InvalidSignature as fehler:
        raise AktualisierungsFehler(
            'Die Signatur passt nicht. Das Manifest ist verändert oder stammt '
            'nicht vom Herausgeber.') from fehler
    return daten


def paketmodus() -> bool:
    """Läuft die App als MSIX-Paket (Microsoft Store, NK-173)? Dann
    aktualisiert der Store, der eigene Updater ist aus."""
    if sys.platform != 'win32':
        return False
    try:  # pragma: no cover - Windows
        import ctypes
        laenge = ctypes.c_uint32(0)
        # APPMODEL_ERROR_NO_PACKAGE (15700): kein Paket; ERROR_INSUFFICIENT_BUFFER
        # (122): es gibt einen Paketnamen.
        return ctypes.windll.kernel32.GetCurrentPackageFullName(
            ctypes.byref(laenge), None) != 15700
    except (AttributeError, OSError):  # pragma: no cover - Windows vor 8
        return False


def quelle() -> str:
    return (os.environ.get('NK_UPDATE_QUELLE') or UPDATE_QUELLE).strip()


def version_als_tupel(version: str) -> tuple[int, ...]:
    teile = re.findall(r'\d+', str(version).split('-', 1)[0])
    if not teile:
        raise AktualisierungsFehler(f'„{version}“ ist keine Versionsnummer.')
    return tuple(int(t) for t in teile)


def _https(adresse: str) -> str:
    if not adresse.lower().startswith('https://'):
        raise AktualisierungsFehler('Updates werden nur über https geladen.')
    return adresse


def _laden(adresse: str, grenze: int, zeit: int = 20) -> bytes:
    # Bandit-Ausnahme (B310): nur https, siehe _https(); kein file:// o. ae.
    with urllib.request.urlopen(_https(adresse), timeout=zeit) as antwort:  # nosec B310
        inhalt = antwort.read(grenze + 1)
    if len(inhalt) > grenze:
        raise AktualisierungsFehler('Die Antwort der Update-Quelle ist zu groß.')
    return inhalt


def manifest_pruefen(roh: bytes, oeffentlich: str | None = None) -> dict:
    try:
        umschlag = json.loads(roh.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as fehler:
        raise AktualisierungsFehler('Die Update-Quelle lieferte kein Manifest.') from fehler
    try:
        daten = signatur_pruefen(umschlag, FORMAT, oeffentlich)
    except AktualisierungsFehler as fehler:
        raise AktualisierungsFehler(f'Das Update-Manifest ist nicht vertrauenswürdig: {fehler}') \
            from fehler
    for feld in ('version', 'veroeffentlicht'):
        if not daten.get(feld):
            raise AktualisierungsFehler(f'Im Manifest fehlt „{feld}“.')
    version_als_tupel(daten['version'])
    try:
        date.fromisoformat(daten['veroeffentlicht'])
    except ValueError as fehler:
        raise AktualisierungsFehler('Das Veröffentlichungsdatum ist unlesbar.') from fehler
    return daten


def suchen(aktuelle_version: str, desktop: bool, oeffentlich: str | None = None,
           laden=None, zeit: int = 20) -> dict:
    """Ergebnis für die Oberfläche. Wirft ``AktualisierungsFehler`` oder ``OSError``."""
    laden = laden or _laden
    adresse = quelle()
    if not adresse:
        raise AktualisierungsFehler(
            'Dieser Build kennt keine Update-Quelle. Neue Versionen finden Sie '
            'auf der Projektseite.')
    schluessel_laden(oeffentlich)  # ohne Herausgeberschlüssel gar nicht erst ins Netz
    daten = manifest_pruefen(laden(adresse, MAX_MANIFEST, zeit), oeffentlich)
    neu = version_als_tupel(daten['version']) > version_als_tupel(aktuelle_version)
    windows = daten.get('windows') or {}
    paket = paketmodus()
    ergebnis = {
        'aktuell': aktuelle_version,
        'version': daten['version'],
        'veroeffentlicht': daten['veroeffentlicht'],
        'hinweise': str(daten.get('hinweise') or ''),
        'notizen': notizen_url(daten),
        'neu': neu,
        'docker': daten.get('docker'),
        'installierbar': bool(neu and desktop and not paket and windows.get('url')
                              and windows.get('sha256')),
    }
    if not neu:
        ergebnis['text'] = f'Sie haben die neueste Version ({aktuelle_version}).'
    elif paket:
        ergebnis['text'] = (f'Version {daten["version"]} ist erschienen. Der Microsoft '
                            'Store installiert sie automatisch.')
    elif desktop:
        ergebnis['text'] = f'Version {daten["version"]} ist verfügbar.'
    else:
        ergebnis['text'] = (
            f'Version {daten["version"]} ist verfügbar. Aktualisieren Sie das '
            f'Abbild ({daten.get("docker") or "neuer Tag"}) mit „docker compose '
            'pull“ und „docker compose up -d“; vor der Umstellung der Datenbank '
            'sichert die Anwendung automatisch.')
    return ergebnis


def notizen_url(daten: dict) -> str:
    """Die Release-Notes; nur Adressen auf der Projektseite, sonst die Liste."""
    notizen = str(daten.get('notizen') or '')
    if notizen.startswith(marke.REPO_URL + '/'):
        return notizen
    return f'{marke.REPO_URL}/releases'


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def automatisch(aktuelle_version: str, desktop: bool, ordner=None,
                oeffentlich: str | None = None, laden=None,
                jetzt: datetime | None = None) -> dict | None:
    """Die Suche beim Start (NK-175). ``None`` heißt: nichts zeigen.

    Still bei jedem Fehler -- offline, Quelle weg, Manifest kaputt --, denn
    niemand hat gefragt. Gesucht wird höchstens alle 24 Stunden; der
    Zeitpunkt zählt auch, wenn die Suche scheitert, sonst fragte eine App
    ohne Netz bei jedem Start. Ein gefundenes Update meldet jeder Start
    wieder („Später erinnern“, Glossar), aus dem gemerkten Ergebnis.
    """
    import einstellungen

    if paketmodus():
        return None
    stand = einstellungen.lesen(ordner)
    if not stand['updates_automatisch']:
        return None
    jetzt = jetzt or _jetzt()
    try:
        zuletzt = datetime.fromisoformat(stand['update_geprueft'])
    except (TypeError, ValueError):
        zuletzt = None
    if zuletzt is not None and timedelta(0) <= jetzt - zuletzt < AUTOMATISCH_ABSTAND:
        # Nach einem Update der App gilt das Gemerkte nicht mehr.
        gefunden = stand['update_gefunden']
        if isinstance(gefunden, dict) and gefunden.get('aktuell') == aktuelle_version:
            return gefunden
        return None
    try:
        einstellungen.schreiben(ordner, update_geprueft=jetzt.isoformat(),
                                update_gefunden=None)
        ergebnis = suchen(aktuelle_version, desktop, oeffentlich, laden,
                          AUTOMATISCH_ZEIT_S)
        if ergebnis['neu']:
            einstellungen.schreiben(ordner, update_gefunden=ergebnis)
    except (AktualisierungsFehler, OSError, ValueError):
        return None
    return ergebnis if ergebnis['neu'] else None


def installer_laden(aktuelle_version: str, oeffentlich: str | None = None,
                    laden=None, ziel: Path | None = None) -> Path:
    """Lädt und prüft den Installer; liefert seinen Pfad."""
    laden = laden or _laden
    daten = manifest_pruefen(laden(quelle(), MAX_MANIFEST), oeffentlich)
    if version_als_tupel(daten['version']) <= version_als_tupel(aktuelle_version):
        raise AktualisierungsFehler('Es gibt keine neuere Version.')
    if paketmodus():
        raise AktualisierungsFehler('Diese Installation aktualisiert der Microsoft Store.')
    windows = daten.get('windows') or {}
    if not windows.get('url') or not windows.get('sha256'):
        raise AktualisierungsFehler('Für Windows gibt es zu dieser Version keinen Installer.')
    inhalt = laden(windows['url'], MAX_INSTALLER, 300)
    if hashlib.sha256(inhalt).hexdigest() != str(windows['sha256']).lower():
        raise AktualisierungsFehler(
            'Der geladene Installer stimmt nicht mit der Prüfsumme überein. '
            'Nichts wurde installiert.')
    ordner = ziel or Path(tempfile.mkdtemp(prefix='nk-update-'))
    datei = ordner / re.sub(r'[^A-Za-z0-9.-]', '', f'NebenkostenFix-{daten["version"]}-Setup.exe')
    datei.write_bytes(inhalt)
    return datei


def installer_starten(datei: Path) -> None:  # pragma: no cover - Windows
    """Startet den Installer und kehrt zurück; er schließt die App selbst."""
    if sys.platform != 'win32':
        raise AktualisierungsFehler('Installieren geht nur in der Windows-App.')
    # Still (NK-175); die Abfrage nach Adminrechten bleibt, solange nach
    # Programme installiert wird. /NEUSTART=1: der Installer startet die App
    # danach wieder (installer.iss).
    befehl = [str(datei), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NEUSTART=1']
    # Bandit-Ausnahme (B603): Pfad aus installer_laden (geprüfte Prüfsumme),
    # feste Argumente, keine Shell.
    subprocess.Popen(befehl, close_fds=True)  # nosec B603
