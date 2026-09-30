"""Haushaltsgroessen. Der eine Ort, an dem Koepfe zu Personentagen werden (NK-046).

Warum es diese Datei gibt (R-NUM-04):

Der Verteilschluessel "nach Personen" ist der einzige im Programm, bei dem sich
die Bezugsgroesse **waehrend** des Abrechnungszeitraums aendern kann. Eine
Wohnflaeche bleibt, ein Miteigentumsanteil bleibt -- eine Haushaltsgroesse
nicht: ein Kind wird geboren, ein Partner zieht ein, jemand zieht aus. Und
Mietverhaeltnisse fangen und hoeren mitten im Jahr an.

Bis NK-046 hat der Rechenkern an dieser Stelle **Datensaetze gezaehlt**: der
anteilige Rechnungsbetrag wurde durch die Zahl der im Zeitraum aktiven
Mietverhaeltnisse geteilt. Das ist an zwei Stellen falsch. Es sieht eine
Familie zu viert und einen Single als dasselbe an, und es gibt einem Mieter,
der im Juli eingezogen ist, denselben Nenner wie einem, der das ganze Jahr da
war. R-NUM-04 verlangt stattdessen **Personentage**: jeder Tag zaehlt so oft,
wie an ihm Personen im Haushalt lebten, und verteilt wird im Verhaeltnis der
eigenen Personentage zur Summe aller.

    Zwei Wohnungen, eine mit 3 Personen ganzjaehrig, eine mit 1 Person ab
    dem 01.07. -> 1095 : 184 Personentage.

Eine Haushaltsgroesse ist hier nie eine einzelne Zahl, sondern immer eine
**Historie**: eine Folge von Staenden, jeder mit dem Tag, ab dem er gilt. Wer
nichts eingetragen hat, hat einen Einpersonenhaushalt (``VORGABE``) -- das ist
der Wert, mit dem die Wanderung aus NK-045 den Altbestand belegt hat, und der
einzige, der nichts still veraendert.

Gerechnet wird in halboffenen Abschnitten ``[von, bis)`` wie ueberall sonst
(R-NUM-03): der Tag, ab dem ein Stand gilt, gehoert zum neuen Stand, der Tag
davor noch zum alten. Niemand wird an seinem Wechseltag doppelt gezaehlt.

Die Datei haengt an nichts als der Standardbibliothek und ``zeitraum`` -- der
Rechenkern importiert kein ORM (NK-037), und diese Regel gilt fuer seine
Bausteine mit.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, NamedTuple, Sequence

from nebenkostenfix.zeitraum import tage

__all__ = [
    'VORGABE',
    'MINDESTENS',
    'Stand',
    'HaushaltsFehler',
    'pruefe',
    'normiere',
    'personen_am',
    'abschnitte',
    'personentage',
]

#: Wie gross ein Haushalt ist, ueber den nichts eingetragen wurde. Eins --
#: nicht null: ein Mietverhaeltnis ohne Bewohner gibt es nicht, und eine Null
#: im Nenner wuerde die Umlage verschwinden lassen statt sie zu verteilen.
VORGABE = 1

#: Die kleinste eintragbare Haushaltsgroesse. Spiegelt die CHECK-Bedingung
#: ``personen >= 1`` der Tabelle ``haushaltsgroessen`` (NK-045).
MINDESTENS = 1


class Stand(NamedTuple):
    """Ab ``gueltig_ab`` leben ``personen`` Menschen in diesem Haushalt."""

    gueltig_ab: date
    personen: int


class HaushaltsFehler(ValueError):
    """Eine Haushaltsgroesse oder eine Historie, mit der nicht zu rechnen ist."""


def pruefe(personen) -> int:
    """Eine einzelne Haushaltsgroesse -- hart, ohne Retten.

        >>> pruefe(3)
        3
        >>> pruefe(0)
        Traceback (most recent call last):
        ...
        nebenkostenfix.haushalt.HaushaltsFehler: Eine Haushaltsgröße muss mindestens 1 sein, nicht 0.

    ``True`` ist in Python eine Eins, hier aber keine Haushaltsgroesse -- wer
    ein Kaestchen statt einer Zahl schickt, hat sich im Feld geirrt.

        >>> pruefe(True)
        Traceback (most recent call last):
        ...
        nebenkostenfix.haushalt.HaushaltsFehler: Eine Haushaltsgröße ist eine ganze Zahl, nicht bool.
    """
    if isinstance(personen, bool) or not isinstance(personen, int):
        raise HaushaltsFehler(
            f'Eine Haushaltsgröße ist eine ganze Zahl, nicht {type(personen).__name__}.'
        )
    if personen < MINDESTENS:
        raise HaushaltsFehler(
            f'Eine Haushaltsgröße muss mindestens {MINDESTENS} sein, nicht {personen}.'
        )
    return personen


def normiere(eintraege: Iterable) -> tuple[Stand, ...]:
    """Eine Historie in die Form bringen, in der mit ihr zu rechnen ist.

    Sortiert nach Stichtag, prueft jede Groesse und laesst keinen Stichtag
    zweimal zu -- zwei Staende ab demselben Tag sind kein Transportrauschen,
    sondern ein Widerspruch, den nur der Vermieter aufloesen kann. Im Schema
    haelt das die UNIQUE-Bedingung ``(tenant_id, gueltig_ab)`` fest.

        >>> from datetime import date
        >>> for stand in normiere([(date(2024, 7, 1), 3), (date(2024, 1, 1), 2)]):
        ...     print(stand.gueltig_ab, stand.personen)
        2024-01-01 2
        2024-07-01 3
        >>> normiere([])
        ()
    """
    staende = []
    for eintrag in eintraege:
        gueltig_ab, personen = eintrag
        if not isinstance(gueltig_ab, date):
            raise HaushaltsFehler(
                f'Ein Stichtag ist ein Datum, nicht {type(gueltig_ab).__name__}.'
            )
        staende.append(Stand(gueltig_ab, pruefe(personen)))
    staende.sort(key=lambda s: s.gueltig_ab)
    for vorher, nachher in zip(staende, staende[1:]):
        if vorher.gueltig_ab == nachher.gueltig_ab:
            raise HaushaltsFehler(
                f'Zwei Haushaltsgrößen ab demselben Tag ({vorher.gueltig_ab.isoformat()}): '
                f'{vorher.personen} und {nachher.personen}.'
            )
    return tuple(staende)


def personen_am(eintraege: Sequence, stichtag: date) -> int:
    """Wie gross der Haushalt an diesem Tag war.

    Eine Treppenfunktion: es gilt der letzte Stand, dessen Stichtag nicht in
    der Zukunft liegt. Vor dem ersten Eintrag -- und ohne jeden Eintrag --
    gilt ``VORGABE``.

        >>> from datetime import date
        >>> h = [(date(2024, 1, 1), 2), (date(2024, 7, 1), 4)]
        >>> personen_am(h, date(2024, 6, 30))
        2
        >>> personen_am(h, date(2024, 7, 1))
        4
        >>> personen_am(h, date(2023, 12, 31))
        1
        >>> personen_am([], date(2024, 5, 5))
        1
    """
    aktuell = VORGABE
    for stand in normiere(eintraege):
        if stand.gueltig_ab > stichtag:
            break
        aktuell = stand.personen
    return aktuell


def abschnitte(eintraege: Sequence, von: date, bis: date) -> tuple[tuple[date, date, int], ...]:
    """``[von, bis)`` in Stuecke schneiden, in denen der Haushalt gleich gross war.

        >>> from datetime import date
        >>> h = [(date(2024, 1, 1), 2), (date(2024, 7, 1), 4)]
        >>> for a, e, p in abschnitte(h, date(2024, 1, 1), date(2025, 1, 1)):
        ...     print(a, e, p)
        2024-01-01 2024-07-01 2
        2024-07-01 2025-01-01 4

    Ein leerer oder umgedrehter Zeitraum hat keine Abschnitte.

        >>> abschnitte(h, date(2024, 5, 1), date(2024, 5, 1))
        ()
    """
    if bis <= von:
        return ()
    staende = normiere(eintraege)
    grenzen = sorted({von, bis} | {s.gueltig_ab for s in staende if von < s.gueltig_ab < bis})
    return tuple(
        (a, e, personen_am(staende, a)) for a, e in zip(grenzen, grenzen[1:])
    )


def personentage(eintraege: Sequence, von: date, bis: date) -> int:
    """Die Personentage in ``[von, bis)`` -- jeder Tag so oft wie seine Koepfe.

    Das ist der Zaehler **und** der Summand des Nenners von R-NUM-04.

        >>> from datetime import date
        >>> personentage([(date(2024, 1, 1), 3)], date(2024, 1, 1), date(2025, 1, 1))
        1098
        >>> personentage([], date(2024, 7, 1), date(2025, 1, 1))
        184

    Ein Haushalt, der mitten im Zeitraum waechst, zaehlt anteilig:

        >>> h = [(date(2025, 1, 1), 2), (date(2025, 7, 1), 3)]
        >>> personentage(h, date(2025, 1, 1), date(2026, 1, 1))
        914
    """
    return sum(personen * tage(a, e) for a, e, personen in abschnitte(eintraege, von, bis))
