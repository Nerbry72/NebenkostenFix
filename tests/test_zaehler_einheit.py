"""NK-220 (V3): Zähler und Ablesungen tragen die Einheit der Abrechnung.

Befund der App-Analyse vom 2026-10-06: die Zählerliste riet die Einheit aus
dem Namen der Kostenart -- „Strom“ wurde kWh, „Gas“/„Wasser“ m³, ein
Wärmezähler der Heizung bekam gar keine, und „Warmwasser“ (Nr. 6) wäre m³
geworden, obwohl die Abrechnung kWh rechnet. Jetzt liefert die API
``einheit`` aus ``rechenkern.einheit_fuer``, also aus dem Katalog.

*Hätte den Fehler gefunden:* jeder Test hier -- vorher fehlte ``einheit``.
"""

from datetime import date

import pytest

from nebenkostenfix.models import CostCategory
from tests import billing_factories as f


@pytest.mark.parametrize('nr, einheit', [
    (2, 'm³'),          # Wasserversorgung
    (4, 'kWh'),         # Heizung: vorher ohne Einheit
    (6, 'kWh'),         # verbundene Anlage: das Wort „Warmwasser“ riet m³
    (11, 'kWh'),        # Allgemeinstrom
])
def test_zaehler_und_ablesung_tragen_die_einheit(auth_client, app_ctx, nr, einheit):
    kategorie = CostCategory.query.filter_by(betrkv_nr=nr).first()
    zaehler = f.meter(f.house(), kategorie, 'Z-1', is_main=True)
    f.reading(zaehler, date(2025, 1, 1), 100.0)

    [z] = auth_client.get('/api/meters').get_json()
    [r] = auth_client.get('/api/readings').get_json()

    assert z['einheit'] == einheit
    assert r['einheit'] == einheit
