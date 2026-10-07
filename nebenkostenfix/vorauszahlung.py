"""Vorschlag zur Anpassung der Vorauszahlung nach einer Abrechnung (R-VZ-01, NK-226).

§ 560 Abs. 4 BGB: nach einer Abrechnung darf jede Seite die vereinbarte
Vorauszahlung auf eine angemessene Höhe anpassen. Angemessen ist hier der
Kostenanteil der Abrechnung je Monat, auf volle Euro gerundet, ohne
Zuschlag. Die Software schlägt vor, sie bucht nichts. Wo sie nichts
Belastbares sagen kann, nennt sie den Grund statt einer Zahl.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def _heute() -> date:
    return date.today()


def monate(beginn: date, ende: date) -> Decimal:
    """Kalendermonate im Zeitraum, angebrochene tagesgenau."""
    summe = Decimal(0)
    jahr, monat = beginn.year, beginn.month
    while (jahr, monat) <= (ende.year, ende.month):
        tage = calendar.monthrange(jahr, monat)[1]
        von = beginn.day if (jahr, monat) == (beginn.year, beginn.month) else 1
        bis = ende.day if (jahr, monat) == (ende.year, ende.month) else tage
        summe += Decimal(bis - von + 1) / tage
        jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)
    return summe


def ab_datum(stichtag: date) -> date:
    """Der Erste des übernächsten Monats: der Zugang liegt sicher davor."""
    m = stichtag.month + 2
    return date(stichtag.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)


def vorschlag(kosten, beginn: date, ende: date, auszug: date | None,
              zahlungen, stichtag: date, teilauswahl: bool = False) -> dict:
    """Der Vorschlag, oder ``{'grund': ...}``, wenn es keinen gibt.

    ``zahlungen`` sind die gebuchten Nebenkostenvorauszahlungen des Mieters
    als (Datum, Betrag); die letzte bis zum Stichtag ist die bisherige Höhe.
    """
    if teilauswahl:
        return {'grund': 'Die Abrechnung umfasst nicht alle Kostenarten mit '
                         'Rechnungen im Zeitraum, ein Monatsbetrag daraus wäre '
                         'zu niedrig.'}
    bisherige = sorted((d, b) for d, b in zahlungen if d <= stichtag)
    if not bisherige:
        return {'grund': 'Keine Nebenkostenvorauszahlung gebucht. Anpassen lässt '
                         'sich nur eine vereinbarte Vorauszahlung (§ 560 Abs. 4 BGB).'}
    ab = ab_datum(stichtag)
    if auszug is not None and auszug < ab:
        return {'grund': f'Der Auszug liegt vor dem {ab:%d.%m.%Y}.'}
    anzahl = monate(beginn, ende)
    bisher = Decimal(bisherige[-1][1])
    neu = (Decimal(kosten) / anzahl).quantize(Decimal('1'), ROUND_HALF_UP)
    return {
        'ab': ab.isoformat(),
        'bisher': f'{bisher:.2f}',
        'neu': f'{neu:.2f}',
        'kosten': f'{Decimal(kosten):.2f}',
        'monate': f'{anzahl:.2f}',
        'kuenftige': sum(1 for d, _ in zahlungen if d >= ab),
        'aenderung': neu != bisher,
    }
