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
    # NK-156: fünf Gruppen der Einstellungen (K8); Eingang / Alle / Nach Kostenart;
    # Phase 47: „Nur offene Zahlungen“ in der Historie; Phase 54: sechste
    # Einstellungs-Gruppe „Kostenarten“; PDF-Aufbau: siebte Gruppe „Abrechnung“.
    assert len(re.findall(r'class="filter-pill', html)) == 18


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
    verboten = re.compile(r"'(?:#4F46E5|#2E7D6B|#C27A12|#8E4FB8|#A3312A|#8C8FA6)'")
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
    modul = tmp_path / "nebenkostenfix" / "nutzung.py"
    modul.parent.mkdir()
    modul.write_text(
        'def blocker(name):\n'
        '    return f"Objekt {name} ist nicht aktiv. Trage die Wohnung nach."\n',
        encoding="utf-8")
    from scripts.ui_beschriftungen import pruefe_backend_meldungen

    verstoesse = pruefe_backend_meldungen(tmp_path)
    assert len(verstoesse) == 1, verstoesse
    assert "nutzung.py:2" in verstoesse[0]
    assert "Imperativ-Anrede" in verstoesse[0]


def test_backend_pruefer_findet_rechne_in_der_ablehnung(tmp_path):
    """NK-184: 'Rechne den Wohnteil … ab' stand in nutzung.ablehnung und kam
    als Blocker in der Oberflaeche an. 'Rechne' fehlte in der Verbliste."""
    modul = tmp_path / "nebenkostenfix" / "nutzung.py"
    modul.parent.mkdir()
    modul.write_text(
        'def ablehnung(name):\n'
        '    return (f"Die Immobilie {name} ist gemischt genutzt. "\n'
        '            f"Rechne den Wohnteil in einer eigenen Immobilie ab.")\n',
        encoding="utf-8")
    from scripts.ui_beschriftungen import pruefe_backend_meldungen

    verstoesse = pruefe_backend_meldungen(tmp_path)
    assert len(verstoesse) == 1, verstoesse
    assert "'Rechne'" in verstoesse[0]


def test_ablehnung_gemischt_genutzter_gebaeude_ist_gesiezt():
    """NK-184: die sichtbare Absage selbst, nicht nur der Wächter."""
    from nebenkostenfix.nutzung import ablehnung
    from scripts.ui_beschriftungen import ANREDE_IMPERATIV, DU_FORM

    for art in ('gemischt', 'gewerbe', 'leer'):
        text = ablehnung('Hauptstr. 5', art)
        assert not ANREDE_IMPERATIV.search(text), text
        assert not DU_FORM.search(text), text
        assert 'Rechnen Sie den Wohnteil' in text


# --- NK-149 (F-79): Modulliste aus den Importen, Umschrift als Regel ---

def test_der_waechter_kennt_alle_module_mit_meldungen():
    """Die sechs Module aus F-79 fehlten in der festen Liste. Jetzt folgt
    die Liste den Importen ab app.py."""
    from scripts.ui_beschriftungen import backend_module

    module = backend_module()
    for name in ('backup.py', 'mieter_daten.py', 'girocode_generator.py',
                 'frist.py', 'beispielimmobilie.py', 'zeitleiste.py',
                 'auth.py', 'rechenkern.py'):
        assert 'nebenkostenfix/' + name in module, name
    for name in ('app.py',):
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


def _media_block(css: str, kopf: str) -> str:
    """Der Rumpf des ersten @media-Blocks mit genau diesem Kopf."""
    start = css.index(kopf)
    tiefe, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        tiefe += {"{": 1, "}": -1}.get(css[j], 0)
        if tiefe == 0:
            return css[i:j]
    raise AssertionError(f"{kopf} ohne schließende Klammer")


def test_erste_schritte_zweitknopf_bricht_am_handy_um():
    # NK-223: unter 720 px rutschte nur .btn-primary unter den Text,
    # „Beispiel löschen“ (.btn-secondary) blieb in der schmalen Spalte.
    schmal = _media_block(_liest(STYLE), "@media (max-width: 720px)")
    assert ".erste-schritte-liste .schritt .btn-secondary" in schmal


def test_erste_schritte_stand_traegt_klasse_und_bricht_nicht_um():
    # NK-223: die Regel .erste-schritte-stand griff nie, der Span hatte nur die id.
    assert re.search(r'<span id="erste-schritte-stand" class="erste-schritte-stand"', _liest(INDEX))
    regel = re.search(r"\n\.erste-schritte-stand \{([^}]*)\}", _liest(STYLE)).group(1)
    assert "white-space: nowrap" in regel


def test_ablesen_nimmt_das_foto_von_der_kamera():
    """NK-227: beim Ablesen am Handy öffnet das Foto-Feld direkt die Kamera."""
    assert 'accept="image/*" capture="environment"' in _liest(APP)
    assert 'onclick="openAblesen()"' in _liest(INDEX)


def test_regelstand_hinweis_klappt_auf_und_fuehrt_zur_vorschau():
    """NK-229: der Hinweis erklärt sich und zeigt den Unterschied, bevor etwas entsteht."""
    app = _liest(APP)
    hinweis = app[app.index('function regelstandHinweis('):]
    hinweis = hinweis[:hinweis.index('\n}\n')]
    assert '<details class="regelstand-hinweis"' in hinweis
    assert 'Unterschied ansehen' in hinweis and 'korrekturErstellen(' in hinweis
    assert 'REGELSTAND_HINWEIS' not in app


def test_heute_ist_das_lokale_datum():
    """NK-238: ``new Date().toISOString()`` ist UTC -- zwischen Mitternacht und
    1 bzw. 2 Uhr stand im Ablesedialog und in den anderen Vorbelegungen noch
    das Datum von gestern."""
    assert "new Date().toISOString()" not in _liest(APP)


def _schmal(css: str) -> str:
    """Alle Blöcke ``@media (max-width: 720px)`` hintereinander."""
    kopf = "@media (max-width: 720px)"
    return "".join(_media_block(css[m.start():], kopf) for m in re.finditer(re.escape(kopf), css))


def test_zaehlertabelle_wird_am_handy_zur_karte():
    """NK-252: unter 720 px rollte die Zählertabelle in ihrer Karte (NK-157),
    Verlauf, Stift und Papierkorb lagen rechts außerhalb des Bilds."""
    app = _liest(APP)
    zaehler = app[app.index("function renderMeters("):]
    zaehler = zaehler[:zaehler.index("\n}\n")]
    assert "table.className = 'zaehler-tabelle'" in zaehler
    assert '<tr class="zaehler-kopf"' in zaehler
    for beschriftung in ("Kategorie", "Zählernummer", "Wohnung", "Letzter Stand"):
        assert f".dataset.label = '{beschriftung}'" in zaehler, beschriftung
    schmal = _schmal(_liest(STYLE))
    karte = re.search(r"\.glass-panel table\.zaehler-tabelle,[^{]*\{([^}]*)\}", schmal)
    assert karte and "display: block" in karte.group(1) and "overflow-x: visible" in karte.group(1)
    assert re.search(r"\.zaehler-tabelle \.zaehler-kopf \{\s*display: none;", schmal)
    assert "content: attr(data-label)" in schmal


def test_kopfaktionen_am_handy_im_menue():
    """NK-253: unter 720 px stapelten sich die Kopfknöpfe (vier bei den
    Zählern) über dem Inhalt; ein Menüknopf neben dem Titel trägt sie."""
    app = _liest(APP)
    start = app[app.index("function initApp("):]
    assert "initKopfMenues();" in start[:start.index("\n}\n")]
    menue = app[app.index("function initKopfMenues("):]
    menue = menue[:menue.index("\n}\n")]
    assert "querySelectorAll('.section-header > .kopf-aktionen, .top-header > .kopf-aktionen')" in menue
    assert "if (aktionen.parentElement.classList.contains('top-header')) aktionen.before(knopf);" in menue
    for merkmal in ("'btn-secondary kopf-menue-knopf'", "'aria-haspopup'", "'aria-expanded'",
                    "'aria-label', 'Aktionen'", "classList.add('mit-menue')", "'Escape'"):
        assert merkmal in menue, merkmal
    css = _liest(STYLE)
    # Am Schreibtisch bleibt der Kopf wie er war.
    assert re.search(r"^\.kopf-menue-knopf \{\s*display: none;", css, re.M)
    schmal = _schmal(css)
    assert re.search(r"\.kopf-menue-knopf \{\s*display: inline-flex;", schmal)
    zu = re.search(r"\.kopf-aktionen\.mit-menue \{([^}]*)\}", schmal)
    assert zu and "display: none" in zu.group(1) and "position: absolute" in zu.group(1)
    assert re.search(r"\.kopf-aktionen\.mit-menue\.offen \{\s*display: flex;", schmal)
    # Der Titel muss schrumpfen dürfen, sonst rutscht der Knopf bei langen
    # Titeln (Mieter, Abrechnungen) unter ihn statt daneben.
    titel = re.search(r"\.section-header > div:first-child \{([^}]*)\}", schmal)
    assert titel and "min-width: 0" in titel.group(1) and "flex: 1 1 0" in titel.group(1)
    assert re.search(r"\.kopf-menue-knopf \{\s*display: inline-flex;\s*align-self: flex-start;", schmal)


# --- Re-Review der Phasen 47/49/53/54 (2026-10-18) -----------------------------

def test_kostenart_modal_nutzt_die_designfelder():
    """Das Modal nutzt .form-group wie die übrige App: .feld ohne Styling
    ließ das Namensfeld wie einen Browser-Standard (XP-Look) aussehen."""
    html = (BASIS / 'static' / 'index.html').read_text(encoding='utf-8')
    block = html.split('id="kategorie-modal"', 1)[1].split('<!-- ', 1)[0]
    assert 'class="feld"' not in block
    assert 'class="form-group"' in block


def test_die_kostenart_fragt_nicht_nach_der_umlage():
    """Die Umlage-Spalte der Kostenart ist keine Abrechnungsentscheidung --
    das Blatt liest das Kostenprofil des Mieters. Nach dem Re-Review fragt
    die Oberfläche sie nicht mehr: kein Feld im Modal, keine Spalte in der
    Tabelle, keine Liste im Quelltext. Ein Feld, das nichts bewirkt, ist
    der reinste Verwirrungs-Generator."""
    html = (BASIS / 'static' / 'index.html').read_text(encoding='utf-8')
    block = html.split('id="kategorie-modal"', 1)[1].split('<!-- ', 1)[0]
    assert 'kategorie-verteilung' not in block
    assert 'kategorie-heizhinweis' not in block
    karten_block = html.split('data-gruppe="kostenarten"', 1)[1].split('data-gruppe="konto"', 1)[0]
    assert '<th>Umlage</th>' not in karten_block
    js = (BASIS / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'KATEGORIE_VERTEILUNGEN' not in js


def test_kostenarten_karte_nimmt_die_volle_breite():
    """Die Einzelkarte der Kostenarten-Gruppe streckt sich über das ganze
    Einstellungs-Raster, statt als 600-px-Spalte ihre Tabelle querrollen zu
    lassen -- die übrigen Gruppen behalten ihr bestehendes Raster."""
    css = (BASIS / 'static' / 'style.css').read_text(encoding='utf-8')
    assert '.einstellungs-raster > .dashboard-card[data-gruppe="kostenarten"]' in css
    assert 'grid-column: 1 / -1' in css


def test_soll_ist_liste_gruppiert_jahresweise():
    """Die Soll/Ist-Tabelle von Vorauszahlungen und Kaltmiete gruppiert je
    Jahr: Kopfzeile mit Summen, Monate dahinter, aufklappbar statt 90
    Zeilen zum Scrollen seit dem Einzug."""
    js = (BASIS / 'static' / 'app.js').read_text(encoding='utf-8')
    for merkmal in ('jahr-kopf', 'jahr-zeile', 'jahrUmschalten',
                    'data-jahr=', 'data-ziel='):
        assert merkmal in js, merkmal


# ---------------------------------------------------------------------------
# Live-Issue #32: Umschalter brauchen ihr Ereignis am Steuerfeld
# ---------------------------------------------------------------------------
# Ein Umschalter, der den Grundzustand eines abhaengigen Feldes sperrt oder
# verbirgt, laeuft beim Oeffnen des Dialogs -- aber nur dann. Haengt er nicht
# zusaetzlich am change-Ereignis seines Steuerfeldes, bleibt das abhaengige
# Feld nach der Wahl gesperrt. Verlangt das Backend dessen Wert, ist der
# Datensatz nicht speicherbar: genau die Sackgasse aus Issue #32.


def _umschalter_bloecke(js: str) -> dict:
    """Jede toggle*-Funktion aus app.js mit ihrem Rumpf."""
    bloecke = {}
    zeilen = js.split("\n")
    for i, zeile in enumerate(zeilen):
        treffer = re.match(r"^function (toggle\w*)\s*\(", zeile)
        if not treffer:
            continue
        rumpf = []
        for folge in zeilen[i + 1:]:
            if folge.startswith("}"):
                break
            rumpf.append(folge)
        bloecke[treffer.group(1)] = "\n".join(rumpf)
    return bloecke


def _gelesene_felder(rumpf: str) -> set:
    """Die Felder, deren Wert der Umschalter liest -- nicht die, die er setzt."""
    gelesen = set()
    muster = r"getElementById\(['\"]([\w-]+)['\"]\)\s*\.(?:value|checked)\s*(={1,3})?"
    for treffer in re.finditer(muster, rumpf):
        if treffer.group(2) == "=":
            continue  # eine Zuweisung: dieses Feld wird gesteuert, nicht gelesen
        gelesen.add(treffer.group(1))
    return gelesen


def _hat_ereignis(html: str, js: str, feld: str) -> bool:
    """Traegt das Feld einen Ereignis-Handler -- im HTML oder aus dem JS?"""
    name = re.escape(feld)
    for tag in re.finditer(r"<[^>]*\bid=\"" + name + r"\"[^>]*>", html):
        if re.search(r"\bon(?:change|input|click)\s*=", tag.group(0)):
            return True
    direkt = (r"getElementById\(['\"]" + name
              + r"['\"]\)\s*\.(?:onchange|oninput|onclick|addEventListener)")
    if re.search(direkt, js):
        return True
    # der Umweg ueber eine Variable: const feld = getElementById(...); feld.onchange = ...
    ueber_var = r"(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(['\"]" + name + r"['\"]\)"
    for zuweisung in re.finditer(ueber_var, js):
        hebel = re.escape(zuweisung.group(1))
        if re.search(r"\b" + hebel + r"\s*\.(?:onchange|oninput|onclick|addEventListener)", js):
            return True
    return False


def test_umschalter_haengen_am_steuerfeld():
    """Jeder Umschalter haengt am change-Ereignis des Feldes, das ihn steuert.

    Ohne das Ereignis laeuft er nur beim Oeffnen des Dialogs: das abhaengige
    Feld bleibt gesperrt oder verborgen, und wenn das Backend dessen Wert
    verlangt, laesst sich der Datensatz nicht speichern (Live-Issue #32).
    """
    js = _liest(APP)
    html = _liest(INDEX)
    offen = []
    for name, rumpf in sorted(_umschalter_bloecke(js).items()):
        for feld in sorted(_gelesene_felder(rumpf)):
            if not _hat_ereignis(html, js, feld):
                offen.append(f"{name}() liest #{feld}, aber #{feld} loest kein Ereignis aus")
    assert offen == [], (
        "Umschalter ohne Ereignis am Steuerfeld:\n  " + "\n  ".join(offen))


def test_rechnung_posten_entsperrt_nach_der_anlagenwahl():
    """Live-Issue #32: die Wahl der Heizungsanlage entsperrt den Posten.

    populateInvoiceHeizung() sperrt das Posten-Feld als Grundzustand;
    toggleInvoiceHeizkosten() entsperrt es wieder. Ohne das Ereignis am
    Anlagen-Feld bleibt der Posten ausgegraut, und saveInvoice() lehnt die
    Rechnung mit "braucht beides" ab.
    """
    tag = re.search(r'<select id="invoice-heizungsanlage"[^>]*>', _liest(INDEX))
    assert tag, "Feld invoice-heizungsanlage fehlt"
    assert "toggleInvoiceHeizkosten()" in tag.group(0), tag.group(0)


def test_warmwasserweg_zeigt_seine_pflichtfelder():
    """Der Wechsel des Warmwasser-Weges blendet die Pflichtfelder ein.

    app.py verlangt beim Weg "zaehler" die kWh, bei "formel" Volumen und
    Temperatur. Ohne das Ereignis bleibt die jeweilige Feldgruppe verborgen
    und die Anlage ist nicht speicherbar -- dasselbe Muster wie Issue #32.
    """
    tag = re.search(r'<select id="heizung-ww-weg"[^>]*>', _liest(INDEX))
    assert tag, "Feld heizung-ww-weg fehlt"
    assert "toggleWwWeg()" in tag.group(0), tag.group(0)


def test_waechter_findet_das_fehlende_ereignis():
    """Negativprobe: der Waechter meldet ein Steuerfeld ohne Ereignis."""
    js = ("function toggleProbe() {\n"
          "    const wahl = document.getElementById('probe-feld').value;\n"
          "    document.getElementById('probe-ziel').disabled = !wahl;\n"
          "}\n")
    bloecke = _umschalter_bloecke(js)
    assert "toggleProbe" in bloecke
    # nur das gelesene Feld zaehlt, nicht das gesteuerte
    assert _gelesene_felder(bloecke["toggleProbe"]) == {"probe-feld"}
    assert not _hat_ereignis('<select id="probe-feld"></select>', js, "probe-feld")
    assert _hat_ereignis(
        '<select id="probe-feld" onchange="toggleProbe()"></select>', js, "probe-feld")


def test_waechter_haelt_zuweisungen_auseinander():
    """Negativprobe: ein Feld, dem der Umschalter nur einen Wert setzt, ist
    kein Steuerfeld -- sonst meldete der Waechter togglePaymentRecurring()
    wegen des geleerten Enddatums."""
    rumpf = ("    document.getElementById('a-feld').value = '';\n"
             "    if (document.getElementById('b-feld').value === 'x') { }\n")
    assert _gelesene_felder(rumpf) == {"b-feld"}


# ---------------------------------------------------------------------------
# Die zweite Bug-Klasse: ein Auswahlfeld ohne Pruefung im Backend
# ---------------------------------------------------------------------------
# Ein <select> hat eine geschlossene Wertemenge. Nimmt die Route seinen Wert
# als freien Text an, laesst sich an der Oberflaeche vorbei jeder Wert setzen.
# Steuert das Feld die Rechnung -- wie die Zahlungsart seit Phase 53 --, ist
# das kein Schoenheitsfehler, sondern ein stiller Rechenfehler: der Datensatz
# steht in der Liste und zaehlt in keiner Auswertung. Genau das war der Fall
# bei POST /api/payments ('Kaltmiete' statt 'Miete').

RUMPF = BASIS / 'app.py'


def _festmenge_selects(html: str) -> dict:
    """Jedes <select>, dessen Optionen im HTML stehen (nicht von JS gefuellt)."""
    gefunden = {}
    for treffer in re.finditer(r'<select[^>]*\bid="([\w-]+)"[^>]*>(.*?)</select>', html, re.S):
        werte = [w for w in re.findall(r'<option[^>]*value="([^"]*)"', treffer.group(2)) if w]
        if werte:
            gefunden[treffer.group(1)] = werte
    return gefunden


def _text_lesungen(rumpf: str) -> dict:
    """Feldname -> die Variablen, in die eingabe.text() ihn legt."""
    lesungen = {}
    for treffer in re.finditer(r"(\w+)\s*=\s*eingabe\.text\(\s*['\"]([\w_]+)['\"]", rumpf):
        lesungen.setdefault(treffer.group(2), []).append(treffer.group(1))
    return lesungen


def _wird_geprueft(rumpf: str, feld: str, variablen: list) -> bool:
    """Prueft die Route den Wert -- gegen eine Liste oder per pruefe_*-Funktion?"""
    for name in variablen:
        if re.search(rf'\b{re.escape(name)}\s+not\s+in\b', rumpf):
            return True
        if re.search(rf'pruefe_\w+\(\s*{re.escape(name)}\b', rumpf):
            return True
    # die Kurzform: pruefe_xyz(eingabe.text('feld', ...)) ohne Zwischenvariable
    if re.search(rf"pruefe_\w+\(\s*\n?\s*eingabe\.text\(\s*['\"]{re.escape(feld)}['\"]", rumpf):
        return True
    return False


def _paare(html: str, rumpf: str) -> list:
    """(Feld-Id, Backend-Feldname, Variablen) fuer jedes Select, das die Route liest."""
    gefunden = []
    lesungen = _text_lesungen(rumpf)
    for feld_id, _werte in sorted(_festmenge_selects(html).items()):
        kurz = feld_id.split('-')[-1]
        for feld, variablen in lesungen.items():
            if feld == kurz or feld.endswith('_' + kurz) or kurz in feld:
                gefunden.append((feld_id, feld, variablen))
                break
    return gefunden


def test_auswahlfelder_werden_im_backend_geprueft():
    """Jedes Auswahlfeld mit fester Wertemenge prüft das Backend nachweislich.

    Ohne die Prüfung nimmt die Route an der Oberfläche vorbei jeden Text an.
    Bei der Zahlungsart hieß das: eine Zahlung mit „Kaltmiete" statt „Miete"
    stand in der Liste und zählte in keinem Soll/Ist — ein Rückstand, den es
    nicht gibt. Die App prüft solche Felder sonst durchgehend, über
    ``not in LISTE`` oder eine ``pruefe_*``-Funktion.
    """
    html, rumpf = _liest(INDEX), _liest(RUMPF)
    paare = _paare(html, rumpf)
    assert len(paare) >= 5, f'zu wenige Paare gefunden, Heuristik prüfen: {paare}'
    offen = [f"#{fid} -> eingabe.text('{feld}') ohne Prüfung"
             for fid, feld, variablen in paare
             if not _wird_geprueft(rumpf, feld, variablen)]
    assert offen == [], 'Auswahlfelder ohne Prüfung im Backend:\n  ' + '\n  '.join(offen)


def test_die_zahlungsart_steht_in_der_liste_der_geprueften():
    """Der Fall, der die Regel ausgelöst hat, ist von ihr erfasst."""
    paare = _paare(_liest(INDEX), _liest(RUMPF))
    assert ('payment-type', 'type', ['type_']) in paare


def test_waechter_findet_ein_ungepruefte_auswahlfeld():
    """Negativprobe: ohne Prüfung meldet der Wächter das Feld."""
    html = '<select id="probe-art"><option value="a">A</option></select>'
    ohne = "    art = eingabe.text('art', pflicht=True)\n"
    mit_liste = ohne + "    if art not in ARTEN:\n        raise EingabeFehler('x', 'art')\n"
    mit_funktion = "    art = eingabe.text('art')\n    pruefe_art(art)\n"
    assert _paare(html, ohne) == [('probe-art', 'art', ['art'])]
    assert not _wird_geprueft(ohne, 'art', ['art'])
    assert _wird_geprueft(mit_liste, 'art', ['art'])
    assert _wird_geprueft(mit_funktion, 'art', ['art'])


def test_waechter_uebergeht_von_js_gefuellte_felder():
    """Negativprobe: ein Select, das JS füllt, hat keine Wertemenge im HTML.

    Solche Felder tragen Datenbank-Ids (Mieter, Immobilie, Anlage) und werden
    über Fremdschlüssel geprüft, nicht über eine Liste."""
    assert _festmenge_selects('<select id="invoice-tenant"></select>') == {}
    assert _festmenge_selects('<select id="x"><option value="">Bitte wählen</option></select>') == {}


def test_das_feld_des_paragraf_7_erklaert_seinen_grauen_zustand():
    """Befund aus Issue #32: das graue Feld muss sagen, was fehlt.

    Der Posten nach § 7 Abs. 2 ist gesperrt, solange keine Heizungsanlage
    gewählt ist -- fachlich richtig, denn ohne Anlage gibt es keinen Posten
    zu verteilen. Der Melder von Issue #32 sah nur das graue Feld und den
    Fehler beim Übernehmen und fragte: „Wie kann ich diesem Fehler
    entgegenwirken?" Die Logik war schon damals richtig; gefehlt hat der
    Satz, der ihn zur Anlage führt.
    """
    seite = INDEX.read_text(encoding="utf-8")
    block = seite[seite.index('id="invoice-heizkostenart"'):][:600]
    assert 'id="hilfe-heizkostenart"' in block, 'kein Hilfetext am Feld'
    hinweis = block[block.index('id="hilfe-heizkostenart"'):]
    hinweis = hinweis[hinweis.index('>') + 1:hinweis.index('</small>')]
    assert 'Heizungsanlage' in hinweis, hinweis
    assert 'feld-hilfe' in block, 'der Hinweis traegt nicht die uebliche Klasse'
