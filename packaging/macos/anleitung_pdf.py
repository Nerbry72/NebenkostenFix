"""Setzt die Anleitung für den Mac als PDF für das DMG (#44).

    python packaging/macos/anleitung_pdf.py docs/handbuch/mac-installation.md ZIEL.pdf

Eine Quelle für GitHub und DMG: Gelesen wird nur der Teil von Markdown, den
die Anleitung nutzt. Das sind Überschriften, Absätze, nummerierte Listen und
Punkte mit eingerückten Folgezeilen, Bilder, Links, fett und `code`. Gesetzt wird
mit reportlab, das die App ohnehin mitbringt. Die Schrift ist Helvetica.
Das einzige Zeichen der Anleitung außerhalb von Windows-1252, der Pfeil
„→“, kommt aus der Symbol-Schrift.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

from nebenkostenfix import marke  # noqa: E402

BILD = re.compile(r'^!\[[^\]]+\]\(([^)]+)\)$')
NUMMER = re.compile(r'^\d+\. (.*)$')
PUNKT = re.compile(r'^- (.*)$')
BILD_DPI = 144                  # Retina-Bildschirmfotos: 2 Pixel je Punkt
BILD_MASSSTAB = 0.75            # in Originalgröße drängten die Dialoge den Text auf die nächste Seite


def inline(text: str) -> str:
    """Markdown einer Zeile als reportlab-Markup."""
    text = html.escape(text, quote=False)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font face="Courier">\1</font>', text)
    text = re.sub(r'\[([^\]]+)\]\((https://[^)\s]+)\)',
                  rf'<a href="\2" color="{marke.FARBE}"><u>\1</u></a>', text)
    return text.replace('→', '<font face="Symbol">→</font>')


def bloecke(text: str) -> list[tuple[str, object]]:
    """Zerlegt die Anleitung in (Art, Inhalt): h1, h2, h3, absatz, nummer,
    punkt, bild. Listen bringen die Liste ihrer Einträge mit."""
    ergebnis: list[tuple[str, object]] = []
    zeilen = text.splitlines()
    i = 0
    while i < len(zeilen):
        zeile = zeilen[i].rstrip()
        if not zeile:
            i += 1
            continue
        if zeile.startswith('#'):
            tiefe, _, titel = zeile.partition(' ')
            ergebnis.append((f'h{len(tiefe)}', titel.strip()))
            i += 1
            continue
        treffer = BILD.match(zeile)
        if treffer:
            ergebnis.append(('bild', treffer.group(1)))
            i += 1
            continue
        for art, muster in (('nummer', NUMMER), ('punkt', PUNKT)):
            if muster.match(zeile):
                eintraege: list[str] = []
                while i < len(zeilen) and zeilen[i].strip():
                    treffer = muster.match(zeilen[i])
                    if treffer:
                        eintraege.append(treffer.group(1).strip())
                    else:                           # eingerückte Folgezeile
                        eintraege[-1] += ' ' + zeilen[i].strip()
                    i += 1
                ergebnis.append((art, eintraege))
                break
        else:
            absatz = []
            # Wie in CommonMark unterbricht eine Liste den Absatz.
            while i < len(zeilen) and zeilen[i].strip() and not zeilen[i].startswith('#') \
                    and not BILD.match(zeilen[i].strip()) \
                    and not (absatz and (NUMMER.match(zeilen[i]) or PUNKT.match(zeilen[i]))):
                absatz.append(zeilen[i].strip())
                i += 1
            ergebnis.append(('absatz', ' '.join(absatz)))
    return ergebnis


def bauen(quelle: Path, ziel: Path, komprimiert: bool = True) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem,
                                    Paragraph, SimpleDocTemplate, Spacer)

    farbe = colors.HexColor(marke.FARBE)
    grund = ParagraphStyle('grund', fontName='Helvetica', fontSize=11, leading=15.5,
                           alignment=TA_LEFT, spaceAfter=7)
    stile = {
        'h1': ParagraphStyle('h1', parent=grund, fontName='Helvetica-Bold', fontSize=20,
                             leading=24, textColor=farbe, spaceAfter=12),
        'h2': ParagraphStyle('h2', parent=grund, fontName='Helvetica-Bold', fontSize=14,
                             leading=18, spaceBefore=12, spaceAfter=6),
        'h3': ParagraphStyle('h3', parent=grund, fontName='Helvetica-Bold', fontSize=12,
                             leading=16, spaceBefore=8),
    }
    dokument = SimpleDocTemplate(
        str(ziel), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm, title=f'{marke.PRODUKT} auf dem Mac installieren',
        author=marke.PRODUKT, invariant=1, pageCompression=1 if komprimiert else 0)

    inhalt = []
    for art, wert in bloecke(quelle.read_text(encoding='utf-8')):
        if art in stile:
            absatz = Paragraph(inline(wert), stile[art])
            # Eine Überschrift steht nie allein unten auf der Seite.
            inhalt.append(KeepTogether([absatz, Spacer(0, 0)]) if art == 'h1' else absatz)
            if art == 'h2':
                absatz.keepWithNext = True
        elif art == 'absatz':
            inhalt.append(Paragraph(inline(wert), grund))
        elif art in ('nummer', 'punkt'):
            punkte = [ListItem(Paragraph(inline(e), grund), leftIndent=16) for e in wert]
            inhalt.append(ListFlowable(
                punkte, bulletType='1' if art == 'nummer' else 'bullet',
                start='1' if art == 'nummer' else '•', bulletFormat='%s.' if art == 'nummer'
                else None, leftIndent=16,
                bulletFontName='Helvetica', bulletFontSize=11))
        elif art == 'bild':
            pfad = (quelle.parent / wert).resolve()
            bild = Image(str(pfad))
            breite = bild.imageWidth * 72 / BILD_DPI * BILD_MASSSTAB
            hoehe = bild.imageHeight * 72 / BILD_DPI * BILD_MASSSTAB
            platz = dokument.width
            if breite > platz:
                breite, hoehe = platz, hoehe * platz / breite
            bild.drawWidth, bild.drawHeight = breite, hoehe
            bild.hAlign = 'LEFT'
            # Der Schritt davor bleibt bei seinem Bild, nie allein unten auf der Seite.
            davor = [inhalt.pop()] if inhalt and isinstance(inhalt[-1], Paragraph) else []
            inhalt.append(KeepTogether(davor + [bild, Spacer(0, 8)]))
    dokument.build(inhalt)


def main(argv: list[str] | None = None) -> int:
    argumente = sys.argv[1:] if argv is None else argv
    if len(argumente) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    bauen(Path(argumente[0]), Path(argumente[1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
