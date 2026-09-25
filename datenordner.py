"""Ein Datenordner für alles (NK-132, E-2 → D-90, F-61).

Bis NK-132 verteilte sich eine Instanz auf mehrere Orte mit eigenen
Variablen: die Datenbank über ``DATABASE_URL`` (``/app/data``), die Belege
über ``NAS_MOUNT_PATH`` (``/mnt/nas/...`` bzw. ``/mnt/belege``, auf Wunsch per
CIFS eingehängt), der Sitzungsschlüssel neben der Datenbank. „NAS“ war dabei
nur ein Name -- die Anwendung hat nie selbst mit einem NAS gesprochen.

Jetzt gibt es **einen** Ordner:

    DATA_DIR/
      nebenkosten.db     Datenbank (SQLite, WAL)
      belege/            Belege, Verträge, Fotos, PDFs (neutrale Namen, NK-131)
      backups/           Sicherungen (Vorgabeziel)
      secret_key         Sitzungsschlüssel (0600)
      nebenkosten.log    Protokoll

Docker hängt genau ein Volume unter ``/data`` ein; wer sein NAS nutzen will,
bindet es als dieses Volume ein (Sache des Betriebssystems, nicht der App).
Die Windows-App setzt ``DATA_DIR`` auf ``Dokumente\\Nebenkostenabrechnung``
(D-84, änderbar).

Übergang (eine Version lang): Ist ``DATA_DIR`` nicht gesetzt, gilt der Ordner
der SQLite-Datei aus ``DATABASE_URL``; ``NAS_MOUNT_PATH`` überschreibt den
Belegordner weiter und wird beim Start als veraltet gemeldet. Beides fällt
mit der nächsten Version weg.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

protokoll = logging.getLogger(__name__)

DB_NAME = 'nebenkosten.db'
BELEGE = 'belege'
SICHERUNGEN = 'backups'


class DatenordnerFehler(RuntimeError):
    """Es ist kein Datenordner erkennbar. Der Start bricht mit Anleitung ab."""


def _sqlite_ordner(adresse: str) -> str | None:
    if not adresse.startswith('sqlite:///'):
        return None
    pfad = adresse[len('sqlite:///'):]
    if pfad.startswith(':memory:') or not pfad:
        return None
    return os.path.dirname(os.path.abspath(pfad)) or '/'


def datenordner() -> Path:
    """Der Datenordner dieser Instanz (nicht angelegt, nur bestimmt)."""
    roh = (os.environ.get('DATA_DIR') or '').strip()
    if roh:
        return Path(os.path.abspath(os.path.expanduser(roh)))
    aus_db = _sqlite_ordner((os.environ.get('DATABASE_URL') or '').strip())
    if aus_db:
        return Path(aus_db)
    nas = (os.environ.get('NAS_MOUNT_PATH') or '').strip()
    if nas:
        # Postgres im Entwicklerstapel ohne DATA_DIR: der alte Belegordner
        # ist der einzige beständige Ort (Verhalten vor NK-132).
        return Path(os.path.abspath(nas))
    raise DatenordnerFehler(
        'Es ist kein Datenordner festgelegt. Setzen Sie DATA_DIR auf den '
        'Ordner, in dem Datenbank, Belege und Sicherungen liegen sollen '
        '(Docker: DATA_DIR=/data mit einem Volume dort).')


def datenbank_url() -> str:
    """DATABASE_URL, sonst SQLite im Datenordner."""
    roh = (os.environ.get('DATABASE_URL') or '').strip()
    if roh:
        return roh
    return f'sqlite:///{datenordner() / DB_NAME}'


def belegordner() -> Path:
    """Die Wurzel der Belegablage.

    ``NAS_MOUNT_PATH`` gilt eine Version lang als Alias (veraltet).
    """
    alt = (os.environ.get('NAS_MOUNT_PATH') or '').strip()
    if alt:
        return Path(os.path.abspath(alt))
    return datenordner() / BELEGE


def sicherungsordner() -> Path:
    """Vorgabeziel für Sicherungen."""
    return datenordner() / SICHERUNGEN


def veraltete_variablen() -> list[str]:
    """Umgebungsvariablen aus der Zeit vor NK-132, die noch gesetzt sind."""
    return [name for name in ('NAS_MOUNT_PATH', 'LOCAL_PDF_PATH', 'LOCAL_TEMP_PATH',
                              'NAS_HOST', 'NAS_SHARE', 'NAS_USERNAME', 'NAS_PASSWORD')
            if (os.environ.get(name) or '').strip()]


def anlegen() -> Path:
    """Legt Datenordner, Belege und Sicherungen an; liefert den Datenordner."""
    ordner = datenordner()
    for pfad in (ordner, belegordner(), sicherungsordner()):
        pfad.mkdir(parents=True, exist_ok=True)
    return ordner
