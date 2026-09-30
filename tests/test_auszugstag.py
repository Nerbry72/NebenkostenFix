"""F-118: Das Auszugsdatum ist der letzte Miettag.

Befund auf 6061: Mieter 3 zieht am 30.09. aus, der Nachmieter kommt am
01.10. Der Vermieter traegt den letzten Miettag ein. Der Lader gab ihn
aber unveraendert als Grenze an den Kern (R-NUM-03, halboffen) -- der
30.09. gehoerte damit niemandem und blieb beim Vermieter haengen.

*Haette den Befund gefunden:* dieser Test -- vor dem Fix bekam der
Vormieter 272,00 EUR, und ein Euro fehlte in der Summe.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nebenkostenfix.abrechnungsdaten import lade_vorgang
from nebenkostenfix.heizung import ZWISCHENABLESUNG
from nebenkostenfix.models import db
from nebenkostenfix.rechenkern import rechne
from tests import billing_factories as f

JAHR_BEGINN, JAHR_ENDE = date(2025, 1, 1), date(2025, 12, 31)


def _anteil(mieter):
    posten = rechne(lade_vorgang(mieter.id, JAHR_BEGINN, JAHR_ENDE))['line_items']
    return sum((p['tenant_cost'] for p in posten), Decimal('0'))


def test_auszugstag_zaehlt_beim_vormieter_und_kein_tag_geht_verloren(app_ctx):
    """365 EUR fuer 365 Tage: 273 Tage bis einschliesslich 30.09., 92 danach."""
    prop = f.house('Wechselhaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    vormieter = f.tenant(wohnung, 'Vormieter', move_in=date(2020, 1, 1),
                         move_out=date(2025, 9, 30))
    nachmieter = f.tenant(wohnung, 'Nachmieter', move_in=date(2025, 10, 1))
    kat = f.category('Müllabfuhr')
    f.profile(vormieter, kat, 'qm')
    f.profile(nachmieter, kat, 'qm')
    f.invoice(prop, kat, 365.00, start=JAHR_BEGINN, end=JAHR_ENDE)

    assert _anteil(vormieter) == Decimal('273.00')
    assert _anteil(nachmieter) == Decimal('92.00')


def test_uebergabe_ablesung_am_letzten_miettag_misst_die_grenze(app_ctx):
    """Auf 6061 stehen die Zwischenablesungen fuer Mieter 3 am 30.09.

    Der Kern sucht sie an der Grenze (01.10.). Ohne Umrechnung fand er sie
    nicht mehr und teilte still nach Tagen statt nach Messung.
    """
    prop = f.house('Ablesehaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    vormieter = f.tenant(wohnung, 'Vormieter', move_in=date(2020, 1, 1),
                         move_out=date(2025, 9, 30))
    f.tenant(wohnung, 'Nachmieter', move_in=date(2025, 10, 1))
    zaehler = f.meter(prop, f.category('Wasserversorgung'), 'W-1',
                      is_main=False, apartment=wohnung)
    f.reading(zaehler, JAHR_BEGINN, 0.0)
    f.reading(zaehler, date(2025, 9, 30), 100.0).ablesungsart = ZWISCHENABLESUNG
    f.reading(zaehler, date(2025, 10, 15), 110.0).ablesungsart = ZWISCHENABLESUNG
    f.reading(zaehler, JAHR_ENDE, 150.0)
    db.session.commit()

    staende = lade_vorgang(vormieter.id, JAHR_BEGINN, JAHR_ENDE).zaehler[0].staende
    assert [(s.datum, s.art) for s in staende if s.art == ZWISCHENABLESUNG] == [
        (date(2025, 10, 1), ZWISCHENABLESUNG),   # Uebergabe -> Grenze
        (date(2025, 10, 15), ZWISCHENABLESUNG),  # kein Auszugstag: bleibt
    ]
