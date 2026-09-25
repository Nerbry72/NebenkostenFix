"""Dateinamen, wie sie in echten Abrechnungsordnern vorkommen (NK-026).

Erzeugte Testdaten, keine echten Mieterdaten. Die Namen stammen aus dem, was
ein Vermieter tatsaechlich anlegt: Umlaute, ss, Leerzeichen, Klammern, mehrere
Punkte, sehr lange Namen aus dem Scanner. Dazu ein paar Faelle, die kein Mensch
absichtlich tippt, die aber ueber Uploads hereinkommen.

Der Inhalt sind echte PDF- und JPEG-Daten, keine Textdateien mit passender
Endung. Das ist kein Selbstzweck: eine Pruefsumme ueber "hallo" beweist nichts
ueber ein 3-MB-Scan, und ein Rundlauf, der nur Text bewegt, laesst offen, ob
irgendwo unterwegs jemand die Datei als Text oeffnet und Zeilenenden umschreibt.
"""

from __future__ import annotations

import hashlib
import io
import unicodedata
from pathlib import Path

# (Name, warum er hier steht). Der Grund steht dabei, damit niemand einen
# Eintrag streicht, weil er ihn fuer eine Marotte haelt.
BOESE_NAMEN = [
    ('Wärmemessdienst.pdf', 'Umlaut'),
    ('Straßenreinigung 2025.pdf', 'ss und Leerzeichen'),
    ('Nebenkosten (Kopie).pdf', 'Klammern'),
    ('Abrechnung.2025.final.pdf', 'mehrere Punkte'),
    ('Grundsteuer B - Bescheid vom 14.03.2025.pdf', 'Punkte, Bindestrich, Leerzeichen'),
    ("O'Briens Rechnung.pdf", 'Apostroph, bricht schlecht gebautes SQL und Shell'),
    ('Beleg #12 & Co. 50%.pdf', 'Raute, Kaufmanns-Und, Prozent: Aerger in URLs'),
    ('-vorne-ein-strich.pdf', 'fuehrender Strich, sieht fuer jedes CLI wie eine Option aus'),
    ('Zähler EG links (Nr. 3).jpg', 'Umlaut, Klammern, Punkt, JPEG'),
    ('Foto 2025-03-14 08.31.02.jpg', 'Punkte in der Uhrzeit, typischer Kameraname'),
    ('GROSSBUCHSTABEN.PDF', 'Endung in Grossbuchstaben'),
    ('Müller_NFC.pdf', 'u-Umlaut als ein Zeichen (NFC)'),
    (unicodedata.normalize('NFD', 'Müller_NFD.pdf'), 'u-Umlaut als u plus Punkte (NFD)'),
    ('a' * 200 + '.pdf', 'Langname, ext4 laesst 255 Bytes zu'),
    ('Ümläüte' * 20 + '.pdf', 'lang und mehrbytig: 240 Namensbytes bei 160 Zeichen'),
]

# Unterverzeichnisse mit denselben Problemen. Der Belegordner ist nach
# Immobilie und Wohnung gegliedert, und die heissen, wie sie heissen.
BOESE_ORDNER = [
    'Haus Müllerstraße 3',
    'Haus Müllerstraße 3/Wohnungen/EG links (72,5 qm)',
    'Haus Müllerstraße 3/Allgemein/Rechnungen 2025',
    'Zweites Objekt/Anhänge & Sonstiges',
]


def echtes_pdf(text: str = 'Testbeleg') -> bytes:
    """Ein gueltiges einseitiges PDF, erzeugt mit reportlab.

    reportlab steht in requirements.txt, die Anwendung baut ihre Abrechnungen
    damit. Das PDF hier ist damit aus derselben Quelle wie die echten.
    """
    from reportlab.pdfgen import canvas

    puffer = io.BytesIO()
    blatt = canvas.Canvas(puffer)
    blatt.drawString(72, 720, text)
    blatt.save()
    return puffer.getvalue()


def echtes_jpg(groesse: tuple[int, int] = (8, 8)) -> bytes:
    """Ein gueltiges JPEG.

    Pillow ist keine eigene Zeile in requirements.txt, kommt aber als harte
    Abhaengigkeit von reportlab (>=9.0.0) mit und ist deshalb da.
    """
    from PIL import Image

    puffer = io.BytesIO()
    Image.new('RGB', groesse, (200, 120, 40)).save(puffer, format='JPEG')
    return puffer.getvalue()


def ist_pdf(daten: bytes) -> bool:
    return daten.startswith(b'%PDF-') and daten.rstrip().endswith(b'%%EOF')


def ist_jpg(daten: bytes) -> bool:
    # SOI am Anfang, EOI am Ende. Die Marker sind das, was ein Betrachter sucht.
    return daten.startswith(b'\xff\xd8\xff') and daten.endswith(b'\xff\xd9')


def pruefsumme(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def belege_anlegen(wurzel: Path) -> dict[str, str]:
    """Legt jeden Namen in jedem Ordner an. Gibt Pfad -> SHA256 zurueck.

    Ueberspringt still, was das Dateisystem nicht hergibt (zu lang, verbotenes
    Zeichen). Die Karte will messen, was durchkommt, nicht am Anlegen
    scheitern; welche Namen tatsaechlich entstanden sind, steht im Rueckgabewert.
    """
    erwartet: dict[str, str] = {}
    for nummer, ordner in enumerate(BOESE_ORDNER):
        ziel = wurzel / ordner
        ziel.mkdir(parents=True, exist_ok=True)
        for name, _grund in BOESE_NAMEN:
            if name.lower().endswith('.jpg'):
                daten = echtes_jpg((8 + nummer, 8))
            else:
                daten = echtes_pdf(f'{ordner} / {name[:40]}')
            pfad = ziel / name
            try:
                pfad.write_bytes(daten)
            except OSError:
                continue
            erwartet[pfad.relative_to(wurzel).as_posix()] = pruefsumme(daten)
    return erwartet
