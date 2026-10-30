"""Formulare im Hausstil: kein rohes Steuerelement rutscht mehr durch.

Gegenproben für ``pruefe_steuerelemente()`` (scripts/ui_beschriftungen.py):
der Prüfer schlägt bei einem nackten Dateifeld, einem Kästchen mit eigener
Größe, einem englischen Browsertext und einem Stylesheet ohne die Hausregeln
an, und lässt die beiden Hausmuster durch. Die Echtprüfung am Ende liest die
wirklichen Dateien; sie war vor dem Umbau rot.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parents[1]
if str(BASIS) not in sys.path:
    sys.path.insert(0, str(BASIS))

import scripts.ui_beschriftungen as gate  # noqa: E402
from scripts.ui_beschriftungen import (  # noqa: E402
    STYLE,
    pruefe_sperrliste,
    pruefe_steuerelemente,
    ui_quellen,
)

CSS = STYLE.read_text(encoding="utf-8")


def _probe(html: str) -> list[str]:
    return pruefe_steuerelemente({"probe.html": html}, CSS)


def test_nacktes_dateifeld_faellt_auf():
    verstoesse = _probe('<label for="x">Paket</label>\n<input type="file" id="x">')
    assert any("Dateifeld #x" in v for v in verstoesse), verstoesse


def test_dateifeld_im_rahmen_ohne_hauslabel_faellt_auf():
    verstoesse = _probe('<div class="file-upload-wrapper">\n'
                        '    <input type="file" id="x">\n'
                        '    <label for="x">Datei auswählen …</label>\n</div>')
    assert any("Dateifeld #x" in v for v in verstoesse), verstoesse


def test_muster_flaeche_ist_gruen():
    assert _probe('<div class="file-upload-wrapper">\n'
                  '    <input type="file" id="x" accept=".pdf"\n'
                  '        onchange="zeige(this.files[0])">\n'
                  '    <label for="x" class="file-upload-label"><span>Datei auswählen …</span></label>\n'
                  '</div>') == []


def test_muster_knopf_ist_gruen():
    assert _probe('<input type="file" id="x" hidden onchange="gewaehlt(this)">\n'
                  '<button class="btn-secondary" onclick="x.click()">Paket auswählen</button>') == []


def test_kaestchen_mit_eigener_groesse_faellt_auf():
    verstoesse = _probe('<input type="checkbox" id="k" style="width:16px">')
    assert any("checkbox #k" in v for v in verstoesse), verstoesse
    # Ein style am Nachbarelement zählt nicht:
    assert _probe('<th style="width: 40px"><input type="checkbox" id="k"></th>') == []


def test_stylesheet_ohne_hausregeln_faellt_auf():
    verstoesse = pruefe_steuerelemente({}, "input[type=\"checkbox\"] { accent-color: red; }")
    assert any("Kästchen und Optionsfelder" in v for v in verstoesse), verstoesse
    assert any("Feldregel" in v for v in verstoesse), verstoesse


def test_appearance_auto_nur_im_hochkontrast():
    zusatz = '\n.liste input[type="checkbox"] { appearance: auto; }'
    assert any("appearance: auto" in v for v in pruefe_steuerelemente({}, CSS + zusatz))
    assert pruefe_steuerelemente({}, CSS) == []


def test_englische_browsertexte_fallen_auf():
    for text in ("Choose File", "No file chosen", "mm/dd/yyyy"):
        verstoesse = pruefe_sperrliste(f"<span>{text}</span>", "index.html")
        assert any(text in v for v in verstoesse), (text, verstoesse)


def test_jede_eigene_js_datei_und_auth_wird_gelesen(tmp_path, monkeypatch):
    """Prüfbefund: umzug.js, formular.js und neue Dateien waren ausgenommen."""
    assert {"index.html", "app.js", "umzug.js", "formular.js", "auth.py"} <= set(ui_quellen())
    (tmp_path / "index.html").write_text("<p>leer</p>", encoding="utf-8")
    (tmp_path / "neu.js").write_text('x.innerHTML = `<input type="file" id="neu-datei">`;',
                                     encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "fremd.js").write_text('"<input type=file>"', encoding="utf-8")
    monkeypatch.setattr(gate, "STATIC", tmp_path)
    monkeypatch.setattr(gate, "INDEX", tmp_path / "index.html")
    verstoesse = pruefe_steuerelemente(None, CSS)
    assert [v.split(":")[0] for v in verstoesse] == ["neu.js"], verstoesse


def test_sperrliste_liest_auth_und_js_dateien():
    assert pruefe_sperrliste("<p>Choose File Password Submit</p>", "auth.py")
    assert pruefe_sperrliste("status.textContent = 'Loading Error';", "umzug.js")


def test_attribute_in_jeder_schreibweise():
    for tag in ("<input type='file' id='neu-datei'>", '<input type=file id="neu">',
                "<input type=\"checkbox\" id='k' style='width:16px'>"):
        assert _probe(tag), tag
    for js in ('const f = document.createElement("input"); f.type = "file";',
               "f.setAttribute('type', 'checkbox');"):
        assert any("im Skript" in v for v in pruefe_steuerelemente({"probe.js": js}, CSS)), js
    assert pruefe_steuerelemente({"probe.js": "knopf.type = 'button';"}, CSS) == []


def test_hidden_nur_als_eigenes_attribut():
    assert _probe('<input type="file" id="neu" class="feld hidden zwei">')
    assert _probe('<input type="file" id="neu" data-x="hidden">')


def test_jede_appearance_ausser_none_faellt_auf():
    for zusatz in (".liste .mein-cb { appearance: auto; width: 13px; }",
                   "input.mein-cb { appearance: revert; }",
                   ".x { -webkit-appearance: checkbox; }"):
        assert any("appearance" in v for v in pruefe_steuerelemente({}, CSS + "\n" + zusatz)), zusatz


def test_hausregel_in_media_zaehlt_nicht():
    regel = CSS[CSS.index('input[type="checkbox"], input[type="radio"] {'):]
    regel = regel[:regel.index("}") + 1]
    css = CSS.replace(regel, "@media screen and (min-width: 99999px) {\n" + regel + "\n}")
    assert any("Kästchen und Optionsfelder" in v for v in pruefe_steuerelemente({}, css))


def test_englische_attribute_und_formularwoerter():
    for html in ("<input type=\"text\" placeholder='Search'>", '<img src="x.png" alt="Loading">',
                 '<input type="submit" value="Submit">', '<input placeholder="Enter amount">',
                 '<span title="Close">x</span>', '<input placeholder="dd/mm/yyyy">',
                 '<p>Upload file</p>', '<b aria-label="Remove item">x</b>'):
        assert pruefe_sperrliste(html, "index.html"), html
    # Deutsche Lehnwörter bleiben erlaubt:
    assert pruefe_sperrliste("<p>Ein neuer Upload, optional mit Enter</p>", "index.html") == []


def test_echte_oberflaeche_ist_im_hausstil():
    """index.html, app.js, auth.py und style.css: Umzug, Import, Einrichtung
    und die Kästchen mit Inline-Größe waren vor dem Umbau rot."""
    verstoesse = pruefe_steuerelemente()
    assert verstoesse == [], "\n".join(verstoesse)


def _html_quellen() -> dict[str, str]:
    quellen = ui_quellen()
    quellen["auth.py"] = gate._html_aus_python(gate.AUTH)
    return quellen


def test_eingabefelder_nicht_in_der_knopfzeile():
    """.knopf-zeile ist für Knöpfe; Felder gehören in .feld-zeile (Breite, Umbruch, Abstand)."""
    funde = [(name, kennung) for name, quelle in _html_quellen().items()
             for zeile in re.findall(r'<div class="knopf-zeile[^"]*"[^>]*>(.*?)</div>', quelle, re.S)
             for kennung in re.findall(r'<(?:input|select|textarea)\b[^>]*\sid="([^"]+)"', zeile)]
    assert funde == []


def test_passphrasen_haben_einen_namen():
    """Ein Platzhalter ist kein Name: Er verschwindet beim Tippen und wird nicht überall vorgelesen."""
    funde = []
    for name, quelle in _html_quellen().items():
        for tag in re.findall(r'<input\b[^>]*type="password"[^>]*>', quelle):
            kennung = re.search(r'\sid="([^"]+)"', tag).group(1)
            if "aria-label" not in tag and f'for="{kennung}"' not in quelle:
                funde.append((name, kennung))
    assert funde == []


def test_paketknopf_nennt_feld_und_auswahl():
    """Der Knopf für ein verstecktes Dateifeld trägt dessen Beschriftung, und die gewählte
    Datei wird angesagt (Einrichtung und Einstellungen)."""
    quellen = _html_quellen()
    for name, knopf, label, anzeige in (
            ("auth.py", "umzug-auswahl-knopf", "umzug-datei-label", "umzug-auswahl-name"),
            ("index.html", "btn-umzug-auswahl", "umzug-datei-einstellungen-label",
             "umzug-auswahl-einstellungen")):
        quelle = quellen[name]
        tag = re.search(rf'<button\b[^>]*\sid="{knopf}"[^>]*>', quelle).group(0)
        assert f'aria-labelledby="{label} {knopf}"' in tag, name
        assert f'aria-describedby="{anzeige}"' in tag, name
        assert re.search(rf'<label\b[^>]*\sid="{label}"', quelle), name
        assert re.search(rf'<\w+\b[^>]*\sid="{anzeige}"[^>]*aria-live="polite"', quelle), name


def test_symbole_im_dateiknopf_sind_stumm():
    """Das Symbol im Hauslabel ist Schmuck; vorgelesen wird nur der Text daneben."""
    funde = [(name, i) for name, quelle in _html_quellen().items()
             for label in re.findall(r'<label\b[^>]*class="file-upload-label"[^>]*>(.*?)</label>', quelle, re.S)
             for i in re.findall(r'<i\b[^>]*>', label) if 'aria-hidden="true"' not in i]
    assert funde == []
