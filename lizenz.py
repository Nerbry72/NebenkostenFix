"""Lizenzdatei, offline geprüft (NK-080, E-9 → D-93).

Die Lizenz gilt für **Updates, nie für die Daten**. Ohne Lizenz, mit einer
abgelaufenen oder einer kaputten Lizenzdatei läuft die installierte Version
unverändert weiter -- jede Abrechnung, jede Sicherung, jeder Export. Nur
``aktualisierung.py`` fragt die Lizenz, und auch dort nur, ob ein Update
installiert werden darf. Es gibt keinen Anruf beim Herausgeber
(kein Phone-Home): geprüft wird die Signatur mit dem öffentlichen Schlüssel,
der in dieser Datei steht.

Format (``lizenz.nklizenz`` im Datenordner, JSON)::

    {"format": "nk-lizenz-1",
     "daten": {"produkt": "nebenkostenabrechnung", "kennung": "<uuid>",
               "lizenznehmer": "Anna Vermieterin", "ausgestellt": "2026-10-01",
               "updates_bis": "2027-10-01"},
     "signatur": "<Ed25519 über die kanonische Form von daten, base64>"}

Kanonisch heißt: JSON mit sortierten Schlüsseln, ohne Leerraum, UTF-8. So
prüft dieselbe Signatur, egal wie ein Editor die Datei später einrückt.

Ein Update ist erlaubt, wenn es **veröffentlicht wurde, solange die Lizenz
lief** (``veroeffentlicht <= updates_bis``). Wer nach Ablauf auf ein Update
aus seiner Laufzeit stößt, bekommt es also noch.

Der private Schlüssel liegt nur beim Herausgeber, nie im Repository;
``scripts/lizenz_werkzeug.py`` erzeugt ihn und stellt Lizenzen aus. Solange
``HERAUSGEBER_SCHLUESSEL`` leer ist, kann diese Fassung keine Lizenz prüfen
und sagt das -- auch das sperrt nichts.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

FORMAT = 'nk-lizenz-1'
PRODUKT = 'nebenkostenabrechnung'
DATEINAME = 'lizenz.nklizenz'
MAX_GROESSE = 16 * 1024

# Öffentlicher Ed25519-Schlüssel des Herausgebers (32 Byte, base64). Der
# Herausgeber erzeugt das Paar mit ``scripts/lizenz_werkzeug.py schluessel``
# und trägt hier den öffentlichen Teil ein (NK-080, Handschritt).
HERAUSGEBER_SCHLUESSEL = ''

PFLICHTFELDER = ('produkt', 'kennung', 'lizenznehmer', 'ausgestellt', 'updates_bis')


class LizenzFehler(Exception):
    """Die Datei ist keine gültige Lizenz. Gesperrt wird dadurch nichts."""


def kanonisch(daten: dict) -> bytes:
    return json.dumps(daten, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def schluessel_laden(oeffentlich: str | None = None) -> Ed25519PublicKey:
    roh = HERAUSGEBER_SCHLUESSEL if oeffentlich is None else oeffentlich
    if not roh:
        raise LizenzFehler(
            'Diese Fassung enthält noch keinen Herausgeberschlüssel und kann '
            'Lizenzen nicht prüfen. Die Anwendung ist trotzdem voll nutzbar.')
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(roh, validate=True))
    except (ValueError, binascii.Error) as fehler:
        raise LizenzFehler('Der eingebaute Herausgeberschlüssel ist beschädigt.') from fehler


def signieren(daten: dict, privat: Ed25519PrivateKey, art: str = FORMAT) -> dict:
    """Für das Werkzeug des Herausgebers und für Tests."""
    return {'format': art, 'daten': daten,
            'signatur': base64.b64encode(privat.sign(kanonisch(daten))).decode('ascii')}


def signatur_pruefen(umschlag: dict, art: str, oeffentlich: str | None = None) -> dict:
    """Prüft Format und Signatur eines Umschlags; liefert ``daten``."""
    if not isinstance(umschlag, dict) or umschlag.get('format') != art:
        raise LizenzFehler('Die Datei hat nicht das erwartete Format.')
    daten = umschlag.get('daten')
    if not isinstance(daten, dict):
        raise LizenzFehler('Die Datei enthält keine Daten.')
    try:
        signatur = base64.b64decode(umschlag.get('signatur') or '', validate=True)
    except (ValueError, binascii.Error) as fehler:
        raise LizenzFehler('Die Signatur ist unlesbar.') from fehler
    try:
        schluessel_laden(oeffentlich).verify(signatur, kanonisch(daten))
    except InvalidSignature as fehler:
        raise LizenzFehler(
            'Die Signatur passt nicht. Die Datei ist verändert oder stammt '
            'nicht vom Herausgeber.') from fehler
    return daten


def _datum(wert, feld: str) -> date:
    try:
        return date.fromisoformat(str(wert))
    except ValueError as fehler:
        raise LizenzFehler(f'Das Feld „{feld}“ ist kein Datum.') from fehler


def pruefen(inhalt: bytes | str, oeffentlich: str | None = None) -> dict:
    """Die geprüften Lizenzdaten, oder ``LizenzFehler``."""
    if isinstance(inhalt, bytes):
        if len(inhalt) > MAX_GROESSE:
            raise LizenzFehler('Die Datei ist zu groß für eine Lizenz.')
        try:
            inhalt = inhalt.decode('utf-8')
        except UnicodeDecodeError as fehler:
            raise LizenzFehler('Die Datei ist keine Lizenzdatei.') from fehler
    if len(inhalt) > MAX_GROESSE:
        raise LizenzFehler('Die Datei ist zu groß für eine Lizenz.')
    try:
        umschlag = json.loads(inhalt)
    except ValueError as fehler:
        raise LizenzFehler('Die Datei ist keine Lizenzdatei.') from fehler
    daten = signatur_pruefen(umschlag, FORMAT, oeffentlich)
    fehlend = [f for f in PFLICHTFELDER if not daten.get(f)]
    if fehlend:
        raise LizenzFehler('In der Lizenz fehlt: ' + ', '.join(fehlend) + '.')
    if daten['produkt'] != PRODUKT:
        raise LizenzFehler('Die Lizenz gilt für ein anderes Produkt.')
    _datum(daten['ausgestellt'], 'ausgestellt')
    _datum(daten['updates_bis'], 'updates_bis')
    return daten


def _deutsch(tag: date) -> str:
    return tag.strftime('%d.%m.%Y')


def status(ordner: str | os.PathLike, heute: date | None = None,
           oeffentlich: str | None = None) -> dict:
    """Was die Oberfläche über die Lizenz sagt. Wirft nie."""
    heute = heute or date.today()
    datei = Path(ordner) / DATEINAME
    if not datei.is_file():
        return {'status': 'keine', 'updates_bis': None, 'lizenznehmer': None,
                'text': 'Keine Lizenz hinterlegt. Die Anwendung ist voll nutzbar; '
                        'eine Lizenz brauchen Sie nur für Updates.'}
    try:
        daten = pruefen(datei.read_bytes(), oeffentlich)
    except (LizenzFehler, OSError) as fehler:
        return {'status': 'ungueltig', 'updates_bis': None, 'lizenznehmer': None,
                'text': f'Die Lizenzdatei ist nicht gültig: {fehler} Die Anwendung '
                        'läuft trotzdem uneingeschränkt weiter.'}
    bis = _datum(daten['updates_bis'], 'updates_bis')
    grund = {'updates_bis': bis.isoformat(), 'lizenznehmer': daten['lizenznehmer'],
             'kennung': daten['kennung']}
    if bis < heute:
        return {'status': 'abgelaufen', **grund,
                'text': f'Updates waren bis {_deutsch(bis)} enthalten. Diese Version '
                        'läuft unbegrenzt weiter; Ihre Daten bleiben vollständig '
                        'nutzbar.'}
    return {'status': 'gueltig', **grund,
            'text': f'Lizenziert für {daten["lizenznehmer"]}, Updates bis {_deutsch(bis)}.'}


def update_erlaubt(lizenzstatus: dict, veroeffentlicht: date) -> bool:
    """Darf ein Update installiert werden, das an ``veroeffentlicht`` erschien?"""
    if lizenzstatus.get('status') not in ('gueltig', 'abgelaufen'):
        return False
    return veroeffentlicht <= date.fromisoformat(lizenzstatus['updates_bis'])


def hinterlegen(ordner: str | os.PathLike, inhalt: bytes | str,
                oeffentlich: str | None = None) -> dict:
    """Prüft und legt die Lizenz im Datenordner ab (ersetzt eine alte)."""
    pruefen(inhalt, oeffentlich)
    roh = inhalt.encode('utf-8') if isinstance(inhalt, str) else inhalt
    ziel = Path(ordner) / DATEINAME
    ziel.parent.mkdir(parents=True, exist_ok=True)
    temp = ziel.with_name(ziel.name + '.neu')
    temp.write_bytes(roh)
    os.replace(temp, ziel)
    return status(ordner, oeffentlich=oeffentlich)
