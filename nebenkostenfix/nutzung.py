"""Nutzungsarten. Der eine Ort, an dem steht, wofuer eine Einheit da ist (NK-045).

Warum es diese Datei gibt (R-CO2-04, § 8 CO2KostAufG):

Das Kohlendioxidkostenaufteilungsgesetz teilt die CO2-Kosten der Heizung
zwischen Vermieter und Mieter auf. Fuer **Wohngebaeude** gilt das
Stufenmodell des § 5, fuer **Nichtwohngebaeude** sieht § 8 eine haelftige
Teilung vor -- bis ein Stufenmodell fuer sie in Kraft tritt, das es noch
nicht gibt. Ein gemischt genutztes Gebaeude ist nach § 3 Abs. 1 Nr. 2 und
Nr. 3 fuer jeden Teil getrennt zu behandeln.

Dieses Programm rechnet nur den Wohnteil. Das ist keine Luecke, sondern eine
Entscheidung: ein Vermieter mit ein bis fuenfzehn Einheiten hat in aller Regel
ein Wohnhaus, und ein halb richtig gerechnetes Gewerbeobjekt waere schlimmer
als gar keines. Damit die Entscheidung haelt, muss das Programm aber
**wissen**, womit es zu tun hat -- und bis NK-045 wusste es das nicht: es gab
kein Feld dafuer. Jedes Objekt sah aus wie ein Wohnhaus, und ein Vermieter,
der seine Gewerbeeinheit mit eintraegt, bekam eine Abrechnung, die nach nichts
aussah, aber nach dem falschen Gesetz gerechnet war.

Hier stehen die zwei Werte, die eine Einheit haben kann, die drei, die sich
daraus fuer ein Objekt ergeben, und der Satz, den der Vermieter liest, wenn
sein Objekt keines ist, das dieses Programm abrechnen darf.

``normiere()`` nimmt Leerzeichen und Grossbuchstaben weg, ``pruefe()`` ist
danach hart -- dieselbe Grenze zwischen Transportrauschen und Sachfehler wie
in ``abrechnungsart.py``. Was in die Datenbank geht, ist die normierte Form;
nur deshalb darf die CHECK-Bedingung im Schema hart sein.

Die Datei haengt an nichts als der Standardbibliothek -- der Rechenkern
importiert kein ORM (NK-037), und diese Regel gilt fuer seine Bausteine mit.
"""

from __future__ import annotations

__all__ = [
    'ARTEN',
    'GUELTIG',
    'VORGABE',
    'OBJEKTARTEN',
    'GEMISCHT',
    'NutzungsartFehler',
    'ist_gueltig',
    'normiere',
    'pruefe',
    'aufzaehlung',
    'objektart',
    'objektart_beschriftung',
    'ist_abrechenbar',
    'ablehnung',
]

#: Wert in der Datenbank -> was der Vermieter dazu liest. Eine Einheit ist
#: entweder Wohnraum oder sie ist es nicht; feinere Unterscheidungen
#: (Laden, Buero, Praxis) macht das Gesetz an dieser Stelle nicht.
ARTEN = {
    'wohnen': 'Wohnraum',
    'gewerbe': 'Gewerbe',
}

GUELTIG = frozenset(ARTEN)

#: Womit eine Einheit angelegt wird, wenn nichts gesagt wird, und worauf die
#: Wanderung den Altbestand setzt. Beides ist ``wohnen``: bis NK-045 gab es
#: das Feld nicht, und alles, was bisher gerechnet wurde, wurde als Wohnraum
#: gerechnet. Ein anderer Vorgabewert wuerde beim Einspielen eines Updates
#: stillschweigend das Ergebnis aendern.
VORGABE = 'wohnen'

#: Was sich fuer ein ganzes Objekt aus den Einheiten ergibt. ``gemischt``
#: steht hier zusaetzlich zu den beiden Einheitenarten -- es ist keine Art,
#: die man einer Wohnung geben koennte, sondern ein Befund ueber das Haus.
GEMISCHT = 'gemischt'

OBJEKTARTEN = {
    'wohnen': 'Wohngebäude',
    'gewerbe': 'Gewerbeobjekt',
    GEMISCHT: 'gemischt genutztes Gebäude',
    'leer': 'Objekt ohne Einheiten',
}

#: Welche Objektart dieses Programm abrechnen darf. Nur eine.
ABRECHENBAR = frozenset({'wohnen'})


class NutzungsartFehler(ValueError):
    """Ein Wert, den keine der Nutzungsarten kennt."""


def aufzaehlung() -> str:
    """Die gueltigen Werte fuer eine Fehlermeldung, in fester Reihenfolge."""
    return ', '.join(ARTEN)


def normiere(wert) -> str:
    """Transportrauschen wegnehmen: Leerzeichen aussen, Grossbuchstaben.

        >>> normiere('  Wohnen ')
        'wohnen'
        >>> normiere('GEWERBE')
        'gewerbe'

    Was keine Zeichenkette ist, geht unveraendert durch -- ``pruefe()`` sagt
    dann, was daran falsch ist.

        >>> normiere(None) is None
        True
    """
    if isinstance(wert, str):
        return wert.strip().lower()
    return wert


def ist_gueltig(wert) -> bool:
    """Ob ``wert`` **genau so** eine Nutzungsart ist -- ohne Normieren.

        >>> ist_gueltig('wohnen'), ist_gueltig('Wohnen'), ist_gueltig('buero')
        (True, False, False)

    ``gemischt`` ist keine Nutzungsart einer Einheit, sondern ein Befund
    ueber ein Objekt -- es darf nicht in der Spalte stehen.

        >>> ist_gueltig('gemischt')
        False
        >>> ist_gueltig(['wohnen']), ist_gueltig(None)
        (False, False)
    """
    return isinstance(wert, str) and wert in GUELTIG


def pruefe(wert, *, einheit: str | None = None) -> str:
    """Die normierte Nutzungsart -- oder ``NutzungsartFehler``.

        >>> pruefe(' GEWERBE ')
        'gewerbe'

    Die Meldung nennt den abgelehnten Wert und alle gueltigen; wer eine
    Einheit uebergibt, bekommt sie im Satz genannt.

        >>> try:
        ...     pruefe('buero', einheit='Wohnung 3')
        ... except NutzungsartFehler as fehler:
        ...     print(fehler)
        Die Einheit „Wohnung 3“ hat die unbekannte Nutzungsart „buero“. \
Erlaubt sind: wohnen, gewerbe.
    """
    normiert = normiere(wert)
    if ist_gueltig(normiert):
        return normiert

    gezeigt = wert if isinstance(wert, str) else repr(wert)
    wo = f'Die Einheit „{einheit}“ hat' if einheit else 'Es gibt'
    raise NutzungsartFehler(
        f'{wo} die unbekannte Nutzungsart „{gezeigt}“. '
        f'Erlaubt sind: {aufzaehlung()}.'
    )


def objektart(nutzungsarten) -> str:
    """Was ein Objekt ist, gemessen an den Nutzungsarten seiner Einheiten.

    Ein Haus aus lauter Wohnungen ist ein Wohngebaeude, eines aus lauter
    Gewerbeeinheiten ein Gewerbeobjekt, alles dazwischen ist gemischt.

        >>> objektart(['wohnen', 'wohnen'])
        'wohnen'
        >>> objektart(['gewerbe'])
        'gewerbe'
        >>> objektart(['wohnen', 'gewerbe', 'wohnen'])
        'gemischt'

    Ein Objekt ohne Einheiten ist kein Wohngebaeude und kein Gewerbeobjekt.
    Es bekommt einen eigenen Befund, damit die Meldung nicht behauptet, das
    Haus sei gewerblich, wenn schlicht noch nichts eingetragen ist.

        >>> objektart([])
        'leer'

    Leere Eintraege zaehlen als Vorgabe -- eine Wohnung aus einem Altbestand
    ohne gesetztes Feld ist Wohnraum, so wie sie bisher gerechnet wurde.

        >>> objektart(['wohnen', None, ''])
        'wohnen'
    """
    vorhanden = {normiere(a) or VORGABE for a in nutzungsarten}
    if not vorhanden:
        return 'leer'
    if len(vorhanden) == 1:
        einzige = next(iter(vorhanden))
        return einzige if einzige in GUELTIG else GEMISCHT
    return GEMISCHT


def objektart_beschriftung(art: str) -> str:
    """Was der Vermieter zu einer Objektart liest.

        >>> objektart_beschriftung('gemischt')
        'gemischt genutztes Gebäude'
    """
    return OBJEKTARTEN.get(art, art)


def ist_abrechenbar(art: str) -> bool:
    """Ob dieses Programm ein Objekt dieser Art abrechnen darf.

        >>> ist_abrechenbar('wohnen'), ist_abrechenbar('gemischt')
        (True, False)
    """
    return art in ABRECHENBAR


def ablehnung(objekt_name: str, art: str) -> str:
    """Der Satz, den der Vermieter liest, wenn sein Objekt keines ist,
    das dieses Programm abrechnen darf.

    Er sagt, was das Programm gesehen hat, warum es aufhoert, und was der
    Vermieter tun kann -- eine Absage ohne Ausweg ist keine Hilfe.

        >>> print(ablehnung('Hauptstr. 5', 'gemischt'))
        Die Immobilie „Hauptstr. 5“ ist ein gemischt genutztes Gebäude: sie \
enthält Wohn- und Gewerbeeinheiten. Für gemischt genutzte und gewerbliche \
Objekte gelten eigene Regeln (§ 8 CO2KostAufG), die dieses Programm nicht \
rechnet. Rechnen Sie den Wohnteil in einer eigenen Immobilie ab oder \
wenden Sie sich an einen Verwalter.
    """
    if art == GEMISCHT:
        befund = (f'ist ein {objektart_beschriftung(art)}: sie enthält '
                  f'Wohn- und Gewerbeeinheiten')
    elif art == 'leer':
        befund = 'hat keine Einheit, an der eine Nutzungsart hinterlegt wäre'
    else:
        befund = f'ist ein {objektart_beschriftung(art)}'

    return (
        f'Die Immobilie „{objekt_name}“ {befund}. Für gemischt genutzte und '
        f'gewerbliche Objekte gelten eigene Regeln (§ 8 CO2KostAufG), die '
        f'dieses Programm nicht rechnet. Rechnen Sie den Wohnteil in einer '
        f'eigenen Immobilie ab oder wenden Sie sich an einen Verwalter.'
    )
