"""Prueft die Beschriftungen der Oberflaeche gegen den Begriffskatalog
(docs/glossar.md). Teil des Ziels 0.8 (NK-074): der Katalog ist nicht
nur Text, sondern wird maschinell geprueft.

Geprueft werden (jeweils ueber static/index.html und die in static/app.js
erzeugten Beschriftungen):

  1. Navigationskanon (Glossar Par. 5): Zieltab, Beschriftung und Icon.
  2. Verbliste fuer Schaltflaechen (Glossar Par. 6): jeder Aktionsknopf
     beginnt mit einem Verb aus dem Katalog. Ausgenommen: Filterpillen
     (Kategorienamen), Knopfe ohne sichtbaren Text (Icon-Knoepfe) und
     die Titelzeilen der Erste-Schritte-Fuehrung.
  3. Sperrliste (Glossar Par. 7): englische Reste, verworfene Synonyme
     und die Du-Form.
  4. Umlagearten (Glossar Par. 2): die Auswahl im Kostenprofil traegt
     die Texte aus abrechnungsart.ARTEN wortgleich.

Aufruf als Werkzeug:  python scripts/ui_beschriftungen.py
Als Pruefung im Testlauf: tests/test_ui_konsistenz.py ruft die gleiche
Funktion auf und schlaegt fehl, sobald ein Verstoess gefunden wird.
"""

from __future__ import annotations

import ast
import html as html_mod
import re
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parents[1]
STATIC = BASIS / "static"
INDEX = STATIC / "index.html"
APP = STATIC / "app.js"

# NK-139: die Meldungen des Backends sind Beschriftungen wie die Knopftexte
# -- die Oberflaeche zeigt, was das Backend zurueckgibt. Diese Fachmodule
# werden deshalb mit derselben Sperrliste gelesen.
BACKEND_DATEIEN: tuple[str, ...] = (
    "app.py", "rechenkern.py", "heizung.py", "co2.py", "auth.py",
    "nutzung.py",
)

# Rechenkern-Pakete importierbar machen, auch bei direktem Aufruf:
if str(BASIS) not in sys.path:
    sys.path.insert(0, str(BASIS))

# --- Glossar Par. 5: Navigationskanon -------------------------------
NAV_KANON: list[tuple[str, str, str]] = [
    ("dashboard", "\u00dcbersicht", "ph-squares-four"),
    ("properties", "Immobilien", "ph-house"),
    ("tenants", "Mieter", "ph-users"),
    ("meters", "Z\u00e4hler & Ablesungen", "ph-gauge"),
    ("invoices", "Rechnungen & Belege", "ph-receipt"),
    ("billing", "Abrechnungen", "ph-file-text"),
    ("payments", "Zahlungen", "ph-coins"),
    ("reports", "Statistiken", "ph-chart-line-up"),
    ("settings", "Einstellungen", "ph-gear"),
]

# --- Glossar Par. 6: Verbliste --------------------------------------
VERBEN: set[str] = {
    "anlegen", "erfassen", "hochladen", "erstellen", "bearbeiten",
    "l\u00f6schen", "speichern", "abbrechen", "schlie\u00dfen",
    "exportieren", "herunterladen", "drucken", "aktualisieren",
    "zur\u00fccksetzen", "\u00f6ffnen", "ansehen", "abrechnen",
    "abmelden", "weiter", "\u00e4ndern", "einspielen",
    # NK-152: Ordnerwahl ueber den Dialog der Windows-App.
    "ausw\u00e4hlen",
    # NK-081: Update-Suche auf Knopfdruck und Installation (Windows-App).
    "suchen", "installieren",
    # NK-164: den Bestand einer anderen Installation übernehmen (ersetzt alles).
    "\u00fcbernehmen",
    # NK-161: Tabellen aus Excel/CSV einlesen und probeweise prüfen.
    "importieren", "pr\u00fcfen",
    # NK-162: Sitzung verlängern und einen gesicherten Entwurf zurückholen.
    "bleiben", "wiederherstellen",
    # NK-160: im mehrstufigen Assistenten einen Schritt zurückgehen.
    "zur\u00fcck",
    # NK-124/NK-160: die Zustellung einer Abrechnung melden (Fristen).
    "melden",
    # NK-174/NK-175: Haftungshinweis quittieren, Update-Hinweis vertagen.
    "verstanden", "erinnern",
}

# Knopftexte, die zwar mit einem Verb aus der Liste beginnen, aber das
# verlorene Vokabular tragen (fruehere Fehler, als Beispiel hier
# festgehalten, damit sie nicht zurueckkommen):
VERBOTENE_KNOPFTEXTE: set[str] = {
    "Profil speichern",      # -> Kostenprofil speichern
    "Stand speichern",       # -> Ablesung speichern
    "Dokument hochladen",    # -> Beleg hochladen
    "Detaillierte PDF",      # -> PDF erstellen (detailliert)
    "Einfache PDF",          # -> PDF erstellen (einfach) / PDF ansehen
    "Export",                # -> Daten exportieren (Glossar Par. 6)
}

# --- Glossar Par. 7: Sperrliste -------------------------------------
# Englische Reste (gross-/kleinschreibung genau so, Wortgrenze):
ENGLISCHE_RESTE: list[str] = [
    "Dashboard", "Settings", "Danger Zone", "YTD", "Loading", "Delete",
    "Save", "Cancel", "Error", "Warning", "Invoice", "Tenant",
    "Property", "Meter", "Reading", "Payment",
]
# Verworfene Synonyme (Par. 1 und 2):
VERWORFENE_SYNONYME: list[str] = [
    "Kostenpunkt", "Dokumenten-Manager", "Nach Quadratmeter",
    "Zahlt nichts", "Sammel-Dokument",
]
# Du-Form (Par. 7), gross-/kleinunabhaengig an Wortgrenze:
DU_FORM = re.compile(
    r"\b(du|dir|dich|dein|deine|deinen|deinem|deiner|deines)\b",
    re.IGNORECASE,
)

# Die Imperativ-Anrede (Par. 7, NK-139): 'Trage … nach' fordert den Leser
# genauso direkt auf wie 'dein' -- in der Sie-Form heisst es 'Tragen Sie',
# und dieses Wortpaar faellt durch die Wortgrenze nicht unter. Ohne diese
# Liste waere 'Lege fest, wie …' am Wächter vorbeigerutscht.
ANREDE_IMPERATIV = re.compile(
    r"\b(Trage|Setze|Lasse|Gib|Lege|Ersetze|Nenne|Prüfe|Pruefe|Wechsle"
    r"|Ergänze|Ergaenze|Hänge|Haenge)\b",
)

# Ausnahmen, die die Sperrliste absichtlich nicht trifft, mit Begruendung:
#  * 'qm' und 'Eigenverbrauch' in app.js: Datenwerte bzw. der Fachbegriff
#    des Teilbetrags "Eigenverbrauch (X m3)" bei direkt zugewiesenen
#    Rechnungen (Entscheidung zu F-20/NK-096) -- kein Artname und keine
#    Beschriftung im Knopfsinn.
#  * 'Eigenverbrauch' als Zwischenueberschrift der Vorschlagskarte
#    (index.html, gleiche Bedeutung wie der Teilbetrag).
QM_IN_APP = "qm"
EIGENVERBRAUCH_IN_APP = "Eigenverbrauch"


def _lies(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


def _normalisiere_knopftext(text: str) -> str:
    """Macht aus rohem HTML-Fragment den sichtbaren Knopftext."""
    text = re.sub(r"\$\{[^}]*\}", " ", text)          # Template-Ausdruecke
    text = re.sub(r"<[^>]+>", " ", text)               # Tags
    text = html_mod.unescape(text)
    text = text.replace("\u201e", " ").replace("\u201c", " ")
    text = re.sub(r"['\"+]", " ", text)                # JS-Kettenreste
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2700-\u27BF\u2190-\u21FF\u2705\u274C]",
                  " ", text)                           # Emoji
    return re.sub(r"\s+", " ", text).strip()


def _sichtbarer_text_index(quelle: str) -> str:
    """Sichtbarer Text von index.html: Textknoten plus Titelzeilen
    (title/aria-label/placeholder). Ids, Klassen und Funktionsnamen
    bleiben draussen -- die Sperrliste gilt der Beschriftung."""
    quelle = re.sub(r"<!--[\s\S]*?-->", " ", quelle)
    quelle = re.sub(r"<(script|style)\b[\s\S]*?</\1>", " ", quelle)
    texte = re.findall(r">([^<>]*)<", quelle)           # Textknoten
    attribute = re.findall(
        r'(?:title|aria-label|placeholder)="([^"]*)"', quelle)
    return _normalisiere_knopftext(" ".join(texte + attribute))


def _ohne_js_kommentare(quelle: str) -> str:
    """Entfernt JS-Zeilenkommentare (//), aber nicht innerhalb von
    Zeichenketten -- so verschieben Kommentar-Texte die Paarbildung der
    Anfuehrungszeichen nicht. Blockkommentare werden danach entfernt."""
    zeilen = []
    for zeile in quelle.split("\n"):
        ausgabe = []
        offen = None
        i = 0
        while i < len(zeile):
            c = zeile[i]
            if offen:
                if c == offen:
                    offen = None
                ausgabe.append(c)
            elif c in ("'", '"', "`"):
                offen = c
                ausgabe.append(c)
            elif c == "/" and i + 1 < len(zeile) and zeile[i + 1] == "/":
                break                       # Rest der Zeile: Kommentar
            else:
                ausgabe.append(c)
            i += 1
        zeilen.append("".join(ausgabe))
    return re.sub(r"/\*[\s\S]*?\*/", " ", "\n".join(zeilen))


def _sichtbare_zeichenketten_app(quelle: str) -> str:
    """Zeichenketten-Inhalte aus app.js (einfache Anfuehrung, doppelte,
    Template-Literale). Kommentare und Code-Bezeichner bleiben draussen;
    Code innerhalb von Template-Ausdruecken (${...}) ebenso."""
    quelle = _ohne_js_kommentare(quelle)
    quelle = re.sub(r"\$\{[^{}]*\}", " ", quelle)
    teile = re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"|`([^`]*)`", quelle)
    return _normalisiere_knopftext(" ".join(a or b or c for a, b, c in teile))


def _knopfe(quelle: str) -> list[tuple[str, str, str]]:
    """Liefert (roher_Tag, sichtbarer_Text, Klassen) aller <button>.
    Auch ueber aneinandergereihte JS-Zeichenketten hinweg; dafuer wird
    der Quelltext als ein grosses HTML behandelt."""
    ergebnis = []
    for m in re.finditer(r"<button\b([^>]*)>([\s\S]*?)</button>", quelle):
        tag = m.group(1)
        klasse_m = re.search(r'class="([^"]*)"', tag)
        klasse = klasse_m.group(1) if klasse_m else ""
        ergebnis.append((tag, _normalisiere_knopftext(m.group(2)), klasse))
    return ergebnis


def _traegt_verb(text: str) -> bool:
    """Deutsche Wortstellung: das Verb steht am Ende ('Immobilie anlegen')
    oder am Anfang ('Weiter zur Vorschau'). Nebenteile hinter '&' oder
    '/' zaehlen einzeln ('PDF erstellen & abschließen', 'Drucken / als
    PDF speichern'). Klammern tragen Naeherung, kein eigenes Verb
    ('PDF erstellen (detailliert)')."""
    text = re.sub(r"\([^)]*\)", " ", text)
    for teil in re.split(r"[&/]", text):
        woerter = teil.split()
        if not woerter:
            continue
        if woerter[0].lower() in VERBEN or woerter[-1].lower() in VERBEN:
            return True
    return False


def pruefe_verben(quelle: str) -> list[str]:
    """Jeder Aktionsknopf traegt ein Verb aus der Liste (Glossar Par. 6)."""
    verstoesse = []
    for _tag, text, klasse in _knopfe(quelle):
        if not text:
            continue                       # Icon-Knopf (nur <i>)
        if "filter-pill" in klasse:
            continue                       # Auswahlpille: Kategoriename
        if text.startswith("Erste Schritte"):
            continue                       # Titel, kein Knopf
        if text in VERBOTENE_KNOPFTEXTE:
            verstoesse.append(f"Knopftext verboten: {text!r} (Glossar Par. 6)")
            continue
        if not _traegt_verb(text):
            verstoesse.append(
                f"Knopftext traegt kein Verb: {text!r} "
                f"(erlaubt: {', '.join(sorted(VERBEN))})")
    return verstoesse


def pruefe_sperrliste(quelle: str, datei: str) -> list[str]:
    """Glossar Par. 7: englische Reste, verworfene Synonyme, Du-Form.
    Geprueft wird nur sichtbarer Text (bei index.html Textknoten und
    Titelzeilen, bei app.js Zeichenketten-Inhalte)."""
    if datei == "index.html":
        sichtbar = _sichtbarer_text_index(quelle)
    else:
        sichtbar = _sichtbare_zeichenketten_app(quelle)
    verstoesse = []
    for wort in ENGLISCHE_RESTE:
        if re.search(rf"\b{re.escape(wort)}\b", sichtbar):
            verstoesse.append(f"{datei}: englischer Rest {wort!r} (Par. 7)")
    for syn in VERWORFENE_SYNONYME:
        if syn.lower() in sichtbar.lower():
            verstoesse.append(f"{datei}: verworfenes Synonym {syn!r} (Par. 7)")
    for m in DU_FORM.finditer(sichtbar):
        verstoesse.append(
            f"{datei}: Du-Form {m.group(0)!r} (Par. 7 -- gesiezt)")
    for m in ANREDE_IMPERATIV.finditer(sichtbar):
        verstoesse.append(
            f"{datei}: Imperativ-Anrede {m.group(0)!r} "
            f"(Par. 7 -- 'Legen Sie', 'Tragen Sie', …)")
    # Fachliche Verbote im sichtbaren Text:
    if datei == "app.js":
        # 'qm' kommt in app.js als Datenwert (Schluessel von ARTEN,
        # Auswahl-Wert) vor -- das ist kein beschrifteter Text. Deshalb
        # hier nicht geprueft; index.html prueft es oben.
        pass
    else:
        for m in re.finditer(r"\bqm\b", sichtbar):
            verstoesse.append(f"{datei}: 'qm' (Par. 7 -- 'm\u00b2')")
    for m in re.finditer(r"\bDokument(en)?\b", sichtbar):
        verstoesse.append(
            f"{datei}: 'Dokument' (Par. 1 -- 'Beleg')")
    if datei == "index.html":
        for m in re.finditer(r"\b(Objekt|Einheit)\b", sichtbar):
            verstoesse.append(
                f"{datei}: {m.group(0)!r} (Par. 7 -- Wohnung/Haus)")
        for m in re.finditer(r"\bExport\b", sichtbar):
            verstoesse.append(
                f"{datei}: 'Export' allein (Par. 6 -- 'Daten exportieren')")
    return verstoesse


def pruefe_navigation(quelle: str) -> list[str]:
    """Glossar Par. 5: Ziel, Beschriftung und Icon wortgleich."""
    verstoesse = []
    gefunden = re.findall(
        r'<a[^>]*class="nav-item[^"]*"[^>]*data-tab="(\w+)"[^>]*>'
        r'\s*<i class="ph ([\w-]+)"></i>\s*([^<]+)', quelle)
    ist = [(tab, _normalisiere_knopftext(text), icon) for tab, icon, text in gefunden]
    if ist != NAV_KANON:
        for erwartet, wirklich in zip(NAV_KANON, ist):
            if erwartet != wirklich:
                verstoesse.append(
                    f"Navigation weicht ab bei {erwartet[0]!r}: erwartet "
                    f"{erwartet[1:]!r}, wirklich {wirklich[1:]!r} (Par. 5)")
        if len(ist) != len(NAV_KANON):
            verstoesse.append(
                f"Navigation hat {len(ist)} Eintraege, Kanon verlangt "
                f"{len(NAV_KANON)} (Par. 5)")
    return verstoesse


def pruefe_umlagearten(quelle: str) -> list[str]:
    """Glossar Par. 2: Auswahl im Kostenprofil traegt ARTEN wortgleich."""
    from abrechnungsart import ARTEN

    verstoesse = []
    block = re.search(
        r'<select id="profile-cat-\$\{[^}]+\}"[\s\S]*?</select>', quelle)
    if not block:
        return ["Kostenprofil-Auswahl (profile-cat) nicht gefunden"]
    optionen = re.findall(
        r'<option value="(\w+)"[^>]*>([^<]+)</option>', block.group(0))
    ist = dict(optionen)
    for schluessel, text in ARTEN.items():
        if ist.get(schluessel) != text:
            verstoesse.append(
                f"Umlageart {schluessel!r}: erwartet {text!r}, wirklich "
                f"{ist.get(schluessel)!r} (Par. 2, wortgleich mit ARTEN)")
    if set(ist) != set(ARTEN):
        verstoesse.append(
            f"Umlagearten-Auswahl hat {sorted(ist)}, ARTEN kennt "
            f"{sorted(ARTEN)} (Par. 2)")
    return verstoesse


def _zeichenketten_python(pfad: Path) -> list[tuple[int, str]]:
    """Alle Text-Konstanten einer Python-Datei mit Zeilennummer.

    Der Baum liefert genau die Zeichenketten-Literale -- auch die Teile
    einer f-Zeichenkette, denn ``ast.walk`` steigt in den JoinedStr
    hinab und bringt dessen Konstanten mit; die Ausdruecke dazwischen
    bleiben unsichtbar. Namen und Kommentare bleiben aussen vor:
    Kommentare sprechen die Entwicklung an, nicht den Vermieter.
    """
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    return [
        (knoten.lineno, knoten.value)
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)
    ]


# --- NK-149 (F-79): Modulliste aus den Importen, Umschrift als Regel -------
#
# Bis NK-149 stand die Liste der Fachmodule von Hand in BACKEND_DATEIEN, und
# sechs Module mit Meldungen fehlten darin (backup, mieter_daten, frist ...).
# Jetzt folgt der Waechter den Importen ab app.py: jedes eigene Modul, das
# die laufende Anwendung laedt, kann Text in eine Antwort geben.

LOG_METHODEN = frozenset({'debug', 'info', 'warning', 'error', 'exception',
                          'critical', 'log'})

# Umschrift, die ohne Woerterbuch sicher ist: Wortstaemme, die im Deutschen
# nur mit Umlaut vorkommen. Ergaenzt um das Vokabular, das die Anwendung
# selbst schon mit Umlaut schreibt (siehe _umlaut_vokabular).
UMSCHRIFT_STAEMME = re.compile(
    r"(?i)\b\w*(waehl|gueltig|ueber|fuer|koenn|muess|moecht|loesch|pruef|"
    r"aender|hoechst|passwoert|zaehl|schluess|groess|rueck|naechst|spaet|"
    r"bestaetig|zurueck|eintraeg|ausfuehr|verfueg|moeglich|noetig|uebrig|"
    r"fuell|faellig|enthaelt|gehoer|wuerd|waer|haett|oeffn|schliess|"
    r"geaendert|geloescht|geprueft|gewaehlt|verknuepf|Oberflaech|Aenderung|"
    r"Loeschung|Pruefung|Zaehler|Wohnungsgroess|Rueckfrage|Datensaetz|"
    r"Saetz|Vorgaeng|Rechnungsbetraeg|Betraeg|Grundstueck|stueck|"
    r"Gebaeud|Geraet|Einzugsermaechtig|Verhaeltnis|verhaeltnis|Haelfte|"
    r"Aufschlaeg|Abschlaeg|Ausloes|ausloes|fuehr|Fuehr|koennt|duerf|"
    r"Duerf|unzulaessig|zulaessig|Maengel|laeng|Laeng|loes|Loes|laess|"
    r"haeng|raeum|Raeum|Uebersicht)\w*\b")

# Woerter, die in ASCII bleiben muessen: Befehlsnamen auf der Kommandozeile.
UMSCHRIFT_ERLAUBT = frozenset({
    'zusammenfuehren',  # python scripts/kostenarten.py zusammenfuehren
})


def backend_module(basis: Path | None = None) -> list[str]:
    """Die eigenen Module, die app.py laedt, direkt oder ueber andere."""
    basis = basis or BASIS
    offen = ['app.py', *BACKEND_DATEIEN]
    gesehen: list[str] = []
    while offen:
        name = offen.pop()
        if name in gesehen or not (basis / name).is_file():
            continue
        gesehen.append(name)
        baum = ast.parse((basis / name).read_text(encoding='utf-8'))
        for knoten in ast.walk(baum):
            ziele = []
            if isinstance(knoten, ast.Import):
                ziele = [a.name for a in knoten.names]
            elif isinstance(knoten, ast.ImportFrom) and knoten.module \
                    and not knoten.level:
                ziele = [knoten.module]
            for ziel in ziele:
                kandidat = ziel.replace('.', '/') + '.py'
                if (basis / kandidat).is_file():
                    offen.append(kandidat)
    return sorted(gesehen)


def _meldungen_python(pfad: Path) -> list[tuple[int, str]]:
    """Zeichenketten, die ein Mensch als Satz liest: ohne Docstrings, ohne
    Protokollzeilen fuer den Betrieb, ohne Bezeichner (kein Leerzeichen)."""
    baum = ast.parse(pfad.read_text(encoding='utf-8'))
    aussen: set[int] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Module, ast.FunctionDef,
                               ast.AsyncFunctionDef, ast.ClassDef)):
            if knoten.body and isinstance(knoten.body[0], ast.Expr) and \
                    isinstance(knoten.body[0].value, ast.Constant):
                aussen.add(id(knoten.body[0].value))
        if isinstance(knoten, ast.Call) and \
                isinstance(knoten.func, ast.Attribute) and \
                knoten.func.attr in LOG_METHODEN:
            for teil in ast.walk(knoten):
                aussen.add(id(teil))
    return [
        (k.lineno, k.value) for k in ast.walk(baum)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
        and id(k) not in aussen and ' ' in k.value.strip()
    ]


def _umlaut_vokabular(basis: Path) -> set[str]:
    """Woerter, die die Anwendung schon mit Umlaut schreibt."""
    vokabular: set[str] = set()
    quellen = [basis / 'static' / 'index.html', basis / 'static' / 'app.js',
               basis / 'docs' / 'glossar.md']
    for quelle in quellen:
        if quelle.is_file():
            vokabular.update(
                w.lower() for w in re.findall(r'[A-Za-zÄÖÜäöüß]+',
                                              quelle.read_text(encoding='utf-8'))
                if re.search('[äöüÄÖÜ]', w))
    return vokabular


def _umlautiert(wort: str) -> str:
    for a, b in (('ae', 'ä'), ('oe', 'ö'), ('ue', 'ü'),
                 ('Ae', 'Ä'), ('Oe', 'Ö'), ('Ue', 'Ü')):
        wort = wort.replace(a, b)
    return wort


def pruefe_umschrift(basis: Path | None = None) -> list[str]:
    """Meldungen in echten Umlauten (Glossar Par. 7, NK-149/F-79)."""
    basis = basis or BASIS
    vokabular = _umlaut_vokabular(basis)
    verstoesse: list[str] = []
    for name in backend_module(basis):
        for zeile, text in _meldungen_python(basis / name):
            # Platzhalter {zaehler} und Codes wie W-ZAEHLER-… sind keine
            # Woerter fuer den Leser.
            text = re.sub(r'\{[^{}]*\}', ' ', text)
            for wort in re.findall(r'[A-Za-zÄÖÜäöüß]+', text):
                if not re.search('(?i)ae|oe|ue', wort) or wort.isupper() \
                        or wort in UMSCHRIFT_ERLAUBT:
                    continue
                if UMSCHRIFT_STAEMME.fullmatch(wort) or \
                        _umlautiert(wort).lower() in vokabular:
                    verstoesse.append(
                        f"{name}:{zeile}: Umschrift {wort!r} statt "
                        f"{_umlautiert(wort)!r} (Par. 7)")
    return verstoesse


def pruefe_backend_meldungen(basis: Path | None = None) -> list[str]:
    """Die Meldungen des Backends sind gesiezt (Par. 7, NK-139).

    Geprueft werden die Zeichenketten-Konstanten aller Fachmodule, die die
    Anwendung laedt (seit NK-149 aus den Importen abgeleitet, vorher die
    feste Liste ``BACKEND_DATEIEN``): Fehlermeldungen, Warnungen und
    Blocker, die die Oberflaeche dem Vermieter zeigt. Jede Du-Form und jede
    Imperativ-Anrede ist ein Verstoess.
    """
    basis = basis or BASIS
    verstoesse: list[str] = []
    for name in backend_module(basis):
        pfad = basis / name
        if not pfad.is_file():
            continue
        for zeile, text in _zeichenketten_python(pfad):
            for m in DU_FORM.finditer(text):
                verstoesse.append(
                    f"{name}:{zeile}: Du-Form {m.group(0)!r} (Par. 7)")
            for m in ANREDE_IMPERATIV.finditer(text):
                verstoesse.append(
                    f"{name}:{zeile}: Imperativ-Anrede {m.group(0)!r} "
                    f"(Par. 7 -- gesiezt)")
    return verstoesse


def alle_verstoesse() -> list[str]:
    """Fuehrt alle Pruefungen aus; liefert die Verstoesse als Texte."""
    index = _lies(INDEX)
    app = _lies(APP)
    verstoesse: list[str] = []
    verstoesse += pruefe_verben(index)
    verstoesse += pruefe_verben(app)
    verstoesse += pruefe_sperrliste(index, "index.html")
    verstoesse += pruefe_sperrliste(app, "app.js")
    verstoesse += pruefe_navigation(index)
    verstoesse += pruefe_umlagearten(app)
    verstoesse += pruefe_backend_meldungen()
    verstoesse += pruefe_umschrift()
    return verstoesse


def main() -> int:
    verstoesse = alle_verstoesse()
    if verstoesse:
        print(f"UI-Beschriftungen: {len(verstoesse)} Verst\u00f6\u00dfe:")
        for v in verstoesse:
            print(f"  - {v}")
        return 1
    print("UI-OK: Beschriftungen folgen dem Begriffskatalog "
          "(docs/glossar.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
