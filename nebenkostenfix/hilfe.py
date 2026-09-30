"""Hilfe in der App: Kurzanleitung zum Ausdrucken (NK-158, F-88).

Die Führung erklärte bis NK-158 die Software, nicht die Aufgabe. Der
Hilfebereich der Oberfläche (``tab-hilfe`` in ``static/index.html``) erklärt
die Grundlagen; die Begriffe kommen aus ``docs/glossar.md`` § 8 über
``static/hilfe-begriffe.json``. Dieses Modul liefert dazu die
**Kurzanleitung** als PDF: zehn Schritte, große Schrift, eine Aufgabe je
Seite -- für den, der lieber auf Papier neben dem Rechner liest.

    GET /api/hilfe/kurzanleitung.pdf
"""

from __future__ import annotations

import io
from html import escape

from nebenkostenfix import marke

# (Titel, [Absätze]); ein Absatz, der mit "• " beginnt, ist ein Listenpunkt.
KURZANLEITUNG = [
    ('Ihre Nebenkostenabrechnung mit ' + marke.PRODUKT, [
        'Diese Anleitung führt Sie in zehn Schritten von der leeren Anwendung zur fertigen '
        'Abrechnung für Ihre Mieter. Jede Seite ist eine Aufgabe.',
        'Einmal im Jahr stellen Sie den Vorauszahlungen Ihrer Mieter die tatsächlichen '
        'Betriebskosten gegenüber. Waren die Kosten höher, zahlt der Mieter nach; waren sie '
        'niedriger, bekommt er Geld zurück.',
        'Die Anwendung rechnet für Sie, prüft vorher, was fehlt, und erstellt die '
        'Abrechnung als PDF mit Rechenweg und Belegliste.',
        'Tipp: Mit „Beispiel anlegen“ (Schritt 0 der Ersten Schritte auf der Übersicht) sehen '
        'Sie ein fertiges Beispielhaus mit Abrechnung, bevor Sie Ihre eigenen Daten eingeben. '
        '„Beispiel löschen“ nimmt es wieder heraus.',
    ]),
    ('1. Was Sie vorher sammeln', [
        '• Die Mietverträge: Wohnfläche jeder Wohnung, vereinbarte Vorauszahlung, welche '
        'Kosten umgelegt werden dürfen.',
        '• Alle Rechnungen des Jahres: Grundsteuerbescheid, Wasser und Abwasser, Müllabfuhr, '
        'Versicherung, Hauswart, Allgemeinstrom, Schornsteinfeger, Heizung und Wartung.',
        '• Die Zählerstände zum Stichtag, meist der 31. Dezember, und bei jedem Mieterwechsel.',
        '• Ein- und Auszugsdaten Ihrer Mieter und wie viele Personen im Haushalt leben.',
        '• Die Vorauszahlungen, die jeder Mieter tatsächlich gezahlt hat (Kontoauszüge).',
    ]),
    ('2. Immobilie und Wohnungen anlegen', [
        'Unter „Immobilien“ legen Sie Ihr Haus an und darin jede vermietete Wohnung mit ihrer '
        'Wohnfläche in m². Nach der Wohnfläche werden die meisten Kosten verteilt.',
        'Haben Sie Ihre Wohnungen schon in Excel? Dann „Aus Excel importieren“: Vorlage '
        'herunterladen, ausfüllen, hochladen.',
    ]),
    ('3. Mieter anlegen', [
        'Unter „Mieter“ legen Sie für jede Wohnung den Mieter mit Einzugsdatum an. Zieht '
        'jemand aus, tragen Sie das Auszugsdatum ein und legen den neuen Mieter an.',
        'Im Kostenprofil jedes Mieters steht, wie er an jeder Kostenart beteiligt ist: nach '
        'Wohnfläche, nach Personen, nach eigenem Zähler oder gar nicht.',
    ]),
    ('4. Rechnungen erfassen', [
        'Unter „Rechnungen & Belege“ erfassen Sie jede Rechnung des Jahres mit Kostenart, '
        'Betrag und Zeitraum. Den Beleg können Sie als PDF oder Foto dazulegen.',
        'Viele Rechnungen auf einmal: „Als Tabelle erfassen“ — Zeile für Zeile wie in Excel, '
        'mit Enter in die nächste Zeile.',
        'Umlegen dürfen Sie nur Betriebskosten nach § 2 Betriebskostenverordnung. Reparaturen, '
        'Verwaltung und Rücklagen gehören nicht in die Abrechnung.',
    ]),
    ('5. Zähler und Ablesungen', [
        'Nur nötig, wenn Kosten nach Verbrauch verteilt werden, etwa Wasser oder Heizung mit '
        'eigenen Zählern in den Wohnungen.',
        'Legen Sie unter „Zähler & Ablesungen“ jeden Zähler an und erfassen Sie die Stände '
        'zum Stichtag. Bei einem Mieterwechsel lesen Sie am Tag des Wechsels ab '
        '(Zwischenablesung).',
    ]),
    ('6. Vorauszahlungen erfassen', [
        'Unter „Zahlungen“ erfassen Sie, was jeder Mieter auf die Nebenkosten vorausgezahlt '
        'hat. Für regelmäßige Zahlungen genügt ein Eintrag mit „Monatlich wiederholen“.',
        'Die Vorauszahlungen werden in der Abrechnung von den Kosten abgezogen.',
    ]),
    ('7. Abrechnung erstellen', [
        'Unter „Abrechnungen“ zeigt die Anwendung, welche Mieter abgerechnet werden können. '
        'Wählen Sie einen Mieter und den Zeitraum und sehen Sie sich die Vorschau an.',
        'Die Vorschau sagt in einem Satz, was das Ergebnis für den Mieter bedeutet: '
        'Nachzahlung oder Guthaben, und warum.',
        'Stimmt alles, erstellen Sie das PDF. Die Abrechnung wird damit festgesetzt und '
        'kann später nur noch als neue Fassung berichtigt werden.',
    ]),
    ('8. Abrechnung zustellen — die Frist', [
        'Die Abrechnung muss dem Mieter spätestens zwölf Monate nach Ende des '
        'Abrechnungszeitraums zugehen (§ 556 Abs. 3 BGB). Für das Jahr 2025 also bis zum '
        '31. Dezember 2026.',
        'Kommt sie zu spät, können Sie keine Nachzahlung mehr verlangen; ein Guthaben müssen '
        'Sie trotzdem auszahlen. Melden Sie in der Abrechnung „Zustellung melden“, dann '
        'behält die Anwendung die Fristen im Blick.',
        'Der Mieter darf die Belege einsehen und hat zwölf Monate Zeit für Einwände.',
    ]),
    ('9. Daten sichern', [
        'Unter „Einstellungen → Sicherung“ erstellen Sie eine Sicherung: Datenbank und alle '
        'Belege in einer Datei. Legen Sie sie auf einen USB-Stick oder Ihr NAS, nicht nur auf '
        'denselben Rechner.',
        'Die Anwendung erinnert Sie, wenn die letzte Sicherung älter als 30 Tage ist.',
    ]),
    ('10. Umzug auf einen anderen Rechner', [
        'Neuer Rechner, oder von Docker in die Windows-App? „Alles exportieren“ erstellt ein '
        'Umzugspaket (.nkfix) mit allem. Auf dem neuen Rechner wählen Sie bei der Einrichtung '
        '„Daten aus einer anderen Installation übernehmen“ und melden sich danach mit Ihrem '
        'bisherigen Konto an.',
        'Keine Rechtsberatung: Im Zweifel fragen Sie Ihren Eigentümerverband oder eine '
        'Anwältin für Mietrecht.',
    ]),
]


def kurzanleitung_pdf() -> bytes:
    """Die Kurzanleitung: A4, 15 pt, eine Aufgabe je Seite."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    farbe = HexColor(marke.FARBE)
    titel = ParagraphStyle('Titel', fontName='Helvetica-Bold', fontSize=24, leading=30,
                           textColor=farbe, spaceAfter=10 * mm)
    text = ParagraphStyle('Text', fontName='Helvetica', fontSize=15, leading=22,
                          spaceAfter=6 * mm)
    punkt = ParagraphStyle('Punkt', parent=text, leftIndent=8 * mm, bulletIndent=0)

    def fuss(leinwand, dokument):
        leinwand.saveState()
        leinwand.setFont('Helvetica', 11)
        leinwand.setFillColor(HexColor('#4B5563'))
        leinwand.drawString(20 * mm, 12 * mm, f'{marke.PRODUKT} — Kurzanleitung')
        leinwand.drawRightString(190 * mm, 12 * mm, f'Seite {dokument.page}')
        leinwand.restoreState()

    puffer = io.BytesIO()
    dokument = SimpleDocTemplate(
        puffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=22 * mm,
        bottomMargin=22 * mm, title=f'{marke.PRODUKT} — Kurzanleitung', author=marke.PRODUKT)
    teile = []
    for nummer, (ueberschrift, absaetze) in enumerate(KURZANLEITUNG):
        if nummer:
            teile.append(PageBreak())
        teile.append(Paragraph(escape(ueberschrift), titel))
        for absatz in absaetze:
            if absatz.startswith('• '):
                teile.append(Paragraph(escape(absatz[2:]), punkt, bulletText='•'))
            else:
                teile.append(Paragraph(escape(absatz), text))
        teile.append(Spacer(1, 4 * mm))
    dokument.build(teile, onFirstPage=fuss, onLaterPages=fuss)
    return puffer.getvalue()


def init_hilfe(app):
    from flask import Response

    @app.route('/api/hilfe/kurzanleitung.pdf', methods=['GET'])
    def hilfe_kurzanleitung():
        return Response(kurzanleitung_pdf(), mimetype='application/pdf', headers={
            'Content-Disposition': f'inline; filename="{marke.PRODUKT}-Kurzanleitung.pdf"',
            'X-Content-Type-Options': 'nosniff',
        })
