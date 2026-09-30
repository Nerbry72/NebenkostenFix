"""NK-041: die Tageskonvention aus R-NUM-03, an ihrem einen Ort geprueft.

Die Regel in einem Satz: der erste Tag zaehlt, der letzte nicht. Was hier
gruen ist, traegt jede Tageszahl im Programm -- Kostenumlage, Personentage,
Zaehlerhochrechnung.

Der Waechter der Datei ist ``test_wechseltag_geht_nie_doppelt``: er wuerfelt
Wechseltage und besteht darauf, dass zwei aneinandergrenzende Mietzeiten
zusammen genau den Zeitraum ergeben. Die Einzelfaelle darueber erklaeren, die
Stichprobe beweist.
"""

from __future__ import annotations

import pathlib
import random
from datetime import date, timedelta

import pytest

from nebenkostenfix.zeitraum import ein_jahr_nach, grenze, letzter_tag, mietende, tage, ueberschneidung


# --- Umrechnung an der Grenze ----------------------------------------------


@pytest.mark.parametrize('letzter,erwartet', [
    (date(2024, 12, 31), date(2025, 1, 1)),
    (date(2024, 2, 29), date(2024, 3, 1)),
    (date(2024, 6, 30), date(2024, 7, 1)),
])
def test_grenze_liegt_einen_tag_hinter_dem_letzten(letzter, erwartet):
    """Ein Zeitraum "bis 31.12." hat seine Grenze am 01.01. (R-NUM-03)."""
    assert grenze(letzter) == erwartet


def test_letzter_tag_fuehrt_zurueck():
    """Fuer die Anzeige: das PDF nennt den 31.12., nicht den 01.01."""
    for tag in (date(2024, 12, 31), date(2024, 2, 29), date(2023, 1, 1)):
        assert letzter_tag(grenze(tag)) == tag


# --- Tage zaehlen ----------------------------------------------------------


@pytest.mark.parametrize('von,bis,erwartet', [
    # Ein ganzes Schaltjahr, so wie der Vermieter es eingibt.
    (date(2024, 1, 1), grenze(date(2024, 12, 31)), 366),
    (date(2023, 1, 1), grenze(date(2023, 12, 31)), 365),
    # Ein einzelner Tag.
    (date(2024, 3, 1), grenze(date(2024, 3, 1)), 1),
    # Leer und umgedreht sind beide null, nicht negativ.
    (date(2024, 3, 1), date(2024, 3, 1), 0),
    (date(2024, 12, 31), date(2024, 1, 1), 0),
])
def test_tage(von, bis, erwartet):
    assert tage(von, bis) == erwartet


def test_der_auszugstag_zaehlt_nicht_mit():
    """Das Herzstueck von D-12: Einzug 01.01., Auszug 30.06. sind 181 Tage.

    Inklusiv gezaehlt waeren es 182 -- und genau der eine Tag zuviel geht
    beim Mieterwechsel an zwei Mieter gleichzeitig.
    """
    assert tage(date(2024, 1, 1), date(2024, 6, 30)) == 181


# --- Ueberschneidung -------------------------------------------------------


@pytest.mark.parametrize('a_von,a_bis,b_von,b_bis,erwartet', [
    # Deckungsgleich.
    (date(2024, 1, 1), date(2025, 1, 1), date(2024, 1, 1), date(2025, 1, 1), 366),
    # Beruehren sich nur an einem Datum -- das ist keine Ueberschneidung.
    (date(2024, 1, 1), date(2024, 7, 1), date(2024, 7, 1), date(2025, 1, 1), 0),
    # Getrennt.
    (date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1), 0),
    # Einer liegt ganz im anderen.
    (date(2024, 3, 1), date(2024, 3, 11), date(2024, 1, 1), date(2025, 1, 1), 10),
])
def test_ueberschneidung(a_von, a_bis, b_von, b_bis, erwartet):
    assert ueberschneidung(a_von, a_bis, b_von, b_bis) == erwartet


def test_ueberschneidung_ist_seitenverkehrt_gleich():
    a = (date(2024, 3, 1), date(2024, 9, 1))
    b = (date(2024, 6, 1), date(2025, 1, 1))
    assert ueberschneidung(*a, *b) == ueberschneidung(*b, *a)


# --- ``Mieter.auszug`` ist schon eine Grenze --------------------------------


def test_mietende_verschiebt_den_auszug_nicht():
    """Wer hier ``grenze()`` anwendet, berechnet den Auszugstag mit."""
    auszug = date(2024, 6, 30)
    assert mietende(auszug, date(2025, 1, 1)) == auszug


def test_mietende_ohne_auszug_nimmt_den_zeitraum():
    assert mietende(None, date(2025, 1, 1)) == date(2025, 1, 1)


# --- Der Waechter ----------------------------------------------------------


def test_wechseltag_geht_nie_doppelt():
    """Zwei aneinandergrenzende Mietzeiten ergeben zusammen den Zeitraum.

    Das ist der tragende Grund aus R-NUM-03, als Rechnung: A zieht an einem
    beliebigen Tag aus, B zieht am selben Tag ein. Ihre Tage muessen sich zu
    genau den Tagen des Jahres addieren -- keiner mehr, keiner weniger.

    Unter der alten, einschliessenden Zaehlung war die Summe hier immer um
    eins zu gross.
    """
    wuerfel = random.Random(41)
    jahr_von = date(2024, 1, 1)
    jahr_bis = grenze(date(2024, 12, 31))
    ganzes_jahr = tage(jahr_von, jahr_bis)
    assert ganzes_jahr == 366

    for _ in range(500):
        wechsel = jahr_von + timedelta(days=wuerfel.randrange(1, ganzes_jahr))

        # A: vom Jahresanfang bis zum Auszug -- der Auszugstag ist die Grenze.
        a = tage(jahr_von, mietende(wechsel, jahr_bis))
        # B: vom Einzug bis zum Jahresende.
        b = tage(wechsel, jahr_bis)

        assert a + b == ganzes_jahr, f'Wechsel am {wechsel}: {a} + {b}'
        assert ueberschneidung(jahr_von, wechsel, wechsel, jahr_bis) == 0


# --- Die Hoechstlaenge eines Abrechnungszeitraums (F-28) --------------------
#
# app.py kuerzte einen zu langen Zeitraum still auf `s_date + 364 Tage`. Fuer
# ein Schaltjahr ist das einer zu wenig: wer 01.01.2024 bis 31.12.2024 eingab,
# bekam eine Abrechnung bis zum 30.12. -- ohne Hinweis. Kein Test hat es
# gemerkt, weil keiner existierte.


def test_ein_volles_schaltjahr_bleibt_ungekuerzt():
    for jahr in (2023, 2024, 2025, 2028):
        von = date(jahr, 1, 1)
        letzter = date(jahr, 12, 31)
        assert grenze(letzter) == ein_jahr_nach(von), (
            f'Das Jahr {jahr} passt nicht in seine eigene Jahresgrenze'
        )


def test_ein_tag_zuviel_wird_auf_das_jahresende_gestutzt():
    von = date(2024, 1, 1)
    gestutzt = letzter_tag(ein_jahr_nach(von))
    assert gestutzt == date(2024, 12, 31)


def test_ein_jahr_ab_dem_schalttag_endet_am_28_februar():
    # Den 29.02.2025 gibt es nicht. Das Jahr laeuft bis zum 28.02.
    assert ein_jahr_nach(date(2024, 2, 29)) == date(2025, 3, 1)
    assert letzter_tag(ein_jahr_nach(date(2024, 2, 29))) == date(2025, 2, 28)


def test_ein_jahr_zaehlt_365_oder_366_tage_nie_364():
    wuerfel = random.Random(28)
    for _ in range(500):
        von = date(2020, 1, 1) + timedelta(days=wuerfel.randrange(0, 3000))
        laenge = tage(von, ein_jahr_nach(von))
        assert laenge in (365, 366), f'{von} -> {laenge} Tage'


def test_app_kuerzt_nicht_mehr_mit_einem_festen_tagesmass():
    """Der Riegel gegen den Rueckfall: kein `364` mehr in app.py.

    Die Zahl war die inklusive Jahreslaenge minus eins und hat den Schalttag
    vergessen. Wer sie wieder einsetzt, faellt hier auf.
    """
    quelle = (pathlib.Path(__file__).resolve().parent.parent / 'app.py').read_text(
        encoding='utf-8'
    )
    assert '364' not in quelle, (
        'app.py rechnet wieder mit einem festen Tagesmass fuer ein Jahr. '
        'Die Jahresgrenze gehoert nach zeitraum.ein_jahr_nach() -- '
        'timedelta(days=364) kuerzt jedes Schaltjahr um einen Tag (F-28).'
    )
