"""NK-116: ein hoher Dialog rollt in sich, „Speichern“ bleibt erreichbar.

Befund aus dem Live-Abgleich (Phase 6, NK-110, Oberflächen-Weg, Klasse B —
Fehler im neuen Stand): Seit NK-113 blendet der Rechnungsdialog bei Nr. 17
das Feld „Bezeichnung“ ein. Mit Bezeichnung und Beleg-Feld wird der Dialog
höher als ein Fenster von 1440 × 900. Die Überlagerung ist fest und
zentriert, der Dialog hatte weder Höchsthöhe noch eigenen Rollbalken — Kopf
und Fuß lagen außerhalb des Fensters, der Knopf „Rechnung speichern“ ließ
sich nicht mehr erreichen. Der Spieler brach an dieser Stelle mit „element
is outside of the viewport“ ab.

Nebenbefund: ``saveInvoice`` setzte die Beschriftung „Speichert...“ nie
zurück — nach der ersten Rechnung trug der Knopf sie bis zum Neuladen.

Wächter, statisch (die DOM-Probe ist der Oberflächen-Lauf selbst):

1. ``.modal`` begrenzt seine Höhe auf das Fenster und rollt in sich.
   *Hätte diesen Fehler gefunden:* die alte Regel hatte weder
   ``max-height`` noch ``overflow-y``.
2. Im Druck gilt die Begrenzung nicht — sonst schnitte der Druck ab.
3. ``saveInvoice`` stellt im ``finally`` die Beschriftung wieder her.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
STYLE = WURZEL / "static" / "style.css"
APP_JS = WURZEL / "static" / "app.js"


def _regel(css: str, selektor: str) -> str:
    """Rumpf der ersten Regel, die genau mit ``selektor`` beginnt."""
    treffer = re.search(r"(?m)^" + re.escape(selektor) + r"\s*\{([^}]*)\}", css)
    assert treffer, f"Regel {selektor!r} fehlt in style.css"
    return treffer.group(1)


def _ohne_kommentare(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_dialog_begrenzt_hoehe_auf_das_fenster():
    rumpf = _ohne_kommentare(_regel(STYLE.read_text(encoding="utf-8"), ".modal"))
    assert re.search(r"max-height\s*:\s*calc\(100vh", rumpf), rumpf
    assert re.search(r"overflow-y\s*:\s*auto", rumpf), rumpf


def test_druck_hebt_die_begrenzung_auf():
    css = _ohne_kommentare(STYLE.read_text(encoding="utf-8"))
    druck = css[css.index("@media print"):]
    treffer = re.search(r"\.modal,\s*\.modal-body\s*\{([^}]*)\}", druck)
    assert treffer, "Druckregel für .modal fehlt"
    assert "max-height: none" in treffer.group(1)
    assert "overflow: visible" in treffer.group(1)


def test_speichern_knopf_bekommt_seine_beschriftung_zurueck():
    quelle = APP_JS.read_text(encoding="utf-8")
    start = quelle.index("async function saveInvoice(")
    ende = quelle.index("\n}\n", start)
    rumpf = quelle[start:ende]
    finally_teil = rumpf[rumpf.index("finally"):]
    assert "btn.textContent = 'Rechnung speichern'" in finally_teil
