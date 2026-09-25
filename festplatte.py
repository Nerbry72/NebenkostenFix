"""Ist der Datenordner auf einer verschluesselten Festplatte? (NK-130, D-86)

Die Datenbank und die Belege liegen im Klartext; gegen einen gestohlenen
Rechner schuetzt die Verschluesselung der Festplatte (BitLocker unter
Windows, LUKS unter Linux, verschluesselter Ordner auf der Synology). Die
Oberflaeche empfiehlt sie und prueft sie, wo das ohne Adminrechte geht:

    Windows  Shell-Eigenschaft System.Volume.BitLockerProtection des
             Laufwerks (braucht keine Adminrechte, anders als manage-bde)
    Linux    Geraet hinter dem Einhaengepunkt; dm-crypt meldet sich unter
             /sys/block/dm-*/dm/uuid mit dem Praefix CRYPT-
    sonst    unbekannt (Docker-Volume, NAS, macOS) -- dann nur der Hinweis

Ergebnis ist immer ein kleines Woerterbuch fuer die Oberflaeche, nie ein
Fehler: eine fehlgeschlagene Pruefung heisst "unbekannt".
"""

from __future__ import annotations

import logging
import os
# Bandit-Ausnahme: feste Argumente, keine Nutzereingabe
import subprocess  # nosec B404
import sys

protokoll = logging.getLogger(__name__)

HINWEIS = ('Datenbank und Belege liegen im Klartext im Datenordner. Schützen '
           'Sie den Rechner mit Festplattenverschlüsselung (Windows: '
           'BitLocker oder Geräteverschlüsselung, Linux: LUKS, Synology: '
           'verschlüsselter freigegebener Ordner) und verschlüsseln Sie '
           'Sicherungen, die den Rechner verlassen.')


def pruefen(pfad: str) -> dict:
    try:
        if sys.platform == 'win32':  # pragma: no cover - Windows
            status = _windows(pfad)
        elif sys.platform.startswith('linux'):
            status = _linux(pfad)
        else:  # pragma: no cover - macOS u. a.
            status = 'unbekannt'
    except Exception:  # noqa: BLE001 -- Pruefung ist Komfort, nie Abbruch
        protokoll.info('Festplattenverschlüsselung nicht prüfbar', exc_info=True)
        status = 'unbekannt'
    texte = {
        'ja': 'Der Datenordner liegt auf einem verschlüsselten Laufwerk.',
        'nein': 'Der Datenordner liegt auf einem unverschlüsselten Laufwerk.',
        'unbekannt': 'Ob das Laufwerk verschlüsselt ist, lässt sich hier '
                     'nicht prüfen.',
    }
    return {'status': status, 'text': texte[status], 'hinweis': HINWEIS}


def _einhaengepunkt(pfad: str, einhaengungen: list[tuple[str, str]]) -> tuple[str, str] | None:
    pfad = os.path.realpath(pfad)
    beste = None
    for geraet, punkt in einhaengungen:
        if pfad == punkt or pfad.startswith(punkt.rstrip('/') + '/') or punkt == '/':
            if beste is None or len(punkt) > len(beste[1]):
                beste = (geraet, punkt)
    return beste


def _linux(pfad: str, mounts: str = '/proc/self/mounts',
           sys_block: str = '/sys/block') -> str:
    with open(mounts, encoding='utf-8') as datei:
        einhaengungen = [(z.split()[0], z.split()[1]) for z in datei if z.strip()]
    treffer = _einhaengepunkt(pfad, einhaengungen)
    if treffer is None:
        return 'unbekannt'
    geraet = treffer[0]
    if not geraet.startswith('/dev/'):
        return 'unbekannt'  # overlay, tmpfs, Netzfreigabe, Docker-Volume
    echt = os.path.realpath(geraet)
    name = os.path.basename(echt)
    if not name.startswith('dm-'):
        return 'nein'
    try:
        with open(os.path.join(sys_block, name, 'dm', 'uuid'), encoding='utf-8') as datei:
            return 'ja' if datei.read().startswith('CRYPT-') else 'nein'
    except OSError:
        return 'unbekannt'


def _windows(pfad: str) -> str:  # pragma: no cover - Windows
    laufwerk = os.path.splitdrive(os.path.realpath(pfad))[0] or 'C:'
    befehl = (
        "(New-Object -ComObject Shell.Application).NameSpace('" + laufwerk + "\\')"
        ".Self.ExtendedProperty('System.Volume.BitLockerProtection')")
    # Bandit-Ausnahme: feste Argumentliste, Laufwerksbuchstabe aus realpath
    ausgabe = subprocess.run(  # nosec B603 B607
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', befehl],
        capture_output=True, text=True, timeout=10,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    # 1 an, 3 wird verschluesselt, 5 angehalten, 6 an (entsperrt); 2 aus
    if ausgabe in ('1', '3', '5', '6'):
        return 'ja'
    if ausgabe == '2':
        return 'nein'
    return 'unbekannt'
