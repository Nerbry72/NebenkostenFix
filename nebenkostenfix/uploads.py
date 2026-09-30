"""Uploads pruefen und Dateien sicher ausliefern (NK-129, F-55, F-59, E-6 → D-88).

Bis NK-129 nahm die Ablage jede Datei an und `/api/files` lieferte sie
inline unter der Adresse der Anwendung aus -- den Typ riet der Browser aus
dem Namen. Eine hochgeladene HTML- oder SVG-Datei lief damit mit der Sitzung
des Vermieters (F-55), und `/api/files` nahm einen frei waehlbaren Pfad an
(F-59).

Jetzt:

Hochladen
    Erlaubt sind PDF, JPEG, PNG, WebP und HEIC/HEIF -- erkannt an den ersten
    Bytes der Datei, nie am Namen (D-88). Die Endung der abgelegten Datei
    kommt aus dem erkannten Typ. Alles andere lehnt die Ablage mit einer
    deutschen 400 ab, bevor etwas geschrieben ist.

Ausliefern
    Nur ueber eine Kennung (`/api/dateien/<art>/<id>`), nie ueber einen Pfad
    aus der Anfrage. Der Pfad kommt aus der Datenbank, wird mit `realpath`
    aufgeloest und muss im Belegordner liegen. Der Content-Type kommt wieder
    aus den ersten Bytes; `nosniff` verbietet dem Browser das Raten.

    - Bilder (JPEG, PNG, WebP): inline mit `CSP: sandbox` -- selbst ein
      Bild, das ein Browser falsch deutete, haette keinen Zugriff auf die
      Anwendung.
    - PDF: inline mit festem `application/pdf`. Keine Sandbox, weil Chrome
      und Firefox ihre PDF-Anzeige in einem Sandbox-Dokument abschalten; der
      PDF-Betrachter laeuft ohnehin getrennt von der Seite und kann ihre
      Adresse nicht skripten. `frame-ancestors 'self'` bleibt.
    - HEIC und alles Unbekannte (Altbestand): nur als Download.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import send_file

from nebenkostenfix.validation import EingabeFehler

# Endung -> MIME-Typ. Die Reihenfolge ist die der Fehlermeldung.
ERLAUBT = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'png': 'image/png',
    'webp': 'image/webp',
    'heic': 'image/heic',
}
INLINE = frozenset({'pdf', 'jpg', 'png', 'webp'})
_HEIF_MARKEN = frozenset({b'heic', b'heix', b'hevc', b'hevx', b'heim',
                          b'heis', b'hevm', b'hevs', b'mif1', b'msf1'})
KOPF_BYTES = 32

MELDUNG = ('Dieser Dateityp ist nicht erlaubt. Erlaubt sind PDF, JPEG, PNG, '
           'WebP und HEIC. Erkannt wird der Typ am Inhalt, nicht am Namen.')

CSP_BILD = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
CSP_PDF = "frame-ancestors 'self'"
CSP_DOWNLOAD = "sandbox; default-src 'none'"


def erkenne(kopf: bytes) -> str | None:
    """Der Typ nach den ersten Bytes, als Endung; None, wenn unbekannt."""
    if kopf.startswith(b'%PDF-'):
        return 'pdf'
    if kopf.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if kopf.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if kopf[:4] == b'RIFF' and kopf[8:12] == b'WEBP':
        return 'webp'
    if kopf[4:8] == b'ftyp' and kopf[8:12] in _HEIF_MARKEN:
        return 'heic'
    return None


def pruefe(datei, feld: str = 'datei') -> str:
    """Prueft einen Upload (werkzeug FileStorage oder etwas mit ``stream``
    bzw. ``content``) und liefert die Endung nach Inhalt.

    Der Lesezeiger steht danach wieder am Anfang: gespeichert wird die ganze
    Datei, nicht der Rest hinter dem Kopf.
    """
    kopf = _kopf(datei)
    endung = erkenne(kopf)
    if endung is None:
        raise EingabeFehler(MELDUNG, feld)
    return endung


# --- Tabellen für den Import (NK-161) -------------------------------------------
#
# Eine Tabelle ist kein Beleg: sie wird gelesen und verworfen, nie im
# Belegordner abgelegt oder ausgeliefert. Die Positivliste der Belege bleibt
# deshalb, wie sie ist; hier gilt eine eigene, ebenfalls nach Inhalt.

TABELLE_MAX_ENTPACKT = 64 * 1024 * 1024
TABELLE_MAX_EINTRAEGE = 2000
TABELLE_MELDUNG = ('Diese Datei ist keine Tabelle, die sich lesen lässt. Erlaubt sind '
                   'Excel-Arbeitsmappen (.xlsx) und CSV-Dateien.')


def pruefe_tabelle(inhalt: bytes) -> str:
    """'xlsx' oder 'csv' nach Inhalt; sonst EingabeFehler.

    XLSX ist ein ZIP: geprüft werden die Pflichtteile einer Arbeitsmappe und
    die entpackte Größe (gegen ZIP-Bomben), bevor openpyxl es öffnet. Das
    alte Excel-Format (.xls) und OpenDocument werden mit Hinweis abgelehnt.
    """
    import io
    import zipfile

    if inhalt.startswith(b'\xd0\xcf\x11\xe0'):
        raise EingabeFehler('Das ist das alte Excel-Format (.xls). Speichern Sie die Datei in '
                            'Excel unter „Excel-Arbeitsmappe (.xlsx)“ und wählen Sie sie erneut.',
                            'datei')
    if inhalt.startswith(b'PK\x03\x04'):
        try:
            with zipfile.ZipFile(io.BytesIO(inhalt)) as mappe:
                eintraege = mappe.infolist()
                namen = {e.filename for e in eintraege}
        except zipfile.BadZipFile as fehler:
            raise EingabeFehler(TABELLE_MELDUNG, 'datei') from fehler
        if 'mimetype' in namen and 'content.xml' in namen:
            raise EingabeFehler('Das ist eine OpenDocument-Tabelle (.ods). Speichern Sie sie als '
                                '.xlsx oder .csv und wählen Sie sie erneut.', 'datei')
        if '[Content_Types].xml' not in namen or 'xl/workbook.xml' not in namen:
            raise EingabeFehler(TABELLE_MELDUNG, 'datei')
        if len(eintraege) > TABELLE_MAX_EINTRAEGE or \
                sum(e.file_size for e in eintraege) > TABELLE_MAX_ENTPACKT:
            raise EingabeFehler('Die Excel-Datei ist entpackt zu groß. Bitte teilen Sie sie auf.',
                                'datei')
        return 'xlsx'
    probe = inhalt[:65536]
    if not probe.strip() or b'\x00' in probe or erkenne(inhalt[:KOPF_BYTES]) is not None:
        raise EingabeFehler(TABELLE_MELDUNG, 'datei')
    return 'csv'


def _kopf(datei) -> bytes:
    inhalt = getattr(datei, 'content', None)
    if isinstance(inhalt, (bytes, bytearray)):
        return bytes(inhalt[:KOPF_BYTES])
    strom = getattr(datei, 'stream', None) or datei
    try:
        position = strom.tell()
    except (AttributeError, OSError):
        position = 0
    kopf = strom.read(KOPF_BYTES) or b''
    try:
        strom.seek(position)
    except (AttributeError, OSError) as fehler:
        raise EingabeFehler('Die Datei ließ sich nicht lesen.', 'datei') from fehler
    return kopf


def pfad_aufloesen(wurzel: str | os.PathLike, gespeichert: str | None) -> Path | None:
    """Der Pfad einer abgelegten Datei, oder None.

    ``gespeichert`` kommt aus der Datenbank: relativ zur Wurzel, beim
    Altbestand auch absolut. Aufgeloest wird mit ``realpath`` -- ``..`` und
    Verknuepfungen fuehren nicht aus dem Belegordner heraus. Was ausserhalb
    liegt oder fehlt, ist None; der Aufrufer behandelt beides wie "fehlt".
    """
    if not gespeichert:
        return None
    basis = os.path.realpath(wurzel)
    kandidat = gespeichert if os.path.isabs(gespeichert) \
        else os.path.join(basis, gespeichert)
    echt = os.path.realpath(kandidat)
    try:
        ausserhalb = os.path.commonpath([basis, echt]) != basis
    except ValueError:
        ausserhalb = True  # Windows: anderes Laufwerk
    if ausserhalb or echt == basis:
        return None
    if not os.path.isfile(echt):
        return None
    return Path(echt)


def ausliefern(pfad: Path, anzeigename: str | None = None):
    """Die Antwort fuer eine abgelegte Datei, mit festem Typ und Koepfen."""
    with open(pfad, 'rb') as datei:
        endung = erkenne(datei.read(KOPF_BYTES))
    name = anzeigename or pfad.name
    if endung in INLINE:
        antwort = send_file(pfad, mimetype=ERLAUBT[endung], as_attachment=False,
                            download_name=name, conditional=True)
        antwort.headers['Content-Security-Policy'] = \
            CSP_PDF if endung == 'pdf' else CSP_BILD
    else:
        mime = ERLAUBT.get(endung, 'application/octet-stream')
        antwort = send_file(pfad, mimetype=mime, as_attachment=True,
                            download_name=name, conditional=True)
        antwort.headers['Content-Security-Policy'] = CSP_DOWNLOAD
    antwort.headers['X-Content-Type-Options'] = 'nosniff'
    antwort.headers['Cache-Control'] = 'private, no-store'
    return antwort
