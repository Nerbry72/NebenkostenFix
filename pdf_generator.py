from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus import PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
import zeit
from pdf_cover_page import build_cover_page_elements
from girocode_generator import build_girocode_elements
from geld import NULL
import betrkv
from zeitraum import HINWEIS_TAGESKONVENTION
import marke
from abrechnung_version import SOFTWARE_VERSION, REGEL_VERSION


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
    canvas.setFillColor(colors.grey)
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
                 detailliert=False):
        self.detailliert = detailliert
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
        self.styles.add(ParagraphStyle(name='TableCell', fontName='Helvetica', fontSize=9, leading=12, wordWrap='CJK'))
        self.styles.add(ParagraphStyle(name='TableCellRight', fontName='Helvetica', fontSize=9, leading=12, alignment=2, wordWrap='CJK'))
        self.styles.add(ParagraphStyle(name='SubTableCell', fontName='Helvetica', fontSize=8, leading=11, leftIndent=10, textColor=colors.HexColor('#4b5563'), wordWrap='CJK'))
        self.styles.add(ParagraphStyle(name='SectionHeader', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.white))
        self.styles.add(ParagraphStyle(name='TotalCell', fontName='Helvetica-Bold', fontSize=10, leading=14))
        self.styles.add(ParagraphStyle(name='TotalCellRight', fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=2))
        self.styles.add(ParagraphStyle(name='GrandTotalCell', fontName='Helvetica-Bold', fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='GrandTotalCellRight', fontName='Helvetica-Bold', fontSize=12, leading=16, alignment=2))
        self.styles.add(ParagraphStyle(name='Fussnote', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#4b5563')))
        self.styles.add(ParagraphStyle(name='MeterHeader', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=colors.white))
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
                        'anbieter': r.get('provider_name') or '-',
                        'dokument': r.get('doc_name') or None,
                        'rechnungsbetrag': r.get('rechnungsbetrag'),
                        'zeitanteilig': r.get('prorated_amount'),
                        'tage': None,
                    })
                continue
            if not item.get('invoice_number'):
                continue
            zeilen.append({
                'position': item['category'],
                'nummer': item['invoice_number'],
                'datum': self._format_datum(item.get('rechnungsdatum')),
                'anbieter': item.get('provider_name') or '-',
                'dokument': item.get('doc_name') or None,
                'rechnungsbetrag': item.get('invoice_total_amount'),
                'zeitanteilig': item.get('prorated_amount'),
                'tage': (item.get('overlap_days'), item.get('invoice_days')),
            })

        if not zeilen:
            return []

        kopf = [
            Paragraph("<b>Position</b>", self.styles['TableCell']),
            Paragraph("<b>Rechnung</b>", self.styles['TableCell']),
            Paragraph("<b>Anbieter</b>", self.styles['TableCell']),
            Paragraph("<b>Beleg</b>", self.styles['TableCell']),
        ]
        if mit_betraegen:
            kopf += [
                Paragraph("<b>Rechnungsbetrag (€)</b>", self.styles['TableCellRight']),
                Paragraph("<b>Zeitanteilig (€)</b>", self.styles['TableCellRight']),
            ]
        data = [kopf]
        for z in zeilen:
            rechnung = f"Nr. {z['nummer']}"
            if z['datum']:
                rechnung += f"<br/>vom {z['datum']}"
            row = [
                Paragraph(z['position'], self.styles['TableCell']),
                Paragraph(rechnung, self.styles['TableCell']),
                Paragraph(z['anbieter'], self.styles['TableCell']),
                Paragraph(z['dokument'] or '—', self.styles['TableCell']),
            ]
            if mit_betraegen:
                zeitanteilig = f"{z['zeitanteilig']:.2f}".replace('.', ',')
                if z['tage'] and z['tage'][0] and z['tage'][1] \
                        and z['tage'][0] < z['tage'][1]:
                    zeitanteilig += f" ({z['tage'][0]}/{z['tage'][1]} Tage)"
                row += [
                    Paragraph(
                        f"{z['rechnungsbetrag']:.2f}".replace('.', ','),
                        self.styles['TableCellRight']),
                    Paragraph(zeitanteilig, self.styles['TableCellRight']),
                ]
            data.append(row)

        breiten = [110, 90, 80, 100]
        if mit_betraegen:
            breiten += [50, 51]
        tabelle = Table(data, colWidths=breiten, repeatRows=1)
        tabelle.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return [
            Spacer(1, 20),
            Paragraph("Belegliste", self.styles['TitleBold']),
            tabelle,
        ]

    def _deutsch(self, wert, stellen=2):
        """Zahl im Sprachbild des Dokuments: Komma statt Punkt.

        Die Werte kommen gerundet aus dem Kern (R-NUM-01) -- hier wird nur
        angezeigt, nichts gerundet. Kein Tausenderpunkt: die Betragsspalte
        hat auch keinen.
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
                    f"{self._deutsch(co2_ausweis.get('kosten'))} € — "
                    f"davon "
                    f"{self._deutsch(co2_ausweis.get('mieter_anteil_euro'))} € "
                    f"auf dieses Mietverhältnis; der Vermieteranteil "
                    f"beträgt "
                    f"{self._deutsch(co2_ausweis.get('vermieter_anteil_euro'))} €.",
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
                        f"{self._deutsch(q.get('kosten'))} €.")
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
            elemente.append(Spacer(1, 12))
            elemente.append(Paragraph(
                "<b>Vermieteranteil (nicht auf die Mieter umgelegt)</b>",
                self.styles['TableCell']))
            for p in positionen:
                elemente.append(Paragraph(
                    f"{p.get('category')} — {p.get('description')}: "
                    f"{self._deutsch(p.get('amount'))} €.",
                    self.styles['TableCell']))
            elemente.append(Paragraph(
                f"Insgesamt beim Vermieter: "
                f"{self._deutsch((landlord_share or {}).get('total_amount'))} € "
                f"(Leerstand "
                f"{self._deutsch((landlord_share or {}).get('leerstand_amount'))} €, "
                f"Eigennutzung "
                f"{self._deutsch((landlord_share or {}).get('eigennutzung_amount'))} €).",
                self.styles['TableCell']))

        return elemente

    def generate(self, line_items, total_amount, prepaid_amount=NULL,
                 co2_ausweis=None, landlord_share=None, anschreiben=None):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=56.7, leftMargin=56.7,
                                topMargin=56.7, bottomMargin=56.7)
        
        elements = []
        
        # Prepend cover page (Deckblatt)
        balance = total_amount - prepaid_amount
        cover_elements = build_cover_page_elements(
            property_name=self.property_name,
            apartment_name=self.apartment_name,
            tenant_name=self.tenant_name,
            start_date=self.start_date,
            end_date=self.end_date,
            total_amount=total_amount,
            prepaid_amount=prepaid_amount,
            balance=balance,
            # NK-064: das Anschreiben des Vermieters spricht auf dem
            # Deckblatt statt des festen Grußes; ohne Vorlage wie gehabt.
            anschreiben=anschreiben,
        )
        elements.extend(cover_elements)
        
        start_fmt = datetime.fromisoformat(self.start_date).strftime('%d.%m.%Y')
        end_fmt = datetime.fromisoformat(self.end_date).strftime('%d.%m.%Y')
        creation_date = zeit.als_ortszeit(zeit.jetzt_utc(), '%d.%m.%Y')
        
        header_data = [
            [Paragraph(f"<b>{self.property_name}</b><br/>(Hausverwaltung / Vermieter)", self.styles['HeaderNormal']),
             Paragraph(f"Datum: {creation_date}", self.styles['HeaderRight'])]
        ]
        
        header_table = Table(header_data, colWidths=[300, 180])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ]))
        elements.append(header_table)
        
        elements.append(Paragraph("An:", self.styles['HeaderNormal']))
        elements.append(Paragraph(f"<b>{self.tenant_name}</b>", self.styles['HeaderNormal']))
        elements.append(Paragraph(f"Wohnung: {self.apartment_name}", self.styles['HeaderNormal']))
        elements.append(Spacer(1, 40))
        
        title_text = f"Nebenkostenabrechnung für den Zeitraum {start_fmt} bis {end_fmt}"
        elements.append(Paragraph(title_text, self.styles['TitleBold']))
        elements.append(Spacer(1, 20))
        
        # Categorization logic
        categories = {
            # Geldwerte kommen als Decimal herein (R-NUM-01, NK-036). Ein
            # Zwischenstand, der bei 0.0 anfaengt, wuerde beim ersten += einen
            # TypeError werfen -- genau das ist die Absicht: float und Euro
            # mischen sich hier nicht mehr.
            # Die Rubrik kommt aus dem Katalog (betrkv), nicht mehr aus
            # Stichwoertern (F-32, NK-121): dieselbe Quelle wie die
            # Analytics, dieselbe Zuordnung fuer gewachsene Namen.
            "Energie": {"items": [], "total": NULL},
            "Wasser & Abwasser": {"items": [], "total": NULL},
            "Betriebskosten": {"items": [], "total": NULL}
        }
        
        for item in line_items:
            rubrik = betrkv.rubrik(betrkv.zuordnung(item['category']))
            categories[rubrik]["items"].append(item)
            categories[rubrik]["total"] += item['tenant_cost']

        data = [
            [Paragraph("<b>Kostenart</b>", self.styles['TableCell']), 
             Paragraph("<b>Abrechnungszeitraum / Anbieter</b>", self.styles['TableCell']), 
             Paragraph("<b>Umlage-Details</b>", self.styles['TableCell']), 
             Paragraph("<b>Betrag (€)</b>", self.styles['TableCellRight'])]
        ]
        
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#d1d5db')),
        ]
        
        row_idx = 1
        anteilig_ausgewiesen = False
        
        for section_name, section_data in categories.items():
            if not section_data["items"]:
                continue
                
            # Section Header
            data.append([Paragraph(f"{section_name}", self.styles['SectionHeader']), '', '', ''])
            table_style.extend([
                ('SPAN', (0, row_idx), (-1, row_idx)),
                ('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#4b5563')),
                ('TOPPADDING', (0, row_idx), (-1, row_idx), 6),
                ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 6),
            ])
            row_idx += 1
            
            stripe_counter = 0
            
            for item in section_data["items"]:
                provider = item.get('provider_name', '-') or '-'
                period_str = f"{item['period']}<br/>Anbieter: {provider}"
                # R-DOC-01 Punkt 8: der Belegverweis direkt an der Position
                # -- fuer jede Zeile, die aus genau einer Rechnung stammt.
                # Mehrere Rechnungen (Heizung, D-47) zaehlen ueber die
                # Belegliste am Ende des Dokuments.
                if item.get('invoice_number'):
                    verweis = f"Rechnung Nr. {item['invoice_number']}"
                    datum = self._format_datum(item.get('rechnungsdatum'))
                    if datum:
                        verweis += f" vom {datum}"
                    period_str += f"<br/>{verweis}"
                
                details = item['description']
                # R-DOC-01 Punkt 6/7: der Rechenweg der Zeile als Satz.
                # Steht er, tragen die Tage ihn selbst -- der alte
                # Zeitanteil-Anhang wuerde dasselbe zweimal sagen.
                schritte = item.get('rechenweg') or []
                if (not schritte and item.get('overlap_days')
                        and item.get('invoice_days')
                        and item['overlap_days'] < item['invoice_days']):
                    details += f", anteilig {item['overlap_days']} von {item['invoice_days']} Tagen"
                    anteilig_ausgewiesen = True

                # Ein Teilposten, der nur die Zeilenbeschreibung wiederholt
                # (qm, Personen), schweigt, wenn der Rechenweg die Zeile
                # schon herzuleiten: derselbe Satz steht nicht zweimal unter
                #einander. Echte Teilposten (Grund-/Verbrauchsteil,
                # Eigenverbrauch, Allgemeinanteil) bleiben.
                folgeposten = [
                    s for s in item.get('sub_items') or []
                    if not (schritte and s['description'] == item['description'])
                ]
                has_sub = bool(folgeposten) or bool(schritte)
                
                bg_color = colors.HexColor('#ffffff') if stripe_counter % 2 == 0 else colors.HexColor('#f9fafb')
                
                # Main row
                main_details = "" if has_sub else details
                data.append([
                    Paragraph(item['category'], self.styles['TableCell']),
                    Paragraph(period_str, self.styles['TableCell']),
                    Paragraph(main_details, self.styles['TableCell']),
                    Paragraph(f"{item['tenant_cost']:.2f}".replace('.', ','), self.styles['TableCellRight'])
                ])
                
                table_style.extend([
                    ('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color),
                    ('TOPPADDING', (0, row_idx), (-1, row_idx), 8),
                    ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 4 if has_sub else 8),
                ])
                
                if not has_sub:
                    table_style.append(('LINEBELOW', (0, row_idx), (-1, row_idx), 0.5, colors.HexColor('#e5e7eb')))
                
                row_idx += 1

                # Die Rechenschritte unter der Zeile (R-DOC-01 Punkt 6/7):
                # ohne eigene Betragsspalte -- das Ergebnis steht im Satz,
                # und der Zeilenbetrag rechts darueber bleibt die eine Zahl,
                # auf die alles hinauslaeuft. Endet die Zeile mit ihnen (qm,
                # Personen), schliesst der letzte die Trennlinie ab.
                for i, schritt in enumerate(schritte):
                    schliesst_ab = (i == len(schritte) - 1 and not folgeposten)
                    data.append([
                        '',
                        '',
                        Paragraph(f"↳ {schritt}", self.styles['SubTableCell']),
                        ''
                    ])

                    table_style.extend([
                        ('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color),
                        ('TOPPADDING', (0, row_idx), (-1, row_idx), 2),
                        ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 8 if schliesst_ab else 2),
                    ])

                    if schliesst_ab:
                        table_style.append(('LINEBELOW', (0, row_idx), (-1, row_idx), 0.5, colors.HexColor('#e5e7eb')))

                    row_idx += 1

                if folgeposten:
                    for i, sub in enumerate(folgeposten):
                        is_last = i == len(folgeposten) - 1
                        prefix = "↳ "
                        data.append([
                            '', 
                            '', 
                            Paragraph(f"{prefix}{sub['description']}", self.styles['SubTableCell']), 
                            Paragraph(f"{sub['cost']:.2f}".replace('.', ','), self.styles['TableCellRight'])
                        ])
                        
                        table_style.extend([
                            ('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color),
                            ('TOPPADDING', (0, row_idx), (-1, row_idx), 2),
                            ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 8 if is_last else 2),
                        ])
                        
                        if is_last:
                            table_style.append(('LINEBELOW', (0, row_idx), (-1, row_idx), 0.5, colors.HexColor('#e5e7eb')))
                        
                        row_idx += 1
                
                stripe_counter += 1
                
            # Subtotal Row
            data.append([
                '', 
                '', 
                Paragraph(f"Zwischensumme {section_name}:", self.styles['TotalCell']), 
                Paragraph(f"{section_data['total']:.2f}".replace('.', ','), self.styles['TotalCellRight'])
            ])
            table_style.extend([
                ('TOPPADDING', (0, row_idx), (-1, row_idx), 8),
                ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 8),
                ('LINEABOVE', (0, row_idx), (-1, row_idx), 1, colors.HexColor('#9ca3af')),
                ('LINEBELOW', (0, row_idx), (-1, row_idx), 1, colors.HexColor('#e5e7eb')),
            ])
            row_idx += 1
            
        # Grand Total Rows
        data.append([
            '', 
            '', 
            Paragraph("Gesamtkosten der Periode:", self.styles['TotalCell']), 
            Paragraph(f"{total_amount:.2f}".replace('.', ','), self.styles['TotalCellRight'])
        ])
        
        balance = total_amount - prepaid_amount
        
        data.append([
            '', 
            '', 
            Paragraph("Abzüglich geleistete Vorauszahlungen:", self.styles['TotalCell']), 
            Paragraph(f"- {prepaid_amount:.2f}".replace('.', ','), self.styles['TotalCellRight'])
        ])
        
        balance_label = "Nachzahlung des Mieters:" if balance > 0 else ("Guthaben des Mieters:" if balance < 0 else "Saldobetrag:")
        
        data.append([
            '', 
            '', 
            Paragraph(balance_label, self.styles['GrandTotalCell']), 
            Paragraph(f"{balance:.2f}".replace('.', ','), self.styles['GrandTotalCellRight'])
        ])
        
        table_style.extend([
            ('TOPPADDING', (0, row_idx), (-1, row_idx), 10),
            ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 10),
            ('LINEABOVE', (0, row_idx), (-1, row_idx), 2, colors.black),
            ('TOPPADDING', (0, row_idx+1), (-1, row_idx+1), 5),
            ('BOTTOMPADDING', (0, row_idx+1), (-1, row_idx+1), 10),
            ('LINEBELOW', (0, row_idx+1), (-1, row_idx+1), 1, colors.HexColor('#9ca3af')),
            ('TOPPADDING', (0, row_idx+2), (-1, row_idx+2), 14),
            ('BOTTOMPADDING', (0, row_idx+2), (-1, row_idx+2), 14),
            ('LINEBELOW', (0, row_idx+2), (-1, row_idx+2), 2, colors.black),
            ('BACKGROUND', (0, row_idx+2), (-1, row_idx+2), colors.HexColor('#f9fafb')),
        ])
        
        # Adjust column widths: category (110), period (130), details (170), amount (70) = 480
        table = Table(data, colWidths=[110, 130, 170, 70])
        table.setStyle(TableStyle(table_style))
        
        elements.append(table)

        # R-NUM-03: der Mieter soll die Tageszahl nachrechnen koennen, statt
        # sie glauben zu muessen. Die Erlaeuterung steht nur da, wo ueberhaupt
        # anteilig gerechnet wurde.
        if anteilig_ausgewiesen:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(HINWEIS_TAGESKONVENTION, self.styles['Fussnote']))

        # NK-060: der Heizkosten- und CO2-Abschnitt -- Verteilung, Stufe,
        # Vermieteranteil -- gehoert auf beide Wege des Dokuments, denn der
        # Vermieter sendet nur eine der beiden Fassungen.
        elements.extend(self._heizung_co2_elemente(
            line_items, co2_ausweis, landlord_share))

        # R-DOC-01 Punkt 8: die Belegliste gehoert auf beide Wege des
        # Dokuments -- der Vermieter sendet nur eine der beiden Fassungen,
        # also muss jede fuer sich die Zuordnung Position zu Beleg tragen.
        elements.extend(self._belegliste_elemente(line_items))

        elements.append(Spacer(1, 40))
        
        if balance > 0:
            elements.append(Paragraph("Bitte überweisen Sie den ausstehenden Betrag innerhalb von 14 Tagen auf das bekannte Konto.", self.styles['HeaderNormal']))
        elements.append(Paragraph("Bei Fragen zur Abrechnung stehen wir Ihnen gerne zur Verfügung.", self.styles['HeaderNormal']))
        

        if self.detailliert:
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
                meter_num_str = f"Zähler {tm['meter_number']}" if tm and tm.get('meter_number') else "Ohne eigener Zähler"
                box_data.append([Paragraph(f"{cat_name} — {meter_num_str} ({self.apartment_name})", self.styles['MeterHeader']), ''])
            
                box_style = [
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
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
                
                def dt_offset(msg, offset, span):
                    if offset > 14:
                        return f"<font color='red'>⚠️ Abweichung: {offset} Tage (Fenster: {span} Tage)</font>"
                    elif offset > 7:
                        return f"<font color='#d97706'>Toleranz verwendet (Abweichung: {offset} Tage)</font>"
                    return ""
            
                # Tenant Meter Readings
                if tm and tm.get('status') != 'no_data':
                    s_date = format_date(tm['r_start']['date'])
                    e_date = format_date(tm['r_end']['date'])
                    s_val = tm['r_start']['total']
                    e_val = tm['r_end']['total']
                    cons = md.get('tenant_consumption')
                    cons_str = f"{cons:.1f}" if cons is not None else "N/A"
                
                    box_data.append([Paragraph(f"Ablesung Anfang: {s_date}", self.styles['MeterText']), Paragraph(f"{s_val:.1f} {unit}", self.styles['MeterTextRight'] if 'MeterTextRight' in self.styles else self.styles['MeterText'])])
                    box_data.append([Paragraph(f"Ablesung Ende: {e_date}", self.styles['MeterText']), Paragraph(f"{e_val:.1f} {unit}", self.styles['MeterTextRight'] if 'MeterTextRight' in self.styles else self.styles['MeterText'])])
                    box_data.append([Paragraph(f"Eigenverbrauch:", self.styles['MeterTextBold']), Paragraph(f"{cons_str} {unit}", self.styles['MeterTextBold'])])
                
                    # Check for interpolation warning
                    if tm.get('is_interpolated'):
                        off_msg = ""
                        if tm['start_offset_days'] > 1:
                            off_msg += dt_offset("Start", tm['start_offset_days'], tm['reading_span_days'])
                        if tm['end_offset_days'] > 1:
                            if off_msg: off_msg += "<br/>"
                            off_msg += dt_offset("Ende", tm['end_offset_days'], tm['reading_span_days'])
                        if off_msg:
                            box_data.append([Paragraph(f"<i>Hinweis: Stichtagswert wurde interpoliert.<br/>{off_msg}</i>", self.styles['SubTableCell']), ''])
                            box_style.append(('SPAN', (0, row_idx+3), (-1, row_idx+3)))
                            row_idx += 1
                        
                    box_style.extend([
                        ('LINEBELOW', (0, row_idx+2), (-1, row_idx+2), 0.5, colors.HexColor('#d1d5db')),
                        ('BOTTOMPADDING', (0, row_idx+2), (-1, row_idx+2), 8),
                    ])
                    row_idx += 3
            
                # Allgemein Logic
                if mm and mm.get('status') != 'no_data':
                    main_c = md.get('main_consumption', 0)
                    sum_sub = md.get('sum_sub_consumption', 0)
                    allg = md.get('allgemein_consumption', 0)
                    pers = md.get('active_tenants')
                    if not pers:
                        pers = 1
                
                    box_data.append([Paragraph(f"Gesamtverbrauch Haus (Hauptzähler):", self.styles['MeterText']), Paragraph(f"{main_c:.1f} {unit}", self.styles['MeterText'])])
                    box_data.append([Paragraph(f"Summe aller Wohnungen:", self.styles['MeterText']), Paragraph(f"{sum_sub:.1f} {unit}", self.styles['MeterText'])])
                    box_data.append([Paragraph(f"Allgemeinverbrauch (Haus − Wohnungen):", self.styles['MeterText']), Paragraph(f"{allg:.1f} {unit}", self.styles['MeterTextBold'])])
                    box_data.append([Paragraph(f"Ihr Anteil am Allgemeinverbrauch (1/{pers}):", self.styles['MeterText']), Paragraph(f"{(allg/pers):.1f} {unit}", self.styles['MeterTextBold'])])
                
                    if mm.get('is_interpolated'):
                        off_msg = ""
                        if mm['start_offset_days'] > 1:
                            off_msg += dt_offset("Start", mm['start_offset_days'], mm['reading_span_days'])
                        if mm['end_offset_days'] > 1:
                            if off_msg: off_msg += "<br/>"
                            off_msg += dt_offset("Ende", mm['end_offset_days'], mm['reading_span_days'])
                        if off_msg:
                            box_data.append([Paragraph(f"<i>Hinweis Hauptzähler: Stichtagswert wurde interpoliert.<br/>{off_msg}</i>", self.styles['SubTableCell']), ''])
                            box_style.append(('SPAN', (0, row_idx+4), (-1, row_idx+4)))
                            row_idx += 1
                        
                    box_style.extend([
                        ('LINEBELOW', (0, row_idx+3), (-1, row_idx+3), 0.5, colors.HexColor('#d1d5db')),
                        ('BOTTOMPADDING', (0, row_idx+3), (-1, row_idx+3), 8),
                    ])
                    row_idx += 4
                
                # Costs breakdown
                box_data.append([Paragraph("Kostenberechnung:", self.styles['MeterTextBold']), ''])
                box_style.append(('SPAN', (0, row_idx), (-1, row_idx)))
                row_idx += 1
            
                for sub in item.get('sub_items', []):
                    box_data.append([Paragraph(f"• {sub['description']}", self.styles['MeterText']), Paragraph(f"{sub['cost']:.2f} €".replace('.', ','), self.styles['MeterText'])])
                    row_idx += 1
                
                box_data.append([Paragraph(f"GESAMT {cat_name}:", self.styles['MeterTextBold']), Paragraph(f"{item['tenant_cost']:.2f} €".replace('.', ','), self.styles['MeterTextBold'])])
            
                box_style.extend([
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ])
            
                t = Table(box_data, colWidths=[350, 130])
                t.setStyle(TableStyle(box_style))
                elements.append(t)
                elements.append(Spacer(1, 20))
            
            # ----------------------------------------------------
            # Belegliste (R-DOC-01 Punkt 8) -- ersetzt die fruehere Tabelle
            # "Verwendete Rechnungen": dieselben Betraege, aber je Rechnung
            # und mit Nummer, Datum, Anbieter und Dokumentseite.
            # ----------------------------------------------------
            elements.extend(
                self._belegliste_elemente(line_items, mit_betraegen=True))
        

        # GiroCode (EPC-QR) — only rendered for Nachzahlung (balance > 0)
        girocode_elements = build_girocode_elements(
            balance=balance,
            tenant_name=self.tenant_name,
            apartment_name=self.apartment_name,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        elements.extend(girocode_elements)
        
        doc.build(elements, onFirstPage=_fuss_zeichnen, onLaterPages=_fuss_zeichnen)
        
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
