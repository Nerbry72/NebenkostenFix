"""Die Fassade vor dem Rechenkern (NK-037).

Diese Datei war bis NK-037 der Rechenkern selbst: 821 Zeilen, in denen
Abfragen und Umlage ineinanderlagen. Seit NK-037 steht das Rechnen in
``rechenkern.py`` und das Fragen in ``abrechnungsdaten.py``. Hier bleibt nur
die Naht: eine Klasse mit der Fläche, die app.py und die Tests seit je
ansprechen.

Sie bleibt bestehen, weil sie an acht Stellen in app.py und in drei
Testdateien steht. Eine Umbenennung wäre eine zweite Änderung in derselben
Karte, und eine Karte, die nebenbei Aufrufer umschreibt, ist schwerer zu
prüfen als eine, die es nicht tut. Wer neu schreibt, ruft ``lade_vorgang()``
und ``rechne()`` direkt auf -- diese Klasse ist der Weg für den Bestand.

``BillingDataError`` wird hier nur weitergereicht; geworfen wird sie im Kern.
"""

from abrechnungsdaten import lade_vorgang, lade_zaehler
from rechenkern import (
    TOLERANCE_DAYS,
    BillingDataError,
    flaechen_pruefung,
    leerer_verbrauch,
    pruefe,
    qm_relevante_rechnungen,
    rechne,
    ueberschneidungstage,
    verbrauch_detail,
)

__all__ = ['BillingEngine', 'BillingDataError', 'TOLERANCE_DAYS']


class BillingEngine:
    TOLERANCE_DAYS = TOLERANCE_DAYS

    def __init__(self, tenant_id, start_date, end_date, category_ids=None):
        self.tenant_id = tenant_id
        self.category_ids = category_ids
        self.warnings = []
        # Der Vorgang wird hier geladen und nicht erst beim Rechnen: die
        # gestutzten Stichtage gehoeren zu ihm, und Aufrufer lesen sie direkt
        # nach dem Bauen (start_date, end_date). Ein Zug Abfragen, danach
        # rechnet alles auf derselben Abschrift.
        self.vorgang = lade_vorgang(tenant_id, start_date, end_date, category_ids)
        self.start_date = self.vorgang.beginn
        self.end_date = self.vorgang.ende

    # -- die beiden Einstiege -------------------------------------------------

    def calculate_bill(self):
        """Rechnet und liefert die fertige Abrechnung als dict."""
        ergebnis = rechne(self.vorgang)
        self.warnings = list(ergebnis['warnings'])
        return ergebnis

    def preflight_check(self):
        """Rechnet nicht, sondern prueft die Zaehlerstaende gegen den Zeitraum."""
        return pruefe(self.vorgang)

    # -- was der Bestand sonst noch anspricht ---------------------------------

    def qm_relevant_invoices(self, invoices, profiles):
        return qm_relevante_rechnungen(invoices, profiles)

    def check_area_data(self):
        return flaechen_pruefung(self.vorgang)

    def get_overlap_days(self, d1_start, d1_end, d2_start, d2_end):
        # Zustandslos, und die Charakterisierungstests rufen sie auf einer
        # Instanz aus __new__ auf -- ohne self-Zugriff bleibt das moeglich.
        return ueberschneidungstage(d1_start, d1_end, d2_start, d2_end)

    @staticmethod
    def get_meter_consumption(meter_id, start_date, end_date):
        """Backward-compatible: returns consumption as float."""
        return BillingEngine.get_meter_consumption_detailed(meter_id, start_date, end_date)['consumption']

    @staticmethod
    def get_meter_consumption_detailed(meter_id, start_date, end_date):
        """Verbrauch eines einzelnen Zaehlers samt Herkunft der Staende.

        Der eine Weg, der ohne Abrechnung auskommt: die Oberflaeche fragt
        nach einem Zaehler und einem Zeitraum. Deshalb laedt er selbst statt
        ueber den Vorgang.
        """
        zaehler = lade_zaehler(meter_id)
        if zaehler is None:
            return leerer_verbrauch('', '')
        return verbrauch_detail(zaehler, start_date, end_date)
