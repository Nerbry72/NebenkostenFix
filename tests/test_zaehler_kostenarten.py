"""NK-105 (D-63): ein Zaehler ist fuer jede Kostenart moeglich.

Fehlermeldung (2026-09-23, Dialog „Neuer Zähler"): „Beim
Zähler-Anlegen gibt es nur die Kategorie Wasserversorgung. Strom etc. kann
ich nicht auswählen." Ursache: der Dialog las ``requires_meter`` als
Erlaubniskennzeichen lesen. Das Feld heisst aber seit NK-044/D-33 nur
„ohne Zählerstand keine Abrechnung" und steht im Katalog allein bei der
Wasserversorgung (Nr. 2).

Die Auflage des Menschen ist Teil der Karte: **Es muss einen Test geben, der
prueft, dass alle Kategorien da sind.** Das sind hier zwei Wächter:

1. **API** — frische Datenbank mit Seed, eine Immobilie; für **jede**
   Kostenart legt ``POST /api/meters`` einen Zähler an und bekommt Erfolg;
   ``GET /api/meters`` liefert danach 18 Zähler mit 18 verschiedenen
   ``category_id``. Dazu die Koppelpruefung: die Anzahl der Kostenarten aus
   ``/api/categories`` ist ``len(betrkv.KATALOG)`` — damit zieht ein
   kuenftig hinzugefuegter Katalogeintrag diesen Test mit, statt ihn zu
   umgehen.
2. **Oberflaeche, statisch** — der Rumpf von ``openAddMeterModal()`` in
   ``static/app.js`` enthaelt kein ``requires_meter`` und keinen ``.filter(``
   auf ``categories``; die Auswahl wird aus der ganzen Liste gebaut.
   *Hätte diesen Fehler gefunden:* der alte Rumpf enthielt
   ``categories.filter(c => c.requires_meter)``.

Die DOM-Pruefung (18 Optionen im echten Dialog-Aufbau) lebt im
Host-Rauchtest ``scripts/rauchtest_design.js`` (``make rauchtest``), die
Kern-Pruefung (Zählerweg fuer eine Kostenart ohne Pflichtkennzeichen) in
``tests/test_rechenkern.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import betrkv

APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"


# --- Pruefung 1: die API nimmt einen Zaehler fuer jede Kostenart ------------


@pytest.fixture
def immobilie(auth_client):
    res = auth_client.post("/api/properties", json={"name": "Zaehlerpruefhaus"})
    assert res.status_code == 201, res.get_data(as_text=True)
    return res.get_json()


def test_kategorien_zaehlen_den_katalog(auth_client):
    """Die Koppelpruefung: was die API liefert, ist der ganze Katalog.

    Ohne sie koennte ein kuenftiger Seed die Halbierung des Angebots
    verstecken; mit ihr schlaegt jeder Katalogeintrag, den der Dialog
    verschluckt, hier an.
    """
    res = auth_client.get("/api/categories")
    assert res.status_code == 200
    assert len(res.get_json()) == len(betrkv.KATALOG)


def test_zaehler_fuer_jede_kostenart_anlegbar(auth_client, immobilie):
    """POST /api/meters gelingt für alle 18 Kostenarten des Katalogs."""
    kategorien = auth_client.get("/api/categories").get_json()
    assert len(kategorien) == len(betrkv.KATALOG)

    for k in kategorien:
        res = auth_client.post("/api/meters", json={
            "category_id": k["id"],
            "property_id": immobilie["id"],
            "meter_number": f"Z-{k['betrkv_nr']:02d}",
        })
        assert res.status_code == 201, (
            f"Zähler für Kostenart {k['betrkv_nr']} „{k['name']}“ nicht "
            f"anlegbar: {res.get_data(as_text=True)}"
        )

    meters = auth_client.get("/api/meters").get_json()
    assert len(meters) == len(betrkv.KATALOG)
    # 18 Zähler mit 18 verschiedenen Kostenarten — keiner wurde still
    # auf eine andere Kostenart umgebogen.
    assert len({m["category_id"] for m in meters}) == len(betrkv.KATALOG)


# --- Pruefung 2: der Dialog baut aus der ganzen Liste -----------------------


def _funktionsrumpf(name: str, quelle: str) -> str:
    """Der Koerper von ``function name()`` bis zur schliessenden Klammer.

    Die Klammer steht in Spalte 0, alles im Rumpf ist eingerueckt — der
    Schnitt auf dem ersten „\\n}" greift darum auch, wenn der Rumpf
    geschachtelte Klammen traegt.
    """
    beginn = quelle.index(f"function {name}()")
    ende = quelle.index("\n}", beginn)
    return quelle[beginn:ende]


def test_dialog_ohne_pflichtfilter():
    """Der Zähler-Dialog filtert nicht mehr nach ``requires_meter``.

    Der alte Rumpf las das Pflichtkennzeichen als Erlaubnis — genau die
    Verwechslung, die den Fehler machte. Der Wächter sieht in den Rumpf und
    schlaegt an, sobald wieder gefiltert wird.
    """
    rumpf = _funktionsrumpf("openAddMeterModal", APP_JS.read_text(encoding="utf-8"))
    assert "requires_meter" not in rumpf, (
        "openAddMeterModal liest requires_meter — das ist die Pflichtfrage, "
        "kein Erlaubniskennzeichen (NK-105, D-63)."
    )
    assert ".filter(" not in rumpf, (
        "openAddMeterModal filtert die Kostenarten — der Dialog muss die "
        "ganze Liste anbieten (NK-105, D-63)."
    )
    # Die Auswahl entsteht aus der gesamten Kategorienliste, in zwei
    # benannten Gruppen; belegt im DOM durch den Host-Rauchtest.
    assert "categories" in rumpf
    assert "Üblich mit Zähler" in rumpf
    assert "Weitere Kostenarten" in rumpf
