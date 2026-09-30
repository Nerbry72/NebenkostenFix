"""Die Datenbeschaffung fuer den Rechenkern (NK-037).

Hier steht das Fragen, in ``rechenkern.py`` das Rechnen. Die Trennung ist der
ganze Zweck: solange beides ineinanderlag, brauchte jede Probe einen
Objektgraphen, eine Sitzung und ein Schema.

Der Lader holt in einem Zug alles, was eine Abrechnung braucht, und uebergibt
es als eingefrorenen ``Vorgang``. Was er einmal geholt hat, aendert sich
waehrend des Rechnens nicht mehr -- kein Nachladen im Hintergrund, keine
Abhaengigkeit davon, in welcher Reihenfolge der Kern seine Felder anfasst.

Er laedt bewusst etwas mehr als der knappste Fall braucht: alle Zaehler der
Immobilie samt Staenden, alle Mieter, alle Rechnungen des Zeitraums. Bei ein
bis fuenfzehn Einheiten sind das ein paar Dutzend Zeilen; dafuer verschwinden
die Abfragen, die vorher in der Umlageschleife standen und je Rechnung erneut
liefen.
"""

from datetime import date, datetime
from typing import Optional

from nebenkostenfix.models import (
    Apartment,
    CostCategory,
    CostInvoice,
    Heizungsanlage as HeizungsanlageZeile,
    Meter,
    MeterReading,
    Payment,
    Tenant,
    db,
)
from nebenkostenfix.haushalt import normiere as normiere_haushalt
from nebenkostenfix.heizung import ZWISCHENABLESUNG
from nebenkostenfix.nutzung import VORGABE as NUTZUNG_VORGABE
from nebenkostenfix.zeitraum import grenze
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
)


def _als_datum(wert) -> date:
    """Nimmt ein date oder eine Zeichenkette im ISO-Format."""
    return wert if isinstance(wert, date) else datetime.strptime(wert, '%Y-%m-%d').date()


def _wohnung(apartment: Apartment) -> Wohnung:
    return Wohnung(
        id=apartment.id,
        name=apartment.name,
        qm=apartment.sqm,
        ist_aktiv=bool(apartment.is_active),
        # Die drei Stammdaten aus NK-045. ``or VORGABE`` faengt die Zeile
        # ab, die vor der Wanderung entstanden ist und noch NULL traegt --
        # in einer Sicherung, einem Import, einer Stichprobe.
        nutzungsart=apartment.nutzungsart or NUTZUNG_VORGABE,
        selbstversorger=bool(apartment.selbstversorger),
        eigennutzung=bool(apartment.eigennutzung),
    )


def _mieter(tenant: Tenant) -> Mieter:
    """Ein Mietverhaeltnis, wie der Kern es sieht -- samt Haushaltshistorie.

    ``normiere_haushalt`` macht aus den ORM-Zeilen einfache Tupel. Das ist
    hier nicht nur Bequemlichkeit: der Rechenkern darf keine Datenbank
    sehen (NK-037), und eine lazy geladene Beziehung waere genau das.
    """
    return Mieter(
        id=tenant.id,
        name=tenant.name,
        einzug=tenant.move_in_date,
        # F-118: Der Vermieter traegt den letzten Miettag ein ("ausgezogen
        # am 30.09., der Nachmieter kommt am 01.10."). Der Kern rechnet mit
        # der Grenze dahinter (R-NUM-03); umgerechnet wird nur hier.
        auszug=grenze(tenant.move_out_date) if tenant.move_out_date else None,
        wohnung_id=tenant.apartment_id,
        haushaltsgroessen=normiere_haushalt(
            (h.gueltig_ab, h.personenanzahl) for h in tenant.haushaltsgroessen
        ),
    )


def _kategorie(category: CostCategory) -> Kategorie:
    return Kategorie(
        id=category.id,
        name=category.name,
        braucht_zaehler=bool(category.requires_meter),
        betrkv_nr=category.betrkv_nr,
    )


def _beleg(invoice: CostInvoice) -> Beleg:
    """Der Nachweis in beiden Formen, die der Altbestand kennt."""
    if invoice.document:
        return Beleg(
            dateiname=invoice.document.filename,
            pfad=invoice.document.document_path,
            seiten=invoice.document_pages,
        )
    return Beleg(pfad_alt=invoice.document_path)


def _rechnung(invoice: CostInvoice) -> Rechnung:
    return Rechnung(
        id=invoice.id,
        kategorie=_kategorie(invoice.category),
        betrag=invoice.amount,
        beginn=invoice.start_date,
        ende=invoice.end_date,
        wohnung_id=invoice.apartment_id,
        nummer=invoice.invoice_number,
        versorger_id=invoice.provider_id,
        versorger_name=invoice.provider.name if invoice.provider else None,
        # Das Datum des Belegs (NK-058). NULL heisst: keiner angegeben --
        # der Kern rechnet damit nicht, er weist es nur aus.
        rechnungsdatum=invoice.rechnungsdatum,
        beleg=_beleg(invoice),
        heizungsanlage_id=invoice.heizungsanlage_id,
        heizkostenart=invoice.heizkostenart,
        co2_kosten=invoice.co2_kosten,
        co2_emission_kg=invoice.co2_emission_kg,
        preis_ht=invoice.preis_ht,
        preis_nt=invoice.preis_nt,
    )


def _heizungsanlage(anlage: HeizungsanlageZeile) -> Heizungsanlage:
    return Heizungsanlage(
        id=anlage.id,
        name=anlage.name,
        versorgt=anlage.versorgt,
        verbrauchsanteil_prozent=anlage.verbrauchsanteil_prozent,
        sonderfall_70=bool(anlage.sonderfall_70),
        # Die Angaben des § 9 zur Warmwassertrennung (NK-050). Sie stehen an
        # der Anlage und gelten fuer den gerechneten Zeitraum -- wer einen
        # anderen Zeitraum rechnet, pflegt sie neu (F-35).
        warmwasser_weg=anlage.warmwasser_weg,
        warmwasser_kwh=anlage.warmwasser_kwh,
        warmwasser_volumen_m3=anlage.warmwasser_volumen_m3,
        warmwasser_temperatur_c=anlage.warmwasser_temperatur_c,
        brennstoff_menge=anlage.brennstoff_menge,
        heizwert_kwh=anlage.heizwert_kwh,
    )


def _staende(readings, auszugstage=frozenset()) -> tuple:
    """Die Staende in fester Reihenfolge -- Gleichstand eingeschlossen (NK-039).

    Zwei Ablesungen am selben Tag kommen beim Mieterwechsel vor: einmal fuer
    den Auszug, kurz darauf fuer den Einzug. Ohne die Kennung im Schluessel
    haengt ihre Reihenfolge daran, in welcher die Datenbank sie liefert.

    F-118: Eine Zwischenablesung am letzten Miettag ist die Uebergabe -- sie
    misst das Ende dieses Tages, also die Grenze am Tag danach, an der der
    Kern sie sucht.
    """
    return tuple(
        # ``art`` traegt die Ablesungsart mit (NK-051): nur der Stand zum
        # Datum eines Nutzerwechsels ist eine Zwischenablesung und misst die
        # Grenze zwischen zwei Mietverhaeltnissen.
        Stand(datum=(grenze(r.reading_date)
                     if r.ablesungsart == ZWISCHENABLESUNG
                     and r.reading_date in auszugstage else r.reading_date),
              wert=r.value, wert_nt=r.value_nt, art=r.ablesungsart)
        for r in sorted(readings, key=lambda r: (r.reading_date, r.id))
    )


def _zaehler(meter: Meter, readings, auszugstage=frozenset()) -> Zaehler:
    return Zaehler(
        id=meter.id,
        nummer=meter.meter_number,
        kategorie_id=meter.category_id,
        kategorie_name=meter.category.name if meter.category else '',
        # Die Nummer aus dem Katalog wandert mit (NK-121): die Einheit und
        # damit die Trennung § 7 / § 8 entscheidet sie, nicht der Name.
        kategorie_betrkv_nr=(meter.category.betrkv_nr
                             if meter.category else None),
        ist_hauptzaehler=bool(meter.is_main_meter),
        immobilie_id=meter.property_id,
        wohnung_id=meter.apartment_id,
        staende=_staende(readings, auszugstage),
        heizungsanlage_id=meter.heizungsanlage_id,
    )


def lade_zaehler(meter_id: int) -> Optional[Zaehler]:
    """Einen einzelnen Zaehler samt Staenden, oder None.

    Fuer den Weg, den die Oberflaeche direkt geht: ein Zaehler, ein Zeitraum,
    eine Auskunft ueber den Verbrauch -- ohne eine ganze Abrechnung.
    """
    meter = db.session.get(Meter, meter_id)
    if meter is None:
        return None
    readings = (
        MeterReading.query.filter_by(meter_id=meter_id)
        .order_by(MeterReading.reading_date, MeterReading.id)
        .all()
    )
    return _zaehler(meter, readings)


def _wasser_kategorie_id(prop_id: int) -> Optional[int]:
    """Die Kategorie des Frischwassers DIESER Immobilie (NK-055, D-56).

    Abwasser hat keinen eigenen Zaehler: gemessen wird, was an den
    Frischwasserzaehlern des Objekts hineingeht. Gesucht wird deshalb nur
    unter den Kostenarten, die an **dieser** Immobilie einen Zaehler haben
    -- die Suche ueber den Namen allein stammte aus der Engine und traf
    auch Kostenarten, die an keinem Zaehler des Objekts haengen oder deren
    Zaehler woanders haengen.

    Das Warmwasser scheidet aus: seine Zaehler messen den Warmwasseranteil
    des § 8 HeizkostenV (NK-050), nicht das Frischwasser, an dem die
    Abwasserkosten haengen. Dasselbe gilt fuer Schmutzwasser und
    Niederschlagswasser -- beides sind Abwasserposten, keine Messung des
    Frischwassers. Passen mehrere Kategorien (zwei Haeuser, zwei Namen),
    gewinnt die mit der kleinsten Kennung, also die aelteste; dass es bei
    jedem Lauf dieselbe ist, gehoert zu NK-039.
    """
    treffer = (CostCategory.query
               .join(Meter, Meter.category_id == CostCategory.id)
               .filter(Meter.property_id == prop_id,
                       CostCategory.name.ilike('%wasser%'),
                       CostCategory.name.notilike('%abwasser%'),
                       CostCategory.name.notilike('%schmutzwasser%'),
                       CostCategory.name.notilike('%niederschlag%'),
                       CostCategory.name.notilike('%warmwasser%'))
               .order_by(CostCategory.id)
               .first())
    return treffer.id if treffer else None


def lade_vorgang(tenant_id, start_date, end_date, category_ids=None) -> Vorgang:
    """Alles, was die Abrechnung dieses Mieters braucht, in einem Zug.

    ``start_date`` und ``end_date`` werden auf das Mietverhaeltnis gestutzt:
    wer im Maerz einzieht, wird ab Maerz abgerechnet. Das gehoert hierher und
    nicht in den Kern, sonst muesste jede Probe es nachbauen.
    """
    tenant = db.session.get(Tenant, tenant_id)
    # Dass ein fehlender Mieter hier mit AttributeError endet, ist das
    # Verhalten der Engine. NK-037 aendert es nicht; die Routen in app.py
    # kommen nur mit einer Kennung aus der eigenen Liste hierher.
    apartment = tenant.apartment
    prop = apartment.property

    beginn = _als_datum(start_date)
    ende = _als_datum(end_date)
    if tenant.move_in_date > beginn:
        beginn = tenant.move_in_date
    if tenant.move_out_date and tenant.move_out_date < ende:
        ende = tenant.move_out_date

    wohnungen = sorted(prop.apartments, key=lambda a: a.id)
    wohnungs_ids = [a.id for a in wohnungen]

    mieter_der_immobilie = (
        Tenant.query.filter(Tenant.apartment_id.in_(wohnungs_ids)).order_by(Tenant.id).all()
        if wohnungs_ids else []
    )

    # ponytail: Auszugstage der ganzen Immobilie, nicht je Wohnung -- eine
    # Zwischenablesung faellt kaum zufaellig auf den Auszug nebenan.
    auszugstage = frozenset(t.move_out_date for t in mieter_der_immobilie
                            if t.move_out_date)

    rechnungen = CostInvoice.query.filter(
        CostInvoice.property_id == prop.id,
        CostInvoice.start_date <= ende,
        CostInvoice.end_date >= beginn,
    ).order_by(CostInvoice.id).all()

    # Die Umlage fragt nach Zaehlern der Immobilie (Haupt- und Unterzaehler)
    # und nach dem Zaehler dieser Wohnung. Beides in einem Zug.
    meters = Meter.query.filter(
        db.or_(Meter.property_id == prop.id, Meter.apartment_id == apartment.id)
    ).order_by(Meter.id).all()

    staende_je_zaehler = {}
    if meters:
        alle_staende = MeterReading.query.filter(
            MeterReading.meter_id.in_([m.id for m in meters])
        ).order_by(MeterReading.reading_date, MeterReading.id).all()
        for stand in alle_staende:
            staende_je_zaehler.setdefault(stand.meter_id, []).append(stand)

    # Die Anlagen der Immobilie. Ohne sie verteilt der Kern die Heizkosten
    # wie gewoehnliche Kostenarten -- genau das Verhalten vor NK-049.
    anlagen = HeizungsanlageZeile.query.filter(
        HeizungsanlageZeile.property_id == prop.id
    ).order_by(HeizungsanlageZeile.id).all()

    zahlungen = Payment.query.filter(
        Payment.tenant_id == tenant_id,
        Payment.type == 'Nebenkostenvorauszahlung',
        Payment.payment_date >= beginn,
        Payment.payment_date <= ende,
    ).order_by(Payment.payment_date, Payment.id).all()

    return Vorgang(
        mieter=_mieter(tenant),
        wohnung=_wohnung(apartment),
        immobilie_id=prop.id,
        immobilie_name=prop.name,
        beginn=beginn,
        ende=ende,
        wohnungen=tuple(_wohnung(a) for a in wohnungen),
        mieter_der_immobilie=tuple(_mieter(t) for t in mieter_der_immobilie),
        profile={p.category_id: p.billing_type for p in tenant.cost_profiles},
        rechnungen=tuple(_rechnung(i) for i in rechnungen),
        zaehler=tuple(_zaehler(m, staende_je_zaehler.get(m.id, []), auszugstage)
                      for m in meters),
        zahlungen=tuple(Zahlung(datum=z.payment_date, betrag=z.amount) for z in zahlungen),
        heizungsanlagen=tuple(_heizungsanlage(a) for a in anlagen),
        wasser_kategorie_id=_wasser_kategorie_id(prop.id),
        kategorien_filter=tuple(category_ids) if category_ids else None,
    )
