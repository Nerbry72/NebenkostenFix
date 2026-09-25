"""Abrechnungsarten. Der eine Ort, an dem steht, welche es gibt (NK-096).

Warum es diese Datei gibt (F-25, gefunden am 21.09.2026):

Beim Bauen eines Probevorgangs bekam das Wasser die Abrechnungsart
``verbrauch``. Die gibt es nicht -- sie heisst ``direkt``. Das Ergebnis war
kein Fehler, sondern ein Blatt mit zwei statt drei Posten, ohne Warnung, mit
einer um 127,78 EUR zu niedrigen Summe. Nachgemessen am Rechenkern faellt
auch ``Qm`` durch (Grossbuchstabe) und ``direkt `` (ein Leerzeichen am Ende):
eine Rechnung ueber 1200 EUR wird aus 600,00 EUR glatt 0,00 EUR.

Der Grund war, dass die fuenf gueltigen Werte nirgends standen. Sie lagen als
Kommentar hinter der Spalte in ``models.py``, als ``elif``-Kette im
Rechenkern, als Auswahlliste in der Oberflaeche -- drei Orte, die
auseinanderlaufen koennen, und keiner davon pruefte etwas. Ein Tippfehler in
einem Skript, ein Import aus einer Fremdanwendung oder eine spaetere
Umbenennung genuegte.

Ein Absturz waere harmlos gewesen: ein Absturz wird bemerkt. Eine Abrechnung,
der eine Kostenart fehlt, sieht vollstaendig aus. Der Vermieter merkt es erst,
wenn er die Summe mit seinen Rechnungen vergleicht -- also vermutlich nie.

Hier stehen die fuenf Werte samt der Beschriftung, die der Vermieter liest,
und die Pruefung, die alle drei Wege benutzen: der Schreibweg in ``app.py``,
das Schema (``models.py`` traegt dieselbe Liste als CHECK-Bedingung) und der
Rechenkern, der einen unbekannten Wert jetzt ablehnt statt ihn zu
ueberspringen.

Zum Zurechtbiegen: ``normiere()`` nimmt Leerzeichen und Grossbuchstaben weg,
``pruefe()`` ist danach hart. Das ist die Grenze zwischen Transportrauschen
und Sachfehler -- ein Leerzeichen aus einem Formular ist keine Aussage, ein
Wort, das es nicht gibt, schon. Was in die Datenbank geht, ist immer die
normierte Form; nur deshalb darf die Bedingung im Schema hart sein.

Die Datei haengt an nichts als der Standardbibliothek -- der Rechenkern
importiert kein ORM (NK-037), und diese Regel gilt fuer seine Bausteine mit.
"""

from __future__ import annotations

__all__ = [
    'ARTEN',
    'GUELTIG',
    'VORGABE',
    'ERSATZ',
    'AbrechnungsartFehler',
    'ist_gueltig',
    'normiere',
    'pruefe',
    'aufzaehlung',
]

#: Wert in der Datenbank -> was der Vermieter dazu liest. Die Reihenfolge ist
#: die der Auswahlliste: das Haeufigste zuerst, das Ausnahmehafte zuletzt.
ARTEN = {
    'qm': 'Umlage nach Wohnfläche',
    'personen': 'Umlage nach Personen',
    'direkt': 'Nach Verbrauch (eigener Zähler)',
    'nur_allgemein': 'Nur Anteil am Allgemeinverbrauch',
    'ignoriert': 'Wird diesem Mieter nicht berechnet',
}

GUELTIG = frozenset(ARTEN)

#: Womit der Rechenkern arbeitet, wenn fuer eine Kostenart gar kein Profil
#: hinterlegt ist. Das ist kein Ersatz fuer einen falschen Wert, sondern die
#: Bedeutung von "nichts eingestellt": nach Flaeche umlegen.
VORGABE = 'qm'

#: Worauf die Wanderung einen unbrauchbaren Altbestandswert setzt. Nicht
#: ``VORGABE``: bisher fiel die Kostenart aus dem Blatt, der Mieter zahlte
#: also nichts. Auf ``qm`` umzustellen wuerde ihm beim Einspielen eines
#: Updates stillschweigend Geld berechnen. ``ignoriert`` behaelt das
#: bisherige Ergebnis bei und macht es zum ersten Mal sichtbar.
ERSATZ = 'ignoriert'


class AbrechnungsartFehler(ValueError):
    """Ein Wert, den keine der fuenf Arten kennt."""


def aufzaehlung() -> str:
    """Die gueltigen Werte fuer eine Fehlermeldung, in fester Reihenfolge."""
    return ', '.join(ARTEN)


def normiere(wert) -> str:
    """Transportrauschen wegnehmen: Leerzeichen aussen, Grossbuchstaben.

        >>> normiere('  Qm ')
        'qm'
        >>> normiere('NUR_ALLGEMEIN')
        'nur_allgemein'

    Was keine Zeichenkette ist, geht unveraendert durch -- ``pruefe()`` sagt
    dann, was daran falsch ist, statt hier an einem ``AttributeError`` zu
    sterben.

        >>> normiere(None) is None
        True
    """
    if isinstance(wert, str):
        return wert.strip().lower()
    return wert


def ist_gueltig(wert) -> bool:
    """Ob ``wert`` **genau so** eine der fuenf Arten ist -- ohne Normieren.

    Fuer Stellen, die nachsehen wollen, was wirklich gespeichert ist:
    ``'Qm'`` ist nicht gueltig, auch wenn ``normiere()`` es retten wuerde.

        >>> ist_gueltig('qm'), ist_gueltig('Qm'), ist_gueltig('verbrauch')
        (True, False, False)

    Alles, was keine Zeichenkette ist, ist schlicht ungueltig. Das ``in``
    allein wuerde an einer Liste aus dem JSON-Rumpf mit einem englischen
    ``TypeError: unhashable type`` sterben, statt dem Vermieter zu sagen,
    was er falsch eingestellt hat.

        >>> ist_gueltig(['qm']), ist_gueltig(None)
        (False, False)
    """
    return isinstance(wert, str) and wert in GUELTIG


def pruefe(wert, *, kostenart: str | None = None) -> str:
    """Die normierte Abrechnungsart -- oder ``AbrechnungsartFehler``.

        >>> pruefe(' DIREKT ')
        'direkt'

    Die Meldung nennt den abgelehnten Wert und alle gueltigen; wer eine
    Kostenart uebergibt, bekommt sie im Satz genannt, damit der Vermieter
    weiss, welche Zeile seiner Einstellungen gemeint ist.

        >>> try:
        ...     pruefe('verbrauch', kostenart='Wasser')
        ... except AbrechnungsartFehler as fehler:
        ...     print(fehler)
        Die Kostenart „Wasser“ hat die unbekannte Abrechnungsart „verbrauch“. \
Erlaubt sind: qm, personen, direkt, nur_allgemein, ignoriert.
    """
    normiert = normiere(wert)
    if ist_gueltig(normiert):
        return normiert

    gezeigt = wert if isinstance(wert, str) else repr(wert)
    wo = f'Die Kostenart „{kostenart}“ hat' if kostenart else 'Es gibt'
    raise AbrechnungsartFehler(
        f'{wo} die unbekannte Abrechnungsart „{gezeigt}“. '
        f'Erlaubt sind: {aufzaehlung()}.'
    )
