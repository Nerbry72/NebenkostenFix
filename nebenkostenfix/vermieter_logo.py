"""Das Logo des Vermieters auf dem Deckblatt (NK-155, optional).

Eine Datei im Datenordner (``vermieter-logo.png`` bzw. ``.jpg``), keine
Datenbankzeile: sie gehört zum Bestand wie die Belege und reist mit der
Sicherung und dem Umzugspaket (NK-164). Erlaubt sind PNG und JPEG, erkannt
am Inhalt (NK-129), höchstens 2 MB und 4000 Pixel Kantenlänge -- ein Logo,
kein Foto. Das Deckblatt setzt es oben rechts ein, höchstens 45 × 18 mm,
im Seitenverhältnis.
"""

from __future__ import annotations

import os
from pathlib import Path

from nebenkostenfix import datenordner
from nebenkostenfix import uploads
from nebenkostenfix.validation import EingabeFehler

STAMM = 'vermieter-logo'
ENDUNGEN = ('png', 'jpg')
MAX_BYTES = 2 * 1024 * 1024
MAX_KANTE = 4000


def pfad(ordner: Path | None = None) -> Path | None:
    """Das hinterlegte Logo, oder None."""
    basis = ordner or datenordner.datenordner()
    for endung in ENDUNGEN:
        kandidat = basis / f'{STAMM}.{endung}'
        if kandidat.is_file():
            return kandidat
    return None


def speichern(datei, ordner: Path | None = None) -> Path:
    """Prüft und legt ein hochgeladenes Logo ab (ersetzt ein altes)."""
    endung = uploads.pruefe(datei, 'logo')
    if endung not in ENDUNGEN:
        raise EingabeFehler('Als Logo gehen PNG und JPEG.', 'logo')
    inhalt = datei.read(MAX_BYTES + 1)
    if len(inhalt) > MAX_BYTES:
        raise EingabeFehler('Das Logo ist größer als 2 MB. Bitte eine kleinere Datei wählen.',
                            'logo')
    breite, hoehe = _masse(inhalt)
    if max(breite, hoehe) > MAX_KANTE:
        raise EingabeFehler(f'Das Logo ist größer als {MAX_KANTE} Pixel. Bitte verkleinern.',
                            'logo')
    basis = ordner or datenordner.datenordner()
    basis.mkdir(parents=True, exist_ok=True)
    ziel = basis / f'{STAMM}.{endung}'
    temp = ziel.with_name(ziel.name + '.neu')
    temp.write_bytes(inhalt)
    os.replace(temp, ziel)
    for andere in ENDUNGEN:
        if andere != endung:
            (basis / f'{STAMM}.{andere}').unlink(missing_ok=True)
    return ziel


def loeschen(ordner: Path | None = None) -> bool:
    gefunden = pfad(ordner)
    if gefunden is None:
        return False
    gefunden.unlink()
    return True


def _masse(inhalt: bytes) -> tuple[int, int]:
    """Breite und Höhe; ein Bild, das sich nicht öffnen lässt, ist keins."""
    import io

    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(inhalt)) as bild:
            bild.verify()
            return bild.size
    except (UnidentifiedImageError, OSError, SyntaxError) as fehler:
        raise EingabeFehler('Die Datei lässt sich nicht als Bild öffnen.', 'logo') from fehler


def deckblatt_bild(max_breite_pt: float = 127.0, max_hoehe_pt: float = 51.0):
    """Das Logo als reportlab-Flowable (45 × 18 mm), oder None."""
    datei = pfad()
    if datei is None:
        return None
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    try:
        breite, hoehe = ImageReader(str(datei)).getSize()
    except (OSError, ValueError):
        return None
    faktor = min(max_breite_pt / breite, max_hoehe_pt / hoehe, 1.0)
    bild = Image(str(datei), width=breite * faktor, height=hoehe * faktor)
    bild.hAlign = 'RIGHT'
    return bild
