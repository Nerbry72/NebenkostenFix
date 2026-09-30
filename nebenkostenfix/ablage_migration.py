"""Der vorhandene Belegbestand wandert auf neutrale Namen (NK-131, D-87).

Vor NK-131 lagen die Dateien unter sprechenden Namen im Baum
``<Immobilie>/Wohnungen/<Wohnung>/<Mieter>/…``. Die Wanderung bringt jede
Datei, auf die die Datenbank zeigt, nach ``<Jahr>/<uuid>.<endung>`` und
schreibt den neuen Pfad in jede Zeile, die auf sie zeigt.

Reihenfolge, damit kein Absturz einen Beleg kostet:

  1. Fuer jede Datei einen harten Verweis (sonst eine Kopie) unter dem neuen
     Namen anlegen und die Pruefsumme vergleichen. Die alte Datei bleibt.
  2. Alle Pfade in einer Transaktion umschreiben, festschreiben.
  3. Erst dann die alten Namen entfernen und leere Ordner aufraeumen.

Bricht der Lauf vor 2 ab, zeigt die Datenbank weiter auf die alten Dateien;
die neuen Verweise werden wieder entfernt (NK-147), der naechste Lauf legt
neue an. Nur ein harter Absturz kann sie liegen lassen -- dann sind sie
harmlos, auch fuer die Sicherung (backup._als_datei). Bricht er nach 2 ab, bleiben alte Namen als zweiter Verweis auf
denselben Inhalt liegen -- kein Verlust, nur ein Rest im alten Baum.

Dateien, auf die keine Zeile zeigt, bleiben unberuehrt. Fehlende Dateien
werden gezaehlt, nicht erfunden. Das Protokoll nennt nur Zahlen, keine Namen.

``pruefen=True`` ist der Probelauf fuer den Live-Schnappschuss (Tor 0.8-S):
er rechnet alles durch und aendert nichts.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from nebenkostenfix import uploads

protokoll = logging.getLogger(__name__)

NEUTRAL = re.compile(r'^\d{4}/[0-9a-f]{32}\.[a-z0-9]{1,16}$')

# NK-147: Wo der Belegordner vor NK-132 im Container hing. Eine alte Instanz
# hat manche Pfade absolut unter dieser Wurzel gespeichert; nach dem Umzug
# liegt derselbe Baum unter DATA_DIR/belege. Ein solcher Pfad wird relativ
# zur neuen Wurzel gelesen -- nie ausserhalb von ihr (pfad_aufloesen).
# ``ALTE_BELEGWURZEL`` nennt eine weitere, falls die alte Instanz anders lag.
ALTE_WURZELN = ('/mnt/nas/nebenkostenabrechnung', '/mnt/belege', '/app/belege')


def _spalten():
    from nebenkostenfix.models import (CostInvoice, InvoiceDocument, MeterReading, Tenant,
                        TenantBillingReport)
    return [
        (Tenant, 'contract_path'),
        (MeterReading, 'document_path'),
        (CostInvoice, 'document_path'),
        (InvoiceDocument, 'document_path'),
        (TenantBillingReport, 'document_path'),
        (TenantBillingReport, 'document_path_detailed'),
    ]


def _sha256(pfad) -> str:
    hasher = hashlib.sha256()
    with open(pfad, 'rb') as datei:
        for stueck in iter(lambda: datei.read(1024 * 1024), b''):
            hasher.update(stueck)
    return hasher.hexdigest()


def _endung(pfad: Path) -> str:
    with open(pfad, 'rb') as datei:
        erkannt = uploads.erkenne(datei.read(uploads.KOPF_BYTES))
    if erkannt:
        return erkannt
    # Altbestand eines anderen Typs: Endung entschaerft behalten, ausgeliefert
    # wird er ohnehin nur als Download (NK-129).
    roh = re.sub(r'[^a-z0-9]', '', pfad.suffix.lower())[:16]
    return roh or 'bin'


def _alte_wurzeln() -> list[str]:
    zusatz = (os.environ.get('ALTE_BELEGWURZEL') or '').strip().rstrip('/')
    return ([zusatz] if zusatz else []) + list(ALTE_WURZELN)


def quelle_finden(wurzel, alt: str) -> Path | None:
    """Die Datei zu einem gespeicherten Pfad, auch unter alter Wurzel."""
    gefunden = uploads.pfad_aufloesen(wurzel, alt)
    if gefunden is not None or not alt.startswith('/'):
        return gefunden
    for alte in _alte_wurzeln():
        if alt.startswith(alte + '/'):
            gefunden = uploads.pfad_aufloesen(wurzel, alt[len(alte) + 1:])
            if gefunden is not None:
                return gefunden
    return None


def offene_pfade(session) -> dict[str, list]:
    """Alte Pfade -> Liste der Zeilen (Modell, id, Spalte), die darauf zeigen."""
    offen: dict[str, list] = {}
    for modell, spalte in _spalten():
        feld = getattr(modell, spalte)
        for kennung, pfad in session.query(modell.id, feld).filter(feld.isnot(None)):
            if pfad and not NEUTRAL.match(pfad):
                offen.setdefault(pfad, []).append((modell, kennung, spalte))
    return offen


def migrieren(session, wurzel, pruefen: bool = False) -> dict:
    """Bringt den Bestand auf neutrale Namen. Liefert einen Bericht mit Zahlen.

    ``pruefen=True``: nur rechnen und Pruefsummen lesen, nichts schreiben.
    """
    wurzel = Path(os.path.realpath(wurzel))
    offen = offene_pfade(session)
    bericht = {'pfade': len(offen), 'zeilen': sum(len(z) for z in offen.values()),
               'umbenannt': 0, 'fehlend': 0, 'bytegleich': 0, 'abweichend': 0,
               'probelauf': pruefen}
    if not offen:
        return bericht

    neu_je_alt: dict[str, tuple[str, Path]] = {}
    for alt in sorted(offen):
        quelle = quelle_finden(wurzel, alt)
        if quelle is None:
            bericht['fehlend'] += 1
            continue
        jahr = datetime.fromtimestamp(quelle.stat().st_mtime).year
        neu = f'{jahr:04d}/{uuid.uuid4().hex}.{_endung(quelle)}'
        if pruefen:
            _sha256(quelle)  # lesbar? sonst faellt es hier auf
            bericht['umbenannt'] += 1
            bericht['bytegleich'] += 1
            continue
        ziel = wurzel / neu
        ziel.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(quelle, ziel)
        except OSError:
            shutil.copy2(quelle, ziel)
        if _sha256(quelle) != _sha256(ziel):
            bericht['abweichend'] += 1
            ziel.unlink()
            continue
        bericht['bytegleich'] += 1
        neu_je_alt[alt] = (neu, quelle)

    if pruefen:
        return bericht

    try:
        for alt, (neu, _) in neu_je_alt.items():
            for modell, kennung, spalte in offen[alt]:
                zeile = session.get(modell, kennung)
                setattr(zeile, spalte, neu)
        session.commit()
    except BaseException:
        # Vor dem Festschreiben abgebrochen: die Datenbank zeigt weiter auf
        # die alten Namen. Die neuen Verweise wieder weg, sonst sammeln sich
        # bei jedem Start weitere an (NK-147).
        session.rollback()
        for neu, _ in neu_je_alt.values():
            with contextlib.suppress(OSError):
                (wurzel / neu).unlink()
        raise
    bericht['umbenannt'] = len(neu_je_alt)

    for _, (neu, quelle) in neu_je_alt.items():
        if quelle.exists() and os.path.realpath(quelle) != os.path.realpath(wurzel / neu):
            quelle.unlink()
    _leere_ordner_entfernen(wurzel)
    protokoll.info(
        'Belegablage auf neutrale Namen umgestellt (NK-131): %d Dateien für '
        '%d Einträge, %d fehlend, %d bytegleich, %d abweichend.',
        bericht['umbenannt'], bericht['zeilen'], bericht['fehlend'],
        bericht['bytegleich'], bericht['abweichend'])
    return bericht


def _leere_ordner_entfernen(wurzel: Path) -> None:
    """Leere Ordner des alten Baums weg; Jahresordner bleiben."""
    for ordner, unterordner, dateien in os.walk(wurzel, topdown=False):
        pfad = Path(ordner)
        if pfad == wurzel or re.fullmatch(r'\d{4}', pfad.name) and pfad.parent == wurzel:
            continue
        try:
            if not any(pfad.iterdir()):
                pfad.rmdir()
        except OSError:
            protokoll.info('Ordner der alten Ablage nicht entfernbar', exc_info=True)
