"""NK-027: Flaechendaten-Guard fuer die Umlage nach Quadratmetern.

Vor dieser Karte teilte billing_engine.py ungeschuetzt durch die Gesamtflaeche.
Eine Immobilie ohne Flaechendaten lieferte ZeroDivisionError, app.py machte
daraus einen 500er, und der Vermieter las "float division by zero".
"""

from __future__ import annotations

import pytest

from billing_engine import BillingDataError, BillingEngine

from tests.billing_factories import (
    YEAR_END,
    YEAR_START,
    apt,
    category,
    house,
    invoice,
    profile,
    tenant,
)


def _engine(tenant_id, category_ids=None):
    return BillingEngine(tenant_id, YEAR_START, YEAR_END, category_ids=category_ids)


def _qm_setup(sqm_a, sqm_b=None, b_active=True, a_active=True):
    """Baut ein Haus mit qm-Umlage. Gibt (Mieter, Kategorie) zurueck."""
    prop = house("Flaechenhaus")
    a = apt(prop, "A", sqm_a, is_active=a_active)
    if sqm_b is not None:
        apt(prop, "B", sqm_b, is_active=b_active)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "qm")
    invoice(prop, cat, 1200.0, invoice_number="F-1")
    return t, cat


# --- Rechenkern: Meldung statt Division ---

def test_keine_aktive_wohnung_meldet_statt_zu_teilen(app_ctx):
    t, _ = _qm_setup(50, a_active=False)
    with pytest.raises(BillingDataError) as exc:
        _engine(t.id).calculate_bill()
    text = str(exc.value)
    assert "Flaechenhaus" in text
    assert "keine aktive Wohnung" in text


def test_gesamtflaeche_null_meldet_statt_zu_teilen(app_ctx):
    t, _ = _qm_setup(0, sqm_b=0)
    with pytest.raises(BillingDataError) as exc:
        _engine(t.id).calculate_bill()
    text = str(exc.value)
    assert "Flaechenhaus" in text
    assert "Quadratmeter" in text


def test_eigene_wohnung_ohne_flaeche_meldet_statt_zu_teilen(app_ctx):
    t, _ = _qm_setup(0, sqm_b=100)
    with pytest.raises(BillingDataError) as exc:
        _engine(t.id).calculate_bill()
    assert "'A'" in str(exc.value)


def test_meldung_ist_keine_division_durch_null(app_ctx):
    t, _ = _qm_setup(0, sqm_b=0)
    with pytest.raises(BillingDataError) as exc:
        _engine(t.id).calculate_bill()
    assert "division by zero" not in str(exc.value).lower()


def test_fehlende_flaeche_bei_nachbarwohnung_ist_nur_eine_warnung(app_ctx):
    t, _ = _qm_setup(50, sqm_b=0)
    bill = _engine(t.id).calculate_bill()
    # 50 von 50 qm, weil B keine Flaeche hat: rechenbar, aber zu teuer.
    assert bill["line_items"][0]["tenant_cost"] == 1200.0
    assert any("B" in w for w in bill["warnings"])


def test_ohne_qm_position_bleibt_die_abrechnung_unberuehrt(app_ctx):
    """Eine Abrechnung ohne qm-Umlage braucht die Gesamtflaeche gar nicht."""
    prop = house("Flaechenhaus")
    a = apt(prop, "A", 0)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "personen")
    invoice(prop, cat, 1200.0, invoice_number="F-2")

    bill = _engine(t.id).calculate_bill()
    assert bill["line_items"][0]["tenant_cost"] == 1200.0


# --- Vorpruefung: der Fall wird vor der Abrechnung gemeldet ---

def test_vorpruefung_meldet_fehlende_gesamtflaeche(app_ctx):
    t, _ = _qm_setup(0, sqm_b=0)
    result = _engine(t.id).preflight_check()
    flaeche = [c for c in result["checks"] if c["category"] == "Wohnflaeche"]
    assert len(flaeche) == 1
    assert flaeche[0]["status"] == "no_data"
    assert flaeche[0]["blocking"] is True
    assert "Quadratmeter" in flaeche[0]["message"]
    assert result["overall"] == "warning"


def test_vorpruefung_meldet_teilflaeche_als_nicht_blockend(app_ctx):
    t, _ = _qm_setup(50, sqm_b=0)
    result = _engine(t.id).preflight_check()
    flaeche = [c for c in result["checks"] if c["category"] == "Wohnflaeche"]
    assert len(flaeche) == 1
    assert flaeche[0]["blocking"] is False


def test_vorpruefung_schweigt_ohne_qm_position(app_ctx):
    prop = house("Flaechenhaus")
    a = apt(prop, "A", 0)
    t = tenant(a, "Mieter A")
    cat = category("Grundsteuer")
    profile(t, cat, "personen")
    invoice(prop, cat, 1200.0, invoice_number="F-3")

    result = _engine(t.id).preflight_check()
    assert [c for c in result["checks"] if c["category"] == "Wohnflaeche"] == []


def test_vorpruefung_liefert_die_gleichen_schluessel_wie_zaehlerpruefungen(app_ctx):
    """Das Frontend rendert alle checks ueber dieselben Felder."""
    t, _ = _qm_setup(0, sqm_b=0)
    check = _engine(t.id).preflight_check()["checks"][0]
    for key in ("category", "meter_type", "meter_number", "status",
                "is_interpolated", "start_offset_days", "end_offset_days"):
        assert key in check
