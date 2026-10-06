"""Der Verbrauchskasten im detaillierten PDF (Phase 12f, App-Analyse).

NK-208 (B1): Der Kasten zeigte als „Ablesung Anfang/Ende“ die Stuetzstellen
der Interpolation -- Staende vor und nach dem Zeitraum. Ende minus Anfang
war nicht der Eigenverbrauch, eine Zwischenablesung fehlte. Jetzt stehen
dort die Staende an den Grenzen des Zeitraums (abgelesen oder berechnet),
darunter die Ablesungen, aus denen sie kommen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nebenkostenfix import heizung
from nebenkostenfix.rechenkern import Stand, Zaehler, verbrauch_in
from tests.test_pdf_rechenweg import _erzeuge, _geklebt, unkomprimiert  # noqa: F401


def zaehler(staende):
    return Zaehler(id=1, nummer='WZ-7', kategorie_id=2, kategorie_name='Wasser',
                   ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                   staende=tuple(staende))


def zaehlerzeile(tm) -> dict:
    return {
        'category': 'Wasserversorgung',
        'period': '01.01.2024 - 31.12.2024',
        'description': 'Eigenverbrauch',
        'tenant_cost': Decimal('100.00'),
        'billing_type': 'verbrauch',
        'sub_items': [{'type': 'eigen', 'description': 'Eigenverbrauch',
                       'cost': Decimal('100.00')}],
        'meter_details': {
            'unit': 'm³',
            'tenant_meter': tm,
            'main_meter': None,
            'tenant_consumption': round(tm['consumption'], 1),
        },
    }


def kasten(tm) -> str:
    return _geklebt(_erzeuge([zaehlerzeile(tm)], detailliert=True))


def test_stichtagswerte_statt_stuetzstellen(unkomprimiert):
    tm = verbrauch_in(zaehler([Stand(date(2023, 12, 1), 0.0),
                               Stand(date(2025, 2, 1), 428.0)]),
                      date(2024, 1, 1), date(2025, 1, 1))
    text = kasten(tm)
    assert 'ZählerstandBeginn01.01.2024(berechnet):31,000m³' in text
    assert 'ZählerstandEnde31.12.2024(berechnet):397,000m³' in text
    assert 'Eigenverbrauch(Ende-Beginn):366,000m³' in text
    assert 'ZugrundeliegendeAblesungen:01.12.2023:0,000·01.02.2025:428,000' in text
    assert 'AblesungAnfang' not in text


def test_abgelesene_grenze_und_zwischenablesung(unkomprimiert):
    tm = verbrauch_in(zaehler([
        Stand(date(2024, 1, 1), 10.0),
        Stand(date(2024, 7, 1), 190.0, art=heizung.ZWISCHENABLESUNG),
        Stand(date(2025, 1, 1), 380.5),
    ]), date(2024, 1, 1), date(2025, 1, 1))
    text = kasten(tm)
    assert 'ZählerstandBeginn01.01.2024(abgelesen):10,000m³' in text
    assert 'ZählerstandEnde31.12.2024(abgelesen):380,500m³' in text
    assert 'Eigenverbrauch(Ende-Beginn):370,500m³' in text
    assert '01.07.2024:190,000(Zwischenablesung)' in text


def test_ende_minus_beginn_geht_auch_gerundet_auf(unkomprimiert):
    """Drittelwerte: die angezeigten Zahlen ergeben trotzdem die Differenz."""
    tm = verbrauch_in(zaehler([Stand(date(2024, 1, 1), 0.0),
                               Stand(date(2024, 1, 4), 1.0)]),
                      date(2024, 1, 2), date(2024, 1, 3))
    text = kasten(tm)
    assert 'ZählerstandBeginn02.01.2024(berechnet):0,333m³' in text
    assert 'ZählerstandEnde02.01.2024(berechnet):0,666m³' in text
    assert 'Eigenverbrauch(Ende-Beginn):0,333m³' in text


def test_gespeicherte_abrechnung_ohne_stichtagswerte(unkomprimiert):
    """Alte Abrechnungen tragen nur r_start/r_end -- das Blatt bricht nicht."""
    tm = verbrauch_in(zaehler([Stand(date(2024, 1, 1), 5.0),
                               Stand(date(2025, 1, 1), 50.0)]),
                      date(2024, 1, 1), date(2025, 1, 1))
    for feld in ('stand_beginn', 'stand_ende', 'beginn_abgelesen',
                 'ende_abgelesen', 'basis_readings'):
        tm.pop(feld)
    text = kasten(tm)
    assert 'Ablesung:01.01.2024' in text
    assert 'Eigenverbrauch:45.0m³' in text


# --- NK-209 (B2): der Anteil am Allgemeinverbrauch -------------------------


def allgemeinzeile(**felder) -> dict:
    """Haus 100 m³, Wohnungen 60 m³, allgemein 40 m³; Anna 90 von 730 Personentagen."""
    tm = verbrauch_in(zaehler([Stand(date(2024, 1, 1), 0.0), Stand(date(2025, 1, 1), 30.0)]),
                      date(2024, 1, 1), date(2025, 1, 1))
    zeile = zaehlerzeile(tm)
    zeile['meter_details'].update({
        'main_meter': {'status': 'ok', 'is_interpolated': False},
        'main_consumption': 100.0, 'sum_sub_consumption': 60.0,
        'allgemein_consumption': 40.0, 'active_tenants': 2, **felder})
    return zeile


def test_anteil_nach_personentagen_statt_eins_durch_n(unkomprimiert):
    """Vorher: „Ihr Anteil am Allgemeinverbrauch (1/2): 20,0 m³“ -- gerechnet
    wurde aber mit 90/730, also 4,9 m³."""
    zeile = allgemeinzeile(allgemein_quote=round(90 / 730, 6), allgemein_anteil=4.9)
    text = _geklebt(_erzeuge([zeile], detailliert=True))
    assert 'IhrAnteilamAllgemeinverbrauch(12,33%):4,9m³' in text
    assert '(1/2)' not in text
    assert '20.0m³' not in text


def test_alte_abrechnung_ohne_quote_zeigt_keinen_falschen_anteil(unkomprimiert):
    text = _geklebt(_erzeuge([allgemeinzeile()], detailliert=True))
    assert 'Allgemeinverbrauch(Haus-Wohnungen):40.0m³' in text
    assert 'IhrAnteilamAllgemeinverbrauch' not in text


def test_ohne_eigenen_zaehler_richtig_gebeugt(unkomprimiert):
    """NK-215 (B8): der Kopf hiess „Ohne eigener Zähler“."""
    zeile = zaehlerzeile({'consumption': 0.0})
    zeile['meter_details']['tenant_meter'] = None
    text = _geklebt(_erzeuge([zeile], detailliert=True))
    assert 'OhneeigenenZähler(Wohnung1)' in text
    assert 'Ohneeigener' not in text


def test_abweichung_vom_stichtag_ist_ein_satz(unkomprimiert):
    """NK-218 (V1): vorher „■■ Abweichung: 31 Tage (Fenster: 428 Tage)“ --
    kein Stichtag, ein unerklärtes Fenster und ein Zeichen, das die Schrift
    nicht kennt."""
    tm = verbrauch_in(zaehler([Stand(date(2023, 12, 1), 0.0),
                               Stand(date(2025, 2, 1), 428.0)]),
                      date(2024, 1, 1), date(2025, 1, 1))
    text = kasten(tm)
    assert ('ZumStichtag01.01.2024liegtdienächsteAblesung31Tageentfernt.'
            'DerVerbrauchdieser31Tageistgeschätzt.') in text
    assert ('ZumStichtag31.12.2024liegtdienächsteAblesung32Tageentfernt.'
            'DerVerbrauchdieser32Tageistgeschätzt.') in text
    assert 'Fenster' not in text and 'Abweichung' not in text


def test_dualtarif_nennt_die_gewichtung_der_quote(unkomprimiert):
    """Review PR 26 (8): beim Dualtarif wiegt die Quote nach Kosten von HT und
    NT (NK-213); vorher stand sie da, als teile sie die Menge."""
    zeile = allgemeinzeile(allgemein_quote=0.25, allgemein_anteil=10.0,
                           preis_ht=Decimal('0.3'), preis_nt=Decimal('0.2'))
    text = _geklebt(_erzeuge([zeile], detailliert=True))
    assert 'IhrAnteilamAllgemeinverbrauch(25,00%,nachdenKostenvonHTundNTgewichtet):10,0' in text

    einheit = _geklebt(_erzeuge([allgemeinzeile(allgemein_quote=0.25, allgemein_anteil=10.0)],
                                detailliert=True))
    assert 'gewichtet' not in einheit


def test_hauptzaehler_nennt_seinen_zeitraum(unkomprimiert):
    """Review PR 26 (9): Haus und Allgemein gelten für die ganze Rechnung, der
    Mieter wohnte vielleicht nur einen Teil davon -- das Blatt sagte es nicht."""
    zeile = allgemeinzeile(allgemein_quote=0.25, allgemein_anteil=10.0)
    zeile['meter_details']['main_meter'].update(
        target_start_date='2024-01-01', target_end_date='2024-12-31')
    text = _geklebt(_erzeuge([zeile], detailliert=True))
    assert 'GesamtverbrauchHaus(Hauptzähler,01.01.2024bis31.12.2024):100.0m³' in text

    alt = _geklebt(_erzeuge([allgemeinzeile()], detailliert=True))
    assert 'GesamtverbrauchHaus(Hauptzähler):100.0m³' in alt
