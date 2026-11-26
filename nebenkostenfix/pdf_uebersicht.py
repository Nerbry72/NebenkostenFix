"""Das Übersichtsblatt vor dem Detailteil (Phase 59, Issue #35 Punkt 2).

Der Melder hat eine Musterabrechnung angehängt und dazu geschrieben:
*„Nach dieser Aufstellung könnte dann noch die Einzelne Berechnung folgen,
wie sie bereits ausgegeben wird."* Er will also **nichts wegnehmen**,
sondern eine Seite davor, die alles auf einen Blick zeigt: eine Tabelle
mit einer Zeile je Kostenposition und drei Summen.

Das ist auch der einzige Weg, der geht. Der Detailteil hängt an Regeln --
Rechenweg je Zeile und Belegliste (R-DOC-01 Punkt 6–8), Heiz- und
CO₂-Abschnitt (R-HK-01), § 35a-Ausweis. Wer dort kürzt, ändert die
Rechtslage der Abrechnung. Eine Übersicht davor tut das nicht.

**Das Gefährliche an einem Übersichtsblatt ist nicht sein Layout, sondern
seine Summe.** Zwei Wege zur selben Zahl können auseinanderlaufen: Eine
Übersicht, die 1.200,00 € nennt, während der Detailteil dahinter auf
1.198,37 € kommt, ist schlimmer als keine Übersicht -- dieselbe Klasse
wie der gemischte Nenner aus Phase 55. Darum rechnet hier **nichts nach**:
``uebersicht`` summiert genau die ``tenant_cost`` der Posten, die auch der
Detailteil zeigt, und ``pruefe_summe`` bricht ab, wenn das Ergebnis von
der Gesamtsumme der Abrechnung abweicht. Ein Abbruch ist sichtbar, eine
falsche Zahl auf einem Brief an den Mieter nicht.

Die Spalten folgen dem Muster des Melders, die Wörter aber dem Vorrat der
Anwendung: Der Verteilerschlüssel kommt aus ``abrechnungsart.ARTEN`` (die
Begriffe, die auch im Mieterprofil stehen), die Trennung Betriebs- gegen
Heizkosten aus ``heizung.BETRKV_NR`` (Nr. 4, 5, 6 des § 2 BetrKV). Keine
zweite Liste, die auseinanderdriften könnte.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, Spacer,
                                Table, TableStyle)
# Bandit-Ausnahme: maskiert Text fuer reportlab, parst kein XML
from xml.sax.saxutils import escape  # nosec B406

from nebenkostenfix import (abrechnungsart, anschrift as anschriften, betrkv,
                            heizung, pdf_stil, zeit)
from nebenkostenfix.geld import NULL
from nebenkostenfix.rechenkern import DIREKT_ZUGEWIESEN, euro_text

#: Die Nummern des § 2 BetrKV, die unter die HeizkostenV fallen -- aus dem
#: Kern, nicht aus einer eigenen Liste.
HEIZKOSTENNUMMERN = frozenset(heizung.BETRKV_NR.values())


def pruefe_heizkostennummern(rubriken=None) -> None:
    """Sind die Heizkostennummern genau die Energie-Nummern der Rubriken?

    ``ist_heizkosten`` fragt ``rubrik(posten) == 'Energie'``. Das stimmt
    nur, solange beide Listen dieselben Nummern nennen; laufen sie
    auseinander, soll das beim Import auffallen und nicht als Widerspruch
    zwischen Übersichtsblatt und Aufstellung im PDF.
    """
    rubriken = betrkv.RUBRIKEN if rubriken is None else rubriken
    energie = frozenset(nr for nr, name in rubriken.items() if name == 'Energie')
    if energie != HEIZKOSTENNUMMERN:
        raise RuntimeError('HEIZKOSTENNUMMERN und die Rubrik Energie in '
                           'betrkv.RUBRIKEN nennen verschiedene Nummern.')


pruefe_heizkostennummern()

#: Der Schluessel der Heizkostenzeile. Die HeizkostenV schreibt die
#: Aufteilung in Grund- und Verbrauchskosten vor (§ 7 Abs. 1, § 8); welcher
#: Anteil wie verteilt wurde, steht im Heizabschnitt des Detailteils.
SCHLUESSEL_HEIZKOSTEN = 'Verbrauch und Fläche (HeizkostenV)'

#: Wo kein Schluessel greift, weil der Betrag nicht aus einer Quote kommt.
OHNE_ANTEIL = '—'

#: Arten, bei denen ein Prozentsatz nichts erklaert: Der Betrag kommt vom
#: eigenen Zaehler, nicht aus einem Anteil an einer Masse.
OHNE_QUOTE = frozenset({'direkt'})

#: Die Spaltenbreiten in pt, gemessen an den laengsten Werten bei 8,5 pt
#: plus 16 pt Polsterung: „Verbrauch und Fläche (HeizkostenV)" braucht 155,
#: „100,0 %" 47, ein fünfstelliger Betrag 61. Vorher brach der Anteil bei
#: 100 % um und der Heizkostenschlüssel in jeder Zeile (Review 0.17.0).
SPALTEN = (118, 76, 156, 48, 72)

#: So viele Zeilen der Tabelle bleiben bei den Summen, wenn die Seite
#: umbricht -- eine Summe ohne eine Zeile darueber hat keine Rechnung.
ZEILEN_BEI_DEN_SUMMEN = 2


class UebersichtFehler(ValueError):
    """Übersichtsblatt und Detailteil nennen verschiedene Summen."""


def katalognummer(kategorie) -> int:
    """Die BetrKV-Nummer der Kostenart, wie sie im Bestand steht.

    Der Name verrät sie nicht verlässlich: Eine „Nahwärme" mit Nr. 4 hielt
    ``zuordnung`` für Nr. 17 (Review 0.17.0). Ohne
    Anwendungskontext oder für einen Namen, den es nicht mehr gibt (alte
    Fassung), bleibt die Vermutung aus dem Namen.

    Öffentlich, weil das Übersichtsblatt (``ist_heizkosten``) und die
    Aufstellung der Kosten (``PDFGenerator.generate``) dieselbe Nummer
    brauchen: Zwei Quellen ließen dieselbe Kostenart im selben PDF unter
    zwei Rubriken stehen (R-DOC-04).
    """
    try:
        from nebenkostenfix.models import CostCategory
        zeile = CostCategory.query.filter_by(name=kategorie).first()
    except RuntimeError:  # kein Anwendungskontext
        zeile = None
    return zeile.betrkv_nr if zeile else betrkv.zuordnung(kategorie)


def ist_direkt_zugewiesen(posten: dict) -> bool:
    """Ist die Rechnung der Wohnung direkt zugewiesen statt gezählt?"""
    return (posten.get('description') or '').startswith(DIREKT_ZUGEWIESEN)


def _aus_der_ablesung(posten: dict) -> bool:
    """Kommt der Betrag aus einem Zähler statt aus einem Anteil?

    Eine direkt zugewiesene Rechnung ohne Zählerteilung trägt die ganze
    verteilte Masse: Dort sagen Gesamtkosten und 100 % etwas.
    """
    if posten.get('billing_type') not in OHNE_QUOTE:
        return False
    return not (ist_direkt_zugewiesen(posten)
                and posten['tenant_cost'] == posten.get('prorated_amount'))


def rubrik(posten: dict) -> str:
    """Die Rubrik der Aufstellung, in die diese Position gehört.

    Die eine Entscheidung für das ganze PDF (R-DOC-04): Das Übersichtsblatt
    (``ist_heizkosten``) und die Aufstellung der Kosten
    (``PDFGenerator.generate``) fragen beide hier. Zwei Wege, weil es zwei
    Fälle gibt: Eine Zeile, die der Kern über eine Heizungsanlage gerechnet
    hat, trägt ``billing_type == 'heizkosten'`` -- sie ist Energie, was
    immer ihr Name vermuten lässt. Sonst entscheidet die gespeicherte
    Nummer der Kostenart.
    """
    if posten.get('billing_type') == 'heizkosten':
        return 'Energie'
    return betrkv.rubrik(katalognummer(posten.get('category')))


def ist_heizkosten(posten: dict) -> bool:
    """Fällt diese Position unter die HeizkostenV?

    Eine Zeile, die der Kern über eine Heizungsanlage gerechnet hat, trägt
    ``billing_type == 'heizkosten'``. Eine Heizkostenrechnung **ohne**
    zugeordnete Anlage rechnet der Kern nach Fläche (die Warnung
    W-HEIZKOSTEN-OHNE-ZUORDNUNG sagt das); sie bleibt trotzdem eine
    Heizkostenposition, und die Nummer verrät es. Beides entscheidet
    ``rubrik``; Heizkosten sind genau die Rubrik Energie, weil
    ``HEIZKOSTENNUMMERN`` die Energie-Nummern der Rubriken sind (die
    Prüfung oben im Modul hält das fest).
    """
    return rubrik(posten) == 'Energie'


def schluessel_text(posten: dict) -> str:
    """Der Verteilerschlüssel im Klartext, in den Worten der Anwendung."""
    art = posten.get('billing_type')
    if art == 'heizkosten':
        return SCHLUESSEL_HEIZKOSTEN
    if ist_direkt_zugewiesen(posten):
        return DIREKT_ZUGEWIESEN
    return abrechnungsart.ARTEN.get(art, OHNE_ANTEIL)


def anteil_text(posten: dict) -> str:
    """Der Anteil des Mieters an der verteilten Masse, in Prozent.

    Gerechnet wird gegen ``prorated_amount`` -- die Masse, die nach der
    Zeitabgrenzung tatsächlich verteilt wurde. Gegen den Rechnungsbetrag
    zu rechnen ergäbe bei einem unterjährigen Zeitraum eine Quote, mit der
    die Zeile auf dem Blatt nicht mehr aufgeht.

    ``—`` steht, wo ein Prozentsatz nichts erklärt: beim eigenen Zähler
    und wo keine Masse da ist, durch die man teilen könnte.
    """
    if _aus_der_ablesung(posten):
        return OHNE_ANTEIL
    masse = posten.get('prorated_amount')
    if not masse:
        return OHNE_ANTEIL
    quote = Decimal(posten['tenant_cost']) / Decimal(masse) * 100
    return f"{quote.quantize(Decimal('0.1'))} %".replace('.', ',')


def gesamtkosten(posten: dict):
    """Die Masse, die bei dieser Position verteilt wurde -- oder nichts.

    Bei einem eigenen Zähler gibt es **keine** verteilte Masse: Der Betrag
    kommt aus der Ablesung. ``prorated_amount`` trägt dort trotzdem den
    linear auf die Tage gerechneten Rechnungsanteil, und **genau diese
    Zahl darf nicht auf das Blatt**: Ein Zähler verbraucht nicht linear
    über das Jahr, und eine Gesamtsumme neben einem Zählerbetrag liest
    sich wie eine Quote, die niemand gerechnet hat. Die Belegliste hat
    dieselbe Zahl aus demselben Grund nie gezeigt
    (``tests/test_praxisbestand.py``).
    """
    if _aus_der_ablesung(posten):
        return None
    return posten.get('prorated_amount')


def uebersicht(posten: list[dict], *, vorauszahlungen=NULL) -> dict:
    """Die Zeilen und Summen des Übersichtsblatts.

    Reine Rechnung, ohne Satz: So lässt sich die Summenprobe prüfen, ohne
    ein PDF zu erzeugen. Die Beträge sind **nicht nachgerechnet**, sondern
    genau die der Posten, die auch der Detailteil zeigt.

    Zeilen mit 0,00 € bleiben stehen (Entscheidung zur Vorlage): Für
    den Mieter ist „geprüft, trifft mich nicht" eine Information, eine
    fehlende Zeile ist keine. Die Übersicht wirft keinen Posten weg; welche
    Posten es gibt, entscheidet ``rechne``. Ein positiver Anteil unter einem
    halben Cent kommt dort als Posten an und steht hier als 0,00 €; ein
    Gutschriftanteil, der auf 0,00 € rundet, kommt gar nicht erst an.
    """
    zeilen = []
    betriebskosten = NULL
    heizkosten = NULL
    for eintrag in posten:
        kosten = eintrag['tenant_cost']
        heiz = ist_heizkosten(eintrag)
        zeilen.append({
            'position': eintrag['category'],
            'gesamtkosten': gesamtkosten(eintrag),
            'schluessel': schluessel_text(eintrag),
            'anteil': anteil_text(eintrag),
            'kosten': kosten,
            'ist_heizkosten': heiz,
        })
        if heiz:
            heizkosten += kosten
        else:
            betriebskosten += kosten

    nebenkosten = betriebskosten + heizkosten
    return {
        'zeilen': zeilen,
        'betriebskosten': betriebskosten,
        'heizkosten': heizkosten,
        'nebenkosten': nebenkosten,
        'vorauszahlungen': vorauszahlungen,
        'saldo': nebenkosten - vorauszahlungen,
    }


def pruefe_summe(stand: dict, gesamtsumme) -> None:
    """Bricht ab, wenn die Übersicht etwas anderes sagt als die Abrechnung.

    Das ist keine Vorsicht, sondern der Zweck des Blattes: Ein Deckblatt,
    das dem Detailteil widerspricht, ist ein falsches Dokument. Lieber
    kein PDF als zwei Zahlen für dieselbe Forderung.
    """
    if stand['nebenkosten'] != gesamtsumme:
        raise UebersichtFehler(
            'Das Übersichtsblatt kommt auf '
            f'{euro_text(stand["nebenkosten"])}, die Abrechnung auf '
            f'{euro_text(gesamtsumme)}. Die Abrechnung wurde nicht '
            'erstellt, weil ein Blatt dem anderen widersprechen würde.')


# --- Der Satz -----------------------------------------------------------
#
# Alle Werte kommen aus `pdf_stil`; hier steht nur die Anordnung. Die
# Vorlage aus Issue #35 setzt die Summen **rechtsbuendig** unter die
# Betragsspalte statt ueber die ganze Breite -- so stehen sie dort, wo das
# Auge sie sucht, und die Tabelle bleibt eine Tabelle.


def _tag(iso: str) -> str:
    """Ein ISO-Datum in der Schreibweise des Dokuments."""
    return datetime.fromisoformat(iso).strftime('%d.%m.%Y')


def build_uebersicht_elements(
    posten: list[dict],
    *,
    gesamtsumme,
    vorauszahlungen=NULL,
    property_name: str = '',
    apartment_name: str = '',
    tenant_name: str = '',
    start_date: str = '',
    end_date: str = '',
    vermieter_name: str = '',
    vermieter_anschrift: str | None = None,
    mieter_anschrift: str | None = None,
    aufstellung_folgt: bool = True,
) -> list:
    """Das Uebersichtsblatt als Liste von Flowables, mit Seitenumbruch.

    ``mieter_anschrift`` ist die Anschrift, an die diese Abrechnung geht --
    die Auswahl zwischen Wohnung und Zustelladresse hat
    ``anschrift.fuer_zustellung`` schon getroffen (Phase 58).

    ``aufstellung_folgt`` sagt, ob die Aufstellung der Kosten hinter dem
    Blatt steht (Standard). Steht sie im gewählten Aufbau davor, verweist
    die Fußnote auf sie statt auf „die folgenden Seiten“.
    """
    stand = uebersicht(posten, vorauszahlungen=vorauszahlungen)
    pruefe_summe(stand, gesamtsumme)

    s = pdf_stil.STIL
    saetze = pdf_stil.stile(s)
    jahr = datetime.fromisoformat(end_date).strftime('%Y') if end_date else ''

    # Der Rhythmus des Blattes: Titel, Luft, Kopfdaten, viel Luft,
    # Mieterdaten, viel Luft, Tabelle. Vorher klebte alles am Titel
    # (Befund: „die Überschrift ist viel zu nah an dem darunter").
    elemente = [Paragraph(f'Nebenkostenabrechnung {jahr}'.strip(), saetze['Titel']),
                Spacer(1, pdf_stil.L)]

    zeitraum = f"{_tag(start_date)} bis {_tag(end_date)}" \
        if start_date and end_date else ''
    kopfdaten = pdf_stil.kopfdaten([
        ('Objekt', property_name),
        ('Wohnung', apartment_name),
        ('Vermieter', vermieter_name),
        ('Anschrift des Vermieters', anschriften.saeubern(vermieter_anschrift)),
        ('Erstellt am', zeit.als_ortszeit(zeit.jetzt_utc(), '%d.%m.%Y')),
    ], s, saetze)
    if kopfdaten is not None:
        elemente += [kopfdaten, Spacer(1, pdf_stil.XXL)]

    # Die Mieterdaten als eigener Block -- so steht in der Vorlage, wen die
    # Abrechnung betrifft, bevor die Zahlen kommen.
    elemente.append(Paragraph('Mieterdaten', saetze['Zwischentitel']))
    elemente.append(Spacer(1, pdf_stil.M))
    mieterdaten = pdf_stil.kopfdaten([
        ('Mieter', tenant_name),
        ('Anschrift des Mieters', anschriften.saeubern(mieter_anschrift)),
        ('Abrechnungszeitraum', zeitraum),
        ('Geleistete Vorauszahlungen', pdf_stil.geld(stand['vorauszahlungen'])),
    ], s, saetze)
    if mieterdaten is not None:
        elemente += [mieterdaten, Spacer(1, pdf_stil.XXL)]

    # --- Die Tabelle ---
    daten = [[
        Paragraph('Kostenposition', saetze['Kopf']),
        Paragraph('Gesamtkosten<br/>(Zeitraum)', saetze['KopfRechts']),
        Paragraph('Verteilerschlüssel', saetze['Kopf']),
        Paragraph('Anteil', saetze['KopfRechts']),
        Paragraph('Kosten Mieter', saetze['KopfRechts']),
    ]]
    for zeile in stand['zeilen']:
        daten.append([
            Paragraph(escape(zeile['position']), saetze['Zelle']),
            Paragraph(pdf_stil.geld(zeile['gesamtkosten'])
                      if zeile['gesamtkosten'] is not None else OHNE_ANTEIL,
                      saetze['ZelleRechts']),
            Paragraph(escape(zeile['schluessel']), saetze['Zelle']),
            Paragraph(zeile['anteil'], saetze['ZelleRechts']),
            Paragraph(pdf_stil.geld(zeile['kosten']), saetze['ZelleFettRechts']),
        ])
    breiten = list(SPALTEN)
    # Die Tabelle darf über die Seite laufen, nur ihre letzten Zeilen
    # bleiben bei den Summen (unten). Alles in ein ``KeepTogether`` zu
    # stecken schob ab zehn Positionen die ganze Tabelle auf die nächste
    # Seite, und das Blatt trug nur noch die Kopfdaten (Review 0.17.0).
    rumpf, schluss = daten[:-ZEILEN_BEI_DEN_SUMMEN], daten[-ZEILEN_BEI_DEN_SUMMEN:]
    if len(rumpf) < 2:
        rumpf, schluss = daten, []
    tabelle = Table(rumpf, colWidths=breiten, repeatRows=1)
    tabelle.setStyle(TableStyle(pdf_stil.tabellenstil(s, len(rumpf))))

    # --- Die Summen, rechtsbuendig unter der Betragsspalte ---
    saldo = stand['saldo']
    # NK-249 gilt weiter: Das Ergebnis steht **einmal** mit seinen Worten,
    # auf Blatt 1. Hier schliesst „Saldo" die Rechnung ab.
    bezeichnung = ('Saldo (Nachzahlung)' if saldo > 0
                   else 'Saldo (Guthaben)' if saldo < 0 else 'Saldo (ausgeglichen)')
    farbe = (s.nachzahlung if saldo > 0 else s.guthaben if saldo < 0 else None)
    summen = pdf_stil.summenblock([
        ('Betriebskosten gesamt', pdf_stil.geld(stand['betriebskosten']), False, None),
        ('Heizkosten gesamt (HeizkostenV)', pdf_stil.geld(stand['heizkosten']),
         False, None),
        ('Nebenkosten gesamt', pdf_stil.geld(stand['nebenkosten']), True, None),
        ('Vorauszahlungen', '- ' + pdf_stil.geld(stand['vorauszahlungen']),
         False, None),
        (bezeichnung, pdf_stil.geld(abs(saldo)), True, farbe),
    ], s, saetze, breite=296)

    # Die letzten Zeilen, die Summen und die Fussnote gehoeren zusammen:
    # Ein Summenblock allein auf der naechsten Seite ist von seiner Rechnung
    # abgeschnitten, eine Fussnote allein erklaert nichts.
    zusammen = []
    if schluss:
        # Ohne Kopf, die Streifen laufen weiter, als waere es eine Tabelle.
        rest = Table(schluss, colWidths=breiten)
        rest.setStyle(TableStyle(pdf_stil.tabellenstil(
            s, len(schluss), kopfzeilen=0, zebra_ab=1 if len(rumpf) % 2 else 2)))
        zusammen.append(rest)
    elemente.append(tabelle)
    wo = ('auf den folgenden Seiten' if aufstellung_folgt
          else 'in der Aufstellung der Kosten')
    elemente.append(KeepTogether(zusammen + [
        Spacer(1, pdf_stil.L), summen, Spacer(1, pdf_stil.L),
        Paragraph(
            f'Wie sich jede Position errechnet, mit Rechenweg und Belegen, steht '
            f'{wo}. Bei Positionen mit eigenem Zähler bleiben '
            'Gesamtkosten und Anteil leer: Der Betrag kommt aus der Ablesung, '
            'nicht aus einem Anteil an einer Summe.', saetze['Fuss'])]))
    elemente.append(PageBreak())
    return elemente
