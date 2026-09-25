"""NK-118: die Haushaltsgröße lässt sich in der Oberfläche pflegen.

Befund der Oberflächenlücke aus dem Live-Abgleich (Phase 6): NK-045/NK-055
legten Tabelle und Routen an, die Oberfläche bot aber keinen Weg. Der
UI-Spieler musste die Haushaltsgröße über die Schnittstelle nachtragen und
schrieb dafür einen ``hinweis`` ins Protokoll.

Jetzt öffnet der Knopf „Haushaltsgröße“ in der Mieterzeile einen Dialog mit
den Stichtagen (ansehen, löschen) und den Feldern für einen neuen Stichtag
(anlegen, berichtigen — derselbe Tag überschreibt, D-39).

Geprüft wird hier, was ohne Browser geht:

1. **Dialog und Knopf** — ``index.html`` trägt ``household-modal`` mit
   Datums- und Zahlfeld (min 1) und dem Primärknopf „Haushaltsgröße
   speichern“; die Mieterzeile in ``app.js`` hängt den Knopf an.
2. **Kopplung an die Routen** — die Pfade und Methoden, die ``app.js``
   anspricht, gibt es in der Anwendung. Die Routen selbst prüft
   ``tests/test_nutzung.py``.

Das Verhalten der Funktionen (Liste, Leerzeile, Abweisen von 0 Personen)
prüft der Host-Rauchtest ``scripts/rauchtest_design.js``; den echten Klick im
Chromium macht der Browser-Rundgang (``scripts/rundgang.py``).

*Hätte die Lücke gefunden:* ``test_mieterzeile_hat_den_knopf`` — vorher gab
es weder Knopf noch Dialog.
"""

from __future__ import annotations


import re
from pathlib import Path

BASIS = Path(__file__).resolve().parents[1]
APP_JS = BASIS / "static" / "app.js"
INDEX = BASIS / "static" / "index.html"


def _dialog() -> str:
    html = INDEX.read_text(encoding="utf-8")
    beginn = html.index('id="household-modal"')
    ende = html.index("<!--", beginn)
    return html[beginn:ende]


def _funktionsrumpf(name: str, quelle: str) -> str:
    """Rumpf von ``[async] function name(`` bis zur Klammer in Spalte 0."""
    beginn = re.search(rf"(async )?function {name}\(", quelle).start()
    ende = quelle.index("\n}", beginn)
    return quelle[beginn:ende]


def test_dialog_hat_felder_und_knoepfe():
    dialog = _dialog()
    assert re.search(r'<input type="date" id="household-gueltig-ab"', dialog)
    assert re.search(r'<input type="number" id="household-personen" min="1"', dialog)
    assert 'id="household-list"' in dialog
    assert 'onclick="saveHouseholdSize()">Haushaltsgröße speichern</button>' in dialog
    assert 'onclick="closeHouseholdModal()">Schließen</button>' in dialog


def test_mieterzeile_hat_den_knopf():
    quelle = APP_JS.read_text(encoding="utf-8")
    assert "householdBtn.title = 'Haushaltsgröße';" in quelle
    assert "householdBtn.onclick = () => openHouseholdModal(t);" in quelle
    assert "tdActions.appendChild(householdBtn);" in quelle


def test_app_js_spricht_die_vorhandenen_routen_an(app_ctx):
    """Pfad und Methode aus app.js gibt es in der Anwendung wirklich."""
    quelle = APP_JS.read_text(encoding="utf-8")
    laden = _funktionsrumpf("loadHouseholdSizes", quelle)
    speichern = _funktionsrumpf("saveHouseholdSize", quelle)
    loeschen = _funktionsrumpf("deleteHouseholdSize", quelle)
    assert "fetch(`/api/tenants/${tenantId}/haushaltsgroessen`)" in laden
    assert "fetch(`/api/tenants/${tenantId}/haushaltsgroessen`, {" in speichern
    assert "method: 'POST'" in speichern
    assert "personenanzahl: personen" in speichern
    assert "gueltig_ab: gueltigAb" in speichern
    assert "fetch(`/api/haushaltsgroessen/${id}`, { method: 'DELETE' })" in loeschen

    regeln = {(r.rule, m) for r in app_ctx.app.url_map.iter_rules()
              for m in r.methods}
    assert ("/api/tenants/<int:tenant_id>/haushaltsgroessen", "GET") in regeln
    assert ("/api/tenants/<int:tenant_id>/haushaltsgroessen", "POST") in regeln
    assert ("/api/haushaltsgroessen/<int:id>", "DELETE") in regeln


def test_speichern_prueft_vor_dem_senden():
    """Ohne Stichtag oder mit weniger als einer Person geht nichts hinaus."""
    rumpf = _funktionsrumpf("saveHouseholdSize", APP_JS.read_text(encoding="utf-8"))
    vor_dem_senden = rumpf[:rumpf.index("fetch(")]
    assert "if (!gueltigAb)" in vor_dem_senden
    assert "personen < 1" in vor_dem_senden

