"""NK-074: die Beschriftungen der Oberflaeche folgen dem Begriffskatalog
(docs/glossar.md).

Der Test ruft die Pruefungen aus scripts/ui_beschriftungen.py auf und
schlaegt fehl, sobald ein Verstoess gefunden wird -- Navigationskanon,
Verbliste der Schaltflaechen, Sperrliste und die Umlagearten-Auswahl im
Kostenprofil. Er laeuft damit automatisch im Testlauf (`make check`).

Die Negativproben am Ende stellen sicher, dass der Pruefer Verstoesse
auch wirklich findet und nicht leer durchlaeuft.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parents[1]
if str(BASIS) not in sys.path:
    sys.path.insert(0, str(BASIS))

from scripts.ui_beschriftungen import (  # noqa: E402
    APP,
    INDEX,
    STATIC,
    alle_verstoesse,
    pruefe_navigation,
    pruefe_sperrliste,
    pruefe_umlagearten,
    pruefe_verben,
)


def test_beschriftungen_folgen_dem_katalog():
    """Die ganze Oberflaeche: keine Verstoesse gegen den Katalog."""
    verstoesse = alle_verstoesse()
    assert verstoesse == [], (
        "Beschriftungen weichen vom Begriffskatalog ab:\n  "
        + "\n  ".join(verstoesse)
    )


def test_navigationskanon():
    """Glossar Par. 5: Ziel, Beschriftung und Icon der Navigation."""
    assert pruefe_navigation(INDEX.read_text(encoding="utf-8")) == []


def test_umlagearten_wortgleich_mit_arten():
    """Glossar Par. 2: die Auswahl im Kostenprofil traegt ARTEN wortgleich."""
    assert pruefe_umlagearten(APP.read_text(encoding="utf-8")) == []


def test_pruefer_findet_du_form():
    probe = "'Bitte gib deinen Namen ein.'"
    verstoesse = pruefe_sperrliste(probe, "probe")
    assert any("Du-Form" in v for v in verstoesse), verstoesse


def test_pruefer_findet_englische_reste():
    probe = "'Möchten Sie das Dashboard wirklich laden?'"
    verstoesse = pruefe_sperrliste(probe, "probe")
    assert any("Dashboard" in v for v in verstoesse), verstoesse


def test_pruefer_findet_verblose_knoepfe():
    assert pruefe_verben("<button onclick=\"hinzufuegen()\">Hinzufügen</button>")
    assert pruefe_verben("<button onclick=\"speichern()\">Profil speichern</button>")
    # Wohlgeformte Knoepfe bleiben unbeanstandet:
    assert not pruefe_verben("<button onclick=\"speichern()\">Kostenprofil speichern</button>")
    assert not pruefe_verben("<button class=\"filter-pill\">Strom</button>")
    assert not pruefe_verben("<button title=\"Schließen\"><i class=\"ph ph-x\"></i></button>")


# ---------------------------------------------------------------------------
# NK-067 (Design-System): die Abnahme 0.8 verlangt, dass kein Screen eigene
# Farben erfindet. Diese Zusicherungen sind maschinell pruefbar und laufen
# damit in `make check` mit; das verhaltensnahe Gegenstueck ist
# scripts/rauchtest_design.js (Wirt, Node).
# ---------------------------------------------------------------------------
STYLE = STATIC / "style.css"


def _liest(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


def test_designsystem_zustandstoene_sind_definiert():
    css = _liest(STYLE)
    for ton in ("--success-bg", "--danger-bg", "--warning-bg"):
        assert f"{ton}:" in css, f"Zustandston {ton} fehlt im Stylesheet"


def test_designsystem_neue_klassen_sind_definiert():
    css = _liest(STYLE)
    for klasse in (".filter-pill", ".gefahrenzone", ".btn-gefahr", ".btn-tint"):
        assert klasse in css, f"Klasse {klasse} fehlt im Stylesheet"


def test_index_nutzt_die_designklassen_statt_inline_farben():
    html = _liest(INDEX)
    assert 'dashboard-card glass-panel gefahrenzone' in html
    assert 'class="btn-gefahr"' in html
    assert 'btn-secondary btn-tint' in html
    # NK-144: zwei Auswahlpillen im Rechnungen-Tab (Liste / Zeitleiste);
    # NK-156: fünf Gruppen der Einstellungen (K8).
    assert len(re.findall(r'class="filter-pill', html)) == 12


def test_kein_off_palette_farbliteral_in_inline_styles():
    """Inline-Styles duerfen nur var()-Verweise oder Palette-Familie tragen."""
    verboten = re.compile(
        r"#(?:ef4444|3b82f6|22c55e|8b5cf6|f59e0b|c2410c|fff7ed|4b5563"
        r"|666\b|e5e7eb|4f46e5|4F46E5|f3f4f6|1f2937)",
    )
    for datei, quelltext in (("index.html", _liest(INDEX)), ("app.js", _liest(APP))):
        inline = re.findall(r'style="[^"]*"', quelltext)
        inline += re.findall(r"cssText = '([^']*)'", quelltext)
        inline += re.findall(r"style\.color = '([^']*)'", quelltext)
        treffer = [s[:80] for s in inline if verboten.search(s)]
        assert treffer == [], (
            f"{datei}: Inline-Farben ausserhalb der Palette: {treffer}")


def test_diagramm_farbe_ist_einzige_stelle_fuer_kategorienfarben():
    app = _liest(APP)
    assert "const DIAGRAMM_FARBE = {" in app
    # Chart-Konfigurationen und Karten nutzen die Palette, keine Literale;
    # erlaubt sind nur die Definitionszeilen der Palette selbst.
    verboten = re.compile(r"'(?:#3B82F6|#10B981|#F59E0B|#8B5CF6|#EF4444|#9CA3AF)'")
    definition = re.compile(r"^\s*(blau|gruen|gelb|lila|rot|grau):", re.UNICODE)
    treffer = [z for z in app.splitlines()
               if verboten.search(z)
               and "DIAGRAMM_FARBE" not in z and not definition.match(z)]
    assert treffer == [], ("Kategorienfarben sollten aus DIAGRAMM_FARBE kommen: "
                           + "; ".join(t.strip() for t in treffer[:5]))


def test_pillen_zustand_nur_ueber_klasse():
    """Der Klick-Handler uebermalt das CSS nicht mit Inline-Styles."""
    app = _liest(APP)
    assert "e.target.style.background" not in app
    assert "p.style.background" not in app


# ---------------------------------------------------------------------------
# NK-123: der Reset-Knopf gehoert nur in den Entwicklerstapel. Die Karte
# prueft die drei Gelenke statisch: verborgen im HTML, entriegelt erst
# durch die Meldung von /api/auth/me, und der Aufruf traegt das Geheimnis.
# ---------------------------------------------------------------------------


def test_gefahrenzone_startet_verborgen():
    """Die Karte ist im HTML verborgen und hat einen Namen zum Entriegeln."""
    html = _liest(INDEX)
    assert 'id="gefahrenzone"' in html
    assert re.search(r'id="gefahrenzone"[^>]*\bhidden\b', html), (
        "Die Gefahrenzone muss im Auslieferungszustand hidden tragen")


def test_gefahrenzone_entriegelt_nur_durch_die_entwicklermeldung():
    """Erst /api/auth/me mit entwicklung: true holt die Karte hervor."""
    app = _liest(APP)
    assert "daten.entwicklung" in app
    assert re.search(
        r"zone\.hidden\s*=\s*!daten\.entwicklung", app), (
        "Die Gefahrenzone wird nur ueber die Entwicklermeldung entriegelt")


def test_der_reset_traegt_das_geheimnis():
    """Der Aufruf schickt X-Debug-Secret und misshandelt 401/404 nicht."""
    app = _liest(APP)
    assert "'X-Debug-Secret': geheimnis" in app
    assert "fragePassphrase(" in app.split("async function resetDatabase")[1].split(
        "await fetch('/api/debug/reset_db'")[0], (
        "Das Geheimnis wird abgefragt, bevor die Route gerufen wird")


# ---------------------------------------------------------------------------
# NK-139: der Wächter liest auch die Meldungen des Backends. Was die
# Oberflaeche dem Vermieter zeigt, sind auch die Fehlermeldungen, Warnungen
# und Blocker, die das Backend zurueckgibt -- sie gehoeren zur selben
# Sperrliste wie die Knopftexte.
# ---------------------------------------------------------------------------


def test_pruefer_findet_imperativ_anrede():
    """'Trage … nach' und 'Lege fest' sind ebenso Anrede wie 'dein'."""
    probe = "'Trage die Quadratmeter nach.' 'Lege fest, wie gerechnet wird.'"
    verstoesse = pruefe_sperrliste(probe, "probe")
    imperativ = [v for v in verstoesse if "Imperativ-Anrede" in v]
    assert len(imperativ) == 2, verstoesse


def test_backend_meldungen_sind_gesiezt():
    """Die Fachmodule sprechen den Vermieter mit 'Sie' an (F-66)."""
    from scripts.ui_beschriftungen import pruefe_backend_meldungen

    assert pruefe_backend_meldungen() == []


def test_backend_pruefer_findet_du_form_in_f_string(tmp_path):
    """Auch der Textanteil einer f-Zeichenkette wird gelesen.

    Die Blocker im Rechenkern sind f-Zeichenketten: ihr Code steckt in
    Ausdruecken, die gesiebten Saetze in den Konstanten dazwischen. Die
    Probe legt eine der geprueften Dateien in ein eigenes Verzeichnis,
    denn der Wächter liest nur die bekannten Module.
    """
    modul = tmp_path / "nutzung.py"
    modul.write_text(
        'def blocker(name):\n'
        '    return f"Objekt {name} ist nicht aktiv. Trage die Wohnung nach."\n',
        encoding="utf-8")
    from scripts.ui_beschriftungen import pruefe_backend_meldungen

    verstoesse = pruefe_backend_meldungen(tmp_path)
    assert len(verstoesse) == 1, verstoesse
    assert "nutzung.py:2" in verstoesse[0]
    assert "Imperativ-Anrede" in verstoesse[0]


# --- NK-149 (F-79): Modulliste aus den Importen, Umschrift als Regel ---

def test_der_waechter_kennt_alle_module_mit_meldungen():
    """Die sechs Module aus F-79 fehlten in der festen Liste. Jetzt folgt
    die Liste den Importen ab app.py."""
    from scripts.ui_beschriftungen import backend_module

    module = backend_module()
    for name in ('backup.py', 'mieter_daten.py', 'girocode_generator.py',
                 'frist.py', 'beispielimmobilie.py', 'zeitleiste.py',
                 'app.py', 'auth.py', 'rechenkern.py'):
        assert name in module, name


def test_backend_meldungen_ohne_umschrift():
    from scripts.ui_beschriftungen import pruefe_umschrift

    assert pruefe_umschrift() == []


def test_umschrift_waechter_findet_waehlen(tmp_path):
    """Gegenprobe: ein Modul, das app.py importiert, mit 'waehlen'."""
    (tmp_path / "app.py").write_text("import neu\n", encoding="utf-8")
    (tmp_path / "neu.py").write_text(
        '"""Docstrings duerfen umschreiben."""\n'
        'import logging\n'
        'logging.getLogger().info("Protokoll fuer den Betrieb")\n'
        'FEHLER = "Bitte waehlen Sie ein gueltiges Archiv."\n'
        'SCHLUESSEL = "zuletzt_gewaehltes_ziel"\n'
        'CODE = "W-ZAEHLER-NEGATIV {zaehler} fehlt"\n',
        encoding="utf-8")
    from scripts.ui_beschriftungen import pruefe_umschrift

    verstoesse = pruefe_umschrift(tmp_path)
    assert len(verstoesse) == 2, verstoesse
    assert all("neu.py:4" in v for v in verstoesse)
