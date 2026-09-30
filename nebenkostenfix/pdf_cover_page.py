"""
Management Summary Cover Page (Deckblatt) for billing PDFs.

Generates a premium one-pager summary that is prepended to the detailed
cost breakdown. Shows key metrics at a glance with dynamic color coding.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak

from nebenkostenfix import vermieter_logo
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from datetime import datetime

from nebenkostenfix import zeit

from nebenkostenfix.geld import NULL
from nebenkostenfix.anschreiben import absaetze


# --- Color Palette ---
COLOR_GREEN = colors.HexColor('#059669')    # Guthaben (credit)
COLOR_RED = colors.HexColor('#DC2626')      # Nachzahlung (payment due)
COLOR_DARK = colors.HexColor('#1f2937')     # Primary text
COLOR_MUTED = colors.HexColor('#6b7280')    # Secondary text
COLOR_LIGHT_BG = colors.HexColor('#f8fafc') # Card backgrounds
COLOR_ACCENT = colors.HexColor('#4f46e5')   # Accent line (indigo)
COLOR_BORDER = colors.HexColor('#e2e8f0')   # Subtle borders


def _create_styles():
    """Create all paragraph styles for the cover page."""
    styles = {}
    
    styles['PropertyName'] = ParagraphStyle(
        'CoverPropertyName',
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=28,
        textColor=COLOR_DARK,
        spaceAfter=4,
    )
    
    styles['SubHeader'] = ParagraphStyle(
        'CoverSubHeader',
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=COLOR_MUTED,
        spaceAfter=30,
    )
    
    styles['Greeting'] = ParagraphStyle(
        'CoverGreeting',
        fontName='Helvetica',
        fontSize=11,
        leading=18,
        textColor=COLOR_DARK,
        spaceAfter=40,
    )
    
    styles['MetricLabel'] = ParagraphStyle(
        'CoverMetricLabel',
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=COLOR_MUTED,
        spaceBefore=4,
    )
    
    styles['MetricValue'] = ParagraphStyle(
        'CoverMetricValue',
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=32,
        textColor=COLOR_DARK,
    )
    
    styles['MetricValueLarge'] = ParagraphStyle(
        'CoverMetricValueLarge',
        fontName='Helvetica-Bold',
        fontSize=32,
        leading=42,
        textColor=COLOR_DARK,  # Overridden dynamically
    )
    
    styles['BalanceLabel'] = ParagraphStyle(
        'CoverBalanceLabel',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=COLOR_DARK,
    )
    
    styles['FooterNote'] = ParagraphStyle(
        'CoverFooterNote',
        fontName='Helvetica',
        fontSize=9,
        leading=14,
        textColor=COLOR_MUTED,
        alignment=1,  # Center
    )
    
    styles['DateRight'] = ParagraphStyle(
        'CoverDateRight',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=COLOR_MUTED,
        alignment=2,  # Right
    )
    
    return styles


def _format_currency(value):
    """Format a float as German currency string (e.g., '1.234,56 €')."""
    # Handle negative values
    prefix = "- " if value < 0 else ""
    abs_val = abs(value)
    # Format with 2 decimal places, then replace . with , for German locale
    formatted = f"{abs_val:,.2f}"
    # Swap . and , for German number format
    formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"{prefix}{formatted} €"


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
):
    """
    Build a list of reportlab Flowable elements for the billing cover page.
    
    Args:
        property_name: Name of the property (e.g., "Lindenstraße 12")
        apartment_name: Name of the apartment (e.g., "EG links")
        tenant_name: Full name of the tenant (e.g., "Anna Mieterin")
        start_date: ISO date string for billing period start
        end_date: ISO date string for billing period end
        total_amount: Total costs for the period
        prepaid_amount: Total prepayments made
        balance: Final balance (positive = Nachzahlung, negative = Guthaben)
    
    Returns:
        List of reportlab Flowable elements (including a trailing PageBreak)
    """
    styles = _create_styles()
    elements = []
    
    # Format dates
    start_fmt = datetime.fromisoformat(start_date).strftime('%d.%m.%Y')
    end_fmt = datetime.fromisoformat(end_date).strftime('%d.%m.%Y')
    creation_date = zeit.als_ortszeit(zeit.jetzt_utc(), '%d.%m.%Y')
    
    # ──────────────────────────────────────────────
    # TOP: Property header + date
    # ──────────────────────────────────────────────
    # NK-155: das Logo des Vermieters, falls hinterlegt, rechts über dem Datum.
    logo = vermieter_logo.deckblatt_bild()
    rechts = [logo, Paragraph(f"Datum: {creation_date}", styles['DateRight'])] if logo \
        else Paragraph(f"Datum: {creation_date}", styles['DateRight'])
    header_data = [
        [
            Paragraph(property_name, styles['PropertyName']),
            rechts,
        ]
    ]
    header_table = Table(header_data, colWidths=[350, 130])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_table)
    
    # Accent line
    accent_data = [['', '']]
    accent_table = Table(accent_data, colWidths=[80, 400])
    accent_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 3, COLOR_ACCENT),
    ]))
    elements.append(accent_table)
    elements.append(Spacer(1, 8))
    
    # Subtitle
    elements.append(Paragraph(
        f"Hausverwaltung / Vermieter",
        styles['SubHeader']
    ))
    
    # ──────────────────────────────────────────────
    # RECIPIENT + GREETING
    # ──────────────────────────────────────────────
    elements.append(Paragraph(f"An: <b>{tenant_name}</b>", styles['Greeting']))
    elements.append(Paragraph(f"Wohnung: {apartment_name}", styles['SubHeader']))
    
    elements.append(Spacer(1, 10))
    
    # Formal greeting (Sie) -- wenn der Vermieter ein Anschreiben hinterlegt
    # hat (NK-064), spricht es statt des festen Grußes; der Vorgabetext der
    # Vorlage deckt denselben Inhalt ab, das Metrik-Block bleibt darunter.
    if anschreiben:
        for absatz in absaetze(anschreiben):
            elements.append(Paragraph(absatz, styles['Greeting']))
            elements.append(Spacer(1, 6))
        elements.append(Spacer(1, 10))
    else:
        elements.append(Paragraph(
            f"Sehr geehrte/r {tenant_name},<br/><br/>"
            f"anbei finden Sie Ihre Nebenkostenabrechnung für den Zeitraum "
            f"<b>{start_fmt}</b> bis <b>{end_fmt}</b>. "
            f"Im Folgenden erhalten Sie einen Überblick über die wichtigsten Kennzahlen.",
            styles['Greeting']
        ))
    
    elements.append(Spacer(1, 30))
    
    # ──────────────────────────────────────────────
    # KEY METRICS — 3 blocks in a row
    # ──────────────────────────────────────────────
    
    # Determine balance color and label
    if balance < 0:
        balance_color = COLOR_GREEN
        balance_label = "Ihr Guthaben"
        display_balance = abs(balance)
    elif balance > 0:
        balance_color = COLOR_RED
        balance_label = "Ihre Nachzahlung"
        display_balance = balance
    else:
        balance_color = COLOR_DARK
        balance_label = "Saldobetrag"
        display_balance = NULL
    
    # Build metric cells
    def _metric_cell(label, value, value_color=COLOR_DARK, font_size=24):
        """Build a single metric block as a mini-table."""
        label_style = ParagraphStyle(
            f'MetricLabel_{label}',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=COLOR_MUTED,
            spaceBefore=0,
            spaceAfter=6,
        )
        value_style = ParagraphStyle(
            f'MetricValue_{label}',
            fontName='Helvetica-Bold',
            fontSize=font_size,
            leading=font_size + 8,
            textColor=value_color,
        )
        cell_data = [
            [Paragraph(label, label_style)],
            [Paragraph(_format_currency(value), value_style)],
        ]
        cell_table = Table(cell_data, colWidths=[148])
        cell_table.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 16),
            ('RIGHTPADDING', (0, 0), (-1, -1), 16),
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_LIGHT_BG),
            ('ROUNDEDCORNERS', [6, 6, 6, 6]),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ]))
        return cell_table
    
    metrics_data = [[
        _metric_cell("Gesamtkosten der Periode", total_amount),
        _metric_cell("Geleistete Vorauszahlungen", prepaid_amount),
        _metric_cell(balance_label, display_balance, balance_color),
    ]]
    
    metrics_table = Table(metrics_data, colWidths=[160, 160, 160])
    metrics_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(metrics_table)
    
    elements.append(Spacer(1, 40))
    
    # ──────────────────────────────────────────────
    # LARGE BALANCE HIGHLIGHT
    # ──────────────────────────────────────────────
    balance_highlight_label = ParagraphStyle(
        'BalanceHighlightLabel',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=18,
        textColor=balance_color,
        alignment=1,
    )
    balance_highlight_value = ParagraphStyle(
        'BalanceHighlightValue',
        fontName='Helvetica-Bold',
        fontSize=36,
        leading=48,
        textColor=balance_color,
        alignment=1,
    )
    
    highlight_data = [
        [Paragraph(balance_label, balance_highlight_label)],
        [Paragraph(_format_currency(display_balance), balance_highlight_value)],
    ]
    highlight_table = Table(highlight_data, colWidths=[480])
    
    # Determine highlight background color
    if balance < 0:
        highlight_bg = colors.HexColor('#ecfdf5')  # green-50
        highlight_border = colors.HexColor('#a7f3d0')  # green-200
    elif balance > 0:
        highlight_bg = colors.HexColor('#fef2f2')  # red-50
        highlight_border = colors.HexColor('#fecaca')  # red-200
    else:
        highlight_bg = COLOR_LIGHT_BG
        highlight_border = COLOR_BORDER
    
    highlight_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), highlight_bg),
        ('BOX', (0, 0), (-1, -1), 1, highlight_border),
        ('TOPPADDING', (0, 0), (-1, 0), 20),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 24),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    elements.append(highlight_table)
    
    elements.append(Spacer(1, 50))
    
    # ──────────────────────────────────────────────
    # FOOTER NOTE
    # ──────────────────────────────────────────────
    elements.append(Paragraph(
        "Die detaillierte Aufstellung finden Sie auf den folgenden Seiten.",
        styles['FooterNote']
    ))
    
    # Page break to cleanly separate from the detail pages
    elements.append(PageBreak())
    
    return elements
