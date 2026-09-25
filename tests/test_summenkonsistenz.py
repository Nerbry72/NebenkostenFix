"""NK-038: Was der Mieter nachaddiert, muss stimmen (R-NUM-02).

Zwei Gleichungen, beide aus R-NUM-02, beide ueber 200 zufaellig gebaute
Abrechnungen geprueft:

1. ``summe(gerundete Zeilen) == total_amount`` -- die Spalte unter dem
   Strich. Seit NK-036 gilt sie, weil ``total_amount`` als Summe der
   gerundeten Zeilen entsteht und nicht als gerundete Summe.
2. ``summe(sub_items) == tenant_cost`` je Zeile -- die Unterposten einer
   Position. Hier fehlte der Restcent: Eigenverbrauch und Allgemeinanteil
   werden einzeln gerundet, ihre Summe lag in jedem vierten Zufallsfall
   einen Cent neben dem Zeilenbetrag. Das behebt NK-038.

Zufall mit festem Keim, nicht mit ``random`` aus der Luft: ein Fehlschlag
muss sich wiederholen lassen (Ziel 4, NK-039). Faellt einer dieser Tests, steht
die Nummer des Falls im Fehlertext, und ``_vorgaenge()`` baut ihn erneut.

Warum 200 Faelle und keine Bibliothek fuer Eigenschaftstests: die Karte
fordert 200 Fixtures, und ein Generator, den man lesen kann, ist hier mehr
wert als einer, der schrumpft. Seit NK-037 braucht ein Fall keine Datenbank
mehr -- ein ``Vorgang`` ist ein Dataclass, 200 davon kosten Millisekunden.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from geld import summe
from rechenkern import (
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

#: Die Abrechnungsarten, die `rechne` kennt. `ignoriert` ist dabei, weil eine
#: Zeile mit Betrag null die Summe genauso treffen muss wie jede andere.
ARTEN = ('qm', 'personen', 'direkt', 'nur_allgemein', 'ignoriert')

#: Kategorien, aus denen gewuerfelt wird. Wasser und Heizung brauchen einen
#: Zaehler, Abwasser nicht -- es haengt am Wasserzaehler und ist der Fall, in
#: dem zwei Rechnungen denselben Stand teilen.
KATEGORIEN = (
    Kategorie(id=1, name='Hausmeister', braucht_zaehler=False),
    Kategorie(id=2, name='Wasser', braucht_zaehler=True),
    Kategorie(id=3, name='Abwasser', braucht_zaehler=False),
    Kategorie(id=4, name='Heizung', braucht_zaehler=True),
    Kategorie(id=5, name='Müllabfuhr', braucht_zaehler=False),
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)


def _betrag(rnd) -> Decimal:
    """Ein Rechnungsbetrag zwischen 50 und 9000 Euro, auf den Cent genau.

    Krumme Betraege sind der Punkt: 1200,00 Euro durch drei Mieter geht auf,
    1199,99 nicht.
    """
    return Decimal(rnd.randrange(5000, 900000)).scaleb(-2)


#: Die Ablesetermine liegen vor dem Abrechnungsjahr und dahinter, damit jede
#: Rechnung innerhalb der Staende liegt und nicht daneben.
ABLESE_BEGINN = JAHR_BEGINN - timedelta(days=90)
ABLESE_ENDE = JAHR_ENDE + timedelta(days=90)


def _termine(rnd):
    """Zwei bis vier Ablesetermine, fuer alle Zaehler einer Kategorie dieselben.

    Dieselben Termine, weil ein Haus einmal abgelesen wird. Das ist nicht nur
    naeher an der Wirklichkeit, es macht den Vergleich Hauptzaehler gegen
    Unterzaehler erst aussagekraeftig: liegen die Termine auseinander, muss
    `verbrauch_detail` interpolieren, und der Allgemeinanteil wird zu einer
    Zahl, die vom Kalender abhaengt statt vom Wasser.
    """
    tage = (ABLESE_ENDE - ABLESE_BEGINN).days
    anzahl = rnd.randint(2, 4)
    return [
        ABLESE_BEGINN + timedelta(days=round(i * tage / (anzahl - 1)))
        for i in range(anzahl)
    ]


def _zaehlerwelt(rnd, kat, wohnungen, erste_id):
    """Die Zaehler einer Kategorie: Wohnungszaehler und darueber der Hauptzaehler.

    Der Hauptzaehler wird **aus** den Unterzaehlern gebaut, nicht neben ihnen
    gewuerfelt: er zaehlt, was die Wohnungen verbrauchen, plus einen Aufschlag
    von fuenf bis vierzig Prozent fuer Garten, Waschkeller und Leitungsverlust.
    Wuerfelt man beide unabhaengig, liegt die Summe der Unterzaehler meist
    ueber dem Hauptzaehler, `max(0, ...)` macht den Allgemeinverbrauch zu null
    -- und der Fall mit zwei Unterposten, um den es in dieser Datei geht,
    entsteht nie.
    """
    termine = _termine(rnd)
    zaehler = []
    naechste_id = erste_id
    haupt_werte = [Decimal(0)] * len(termine)

    for w in wohnungen:
        if rnd.random() >= 0.85:          # nicht jede Wohnung hat einen Zaehler
            continue
        wert = Decimal(rnd.randrange(0, 50000)).scaleb(-1)
        werte = []
        for _ in termine:
            werte.append(wert)
            wert += Decimal(rnd.randrange(1, 30000)).scaleb(-1)
        for i, v in enumerate(werte):
            haupt_werte[i] += v
        zaehler.append(Zaehler(
            id=naechste_id, nummer=f'W{naechste_id}', kategorie_id=kat.id,
            kategorie_name=kat.name, ist_hauptzaehler=False, immobilie_id=1,
            wohnung_id=w.id,
            staende=tuple(Stand(datum=d, wert=float(v), wert_nt=None)
                          for d, v in zip(termine, werte)),
        ))
        naechste_id += 1

    if rnd.random() < 0.8:
        aufschlag = Decimal(rnd.randrange(105, 140)) / 100
        basis = haupt_werte[0]
        zaehler.append(Zaehler(
            id=naechste_id, nummer=f'H{naechste_id}', kategorie_id=kat.id,
            kategorie_name=kat.name, ist_hauptzaehler=True, immobilie_id=1,
            wohnung_id=None,
            staende=tuple(
                Stand(datum=d, wert=float(basis + (v - basis) * aufschlag), wert_nt=None)
                for d, v in zip(termine, haupt_werte)
            ),
        ))
        naechste_id += 1

    return zaehler, naechste_id


def _vorgang(rnd, nummer):
    """Eine vollstaendige Abrechnung aus Zufallsteilen.

    Gewuerfelt werden: Zahl der Wohnungen und ihre Flaechen, wer wann ein-
    und auszieht, welche Kategorie wie abgerechnet wird, wie viele Rechnungen
    es gibt und ueber welche Zeitraeume, welche Zaehler haengen wo, und was
    der Mieter vorausgezahlt hat.
    """
    anzahl_wohnungen = rnd.randint(1, 5)
    wohnungen = tuple(
        Wohnung(id=i + 1, name=f'Wohnung {i + 1}', qm=float(rnd.randrange(250, 1400)) / 10)
        for i in range(anzahl_wohnungen)
    )

    mieter = []
    for w in wohnungen:
        # Ein Drittel der Mietverhaeltnisse faengt spaeter an oder hoert
        # frueher auf. Das erzeugt Teilzeitraeume und ungleiche Personentage.
        einzug = JAHR_BEGINN - timedelta(days=rnd.randrange(0, 900))
        auszug = None
        wuerfel = rnd.random()
        if wuerfel < 0.2:
            einzug = JAHR_BEGINN + timedelta(days=rnd.randrange(1, 300))
        elif wuerfel < 0.35:
            auszug = JAHR_BEGINN + timedelta(days=rnd.randrange(30, 360))
        mieter.append(
            Mieter(id=w.id, name=f'Mieter {w.id}', einzug=einzug, auszug=auszug, wohnung_id=w.id)
        )
    mieter = tuple(mieter)

    ich = mieter[0]
    meine_wohnung = wohnungen[0]
    beginn = max(JAHR_BEGINN, ich.einzug)
    ende = min(JAHR_ENDE, ich.auszug) if ich.auszug else JAHR_ENDE
    if beginn > ende:                      # ausgewuerfelt, aber unbrauchbar
        beginn, ende = JAHR_BEGINN, JAHR_ENDE
        ich = Mieter(id=ich.id, name=ich.name, einzug=JAHR_BEGINN - timedelta(days=30),
                     auszug=None, wohnung_id=ich.wohnung_id)
        mieter = (ich,) + mieter[1:]

    profile = {k.id: rnd.choice(ARTEN) for k in KATEGORIEN}

    rechnungen = []
    for i in range(rnd.randint(1, 6)):
        kat = rnd.choice(KATEGORIEN)
        # Mal das ganze Jahr, mal ein Quartal, mal ueber den Jahreswechsel
        # hinaus -- der Zeitanteil einer Rechnung ist selten eins.
        r_beginn = JAHR_BEGINN + timedelta(days=rnd.randrange(-60, 300))
        r_ende = r_beginn + timedelta(days=rnd.randrange(28, 400))
        rechnungen.append(
            Rechnung(id=i + 1, kategorie=kat, betrag=_betrag(rnd),
                     beginn=r_beginn, ende=r_ende,
                     wohnung_id=rnd.choice(wohnungen).id if rnd.random() < 0.15 else None)
        )

    zaehler = []
    naechste_id = 1
    for kat in KATEGORIEN:
        if kat.braucht_zaehler:
            neue, naechste_id = _zaehlerwelt(rnd, kat, wohnungen, naechste_id)
            zaehler += neue

    zahlungen = tuple(
        Zahlung(datum=beginn + timedelta(days=30 * i), betrag=_betrag(rnd) / 12)
        for i in range(rnd.randint(0, 12))
    )

    return Vorgang(
        mieter=ich, wohnung=meine_wohnung, immobilie_id=1,
        immobilie_name=f'Objekt {nummer}', beginn=beginn, ende=ende,
        wohnungen=wohnungen, mieter_der_immobilie=mieter, profile=profile,
        rechnungen=tuple(rechnungen), zaehler=tuple(zaehler), zahlungen=zahlungen,
        wasser_kategorie_id=2,
    )


def _vorgaenge(anzahl=200, keim=20260921):
    """Die 200 Faelle. Fester Keim, damit ein Fehlschlag wiederholbar ist."""
    rnd = random.Random(keim)
    return [_vorgang(rnd, i) for i in range(anzahl)]


FAELLE = _vorgaenge()


@pytest.mark.parametrize('nummer', range(len(FAELLE)))
def test_die_zeilen_ergeben_den_gesamtbetrag(nummer):
    """R-NUM-02, erste Haelfte: die Spalte, die der Mieter nachaddiert."""
    ergebnis = rechne(FAELLE[nummer])
    zeilen = summe(z['tenant_cost'] for z in ergebnis['line_items'])
    assert zeilen == ergebnis['total_amount'], (
        f"Fall {nummer}: Zeilen ergeben {zeilen}, "
        f"ausgewiesen sind {ergebnis['total_amount']}"
    )


@pytest.mark.parametrize('nummer', range(len(FAELLE)))
def test_die_unterposten_ergeben_den_zeilenbetrag(nummer):
    """R-NUM-02, zweite Haelfte: die Restcent-Regel R1 innerhalb einer Zeile."""
    ergebnis = rechne(FAELLE[nummer])
    for zeile in ergebnis['line_items']:
        if not zeile['sub_items']:
            continue
        posten = summe(p['cost'] for p in zeile['sub_items'])
        assert posten == zeile['tenant_cost'], (
            f"Fall {nummer}, Position {zeile['category']}: Unterposten ergeben "
            f"{posten}, die Zeile weist {zeile['tenant_cost']} aus"
        )


def test_der_saldo_ist_die_differenz_und_keine_dritte_zahl():
    """Nachzahlung = die zwei Zahlen darueber, voneinander abgezogen.

    Nicht die gerundete Differenz zweier ungerundeter Zahlen: die weicht um
    einen Cent ab, sobald eine Vorauszahlung krumm hereinkommt (F-21).
    """
    for nummer, vorgang in enumerate(FAELLE):
        ergebnis = rechne(vorgang)
        assert ergebnis['balance'] == ergebnis['total_amount'] - ergebnis['prepaid_amount'], (
            f'Fall {nummer}'
        )


def test_die_vorauszahlungen_ergeben_die_ausgewiesene_summe():
    """R1 eine Ebene tiefer: die Liste der Zahlungen gegen ihre Summe."""
    for nummer, vorgang in enumerate(FAELLE):
        ergebnis = rechne(vorgang)
        einzeln = summe(z['amount'] for z in ergebnis['prepayments'])
        assert einzeln == ergebnis['prepaid_amount'], f'Fall {nummer}'


def test_jede_ausgewiesene_zahl_steht_auf_cent():
    """Kein Betrag im Ergebnis hat eine dritte Nachkommastelle."""
    for nummer, vorgang in enumerate(FAELLE):
        ergebnis = rechne(vorgang)
        betraege = [ergebnis['total_amount'], ergebnis['prepaid_amount'], ergebnis['balance']]
        betraege += [z['amount'] for z in ergebnis['prepayments']]
        for zeile in ergebnis['line_items']:
            betraege.append(zeile['tenant_cost'])
            betraege.append(zeile['prorated_amount'])
            betraege += [p['cost'] for p in zeile['sub_items']]
        for betrag in betraege:
            assert isinstance(betrag, Decimal), f'Fall {nummer}: {betrag!r} ist kein Decimal'
            assert -betrag.as_tuple().exponent <= 2, f'Fall {nummer}: {betrag} hat zu viele Stellen'


def test_die_faelle_treffen_auch_den_fall_mit_zwei_unterposten():
    """Ein Generator, der den interessanten Fall nie baut, prueft nichts.

    Zwei Unterposten entstehen nur bei `direkt` mit Wohnungszaehler *und*
    Hauptzaehler -- genau dort trat der Restcent auf.
    """
    mit_zwei = 0
    for vorgang in FAELLE:
        for zeile in rechne(vorgang)['line_items']:
            if len(zeile['sub_items']) > 1:
                mit_zwei += 1
    assert mit_zwei >= 20, f'nur {mit_zwei} Zeilen mit zwei Unterposten'
