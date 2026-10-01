"""F-135: Leerstand im Haus mit nur einer Wohnung wird sichtbar.

Im Haus mit mehreren Wohnungen steht der Leerstand einer Wohnung als
Vermieteranteil in den Abrechnungen der anderen. Hat das Haus nur eine
Wohnung, fällt er in keinen Abrechnungszeitraum: Die Kosten blieben richtig
beim Vermieter, aber keine Abrechnung zeigte sie. Jetzt nennt die Abrechnung
die unvermieteten Tage ihrer Rechnungen. Am Betrag ändert sich nichts.

Die Daten sind erfunden.
"""

from datetime import date
from decimal import Decimal

from nebenkostenfix.rechenkern import Kategorie, Mieter, Rechnung, Vorgang, Wohnung, rechne

KENNUNG = 'W-LEERSTAND-OHNE-ABRECHNUNG'
VERSICHERUNG = Kategorie(id=7, name='Versicherung', braucht_zaehler=False)


def _vorgang(wohnungen, mieter, beginn=date(2025, 4, 1)):
    """Mieter ab 01.04.2025, Jahresrechnung 365 EUR -- 1 EUR je Tag."""
    return Vorgang(
        mieter=mieter[0], wohnung=wohnungen[0], immobilie_id=1, immobilie_name='Haus 1',
        beginn=beginn, ende=date(2025, 12, 31), wohnungen=tuple(wohnungen),
        mieter_der_immobilie=tuple(mieter), profile={VERSICHERUNG.id: 'qm'},
        rechnungen=(Rechnung(id=1, kategorie=VERSICHERUNG, betrag=Decimal('365.00'),
                             beginn=date(2025, 1, 1), ende=date(2025, 12, 31)),),
        zaehler=())


def _meldungen(ergebnis):
    return [w for w in ergebnis['warnings'] if KENNUNG in w]


def test_leerstand_der_einzigen_wohnung_wird_gemeldet():
    """01.01. bis 31.03.2025 leer (90 Tage): der Mieter zahlt 275 EUR, der
    Rest von 90 EUR steht jetzt als Hinweis da."""
    wohnung = Wohnung(id=1, name='Wohnung oben', qm=80.0)
    mieter = Mieter(id=1, name='Mieter 1', einzug=date(2025, 4, 1), auszug=None, wohnung_id=1)
    ergebnis = rechne(_vorgang([wohnung], [mieter]))

    assert ergebnis['total_amount'] == Decimal('275.00')
    assert _meldungen(ergebnis) == [
        'W-LEERSTAND-OHNE-ABRECHNUNG · „Wohnung oben“ ist die einzige Wohnung im Haus '
        'und war an 90 Tagen nicht vermietet, über die Rechnungen dieser Abrechnung '
        'auch laufen (90 von 01.01.2025–31.03.2025). Die Kosten dieser Tage trägt der '
        'Vermieter. Sie stehen in keiner Abrechnung, weil kein anderer Mieter sie als '
        'Vermieteranteil ausweist. Vermerken Sie sie bei Bedarf selbst, etwa für die Steuer.']


def test_vorher_vermietet_schweigt():
    """Wohnte vorher jemand dort, steht nichts leer -- kein Hinweis."""
    wohnung = Wohnung(id=1, name='Wohnung oben', qm=80.0)
    neu = Mieter(id=1, name='Mieter 1', einzug=date(2025, 4, 1), auszug=None, wohnung_id=1)
    alt = Mieter(id=2, name='Mieter 2', einzug=date(2020, 1, 1), auszug=date(2025, 4, 1),
                 wohnung_id=1)
    assert _meldungen(rechne(_vorgang([wohnung], [neu, alt]))) == []


def test_mehrere_wohnungen_zeigen_den_leerstand_schon():
    """Mit zwei Wohnungen steht der Leerstand im Vermieteranteil -- kein Hinweis."""
    oben = Wohnung(id=1, name='Wohnung oben', qm=80.0)
    unten = Wohnung(id=2, name='Wohnung unten', qm=80.0)
    mieter = [Mieter(id=1, name='Mieter 1', einzug=date(2025, 4, 1), auszug=None, wohnung_id=1),
              Mieter(id=2, name='Mieter 2', einzug=date(2020, 1, 1), auszug=None, wohnung_id=2)]
    assert _meldungen(rechne(_vorgang([oben, unten], mieter))) == []
