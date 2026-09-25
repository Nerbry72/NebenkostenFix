"""Fristen des § 556 Abs. 3 BGB. Der eine Ort fuer Jahresfrist und Zustellung.

Warum es diese Datei gibt (R-FRIST-01/R-FRIST-02, NK-054):

Zwei Fristen haengen an derselben Abrechnung, und beide laufen in Monaten,
nicht in Tagen:

**Die Abrechnungsfrist.** Der Vermieter muss ueber Vorauszahlungen jaehrlich
abrechnen, und die Abrechnung ist dem Mieter spaetestens bis zum Ablauf des
zwoelften Monats nach Ende des Abrechnungszeitraums mitzuteilen (§ 556
Abs. 3 BGB). Danach ist die Geltendmachung einer Nachforderung
ausgeschlossen -- es sei denn, der Vermieter hat die verspaetete
Geltendmachung nicht zu vertreten. Ob er das hat, entscheidet nicht die
Software: sie waernt und erzeugt trotzdem.

**Die Einwendungsfrist.** Der Mieter muss Einwendungen ebenfalls binnen
zwoelf Monaten nach dem **Zugang** der Abrechnung erheben. Informativ;
sie wirkt auf keine Zahl.

Zwei Festlegungen, die hier bewusst und sichtbar sind:

**Das Fristende ist ein Kalendertag, kein Grenzdatum.** ``zeitraum.py`` hat
``ein_jahr_nach`` -- ein halboffenes Grenzdatum, an dem der letzte
mitzaehlende Tag der Tag *vor* dem Ergebnis ist. Das Fristende ist das
Gegenteil: es ist der **letzte gueltige Tag selbst**. Beide rechnen
"zwolf Monate", und beide unterscheiden sich genau am Schalttag:
``ein_jahr_nach(29.02.2024)`` ist der 01.03.2025 (Grenze, der 28.02. zaehlt
mit), ``frist_ende(29.02.2024)`` ist der 28.02.2025 -- § 188 Abs. 2 BGB:
endet die Frist in einem Monat, der den Ereignistag nicht hat, mit Ablauf
des letzten Tages dieses Monats. Wer die beiden vereinheitlicht, verschiebt
eine der beiden Fristen um einen Tag.

**Die Frist haengt am Abrechnungszeitraum, nicht am Zustelldatum.** Die
Abrechnungsfrist laeuft ab, ob der Vermieter zustellt oder nicht; das
Zustelldatum ist die ehrliche Korrektur am anderen Ende -- es ist der
Beleg dafuer, wann zugriffen wurde, und traegt die Einwendungsfrist.

Die Datei haengt an nichts als ``calendar`` und ``datetime``.
"""

import calendar
from datetime import date

__all__ = [
    'FRIST_MONATE',
    'WARN_TAGE',
    'KENNUNG_VERPASST',
    'KENNUNG_NAHT',
    'KENNUNG_ZUSTELLUNG',
    'HINWEIS_VERPASST',
    'HINWEIS_NAHT',
    'HINWEIS_ZUSTELLUNG',
    'frist_ende',
    'einwendungsfrist',
    'frist_status',
    'zustellwarnung',
]

#: Zwölf Monate nach Ende des Abrechnungszeitraums (§ 556 Abs. 3 BGB).
#: Konstante, keine Einstellung: die Frist ist Gesetz, nicht Konfiguration.
FRIST_MONATE = 12

#: Wie viele Tage vor dem Fristende die Vorwarnung anfaengt (R-FRIST-02).
WARN_TAGE = 30

#: Kennung der Warnung, wenn die Frist bereits abgelaufen ist.
KENNUNG_VERPASST = 'W-FRIST-VERPASST'

#: Kennung der Vorwarnung, wenn die Frist in weniger als WARN_TAGE Tagen endet.
KENNUNG_NAHT = 'W-FRIST-30TAGE'

HINWEIS_VERPASST = (
    KENNUNG_VERPASST + ' · Die Frist zur Abrechnung nach § 556 Abs. 3 BGB war '
    'am {frist_ende:%d.%m.%Y} bereits abgelaufen. Die Abrechnung wird trotzdem '
    'erzeugt. Ist eine Nachforderung darin enthalten, ist ihre Geltendmachung '
    'grundsätzlich ausgeschlossen -- es sei denn, die verspätete Geltendmachung '
    'ist nicht zu vertreten; das beurteilt nicht die Software.'
)

HINWEIS_NAHT = (
    KENNUNG_NAHT + ' · Die Frist zur Abrechnung nach § 556 Abs. 3 BGB läuft am '
    '{frist_ende:%d.%m.%Y} ab -- {wann}.'
)

#: Kennung der Warnung, wenn der Zugang erst nach dem Fristende lag (F-37).
KENNUNG_ZUSTELLUNG = 'W-ZUSTELLUNG-NACHFRIST'

HINWEIS_ZUSTELLUNG = (
    KENNUNG_ZUSTELLUNG + ' · Die Abrechnung wurde erst am '
    '{zugestellt_am:%d.%m.%Y} zugestellt -- die Frist nach § 556 Abs. 3 BGB '
    'war am {frist_ende:%d.%m.%Y} bereits abgelaufen. Der Vermieter muss die '
    'Abrechnung so rechtzeitig zugehen lassen, dass der Mieter noch innerhalb '
    'der Frist Einwendungen erheben kann. Ist eine Nachforderung in der '
    'Abrechnung enthalten, ist ihre Geltendmachung grundsätzlich '
    'ausgeschlossen -- es sei denn, die verspätete Geltendmachung ist nicht zu '
    'vertreten; das beurteilt nicht die Software.'
)


def _heute() -> date:
    """Der heutige Tag als eigene Stelle, damit Proben ihn tauschen koennen."""
    return date.today()


def frist_ende(zeitraum_ende: date) -> date:
    """Der letzte gueltige Tag der Abrechnungsfrist: AZ-Ende + 12 Monate.

    Der Ereignistag selbst ist das Ende des Abrechnungszeitraums; er zaehlt
    nicht mit (§ 187 Abs. 1 BGB). Die Frist endet mit dem Tag des
    zwoelften Monats, der dem Ereignistag entspricht (§ 188 Abs. 2 BGB) --
    hier ist das immer derselbe Monatstag im Folgejahr.

    Hat der Zielmonat diesen Tag nicht, endet die Frist mit dem letzten Tag
    des Monats: der 29.02.2024 fuehrt zum 28.02.2025. Vergleiche
    ``zeitraum.ein_jahr_nach``, das fuer dieselbe Angabe die Grenze
    01.03.2025 liefert -- Grenze, nicht Kalendertag.

        >>> frist_ende(date(2025, 12, 31))
        datetime.date(2026, 12, 31)
        >>> frist_ende(date(2025, 1, 31))
        datetime.date(2026, 1, 31)
        >>> frist_ende(date(2024, 2, 29))
        datetime.date(2025, 2, 28)
        >>> frist_ende(date(2024, 2, 28))
        datetime.date(2025, 2, 28)
    """
    jahr = zeitraum_ende.year + 1
    monat = zeitraum_ende.month
    tag = zeitraum_ende.day
    try:
        return date(jahr, monat, tag)
    except ValueError:
        # Der Zielmonat hat den Tag nicht (29.02.): der letzte Tag des
        # Monats endet die Frist (§ 188 Abs. 2 BGB).
        return date(jahr, monat, calendar.monthrange(jahr, monat)[1])


def einwendungsfrist(zugestellt_am: date) -> date:
    """Das Ende der Einwendungsfrist des Mieters: Zugang + 12 Monate.

    Informativ (R-FRIST-03): sie wirkt auf keine Zahl. Dieselbe Arithmetik
    wie die Abrechnungsfrist, nur am Zustelldatum.

        >>> einwendungsfrist(date(2026, 1, 15))
        datetime.date(2027, 1, 15)
        >>> einwendungsfrist(date(2024, 2, 29))
        datetime.date(2025, 2, 28)
    """
    return frist_ende(zugestellt_am)


def frist_status(zeitraum_ende: date, heute: date | None = None) -> dict:
    """Wo steht die Abrechnungsfrist, wenn heute erzeugt wird?

    Gibt ein Wörterbuch mit dem Fristende, dem Kennzeichen, ob sie
    überschritten ist, und der Warnung zurück, die mit in die Abrechnung
    gehört -- oder ``None``, solange noch mehr als ``WARN_TAGE`` Tage Zeit
    sind. Überschritten heißt: der Erzeugungstag liegt nach dem Fristende;
    am Fristende selbst ist die Abrechnung noch rechtzeitig ("bis zum
    Ablauf").

        >>> s = frist_status(date(2025, 12, 31), date(2027, 1, 2))
        >>> s['frist_ende']
        datetime.date(2026, 12, 31)
        >>> s['ueberschritten']
        True
        >>> s['warnung'].startswith(KENNUNG_VERPASST)
        True

    Zwei Tage vor dem Ablauf (R-FRIST-02: weniger als 30):

        >>> s = frist_status(date(2025, 12, 31), date(2026, 12, 29))
        >>> s['ueberschritten']
        False
        >>> '2 Tagen' in s['warnung']
        True

    Am Fristende selbst läuft sie "heute" ab -- die Abrechnung ist gerade
    noch rechtzeitig:

        >>> s = frist_status(date(2025, 12, 31), date(2026, 12, 31))
        >>> s['ueberschritten']
        False
        >>> 'heute' in s['warnung']
        True

    Und mit viel Zeit steht keine Warnung:

        >>> frist_status(date(2025, 12, 31), date(2026, 6, 30))['warnung'] is None
        True
    """
    ziel = frist_ende(zeitraum_ende)
    if heute is None:
        heute = _heute()
    rest = (ziel - heute).days
    if rest < 0:
        warnung = HINWEIS_VERPASST.format(frist_ende=ziel)
    elif rest < WARN_TAGE:
        warnung = HINWEIS_NAHT.format(
            frist_ende=ziel, wann='heute' if rest == 0 else f'in {rest} Tagen')
    else:
        warnung = None
    return {'frist_ende': ziel, 'ueberschritten': rest < 0, 'warnung': warnung}


def zustellwarnung(zugestellt_am: date, zeitraum_ende: date) -> str | None:
    """Warnt, wenn der Zugang erst nach dem Ende der Frist lag (F-37).

    ``frist_status`` schaut bei der Erzeugung auf den heutigen Tag; was
    er nicht wissen kann, ist der spaetere Zugang beim Mieter. Genau den
    traegt die Zustellungsroute nach -- und hier wird er beurteilt:

    Die Nachforderung ist nach § 556 Abs. 3 BGB ausgeschlossen, wenn sie
    nicht vor Ablauf der Frist geltend gemacht wird; der Vermieter muss
    die Abrechnung deshalb so rechtzeitig zugehen lassen, dass der Mieter
    noch innerhalb der Frist Einwendungen erheben kann. Liegt der Zugang
    nach dem Fristende, warnt dieses Modul. Der Zugang **am** Fristende
    reicht noch -- dieselbe Festlegung wie bei ``frist_status``: "bis zum
    Ablauf".

    Die Warnung ist informativ (R-FRIST-03): sie wirkt auf keine Zahl und
    wird nicht gespeichert, sondern nur mit der Antwort der Route
    mitgegeben. Ob die verspaetete Geltendmachung nicht zu vertreten ist
    (§ 556 Abs. 3 S. 2 BGB), beurteilt nicht die Software.

        >>> z = zustellwarnung(date(2027, 1, 5), date(2025, 12, 31))
        >>> z.startswith(KENNUNG_ZUSTELLUNG)
        True
        >>> '31.12.2026' in z
        True
        >>> zustellwarnung(date(2026, 12, 31), date(2025, 12, 31)) is None
        True
    """
    ziel = frist_ende(zeitraum_ende)
    if zugestellt_am > ziel:
        return HINWEIS_ZUSTELLUNG.format(
            zugestellt_am=zugestellt_am, frist_ende=ziel)
    return None
