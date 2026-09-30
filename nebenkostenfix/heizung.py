"""Die zentrale Heizungsanlage. Der eine Ort (NK-048).

Warum es diese Datei gibt (R-HK-02):

Heizkosten sind kein einzelner Betrag. § 7 Abs. 2 HeizkostenV zaehlt auf, was
zu den **Kosten des Betriebs der zentralen Heizungsanlage** gehoert: der
Brennstoff und seine Lieferung, der Betriebsstrom, die Bedienung, die
jaehrliche Pruefung durch eine Fachkraft, die Reinigung, die Messungen nach
dem Bundes-Immissionsschutzgesetz, die Miete fuer die Verbrauchserfassung und
deren Verwendung samt Eichung und Abrechnung. Acht Posten, in der Praxis vier
bis sechs Rechnungen von vier bis sechs Firmen -- und **alle zusammen** sind
die Masse, die nach § 7 Abs. 1 zu 50 bis 70 vom Hundert nach Verbrauch und im
Rest nach Flaeche verteilt wird.

Bis hierher kannte die Anwendung nur einzelne Kostenarten. Gas lief als
gewoehnlicher Zaehlerschluessel, die Wartungsrechnung des Heizungsbauers als
irgendeine Position nach Flaeche, der Ablesedienst als noch eine. Jede wurde
fuer sich verteilt, und damit war der Verbrauchsanteil des § 7 Abs. 1 nicht
einmal formulierbar: er bezieht sich auf die Summe, nicht auf die einzelne
Rechnung.

**Die Anlage ist deshalb eine eigene Sache im Datenmodell**, kein Etikett an
einer Kostenart. An ihr haengen die Rechnungen, an ihr haengt der
Verbrauchsanteil, und an ihr haengt spaeter die Trennung von Heizung und
Warmwasser (§ 9, NK-050) und die CO2-Aufteilung (NK-053). Ein Haus kann zwei
Anlagen haben, und eine Anlage kann Heizung, Warmwasser oder beides
versorgen -- das sind die Nummern 4, 5 und 6 des § 2 BetrKV.

**Welcher Posten des § 7 Abs. 2 eine Rechnung ist, steht an der Rechnung,
nicht an der Kostenart** (D-44). Dieselbe Kostenart "Heizung" traegt im Jahr
die Brennstoffrechnung, die Wartungsrechnung und die des Ablesedienstes; wer
die Zuordnung an die Kostenart haengt, zwingt den Vermieter, acht Kostenarten
zu pflegen, die er nie auseinanderhalten wollte. Am Vorgang ist sie eine
Frage, die sich beim Eintragen der Rechnung von selbst stellt.

**Gerechnet wird mit alldem in dieser Karte noch nicht.** NK-048 legt die
Anlage, die Zuordnung und die Grenzen des Verbrauchsanteils; die Verteilung
nach R-HK-01 kommt mit NK-049. Dasselbe Vorgehen wie bei NK-045: erst der
Datenfall, dann das Rechnen -- bei einer roten Fixture soll unterscheidbar
bleiben, ob das Schema oder die Umlage schuld ist.

Die Datei haengt an nichts als der Standardbibliothek und ``geld``. Der
Rechenkern importiert kein ORM (NK-037), und diese Regel gilt fuer seine
Bausteine mit -- dasselbe Versprechen wie in ``geld.py``, ``zeitraum.py``,
``betrkv.py``, ``haushalt.py`` und ``leerstand.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from nebenkostenfix.geld import dec, summe as geld_summe

__all__ = [
    'KOSTENARTEN',
    'SCHLUESSEL',
    'VERSORGT',
    'REIHENFOLGE',
    'HEIZUNG',
    'WARMWASSER',
    'VERBUNDEN',
    'BETRKV_NR',
    'ANTEIL_MIN',
    'ANTEIL_MAX',
    'ANTEIL_VORGABE',
    'ABLESUNG',
    'ZWISCHENABLESUNG',
    'ABLESUNGSARTEN',
    'HINWEIS_ERSATZMASSSTAB',
    'KUERZUNG_15',
    'HINWEIS_KUERZUNG_15',
    'HeizungsFehler',
    'bezeichnung',
    'ist_kostenart',
    'pruefe_kostenart',
    'ist_versorgungsart',
    'pruefe_versorgungsart',
    'betrkv_nr',
    'pruefe_anteil',
    'flaechenanteil',
    'gruppensumme',
    'teile_masse',
    'nach_verbrauch',
    'nach_flaeche',
    'WW_ZAEHLER',
    'WW_FORMEL',
    'WW_ERSATZ',
    'WW_WEGE',
    'WW_WEG_TEXT',
    'ist_warmwasserweg',
    'pruefe_warmwasserweg',
    'warmwassermenge_formel',
    'warmwassermenge_ersatz',
    'brennstoffanteil',
    'warmwasseranteil',
    'trenne_verbundene',
    'HINWEIS_ANTEIL',
    'HINWEIS_OHNE_VERBRAUCH',
    'HINWEIS_OHNE_TRENNUNG',
    'ZEILENTITEL',
    'VORSCHRIFT',
    'VERBRAUCHSART',
    'ZAEHLERART',
]

#: Die Posten des § 7 Abs. 2 HeizkostenV -> was der Vermieter dazu liest.
#: Am Verordnungstext gekuerzt: die Sache, nicht der volle Wortlaut. Wer den
#: braucht, findet ihn in der HeizkostenV (R-HK-02).
KOSTENARTEN = {
    'brennstoff': 'Brennstoff und seine Lieferung',
    'betriebsstrom': 'Betriebsstrom',
    'bedienung': 'Bedienung, Überwachung und Pflege der Anlage',
    'pruefung': 'Prüfung der Betriebsbereitschaft und Betriebssicherheit',
    'reinigung': 'Reinigung der Anlage und des Betriebsraums',
    'messung': 'Messungen nach dem Bundes-Immissionsschutzgesetz',
    'anmietung_erfassung': 'Anmietung der Ausstattung zur Verbrauchserfassung',
    'verwendung_erfassung': 'Verwendung der Verbrauchserfassung, Eichung, Abrechnung',
}

SCHLUESSEL = frozenset(KOSTENARTEN)

#: Was eine Anlage versorgt. Die drei Faelle des Gesetzes, nicht mehr:
#: nur Heizung (§ 2 Nr. 4 BetrKV), nur Warmwasser (Nr. 5) oder beides aus
#: einem Kessel (Nr. 6, die verbundene Anlage des § 9 HeizkostenV).
HEIZUNG = 'heizung'
WARMWASSER = 'warmwasser'
VERBUNDEN = 'verbunden'

#: Die Reihenfolge ist die des Gesetzes -- Nr. 4, 5, 6 des § 2 BetrKV --,
#: nicht die des Alphabets. So liest sie der Vermieter in jeder Meldung.
REIHENFOLGE = (HEIZUNG, WARMWASSER, VERBUNDEN)

VERSORGT = frozenset(REIHENFOLGE)

#: Welche Nummer des § 2 BetrKV die Anlage traegt. Die Abrechnung muss die
#: Kostenart benennen (R-DOC-01), und bei einer verbundenen Anlage ist das
#: nicht Nr. 4 und auch nicht Nr. 5, sondern Nr. 6.
BETRKV_NR = {
    HEIZUNG: 4,
    WARMWASSER: 5,
    VERBUNDEN: 6,
}

#: Was eine verbundene Anlage nach der Trennung (§ 9) hervorbringt: zwei
#: Kostenarten, jede mit eigener Vorschrift, eigener Erfassung und eigenem
#: Namen auf dem Blatt. Die vier Woerterbuecher stehen hier und nicht im
#: Rechenkern, damit Zweck und Paragraf nicht auseinanderlaufen.
#:
#: Der Rahmen ist derselbe: § 8 Abs. 1 verweist fuer die Warmwasserkosten auf
#: dieselben 50 bis 70 vom Hundert. Verschieden ist nur, **was** erfasst wird
#: -- Waerme in Kilowattstunden dort, Warmwasser in Kubikmetern hier.
ZEILENTITEL = {
    HEIZUNG: 'Heizkosten',
    WARMWASSER: 'Warmwasserkosten',
}

VORSCHRIFT = {
    HEIZUNG: '§ 7 HeizkostenV',
    WARMWASSER: '§ 8 HeizkostenV',
}

VERBRAUCHSART = {
    HEIZUNG: 'Wärmeverbrauch',
    WARMWASSER: 'Warmwasserverbrauch',
}

ZAEHLERART = {
    HEIZUNG: 'Wärmezähler',
    WARMWASSER: 'Warmwasserzähler',
}

#: Der Rahmen des § 7 Abs. 1 Satz 1 HeizkostenV: mindestens 50, hoechstens
#: 70 vom Hundert nach erfasstem Verbrauch.
ANTEIL_MIN = 50
ANTEIL_MAX = 70

#: Die Vorgabe ist die Obergrenze. Sie ist der Wert, den der Sonderfall des
#: Satzes 2 zwingend verlangt, und der, mit dem der Vermieter am wenigsten
#: falsch macht: je mehr nach Verbrauch verteilt wird, desto weniger zahlt
#: ein Mieter fuer die Waerme eines anderen.
ANTEIL_VORGABE = 70

#: Die zwei Ablesungsarten eines Zaehlerstands (NK-051, R-HK-04). Die
#: gewoehnliche Ablesung ist jeder Stand, wie er anfaellt. Die
#: **Zwischenablesung** ist der Stand zum Datum eines Nutzerwechsels -- § 9b
#: HeizkostenV verlangt sie, und nur sie misst die Grenze zwischen zwei
#: Mietverhaeltnissen. Der Kern rechnet sie nicht durch Interpolation her,
#: und wo sie fehlt, waehlt er den Ersatzmassstab ausdruecklich (D-52).
ABLESUNG = 'ablesung'
ZWISCHENABLESUNG = 'zwischenablesung'
ABLESUNGSARTEN = (ABLESUNG, ZWISCHENABLESUNG)

#: Ein Mietrand im Rechnungszeitraum ohne Zwischenablesung (NK-051, R-HK-04):
#: die Verbrauchskosten der Anlage werden fuer die betroffene Rechnung
#: zeitanteilig verteilt, und die Abrechnung sagt es -- still geschaetzt wird
#: nicht.
HINWEIS_ERSATZMASSSTAB = (
    "Für die Heizungsanlage „{anlage}“ liegt zum Nutzerwechsel am {daten} "
    "keine Zwischenablesung vor. Die Verbrauchskosten der Rechnung wurden "
    "deshalb zeitanteilig verteilt (Ersatzmaßstab nach § 9b HeizkostenV) "
    "statt nach Zählerständen. Lassen Sie bei jedem Nutzerwechsel eine "
    "Zwischenablesung machen, dann rechnet die Abrechnung wieder nach "
    "gemessenem Verbrauch."
)

#: Steht ueber der Angabe in der Oberflaeche und in der Abrechnung.
#: ``{verbrauch}`` und ``{zaehler}`` kommen aus ``VERBRAUCHSART`` und
#: ``ZAEHLERART``: derselbe Satz traegt seit NK-050 auch den Fall des § 8,
#: denn das Kuerzungsrecht des § 12 Abs. 1 gilt fuer beide Kostenarten.
HINWEIS_OHNE_VERBRAUCH = (
    "Für die Heizungsanlage „{anlage}“ ist der {verbrauch} im Zeitraum "
    "nicht vollständig erfasst ({grund}). Die Kosten wurden deshalb ganz nach "
    "Wohnfläche verteilt. Eine Abrechnung ohne Verbrauchserfassung gibt dem "
    "Mieter nach § 12 Abs. 1 HeizkostenV das Recht, seinen Anteil um 15 vom "
    "Hundert zu kürzen. Tragen Sie die {zaehler} und ihre Ablesungen nach."
)


#: Die Kennung der Kuerzungswarnung (R-HK-05, NK-052). Sie steht im Text,
#: damit Oberflaeche und PDF die Warnung wiederfinden, ohne den Satz zu
#: parsen.
KUERZUNG_15 = 'W-HKV-KUERZUNG-15'

#: § 12 Abs. 1 HeizkostenV (NK-052, R-HK-05): wird nicht oder nicht
#: ausschliesslich nach erfasstem Verbrauch abgerechnet, kann der Nutzer
#: den auf ihn entfallenden Kostenanteil um 15 vom Hundert kuerzen. Die
#: Software kuerzt nicht selbst -- sie warnt. Die Warnung steht neben der
#: Zeilenwarnung (HINWEIS_OHNE_VERBRAUCH erklaert das Missen, diese nennt
#: das Recht), einmal je betroffener Verteilmasse.
HINWEIS_KUERZUNG_15 = (
    "W-HKV-KUERZUNG-15 · Kürzungsrecht des Mieters nach § 12 Abs. 1 "
    "HeizkostenV in Höhe von 15 % möglich: Für die Heizungsanlage "
    "„{anlage}“ wurde der {verbrauch} nicht oder nicht ausschließlich nach "
    "erfasstem Verbrauch verteilt. Der Mieter kann seinen Anteil an diesen "
    "Kosten um 15 vom Hundert kürzen."
)


#: Warum die Erfassung unvollstaendig ist -- fuer ``HINWEIS_OHNE_VERBRAUCH``.
OHNE_ZAEHLER = "ohne {zaehler}: {wohnungen}"
OHNE_STAENDE = "kein abgelesener Verbrauch"


HINWEIS_ANTEIL = (
    'Von den Kosten des Betriebs der Heizungsanlage sind nach § 7 Abs. 1 '
    'HeizkostenV mindestens 50 und höchstens 70 vom Hundert nach dem '
    'erfassten Verbrauch zu verteilen, der Rest nach der Fläche.'
)


class HeizungsFehler(ValueError):
    """Eine Angabe zur Heizungsanlage, mit der nicht zu rechnen ist."""


def bezeichnung(schluessel) -> str:
    """Die Bezeichnung zum Posten -- oder ``HeizungsFehler``.

        >>> bezeichnung('betriebsstrom')
        'Betriebsstrom'
    """
    return KOSTENARTEN[pruefe_kostenart(schluessel)]


def ist_kostenart(schluessel) -> bool:
    """Ob ``schluessel`` **genau so** ein Posten des § 7 Abs. 2 ist.

        >>> ist_kostenart('brennstoff'), ist_kostenart('Brennstoff')
        (True, False)
        >>> ist_kostenart('grundsteuer'), ist_kostenart(None)
        (False, False)
    """
    return isinstance(schluessel, str) and schluessel in SCHLUESSEL


def pruefe_kostenart(schluessel) -> str:
    """Ein Posten des § 7 Abs. 2 -- hart, ohne Retten.

        >>> pruefe_kostenart('reinigung')
        'reinigung'
        >>> pruefe_kostenart('kaminkehrer')
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: „kaminkehrer" ist kein Posten des § 7 Abs. 2 HeizkostenV. Zur Wahl stehen: anmietung_erfassung, bedienung, betriebsstrom, brennstoff, messung, pruefung, reinigung, verwendung_erfassung.

    Die Aufzaehlung des § 7 Abs. 2 ist mit "insbesondere" eingeleitet und
    damit nicht abschliessend -- anders als der Katalog des § 2 BetrKV. Das
    Programm laesst trotzdem nur die acht genannten Posten zu: was sonst noch
    zu den Betriebskosten der Anlage gehoert, ist Rechtsprechung im Einzelfall
    und keine Auswahlliste. Wer etwas anderes hat, traegt es als gewoehnliche
    Kostenart ein und verteilt es nicht nach Verbrauch.
    """
    if not ist_kostenart(schluessel):
        raise HeizungsFehler(
            f'„{schluessel}" ist kein Posten des § 7 Abs. 2 HeizkostenV. '
            f'Zur Wahl stehen: {", ".join(sorted(SCHLUESSEL))}.'
        )
    return schluessel


def ist_versorgungsart(art) -> bool:
    """Ob ``art`` **genau so** eine der drei Versorgungsarten ist.

        >>> ist_versorgungsart('verbunden'), ist_versorgungsart('beides')
        (True, False)
    """
    return isinstance(art, str) and art in VERSORGT


def pruefe_versorgungsart(art) -> str:
    """Eine der drei Versorgungsarten -- hart, ohne Retten.

        >>> pruefe_versorgungsart('warmwasser')
        'warmwasser'
        >>> pruefe_versorgungsart('fernwaerme')
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Eine Heizungsanlage versorgt „heizung", „warmwasser" oder „verbunden", nicht „fernwaerme".

    Fernwaerme ist keine vierte Art: sie ist eine Lieferform des Brennstoffs
    und steht als solche in § 7 Abs. 4 HeizkostenV. Eine Anlage, die damit
    gespeist wird, versorgt trotzdem die Heizung, das Warmwasser oder beides.
    """
    if not ist_versorgungsart(art):
        erlaubt = '„%s" oder „%s"' % (
            '", „'.join(REIHENFOLGE[:-1]), REIHENFOLGE[-1])
        raise HeizungsFehler(
            f'Eine Heizungsanlage versorgt {erlaubt}, nicht „{art}".'
        )
    return art


def betrkv_nr(art) -> int:
    """Die Nummer des § 2 BetrKV zur Versorgungsart.

        >>> betrkv_nr('heizung'), betrkv_nr('warmwasser'), betrkv_nr('verbunden')
        (4, 5, 6)
    """
    return BETRKV_NR[pruefe_versorgungsart(art)]


def pruefe_anteil(prozent, sonderfall: bool = False) -> int:
    """Der Verbrauchsanteil in Prozent -- der Rahmen des § 7 Abs. 1.

        >>> pruefe_anteil(50), pruefe_anteil(70), pruefe_anteil(65)
        (50, 70, 65)
        >>> pruefe_anteil(45)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Der Verbrauchsanteil muss zwischen 50 und 70 vom Hundert liegen (§ 7 Abs. 1 HeizkostenV), nicht 45.

    Im Sonderfall des Satzes 2 -- Gebaeude ohne das Anforderungsniveau der
    Waermeschutzverordnung 1994, mit Oel- oder Gasheizung, ueberwiegend
    gedaemmte Leitungen -- *sind* 70 vom Hundert nach Verbrauch zu verteilen.
    Der Satz ist zwingend formuliert, nicht als Wahlrecht, und deshalb ist
    dann kein anderer Wert zulaessig:

        >>> pruefe_anteil(70, sonderfall=True)
        70
        >>> pruefe_anteil(60, sonderfall=True)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Liegt der Sonderfall des § 7 Abs. 1 Satz 2 HeizkostenV vor, sind 70 vom Hundert nach Verbrauch zu verteilen, nicht 60.

    ``True`` ist in Python eine Eins, hier aber keine Prozentangabe:

        >>> pruefe_anteil(True)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Der Verbrauchsanteil ist eine ganze Zahl, nicht bool.
    """
    if isinstance(prozent, bool) or not isinstance(prozent, int):
        raise HeizungsFehler(
            f'Der Verbrauchsanteil ist eine ganze Zahl, '
            f'nicht {type(prozent).__name__}.'
        )
    if not ANTEIL_MIN <= prozent <= ANTEIL_MAX:
        raise HeizungsFehler(
            f'Der Verbrauchsanteil muss zwischen {ANTEIL_MIN} und '
            f'{ANTEIL_MAX} vom Hundert liegen (§ 7 Abs. 1 HeizkostenV), '
            f'nicht {prozent}.'
        )
    if sonderfall and prozent != ANTEIL_MAX:
        raise HeizungsFehler(
            f'Liegt der Sonderfall des § 7 Abs. 1 Satz 2 HeizkostenV vor, '
            f'sind {ANTEIL_MAX} vom Hundert nach Verbrauch zu verteilen, '
            f'nicht {prozent}.'
        )
    return prozent


def flaechenanteil(prozent) -> int:
    """Was nach Flaeche geht: der Rest zu hundert (§ 7 Abs. 1 Satz 5).

        >>> flaechenanteil(70), flaechenanteil(50)
        (30, 50)
    """
    return 100 - pruefe_anteil(prozent)


def gruppensumme(posten: Iterable) -> Decimal:
    """Die Kosten des Betriebs der Anlage: die Summe aller Posten.

    ``posten`` sind Paare aus Schluessel und Betrag. Das ist die Masse, die
    R-HK-01 verteilt -- nicht die einzelne Rechnung.

        >>> from decimal import Decimal
        >>> gruppensumme([
        ...     ('brennstoff', Decimal('8200.00')),
        ...     ('betriebsstrom', Decimal('310.50')),
        ...     ('bedienung', Decimal('420.00')),
        ...     ('verwendung_erfassung', Decimal('180.00')),
        ... ])
        Decimal('9110.50')

    Ohne Posten ist die Summe null, nicht undefiniert:

        >>> gruppensumme([])
        Decimal('0')

    Ein Schluessel, den § 7 Abs. 2 nicht kennt, faellt hier auf und nicht
    erst in der Abrechnung:

        >>> gruppensumme([('gartenpflege', Decimal('100.00'))])
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: „gartenpflege" ist kein Posten des § 7 Abs. 2 HeizkostenV. Zur Wahl stehen: anmietung_erfassung, bedienung, betriebsstrom, brennstoff, messung, pruefung, reinigung, verwendung_erfassung.
    """
    betraege = []
    for schluessel, betrag in posten:
        pruefe_kostenart(schluessel)
        betraege.append(betrag)
    return geld_summe(betraege)


# ---------------------------------------------------------------------------
# Die Verteilung nach § 7 Abs. 1 (R-HK-01, NK-049)
# ---------------------------------------------------------------------------
#
# Drei Funktionen, drei Saetze des Gesetzes. Sie rechnen mit Zahlen und
# kennen weder Wohnung noch Mieter noch Rechnung -- wer sie aufruft, hat die
# Zuordnung schon getroffen. Gerundet wird hier nicht: das geschieht erst am
# Ende der Kette (R-NUM-02), sonst sammelt jede Zwischenstufe ihren halben
# Cent und die Zeile stimmt am Schluss nicht mehr mit ihren Unterposten.


def teile_masse(betrag, prozent) -> tuple:
    """``(Verbrauchsteil, Grundteil)`` der Kosten nach § 7 Abs. 1.

    ``betrag`` ist die Gruppensumme, nicht die einzelne Rechnung -- der
    Verbrauchsanteil bezieht sich auf die Kosten des Betriebs der Anlage als
    Ganzes. ``prozent`` ist der Satz des Gebaeudes, 50 bis 70.

        >>> from decimal import Decimal
        >>> teile_masse(Decimal('10000.00'), 70)
        (Decimal('7000.00'), Decimal('3000.00'))
        >>> teile_masse(Decimal('10000.00'), 50)
        (Decimal('5000.00'), Decimal('5000.00'))

    Der Grundteil ist die Differenz und nicht die zweite Multiplikation:
    so ergeben beide Teile zusammen wieder genau die Masse, auch wenn der
    Satz krumm auf den Betrag faellt.

        >>> verbrauch, grund = teile_masse(Decimal('999.99'), 65)
        >>> verbrauch + grund
        Decimal('999.9900')

    Ein Satz ausserhalb des Rahmens faellt hier auf:

        >>> teile_masse(Decimal('100.00'), 45)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Der Verbrauchsanteil muss zwischen 50 und 70 vom Hundert liegen (§ 7 Abs. 1 HeizkostenV), nicht 45.
    """
    satz = pruefe_anteil(prozent)
    verbrauchsteil = dec(betrag) * dec(satz) / dec(100)
    return verbrauchsteil, dec(betrag) - verbrauchsteil


def nach_verbrauch(verbrauchsteil, eigener, gesamt) -> Decimal:
    """Der Anteil am Verbrauchsteil (§ 7 Abs. 1 Satz 1).

    ``eigener`` und ``gesamt`` sind erfasste Waermemengen in derselben
    Einheit -- Kilowattstunden beim Waermezaehler, Striche beim
    Heizkostenverteiler. Welche es ist, spielt fuer den Bruch keine Rolle;
    er kuerzt sich heraus.

        >>> from decimal import Decimal
        >>> nach_verbrauch(Decimal('7000.00'), 1200, 6000)
        Decimal('1400.00')

    Ist nichts erfasst, gibt es nichts zu verteilen. Null ist hier eine
    Antwort und kein Fehler: wer ruft, traegt die Masse dann nach Flaeche
    (siehe ``HINWEIS_OHNE_VERBRAUCH``).

        >>> nach_verbrauch(Decimal('7000.00'), 0, 0)
        Decimal('0')
    """
    if gesamt is None or dec(gesamt) <= 0:
        return dec(0)
    return dec(verbrauchsteil) * dec(eigener) / dec(gesamt)


def nach_flaeche(grundteil, eigene_qm, gesamt_qm) -> Decimal:
    """Der Anteil am Grundteil (§ 7 Abs. 1 Satz 5).

    Der Nenner ist die Flaeche, die an der Anlage haengt -- nicht die des
    ganzen Hauses. Wer seine Waerme selbst erzeugt, nimmt an dieser Anlage
    nicht teil und zaehlt in keinem der beiden Teile mit (R-CO2-03).

        >>> from decimal import Decimal
        >>> nach_flaeche(Decimal('3000.00'), 75, 250)
        Decimal('900.00')
        >>> nach_flaeche(Decimal('3000.00'), 75, 0)
        Decimal('0')
    """
    if gesamt_qm is None or dec(gesamt_qm) <= 0:
        return dec(0)
    return dec(grundteil) * dec(eigene_qm) / dec(gesamt_qm)


# ---------------------------------------------------------------------------
# Die verbundene Anlage: Warmwasser abtrennen (§ 9, R-HK-03, NK-050)
# ---------------------------------------------------------------------------
#
# Ein Kessel, zwei Kostenarten. Die Nummern 4 und 5 des § 2 BetrKV sind
# verschiedene Betriebskosten mit verschiedenen Verteilungsregeln -- § 7 fuer
# die Waerme, § 8 fuer das Warmwasser --, und wenn beides aus derselben
# Flamme kommt, liegt trotzdem **eine** Rechnung vor. § 9 sagt, wie sie zu
# teilen ist, und zwar **vor** der Verteilung: erst die Masse trennen, dann
# jede Haelfte nach ihrer eigenen Vorschrift verteilen.
#
# Geteilt wird nach Waermemengen, nicht nach Gutduenken. Die auf das
# Warmwasser entfallende Menge Q wird gemessen; geht das nicht mit
# vertretbarem Aufwand, wird sie gerechnet; geht auch das nicht, wird sie
# geschaetzt. Drei Wege, in dieser Rangfolge -- gemessen vor gerechnet,
# gerechnet vor geschaetzt --, und welcher genommen wurde, steht in der
# Abrechnung (R-HK-03).


#: Die drei Wege des § 9 Abs. 1 und 2 zur Waermemenge des Warmwassers.
WW_ZAEHLER = 'zaehler'
WW_FORMEL = 'formel'
WW_ERSATZ = 'ersatz'

#: Die Rangfolge des Gesetzes, nicht das Alphabet.
WW_WEGE = (WW_ZAEHLER, WW_FORMEL, WW_ERSATZ)

#: Was in der Abrechnung ueber dem Warmwasseranteil steht. Der Mieter soll
#: nachrechnen koennen, warum gerade dieser Teil der Kosten auf das
#: Warmwasser entfaellt -- deshalb steht der Weg da und nicht nur das
#: Ergebnis (R-HK-03, R-DOC-01).
WW_WEG_TEXT = {
    WW_ZAEHLER: 'mit Wärmezähler gemessen (§ 9 Abs. 2 Satz 1 HeizkostenV)',
    WW_FORMEL: 'berechnet nach § 9 Abs. 2 Satz 4 HeizkostenV '
               '(Q = 2,5 · V · (tw − 10))',
    WW_ERSATZ: 'geschätzt nach § 9 Abs. 2 Satz 4 HeizkostenV '
               '(Q = 32 kWh je m² Wohnfläche)',
}

#: Die Zahlen der Formel. ``2,5`` ist die spezifische Waermekapazitaet des
#: Wassers in kWh je m3 und Kelvin, aufgerundet auf die Zahl, die die
#: Verordnung nennt; ``10`` ist die angenommene Kaltwassertemperatur in Grad.
WW_FAKTOR = Decimal('2.5')
WW_KALTWASSER_GRAD = Decimal('10')

#: Die Ersatzformel: 32 Kilowattstunden je Quadratmeter Wohnflaeche im Jahr.
WW_ERSATZ_JE_QM = Decimal('32')

#: Warum keine Trennung moeglich war -- fuer ``HINWEIS_OHNE_TRENNUNG``.
OHNE_WEG = "kein Weg zur Ermittlung der Wärmemenge angegeben"
OHNE_WERTE = "die Angaben zum gewählten Weg fehlen"
OHNE_GESAMTMENGE = "kein Gesamtverbrauch der Anlage angegeben"

#: Steht in der Abrechnung, wenn die Trennung nicht gelingt.
HINWEIS_OHNE_TRENNUNG = (
    "Die Heizungsanlage „{anlage}“ versorgt Heizung und Warmwasser gemeinsam. "
    "Nach § 9 HeizkostenV sind die Kosten vor der Verteilung zu trennen; dafür "
    "fehlen die Angaben ({grund}). Die Kosten wurden deshalb ganz als "
    "Heizkosten verteilt — das ist eine Abrechnung, die der Mieter nicht gegen "
    "sich gelten lassen muss. Tragen Sie die Wärmemenge für das Warmwasser und "
    "den Gesamtverbrauch der Anlage nach."
)


def ist_warmwasserweg(weg) -> bool:
    """Ob ``weg`` **genau so** einer der drei Wege des § 9 ist.

        >>> ist_warmwasserweg('formel'), ist_warmwasserweg('Formel')
        (True, False)
        >>> ist_warmwasserweg(None)
        False
    """
    return isinstance(weg, str) and weg in WW_WEGE


def pruefe_warmwasserweg(weg) -> str:
    """Einer der drei Wege -- hart, ohne Retten.

        >>> pruefe_warmwasserweg('zaehler')
        'zaehler'
        >>> pruefe_warmwasserweg('geschaetzt')
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Die Wärmemenge für das Warmwasser wird „zaehler", „formel" oder „ersatz" ermittelt (§ 9 HeizkostenV), nicht „geschaetzt".
    """
    if not ist_warmwasserweg(weg):
        erlaubt = '„%s" oder „%s"' % ('", „'.join(WW_WEGE[:-1]), WW_WEGE[-1])
        raise HeizungsFehler(
            f'Die Wärmemenge für das Warmwasser wird {erlaubt} ermittelt '
            f'(§ 9 HeizkostenV), nicht „{weg}".'
        )
    return weg


def warmwassermenge_formel(volumen_m3, temperatur_c) -> Decimal:
    """``Q = 2,5 · V · (tw − 10)`` in Kilowattstunden (§ 9 Abs. 2 Satz 4).

    ``volumen_m3`` ist das im Zeitraum gemessene Warmwasservolumen,
    ``temperatur_c`` die Warmwassertemperatur in Grad Celsius.

        >>> warmwassermenge_formel(120, 60)
        Decimal('15000.0')

    Das ist der Prüfwert aus R-HK-03: 2,5 · 120 · 50 = 15.000 kWh.

    Unter der angenommenen Kaltwassertemperatur von 10 Grad gibt die Formel
    keine Waermemenge mehr her, sondern eine negative Zahl. Das ist keine
    Rechnung, sondern eine falsche Angabe:

        >>> warmwassermenge_formel(120, 8)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Die Warmwassertemperatur muss über 10 Grad liegen (§ 9 Abs. 2 Satz 4 HeizkostenV), nicht 8.
    """
    grad = dec(temperatur_c)
    if grad <= WW_KALTWASSER_GRAD:
        raise HeizungsFehler(
            f'Die Warmwassertemperatur muss über {WW_KALTWASSER_GRAD:.0f} '
            f'Grad liegen (§ 9 Abs. 2 Satz 4 HeizkostenV), '
            f'nicht {temperatur_c}.'
        )
    volumen = dec(volumen_m3)
    if volumen < 0:
        raise HeizungsFehler(
            f'Das Warmwasservolumen ist keine negative Menge, '
            f'nicht {volumen_m3}.'
        )
    return WW_FAKTOR * volumen * (grad - WW_KALTWASSER_GRAD)


def warmwassermenge_ersatz(wohnflaeche_qm) -> Decimal:
    """``Q = 32 · A_Wohn`` in Kilowattstunden -- der letzte Ausweg.

        >>> warmwassermenge_ersatz(250)
        Decimal('8000')

    Auch das ist ein Prüfwert aus R-HK-03: 32 · 250 = 8.000 kWh.

    Der Weg steht in der Verordnung erst, wenn weder die Waermemenge noch
    das Volumen gemessen werden koennen. Er schaetzt den Jahresbedarf eines
    Quadratmeters und trifft damit jedes Haus gleich -- also keines genau.
    Wer ihn waehlt, weist ihn aus.

        >>> warmwassermenge_ersatz(-5)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Die Wohnfläche ist keine negative Menge, nicht -5.
    """
    flaeche = dec(wohnflaeche_qm)
    if flaeche < 0:
        raise HeizungsFehler(
            f'Die Wohnfläche ist keine negative Menge, nicht {wohnflaeche_qm}.'
        )
    return WW_ERSATZ_JE_QM * flaeche


def brennstoffanteil(waermemenge, heizwert) -> Decimal:
    """``B = Q / Hi`` -- die Waermemenge in Brennstoff umgerechnet.

    ``heizwert`` ist der Heizwert des Brennstoffs in Kilowattstunden je
    Einheit: rund 10 kWh je Liter Heizoel, rund 10 kWh je Kubikmeter Erdgas,
    rund 4,8 kWh je Kilogramm Pellets.

        >>> brennstoffanteil(Decimal('15000'), 10)
        Decimal('1500')

    Der Schritt ist nur noetig, wenn der Gesamtverbrauch in Brennstoff
    gemessen ist -- in Litern auf dem Lieferschein etwa. Liegt er ohnehin in
    Kilowattstunden vor, wie auf jeder Gasrechnung, kuerzt sich der Heizwert
    aus dem Bruch heraus und dieser Schritt entfaellt.

        >>> brennstoffanteil(Decimal('15000'), 0)
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Der Heizwert des Brennstoffs muss größer als null sein (§ 9 Abs. 2 HeizkostenV), nicht 0.
    """
    hi = dec(heizwert)
    if hi <= 0:
        raise HeizungsFehler(
            f'Der Heizwert des Brennstoffs muss größer als null sein '
            f'(§ 9 Abs. 2 HeizkostenV), nicht {heizwert}.'
        )
    return dec(waermemenge) / hi


def warmwasseranteil(menge_ww, menge_gesamt) -> Decimal:
    """Der Anteil des Warmwassers an der Masse, als Bruch zwischen 0 und 1.

    Beide Mengen stehen in derselben Einheit -- Kilowattstunden, Liter Oel,
    Kubikmeter Gas. Welche es ist, spielt fuer den Bruch keine Rolle; sie
    kuerzt sich heraus, genau wie bei ``nach_verbrauch``.

        >>> warmwasseranteil(Decimal('15000'), Decimal('60000'))
        Decimal('0.25')

    Ohne Gesamtmenge gibt es keinen Bruch und damit keine Trennung. Null ist
    hier eine Antwort und kein Fehler: wer ruft, verteilt die Masse dann ganz
    als Heizkosten und warnt (siehe ``HINWEIS_OHNE_TRENNUNG``).

        >>> warmwasseranteil(Decimal('15000'), 0)
        Decimal('0')

    Mehr Warmwasser als Gesamtverbrauch gibt es dagegen nicht. Das ist keine
    Luecke, sondern ein Widerspruch in den Angaben, und er faellt hier auf
    und nicht erst in der Abrechnung:

        >>> warmwasseranteil(Decimal('70000'), Decimal('60000'))
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Die Wärmemenge für das Warmwasser (70000) ist größer als der Gesamtverbrauch der Anlage (60000). Eine der beiden Angaben stimmt nicht.
    """
    if menge_gesamt is None or dec(menge_gesamt) <= 0:
        return dec(0)
    ww = dec(menge_ww)
    gesamt = dec(menge_gesamt)
    if ww < 0:
        raise HeizungsFehler(
            f'Die Wärmemenge für das Warmwasser ist keine negative Menge, '
            f'nicht {menge_ww}.'
        )
    if ww > gesamt:
        raise HeizungsFehler(
            f'Die Wärmemenge für das Warmwasser ({ww:f}) ist größer als der '
            f'Gesamtverbrauch der Anlage ({gesamt:f}). Eine der beiden '
            f'Angaben stimmt nicht.'
        )
    return ww / gesamt


def trenne_verbundene(betrag, anteil) -> tuple:
    """``(Warmwasserkosten, Heizkosten)`` der verbundenen Anlage (§ 9 Abs. 1).

    ``anteil`` ist der Bruch aus ``warmwasseranteil``.

        >>> from decimal import Decimal
        >>> trenne_verbundene(Decimal('10000.00'), Decimal('0.25'))
        (Decimal('2500.0000'), Decimal('7500.0000'))

    Die Heizkosten sind die Differenz und nicht die zweite Multiplikation --
    aus demselben Grund wie in ``teile_masse``: so ergeben beide Teile
    zusammen wieder genau die Masse, auch wenn der Anteil krumm faellt.

        >>> warm, heiz = trenne_verbundene(Decimal('999.99'), Decimal('1') / Decimal('3'))
        >>> warm + heiz == Decimal('999.99')
        True

    Ein Anteil ausserhalb von null bis eins ist kein Anteil:

        >>> trenne_verbundene(Decimal('100.00'), Decimal('1.5'))
        Traceback (most recent call last):
        ...
        nebenkostenfix.heizung.HeizungsFehler: Der Warmwasseranteil liegt zwischen 0 und 1, nicht 1.5.
    """
    teil = dec(anteil)
    if not 0 <= teil <= 1:
        raise HeizungsFehler(
            f'Der Warmwasseranteil liegt zwischen 0 und 1, nicht {teil:f}.'
        )
    warm = dec(betrag) * teil
    return warm, dec(betrag) - warm
