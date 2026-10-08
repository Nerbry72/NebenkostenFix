"""Die Versionierung finalisierter Abrechnungen (R-DOC-02, NK-061).

Eine als final erzeugte Abrechnung ist ein zugegangenes Dokument: sie darf
nachträglich nicht stillschweigend anders berechnet werden. Deshalb schreibt
die Festsetzung einen Schnappschuss ihrer Eingangsdaten und ihres Ergebnisses
in die Datenbank -- und die Korrektur legt statt einer Änderung eine neue
Version an, die auf die ersetzte verweist.

Dieses Modul trägt drei Dinge:

* die Konstanten ``SOFTWARE_VERSION`` und ``REGEL_VERSION`` -- der Stand, der
  mit jeder Version gespeichert wird und seit NK-062 in den Fußbereich jedes
  PDFs gehört;
* ``json_sicher`` -- die eine Wandlung, die einen Vorgang und ein
  Kern-Ergebnis in JSON-verträgliche Daten überführt (Datum als ISO-Zeichen,
  Geld als Zeichenkette, Aufzählungen als Listen);
* ``schnappschuss`` -- die Zusammensetzung der beiden Snapshots für die
  Versionstabelle.

Geld wird als Zeichenkette gespeichert, nicht als Zahl: die Schnappschüsse
sollen exakt das wiedergeben, was der Kern gerechnet hat, ohne den Weg über
eine Fließkommazahl (R-NUM-01). Die Zeilen des Kerns sind ohnehin bereits
JSON-sicher aufgebaut (D-57); ``json_sicher`` trägt die Ebene darüber.
"""

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal

# Die einzige Stelle der Versionsnummer (x.y.z). Docker-Abbild, Windows-
# Installer und GitHub-Release lesen sie von hier; jeder Merge nach main
# braucht eine neue Nummer, sonst lehnt die CI den Pull Request ab.
SOFTWARE_VERSION = '0.13.0'

# Der Stand der rechtlichen Grundlage (BetrKV, HeizkostenV, CO2KostAufG),
# gegen den die Rechenregeln geprüft sind. Wer eine Regel nach neuer
# Rechtslage ändert, hebt diese Konstante im selben Zug mit. Seit NK-217 hebt
# sie auch eine Änderung, die Zahlen einer Abrechnung ändert (NK-208, NK-213):
# daran erkennt die Anwendung Abrechnungen nach älterem Stand.
REGEL_VERSION = '2026-10-06'

# NK-229 (R-DOC-03): was sich mit einem Regelstand an der Rechnung geändert
# hat, in Worten für den Vermieter. Wer REGEL_VERSION hebt, trägt hier ein,
# warum -- der Hinweis „Nach älterem Regelstand erstellt“ zeigt es an.
REGEL_AENDERUNGEN = {
    '2026-10-06': 'Der Allgemeinverbrauch (Hauptzähler minus Wohnungszähler) wird bei einem '
                  'Mieterwechsel nur noch zwischen Tagen geteilt, an denen alle Zähler abgelesen '
                  'sind, und dort nach Personentagen; die Anteile aller Parteien ergeben zusammen '
                  'genau den Allgemeinverbrauch (NK-213). Der Verbrauchsnachweis nennt die '
                  'Zählerstände genau an den Zeitraumgrenzen (NK-208).',
}


def aenderungen_seit(regelstand):
    """Die Änderungstexte aller Regelstände nach ``regelstand``, älteste zuerst."""
    return [text for stand, text in sorted(REGEL_AENDERUNGEN.items()) if stand > (regelstand or '')]


def json_sicher(objekt):
    """Wandelt einen Wert in JSON-verträgliche Daten (R-DOC-02).

    Datum und Uhrzeit werden zu ISO-Zeichen, Dezimalzahlen zu Zeichenketten,
    Aufzählungen zu Listen, Datenklassen zu Wörterbüchern. Alles andere geht
    durch, oder -- falls JSON es nicht kennt -- als Zeichenkette, damit kein
    Schnappschuss an einem einzelnen Feld scheitert.
    """
    if objekt is None or isinstance(objekt, (str, int, bool, float)):
        return objekt
    if isinstance(objekt, Decimal):
        return str(objekt)
    if isinstance(objekt, (date, datetime)):
        return objekt.isoformat()
    if is_dataclass(objekt) and not isinstance(objekt, type):
        return {schluessel: json_sicher(wert)
                for schluessel, wert in asdict(objekt).items()}
    if isinstance(objekt, Mapping):
        return {str(schluessel): json_sicher(wert)
                for schluessel, wert in objekt.items()}
    if isinstance(objekt, (list, tuple, set, frozenset)):
        return [json_sicher(wert) for wert in objekt]
    return str(objekt)


# Felder, die nur in Worten sagen, was die Zahlen daneben schon tragen.
# Ändert eine neue Fassung allein ihren Wortlaut (Zahlformat, „m²“), rechnet
# die Abrechnung gleich und braucht keine Korrektur (NK-235).
PROSA = frozenset({'description', 'rechenweg'})


def _ohne_prosa(wert):
    if isinstance(wert, Mapping):
        return {k: _ohne_prosa(v) for k, v in wert.items() if k not in PROSA}
    if isinstance(wert, list):
        return [_ohne_prosa(v) for v in wert]
    return wert


def gleich_gerechnet(alt, neu):
    """Ob zwei Ergebnisse dieselben Zahlen tragen, gleich wie sie beschrieben sind."""
    return _ohne_prosa(alt) == _ohne_prosa(neu)


def schnappschuss(vorgang, bill_data):
    """Liefert (eingangsdaten, ergebnis) für eine Version (R-DOC-02).

    Die Eingangsdaten sind der geladene Vorgang -- genau die Abschrift, auf
    der gerechnet wurde, nicht die Datenbank, die sich danach ändern kann.
    Das Ergebnis ist das volle Kern-Ergebnis mit Zeilen, Rechenweg, Belegliste,
    CO2-Ausweis und Vermieteranteil.
    """
    return json_sicher(vorgang), json_sicher(bill_data)
