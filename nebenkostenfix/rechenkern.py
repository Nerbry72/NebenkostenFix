"""Der Rechenkern der Nebenkostenabrechnung -- ohne Datenbank (NK-037).

Bis zu dieser Karte rechnete ``billing_engine.py`` mitten im Rechnen:
``Tenant.query.get``, ``Meter.query.filter_by``, ``db.or_`` standen zwischen
den Zeilen, die Geld verteilen. Wer eine Umlage pruefen wollte, brauchte eine
Flask-App, eine Sitzung, ein Schema und einen aufgebauten Objektgraphen. Das
ist der Grund, warum es fuer die Rechenregeln bisher keine
Stichprobe ueber hundert Faelle gab: jeder Fall kostete einen halben Graphen.

Hier steht nur noch das Rechnen. Das Modul importiert ``geld`` und die
Standardbibliothek, sonst nichts -- kein ``models``, kein ``db``, kein
``flask``. Die Eingabe ist ein ``Vorgang``: eine flache, eingefrorene
Abschrift dessen, was eine Abrechnung an Daten braucht. Wer ihn baut, steht in
``abrechnungsdaten.py``; dort und nur dort wird gefragt.

Was das einbringt:

* Ein Fall ist ein Datensatz, kein Objektgraph. NK-038 kann damit 200
  Zufallsfaelle durchrechnen, NK-039 zweimal denselben und die Ergebnisse
  vergleichen.
* Der Lesende sieht, woran eine Zahl haengt: am ``Vorgang``, an nichts sonst.
  Kein Nachladen im Hintergrund, keine Reihenfolgeabhaengigkeit.

Was diese Karte **nicht** tut: das Verhalten aendern. Die Umlageschleife ist
Zeile fuer Zeile dieselbe, samt ihrer Eigenheiten -- der Verbrauch bleibt
``float`` (nur Geld ist ``Decimal``) und die Tageszaehlung bleibt uneinheitlich
(NK-041 raeumt das auf). Ein Refactoring, das nebenbei Zahlen aendert, ist kein
Refactoring. Die Charakterisierungstests aus NK-003 sind das Netz darunter.

Der Ablauf im Bild -- rechne()
------------------------------

Das Bild stand bis NK-037 ueber ``billing_engine.py`` (NK-033). Es gehoert
dorthin, wo gerechnet wird, also hierher. Die Namen sind nachgezogen, der Weg
ist derselbe.

  Eingabe: ein Vorgang. Sein Zeitraum ist schon auf das Mietverhaeltnis
  gestutzt -- Einzug nach dem Beginn zieht den Beginn hoch, Auszug vor dem
  Ende zieht das Ende runter. Das erledigt der Lader.
      |
      v
  Umlageprofile des Mieters: kategorie_id -> billing_type.
  Fehlt fuer eine Kategorie das Profil, gilt 'qm'.
      |
      v
  rechnungen_im_umfang(): die Rechnungen des Zeitraums, eingeschraenkt auf
  kategorien_filter, wenn eine Auswahl uebergeben wurde. Der Vorgang traegt
  immer alle -- pruefe() braucht sie ungefiltert.
      |
      v
  flaechen_pruefung(): Gesamtflaeche und Befunde
      |   'warning' -> wandert in die Warnungen und spaeter in den Bericht
      |   'blocker' -> nur gemerkt. Geworfen wird er erst, wenn wirklich eine
      |                Position nach qm umgelegt werden soll (s.u.).
      v
  +---------------------- fuer jede Rechnung ----------------------+
  |                                                                 |
  |  Ueberschneidung mit dem Zeitraum?  nein -> Rechnung faellt raus |
  |      |                                                          |
  |      v                                                          |
  |  anteilig = betrag * (ueberschneidungstage / rechnungstage)     |
  |      |                                                          |
  |      v                                                          |
  |  welcher Weg?                                                   |
  |                                                                 |
  |   wohnung_id gesetzt (Rechnung gehoert einer Wohnung)           |
  |       fremde Wohnung -> Rechnung faellt raus                    |
  |       eigene Wohnung -> 100 % des anteiligen Betrags            |
  |                                                                 |
  |   'qm'             blocker aus flaechen_pruefung -> BillingDataError
  |                    sonst anteilig * (Wohnflaeche / Gesamtflaeche)
  |                                                                 |
  |   'personen'       voller Betrag * eigene / alle Personentage   |
  |                                                                 |
  |   'direkt'         ueber Zaehler -- zweites Bild unten          |
  |   'nur_allgemein'                                               |
  |                                                                 |
  |   'ignoriert'      0,00 EUR, Position bleibt trotzdem sichtbar  |
  |                                                                 |
  |      |                                                          |
  |      v                                                          |
  |  Position bauen: Beschreibung, sub_items (Eigenverbrauch und    |
  |  Anteil Allgemein getrennt), meter_details, Belegname --        |
  |  und den Betrag auf die Summe addieren                          |
  +-----------------------------------------------------------------+
      |
      v
  Vorauszahlungen des Mieters im Zeitraum summieren
      |
      v
  balance = Summe der Positionen - Vorauszahlungen
      |
      v
  Ausgabe: line_items, total_amount, prepayments, prepaid_amount,
           balance, warnings

Eine Position mit 0,00 EUR verschwindet nicht immer: bei 'direkt',
'ignoriert' und 'nur_allgemein' bleibt sie stehen. Ein Mieter soll sehen, dass
die Kategorie bedacht wurde, statt sie im Bericht zu vermissen.

Der Zaehlerweg -- 'direkt' und 'nur_allgemein'
----------------------------------------------

  Kategorie mit Zaehler (braucht_zaehler) oder Abwasser?
      nein -> 0,00 EUR, "Nur Allgemein (Fehler: Kategorie hat keinen Zaehler)"
      ja
      |
      v
  Abwasser wird am Wasserzaehler gemessen, nicht an einem eigenen. Traegt der
  Vorgang eine wasser_kategorie_id, rechnet der Zweig ab hier auf deren
  Zaehlern.
      |
      v
  Hauptzaehler der Immobilie vorhanden?
      |
      +-- ja --> Allgemein = max(0, Hauptzaehler - Summe aller Wohnungszaehler)
      |          Preis je Einheit = betrag / Hauptzaehlerverbrauch
      |          Die Allgemeinkosten werden nach Personentagen verteilt, nicht
      |          nach Koepfen: wer zwei Monate im Jahr da war, traegt zwei
      |          Monate.
      |             'direkt' mit eigenem Zaehler
      |                 -> Eigenverbrauch * Preis + Anteil Allgemein
      |             sonst
      |                 -> nur der Anteil Allgemein
      |
      +-- nein -> Preis je Einheit = betrag / Summe der Wohnungszaehler
                  'direkt' mit eigenem Zaehler
                      -> Eigenverbrauch * Preis (ohne Allgemein-Anteil, weil
                         ohne Hauptzaehler niemand weiss, wie gross er ist)
                  sonst
                      -> 0,00 EUR, "Entfaellt, da kein Hauptzaehler existiert"

Zaehlerstaende liegen selten genau auf den Stichtagen. verbrauch_detail()
rechnet deshalb zwischen den beiden umliegenden Staenden linear und gibt neben
dem Verbrauch immer mit aus, wie weit der naechste echte Stand vom Stichtag
entfernt lag (TOLERANCE_DAYS als Mass fuer "noch gut"). Die Ampel in pruefe()
und die Anzeige im Bericht haengen an genau diesen Feldern.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from nebenkostenfix.abrechnungsart import VORGABE, aufzaehlung, ist_gueltig
from nebenkostenfix import betrkv
from nebenkostenfix import co2
from nebenkostenfix.geld import NULL, dec, restcent_auf_letzte, runde, runde_einheitspreis, summe
from nebenkostenfix import heizung
from nebenkostenfix.haushalt import Stand as Haushaltsstand
# Zwei Vorgaben mit demselben Namen, aber verschiedenen Dingen: die
# Abrechnungsart 'qm' fuer Kostenarten ohne Profil (oben), und die
# Haushaltsgrösse 1 fuer Haushalte ohne Eintrag (NK-046). Das Alias folgt
# dem Muster der Nutzungsart darunter.
from nebenkostenfix.haushalt import VORGABE as HAUSHALT_VORGABE, personentage
from nebenkostenfix.leerstand import EIGENNUTZUNG, GRUND_TEXT, LEERSTAND
from nebenkostenfix.leerstand import Einheit as Leerstandseinheit
from nebenkostenfix.leerstand import bilanzen as leerstandsbilanzen
from nebenkostenfix.leerstand import unbelegte_flaechentage
from nebenkostenfix.nutzung import VORGABE as NUTZUNG_VORGABE
from nebenkostenfix.nutzung import ablehnung as nutzungs_ablehnung
from nebenkostenfix.nutzung import ist_abrechenbar, objektart
from nebenkostenfix.zeitraum import grenze, letzter_tag, mietende, tage, ueberschneidung

#: Fenster fuer die Zaehlerstandssuche, unveraendert aus BillingEngine.
TOLERANCE_DAYS = 10


class BillingDataError(Exception):
    """Die Stammdaten reichen fuer diese Abrechnung nicht aus.

    Traegt eine fertige deutsche Meldung fuer den Vermieter. Die Routen in
    app.py geben sie als 400 zurueck, nicht als 500 mit Stacktrace (NK-027).
    Sie steht hier und nicht in ``billing_engine.py``, weil der Kern sie wirft;
    ``billing_engine`` reicht den Namen nur weiter, damit bestehende Importe
    und ``except``-Zweige unveraendert bleiben.
    """


# ---------------------------------------------------------------------------
# Die Eingabe: ein Vorgang
# ---------------------------------------------------------------------------
#
# Alle Bestandteile sind eingefroren. Das ist keine Zierde: der Kern darf seine
# Eingabe nicht veraendern, sonst haengt das Ergebnis des zweiten Aufrufs am
# ersten -- genau die Eigenschaft, die NK-039 ausschliessen soll.


@dataclass(frozen=True)
class Stand:
    """Ein Zaehlerstand. ``wert_nt`` ist der Niedertarif, meist None.

    ``art`` ist die Ablesungsart (NK-051, R-HK-04): die gewoehnliche
    Ablesung, oder -- nur zum Datum eines Nutzerwechsels -- die
    Zwischenablesung, die die Grenze zwischen zwei Mietverhaeltnissen
    misst (§ 9b HeizkostenV).
    """

    datum: date
    wert: float
    wert_nt: Optional[float] = None
    art: str = heizung.ABLESUNG

    @property
    def gesamt(self) -> Decimal:
        """Hoch- plus Niedertarif als Decimal -- so rechnete es die Engine."""
        return Decimal(str(self.wert)) + Decimal(str(self.wert_nt or 0))


@dataclass(frozen=True)
class Zaehler:
    id: int
    nummer: str
    kategorie_id: int
    kategorie_name: str
    ist_hauptzaehler: bool
    immobilie_id: int
    wohnung_id: Optional[int] = None
    staende: tuple = ()
    # Fuer welche Heizungsanlage dieser Zaehler erfasst (NK-049, D-45).
    # None heisst: fuer keine -- der Regelfall. Ein gesetzter Wert macht ihn
    # zum Zaehler dieser Anlage, und nur solche Zaehler bilden den Nenner des
    # Verbrauchsanteils nach § 7 Abs. 1 Satz 1. Seit NK-050 entscheidet die
    # Einheit, was er zaehlt: Kubikmeter das Warmwasser (§ 8), sonst die
    # Waerme (§ 7) -- siehe ist_warmwasserzaehler.
    heizungsanlage_id: Optional[int] = None
    # Die BetrKV-Nummer der Kostenart dieses Zaehlers (NK-121, F-51). Aus
    # ihr kommt die Einheit -- nicht aus dem Namen: die verbundene Anlage
    # (Nr. 6) heisst "Warmwasser" und misst trotzdem Kilowattstunden.
    # None heisst: eine Probe ohne Katalog, dann raet der Name.
    kategorie_betrkv_nr: Optional[int] = None


@dataclass(frozen=True)
class Kategorie:
    id: int
    name: str
    braucht_zaehler: bool
    #: Nummer nach § 2 BetrKV (NK-044); ``None`` bei Proben ohne Katalog.
    betrkv_nr: Optional[int] = None


#: § 2 Nr. 3 BetrKV, im Katalog „Entwässerung“.
BETRKV_NR_ENTWAESSERUNG = 3


def ist_abwasser(kategorie: Kategorie) -> bool:
    """Wird die Kostenart am Frischwasser gemessen (NK-114, D-56)?

    Entscheidet die Katalognummer: Nr. 3 ist das Abwasser, ausser dem
    Niederschlagswasser, das nach Flaeche geht und an keinem Zaehler haengt.
    Bis NK-114 fragte der Rechenkern den Namen nach „abwasser“ ab -- seit
    dem Katalog (NK-044) heisst die Nr. 3 aber „Entwässerung“, und die
    Position fiel still auf 0,00. Ohne Nummer (Proben ohne Katalog) bleibt
    der Name die Auskunft.
    """
    name = (kategorie.name or '').lower()
    # Der Katalog kennt das Niederschlagswasser als eigenen Eintrag der
    # Nr. 3 (NK-117, D-72); woran es zu erkennen ist, sagt betrkv.
    if betrkv.ist_niederschlag(kategorie.name):
        return False
    if kategorie.betrkv_nr is not None:
        return kategorie.betrkv_nr == BETRKV_NR_ENTWAESSERUNG
    return any(x in name for x in ('abwasser', 'schmutzwasser', 'entwäss'))


@dataclass(frozen=True)
class Beleg:
    """Der Nachweis zu einer Rechnung, in beiden Formen des Altbestands.

    Entweder haengt ein ``InvoiceDocument`` daran (``dateiname``/``pfad``,
    dazu die Seitenangabe) oder nur ein Dateipfad aus der Zeit davor
    (``pfad_alt``). Welche Form gewinnt, entscheidet ``beleg_angabe``.
    """

    dateiname: Optional[str] = None
    pfad: Optional[str] = None
    seiten: Optional[str] = None
    pfad_alt: Optional[str] = None


@dataclass(frozen=True)
class Rechnung:
    id: int
    kategorie: Kategorie
    betrag: Decimal
    beginn: date
    ende: date
    wohnung_id: Optional[int] = None
    nummer: Optional[str] = None
    versorger_id: Optional[int] = None
    versorger_name: Optional[str] = None
    # Das Datum des Belegs (NK-058), wie er es ausweist. NULL heisst: nicht
    # angegeben -- der Kern rechnet damit nicht, die Belegliste weist es
    # aus, wo es da ist, und schweigt, wo es fehlt.
    rechnungsdatum: Optional[date] = None
    beleg: Beleg = field(default_factory=Beleg)
    # Zu welcher Heizungsanlage diese Rechnung gehoert und welcher der acht
    # Posten des § 7 Abs. 2 HeizkostenV sie ist (NK-048, D-44). Beides steht
    # an der Rechnung, nicht an der Kostenart: dieselbe Kostenart "Heizung"
    # traegt im Jahr den Brennstoff, die Wartung und den Ablesedienst.
    heizungsanlage_id: Optional[int] = None
    heizkostenart: Optional[str] = None
    # Die CO2-Angaben der Lieferantenrechnung (NK-053): Emissionsmenge in
    # kg und CO2-Kosten in Euro, wie der Beleg sie ausweist. ``None`` heisst
    # keine Angabe -- und ohne Angabe gibt es keine Einstufung, sondern die
    # blockierende Warnung des R-CO2-02. Emissionen zu rechnen statt zu
    # uebernehmen waere ein erfundener Messwert (D-54).
    co2_kosten: Optional[Decimal] = None
    co2_emission_kg: Optional[Decimal] = None
    # Die Preise je Tarif einer Dualtarifrechnung (NK-055). ``None`` heisst
    # Einheitstarif oder keine Angabe -- dann faellt der Zaehlerweg auf den
    # einen Mischpreis zurueck, den es vor dieser Karte gab. Der Betrag der
    # Rechnung bleibt auch beim Dualtarif die verbindliche Summe: die Preise
    # bestimmen nur, wie er zwischen HT und NT gesplitet wird.
    preis_ht: Optional[Decimal] = None
    preis_nt: Optional[Decimal] = None
    # Der verbrauchsunabhaengige Teil des Betrags (F-137). Bei einer
    # Wohnungsrechnung mit Zaehler folgt er den Tagen, nur der Rest dem
    # Zaehler. ``None`` heisst keine Angabe: alles nach Zaehler wie bisher.
    grundpreis: Optional[Decimal] = None

    @property
    def ende_grenze(self) -> date:
        """Die obere Grenze des Rechnungszeitraums, halboffen (R-NUM-03).

        Eine Rechnung ueber "01.01. bis 31.12." meint beide Raender, also
        liegt ihre Grenze auf dem 01.01. des Folgejahres.
        """
        return grenze(self.ende)


@dataclass(frozen=True)
class Heizungsanlage:
    """Eine zentrale Heizungsanlage, wie der Kern sie sieht (NK-048/NK-049).

    ``verbrauchsanteil_prozent`` ist der Satz des § 7 Abs. 1 Satz 1: 50 bis
    70 vom Hundert der Kosten gehen nach erfasstem Waermeverbrauch, der Rest
    nach Wohnflaeche. Der Satz haengt am Gebaeude, nicht an der Kostenart und
    nicht am Mieter -- deshalb steht er hier und nicht im Kostenprofil.

    ``sonderfall_70`` ist § 7 Abs. 1 Satz 2: erfuellt das Gebaeude das
    Anforderungsniveau der WSchV 1994 nicht, wird mit Oel oder Gas geheizt
    und sind die freiliegenden Leitungen ueberwiegend gedaemmt, dann sind es
    **zwingend** 70 vom Hundert. Die Datenbank haelt das als Bedingung fest;
    hier ist es eine Angabe fuer die Begruendung auf dem Blatt.

    Die sechs Felder ab ``warmwasser_weg`` sind § 9 HeizkostenV (NK-050): bei
    einer verbundenen Anlage wird die auf das Warmwasser entfallende
    Waermemenge ermittelt -- gemessen, gerechnet oder geschaetzt -- und die
    Kosten werden danach getrennt, **bevor** irgendetwas verteilt wird. Sie
    stehen an der Anlage und nicht am Zaehler (D-50), gelten fuer den
    gerechneten Zeitraum und tragen keine Historie (F-35).
    """

    id: int
    name: str
    versorgt: str = heizung.HEIZUNG
    verbrauchsanteil_prozent: int = heizung.ANTEIL_VORGABE
    sonderfall_70: bool = False
    warmwasser_weg: Optional[str] = None
    warmwasser_kwh: Optional[Decimal] = None
    warmwasser_volumen_m3: Optional[Decimal] = None
    warmwasser_temperatur_c: Optional[Decimal] = None
    brennstoff_menge: Optional[Decimal] = None
    heizwert_kwh: Optional[Decimal] = None


@dataclass(frozen=True)
class Wohnung:
    id: int
    name: str
    qm: Optional[float]
    ist_aktiv: bool = True
    # Die drei Stammdaten aus NK-045. Sie haben Vorgabewerte, weil jede
    # Stichprobe und jeder Altbestand ohne sie auskommen muss -- und weil
    # die Vorgabe genau das ist, was vor NK-045 gerechnet wurde: Wohnraum,
    # kein Selbstversorger, vom Vermieter nicht bewohnt.
    nutzungsart: str = NUTZUNG_VORGABE
    # Wer seine Waerme selbst erzeugt, nimmt an der Heizungsanlage des
    # Hauses nicht teil (R-CO2-03). Gerechnet wird damit noch nicht -- das
    # kommt mit dem Heizkostenmodul; hier steht der Wert, damit der Kern
    # ihn nicht erst nachtraeglich geliefert bekommen muss.
    selbstversorger: bool = False
    # Eine vom Vermieter bewohnte Einheit ist nicht leer und hat doch
    # keinen Mieter (R-NUM-05, Leerstandsausweis in NK-047).
    eigennutzung: bool = False


@dataclass(frozen=True)
class Mieter:
    id: int
    name: str
    einzug: date
    auszug: Optional[date]
    wohnung_id: int
    # Wie viele Personen ab wann zu diesem Mietverhaeltnis gehoeren
    # (R-NUM-04). Eine Folge von ``(gueltig_ab, personen)`` und keine Zahl:
    # ein Kind wird geboren, ein Partner zieht ein, und die Umlage muss dem
    # taggenau folgen. Leer heisst Einpersonenhaushalt -- ``haushalt.VORGABE``
    # und der Wert, den die Wanderung aus NK-045 dem Altbestand gab.
    haushaltsgroessen: Sequence[Haushaltsstand] = ()


@dataclass(frozen=True)
class Zahlung:
    datum: date
    betrag: Decimal


@dataclass(frozen=True)
class Vorgang:
    """Alles, was eine Abrechnung an Daten braucht -- und nichts sonst.

    ``beginn`` und ``ende`` sind bereits auf das Mietverhaeltnis gestutzt: ein
    Mieter, der im Maerz einzieht, hat hier den 1. Maerz stehen, nicht den
    1. Januar. Das Stutzen gehoert zum Laden, nicht zum Rechnen, sonst muesste
    jeder Stichprobenfall es nachbauen.

    Genau dieses Stutzen macht ``ende`` zweideutig: mal ist es das Ende des
    Abrechnungszeitraums, mal der letzte Miettag des Mieters. Gerechnet wird
    deshalb nie mit ``ende``, sondern mit ``ende_grenze`` -- das Feld bleibt
    fuer die Anzeige, die Grenze fuer die Tage.
    """

    mieter: Mieter
    wohnung: Wohnung
    immobilie_id: int
    immobilie_name: str
    beginn: date
    ende: date
    wohnungen: tuple = ()
    mieter_der_immobilie: tuple = ()
    profile: Mapping[int, str] = field(default_factory=dict)
    rechnungen: tuple = ()
    zaehler: tuple = ()
    zahlungen: tuple = ()
    # Die Heizungsanlagen der Immobilie (NK-048/NK-049). Leer heisst: das
    # Objekt hat keine erfasste Anlage, und Heizkosten laufen wie bisher als
    # gewoehnliche Kostenarten ueber das Kostenprofil.
    heizungsanlagen: tuple = ()
    #: Die Kategorie, an deren Zaehler das Abwasser haengt (objektweit).
    wasser_kategorie_id: Optional[int] = None
    #: Auf diese Kategorien beschraenkt der Vermieter die Abrechnung; None
    #: heisst: alle. ``rechnungen`` enthaelt immer alle Rechnungen des
    #: Zeitraums, weil die Vorpruefung sie auch ungefiltert braucht.
    kategorien_filter: Optional[tuple] = None

    @property
    def ende_grenze(self) -> date:
        """Die obere Grenze des abzurechnenden Zeitraums, halboffen (R-NUM-03).

        Hier loest sich die Zweideutigkeit von ``ende`` auf, und zwar an der
        einzigen Stelle, an der die noetige Auskunft vorliegt: am Mieter.
        ``Mieter.auszug`` ist schon die Grenze, der Tag nach dem letzten
        Miettag (der Lader rechnet um, F-118). Liegt sie im Zeitraum, gilt
        sie. Sonst ist ``ende`` ein Zeitraumende und die Grenze liegt einen
        Tag weiter.

        Ohne diese Unterscheidung bekommt der Wechseltag zwei Rechnungen: bei
        einem Auszug am 30.06. zahlten Vor- und Nachmieter zusammen 367 von
        366 Tagen.
        """
        return mietende(
            self.mieter.auszug if self.mieter.auszug and self.mieter.auszug <= self.ende else None,
            grenze(self.ende),
        )


# ---------------------------------------------------------------------------
# Zaehler im Vorgang finden
# ---------------------------------------------------------------------------
#
# Die Engine fragte ``Meter.query.filter_by(...).first()`` -- ohne
# ``order_by``, also in der Reihenfolge, die SQLite liefert, praktisch nach
# ``id``. Die Suche hier sortiert ausdruecklich nach ``id`` und ist damit
# festgelegt statt zufaellig gleich.


def _nach_id(zaehler: Sequence[Zaehler]) -> list:
    return sorted(zaehler, key=lambda z: z.id)


def hauptzaehler(vorgang: Vorgang, kategorie_id: int) -> Optional[Zaehler]:
    """Der Hauptzaehler der Immobilie fuer diese Kategorie, oder None."""
    for z in _nach_id(vorgang.zaehler):
        if z.immobilie_id == vorgang.immobilie_id and z.kategorie_id == kategorie_id and z.ist_hauptzaehler:
            return z
    return None


def wohnungszaehler(vorgang: Vorgang, kategorie_id: int,
                    wohnung_id: Optional[int] = None) -> Optional[Zaehler]:
    """Der Zaehler dieser (oder der genannten) Wohnung fuer diese Kategorie, oder None."""
    wohnung_id = wohnung_id or vorgang.wohnung.id
    for z in _nach_id(vorgang.zaehler):
        if z.wohnung_id == wohnung_id and z.kategorie_id == kategorie_id and not z.ist_hauptzaehler:
            return z
    return None


def unterzaehler(vorgang: Vorgang, kategorie_id: int) -> list:
    """Alle Nicht-Hauptzaehler der Immobilie fuer diese Kategorie."""
    return [
        z for z in _nach_id(vorgang.zaehler)
        if z.immobilie_id == vorgang.immobilie_id and z.kategorie_id == kategorie_id and not z.ist_hauptzaehler
    ]


def zaehler_vorhanden(vorgang: Vorgang, kategorie_id: int) -> bool:
    """Haengt an dieser Kostenart irgendein Zaehler des Hauses? (NK-105, D-63)

    ``braucht_zaehler`` heisst nur, dass ohne Zählerstand keine Abrechnung
    moeglich ist -- es ist kein Erlaubniskennzeichen. Ob der Zaehlerweg
    beschritten wird, entscheidet die Existenz eines Zaehlers, nicht die
    Pflicht: ein Allgemeinstromzaehler ist real, auch wenn § 2 BetrKV fuer
    Beleuchtung keinen Pflichtzaehler kennt.
    """
    return (
        hauptzaehler(vorgang, kategorie_id) is not None
        or wohnungszaehler(vorgang, kategorie_id) is not None
        or bool(unterzaehler(vorgang, kategorie_id))
    )


# ---------------------------------------------------------------------------
# Einheiten und Belege
# ---------------------------------------------------------------------------


def einheit_fuer(kategorie_name: str, betrkv_nr: Optional[int] = None) -> str:
    """Die Einheit der Menge, die ein Zaehler dieser Kostenart misst.

    Die Quelle ist der Katalog: die BetrKV-Nummer der Kostenart entscheidet
    (F-51, NK-121). Nur ein Name ohne Nummer -- eine Probe ohne Seed, ein
    im Test von Hand gebauter Zaehler -- faellt auf das Wort zurueck; das
    Wort raet schlechter und bleibt nur, damit der Kern auch ohne Katalog
    lesbar bleibt.
    """
    if betrkv_nr is not None:
        return betrkv.einheit(betrkv_nr)
    name = (kategorie_name or '').lower()
    if 'strom' in name:
        return 'kWh'
    if any(x in name for x in ['wasser', 'gas', 'entwäss']):
        return 'm³'
    # Waermezaehler zaehlen Waermemenge, und die misst die HeizkostenV in
    # Kilowattstunden (§ 5 Abs. 1 nennt Waermezaehler ausdruecklich).
    if any(x in name for x in ['wärme', 'waerme', 'heiz']):
        return 'kWh'
    return 'Einheiten'


def beleg_angabe(beleg: Beleg) -> tuple:
    """Gibt (Anzeigename, Pfad) des Nachweises zurueck, beide notfalls ''."""
    if beleg.dateiname:
        name = beleg.dateiname
        if beleg.seiten:
            name += f", Seiten {beleg.seiten}"
        return name, beleg.pfad
    if beleg.pfad_alt:
        return os.path.basename(beleg.pfad_alt), beleg.pfad_alt
    return "", ""


def rechnungsdatum_angabe(datum: Optional[date]) -> Optional[str]:
    """Das Ausstellungsdatum einer Rechnung als ISO-Zeichenkette -- oder None.

    Die Zeilen des Ergebnisses wandern als JSON ueber die Leitung; ein
    Datumsobjekt ist dort nicht uebertragbar (Auslegung an der JSON-Grenze,
    NK-036). Die Formatierung fuer das Dokument uebernimmt der PDF-Erbauer,
    nicht der Kern -- der Kern liefert die Rohangabe fuer R-DOC-01 Punkt 8
    (Rechnungsnummer, Anbieter, Datum, Dokumentseite).
    """
    return datum.isoformat() if datum else None


def euro_text(betrag) -> str:
    """Ein Betrag als Klartext: "1200,00 €" -- wie die Tabelle ihn zeigt.

    Der Rechenweg (R-DOC-01 Punkt 6) ist ein Satz, keine Formel: er mischt
    Zahlen und Woerter, und die Betraege darin muessen so aussehen wie die
    in der Betragsspalte, sonst rechnet der Mieter zwei Schriften
    gegeneinander. Kein Tausendertrennzeichen -- die Betragsspalte des
    Dokuments hat auch keins.
    """
    return f"{runde(betrag):.2f}".replace('.', ',') + ' €'


def zahl_text(wert) -> str:
    """Eine Zahl als Klartext: 72.0 wird "72", 0.5 wird "0,5".

    Dieselbe Regel wie fuer die Betraege: der Punkt eines floats gehoert
    nicht in ein deutsches Dokument.
    """
    return f"{float(wert):g}".replace('.', ',')


def rechenweg_rechnungsbetrag(betrag, anteilige_tage: int,
                              rechnungstage: int,
                              anteiliger_betrag) -> list:
    """Der erste Schritt des Rechenwegs: die Rechnung in den Zeitraum.

    R-DOC-01 Punkt 7 -- bei unterjaehrigem Mietverhaeltnis stehen die Tage
    im Satz, und das Zwischenergebnis (der zeitanteilige Betrag) ist
    sichtbar, nicht verschluckt. Bei einer Rechnung, die den ganzen
    Abrechnungszeitraum deckt, faellt der Schritt nicht an: dann steht die
    Rechnung schon als Ausgangswert des naechsten Schritts.
    """
    if anteilige_tage >= rechnungstage:
        return [f"{euro_text(betrag)} Rechnungsbetrag"]
    return [
        f"{euro_text(betrag)} Rechnungsbetrag, anteilig {anteilige_tage} "
        f"von {rechnungstage} Tagen = {euro_text(anteiliger_betrag)}",
    ]


# ---------------------------------------------------------------------------
# Tage
# ---------------------------------------------------------------------------


def ueberschneidungstage(d1_start: date, d1_end: date, d2_start: date, d2_end: date) -> int:
    """Gemeinsame Tage zweier Zeitraeume, **einschliesslich** beider Raender.

    Fuer Zeitraeume, die so gemeint sind, wie der Vermieter sie eingibt:
    "01.01. bis 31.12." sind 365 Tage. Gerechnet wird halboffen, die Raender
    werden dafuer nach ``zeitraum.grenze()`` verschoben -- das ``+ 1`` steht
    nicht mehr hier (NK-041, R-NUM-03).

    **Nicht fuer Mietverhaeltnisse.** ``Mieter.auszug`` ist kein letzter Tag,
    sondern schon die Grenze; wer es hier hineingibt, berechnet einen Tag zu
    viel. Dafuer gibt es ``Vorgang.ende_grenze``.
    """
    return ueberschneidung(d1_start, grenze(d1_end), d2_start, grenze(d2_end))


# ---------------------------------------------------------------------------
# Flaechendaten pruefen
# ---------------------------------------------------------------------------


def flaechen_pruefung(vorgang: Vorgang) -> tuple:
    """Pruefklasse Flaechendaten. Gibt (gesamtflaeche, befunde) zurueck.

    preflight_check hat bis NK-027 nur Zaehler geprueft und dabei jeden
    billing_type ausser direkt und nur_allgemein uebersprungen. qm ist der
    Standard, also lief ausgerechnet die haeufigste Umlageart ungeprueft.
    Ohne diese Pruefung endete eine Immobilie ohne Flaechendaten in einer
    Division durch null, und der Vermieter sah "float division by zero".

    Befunde sind Paare (status, meldung). status 'blocker' heisst: die
    Umlage nach qm ist rechnerisch unmoeglich. status 'warning' heisst:
    sie laeuft, aber auf unvollstaendigen Daten.
    """
    aktive = [w for w in vorgang.wohnungen if w.ist_aktiv]
    gesamt_qm = sum(w.qm or 0 for w in aktive)
    befunde = []

    if not aktive:
        befunde.append((
            'blocker',
            f"Die Immobilie '{vorgang.immobilie_name}' hat keine aktive Wohnung. "
            f"Eine Umlage nach Quadratmetern ist damit nicht möglich. "
            f"Setzen Sie mindestens eine Wohnung auf aktiv."
        ))
    elif gesamt_qm <= 0:
        befunde.append((
            'blocker',
            f"Für die Immobilie '{vorgang.immobilie_name}' ist bei keiner aktiven Wohnung "
            f"eine Wohnfläche hinterlegt. Die Umlage nach Quadratmetern braucht die "
            f"Gesamtfläche. Tragen Sie die Quadratmeter bei den Wohnungen ein."
        ))
    elif not vorgang.wohnung.qm:
        befunde.append((
            'blocker',
            f"Für die Wohnung '{vorgang.wohnung.name}' ist keine Wohnfläche hinterlegt. "
            f"Ohne sie lässt sich ihr Anteil an {gesamt_qm} qm Gesamtfläche nicht "
            f"berechnen. Tragen Sie die Quadratmeter bei dieser Wohnung ein."
        ))
    else:
        ohne_flaeche = [w.name for w in aktive if not w.qm]
        if ohne_flaeche:
            befunde.append((
                'warning',
                f"Bei {len(ohne_flaeche)} aktiven Wohnungen fehlt die Wohnfläche "
                f"({', '.join(ohne_flaeche)}). Die Gesamtfläche von {gesamt_qm} qm "
                f"ist damit zu klein und der Anteil dieses Mieters zu hoch. "
                f"Tragen Sie die fehlenden Quadratmeter nach."
            ))

    return gesamt_qm, befunde


def nutzungs_pruefung(vorgang: Vorgang) -> tuple:
    """Pruefklasse Nutzungsart. Gibt (objektart, befunde) zurueck.

    Dieses Programm rechnet nach dem Recht fuer Wohngebaeude. Fuer Gewerbe
    und fuer gemischt genutzte Haeuser gilt anderes -- § 8 CO2KostAufG
    sieht fuer Nichtwohngebaeude eine haelftige Teilung vor, bis ein
    Stufenmodell fuer sie in Kraft tritt, das es noch nicht gibt
    (R-CO2-04). Ein halb richtig gerechnetes Gewerbeobjekt waere schlimmer
    als gar keines: es saehe aus wie eine Abrechnung.

    Gezaehlt werden **alle** Einheiten, auch die inaktiven. Ein leer
    stehender Laden macht das Haus nicht zum Wohngebaeude -- die Kosten,
    die auf ihn entfallen, fallen trotzdem an.

    Ein Objekt ohne jede Einheit bleibt hier ohne Befund. Dafuer gibt es
    schon ``flaechen_pruefung()``, die genauer sagt, was fehlt; zwei
    Absagen auf denselben Mangel helfen niemandem.

    Befunde sind Paare (status, meldung), wie bei der Flaeche. Hier gibt
    es nur ``blocker``: an der Nutzungsart gibt es nichts, was man mit
    einer Warnung durchrechnen koennte.
    """
    art = objektart(w.nutzungsart for w in vorgang.wohnungen)
    if art == 'leer' or ist_abrechenbar(art):
        return art, []
    return art, [('blocker', nutzungs_ablehnung(vorgang.immobilie_name, art))]


def art_meldung(kategorie_name: str, art) -> str:
    """Der Satz, den der Vermieter zu einer unbrauchbaren Abrechnungsart liest.

    Er nennt die Kostenart, damit klar ist, welche Zeile im Kostenprofil
    gemeint ist, und zaehlt auf, was stattdessen dort stehen darf. Ohne die
    Aufzaehlung muesste der Vermieter raten -- und geraten hat in F-25
    jemand "verbrauch" statt "direkt".
    """
    gezeigt = art if isinstance(art, str) and art.strip() else repr(art)
    return (
        f'Die Kostenart „{kategorie_name}“ ist mit der Abrechnungsart „{gezeigt}“ '
        f'hinterlegt, die es nicht gibt. Bitte stellen Sie im Kostenprofil des '
        f'Mieters eine der folgenden ein: {aufzaehlung()}.'
    )


def abrechnungsart_von(profile: Mapping[int, str], kategorie) -> str:
    """Die Abrechnungsart einer Kostenart -- oder die Absage (F-25).

    Frueher lief ein unbekannter Wert durch die ganze Fallunterscheidung in
    ``rechne()`` und fiel hinten lautlos heraus: die Kostenart fehlte im
    Blatt, die Summe war zu niedrig, gewarnt hat niemand. Eine Abrechnung,
    der eine Kostenart fehlt, sieht vollstaendig aus -- deshalb bricht der
    Kern hier lieber ab, als weiterzurechnen.

    Gelesen wird ohne ``normiere()``: was in der Datenbank steht, muss exakt
    stimmen. Zurechtgebogen wird an der Eingabe, nicht hier -- sonst rechnete
    der Kern mit etwas anderem, als gespeichert ist.
    """
    art = profile.get(kategorie.id, VORGABE)
    if not ist_gueltig(art):
        raise BillingDataError(art_meldung(kategorie.name, art))
    return art


def qm_relevante_rechnungen(rechnungen: Sequence[Rechnung], profile: Mapping[int, str]) -> list:
    """Rechnungen, die fuer diesen Mieter nach Flaeche umgelegt werden.

    qm ist der Standard, wenn kein Profil gesetzt ist. Rechnungen mit
    Wohnungsbezug gehen zu 100 Prozent an eine Wohnung und brauchen keine
    Flaeche.
    """
    return [
        r for r in rechnungen
        if not r.wohnung_id and profile.get(r.kategorie.id, VORGABE) == 'qm'
    ]


# ---------------------------------------------------------------------------
# Verbrauch aus Zaehlerstaenden
# ---------------------------------------------------------------------------


def leerer_verbrauch(zaehler_nummer: str = '', einheit: str = '') -> dict:
    """Das Ergebnis, wenn sich aus den Staenden nichts ableiten laesst."""
    return {
        'consumption': 0.0, 'ht': 0.0, 'nt': 0.0,
        'r_start': None, 'r_end': None, 'reading_span_days': 0,
        'target_days': 0, 'start_offset_days': 0, 'end_offset_days': 0,
        'status': 'no_data', 'is_interpolated': True, 'gradtage': False,
        'meter_number': zaehler_nummer, 'unit': einheit,
    }


def _stand_angabe(stand: Stand) -> dict:
    return {
        'date': stand.datum.isoformat(),
        'value': stand.wert,
        'value_nt': stand.wert_nt or 0,
        'total': float(stand.gesamt),
    }


# ---------------------------------------------------------------------------
# Dualtarif (NK-055, IST-Stand Risiko 8)
# ---------------------------------------------------------------------------


#: Kennung der Warnung zum Preisfuss. Sie steht im Text, damit Oberflaeche
#: und PDF die Warnung wiederfinden, ohne den Satz zu parsen (dieselbe
#: Konvention wie W-HKV-KUERZUNG-15 und W-FRIST-30TAGE). Eine Warnung je
#: Zaehler, nicht je Rechnung (F-125): {zeitraeume} zaehlt alle Rechnungen auf.
HINWEIS_PREIS_HOCHGERECHNET = (
    "W-ZAEHLER-PREIS-HOCHGERECHNET · Der Einheitspreis für „{kategorie}“ ist "
    "geschätzt: Die Ablesungen von Zähler {zaehler} decken {zeitraeume} nicht "
    "ab. Tragen Sie Ablesungen zu Beginn und Ende der {rechnungen} nach und "
    "erstellen Sie die Abrechnung erneut."
)


def _zaehlername(nummer: Optional[str]) -> str:
    """Die Nummer ohne vorangestelltes „Zähler“ -- der Satz bringt es selbst (F-125)."""
    name = nummer or '?'
    return name[7:].lstrip() if name.lower().startswith('zähler ') else name


def meldungen_buendeln(meldungen: Sequence[str]) -> list[str]:
    """Jede Meldung nur einmal; gleiche Meldungen, die sich nur in der
    Kostenart („…“) unterscheiden, werden zu einer (F-132). Wasserversorgung
    und Entwässerung lesen meist denselben Hauptzähler -- eine Ursache, eine
    Meldung: „Für „Wasserversorgung“ und „Entwässerung“ …“."""
    gruppen: dict[str, list] = {}
    for text in meldungen:
        kat = re.search(r'„[^“]*“', text)
        schluessel = text.replace(kat.group(0), '„…“', 1) if kat else text
        gruppe = gruppen.setdefault(schluessel, [text, []])
        if kat and kat.group(0) not in gruppe[1]:
            gruppe[1].append(kat.group(0))
    ergebnis = []
    for text, kats in gruppen.values():
        if len(kats) > 1:
            text = text.replace(kats[0], ', '.join(kats[:-1]) + ' und ' + kats[-1], 1)
        ergebnis.append(text)
    return ergebnis


def _zeitraeume(spannen: list[str]) -> str:
    """„den Rechnungszeitraum X“ oder „die Rechnungszeiträume X, Y und Z“."""
    if len(spannen) == 1:
        return f"den Rechnungszeitraum {spannen[0]}"
    return f"die Rechnungszeiträume {', '.join(spannen[:-1])} und {spannen[-1]}"

#: Kennung der Warnung zur negativen Allgemeinmenge (NK-115). Im
#: Abrechnungszeitraum wird jeder Zaehler zwischen seinen Ablesungen linear
#: geschaetzt (NK-097). Liegen die Ablesetage von Haupt- und Wohnungszaehlern
#: auseinander, kann die Summe der Wohnungszaehler im Fenster den
#: Hauptzaehler uebersteigen -- rechnerisch negativer Allgemeinverbrauch.
#: Angesetzt wird dann 0; still darf das nicht geschehen, weil die Kosten
#: des Allgemeinverbrauchs so beim Vermieter bleiben.
HINWEIS_ALLGEMEIN_NEGATIV = (
    "W-ZAEHLER-ALLGEMEIN-NEGATIV · Für „{kategorie}“ zeigen die "
    "Wohnungszähler im Abrechnungszeitraum ({beginn} – {ende}) zusammen "
    "mehr Verbrauch als der Hauptzähler {zaehler}: Der Allgemeinverbrauch"
    "{register} wäre rechnerisch {menge} {einheit}. Angesetzt wird 0 — auf "
    "die Mieter wird dafür kein Allgemeinanteil verteilt. Das entsteht "
    "meist, wenn Haupt- und Wohnungszähler an verschiedenen Tagen abgelesen "
    "wurden und der Verbrauch dazwischen geschätzt wird. Lesen Sie alle "
    "Zähler am selben Tag ab — beim Mieterwechsel am Einzugs- bzw. "
    "Auszugstag — und erstellen Sie die Abrechnung erneut. Zeigt der "
    "Hauptzähler auch dann weniger, ist ein Stand falsch erfasst oder ein "
    "Wohnungszähler dem falschen Hauptzähler zugeordnet. Prüfen Sie die "
    "Stände und die Zuordnung der Zähler."
)

#: F-137: eine Wohnungsrechnung mit Zaehler wird nach Verbrauch geteilt. Ein
#: Grundpreis faellt aber auch im Leerstand an; ohne die Angabe, wie viel
#: davon Grundpreis ist, traegt der Mieter mehr als seine Tage.
HINWEIS_GRUNDPREIS_LEERSTAND = (
    "W-GRUNDPREIS-LEERSTAND · Die Rechnung „{kategorie}“ für {wohnung} "
    "({beginn} – {ende}) wird nach dem Zähler der Wohnung verteilt, und die "
    "Wohnung war darin {tage} Tage nicht vermietet. Ein Grundpreis oder eine "
    "Zählermiete fällt auch dann an. Nach Verbrauch geteilt trägt der Mieter "
    "davon mehr, als auf seine Tage entfällt. Tragen Sie bei der Rechnung "
    "„davon Grundpreis/Zählermiete“ ein, dann teilt die App ihn nach Tagen "
    "und gibt den Anteil der leeren Tage an den Vermieter."
)


def tarifpreise(betrag, ht_menge, nt_menge, preis_ht, preis_nt):
    """Den Rechnungsbetrag auf die Tarife verteilen, oder (NULL, NULL).

    Ein Dualtarif hat zwei Mengen und zwei Preise. Der Betrag der Rechnung
    bleibt die verbindliche Summe -- was sich verteilt, ist **er**, nicht
    das, was die Preise rechnen wuerden; die Preise bestimmen nur den
    Schnitt. Der Weg geht ueber den Wertanteil: die HT-Menge mal der
    HT-Preis geteilt durch den Gesamtwert beider Tarife ist der Anteil des
    Betrags, der auf den Hochtarif entfaellt. Die effektiven Preise sind
    die Anteile je Menge -- sie summieren sich wieder zum Betrag, und ein
    Mieter mit NT-lastigem Verbrauch zahlt den NT-Anteil, nicht den
    Mischpreis des ganzen Hauses.

    (None, None) heisst: kein Dualtarif -- Preise fehlen (Altbestand,
    Einheitstarif), eine der Mengen ist null (dann traegt der eine Tarif
    ohnehin alles, und der Mischpreis trifft exakt), oder der Gesamtwert
    ist null (Preise von 0 -- nichts zu verteilen). Der Aufrufer faellt
    dann auf den einen Preis zurueck, den es vor NK-055 gab. ``None`` und
    nicht ``NULL``: NULL waere ein Preis von null, hier ist gemeint, dass
    es keinen Preis gibt.

    Beispielfall: 60 kWh HT zum Preis 0,30 und 40 kWh NT zum Preis 0,20,
    der Betrag 100,00 EUR -- der Wertanteil des HT ist 18 von 26, also
    entfaellt ein Betrag von rund 69,23 EUR auf HT und 30,77 auf NT;
    daraus wieder die effektiven Preise je kWh. Ausgewiesen und gerechnet
    wird ungerundet; die vierte Stelle im Nachweis rundet
    ``runde_einheitspreis``.
    """
    if preis_ht is None or preis_nt is None:
        return None, None
    if ht_menge <= 0 or nt_menge <= 0:
        return None, None
    gesamtwert = ht_menge * preis_ht + nt_menge * preis_nt
    if gesamtwert <= 0:
        return None, None
    betrag_ht = betrag * (ht_menge * preis_ht) / gesamtwert
    return betrag_ht / ht_menge, (betrag - betrag_ht) / nt_menge


def verbrauch_detail(zaehler: Zaehler, start_date: date, end_date: date) -> dict:
    """Verbrauch im Zeitraum, samt Auskunft darueber, worauf er beruht.

    Die Hochrechnung ist die der Engine: zwischen je zwei Staenden wird ein
    Tagesmittel gebildet und mit den Tagen multipliziert, die in den Zeitraum
    fallen. Was am Rand fehlt, wird mit dem Mittel ueber alle Staende
    aufgefuellt. ``status`` ist die Ampel fuer die Oberflaeche, sie bewertet
    den Abstand der naechsten Ablesung zum Zeitraumrand.

    Der Verbrauch geht als ``float`` zurueck, nicht als ``Decimal``: er ist
    kein Geld, sondern eine Messgroesse mit eigener Unsicherheit (R-NUM-01
    bindet nur Euro-Betraege). Gerechnet wird trotzdem mit ``Decimal``, damit
    die Division durch die Tage nicht schon vor der Multiplikation abrutscht.

    ``end_date`` ist der **letzte Tag** des Zeitraums, einschliesslich -- so,
    wie eine Rechnung ihn nennt. Wer bereits eine Grenze hat, etwa aus
    ``Vorgang.ende_grenze``, nimmt ``verbrauch_in()`` und spart sich das
    Zurueckrechnen.
    """
    return verbrauch_in(zaehler, start_date, grenze(end_date))


def eigenverbrauch_text(menge, unit: str, detail: dict | None) -> str:
    """Der Unterposten Eigenverbrauch. Ein nach Gradtagszahlen geschaetzter
    Stichtag steht auch im einfachen PDF dabei, nicht nur im detaillierten (D-115);
    die Schwelle von 7 Tagen ist dieselbe wie dort."""
    text = f"Eigenverbrauch ({menge:.1f} {unit}"
    if detail and detail.get('gradtage') and max(detail['start_offset_days'], detail['end_offset_days']) > 7:
        text += ", Stichtag nach Gradtagszahlen geschätzt"
    return text + ")"


def verbrauch_in(zaehler: Zaehler, von: date, bis: date) -> dict:
    """Verbrauch in ``[von, bis)`` -- der erste Tag zaehlt, der letzte nicht.

    Die halboffene Form ist die, in der der Kern rechnet (R-NUM-03). Sie ist
    hier noetig, weil ein auf das Mietverhaeltnis gestutzter Zeitraum an
    ``Mieter.auszug`` endet, und das ist bereits eine Grenze und kein letzter
    Tag.

    Liegt eine **Zwischenablesung** (NK-051, R-HK-04) genau auf einer der
    beiden Grenzen, dann misst sie diese Grenze: liegt ein Ablesungspaar an
    beiden Raendern, geht nichts durch Interpolation verloren, und der
    Verbrauch ist exakt die Differenz der Staende. Die Auskunft nennt die
    Zwischenablesungen mit Datum und Stand, damit die Abrechnung sagen
    kann, worauf ihre Zahlen beruhen.

    Bei einem Dualtarifzaehler (NK-055) tragen ``ht`` und ``nt`` die Mengen
    getrennt, nach derselben Interpolation wie die Gesamtmenge; ihre Summe
    ist der Verbrauch. Ohne Niedertarif steht in ``nt`` die 0.

    Ein **Heizwaermezaehler** ohne Stand am Stichtag wird nach
    Gradtagszahlen geschaetzt, nicht nach Tagen (D-115, VDI 2067): der
    Winteranteil eines Ablesejahrs traegt den Grossteil der Waerme. Die
    Auskunft sagt es mit ``gradtage``. Wasser und Strom bleiben linear.
    """
    einheit = einheit_fuer(zaehler.kategorie_name, zaehler.kategorie_betrkv_nr)
    heiz = ist_heizwaermezaehler(zaehler)

    def wirksame_tage(a: date, b: date, basis_von: date, basis_bis: date) -> Decimal:
        """Tage in ``[a, b)``, beim Heizwaermezaehler nach Gradtagen gewichtet."""
        if not heiz:
            return Decimal(str((b - a).days))
        anteil = heizung.gradtage(a, b) / heizung.gradtage(basis_von, basis_bis)
        return (Decimal((basis_bis - basis_von).days) * anteil.numerator) / anteil.denominator
    leer = leerer_verbrauch(zaehler.nummer or '', einheit)

    staende = sorted(zaehler.staende, key=lambda s: s.datum)
    if len(staende) < 2:
        return leer

    target_days = tage(von, bis)
    if target_days <= 0:
        return leer

    total_consumption = Decimal('0.0')
    total_ht = Decimal('0.0')
    total_nt = Decimal('0.0')
    total_covered_days = 0
    r_start_global = None
    r_end_global = None
    # Indizes statt der Staende selbst: zwei Ablesungen mit gleichem Datum und
    # gleichem Wert sind als eingefrorener Datensatz dasselbe Objekt und
    # fielen in einer Menge zusammen.
    benutzt = set()

    for i in range(len(staende) - 1):
        s1 = staende[i]
        s2 = staende[i + 1]

        interval_days = (s2.datum - s1.datum).days
        if interval_days <= 0:
            continue

        overlap_start = max(von, s1.datum)
        overlap_end = min(bis, s2.datum)
        overlap_days = (overlap_end - overlap_start).days

        if overlap_days > 0:
            interval_consumption = s2.gesamt - s1.gesamt
            daily_rate = interval_consumption / Decimal(str(interval_days))
            wirksam = wirksame_tage(overlap_start, overlap_end, s1.datum, s2.datum)
            total_consumption += daily_rate * wirksam
            # Der Dualtarif braucht die Mengen getrennt (NK-055): dieselbe
            # Interpolation, zweimal -- einmal je Register. Die Differenzen
            # addieren sich wieder zum Gesamtbetrag, denn gesamt ist HT
            # plus NT.
            ht_rate = (dec(s2.wert) - dec(s1.wert)) / Decimal(str(interval_days))
            nt_rate = (dec(s2.wert_nt or 0) - dec(s1.wert_nt or 0)) / Decimal(str(interval_days))
            total_ht += ht_rate * wirksam
            total_nt += nt_rate * wirksam
            total_covered_days += overlap_days

            benutzt.add(i)
            benutzt.add(i + 1)

            if r_start_global is None:
                r_start_global = s1
            r_end_global = s2

    # Was der Zeitraum ueber die Staende hinausragt, wird mit dem Mittel ueber
    # alle Staende aufgefuellt -- etwa wenn das Mietverhaeltnis vor der ersten
    # Ablesung beginnt.
    missing_days = target_days - total_covered_days
    if missing_days > 0 and len(staende) >= 2:
        erster = staende[0]
        letzter = staende[-1]
        global_days = (letzter.datum - erster.datum).days
        if global_days > 0:
            global_rate = (letzter.gesamt - erster.gesamt) / Decimal(str(global_days))
            # Die Luecken liegen vor der ersten und nach der letzten Ablesung.
            fehlend = Decimal(str(missing_days))
            if heiz:
                fehlend = sum((wirksame_tage(a, b, erster.datum, letzter.datum)
                               for a, b in ((von, min(bis, erster.datum)),
                                            (max(von, letzter.datum), bis)) if a < b),
                              Decimal(0))
            total_consumption += global_rate * fehlend
            global_rate_ht = (dec(letzter.wert) - dec(erster.wert)) / Decimal(str(global_days))
            global_rate_nt = (dec(letzter.wert_nt or 0) - dec(erster.wert_nt or 0)) / Decimal(str(global_days))
            total_ht += global_rate_ht * fehlend
            total_nt += global_rate_nt * fehlend
            benutzt.add(0)
            benutzt.add(len(staende) - 1)

    if r_start_global is None:
        r_start_global = staende[0]
    if r_end_global is None:
        r_end_global = staende[-1]

    # Die Ampel misst den Abstand zum letzten Tag, nicht zur Grenze: sie
    # beantwortet dem Vermieter, wie nah die Ablesung am Zeitraumrand lag.
    letzter = letzter_tag(bis)
    start_offset = min(abs((s.datum - von).days) for s in staende)
    end_offset = min(abs((s.datum - letzter).days) for s in staende)

    is_interpolated = start_offset > 1 or end_offset > 1 or missing_days > 10
    consumption = float(total_consumption)

    max_offset = max(start_offset, end_offset)
    if missing_days > 10:
        status = 'warning'      # zu viel hochgerechnet
    elif max_offset <= 7:
        status = 'excellent'
    elif max_offset <= 14:
        status = 'acceptable'
    else:
        status = 'warning'

    basis_readings = [
        {'date': staende[i].datum.isoformat(), 'total': float(staende[i].gesamt)}
        for i in sorted(benutzt)
    ]

    # Die Zwischenablesungen an den Grenzen (NK-051): der Messwert, der die
    # Grenze zwischen zwei Mietverhaeltnissen wirklich misst (§ 9b).
    zwischen = [
        {
            'datum': s.datum.isoformat(),
            'stand': float(s.gesamt),
            'seite': 'beginn' if s.datum == von else 'ende',
        }
        for s in staende
        if s.art == heizung.ZWISCHENABLESUNG and s.datum in (von, bis)
    ]

    return {
        'consumption': consumption,
        'ht': float(total_ht),
        'nt': float(total_nt),
        'r_start': _stand_angabe(r_start_global),
        'r_end': _stand_angabe(r_end_global),
        'basis_readings': basis_readings,
        'reading_span_days': (r_end_global.datum - r_start_global.datum).days,
        'target_days': target_days,
        'target_start_date': von.isoformat(),
        'target_end_date': letzter.isoformat(),
        'start_offset_days': start_offset,
        'end_offset_days': end_offset,
        'status': status,
        'is_interpolated': is_interpolated,
        'gradtage': heiz and is_interpolated,
        'zwischenablesungen': zwischen,
        'meter_id': zaehler.id,
        'meter_number': zaehler.nummer or '',
        'unit': einheit,
    }


def verbrauch(zaehler: Zaehler, start_date: date, end_date: date) -> float:
    """Nur die Zahl, ohne die Auskunft darueber, worauf sie beruht."""
    return verbrauch_detail(zaehler, start_date, end_date)['consumption']


# ---------------------------------------------------------------------------
# Die Umlage
# ---------------------------------------------------------------------------


def _aktive_mieter(vorgang: Vorgang, von: date, bis: date) -> list:
    """Mieter der Immobilie, deren Mietzeit nach ``[von, bis)`` hineinreicht.

    Die Grenzen sind halboffen (R-NUM-03), und das aendert den Wechselfall:
    wer am ``von`` auszieht, war in diesem Zeitraum keinen Tag mehr da und
    zaehlt nicht mit. Vorher tat er es, und am Wechseltag standen zwei Mieter
    in der Liste, durch die die Personenumlage teilt.

    Die Bedingung stand als ``db.or_`` in der Datenbank und lautete: eingezogen
    spaetestens am letzten Tag, nicht ausgezogen vor dem ersten.
    """
    return sorted(
        [
            m for m in vorgang.mieter_der_immobilie
            if m.einzug < bis and (m.auszug is None or m.auszug > von)
        ],
        key=lambda m: m.id,
    )


def _personentage_des_mieters(mieter: Mieter, von: date, bis: date) -> int:
    """Die Personentage eines Mietverhaeltnisses im Schnitt mit ``[von, bis)``.

    Erst wird die Mietzeit mit dem Zeitraum geschnitten, dann zaehlt jeder Tag
    so oft, wie an ihm Personen im Haushalt lebten (R-NUM-04). Der Einzugstag
    zaehlt und der letzte Miettag auch -- ``Mieter.auszug`` ist der Tag
    danach, die Grenze (R-NUM-03, F-118).
    """
    m_von = max(von, mieter.einzug)
    m_bis = min(bis, mietende(mieter.auszug, bis))
    return personentage(mieter.haushaltsgroessen, m_von, m_bis)


def _personentage_im_haus(vorgang: Vorgang, von: date, bis: date):
    """``(eigene, alle, Parteien)`` Personentage in ``[von, bis)``.

    ``alle`` ist der Nenner aus R-NUM-04: die Summe der Personentage **aller**
    Mietverhaeltnisse der Immobilie im Zeitraum. ``eigene`` ist der Zaehler
    fuer den Mieter, um den es geht -- null, wenn er im Zeitraum nicht da war.
    ``Parteien`` zaehlt die Mietverhaeltnisse, nicht die Koepfe; die Zahl geht
    nur noch in die Zaehlerdetails, nicht mehr in eine Division.

    Leerstand taucht hier gar nicht auf: wo kein Mietverhaeltnis ist, gibt es
    keine Personentage. Wer den Leerstandsanteil traegt, ist eine andere Frage
    -- die von R-NUM-05 und NK-047.
    """
    eigene = 0
    alle = 0
    parteien = 0
    for m in _aktive_mieter(vorgang, von, bis):
        pt = _personentage_des_mieters(m, von, bis)
        if pt <= 0:
            continue
        alle += pt
        parteien += 1
        if m.id == vorgang.mieter.id:
            eigene = pt
    return eigene, alle, parteien


def _allgemeinquoten(vorgang: Vorgang, haupt: Zaehler, unter, von: date, bis: date,
                     fenster_von: date, fenster_bis: date):
    """``(Mieter, Vermieter)``: die Anteile am Allgemeinverbrauch der Rechnung ``[von, bis)``.

    F-122: die Rechnung zerfaellt an jedem Einzug, Auszug und jeder Aenderung
    der Haushaltsgroesse in Abschnitte gleicher Belegung. In jedem Abschnitt
    wird der Allgemeinverbrauch gemessen und nach Personentagen geteilt; die
    Quote ist der Anteil an der Summe. Mieter wie Vermieter tragen nur aus
    dem Abrechnungsfenster ``[fenster_von, fenster_bis)`` (der Vermieter seit
    F-128). Mal dem Allgemeinbetrag der ganzen Rechnung ergeben die Anteile
    aller Mieter plus der Vermieteranteile aller Zeitraeume die Rechnung --
    auch wenn der Verbrauch uebers Jahr ungleich liegt.

    D-73 je Abschnitt: misst ein Abschnitt negativen Allgemeinverbrauch, zaehlt
    er als null. Niemand bekommt eine Gutschrift, und die positiven Abschnitte
    teilen sich, was die Rechnung netto an Allgemeinverbrauch hat.

    ``None``, wenn die Belegung ueber die ganze Rechnung gleich bleibt (dann
    ist die Quote das Verhaeltnis der Personentage, wie seit NK-097) oder kein
    Abschnitt positiv ist.
    """
    belegung = {von, bis}
    for m in vorgang.mieter_der_immobilie:
        belegung |= {m.einzug, mietende(m.auszug, bis)}
        belegung |= {h.gueltig_ab for h in m.haushaltsgroessen}
    belegung = {g for g in sorted(belegung) if von <= g <= bis}
    if len(belegung) <= 2:
        return None
    grenzen = [g for g in sorted(belegung | {fenster_von, fenster_bis}) if von <= g <= bis]

    summe = mieter = vermieter = NULL
    for a, e in zip(grenzen, grenzen[1:]):
        allgemein = dec(verbrauch_in(haupt, a, e)['consumption']) - sum(
            dec(verbrauch_in(z, a, e)['consumption']) for z in unter)
        if allgemein <= 0:
            continue
        eigene, alle, _ = _personentage_im_haus(vorgang, a, e)
        leer = sum(b.unbelegt for b in _leerstandsbilanz(vorgang, a, e)
                   if b.traegt_der_vermieter)
        if alle + leer <= 0:
            continue
        summe += allgemein
        if fenster_von <= a and e <= fenster_bis:
            mieter += allgemein * dec(eigene) / dec(alle + leer)
            vermieter += allgemein * dec(leer) / dec(alle + leer)
    if summe <= 0:
        return None
    return mieter / summe, vermieter / summe


def _leerstandsbilanz(vorgang: Vorgang, von: date, bis: date, nur=None) -> list:
    """Je aktiver Wohnung eine Bilanz belegter und unbelegter Tage (R-NUM-05).

    Die Mietzeiten kommen aus **allen** Mietverhaeltnissen der Immobilie, nicht
    nur aus dem, um den es gerade geht: eine Wohnung steht nicht deshalb leer,
    weil ein anderer Mieter dort wohnt.

    ``nur`` schraenkt auf eine Menge von Wohnungskennungen ein. Das braucht die
    Heizkostenverteilung (NK-049): ihr Nenner ist nicht das ganze Haus, sondern
    die Flaeche, die an der Anlage haengt -- ohne die Selbstversorger, die ihre
    Waerme selbst erzeugen (R-CO2-03), und bei zwei Anlagen ohne die Wohnungen
    der anderen. Ohne ``nur`` bleibt es bei allen aktiven Wohnungen.
    """
    mietzeiten = {}
    for m in vorgang.mieter_der_immobilie:
        mietzeiten.setdefault(m.wohnung_id, []).append(
            (m.einzug, mietende(m.auszug, bis))
        )
    einheiten = [
        Leerstandseinheit(
            wohnung_id=w.id,
            name=w.name,
            qm=w.qm or 0,
            eigennutzung=w.eigennutzung,
            mietzeiten=tuple(mietzeiten.get(w.id, ())),
        )
        for w in vorgang.wohnungen
        if w.ist_aktiv and (nur is None or w.id in nur)
    ]
    return leerstandsbilanzen(einheiten, von, bis)


def _vermieteranteil(vorgang, kategorie_name, rechnung, anteiliger_betrag,
                     gesamt_qm, von, bis, nur=None) -> Optional[dict]:
    """Was von einer qm-Rechnung beim Vermieter bleibt -- oder ``None``.

    Der Nenner der Flaechenumlage ist die **volle** Gesamtflaeche; eine
    leerstehende Wohnung faellt nicht aus ihm heraus. Genau dadurch traegt der
    Vermieter den Leerstand, und zwar schon immer. Neu ist seit NK-047 nur,
    dass es jemand sieht: der Anteil wird ausgewiesen statt zwischen den
    Zeilen zu verschwinden (R-NUM-05, Produktprinzip 3).

    Gemessen wird im selben Fenster wie ``prorated_amount``, also in
    ``[von, bis)``. Damit gilt Zeile fuer Zeile: die Anteile aller Mieter plus
    der Vermieteranteil ergeben den anteiligen Rechnungsbetrag.
    """
    laenge = tage(von, bis)
    nenner = dec(gesamt_qm) * dec(laenge)
    if nenner <= 0:
        return None

    bilanz = _leerstandsbilanz(vorgang, von, bis, nur)
    leer = dec(unbelegte_flaechentage(bilanz, LEERSTAND))
    eigen = dec(unbelegte_flaechentage(bilanz, EIGENNUTZUNG))
    if leer <= 0 and eigen <= 0:
        return None

    leer_betrag = runde(anteiliger_betrag * (leer / nenner))
    eigen_betrag = runde(anteiliger_betrag * (eigen / nenner))

    einheiten = [
        {
            'apartment': b.name,
            'sqm': b.qm,
            'vacant_days': b.unbelegt,
            'period_days': laenge,
            'reason': b.grund,
            'reason_text': GRUND_TEXT[b.grund],
        }
        for b in bilanz if b.traegt_der_vermieter
    ]
    namen = {
        LEERSTAND: [e['apartment'] for e in einheiten if e['reason'] == LEERSTAND],
        EIGENNUTZUNG: [e['apartment'] for e in einheiten if e['reason'] == EIGENNUTZUNG],
    }
    teile = [
        f"{GRUND_TEXT[grund]} ({', '.join(namen[grund])})"
        for grund in (LEERSTAND, EIGENNUTZUNG) if namen[grund]
    ]

    return {
        'category': kategorie_name,
        'invoice_id': rechnung.id,
        'invoice_number': rechnung.nummer,
        'rechnungsdatum': rechnungsdatum_angabe(rechnung.rechnungsdatum),
        'period': f"{rechnung.beginn.strftime('%d.%m.%Y')} - {rechnung.ende.strftime('%d.%m.%Y')}",
        'prorated_amount': runde(anteiliger_betrag),
        'total_sqm': gesamt_qm,
        'leerstand_amount': leer_betrag,
        'eigennutzung_amount': eigen_betrag,
        'amount': leer_betrag + eigen_betrag,
        'units': einheiten,
        'description': 'Nicht auf die Mieter umgelegt: ' + ', '.join(teile),
    }


def _vermieterpersonenanteil(vorgang, kategorie_name, rechnung, bilanz,
                             vermieter_pt, nenner, betrag=None,
                             quote=None) -> Optional[dict]:
    """Was von einer Personen-Umlage beim Vermieter bleibt -- oder ``None``.

    Der Personennenner zaehlte nur Mietverhaeltnisse; eine Wohnung ohne
    laufendes Mietverhaeltnis tauchte darin gar nicht auf, und ihr Anteil
    verteilte sich stillschweigend auf die uebrigen Mieter (F-34). Seit
    NK-098 zaehlt sie wie ein Einpersonenhaushalt (``haushalt.VORGABE``):
    ihre Personentage stehen im Nenner, und ihr Anteil bleibt beim Vermieter
    -- ausgewiesen statt zwischen den Zeilen zu verschwinden (R-NUM-05,
    Produktprinzip 3).

    Der Nenner ist der des vollen Rechnungszeitraums -- derselbe, an dem auch
    die Personentage der Mieter haengen, denn beim Personenschluessel steckt
    die Zeitanteiligkeit im Verhaeltnis und nicht im Betrag (R-NUM-04). Die
    ``bilanz`` und ``vermieter_pt`` gelten dagegen nur fuer den Zeitraum der
    Abrechnung (F-128): ueber alle Zeitraeume zusammen ergeben die Anteile
    aller Mieter plus der Vermieteranteile den vollen Rechnungsbetrag, und
    keiner zeigt Leerstand, der ausserhalb seines Zeitraums liegt.

    ``betrag`` ersetzt den Rechnungsbetrag, wenn nur ein Teil nach Personen
    geht -- im Zaehlerzweig die Kosten des Allgemeinverbrauchs (F-121).
    ``quote`` ersetzt dort das Verhaeltnis der Personentage, wenn der
    Verbrauch je Belegungsabschnitt gemessen wurde (F-122).
    """
    if vermieter_pt <= 0 or nenner <= 0:
        return None

    basis = rechnung.betrag if betrag is None else betrag
    if quote is None:
        quote = dec(vermieter_pt) / dec(nenner)
    anteiliger_betrag = runde(dec(basis) * quote)
    leer_tage = sum(b.unbelegt for b in bilanz if b.grund == LEERSTAND)
    eigen_tage = sum(b.unbelegt for b in bilanz if b.grund == EIGENNUTZUNG)
    leer_betrag = runde(anteiliger_betrag * (dec(leer_tage) / dec(vermieter_pt)))
    eigen_betrag = runde(anteiliger_betrag * (dec(eigen_tage) / dec(vermieter_pt)))

    einheiten = [
        {
            'apartment': b.name,
            # Die Köpfe einer Wohnung ohne Mietverhaeltnis sind nicht bekannt.
            # Es gilt dieselbe Vorgabe wie fuer ein Mietverhaeltnis ohne
            # Haushaltseintrag: eine Person (Entscheidung zu NK-098).
            'personen': HAUSHALT_VORGABE,
            'vacant_days': b.unbelegt,
            'period_days': b.belegt + b.unbelegt,
            'reason': b.grund,
            'reason_text': GRUND_TEXT[b.grund],
        }
        for b in bilanz if b.traegt_der_vermieter
    ]
    namen = {
        LEERSTAND: [e['apartment'] for e in einheiten if e['reason'] == LEERSTAND],
        EIGENNUTZUNG: [e['apartment'] for e in einheiten if e['reason'] == EIGENNUTZUNG],
    }
    teile = [
        f"{GRUND_TEXT[grund]} ({', '.join(namen[grund])})"
        for grund in (LEERSTAND, EIGENNUTZUNG) if namen[grund]
    ]

    return {
        'category': kategorie_name,
        'invoice_id': rechnung.id,
        'invoice_number': rechnung.nummer,
        'rechnungsdatum': rechnungsdatum_angabe(rechnung.rechnungsdatum),
        'period': f"{rechnung.beginn.strftime('%d.%m.%Y')} - {rechnung.ende.strftime('%d.%m.%Y')}",
        'prorated_amount': anteiliger_betrag,
        'total_person_days': nenner,
        'vermieter_personentage': vermieter_pt,
        'leerstand_amount': leer_betrag,
        'eigennutzung_amount': eigen_betrag,
        'amount': leer_betrag + eigen_betrag,
        'units': einheiten,
        'description': 'Nicht auf die Mieter umgelegt: ' + ', '.join(teile),
    }


def _belegte_verbrauchsmenge(vorgang: Vorgang, zaehler: Zaehler,
                             rechnung: Rechnung, gemessen: bool = False,
                             fenster=None) -> float:
    """Wie viel der Menge eines Zaehlers auf Mietverhaeltnisse entfaellt.

    Fuer jede Wohnung zaehlt dasselbe, was auch ihre Zeile als
    verbrauchsabhaengige Menge annimmt (D-52; im Zaehlerzweig mit
    ``gemessen`` immer die Menge im Fenster, F-120): liegt an jedem Mietrand des
    Mietverhaeltnisses eine Zwischenablesung, die gemessene Menge des
    Fensters -- sonst der Ersatzmassstab, die gemessene Menge der Wohnung,
    zeitanteilig geteilt. Fuer eine ganz belegte Wohnung ergibt das genau
    ihre gemessene Menge, und der Rest fuer den Vermieter ist null.

    Zusammen mit dem Rest dieser Funktion haelt sie die Bilanz der Zeile:
    was die Mieter verbrauchsabhaengig zahlen und was beim Vermieter
    verbleibt, ergibt zusammen den Verbrauchsteil der Rechnung.

    ``fenster`` (``(von, bis)``) zaehlt nur die Mietzeit darin (F-128).
    """
    von = rechnung.beginn
    bis = rechnung.ende_grenze
    laenge = tage(von, bis)
    if laenge <= 0:
        return 0.0
    f_von, f_bis = fenster or (von, bis)
    volle_menge = verbrauch(zaehler, rechnung.beginn, rechnung.ende)
    menge = 0.0
    for m in vorgang.mieter_der_immobilie:
        if m.wohnung_id != zaehler.wohnung_id:
            continue
        fenster_von = max(m.einzug, von, f_von)
        fenster_bis = min(m.auszug or bis, bis, f_bis)
        if tage(fenster_von, fenster_bis) <= 0:
            continue
        raende = [
            g for g in (m.einzug, m.auszug)
            if g and von < g < bis]
        fehlen = [
            g for g in raende
            if not any(s.art == heizung.ZWISCHENABLESUNG and s.datum == g
                       for s in zaehler.staende)]
        if fehlen and not gemessen:
            # Ersatzmassstab: die Tage des Mietverhaeltnisses im Zeitraum.
            menge += volle_menge * (tage(fenster_von, fenster_bis) / laenge)
        else:
            # Gemessen -- eine Zwischenablesung an jedem Mietrand.
            menge += verbrauch_in(zaehler, fenster_von, fenster_bis)['consumption']
    return menge


def _vermieterverbrauchsanteil(vorgang: Vorgang, kategorie_name: str,
                               rechnung: Rechnung, verbrauchsteil,
                               summe_zaehler: float, zaehler: dict,
                               einheit: str, ids: set,
                               gemessen: bool = False,
                               fenster=None) -> Optional[dict]:
    """Was vom Verbrauchsteil einer Rechnung beim Vermieter bleibt.

    Eine leer stehende oder eigengenutzte Wohnung verbraucht dennoch Waerme
    von der Anlage; ihr Zaehler steht im Nenner der Verteilung, und ihr
    Anteil bleibt beim Vermieter (R-NUM-05). Gemessen wird er als Rest: die
    gemessene Menge des Zaehlers abzueglich dessen, was die Mietverhaeltnisse
    der Wohnung fuer sich nehmen. Damit gilt Zeile fuer Zeile: die
    verbrauchsabhaengigen Anteile aller Mieter plus dieser Rest ergeben
    zusammen den Verbrauchsteil der Rechnung -- nichts wird doppelt
    verteilt, nichts verschwindet.

    ``fenster`` (``(von, bis)``, der Teil der Rechnung im Zeitraum der
    Abrechnung) misst nur den Rest darin (F-128): keine Abrechnung zeigt
    Leerstand ausserhalb ihres Zeitraums, und ueber alle Zeitraeume ergibt
    sich der Rest der ganzen Rechnung.
    """
    if verbrauchsteil is None or summe_zaehler <= 0:
        return None
    von, bis = fenster or (rechnung.beginn, rechnung.ende_grenze)
    bilanz = _leerstandsbilanz(vorgang, von, bis, ids)
    # F-133: ohne ``gemessen`` zahlen die Mieter ihren Teil im Ersatzmassstab
    # (Tage). Der Rest im Fenster ist dann der Rest der ganzen Rechnung, nach
    # den Leertagen geteilt -- so ergeben alle Zeitraeume zusammen genau ihn.
    leertage = ({b.wohnung_id: b.unbelegt for b in _leerstandsbilanz(
        vorgang, rechnung.beginn, rechnung.ende_grenze, ids)}
        if fenster and not gemessen else None)
    einheiten = []
    mengen = {LEERSTAND: 0.0, EIGENNUTZUNG: 0.0}
    for b in bilanz:
        if not b.traegt_der_vermieter:
            continue
        z = zaehler.get(b.wohnung_id)
        if z is None:
            continue
        if leertage is not None:
            ganz = (verbrauch(z, rechnung.beginn, rechnung.ende)
                    - _belegte_verbrauchsmenge(vorgang, z, rechnung))
            rest = ganz * b.unbelegt / leertage[b.wohnung_id]
        else:
            menge = (verbrauch_in(z, von, bis)['consumption'] if fenster
                     else verbrauch(z, rechnung.beginn, rechnung.ende))
            rest = menge - _belegte_verbrauchsmenge(vorgang, z, rechnung, gemessen, fenster)
        if rest <= 0:
            continue
        einheiten.append({
            'apartment': b.name,
            'vacant_days': b.unbelegt,
            'period_days': tage(von, bis),
            'consumption': round(rest, 1),
            'reason': b.grund,
            'reason_text': GRUND_TEXT[b.grund],
        })
        mengen[b.grund] += rest
    if not einheiten:
        return None
    rest_menge = mengen[LEERSTAND] + mengen[EIGENNUTZUNG]
    leer_betrag = runde(
        dec(verbrauchsteil) * dec(mengen[LEERSTAND]) / dec(summe_zaehler))
    eigen_betrag = runde(
        dec(verbrauchsteil) * dec(mengen[EIGENNUTZUNG]) / dec(summe_zaehler))

    namen = {
        LEERSTAND: [e['apartment'] for e in einheiten if e['reason'] == LEERSTAND],
        EIGENNUTZUNG: [e['apartment'] for e in einheiten if e['reason'] == EIGENNUTZUNG],
    }
    teile = [
        f"{GRUND_TEXT[grund]}: {', '.join(namen[grund])} "
        f"({mengen[grund]:.1f} von {summe_zaehler:.1f} {einheit})"
        for grund in (LEERSTAND, EIGENNUTZUNG) if namen[grund]
    ]

    return {
        'category': kategorie_name,
        'invoice_id': rechnung.id,
        'invoice_number': rechnung.nummer,
        'rechnungsdatum': rechnungsdatum_angabe(rechnung.rechnungsdatum),
        'period': f"{rechnung.beginn.strftime('%d.%m.%Y')} - {rechnung.ende.strftime('%d.%m.%Y')}",
        'prorated_amount': runde(verbrauchsteil),
        'total_consumption': round(summe_zaehler, 1),
        'vermieter_consumption': round(rest_menge, 1),
        'leerstand_amount': leer_betrag,
        'eigennutzung_amount': eigen_betrag,
        'amount': leer_betrag + eigen_betrag,
        'units': einheiten,
        'description': 'Nicht auf die Mieter umgelegt: ' + ', '.join(teile),
    }


# ---------------------------------------------------------------------------
# Die Heizkosten (R-HK-01, NK-049)
# ---------------------------------------------------------------------------
# Heizkosten verteilt nicht das Kostenprofil, sondern § 7 HeizkostenV. Die
# Vorschrift ist zwingend (§ 2 HeizkostenV geht sogar rechtsgeschaeftlichen
# Bestimmungen vor), und sie verteilt nicht die einzelne Rechnung, sondern
# die **Summe** der Posten des § 7 Abs. 2: 50 bis 70 vom Hundert nach
# erfasstem Waermeverbrauch, der Rest nach Wohnflaeche.
#
# Deshalb laufen diese Rechnungen nicht durch die Umlageschleife. Sie werden
# vorher abgetrennt, je Anlage zu einer Masse zusammengelegt und als **eine**
# Zeile mit zwei Unterposten ausgewiesen (D-47). Eine Zeile je Rechnung waere
# eine Aufteilung, die das Gesetz nicht kennt: der Verbrauchsanteil bezieht
# sich auf die Masse, nicht auf den Brennstoff allein.


def ist_heizwaermezaehler(zaehler) -> bool:
    """Ob dieser Zaehler Raumwaerme misst, deren Verbrauch dem Wetter folgt (D-115).

    Heizung (Nr. 4) und verbundene Anlage (Nr. 6), jeder Zaehler einer
    Heizungsanlage, ohne Katalog der Name -- aber nie das Warmwasser in
    Kubikmetern, das fliesst im Sommer wie im Winter.
    """
    if ist_warmwasserzaehler(zaehler):
        return False
    if zaehler.kategorie_betrkv_nr in (4, 6) or zaehler.heizungsanlage_id is not None:
        return True
    name = (zaehler.kategorie_name or '').lower()
    return zaehler.kategorie_betrkv_nr is None and any(
        x in name for x in ('heiz', 'wärme', 'waerme'))


def ist_warmwasserzaehler(zaehler) -> bool:
    """Ob dieser Zaehler das Warmwasser erfasst und nicht die Waerme.

    Entschieden wird nach der Einheit: ein Warmwasserzaehler zaehlt
    Kubikmeter, ein Waermezaehler Kilowattstunden. Das ist kein Kunstgriff,
    sondern der Unterschied der beiden Vorschriften -- § 8 verteilt nach
    Kubikmetern Warmwasser, § 7 nach erfasster Waerme. Die Einheit kommt
    aus der BetrKV-Nummer (NK-121): der Wärmezähler der verbundenen Anlage
    (Nr. 6) heisst "Warmwasser" und bleibt trotzdem Wärmezähler.
    """
    return einheit_fuer(
        zaehler.kategorie_name, zaehler.kategorie_betrkv_nr) == 'm³'


def _anlagenzaehler(vorgang: Vorgang, anlage_id: int,
                    zweck: Optional[str] = None) -> list:
    """Die Zaehler, die fuer diese Anlage erfassen -- je Wohnung einer.

    Die Zuordnung steht am Zaehler (D-45) und wird nicht aus der Kostenart
    erraten. Ein Hauptzaehler taucht hier nicht auf: erfasst wird, was die
    einzelne Wohnung verbraucht hat, und daraus bildet sich der Nenner.

    Ohne ``zweck`` kommen alle Zaehler der Anlage; mit ``zweck`` nur die des
    einen Zwecks. Eine verbundene Anlage hat seit NK-050 beides nebeneinander
    -- Waermezaehler fuer § 7, Warmwasserzaehler fuer § 8 --, und in jeden
    Nenner gehoeren nur die eigenen.
    """
    zaehler = [
        z for z in _nach_id(vorgang.zaehler)
        if z.heizungsanlage_id == anlage_id and z.wohnung_id is not None
    ]
    if zweck is None:
        return zaehler
    warm = zweck == heizung.WARMWASSER
    return [z for z in zaehler if ist_warmwasserzaehler(z) is warm]


def anlagen_wohnungen(vorgang: Vorgang, anlage, mehrere: bool) -> list:
    """Die Wohnungen, die an dieser Anlage haengen.

    Zwei Faelle, eine Regel dahinter: gezaehlt wird, wer von der Anlage
    versorgt wird.

    Hat das Objekt **eine** Anlage, versorgt sie jede aktive Wohnung -- ausser
    den Selbstversorgern. Wer seine Waerme selbst erzeugt, nimmt an der Anlage
    des Hauses nicht teil und gehoert in keinen der beiden Nenner (R-CO2-03);
    stuende seine Flaeche im Nenner, truege er einen Teil fremder Heizkosten.

    Hat das Objekt **zwei** Anlagen -- Vorderhaus und Hinterhaus --, laesst
    sich das nicht mehr sagen, und dann entscheidet der Waermezaehler: eine
    Wohnung haengt an der Anlage, fuer die sie einen Zaehler hat. Wer die
    zweite Anlage anlegt, pflegt damit auch die Zuordnung.
    """
    aktive = [w for w in vorgang.wohnungen if w.ist_aktiv and not w.selbstversorger]
    if not mehrere:
        return aktive
    zugeordnet = {z.wohnung_id for z in _anlagenzaehler(vorgang, anlage.id)}
    return [w for w in aktive if w.id in zugeordnet]


def heizkosten_abtrennen(vorgang: Vorgang, rechnungen: Sequence[Rechnung]) -> tuple:
    """``(uebrige, {anlage_id: [rechnungen]})`` -- die Heizkosten heraus.

    Abgetrennt wird, was einer Anlage zugeordnet ist. Die Abrechnungsart aus
    dem Kostenprofil wird dabei uebergangen (D-46): § 7 HeizkostenV ist
    zwingendes Recht, und eine Heizkostenrechnung nach Personen oder nach
    Flaeche allein zu verteilen waere eine Abrechnung, die der Mieter nicht
    gegen sich gelten lassen muesste.

    **Eine Ausnahme: ``ignoriert``.** Das ist keine andere Verteilung, sondern
    der Verzicht des Vermieters -- er nimmt diesen Mieter aus der Kostenart
    heraus. Das steht ihm frei, es geht nur zu seinen Lasten, und es bleibt
    deshalb wirksam. Der Kategorienfilter wirkt ohnehin schon frueher.
    """
    bekannt = {a.id: a for a in vorgang.heizungsanlagen}
    uebrig = []
    je_anlage = {}
    for r in rechnungen:
        anlage = bekannt.get(r.heizungsanlage_id)
        if anlage is None:
            uebrig.append(r)
            continue
        if abrechnungsart_von(vorgang.profile, r.kategorie) == 'ignoriert':
            uebrig.append(r)
            continue
        je_anlage.setdefault(anlage.id, []).append(r)
    return uebrig, je_anlage


def _co2_einstufung(vorgang: Vorgang, je_anlage: Mapping[int, list],
                    warnings: list) -> Optional[dict]:
    """Die Einstufung des Gebaeudes nach § 5 CO2KostAufG -- oder ``None``.

    ``None`` heisst: keine Aufteilung. Dafuer gibt es drei Gruende, und nur
    einer von ihnen ist still: keine Heizkostenrechnung im Spiel (keine
    Anlage, nichts zu teilen); **fehlende CO2-Angaben** an mindestens einer
    Rechnung -- dann steht die blockierende Warnung ``E-CO2-AUSWEIS-FEHLT``
    in den Warnungen, denn ein Ausweis nach § 7 CO2KostAufG ohne die
    Angaben ist unvollstaendig, und eine halbe Einstufung waere schlimmer
    als keine (D-54: alles oder nichts); oder keine Wohnflaeche, die als
    Nenner bleiben koennte.

    Ermittelt wird **fuers Gebaeude**, nicht fuer das Mietverhaeltnis: alle
    Heizrechnungen der Abrechnung zaehlen, auch die vor dem Einzug oder
    nach dem Auszug (§ 5 Abs. 1: der Ausstoss des Gebaeudes im Zuge der
    jaehrlichen Abrechnung). Die Bezugsflaeche sind alle aktiven Wohnungen
    ohne die Selbstversorger (R-CO2-03) -- dieselbe Grundlage, auf der die
    Anlagen ihre Einheiten finden (D-45).
    """
    heizrechnungen = [r for gruppe in je_anlage.values() for r in gruppe]
    if not heizrechnungen:
        return None

    fehlend = [r for r in heizrechnungen
               if r.co2_kosten is None or r.co2_emission_kg is None]
    if fehlend:
        warnings.append(co2.HINWEIS_AUSWEIS_FEHLT.format(
            rechnungen=', '.join(r.nummer or f'#{r.id}' for r in fehlend)))
        return None

    flaeche = sum(
        (w.qm or 0) for w in vorgang.wohnungen
        if w.ist_aktiv and not w.selbstversorger)
    if flaeche <= 0:
        return None

    emission = sum(
        (dec(r.co2_emission_kg) for r in heizrechnungen), NULL)
    kosten = sum(
        (dec(r.co2_kosten) for r in heizrechnungen), NULL)
    wert = float(emission) / flaeche
    # Die Tabelle bleibt jaehrlich: die anteilige Kuerzung des § 5 Abs. 1
    # Satz 4 greift nur bei einem **vereinbarten** unterjaehrigen
    # Abrechnungszeitraum (F-31), nicht bei einem Zeitraum, der faktisch
    # kuerzer ist, weil der Mieter unterjaehrig wechselt. Das gestutzte
    # Mietzeitfenster ist keine Vereinbarung -- der Kern stuft deshalb
    # gegen die Jahestabelle ein. ``co2.stufe_fuer`` kennt die Kuerzung
    # dennoch; sie anzuschliessen, braucht den vereinbarten Zeitraum am
    # Vorgang, nicht das Fenster des einzelnen Mieters.
    stufe = co2.stufe_fuer(wert)
    mieter_prozent, vermieter_prozent = co2.anteile(stufe)
    return {
        'stufe': stufe,
        'mieter_prozent': mieter_prozent,
        'vermieter_prozent': vermieter_prozent,
        'emission_kg': float(co2.runde_wert(emission)),
        'kg_pro_qm': float(co2.runde_wert(wert)),
        'kosten': runde(kosten),
        'quellen': [
            {
                'invoice_id': r.id,
                'invoice_number': r.nummer,
                'rechnungsdatum': rechnungsdatum_angabe(r.rechnungsdatum),
                'emission_kg': float(dec(r.co2_emission_kg)),
                'kosten': runde(r.co2_kosten),
            }
            for r in heizrechnungen
        ],
    }


def anlagen_warmwassermenge(anlage, gesamt_qm) -> tuple:
    """``(Waermemenge, Fehlgrund)`` fuer das Warmwasser der Anlage (§ 9 Abs. 2).

    Die drei Wege in der Rangfolge des Gesetzes -- gemessen, gerechnet,
    geschaetzt --, und welcher gilt, steht an der Anlage (D-50). Fehlt die
    Angabe, ist das kein Fehler, sondern ein Grund: der Aufrufer verteilt
    dann alles als Heizkosten und weist darauf hin.
    """
    if not anlage.warmwasser_weg:
        return None, heizung.OHNE_WEG

    weg = heizung.pruefe_warmwasserweg(anlage.warmwasser_weg)
    if weg == heizung.WW_ZAEHLER:
        if anlage.warmwasser_kwh is None:
            return None, heizung.OHNE_WERTE
        return dec(anlage.warmwasser_kwh), None

    if weg == heizung.WW_FORMEL:
        if (anlage.warmwasser_volumen_m3 is None
                or anlage.warmwasser_temperatur_c is None):
            return None, heizung.OHNE_WERTE
        return heizung.warmwassermenge_formel(
            anlage.warmwasser_volumen_m3,
            anlage.warmwasser_temperatur_c), None

    # Die Ersatzformel rechnet mit der Wohnflaeche **an dieser Anlage**, nicht
    # mit der des Hauses -- derselbe Nenner wie beim Grundkostenanteil.
    if not gesamt_qm:
        return None, heizung.OHNE_WERTE
    return heizung.warmwassermenge_ersatz(gesamt_qm), None


def anlagen_warmwasseranteil(anlage, gesamt_qm) -> tuple:
    """``(Anteil zwischen 0 und 1, Fehlgrund)`` -- § 9 Abs. 1 HeizkostenV.

    Wie viel der Masse auf das Warmwasser entfaellt. Eine reine Heizung gibt
    nichts ab, eine reine Warmwasseranlage alles; nur die verbundene Anlage
    wird gerechnet.

    Ein Fehlgrund heisst: es bleibt bei einer Zeile, und der Vermieter
    erfaehrt, was fehlt. Auch widersprechende Angaben brechen die Abrechnung
    nicht ab, sondern werden zum Grund -- dieselbe Linie wie bei der
    unvollstaendigen Erfassung (D-48). Eine Abrechnung, die der Mieter nicht
    gegen sich gelten lassen muss, ist immer noch besser als gar keine, und
    der Weg zurueck ist derselbe: die Angabe nachtragen.
    """
    if anlage.versorgt == heizung.WARMWASSER:
        return dec(1), None
    if anlage.versorgt != heizung.VERBUNDEN:
        return dec(0), None

    try:
        menge, grund = anlagen_warmwassermenge(anlage, gesamt_qm)
        if grund:
            return dec(0), grund
        if anlage.brennstoff_menge is None or dec(anlage.brennstoff_menge) <= 0:
            return dec(0), heizung.OHNE_GESAMTMENGE
        # Steht der Gesamtverbrauch in Litern oder Kubikmetern Brennstoff,
        # muss die Waermemenge erst in dieselbe Einheit -- sonst nicht.
        if anlage.heizwert_kwh is not None:
            menge = heizung.brennstoffanteil(menge, anlage.heizwert_kwh)
        return heizung.warmwasseranteil(menge, anlage.brennstoff_menge), None
    except heizung.HeizungsFehler as fehler:
        return dec(0), str(fehler)


def _verteilzeile(vorgang: Vorgang, anlage, rechnungen: Sequence[Rechnung],
                  vermieter_positionen: list, *, zweck: str, ww_anteil,
                  wohnungen: list, ids: set, gesamt_qm,
                  zaehler: dict, trennungsgrund,
                  co2_aufteilung: Optional[dict] = None) -> Optional[dict]:
    """Eine Abrechnungszeile fuer **einen Zweck** einer Anlage, oder ``None``.

    ``None`` heisst: keine der Rechnungen faellt in den Abrechnungszeitraum.

    ``zweck`` ist ``heizung.HEIZUNG`` oder ``heizung.WARMWASSER``, ``ww_anteil``
    der Bruch aus ``anlagen_warmwasseranteil``. Getrennt wird je Rechnung und
    genau einmal: ``trenne_verbundene`` gibt beide Teile zurueck, und diese
    Zeile nimmt sich ihren. Zweimal zu multiplizieren waere derselbe Fehler
    wie zweimal zu runden -- die Teile ergaeben zusammen nicht mehr die Masse.

    Gerechnet wird je Rechnung und erst danach summiert. Das ist kein
    Widerspruch dazu, dass § 7 Abs. 1 die **Masse** teilt: der Satz ist ein
    fester Anteil, die Teilung also linear, und alle Rechnungen einer Anlage
    tragen denselben Satz -- er haengt an der Anlage. Je Rechnung zu rechnen
    ist noetig, weil die Rechnungen verschiedene Zeitraeume haben und der
    Grundkostenanteil zeitanteilig faellt.

    Der **Verbrauchsanteil** faellt dagegen nicht zeitanteilig: die
    Zeitanteiligkeit steckt schon in der gemessenen Menge. Wer im halben Jahr
    auszieht, hat in diesem halben Jahr eine bestimmte Menge verbraucht, und
    genau die zaehlt -- dieselbe Ueberlegung wie beim Personenschluessel
    (R-NUM-04) und beim Eigenverbrauch am Zaehler.
    """
    eigener_zaehler = zaehler.get(vorgang.wohnung.id)

    # Erfasst ist der Verbrauch nur, wenn ihn **jede** Wohnung der Anlage
    # erfasst. Fehlt auch nur ein Zaehler, laesst sich kein Nenner bilden,
    # der die Wahrheit sagt: der Anteil der uebrigen waere zu hoch.
    ohne_zaehler = [w.name for w in wohnungen if w.id not in zaehler]

    # Derselbe Satz fuer beide Zwecke: § 8 Abs. 1 verweist fuer die
    # Warmwasserkosten auf denselben Rahmen wie § 7 Abs. 1. Ein zweiter Satz
    # waere ein zweites Feld -- und eine Angabe, die kaum jemand pflegt.
    satz = heizung.pruefe_anteil(
        anlage.verbrauchsanteil_prozent, anlage.sonderfall_70)
    eigener = eigener_zaehler is not None
    einheit = einheit_fuer(
        eigener_zaehler.kategorie_name if eigener
        else ('Warmwasser' if zweck == heizung.WARMWASSER else 'Waerme'),
        eigener_zaehler.kategorie_betrkv_nr if eigener
        else (betrkv.NR_WARMWASSER if zweck == heizung.WARMWASSER
              else betrkv.NR_HEIZUNG))

    verbrauchsanteil = NULL
    flaechenanteil = NULL
    # Die CO2-Kosten des Mieters und was beim Vermieter bleibt (NK-053,
    # D-54). Ohne Einstufung des Gebäudes bleiben alle vier null und
    # unberuehrt -- dann gibt es in dieser Zeile kein CO2.
    co2_verbrauchsanteil = NULL
    co2_flaechenanteil = NULL
    co2_flat = NULL
    masse = NULL
    masse_anteilig = NULL
    eigener_verbrauch = 0.0
    gesamtverbrauch = 0.0
    ohne_staende = False
    # § 9b (NK-051): welche Wechseldaten ohne Zwischenablesung blieben und
    # welche gelesen wurden -- fuer Ausweis und Warnung.
    ersatz_daten = []
    gelesen_gesamt = []
    belege = []
    beginn = min(r.beginn for r in rechnungen)
    ende = max(r.ende for r in rechnungen)
    ende_g = max(r.ende_grenze for r in rechnungen)

    for inv in rechnungen:
        invoice_days = tage(inv.beginn, inv.ende_grenze)
        overlap_von = max(inv.beginn, vorgang.beginn)
        overlap_bis = min(inv.ende_grenze, vorgang.ende_grenze)
        overlap_days = tage(overlap_von, overlap_bis)
        if overlap_days <= 0:
            continue

        # § 9 vor § 7: erst die Masse trennen, dann verteilen. Beide Teile
        # kommen aus einem Aufruf, damit sie zusammen die Rechnung ergeben.
        warm, heiz = heizung.trenne_verbundene(inv.betrag, ww_anteil)
        betrag = warm if zweck == heizung.WARMWASSER else heiz

        time_fraction = dec(overlap_days) / dec(invoice_days)
        # § 6 vor § 7 (NK-053, D-54): die CO2-Kosten sind keine Masse der
        # Heizkostenverordnung. § 6 Abs. 1 teilt sie nach der Stufe des
        # Gebaeudes zwischen Vermieter und Mieter, und nur der Mieteranteil
        # laeuft danach durch die § 7-Maschinerie -- mit demselben Satz,
        # denn § 6 Abs. 3 verweist auf § 7 Abs. 1 Saetze 1 bis 3. Erst
        # herausziehen, dann verteilen: bei einer verbundenen Anlage
        # zerfaellt der CO2-Teil je Zweck, und beide Zeilen nehmen sich
        # ihren -- dieselbe einmalige Trennung wie beim Rechnungsbetrag.
        # Ohne Einstufung (fehlende Angaben, R-CO2-02) bleibt alles null.
        co2_teil = NULL
        co2_mieter = NULL
        co2_vermieter = NULL
        if co2_aufteilung:
            co2_warm, co2_heiz = heizung.trenne_verbundene(
                dec(inv.co2_kosten), ww_anteil)
            co2_teil = dec(
                co2_warm if zweck == heizung.WARMWASSER else co2_heiz
            ) * time_fraction
            co2_mieter, co2_vermieter = co2.teile_aufteilung(
                co2_teil, co2_aufteilung['mieter_prozent'])
            co2_flat += co2_vermieter
            betrag -= co2_teil
        masse += betrag
        masse_anteilig += betrag * time_fraction

        summe_zaehler = sum(
            verbrauch(z, inv.beginn, inv.ende) for z in zaehler.values())
        # § 9b (NK-051, D-52): liegt ein Mietrand -- Einzug oder Auszug --
        # innerhalb des Rechnungszeitraums, misst nur eine **Zwischenablesung**
        # an diesem Datum die Grenze zwischen den Mietverhaeltnissen. Fehlt
        # sie, wird nicht still interpoliert: die gemessene Menge der Wohnung
        # wird zeitanteilig geteilt (Ersatzmassstab), und die Zeile sagt es.
        # Nur der als Zwischenablesung markierte Stand zaehlt -- ob eine
        # Ablesung wirklich die des Wechsels ist, kann nur der Vermieter
        # sagen; ein zufaelliger Stand in der Naehe ist kein Messwert der
        # Grenze.
        mietraende = [
            g for g in (vorgang.mieter.einzug, vorgang.mieter.auszug)
            if g and inv.beginn < g < inv.ende_grenze]
        gelesen = []
        fehlende = []
        for g in mietraende:
            treffer = [
                s for s in (eigener_zaehler.staende if eigener_zaehler else ())
                if s.art == heizung.ZWISCHENABLESUNG and s.datum == g]
            if treffer:
                gelesen.append(
                    {'datum': g.isoformat(), 'stand': float(treffer[0].gesamt)})
            else:
                fehlende.append(g)
        if fehlende:
            # Ersatzmassstab: die gemessene Menge der Wohnung, zeitanteilig
            # geteilt. Sie bleibt in der Wohnung -- nicht die interpolierten
            # Stuecke zweier Schranken verteilen die Kosten, sondern die Tage.
            eigen = (
                verbrauch(eigener_zaehler, inv.beginn, inv.ende)
                * float(time_fraction)
                if eigener_zaehler else 0.0
            )
            ersatz_daten.extend(
                g.strftime('%d.%m.%Y') for g in fehlende)
        else:
            eigen = (
                verbrauch_in(eigener_zaehler, overlap_von, overlap_bis)['consumption']
                if eigener_zaehler else 0.0
            )
        gelesen_gesamt.extend(gelesen)
        gesamtverbrauch += summe_zaehler
        eigener_verbrauch += eigen

        erfasst = not ohne_zaehler and summe_zaehler > 0
        if not erfasst:
            ohne_staende = ohne_staende or not ohne_zaehler
            # Kein erfasster Verbrauch heisst nicht: keine Verteilung. Die
            # Kosten sind angefallen und muessen getragen werden. Sie gehen
            # dann ganz nach Flaeche -- mit einer Warnung, denn dem Mieter
            # steht dafuer das Kuerzungsrecht des § 12 zu (NK-052).
            verbrauchsteil, grundteil = NULL, betrag
            # Und die CO2-Masse ebenso (D-54): dieselbe Degradation, auf
            # der anderen Masse.
            co2_verbrauchsteil, co2_grundteil = NULL, co2_mieter
        else:
            verbrauchsteil, grundteil = heizung.teile_masse(betrag, satz)
            co2_verbrauchsteil, co2_grundteil = heizung.teile_masse(
                co2_mieter, satz)

        verbrauchsanteil += heizung.nach_verbrauch(
            verbrauchsteil, eigen, summe_zaehler)
        grundteil_anteilig = grundteil * time_fraction
        flaechenanteil += heizung.nach_flaeche(
            grundteil_anteilig, vorgang.wohnung.qm or 0, gesamt_qm)
        co2_verbrauchsanteil += heizung.nach_verbrauch(
            co2_verbrauchsteil, eigen, summe_zaehler)
        co2_flaechenanteil += heizung.nach_flaeche(
            co2_grundteil * time_fraction, vorgang.wohnung.qm or 0, gesamt_qm)

        # Was vom Grundteil beim Vermieter bleibt (R-NUM-05). Der Nenner ist
        # hier nicht das ganze Haus, sondern die Flaeche an dieser Anlage --
        # deshalb ``nur``. Der Verbrauchsteil braucht keine qm-Position:
        # die leerstehende Wohnung hat einen Waermezaehler, ihr Verbrauch
        # steht im Nenner, ihr Anteil bleibt also schon von selbst beim
        # Vermieter. Ausgewiesen wird er unten als verbrauchsabhaengige
        # Vermieterposition (NK-051).
        anteil = _vermieteranteil(
            vorgang, f"{heizung.ZEILENTITEL[zweck]} ({anlage.name})", inv,
            grundteil_anteilig, gesamt_qm, overlap_von, overlap_bis, nur=ids)
        if anteil:
            vermieter_positionen.append(anteil)

        # Und der Verbrauchsteil: was leer steht oder eigengenutzt wird,
        # verbraucht dennoch Waerme von dieser Anlage. Sein Anteil bleibt
        # beim Vermieter -- ausgewiesen, nicht zwischen den Zeilen
        # verschwunden (D-47, R-NUM-05).
        if erfasst:
            anteil = _vermieterverbrauchsanteil(
                vorgang, f"{heizung.ZEILENTITEL[zweck]} ({anlage.name})", inv,
                verbrauchsteil, summe_zaehler, zaehler, einheit, ids,
                fenster=(overlap_von, overlap_bis))  # F-133: nur dieser Zeitraum
            if anteil:
                vermieter_positionen.append(anteil)

        # Und dasselbe fuer die CO2-Masse (D-54): Leerstand und Eigennutzung
        # tragen auch am Mieteranteil der CO2-Kosten -- nach denselben
        # Regeln und denselben Messwerten wie oben, nur an der anderen
        # Masse. Die Zuordnungslogik ist dieselbe Funktion; nur der Betrag,
        # den sie verteilt, ist der CO2-Teil.
        co2_rest = _vermieteranteil(
            vorgang, f"CO2-Kosten ({anlage.name})", inv,
            co2_grundteil * time_fraction, gesamt_qm,
            overlap_von, overlap_bis, nur=ids)
        if co2_rest:
            vermieter_positionen.append(co2_rest)
        if erfasst:
            co2_rest = _vermieterverbrauchsanteil(
                vorgang, f"CO2-Kosten ({anlage.name})", inv,
                co2_verbrauchsteil, summe_zaehler, zaehler, einheit, ids,
                fenster=(overlap_von, overlap_bis))
            if co2_rest:
                vermieter_positionen.append(co2_rest)

        belege.append({
            'invoice_id': inv.id,
            'invoice_number': inv.nummer,
            'rechnungsdatum': rechnungsdatum_angabe(inv.rechnungsdatum),
            'kostenart': inv.heizkostenart,
            'kostenart_text': heizung.bezeichnung(inv.heizkostenart)
                              if inv.heizkostenart else None,
            'provider_name': inv.versorger_name or 'Unbekannt',
            'period': f"{inv.beginn.strftime('%d.%m.%Y')} - {inv.ende.strftime('%d.%m.%Y')}",
            # R-DOC-01 Punkt 8: der Verweis auf den Beleg -- Name und Seiten
            # wie bei den uebrigen Zeilen (beleg_angabe haengt ", Seiten N"
            # an), damit die Belegliste je Rechnung dasselbe zeigen kann.
            'doc_name': beleg_angabe(inv.beleg)[0] or None,
            'doc_path': beleg_angabe(inv.beleg)[1],
            # ``amount`` ist der Teil der Rechnung, der auf diesen Zweck
            # entfaellt; bei einer getrennten Anlage steht der volle Betrag
            # daneben, sonst sind beide gleich.
            'amount': runde(betrag),
            'rechnungsbetrag': inv.betrag,
            'prorated_amount': runde(betrag * time_fraction),
            # Mit erfasstem Verbrauch ist ``prorated_amount`` nur der Tagesanteil
            # der Rechnung -- angesetzt wird aber der Verbrauch am Zaehler (am
            # Stichtag nach Gradtagen geschaetzt). Die Belegliste darf den
            # Tagesbetrag dann nicht als angesetzt ausweisen.
            'nach_verbrauch': erfasst,
            'grundteil': runde(grundteil * time_fraction),
            'verbrauchsteil': runde(verbrauchsteil),
            # § 6 CO2KostAufG (NK-053): der Teil der Rechnung, der vor der
            # Verteilung herausgenommen wurde, und wie er sich teilte.
            'co2_kosten': runde(co2_teil),
            'co2_mieteranteil': runde(co2_mieter),
            'co2_vermieteranteil': runde(co2_vermieter),
            # § 9b: an welchen Wechseldaten dieser Rechnung der Ersatzmassstab
            # galt (NK-051). Ohne solchen Wechsel: None.
            'ersatzmassstab': (
                sorted({g.strftime('%d.%m.%Y') for g in fehlende})
                if fehlende else None),
        })

    if not belege:
        return None

    fehlgrund = None
    if ohne_zaehler:
        fehlgrund = heizung.OHNE_ZAEHLER.format(
            zaehler=heizung.ZAEHLERART[zweck],
            wohnungen=', '.join(ohne_zaehler))
    elif ohne_staende:
        fehlgrund = heizung.OHNE_STAENDE

    tenant_cost = verbrauchsanteil + flaechenanteil
    co2_anteil = co2_verbrauchsanteil + co2_flaechenanteil
    if co2_aufteilung:
        tenant_cost += co2_anteil
    einzeln = rechnungen[0] if len(rechnungen) == 1 else None

    if co2_aufteilung and co2_flat:
        # Der flache Vermieteranteil des § 6: er folgt keiner der beiden
        # Verteilmassen, sondern gehoert dem Vermieter von vornherein. Ein
        # Positionsposten je Zeile, damit das Blatt sagt, wohin er ging
        # (R-NUM-05) -- und damit der Ausweis des § 7 seine Eurosumme hat.
        vermieter_positionen.append({
            'category': f"CO2-Kosten ({anlage.name})",
            'invoice_id': einzeln.id if einzeln else None,
            'invoice_number': einzeln.nummer if einzeln else None,
            'rechnungsdatum': (
                rechnungsdatum_angabe(einzeln.rechnungsdatum)
                if einzeln else None),
            'period': (
                f"{beginn.strftime('%d.%m.%Y')} - "
                f"{ende.strftime('%d.%m.%Y')}"),
            'prorated_amount': runde(co2_flat),
            'amount': runde(co2_flat),
            # Die Bilanzschluessel jeder Vermieterposition (R-NUM-05): der
            # flache Anteil traegt zu keiner der beiden Ruicken.
            'leerstand_amount': NULL,
            'eigennutzung_amount': NULL,
            'description': (
                f"Vermieteranteil an den CO2-Kosten nach § 6 CO2KostAufG "
                f"(Stufe {co2_aufteilung['stufe']}: "
                f"{co2_aufteilung['vermieter_prozent']} % Vermieter, "
                f"{co2_aufteilung['mieter_prozent']} % Mieter)"),
        })
    doc_name, doc_path = beleg_angabe(einzeln.beleg) if einzeln else (None, None)

    titel = heizung.ZEILENTITEL[zweck]
    vorschrift = heizung.VORSCHRIFT[zweck]

    if fehlgrund:
        beschreibung = (
            f"{titel} nach {vorschrift}, ganz nach Wohnfläche "
            f"(kein erfasster Verbrauch)"
        )
        unterposten = [{
            'type': 'heizung_flaeche',
            'description': (
                f"Grundkosten 100 % nach Wohnfläche "
                f"({vorgang.wohnung.qm} von {gesamt_qm} qm)"
            ),
            'cost': runde(flaechenanteil),
        }]
    else:
        beschreibung = (
            f"{titel} nach {vorschrift}: {satz} % nach erfasstem "
            f"Verbrauch, {heizung.flaechenanteil(satz)} % nach Wohnfläche"
        )
        # § 9b (NK-051): blieben Wechseldaten ohne Zwischenablesung, sagt die
        # Zeile es -- der Ersatzmassstab ist kein stiller.
        if ersatz_daten:
            beschreibung += (
                ". Keine Zwischenablesung am "
                f"{', '.join(sorted(set(ersatz_daten)))}: die Verbrauchskosten "
                "wurden zeitanteilig verteilt (Ersatzmaßstab nach § 9b "
                "HeizkostenV)."
            )
        unterposten = [
            {
                'type': 'heizung_verbrauch',
                'description': (
                    f"Verbrauchskosten {satz} % "
                    f"({eigener_verbrauch:.1f} von {gesamtverbrauch:.1f} {einheit})"
                ),
                'cost': runde(verbrauchsanteil),
            },
            {
                'type': 'heizung_flaeche',
                'description': (
                    f"Grundkosten {heizung.flaechenanteil(satz)} % nach Wohnfläche "
                    f"({vorgang.wohnung.qm} von {gesamt_qm} qm)"
                ),
                'cost': runde(flaechenanteil),
            },
        ]

    if co2_aufteilung:
        unterposten.append({
            'type': 'heizung_co2',
            'description': (
                f"davon CO2-Kosten (Stufe {co2_aufteilung['stufe']}: "
                f"{co2_aufteilung['mieter_prozent']} % Mieteranteil, "
                f"{co2_aufteilung['vermieter_prozent']} % Vermieteranteil)"),
            'cost': runde(co2_anteil),
        })

    # Restcent-Regel R1 (R-NUM-02), wie bei jeder anderen Zeile: die
    # Unterposten muessen sich zum Zeilenbetrag addieren.
    # Vorher der eigene CO2-Anteil (§ 6 CO2KostAufG, NK-053, D-54) als
    # eigener Unterposten -- er rechnet nach einem anderen Gesetz als die
    # Zeile ueber ihm, und der Mieter sieht das.
    unterposten = [
        dict(posten, cost=betrag)
        for posten, betrag in zip(
            unterposten,
            restcent_auf_letzte([p['cost'] for p in unterposten], tenant_cost),
        )
    ]

    getrennt = anlage.versorgt == heizung.VERBUNDEN and not trennungsgrund
    return {
        'category': f"{titel} ({anlage.name})",
        'invoice_id': einzeln.id if einzeln else None,
        'invoice_number': einzeln.nummer if einzeln else None,
        'rechnungsdatum': (
            rechnungsdatum_angabe(einzeln.rechnungsdatum)
            if einzeln else None),
        'provider_id': einzeln.versorger_id if einzeln else None,
        'provider_name': (
            einzeln.versorger_name or 'Unbekannt' if einzeln
            else f"{len(belege)} Rechnungen"
        ),
        'period': f"{beginn.strftime('%d.%m.%Y')} - {ende.strftime('%d.%m.%Y')}",
        'total_amount': runde(masse),
        'prorated_amount': runde(masse_anteilig),
        'billing_type': 'heizkosten',
        'description': beschreibung,
        'tenant_cost': runde(tenant_cost),
        'overlap_days': tage(max(beginn, vorgang.beginn),
                             min(ende_g, vorgang.ende_grenze)),
        'invoice_days': tage(beginn, ende_g),
        'invoice_total_amount': runde(masse),
        'doc_name': doc_name,
        'doc_path': doc_path,
        'sub_items': unterposten,
        'meter_details': None,
        # R-DOC-01 Punkt 6/7: der Weg vom Rechnungsbetrag zur Masse steht
        # als Satz an der Zeile -- bei unterjaehrigem Zeitraum mit Tagen
        # und Zwischenergebnis. Die Teilposten darunter sagen dann, wie
        # sich die Masse auf Grund- und Verbrauchsteil teilt.
        'rechenweg': rechenweg_rechnungsbetrag(
            masse,
            tage(max(beginn, vorgang.beginn), min(ende_g, vorgang.ende_grenze)),
            tage(beginn, ende_g),
            masse_anteilig,
        ),
        # Alles, was das Blatt zur Begruendung braucht (R-DOC-01): die Anlage,
        # der Satz und woher er kommt, die Zaehlerstaende und die einzelnen
        # Rechnungen, die zur Masse zusammengelegt wurden.
        'heizung_details': {
            'anlage_id': anlage.id,
            'anlage': anlage.name,
            'versorgt': anlage.versorgt,
            'zweck': zweck,
            # Nr. 4 fuer die Waerme, Nr. 5 fuer das Warmwasser -- aber Nr. 6,
            # solange eine verbundene Anlage ungetrennt bleibt. Die Nummer
            # sagt dem Mieter, welche Betriebskosten er vor sich hat.
            'betrkv_nr': heizung.betrkv_nr(
                anlage.versorgt if trennungsgrund else zweck),
            'verbrauchsanteil_prozent': satz,
            'flaechenanteil_prozent': heizung.flaechenanteil(satz),
            'sonderfall_70': bool(anlage.sonderfall_70),
            'erfasst': fehlgrund is None,
            'fehlgrund': fehlgrund,
            'tenant_consumption': round(eigener_verbrauch, 1),
            'total_consumption': round(gesamtverbrauch, 1),
            'unit': einheit,
            'tenant_sqm': vorgang.wohnung.qm,
            'total_sqm': gesamt_qm,
            'apartments': len(wohnungen),
            # Die Trennung nach § 9, zum Ausweisen auf dem Blatt (R-HK-03):
            # welcher Weg, welcher Anteil -- und warum es nicht ging.
            'warmwasser_weg': anlage.warmwasser_weg if getrennt else None,
            'warmwasser_weg_text': (
                heizung.WW_WEG_TEXT.get(anlage.warmwasser_weg)
                if getrennt else None),
            'warmwasser_anteil_prozent': (
                (dec(ww_anteil) * 100).quantize(Decimal('0.01'))
                if getrennt else None),
            'trennungsgrund': trennungsgrund,
            # § 6 CO2KostAufG (NK-053): Stufe und Anteile des Gebaeudes,
            # der eigene Anteil in Euro, und was der Vermieter von den
            # CO2-Kosten dieser Zeile behaelt. None ohne Einstufung --
            # dann steht die blockierende Warnung im Ergebnis.
            'co2': {
                'stufe': co2_aufteilung['stufe'],
                'mieter_prozent': co2_aufteilung['mieter_prozent'],
                'vermieter_prozent': co2_aufteilung['vermieter_prozent'],
                'anteil': runde(co2_anteil),
                'vermieteranteil': runde(co2_flat),
            } if co2_aufteilung else None,
            # § 9b (NK-051, R-HK-04): die Zwischenablesungen der Mietraender
            # (Datum und Stand) und die Wechseldaten, an denen der
            # Ersatzmassstab galt. Beides None, wenn kein Nutzerwechsel
            # innerhalb des Zeitraums lag.
            'zwischenablesung': gelesen_gesamt or None,
            'ersatzmassstab': (
                {'daten': sorted(set(ersatz_daten))} if ersatz_daten else None),
            'rechnungen': belege,
        },
    }


def _anlagenzeilen(vorgang: Vorgang, anlage, rechnungen: Sequence[Rechnung],
                   mehrere: bool, vermieter_positionen: list,
                   co2_aufteilung: Optional[dict] = None) -> list:
    """Die Zeilen einer Anlage -- eine je Zweck, hoechstens zwei.

    Eine leere Liste heisst: diese Anlage versorgt den Mieter nicht (er ist
    Selbstversorger oder wohnt im anderen Haus), oder keine ihrer Rechnungen
    faellt in den Zeitraum.

    Zwei Zeilen entstehen nur bei einer verbundenen Anlage, deren Trennung
    gelingt: dann sind es zwei Kostenarten (§ 2 Nr. 4 und Nr. 5 BetrKV) mit
    zwei Vorschriften und zwei Erfassungen, und sie gehoeren auch auf dem
    Blatt getrennt ausgewiesen. Gelingt die Trennung nicht, bleibt es bei
    einer Zeile unter Nr. 6 -- mit Hinweis.

    Eine **reine Warmwasseranlage** faellt hier nebenbei auf ihre Fuesse: sie
    bekommt den Anteil 1 und damit die Zeile nach § 8. Bis NK-050 wurde sie
    wie eine Heizung behandelt.
    """
    wohnungen = anlagen_wohnungen(vorgang, anlage, mehrere)
    ids = {w.id for w in wohnungen}
    if vorgang.wohnung.id not in ids:
        return []

    gesamt_qm = sum(w.qm or 0 for w in wohnungen)
    ww_anteil, trennungsgrund = anlagen_warmwasseranteil(anlage, gesamt_qm)

    zeilen = []
    # § 7 vor § 8 -- die Reihenfolge des Gesetzes und die der Nummern 4 und 5.
    for zweck, teil in ((heizung.HEIZUNG, dec(1) - ww_anteil),
                        (heizung.WARMWASSER, ww_anteil)):
        if teil <= 0:
            continue
        zaehler = {z.wohnung_id: z
                   for z in _anlagenzaehler(vorgang, anlage.id, zweck)
                   if z.wohnung_id in ids}
        zeile = _verteilzeile(
            vorgang, anlage, rechnungen, vermieter_positionen,
            zweck=zweck, ww_anteil=ww_anteil, wohnungen=wohnungen, ids=ids,
            gesamt_qm=gesamt_qm, zaehler=zaehler,
            trennungsgrund=trennungsgrund,
            co2_aufteilung=co2_aufteilung)
        if zeile is not None:
            zeilen.append(zeile)
    return zeilen


def rechnungen_im_umfang(vorgang: Vorgang) -> list:
    """Die Rechnungen, die der Vermieter abrechnen will.

    Ohne Filter sind es alle des Zeitraums. Die Vorpruefung nimmt bewusst die
    ungefilterte Liste: sie soll auch auf einen Zaehler hinweisen, der zu einer
    gerade abgewaehlten Kategorie gehoert.
    """
    if not vorgang.kategorien_filter:
        return list(vorgang.rechnungen)
    erlaubt = set(vorgang.kategorien_filter)
    return [r for r in vorgang.rechnungen if r.kategorie.id in erlaubt]


def _fuer_die_wohnung(vorgang: Vorgang, rechnungen: Sequence[Rechnung]) -> list:
    return [r for r in rechnungen
            if not r.wohnung_id or r.wohnung_id == vorgang.wohnung.id]


def _d(tag: date) -> str:
    return tag.strftime('%d.%m.%Y')


def abdeckungsluecken(vorgang: Vorgang, rechnungen: Sequence[Rechnung]) -> list:
    """Je Kostenart die Tage des Zeitraums, fuer die keine Rechnung da ist (F-115).

    Eine Rechnung, die vor dem Zeitraumende aufhoert, rechnet nur ihre Tage
    ab; die Vorauszahlungen zaehlen trotzdem voll. Das ergab ein Guthaben,
    das nur aus fehlenden Rechnungen entstand, ohne jeden Hinweis. Gemeldet
    werden nur Kostenarten, die im Zeitraum ueberhaupt eine Rechnung haben.
    Luecken sind ``(erster, letzter)`` Tag, beide einschliesslich.
    """
    von, bis = vorgang.beginn, vorgang.ende_grenze
    je_art: dict = {}
    for r in _fuer_die_wohnung(vorgang, rechnungen):
        a, b = max(r.beginn, von), min(r.ende_grenze, bis)
        if a < b:
            je_art.setdefault(r.kategorie.name, []).append((a, b))
    ergebnis = []
    for name in sorted(je_art):
        luecken, stand = [], von
        for a, b in sorted(je_art[name]):
            if a > stand:
                luecken.append((stand, a))
            stand = max(stand, b)
        if stand < bis:
            luecken.append((stand, bis))
        if luecken:
            ergebnis.append({
                'kategorie': name,
                'tage': tage(von, bis) - sum(tage(a, b) for a, b in luecken),
                'von_tagen': tage(von, bis),
                'luecken': [(a, letzter_tag(b)) for a, b in luecken],
            })
    return ergebnis


def _lueckentext(eintrag: dict) -> str:
    return ', '.join(f'{_d(a)}–{_d(b)}' for a, b in eintrag['luecken'])


def abdeckungs_warnung(vorgang: Vorgang, luecken: list) -> Optional[str]:
    """Der Hinweis an den Vermieter samt Vorschlag, den Zeitraum zu teilen."""
    if not luecken:
        return None
    arten = '; '.join(
        f"„{e['kategorie']}“ {e['tage']} von {e['von_tagen']} Tagen "
        f"(fehlt {_lueckentext(e)})" for e in luecken)
    text = (f'Die Rechnungen decken den Zeitraum nicht ganz ab: {arten}. '
            'Die fehlenden Tage werden nicht abgerechnet, die Vorauszahlungen '
            'zählen aber voll.')
    # Bis wohin ist jede Kostenart lueckenlos da? Dahin laesst sich jetzt
    # abrechnen, der Rest spaeter in einem eigenen Zeitraum.
    teilbar_bis = min(e['luecken'][0][0] for e in luecken)
    if teilbar_bis > vorgang.beginn:
        text += (f' Vorschlag: Zeitraum aufteilen – jetzt bis '
                 f'{_d(letzter_tag(teilbar_bis))} abrechnen, den Rest, sobald '
                 'die Rechnungen vorliegen.')
    return text


def abdeckungs_vorbehalt(luecken: list) -> Optional[str]:
    """Der Satz fuer den Mieter im PDF: was noch nicht abgerechnet ist."""
    if not luecken:
        return None
    arten = '; '.join(f"{e['kategorie']} ({_lueckentext(e)})" for e in luecken)
    return ('Vorbehalt: Für folgende Kostenarten lagen bei Erstellung noch '
            f'nicht alle Rechnungen vor: {arten}. Diese Zeiträume sind hier '
            'nicht abgerechnet und werden nachberechnet, sobald die '
            'Rechnungen vorliegen.')


# ponytail: kurze Ueberschneidung = Tippfehler an der Grenze. Laengere
# Ueberschneidungen sind oft echt (zwei Policen einer Versicherung, Brennstoff
# und Wartung einer Anlage) und bleiben still; bei Bedarf je Versorger pruefen.
UEBERSCHNEIDUNG_MAX_TAGE = 7


def ueberschneidende_rechnungen(vorgang: Vorgang, rechnungen: Sequence[Rechnung]) -> list:
    """Rechnungen derselben Kostenart, die sich am Rand ueberlappen (F-117).

    Rechnung 1 bis 01.01., Rechnung 2 ab 01.01.: der 01.01. zaehlt doppelt.
    Gemeldet wird nur, was im Abrechnungszeitraum liegt.
    """
    meldungen = []
    gruppen: dict = {}
    for r in _fuer_die_wohnung(vorgang, rechnungen):
        schluessel = (r.kategorie.id, r.wohnung_id, r.heizungsanlage_id, r.heizkostenart)
        gruppen.setdefault(schluessel, []).append(r)
    for gruppe in gruppen.values():
        gruppe.sort(key=lambda r: (r.beginn, r.ende))
        for i, r1 in enumerate(gruppe):
            for r2 in gruppe[i + 1:]:
                a = max(r2.beginn, vorgang.beginn)
                b = min(r1.ende_grenze, r2.ende_grenze, vorgang.ende_grenze)
                doppelt = tage(a, b)
                if 0 < doppelt <= UEBERSCHNEIDUNG_MAX_TAGE:
                    tage_text = (f'am {_d(a)}' if doppelt == 1
                                 else f'vom {_d(a)} bis {_d(letzter_tag(b))}')
                    meldungen.append(
                        f'Zwei Rechnungen für „{r1.kategorie.name}“ überschneiden '
                        f'sich {tage_text} ({_d(r1.beginn)}–{_d(r1.ende)} und '
                        f'{_d(r2.beginn)}–{_d(r2.ende)}). Diese Tage werden '
                        'doppelt umgelegt. Meist endet die erste Rechnung einen '
                        'Tag früher; prüfen Sie die Daten.')
    return meldungen


HINWEIS_STAND_FAELLT = (
    "W-ZAEHLER-STAND-FAELLT · Zähler {zaehler} fällt vom {d1} ({w1}) auf den "
    "{d2} ({w2}). Ein Zähler zählt nur vorwärts; gerechnet wird damit ein "
    "negativer Verbrauch. Prüfen Sie beide Stände auf Tippfehler und "
    "korrigieren Sie den falschen. Wurde der Zähler getauscht, legen Sie den "
    "neuen Zähler an und tragen Sie seine Stände dort ein."
)


def fallende_staende(vorgang: Vorgang, rechnungen: Sequence[Rechnung]) -> list:
    """Zaehlerstaende, die rueckwaerts laufen (Punkt 3 aus dem Vergleich).

    Ein fallendes Paar rechnet still einen negativen Verbrauch. Korrigiert
    wird nichts -- welcher der beiden Staende falsch ist, weiss nur der
    Vermieter. Gemeldet wird jedes Paar, dessen Intervall den Zeitraum der
    Abrechnung oder einer ihrer Rechnungen beruehrt.
    """
    von = min([vorgang.beginn, *(r.beginn for r in rechnungen)])
    bis = max([vorgang.ende_grenze, *(r.ende_grenze for r in rechnungen)])
    meldungen = []
    for z in vorgang.zaehler:
        staende = sorted(z.staende, key=lambda s: s.datum)
        for s1, s2 in zip(staende, staende[1:]):
            if s2.datum > s1.datum and s2.gesamt < s1.gesamt and s1.datum < bis and s2.datum > von:
                meldungen.append(HINWEIS_STAND_FAELLT.format(
                    zaehler=_zaehlername(z.nummer), d1=_d(s1.datum), w1=zahl_text(s1.gesamt),
                    d2=_d(s2.datum), w2=zahl_text(s2.gesamt)))
    return meldungen


HINWEIS_LEERSTAND_EINZIGE_WOHNUNG = (
    "W-LEERSTAND-OHNE-ABRECHNUNG · „{wohnung}“ ist die einzige Wohnung im Haus "
    "und war an {tage} nicht vermietet, über die Rechnungen dieser "
    "Abrechnung auch laufen ({spannen}). Die Kosten dieser Tage trägt der "
    "Vermieter. Sie stehen in keiner Abrechnung, weil kein anderer Mieter sie "
    "als Vermieteranteil ausweist. Vermerken Sie sie bei Bedarf selbst, etwa für "
    "die Steuer."
)


def _tage_text(n: int) -> str:
    return '1 Tag' if n == 1 else f'{n} Tagen'


def leerstand_der_einzigen_wohnung(vorgang: Vorgang, rechnungen: Sequence[Rechnung]) -> list:
    """Leerstand, den keine Abrechnung zeigt (Punkt 2 aus dem Vergleich).

    Im Haus mit mehreren Wohnungen steht der Leerstand einer Wohnung als
    Vermieteranteil in den Abrechnungen der anderen. Hat das Haus nur eine
    Wohnung, faellt er in keinen Abrechnungszeitraum: er blieb richtig beim
    Vermieter, aber unsichtbar. Gemeldet werden die unvermieteten Tage der
    Rechnungen dieser Abrechnung ausserhalb ihres Zeitraums.
    """
    aktiv = [w for w in vorgang.wohnungen if w.ist_aktiv]
    rechnungen = _fuer_die_wohnung(vorgang, rechnungen)
    if len(aktiv) != 1 or not rechnungen:
        return []
    von = min(r.beginn for r in rechnungen)
    bis = max(r.ende_grenze for r in rechnungen)
    stuecke = []
    for a, b in ((von, vorgang.beginn), (vorgang.ende_grenze, bis)):
        if a < b:
            leer = sum(x.unbelegt for x in _leerstandsbilanz(vorgang, a, b))
            if leer:
                stuecke.append((leer, f'{_d(a)}–{_d(letzter_tag(b))}'))
    if not stuecke:
        return []
    return [HINWEIS_LEERSTAND_EINZIGE_WOHNUNG.format(
        wohnung=aktiv[0].name, tage=_tage_text(sum(t for t, _ in stuecke)),
        spannen=' und '.join(f'{t} von {s}' for t, s in stuecke))]


def rechne(vorgang: Vorgang) -> dict:
    """Die Abrechnung fuer einen Mieter. Rein: gleiche Eingabe, gleiches Bild.

    Das Ergebnis ist das der bisherigen ``BillingEngine.calculate_bill`` --
    dieselben Schluessel, dieselben Betraege, dieselben Texte. Geld ist
    ``Decimal``, jede Zeile ist auf Cent gerundet, und ``total_amount`` ist die
    Summe der **gerundeten** Zeilen (R-NUM-01).
    """
    line_items = []
    warnings = []
    # Was von den qm-Rechnungen beim Vermieter bleibt (R-NUM-05, NK-047).
    vermieter_positionen = []
    # Geld ist Decimal (R-NUM-01). Ein 0.0 hier vergiftet die ganze
    # Summenkette, weil Decimal + float ein TypeError ist -- und das ist
    # gut so: der Fehler faellt sofort auf, statt still zu rechnen.
    total_amount = NULL

    # Zuerst die Nutzungsart, und zwar vor allem anderen: ein Objekt, das
    # dieses Programm nicht abrechnen darf, darf auch keine halbe Zeile
    # bekommen. Die Flaeche erst danach -- sie waere auf einem gemischt
    # genutzten Haus ohnehin der falsche Nenner (R-CO2-04).
    _, nutzungs_befunde = nutzungs_pruefung(vorgang)
    if nutzungs_befunde:
        raise BillingDataError(nutzungs_befunde[0][1])

    profiles = vorgang.profile
    invoices = rechnungen_im_umfang(vorgang)

    # Vor der Heizkostentrennung, damit auch Heizrechnungen mitzaehlen:
    # Luecken im Zeitraum (F-115) und doppelt gezaehlte Tage (F-117).
    luecken = abdeckungsluecken(vorgang, invoices)
    if not _fuer_die_wohnung(vorgang, invoices):
        # H8: ohne Rechnung kostet der Zeitraum 0 und jede Vorauszahlung
        # geht zurueck -- ohne jeden Hinweis sah das wie ein Ergebnis aus.
        folge = (', die Abrechnung erstattet deshalb alle Vorauszahlungen.'
                 if vorgang.zahlungen else '.')
        warnings.append(
            f'Für {_d(vorgang.beginn)}–{_d(vorgang.ende)} ist keine Rechnung erfasst{folge}'
            ' Erfassen Sie zuerst die Rechnungen des Zeitraums.')
    if luecken:
        warnings.append(abdeckungs_warnung(vorgang, luecken))
    warnings.extend(ueberschneidende_rechnungen(vorgang, invoices))
    warnings.extend(fallende_staende(vorgang, invoices))
    warnings.extend(leerstand_der_einzigen_wohnung(vorgang, invoices))

    # Die Heizkosten gehen ihren eigenen Weg (R-HK-01, D-46/D-47): sie
    # laufen nicht durch die Fallunterscheidung darunter, sondern werden je
    # Anlage zusammengelegt und nach § 7 HeizkostenV verteilt.
    invoices, heizrechnungen = heizkosten_abtrennen(vorgang, invoices)

    # Die Einstufung des Gebaeudes nach § 5 CO2KostAufG (NK-053, D-54).
    # Sie ist einmal je Abrechnung, nicht je Anlage: das Haus hat eine
    # Stufe, auch wenn es zwei Anlagen hat. Fehlt an einer Rechnung die
    # CO2-Angabe, steht hier die blockierende Warnung und die Aufteilung
    # bleibt ganz weg (alles oder nichts, R-CO2-02).
    co2_aufteilung = _co2_einstufung(vorgang, heizrechnungen, warnings)

    property_sqm, area_findings = flaechen_pruefung(vorgang)
    area_blocker = next((msg for status, msg in area_findings if status == 'blocker'), None)
    for status, msg in area_findings:
        if status == 'warning':
            warnings.append(msg)

    # F-125: geschaetzter Preisfuss je (Kostenart, Zaehler) -> Rechnungszeitraeume
    preis_geschaetzt: dict[tuple[str, str], list[str]] = {}
    for inv in invoices:
        cat = inv.kategorie
        billing_type = abrechnungsart_von(profiles, cat)

        # Nichts aus der vorigen Rechnung darf in diese hineinlecken. Die
        # Engine hatte diese Liste schon, nur unvollstaendig -- die sieben
        # Namen darunter fehlten, und genau daran starb jede Rechnung, die
        # auf eine Wohnung gebucht war (F-19). Wer kein Leck will, muss alle
        # Namen setzen, nicht die meisten.
        tenant_meter = None
        tenant_consumption = 0
        tenant_direct_cost = NULL
        tenant_allgemein_share_prorated = NULL
        allgemein_consumption = 0
        active_tenants = 0
        unit = ""
        main_detail = None
        tenant_detail = None
        is_abwasser = False
        main_meter = None
        main_consumption = 0
        sum_sub_consumption = 0
        cost_per_unit = NULL
        # Preisfuss: der Hauptzaehlerverbrauch des vollen Rechnungszeitraums
        # (NK-097). Wird nur im Zhaehlerzweig gesetzt, das Zuruecksetzen
        # verhindert, dass eine vorige Rechnung hineinleckt (F-19).
        rechnung_main_consumption = 0
        # NK-105 (D-63): haengt an der Kostenart ein Zaehler? Frisch je
        # Rechnung gesetzt, damit nichts aus der vorigen hineinleckt (F-19).
        hat_zaehler = zaehler_vorhanden(vorgang, cat.id)
        # Die effektiven Tarifpreile (NK-055): NULL heisst Einheitstarif.
        preis_ht_eff = None
        preis_nt_eff = None
        this_tenant_days = 0
        total_person_days = 0
        # F-122: steht hinter "Personentagen", wenn der Allgemeinanteil je
        # Belegungsabschnitt gemessen wurde.
        abschnitte_text = ''

        # Halboffen (R-NUM-03): der erste Tag zaehlt, der letzte nicht.
        # ``ende_grenze`` entscheidet dabei, ob das Ende ein Zeitraumende ist
        # -- dann liegt die Grenze einen Tag weiter -- oder ein Mietende,
        # das schon die Grenze ist. Der Lader stutzt beides in dasselbe Feld.
        invoice_days = tage(inv.beginn, inv.ende_grenze)
        overlap_von = max(inv.beginn, vorgang.beginn)
        overlap_bis = min(inv.ende_grenze, vorgang.ende_grenze)
        overlap_days = tage(overlap_von, overlap_bis)

        if overlap_days <= 0:
            continue

        # Der Zeitanteil ist ein exakter Bruch, kein float: 181/365
        # laesst sich binaer nicht darstellen, und der Fehler wanderte
        # sonst in jeden Betrag, der damit multipliziert wird.
        time_fraction = dec(overlap_days) / dec(invoice_days)
        prorated_invoice_amount = inv.betrag * time_fraction

        tenant_cost = NULL
        description = ""
        is_apartment_direct = False
        # Der Rechenweg der Zeile als Satz (R-DOC-01 Punkt 6/7): leer bei
        # allen Wegen, die ihre Schritte schon anders zeigen -- Direkt- und
        # Zaelerzeilen ueber die Teilposten und Zaehlerdetails, Wohnungs-
        # rechnungen ueber den hundertprozentigen Betrag.
        rechenweg: list = []

        if inv.wohnung_id:
            # F-123: was die Wohnung verbraucht, waehrend niemand dort wohnt,
            # zahlt kein Mieter. Es bleibt beim Vermieter und steht, wie jeder
            # Vermieteranteil, in jeder Abrechnung des Hauses -- auch wenn die
            # Wohnung die ganze Zeit leer stand und es ihre eigene nicht gibt.
            # Gemessen am Zaehler der Wohnung, ohne Zaehler nach Tagen.
            leer_zaehler = wohnungszaehler(vorgang, cat.id, inv.wohnung_id)
            qm = next((w.qm for w in vorgang.wohnungen if w.id == inv.wohnung_id), None)
            # F-137: der Grundpreis faellt auch im Leerstand an, unabhaengig
            # vom Verbrauch. Er folgt den Tagen, nur der Rest dem Zaehler.
            grundpreis = inv.grundpreis if leer_zaehler else None
            if leer_zaehler:
                anteil = _vermieterverbrauchsanteil(
                    vorgang, cat.name, inv, inv.betrag - (grundpreis or NULL),
                    verbrauch(leer_zaehler, inv.beginn, inv.ende),
                    {inv.wohnung_id: leer_zaehler},
                    einheit_fuer(cat.name, cat.betrkv_nr), {inv.wohnung_id},
                    gemessen=True, fenster=(overlap_von, overlap_bis))
                if grundpreis:
                    grundanteil = qm and _vermieteranteil(
                        vorgang, cat.name, inv, grundpreis * time_fraction, qm,
                        overlap_von, overlap_bis, nur={inv.wohnung_id})
                    if grundanteil:
                        grundanteil['description'] = (
                            'Grundpreis/Zählermiete nach Tagen. ' + grundanteil['description'])
                        vermieter_positionen.append(grundanteil)
                elif vorgang.wohnung.id == inv.wohnung_id:
                    leertage = sum(
                        b.unbelegt for b in _leerstandsbilanz(
                            vorgang, inv.beginn, inv.ende_grenze, {inv.wohnung_id})
                        if b.traegt_der_vermieter)
                    if leertage > 0:
                        warnings.append(HINWEIS_GRUNDPREIS_LEERSTAND.format(
                            kategorie=cat.name, wohnung=vorgang.wohnung.name,
                            beginn=inv.beginn.strftime('%d.%m.%Y'),
                            ende=inv.ende.strftime('%d.%m.%Y'), tage=leertage))
            else:
                # F-128: nur der Leerstand im Zeitraum dieser Abrechnung.
                anteil = qm and _vermieteranteil(
                    vorgang, cat.name, inv, prorated_invoice_amount, qm,
                    overlap_von, overlap_bis, nur={inv.wohnung_id})
            if anteil:
                vermieter_positionen.append(anteil)
            if vorgang.wohnung.id != inv.wohnung_id:
                continue  # Not for this apartment
            tenant_cost = prorated_invoice_amount
            billing_type = 'direkt'
            is_apartment_direct = True
            description = "Direkt zugewiesen (100 % der Rechnung für diese Wohnung)"

            # Zaehlerdetails auch bei einer Direktrechnung, der Nachvollziehbarkeit wegen
            if cat.braucht_zaehler or hat_zaehler:
                unit = einheit_fuer(cat.name, cat.betrkv_nr)

                tenant_meter = wohnungszaehler(vorgang, cat.id)
                if tenant_meter:
                    # Nur der Verbrauch im Abrechnungszeitraum (F-114). Ragt
                    # die Rechnung hinaus, teilt der Zaehler den Betrag, nicht
                    # die Tage: Gas im Winter ist nicht Gas im Sommer.
                    tenant_detail = verbrauch_in(tenant_meter, overlap_von, overlap_bis)
                    tenant_consumption = tenant_detail['consumption']
                    gesamt = verbrauch_in(tenant_meter, inv.beginn, inv.ende_grenze)['consumption']
                    if overlap_days < invoice_days and gesamt > 0:
                        anteil = min(max(dec(tenant_consumption) / dec(gesamt), NULL), dec(1))
                        verbrauchsteil = inv.betrag - (grundpreis or NULL)
                        tenant_cost = verbrauchsteil * anteil
                        description = (f"Direkt zugewiesen, nach Verbrauch: "
                                       f"{zahl_text(round(tenant_consumption, 1))} von "
                                       f"{zahl_text(round(gesamt, 1))} {unit} der Rechnung")
                        if grundpreis:
                            # F-137: der Grundpreis nach Tagen, der Rest nach Zaehler.
                            grund_kosten = grundpreis * time_fraction
                            tenant_cost += grund_kosten
                            description += ", Grundpreis/Zählermiete nach Tagen"
                            rechenweg.append(
                                f"{euro_text(grundpreis)} Grundpreis/Zählermiete, anteilig "
                                f"{overlap_days} von {invoice_days} Tagen = "
                                f"{euro_text(runde(grund_kosten))}")
                        rechenweg.append(
                            f"{euro_text(verbrauchsteil)} "
                            f"{'übriger Betrag' if grundpreis else 'Rechnungsbetrag'} × "
                            f"{zahl_text(round(tenant_consumption, 1))} / {zahl_text(round(gesamt, 1))} {unit} "
                            f"= {euro_text(runde(verbrauchsteil * anteil))}")

        elif billing_type == 'qm':
            # Erst hier abbrechen, nicht schon oben: eine Abrechnung ohne
            # einzige qm-Position braucht die Gesamtflaeche gar nicht.
            if area_blocker:
                raise BillingDataError(area_blocker)
            tenant_cost = prorated_invoice_amount * (dec(vorgang.wohnung.qm) / dec(property_sqm))
            description = f"Umlage nach qm ({vorgang.wohnung.qm} von {property_sqm} qm)"
            # Der Rechenweg sagt es mit Zwischenergebnis (R-DOC-01 Punkt 6):
            # erst der Zeitanteil mit Tagen (Punkt 7), dann der Schluessel.
            # Ohne Zeitanteil faellt der erste Schritt weg -- die Rechnung
            # steht schon als Ausgangswert des Schluesselschritts.
            if overlap_days < invoice_days:
                rechenweg.append(
                    f"{euro_text(inv.betrag)} Rechnungsbetrag, anteilig "
                    f"{overlap_days} von {invoice_days} Tagen = "
                    f"{euro_text(prorated_invoice_amount)}")
            rechenweg.append(
                f"{euro_text(prorated_invoice_amount)} nach Wohnfläche "
                f"{zahl_text(vorgang.wohnung.qm)} von "
                f"{zahl_text(property_sqm)} qm = {euro_text(tenant_cost)}")

            # Der Rest dieser Rechnung faellt auf Flaeche, die im Zeitraum
            # niemand gemietet hatte. Er bleibt beim Vermieter -- und steht
            # ab jetzt auch da (R-NUM-05).
            anteil = _vermieteranteil(
                vorgang, cat.name, inv, prorated_invoice_amount,
                property_sqm, overlap_von, overlap_bis)
            if anteil:
                vermieter_positionen.append(anteil)

        elif billing_type == 'personen':
            # R-NUM-04: verteilt wird nach Personentagen, nicht nach der Zahl
            # der Mietverhaeltnisse. Gewichtet wird der **volle** Betrag der
            # Rechnung, nicht der schon auf die Mietzeit gestutzte: die
            # Zeitanteiligkeit steckt bereits in den eigenen Personentagen.
            # Beides zu nehmen hiesse, denselben Mieter zweimal zu kuerzen.
            this_tenant_days = _personentage_des_mieters(
                vorgang.mieter, overlap_von, overlap_bis)
            _, total_person_days, active_tenants = _personentage_im_haus(
                vorgang, inv.beginn, inv.ende_grenze)

            # Wohnungen ohne laufendes Mietverhaeltnis standen bis NK-098
            # gar nicht im Nenner -- ihr Anteil verteilte sich stillschweigend
            # auf die uebrigen Mieter (F-34). Sie zaehlen jetzt wie ein
            # Einpersonenhaushalt (haushalt.VORGABE): dieselbe Vorgabe, die
            # jedes Mietverhaeltnis ohne Haushaltseintrag hat. Der Anteil
            # bleibt beim Vermieter und wird ausgewiesen (R-NUM-05).
            bilanz = _leerstandsbilanz(vorgang, inv.beginn, inv.ende_grenze)
            vermieter_pt = sum(b.unbelegt for b in bilanz if b.traegt_der_vermieter)
            nenner = total_person_days + vermieter_pt

            if nenner > 0 and this_tenant_days > 0:
                tenant_cost = inv.betrag * (dec(this_tenant_days) / dec(nenner))
                description = (
                    f"Umlage nach Personen ({this_tenant_days} von "
                    f"{nenner} Personentagen)"
                )
                # R-NUM-04: die Zeit steckt schon in den Personentagen --
                # der Rechenweg kennt deshalb keinen zweiten, zeitlichen
                # Schritt. Der volle Rechnungsbetrag mal der Personentag-
                # anteil ergibt die Zeile.
                rechenweg.append(
                    f"{euro_text(inv.betrag)} nach Personentagen "
                    f"{this_tenant_days} von {nenner} = "
                    f"{euro_text(tenant_cost)}")
                # F-128: ausgewiesen wird nur der Leerstand im Zeitraum dieser
                # Abrechnung, wie beim qm-Schluessel -- der Nenner bleibt der
                # der ganzen Rechnung, wie bei den Mietern.
                zeitraum = _leerstandsbilanz(vorgang, overlap_von, overlap_bis)
                zeitraum_pt = sum(b.unbelegt for b in zeitraum if b.traegt_der_vermieter)
                if zeitraum_pt > 0:
                    anteil = _vermieterpersonenanteil(
                        vorgang, cat.name, inv, zeitraum, zeitraum_pt, nenner)
                    if anteil:
                        vermieter_positionen.append(anteil)

        elif billing_type in ['direkt', 'nur_allgemein']:
            is_abwasser = ist_abwasser(cat)

            # NK-105 (D-63): der Zaehlerweg gilt fuer jede Kostenart, an der
            # ein Zaehler haengt. ``braucht_zaehler`` entscheidet weiter nur
            # die Pflichtfrage (fehlt ein Zähler, wo einer Pflicht ist ->
            # Fehlerkachel), nicht mehr, ob gemessen werden darf.
            if cat.braucht_zaehler or is_abwasser or hat_zaehler:
                # Abwasser hat keinen eigenen Zaehler: gemessen wird das
                # Frischwasser, abgerechnet beides ueber denselben Stand.
                actual_cat_id = cat.id
                if is_abwasser and vorgang.wasser_kategorie_id:
                    actual_cat_id = vorgang.wasser_kategorie_id

                # Abwasser misst das Frischwasser, also auch in dessen
                # Einheit -- gleich, wie die Kostenart heisst (NK-114).
                unit = 'm³' if is_abwasser else einheit_fuer(
                    cat.name, cat.betrkv_nr)

                # Allgemein-Logik: Hauptzaehler minus Summe der Unterzaehler
                main_meter = hauptzaehler(vorgang, actual_cat_id)
                tenant_meter = wohnungszaehler(vorgang, actual_cat_id)
                all_sub_meters = unterzaehler(vorgang, actual_cat_id)

                main_detail = None
                tenant_detail = None

                if main_meter:
                    # Alles, was hier verteilt wird, wird im Schnitt aus
                    # Rechnungs- und Abrechnungszeitraum gemessen (F-33).
                    # Vorher wurde der Allgemeinverbrauch ueber den **vollen**
                    # Rechnungszeitraum genommen, während der Eigenverbrauch
                    # schon geschnitten war: eine Abrechnung ueber ein Quartal
                    # berechnete denselben Allgemeinverbrauch viermal, und ein
                    # Mieter, der zur Jahresmitte einzog, trug einen
                    # Allgemeinanteil fuer eine Mietzeit, die er noch gar
                    # nicht hatte. Geschnitten wird durch Messen, nicht durch
                    # einen Zeiteinheitsfaktor: der Verbrauch im Fenster wird
                    # zwischen den Ablesungen linear geschätzt -- derselbe
                    # Weg, den der Eigenverbrauch schon immer nahm.
                    main_detail = verbrauch_in(main_meter, overlap_von, overlap_bis)
                    main_consumption = main_detail['consumption']
                    unter_details = [verbrauch_in(m, overlap_von, overlap_bis)
                                     for m in all_sub_meters]
                    sum_sub_consumption = sum(d['consumption'] for d in unter_details)
                    # Beim Dualtarif braucht auch das Fenster die Mengen
                    # getrennt (NK-055): der Allgemeinanteil jedes Registers
                    # wird mit dem Preis seines Registers gerechnet.
                    sum_sub_ht = sum(dec(d['ht']) for d in unter_details)
                    sum_sub_nt = sum(dec(d['nt']) for d in unter_details)

                    allgemein_consumption = max(0, main_consumption - sum_sub_consumption)
                    allgemein_ht = max(Decimal('0'), dec(main_detail['ht']) - sum_sub_ht)
                    allgemein_nt = max(Decimal('0'), dec(main_detail['nt']) - sum_sub_nt)
                    # NK-115: das Klemmen auf 0 wird benannt. Beim Dualtarif
                    # (der Hauptzaehler misst einen Niedertarif) zaehlt auch
                    # ein einzelnes Register -- auch dort bliebe sonst ein
                    # Teil der Kosten still liegen.
                    roh = [('', dec(main_consumption) - dec(sum_sub_consumption))]
                    if dec(main_detail['nt']) > 0:
                        roh += [(' im Hochtarif', dec(main_detail['ht']) - sum_sub_ht),
                                (' im Niedertarif', dec(main_detail['nt']) - sum_sub_nt)]
                    register, roh_menge = min(roh, key=lambda r: r[1])
                    if roh_menge < 0:
                        warnings.append(HINWEIS_ALLGEMEIN_NEGATIV.format(
                            kategorie=cat.name,
                            zaehler=_zaehlername(main_meter.nummer),
                            beginn=overlap_von.strftime('%d.%m.%Y'),
                            ende=(overlap_bis - timedelta(days=1)).strftime('%d.%m.%Y'),
                            register=register,
                            menge=f"{roh_menge:.1f}".replace('.', ','),
                            einheit=unit))

                    # Der Preis je Einheit bleibt der der Rechnung:
                    # Rechnungsbetrag durch den Gesamtverbrauch des
                    # Hauptzaehlers ueber den vollen Rechnungszeitraum. Wuerde
                    # der Preis aus dem geschnittenen Verbrauch entstehen,
                    # truenge jede Teilabrechnung den vollen Betrag je
                    # Einheit -- und vier Quartale ergaeben das Vierfache.
                    # Nur so addieren sich die Abschnitte wieder zum
                    # Rechnungsbetrag; der volle Verbrauch steht deshalb als
                    # eigener Schluessel in den Zaehlerdetails.
                    # Dieselbe Ablesung liefert seit NK-055 auch die
                    # Zeitraumpruefung des Preisfusses (Risiko 8): beruht
                    # der Preis auf hochgerechnetem Verbrauch, weil die
                    # Ablesungen den Rechnungszeitraum nicht decken, steht
                    # das in den Warnungen -- verteilt wird trotzdem, den
                    # Einheitspreis absagen hiesse die Abrechnung absagen.
                    rechnung_main_detail = verbrauch_detail(main_meter, inv.beginn, inv.ende)
                    rechnung_main_consumption = rechnung_main_detail['consumption']
                    if rechnung_main_detail['status'] == 'warning':
                        spannen = preis_geschaetzt.setdefault(
                            (cat.name, _zaehlername(main_meter.nummer)), [])
                        spanne = f"{_d(inv.beginn)}–{_d(inv.ende)}"
                        if spanne not in spannen:
                            spannen.append(spanne)

                    # Beim Dualtarif (NK-055) werden HT und NT getrennt
                    # gerechnet: der Betrag wird nach Wertanteil auf die
                    # Tarife gesplitet, und jeder Verbrauchstraeger zahlt
                    # mit dem Preis seines Registers. Basis ist die Menge
                    # des Rechnungszeitraums -- derselbe Preisfuss wie beim
                    # Mischpreis. Fuellt ``tarifpreise`` (NULL, NULL)
                    # zurueck, gilt der Einheitstarif weiter.
                    preis_ht_eff, preis_nt_eff = tarifpreise(
                        inv.betrag,
                        dec(rechnung_main_detail['ht']),
                        dec(rechnung_main_detail['nt']),
                        inv.preis_ht, inv.preis_nt)

                    if preis_ht_eff is not None:
                        cost_per_unit = NULL
                        allgemein_cost = allgemein_ht * preis_ht_eff + allgemein_nt * preis_nt_eff
                    else:
                        cost_per_unit = (
                            inv.betrag / dec(rechnung_main_consumption)
                            if rechnung_main_consumption > 0 else NULL)
                        allgemein_cost = dec(allgemein_consumption) * cost_per_unit

                    # Personentage verteilen den Allgemeinverbrauch. Bis
                    # NK-046 waren es blosse Tage: zwei Wohnungen gleicher
                    # Mietdauer trugen gleich viel, ob dort eine Person lebte
                    # oder vier (R-NUM-04). Seit NK-097 im **selben Fenster**
                    # wie der gemessene Allgemeinverbrauch -- Zaehler wie
                    # Nenner. Ueber den vollen Rechnungszeitraum gebildet,
                    # wuerde der Nenner Koepfe zaehlen, die den hier
                    # verteilten Verbrauch gar nicht verursacht haben.
                    this_tenant_days, total_person_days, active_tenants = (
                        _personentage_im_haus(vorgang, overlap_von, overlap_bis))
                    # F-121: Wohnungen ohne Mietverhaeltnis zaehlen auch hier
                    # wie ein Einpersonenhaushalt (wie NK-098 beim
                    # Personenschluessel) -- sonst traegen die Mieter ihren
                    # Anteil am Allgemeinverbrauch still mit.
                    zeitraum = _leerstandsbilanz(vorgang, overlap_von, overlap_bis)
                    vermieter_pt = sum(b.unbelegt for b in zeitraum if b.traegt_der_vermieter)
                    total_person_days += vermieter_pt

                    # Der Allgemeinbetrag der ganzen Rechnung (D-73: nie negativ).
                    haupt = verbrauch_in(main_meter, inv.beginn, inv.ende_grenze)
                    unter = [verbrauch_in(m, inv.beginn, inv.ende_grenze)
                             for m in all_sub_meters]
                    if preis_ht_eff is not None:
                        allgemein_voll = (
                            max(NULL, dec(haupt['ht']) - sum(dec(d['ht']) for d in unter))
                            * preis_ht_eff
                            + max(NULL, dec(haupt['nt']) - sum(dec(d['nt']) for d in unter))
                            * preis_nt_eff)
                    else:
                        allgemein_voll = dec(max(0, haupt['consumption'] - sum(
                            d['consumption'] for d in unter))) * cost_per_unit

                    # F-122: wechselt die Belegung in der Rechnung, wird je
                    # Abschnitt gemessen -- sonst die Quote der Personentage.
                    quoten = _allgemeinquoten(
                        vorgang, main_meter, all_sub_meters, inv.beginn, inv.ende_grenze,
                        overlap_von, overlap_bis)
                    if quoten:
                        tenant_allgemein_share_prorated = allgemein_voll * quoten[0]
                        abschnitte_text = ', gemessen je Belegungsabschnitt'
                    elif total_person_days > 0:
                        tenant_allgemein_share_prorated = allgemein_cost * (dec(this_tenant_days) / dec(total_person_days))
                    else:
                        tenant_allgemein_share_prorated = NULL

                    # Ausgewiesen wird der Vermieteranteil im selben Fenster
                    # wie die Mieterzeile (F-128): keine Abrechnung zeigt
                    # Leerstand ausserhalb ihres Zeitraums.
                    if vermieter_pt > 0:
                        anteil = _vermieterpersonenanteil(
                            vorgang, f"{cat.name} (Allgemeinverbrauch)", inv, zeitraum,
                            vermieter_pt, total_person_days,
                            betrag=allgemein_voll if quoten else allgemein_cost,
                            quote=quoten[1] if quoten else None)
                        if anteil:
                            vermieter_positionen.append(anteil)

                    # F-120: was der Unterzaehler einer leeren oder
                    # eigengenutzten Wohnung misst, zahlt kein Mieter. Es
                    # bleibt beim Vermieter -- ausgewiesen wie bei der Heizung.
                    # Gemessen wird wie in der Mieterzeile (verbrauch_in), damit
                    # die Rechnung aufgeht.
                    # ponytail: beim Dualtarif mit dem Mischpreis der Rechnung,
                    # getrennte Register erst, wenn es jemand braucht.
                    if billing_type == 'direkt':
                        anteil = _vermieterverbrauchsanteil(
                            vorgang, f"{cat.name} (Verbrauch der Wohnung)", inv,
                            inv.betrag, rechnung_main_consumption,
                            {m.wohnung_id: m for m in all_sub_meters}, unit, None,
                            gemessen=True, fenster=(overlap_von, overlap_bis))
                        if anteil:
                            vermieter_positionen.append(anteil)

                    if billing_type == 'direkt' and tenant_meter:
                        tenant_detail = verbrauch_in(tenant_meter, overlap_von, overlap_bis)
                        tenant_consumption = tenant_detail['consumption']
                        if preis_ht_eff is not None:
                            tenant_direct_cost = (
                                dec(tenant_detail['ht']) * preis_ht_eff
                                + dec(tenant_detail['nt']) * preis_nt_eff)
                        else:
                            tenant_direct_cost = dec(tenant_consumption) * cost_per_unit

                        tenant_cost = tenant_direct_cost + tenant_allgemein_share_prorated
                        description = f"Eigenverbrauch ({tenant_consumption:.1f} {unit}) + Anteil Allgemein (Haus gesamt: {allgemein_consumption:.1f} {unit}, Anteil: {this_tenant_days} von {total_person_days} Personentagen{abschnitte_text})"
                    else:
                        tenant_cost = tenant_allgemein_share_prorated
                        description = f"Anteil am Allgemeinverbrauch (Haus gesamt: {allgemein_consumption:.1f} {unit}, Anteil: {this_tenant_days} von {total_person_days} Personentagen{abschnitte_text})"
                else:
                    # Kein Hauptzaehler: der Preis je Einheit kommt aus der Summe der Unterzaehler
                    unter_rechnung_details = [verbrauch_detail(m, inv.beginn, inv.ende)
                                              for m in all_sub_meters]
                    sum_sub_consumption = sum(
                        d['consumption'] for d in unter_rechnung_details)
                    preis_ht_eff, preis_nt_eff = tarifpreise(
                        inv.betrag,
                        sum(dec(d['ht']) for d in unter_rechnung_details),
                        sum(dec(d['nt']) for d in unter_rechnung_details),
                        inv.preis_ht, inv.preis_nt)
                    if preis_ht_eff is not None:
                        cost_per_unit = NULL
                    else:
                        cost_per_unit = inv.betrag / dec(sum_sub_consumption) if sum_sub_consumption > 0 else NULL

                    if billing_type == 'direkt' and tenant_meter:
                        tenant_detail = verbrauch_in(tenant_meter, overlap_von, overlap_bis)
                        tenant_consumption = tenant_detail['consumption']
                        if preis_ht_eff is not None:
                            tenant_direct_cost = (
                                dec(tenant_detail['ht']) * preis_ht_eff
                                + dec(tenant_detail['nt']) * preis_nt_eff)
                        else:
                            tenant_direct_cost = dec(tenant_consumption) * cost_per_unit
                        tenant_cost = tenant_direct_cost
                        description = f"Eigenverbrauch ohne Hauptzähler ({tenant_consumption:.1f} {unit} / {sum_sub_consumption:.1f} {unit} Anteil)"
                    else:
                        tenant_cost = NULL
                        description = "Nur Allgemein (Entfällt, da kein Hauptzähler existiert)"
            else:
                tenant_cost = NULL
                description = "Nur Allgemein (Fehler: Kategorie hat keinen Zähler)"

        elif billing_type == 'ignoriert':
            tenant_cost = NULL
            description = "Ignoriert (Zahlt absolut nichts für diese Kategorie)"

        doc_name, doc_path = beleg_angabe(inv.beleg)

        if tenant_cost > 0 or billing_type in ['direkt', 'ignoriert', 'nur_allgemein']:
            sub_items = []

            # Die Unterposten folgen dem Weg, auf dem die Beschreibung entstand
            if is_apartment_direct:
                desc = "Direkt zugewiesen (100 % der Rechnung)"
                if tenant_consumption and tenant_consumption > 0:
                    desc = eigenverbrauch_text(tenant_consumption, unit, tenant_detail)
                sub_items.append({
                    'type': 'eigenverbrauch',
                    'description': desc,
                    'cost': runde(tenant_cost)
                })
            elif billing_type == 'direkt' and tenant_meter:
                if 'Hauptzähler' in description:
                    sub_items.append({
                        'type': 'eigenverbrauch',
                        'description': eigenverbrauch_text(tenant_consumption, unit, tenant_detail),
                        'cost': runde(tenant_direct_cost)
                    })
                else:
                    sub_items.append({
                        'type': 'eigenverbrauch',
                        'description': eigenverbrauch_text(tenant_consumption, unit, tenant_detail),
                        'cost': runde(tenant_direct_cost)
                    })
                    sub_desc = f"Anteil Allgemein (Haus gesamt: {allgemein_consumption:.1f} {unit}, Anteil: {this_tenant_days} von {total_person_days} Personentagen{abschnitte_text})"
                    sub_items.append({
                        'type': 'allgemein',
                        'description': sub_desc,
                        'cost': runde(tenant_allgemein_share_prorated)
                    })
            elif billing_type == 'nur_allgemein' or (billing_type == 'direkt' and not tenant_meter):
                if 'Entfällt' not in description and 'Fehler' not in description:
                    sub_desc = f"Anteil Allgemein (Haus gesamt: {allgemein_consumption:.1f} {unit}, Anteil: {this_tenant_days} von {total_person_days} Personentagen{abschnitte_text})"
                    sub_items.append({
                        'type': 'allgemein',
                        'description': sub_desc,
                        'cost': runde(tenant_cost)
                    })
            elif billing_type == 'personen':
                sub_items.append({
                    'type': 'allgemein',
                    'description': description,
                    'cost': runde(tenant_cost)
                })
            elif billing_type == 'qm':
                sub_items.append({
                    'type': 'allgemein',
                    'description': description,
                    'cost': runde(tenant_cost)
                })

            # Restcent-Regel R1 (R-NUM-02). Der Mieter addiert die
            # Unterposten und muss auf den Zeilenbetrag kommen. Jeder Posten
            # wird fuer sich gerundet, der Zeilenbetrag ebenfalls -- bei
            # Eigenverbrauch plus Allgemeinanteil liegt die Summe der beiden
            # in jedem vierten Fall einen Cent daneben. Der Cent wird nicht
            # verschluckt, er geht auf den letzten Posten.
            sub_items = [
                dict(posten, cost=betrag)
                for posten, betrag in zip(
                    sub_items,
                    restcent_auf_letzte([p['cost'] for p in sub_items], tenant_cost),
                )
            ]

            # Zaehlerdetails fuer die Nachvollziehbarkeit
            meter_details = None
            # Dieselbe Bedingung wie beim Eintritt in den Zaehlerweg oben --
            # sonst wuerden die Details fehlen, wo gerechnet wurde (NK-105).
            if billing_type in ['direkt', 'nur_allgemein'] and (cat.braucht_zaehler or is_abwasser or hat_zaehler):
                meter_details = {
                    'main_meter': main_detail,
                    'tenant_meter': tenant_detail,
                    'main_consumption': round(main_consumption, 1) if main_meter and main_detail else None,
                    'sum_sub_consumption': round(sum_sub_consumption, 1) if main_meter and main_detail else None,
                    'allgemein_consumption': round(allgemein_consumption, 1) if main_meter and main_detail else None,
                    # Der Preisfuss des Einheitspreises: der Gesamtverbrauch
                    # des Hauptzaehlers ueber den vollen Rechnungszeitraum
                    # (NK-097). Ohne ihn liesse sich cost_per_unit aus den
                    # geschnittenen Zahlen nicht nachrechnen.
                    'rechnung_main_consumption': (
                        round(rechnung_main_consumption, 1)
                        if main_meter and main_detail else None),
                    # Beim Einheitstarif der Mischpreis (wie bisher); beim
                    # Dualtarif None -- sein Preis steht bei preis_ht/
                    # preis_nt, ein Mischpreis von 0,0000 wuerde nur
                    # verwirren.
                    'cost_per_unit': (
                        runde_einheitspreis(cost_per_unit)
                        if main_meter and main_detail and preis_ht_eff is None
                        else None),
                    # Der Dualtarif nennt seine Preise (NK-055): die
                    # effektiven Preise je Register, damit der Nachweis
                    # nachrechenbar bleibt -- Menge mal Preis je Register,
                    # summiert ueber beide, ergibt den Zeilenbetrag. Beim
                    # Einheitstarif bleibt alles None.
                    'preis_ht': runde_einheitspreis(preis_ht_eff) if preis_ht_eff is not None and main_meter and main_detail else None,
                    'preis_nt': runde_einheitspreis(preis_nt_eff) if preis_nt_eff is not None and main_meter and main_detail else None,
                    'tenant_consumption': round(tenant_consumption, 1) if tenant_meter else None,
                    'active_tenants': active_tenants,
                    'unit': unit
                }

            line_items.append({
                'category': cat.name,
                'invoice_id': inv.id,
                'invoice_number': inv.nummer,
                'rechnungsdatum': rechnungsdatum_angabe(inv.rechnungsdatum),
                'provider_id': inv.versorger_id,
                'provider_name': inv.versorger_name if inv.versorger_name else 'Unbekannt',
                'period': f"{inv.beginn.strftime('%d.%m.%Y')} - {inv.ende.strftime('%d.%m.%Y')}",
                'total_amount': inv.betrag,
                'prorated_amount': runde(prorated_invoice_amount),
                'billing_type': billing_type,
                'description': description,
                'tenant_cost': runde(tenant_cost),
                'overlap_days': overlap_days,
                'invoice_days': invoice_days,
                'invoice_total_amount': inv.betrag,
                'doc_name': doc_name,
                'doc_path': doc_path,
                'sub_items': sub_items,
                'meter_details': meter_details,
                # R-DOC-01 Punkt 6/7: der Rechenweg der Zeile als Satz --
                # bei qm mit Zeitanteil und Zwischenergebnis, bei Personen
                # mit dem Personentaganteil. Leer bei Direkt- und Zaeler-
                # zeilen: deren Schritte stehen in den Teilposten.
                'rechenweg': rechenweg,
            })
            total_amount += runde(tenant_cost)

    for (kategorie, zaehler), spannen in preis_geschaetzt.items():
        warnings.append(HINWEIS_PREIS_HOCHGERECHNET.format(
            kategorie=kategorie, zaehler=zaehler, zeitraeume=_zeitraeume(spannen),
            rechnungen='Rechnungen' if len(spannen) > 1 else 'Rechnung'))

    # Und jetzt die Heizkosten -- eine Zeile je Anlage, in der Reihenfolge,
    # in der die Anlagen am Vorgang haengen, damit zwei Laeufe dasselbe Blatt
    # ergeben.
    mehrere = len(heizrechnungen) > 1
    for anlage in vorgang.heizungsanlagen:
        gruppe = heizrechnungen.get(anlage.id)
        if not gruppe:
            continue
        # Der Grundkostenanteil geht nach Flaeche, und ohne verlaessliche
        # Flaechen gibt es keinen Nenner -- derselbe Abbruch wie bei qm.
        if area_blocker:
            raise BillingDataError(area_blocker)
        for zeile in _anlagenzeilen(
                vorgang, anlage, gruppe, mehrere, vermieter_positionen,
                co2_aufteilung):
            line_items.append(zeile)
            total_amount += zeile['tenant_cost']
            details = zeile['heizung_details']
            # Die misslungene Trennung gibt es hoechstens einmal je Anlage:
            # ohne Trennung entsteht nur die eine Zeile nach § 7.
            if details['trennungsgrund']:
                warnings.append(heizung.HINWEIS_OHNE_TRENNUNG.format(
                    anlage=anlage.name,
                    grund=details['trennungsgrund'],
                ))
            if details['fehlgrund']:
                warnings.append(heizung.HINWEIS_OHNE_VERBRAUCH.format(
                    anlage=anlage.name,
                    verbrauch=heizung.VERBRAUCHSART[details['zweck']],
                    zaehler=heizung.ZAEHLERART[details['zweck']],
                    grund=details['fehlgrund'],
                ))
                # § 12 Abs. 1 (NK-052, R-HK-05): die Software kürzt nicht
                # selbst -- sie sagt dem Vermieter, dass der Mieter es darf.
                # Nur der Fall ohne jede Verbrauchsbasis löst die Warnung
                # aus; der Ersatzmaßstab des § 9b (NK-051, D-52) verteilt
                # ausdrücklich auf Grundlage der Messung und trägt seinen
                # eigenen Ausweis.
                warnings.append(heizung.HINWEIS_KUERZUNG_15.format(
                    anlage=anlage.name,
                    verbrauch=heizung.VERBRAUCHSART[details['zweck']],
                ))
            # § 9b (NK-051): der Ersatzmassstab ist ausdruecklich gewaehlt --
            # die Warnung nennt die Anlage und die Wechseldaten ohne Ablesung.
            if details['ersatzmassstab']:
                warnings.append(heizung.HINWEIS_ERSATZMASSSTAB.format(
                    anlage=anlage.name,
                    daten=', '.join(details['ersatzmassstab']['daten']),
                ))

    # Dieselbe Regel eine Ebene tiefer: der Mieter addiert die aufgelisteten
    # Vorauszahlungen und muss auf die ausgewiesene Summe kommen, und die
    # Nachzahlung muss die Differenz der beiden Zahlen sein, die auf dem Blatt
    # stehen -- nicht die gerundete Differenz zweier Zahlen, die dort nicht
    # stehen. Beides faellt erst auf, wenn eine Zahlung krumm hereinkommt;
    # aus der Datenbank kommt sie auf Cent, aus einem Import kann sie es
    # nicht (F-21).
    roh = [z.betrag for z in vorgang.zahlungen]
    prepaid_amount = runde(summe(roh))
    prepayments = [
        {'date': z.datum.isoformat(), 'amount': betrag}
        for z, betrag in zip(vorgang.zahlungen, restcent_auf_letzte(roh, summe(roh)))
    ]
    balance = total_amount - prepaid_amount

    # Der Ausweis des § 7 CO2KostAufG (NK-053, R-CO2-02). Die Emission
    # gilt fuer das Gebaeude und den Abrechnungszeitraum; die Eurobetræge
    # sind die dieses Mietverhaeltnisses -- der Mieteranteil steckt in den
    # Unterposten der Heizzeilen, der flache Vermieteranteil in den
    # Vermieterpositionen. Fehlt der Ausweis, fehlt er ganz: dann steht
    # die blockierende Warnung E-CO2-AUSWEIS-FEHLT in den Warnungen.
    co2_ausweis = None
    if co2_aufteilung:
        co2_zeilen = [
            z['heizung_details']['co2'] for z in line_items
            if z.get('billing_type') == 'heizkosten'
            and z.get('heizung_details', {}).get('co2')]
        co2_ausweis = {
            **co2_aufteilung,
            'mieter_anteil_euro': runde(sum(
                (d['anteil'] for d in co2_zeilen), NULL)),
            'vermieter_anteil_euro': runde(sum(
                (d['vermieteranteil'] for d in co2_zeilen), NULL)),
        }

    return {
        'tenant_name': vorgang.mieter.name,
        'apartment': vorgang.wohnung.name,
        'property': vorgang.immobilie_name,
        'start_date': vorgang.beginn.isoformat(),
        'end_date': vorgang.ende.isoformat(),
        'line_items': line_items,
        # total_amount ist bereits die Summe gerundeter Zeilen; runde()
        # bestaetigt hier nur die zwei Stellen, es rechnet nichts um.
        'total_amount': runde(total_amount),
        'prepayments': prepayments,
        'prepaid_amount': prepaid_amount,
        'balance': balance,
        # Der ausgewiesene Vermieteranteil. Er gehoert nicht in
        # total_amount -- der Mieter schuldet ihn nicht, er soll ihn nur
        # sehen koennen (R-NUM-05).
        'landlord_share': {
            'positions': vermieter_positionen,
            'leerstand_amount': summe(p['leerstand_amount'] for p in vermieter_positionen),
            'eigennutzung_amount': summe(p['eigennutzung_amount'] for p in vermieter_positionen),
            'total_amount': summe(p['amount'] for p in vermieter_positionen),
        },
        # Der Ausweis des § 7 CO2KostAufG (NK-053): Emission, Einstufung,
        # Anteile in Prozent und Euro, Herkunft der Zahlen. None heisst:
        # keine Einstufung -- dann erklaert die blockierende Warnung, warum.
        'co2': co2_ausweis,
        # Der Satz fuers PDF, wenn Rechnungen im Zeitraum fehlen (F-115).
        'vorbehalt': abdeckungs_vorbehalt(luecken),
        # D-116: dieselbe Meldung nur einmal, in der Reihenfolge des Auftretens.
        'warnings': meldungen_buendeln(warnings)
    }


# ---------------------------------------------------------------------------
# Die Vorpruefung
# ---------------------------------------------------------------------------


def _zaehler_pruefung(kategorie_name, art, zaehler, wohnung_name, rechnung, detail) -> dict:
    """Eine Kachel der Vorpruefung, wie die Oberflaeche sie erwartet."""
    return {
        'category': kategorie_name,
        'meter_type': art,
        'meter_number': zaehler.nummer,
        'meter_id': zaehler.id,
        'apartment': wohnung_name,
        'invoice_period': f"{rechnung.beginn.strftime('%d.%m.%Y')} - {rechnung.ende.strftime('%d.%m.%Y')}",
        'status': detail['status'],
        'r_start': detail['r_start'],
        'r_end': detail['r_end'],
        'start_offset_days': detail['start_offset_days'],
        'end_offset_days': detail['end_offset_days'],
        'reading_span_days': detail['reading_span_days'],
        'target_days': detail['target_days'],
        'is_interpolated': detail['is_interpolated'],
    }


def _abwasser_kachel(vorgang: Vorgang, kategorie) -> dict:
    """Eine nicht-blockierende Kachel fuer Abwasser ohne Frischwasserzaehler.

    Gebaut wie die Art-Kachel, nur ohne Absage: die Abrechnung selbst ist
    moeglich, sie misst nur nichts -- die Position bleibt bei 0,00 (D-56).
    """
    return {
        'category': kategorie.name,
        'meter_type': 'Frischwasser',
        'meter_number': None,
        'meter_id': None,
        'apartment': vorgang.wohnung.name,
        'invoice_period': None,
        'status': 'no_data',
        'blocking': False,
        'message': (
            f"Für die Kostenart „{kategorie.name}“ gibt es am Objekt keinen "
            "Frischwasserzähler. Die Abwasserkosten werden am "
            "Frischwasserverbrauch gemessen; ohne Zähler bleibt die Position "
            "unbebilligt (0,00). Tragen Sie den Frischwasserzähler des Objekts "
            "mit seiner Kostenart und seinen Ablesungen nach."
        ),
        'r_start': None,
        'r_end': None,
        'start_offset_days': None,
        'end_offset_days': None,
        'reading_span_days': None,
        'target_days': None,
        'is_interpolated': False,
    }


def _art_kachel(vorgang: Vorgang, kategorie, art) -> dict:
    """Eine blockierende Kachel fuer eine Abrechnungsart, die es nicht gibt.

    Gebaut wie die Flaechenkachel aus NK-027: ``no_data`` faerbt sie rot und
    blendet die Zaehlerabweichungen aus, die es hier nicht gibt.
    """
    return {
        'category': kategorie.name,
        'meter_type': 'Abrechnungsart',
        'meter_number': None,
        'meter_id': None,
        'apartment': vorgang.wohnung.name,
        'invoice_period': None,
        'status': 'no_data',
        'blocking': True,
        'message': art_meldung(kategorie.name, art),
        'r_start': None,
        'r_end': None,
        'start_offset_days': None,
        'end_offset_days': None,
        'reading_span_days': None,
        'target_days': None,
        'is_interpolated': False,
    }


def pruefe(vorgang: Vorgang) -> dict:
    """Vorpruefung: wie gut decken die Ablesungen den Abrechnungszeitraum ab?

    Gibt je Zaehler eine Ampel zurueck und darueber ein Gesamturteil. Sie
    laeuft ueber **alle** Rechnungen des Zeitraums, auch ueber die gerade
    abgewaehlten -- ein fehlender Zaehlerstand bleibt ein fehlender
    Zaehlerstand.
    """
    checks = []
    profiles = vorgang.profile
    invoices = list(vorgang.rechnungen)

    checked_meters = set()
    # Je Kostenart eine Kachel, nicht je Rechnung: dieselbe Kostenart
    # kommt im Zeitraum mehrfach vor, das Profil ist trotzdem eines.
    gemeldete_arten = set()

    for inv in invoices:
        cat = inv.kategorie
        # Die Vorpruefung warnt, wo rechne() abbricht -- dieselbe
        # Arbeitsteilung wie bei der Flaeche. Wer hier eine Absage wuerfe,
        # naehme dem Vermieter die Ampel weg und mit ihr den Hinweis,
        # welche Kostenart es ist (F-25).
        art = profiles.get(cat.id, VORGABE)
        if not ist_gueltig(art):
            if cat.id not in gemeldete_arten:
                gemeldete_arten.add(cat.id)
                checks.append(_art_kachel(vorgang, cat, art))
            continue
        billing_type = art
        if billing_type not in ('direkt', 'nur_allgemein'):
            continue
        # NK-105 (D-63): geprueft wird jede Kostenart, an der ein Zaehler
        # haengt. Ohne Zaehler und ohne Pflicht gibt es nichts zu messen;
        # das bisherige stille Ueberspringen bleibt.
        if (not cat.braucht_zaehler
                and not ist_abwasser(cat)
                and not zaehler_vorhanden(vorgang, cat.id)):
            continue
        if inv.wohnung_id and inv.wohnung_id != vorgang.wohnung.id:
            continue

        actual_cat_id = cat.id
        is_abwasser = ist_abwasser(cat)
        if is_abwasser and vorgang.wasser_kategorie_id:
            actual_cat_id = vorgang.wasser_kategorie_id

        # Abwasser ohne Anknuepfung (NK-055, D-56): die Kopplung findet das
        # Frischwasser ueber die Zaehler des Objekts. Findet sie keins, misst
        # die Abrechnung nichts, und die Position bleibt still bei 0,00 --
        # derselbe lautlose Ausfall, den NK-096 aus dem Kostenprofil gejagt
        # hat. Die Kachel sagt es, statt es stillzuhalten; sie blockiert
        # nicht, denn die Abrechnung an sich ist moeglich.
        if (is_abwasser and not vorgang.wasser_kategorie_id
                and cat.id not in gemeldete_arten):
            gemeldete_arten.add(cat.id)
            checks.append(_abwasser_kachel(vorgang, cat))
            continue

        main_meter = hauptzaehler(vorgang, actual_cat_id)
        if main_meter and main_meter.id not in checked_meters:
            checked_meters.add(main_meter.id)
            detail = verbrauch_detail(main_meter, inv.beginn, inv.ende)
            checks.append(_zaehler_pruefung(cat.name, 'Hauptzähler', main_meter, None, inv, detail))

        tenant_meter = wohnungszaehler(vorgang, actual_cat_id)
        if tenant_meter and tenant_meter.id not in checked_meters:
            checked_meters.add(tenant_meter.id)
            detail = verbrauch_detail(tenant_meter, inv.beginn, inv.ende)
            checks.append(_zaehler_pruefung(cat.name, 'Wohnungszähler', tenant_meter, vorgang.wohnung.name, inv, detail))

    # Pruefklasse Nutzungsart (NK-045). Sie haengt an keiner Rechnung und
    # an keinem Zaehler, deshalb steht sie ausserhalb der Schleife: sie
    # gilt fuer das Haus, nicht fuer eine Kostenart. rechne() sagt hier ab
    # -- die Vorpruefung soll es vorher zeigen, damit der Vermieter die
    # Absage nicht erst nach dem Klick auf "Abrechnung erstellen" liest.
    _, nutzungs_befunde = nutzungs_pruefung(vorgang)
    for status, message in nutzungs_befunde:
        checks.append({
            'category': 'Nutzungsart',
            'meter_type': 'Wohngebäude',
            'meter_number': None,
            'meter_id': None,
            'apartment': vorgang.wohnung.name,
            'invoice_period': None,
            'status': 'no_data',
            'blocking': status == 'blocker',
            'message': message,
            'r_start': None,
            'r_end': None,
            'start_offset_days': None,
            'end_offset_days': None,
            'reading_span_days': None,
            'target_days': None,
            'is_interpolated': False,
        })

    # Pruefklasse Flaechendaten (NK-027). Die Zaehlerschleife oben
    # ueberspringt jeden billing_type ausser direkt und nur_allgemein und
    # hat den qm-Fall darum nie gesehen.
    if qm_relevante_rechnungen(invoices, profiles):
        _, area_findings = flaechen_pruefung(vorgang)
        for status, message in area_findings:
            checks.append({
                'category': 'Wohnflaeche',
                'meter_type': 'Umlage nach qm',
                'meter_number': None,
                'meter_id': None,
                'apartment': vorgang.wohnung.name,
                'invoice_period': None,
                # no_data faerbt die Kachel im Frontend rot und blendet die
                # Zaehlerabweichungen aus, die es hier nicht gibt.
                'status': 'no_data',
                'blocking': status == 'blocker',
                'message': message,
                'r_start': None,
                'r_end': None,
                'start_offset_days': None,
                'end_offset_days': None,
                'reading_span_days': None,
                'target_days': None,
                'is_interpolated': False
            })

    # Luecken (F-115) und doppelte Tage (F-117) als Hinweis, nicht als
    # Sperre: eine Abrechnung bis zur Luecke ist ja der Vorschlag.
    hinweise = [('Rechnungen', 'Abdeckung', abdeckungs_warnung(
        vorgang, abdeckungsluecken(vorgang, invoices)))]
    hinweise += [('Rechnungen', 'Überschneidung', m)
                 for m in ueberschneidende_rechnungen(vorgang, invoices)]
    hinweise += [('Zähler', 'Stand', m) for m in fallende_staende(vorgang, invoices)]
    for kategorie, art_text, message in hinweise:
        if message:
            checks.append({
                'category': kategorie, 'meter_type': art_text,
                'meter_number': None, 'meter_id': None,
                'apartment': vorgang.wohnung.name, 'invoice_period': None,
                'status': 'warning', 'blocking': False, 'message': message,
                'r_start': None, 'r_end': None, 'start_offset_days': None,
                'end_offset_days': None, 'reading_span_days': None,
                'target_days': None, 'is_interpolated': False,
            })

    statuses = [c['status'] for c in checks]
    if 'warning' in statuses or 'no_data' in statuses:
        overall = 'warning'
    elif 'acceptable' in statuses:
        overall = 'acceptable'
    elif checks:
        overall = 'excellent'
    else:
        overall = 'no_meters'

    return {'overall': overall, 'checks': checks}
