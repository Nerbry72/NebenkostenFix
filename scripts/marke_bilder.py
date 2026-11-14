"""Erzeugt alle Bilddateien der Marke aus ``marke.py`` (NK-155).

    python scripts/marke_bilder.py

Schreibt:
  static/marke/zeichen.svg            Zeichen für Oberfläche und Anmeldeseiten
  static/marke/favicon.svg            Favicon (SVG, moderne Browser)
  static/marke/favicon.ico            Favicon 16/32/48 (ältere Browser)
  static/marke/zeichen-180.png        Symbol für „Zum Home-Bildschirm“
  packaging/windows/nebenkostenfix.ico  Exe, Fenster, Installer: 16 … 256 px
  packaging/windows/installer-gross*.bmp / installer-klein*.bmp
                                      Bilder des Installationsassistenten (100 % und 200 %)
  packaging/macos/nebenkostenfix.icns   Bundle der macOS-App: 32 … 1024 px (#44)
  packaging/macos/dmg-hintergrund*.png  Hintergrund des DMG-Fensters (1× und 2×)

Die Dateien liegen im Repository; neu erzeugt wird nur, wenn sich das
Zeichen ändert. ``tests/test_marke.py`` prüft, dass die SVGs zum Code passen.
"""

from __future__ import annotations

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL))

from nebenkostenfix import marke  # noqa: E402

ICON_GROESSEN = [16, 24, 32, 48, 64, 128, 256]


def _assistentenbild(breite: int, hoehe: int, zeichen: int):
    """Heller Verlauf in der Markenfarbe, Zeichen mittig im oberen Drittel."""
    from PIL import Image

    bild = Image.new('RGB', (breite, hoehe), '#FFFFFF')
    oben = (238, 242, 255)          # Primärtönung, sehr hell
    for y in range(hoehe):
        anteil = y / max(1, hoehe - 1)
        farbe = tuple(round(o + (255 - o) * anteil) for o in oben)
        for x in range(breite):
            bild.putpixel((x, y), farbe)
    symbol = marke.zeichen_bild(zeichen)
    bild.paste(symbol, ((breite - zeichen) // 2, hoehe // 4 - zeichen // 2 + zeichen // 4),
               symbol)
    return bild


def _dmg():
    """packaging/macos/dmg.py: Dort stehen Fenster und Symbolpositionen."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('dmg', WURZEL / 'packaging' / 'macos' / 'dmg.py')
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def main() -> int:
    statisch = WURZEL / 'static' / 'marke'
    statisch.mkdir(parents=True, exist_ok=True)
    (statisch / 'zeichen.svg').write_text(marke.zeichen_svg() + '\n', encoding='utf-8')
    (statisch / 'favicon.svg').write_text(marke.zeichen_svg(titel=False) + '\n', encoding='utf-8')

    gross = marke.zeichen_bild(256)
    # Jede Größe eigens gezeichnet, nicht aus 256 px verkleinert.
    gross.save(statisch / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)],
               append_images=[marke.zeichen_bild(g) for g in (16, 32, 48)])
    marke.zeichen_bild(180).save(statisch / 'zeichen-180.png')

    windows = WURZEL / 'packaging' / 'windows'
    gross.save(windows / 'nebenkostenfix.ico', sizes=[(g, g) for g in ICON_GROESSEN],
               append_images=[marke.zeichen_bild(g) for g in ICON_GROESSEN])
    _assistentenbild(164, 314, 96).save(windows / 'installer-gross.bmp')
    _assistentenbild(328, 628, 192).save(windows / 'installer-gross-2x.bmp')
    from PIL import Image
    for name, kante in (('installer-klein.bmp', 55), ('installer-klein-2x.bmp', 110)):
        grund = Image.new('RGB', (kante, kante), '#FFFFFF')
        symbol = marke.zeichen_bild(kante)
        grund.paste(symbol, (0, 0), symbol)
        grund.save(windows / name)
    # Pillow schreibt ICNS immer in 32 bis 1024 px, verkleinert aus der Vorlage.
    macos = WURZEL / 'packaging' / 'macos'
    macos.mkdir(parents=True, exist_ok=True)
    marke.zeichen_bild(1024).save(macos / 'nebenkostenfix.icns')
    _dmg().hintergrund_schreiben(macos)
    print('Marke erzeugt:', statisch, windows, macos)
    return 0


if __name__ == '__main__':
    sys.exit(main())
