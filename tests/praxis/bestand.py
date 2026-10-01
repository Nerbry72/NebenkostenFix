"""Der Praxisbestand (NK-193): die Form von einem echten Bestand, alle Werte erfunden.

Drei Häuser, sechs Wohnungen, fünf Mieter, zehn Zähler und die Lagen H1 bis
H12 aus Phase 12d. Namen, Beträge, Zählerstände und Stichtage sind neu
erfunden; die Jahre liegen in den 2030ern, damit nichts an echte Daten
erinnert. ``HEUTE`` ist der Tag, an dem der Vermieter abrechnet.

- **Haus A** rechnet April bis März ab (H1). Wohnungszähler werden um Ende
  März abgelesen, die DG-Wohnung erst Mitte Mai (H2). Heizung ohne Stand am
  Stichtag (H3). Wasser- und Heizungsrechnungen enden sechs Tage vor dem
  31.03. (H6), die Versicherung endet am 01.01. des Folgejahres (H5), die
  Stromrechnung läuft nur bis 31.12. (H7). Strom mit HT/NT, die DG-Wohnung
  hat keinen eigenen Stromzähler (H11), W2 steht leer, ihr Wasserzähler läuft weiter.
  - Mieter 1 (EG) und Mieter 2 (DG): Bestand, „abgerechnet bis“ steht ein
    Jahr hinter der letzten Abrechnung (H10), Vorauszahlungen bis 2035 (H9).
  - Mieter 3 (W3): Einzug am Monatsersten, erste Ablesung gut zwei Wochen
    später (H4), Auszug Ende Juli, Vorauszahlungen bis Dezember (H9).
- **Haus B:** Mieter 4 ohne Kostenprofil und ohne Rechnung (H8).
- **Haus C:** Mieter 5 mit Wohnungsrechnungen, eine davon vier Jahre alt (H12).
"""

from __future__ import annotations

from datetime import date

from nebenkostenfix.frist import frist_ende
from nebenkostenfix.models import TenantBillingReport, db
from tests import billing_factories as f

HEUTE = date(2034, 10, 15)


def _monatlich(mieter, betrag, von: date, bis: date):
    jahr, monat = von.year, von.month
    while (jahr, monat) <= (bis.year, bis.month):
        f.payment(mieter, betrag, date(jahr, monat, 3))
        jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)


def _alte_abrechnung(mieter, beginn: date, ende: date):
    db.session.add(TenantBillingReport(tenant_id=mieter.id, start_date=beginn, end_date=ende,
                                       frist_ende=frist_ende(ende)))
    db.session.commit()


def _haus_a():
    haus = f.house('Haus A')
    haus.abrechnungsjahr_beginn = '04-01'
    wasser, heizung = f.category('Wasserversorgung'), f.category('Heizung')
    strom, versicherung = f.category('Strom'), f.category('Gebaeudeversicherung')

    eg, w2 = f.apt(haus, 'EG', 71.5), f.apt(haus, 'W2', 46.0)
    w3, dg = f.apt(haus, 'W3', 58.0), f.apt(haus, 'DG', 39.5)
    m1 = f.tenant(eg, 'Mieter 1', move_in=date(2028, 6, 1))
    m2 = f.tenant(dg, 'Mieter 2', move_in=date(2031, 5, 1))
    m3 = f.tenant(w3, 'Mieter 3', move_in=date(2033, 10, 1), move_out=date(2034, 7, 31))

    for m in (m1, m2, m3):
        f.profile(m, wasser, 'direkt')
        f.profile(m, versicherung, 'qm')
    f.profile(m1, heizung, 'direkt')
    f.profile(m3, heizung, 'direkt')
    f.profile(m2, heizung, 'ignoriert')
    f.profile(m1, strom, 'direkt')
    f.profile(m3, strom, 'direkt')
    f.profile(m2, strom, 'nur_allgemein')

    # Wasser: Hauptzähler an anderen Tagen als die Wohnungen (H2)
    hw = f.meter(haus, wasser, 'HW-1', is_main=True)
    for tag, stand in ((date(2032, 4, 4), 1210.0), (date(2033, 4, 3), 1487.0), (date(2034, 4, 5), 1771.0)):
        f.reading(hw, tag, stand)
    for wohnung, nummer, staende in (
            (eg, 'W-EG', ((date(2032, 3, 30), 402.0), (date(2033, 3, 29), 488.0), (date(2034, 3, 31), 577.0))),
            (w2, 'W-W2', ((date(2032, 3, 30), 80.0), (date(2033, 3, 29), 84.0), (date(2034, 3, 31), 87.0))),
            (dg, 'W-DG', ((date(2032, 5, 13), 150.0), (date(2033, 5, 14), 191.0), (date(2034, 5, 16), 236.0))),
            (w3, 'W-W3', ((date(2033, 10, 17), 61.0), (date(2034, 7, 31), 103.0)))):
        z = f.meter(haus, wasser, nummer, is_main=False, apartment=wohnung)
        for tag, stand in staende:
            f.reading(z, tag, stand)

    # Heizung: Wärmezähler EG und W3, kein Stand am 31.03. (H3)
    for wohnung, nummer, staende in (
            (eg, 'WMZ-EG', ((date(2033, 3, 28), 18400.0), (date(2034, 4, 2), 24650.0))),
            (w3, 'WMZ-W3', ((date(2033, 10, 17), 3100.0), (date(2034, 7, 31), 7020.0)))):
        z = f.meter(haus, heizung, nummer, is_main=False, apartment=wohnung)
        for tag, stand in staende:
            f.reading(z, tag, stand)

    # Strom mit HT/NT am Haupt- und an den Wohnungszählern, DG ohne Zähler (H11)
    hs = f.meter(haus, strom, 'HS-1', is_main=True)
    f.reading(hs, date(2033, 4, 1), 8200.0, 3100.0)
    f.reading(hs, date(2034, 4, 1), 9960.0, 3790.0)
    for wohnung, nummer, staende in (
            (eg, 'S-EG', ((date(2033, 4, 1), 5100.0, 1900.0), (date(2034, 4, 1), 6020.0, 2270.0))),
            (w3, 'S-W3', ((date(2033, 10, 17), 700.0, 260.0), (date(2034, 7, 31), 1190.0, 445.0)))):
        z = f.meter(haus, strom, nummer, is_main=False, apartment=wohnung)
        for tag, ht, nt in staende:
            f.reading(z, tag, ht, nt)

    # Rechnungen
    f.invoice(haus, wasser, 1488.40, date(2032, 3, 26), date(2033, 3, 25), invoice_number='WA-32')
    f.invoice(haus, wasser, 1562.90, date(2033, 3, 26), date(2034, 3, 25), invoice_number='WA-33')  # H6
    f.invoice(haus, heizung, 3920.00, date(2033, 3, 26), date(2034, 3, 25), invoice_number='HZ-33')  # H6
    f.invoice(haus, strom, 1137.60, date(2033, 1, 1), date(2033, 12, 31), invoice_number='ST-33')  # H7
    f.invoice(haus, versicherung, 846.00, date(2033, 1, 1), date(2034, 1, 1), invoice_number='VG-33')  # H5
    f.invoice(haus, versicherung, 889.20, date(2034, 1, 1), date(2035, 1, 1), invoice_number='VG-34')  # H5

    # Bisherige Abrechnungen, das Feld steht ein Jahr dahinter (H10)
    for m in (m1, m2):
        _alte_abrechnung(m, date(2032, 4, 1), date(2033, 3, 31))
        m.last_billed_until = date(2032, 3, 31)

    # Vorauszahlungen bis weit in die Zukunft, bei Mieter 3 nach dem Auszug (H9)
    _monatlich(m1, 145.0, date(2033, 4, 1), date(2035, 12, 1))
    _monatlich(m2, 85.0, date(2033, 4, 1), date(2035, 12, 1))
    _monatlich(m3, 110.0, date(2033, 10, 1), date(2034, 12, 1))
    db.session.commit()
    return m1, m2, m3


def _haus_b():
    """Eine Einzeleinheit, Mieter ohne Kostenprofil und ohne Rechnung (H8)."""
    haus = f.house('Haus B')
    haus.is_standalone = True
    return f.tenant(f.apt(haus, 'Wohnung', 64.0), 'Mieter 4', move_in=date(2033, 11, 1))


def _haus_c():
    """Wohnungsrechnungen, eine vier Jahre alt (H12)."""
    haus = f.house('Haus C')
    haus.is_standalone = True
    wohnung = f.apt(haus, 'Wohnung', 82.0)
    m5 = f.tenant(wohnung, 'Mieter 5', move_in=date(2032, 8, 1))
    m5.last_billed_until = date(2032, 12, 31)
    grundsteuer, muell = f.category('Grundsteuer'), f.category('Müllabfuhr')
    for kat in (grundsteuer, muell):
        f.profile(m5, kat, 'qm')
    f.invoice(haus, grundsteuer, 377.10, date(2029, 1, 1), date(2029, 12, 31), wohnung, 'GS-29')  # H12
    f.invoice(haus, grundsteuer, 412.80, date(2033, 1, 1), date(2033, 12, 31), wohnung, 'GS-33')
    f.invoice(haus, muell, 263.40, date(2033, 1, 1), date(2033, 12, 31), wohnung, 'MU-33')
    _monatlich(m5, 60.0, date(2033, 1, 1), date(2034, 12, 1))
    db.session.commit()
    return m5


def aufbauen() -> dict[str, int]:
    """Legt den Bestand an und liefert ``{'Mieter N': tenant_id}``."""
    mieter = [*_haus_a(), _haus_b(), _haus_c()]
    db.session.commit()
    return {m.name: m.id for m in mieter}
