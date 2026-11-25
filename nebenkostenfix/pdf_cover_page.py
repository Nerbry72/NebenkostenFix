"""Blatt 1: der Brief an den Mieter (Phase 60, Vorlage aus Issue #35).

Dieses Blatt ist **ein Brief**, kein Kennzahlenblatt. Die Vorlage des
Melders gibt die Reihenfolge vor, und sie wird hier eingehalten:

    Anschrift Mieter                       Anschrift Vermieter

                                           Ort, Datum

    Nebenkostenabrechnung JJJJ
    Objekt – Wohnung
    Abrechnungszeitraum: … bis …

    Anrede,

    Brieftext des Vermieters.

    Ihr Anteil an den Nebenkosten
      Ihre Nebenkosten:        …
      Ihre Vorauszahlungen:  - …
      Nachzahlung:             …

    Gruß des Vermieters

    ______________________
    Vermietername

Keine Flächen, keine Kästen, keine Linien ausser der Unterschriftslinie.
Ein Brief, den ein Mieter in die Hand nimmt, soll wie ein Brief aussehen
und nicht wie ein Formular -- deshalb ist der Zahlenblock hier schlicht
gesetzt, obwohl dieselbe Funktion auf den Tabellenblättern eine Fläche
bekommt.

**Der Zahlenblock steht zwischen Brieftext und Gruß.** Der Gruß gehört dem
Vermieter (NK-064), und ein Block hinter dem Gruß stünde hinter der
Unterschrift; ``anschreiben.teile`` trennt deshalb Körper und Gruß.

Alle Werte -- Farben, Schriftgrade, Abstände -- kommen aus ``pdf_stil``.
"""

import re
from datetime import datetime

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak
# Bandit-Ausnahme: maskiert Text fuer reportlab, parst kein XML
from xml.sax.saxutils import escape  # nosec B406

from nebenkostenfix import anschrift as anschriften, vermieter_logo, zeit
from nebenkostenfix import pdf_stil
from nebenkostenfix.anschreiben import absaetze, anrede, teile
from nebenkostenfix.geld import NULL

# Bestand: der Detailteil importiert diese Namen seit NK-177 von hier.
COLOR_DARK = pdf_stil.STIL.text
COLOR_MUTED = pdf_stil.STIL.leise
COLOR_BORDER = pdf_stil.STIL.linie
COLOR_HEAD_BG = pdf_stil.STIL.flaeche
COLOR_LIGHT_BG = pdf_stil.STIL.flaeche
COLOR_GREEN = pdf_stil.STIL.guthaben
COLOR_RED = pdf_stil.STIL.nachzahlung

#: Eine deutsche Postzeile: fünf Ziffern, dann der Ort.
_PLZ_ORT = re.compile(r'^\d{5}\s+(.+)$')


def ort_aus(anschrift_text) -> str:
    """Der Ort aus der letzten Zeile einer Anschrift, sonst nichts.

    Für die Zeile „Ort, Datum" der Vorlage. Passt die letzte Zeile nicht
    auf „PLZ Ort", bleibt der Ort weg -- dann steht nur das Datum da. Ein
    geratener Ort auf einem Brief wäre schlimmer als keiner.
    """
    zeilen = anschriften.zeilen(anschrift_text)
    treffer = _PLZ_ORT.match(zeilen[-1]) if zeilen else None
    return treffer.group(1).strip() if treffer else ''


def _anschrift(name, anschrift_text, saetze):
    """Name und Anschrift als ein Absatz -- so bleibt der Block zusammen."""
    zeilen = [escape(name)] if name else []
    zeilen += [escape(z) for z in anschriften.zeilen(anschrift_text)]
    return Paragraph('<br/>'.join(zeilen), saetze['Anschrift'])


def build_cover_page_elements(
    property_name,
    apartment_name,
    tenant_name,
    start_date,
    end_date,
    total_amount,
    prepaid_amount,
    balance,
    anschreiben=None,
    vermieter_name='',
    tenant_anrede=None,
    mieter_anschrift=None,
    vermieter_anschrift=None,
    girocode=(),
):
    """Blatt 1 als Liste von Flowables, mit Seitenumbruch am Ende.

    Args:
        property_name: Name des Objekts (etwa „Lindenstraße 12")
        apartment_name: Name der Wohnung (etwa „EG links")
        tenant_name: Name des Mieters
        tenant_anrede: eigene Anrede des Mieters (NK-264), sonst neutral
        start_date, end_date: ISO-Daten des Abrechnungszeitraums
        total_amount, prepaid_amount, balance: die drei Zahlen des Ergebnisses
        anschreiben: die Vorlage des Vermieters (NK-064), sonst Vorgabetext
        vermieter_name: Name des Vermieters (NK-210); leer zeigt die Rolle
        mieter_anschrift: die Anschrift, an die dieses Blatt geht (Phase 58)
        vermieter_anschrift: die eigene Anschrift als Absender
        girocode: Flowables des GiroCodes, die unter „Ihr Anteil“ stehen
            sollen; leer (Standard) heißt, er steht beim Zahlungshinweis
            oder gar nicht

    Returns:
        Liste von Flowables, mit einem PageBreak am Ende
    """
    s = pdf_stil.STIL
    saetze = pdf_stil.stile(s)
    elemente = []

    anfang = datetime.fromisoformat(start_date).strftime('%d.%m.%Y')
    ende = datetime.fromisoformat(end_date).strftime('%d.%m.%Y')
    heute = zeit.als_ortszeit(zeit.jetzt_utc(), '%d.%m.%Y')
    jahr = datetime.fromisoformat(end_date).strftime('%Y')
    absender_name = vermieter_name or 'Hausverwaltung / Vermieter'

    # --- Die beiden Anschriften nebeneinander ---
    logo = vermieter_logo.deckblatt_bild()
    rechts = [_anschrift(absender_name, vermieter_anschrift, saetze)]
    if logo:
        rechts.insert(0, logo)
    kopf = Table([[_anschrift(tenant_name, mieter_anschrift, saetze), rechts]],
                 colWidths=[pdf_stil.SATZBREITE * 0.55,
                            pdf_stil.SATZBREITE * 0.45])
    kopf.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elemente += [kopf, Spacer(1, pdf_stil.XXL)]

    # --- Ort, Datum -- rechts, wie in der Vorlage ---
    ort = ort_aus(vermieter_anschrift)
    elemente.append(Paragraph(
        escape(f"{ort}, {heute}" if ort else heute),
        ParagraphStyle('NKOrtDatum', parent=saetze['Text'], alignment=2)))
    elemente.append(Spacer(1, pdf_stil.XXL))

    # --- Betreff ---
    elemente.append(Paragraph(f"Nebenkostenabrechnung {jahr}", saetze['Betreff']))
    elemente.append(Spacer(1, pdf_stil.S))
    elemente.append(Paragraph(
        f"{escape(property_name)} – {escape(apartment_name)}", saetze['Text']))
    elemente.append(Paragraph(
        f"Abrechnungszeitraum: {anfang} bis {ende}", saetze['Text']))
    # Zwei Leerzeilen zwischen Betreff und Anrede -- so steht es in
    # DIN 5008 und so sieht ein Brief aus. XL las sich gedrängt.
    elemente.append(Spacer(1, pdf_stil.XXL))

    # --- Der Brief, Körper ---
    if anschreiben:
        koerper, gruss = teile(anschreiben)
    else:
        koerper, gruss = (
            f"{anrede(tenant_name, tenant_anrede)}\n\n"
            f"anbei übersenden wir Ihnen die Nebenkostenabrechnung für die "
            f"Nebenkostenperiode {jahr}. Die Einzelheiten entnehmen Sie bitte "
            f"der beigefügten Aufstellung.",
            'Mit freundlichen Grüßen')
    for absatz in absaetze(koerper):
        elemente.append(Paragraph(absatz, saetze['Text']))
        elemente.append(Spacer(1, pdf_stil.M))

    # --- Ihr Anteil an den Nebenkosten ---
    if balance < 0:
        bezeichnung, farbe, betrag = 'Guthaben:', s.guthaben, abs(balance)
    elif balance > 0:
        bezeichnung, farbe, betrag = 'Nachzahlung:', s.nachzahlung, balance
    else:
        bezeichnung, farbe, betrag = 'Saldo:', None, NULL

    elemente.append(Spacer(1, pdf_stil.M))
    elemente.append(Paragraph('Ihr Anteil an den Nebenkosten',
                              saetze['Zwischentitel']))
    elemente.append(Spacer(1, pdf_stil.M))
    elemente.append(pdf_stil.summenblock([
        ('Ihre Nebenkosten:', pdf_stil.geld(total_amount), False, None),
        ('Ihre Vorauszahlungen:', '- ' + pdf_stil.geld(prepaid_amount),
         False, None),
        (bezeichnung, pdf_stil.geld(betrag), True, farbe),
    ], s, saetze, breite=300, ausrichtung='LEFT', schlicht=True))
    # Wahlweise der GiroCode direkt unter dem Betrag (Layout „deckblatt“).
    elemente.extend(girocode)
    elemente.append(Spacer(1, pdf_stil.XL))

    # --- Gruß und Unterschrift ---
    for absatz in absaetze(gruss):
        elemente.append(Paragraph(absatz, saetze['Text']))
    elemente.append(Spacer(1, pdf_stil.XXL + pdf_stil.M))
    elemente.append(Paragraph('_________________________________',
                              saetze['Text']))
    elemente.append(Paragraph(escape(absender_name), saetze['Text']))

    elemente.append(PageBreak())
    return elemente
