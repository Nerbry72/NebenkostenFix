"""NK-140: die Kennung hinter app.js und style.css kommt aus dem Inhalt.

Die Version wurde von Hand gepflegt („app.js?v=26“, „style.css?v=10“) und
nie erhöht -- ein Browser mit altem Cache hat die neuen Knöpfe aus NK-118
und NK-119 nicht gesehen. Seit NK-140 setzt der Server beim Ausliefern von
``index.html`` den sha256 der beiden Dateien ein (12 Zeichen): Ändert sich
eine Datei, ändert sich die Adresse, und der Browser lädt neu -- ohne dass
jemand eine Versionsnummer von Hand erhöht.

Der Wächtertest prüft beide Enden: die echte Oberfläche trägt die Kennung
ihrer echten Dateien, und in einem Probenverzeichnis ändert sich die
Kennung, sobald sich der Inhalt ändert.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import app as app_modul

BASIS = Path(__file__).resolve().parents[1]
STATIC = BASIS / "static"


def _kennung(inhalt: bytes) -> str:
    return hashlib.sha256(inhalt).hexdigest()[:12]


def test_die_oberflaeche_traegt_die_kennung_ihrer_dateien(auth_client):
    """Die ausgelieferte Seite nennt app.js und style.css mit ihrem sha256."""
    html = app_modul._index_mit_kennung(STATIC)

    erwartet_js = _kennung((STATIC / "app.js").read_bytes())
    erwartet_css = _kennung((STATIC / "style.css").read_bytes())
    assert f"app.js?v={erwartet_js}" in html
    assert f"style.css?v={erwartet_css}" in html

    # Und die Route liefert genau dieses HTML:
    antwort = auth_client.get("/")
    assert antwort.status_code == 200
    assert erwartet_js in antwort.get_data(as_text=True)


def test_keine_handgepflegte_kennung_bleibt_uebrig():
    """Niemand muss mehr von Hand erhöhen: die alten '?v=26'-Reste sind weg."""
    html = app_modul._index_mit_kennung(STATIC)
    rest = [treffer for treffer in re.findall(r"\?v=(\w+)", html)
            if len(treffer) != 12]
    assert rest == [], (
        f"Kennungen ohne 12 Zeichen (von Hand gepflegt?): {rest}")


def test_eine_geaenderte_datei_aendert_die_kennung(tmp_path):
    """Der Wächterfall: app.js ändert sich, die Kennung springt mit."""
    (tmp_path / "style.css").write_text("body { color: black; }",
                                        encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log('alt');", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<link rel="stylesheet" href="/static/style.css?v=10">\n'
        '<script src="/static/app.js?v=26"></script>\n', encoding="utf-8")

    vorher = app_modul._index_mit_kennung(tmp_path)
    kennung_alt = re.search(r"app\.js\?v=(\w+)", vorher).group(1)
    assert kennung_alt == _kennung(b"console.log('alt');")

    (tmp_path / "app.js").write_text("console.log('neu -- ein Knopf mehr');",
                                     encoding="utf-8")
    nachher = app_modul._index_mit_kennung(tmp_path)
    kennung_neu = re.search(r"app\.js\?v=(\w+)", nachher).group(1)

    assert kennung_neu != kennung_alt
    assert kennung_neu == _kennung(
        (tmp_path / "app.js").read_bytes())
    # Die unberührte style.css behält ihre Kennung.
    assert re.search(r"style\.css\?v=(\w+)", nachher).group(1) \
        == re.search(r"style\.css\?v=(\w+)", vorher).group(1)
