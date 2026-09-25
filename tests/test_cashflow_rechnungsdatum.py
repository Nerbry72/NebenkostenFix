"""NK-120: Der Cashflow ordnet eine Rechnung nach ihrem Ausstellungsdatum ein.

Folgekarte aus dem Abschluss von Phase 6: Der Cashflow in
``GET /api/analytics/building/<id>`` nahm das Jahr aus dem Upload des
verknüpften Belegs. Das ist der Tag, an dem jemand den Beleg in die Software
geladen hat, nicht der Tag auf dem Beleg. Dieselbe Rechnung landete deshalb
je nach Erfassungstag in einem anderen Jahr — wer die Belege eines Jahres
im Januar nachträgt, sah sie im falschen Jahr.

Seit NK-058 trägt die Rechnung ihr Ausstellungsdatum (``rechnungsdatum``,
D-57). Das zählt jetzt zuerst. Fehlt es (Altbestand, NULL), gilt der
bisherige Rückfall: Upload des Belegs, sonst Beginn des Rechnungszeitraums.

*Hätte den Befund gefunden:* ``test_ausstellungsdatum_schlaegt_upload`` —
vorher stand der Betrag im Jahr des Uploads.

Die Daten sind synthetisch. Die Jahre hängen am heutigen Tag, damit
„vergangen“ und „Vorschau“ unabhängig vom Laufdatum stimmen.
"""

from __future__ import annotations

from datetime import date, timedelta

from models import InvoiceDocument, db
from tests import billing_factories as f

HEUTE = date.today()
VORJAHR = HEUTE.year - 1
VORVORJAHR = HEUTE.year - 2


def _rechnung(betrag, *, rechnungsdatum=None, upload=None, beginn=None):
    haus = f.house()
    kat = f.category("Grundsteuer")
    beginn = beginn or date(VORVORJAHR, 1, 1)
    inv = f.invoice(haus, kat, betrag, start=beginn, end=date(beginn.year, 12, 31))
    inv.rechnungsdatum = rechnungsdatum
    if upload is not None:
        beleg = InvoiceDocument(property_id=haus.id, filename="beleg.pdf",
                                document_path="beleg.pdf", upload_date=upload)
        db.session.add(beleg)
        db.session.flush()
        inv.invoice_document_id = beleg.id
    db.session.commit()
    return haus


def _cashflow(client, haus):
    antwort = client.get(f"/api/analytics/building/{haus.id}")
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    daten = antwort.get_json()
    return {z["year"]: z for z in daten["cashflow"]}, daten["kpis"]


def test_ausstellungsdatum_schlaegt_upload(auth_client):
    """Ausgestellt im Vorjahr, heute hochgeladen: zählt im Vorjahr."""
    haus = _rechnung(300.0, rechnungsdatum=date(VORJAHR, 3, 15), upload=HEUTE)

    jahre, kpis = _cashflow(auth_client, haus)

    assert set(jahre) == {str(VORJAHR)}
    assert jahre[str(VORJAHR)]["out_actual"] == 300.0
    assert jahre[str(VORJAHR)]["out_forecast"] == 0
    # Im laufenden Jahr ist nichts abgeflossen.
    assert kpis["cashflow_ytd"] == 0


def test_ausstellungsdatum_in_der_zukunft_ist_vorschau(auth_client):
    """Ein Beleg mit Datum nach heute zählt als Vorschau, nicht als Abfluss."""
    morgen = HEUTE + timedelta(days=1)
    haus = _rechnung(120.0, rechnungsdatum=morgen, upload=HEUTE)

    jahre, _ = _cashflow(auth_client, haus)

    zeile = jahre[str(morgen.year)]
    assert zeile["out_actual"] == 0
    assert zeile["out_forecast"] == 120.0


def test_ohne_ausstellungsdatum_gilt_der_upload(auth_client):
    """Altbestand ohne ``rechnungsdatum``: der Upload des Belegs, wie bisher."""
    haus = _rechnung(200.0, upload=date(VORJAHR, 6, 1))

    jahre, _ = _cashflow(auth_client, haus)

    assert set(jahre) == {str(VORJAHR)}
    assert jahre[str(VORJAHR)]["out_actual"] == 200.0


def test_ohne_datum_und_beleg_gilt_der_zeitraumbeginn(auth_client):
    """Weder Ausstellungsdatum noch Beleg: der Beginn des Rechnungszeitraums."""
    haus = _rechnung(80.0, beginn=date(VORVORJAHR, 1, 1))

    jahre, _ = _cashflow(auth_client, haus)

    assert set(jahre) == {str(VORVORJAHR)}
    assert jahre[str(VORVORJAHR)]["out_actual"] == 80.0


def test_laufendes_jahr_zaehlt_nach_ausstellungsdatum(auth_client):
    """Der KPI „Cashflow lfd. Jahr“ nimmt dieselbe Regel wie die Jahreszeilen.

    Upload im Vorjahr, ausgestellt im laufenden Jahr (bis gestern): der
    Abfluss gehört ins laufende Jahr.
    """
    ausgestellt = max(date(HEUTE.year, 1, 1), HEUTE - timedelta(days=1))
    haus = _rechnung(50.0, rechnungsdatum=ausgestellt, upload=date(VORJAHR, 12, 1))

    _, kpis = _cashflow(auth_client, haus)

    assert kpis["cashflow_ytd"] == -50.0
