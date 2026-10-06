"""NK-208 (B1): der Verbrauchsnachweis laesst sich nachrechnen.

Befund der App-Analyse vom 2026-10-06: Das detaillierte PDF zeigte bei
„Ablesung Anfang/Ende“ die aeusseren Stuetzstellen der Interpolation, also
Staende ausserhalb des Zeitraums. Ende minus Anfang ergab dann nicht den
Eigenverbrauch, und eine Zwischenablesung tauchte gar nicht auf.

Jetzt liefert ``verbrauch_in`` die Staende an den Grenzen selbst
(``stand_beginn``, ``stand_ende``), nach derselben Rechnung wie der
Verbrauch. Es gilt immer: ``stand_ende - stand_beginn == consumption``.

*Haette den Fehler gefunden:* jeder Test hier -- vorher gab es die Felder
nicht, und das PDF rechnete mit ``r_start``/``r_end``.
"""

from datetime import date

import pytest

from nebenkostenfix import heizung
from nebenkostenfix.rechenkern import Stand, Zaehler, verbrauch_in


def zaehler(staende, name='Wasser', betrkv_nr=None):
    return Zaehler(id=1, nummer='Z-1', kategorie_id=2, kategorie_name=name,
                   ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                   staende=tuple(staende), kategorie_betrkv_nr=betrkv_nr)


def geht_auf(d):
    assert d['stand_ende'] - d['stand_beginn'] == pytest.approx(d['consumption'])


def test_staende_auf_den_grenzen_sind_abgelesen():
    z = zaehler([Stand(date(2024, 1, 1), 1000.0), Stand(date(2025, 1, 1), 1366.0)])
    d = verbrauch_in(z, date(2024, 1, 1), date(2025, 1, 1))
    assert d['stand_beginn'] == pytest.approx(1000.0)
    assert d['stand_ende'] == pytest.approx(1366.0)
    assert d['beginn_abgelesen'] is True
    assert d['ende_abgelesen'] is True
    geht_auf(d)


def test_staende_ausserhalb_werden_auf_den_stichtag_gerechnet():
    """Der Fall aus der Analyse: die Ablesungen liegen vor und nach dem
    Zeitraum. Das Blatt zeigt nicht mehr 0 und 428, sondern 31 und 397."""
    z = zaehler([Stand(date(2023, 12, 1), 0.0), Stand(date(2025, 2, 1), 428.0)])  # 1 je Tag
    d = verbrauch_in(z, date(2024, 1, 1), date(2025, 1, 1))
    assert d['stand_beginn'] == pytest.approx(31.0)
    assert d['stand_ende'] == pytest.approx(397.0)
    assert d['beginn_abgelesen'] is False
    assert d['ende_abgelesen'] is False
    assert d['r_start']['total'] == 0.0   # die Stuetzstelle bleibt in der Auskunft
    geht_auf(d)


def test_stand_innen_folgt_dem_eigenen_abschnitt():
    """Drei Staende mit verschiedenen Raten: der Stand am Stichtag kommt aus
    dem Abschnitt, in dem er liegt, nicht aus dem Mittel."""
    z = zaehler([
        Stand(date(2024, 1, 1), 0.0),
        Stand(date(2024, 7, 1), 364.0),    # 182 Tage, 2 je Tag
        Stand(date(2025, 1, 1), 548.0),    # 184 Tage, 1 je Tag
    ])
    d = verbrauch_in(z, date(2024, 4, 1), date(2024, 10, 1))
    assert d['stand_beginn'] == pytest.approx(182.0)
    assert d['stand_ende'] == pytest.approx(456.0)
    assert d['consumption'] == pytest.approx(274.0)
    geht_auf(d)


def test_vor_dem_ersten_stand_wird_zurueckgerechnet():
    z = zaehler([Stand(date(2024, 3, 1), 0.0), Stand(date(2024, 4, 1), 31.0)])
    d = verbrauch_in(z, date(2024, 2, 1), date(2024, 5, 1))
    assert d['stand_beginn'] == pytest.approx(-29.0)
    assert d['stand_ende'] == pytest.approx(61.0)
    geht_auf(d)


def test_benachbarte_zeitraeume_teilen_den_stand():
    """Das Ende des einen Zeitraums ist der Anfang des naechsten -- auch beim
    Heizwaermezaehler, der nach Gradtagen schaetzt."""
    for name, nr in (('Wasser', None), ('Heizung', 4)):
        z = zaehler([Stand(date(2024, 1, 1), 0.0), Stand(date(2025, 1, 1), 1000.0)],
                    name=name, betrkv_nr=nr)
        erst = verbrauch_in(z, date(2024, 1, 1), date(2024, 7, 1))
        dann = verbrauch_in(z, date(2024, 7, 1), date(2025, 1, 1))
        assert erst['stand_ende'] == pytest.approx(dann['stand_beginn'])
        geht_auf(erst)
        geht_auf(dann)


def test_heizung_schaetzt_den_stichtag_nach_gradtagen():
    z = zaehler([Stand(date(2024, 1, 1), 0.0), Stand(date(2025, 1, 1), 1000.0)],
                name='Heizung', betrkv_nr=4)
    d = verbrauch_in(z, date(2024, 4, 1), date(2025, 1, 1))
    # 1. April: 450 von 1000 Gradtagen sind vorbei, nicht 91/366
    assert d['stand_beginn'] == pytest.approx(450.0)
    assert d['gradtage'] is True
    geht_auf(d)


def test_zwei_staende_am_selben_tag_gehen_trotzdem_auf():
    z = zaehler([
        Stand(date(2024, 1, 1), 0.0),
        Stand(date(2024, 7, 1), 100.0),
        Stand(date(2024, 7, 1), 120.0),
        Stand(date(2025, 1, 1), 300.0),
    ])
    geht_auf(verbrauch_in(z, date(2024, 3, 1), date(2024, 11, 1)))


def test_zwischenablesung_ist_in_den_ablesungen_markiert():
    z = zaehler([
        Stand(date(2024, 1, 1), 0.0),
        Stand(date(2024, 7, 1), 180.0, art=heizung.ZWISCHENABLESUNG),
        Stand(date(2025, 1, 1), 370.0),
    ])
    d = verbrauch_in(z, date(2024, 7, 1), date(2025, 1, 1))
    assert d['stand_beginn'] == pytest.approx(180.0)
    assert d['beginn_abgelesen'] is True
    assert [b['zwischenablesung'] for b in d['basis_readings']] == [True, False]


def test_alle_staende_am_selben_tag_ergeben_keinen_anstieg():
    z = zaehler([Stand(date(2024, 7, 1), 100.0), Stand(date(2024, 7, 1), 120.0)])
    d = verbrauch_in(z, date(2024, 1, 1), date(2025, 1, 1))
    assert d['stand_beginn'] == pytest.approx(100.0)
    geht_auf(d)
