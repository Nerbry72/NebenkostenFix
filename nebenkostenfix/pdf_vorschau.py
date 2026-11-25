"""Vorschau-PDF eines Layouts mit einer erfundenen Beispielimmobilie.

Die Vorschau zeigt, wie ein Layout auf dem Blatt aussieht, bevor es
gespeichert wird. Sie rechnet einen Vorgang, der nur im Speicher steht:
keine Immobilie, kein Mieter, keine Rechnung aus der Datenbank, nichts wird
geschrieben. Die Namen kommen aus der Beispielimmobilie
(``beispielimmobilie.py``). Die Welt belegt jeden Block -- Übersicht,
Heizung mit CO2-Aufteilung, Lohnanteile nach § 35a EStG, Belegliste,
Nachzahlung mit Zahlungshinweis und die Verbrauchsnachweise.

Was der Generator selbst holt, bleibt wie beim echten Blatt: Name,
Anschrift, IBAN und Logo des Vermieters aus den eigenen Einstellungen.
Ohne IBAN zeigt auch die Vorschau keinen GiroCode.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nebenkostenfix import beispielimmobilie
from nebenkostenfix.rechenkern import (
    Beleg,
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    Zahlung,
    rechne,
)

WOHNUNG = 'EG links'
_WASSER = Kategorie(id=1, name='Wasserversorgung', braucht_zaehler=True)
_GRUNDSTEUER = Kategorie(id=2, name='Grundsteuer', braucht_zaehler=False)
_GARTEN = Kategorie(id=3, name='Gartenpflege', braucht_zaehler=False)
_WAERME = Kategorie(id=4, name='Heizung', braucht_zaehler=True)


def _jahr() -> int:
    return date.today().year - 1


def vorgang() -> Vorgang:
    """Zwei Wohnungen, vier Kostenarten, eine Heizungsanlage -- erfunden."""
    jahr = _jahr()
    beginn, ende = date(jahr, 1, 1), date(jahr, 12, 31)
    erste, zweite = beispielimmobilie.MIETER[:2]
    links = Wohnung(id=1, name=WOHNUNG, qm=60.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=40.0)
    mieter = Mieter(id=1, name=erste, einzug=beginn, auszug=None, wohnung_id=1,
                    haushaltsgroessen=((beginn, 2),))
    nachbar = Mieter(id=2, name=zweite, einzug=beginn, auszug=None, wohnung_id=2)

    def rechnung(nr, kategorie, betrag, datei, **kw):
        return Rechnung(
            id=nr, kategorie=kategorie, betrag=Decimal(betrag), beginn=beginn, ende=ende,
            nummer=f'B-{jahr}-{nr:03d}', versorger_name='Beispielversorger',
            rechnungsdatum=date(jahr + 1, 1, 15),
            beleg=Beleg(dateiname=datei, seiten='1'), **kw)

    def zaehler(nr, nummer, kategorie, wohnung_id, bis, haupt=False, anlage=None):
        return Zaehler(
            id=nr, nummer=nummer, kategorie_id=kategorie.id,
            kategorie_name=kategorie.name, ist_hauptzaehler=haupt, immobilie_id=1,
            wohnung_id=wohnung_id, heizungsanlage_id=anlage,
            staende=(Stand(datum=beginn, wert=0.0), Stand(datum=ende, wert=bis)))

    return Vorgang(
        mieter=mieter, wohnung=links, immobilie_id=1,
        immobilie_name=beispielimmobilie.NAME, beginn=beginn, ende=ende,
        wohnungen=(links, rechts), mieter_der_immobilie=(mieter, nachbar),
        profile={_WASSER.id: 'direkt', _GRUNDSTEUER.id: 'qm', _GARTEN.id: 'qm'},
        rechnungen=(
            rechnung(1, _WASSER, '900.00', 'wasser.pdf'),
            rechnung(2, _GRUNDSTEUER, '600.00', 'grundsteuer.pdf'),
            rechnung(3, _GARTEN, '480.00', 'garten.pdf',
                     art_35a='haushaltsnah', lohnanteil=Decimal('360.00')),
            rechnung(4, _WAERME, '3000.00', 'waerme.pdf', heizungsanlage_id=1,
                     heizkostenart='brennstoff', co2_kosten=Decimal('400.00'),
                     co2_emission_kg=Decimal('1500.00')),
        ),
        zaehler=(
            zaehler(1, 'W-0', _WASSER, None, 150.0, haupt=True),
            zaehler(2, 'W-1', _WASSER, 1, 90.0),
            zaehler(3, 'W-2', _WASSER, 2, 60.0),
            zaehler(4, 'H-1', _WAERME, 1, 700.0, anlage=1),
            zaehler(5, 'H-2', _WAERME, 2, 300.0, anlage=1),
        ),
        zahlungen=(Zahlung(datum=date(jahr, 6, 1), betrag=Decimal('2400.00')),),
        heizungsanlagen=(Heizungsanlage(id=1, name='Zentralheizung',
                                        verbrauchsanteil_prozent=70),),
        wasser_kategorie_id=_WASSER.id,
    )


def vorschau_pdf(layout: dict) -> bytes:
    """Die ausführliche Fassung der Beispielabrechnung im übergebenen Layout."""
    from nebenkostenfix.pdf_generator import PDFGenerator

    fall = vorgang()
    ergebnis = rechne(fall)
    erzeuger = PDFGenerator(
        property_name=fall.immobilie_name, apartment_name=WOHNUNG,
        tenant_name=fall.mieter.name, start_date=ergebnis['start_date'],
        end_date=ergebnis['end_date'], detailliert=True)
    return erzeuger.generate(
        ergebnis['line_items'], ergebnis['total_amount'], ergebnis['prepaid_amount'],
        co2_ausweis=ergebnis['co2'], landlord_share=ergebnis['landlord_share'],
        vorbehalt=ergebnis['vorbehalt'], ausweis_35a=ergebnis['ausweis_35a'],
        layout=layout)
