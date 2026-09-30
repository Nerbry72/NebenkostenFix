"""Minimal graph builders for BillingEngine characterization tests (NK-003)."""

from __future__ import annotations

from datetime import date

from nebenkostenfix.betrkv import zuordnung
from nebenkostenfix.nutzung import VORGABE as NUTZUNG_VORGABE

from nebenkostenfix.models import (
    Apartment,
    CostCategory,
    CostInvoice,
    Haushaltsgroesse,
    Meter,
    MeterReading,
    Payment,
    Property,
    Tenant,
    TenantCostProfile,
    db,
)

YEAR_START = date(2024, 1, 1)
YEAR_END = date(2024, 12, 31)


def category(name: str) -> CostCategory:
    """Die Kostenart, die hier „name" heisst -- oder die, die es geworden ist.

    Seit NK-044 heisst der Seed nach dem Katalog aus § 2 BetrKV: aus „Strom"
    wurde Nr. 11 „Beleuchtung (Allgemeinstrom)", aus „Gebaeudeversicherung"
    Nr. 13 „Sach- und Haftpflichtversicherung". Die Tests hier reden aber vom
    Fall, nicht vom Etikett, und der Fall ist derselbe geblieben. Der Umweg
    ueber die Nummer haelt sie lesbar und ueberlebt die naechste
    Umbenennung -- scharf bleibt er trotzdem: findet sich auch unter der
    Nummer nichts, schlaegt der assert zu.
    """
    cat = CostCategory.query.filter_by(name=name).first()
    if cat is None:
        cat = CostCategory.query.filter_by(betrkv_nr=zuordnung(name)).first()
    assert cat is not None, f"seed category missing: {name}"
    return cat


def house(name: str = "Charakterhaus") -> Property:
    prop = Property(name=name, is_standalone=False)
    db.session.add(prop)
    db.session.commit()
    return prop


def apt(
    prop: Property,
    name: str,
    sqm: float,
    is_active: bool = True,
    *,
    nutzungsart: str = NUTZUNG_VORGABE,
    selbstversorger: bool = False,
    eigennutzung: bool = False,
) -> Apartment:
    """Eine Einheit. Die drei Stammdaten aus NK-045 stehen auf dem Normalfall.

    Der Normalfall ist Wohnraum, fremd bewohnt, an der Heizungsanlage des
    Hauses. Genau so wurde vor NK-045 jede Einheit gerechnet -- die Vorgaben
    hier halten die vorhandenen Proben deshalb unveraendert.
    """
    apartment = Apartment(
        property_id=prop.id, name=name, sqm=sqm, is_active=is_active,
        nutzungsart=nutzungsart, selbstversorger=selbstversorger,
        eigennutzung=eigennutzung,
    )
    db.session.add(apartment)
    db.session.commit()
    return apartment


def haushalt(t: Tenant, gueltig_ab: date, personen: int) -> Haushaltsgroesse:
    """Ab diesem Tag wohnen so viele Koepfe im Haushalt (NK-045)."""
    h = Haushaltsgroesse(tenant_id=t.id, gueltig_ab=gueltig_ab, personenanzahl=personen)
    db.session.add(h)
    db.session.commit()
    return h


def tenant(
    apartment: Apartment,
    name: str,
    move_in: date = YEAR_START,
    move_out: date | None = None,
) -> Tenant:
    t = Tenant(
        apartment_id=apartment.id,
        name=name,
        move_in_date=move_in,
        move_out_date=move_out,
    )
    db.session.add(t)
    db.session.commit()
    return t


def profile(t: Tenant, cat: CostCategory, billing_type: str) -> TenantCostProfile:
    p = TenantCostProfile(tenant_id=t.id, category_id=cat.id, billing_type=billing_type)
    db.session.add(p)
    db.session.commit()
    return p


def invoice(
    prop: Property,
    cat: CostCategory,
    amount: float,
    start: date = YEAR_START,
    end: date = YEAR_END,
    apartment: Apartment | None = None,
    invoice_number: str = "INV-1",
) -> CostInvoice:
    inv = CostInvoice(
        category_id=cat.id,
        property_id=prop.id,
        apartment_id=apartment.id if apartment else None,
        start_date=start,
        end_date=end,
        amount=amount,
        invoice_number=invoice_number,
    )
    db.session.add(inv)
    db.session.commit()
    return inv


def meter(
    prop: Property,
    cat: CostCategory,
    number: str,
    *,
    is_main: bool,
    apartment: Apartment | None = None,
) -> Meter:
    m = Meter(
        category_id=cat.id,
        property_id=prop.id,
        apartment_id=apartment.id if apartment else None,
        is_main_meter=is_main,
        meter_number=number,
    )
    db.session.add(m)
    db.session.commit()
    return m


def reading(m: Meter, when: date, value: float, value_nt: float | None = None) -> MeterReading:
    r = MeterReading(meter_id=m.id, reading_date=when, value=value, value_nt=value_nt)
    db.session.add(r)
    db.session.commit()
    return r


def payment(t: Tenant, amount: float, when: date, ptype: str = "Nebenkostenvorauszahlung") -> Payment:
    p = Payment(tenant_id=t.id, amount=amount, payment_date=when, type=ptype)
    db.session.add(p)
    db.session.commit()
    return p
