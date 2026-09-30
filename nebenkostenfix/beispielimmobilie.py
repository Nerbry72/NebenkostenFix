"""NK-141/NK-159: Eine Beispielimmobilie zum Ausprobieren.

Wer die App zum ersten Mal aufmacht, sieht leere Listen -- und weiss nicht,
wonach die Uebersicht „Fehlende Daten" sucht. Diese Demo legt ein kleines
Haus mit Zaehlern in allen vier Zustaenden an (frisch, veraltet, dringend,
nie gelesen) plus eine Warnung: nach Verbrauch abgerechnet ohne Unterzaehler.
Danach zeigt die Uebersicht sofort, was sie kann.

Die Beispielimmobilie ist echte Datenbank, keine Sonderbehandlung: Sie kann
bearbeitet, geloescht und abgerechnet werden wie jede andere Immobilie auch.
Zweimal anlegen gibt es nicht -- der feste Name macht sie wiedererkennbar,
ein zweiter Aufruf meldet die vorhandene.

NK-159 (vollständiges Beispiel): Der Anfänger soll das Ziel sehen, bevor er
anfängt. Deshalb trägt das Haus die Rechnungen des Vorjahres, Annas
Vorauszahlungen und -- angelegt von der Route über den gewöhnlichen
Festsetzungsweg, kein zweiter Rechenweg -- eine festgesetzte Abrechnung mit
PDF. ``entfernen()`` nimmt alles in einem Zug wieder heraus, samt PDFs und
ohne die Aufbewahrungssperre (NK-153): es sind keine echten Mieter. In den
Kennzahlen der Übersicht zählt das Beispiel nicht (``ist_beispiel``).
"""

from __future__ import annotations

from datetime import date, timedelta

NAME = 'Beispielhaus (Demo)'
MIETER = ('Anna Beispiel', 'Ben Beispiel')


class BeispielExistiert(Exception):
    """Die Beispielimmobilie liegt schon vor; sie wird nicht doppelt angelegt."""

    def __init__(self, property_id: int):
        super().__init__(NAME)
        self.property_id = property_id


def _heute_minus(tage: int) -> date:
    return date.today() - timedelta(days=tage)


def ist_beispiel(haus) -> bool:
    """Ob eine Immobilie das Beispielhaus ist (fester Name, siehe oben)."""
    return haus is not None and haus.name == NAME


def vorjahr() -> tuple[date, date]:
    jahr = date.today().year - 1
    return date(jahr, 1, 1), date(jahr, 12, 31)


# Die Rechnungen des Vorjahres (umgelegt nach Wohnfläche, der Vorgabe).
RECHNUNGEN = (
    ('Grundsteuer', '460.00', 'Grundsteuerbescheid', 'BSP-GS'),
    ('Straßenreinigung und Müllbeseitigung', '540.00', 'Müllabfuhr und Straßenreinigung', 'BSP-MUELL'),
    ('Sach- und Haftpflichtversicherung', '610.00', 'Gebäudeversicherung', 'BSP-VERS'),
    ('Beleuchtung (Allgemeinstrom)', '190.00', 'Strom für Treppenhaus und Keller', 'BSP-STROM'),
)
VORAUSZAHLUNG = '60.00'


def anlegen():
    """Legt das Beispielhaus an und gibt den Bericht fuer die Antwort zurueck."""
    from nebenkostenfix.models import (Apartment, CostCategory, Meter, MeterReading,
                        Property, Tenant, TenantCostProfile, db)

    vorhanden = Property.query.filter_by(name=NAME).first()
    if vorhanden:
        raise BeispielExistiert(vorhanden.id)

    def kategorie(name: str) -> CostCategory:
        kat = CostCategory.query.filter_by(name=name).first()
        if kat is None:
            raise ValueError(f'Kostenart {name} fehlt im Katalog')
        return kat

    heizung = kategorie('Heizung')
    warmwasser = kategorie('Warmwasser')
    wasser = kategorie('Wasserversorgung')

    haus = Property(name=NAME)
    db.session.add(haus)
    db.session.flush()

    eg = Apartment(property_id=haus.id, name='EG links', sqm=52.0)
    og = Apartment(property_id=haus.id, name='OG rechts', sqm=61.0)
    db.session.add_all([eg, og])
    db.session.flush()

    # Anna wohnt seit der Mitte des vorletzten Jahres dort: das ganze Vorjahr
    # ist ihr Abrechnungszeitraum (NK-159).
    anna = Tenant(apartment_id=eg.id, name=MIETER[0],
                  move_in_date=date(date.today().year - 2, 7, 1))
    ben = Tenant(apartment_id=og.id, name=MIETER[1],
                 move_in_date=_heute_minus(200))
    db.session.add_all([anna, ben])
    db.session.flush()

    # Kostenprofile: Anna verrechnet Heizung nach Flaeche, Ben nach Verbrauch
    # -- ohne Unterzaehler fuer Warmwasser. Genau dafuer warnt die Uebersicht.
    db.session.add(TenantCostProfile(tenant_id=anna.id, category_id=heizung.id,
                                     billing_type='qm'))
    db.session.add(TenantCostProfile(tenant_id=ben.id, category_id=warmwasser.id,
                                     billing_type='direkt'))

    zaehler = []

    def zaehler_anlegen(kat: CostCategory, nummer: str, main: bool,
                        apartment: Apartment | None = None) -> Meter:
        m = Meter(category_id=kat.id, property_id=haus.id,
                  apartment_id=apartment.id if apartment else None,
                  is_main_meter=main, meter_number=nummer)
        db.session.add(m)
        db.session.flush()
        zaehler.append(m)
        return m

    def lese(m: Meter, tage: int, wert: float) -> None:
        db.session.add(MeterReading(meter_id=m.id,
                                    reading_date=_heute_minus(tage), value=wert))

    # Vier Zustaende der Aktualitaet, je einer:
    main_heizung = zaehler_anlegen(heizung, 'H-Heiz-1', main=True)
    lese(main_heizung, 30, 2450.0)          # frisch
    unterm_eg = zaehler_anlegen(heizung, 'H-EG-1', main=False, apartment=eg)
    lese(unterm_eg, 210, 4100.0)            # dringend
    main_ww = zaehler_anlegen(warmwasser, 'H-WW-1', main=True)  # nie gelesen
    main_wasser = zaehler_anlegen(wasser, 'H-W-1', main=True)
    lese(main_wasser, 120, 96.0)            # veraltet
    # Ein Unterzaehler fuer OG Wasser blieb ausgelassen: Das Haus ist absichtlich
    # unvollstaendig, damit die Uebersicht etwas zu sagen hat.

    # NK-159: die Rechnungen des Vorjahres und Annas Vorauszahlungen. Ben
    # zog erst später ein: sein Teil des Vorjahres ist Leerstand und bleibt
    # beim Vermieter -- auch das zeigt die Abrechnung.
    from decimal import Decimal

    from nebenkostenfix.models import CostInvoice, Payment
    von, bis = vorjahr()
    kostenarten = []
    for nummer, (kat_name, betrag, beschreibung, kuerzel) in enumerate(RECHNUNGEN, 1):
        kat = kategorie(kat_name)
        kostenarten.append(kat.id)
        db.session.add(CostInvoice(
            property_id=haus.id, category_id=kat.id, amount=Decimal(betrag),
            start_date=von, end_date=bis, rechnungsdatum=date(von.year + 1, 1, 10 + nummer),
            invoice_number=f'{kuerzel}-{von.year}', description=beschreibung))
    for monat in range(1, 13):
        db.session.add(Payment(tenant_id=anna.id, amount=Decimal(VORAUSZAHLUNG),
                               payment_date=date(von.year, monat, 3),
                               type='Nebenkostenvorauszahlung'))

    db.session.commit()
    return {
        'property_id': haus.id,
        'wohnungen': 2,
        'mieter': len(MIETER),
        'zaehler': len(zaehler),
        'rechnungen': len(RECHNUNGEN),
        'abrechnung_auftrag': {
            'tenant_id': anna.id, 'start_date': von.isoformat(),
            'end_date': bis.isoformat(), 'category_ids': kostenarten,
        },
        'hinweis': ('Das Beispielhaus zeigt eine fertige Abrechnung des '
                    'Vorjahres, alle vier Zustände der Zählerstand-Aktualität '
                    'und eine Warnung (nach Verbrauch abgerechnet ohne '
                    'Unterzähler). „Beispiel löschen“ nimmt alles wieder heraus.'),
    }


def entfernen() -> dict:
    """Löscht das Beispielhaus mit allem, was dazugehört, in einem Zug.

    Anders als beim Löschen echter Mieter gibt es keine Aufbewahrungssperre
    (NK-153): Anna und Ben sind erfunden. Die PDFs der Beispielabrechnung
    verschwinden mit.
    """
    from nebenkostenfix import datenordner
    from nebenkostenfix import uploads
    from nebenkostenfix.models import (AnschreibenVorlage, CostInvoice, Heizungsanlage,
                        InvoiceDocument, Meter, Property, TenantBillingReport, db)

    haus = Property.query.filter_by(name=NAME).first()
    if haus is None:
        return {'entfernt': False}
    wurzel = datenordner.belegordner()
    dateien = 0
    mieter_ids = [t.id for w in haus.apartments for t in w.tenants]
    for bericht in TenantBillingReport.query.filter(
            TenantBillingReport.tenant_id.in_(mieter_ids)).all() if mieter_ids else []:
        for pfad in (bericht.document_path, bericht.document_path_detailed):
            echt = uploads.pfad_aufloesen(wurzel, pfad)
            if echt is not None:
                echt.unlink()
                dateien += 1
        db.session.delete(bericht)
    for dokument in InvoiceDocument.query.filter_by(property_id=haus.id).all():
        echt = uploads.pfad_aufloesen(wurzel, dokument.document_path)
        if echt is not None:
            echt.unlink()
            dateien += 1
    for modell in (CostInvoice, Meter, InvoiceDocument, AnschreibenVorlage, Heizungsanlage):
        for zeile in modell.query.filter_by(property_id=haus.id).all():
            db.session.delete(zeile)
    # Ein Flush für alles: die Arbeitseinheit ordnet die Löschungen nach den
    # Fremdschlüsseln (Zahlungen vor Abrechnungen vor Mietern).
    db.session.delete(haus)
    db.session.commit()
    return {'entfernt': True, 'dateien': dateien}
