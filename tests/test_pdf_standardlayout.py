"""Das Standardlayout der Abrechnungs-PDF bleibt, wie es ist (F1-01).

Vorbereitung eines PDF-Layout-Editors, Schritt 1: Bevor
``PDFGenerator.generate()`` in einzelne Blöcke zerlegt wird, hält dieser
Test fest, was heute auf dem Blatt steht: die Zahl der Seiten und die
Folge der Texte und Bilder je Seite. Lage, Abstände, Schrift und Farben
prüft er nicht -- eine verrutschte Zeile mit gleichem Text auf derselben
Seite fiele ihm nicht auf.

Geprüft wird je Fall und Fassung (einfach, ausführlich):

* die Zahl der Seiten,
* der Text jeder Seite in der Reihenfolge des Zeichnens, dazu ein Marker
  ``[Bild]`` an jeder Stelle, an der ein Bild steht (der GiroCode).

Die Welt ist erfunden (wie ``scripts/muster_0_7.py``) und deckt jeden
Block ab: Deckblatt mit Anschreiben oder Vorgabetext, Übersicht,
Kostenaufstellung mit Summenblock und Fußnoten (Tageskonvention,
Vorbehalt), Heizung mit CO2-Ausweis und Vermieteranteil, Ausweis nach
§ 35a EStG mit Lohnanteilen, Belegliste, Zahlungssatz mit GiroCode und
die Verbrauchsnachweise der ausführlichen Fassung.

Was nicht zum Layout gehört, wird festgehalten oder herausgefiltert:
Das Erstelldatum ist eingefroren, Software- und Regelstand im Fuß
werden durch Platzhalter ersetzt, Vermieterdaten, Logo und BetrKV-Nummer
kommen nicht aus einer Datenbank, die ein anderer Test gefüllt haben
könnte. Der Test hängt darum weder von der Reihenfolge noch vom Tag ab.

Die Referenz unter ``tests/referenz/pdf_standardlayout/`` ist mit dem
Stand v0.20.1 erzeugt. Neu schreiben (nur nach einer **gewollten**
Änderung am Blatt): die betroffene Datei löschen und den Test laufen
lassen. Er schreibt sie neu und schlägt einmal fehl, damit niemand eine
ungeprüfte Referenz für grün hält.
"""

from __future__ import annotations

import difflib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import reportlab.rl_config

from nebenkostenfix import betrkv, pdf_uebersicht, vermieter_logo, zeit
from nebenkostenfix.anschreiben import VORGABE, text_fuer
from nebenkostenfix.pdf_generator import PDFGenerator
from nebenkostenfix.rechenkern import (
    Beleg,
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    Zahlung,
    rechne,
)

REFERENZ = Path(__file__).resolve().parent / 'referenz' / 'pdf_standardlayout'
FAELLE = ('nachzahlung', 'guthaben')
FASSUNGEN = ('einfach', 'detailliert')

#: Der Tag, an dem das Blatt „erstellt“ wird -- eingefroren.
HEUTE = datetime(2025, 3, 14, 9, 30, tzinfo=timezone.utc)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)
EINZUG = date(2024, 3, 1)

WASSER = Kategorie(id=10, name='Wasserversorgung', braucht_zaehler=True)
GRUNDSTEUER = Kategorie(id=20, name='Grundsteuer', braucht_zaehler=False)
ABFALL = Kategorie(id=30, name='Müllbeseitigung', braucht_zaehler=False)
GARTEN = Kategorie(id=40, name='Gartenpflege', braucht_zaehler=False)
HAUSWART = Kategorie(id=50, name='Hauswart', braucht_zaehler=False)
WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True)

OBJEKT = 'Beispielweg 7'
WOHNUNG = 'EG links'
MIETERIN = 'Anna Mieterin'


class _Vermieter:
    """Die Zeile der Einstellungen, ohne Datenbank (erfunden)."""

    name = 'Erika Musterfrau'
    iban = 'DE02120300000000202051'
    art = 'privat'
    anschrift = 'Musterallee 1\n12345 Musterstadt'


def _rechnung(id, kategorie, betrag, nummer, anbieter, ausgestellt, datei,
              beginn=JAHR_BEGINN, ende=JAHR_ENDE, **kw):
    return Rechnung(
        id=id, kategorie=kategorie, betrag=Decimal(betrag),
        beginn=beginn, ende=ende, nummer=nummer, versorger_name=anbieter,
        rechnungsdatum=ausgestellt, beleg=Beleg(dateiname=datei, seiten='1'),
        **kw)


def _zaehler(id, nummer, kategorie, wohnung_id, bis, haupt=False, anlage=None):
    return Zaehler(
        id=id, nummer=nummer, kategorie_id=kategorie.id,
        kategorie_name=kategorie.name, ist_hauptzaehler=haupt,
        immobilie_id=1, wohnung_id=wohnung_id, heizungsanlage_id=anlage,
        staende=(Stand(datum=JAHR_BEGINN, wert=0.0),
                 Stand(datum=JAHR_ENDE, wert=bis)))


def vorgang(fall: str) -> Vorgang:
    """Zwei Wohnungen, sechs Kostenarten, eine Heizungsanlage.

    ``nachzahlung``: kleine Vorauszahlung, alle Rechnungen liegen vor.
    ``guthaben``: große Vorauszahlung, die Müllrechnung endet im
    September -- das bringt den Vorbehalt unter die Aufstellung.
    """
    links = Wohnung(id=1, name=WOHNUNG, qm=50.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=50.0)
    anna = Mieter(id=1, name=MIETERIN, einzug=EINZUG, auszug=None,
                  wohnung_id=1, haushaltsgroessen=((EINZUG, 2),))
    bert = Mieter(id=2, name='Bert Nachbar', einzug=JAHR_BEGINN,
                  auszug=None, wohnung_id=2)
    abfall_ende = JAHR_ENDE if fall == 'nachzahlung' else date(2024, 9, 30)
    rechnungen = (
        _rechnung(1, WASSER, '1200.00', 'W-2024-042', 'Stadtwerke Musterstadt',
                  date(2025, 1, 10), 'wasser_2024.pdf'),
        _rechnung(2, GRUNDSTEUER, '1800.00', 'GS-2024-008', 'Stadt Musterstadt',
                  date(2025, 2, 3), 'grundsteuer_2024.pdf'),
        _rechnung(3, ABFALL, '730.00', 'AB-2024-115', 'Abfallbetrieb Musterstadt',
                  date(2025, 1, 28), 'abfall_2024.pdf', ende=abfall_ende),
        _rechnung(4, GARTEN, '960.00', 'G-2024-031', 'Grünpflege Beispiel',
                  date(2025, 1, 20), 'garten_2024.pdf',
                  art_35a='haushaltsnah', lohnanteil=Decimal('720.00')),
        _rechnung(5, HAUSWART, '1440.00', 'HW-2024-012', 'Hausdienst Beispiel',
                  None, 'hauswart_2024.pdf',
                  art_35a='handwerker', lohnanteil=Decimal('1000.00')),
        _rechnung(6, WAERME, '10000.00', 'R-2024-777', 'Fernwärme Beispiel GmbH',
                  date(2025, 1, 15), 'fernwaerme_2024.pdf',
                  heizungsanlage_id=1, heizkostenart='brennstoff',
                  co2_kosten=Decimal('2000.00'), co2_emission_kg=Decimal('2200.00')),
    )
    zaehler = (
        _zaehler(1, 'WA-H', WASSER, None, 2000.0, haupt=True),
        _zaehler(2, 'WA-A', WASSER, 1, 1000.0),
        _zaehler(3, 'WA-B', WASSER, 2, 800.0),
        _zaehler(4, 'WM-1', WAERME, 1, 1200.0, anlage=1),
        _zaehler(5, 'WM-2', WAERME, 2, 800.0, anlage=1),
    )
    vorauszahlung = '1500.00' if fall == 'nachzahlung' else '9000.00'
    return Vorgang(
        mieter=anna,
        wohnung=links,
        immobilie_id=1,
        immobilie_name=OBJEKT,
        beginn=EINZUG,
        ende=JAHR_ENDE,
        wohnungen=(links, rechts),
        mieter_der_immobilie=(anna, bert),
        profile={WASSER.id: 'direkt', GRUNDSTEUER.id: 'qm', ABFALL.id: 'personen',
                 GARTEN.id: 'qm', HAUSWART.id: 'qm'},
        rechnungen=rechnungen,
        zaehler=zaehler,
        zahlungen=(Zahlung(datum=date(2024, 6, 1), betrag=Decimal(vorauszahlung)),),
        heizungsanlagen=(Heizungsanlage(id=1, name='Zentralheizung',
                                        verbrauchsanteil_prozent=70,
                                        sonderfall_70=False),),
        wasser_kategorie_id=WASSER.id,
    )


def _anschreiben(ergebnis: dict) -> str:
    anfang, ende = ergebnis['start_date'], ergebnis['end_date']
    return text_fuer(
        VORGABE, mieter_name=MIETERIN, wohnung_name=WOHNUNG, objekt_name=OBJEKT,
        zeitraum=(f'{anfang[8:10]}.{anfang[5:7]}.{anfang[:4]} bis '
                  f'{ende[8:10]}.{ende[5:7]}.{ende[:4]}'),
        gesamtsumme=ergebnis['total_amount'],
        vorauszahlungen=ergebnis['prepaid_amount'],
        saldo=ergebnis['balance'], vermieter_name=_Vermieter.name)


def erzeuge(fall: str, fassung: str) -> bytes:
    """Die PDF eines Falls in einer Fassung -- so, wie die Route sie baut."""
    ergebnis = rechne(vorgang(fall))
    generator = PDFGenerator(
        property_name=OBJEKT, apartment_name=WOHNUNG, tenant_name=MIETERIN,
        start_date=ergebnis['start_date'], end_date=ergebnis['end_date'],
        detailliert=fassung == 'detailliert',
        tenant_anrede='Liebe Frau Mieterin,',
        tenant_anschrift='Beispielweg 7\n12345 Musterstadt')
    return generator.generate(
        ergebnis['line_items'], ergebnis['total_amount'], ergebnis['prepaid_amount'],
        co2_ausweis=ergebnis['co2'], landlord_share=ergebnis['landlord_share'],
        # Der Fall mit Nachzahlung trägt das Anschreiben, der andere den
        # Vorgabetext des Deckblatts -- so sind beide Wege belegt.
        anschreiben=_anschreiben(ergebnis) if fall == 'nachzahlung' else None,
        vorbehalt=ergebnis['vorbehalt'], ausweis_35a=ergebnis['ausweis_35a'])


# --- Auslesen ------------------------------------------------------------

_OBJEKT = re.compile(rb'(\d+) 0 obj(.*?)endobj', re.S)
_STROM = re.compile(rb'stream\r?\n(.*?)\r?\nendstream', re.S)
_ZEICHEN = re.compile(r'\(((?:\\.|[^\\)])*)\)\s*Tj|/(\S+)\s+Do\b')
_FUSS = re.compile(r'^(Erstellt mit \S+) \S+ · Rechenstand der Regeln: \S+ · ')


def _entschluesselt(stueck: str) -> str:
    """Die Escapes eines PDF-Strings aufgelöst, die Bytes als WinAnsi gelesen."""
    roh = bytearray()
    i = 0
    while i < len(stueck):
        zeichen = stueck[i]
        if zeichen == '\\' and i + 1 < len(stueck):
            folge = stueck[i + 1]
            if folge in '01234567':
                j = i + 1
                while j < len(stueck) and j < i + 4 and stueck[j] in '01234567':
                    j += 1
                roh.append(int(stueck[i + 1:j], 8) & 0xFF)
                i = j
                continue
            roh.extend({'n': b'\n', 'r': b'\r', 't': b'\t', 'b': b'\b',
                        'f': b'\f'}.get(folge, folge.encode('latin-1')))
            i += 2
            continue
        roh.extend(zeichen.encode('latin-1'))
        i += 1
    return bytes(roh).decode('cp1252', 'backslashreplace')


def _normalisiert(zeile: str) -> str:
    """Erstelldatum, Software- und Regelstand als Platzhalter."""
    zeile = zeile.replace(zeit.als_ortszeit(HEUTE, '%d.%m.%Y'), '{HEUTE}')
    return _FUSS.sub(r'\1 {VERSION} · Rechenstand der Regeln: {REGELSTAND} · ', zeile)


def seiten(pdf: bytes) -> list[list[str]]:
    """Je Seite die gezeichneten Textstücke und Bilder, in Seitenreihenfolge.

    Die Seiten kommen aus ``/Kids`` des Seitenbaums, ihr Inhalt aus
    ``/Contents`` -- nicht aus jedem Strom der Datei, denn auch ein Bild
    ist ein Strom und kann Klammern enthalten.
    """
    objekte = {int(nr): inhalt for nr, inhalt in _OBJEKT.findall(pdf)}
    baum = next(o for o in objekte.values() if re.search(rb'/Type\s*/Pages\b', o))
    kinder = re.search(rb'/Kids\s*\[([^\]]*)\]', baum).group(1)
    ergebnis = []
    for nr in re.findall(rb'(\d+) 0 R', kinder):
        seite = objekte[int(nr)]
        inhalt = int(re.search(rb'/Contents\s+(\d+) 0 R', seite).group(1))
        strom = _STROM.search(objekte[inhalt]).group(1).decode('latin-1')
        ergebnis.append([
            _normalisiert(_entschluesselt(text)) if bild == '' else '[Bild]'
            for text, bild in _ZEICHEN.findall(strom)])
    return ergebnis


# --- Test ----------------------------------------------------------------


@pytest.fixture
def feste_umgebung(monkeypatch):
    """Alles, was nicht zur Welt gehört, festgehalten."""
    from nebenkostenfix.models import Vermieterdaten

    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)
    monkeypatch.setattr(zeit, 'jetzt_utc', lambda: HEUTE)
    monkeypatch.setattr(Vermieterdaten, 'einziger', classmethod(lambda cls: _Vermieter()))
    monkeypatch.setattr(vermieter_logo, 'pfad', lambda ordner=None: None)
    # Die Kostenart kennt der Test nur dem Namen nach -- wie ohne Datenbank.
    monkeypatch.setattr(pdf_uebersicht, 'katalognummer', betrkv.zuordnung)
    monkeypatch.delenv('VERMIETER_NAME', raising=False)
    monkeypatch.delenv('VERMIETER_IBAN', raising=False)


def _als_zeilen(stand: dict) -> list[str]:
    return [f'--- Seite {n} ---' if z is None else z
            for n, seite in enumerate(stand['text'], 1) for z in [None, *seite]]


@pytest.mark.parametrize('fassung', FASSUNGEN)
@pytest.mark.parametrize('fall', FAELLE)
def test_das_blatt_gleicht_der_referenz(feste_umgebung, fall, fassung):
    gelesen = seiten(erzeuge(fall, fassung))
    stand = {'seiten': len(gelesen), 'text': gelesen}
    name = f'{fall}_{fassung}.json'

    weg = REFERENZ / name
    if not weg.exists():
        weg.parent.mkdir(parents=True, exist_ok=True)
        weg.write_text(json.dumps(stand, ensure_ascii=False, indent=1) + '\n',
                       encoding='utf-8')
        pytest.fail(f'Referenz fehlte und ist jetzt geschrieben: {weg} -- '
                    'durchsehen und einchecken.')

    referenz = json.loads(weg.read_text(encoding='utf-8'))
    if stand != referenz:
        unterschied = '\n'.join(difflib.unified_diff(
            _als_zeilen(referenz), _als_zeilen(stand), 'Referenz', 'jetzt', lineterm=''))
        pytest.fail(f'{name}: {referenz["seiten"]} Seiten erwartet, '
                    f'{stand["seiten"]} erzeugt.\n{unterschied}')


def test_die_welt_belegt_jeden_block(feste_umgebung):
    """Die Referenz taugt nur, wenn jeder Block wirklich auf dem Blatt steht."""
    def text(fall, fassung):
        return ' '.join(' '.join(s) for s in seiten(erzeuge(fall, fassung)))

    nach = text('nachzahlung', 'detailliert')
    for teil in ('Ihr Anteil an den Nebenkosten', 'Aufstellung der Kosten',
                 'CO2', '35a', 'Bitte überweisen', 'Verwendungszweck',
                 'Detaillierte Verbrauchsnachweise', '{HEUTE}', '{VERSION}'):
        assert teil in nach, teil
    assert '[Bild]' in nach, 'kein GiroCode auf dem Blatt'

    gut = text('guthaben', 'einfach')
    assert 'Guthaben' in gut and 'Vorbehalt' in gut
    assert '[Bild]' not in gut and 'Bitte überweisen' not in gut
    assert 'Detaillierte Verbrauchsnachweise' not in gut
