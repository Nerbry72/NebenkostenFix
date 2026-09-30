"""
GiroCode (EPC-QR-Code) generator for billing PDFs.

Generates a standardized European Payments Council (EPC) QR code that
tenants can scan with their banking app for 1-click payment of their
Nachzahlung (balance due).

The QR code is only generated when the balance is positive (Nachzahlung).
When the tenant has a Guthaben (credit), no QR code is shown.
"""

import os
import re
from io import BytesIO
from datetime import datetime

import segno
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle
from nebenkostenfix.validation import EingabeFehler


# --- IBAN (NK-124) ---

def iban_saeubern(iban):
    """Die IBAN so, wie der Zahlungsverkehr sie liest: gross, ohne Leerraum."""
    return re.sub(r'[\s\-]', '', (iban or '')).upper()


def iban_pruefen(iban):
    """Prueft die IBAN auf Form und Pruefsumme (mod-97, ISO 13616).

    Liefert die gesaeuberte IBAN oder wirft EingabeFehler — dieselbe
    Grenze wie alle anderen Felder: die Oberflaeche zeigt den deutschen
    Text und hebt das Feld hervor. Ohne Pruefung traegt das Blatt eine
    IBAN, die die Bank des Mieters abweist — der Fehler zeigt sich erst
    beim Zahlversuch des Mieters, Wochen spaeter.
    """
    sauber = iban_saeubern(iban)
    if not sauber:
        raise EingabeFehler('Die IBAN ist leer. Tragen Sie sie ein oder '
                            'lassen Sie das Feld frei.', 'iban')
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{10,30}', sauber):
        raise EingabeFehler(
            'Diese IBAN hat keine gültige Form: sie beginnt mit zwei '
            'Buchstaben und zwei Ziffern, gefolgt von der Kontonummer '
            '(insgesamt 15 bis 34 Zeichen, ohne Leerraum).', 'iban')
    # Pruefsumme: die ersten vier Zeichen hängen nach hinten, Buchstaben
    # werden zu Zahlen (A=10, ... Z=35), dann mod 97 == 1.
    umgestellt = sauber[4:] + sauber[:4]
    zahl = ''.join(
        str(ord(z) - ord('A') + 10) if z.isalpha() else z for z in umgestellt)
    if int(zahl) % 97 != 1:
        raise EingabeFehler(
            'Diese IBAN hat eine falsche Prüfsumme. Überprüfen Sie die '
            'Nummer auf dem Beleg — ein Vertipper fällt hier auf.', 'iban')
    return sauber


def vermieter_ausweis():
    """Empfaenger und IBAN für den GiroCode, einmal aus einer Hand (NK-124).

    Erste Quelle sind die Vermieterdaten aus der Oberflaeche (Tabelle
    ``vermieterdaten``), zweite Quelle die Umgebungsvariablen des
    Bestands (D-81). Jedes Feld fuer sich: wer nur den Namen in der
    Oberflaeche pflegt und die IBAN in der .env, bekommt beides. Beides
    leer heisst: kein GiroCode.

    Ohne Anwendungskontext (Direktnutzung im Werkzeug, im Test) gibt es
    keine Datenbank: dann nur die Umgebung.
    """
    name_datenbank = iban_datenbank = None
    try:
        from nebenkostenfix.models import Vermieterdaten
        zeile = Vermieterdaten.einziger()
    except RuntimeError:  # kein Anwendungskontext
        zeile = None
    if zeile is not None:
        name_datenbank = (zeile.name or '').strip() or None
        iban_datenbank = (zeile.iban or '').strip() or None
    name = name_datenbank or os.environ.get('VERMIETER_NAME', '')
    iban = iban_datenbank or os.environ.get('VERMIETER_IBAN', '')
    return name.strip(), iban_saeubern(iban)


# --- Color Palette (matching cover page) ---
COLOR_DARK = colors.HexColor('#1f2937')
COLOR_MUTED = colors.HexColor('#6b7280')
COLOR_LIGHT_BG = colors.HexColor('#f8fafc')
COLOR_BORDER = colors.HexColor('#e2e8f0')
COLOR_ACCENT = colors.HexColor('#4f46e5')


def _format_iban_display(iban):
    """Format IBAN in groups of 4 for display (e.g., DE89 3704 0044 ...)."""
    clean = iban.replace(' ', '')
    return ' '.join(clean[i:i+4] for i in range(0, len(clean), 4))


def _format_currency_de(value):
    """Format a float as German currency string (e.g., '219,37 EUR')."""
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"{formatted} EUR"


def _sanitize_epc_text(text):
    """Sanitize text for EPC QR code payload (max 140 chars, limited charset)."""
    # EPC standard allows: a-z A-Z 0-9 and a few special chars
    # Remove any characters that might cause issues
    sanitized = re.sub(r'[^\w\s/\-.,+()]', '', text, flags=re.UNICODE)
    return sanitized[:140]


def _build_epc_payload(beneficiary_name, iban, amount, remittance_text):
    """
    Build the EPC QR code payload string per the EPC069-12 standard.
    
    Structure:
        BCD            - Service Tag (fixed)
        002            - Version 2
        1              - Character set: UTF-8
        SCT            - Identification: SEPA Credit Transfer
        [BIC]          - BIC (optional, empty)
        [Name]         - Beneficiary name (max 70 chars)
        [IBAN]         - IBAN
        EUR[Amount]    - Amount with EUR prefix
        [Purpose]      - Purpose code (empty)
        [Ref]          - Structured remittance reference (empty)
        [Text]         - Unstructured remittance text (max 140 chars)
        [Info]         - Beneficiary to originator information (empty)
    """
    lines = [
        'BCD',                          # Service Tag
        '002',                          # Version
        '1',                            # Character set (UTF-8)
        'SCT',                          # Identification
        '',                             # BIC (optional)
        beneficiary_name[:70],          # Beneficiary name
        iban.replace(' ', ''),          # IBAN (no spaces)
        f'EUR{amount:.2f}',             # Amount
        '',                             # Purpose code
        '',                             # Structured reference
        _sanitize_epc_text(remittance_text),  # Unstructured text
        '',                             # Information
    ]
    return '\n'.join(lines)


def _generate_qr_image(payload, size_mm=40):
    """Generate a QR code image as a ReportLab Image flowable."""
    qr = segno.make(payload, error='m')
    
    buffer = BytesIO()
    qr.save(buffer, kind='png', scale=8, border=2)
    buffer.seek(0)
    
    img = Image(buffer, width=size_mm * mm, height=size_mm * mm)
    return img


def build_girocode_elements(balance, tenant_name, apartment_name, start_date, end_date):
    """
    Build ReportLab flowable elements for the GiroCode payment section.
    
    Only generates content when balance > 0 (Nachzahlung).
    Returns an empty list when balance <= 0 (Guthaben or zero).
    
    Args:
        balance: The payment balance (positive = tenant owes money)
        tenant_name: Full name of the tenant
        apartment_name: Name of the apartment (e.g., "EG", "1. OG")
        start_date: ISO date string for billing period start
        end_date: ISO date string for billing period end
    
    Returns:
        List of ReportLab Flowable elements (may be empty)
    """
    # Only show GiroCode for Nachzahlung (positive balance)
    if balance <= 0:
        return []
    
    # Erst die Oberflaeche, dann die Umgebung (NK-124, D-81). Beides leer
    # heisst: kein GiroCode, und das steht jetzt auch in der Oberflaeche.
    beneficiary, iban = vermieter_ausweis()
    
    if not beneficiary or not iban:
        # Cannot generate GiroCode without IBAN/name — skip silently
        return []
    
    # Build Verwendungszweck with full tenant name
    try:
        year = datetime.fromisoformat(start_date).year
    except (ValueError, TypeError):
        year = datetime.now().year
    
    remittance = f"Nebenkosten {year} {apartment_name} {tenant_name}"
    
    # Generate EPC QR payload
    payload = _build_epc_payload(beneficiary, iban, balance, remittance)
    
    # Generate QR image
    qr_image = _generate_qr_image(payload, size_mm=38)
    
    # --- Build styled elements ---
    elements = []
    
    elements.append(Spacer(1, 20))
    
    # Styles
    heading_style = ParagraphStyle(
        'GiroHeading',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=16,
        textColor=COLOR_DARK,
    )
    
    body_style = ParagraphStyle(
        'GiroBody',
        fontName='Helvetica',
        fontSize=9,
        leading=14,
        textColor=COLOR_MUTED,
    )
    
    detail_style = ParagraphStyle(
        'GiroDetail',
        fontName='Helvetica',
        fontSize=8,
        leading=12,
        textColor=COLOR_MUTED,
    )
    
    detail_bold_style = ParagraphStyle(
        'GiroDetailBold',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=12,
        textColor=COLOR_DARK,
    )
    
    # Build inner content
    inner_elements = []
    
    # Title row
    inner_elements.append(Paragraph(
        "Zahlung per GiroCode",
        heading_style,
    ))
    inner_elements.append(Spacer(1, 4))
    inner_elements.append(Paragraph(
        "Scannen Sie diesen QR-Code mit Ihrer Banking-App, "
        "um die Überweisung automatisch auszufüllen.",
        body_style,
    ))
    inner_elements.append(Spacer(1, 12))
    
    # QR code centered with payment details to the right
    detail_rows = [
        [Paragraph("Begünstigter:", detail_style),
         Paragraph(beneficiary, detail_bold_style)],
        [Paragraph("IBAN:", detail_style),
         Paragraph(_format_iban_display(iban), detail_bold_style)],
        [Paragraph("Betrag:", detail_style),
         Paragraph(_format_currency_de(balance), detail_bold_style)],
        [Paragraph("Verwendungszweck:", detail_style),
         Paragraph(remittance, detail_bold_style)],
    ]
    
    detail_table = Table(detail_rows, colWidths=[85, 185])
    detail_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    # Layout: QR code on left, details on right
    layout_data = [[qr_image, detail_table]]
    layout_table = Table(layout_data, colWidths=[42 * mm, 280])
    layout_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 12),
        ('LEFTPADDING', (1, 0), (1, 0), 12),
    ]))
    
    # Wrap everything in a bordered box
    box_content = []
    for el in inner_elements:
        box_content.append([el])
    box_content.append([layout_table])
    
    box_table = Table(box_content, colWidths=[460])
    box_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('TOPPADDING', (0, 0), (0, 0), 16),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 16),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    
    elements.append(box_table)
    
    return elements
