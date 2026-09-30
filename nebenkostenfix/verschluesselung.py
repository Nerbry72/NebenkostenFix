"""Verschluesselte Sicherungen und Exporte (NK-130, F-71, E-4 → D-86).

Datenbank und Belege bleiben im Datenordner im Klartext -- dort schuetzt die
Festplattenverschluesselung (BitLocker, LUKS, verschluesselter Synology-
Ordner) besser, weil die laufende Anwendung ihren Schluessel ohnehin im
Speicher haette. Was den Rechner verlaesst -- die Sicherung auf dem
USB-Stick, der Export in der Cloud -- wird mit einer Passphrase verschluesselt.

Verfahren
---------

- Schluessel: scrypt (N = 2^15, r = 8, p = 1, 16 Byte Salz) aus der
  Passphrase, 32 Byte -> AES-256-GCM.
- Die Datei wird in Stuecken zu 1 MiB verschluesselt, damit eine Sicherung
  mit Hunderten Megabyte Belegen nicht auf einmal in den Speicher muss. Jedes
  Stueck hat eine eigene Nonce (8 Byte Zufallspraefix + 4 Byte Zaehler) und
  traegt als zusaetzliche Daten den ganzen Kopf, seine Nummer und ein
  Schlusszeichen. Vertauschte, fehlende oder angehaengte Stuecke und ein
  veraenderter Kopf fallen beim Entschluesseln auf.

Aufbau der Datei
----------------

    NKVERS1\\n                       7 Byte Kennung
    <4 Byte Laenge><Kopf als JSON>  Verfahren, Salz, Noncepraefix und
                                    Metadaten (lesbar, aber geschuetzt)
    je Stueck: <4 Byte Laenge><Chiffrat mit 16 Byte Tag>

Die Metadaten im Kopf (Zeitpunkt, Schemastand, Anzahl Belege) sind bewusst
lesbar: die Oberflaeche zeigt eine verschluesselte Sicherung in der Liste,
ohne nach der Passphrase zu fragen. Sie enthalten keine Personendaten, und
wer sie aendert, macht die Datei unlesbar.

Ohne Passphrase ist die Sicherung verloren. Das sagt die Oberflaeche, bevor
sie verschluesselt.
"""

from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

KENNUNG = b'NKVERS1\n'
STUECK = 1024 * 1024
MINDESTLAENGE = 12
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1


class VerschluesselungsFehler(Exception):
    """Passphrase falsch, Datei beschaedigt oder keine verschluesselte Datei."""


def passphrase_pruefen(passphrase: str | None) -> str:
    """Die Passphrase fuer eine neue Verschluesselung, oder ein Fehler."""
    if not passphrase or len(passphrase) < MINDESTLAENGE:
        raise VerschluesselungsFehler(
            f'Die Passphrase muss mindestens {MINDESTLAENGE} Zeichen haben. '
            'Ein Satz aus mehreren Wörtern ist leichter zu merken als ein '
            'kurzes Kennwort.')
    return passphrase


def _schluessel(passphrase: str, salz: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salz, length=32, n=n, r=r, p=p).derive(
        passphrase.encode('utf-8'))


def ist_verschluesselt(pfad) -> bool:
    try:
        with open(pfad, 'rb') as datei:
            return datei.read(len(KENNUNG)) == KENNUNG
    except OSError:
        return False


def _kopf_lesen(datei) -> tuple[bytes, dict]:
    if datei.read(len(KENNUNG)) != KENNUNG:
        raise VerschluesselungsFehler(
            'Das ist keine verschlüsselte Datei dieser Anwendung.')
    laenge_roh = datei.read(4)
    if len(laenge_roh) != 4:
        raise VerschluesselungsFehler('Die Datei ist unvollständig.')
    (laenge,) = struct.unpack('>I', laenge_roh)
    if laenge > 64 * 1024:
        raise VerschluesselungsFehler('Der Kopf der Datei ist beschädigt.')
    roh = datei.read(laenge)
    try:
        kopf = json.loads(roh.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as fehler:
        raise VerschluesselungsFehler('Der Kopf der Datei ist beschädigt.') from fehler
    if kopf.get('verfahren') != 'scrypt+aes-256-gcm':
        raise VerschluesselungsFehler('Unbekanntes Verschlüsselungsverfahren.')
    return KENNUNG + laenge_roh + roh, kopf


def metadaten_lesen(pfad) -> dict:
    """Die lesbaren Metadaten aus dem Kopf, ohne Passphrase.

    Nicht geprueft -- das geschieht erst beim Entschluesseln. Fuer die
    Anzeige in der Liste genuegt das; eingespielt wird nichts ungeprueft.
    """
    with open(pfad, 'rb') as datei:
        _, kopf = _kopf_lesen(datei)
    return dict(kopf.get('metadaten') or {})


def verschluesseln(quelle, ziel, passphrase: str, metadaten: dict | None = None) -> Path:
    """Verschluesselt ``quelle`` nach ``ziel``. Die Passphrase muss die
    Mindestlaenge haben (``passphrase_pruefen``)."""
    passphrase_pruefen(passphrase)
    salz = os.urandom(16)
    praefix = os.urandom(8)
    kopf = {
        'verfahren': 'scrypt+aes-256-gcm',
        'scrypt': {'n': SCRYPT_N, 'r': SCRYPT_R, 'p': SCRYPT_P,
                   'salz': base64.b64encode(salz).decode('ascii')},
        'nonce_praefix': base64.b64encode(praefix).decode('ascii'),
        'stueck': STUECK,
        'metadaten': metadaten or {},
    }
    roh = json.dumps(kopf, ensure_ascii=False, sort_keys=True).encode('utf-8')
    kopf_bytes = KENNUNG + struct.pack('>I', len(roh)) + roh
    aes = AESGCM(_schluessel(passphrase, salz, SCRYPT_N, SCRYPT_R, SCRYPT_P))
    ziel = Path(ziel)
    temp = ziel.with_name(ziel.name + '.teil')
    try:
        with open(quelle, 'rb') as ein, open(temp, 'wb') as aus:
            aus.write(kopf_bytes)
            nummer = 0
            stueck = ein.read(STUECK)
            while True:
                naechstes = ein.read(STUECK)
                letztes = not naechstes
                nonce = praefix + struct.pack('>I', nummer)
                zusatz = kopf_bytes + struct.pack('>I?', nummer, letztes)
                chiffrat = aes.encrypt(nonce, stueck, zusatz)
                aus.write(struct.pack('>I', len(chiffrat)))
                aus.write(chiffrat)
                if letztes:
                    break
                stueck = naechstes
                nummer += 1
                if nummer >= 2 ** 32 - 1:
                    raise VerschluesselungsFehler('Die Datei ist zu groß.')
            aus.flush()
            os.fsync(aus.fileno())
        os.replace(temp, ziel)
    except BaseException:
        if temp.exists():
            temp.unlink()
        raise
    return ziel


def entschluesseln(quelle, ziel, passphrase: str) -> dict:
    """Entschluesselt ``quelle`` nach ``ziel`` und liefert die Metadaten.

    Bei falscher Passphrase oder jeder Veraenderung der Datei bleibt ``ziel``
    nicht halb geschrieben liegen: es entsteht erst am Ende.
    """
    ziel = Path(ziel)
    temp = ziel.with_name(ziel.name + '.teil')
    try:
        with open(quelle, 'rb') as ein:
            kopf_bytes, kopf = _kopf_lesen(ein)
            try:
                parameter = kopf['scrypt']
                salz = base64.b64decode(parameter['salz'])
                praefix = base64.b64decode(kopf['nonce_praefix'])
                schluessel = _schluessel(passphrase or '', salz, int(parameter['n']),
                                         int(parameter['r']), int(parameter['p']))
            except (KeyError, ValueError, TypeError) as fehler:
                raise VerschluesselungsFehler(
                    'Der Kopf der Datei ist beschädigt.') from fehler
            aes = AESGCM(schluessel)
            with open(temp, 'wb') as aus:
                nummer = 0
                while True:
                    laenge_roh = ein.read(4)
                    if len(laenge_roh) != 4:
                        raise VerschluesselungsFehler(
                            'Die Datei ist unvollständig oder beschädigt.')
                    (laenge,) = struct.unpack('>I', laenge_roh)
                    chiffrat = ein.read(laenge)
                    if len(chiffrat) != laenge or laenge > STUECK + 16:
                        raise VerschluesselungsFehler(
                            'Die Datei ist unvollständig oder beschädigt.')
                    nonce = praefix + struct.pack('>I', nummer)
                    klar = None
                    for letztes in (False, True):
                        zusatz = kopf_bytes + struct.pack('>I?', nummer, letztes)
                        try:
                            klar = aes.decrypt(nonce, chiffrat, zusatz)
                            break
                        except InvalidTag:
                            continue
                    if klar is None:
                        raise VerschluesselungsFehler(
                            'Die Passphrase stimmt nicht, oder die Datei ist '
                            'beschädigt.')
                    aus.write(klar)
                    if letztes:
                        if ein.read(1):
                            raise VerschluesselungsFehler(
                                'Hinter dem letzten Stück stehen fremde Daten.')
                        break
                    nummer += 1
        os.replace(temp, ziel)
    except BaseException:
        if temp.exists():
            temp.unlink()
        raise
    return dict(kopf.get('metadaten') or {})
