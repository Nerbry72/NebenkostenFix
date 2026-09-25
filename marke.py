"""Die Marke NebenkostenFix an einer Stelle (NK-155, D-94, D-95).

Name, alter Name, Abbild und die Geometrie des Zeichens stehen nur hier.
Oberfläche, Anmeldeseiten, PDF-Fuß, Fenster, Installer und die erzeugten
Icons (``scripts/marke_bilder.py``) lesen sie von hier -- ein Wächter
(``tests/test_marke.py``) verhindert, dass der Name woanders auseinanderläuft.

Das Zeichen: ein Haus mit Haken auf einer abgerundeten Fläche in der
Primärfarbe der Oberfläche. Haus = Immobilie, Haken = die Abrechnung stimmt.
Es ist auf einem Raster von 64 Einheiten gezeichnet und wird als SVG
(Oberfläche, Favicon) und als Bitmap (Windows-Icon, Installer) ausgegeben --
beide aus denselben Punkten unten.
"""

from __future__ import annotations

PRODUKT = 'NebenkostenFix'
# Ordnername älterer Installationen (bis 0.9, D-95): vorhandene Daten bleiben
# dort, neue Installationen nehmen PRODUKT.
ALTER_NAME = 'Nebenkostenabrechnung'
ABBILD = 'ghcr.io/nerbry72/nebenkostenfix'

FARBE = '#4F46E5'          # --primary der Oberfläche
FARBE_DUNKEL = '#4338CA'   # --primary-hover
WEISS = '#FFFFFF'

# --- Geometrie auf 64 x 64 ------------------------------------------------------

RASTER = 64
ECKENRADIUS = 14
# Haus: Dach mit Traufe, Körper. Im Uhrzeigersinn ab dem First.
HAUS = [(32, 12), (53, 31), (47, 31), (47, 52), (17, 52), (17, 31), (11, 31)]
# Haken im Haus, in der Primärfarbe (als Aussparung gelesen).
HAKEN = [(24, 41), (30, 47), (41, 35)]
HAKEN_BREITE = 5.2


def zeichen_svg(breite: int | None = None, titel: bool = True) -> str:
    """Das Zeichen als eigenständiges SVG."""
    punkte = ' '.join(f'{x},{y}' for x, y in HAUS)
    haken = ' '.join(f'{x},{y}' for x, y in HAKEN)
    groesse = f' width="{breite}" height="{breite}"' if breite else ''
    beschriftung = f'<title>{PRODUKT}</title>' if titel else ''
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {RASTER} {RASTER}"{groesse} '
        f'role="img" aria-label="{PRODUKT}">{beschriftung}'
        f'<rect width="{RASTER}" height="{RASTER}" rx="{ECKENRADIUS}" fill="{FARBE}"/>'
        f'<polygon points="{punkte}" fill="{WEISS}" stroke="{WEISS}" stroke-width="2" '
        f'stroke-linejoin="round"/>'
        f'<polyline points="{haken}" fill="none" stroke="{FARBE}" stroke-width="{HAKEN_BREITE}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>')


def zeichen_bild(kante: int):  # pragma: no cover - nur im Erzeuger
    """Das Zeichen als Pillow-Bild (RGBA), für Icons und Installerbilder.

    Vierfach überabgetastet und verkleinert, damit Kanten und Haken auch in
    16 px sauber bleiben.
    """
    from PIL import Image, ImageDraw

    faktor = 4
    gross = kante * faktor
    skala = gross / RASTER
    bild = Image.new('RGBA', (gross, gross), (0, 0, 0, 0))
    stift = ImageDraw.Draw(bild)
    stift.rounded_rectangle([0, 0, gross - 1, gross - 1], radius=ECKENRADIUS * skala, fill=FARBE)
    stift.polygon([(x * skala, y * skala) for x, y in HAUS], fill=WEISS)
    breite = max(1, round(HAKEN_BREITE * skala))
    punkte = [(x * skala, y * skala) for x, y in HAKEN]
    stift.line(punkte, fill=FARBE, width=breite, joint='curve')
    for x, y in (punkte[0], punkte[-1]):
        r = breite / 2
        stift.ellipse([x - r, y - r, x + r, y + r], fill=FARBE)
    return bild.resize((kante, kante), Image.LANCZOS)
