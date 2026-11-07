"""Baut das gestaltete DMG der Mac-App (#44) mit dmgbuild.

    python packaging/macos/dmg.py --app dist/NebenkostenFix.app \\
        --anleitung dist/Installationsanleitung.pdf --ziel dist/NebenkostenFix-….dmg

Im Fenster des DMG liegen die App links und die Verknüpfung „Programme“
rechts, dazwischen zeigt ein Pfeil im Hintergrund die Richtung. Unten in der
Mitte liegt die Anleitung als PDF. dmgbuild schreibt die ``.DS_Store``
selbst und braucht dafür weder Finder noch AppleScript. Ab 1.6.7 zeigt Finder
auch unter macOS 26.2 den Hintergrund. dmgbuild kommt nur im Workflow dazu,
nicht in die App.

Den Hintergrund (``dmg-hintergrund.png`` und ``@2x``) schreibt
``scripts/marke_bilder.py`` aus ``hintergrund()``. Positionen und Bild
stehen deshalb an einer Stelle.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

from nebenkostenfix import marke  # noqa: E402

ANLEITUNG_NAME = 'Installationsanleitung.pdf'
FENSTER = (660, 400)            # Inhalt des Fensters in Punkt, ohne Titelleiste
# window_rect meint das ganze Fenster: Die Titelleiste kommt dazu (macOS 26:
# 32 Punkt, macOS 15: 28). Das Bild reicht deshalb weiter als der Inhalt.
TITELLEISTE = 32
BILD = (660, 440)               # @2x hat die doppelte Größe
SYMBOLGROESSE = 104
POSITIONEN = {                  # Mitte des Symbols, von oben links
    'NebenkostenFix.app': (165, 170),
    'Programme': (495, 170),
    ANLEITUNG_NAME: (330, 275),
}
HINTERGRUND = HIER / 'dmg-hintergrund.png'
SYMBOL = HIER / 'nebenkostenfix.icns'
SCHRIFT = WURZEL / 'static' / 'vendor' / 'fonts' / 'geist' / 'geist-latin.woff2'
VERSUCHE = 3


def einstellungen(app: Path, anleitung: Path) -> dict:
    """Die Einstellungen für ``dmgbuild.build_dmg``."""
    if anleitung.name != ANLEITUNG_NAME:
        raise ValueError(f'Die Anleitung muss {ANLEITUNG_NAME} heißen, nicht {anleitung.name}.')
    return {
        'format': 'UDZO',
        'files': [str(app), str(anleitung)],
        'symlinks': {'Programme': '/Applications'},
        'icon': str(SYMBOL),
        'background': str(HINTERGRUND),
        'window_rect': ((200, 120), (FENSTER[0], FENSTER[1] + TITELLEISTE)),
        'default_view': 'icon-view',
        'show_toolbar': False,
        'show_sidebar': False,
        'show_status_bar': False,
        'show_pathbar': False,
        'show_tab_view': False,
        'arrange_by': None,
        'icon_size': SYMBOLGROESSE,
        'text_size': 13,
        'icon_locations': dict(POSITIONEN),
        # Kein hide_extensions: Es setzt com.apple.FinderInfo am Bundle, und
        # codesign --strict nennt die App dann „detritus“. Finder zeigt die
        # Endung .app ohnehin nicht.
    }


def _schrift(groesse: int, gewicht: str):
    from PIL import ImageFont
    schrift = ImageFont.truetype(str(SCHRIFT), groesse)
    try:
        schrift.set_variation_by_name(gewicht)
    except (OSError, ValueError):   # keine variable Schrift: dann eben Regular
        pass
    return schrift


def hintergrund(skala: int = 1):
    """Heller Verlauf in der Markenfarbe, oben zwei Zeilen Text, dazwischen
    der Pfeil von der App zu „Programme“. Unter den Symbolen bleibt der
    Verlauf frei, Finder zeichnet dort Symbol und Beschriftung.

    Gezeichnet wird vierfach und dann verkleinert: Pillow glättet die
    Kanten von Linien und Vielecken nicht."""
    from PIL import Image

    groesse = (BILD[0] * skala, BILD[1] * skala)
    return _zeichnen(4).resize(groesse, Image.LANCZOS)


def _zeichnen(skala: int):
    from PIL import Image, ImageDraw

    breite, hoehe = BILD[0] * skala, BILD[1] * skala
    bild = Image.new('RGB', (breite, hoehe), marke.WEISS)
    oben = (238, 242, 255)          # Primärtönung, sehr hell, wie im Installer unter Windows
    stift = ImageDraw.Draw(bild)
    for y in range(hoehe):
        anteil = y / max(1, hoehe - 1)
        stift.line([(0, y), (breite, y)],
                   fill=tuple(round(o + (255 - o) * anteil) for o in oben))

    mitte = breite // 2
    stift.text((mitte, 40 * skala), f'Ziehen Sie {marke.PRODUKT} auf „Programme“.',
               font=_schrift(22 * skala, 'SemiBold'), fill='#111827', anchor='mm')
    stift.text((mitte, 70 * skala), 'Beim ersten Start hilft die Installationsanleitung.',
               font=_schrift(15 * skala, 'Regular'), fill='#4B5563', anchor='mm')

    (ax, ay), (bx, _) = POSITIONEN['NebenkostenFix.app'], POSITIONEN['Programme']
    rand = SYMBOLGROESSE // 2 + 16
    von, bis, y = (ax + rand) * skala, (bx - rand) * skala, ay * skala
    spitze = 14 * skala
    stift.line([(von, y), (bis - spitze, y)], fill=marke.FARBE, width=6 * skala)
    stift.polygon([(bis, y), (bis - spitze - 4 * skala, y - spitze),
                   (bis - spitze - 4 * skala, y + spitze)], fill=marke.FARBE)
    return bild


def hintergrund_schreiben(ordner: Path = HIER) -> None:
    hintergrund(1).save(ordner / 'dmg-hintergrund.png', optimize=True, dpi=(72, 72))
    hintergrund(2).save(ordner / 'dmg-hintergrund@2x.png', optimize=True, dpi=(144, 144))


def bauen(ziel: Path, app: Path, anleitung: Path) -> None:
    """hdiutil meldet auf den Runnern gelegentlich „Resource busy“
    (runner-images#7522). dmgbuild versucht das Aushängen selbst mehrmals
    (``detach_retries``), hier kommt der ganze Bau noch einmal dazu. Eine
    halbe Datei vom Fehlversuch zählt nicht."""
    import dmgbuild

    for versuch in range(1, VERSUCHE + 1):
        try:
            dmgbuild.build_dmg(str(ziel), marke.PRODUKT,
                               settings=einstellungen(app, anleitung), detach_retries=12)
            return
        except Exception:
            ziel.unlink(missing_ok=True)
            if versuch == VERSUCHE:
                raise
            time.sleep(10 * versuch)


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument('--app', type=Path, required=True)
    zerleger.add_argument('--anleitung', type=Path, required=True)
    zerleger.add_argument('--ziel', type=Path, required=True)
    argumente = zerleger.parse_args(argv)
    bauen(argumente.ziel, argumente.app, argumente.anleitung)
    return 0


if __name__ == '__main__':
    sys.exit(main())
