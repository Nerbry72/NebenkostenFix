"""NK-189: Zählerstände, wie sie im Bestand liegen (D-115).

Die Praxisprobe (NK-187) fand Wärmezähler, die im Frühjahr abgelesen
werden, während das Haus zum Jahresende abrechnet (H2). Bisher schätzte die
App den Stand am Stichtag nach Tagen: dann trägt ein Julitag so viel Wärme
wie ein Januartag. Jetzt schätzt sie nach Gradtagszahlen (VDI 2067) und sagt
es. Wasser und Strom bleiben linear. Alle Werte sind erfunden.
"""

from __future__ import annotations

from datetime import date

import pytest

from nebenkostenfix import heizung
from nebenkostenfix.billing_engine import BillingEngine
from nebenkostenfix.pdf_generator import stichtag_hinweis
from nebenkostenfix.rechenkern import Stand, Zaehler, verbrauch_in
from nebenkostenfix.zeitraumvorschlag import vorschlag
from tests import billing_factories as f

JAN = date(2025, 1, 1)
APRIL = date(2025, 4, 1)
NEUJAHR = date(2026, 1, 1)


def _zaehler(name, betrkv_nr, *staende, anlage=None):
    return Zaehler(id=1, nummer='Z-1', kategorie_id=1, kategorie_name=name,
                   ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                   staende=tuple(Stand(d, w, nt) for d, w, nt in staende),
                   heizungsanlage_id=anlage, kategorie_betrkv_nr=betrkv_nr)


def test_gradtage_summieren_sich_auf_ein_jahr():
    assert heizung.gradtage(JAN, NEUJAHR) == 1000
    assert heizung.gradtage(APRIL, NEUJAHR) == 550
    assert heizung.gradtage(date(2024, 1, 1), date(2025, 1, 1)) == 1000  # Schaltjahr


# --- H2: Ablesung im April, Stichtag Jahresende ---------------------------------------

def test_waerme_wird_nach_gradtagen_geschaetzt():
    """Vorher: 2000 × 275/365 = 1506,8 kWh für April bis Dezember."""
    z = _zaehler('Heizung', 4, (APRIL, 1000, None), (date(2026, 4, 1), 3000, None))

    d = verbrauch_in(z, APRIL, NEUJAHR)

    assert d['consumption'] == pytest.approx(1100)  # 550 ‰ von 2000
    assert d['gradtage'] is True
    assert stichtag_hinweis(d).startswith('Stichtagswert nach Gradtagszahlen geschätzt')


def test_luecke_nach_der_letzten_ablesung():
    """Stand nur bis Juli: der Rest des Jahres nach dem Wärmebedarf aufgefüllt."""
    z = _zaehler('Heizung', 4, (JAN, 0, None), (date(2025, 7, 1), 700, None))

    d = verbrauch_in(z, JAN, NEUJAHR)

    # Januar bis Juni sind 583⅓ ‰; 700 kWh dort heißen 1200 kWh im Jahr.
    assert d['consumption'] == pytest.approx(1200)


@pytest.mark.parametrize('name, nr, anlage', [
    ('Heizung', 4, None), ('Warmwasser', 6, None), ('Wärmemenge', None, None),
    ('Verbrauch', None, 7)])
def test_das_sind_waermezaehler(name, nr, anlage):
    z = _zaehler(name, nr, (APRIL, 0, None), (date(2026, 4, 1), 1000, None), anlage=anlage)
    assert verbrauch_in(z, APRIL, NEUJAHR)['gradtage'] is True


@pytest.mark.parametrize('name, nr', [('Wasser', 2), ('Warmwasser', None), ('Allgemeinstrom', 11)])
def test_wasser_und_strom_bleiben_linear(name, nr):
    z = _zaehler(name, nr, (APRIL, 0, None), (date(2026, 4, 1), 365, None))

    d = verbrauch_in(z, APRIL, NEUJAHR)

    assert d['consumption'] == pytest.approx(275)
    assert d['gradtage'] is False
    assert stichtag_hinweis(d) == 'Stichtagswert wurde interpoliert.'


def test_am_stichtag_abgelesen_ist_nichts_geschaetzt():
    z = _zaehler('Heizung', 4, (JAN, 0, None), (NEUJAHR, 1234, None))

    d = verbrauch_in(z, JAN, NEUJAHR)

    assert d['consumption'] == pytest.approx(1234)
    assert d['gradtage'] is False


# --- H3: Dualtarif --------------------------------------------------------------------

def test_dualtarif_hochtarif_und_niedertarif_ergeben_die_summe():
    z = _zaehler('Heizung', 4, (APRIL, 1000, 500), (date(2026, 4, 1), 2000, 1500))

    d = verbrauch_in(z, APRIL, NEUJAHR)

    assert (d['ht'], d['nt']) == (pytest.approx(550), pytest.approx(550))
    assert d['ht'] + d['nt'] == pytest.approx(d['consumption'])


# --- Der Vorschlag nennt den fehlenden Stand ------------------------------------------

def test_vorschlag_nennt_die_naechste_ablesung(app_ctx):
    prop = f.house('Wärmehaus')
    wohnung = f.apt(prop, 'EG', 60.0)
    mieter = f.tenant(wohnung, 'Mieter 1', move_in=date(2020, 1, 1))
    mieter.last_billed_until = date(2024, 12, 31)
    kat = f.category('Heizung')
    kat.betrkv_nr = 4
    f.profile(mieter, kat, 'direkt')
    f.invoice(prop, kat, 1200.0, start=JAN, end=date(2025, 12, 31), invoice_number='H-1')
    z = f.meter(prop, kat, 'WZ-1', is_main=False, apartment=wohnung)
    f.reading(z, date(2024, 4, 1), 100)
    f.reading(z, APRIL, 1100)
    f.reading(z, date(2026, 4, 1), 2100)

    gruende = vorschlag(mieter.id, date(2026, 9, 30))['gruende']

    assert ('Der Wärmezähler WZ-1 hat um den 31.12.2025 keine Ablesung, die letzte davor ist '
            'vom 01.04.2025, die erste danach vom 01.04.2026. Lesen Sie zum 31.12.2025 ab, dann '
            'rechnet die Abrechnung genau; sonst schätzt sie nach Gradtagszahlen.') in gruende


def test_vorschlag_nennt_keine_fruehere_ablesung_als_naechste(app_ctx):
    """Praxisbestand: Die nächstgelegene Ablesung lag vor dem Stichtag und hieß „die nächste“."""
    prop = f.house('Wärmehaus')
    wohnung = f.apt(prop, 'EG', 60.0)
    mieter = f.tenant(wohnung, 'Mieter 1', move_in=date(2025, 10, 1))
    kat = f.category('Heizung')
    kat.betrkv_nr = 4
    f.profile(mieter, kat, 'direkt')
    f.invoice(prop, kat, 1200.0, start=JAN, end=date(2025, 12, 31), invoice_number='H-1')
    z = f.meter(prop, kat, 'WZ-1', is_main=False, apartment=wohnung)
    f.reading(z, date(2025, 10, 17), 100)
    f.reading(z, date(2026, 7, 31), 900)

    [hinweis] = [g for g in vorschlag(mieter.id, date(2026, 9, 30))['gruende'] if 'WZ-1' in g]

    assert 'die letzte davor ist vom 17.10.2025, die erste danach vom 31.07.2026' in hinweis
    assert 'nächste' not in hinweis


def test_vorschlag_schweigt_bei_ablesung_am_jahresende(app_ctx):
    prop = f.house('Wärmehaus')
    wohnung = f.apt(prop, 'EG', 60.0)
    mieter = f.tenant(wohnung, 'Mieter 2', move_in=date(2020, 1, 1))
    mieter.last_billed_until = date(2024, 12, 31)
    kat = f.category('Heizung')
    kat.betrkv_nr = 4
    f.profile(mieter, kat, 'direkt')
    f.invoice(prop, kat, 1200.0, start=JAN, end=date(2025, 12, 31), invoice_number='H-1')
    z = f.meter(prop, kat, 'WZ-2', is_main=False, apartment=wohnung)
    f.reading(z, date(2024, 12, 31), 100)
    f.reading(z, date(2026, 1, 3), 1100)

    v = vorschlag(mieter.id, date(2026, 9, 30))

    assert (v['beginn'], v['ende']) == ('2025-01-01', '2025-12-31')
    assert not any('Wärmezähler' in g for g in v['gruende'])


# --- Das einfache PDF sagt, dass der Stichtag geschätzt ist ---------------------------

def _heizposten(*ablesungen):
    prop = f.house('Wärmehaus')
    wohnung = f.apt(prop, 'EG', 60.0)
    mieter = f.tenant(wohnung, 'Mieter 1', move_in=date(2020, 1, 1))
    kat = f.category('Heizung')
    kat.betrkv_nr = 4
    f.profile(mieter, kat, 'direkt')
    f.invoice(prop, kat, 1200.0, start=JAN, end=date(2025, 12, 31), invoice_number='H-1')
    z = f.meter(prop, kat, 'WZ-1', is_main=False, apartment=wohnung)
    for tag, stand in ablesungen:
        f.reading(z, tag, stand)
    [zeile] = BillingEngine(mieter.id, '2025-01-01', '2025-12-31').calculate_bill()['line_items']
    return next(s['description'] for s in zeile['sub_items'] if s['type'] == 'eigenverbrauch')


def test_einfaches_pdf_nennt_geschaetzten_stichtag(app_ctx):
    """Praxisbestand: Nur das detaillierte PDF sagte „nach Gradtagszahlen geschätzt“."""
    text = _heizposten((date(2024, 4, 1), 100), (APRIL, 1100), (date(2026, 4, 1), 2100))
    assert text.endswith(', Stichtag nach Gradtagszahlen geschätzt)')


def test_einfaches_pdf_schweigt_bei_ablesung_am_stichtag(app_ctx):
    text = _heizposten((date(2024, 12, 31), 100), (date(2025, 12, 31), 1100))
    assert text == 'Eigenverbrauch (1000,0 kWh)'
