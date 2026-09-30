"""NK-113: das Bezeichnungsfeld der Rechnung erscheint bei Nr. 17.

Befund aus dem Live-Abgleich (Phase 6, NK-110/NK-111, Klasse B — Fehler im
neuen Stand): Der Rechnungsdialog blendet das Feld „Bezeichnung“ nur für die
sonstigen Betriebskosten ein. ``toggleInvoiceDescription`` suchte dazu im
Namen der gewählten Kostenart nach „sonstiges“. Seit dem Katalog (NK-044)
heißt Nr. 17 aber „Sonstige Betriebskosten“ — das Feld blieb für jede
Kostenart verborgen, eine Bezeichnung ließ sich über die Oberfläche nicht
mehr eintragen. Im alten Stand hieß die Kostenart frei „Sonstiges“, dort
ging es.

Zwei Wächter:

1. **Oberfläche, statisch** — der Rumpf von ``toggleInvoiceDescription``
   vergleicht keinen Namen mehr, sondern die Katalognummer
   (``betrkv_nr === BETRKV_NR_SONSTIGE``, und die Konstante ist 17).
   *Hätte diesen Fehler gefunden:* der alte Rumpf enthielt
   ``.includes('sonstiges')``. Die DOM-Prüfung (sichtbar genau bei Nr. 17,
   für alle 18 Kostenarten) lebt im Rauchtest ``scripts/rauchtest_design.js``.
2. **API** — eine Rechnung der Nr. 17 trägt ihre Bezeichnung durch Speichern
   und Lesen; die Oberfläche braucht das Feld, damit sie ankommt.

Die Daten sind synthetisch.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from nebenkostenfix import betrkv

APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"


def _rumpf(name: str) -> str:
    quelle = APP_JS.read_text(encoding="utf-8")
    treffer = re.search(rf"function {name}\(\) \{{[\s\S]*?\n\}}", quelle)
    assert treffer, f"{name} nicht in static/app.js gefunden"
    return treffer.group(0)


def test_beschreibung_haengt_an_der_katalognummer():
    rumpf = _rumpf("toggleInvoiceDescription")
    assert "sonstiges" not in rumpf.lower(), (
        "toggleInvoiceDescription vergleicht wieder den Namen der Kostenart")
    assert ".text" not in rumpf, (
        "toggleInvoiceDescription liest den Anzeigetext statt der Kostenart")
    assert "betrkv_nr === BETRKV_NR_SONSTIGE" in rumpf


def test_konstante_ist_die_nummer_der_sonstigen_betriebskosten():
    quelle = APP_JS.read_text(encoding="utf-8")
    treffer = re.search(r"const BETRKV_NR_SONSTIGE = (\d+);", quelle)
    assert treffer, "BETRKV_NR_SONSTIGE fehlt in static/app.js"
    nr = int(treffer.group(1))
    eintrag = next(k for k in betrkv.KATALOG if k["nr"] == nr)
    assert nr == 17
    assert eintrag["name"].startswith("Sonstige")


@pytest.fixture
def stammdaten(auth_client):
    haus = auth_client.post("/api/properties", json={"name": "Beschreibungshaus"})
    assert haus.status_code == 201, haus.get_data(as_text=True)
    anbieter = auth_client.post("/api/providers", json={"name": "Hausdienst Probe"})
    assert anbieter.status_code == 201, anbieter.get_data(as_text=True)
    kategorien = auth_client.get("/api/categories").get_json()
    nr17 = next(k for k in kategorien if k["betrkv_nr"] == 17)
    return haus.get_json()["id"], anbieter.get_json()["id"], nr17["id"]


def test_bezeichnung_der_nr17_kommt_an(auth_client, stammdaten):
    haus_id, anbieter_id, kategorie_id = stammdaten
    res = auth_client.post("/api/invoices", data={
        "category_id": str(kategorie_id),
        "property_id": str(haus_id),
        "amount": "120.00",
        "invoice_number": "S-1",
        "description": "Schornsteinfeger",
        "provider_id": str(anbieter_id),
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "document_pages": "",
        "file": (io.BytesIO(b"%PDF-1.4\n%synthetisch\n"), "beleg.pdf"),
    }, content_type="multipart/form-data")
    assert res.status_code == 201, res.get_data(as_text=True)
    neu_id = res.get_json()["id"]
    liste = auth_client.get("/api/invoices").get_json()
    rechnung = next(r for r in liste if r["id"] == neu_id)
    assert rechnung["description"] == "Schornsteinfeger"
