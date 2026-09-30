"""Zeit. Der eine Ort, an dem aus zwei Daten eine Anzahl Tage wird.

Warum es diese Datei gibt (R-NUM-03, entschieden am 21.09.2026):

Ein Mieter zieht am 30.06. aus, der naechste zieht am selben Tag ein. Zaehlt
man beide Zeitraeume einschliesslich ihrer Raender, bekommt der eine 182 und
der andere 185 Tage -- zusammen 367 in einem Jahr mit 366. Der Wechseltag wird
zweimal berechnet, und der Vermieter nimmt in Summe mehr ein, als angefallen
ist. Gemessen an einer Rechnung ueber 1200 EUR auf eine halbe Immobilie sind
das 1,64 EUR, die keinem der beiden Mieter zustehen.

Deshalb rechnet dieses Programm auf **halboffenen** Zeitraeumen ``[von, bis)``:
der erste Tag zaehlt, der letzte nicht. Zwei aneinandergrenzende Zeitraeume
ergeben dann zusammen genau den ganzen, ohne Ueberschneidung und ohne Luecke.

Der Preis dafuer ist eine Umrechnung an genau zwei Stellen, und um die geht es
hier. Es gibt naemlich **zwei Arten von Datumsangaben** im Bestand, und sie
sehen gleich aus:

``grenze(letzter_tag)``
    Ein **Zeitraum**, wie ihn der Vermieter eingibt und wie er auf der
    Rechnung steht: "01.01. bis 31.12." meint beide Raender. Der 31.12. wird
    zur Grenze 01.01. des Folgejahres. Das ist keine Verlaengerung -- der
    Zeitraum deckt weiterhin 365 Tage ab, er wird nur so geschrieben, dass
    man sie abziehen kann.

``mietende(auszug, ...)``
    Ein **Auszugsdatum**. Der Auszugstag zaehlt nicht mit, also ist er
    bereits die Grenze und wird **nicht** verschoben. Genau hier lag der
    Fehler: der Lader stutzt das Zeitraumende auf das Auszugsdatum, und
    danach sah ein Auszugsdatum aus wie ein Zeitraumende.

Wer eine Tageszahl braucht, nimmt ``tage()`` oder ``ueberschneidung()`` und
uebergibt Grenzen -- keine letzten Tage. Ein ``+ 1`` steht in diesem Programm
nur noch in ``grenze()``.

Fuer die Anzeige fuehrt ``letzter_tag()`` zurueck: das PDF nennt den 31.12.,
nicht den 01.01. des Folgejahres.

Die Datei haengt bewusst an nichts als ``datetime`` -- der Rechenkern
importiert kein ORM (NK-037), und diese Regel gilt fuer seine Bausteine mit.
"""

from datetime import date, timedelta

__all__ = [
    'grenze',
    'letzter_tag',
    'tage',
    'ueberschneidung',
    'mietende',
    'ein_jahr_nach',
    'HINWEIS_TAGESKONVENTION',
]

# R-NUM-03 verlangt, dass die Abrechnung die Konvention im Klartext benennt:
# der Mieter soll die Tageszahl nachrechnen koennen, statt sie glauben zu
# muessen. Der Satz steht hier und nicht im PDF-Erzeuger, weil er dieselbe
# Regel beschreibt, die dieses Modul rechnet -- wer die eine aendert, sieht
# die andere daneben. Zwei PDF-Varianten benutzen ihn.
HINWEIS_TAGESKONVENTION = (
    '<b>Zu den Tagesangaben:</b> Gezählt wird vom ersten bis zum letzten Tag '
    'des angegebenen Zeitraums, beide Tage eingeschlossen. Der Einzugstag wird '
    'also mitberechnet. Endet ein Mietverhältnis, zählt der Auszugstag nicht '
    'mehr mit – er ist bereits der erste Tag des nachfolgenden '
    'Mietverhältnisses. So wird kein Tag zweimal abgerechnet.'
)


def grenze(letzter_tag_einschliesslich: date) -> date:
    """Aus einem letzten Tag die obere Grenze ``bis`` machen.

    Fuer Zeitraeume, die einschliesslich beider Raender gemeint sind:
    Abrechnungszeitraum, Rechnungszeitraum, Ableseperiode.

        >>> grenze(date(2024, 12, 31))
        datetime.date(2025, 1, 1)
    """
    return letzter_tag_einschliesslich + timedelta(days=1)


def letzter_tag(bis: date) -> date:
    """Der Rueckweg fuer die Anzeige: aus der Grenze den letzten Tag.

        >>> letzter_tag(date(2025, 1, 1))
        datetime.date(2024, 12, 31)
    """
    return bis - timedelta(days=1)


def tage(von: date, bis: date) -> int:
    """Volle Tage in ``[von, bis)`` -- der erste zaehlt, der letzte nicht.

    Nie negativ: ein umgedrehter Zeitraum hat null Tage, nicht minus welche.

        >>> tage(date(2024, 1, 1), date(2025, 1, 1))
        366
        >>> tage(date(2024, 1, 1), date(2024, 1, 1))
        0
    """
    return max(0, (bis - von).days)


def ueberschneidung(a_von: date, a_bis: date, b_von: date, b_bis: date) -> int:
    """Gemeinsame Tage zweier halboffener Zeitraeume.

    Zwei Zeitraeume, die sich nur an einem Datum beruehren, ueberschneiden
    sich nicht -- das ist der ganze Zweck der halboffenen Rechnung.

        >>> ueberschneidung(date(2024, 1, 1), date(2024, 7, 1),
        ...                 date(2024, 7, 1), date(2025, 1, 1))
        0
    """
    return tage(max(a_von, b_von), min(a_bis, b_bis))


def mietende(auszug, wenn_offen: date) -> date:
    """Die obere Grenze eines Mietverhaeltnisses.

    Ein gesetztes Auszugsdatum geht **unveraendert** durch: der Auszugstag
    zaehlt nach R-NUM-03 nicht mit und ist damit schon die Grenze. Wer hier
    ``grenze()`` anwendet, berechnet den Wechseltag zweimal.

    ``wenn_offen`` ist die Grenze, die gilt, solange niemand ausgezogen ist --
    in aller Regel das Ende des Abrechnungs- oder Rechnungszeitraums.
    """
    return auszug if auszug is not None else wenn_offen


def ein_jahr_nach(von: date) -> date:
    """Die Grenze genau ein Jahr nach ``von`` -- der Schalttag zaehlt mit.

    Fuer die Hoechstlaenge eines Abrechnungszeitraums (§ 556 Abs. 3 BGB).
    Ein festes ``timedelta(days=365)`` waere hier falsch: es schneidet dem
    Schaltjahr einen Tag ab.

        >>> ein_jahr_nach(date(2024, 1, 1))
        datetime.date(2025, 1, 1)
        >>> ein_jahr_nach(date(2023, 1, 1))
        datetime.date(2024, 1, 1)

    Den 29.02. gibt es im Folgejahr nicht. Das Jahr endet dann am 01.03. --
    der letzte mitzaehlende Tag ist der 28.02.

        >>> ein_jahr_nach(date(2024, 2, 29))
        datetime.date(2025, 3, 1)
    """
    try:
        return von.replace(year=von.year + 1)
    except ValueError:
        return date(von.year + 1, 3, 1)
