"""NK-190: Rechnungen, wie sie im Bestand liegen.

Die Praxisprobe (NK-187) fand Rechnungen über den Jahreswechsel, doppelt
erfasste Tage, Lücken am Jahresende, alte Rechnungen aus Vorjahren und leere
Wohnungen (H4 bis H7, H12). Dazu F-128: der Vermieteranteil beim
Personenschlüssel, bei Wohnungsrechnungen und im Zählerzweig galt der ganzen
Rechnung, nicht dem Zeitraum der Abrechnung -- eine Abrechnung für 2025 wies
Leerstand aus 2024 aus. Alle Werte sind erfunden.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest

from nebenkostenfix.rechenkern import (
    Kategorie, Mieter, Rechnung, Stand, Vorgang, Wohnung, Zaehler, rechne)

B, E = date(2025, 1, 1), date(2025, 12, 31)
VERS = Kategorie(id=1, name='Versicherung', braucht_zaehler=False, betrkv_nr=13)
MUELL = Kategorie(id=2, name='Müllabfuhr', braucht_zaehler=False, betrkv_nr=8)
GARTEN = Kategorie(id=3, name='Gartenpflege', braucht_zaehler=False, betrkv_nr=10)
HAUSWART = Kategorie(id=4, name='Hauswart', braucht_zaehler=False, betrkv_nr=14)
WASSER = Kategorie(id=5, name='Frischwasser', braucht_zaehler=True, betrkv_nr=2)


def _vorgang(mieter, wohnungen, alle, rechnungen, profile, zaehler=(), beginn=B, ende=E):
    return Vorgang(mieter=mieter, wohnung=wohnungen[mieter.wohnung_id - 1], immobilie_id=1,
                   immobilie_name='Haus', beginn=max(beginn, mieter.einzug),
                   ende=min(ende, mieter.auszug or ende), wohnungen=wohnungen,
                   mieter_der_immobilie=alle, profile=profile, rechnungen=rechnungen,
                   zaehler=zaehler)


def _vermieter(ergebnis, invoice_id):
    return sum((Decimal(str(p['amount'])) for p in ergebnis['landlord_share']['positions']
                if p['invoice_id'] == invoice_id), Decimal(0))


# --- H4 bis H7, H12: die Lagen aus dem Bestand -----------------------------------------

@pytest.fixture
def haus():
    """W1 ganzjährig, W2 ab Juli, W3 leer; fünf Rechnungen wie im Bestand."""
    w = (Wohnung(1, 'W1', 50.0), Wohnung(2, 'W2', 50.0), Wohnung(3, 'W3', 100.0))
    m = (Mieter(1, 'Mieter 1', B, None, 1), Mieter(2, 'Mieter 2', date(2025, 7, 1), None, 2))
    r = (Rechnung(1, VERS, Decimal('365.00'), date(2024, 1, 1), date(2025, 1, 1)),
         Rechnung(2, VERS, Decimal('366.00'), B, date(2026, 1, 1)),
         Rechnung(3, MUELL, Decimal('359.00'), B, date(2025, 12, 25)),
         Rechnung(4, GARTEN, Decimal('60.00'), date(2021, 1, 1), date(2021, 12, 31)),
         Rechnung(5, MUELL, Decimal('100.00'), B, E, wohnung_id=3))
    profile = {1: 'qm', 2: 'qm', 3: 'qm'}
    return {mieter.id: rechne(_vorgang(mieter, w, m, r, profile)) for mieter in m}


def test_leerstand_traegt_der_vermieter(haus):
    """H4: W3 steht leer; ihr Teil der Müllabfuhr bleibt beim Vermieter."""
    zeile = next(z for z in haus[1]['line_items'] if z['invoice_id'] == 3)
    assert zeile['tenant_cost'] == Decimal('89.75')          # 50 von 200 qm
    assert _vermieter(haus[1], 3) == Decimal('224.75')        # W2 bis Juni, W3 ganz
    assert _vermieter(haus[1], 5) == Decimal('100.00')        # Rechnung nur für W3


def test_ueberlappung_wird_gemeldet(haus):
    """H5: zwei Versicherungsrechnungen teilen sich den 01.01.2025."""
    assert any('überschneiden sich am 01.01.2025' in w for w in map(str, haus[1]['warnings']))


def test_luecke_wird_gemeldet_und_nur_anteilig_umgelegt(haus):
    """H6: die Müllabfuhr endet am 25.12.; die sechs Tage danach fehlen."""
    assert any('fehlt 26.12.2025–31.12.2025' in w for w in map(str, haus[1]['warnings']))
    zeile = next(z for z in haus[1]['line_items'] if z['invoice_id'] == 3)
    assert zeile['prorated_amount'] == Decimal('359.00')


def test_alte_rechnung_bleibt_draussen(haus):
    """H12: eine Gartenrechnung von 2021 gehört in keine Abrechnung für 2025."""
    for ergebnis in haus.values():
        assert all(z['invoice_id'] != 4 for z in ergebnis['line_items'])
        assert _vermieter(ergebnis, 4) == 0


def test_zeitraum_der_rechnung_steht_in_der_zeile(haus):
    """H7: wer die Zeile liest, sieht, welchen Zeitraum die Rechnung hatte."""
    zeile = next(z for z in haus[1]['line_items'] if z['invoice_id'] == 1)
    assert zeile['period'] == '01.01.2024 - 01.01.2025'
    assert zeile['prorated_amount'] == Decimal('0.99')        # 1 von 366 Tagen


# --- F-128: der Vermieteranteil gilt dem Zeitraum der Abrechnung -----------------------

def _zwei_wohnungen():
    return (Wohnung(1, 'W1', 50.0), Wohnung(2, 'W2', 50.0)), (Mieter(1, 'Mieter 1', date(2020, 1, 1), None, 1),)


def test_personenschluessel_ueber_den_jahreswechsel():
    """31.10.2024–07.01.2025, 69 Tage, W2 leer: 7 Tage davon liegen in 2025.

    Vorher stand beim Vermieter die ganze leere Zeit, 69 von 138 Personentagen.
    """
    w, m = _zwei_wohnungen()
    r = (Rechnung(1, HAUSWART, Decimal('138.00'), date(2024, 10, 31), date(2025, 1, 7)),)
    ergebnis = rechne(_vorgang(m[0], w, m, r, {HAUSWART.id: 'personen'}))

    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('7.00')
    assert _vermieter(ergebnis, 1) == Decimal('7.00')
    einheit = ergebnis['landlord_share']['positions'][0]['units'][0]
    assert (einheit['vacant_days'], einheit['period_days']) == (7, 7)


def test_wohnungsrechnung_einer_leeren_wohnung_ueber_den_jahreswechsel():
    """01.12.2024–31.01.2025 für die leere W2: in 2025 liegen 31 von 62 Tagen."""
    w, m = _zwei_wohnungen()
    r = (Rechnung(1, MUELL, Decimal('62.00'), date(2024, 12, 1), date(2025, 1, 31), wohnung_id=2),)
    ergebnis = rechne(_vorgang(m[0], w, m, r, {MUELL.id: 'qm'}))

    assert _vermieter(ergebnis, 1) == Decimal('31.00')


def _wasserzaehler(id, staende, wohnung_id=None):
    return Zaehler(id=id, nummer=f'Z-{id}', kategorie_id=WASSER.id, kategorie_name=WASSER.name,
                   ist_hauptzaehler=wohnung_id is None, immobilie_id=1, wohnung_id=wohnung_id,
                   staende=tuple(Stand(d, v) for d, v in staende), kategorie_betrkv_nr=2)


def test_zaehlerzweig_ueber_den_jahreswechsel():
    """Rechnung 01.07.2024–30.06.2025, 1000 EUR für 100 m³; W2 leer.

    Abgelesen zum 01.01.2025: je Halbjahr 50 m³ im Haus, 15 in W1, 10 in W2,
    25 allgemein. In 2025 gehört die halbe Rechnung: W1 zahlt 150 eigen plus
    125 allgemein, beim Vermieter bleiben 100 für W2 und 125 allgemein.
    Vorher waren es 200 und 250 -- beide Halbjahre.
    """
    w, m = _zwei_wohnungen()
    a, j, e = date(2024, 7, 1), date(2025, 1, 1), date(2025, 7, 1)
    z = (_wasserzaehler(10, [(a, 0), (j, 50), (e, 100)]),
         _wasserzaehler(11, [(a, 0), (j, 15), (e, 30)], 1),
         _wasserzaehler(12, [(a, 0), (j, 10), (e, 20)], 2))
    r = (Rechnung(1, WASSER, Decimal('1000.00'), a, date(2025, 6, 30)),)
    ergebnis = rechne(_vorgang(m[0], w, m, r, {WASSER.id: 'direkt'}, z))

    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('275.00')
    assert _vermieter(ergebnis, 1) == Decimal('225.00')


# --- Erhaltung: im Zeitraum geht jede Rechnung auf --------------------------------------

def _tag(rng, von, bis):
    return von + timedelta(days=rng.randrange((bis - von).days + 1))


def _welt(seed):
    """2–4 Wohnungen, W1 ganzjährig; die übrigen leer, vermietet oder im Wechsel."""
    rng = random.Random(seed)
    w = tuple(Wohnung(i, f'W{i}', float(rng.randrange(30, 121)))
              for i in range(1, rng.randint(2, 4) + 1))
    m = [Mieter(1, 'Mieter 1', date(2020, 1, 1), None, 1)]

    def neu(einzug, auszug, wid):
        m.append(Mieter(len(m) + 1, f'Mieter {len(m) + 1}', einzug, auszug, wid))

    for wohnung in w[1:]:
        lage = rng.choice(['leer', 'ganz', 'einzug', 'auszug', 'wechsel'])
        if lage == 'ganz':
            neu(date(2019, 5, 1), None, wohnung.id)
        elif lage == 'einzug':
            neu(_tag(rng, B, E), None, wohnung.id)
        elif lage == 'auszug':
            neu(date(2019, 5, 1), _tag(rng, B, E), wohnung.id)
        elif lage == 'wechsel':
            aus = _tag(rng, B, date(2025, 6, 30))
            neu(date(2019, 5, 1), aus, wohnung.id)
            neu(aus + timedelta(days=rng.randrange(1, 60)), None, wohnung.id)
    kats = (VERS, MUELL, GARTEN, HAUSWART)
    r = []
    for i in range(rng.randint(1, 5)):
        s = _tag(rng, date(2024, 7, 1), date(2025, 9, 30))
        r.append(Rechnung(i + 1, rng.choice(kats), Decimal(rng.randrange(1000, 200000)) / 100,
                          s, s + timedelta(days=rng.randrange(60, 500)),
                          wohnung_id=rng.choice([None, None, None] + [x.id for x in w])))
    return w, tuple(m), tuple(r), {k.id: rng.choice(['qm', 'personen']) for k in kats}


@pytest.mark.parametrize('seed', range(60))
def test_jede_rechnung_geht_im_zeitraum_auf(seed):
    """Mieterzeilen plus Vermieteranteil = der Teil der Rechnung im Jahr 2025.

    Den Vermieteranteil liest die Probe aus der Abrechnung von Mieter 1, der
    das ganze Jahr wohnt -- sein Zeitraum ist der ganze Zeitraum.
    """
    w, m, r, profile = _welt(seed)
    ergebnisse = {x.id: rechne(_vorgang(x, w, m, r, profile)) for x in m}
    mieter, parteien = defaultdict(Decimal), defaultdict(lambda: 1)
    for ergebnis in ergebnisse.values():
        for zeile in ergebnis['line_items']:
            mieter[zeile['invoice_id']] += zeile['tenant_cost']
            parteien[zeile['invoice_id']] += 1
    for rechnung in r:
        drin = (min(E, rechnung.ende) - max(B, rechnung.beginn)).days + 1
        if drin <= 0:
            continue
        soll = (rechnung.betrag * drin / ((rechnung.ende - rechnung.beginn).days + 1)).quantize(
            Decimal('0.01'), ROUND_HALF_UP)
        ist = mieter[rechnung.id] + _vermieter(ergebnisse[1], rechnung.id)
        # ponytail: jede Partei rundet für sich auf den Cent; mehr als ein Cent
        # je Partei wäre ein Fehler, weniger lässt sich nicht verlangen.
        assert abs(soll - ist) <= Decimal('0.01') * parteien[rechnung.id], (
            seed, rechnung, soll, ist)
