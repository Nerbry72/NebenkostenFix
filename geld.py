"""Geld. Der eine Ort, an dem Euro-Betraege entstehen, gerundet und gespeichert werden.

Warum es diese Datei gibt (R-NUM-01, entschieden am 28.08.2026):

    >>> 0.1 + 0.2 == 0.3
    False

Eine Fliesskommazahl kann 12,34 EUR nicht darstellen, sie kann nur nahe
herankommen. Bei einer einzelnen Zeile faellt das nicht auf, bei einer
Abrechnung aus dreissig Positionen fehlt am Ende ein Cent, und der Mieter, der
nachrechnet, hat recht und die Software unrecht. Deshalb: Geld ist `Decimal`,
von der Eingabe bis in die Datenbank.

Drei Werkzeuge, mehr braucht es nicht:

    dec(wert)      wandelt nach Decimal, ohne unterwegs einen float zu bauen
    runde(betrag)  kaufmaennisch auf Cent -- nur beim Ausweisen einer Zeile
    Geld           der Spaltentyp fuer die Modelle

Der Rundungsmodus ist `ROUND_HALF_UP`, also 0,005 -> 0,01. Python rundet von
Haus aus anders (`ROUND_HALF_EVEN`, 0,005 -> 0,00), was statistisch schoener
und auf einer Rechnung falsch ist: der Vermieter erwartet die kaufmaennische
Rundung, die er aus jedem Kassenbon kennt. Diese Wahl ist nicht Geschmack,
sondern Vorgabe aus R-NUM-01.

Zwischenergebnisse werden **nicht** gerundet. Gerundet wird ausschliesslich
dort, wo ein Betrag als Zeile ausgewiesen wird -- und der Gesamtbetrag ist die
Summe der **gerundeten** Zeilen, nicht die gerundete Summe der ungerundeten.
Nur so stimmt die Spalte, die der Mieter nachaddiert.

Speicherung (NK-036): SQLite kennt keinen eigenen Dezimaltyp. Ein `Decimal`
geht deshalb als Zeichenkette hinein und kommt als `float` zurueck. Das ist
verlustfrei, solange der Wert hoechstens 15 signifikante Stellen hat -- bei
`Numeric(12, 2)` sind es hoechstens 12 --, und der Rueckweg ueber `repr()`
laeuft, das die kuerzeste Darstellung liefert, die wieder denselben float
ergibt. Behauptet wird das hier nicht: `tests/test_geld.py` schickt
zwanzigtausend Betraege durch eine echte SQLite-Datei und vergleicht.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import Numeric
from sqlalchemy.types import TypeDecorator

#: Die kleinste Einheit, auf die ausgewiesen wird.
CENT = Decimal('0.01')

#: Ein Nullbetrag als Decimal. Spart das `Decimal('0')` an dreissig Stellen.
NULL = Decimal('0')

#: Feinheit eines Einheitspreises (EUR je kWh oder Kubikmeter). Ein Cent je
#: Kilowattstunde waere zu grob: bei 4000 kWh im Jahr entscheidet die dritte
#: Nachkommastelle ueber vierzig Euro. Ausgewiesen wird er nur zur
#: Nachvollziehbarkeit; gerechnet wird mit dem ungerundeten Wert.
ZEHNTELCENT = Decimal('0.0001')

#: Stellen vor und nach dem Komma, wie in R-NUM-01 festgelegt.
STELLEN = 12
NACHKOMMA = 2


class GeldFehler(ValueError):
    """Etwas, das kein Betrag ist, sollte einer werden."""


def dec(wert) -> Decimal:
    """Nach `Decimal`, ohne unterwegs Genauigkeit zu verlieren.

    Ein `float` kommt hier ueber `repr()` herein, nicht ueber `Decimal(float)`.
    Der Unterschied ist der Punkt der ganzen Datei:

        >>> Decimal(0.1)
        Decimal('0.1000000000000000055511151231257827021181583404541015625')
        >>> dec(0.1)
        Decimal('0.1')

    Der zweite Wert ist der, den der Benutzer eingetippt hat. Der erste ist der,
    den die Maschine daraus gemacht hat.

    Floats sind zugelassen, weil Flaechen und Zaehlerstaende welche sind und in
    Geldrechnungen eingehen muessen. Fuer einen Euro-Betrag ist ein float als
    Eingabe ein Geruch, aber kein Fehler -- er kommt aus dem Formular.
    """
    if isinstance(wert, Decimal):
        return wert
    if wert is None:
        raise GeldFehler('Kein Betrag: None.')
    if isinstance(wert, bool):
        # bool ist in Python ein int. 12,34 EUR sind kein "wahr".
        raise GeldFehler(f'Kein Betrag: {wert!r}.')
    if isinstance(wert, int):
        return Decimal(wert)
    if isinstance(wert, float):
        if wert != wert or wert in (float('inf'), float('-inf')):
            raise GeldFehler(f'Kein endlicher Betrag: {wert!r}.')
        return Decimal(repr(wert))
    if isinstance(wert, str):
        # "1.234,50" ist die Schreibweise auf jeder deutschen Rechnung.
        text = wert.strip().replace(' ', '')
        if ',' in text:
            text = text.replace('.', '').replace(',', '.')
        try:
            zahl = Decimal(text)
        except InvalidOperation:
            raise GeldFehler(f'Kein Betrag: {wert!r}.') from None
        if not zahl.is_finite():
            raise GeldFehler(f'Kein endlicher Betrag: {wert!r}.')
        return zahl
    raise GeldFehler(f'Kein Betrag: {wert!r} ({type(wert).__name__}).')


def runde(betrag) -> Decimal:
    """Kaufmaennisch auf Cent. Nur aufrufen, wo ein Betrag ausgewiesen wird."""
    return dec(betrag).quantize(CENT, rounding=ROUND_HALF_UP)


def runde_einheitspreis(betrag) -> Decimal:
    """Einheitspreis auf vier Stellen, zum Ausweisen im Nachweis."""
    return dec(betrag).quantize(ZEHNTELCENT, rounding=ROUND_HALF_UP)


def summe(betraege) -> Decimal:
    """Summe als Decimal, auch wenn nichts zu summieren war.

    `sum()` faengt bei `0` an, einem int -- was gutgeht, aber einen Typ in die
    Kette bringt, der hier nichts verloren hat.
    """
    gesamt = NULL
    for b in betraege:
        gesamt += dec(b)
    return gesamt


def restcent_auf_letzte(teile, ziel):
    """Teilbetraege auf Cent runden, ohne dass die Summe den Zielwert verfehlt.

    Die Restcent-Regel R1 aus R-NUM-02. Ein Mieter, der die Unterposten einer
    Zeile addiert, muss auf den Zeilenbetrag kommen. Er kommt es nicht, wenn
    jeder Posten fuer sich gerundet wird:

        >>> restcent_auf_letzte([Decimal('273.965'), Decimal('1577.255')], Decimal('1851.22'))
        [Decimal('273.97'), Decimal('1577.25')]

    Einzeln gerundet waeren das 273,97 und 1577,26, zusammen 1851,23 -- einen
    Cent ueber dem Zeilenbetrag. Der Cent verschwindet nicht und wird nicht
    verteilt, er geht sichtbar auf den **letzten** Posten. Letzter, nicht
    groesster: welcher es trifft, muss vorhersagbar sein, damit zwei Laeufe
    dasselbe Blatt ergeben -- die zugesagte Reproduzierbarkeit,
    die NK-039 in einen Test giesst.

    `ziel` muss die ungerundete Summe der Teile sein. Ist es das nicht, liegt
    kein Rundungsrest vor, sondern ein Rechenfehler weiter oben -- dann darf
    ihn niemand auf einen Posten schieben:

        >>> restcent_auf_letzte([Decimal('10')], Decimal('99'))
        Traceback (most recent call last):
        ...
        geld.GeldFehler: Restcent von 89.00 EUR auf 1 Posten ist kein Rundungsrest.
    """
    gerundet = [runde(t) for t in teile]
    if not gerundet:
        return gerundet
    rest = runde(ziel) - summe(gerundet)
    if abs(rest) > CENT * len(gerundet):
        raise GeldFehler(
            f'Restcent von {rest} EUR auf {len(gerundet)} Posten '
            f'ist kein Rundungsrest.'
        )
    gerundet[-1] += rest
    return gerundet


class Geld(TypeDecorator):
    """Spaltentyp fuer Euro-Betraege: `Numeric(12, 2)`, in Python `Decimal`.

    Der Umweg ueber die Zeichenkette beim Schreiben ist Absicht. Wuerde hier
    ein `Decimal` direkt an SQLite gereicht, warnte SQLAlchemy zu Recht, dass
    der Treiber keine Dezimalzahlen kann, und konvertierte selbst ueber float.
    Dann laege der Umrechnungsweg im Dialekt statt im Projekt, und niemand
    koennte ihn pruefen. So liegt er hier, in zwei Methoden, mit einem Test.
    """

    impl = Numeric(STELLEN, NACHKOMMA)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Python -> Datenbank."""
        if value is None:
            return None
        return str(runde(value))

    def process_result_value(self, value, dialect):
        """Datenbank -> Python."""
        if value is None:
            return None
        return runde(value)


class Einheitspreis(TypeDecorator):
    """Spaltentyp fuer Einheitspreise: `Numeric(12, 4)`, in Python `Decimal`.

    Ein Dualtarif nennt auf der Rechnung einen Preis je Tarif -- 0,3582 EUR
    im Hochtarif, 0,2147 im Niedertarif. Zwei Nachkommastellen wuerden die
    Preise der Versorger auf 0,36 und 0,21 runden und damit einen Betrag
    rechnen, den niemand schuldet; die vierte Stelle ist dieselbe Feinheit,
    die `runde_einheitspreis` (ZEHNTELCENT) fuer den Ausweis im Nachweis
    benutzt. Der Umweg ueber die Zeichenkette ist derselbe wie bei `Geld`:
    SQLite kennt keinen Dezimaltyp, und die Umrechnung gehoert hierher, in
    eine pruefbare Methode -- nicht in den Dialekt (NK-036).
    """

    impl = Numeric(STELLEN, 4)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Python -> Datenbank, auf die vierte Stelle gerundet."""
        if value is None:
            return None
        return str(runde_einheitspreis(value))

    def process_result_value(self, value, dialect):
        """Datenbank -> Python, auf die vierte Stelle gerundet."""
        if value is None:
            return None
        return runde_einheitspreis(value)
