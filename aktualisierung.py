"""Nach Updates suchen -- nur auf Knopfdruck (NK-081, E-9 → D-93).

Die Anwendung ruft nie von selbst nach Hause. Erst der Knopf „Nach Updates
suchen“ lädt eine kleine Beschreibung der neuesten Version (das Manifest)
von ``UPDATE_QUELLE``. Das Manifest ist mit demselben Herausgeberschlüssel
signiert wie die Lizenzen (``lizenz.py``); ein verändertes oder fremdes
Manifest wird verworfen, bevor irgendetwas geladen wird.

Manifest (JSON)::

    {"format": "nk-update-1",
     "daten": {"version": "0.9.1", "veroeffentlicht": "2026-10-15",
               "hinweise": "Kurz, was neu ist.",
               "windows": {"url": "https://…/NebenkostenFix-0.9.1-Setup.exe",
                           "sha256": "…"},
               "docker": "ghcr.io/nerbry72/nebenkostenfix:0.9.1"},
     "signatur": "…"}

Zwei Wege:

- **Docker:** die Anwendung sagt nur, dass es eine neue Version gibt und
  welches Abbild; aktualisiert wird per Tag (``docker compose pull`` und
  ``up -d``). Beim Start sichert die Anwendung vor jeder Wanderung
  automatisch (``app.vor_der_wanderung_sichern``).
- **Windows-App:** lädt den Installer über https, prüft die Prüfsumme aus
  dem signierten Manifest und startet ihn. Er installiert über die bestehende
  Installation (gleiche AppId), schließt die App dabei sauber (Restart
  Manager) und lässt die Daten in ihrem Ordner. Nur, wenn die Lizenz das
  Update umfasst (``lizenz.update_erlaubt``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
# Bandit-Ausnahme (B404): nur installer_starten, feste Argumente
import subprocess  # nosec B404
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

import lizenz
from lizenz import LizenzFehler

FORMAT = 'nk-update-1'
# Wird mit dem ersten Release gesetzt (NK-135); leer heißt: dieser Build
# kennt keine Update-Quelle. ``NK_UPDATE_QUELLE`` überschreibt ihn.
UPDATE_QUELLE = ''
MAX_MANIFEST = 64 * 1024
MAX_INSTALLER = 500 * 1024 * 1024


class AktualisierungsFehler(Exception):
    """Suche oder Download gescheitert; die installierte Version bleibt."""


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
        daten = lizenz.signatur_pruefen(umschlag, FORMAT, oeffentlich)
    except LizenzFehler as fehler:
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


def suchen(aktuelle_version: str, lizenzstatus: dict, desktop: bool,
           oeffentlich: str | None = None, laden=None) -> dict:
    """Ergebnis für die Oberfläche. Wirft ``AktualisierungsFehler``."""
    laden = laden or _laden
    adresse = quelle()
    if not adresse:
        raise AktualisierungsFehler(
            'Dieser Build kennt keine Update-Quelle. Neue Versionen finden Sie '
            'auf der Seite, von der Sie die Anwendung haben.')
    daten = manifest_pruefen(laden(adresse, MAX_MANIFEST), oeffentlich)
    neu = version_als_tupel(daten['version']) > version_als_tupel(aktuelle_version)
    veroeffentlicht = date.fromisoformat(daten['veroeffentlicht'])
    erlaubt = lizenz.update_erlaubt(lizenzstatus, veroeffentlicht)
    windows = daten.get('windows') or {}
    ergebnis = {
        'aktuell': aktuelle_version,
        'version': daten['version'],
        'veroeffentlicht': daten['veroeffentlicht'],
        'hinweise': str(daten.get('hinweise') or ''),
        'neu': neu,
        'lizenz_erlaubt': erlaubt,
        'docker': daten.get('docker'),
        'installierbar': bool(neu and erlaubt and desktop and windows.get('url')
                              and windows.get('sha256')),
    }
    if not neu:
        ergebnis['text'] = f'Sie haben die neueste Version ({aktuelle_version}).'
    elif not erlaubt:
        ergebnis['text'] = (
            f'Version {daten["version"]} ist erschienen. Ihre Lizenz umfasst dieses '
            'Update nicht. Ihre installierte Version läuft unverändert weiter.')
    elif desktop:
        ergebnis['text'] = f'Version {daten["version"]} ist verfügbar.'
    else:
        ergebnis['text'] = (
            f'Version {daten["version"]} ist verfügbar. Aktualisieren Sie das '
            f'Abbild ({daten.get("docker") or "neuer Tag"}) mit „docker compose '
            'pull“ und „docker compose up -d“; vor der Umstellung der Datenbank '
            'sichert die Anwendung automatisch.')
    return ergebnis


def installer_laden(aktuelle_version: str, lizenzstatus: dict,
                    oeffentlich: str | None = None, laden=None,
                    ziel: Path | None = None) -> Path:
    """Lädt und prüft den Installer; liefert seinen Pfad."""
    laden = laden or _laden
    daten = manifest_pruefen(laden(quelle(), MAX_MANIFEST), oeffentlich)
    if version_als_tupel(daten['version']) <= version_als_tupel(aktuelle_version):
        raise AktualisierungsFehler('Es gibt keine neuere Version.')
    if not lizenz.update_erlaubt(lizenzstatus, date.fromisoformat(daten['veroeffentlicht'])):
        raise AktualisierungsFehler('Ihre Lizenz umfasst dieses Update nicht.')
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
    # Bandit-Ausnahme (B603): Pfad aus installer_laden (geprüfte Prüfsumme),
    # feste Argumente, keine Shell.
    subprocess.Popen([str(datei), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],  # nosec B603
                     close_fds=True)
