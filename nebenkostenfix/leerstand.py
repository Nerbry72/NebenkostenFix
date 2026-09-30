"""Leerstand. Der eine Ort, an dem unvermietete Tage zu einem Vermieteranteil
werden (NK-047).

Warum es diese Datei gibt (R-NUM-05):

Ein Haus mit drei Wohnungen zu je 50 qm bekommt eine Grundsteuerrechnung ueber
300,00 EUR. Eine Wohnung steht das ganze Jahr leer. Der Rechenkern teilt den
Betrag nach Flaeche: 50 von 150 qm, also 100,00 EUR je vermieteter Wohnung.
Zwei Mieter zahlen zusammen 200,00 EUR -- und die restlichen 100,00 EUR
tauchen **nirgends** auf. Sie sind nicht falsch verteilt, sie sind gar nicht
verteilt: der Leerstandsanteil verschwindet zwischen den Zeilen.

Rechnerisch ist das schon richtig. Der Vermieter traegt den Leerstand, und
genau das tut er hier, weil der Nenner die volle Flaeche bleibt. Falsch ist
nur, dass es niemand sieht. Produktprinzip 3 verlangt das Gegenteil: eine
Abrechnung soll nachrechenbar sein, und nachrechnen kann nur, wer alle
Summanden kennt. Deshalb weist die Abrechnung seit NK-047 aus, welcher Teil
jeder Rechnung beim Vermieter bleibt und warum.

**Taggenau, nicht nach Belegungsstatus.** R-NUM-05 fragt in ihrer aelteren
Fassung, ob eine Wohnung im Abrechnungszeitraum "mindestens ein
ueberlappendes Mietverhaeltnis" hatte -- eine Ja/Nein-Frage. Die genuegt
nicht. Zieht ein Mieter zum 01.07. aus und niemand nach, ist die Wohnung ein
halbes Jahr vermietet und ein halbes Jahr leer; eine Ja/Nein-Antwort
verschluckt das halbe Jahr. Dieses Modul zaehlt deshalb **Tage**: fuer jede
Einheit die Tage mit laufendem Mietverhaeltnis und die ohne. Damit geht die
Rechnung auf -- die Anteile aller Mieter plus der Vermieteranteil ergeben
wieder den (zeitanteiligen) Rechnungsbetrag, auf den Cent.

**Zwei Gruende, eine Zahl waere zu wenig.** Eine Einheit ohne Mietverhaeltnis
ist entweder leer oder vom Vermieter selbst bewohnt. Beides traegt der
Vermieter, aber es sind zwei verschiedene Dinge: das eine ist ein Ausfall, das
andere sind seine eigenen Wohnkosten. ``eigennutzung`` (NK-045) unterscheidet
sie, und dieses Modul reicht die Unterscheidung bis in den Ausweis durch.

**Ueberlappende Mietverhaeltnisse zaehlen einmal.** Am Wechseltag koennen
Vormieter und Nachmieter beide in der Liste stehen. Gezaehlt wird die
**Vereinigung** der Mietzeiten, nicht ihre Summe -- sonst haette eine Wohnung
mehr belegte Tage als der Zeitraum lang ist, und der Leerstand wuerde negativ.

Gerechnet wird in halboffenen Zeitraeumen ``[von, bis)`` wie ueberall sonst
(R-NUM-03). Die Datei haengt an nichts als der Standardbibliothek und
``zeitraum`` -- der Rechenkern importiert kein ORM (NK-037), und diese Regel
gilt fuer seine Bausteine mit. Geld kommt hier nicht vor: dieses Modul zaehlt
Tage und Quadratmeter, das Multiplizieren bleibt beim Rechenkern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence, Tuple

from nebenkostenfix.zeitraum import tage

__all__ = [
    'VERMIETET',
    'EIGENNUTZUNG',
    'LEERSTAND',
    'GRUND_TEXT',
    'Einheit',
    'Bilanz',
    'belegte_tage',
    'bilanzen',
    'unbelegte_flaechentage',
]

#: Die Einheit war im ganzen Zeitraum vermietet -- kein Vermieteranteil.
VERMIETET = 'vermietet'
#: Der Vermieter bewohnt sie selbst (NK-045, ``Wohnung.eigennutzung``).
EIGENNUTZUNG = 'eigennutzung'
#: Sie stand leer -- ganz oder an einzelnen Tagen.
LEERSTAND = 'leerstand'

#: Wie die Abrechnung den Grund benennt. Die Woerter stehen hier und nicht im
#: PDF-Erzeuger, damit Oberflaeche und Dokument dasselbe sagen.
GRUND_TEXT = {
    VERMIETET: 'vermietet',
    EIGENNUTZUNG: 'Eigennutzung',
    LEERSTAND: 'Leerstand',
}


@dataclass(frozen=True)
class Einheit:
    """Eine Wohnung, wie dieses Modul sie braucht -- und nichts sonst.

    ``mietzeiten`` sind Paare ``(von, bis)`` halboffener Grenzen. Der Aufrufer
    hat sie bereits aus den Mietverhaeltnissen gebildet; ob ein Auszugsdatum
    gesetzt war oder nicht, ist hier nicht mehr zu sehen (R-NUM-03,
    ``zeitraum.mietende``).
    """

    wohnung_id: int
    name: str
    qm: float
    eigennutzung: bool = False
    mietzeiten: Sequence[Tuple[date, date]] = ()


@dataclass(frozen=True)
class Bilanz:
    """Was eine Einheit in einem Zeitraum beigetragen hat.

    ``belegt + unbelegt`` ist immer die Laenge des Zeitraums in Tagen.
    """

    wohnung_id: int
    name: str
    qm: float
    belegt: int
    unbelegt: int
    grund: str

    @property
    def traegt_der_vermieter(self) -> bool:
        return self.unbelegt > 0


def belegte_tage(mietzeiten: Iterable[Tuple[date, date]], von: date, bis: date) -> int:
    """Tage in ``[von, bis)``, an denen mindestens ein Mietverhaeltnis lief.

    Die Vereinigung, nicht die Summe: zwei Mietverhaeltnisse, die sich
    ueberschneiden, machen den Tag nicht zweimal belegt.

        >>> belegte_tage([(date(2024, 1, 1), date(2024, 7, 1))],
        ...              date(2024, 1, 1), date(2025, 1, 1))
        182
        >>> belegte_tage([(date(2024, 1, 1), date(2024, 7, 1)),
        ...               (date(2024, 6, 1), date(2025, 1, 1))],
        ...              date(2024, 1, 1), date(2025, 1, 1))
        366
        >>> belegte_tage([], date(2024, 1, 1), date(2025, 1, 1))
        0
    """
    geschnitten = []
    for m_von, m_bis in mietzeiten:
        a = max(von, m_von)
        b = min(bis, m_bis)
        if b > a:
            geschnitten.append((a, b))
    if not geschnitten:
        return 0

    geschnitten.sort()
    summe = 0
    lauf_von, lauf_bis = geschnitten[0]
    for a, b in geschnitten[1:]:
        if a > lauf_bis:
            summe += tage(lauf_von, lauf_bis)
            lauf_von, lauf_bis = a, b
        elif b > lauf_bis:
            lauf_bis = b
    return summe + tage(lauf_von, lauf_bis)


def _grund(einheit: Einheit, unbelegt: int) -> str:
    if unbelegt <= 0:
        return VERMIETET
    return EIGENNUTZUNG if einheit.eigennutzung else LEERSTAND


def bilanzen(einheiten: Iterable[Einheit], von: date, bis: date) -> list:
    """Je Einheit eine ``Bilanz`` fuer ``[von, bis)``.

    Die Reihenfolge der Eingabe bleibt erhalten: die Abrechnung listet die
    Wohnungen so auf, wie der Vermieter sie angelegt hat.
    """
    laenge = tage(von, bis)
    ergebnis = []
    for e in einheiten:
        belegt = min(belegte_tage(e.mietzeiten, von, bis), laenge)
        unbelegt = laenge - belegt
        ergebnis.append(Bilanz(
            wohnung_id=e.wohnung_id,
            name=e.name,
            qm=e.qm or 0,
            belegt=belegt,
            unbelegt=unbelegt,
            grund=_grund(e, unbelegt),
        ))
    return ergebnis


def unbelegte_flaechentage(bilanzen_: Iterable[Bilanz], grund: str = None) -> float:
    """Summe ``qm * unbelegte Tage`` -- der Zaehler des Vermieteranteils.

    Der zugehoerige Nenner ist ``Gesamtflaeche * Zeitraumlaenge``: beide
    zusammen ergeben den Bruchteil der Rechnung, der beim Vermieter bleibt.
    Ohne ``grund`` zaehlt alles Unbelegte, mit ``grund`` nur der eine Fall --
    Leerstand und Eigennutzung werden getrennt ausgewiesen.
    """
    return sum(
        b.qm * b.unbelegt
        for b in bilanzen_
        if grund is None or b.grund == grund
    )
