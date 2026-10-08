"""NK-003 characterization of BillingEngine IST.

These tests pin current behaviour. Do not change billing_engine.py to make
them pass. Goldens are literals, not a second copy of the engine.

NK-036 hat die Rundungsentscheidung nachgezogen, auf die der urspruengliche
Kopf hier verwies: Geld ist ``Decimal``, kaufmaennisch auf Cent gerundet
(R-NUM-01). Die Goldens sind deshalb Decimal-Literale. **Ihre Zahlenwerte
sind unveraendert** -- 201.09 bleibt 201.09 -- mit einer einzigen Ausnahme,
und die war der Zweck der Karte: ``total_amount`` ist jetzt die Summe der
gerundeten Zeilen, siehe
test_total_amount_ist_die_summe_der_gerundeten_zeilen.

NK-044 hat den Seed auf § 2 BetrKV gestellt. Wo hier frueher ``Strom``
stand, steht jetzt ``Wasserversorgung``: die Zaehlerfaelle brauchen eine
Kostenart, an der ein Zaehler haengt, und das ist im Gesetzeskatalog die
Nr. 2. Die frei benannte Kostenart ``Strom`` ist zur Nr. 11 geworden,
``Beleuchtung (Allgemeinstrom)`` -- Treppenhauslicht wird nach Flaeche
verteilt, nicht je Wohnung gemessen. **Die Goldens sind unveraendert**:
welche Kostenart die Rechnung traegt, aendert an der Rechnung nichts.

NK-046 hat **einen** Golden bewegt, und das war der Zweck der Karte:
GOLDEN_PERSONEN_MIDYEAR_JUL_DEC. Der Personenschluessel teilte durch die
**Anzahl** der Mietverhaeltnisse im Zeitraum und stutzte den Betrag
ausserdem auf die Mietzeit -- wer im Juli einzog, wurde zweimal
zeitanteilig gekuerzt und zahlte 301,64 EUR statt der 401,45 EUR, die auf
ihn entfallen. Seither wird nach Personentagen verteilt (R-NUM-04). Die
beiden Faelle unten hiessen ...counts_tenant_rows... und
...uses_headcount_not_person_days...: sie hielten den Befund fest, den die
Karte behoben hat. Alle uebrigen Goldens sind unveraendert -- bei gleich
grossen, ganzjaehrigen Haushalten ist die Verteilung nach Personentagen
dieselbe wie die nach Koepfen.

NK-098 hat denselben Golden ein zweites Mal bewegt: Wohnung B stand bis
zum Einzug am 01.07. leer, und ihre 182 Personentage tauchten -- wie jede
Wohnung ohne Mietverhaeltnis -- nicht im Nenner auf. Der still verteilte
Rest ist jetzt als Vermieteranteil ausgewiesen (R-NUM-05): 184 von 732
Personentagen, 301,64 EUR. Dass die Zahl wieder die des alten Fehlers ist,
ist Zufall der Arithmetik -- die Wege dorthin sind verschiedene.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix.billing_engine import BillingEngine

from tests.billing_factories import (
    YEAR_END,
    YEAR_START,
    apt,
    category,
    house,
    invoice,
    meter,
    payment,
    profile,
    reading,
    tenant,
)

# --- pinned IST goldens (leap year 2024, 366 inclusive days) ---
NULL_EURO = Decimal("0.00")
GOLDEN_QM_50_OF_150_ON_1200 = Decimal("400.00")
GOLDEN_PERSONEN_TWO_HEADS_ON_1200 = Decimal("600.00")
GOLDEN_MIDYEAR_QM_JUL_DEC = Decimal("201.09")  # 1200 * 184/366 * 50/150, dann runde()
GOLDEN_PERSONEN_MIDYEAR_JUL_DEC = Decimal("301.64")  # 1200 * 184/(366+184+182) Personentage
GOLDEN_METER_EXACT_CONSUMPTION = Decimal("366.00")
GOLDEN_DIREKT_WITH_ALLGEMEIN = Decimal("1330.00")
GOLDEN_NUR_ALLGEMEIN = Decimal("330.00")
GOLDEN_DIREKT_NO_MAIN = Decimal("1220.00")
GOLDEN_WOHNUNGSRECHNUNG_VOLL = Decimal("500.00")  # 500 * 366/366, nur diese Wohnung


def _bill(tenant_id, start=YEAR_START, end=YEAR_END, category_ids=None):
    return BillingEngine(tenant_id, start, end, category_ids=category_ids).calculate_bill()


def test_qm_full_year_sqm_share(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "B", 100)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0, invoice_number="G-1")

    bill = _bill(t.id)
    assert len(bill["line_items"]) == 1
    item = bill["line_items"][0]
    assert item["billing_type"] == "qm"
    assert item["tenant_cost"] == GOLDEN_QM_50_OF_150_ON_1200
    assert bill["total_amount"] == GOLDEN_QM_50_OF_150_ON_1200
    assert item["overlap_days"] == 366
    assert item["invoice_days"] == 366
    assert bill["warnings"] == []


def test_personen_zwei_gleiche_haushalte_teilen_haelftig(app_ctx):
    """Zwei ungepflegte Mietverhaeltnisse, ganzjaehrig: der Golden bleibt.

    Vor NK-046 hiess dieser Fall ...counts_tenant_rows_not_household_size
    und hielt fest, dass der Zweig Zeilen zaehlte statt Koepfe. Seither
    zaehlt er Personentage -- und weil ohne gepflegte Groesse ein Kopf gilt
    (``haushalt.VORGABE``) und beide das ganze Jahr da sind, kommt dieselbe
    Haelfte heraus. Nur der Wortlaut nennt jetzt, was gerechnet wurde.
    """
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    t1 = tenant(a, "Mieter A")
    tenant(b, "Mieter B")  # second head; no profile needed to be counted
    cat = category("Gebäudeversicherung")
    profile(t1, cat, "personen")
    invoice(prop, cat, 1200.0)

    bill = _bill(t1.id)
    item = bill["line_items"][0]
    assert item["billing_type"] == "personen"
    assert item["tenant_cost"] == GOLDEN_PERSONEN_TWO_HEADS_ON_1200
    assert "366 von 732 Personentagen" in item["description"]


def test_apartment_id_invoice_geht_voll_an_diese_wohnung(app_ctx):
    """Eine Rechnung mit apartment_id gehoert zu 100 Prozent dieser Wohnung.

    Dieser Test hielt bis NK-037 das Gegenteil fest: die Umlageschleife setzte
    neun Namen je Durchgang zurueck und sieben nicht, darunter ``is_abwasser``
    und ``main_meter``. Jede Rechnung auf eine Wohnung starb deshalb mit
    ``UnboundLocalError`` -- oder, schlimmer, rechnete mit dem Hauptzaehler
    einer fremden Rechnung aus einem frueheren Durchgang weiter und lieferte
    stillschweigend falsche Zahlen. Das war F-19.

    NK-037 hat den Schleifenkopf vervollstaendigt (``rechenkern.rechne``).
    Der Test bleibt stehen, jetzt als Waechter ueber der Behebung: was vorher
    platzte, muss jetzt rechnen, und was es rechnet, steht hier als Zahl.
    """
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    t_a = tenant(a, "Mieter A")
    t_b = tenant(b, "Mieter B")
    cat = category("Sonstiges")
    profile(t_a, cat, "qm")
    profile(t_b, cat, "qm")
    invoice(prop, cat, 500.0, apartment=a, invoice_number="DIR-A")

    bill_a = _bill(t_a.id)
    item = bill_a["line_items"][0]
    assert item["tenant_cost"] == GOLDEN_WOHNUNGSRECHNUNG_VOLL
    assert item["billing_type"] == "direkt"
    # Die Beschriftung hieß "Nach Verbrauch", obwohl hier nichts gemessen
    # wurde (F-20) -- seit der Beschriftungsdurchsicht (NK-066, Phase 5)
    # heißt sie "Direkt zugewiesen". Die Umkehrung ist im Commit begründet.
    assert item["description"] == (
        "Direkt zugewiesen (100 % der Rechnung für diese Wohnung)"
    )
    assert bill_a["total_amount"] == GOLDEN_WOHNUNGSRECHNUNG_VOLL

    # Der Nachbar sieht die Rechnung nicht: sie faellt vor jeder Umlage raus.
    bill_b = _bill(t_b.id)
    assert bill_b["line_items"] == []
    assert bill_b["total_amount"] == NULL_EURO


def test_ignoriert_is_zero_line(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "ignoriert")
    invoice(prop, cat, 999.0)

    bill = _bill(t.id)
    assert len(bill["line_items"]) == 1
    assert bill["line_items"][0]["tenant_cost"] == NULL_EURO
    assert bill["line_items"][0]["billing_type"] == "ignoriert"
    assert bill["total_amount"] == NULL_EURO


def test_missing_profile_defaults_to_qm(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "B", 100)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    invoice(prop, cat, 1200.0)

    bill = _bill(t.id)
    assert bill["line_items"][0]["billing_type"] == "qm"
    assert bill["line_items"][0]["tenant_cost"] == GOLDEN_QM_50_OF_150_ON_1200


def test_allocation_method_on_category_is_ignored(app_ctx):
    """Wasserversorgung is seeded METER_READING; profile qm still splits by sqm."""
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "B", 100)
    t = tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    assert cat.allocation_method == "METER_READING"
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0)

    bill = _bill(t.id)
    assert bill["line_items"][0]["billing_type"] == "qm"
    assert bill["line_items"][0]["tenant_cost"] == GOLDEN_QM_50_OF_150_ON_1200


def test_constructor_clips_to_move_in_and_move_out(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    t = tenant(a, "Kurz", move_in=date(2024, 7, 1), move_out=date(2024, 9, 30))
    engine = BillingEngine(t.id, YEAR_START, YEAR_END)
    assert engine.start_date == date(2024, 7, 1)
    assert engine.end_date == date(2024, 9, 30)


def test_overlap_days_are_inclusive(app_ctx):
    engine = BillingEngine.__new__(BillingEngine)
    days = engine.get_overlap_days(
        date(2024, 1, 1), date(2024, 1, 10), date(2024, 1, 10), date(2024, 1, 20)
    )
    assert days == 1
    assert engine.get_overlap_days(
        date(2024, 1, 1), date(2024, 1, 5), date(2024, 1, 6), date(2024, 1, 10)
    ) == 0


def test_midyear_move_in_prorates_qm(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "B", 100)
    t = tenant(a, "Ab Juli", move_in=date(2024, 7, 1))
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0)

    bill = _bill(t.id)
    item = bill["line_items"][0]
    assert bill["start_date"] == "2024-07-01"
    assert item["overlap_days"] == 184
    assert item["invoice_days"] == 366
    assert item["tenant_cost"] == GOLDEN_MIDYEAR_QM_JUL_DEC
    assert bill["total_amount"] == GOLDEN_MIDYEAR_QM_JUL_DEC


def test_personen_beim_einzug_zur_jahresmitte_nach_personentagen(app_ctx):
    """Der eine Golden, den NK-046 bewegt hat -- und den NK-098 weiterbewegt.

    Wer am 01.07. einzieht, war 184 von 732 Personentagen da und traegt
    301,64 EUR. Vor NK-046 wurde doppelt zeitanteilig gekuerzt (301,64 EUR),
    danach nach 550 Personentagen verteilt (401,45 EUR) -- aber Wohnung B
    stand bis zum Einzug leer und ihre 182 Personentage fehlten im Nenner,
    der still auf A und den Einziehenden verteilt wurde. Seit NK-098 zaehlt
    sie wie ein Einpersonenhaushalt: 366 + 184 + 182 = 732 Personentage, der
    Leerstandsanteil bleibt beim Vermieter und wird ausgewiesen.
    """
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    tenant(a, "Ganzjahr")
    t2 = tenant(b, "Halbjahr", move_in=date(2024, 7, 1))
    cat = category("Gebäudeversicherung")
    profile(t2, cat, "personen")
    invoice(prop, cat, 1200.0)

    bill = _bill(t2.id)
    item = bill["line_items"][0]
    assert item["overlap_days"] == 184
    assert "184 von 732 Personentagen" in item["description"]
    assert item["tenant_cost"] == GOLDEN_PERSONEN_MIDYEAR_JUL_DEC


def test_inactive_apartment_excluded_from_qm_denominator(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "Leer inaktiv", 80, is_active=False)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0)

    bill = _bill(t.id)
    assert bill["line_items"][0]["tenant_cost"] == Decimal("1200.00")
    assert "50 von 50 m²" in bill["line_items"][0]["description"]


def test_vacant_active_apartment_stays_in_qm_denominator(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "Leer aktiv", 100, is_active=True)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0)

    bill = _bill(t.id)
    assert bill["line_items"][0]["tenant_cost"] == GOLDEN_QM_50_OF_150_ON_1200
    assert "50 von 150 m²" in bill["line_items"][0]["description"]


def test_meter_exact_coverage_consumption_and_status(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    m = meter(prop, cat, "H-1", is_main=True)
    reading(m, YEAR_START, 1000.0)
    reading(m, date(2025, 1, 1), 1366.0)

    detail = BillingEngine.get_meter_consumption_detailed(m.id, YEAR_START, YEAR_END)
    assert detail["consumption"] == GOLDEN_METER_EXACT_CONSUMPTION
    assert BillingEngine.get_meter_consumption(m.id, YEAR_START, YEAR_END) == GOLDEN_METER_EXACT_CONSUMPTION
    assert detail["target_days"] == 366
    assert detail["status"] == "excellent"
    assert detail["is_interpolated"] is False
    assert detail["start_offset_days"] == 0
    assert detail["end_offset_days"] == 1
    assert isinstance(detail["consumption"], float)


def test_meter_interpolation_fallback_and_warning_when_missing_days(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    m = meter(prop, cat, "H-2", is_main=True)
    reading(m, date(2024, 1, 15), 1000.0)
    reading(m, date(2024, 12, 15), 1335.0)

    detail = BillingEngine.get_meter_consumption_detailed(m.id, YEAR_START, YEAR_END)
    assert detail["consumption"] == GOLDEN_METER_EXACT_CONSUMPTION
    assert detail["status"] == "warning"
    assert detail["is_interpolated"] is True
    assert detail["start_offset_days"] == 14
    assert detail["end_offset_days"] == 16


def test_meter_dual_tariff_adds_value_nt(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    m = meter(prop, cat, "H-NT", is_main=True)
    reading(m, YEAR_START, 100.0, value_nt=20.0)
    reading(m, date(2025, 1, 1), 200.0, value_nt=40.0)

    detail = BillingEngine.get_meter_consumption_detailed(m.id, YEAR_START, YEAR_END)
    assert detail["consumption"] == 120.0
    assert detail["r_start"]["total"] == 120.0
    assert detail["r_end"]["total"] == 240.0


def test_meter_fewer_than_two_readings_is_no_data(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    m = meter(prop, cat, "H-empty", is_main=True)
    reading(m, YEAR_START, 10.0)

    detail = BillingEngine.get_meter_consumption_detailed(m.id, YEAR_START, YEAR_END)
    assert detail["status"] == "no_data"
    assert detail["consumption"] == 0.0
    assert detail["is_interpolated"] is True


def test_direkt_eigenverbrauch_plus_allgemein_person_days(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    t1 = tenant(a, "Mieter A")
    t2 = tenant(b, "Mieter B")
    cat = category("Wasserversorgung")
    profile(t1, cat, "direkt")
    profile(t2, cat, "direkt")
    invoice(prop, cat, 3660.0)
    main = meter(prop, cat, "MAIN", is_main=True)
    sub_a = meter(prop, cat, "A", is_main=False, apartment=a)
    sub_b = meter(prop, cat, "B", is_main=False, apartment=b)
    for m, v0, v1 in ((main, 1000.0, 1366.0), (sub_a, 1000.0, 1100.0), (sub_b, 1000.0, 1200.0)):
        reading(m, YEAR_START, v0)
        reading(m, date(2025, 1, 1), v1)

    bill = _bill(t1.id)
    item = bill["line_items"][0]
    assert item["billing_type"] == "direkt"
    assert item["tenant_cost"] == GOLDEN_DIREKT_WITH_ALLGEMEIN
    assert bill["total_amount"] == GOLDEN_DIREKT_WITH_ALLGEMEIN
    md = item["meter_details"]
    assert md["main_consumption"] == 366.0
    assert md["sum_sub_consumption"] == 300.0
    assert md["allgemein_consumption"] == 66.0
    assert md["tenant_consumption"] == 100.0
    assert md["cost_per_unit"] == Decimal("10.0000")
    assert md["active_tenants"] == 2
    costs = {s["type"]: s["cost"] for s in item["sub_items"]}
    assert costs["eigenverbrauch"] == 1000.0
    assert costs["allgemein"] == 330.0


def test_nur_allgemein_excludes_eigenverbrauch(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    t1 = tenant(a, "Mieter A")
    tenant(b, "Mieter B")
    cat = category("Wasserversorgung")
    profile(t1, cat, "nur_allgemein")
    invoice(prop, cat, 3660.0)
    main = meter(prop, cat, "MAIN", is_main=True)
    sub_a = meter(prop, cat, "A", is_main=False, apartment=a)
    sub_b = meter(prop, cat, "B", is_main=False, apartment=b)
    for m, v0, v1 in ((main, 1000.0, 1366.0), (sub_a, 1000.0, 1100.0), (sub_b, 1000.0, 1200.0)):
        reading(m, YEAR_START, v0)
        reading(m, date(2025, 1, 1), v1)

    bill = _bill(t1.id)
    item = bill["line_items"][0]
    assert item["billing_type"] == "nur_allgemein"
    assert item["tenant_cost"] == GOLDEN_NUR_ALLGEMEIN
    assert all(s["type"] == "allgemein" for s in item["sub_items"])


def test_direkt_without_main_meter_uses_submeter_share_only(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    t1 = tenant(a, "Mieter A")
    tenant(b, "Mieter B")
    cat = category("Wasserversorgung")
    profile(t1, cat, "direkt")
    invoice(prop, cat, 3660.0)
    sub_a = meter(prop, cat, "A", is_main=False, apartment=a)
    sub_b = meter(prop, cat, "B", is_main=False, apartment=b)
    for m, v0, v1 in ((sub_a, 1000.0, 1100.0), (sub_b, 1000.0, 1200.0)):
        reading(m, YEAR_START, v0)
        reading(m, date(2025, 1, 1), v1)

    bill = _bill(t1.id)
    item = bill["line_items"][0]
    assert item["tenant_cost"] == GOLDEN_DIREKT_NO_MAIN
    assert "ohne Hauptzähler" in item["description"]


def test_nur_allgemein_without_main_meter_is_zero(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    t1 = tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    profile(t1, cat, "nur_allgemein")
    invoice(prop, cat, 3660.0)
    sub_a = meter(prop, cat, "A", is_main=False, apartment=a)
    reading(sub_a, YEAR_START, 1000.0)
    reading(sub_a, date(2025, 1, 1), 1100.0)

    bill = _bill(t1.id)
    item = bill["line_items"][0]
    assert item["tenant_cost"] == NULL_EURO
    assert "Entfällt" in item["description"]


def test_python3_round_is_bankers_rounding(app_ctx):
    assert round(2.5) == 2
    assert round(3.5) == 4
    # float 1.225 is 1.2250000000000001 → round-half-even lands on 1.23
    assert round(1.225, 2) == 1.23


def test_total_amount_ist_die_summe_der_gerundeten_zeilen(app_ctx):
    """R-NUM-01: total_amount += runde(zeile), nicht runde(summe(ungerundet)).

    Der Aufbau ist der Grenzfall, an dem die beiden Wege auseinanderlaufen:
    zwei Wohnungen zu je 50 qm, zwei Rechnungen ueber 1,01 EUR. Jede Zeile
    ist 1,01 * 50/100 = 0,505 -- genau eine halbe Cent-Stelle.

    Bis NK-036 stand hier das Gegenteil, als Kennzeichnung des IST: die
    Zeilen wurden einzeln auf 0,51 gerundet, zusammen 1,02, der Gesamtbetrag
    dagegen aus den ungerundeten 0,505 gebildet und erst am Ende auf 1,01
    gerundet. Der Mieter, der die Spalte nachaddiert, kam also auf einen
    anderen Betrag als den, der unter dem Strich stand -- einen Cent, zu dem
    es keine Zeile gab.

    Jetzt zaehlt die Rechnung, die der Mieter nachrechnen kann.
    """
    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 50)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1.01, invoice_number="R1")
    invoice(prop, cat, 1.01, invoice_number="R2")

    bill = _bill(t.id)
    line_sum = sum(item["tenant_cost"] for item in bill["line_items"])
    # je Zeile 1.01 * 50/100 = 0.505, kaufmaennisch gerundet 0.51
    assert bill["line_items"][0]["tenant_cost"] == Decimal("0.51")
    assert bill["line_items"][1]["tenant_cost"] == Decimal("0.51")
    assert line_sum == Decimal("1.02")
    assert bill["total_amount"] == Decimal("1.02")
    assert line_sum == bill["total_amount"]


def test_prepayments_only_nebenkostenvorauszahlung_and_balance(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "B", 100)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0)
    payment(t, 150.0, date(2024, 3, 1), "Nebenkostenvorauszahlung")
    payment(t, 50.0, date(2024, 6, 1), "Nebenkostenvorauszahlung")
    payment(t, 999.0, date(2024, 4, 1), "Miete")
    payment(t, 40.0, date(2023, 12, 31), "Nebenkostenvorauszahlung")

    bill = _bill(t.id)
    assert bill["total_amount"] == GOLDEN_QM_50_OF_150_ON_1200
    assert bill["prepaid_amount"] == Decimal("200.00")
    assert bill["balance"] == Decimal("200.00")
    assert len(bill["prepayments"]) == 2


def test_category_ids_filter_skips_other_invoices(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    apt(prop, "B", 100)
    t = tenant(a, "Mieter A")
    grund = category("Grundsteuer")
    vers = category("Gebäudeversicherung")
    profile(t, grund, "qm")
    profile(t, vers, "qm")
    invoice(prop, grund, 1200.0, invoice_number="G")
    invoice(prop, vers, 300.0, invoice_number="V")

    bill = _bill(t.id, category_ids=[grund.id])
    assert len(bill["line_items"]) == 1
    assert bill["line_items"][0]["category"] == "Grundsteuer"
    assert bill["total_amount"] == GOLDEN_QM_50_OF_150_ON_1200


def test_zero_overlap_invoice_omitted(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 100.0, start=date(2023, 1, 1), end=date(2023, 12, 31))

    bill = _bill(t.id)
    assert bill["line_items"] == []
    assert bill["total_amount"] == NULL_EURO


def test_preflight_excellent_on_exact_meter_coverage(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    t = tenant(a, "Mieter A")
    cat = category("Wasserversorgung")
    profile(t, cat, "direkt")
    invoice(prop, cat, 10.0)
    main = meter(prop, cat, "MAIN", is_main=True)
    sub = meter(prop, cat, "A", is_main=False, apartment=a)
    for m in (main, sub):
        reading(m, YEAR_START, 1.0)
        reading(m, date(2025, 1, 1), 2.0)

    result = BillingEngine(t.id, YEAR_START, YEAR_END).preflight_check()
    assert result["overall"] == "excellent"
    assert len(result["checks"]) == 2


def test_warnings_list_stays_empty(app_ctx):
    prop = house()
    a = apt(prop, "A", 50)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    invoice(prop, cat, 10.0)
    bill = _bill(t.id)
    assert bill["warnings"] == []


def test_get_overlap_days_full_year_leap(app_ctx):
    engine = BillingEngine.__new__(BillingEngine)
    assert engine.get_overlap_days(YEAR_START, YEAR_END, YEAR_START, YEAR_END) == 366
