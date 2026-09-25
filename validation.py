"""Eingabepruefung an einer Stelle (NK-028).

Vorher stand dieselbe Arbeit ueber neun Entitaeten verteilt in app.py, jedes
Mal etwas anders. Drei Sorten Schaden kamen daraus:

1. Abstuerze statt Absagen. ``int(request.form.get('meter_id'))`` wirft einen
   TypeError, sobald das Feld fehlt. Der Vermieter sieht dann eine 500 und im
   Log einen Stapelabzug, obwohl seine Eingabe schlicht unvollstaendig war.
   Dasselbe bei ``float(...)`` fuer Betraege und bei
   ``datetime.strptime(None, ...)`` fuer Datumsfelder.
2. Stilles Schlucken. Beim Aendern eines Mieters fing app.py den ValueError
   eines kaputten Datums mit ``pass`` ab: die Antwort war 200 "Tenant
   updated", das Datum aber unveraendert. Falsch gespeichert ohne Hinweis ist
   schlimmer als gar nicht gespeichert.
3. Englische Meldungen. "name, property_id, and sqm are required" hilft
   niemandem, der eine Nebenkostenabrechnung machen will.

Dieses Modul loest alle drei: eine Absage ist eine 400 mit deutschem Text,
der das betroffene Feld benennt, und sie kommt aus derselben Zeile Code,
egal ob die Anfrage JSON, ein Formular oder ein Datei-Upload war.

Aufbau:

* ``Eingabe.aus_request()`` liest die Nutzlast, ohne dass der Aufrufer wissen
  muss, ob sie als JSON oder als ``multipart/form-data`` kam.
* Die Lesemethoden (``text``, ``ganzzahl``, ``kommazahl``, ``geldbetrag``,
  ``datum``, ``wahrheit``, ``datei``) liefern den fertigen Wert oder werfen
  ``EingabeFehler``.
* ``init_validation(app)`` haengt den Fehler an einen errorhandler. Damit
  braucht keine Route ein eigenes try/except: ein ``raise`` irgendwo in der
  Ansichtsfunktion wird zur sauberen 400.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import jsonify, request

from abrechnungsart import AbrechnungsartFehler
from abrechnungsart import pruefe as pruefe_art
from geld import GeldFehler, runde, runde_einheitspreis
from nutzung import NutzungsartFehler
from nutzung import pruefe as pruefe_nutzung

DATUMSFORMAT = '%Y-%m-%d'
DATUM_LESBAR = 'JJJJ-MM-TT'

# Ein fehlender Wert muss von None unterscheidbar sein: ``move_out_date: null``
# heisst "Feld ausraeumen", ein fehlendes move_out_date heisst "nicht
# angefasst". Ohne eigenen Wachposten fallen beide Faelle zusammen.
FEHLT = object()

# Wahrheitswerte kommen aus drei Richtungen: als echtes true/false aus JSON,
# als "true"/"false" aus FormData.append(feld, jsBoolean), und als "on" von
# einem angehakten HTML-Kaestchen ohne JavaScript.
WAHR = frozenset({'true', '1', 'ja', 'yes', 'on', 'y'})
FALSCH = frozenset({'false', '0', 'nein', 'no', 'off', 'n', ''})

# Technischer Feldname zu dem, was der Vermieter im Formular liest. Fehlt ein
# Eintrag, nennt die Meldung nur den technischen Namen: unschoen, aber immer
# noch besser als eine Meldung ohne Feld.
FELDNAMEN = {
    'amount': 'Betrag',
    'apartment_id': 'Wohnung',
    'billing_report_id': 'Abrechnung',
    'category_id': 'Kostenart',
    'category_ids': 'Kostenarten',
    'contract_file': 'Mietvertrag',
    'description': 'Beschreibung',
    'eigennutzung': 'vom Eigentümer genutzt',
    'detailed': 'ausführliche Abrechnung',
    'document_pages': 'Seiten im Beleg',
    'end_date': 'Ende des Zeitraums',
    'gueltig_ab': 'gültig ab',
    'file': 'Datei',
    'has_dual_tariff': 'Doppeltarif',
    'ids': 'Auswahl',
    'invoice_document_id': 'Belegdokument',
    'invoice_number': 'Rechnungsnummer',
    'is_main_meter': 'Hauptzähler',
    'is_official': 'geeichter Zähler',
    'is_official_invoice': 'Abrechnung des Versorgers',
    'is_recurring': 'wiederkehrende Zahlung',
    'is_standalone': 'Einzelobjekt',
    'last_billed_until': 'abgerechnet bis',
    'meter_id': 'Zähler',
    'meter_number': 'Zählernummer',
    'move_in_date': 'Einzugsdatum',
    'move_out_date': 'Auszugsdatum',
    'name': 'Name',
    'nutzungsart': 'Nutzungsart',
    'personenanzahl': 'Personen im Haushalt',
    'payment_date': 'Zahlungsdatum',
    'property_id': 'Immobilie',
    'provider_id': 'Anbieter',
    'reading_date': 'Ablesedatum',
    'selbstversorger': 'Selbstversorger',
    'sqm': 'Wohnfläche',
    'start_date': 'Beginn des Zeitraums',
    'tenant_id': 'Mieter',
    'type': 'Art der Zahlung',
    'value': 'Zählerstand',
    'value_nt': 'Zählerstand Nachttarif',
}


class EingabeFehler(Exception):
    """Die Anfrage ist unbrauchbar, und zwar an einer benennbaren Stelle.

    Traegt den deutschen Text und den technischen Feldnamen getrennt, damit
    die Antwort beides ausliefern kann: den Text fuer den Menschen, das Feld
    fuer die Oberflaeche, die es hervorheben moechte.
    """

    def __init__(self, meldung: str, feld: str | None = None):
        self.meldung = meldung
        self.feld = feld
        super().__init__(meldung)

    def als_json(self) -> dict:
        rumpf = {'error': self.meldung}
        if self.feld:
            rumpf['feld'] = self.feld
        return rumpf


def benenne(feld: str) -> str:
    """Das Feld so, wie es in einer Meldung stehen soll.

    Beide Namen, weil beide gebraucht werden: der Vermieter sucht "Betrag" auf
    seinem Bildschirm, wer den Fehler meldet, kann amount mitschicken.
    """
    lesbar = FELDNAMEN.get(feld)
    return f'"{lesbar}" ({feld})' if lesbar else f'"{feld}"'


def _gekuerzt(wert, grenze: int = 40) -> str:
    """Der Wert fuer die Meldung, aber nicht in voller Laenge.

    Wer 300 Zeichen schickt, soll sie nicht 1:1 zurueckbekommen: die Meldung
    landet in Logs und in einer Sprechblase, beide haben kein Interesse an
    einem Roman.
    """
    text = str(wert)
    return text if len(text) <= grenze else text[:grenze] + '…'


class Eingabe:
    """Die Nutzlast einer Anfrage, gelesen ohne Ruecksicht auf ihre Verpackung.

    ``json`` und ``form`` verhalten sich beim Lesen gleich genug, dass die
    Routen den Unterschied nicht kennen muessen. Die Dateien liegen daneben,
    weil ein Upload immer aus ``request.files`` kommt, auch wenn die uebrigen
    Felder als JSON ankaemen.
    """

    def __init__(self, werte=None, dateien=None):
        self.werte = {} if werte is None else werte
        self.dateien = {} if dateien is None else dateien

    # ------------------------------------------------------------------
    # Herkunft
    # ------------------------------------------------------------------

    @classmethod
    def aus_request(cls, anfrage=None) -> 'Eingabe':
        """Liest JSON oder Formular, je nachdem was gekommen ist.

        Bis NK-028 stand in den Routen ``request.json``. Das wirft in Flask 3
        eine 415, sobald der Aufrufer denselben Inhalt als Formular schickt,
        und die 415 hat keinen deutschen Text. Hier entscheidet der
        Content-Type, und beide Wege fuehren zum selben Ergebnis.
        """
        anfrage = request if anfrage is None else anfrage
        if anfrage.is_json:
            werte = anfrage.get_json(silent=True)
            if werte is None:
                raise EingabeFehler(
                    'Die Anfrage sollte JSON enthalten, war aber keins.')
            if not isinstance(werte, dict):
                raise EingabeFehler(
                    'Die Anfrage muss ein JSON-Objekt sein, keine Liste und '
                    'keinen einzelnen Wert.')
        else:
            werte = anfrage.form
        return cls(werte, anfrage.files)

    @classmethod
    def aus_query(cls, anfrage=None) -> 'Eingabe':
        """Dieselben Lesemethoden fuer die Zeichen hinter dem Fragezeichen.

        Ein GET traegt seine Angaben in der Adresse, nicht im Rumpf. Die
        Pruefung ist dieselbe, und eine Meldung wie "Missing parameters"
        soll es auch dort nicht mehr geben.
        """
        anfrage = request if anfrage is None else anfrage
        return cls(anfrage.args, anfrage.files)

    # ------------------------------------------------------------------
    # Zugriff
    # ------------------------------------------------------------------

    def __contains__(self, feld: str) -> bool:
        return feld in self.werte

    def vorhanden(self, feld: str) -> bool:
        """Ob das Feld ueberhaupt mitgeschickt wurde.

        Fuer Teilaenderungen: nur was dasteht, wird angefasst.
        """
        return feld in self.werte

    def _roh(self, feld: str):
        wert = self.werte.get(feld, FEHLT)
        if isinstance(wert, str):
            wert = wert.strip()
        return wert

    def _pflicht_fehlt(self, feld: str):
        raise EingabeFehler(f'Das Feld {benenne(feld)} fehlt.', feld)

    def _pflicht_leer(self, feld: str):
        raise EingabeFehler(f'Das Feld {benenne(feld)} darf nicht leer sein.', feld)

    def _fehlend_oder_leer(self, feld: str, pflicht: bool, standard):
        """Gibt (fertig, wert) zurueck.

        ``fertig`` heisst: der Aufrufer bekommt den Standardwert und muss
        nicht weiter umwandeln. Sonst steht in ``wert`` etwas Umwandelbares.
        """
        wert = self._roh(feld)
        if wert is FEHLT:
            if pflicht:
                self._pflicht_fehlt(feld)
            return True, standard
        if wert is None or wert == '':
            if pflicht:
                self._pflicht_leer(feld)
            return True, standard
        return False, wert

    # ------------------------------------------------------------------
    # Lesemethoden
    # ------------------------------------------------------------------

    def text(self, feld, pflicht=False, standard=None, maxlaenge=None) -> str | None:
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        wert = str(wert)
        if maxlaenge is not None and len(wert) > maxlaenge:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} ist zu lang: {len(wert)} Zeichen, '
                f'erlaubt sind {maxlaenge}.', feld)
        return wert

    def ganzzahl(self, feld, pflicht=False, standard=None, min_wert=None) -> int | None:
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        if isinstance(wert, bool):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht eine ganze Zahl, hier stand '
                f'ein Ja/Nein-Wert.', feld)
        try:
            zahl = int(wert)
        except (TypeError, ValueError):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht eine ganze Zahl, hier stand '
                f'"{_gekuerzt(wert)}".', feld) from None
        if min_wert is not None and zahl < min_wert:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} darf nicht kleiner als {min_wert} '
                f'sein, hier stand {zahl}.', feld)
        return zahl

    def kommazahl(self, feld, pflicht=False, standard=None, min_wert=None) -> float | None:
        """Zahl mit Nachkommastellen, auch mit Komma geschrieben.

        "1234,50" ist die Schreibweise, die auf jeder deutschen Rechnung
        steht. Sie an float zu reichen ergibt einen ValueError, also eine
        Absage fuer eine Eingabe, die vollkommen in Ordnung ist.
        """
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        if isinstance(wert, bool):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht eine Zahl, hier stand ein '
                f'Ja/Nein-Wert.', feld)
        roh = wert.replace(',', '.') if isinstance(wert, str) else wert
        try:
            zahl = float(roh)
        except (TypeError, ValueError):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht eine Zahl, hier stand '
                f'"{_gekuerzt(wert)}".', feld) from None
        if zahl != zahl or zahl in (float('inf'), float('-inf')):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht eine endliche Zahl, hier '
                f'stand "{_gekuerzt(wert)}".', feld)
        if min_wert is not None and zahl < min_wert:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} darf nicht kleiner als {min_wert} '
                f'sein, hier stand {zahl}.', feld)
        return zahl

    def geldbetrag(self, feld, pflicht=False, standard=None, min_wert=None):
        """Ein Euro-Betrag als ``Decimal``, auf Cent gerundet (R-NUM-01).

        Nicht ``kommazahl``: die liefert float und ist fuer Flaechen und
        Zaehlerstaende auch richtig so. Geld darf den Umweg ueber float nicht
        nehmen -- "1234,57" wird als float zu 1234.5699999999999 und traegt
        diesen Rest durch jede Multiplikation der Abrechnung weiter. Der Weg
        geht deshalb direkt vom Text in ein Decimal, ohne Zwischenstation.

        Was hereinkommt, ist eine Rechnungszeile oder eine Ueberweisung: mehr
        als zwei Nachkommastellen gibt es dort nicht. Ein dritter Stelle wird
        hier einmal und sichtbar auf Cent gerundet, damit sie nicht spaeter im
        Rechenkern auftaucht, wo niemand mit ihr rechnet.
        """
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        if isinstance(wert, bool):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht einen Betrag, hier stand '
                f'ein Ja/Nein-Wert.', feld)
        try:
            betrag = runde(wert)
        except GeldFehler:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht einen Betrag, hier stand '
                f'"{_gekuerzt(wert)}".', feld) from None
        if min_wert is not None and betrag < runde(min_wert):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} darf nicht kleiner als {min_wert} '
                f'sein, hier stand {betrag}.', feld)
        return betrag

    def einheitspreis(self, feld, pflicht=False, standard=None) -> Decimal | None:
        """Ein Preis je Menge als ``Decimal``, auf die vierte Stelle (NK-055).

        Der Weg ist derselbe wie bei ``geldbetrag`` -- direkt vom Text in ein
        Decimal, ohne den Umweg ueber float --, nur auf vier Nachkommastellen:
        ein Versorger stellt einem Dualtarif 0,3582 und 0,2147 EUR je kWh, und
        eine auf zwei Stellen gerundete Eingabe wuerde diese Preise veraendern,
        bevor irgendetwas gerechnet wurde.
        """
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        if isinstance(wert, bool):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht einen Preis, hier stand '
                f'ein Ja/Nein-Wert.', feld)
        try:
            preis = runde_einheitspreis(wert)
        except GeldFehler:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht einen Preis, hier stand '
                f'"{_gekuerzt(wert)}".', feld) from None
        if preis < 0:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} darf nicht negativ sein, hier '
                f'stand {preis}.', feld)
        return preis

    def datum(self, feld, pflicht=False, standard=None):
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        if not isinstance(wert, str):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht ein Datum im Format '
                f'{DATUM_LESBAR}, hier stand "{_gekuerzt(wert)}".', feld)
        try:
            return datetime.strptime(wert, DATUMSFORMAT).date()
        except ValueError:
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht ein Datum im Format '
                f'{DATUM_LESBAR}, hier stand "{_gekuerzt(wert)}".', feld) from None

    def nutzungsart(self, feld='nutzungsart', pflicht=False, standard=None,
                    einheit=None) -> str | None:
        """Eine Nutzungsart aus ``nutzung.GUELTIG``, normiert.

        Die Liste steht nicht hier, sondern in ``nutzung.py`` -- dem einen
        Ort. Diese Methode uebersetzt nur den ``NutzungsartFehler`` in einen
        ``EingabeFehler``, damit die Route wie bei jedem anderen Feld mit
        400 und benanntem Feld antwortet.

        ``einheit`` ist der Name der Wohnung, damit die Meldung sagen kann,
        welche gemeint ist -- bei fuenfzehn Einheiten ist das der
        Unterschied zwischen einer brauchbaren und einer nutzlosen Absage.
        """
        fertig, wert = self._fehlend_oder_leer(feld, pflicht, standard)
        if fertig:
            return wert
        try:
            return pruefe_nutzung(wert, einheit=einheit)
        except NutzungsartFehler as fehler:
            raise EingabeFehler(str(fehler), feld) from None

    def wahrheit(self, feld, standard=False) -> bool:
        wert = self._roh(feld)
        if wert is FEHLT or wert is None:
            return standard
        if isinstance(wert, bool):
            return wert
        if isinstance(wert, (int, float)):
            return bool(wert)
        gesenkt = str(wert).lower()
        if gesenkt in WAHR:
            return True
        if gesenkt in FALSCH:
            return False
        raise EingabeFehler(
            f'Das Feld {benenne(feld)} braucht ja oder nein, hier stand '
            f'"{_gekuerzt(wert)}".', feld)

    def datei(self, feld, pflicht=False):
        """Ein Upload, oder None.

        Ein Browser schickt ein leeres Datei-Feld als Teil mit leerem
        Dateinamen mit. Das ist kein Upload, sondern ein nicht ausgefuelltes
        Feld, und genau diese Unterscheidung stand vorher an sechs Stellen
        einzeln in app.py.
        """
        datei = self.dateien.get(feld)
        if datei is None or not datei.filename:
            if pflicht:
                raise EingabeFehler(
                    f'Das Feld {benenne(feld)} fehlt: es wurde keine Datei '
                    f'ausgewählt.', feld)
            return None
        return datei

    def ganzzahlliste(self, feld, pflicht=False) -> list:
        """Eine Liste von Ids, wie sie das Sammel-Loeschen schickt."""
        wert = self.werte.get(feld, FEHLT)
        if wert is FEHLT or wert is None:
            if pflicht:
                self._pflicht_fehlt(feld)
            return []
        if not isinstance(wert, (list, tuple)):
            raise EingabeFehler(
                f'Das Feld {benenne(feld)} braucht eine Liste.', feld)
        if pflicht and not wert:
            self._pflicht_leer(feld)
        zahlen = []
        for eintrag in wert:
            if isinstance(eintrag, bool):
                raise EingabeFehler(
                    f'Das Feld {benenne(feld)} darf nur ganze Zahlen '
                    f'enthalten, hier stand ein Ja/Nein-Wert.', feld)
            try:
                zahlen.append(int(eintrag))
            except (TypeError, ValueError):
                raise EingabeFehler(
                    f'Das Feld {benenne(feld)} darf nur ganze Zahlen '
                    f'enthalten, hier stand "{_gekuerzt(eintrag)}".',
                    feld) from None
        return zahlen


def zahlenschluessel(rohdaten, feldname: str) -> dict:
    """Eine Zuordnung, deren Schluessel Zahlen sein muessen.

    Die Kostenprofile eines Mieters kommen als {"3": "PAUSCHALE"}, weil JSON
    keine Zahlen als Schluessel kennt. ``int(schluessel)`` ohne Pruefung war
    eine 500, sobald irgendetwas anderes im Objekt stand.
    """
    if rohdaten is None:
        raise EingabeFehler('Die Anfrage sollte JSON enthalten, war aber keins.')
    if not isinstance(rohdaten, dict):
        raise EingabeFehler(
            f'{feldname} muss ein JSON-Objekt sein, dessen Schlüssel '
            f'Kostenart-Nummern sind.')
    ergebnis = {}
    for schluessel, wert in rohdaten.items():
        try:
            nummer = int(schluessel)
        except (TypeError, ValueError):
            raise EingabeFehler(
                f'{feldname}: "{_gekuerzt(schluessel)}" ist keine '
                f'Kostenart-Nummer.') from None
        ergebnis[nummer] = wert
    return ergebnis


def kostenprofile(rohdaten, kostenart_namen=None) -> dict:
    """Die Kostenprofile eines Mieters: Kostenart-Nummer -> Abrechnungsart.

    Bis NK-096 ging der Wert hier ungeprueft durch bis in die Datenbank, und
    der Rechenkern liess die Kostenart spaeter lautlos aus dem Blatt fallen
    (F-25). Geprueft wird **alles**, bevor irgendetwas geschrieben wird: die
    Route loescht die alten Profile, ehe sie die neuen anlegt, und ein
    Abbruch in der Mitte liesse den Mieter ohne Profile zurueck.

    ``kostenart_namen`` ordnet Nummern Namen zu, damit die Meldung sagen
    kann, welche Zeile gemeint ist. Die Zuordnung kommt von aussen -- diese
    Datei fragt die Datenbank nicht.
    """
    roh = zahlenschluessel(rohdaten, 'Kostenprofile')
    namen = kostenart_namen or {}
    geprueft = {}
    for nummer, art in roh.items():
        try:
            geprueft[nummer] = pruefe_art(art, kostenart=namen.get(nummer))
        except AbrechnungsartFehler as fehler:
            raise EingabeFehler(str(fehler), feld=f'kostenart_{nummer}') from None
    return geprueft


def init_validation(app):
    """Haengt EingabeFehler an einen errorhandler.

    Ohne den brauchte jede Route ein eigenes try/except um die Pruefung, und
    genau diese Verdopplung soll NK-028 loswerden. So genuegt ein raise an
    beliebiger Stelle der Ansichtsfunktion.
    """

    @app.errorhandler(EingabeFehler)
    def _eingabe_abgelehnt(fehler):
        return jsonify(fehler.als_json()), 400

    return app
