"""CSV-Export der Abrechnungspositionen (NK-145).

Der Vermieter will die Zahlen seiner Abrechnung in der Tabellenkalkulation
weiterverwenden: fuer die Steuererklaerung, fuer einen Vergleich ueber die
Jahre, fuer den Steuerberater. Das PDF ist dafuer das falsche Format.

Gelesen wird dasselbe Ergebnis wie in der Detailansicht und im Beleg-ZIP:
der Schnappschuss der gueltigen Version (R-DOC-02), beim Altbestand die
frische Rechnung. Die CSV ist also genau die Abrechnung, die der Mieter
bekommen hat, nicht eine neue Rechnung gegen heutige Stammdaten.

Format fuer Excel und LibreOffice in deutscher Einstellung:

    - Trennzeichen Semikolon, Dezimalkomma, Datum TT.MM.JJJJ
    - UTF-8 mit BOM (sonst liest Excel die Umlaute als Mojibake)
    - Zeilenende CRLF

Sicherheit (CSV-/Formel-Injektion): Ein Anbietername, der mit ``=``, ``+``,
``-``, ``@`` oder einem Tabulator beginnt, waere in Excel eine Formel. Text-
spalten bekommen davor ein Hochkomma; Betragsspalten sind von uns formatierte
Zahlen und bleiben unberuehrt, damit sie als Zahl ankommen.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from abrechnungsart import ARTEN as ARTTEXT

SPALTEN = (
    'Zeile', 'Art', 'Kostenart', 'Anbieter', 'Rechnungsnummer',
    'Rechnungsdatum', 'Rechnungszeitraum', 'Rechnungsbetrag (EUR)',
    'Umlageart', 'Tage im Abrechnungszeitraum', 'Tage der Rechnung',
    'Ihr Anteil (EUR)', 'Erläuterung',
)

_FORMELZEICHEN = ('=', '+', '-', '@', '\t', '\r')


def _text(wert) -> str:
    """Textzelle, gegen Formel-Injektion geschuetzt."""
    if wert is None:
        return ''
    text = str(wert)
    if text.startswith(_FORMELZEICHEN):
        return "'" + text
    return text


def _betrag(wert) -> str:
    """Geld mit Dezimalkomma, ohne Tausenderpunkt (Excel rechnet damit)."""
    if wert is None or wert == '':
        return ''
    try:
        zahl = Decimal(str(wert)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return _text(wert)
    return f'{zahl}'.replace('.', ',')


def _zahl(wert) -> str:
    return '' if wert is None else str(wert)


def _datum(iso) -> str:
    if not iso:
        return ''
    try:
        return date.fromisoformat(str(iso)[:10]).strftime('%d.%m.%Y')
    except ValueError:
        return _text(iso)


def _umlageart(schluessel) -> str:
    if not schluessel:
        return ''
    if schluessel == 'heizkosten':
        return 'Heizkosten nach HeizkostenV'
    return ARTTEXT.get(schluessel, str(schluessel))


def positionen_csv(ergebnis: dict) -> str:
    """Die Abrechnung als CSV-Text (ohne BOM; die Route setzt ihn davor)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=';', lineterminator='\r\n',
                           quoting=csv.QUOTE_MINIMAL)
    schreiber.writerow(SPALTEN)
    for nummer, zeile in enumerate(ergebnis.get('line_items') or [], start=1):
        schreiber.writerow([
            nummer, 'Position',
            _text(zeile.get('category')),
            _text(zeile.get('provider_name')),
            _text(zeile.get('invoice_number')),
            _datum(zeile.get('rechnungsdatum')),
            _text(zeile.get('period')),
            _betrag(zeile.get('invoice_total_amount', zeile.get('total_amount'))),
            _text(_umlageart(zeile.get('billing_type'))),
            _zahl(zeile.get('overlap_days')),
            _zahl(zeile.get('invoice_days')),
            _betrag(zeile.get('tenant_cost')),
            _text(zeile.get('rechenweg') or zeile.get('description')),
        ])
        for teil in zeile.get('sub_items') or []:
            schreiber.writerow([
                nummer, 'Teilposten', _text(zeile.get('category')),
                '', '', '', '', '', '', '', '',
                _betrag(teil.get('cost')),
                _text(teil.get('description')),
            ])
    # Summenzeilen: Betrag in der Spalte 'Ihr Anteil (EUR)'.
    anteil = SPALTEN.index('Ihr Anteil (EUR)')
    leer = [''] * (anteil - 3)
    schreiber.writerow(['', 'Summe', 'Summe Ihrer Kosten', *leer,
                        _betrag(ergebnis.get('total_amount')), ''])
    schreiber.writerow(['', 'Summe', 'Ihre Vorauszahlungen', *leer,
                        _betrag(ergebnis.get('prepaid_amount')), ''])
    saldo = ergebnis.get('balance')
    try:
        saldo_zahl = Decimal(str(saldo))
    except (InvalidOperation, ValueError, TypeError):
        saldo_zahl = Decimal('0')
    if saldo_zahl > 0:
        text = 'Nachzahlung'
    elif saldo_zahl < 0:
        text = 'Guthaben'
    else:
        text = 'Ausgeglichen'
    schreiber.writerow(['', 'Summe', text, *leer, _betrag(saldo), ''])
    return puffer.getvalue()


def dateiname(bericht) -> str:
    """Positionen_<Mieter>_<Beginn>-<Ende>.csv, nur sichere Zeichen."""
    mieter = bericht.tenant.name if bericht.tenant else 'Mieter'
    sicher = ''.join(z if z.isalnum() or z in ' -_' else '_' for z in mieter)
    return (f'Positionen_{sicher}_{bericht.start_date.strftime("%Y%m%d")}-'
            f'{bericht.end_date.strftime("%Y%m%d")}.csv')
