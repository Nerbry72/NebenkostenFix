"""NK-149 (F-78): keine unmaskierte Einsetzung in HTML-Schablonen.

Bis NK-149 setzten die Anlagenuebersicht und die Zeitleiste Nutzertext ohne
``escapeHtml`` in ``innerHTML``; eine praeparierte Rechnungsnummer fuehrte
beim Oeffnen der Zeitleiste Code aus. Beim Durchsehen fielen weitere Stellen
auf: Namen in Auswahllisten, Einheiten, und eine Vorschlagskarte, die den
ganzen Vorschlag samt Mietername als JSON in ein ``onclick``-Attribut mit
einfachen Anfuehrungszeichen schrieb (ein Apostroph im Namen brach aus).

Der Waechter (``scripts/html_maskierung.py``) meldet jede Einsetzung, die
weder maskiert ist noch einer sicheren Form folgt. Was bleibt, steht hier
mit Begruendung. Eine neue Einsetzung von Nutzertext macht den Test rot.
"""

from __future__ import annotations

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / 'scripts'))

import html_maskierung  # noqa: E402

# Schluessel: die ersten 60 Zeichen des normierten Ausdrucks.
AUSNAHMEN = {
    # Im Code gebautes HTML, Nutzertext darin ist schon maskiert
    'beleg': 'Symbol-HTML aus festen Zeichenketten',
    'klasse': 'Phosphor-Klasse aus festen Zeichenketten (getCategoryIcon, NK-156)',
    'html': 'Tabelle, deren Zellen einzeln maskiert werden',
    'rows': 'Zeilen, deren Zellen einzeln maskiert werden',
    'tableRows': 'Zeilen, deren Zellen einzeln maskiert werden',
    'liste': 'Liste aus maskierten Eintraegen (Versionen)',
    'knopf': 'Knopf aus Code-Konstanten',
    'marke': 'Symbol aus Code-Konstanten',
    'hinweis': 'feste Zeichenkette',
    'weitere': 'Zahl aus der Laenge der Liste (D-116)',
    "zeilen.slice(3).join('')": 'Zeilen, deren Texte einzeln maskiert werden (D-116)',
    'iconImKnopf': 'Symbolklasse aus Code-Konstanten',
    'icon': 'Symbolklasse oder -HTML aus Code-Konstanten',
    'getIcon(group.category)': 'liefert ein Emoji aus einer festen Tabelle',
    'valStr': 'Wert-HTML aus Zahlformat und maskierter Einheit',
    'ttStr': 'Tooltip aus Datum, Zahl und maskierter Einheit',
    'subDesc': 'escapeHtml(sub.description), ggf. in wrapInterpolated',
    "hasSub ? '' : itemDesc": 'escapeHtml(item.description), ggf. in wrapInterpolated',
    'tCons': 'toFixed(1) in wrapInterpolated',
    'mCons': 'toFixed(1) in wrapInterpolated',
    'aCons': 'toFixed(1) in wrapInterpolated',
    'prozent': 'toLocaleString der Allgemeinquote (NK-209)',
    "r.veraltet ? REGELSTAND_HINWEIS : ''": 'fester Hinweistext (NK-217)',
    "umschlag.veraltet ? REGELSTAND_HINWEIS : ''": 'fester Hinweistext (NK-217)',
    'pfTitle': 'feste Zeichenkette je Ampelstufe',
    'umschlag.version ? `<p style="color: var(--text-muted); marg':
        'Versionsnummer (Zahl), Texte darin maskiert',
    'group.kaution > 0 ? ` <div style="display: flex; justify-con':
        'Betraege per toLocaleString',
    "k.last_login_at ? escapeHtml(k.last_login_at) : 'nie'": 'maskiert oder fest',
    "data.balance > 0 ? 'Nachzahlung des Mieters' : (data.balance":
        'verschachtelter Ternaer aus festen Zeichenketten',
    "data.balance > 0 ? 'Nachzahlung des Mieters:' : (data.balanc":
        'verschachtelter Ternaer aus festen Zeichenketten',
    "p.type === 'Miete' ? 'badge-primary' : (p.type === 'Nebenkos":
        'CSS-Klassen aus festen Zeichenketten',
    # Oberflaechentexte aus Code-Konstanten (Erste Schritte, Leerzustaende)
    # NK-160: Bausteine des Jahresassistenten, jeder aus maskierten Teilen.
    'mieterKopf': 'Name, Wohnung und Zeitraum, einzeln maskiert',
    'positionen': 'Listenpunkte, Kostenart, Betrag und Rechenweg einzeln maskiert',
    'warnListe': 'Warnungen, einzeln maskiert',
    'warnungenHtml(hinweise)': 'Listenpunkte aus warnungenHtml, jeder Text maskiert (F-116)',
    'gruende': 'Listenpunkte des Zeitraumvorschlags, jeder Grund maskiert (NK-186)',
    'kopf': 'Kopf des Zeitraumvorschlags, Daten maskiert (NK-186)',
    'pdfLinks': 'Adressen aus dateiAdresse (Zahl), Texte fest',
    'zustellung': 'Datum maskiert oder Knopf mit Zahl',
    's.aktion': 'Funktionsaufruf aus der Schrittdefinition im Code',
    's.aktionsText': 'Knopftext aus der Schrittdefinition (Glossar-Pruefung)',
    's.titel': 'Schritttitel aus dem Code',
    's.beschreibung': 'Schritttext aus dem Code',
    'aktion.fn': 'Funktionsaufruf aus dem Code (leerzustand)',
    'aktion.icon': 'Symbolklasse aus dem Code (leerzustand)',
    'aktion.label': 'Knopftext aus dem Code (Glossar-Pruefung)',
    'titel': 'Leerzustand-Titel, alle Aufrufer mit Konstanten',
    'text': 'Leerzustand-Text bzw. HEIZKOSTENARTEN_TEXT (Konstanten)',
    'schluessel': 'Schluessel aus HEIZKOSTENARTEN_TEXT (Konstante)',
    # Zahlen, Datum, Kennungen
    'apt.sqm': 'Zahl aus der Datenbank (Float-Spalte)',
    'jahr.jahr': 'Jahreszahl (Integer vom Server)',
    's.belege': 'Anzahl (Integer)',
    'cat.invoice_count': 'Anzahl (Integer)',
    'kpis.open_tasks': 'Anzahl (Integer)',
    'formatVal(r.value)': 'Intl.NumberFormat',
    'formatVal(r.value_nt)': 'Intl.NumberFormat',
    'rDate': 'toLocaleDateString',
    'rStart': 'toLocaleDateString',
    'rEnd': 'toLocaleDateString',
    'dateStr': "toLocaleDateString oder '-'",
    'r.start_date': 'ISO-Datum vom Server (Date-Spalte)',
    'r.end_date': 'ISO-Datum vom Server (Date-Spalte)',
    'accId': 'Kennung aus Zaehlschleife',
    'stepCount++': 'Zaehler',
    'pct': 'Prozentwert (Zahl)',
    'overlapDays': 'Tage (Zahl)',
    'intervalDays': 'Tage (Zahl)',
    'missingDays': 'Tage (Zahl)',
    'umschlag.version': 'Versionsnummer (Integer)',
    # Adressen, gebaut mit dateiUrl()
    'imgUrl': 'dateiAdresse(art, Zahl) (NK-129)',
    'docUrl': 'dateiAdresse(art, Zahl) (NK-129)',
}


def _funde():
    quelle = html_maskierung.APP_JS.read_text(encoding='utf-8')
    return html_maskierung.unmaskierte_ausdruecke(quelle)


def test_keine_unbegruendete_unmaskierte_einsetzung():
    offen = sorted({(zeile, ausdruck) for zeile, ausdruck in _funde()
                    if ausdruck[:60] not in AUSNAHMEN})
    assert offen == [], (
        'Unmaskierte Einsetzung in einer HTML-Schablone. escapeHtml(…) '
        'verwenden oder mit Begruendung in AUSNAHMEN eintragen:\n'
        + '\n'.join(f'  static/app.js:{z}: ${{{a[:80]}}}' for z, a in offen))


def test_ausnahmeliste_hat_keine_leichen():
    """Jede Ausnahme muss noch vorkommen, sonst waechst die Liste still."""
    vorhanden = {ausdruck[:60] for _, ausdruck in _funde()}
    tot = sorted(set(AUSNAHMEN) - vorhanden)
    assert tot == [], f'Ausnahmen ohne Fundstelle: {tot}'


def test_die_befundstellen_aus_f78_sind_maskiert():
    quelle = html_maskierung.APP_JS.read_text(encoding='utf-8')
    assert '<strong>${escapeHtml(anlage.name)}</strong>' in quelle
    assert 'Nr. ${escapeHtml(e.invoice_number)}' in quelle
    assert "${escapeHtml(wer || 'Ohne Anbieter')}" in quelle
    assert "${escapeHtml(e.property_name || '')}" in quelle
    # Kein Objekt als JSON in einem onclick-Attribut (Vorschlagskarte).
    assert "onclick='" not in quelle


def test_der_waechter_erkennt_eine_neue_luecke():
    """Gegenprobe: der Scanner meldet eine unmaskierte Einsetzung."""
    probe = "el.innerHTML = `<b>${mieter.name}</b> ${escapeHtml(x)} ${a.id}`;"
    assert [a for _, a in html_maskierung.unmaskierte_ausdruecke(probe)] == \
        ['mieter.name']


def test_dateien_nur_per_kennung_nie_per_pfad():
    """NK-129: die Oberflaeche nennt nie einen Pfad, nur Art und Kennung."""
    quelle = html_maskierung.APP_JS.read_text(encoding='utf-8')
    assert '/api/files' not in quelle
    assert '${Number(kennung)}' in quelle
