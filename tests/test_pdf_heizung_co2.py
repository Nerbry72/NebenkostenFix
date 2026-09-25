"""Heizkosten- und CO2-Abschnitt im PDF (NK-060, R-HK-01/R-CO2-02).

Drei Dinge standen bisher auf keinem Blatt, obwohl der Kern sie trägt:

* der Grund hinter den Prozenten der Heizzeile -- der Sonderfall 70 %
  (§ 7 Abs. 1 Satz 2 HeizkostenV), der Fehlgrund beim nicht erfassten
  Verbrauch und der Weg der Warmwassertrennung (R-HK-03);
* der Ausweis des § 7 CO2KostAufG: Emission, kg/m²a, Stufe, Anteile in
  Prozent und Euro, Herkunft der Emissionsdaten (R-CO2-02);
* der Vermieteranteil (R-NUM-05): die Positionen, die nicht auf die
  Mieter umgelegt wurden.

Der Abschnitt steht in beiden Fassungen -- der Vermieter sendet nur eine
(dieselbe Regel wie bei der Belegliste, NK-058). Fehlt der CO2-Ausweis,
trägt der Abschnitt die Kennung ``E-CO2-AUSWEIS-FEHLT`` statt der Zahlen:
nichts wird erfunden (D-54), und die 3-%-Kürzung wird nicht doppelt
gewarnt (D-53). Das Auslesen des PDF arbeitet wie in
``test_pdf_rechenweg.py``: Seiten unkomprimiert, Textströme gelesen,
Escapes aufgelöst, Leerraum gestrichen.

Die Welt ist dieselbe wie in ``test_co2_aufteilung.py``: zwei Wohnungen
zu 50 qm, eine Anlage, Satz 70, eine Rechnung über 10.000 Euro mit
CO2-Kosten 2.000 Euro und Emission 2.200 kg -- 22,0 kg/m²a, Stufe 4,
70 % Mieter, 30 % Vermieter. Der Mieteranteil dieses Mietverhältnisses
ist 798,00 €, der Vermieteranteil 600,00 €.
"""

from __future__ import annotations

import re
import zlib
from datetime import date
from decimal import Decimal

import pytest
import reportlab.rl_config

from pdf_generator import PDFGenerator
from rechenkern import (
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    rechne,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)

WASSER = Kategorie(id=10, name='Wasserversorgung', braucht_zaehler=False)
WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True)


# --- Die Welt: dieselbe wie in test_co2_aufteilung ---------------------------


def welt(rechnungen=(), zaehler=(), anlagen=()):
    """Zwei Wohnungen zu 50 qm; mein Mieter wohnt in der linken."""
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    andere = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = Mieter(id=1, name='Anna Mieterin', einzug=JAHR_BEGINN, auszug=None,
                 wohnung_id=1)
    nachbar = Mieter(id=2, name='Bert Nachbar', einzug=JAHR_BEGINN,
                     auszug=None, wohnung_id=2)
    return Vorgang(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(meine, andere),
        mieter_der_immobilie=(ich, nachbar),
        profile={},
        rechnungen=tuple(rechnungen),
        zaehler=tuple(zaehler),
        heizungsanlagen=tuple(anlagen),
    )


def heizanlage(sonderfall=False):
    return Heizungsanlage(
        id=1, name='Zentralheizung', verbrauchsanteil_prozent=70,
        sonderfall_70=sonderfall)


def heizrechnung(co2_kosten='2000.00', co2_emission='2200.00'):
    return Rechnung(
        id=1,
        kategorie=WAERME,
        betrag=Decimal('10000.00'),
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        nummer='R-2024-777',
        rechnungsdatum=date(2025, 1, 15),
        heizungsanlage_id=1,
        heizkostenart='brennstoff',
        co2_kosten=Decimal(co2_kosten) if co2_kosten is not None else None,
        co2_emission_kg=(
            Decimal(co2_emission) if co2_emission is not None else None),
    )


def waermezaehler(zaehler_id, wohnung_id, verbraucht):
    return Zaehler(
        id=zaehler_id,
        nummer=f'W-{zaehler_id}',
        kategorie_id=WAERME.id,
        kategorie_name='Waerme',
        ist_hauptzaehler=False,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=(Stand(datum=JAHR_BEGINN, wert=0.0),
                 Stand(datum=date(2025, 1, 1), wert=verbraucht)),
        heizungsanlage_id=1,
    )


def co2_welt(co2_kosten='2000.00', co2_emission='2200.00', sonderfall=False):
    """Das ganze Haus: Anlage, Rechnung mit CO2-Angaben, zwei Zähler."""
    return welt(
        rechnungen=(heizrechnung(co2_kosten, co2_emission),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        anlagen=(heizanlage(sonderfall),),
    )


# --- Das PDF -----------------------------------------------------------------


@pytest.fixture
def unkomprimiert(monkeypatch):
    """Seiten ohne Kompression, damit der Text lesbar im Strom steht."""
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)


def _entschluesselt(stueck: str) -> str:
    """Löst die Escapes eines PDF-Textstücks auf (Umlaute als Oktal).

    WinAnsi schreibt das Eurozeichen als \200; die Rohform ist kein
    Zeichen, das ein Test vergleichen kann -- darum zurück nach €.
    """
    ausgabe = []
    i = 0
    while i < len(stueck):
        zeichen = stueck[i]
        if zeichen == '\\' and i + 1 < len(stueck):
            if stueck[i + 1] in '01234567':
                ziffern = ''
                j = i + 1
                while j < len(stueck) and len(ziffern) < 3 \
                        and stueck[j] in '01234567':
                    ziffern += stueck[j]
                    j += 1
                ausgabe.append(chr(int(ziffern, 8)))
                i = j
                continue
            ausgabe.append(stueck[i + 1])
            i += 2
            continue
        ausgabe.append(zeichen)
        i += 1
    # WinAnsi 0x80 ist das Eurozeichen -- es kommt als Oktal \200 durch;
    # 0x97 ist der Gedankenstrich (\227).
    return ''.join(ausgabe).replace(chr(0x80), '€').replace(chr(0x97), '—')


def _geklebt(pdf: bytes) -> str:
    """Der Text ohne Zeilenumbrüche, in der Reihenfolge des Zeichnens."""
    stuecke = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            pass
        stuecke.extend(_entschluesselt(m) for m in re.findall(
            r'\(((?:\\.|[^\\)])*)\)', roh.decode('latin-1', 'replace')))
    return re.sub(r'\s+', '', ''.join(stuecke))


def _erzeuge(ergebnis, detailliert=False) -> bytes:
    """Das Blatt aus einem echten Kern-Ergebnis -- wie die Route es baut."""
    erzeuger = PDFGenerator(
        property_name=ergebnis['property'],
        apartment_name=ergebnis['apartment'],
        tenant_name=ergebnis['tenant_name'],
        start_date=ergebnis['start_date'],
        end_date=ergebnis['end_date'],
        detailliert=detailliert,
    )
    return erzeuger.generate(
        ergebnis['line_items'],
        ergebnis['total_amount'],
        ergebnis['prepaid_amount'],
        co2_ausweis=ergebnis.get('co2'),
        landlord_share=ergebnis.get('landlord_share'),
    )


# --- Der Abschnitt: Verteilung, CO2-Ausweis, Vermieteranteil -----------------


@pytest.mark.parametrize('detailliert', [False, True], ids=['einfach', 'detailliert'])
def test_der_abschnitt_zeigt_verteilung_und_ausweis(unkomprimiert, detailliert):
    """Beide Fassungen tragen Verteilung und den Ausweis des § 7.

    2.200 kg auf 100 qm sind 22,0 kg/m²a -- Stufe 4, 70 % Mieter,
    30 % Vermieter. Von den 2.000 € CO2-Kosten trägt dieses
    Mietverhältnis 798 €, der Vermieter 600 €. Die Herkunft steht je
    Rechnung: R-2024-777 vom 15.01.2025, 2.200 kg, 2.000 €.
    """
    ergebnis = rechne(co2_welt())
    text = _geklebt(_erzeuge(ergebnis, detailliert))

    assert 'HeizkostenundCO2' in text
    assert ('Verteilungnach§7Abs.1HeizkostenV:70%nacherfasstem'
            'Verbrauch(1200,0von2000,0kWh),30%nachWohnfläche.') in text
    assert 'CO2-Ausweisnach§7CO2KostAufG' in text
    assert 'EmissiondesGebäudes:2200,0kgCO2imAbrechnungszeitraum—22,0kg/m²a.' \
        in text
    assert 'Einstufung:Stufe4—Mieteranteil70%,Vermieteranteil30%.' in text
    assert ('CO2-KostendesGebäudes:2000,00€—davon798,00€aufdieses'
            'Mietverhältnis;derVermieteranteilbeträgt600,00€.') in text
    assert ('HerkunftderEmissionsdaten:RechnungR-2024-777vom15.01.2025'
            '—2200,0kg,2000,00€.') in text


def test_der_vermieteranteil_steht_auf_dem_blatt(unkomprimiert):
    """R-NUM-05: was nicht auf die Mieter umgelegt wurde, steht da.

    Im CO2-Fall ist es der flache Anteil des § 6: 600 € als eigene
    Position, mit dem Satz, warum ihm keine Verteilmasse zugrunde liegt.
    """
    ergebnis = rechne(co2_welt())
    text = _geklebt(_erzeuge(ergebnis))

    assert 'Vermieteranteil(nichtaufdieMieterumgelegt)' in text
    assert ('CO2-Kosten(Zentralheizung)—VermieteranteilandenCO2-Kostennach'
            '§6CO2KostAufG(Stufe4:30%Vermieter,70%Mieter):600,00€.') in text
    assert 'InsgesamtbeimVermieter:600,00€(Leerstand0,00€,Eigennutzung0,00€).' \
        in text


def test_der_sonderfall_70_wird_begruendet(unkomprimiert):
    """Der Satz von 70 % ist zwingend formuliert -- der Abschnitt sagt es.

    § 7 Abs. 1 Satz 2 verlangt drei Voraussetzungen; die Anlage trägt
    den Sonderfall, der Abschnitt benennt die Vorschrift.
    """
    ergebnis = rechne(co2_welt(sonderfall=True))
    text = _geklebt(_erzeuge(ergebnis))

    assert ('DererhöhteVerbrauchsanteilvon70%beruhtauf§7Abs.1Satz2'
            'HeizkostenV(Sonderfall70%).') in text


def test_ohne_co2_angaben_traegt_der_abschnitt_die_kennung(unkomprimiert):
    """Fehlt der Ausweis, fehlt er ganz -- und der Abschnitt sagt es.

    Eine Rechnung ohne CO2-Angaben: keine Einstufung (D-54), keine
    Zahlen -- aber die Kennung ``E-CO2-AUSWEIS-FEHLT`` steht auf dem
    Blatt. Die 3-%-Kürzung wird nicht doppelt gewarnt (D-53).
    """
    ergebnis = rechne(co2_welt(co2_kosten=None, co2_emission=None))
    assert ergebnis['co2'] is None

    text = _geklebt(_erzeuge(ergebnis))

    assert 'E-CO2-AUSWEIS-FEHLT' in text
    assert 'Stufe' not in text
    assert '3%' not in text


def test_ohne_heizkosten_gibt_es_keinen_abschnitt(unkomprimiert):
    """Eine Abrechnung ohne Heizkosten braucht keinen Heizkostenabschnitt.

    Wasser allein: keine Heizzeile, kein CO2-Ausweis, keine
    Vermieterposition -- der Abschnitt bleibt ganz weg.
    """
    wasser = Rechnung(
        id=5, kategorie=WASSER, betrag=Decimal('1200.00'),
        beginn=JAHR_BEGINN, ende=JAHR_ENDE, nummer='R-W1')
    ergebnis = rechne(welt(rechnungen=(wasser,)))
    assert ergebnis['co2'] is None

    text = _geklebt(_erzeuge(ergebnis))

    assert 'HeizkostenundCO2' not in text
    assert 'Vermieteranteil(nichtaufdieMieterumgelegt)' not in text


def test_die_warmwasser_trennung_zeigt_ihren_weg(unkomprimiert):
    """R-HK-03: der Weg der Trennung steht auf dem Blatt, nicht nur das Ergebnis.

    Die Zeile kommt aus der Hand -- die Welt mit verbundener Anlage und
    Warmwasserzähler ist schwerer als der Satz, den der Abschnitt tragen
    soll: der Weg mit seiner Vorschrift und dem Anteil.
    """
    zeile = _heizzeile()
    zeile['heizung_details']['warmwasser_weg_text'] = (
        'mit Wärmezähler gemessen (§ 9 Abs. 2 Satz 1 HeizkostenV)')
    zeile['heizung_details']['warmwasser_anteil_prozent'] = Decimal('40.00')

    text = _geklebt(_erzeuge(_ergebnis_mit([zeile])))

    assert ('Warmwasserwurdegetrenntermittelt—mitWärmezählergemessen'
            '(§9Abs.2Satz1HeizkostenV),Anteil40,00%.') in text


def test_die_misslungene_trennung_nennt_ihren_grund(unkomprimiert):
    """Kann nicht getrennt werden, steht der Grund da -- statt eines Weges."""
    zeile = _heizzeile()
    zeile['heizung_details']['trennungsgrund'] = (
        'kein Weg zur Ermittlung der Wärmemenge angegeben')

    text = _geklebt(_erzeuge(_ergebnis_mit([zeile])))

    assert ('HeizungundWarmwasserwurdennichtgetrennt(keinWegzurErmittlung'
            'derWärmemengeangegeben).') in text


def test_nicht_erfasster_verbrauch_wird_begruendet(unkomprimiert):
    """Ganz nach Wohnfläche: der Fehlgrund steht im Abschnitt.

    Die Tabelle sagt nur „kein erfasster Verbrauch"; welcher Zähler
    fehlt oder wem Ablesungen fehlen, steht in ``fehlgrund`` -- der
    Abschnitt trägt ihn.
    """
    zeile = _heizzeile()
    zeile['heizung_details']['erfasst'] = False
    zeile['heizung_details']['fehlgrund'] = (
        'kein Zähler für die Wohnungen EG links')

    text = _geklebt(_erzeuge(_ergebnis_mit([zeile])))

    assert ('Verteilungnach§7Abs.1HeizkostenV:keinerfassterVerbrauch,'
            'dieKostengehenganznachWohnfläche.') in text
    assert 'Grund:keinZählerfürdieWohnungenEGlinks.' in text


# --- Helfer für die Zeilen aus der Hand --------------------------------------


def _heizzeile() -> dict:
    """Eine Heizzeile, wie der Kern sie liefert -- hier aus der Hand."""
    return {
        'category': 'Heizkosten (Zentralheizung)',
        'period': '01.01.2024 - 31.12.2024',
        'description': (
            'Heizkosten nach § 7 HeizkostenV: 70 % nach erfasstem '
            'Verbrauch, 30 % nach Wohnfläche'),
        'tenant_cost': Decimal('5700.00'),
        'invoice_days': 366,
        'overlap_days': 366,
        'billing_type': 'heizkosten',
        'invoice_total_amount': Decimal('10000.00'),
        'prorated_amount': Decimal('10000.00'),
        'sub_items': [],
        'rechenweg': ['10000,00 € Rechnungsbetrag'],
        'heizung_details': {
            'anlage_id': 1,
            'anlage': 'Zentralheizung',
            'zweck': 'heizung',
            'betrkv_nr': 4,
            'verbrauchsanteil_prozent': 70,
            'flaechenanteil_prozent': 30,
            'sonderfall_70': False,
            'erfasst': True,
            'tenant_consumption': 1200.0,
            'total_consumption': 2000.0,
            'unit': 'kWh',
            'tenant_sqm': 50.0,
            'total_sqm': 100.0,
            'warmwasser_weg': None,
            'warmwasser_weg_text': None,
            'warmwasser_anteil_prozent': None,
            'trennungsgrund': None,
            'co2': None,
            'rechnungen': [],
        },
    }


def _ergebnis_mit(zeilen: list[dict]) -> dict:
    """Ein minimales Ergebnis um die Zeilen herum, wie ``generate`` es liest."""
    return {
        'property': 'Hauptstrasse 1',
        'apartment': 'EG links',
        'tenant_name': 'Anna Mieterin',
        'start_date': JAHR_BEGINN.isoformat(),
        'end_date': JAHR_ENDE.isoformat(),
        'line_items': zeilen,
        'total_amount': Decimal('5700.00'),
        'prepaid_amount': Decimal('0.00'),
        'co2': None,
        'landlord_share': {
            'positions': [],
            'leerstand_amount': Decimal('0.00'),
            'eigennutzung_amount': Decimal('0.00'),
            'total_amount': Decimal('0.00'),
        },
    }
