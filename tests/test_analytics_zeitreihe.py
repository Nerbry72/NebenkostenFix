"""NK-122: die Zeitreihe der Analytics summiert, statt zu überschreiben.

Fehlerbild: in ``GET /api/analytics/building/<id>`` begann der Kosten-
stand der Zeitreihe bei 0 und wurde mit ``=`` statt ``+=`` gesetzt -- die
zweite Rechnung desselben Jahres löschte die erste. Zwei Rechnungen über
je 200 EUR erschienen als eine über 200 EUR, und die Auswertung versprach
weniger Kosten, als geflossen sind.

Behoben in ``app.py`` (``cost_timeseries[key]['cost'] += inv.amount``).
Die Fälle hier rufen die Route auf, wie es die Oberfläche tut: zwei
Rechnungen desselben Jahres und desselben Bereichs müssen sich summieren,
zwei Bereiche desselben Jahres müssen getrennt bleiben.

Die Daten sind synthetisch, die Jahre hängen am heutigen Tag -- dieselbe
Konvention wie ``tests/test_cashflow_rechnungsdatum.py``.
"""

from __future__ import annotations

from datetime import date

from tests import billing_factories as f

VORJAHR = date.today().year - 1


def _zeitenreihe(client, haus):
    antwort = client.get(f"/api/analytics/building/{haus.id}")
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    return antwort.get_json()["timeseries_data"]


def test_zwei_rechnungen_eines_jahres_summieren_sich(auth_client):
    """Zweimal 200 EUR im selben Jahr und Bereich: 400 EUR, nicht 200.

    Vor der Korrektur stand hier 200.00 -- der Stand der zweiten Rechnung.
    """
    haus = f.house()
    kat = f.category("Grundsteuer")
    beginn = date(VORJAHR, 1, 1)
    f.invoice(haus, kat, 200.0, start=beginn, end=date(VORJAHR, 6, 30),
              invoice_number="INV-1")
    f.invoice(haus, kat, 200.0, start=date(VORJAHR, 7, 1),
              end=date(VORJAHR, 12, 31), invoice_number="INV-2")

    zeiten = _zeitenreihe(auth_client, haus)

    bereich = [z for z in zeiten
               if z["year"] == VORJAHR and z["category"] == "Sonstige Kosten"]
    assert len(bereich) == 1
    assert bereich[0]["cost"] == 400.0
    # Der Zeitraum spannt beide Rechnungen auf.
    assert "01.01." in bereich[0]["period"]
    assert "31.12." in bereich[0]["period"]


def test_zwei_bereiche_eines_jahres_bleiben_getrennt(auth_client):
    """Grundsteuer und Heizung teilen sich das Jahr, nicht den Stand.

    Der Schlüssel der Zeitreihe ist das Paar aus Jahr und Bereich; der
    Summierfehler hätte auch hier nichts zu suchen.
    """
    haus = f.house()
    grundsteuer = f.category("Grundsteuer")
    heizung = f.category("Heizung")
    beginn = date(VORJAHR, 1, 1)
    f.invoice(haus, grundsteuer, 150.0, start=beginn,
              end=date(VORJAHR, 12, 31), invoice_number="INV-G")
    f.invoice(haus, heizung, 90.0, start=beginn, end=date(VORJAHR, 12, 31),
              invoice_number="INV-H")

    zeiten = _zeitenreihe(auth_client, haus)

    jahr = [z for z in zeiten if z["year"] == VORJAHR]
    stehende = {z["category"]: z["cost"] for z in jahr}
    assert stehende == {"Sonstige Kosten": 150.0, "Gas": 90.0}
