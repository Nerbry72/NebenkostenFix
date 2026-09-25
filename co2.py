"""Die CO2-Kostenaufteilung nach dem CO2KostAufG (NK-053, R-CO2-01/02).

Warum es diese Datei gibt: Seit dem 1. Januar 2023 teilt das
Kohlendioxidkostenaufteilungsgesetz die CO2-Kosten der Waermeversorgung
zwischen Vermieter und Nutzer -- je nach Kohlendioxidausstoss des Gebaeudes.
Je schlechter das Gebaeude, desto groesser der Vermieteranteil: das Gesetz
setzt einen Anreiz zu sanieren, nicht zu kuerzen. Der Ausstoss wird in
Kilogramm Kohlendioxid je Quadratmeter Wohnflaeche und Jahr ermittelt
(§ 5 Abs. 1 Satz 1), auf eine Nachkommastelle gerundet (Satz 3) und in die
Tabelle der Anlage eingeordnet (Abs. 2).

Dieses Modul ist der eine Ort der Tabelle und der Regeln drumherum -- im
selben Muster wie ``heizung.py`` fuer die Heizkostenverordnung. Es haengt an
keinem ORM und kennt keine Rechnungen: reine Zahlenwerkzeuge, die der
Rechenkern ruft.

Drei Feinheiten des § 5, die hier ihre Heimat haben:

* **Runden vor dem Einstufen.** 11,96 kg/m2a wird zu 12,0 gerundet und
  faellt damit in Stufe 2 -- nicht in Stufe 1. Die Nachkommastelle gehoert
  dem Wert, nicht der Tabelle.
* **Grenzen links einschliessend, rechts ausschliessend.** Ein Wert von
  genau 12,0 ist Stufe 2; 22,0 ist Stufe 4. Dasselbe Muster wie die
  halboffenen Zeiträume in ``zeitraum.py``.
* **Die anteilige Kuerzung (§ 5 Abs. 1 Satz 4).** Bei einem *vereinbarten*
  Abrechnungszeitraum von unter einem Jahr werden die Werte der
  Einstufungstabelle gekuerzt -- nicht der Ausstoss. Dass die Kuerzung an
  der Vereinbarung und nicht an der faktischen Dauer haengt, steht in F-31:
  ein Mieterwechsel macht den Zeitraum kuerzer, ohne die Tabelle zu rufen.

Der Vermieteranteil der Stufe ist kein Geld des Mieters (§ 6 CO2KostAufG);
die Software kuerzt nichts und traegt nichts -- sie rechnet die Aufteilung
und weist sie aus (R-CO2-02). Was sie unterlaesst, wenn die Emissionsdaten
fehlt, ist die blockierende Warnung ``AUSWEIS_FEHLT``.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from geld import dec


class CO2Fehler(ValueError):
    """Etwas, das keine Stufe oder kein Anteil ist, sollte einer werden."""


#: Die Kennung der blockierenden Ausweis-Warnung (R-CO2-02). Ein grosses
#: ``E-`` wie ``E-CO2-AUSWEIS-FEHLT`` markiert, was eine Abrechnung ungueltig
#: laesst, solange es fehlt -- die Vorpruefung und, sobald es sie gibt, die
#: PDF-Erzeugung behandeln E-Befunde als blockierend.
AUSWEIS_FEHLT = 'E-CO2-AUSWEIS-FEHLT'

#: Ein Jahr hat 365 Tage (D-54). Mit dieser Basis wird die Tabelle fuer
#: unterjaehrige Abrechnungszeitraeume anteilig gekuerzt (§ 5 Abs. 1 Satz 4).
JAHR = 365

#: Die Anlage (zu den §§ 5 bis 7) CO2KostAufG: ``(Grenze, Mieteranteil)``
#: je Stufe. Die Grenze ist die **obere** Grenze der Stufe in kg CO2/m2a;
#: eine Stufe umfasst alles ab der Grenze der Stufe davor bis hinunter zu
#: dieser -- 22,0 gehoert zur Stufe 4 (22 bis unter 27), nicht mehr zur
#: Stufe 3. ``None`` heisst: keine obere Grenze (Stufe 10). Der
#: Mieteranteil steht in Prozent, der Vermieteranteil ist die Differenz.
STUFEN = (
    (12, 100), (17, 90), (22, 80), (27, 70), (32, 60),
    (37, 50), (42, 40), (47, 30), (52, 20), (None, 5),
)

#: Die blockierende Warnung des R-CO2-02 (NK-053). Sie nennt die Rechnungen,
#: deren CO2-Angaben fehlen -- ohne sie ist der Ausweis des § 7
#: CO2KostAufG unvollstaendig, und die Abrechnung darf nicht als endgültig
#: gelten. Der Aufruf geschieht im Rechenkern, sobald eine im Zeitraum
#: liegende Heizkostenrechnung keine Emissions- oder Kostenangabe traegt.
HINWEIS_AUSWEIS_FEHLT = (
    "E-CO2-AUSWEIS-FEHLT · Die Abrechnung enthält Heizkostenrechnungen ohne "
    "CO2-Angaben ({rechnungen}). Ohne Emissionsmenge und CO2-Kosten der "
    "Lieferantenrechnung kann das Gebäude nicht eingestuft und der Ausweis "
    "nach § 7 CO2KostAufG nicht erteilt werden -- die Abrechnung gilt nicht "
    "als endgültig. Tragen Sie die Angaben nach."
)

__all__ = [
    'AUSWEIS_FEHLT',
    'JAHR',
    'STUFEN',
    'HINWEIS_AUSWEIS_FEHLT',
    'CO2Fehler',
    'runde_wert',
    'stufe_fuer',
    'anteile',
    'teile_aufteilung',
]


def runde_wert(wert) -> Decimal:
    """Der Ausstoss auf eine Nachkommastelle gerundet (§ 5 Abs. 1 Satz 3).

    Gerundet wird kaufmaennisch (R-NUM-01) und **vor** der Einstufung --
    genau deshalb faellt 11,96 in Stufe 2 und nicht in Stufe 1. Der Wert
    der Regelprobe ist 11,94: er bleibt 11,9 und bleibt in Stufe 1.

        >>> runde_wert(11.96)
        Decimal('12.0')
        >>> runde_wert('21.984')
        Decimal('22.0')
    """
    return dec(wert).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def stufe_fuer(wert, tage: int = JAHR) -> int:
    """Die Stufe des Ausstosses in der (gegebenenfalls gekuerzten) Tabelle.

    Wiedervorlage (R-CO2-05): Art. 5 des Gesetzes vom 23.07.2026 fuegt die
    §§ 5a-5d CO2KostAufG ein -- fuer Heizungsanlagen nach § 43 Abs. 1 GEG.
    Sie greifen fuer Abrechnungszeitraeume ab dem 1.1.2028 (Netzentgelte und
    CO2-Kosten) bzw. 1.1.2029 (Brennstoffkosten, nur bis 30 vom Hundert des
    Einsatzes). Diese Tabelle bleibt davon unberuehrt; vor dem
    Abrechnungsjahr 2028 sind die neuen Vorschriften als eigene Regeln
    aufzunehmen, damit die Stichtage nicht in Vergessenheit geraten.
    (tests/test_regelverweise.py haelt diesen Hinweis fest.)

    ``wert`` ist der Ausstoss in kg CO2/m2a -- er wird hier gerundet, denn
    das Gesetz rundet vor dem Einordnen. ``tage`` ist die Laenge des
    Abrechnungszeitraums; liegt er unter einem Jahr, werden die Werte der
    Tabelle anteilig gekuerzt (§ 5 Abs. 1 Satz 4): die Grenzen wachsen mit
    ``tage/365``. Das ist dieselbe Rechnung wie das Vergroessern des Werts,
    aber es ist die Rechnung, die das Gesetz beschreibt -- die Tabelle wird
    gekuerzt, nicht der Ausstoss.

        >>> stufe_fuer(11.94)
        1
        >>> stufe_fuer(11.96)
        2
        >>> stufe_fuer(52)
        10
    """
    wert_r = runde_wert(wert)
    verhaeltnis = Decimal(tage) / Decimal(JAHR)
    for nummer, (grenze, _) in enumerate(STUFEN, start=1):
        if grenze is None or wert_r < Decimal(grenze) * verhaeltnis:
            return nummer
    return len(STUFEN)


def anteile(stufe: int) -> tuple:
    """``(Mieteranteil, Vermieteranteil)`` der Stufe, in Prozent.

        >>> anteile(4)
        (70, 30)
        >>> anteile(10)
        (5, 95)
    """
    if not 1 <= stufe <= len(STUFEN):
        raise CO2Fehler(
            f'Die Stufe liegt zwischen 1 und {len(STUFEN)}, nicht {stufe}.')
    mieter = STUFEN[stufe - 1][1]
    return mieter, 100 - mieter


def teile_aufteilung(kosten, mieter_prozent: int) -> tuple:
    """``(Mieteranteil, Vermieteranteil)`` der CO2-Kosten in Euro.

    Derselbe Differenz-Trick wie in ``heizung.teile_masse``: der Vermieter-
    anteil ist das, was uebrig bleibt, nicht die zweite Multiplikation -- so
    ergeben beide Teile zusammen wieder genau die Kosten, auch wenn der
    Hundertsatz krumm auf den Betrag faellt.

        >>> from decimal import Decimal
        >>> mieter, vermieter = teile_aufteilung(Decimal('2000.00'), 70)
        >>> (mieter, vermieter)
        (Decimal('1400.00'), Decimal('600.00'))
        >>> summe = teile_aufteilung(Decimal('1999.99'), 5)
        >>> summe[0] + summe[1] == Decimal('1999.99')
        True

    Ein Hundertsatz ausserhalb von null bis hundert ist keiner:

        >>> teile_aufteilung(Decimal('100.00'), 150)
        Traceback (most recent call last):
        ...
        co2.CO2Fehler: Der Mieteranteil liegt zwischen 0 und 100, nicht 150.
    """
    if not 0 <= mieter_prozent <= 100:
        raise CO2Fehler(
            'Der Mieteranteil liegt zwischen 0 und 100, nicht '
            f'{mieter_prozent}.')
    kosten_d = dec(kosten)
    mieter = kosten_d * Decimal(mieter_prozent) / Decimal(100)
    return mieter, kosten_d - mieter
