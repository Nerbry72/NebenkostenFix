"""NK-119: der Abrechnungszeitraum ist in der Oberfläche frei wählbar.

Befund der Oberflächenlücke aus dem Live-Abgleich (Phase 6): Der Dialog
„Abrechnung erstellen“ nahm den Zeitraum stumm aus den vorgeschlagenen
Kategorien (frühester Beginn, spätestes Ende). Einen anderen Zeitraum — etwa
vom Einzug bis zum Stichtag — bot er nicht. Der UI-Spieler musste solche
Abrechnungen über die Schnittstelle erzeugen und schrieb dafür einen
``hinweis`` ins Protokoll.

Jetzt trägt der Dialog zwei Datumsfelder. Sie sind aus der Auswahl
vorbelegt, folgen ihr, bis sie von Hand geändert werden, und gehen
unverändert an Vorschau und Festsetzung. Vor dem Senden prüft die Oberfläche
nur, dass beide Tage da sind und der Beginn nicht nach dem Ende liegt; die
Überschneidung mit festgesetzten Abrechnungen prüft der Server (D-55).

Geprüft wird hier, was ohne Browser geht:

1. **Dialog** — ``index.html`` trägt beide Datumsfelder mit Beschriftung,
   die Kategorienliste bleibt ein eigener Behälter.
2. **Ablauf** — der Weiter-Knopf nimmt die Felder statt der errechneten
   Grenzen und prüft vor dem Senden.

Das Verhalten der Vorbelegung und der Prüfung rechnet der Host-Rauchtest
``scripts/rauchtest_design.js`` nach; den echten Klick im Chromium macht der
Browser-Rundgang (``scripts/rundgang.py``).

*Hätte die Lücke gefunden:* ``test_dialog_hat_die_zeitraumfelder`` — vorher
gab es keine Felder.
"""

from __future__ import annotations


import re
from pathlib import Path

BASIS = Path(__file__).resolve().parents[1]
APP_JS = BASIS / "static" / "app.js"
INDEX = BASIS / "static" / "index.html"


def _dialog() -> str:
    html = INDEX.read_text(encoding="utf-8")
    beginn = html.index('id="billing-selection-modal"')
    ende = html.index("<!--", html.index('id="btn-proceed-preview"'))
    return html[beginn:ende]


def _funktionsrumpf(name: str, quelle: str) -> str:
    """Rumpf von ``[async] function name(`` bis zur Klammer in Spalte 0."""
    beginn = re.search(rf"(async )?function {name}\(", quelle).start()
    ende = quelle.index("\n}", beginn)
    return quelle[beginn:ende]


def test_dialog_hat_die_zeitraumfelder():
    dialog = _dialog()
    for feld, text in (("billing-period-start", "Beginn des Abrechnungszeitraums"),
                       ("billing-period-end", "Ende des Abrechnungszeitraums")):
        # NK-158: hinter dem Text darf das „?“ des Begriffs stehen.
        assert f'<label for="{feld}">{text}' in dialog
        assert f'<input type="date" id="{feld}" required>' in dialog
    # Die Kategorienliste wird neu geschrieben — die Felder liegen außerhalb.
    assert '<div id="billing-selection-body"></div>' in dialog


def test_weiter_nimmt_die_felder_und_prueft_vorher():
    rumpf = _funktionsrumpf("openBillingSelectionModal", APP_JS.read_text(encoding="utf-8"))
    weiter = rumpf[rumpf.index("btn-proceed-preview"):]
    assert "pruefeAbrechnungszeitraum(beginn, ende)" in weiter
    assert "generateBillPreview(suggestion.tenant_id, beginn, ende, selectedCategoryIds)" in weiter
    assert weiter.index("pruefeAbrechnungszeitraum") < weiter.index("generateBillPreview")
    # Die alten, stumm errechneten Grenzen sind weg.
    assert "minStart" not in rumpf and "maxEnd" not in rumpf


def test_vorbelegung_folgt_der_auswahl_bis_zur_handeingabe():
    rumpf = _funktionsrumpf("openBillingSelectionModal", APP_JS.read_text(encoding="utf-8"))
    assert "vorgeschlagenerZeitraum(suggestion.categories, ausgewaehlteIds())" in rumpf
    assert "cb.onchange = vorbelegen" in rumpf
    assert "if (vonHand) return;" in rumpf
    assert "beginnFeld.oninput = () => { vonHand = true; };" in rumpf

