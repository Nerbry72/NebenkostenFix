from dataclasses import dataclass, replace
from io import BytesIO
# Bandit-Ausnahme: maskiert Text fuer reportlab, parst kein XML
from xml.sax.saxutils import escape  # nosec B406
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus import KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
from decimal import Decimal
from nebenkostenfix.pdf_cover_page import (
    build_cover_page_elements, COLOR_BORDER, COLOR_MUTED,
)
from nebenkostenfix.anschreiben import saetze as anschreiben_saetze
from nebenkostenfix.girocode_generator import (
    _format_iban_display, build_girocode_elements, vermieter_art, vermieter_ausweis)
from nebenkostenfix.geld import NULL, text as geld_text
from nebenkostenfix import pdf_stil
from nebenkostenfix import pdf_uebersicht
from nebenkostenfix import pdf_layout
from nebenkostenfix.rechenkern import VERMIETERANTEIL_VORSATZ
from nebenkostenfix.zeitraum import HINWEIS_TAGESKONVENTION
from nebenkostenfix import marke
from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION, REGEL_VERSION


#: Die Blöcke der Abrechnungs-PDF in ihrer Standardreihenfolge, festgelegt
#: in ``pdf_layout.BLOECKE``. ``generate()`` geht die eingeschalteten
#: Blöcke des Layouts durch; je ID liefert ``PDFGenerator._block_<id>``
#: die Flowables. Der GiroCode ist ein Unterblock: im Standard von
#: ``zahlung`` (Zahlungssatz und Kasten bleiben zusammen auf einer Seite),
#: wahlweise auf dem Deckblatt oder aus.
#: ``verbrauchsnachweise`` gibt es nur in der ausführlichen Fassung.
STANDARDLAYOUT = pdf_layout.STANDARDLAYOUT


@dataclass(frozen=True)
class _Inhalt:
    """Was ``generate()`` bekommt, einmal für alle Blöcke zusammengefasst."""

    line_items: list
    total_amount: Decimal
    prepaid_amount: Decimal
    balance: Decimal
    co2_ausweis: dict | None
    landlord_share: dict | None
    anschreiben: str | None
    vorbehalt: str | None
    ausweis_35a: dict | None
    vermieter: str
    vermieter_adresse: str
    #: Wo der GiroCode steht: ``zahlung``, ``deckblatt`` oder ``aus``.
    girocode: str = pdf_layout.GIROCODE_STANDARD
    #: Die eingeschalteten Blöcke in der Folge des Blatts; ein Block, der auf
    #: andere verweist, liest hier, wo sie stehen.
    folge: tuple = STANDARDLAYOUT
    #: Der Block beginnt auf einer frischen Seite: Der vorige endete mit
    #: einem Umbruch (Deckblatt, Übersicht) oder er ist der erste.
    seitenanfang: bool = False

    def steht_danach(self, block: str, bezug: str) -> bool:
        """Ob ``bezug`` im Blatt hinter ``block`` steht."""
        if block not in self.folge or bezug not in self.folge:
            return False
        return self.folge.index(bezug) > self.folge.index(block)


def vermieter_anschrift() -> str:
    """Die eigene Anschrift des Vermieters fuer den Briefkopf (Phase 58).

    Wie ``vermieter_ausweis`` fuer Name und IBAN: Der Generator holt sie
    selbst, damit jeder Aufrufer sie bekommt, ohne sie durchzureichen.
    Ohne Anwendungskontext (Werkzeug, Test) gibt es keine Datenbank, und
    dann bleibt der Briefkopf leer -- das ist richtig so, erfunden wird
    hier nichts.

    Anders als Name und IBAN hat die Anschrift keinen Rueckfall aus der
    Umgebung: Es gab nie ein VERMIETER_ANSCHRIFT.
    """
    try:
        from nebenkostenfix.models import Vermieterdaten
        zeile = Vermieterdaten.einziger()
    except RuntimeError:  # kein Anwendungskontext
        return ''
    return (zeile.anschrift or '').strip() if zeile else ''


def zahlungssatz(saetze: dict, iban: str | None) -> str:
    """Der Satz „Bitte überweisen Sie … auf das Konto mit der IBAN …".

    Die IBAN steht darin in **einer** Zeile. Durchsicht am 2026-10-22: Vorher
    brach der Absatz mitten durch sie hindurch („… IBAN DE89" / „3704 0044
    …"), und eine halbe Kontonummer am Zeilenende liest sich wie ein
    Tippfehler. Geschützte Leerzeichen halten die Vierergruppen zusammen;
    der Umbruch sucht sich die Stelle davor.

        >>> satz = zahlungssatz({'konto': 'mein Konto'}, 'DE89370400440532013000')
        >>> 'DE89\u00a03704\u00a00044\u00a00532\u00a00130\u00a000' in satz
        True
        >>> zahlungssatz({'bekanntes_konto': 'das bekannte Konto'}, None)
        'Bitte überweisen Sie den ausstehenden Betrag innerhalb von 14 Tagen auf das bekannte Konto.'
    """
    if iban:
        konto = (f"{saetze['konto']} mit der IBAN "
                 f"{_format_iban_display(iban).replace(' ', chr(0xa0))}")
    else:
        konto = saetze['bekanntes_konto']
    return ("Bitte überweisen Sie den ausstehenden Betrag innerhalb von "
            f"14 Tagen auf {konto}.")


def stichtag_hinweis(detail: dict) -> str:
    """Wie der fehlende Stand am Stichtag geschaetzt wurde (D-115)."""
    if detail.get('gradtage'):
        return ("Stichtagswert nach Gradtagszahlen geschätzt (VDI 2067, § 9b HeizkostenV): "
                "Wintertage tragen mehr Wärme als Sommertage.")
    return "Stichtagswert wurde interpoliert."

def _zeichen_malen(canvas, x, y, kante):
    """Das Zeichen aus ``marke`` als Vektor, linke untere Ecke bei x, y.
    Das Raster zählt von oben, die PDF-Seite von unten."""
    mass = kante / marke.RASTER

    def punkt(px, py):
        return x + px * mass, y + kante - py * mass

    def linie(punkte, schliessen):
        pfad = canvas.beginPath()
        pfad.moveTo(*punkt(*punkte[0]))
        for p in punkte[1:]:
            pfad.lineTo(*punkt(*p))
        if schliessen:
            pfad.close()
        return pfad

    farbe = colors.HexColor(marke.FARBE)
    weiss = colors.HexColor(marke.WEISS)
    canvas.setLineJoin(1)
    canvas.setLineCap(1)
    canvas.setFillColor(farbe)
    canvas.roundRect(x, y, kante, kante, marke.ECKENRADIUS * mass, stroke=0, fill=1)
    canvas.setFillColor(weiss)
    canvas.setStrokeColor(weiss)
    canvas.setLineWidth(2 * mass)
    canvas.drawPath(linie(marke.HAUS, True), stroke=1, fill=1)
    canvas.setStrokeColor(farbe)
    canvas.setLineWidth(marke.HAKEN_BREITE * mass)
    canvas.drawPath(linie(marke.HAKEN, False), stroke=1, fill=0)


def _fuss_zeichnen(canvas, doc):
    """Zeichnet auf jedem Blatt Kopf und Fuß.

    Kopf (NK-177): Zeichen und Name rechts oben im Seitenrand, über dem
    Satzspiegel -- Anschriftfeld und Absender des Vermieters bleiben, wo
    sie sind.

    Fuß, R-DOC-02 (NK-062): wer das Blatt später prüft -- Mieter, Gericht,
    Vermieter selbst -- soll sehen, mit welchem Stand der Software und
    welchem Rechenstand der Regeln es entstanden ist. Die Stände kommen
    aus ``abrechnung_version`` -- dieselben, die NK-061 mit der Version
    der finalisierten Abrechnung abspeichert: Blatt und Versionssatz
    erzählen dieselbe Sache. Dahinter die Projektseite als Link (NK-178).
    """
    try:
        regelstand = datetime.strptime(
            REGEL_VERSION, '%Y-%m-%d').strftime('%d.%m.%Y')
    except ValueError:
        # Der Regelstand ist kein Datum mehr (etwa ein Hash): dann steht
        # er roh im Fuß -- die Version der Abrechnung trägt ihn genauso.
        regelstand = REGEL_VERSION
    projektseite = marke.REPO_URL.removeprefix('https://')
    text = (f'Erstellt mit {marke.PRODUKT} {SOFTWARE_VERSION} '
            f'· Rechenstand der Regeln: {regelstand} · ')
    canvas.saveState()

    kante, rechts, oben = 14, A4[0] - 56.7, A4[1] - 38
    canvas.setFont('Helvetica-Bold', 9)
    name_breite = canvas.stringWidth(marke.PRODUKT, 'Helvetica-Bold', 9)
    _zeichen_malen(canvas, rechts - name_breite - 5 - kante, oben - 3.5, kante)
    canvas.setFillColor(colors.HexColor(marke.FARBE_DUNKEL))
    canvas.drawRightString(rechts, oben, marke.PRODUKT)

    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(COLOR_MUTED)
    breite = canvas.stringWidth(text + projektseite, 'Helvetica', 8)
    links = (A4[0] - breite) / 2
    canvas.drawString(links, 30, text + projektseite)
    start = links + canvas.stringWidth(text, 'Helvetica', 8)
    canvas.linkURL(marke.REPO_URL, (start, 28, links + breite, 38), relative=0, thickness=0)
    canvas.restoreState()


class PDFGenerator:
    """Der einzige Erzeuger der Abrechnungs-PDF (Abnahme 0.7 beweist das).

    Auf jedem Blatt steht im Fuß, mit welchem Software- und Regelstand es
    gerechnet wurde (R-DOC-02, NK-062). Die Stände kommen aus
    ``abrechnung_version`` -- dieselben, die NK-061 mit der Version der
    finalisierten Abrechnung abspeichert."""
    def __init__(self, property_name, apartment_name, tenant_name, start_date, end_date,
                 detailliert=False, tenant_anrede=None, tenant_anschrift=None,
):
        self.detailliert = detailliert
        # Phase 60: ein Erscheinungsbild fuer das ganze Dokument. Welches,
        # entscheidet `pdf_stil`; hier wird es nur durchgereicht, damit
        # Deckblatt, Uebersicht und Detailteil dasselbe benutzen.
        self.stil = pdf_stil.STIL
        #: Die leise Farbe als Markup für die Angabenzeilen in den Tabellen.
        #: Abgeschrieben als „#5B5D72" wäre sie eine zweite Quelle -- und
        #: der Wächter in `test_design_einheit` prüft genau das nicht nach.
        self.leise_markup = f'#{self.stil.leise.hexval()[2:]}'
        self.tenant_anrede = tenant_anrede  # NK-264
        # Phase 58/59: die Anschrift, an die dieses Blatt geht. Welche der
        # beiden Anschriften des Mietverhaeltnisses das ist, hat die Route
        # mit `anschrift.fuer_zustellung` entschieden -- hier kommt nur das
        # Ergebnis an, denn ein Satzer soll keine Fristen auslegen.
        self.tenant_anschrift = tenant_anschrift
        self.property_name = property_name
        self.apartment_name = apartment_name
        self.tenant_name = tenant_name
        self.start_date = start_date
        self.end_date = end_date
        self.styles = getSampleStyleSheet()
        
        # Professional Typography styles
        self.styles.add(ParagraphStyle(name='TitleBold', fontName='Helvetica-Bold', fontSize=18, leading=22, spaceAfter=20))
        self.styles.add(ParagraphStyle(name='HeaderNormal', fontName='Helvetica', fontSize=10, leading=14))
        self.styles.add(ParagraphStyle(name='HeaderRight', fontName='Helvetica', fontSize=10, leading=14, alignment=2))
        # NK-250: kein wordWrap='CJK' -- es brach Wörter an beliebiger Stelle.
        self.styles.add(ParagraphStyle(name='TableCell', fontName='Helvetica', fontSize=9, leading=12))
        self.styles.add(ParagraphStyle(name='TableCellRight', fontName='Helvetica', fontSize=9, leading=12, alignment=2))
        self.styles.add(ParagraphStyle(name='SubTableCell', fontName='Helvetica', fontSize=8, leading=11, leftIndent=10, textColor=COLOR_MUTED))
        # Phase 61: Der Teilposten liest sich wie die Umlage darüber, nur
        # eingerückt. Vorher war er kleiner, grau und trug einen
        # Gedankenstrich -- drei Signale für dasselbe, und in einer Tabelle,
        # in der andere Zeilen ihren Satz schwarz und oben tragen.
        self.styles.add(ParagraphStyle(name='Teilposten', fontName='Helvetica', fontSize=8.5, leading=11.5, leftIndent=12))
        self.styles.add(ParagraphStyle(name='SectionHeader', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.white))
        self.styles.add(ParagraphStyle(name='TotalCell', fontName='Helvetica-Bold', fontSize=10, leading=14))
        self.styles.add(ParagraphStyle(name='TotalCellRight', fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=2))
        self.styles.add(ParagraphStyle(name='GrandTotalCell', fontName='Helvetica-Bold', fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='GrandTotalCellRight', fontName='Helvetica-Bold', fontSize=12, leading=16, alignment=2))
        self.styles.add(ParagraphStyle(name='Fussnote', fontName='Helvetica', fontSize=8, leading=11, textColor=COLOR_MUTED))
        # Phase 60: Der Kopf des Zählerkastens stand als letzter noch auf
        # einem violetten Vollbalken -- die zweite Designsprache, die
        # sonst überall verschwunden ist. Sie überlebte hier, weil der
        # Nachweisteil nur bei Zählern entsteht und in keinem Muster
        # vorkam. Jetzt: dunkle Schrift auf der Kastenfläche.
        self.styles.add(ParagraphStyle(name='MeterHeader', fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=self.stil.text))
        self.styles.add(ParagraphStyle(name='MeterText', fontName='Helvetica', fontSize=9, leading=14))
        self.styles.add(ParagraphStyle(name='MeterTextBold', fontName='Helvetica-Bold', fontSize=9, leading=14))
        self.styles.add(ParagraphStyle(name='MeterTextRight', fontName='Helvetica-Bold', fontSize=9, leading=14, alignment=2))


    def _format_datum(self, iso):
        """ISO-Datum als Anzeigeformat -- oder None ohne Datum.

        ``rechnungsdatum`` kommt als ISO-Zeichenkette (oder None) aus dem
        Kern, weil die Zeilen JSON-sicher sind. Ohne Datum bleibt die
        Angabe leer: nichts erfinden (D-57) -- eine Rechnung vom Januar
        kann im April ausgestellt sein, der Zeitraum ist kein Datum.
        """
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso).strftime('%d.%m.%Y')
        except (ValueError, TypeError):
            return iso

    def _belegliste_elemente(self, line_items, mit_betraegen=False):
        """Baut die Belegliste (R-DOC-01 Punkt 8): eine Zeile je Rechnung.

        Je Beleg stehen Rechnungsnummer, Ausstellungsdatum, Anbieter und
        das Dokument mit Seitenzahl auf dem Blatt. Heizzeilen tragen ihre
        Rechnungen in ``heizung_details['rechnungen']`` -- dort wird je
        Rechnung eine Zeile, damit die Zuordnung auch bleibt, wenn mehrere
        Rechnungen in einer Position zusammengefasst sind (D-47). Ohne
        Rechnungsnummer gibt es keinen Verweis -- und nichts zu erfinden
        (D-57); solche Positionen tauchen in der Liste nicht auf.

        ``mit_betraegen`` ergaenzt die Betragsspalten der ausfuehrlichen
        Variante (Rechnungsbetrag, zeitanteilig angesetzt).
        """
        zeilen = []
        for item in line_items:
            heizung = item.get('heizung_details') or {}
            rechnungen = heizung.get('rechnungen')
            if rechnungen:
                for r in rechnungen:
                    if not r.get('invoice_number'):
                        continue
                    position = item['category']
                    if r.get('kostenart_text'):
                        position += f" — {r['kostenart_text']}"
                    zeilen.append({
                        'position': position,
                        'nummer': r['invoice_number'],
                        'datum': self._format_datum(r.get('rechnungsdatum')),
                        'anbieter': r.get('provider_name'),
                        'dokument': r.get('doc_name') or None,
                        'rechnungsbetrag': r.get('rechnungsbetrag'),
                        # Nach Verbrauch verteilt passt der Tagesanteil nicht
                        # zum angesetzten Betrag -- dann steht der Weg da.
                        'zeitanteilig': (None if r.get('nach_verbrauch')
                                         else r.get('prorated_amount')),
                        'tage': None,
                    })
                continue
            if not item.get('invoice_number'):
                continue
            zeilen.append({
                'position': item['category'],
                'nummer': item['invoice_number'],
                'datum': self._format_datum(item.get('rechnungsdatum')),
                'anbieter': item.get('provider_name'),
                'dokument': item.get('doc_name') or None,
                'rechnungsbetrag': item.get('invoice_total_amount'),
                # Nach Zaehler gerechnet ist der Tagesanteil nicht der
                # angesetzte Betrag (bei Heizung am Stichtag nach Gradtagen
                # geschaetzt) -- die Spalte nennt dann den Weg.
                'zeitanteilig': (None if item.get('meter_details')
                                 else item.get('prorated_amount')),
                'tage': (item.get('overlap_days'), item.get('invoice_days')),
            })

        if not zeilen:
            return []

        # Phase 60: der Kopf traegt die Schrift des Stils -- auf dunkler
        # Flaeche waere dunkler Text unlesbar.
        beleg_saetze = pdf_stil.stile(self.stil)
        # Phase 60 (Durchsicht am 2026-10-21): Anbieter und Beleg stehen als
        # leise Zeile **unter** der Position, nicht in eigenen Spalten. Mit
        # sechs Spalten blieben fuer den Dateinamen 60 pt -- „wasser_2024
        # .pdf, Seiten 3" brach dort in vier Zeilen, und jede Zeile der
        # Liste wurde so hoch wie ein Absatz. Dieselbe Form wie in der
        # Aufstellung: Was die Position ausweist, steht bei ihr.
        kopf = [
            Paragraph("Position", beleg_saetze['Kopf']),
            Paragraph("Rechnung", beleg_saetze['Kopf']),
        ]
        if mit_betraegen:
            kopf += [
                Paragraph("Rechnungsbetrag (€)", beleg_saetze['KopfRechts']),
                Paragraph("Zeitanteilig (€)", beleg_saetze['KopfRechts']),
            ]
        data = [kopf]
        for z in zeilen:
            rechnung = f"Nr. {escape(z['nummer'])}"
            if z['datum']:
                rechnung += f"<br/>vom {z['datum']}"
            herkunft = ' · '.join(
                teil for teil in (z['anbieter'], z['dokument']) if teil)
            row = [
                Paragraph(
                    f"<b>{escape(z['position'])}</b>"
                    + (f"<br/><font size=7.5 color='{self.leise_markup}'>"
                       f"{escape(herkunft)}</font>" if herkunft else ''),
                    self.styles['TableCell']),
                Paragraph(rechnung, self.styles['TableCell']),
            ]
            if mit_betraegen:
                if z['zeitanteilig'] is None:
                    zeitanteilig = 'nach Zähler'
                else:
                    # Phase 60: derselbe Tausenderpunkt wie überall
                    # sonst. Ohne ihn stand „10000,00" neben „10.000,00".
                    zeitanteilig = pdf_stil.geld(z['zeitanteilig'],
                                                 waehrung=False)
                if z['zeitanteilig'] is not None and z['tage'] and z['tage'][0] and z['tage'][1] \
                        and z['tage'][0] < z['tage'][1]:
                    zeitanteilig += f" ({z['tage'][0]}/{z['tage'][1]} Tage)"
                row += [
                    Paragraph(
                        pdf_stil.geld(z['rechnungsbetrag'], waehrung=False),
                        self.styles['TableCellRight']),
                    Paragraph(zeitanteilig, self.styles['TableCellRight']),
                ]
            data.append(row)

        # Phase 60: dieselbe Breite und dieselbe Sprache wie die Aufstellung.
        # Vorher war die Belegliste schmaler als alles andere und mittig --
        # auf dem Blatt sah sie aus wie ein Zitat aus einem anderen Papier.
        # NK-250: die Kopfwörter der Betragsspalten passen ungebrochen hinein.
        # NK-250: die Kopfwoerter muessen ungebrochen hineinpassen. Phase 60
        # hat das Zellenpolster von 6 auf 8 pt gehoben -- damit verliert
        # jede Spalte 4 pt nutzbare Breite, und „Rechnungsbetrag" brach in
        # „Rechnungsbetra". Die Geldspalten sind deshalb breiter.
        # Gemessen: „Anbieter · Beleg" braucht bei 7,5 pt bis zu 197 pt,
        # „Rechnungsbetrag" als Kopfwort 89 (NK-250: es darf nicht brechen),
        # „Nr. AB-2024-115 vom 28.01.2025" in einer Zeile 176.
        # Echte Rechnungsnummern sind laenger als die der Muster
        # („5.0100.009177.3"): die Spalte bekommt 10 pt mehr, die
        # Angabenzeile unter der Position bricht ohnehin um.
        breiten = ([190, 96, 90, 94] if mit_betraegen else [280, 190])
        saetze = pdf_stil.stile(self.stil)
        tabelle = Table(data, colWidths=breiten, repeatRows=1)
        befehle = pdf_stil.tabellenstil(self.stil, len(data))
        befehle.append(('LINEBELOW', (0, 1), (-1, -1), 0.4, self.stil.linie))
        tabelle.setStyle(TableStyle(befehle))
        # Eine Ueberschrift allein am Seitenfuss ist ein verwaister Kopf:
        # Sie bleibt bei den ersten Zeilen ihrer Liste.
        return [
            Spacer(1, pdf_stil.XL),
            KeepTogether([
                Paragraph("Belegliste", saetze['Titel']),
                Spacer(1, pdf_stil.M),
                tabelle,
            ]),
        ]

    def _deutsch(self, wert, stellen=2):
        """Zahl im Sprachbild des Dokuments: Komma statt Punkt.

        Die Werte kommen gerundet aus dem Kern (R-NUM-01) -- hier wird nur
        angezeigt, nichts gerundet. Nur fuer Mengen und Prozente: ein
        Geldbetrag geht durch ``geld.text`` und bekommt den Tausenderpunkt
        wie die Betragsspalte.
        """
        if wert is None:
            return None
        return f"{float(wert):.{stellen}f}".replace('.', ',')

    def _heizung_co2_elemente(self, line_items, co2_ausweis, landlord_share):
        """Heizkosten- und CO2-Abschnitt (NK-060, R-HK-01/R-CO2-02/R-NUM-05).

        Drei Dinge stehen hier, die nirgends sonst auf dem Blatt stehen:

        * je Heizanlage die Begruendungen hinter den Zahlen der Tabelle --
          der Sonderfall 70 % (§ 7 Abs. 1 Satz 2), warum der Verbrauch
          nicht erfasst wurde und ob/wie Warmwasser getrennt wurde
          (R-HK-03);
        * der Ausweis des § 7 CO2KostAufG: Emission, kg/m²a, Stufe,
          Anteile in Prozent und Euro, Herkunft der Emissionsdaten. Fehlt
          der Ausweis, sagt der Abschnitt es mit der Kennung
          ``E-CO2-AUSWEIS-FEHLT`` -- ohne die 3-%-Kürzung zu nennen, denn
          sie ist die Sanktion des fehlenden Ausweises selbst (D-53);
        * der Vermieteranteil (R-NUM-05): die Positionen, die nicht auf
          die Mieter umgelegt wurden. Er haengt nicht an den Heizzeilen
          -- auch eine Abrechnung ohne Heizkosten kann Leerstand tragen.

        Beide Varianten tragen den Abschnitt: der Vermieter sendet nur
        eine der beiden Fassungen (dieselbe Regel wie bei der Belegliste,
        NK-058). Ohne Heizzeilen und ohne Vermieterpositionen gibt es
        nichts zu sagen -- dann bleibt der Abschnitt ganz weg.
        """
        heizzeilen = [z for z in line_items
                      if z.get('billing_type') == 'heizkosten'
                      and z.get('heizung_details')]
        elemente = []

        if heizzeilen:
            elemente.append(Spacer(1, 20))
            elemente.append(Paragraph(
                "Heizkosten und CO2", self.styles['TitleBold']))

        for zeile in heizzeilen:
            d = zeile['heizung_details']
            elemente.append(Paragraph(
                f"<b>{zeile['category']}</b>", self.styles['TableCell']))
            if d.get('erfasst'):
                verbrauch = (
                    f"{self._deutsch(d.get('tenant_consumption'), 1)} von "
                    f"{self._deutsch(d.get('total_consumption'), 1)} "
                    f"{d.get('unit') or ''}").strip()
                elemente.append(Paragraph(
                    f"Verteilung nach § 7 Abs. 1 HeizkostenV: "
                    f"{d.get('verbrauchsanteil_prozent')} % nach erfasstem "
                    f"Verbrauch ({verbrauch}), "
                    f"{d.get('flaechenanteil_prozent')} % nach Wohnfläche.",
                    self.styles['TableCell']))
            else:
                elemente.append(Paragraph(
                    "Verteilung nach § 7 Abs. 1 HeizkostenV: kein erfasster "
                    "Verbrauch, die Kosten gehen ganz nach Wohnfläche.",
                    self.styles['TableCell']))
            if d.get('fehlgrund'):
                elemente.append(Paragraph(
                    f"Grund: {d['fehlgrund']}.", self.styles['TableCell']))
            if d.get('sonderfall_70'):
                elemente.append(Paragraph(
                    "Der erhöhte Verbrauchsanteil von 70 % beruht auf "
                    "§ 7 Abs. 1 Satz 2 HeizkostenV (Sonderfall 70 %).",
                    self.styles['TableCell']))
            if d.get('warmwasser_weg_text'):
                elemente.append(Paragraph(
                    f"Warmwasser wurde getrennt ermittelt — "
                    f"{d['warmwasser_weg_text']}, Anteil "
                    f"{self._deutsch(d.get('warmwasser_anteil_prozent'), 2)} %.",
                    self.styles['TableCell']))
            elif d.get('trennungsgrund'):
                elemente.append(Paragraph(
                    f"Heizung und Warmwasser wurden nicht getrennt "
                    f"({d['trennungsgrund']}).",
                    self.styles['TableCell']))

        if heizzeilen:
            if co2_ausweis:
                elemente.append(Paragraph(
                    "<b>CO2-Ausweis nach § 7 CO2KostAufG</b>",
                    self.styles['TableCell']))
                elemente.append(Paragraph(
                    f"Emission des Gebäudes: "
                    f"{self._deutsch(co2_ausweis.get('emission_kg'), 1)} "
                    f"kg CO2 im Abrechnungszeitraum — "
                    f"{self._deutsch(co2_ausweis.get('kg_pro_qm'), 1)} "
                    f"kg/m²a.",
                    self.styles['TableCell']))
                elemente.append(Paragraph(
                    f"Einstufung: Stufe {co2_ausweis.get('stufe')} — "
                    f"Mieteranteil {co2_ausweis.get('mieter_prozent')} %, "
                    f"Vermieteranteil "
                    f"{co2_ausweis.get('vermieter_prozent')} %.",
                    self.styles['TableCell']))
                elemente.append(Paragraph(
                    f"CO2-Kosten des Gebäudes: "
                    f"{geld_text(co2_ausweis.get('kosten'))} — "
                    f"davon "
                    f"{geld_text(co2_ausweis.get('mieter_anteil_euro'))} "
                    f"auf dieses Mietverhältnis; der Vermieteranteil "
                    f"beträgt "
                    f"{geld_text(co2_ausweis.get('vermieter_anteil_euro'))}.",
                    self.styles['TableCell']))
                for q in co2_ausweis.get('quellen') or []:
                    herkunft = "Herkunft der Emissionsdaten: Rechnung "
                    herkunft += q.get('invoice_number') or 'ohne Rechnungsnummer'
                    if q.get('rechnungsdatum'):
                        herkunft += (
                            f" vom "
                            f"{self._format_datum(q.get('rechnungsdatum'))}")
                    herkunft += (
                        f" — {self._deutsch(q.get('emission_kg'), 1)} kg, "
                        f"{geld_text(q.get('kosten'))}.")
                    elemente.append(Paragraph(
                        herkunft, self.styles['TableCell']))
            else:
                elemente.append(Paragraph(
                    "Der Ausweis nach § 7 CO2KostAufG fehlt "
                    "(E-CO2-AUSWEIS-FEHLT): mindestens eine "
                    "Heizkostenrechnung trägt keine CO2-Angaben. Ohne "
                    "Emissionsmenge und CO2-Kosten kann das Gebäude nicht "
                    "eingestuft werden — die Abrechnung gilt nicht als "
                    "endgültig.",
                    self.styles['TableCell']))

        positionen = (landlord_share or {}).get('positions') or []
        if positionen:
            # Phase 61 (Durchsicht am 2026-10-22): **eine Tabelle, kein Fließtext.**
            # Vorher stand je Position ein Satz, der mit „— Nicht auf die
            # Mieter umgelegt:" anfing -- an jeder einzelnen Zeile, obwohl die
            # Überschrift darüber genau das sagt. Der Betrag hing hinten am
            # Satz und brach um, sodass das Eurozeichen in der nächsten Zeile
            # allein stand. Jetzt: links die Position mit ihrem Grund, rechts
            # der Betrag, darunter die Summe.
            saetze = pdf_stil.stile(self.stil)
            elemente.append(Spacer(1, pdf_stil.XL))
            elemente.append(Paragraph('Vermieteranteil (nicht auf die Mieter '
                                      'umgelegt)', saetze['Zwischentitel']))
            elemente.append(Spacer(1, pdf_stil.M))
            zeilen = []
            for p in positionen:
                grund = str(p.get('description') or '')
                if grund.startswith(VERMIETERANTEIL_VORSATZ):
                    grund = grund[len(VERMIETERANTEIL_VORSATZ):]
                bezeichnung = p.get('category') or ''
                if grund:
                    bezeichnung = f"{bezeichnung} — {grund}"
                zeilen.append((bezeichnung, pdf_stil.geld(p.get('amount')),
                               False, None))
            anteil = landlord_share or {}
            zeilen.append((
                f"Insgesamt beim Vermieter (Leerstand "
                f"{pdf_stil.geld(anteil.get('leerstand_amount'))}, "
                f"Eigennutzung {pdf_stil.geld(anteil.get('eigennutzung_amount'))})",
                pdf_stil.geld(anteil.get('total_amount')), True, None))
            elemente.append(pdf_stil.summenblock(
                zeilen, self.stil, saetze, breite=pdf_stil.SATZBREITE,
                ausrichtung='LEFT', schlicht=True))

        return elemente

    def _ausweis_35a_elemente(self, ausweis_35a):
        """Die Lohnanteile nach § 35a EStG (NK-268, R-35A-01).

        Eine Tabelle je Art (haushaltsnahe Dienstleistungen,
        Handwerkerleistungen) mit der Summe darunter -- nur Beträge, kein
        Steuersatz und kein Höchstbetrag; der Hinweis sagt, woher sie
        kommen. Ohne Angabe an einer Rechnung bleibt der Abschnitt weg.
        """
        if not ausweis_35a:
            return []
        elemente = [Spacer(1, 20), Paragraph(
            "Lohnanteile nach § 35a EStG", self.styles['TitleBold'])]
        for gruppe in ausweis_35a['gruppen']:
            daten = [[Paragraph(f"<b>{gruppe['art_text']}</b>", self.styles['TableCell']),
                      Paragraph("<b>Ihr Anteil</b>", self.styles['TableCellRight'])]]
            daten += [[Paragraph(escape(z['kostenart']), self.styles['TableCell']),
                       Paragraph(geld_text(z['betrag']), self.styles['TableCellRight'])]
                      for z in gruppe['zeilen']]
            daten.append([Paragraph("Summe", self.styles['TotalCell']),
                          Paragraph(geld_text(gruppe['summe']),
                                    self.styles['TotalCellRight'])])
            # 480 pt ragten 5 pt aus dem Satzspiegel (siehe SATZBREITE).
            tabelle = Table(daten, colWidths=[370, 100])
            tabelle.setStyle(TableStyle([
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, self.stil.linie),
                ('LINEABOVE', (0, -1), (-1, -1), 0.5, self.stil.text),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elemente += [tabelle, Spacer(1, 8)]
        elemente.append(Paragraph(escape(ausweis_35a['hinweis']), self.styles['Fussnote']))
        return elemente

    def generate(self, line_items, total_amount, prepaid_amount=NULL,
                 co2_ausweis=None, landlord_share=None, anschreiben=None,
                 vorbehalt=None, ausweis_35a=None, layout=None):
        """Die Abrechnungs-PDF: die eingeschalteten Blöcke des Layouts hintereinander.

        Jeder Block ist eine eigene Methode ``_block_<id>``, die ihre
        Flowables liefert; hier wird nur noch die Liste durchgegangen. Ein
        Block, der nichts zu zeigen hat (kein Heizungsteil, kein § 35a, die
        einfache Fassung ohne Nachweise), liefert eine leere Liste. Jeder
        Block erfährt, wo die anderen stehen und ob er auf einer frischen
        Seite beginnt -- so stimmt ein Verweis wie „auf den folgenden
        Seiten“ auch, wenn der Vermieter die Reihenfolge ändert.

        ``layout`` ist ein Layout im Format von ``pdf_layout``; ohne Angabe
        gilt der Standard, und das Blatt bleibt, wie es war. Es wird
        tolerant geladen: Unbekanntes fällt weg, Pflichtblöcke bleiben an.
        """
        layout = pdf_layout.laden(layout)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=56.7, leftMargin=56.7,
                                topMargin=56.7, bottomMargin=56.7)

        inhalt = _Inhalt(
            line_items=line_items,
            total_amount=total_amount,
            prepaid_amount=prepaid_amount,
            balance=total_amount - prepaid_amount,
            co2_ausweis=co2_ausweis,
            landlord_share=landlord_share,
            anschreiben=anschreiben,
            vorbehalt=vorbehalt,
            ausweis_35a=ausweis_35a,
            # NK-210: der Name aus den Einstellungen statt der Rolle
            vermieter=vermieter_ausweis()[0],
            vermieter_adresse=vermieter_anschrift(),
            girocode=layout['girocode'],
            folge=tuple(pdf_layout.aktive_bloecke(layout)),
        )
        bloecke = self._bloecke()
        elements = []
        for block in inhalt.folge:
            seitenanfang = not elements or isinstance(elements[-1], PageBreak)
            elements.extend(bloecke[block](replace(inhalt, seitenanfang=seitenanfang)))

        doc.build(elements, onFirstPage=_fuss_zeichnen, onLaterPages=_fuss_zeichnen)

        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data

    def _bloecke(self):
        """Block-ID → Methode, die die Flowables des Blocks liefert."""
        return {
            'deckblatt': self._block_deckblatt,
            'uebersicht': self._block_uebersicht,
            'kostenaufstellung': self._block_kostenaufstellung,
            'heizung_co2': self._block_heizung_co2,
            'ausweis_35a': self._block_ausweis_35a,
            'belegliste': self._block_belegliste,
            'zahlung': self._block_zahlung,
            'verbrauchsnachweise': self._block_verbrauchsnachweise,
        }

    def _block_deckblatt(self, inhalt):
        """Blatt 1: Anschriften, Betreff, Brief, „Ihr Anteil“; endet mit Umbruch."""
        return build_cover_page_elements(
            property_name=self.property_name,
            apartment_name=self.apartment_name,
            tenant_name=self.tenant_name,
            tenant_anrede=self.tenant_anrede,
            start_date=self.start_date,
            end_date=self.end_date,
            total_amount=inhalt.total_amount,
            prepaid_amount=inhalt.prepaid_amount,
            balance=inhalt.balance,
            # NK-064: das Anschreiben des Vermieters spricht auf dem
            # Deckblatt statt des festen Grußes; ohne Vorlage wie gehabt.
            anschreiben=inhalt.anschreiben,
            vermieter_name=inhalt.vermieter,
            # Phase 59: der Briefkopf des Musters -- Empfaenger mit
            # Anschrift, Absender mit Anschrift.
            mieter_anschrift=self.tenant_anschrift,
            vermieter_anschrift=inhalt.vermieter_adresse,
            # Wahlweise steht der GiroCode direkt unter „Ihr Anteil“.
            girocode=(self._block_girocode(inhalt)
                      if inhalt.girocode == 'deckblatt' else ()),
        )

    def _block_uebersicht(self, inhalt):
        """Das Übersichtsblatt: eine Zeile je Position, drei Summen."""
        # Phase 59 (Issue #35, Punkt 2): das Uebersichtsblatt -- eine Zeile
        # je Position, drei Summen. Es kommt **vor** den Detailteil und
        # nimmt ihm nichts weg: Der Melder wollte ausdruecklich beides.
        # `build_uebersicht_elements` bricht ab, wenn seine Summe von
        # `total_amount` abweicht; zwei Blaetter, die sich widersprechen,
        # sind schlimmer als ein Blatt weniger.
        return pdf_uebersicht.build_uebersicht_elements(
            inhalt.line_items,
            gesamtsumme=inhalt.total_amount,
            vorauszahlungen=inhalt.prepaid_amount,
            property_name=self.property_name,
            apartment_name=self.apartment_name,
            tenant_name=self.tenant_name,
            start_date=self.start_date,
            end_date=self.end_date,
            vermieter_name=inhalt.vermieter,
            vermieter_anschrift=inhalt.vermieter_adresse,
            mieter_anschrift=self.tenant_anschrift,
            aufstellung_folgt=inhalt.steht_danach('uebersicht', 'kostenaufstellung'),
        )

    def _block_kostenaufstellung(self, inhalt):
        """Die Aufstellung der Kosten mit Summenblock und Fußnoten."""
        line_items = inhalt.line_items
        total_amount = inhalt.total_amount
        prepaid_amount = inhalt.prepaid_amount
        vorbehalt = inhalt.vorbehalt
        elements = []

        start_fmt = datetime.fromisoformat(self.start_date).strftime('%d.%m.%Y')
        end_fmt = datetime.fromisoformat(self.end_date).strftime('%d.%m.%Y')

        # Phase 60: **kein zweiter Briefkopf.** Objekt, Vermieter und Datum
        # stehen auf Blatt 1 und im Kopf des Uebersichtsblatts; hier noch
        # einmal gesetzt, lasen sie sich wie der Anfang eines neuen
        # Dokuments. Das Blatt traegt seinen Titel, sonst nichts.
        
        # Phase 60: derselbe Titelblock wie auf Blatt 1 und 2 -- Titel,
        # darunter eng die Angaben. Vorher stand hier ein zweiter Briefkopf
        # („An: …") mit 40 pt Luft, und das Blatt sah aus wie ein eigenes
        # Dokument.
        saetze = pdf_stil.stile(self.stil)
        elements.append(Paragraph('Aufstellung der Kosten', saetze['Titel']))
        elements.append(Spacer(1, pdf_stil.M))
        elements.append(Paragraph(
            f"{escape(self.tenant_name)} · {escape(self.apartment_name)}",
            saetze['Titelzeile']))
        elements.append(Paragraph(
            f"Abrechnungszeitraum: {start_fmt} bis {end_fmt}", saetze['Titelzeile']))
        elements.append(Spacer(1, pdf_stil.XXL))
        
        # Categorization logic
        categories = {
            # Geldwerte kommen als Decimal herein (R-NUM-01, NK-036). Ein
            # Zwischenstand, der bei 0.0 anfaengt, wuerde beim ersten += einen
            # TypeError werfen -- genau das ist die Absicht: float und Euro
            # mischen sich hier nicht mehr.
            # Die Rubrik kommt aus dem Katalog (betrkv), nicht mehr aus
            # Stichwoertern (F-32, NK-121). Sie entscheidet
            # ``pdf_uebersicht.rubrik``, dieselbe Funktion wie fuer das
            # Uebersichtsblatt (R-DOC-04): eine Heizzeile der Anlage ist
            # Energie, sonst gilt die gespeicherte Nummer der Kostenart;
            # nur ohne Bestandszeile bleibt die Vermutung aus dem Namen.
            "Energie": {"items": [], "total": NULL},
            "Wasser & Abwasser": {"items": [], "total": NULL},
            "Betriebskosten": {"items": [], "total": NULL}
        }
        
        for item in line_items:
            rubrik = pdf_uebersicht.rubrik(item)
            categories[rubrik]["items"].append(item)
            categories[rubrik]["total"] += item['tenant_cost']

        # Phase 60 (nach der zweiten Sichtung): **drei Spalten statt
        # vier.** Vorher standen Zeitraum, Anbieter und Rechnungsnummer als
        # drei eigene Zeilen in einer eigenen Spalte -- bei sieben Posten
        # waren das einundzwanzig Zeilen Kleingedrucktes, die die Tabelle
        # erschlugen. Jetzt stehen sie als **eine** leise Zeile unter ihrer
        # Kostenart, dort, wo sie hingehoeren. Die Angaben sind dieselben.
        data = [
            [Paragraph("Kostenart und Umlage", saetze['Kopf']),
             Paragraph("Betrag (€)", saetze['KopfRechts'])]
        ]

        # Phase 60: derselbe Tabellenkopf wie im Uebersichtsblatt. Das Zebra
        # macht hier keinen Sinn -- eine Position belegt mehrere Zeilen
        # (Rechenweg, Teilposten), und eine Toenung je Zeile zerschnitte sie.
        # TOP statt MIDDLE: Bei einer Zeile mit Rechenweg schwebte der
        # Betrag vorher in der Mitte eines hohen Felds, weit weg von der
        # Kostenart, zu der er gehoert. Oben ausgerichtet steht alles auf
        # derselben ersten Zeile.
        table_style = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('LINEBELOW', (0, 0), (-1, 0), 0.8, self.stil.linie),
        ]
        if self.stil.kopf_flaeche is not None:
            table_style.append(
                ('BACKGROUND', (0, 0), (-1, 0), self.stil.kopf_flaeche))
        else:
            table_style.append(('LINEABOVE', (0, 0), (-1, 0), 0.8, self.stil.linie))
        
        row_idx = 1
        anteilig_ausgewiesen = False
        # Derselbe Wortlaut, den der Kern den Positionen mitgibt
        # (``rechenkern``: „%d.%m.%Y - %d.%m.%Y"). Nur so greift der
        # Vergleich unten, der den wiederholten Zeitraum weglaesst.
        eigener_zeitraum = (
            f"{datetime.fromisoformat(self.start_date).strftime('%d.%m.%Y')}"
            f" - {datetime.fromisoformat(self.end_date).strftime('%d.%m.%Y')}")
        
        for section_name, section_data in categories.items():
            if not section_data["items"]:
                continue
                
            # Rubrik: Phase 60 -- eine fette Zeile mit Haarlinie statt des
            # violetten Vollbalkens. Der Balken war die zweite Designsprache
            # im selben Dokument; eine Ueberschrift muss nicht schreien, um
            # eine Ueberschrift zu sein.
            data.append([Paragraph(escape(section_name.upper()),
                                   saetze['Rubrik']), ''])
            table_style.extend([
                ('SPAN', (0, row_idx), (-1, row_idx)),
                # Die Luft gehoert **ueber** die Rubrik: Dort trennt sie die
                # vorige Gruppe ab. Darunter bleibt sie knapp, damit die
                # Rubrik zu ihren Positionen gehoert und nicht dazwischen
                # schwebt.
                ('TOPPADDING', (0, row_idx), (-1, row_idx), 16),
                ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 5),
                ('LINEBELOW', (0, row_idx), (-1, row_idx), 0.8, self.stil.linie),
            ])
            row_idx += 1
            
            stripe_counter = 0
            
            for item in section_data["items"]:
                # Zeitraum, Anbieter und Beleg in einer Zeile, mit
                # Mittelpunkten getrennt. NK-246: ohne Anbieter keine
                # Anbieterangabe. R-DOC-01 Punkt 8: der Belegverweis steht
                # weiter an der Position -- fuer jede Zeile aus genau einer
                # Rechnung; mehrere (Heizung, D-47) zaehlt die Belegliste.
                angaben = []
                # Der Zeitraum der Rechnung steht nur, wenn er **abweicht**.
                # Deckt er sich mit dem Abrechnungszeitraum, wiederholt er
                # bloss die Kopfzeile des Blattes -- siebenmal dieselbe
                # Zeitspanne, und die Zeile, die wirklich abweicht, geht
                # darin unter. Genau die ist die rechtlich interessante.
                if item['period'] != eigener_zeitraum:
                    angaben.append(escape(item['period']))
                if item.get('provider_name'):
                    angaben.append(escape(item['provider_name']))
                if item.get('invoice_number'):
                    verweis = f"Rechnung Nr. {item['invoice_number']}"
                    datum = self._format_datum(item.get('rechnungsdatum'))
                    if datum:
                        verweis += f" vom {datum}"
                    angaben.append(escape(verweis))
                angabenzeile = ' · '.join(angaben)
                
                details = item['description']
                # R-DOC-01 Punkt 6/7: der Rechenweg der Zeile als Satz.
                # Steht er, tragen die Tage ihn selbst -- der alte
                # Zeitanteil-Anhang wuerde dasselbe zweimal sagen.
                schritte = item.get('rechenweg') or []
                zusatz = ''
                if (not schritte and item.get('overlap_days')
                        and item.get('invoice_days')
                        and item['overlap_days'] < item['invoice_days']):
                    zusatz = (f"anteilig {item['overlap_days']} von "
                              f"{item['invoice_days']} Tagen")
                    anteilig_ausgewiesen = True

                # Ein Teilposten, der nur die Zeilenbeschreibung wiederholt
                # (qm, Personen), schweigt, wenn der Rechenweg die Zeile
                # schon herzuleiten: derselbe Satz steht nicht zweimal unter
                #einander. Echte Teilposten (Grund-/Verbrauchsteil,
                # Eigenverbrauch, Allgemeinanteil) bleiben.
                folgeposten = [
                    s for s in item.get('sub_items') or []
                    if s['description'] != item['description']
                ]
                # Phase 60: Der Rechenweg steht **in derselben Zelle** wie die
                # Umlage, nicht als eigene Tabellenzeile. Als eigene Zeile
                # rutschte er unter die ganze Position und stand dann weit
                # unter der Zahl, die er erklaert (Befund: „die kleinen Sachen
                # weiter unten"). Teilposten mit eigenem Betrag bleiben
                # eigene Zeilen -- ihre Zahl gehoert in die Betragsspalte.
                has_sub = bool(folgeposten)
                
                # Phase 60: die Tönung kommt aus dem Stil. Im gewählten
                # gibt es keine -- was die Positionen trennt, ist die
                # Haarlinie darunter, wie auf dem Übersichtsblatt.
                bg_color = (colors.white
                            if self.stil.zebra is None or stripe_counter % 2 == 0
                            else self.stil.zebra)
                
                # Main row
                # Eine Stimme je Zelle: Wo ein Rechenweg steht, sagt er die
                # Umlage mit Zahlen („852,00 € nach Wohnfläche 62 von 186 m²
                # = 284,00 €"). Die Beschreibung daneben saegte denselben
                # Satz ohne Zahlen noch einmal.
                # Phase 61 (Durchsicht am 2026-10-22): **Jede Zeile hat dieselbe
                # Form.** Vorher blieb die Zelle bei Positionen mit
                # Teilposten leer, und darunter standen eingerückte graue
                # Zeilen -- in derselben Tabelle, in der andere Zeilen ihren
                # Satz oben und schwarz trugen. „Manchmal schwarz, manchmal
                # weiter unten versetzt in hellgrau": zwei Formen für
                # dieselbe Sache. Jetzt steht die Umlage immer oben, auf
                # Höhe ihres Betrags; die Teilposten folgen darunter in
                # derselben Schrift.
                # Eine Zeile sagt die Umlage **einmal**. Lesen sich die
                # Teilposten zusammen schon wie die Beschreibung
                # („Eigenverbrauch (32,7 m³) + Anteil Allgemein (…)"),
                # dann stuende sie darueber und darunter dasselbe. Die
                # Tageszahl faellt dabei nicht mit weg: Sie steht in keinem
                # Teilposten und ist R-NUM-03.
                deckt_ab = bool(folgeposten) and all(
                    s['description'] in details for s in folgeposten)
                if schritte:
                    # Die Schritte sagen die Umlage mit Zahlen
                    # („nach Wohnfläche 52,40 von 210,00 m²  2,25 €").
                    # Die Beschreibung daneben sagte denselben Satz ohne
                    # Zahlen noch einmal. Die Tageszahl steckt als eigener
                    # Schritt schon drin.
                    umlage = []
                elif deckt_ab or not details:
                    umlage = [zusatz] if zusatz else []
                else:
                    umlage = [f"{details}, {zusatz}" if zusatz else details]
                # Phase 61: **Zwei Spalten statt dreier.** Die
                # Rechenschritte brauchen 240 bis 310 pt für eine Zeile --
                # in einer 200 pt breiten Spalte bricht jeder von ihnen um,
                # und aus zwei Schritten werden vier Zeilen. Keine Aufteilung
                # in drei Spalten löst das: Die Kostenart-Spalte braucht
                # ihrerseits 190 pt für die Angabenzeile. Also steht jetzt
                # alles zu einer Position **untereinander in einer Zelle** --
                # Name, Rechenweg, Herkunft --, und daneben der Betrag. Jede
                # Zeile passt, nichts bricht um.
                # Die Herkunftszeile steht **direkt unter dem Namen**
                # (Durchsicht am 2026-10-22). Vorher schloss sie die Zelle ab --
                # das hiess „schliesst die Position ab" nur dort, wo keine
                # Teilposten folgten; bei Zaehlerpositionen stand sie
                # mittendrin. Jetzt ist ihr Platz immer derselbe, egal was
                # folgt: Name, woher, wie gerechnet.
                zeilen = [f"<b>{escape(item['category'])}</b>"]
                if angabenzeile:
                    zeilen.append(f"<font size=7.5 color='{self.leise_markup}'>"
                                  f"{angabenzeile}</font>")
                zeilen += [escape(z) for z in umlage]
                zelle = [Paragraph('<br/>'.join(zeilen),
                                   self.styles['TableCell'])]
                # Phase 61: Steht ein Rechenweg, kommt er als eigene kleine
                # Aufstellung dazu -- links der Schritt, rechts sein
                # Ergebnis, rechtsbündig untereinander. Vorher war jeder
                # Schritt ein Satz mit „=", und weil der nächste wieder mit
                # dem Zwischenergebnis anfing, stand jede Zahl zweimal.
                if schritte:
                    zelle.append(pdf_stil.rechenweg(schritte, self.stil, saetze))
                data.append([
                    zelle,
                    Paragraph(pdf_stil.geld(item['tenant_cost'], waehrung=False),
                              self.styles['TableCellRight'])
                ])
                
                table_style.extend([
                    ('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color),
                    ('TOPPADDING', (0, row_idx), (-1, row_idx), 9),
                    ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 4 if has_sub else 9),
                ])
                
                if not has_sub:
                    table_style.append(('LINEBELOW', (0, row_idx), (-1, row_idx), 0.5, COLOR_BORDER))
                
                row_idx += 1

                if folgeposten:
                    for i, sub in enumerate(folgeposten):
                        is_last = i == len(folgeposten) - 1
                        data.append([
                            Paragraph(escape(sub['description']),
                                      self.styles['Teilposten']),
                            Paragraph(pdf_stil.geld(sub['cost'], waehrung=False),
                                      self.styles['TableCellRight'])
                        ])
                        
                        table_style.extend([
                            ('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color),
                            ('TOPPADDING', (0, row_idx), (-1, row_idx), 2),
                            ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 8 if is_last else 2),
                        ])
                        
                        if is_last:
                            table_style.append(('LINEBELOW', (0, row_idx), (-1, row_idx), 0.5, COLOR_BORDER))
                        
                        row_idx += 1
                
                stripe_counter += 1
                
            # Subtotal Row
            data.append([
                Paragraph(f"Zwischensumme {section_name}",
                          self.styles['TotalCellRight']),
                Paragraph(pdf_stil.geld(section_data['total'], waehrung=False),
                          self.styles['TotalCellRight'])
            ])
            table_style.extend([
                ('TOPPADDING', (0, row_idx), (-1, row_idx), 8),
                ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 8),
                ('LINEABOVE', (0, row_idx), (-1, row_idx), 0.5, COLOR_MUTED),
                ('LINEBELOW', (0, row_idx), (-1, row_idx), 1, COLOR_BORDER),
            ])
            row_idx += 1
            
        # Phase 60: Die drei Schlusszeilen stehen **nicht mehr in der
        # Tabelle**. Dort waren sie die letzten Zeilen eines Satzes, der
        # ueber Seiten laeuft -- und landeten allein auf der naechsten
        # Seite, abgeschnitten von der Rechnung, zu der sie gehoeren. Jetzt
        # sind sie ein eigener, rechtsbuendiger Block wie in der Vorlage:
        # unteilbar, und er folgt der Tabelle, statt in ihr zu stecken.
        balance = total_amount - prepaid_amount
        if balance > 0:
            saldo_wort, saldo_farbe = 'Nachzahlung des Mieters', self.stil.nachzahlung
        elif balance < 0:
            saldo_wort, saldo_farbe = 'Guthaben des Mieters', self.stil.guthaben
        else:
            saldo_wort, saldo_farbe = 'Saldobetrag', None

        # Die Betragsspalte bleibt schmal, der Rest teilt sich den Platz.
        # 390 pt für den Text, 80 für den Betrag. Gemessen am längsten,
        # was vorkommt: ein Rechenschritt („732,00 € Rechnungsbetrag,
        # anteilig 275 von 366 Tagen = 550,00 €") braucht 267 pt, ein
        # Teilposten mit Personentagen 307, die Angabenzeile bei 7,5 pt
        # rund 300. Alles passt in eine Zeile.
        table = Table(data, colWidths=[390, 80], repeatRows=1)
        table.setStyle(TableStyle(table_style))
        elements.append(table)
        elements.append(Spacer(1, pdf_stil.M))
        elements.append(KeepTogether(pdf_stil.summenblock([
            ('Gesamtkosten der Periode', pdf_stil.geld(total_amount), False, None),
            ('Abzüglich geleistete Vorauszahlungen',
             '- ' + pdf_stil.geld(prepaid_amount), False, None),
            (saldo_wort, pdf_stil.geld(abs(balance)), True, saldo_farbe),
        ], self.stil, saetze, breite=320)))

        # R-NUM-03: der Mieter soll die Tageszahl nachrechnen koennen, statt
        # sie glauben zu muessen. Die Erlaeuterung steht nur da, wo ueberhaupt
        # anteilig gerechnet wurde.
        if anteilig_ausgewiesen:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(HINWEIS_TAGESKONVENTION, self.styles['Fussnote']))

        # F-115: fehlen Rechnungen fuer einen Teil des Zeitraums, sagt das
        # Blatt es dem Mieter, statt ein Guthaben als endgueltig zu zeigen.
        if vorbehalt:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(escape(vorbehalt), self.styles['Fussnote']))
        return elements

    def _block_heizung_co2(self, inhalt):
        """Heizkosten und CO2-Ausweis; leer ohne Heizzeile der Anlage."""
        # NK-060: der Heizkosten- und CO2-Abschnitt -- Verteilung, Stufe,
        # Vermieteranteil -- gehoert auf beide Wege des Dokuments, denn der
        # Vermieter sendet nur eine der beiden Fassungen.
        return self._heizung_co2_elemente(
            inhalt.line_items, inhalt.co2_ausweis, inhalt.landlord_share)

    def _block_ausweis_35a(self, inhalt):
        """Die Lohnanteile nach § 35a EStG; leer ohne Lohnanteile."""
        # NK-268: die Lohnanteile nach § 35a EStG, auf beiden Fassungen.
        return self._ausweis_35a_elemente(inhalt.ausweis_35a)

    def _block_belegliste(self, inhalt):
        """Die Belegliste, in der ausführlichen Fassung mit Beträgen."""
        # R-DOC-01 Punkt 8: die Belegliste gehoert auf beide Wege des
        # Dokuments -- der Vermieter sendet nur eine der beiden Fassungen,
        # also muss jede fuer sich die Zuordnung Position zu Beleg tragen.
        # NK-244: genau einmal; die ausfuehrliche Fassung mit Betraegen.
        return self._belegliste_elemente(
            inhalt.line_items, mit_betraegen=self.detailliert)

    def _block_zahlung(self, inhalt):
        """Zahlungssatz und Rückfragen, darin der GiroCode -- als ein Block.

        Satz und Kasten bleiben zusammen; passt der Block nicht mehr,
        rückt er als Ganzes auf die nächste Seite.
        """
        elements = [Spacer(1, 40)]
        # NK-248: die hinterlegte IBAN steht im Satz. NK-264: ich/wir nach
        # der Art des Vermieters, ohne Angabe neutral.
        saetze = anschreiben_saetze(vermieter_art())
        zahlungsblock = []
        if inhalt.balance > 0:
            zahlungsblock.append(Paragraph(
                zahlungssatz(saetze, vermieter_ausweis()[1]),
                self.styles['HeaderNormal']))
        zahlungsblock.append(Paragraph(saetze['rueckfragen'], self.styles['HeaderNormal']))
        if inhalt.girocode == 'zahlung':
            zahlungsblock.extend(self._block_girocode(inhalt))
        elements.append(KeepTogether(zahlungsblock))
        return elements

    def _block_girocode(self, inhalt):
        """Der GiroCode (EPC-QR), beim Zahlungshinweis oder auf dem Deckblatt.

        Nur bei Nachzahlung und mit Name und IBAN des Vermieters, sonst leer.
        """
        return build_girocode_elements(
            balance=inhalt.balance,
            tenant_name=self.tenant_name,
            apartment_name=self.apartment_name,
            start_date=self.start_date,
            end_date=self.end_date,
        )

    def _block_verbrauchsnachweise(self, inhalt):
        """Die Verbrauchsnachweise der ausführlichen Fassung, ab neuer Seite.

        Davor steht der Verweis „auf den folgenden Seiten“ -- er gehört zu
        diesem Block, denn er erscheint genau dann, wenn der Block erscheint.
        Beginnt der Block ohnehin auf einer frischen Seite (etwa direkt nach
        dem Deckblatt), entfallen Verweis und Umbruch: Der Verweis stünde
        sonst allein auf einer Seite und zeigte auf die nächste.
        """
        line_items = inhalt.line_items
        elements = []
        # NK-245: ohne Zaehlerzeile kein leerer Nachweisteil samt Umbruch.
        if self.detailliert and any(item.get('meter_details') for item in line_items):
            if not inhalt.seitenanfang:
                # Der Verweis klebte am GiroCode-Kasten darüber.
                elements.append(Spacer(1, pdf_stil.M))
                elements.append(Paragraph(
                    '<i>Detaillierte Verbrauchsnachweise auf den folgenden Seiten</i>',
                    self.styles['HeaderNormal']))
                elements.append(PageBreak())
        
            # ----------------------------------------------------
            # PAGE 2+: Detailed Consumption Breakdown
            # ----------------------------------------------------
            elements.append(Paragraph("Detaillierte Verbrauchsnachweise", self.styles['TitleBold']))
            elements.append(Spacer(1, 10))
        
            for item in line_items:
                md = item.get('meter_details')
                if not md:
                    continue
                
                unit = md.get('unit', '')
                tm = md.get('tenant_meter')
                mm = md.get('main_meter')
            
                # Draw a box for each metered category
                box_data = []
            
                # Header
                cat_name = item['category'].upper()
                meter_num_str = f"Zähler {tm['meter_number']}" if tm and tm.get('meter_number') else "Ohne eigenen Zähler"
                box_data.append([Paragraph(f"{cat_name} — {meter_num_str} ({self.apartment_name})", self.styles['MeterHeader']), ''])
            
                box_style = [
                    ('BACKGROUND', (0, 0), (-1, 0), self.stil.flaeche),
                    ('LINEBELOW', (0, 0), (-1, 0), 0.8, self.stil.linie),
                    ('SPAN', (0, 0), (-1, 0)),
                    ('TOPPADDING', (0, 0), (-1, 0), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ]
            
                row_idx = 1
            
                def format_date(d):
                    # Das blanke ``except`` hier hat auch KeyboardInterrupt und
                    # SystemExit gefangen (NK-042): wer den Container anhaelt,
                    # waehrend ein PDF gebaut wird, sah das Signal verschwinden und
                    # die Zeile stattdessen im Rohformat. Gemeint waren die zwei
                    # Faelle darunter -- eine Zeichenkette, die kein ISO-Datum ist
                    # (ValueError), und etwas, das gar keine Zeichenkette ist
                    # (TypeError). In beiden ist der Rohwert die bessere Anzeige
                    # als ein Abbruch mitten im Dokument.
                    if not d: return "-"
                    try: return datetime.fromisoformat(d).strftime('%d.%m.%Y')
                    except (ValueError, TypeError): return d
                
                def dt_offset(stichtag, offset):
                    # NK-218: ein Satz statt „Abweichung X Tage (Fenster Y
                    # Tage)“; das Warnzeichen davor kannte die Schrift nicht.
                    if offset <= 7:
                        return ""
                    farbe = '#A3312A' if offset > 14 else '#8A5300'
                    am = f" {format_date(stichtag)}" if stichtag else ""
                    return (f"<font color='{farbe}'>Zum Stichtag{am} liegt die nächste Ablesung "
                            f"{offset} Tage entfernt. Der Verbrauch dieser {offset} Tage ist geschätzt.</font>")
            
                # Tenant Meter Readings
                if tm and tm.get('status') != 'no_data':
                    rechts = self.styles['MeterTextRight']
                    if 'stand_beginn' in tm:
                        # NK-208: die Staende an den Grenzen des Zeitraums, nicht
                        # die Stuetzstellen dahinter -- Ende minus Anfang ist der
                        # Eigenverbrauch. Gerechnet wird mit den angezeigten,
                        # auf drei Stellen gerundeten Zahlen, damit die Zeile
                        # auf dem Papier aufgeht.
                        drei = Decimal('0.001')
                        anfang = Decimal(str(tm['stand_beginn'])).quantize(drei)
                        verbrauch = Decimal(str(tm['consumption'])).quantize(drei)
                        # NK-258: bei einem Zaehlerwechsel ist der Verbrauch
                        # (Endstand alt - Beginn) + (Ende - Anfangsstand neu).
                        wechsel = tm.get('zaehlerwechsel') or []
                        ende = anfang + verbrauch - sum(
                            (Decimal(str(w['endstand'])).quantize(drei)
                             - Decimal(str(w['anfangsstand'])).quantize(drei) for w in wechsel),
                            Decimal(0))

                        def wie(abgelesen):
                            return "abgelesen" if abgelesen else "berechnet"

                        box_data.append([Paragraph(f"Zählerstand Beginn {format_date(tm.get('target_start_date'))} ({wie(tm.get('beginn_abgelesen'))}):", self.styles['MeterText']), Paragraph(f"{self._deutsch(anfang, 3)} {unit}", rechts)])
                        for w in wechsel:
                            box_data.append([Paragraph(
                                f"Zählerwechsel {format_date(w['datum'])}: Endstand {escape(w['alt'])} "
                                f"{self._deutsch(w['endstand'], 3)}, Anfangsstand {escape(w['neu'])} "
                                f"{self._deutsch(w['anfangsstand'], 3)} {unit}", self.styles['MeterText']), ''])
                            box_style.append(('SPAN', (0, len(box_data) - 1), (-1, len(box_data) - 1)))
                            row_idx += 1
                        box_data.append([Paragraph(f"Zählerstand Ende {format_date(tm.get('target_end_date'))} ({wie(tm.get('ende_abgelesen'))}):", self.styles['MeterText']), Paragraph(f"{self._deutsch(ende, 3)} {unit}", rechts)])
                        box_data.append([Paragraph("Eigenverbrauch (beide Zähler):" if wechsel else "Eigenverbrauch (Ende − Beginn):", self.styles['MeterTextBold']), Paragraph(f"{self._deutsch(verbrauch, 3)} {unit}", self.styles['MeterTextBold'])])
                        ablesungen = [
                            f"{format_date(b['date'])}: {self._deutsch(b['total'], 3)}"
                            + (" (Zwischenablesung)" if b.get('zwischenablesung') else "")
                            for b in tm.get('basis_readings') or []
                        ]
                        if ablesungen:
                            box_data.append([Paragraph("<i>Zugrunde liegende Ablesungen: " + " · ".join(ablesungen) + "</i>", self.styles['SubTableCell']), ''])
                            box_style.append(('SPAN', (0, len(box_data) - 1), (-1, len(box_data) - 1)))
                            row_idx += 1
                    else:
                        # Gespeicherte Abrechnungen von vor NK-208 kennen die
                        # Stichtagswerte nicht; sie zeigen die Ablesungen wie damals.
                        cons = md.get('tenant_consumption')
                        cons_str = f"{cons:.1f}" if cons is not None else "N/A"
                        box_data.append([Paragraph(f"Ablesung: {format_date(tm['r_start']['date'])}", self.styles['MeterText']), Paragraph(f"{tm['r_start']['total']:.1f} {unit}", rechts)])
                        box_data.append([Paragraph(f"Ablesung: {format_date(tm['r_end']['date'])}", self.styles['MeterText']), Paragraph(f"{tm['r_end']['total']:.1f} {unit}", rechts)])
                        box_data.append([Paragraph("Eigenverbrauch:", self.styles['MeterTextBold']), Paragraph(f"{cons_str} {unit}", self.styles['MeterTextBold'])])

                    # Check for interpolation warning
                    if tm.get('is_interpolated'):
                        off_msg = ""
                        if tm['start_offset_days'] > 1:
                            off_msg += dt_offset(tm.get('target_start_date'), tm['start_offset_days'])
                        if tm['end_offset_days'] > 1:
                            if off_msg: off_msg += "<br/>"
                            off_msg += dt_offset(tm.get('target_end_date'), tm['end_offset_days'])
                        if off_msg:
                            box_data.append([Paragraph(f"<i>Hinweis: {stichtag_hinweis(tm)}<br/>{off_msg}</i>", self.styles['SubTableCell']), ''])
                            box_style.append(('SPAN', (0, row_idx+3), (-1, row_idx+3)))
                            row_idx += 1
                        
                    box_style.extend([
                        ('LINEBELOW', (0, row_idx+2), (-1, row_idx+2), 0.5, COLOR_BORDER),
                        ('BOTTOMPADDING', (0, row_idx+2), (-1, row_idx+2), 8),
                    ])
                    row_idx += 3
            
                # Allgemein Logic
                if mm and mm.get('status') != 'no_data':
                    main_c = md.get('main_consumption', 0)
                    sum_sub = md.get('sum_sub_consumption', 0)
                    allg = md.get('allgemein_consumption', 0)
                    quote = md.get('allgemein_quote')
                    zeilen = 3 if quote is None else 4

                    # Haus und Allgemein gelten fuer die ganze Rechnung (NK-213),
                    # nicht fuer den Zeitraum des Mieters -- der Kasten sagt es.
                    zeitraum = (f", {format_date(mm['target_start_date'])} bis {format_date(mm['target_end_date'])}"
                                if mm.get('target_start_date') and mm.get('target_end_date') else "")
                    box_data.append([Paragraph(f"Gesamtverbrauch Haus (Hauptzähler{zeitraum}):", self.styles['MeterText']), Paragraph(f"{main_c:.1f} {unit}", self.styles['MeterText'])])
                    box_data.append([Paragraph(f"Summe aller Wohnungen:", self.styles['MeterText']), Paragraph(f"{sum_sub:.1f} {unit}", self.styles['MeterText'])])
                    box_data.append([Paragraph(f"Allgemeinverbrauch (Haus − Wohnungen):", self.styles['MeterText']), Paragraph(f"{allg:.1f} {unit}", self.styles['MeterTextBold'])])
                    # NK-209: der Anteil, mit dem gerechnet wurde -- nach
                    # Personentagen, nicht 1/Zahl der Mieter. Gespeicherte
                    # Abrechnungen von davor kennen ihn nicht; dort fehlt die
                    # Zeile lieber, als dass sie etwas Falsches sagt.
                    # Beim Dualtarif wiegt die Quote die Abschnitte nach ihren
                    # Kosten in HT und NT, nicht nach der Menge (NK-213).
                    if quote is not None:
                        gewichtet = ", nach den Kosten von HT und NT gewichtet" if md.get('preis_ht') is not None else ""
                        box_data.append([Paragraph(f"Ihr Anteil am Allgemeinverbrauch ({self._deutsch(quote * 100)} %{gewichtet}):", self.styles['MeterText']), Paragraph(f"{self._deutsch(md.get('allgemein_anteil'), 1)} {unit}", self.styles['MeterTextBold'])])
                
                    if mm.get('is_interpolated'):
                        off_msg = ""
                        if mm['start_offset_days'] > 1:
                            off_msg += dt_offset(mm.get('target_start_date'), mm['start_offset_days'])
                        if mm['end_offset_days'] > 1:
                            if off_msg: off_msg += "<br/>"
                            off_msg += dt_offset(mm.get('target_end_date'), mm['end_offset_days'])
                        if off_msg:
                            box_data.append([Paragraph(f"<i>Hinweis Hauptzähler: {stichtag_hinweis(mm)}<br/>{off_msg}</i>", self.styles['SubTableCell']), ''])
                            box_style.append(('SPAN', (0, row_idx+zeilen), (-1, row_idx+zeilen)))
                            row_idx += 1
                        
                    box_style.extend([
                        ('LINEBELOW', (0, row_idx+zeilen-1), (-1, row_idx+zeilen-1), 0.5, COLOR_BORDER),
                        ('BOTTOMPADDING', (0, row_idx+zeilen-1), (-1, row_idx+zeilen-1), 8),
                    ])
                    row_idx += zeilen
                
                # Costs breakdown
                box_data.append([Paragraph("Kostenberechnung:", self.styles['MeterTextBold']), ''])
                box_style.append(('SPAN', (0, row_idx), (-1, row_idx)))
                row_idx += 1
            
                for sub in item.get('sub_items', []):
                    box_data.append([Paragraph(f"• {sub['description']}", self.styles['MeterText']), Paragraph(pdf_stil.geld(sub['cost']), self.styles['MeterText'])])
                    row_idx += 1
                
                box_data.append([Paragraph(f"GESAMT {cat_name}:", self.styles['MeterTextBold']), Paragraph(pdf_stil.geld(item['tenant_cost']), self.styles['MeterTextBold'])])
            
                box_style.extend([
                    ('BACKGROUND', (0, 1), (-1, -1), self.stil.flaeche),
                    ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ])
            
                # Wie oben: die Summe der Spalten passt in den Satz.
                t = Table(box_data, colWidths=[340, 130])
                t.setStyle(TableStyle(box_style))
                # Phase 61 (Durchsicht am 2026-10-22): Der Kasten bleibt
                # zusammen. Vorher rutschte die letzte Zeile -- „GESAMT
                # WASSERVERSORGUNG" samt Rahmenkante -- allein auf die
                # nächste Seite, während der Rest des Nachweises oben
                # stand. Passt er nicht mehr, fängt er auf der nächsten
                # Seite als Ganzes an.
                elements.append(KeepTogether([t, Spacer(1, 20)]))
        return elements
