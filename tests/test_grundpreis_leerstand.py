"""F-137: der Grundpreis einer Wohnungsrechnung folgt den Tagen, nicht dem Zähler.

Gefunden bei der Praxisprobe (NK-187): eine Gasrechnung, die nur einer
Wohnung gehört, wurde im Zählerzweig (F-114) ganz nach Verbrauch geteilt.
Der Grundpreis bzw. die Zählermiete fällt aber auch in den Leermonaten an,
verbrauchsunabhängig. Nach Verbrauch geteilt landete der Grundpreis der
Leermonate beim Mieter, wenn der Leerstand wenig verbrauchte. Den Leerstand
trägt der Vermieter (§ 556 Abs. 3 BGB).

Seit dem Fix trägt die Rechnung optional „davon Grundpreis/Zählermiete“.
Ist er angegeben, wird er nach Tagen geteilt und nur der Rest nach Zähler.
Fehlt er bei einer Wohnungsrechnung mit Zähler und Leerstand, gibt es einen
Hinweis. Gerechnet wird dann wie bisher.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from nebenkostenfix.rechenkern import (
    Kategorie, Mieter, Rechnung, Stand, Vorgang, Wohnung, Zaehler, rechne)
from billing_factories import apt, house, tenant

BEGINN = date(2025, 1, 1)
EINZUG = date(2025, 4, 1)
ENDE = date(2025, 12, 31)
GRENZE = date(2026, 1, 1)
GAS = Kategorie(id=5, name='Gas', braucht_zaehler=True)
CODE = 'W-GRUNDPREIS-LEERSTAND'


def _vorgang(grundpreis=None, vormieter=False):
    """1200,00 EUR Gas für Wohnung 1; Zähler 300 bis April (leer), 900 danach."""
    wohnung = Wohnung(id=1, name='Wohnung 1', qm=50.0)
    mieter = Mieter(id=1, name='Mieter 1', einzug=EINZUG, auszug=None, wohnung_id=1)
    alle = (mieter,)
    if vormieter:
        alle += (Mieter(id=2, name='Mieter 2', einzug=BEGINN, auszug=EINZUG, wohnung_id=1),)
    zaehler = (Zaehler(id=10, nummer='Z-10', kategorie_id=5, kategorie_name='Gas',
                       ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
                       staende=(Stand(BEGINN, 0.0), Stand(EINZUG, 300.0),
                                Stand(GRENZE, 1200.0))),)
    return Vorgang(
        mieter=mieter, wohnung=wohnung, immobilie_id=1, immobilie_name='Hauptstrasse 1',
        beginn=EINZUG, ende=ENDE, wohnungen=(wohnung,), mieter_der_immobilie=alle,
        profile={GAS.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=GAS, betrag=Decimal('1200.00'),
                             beginn=BEGINN, ende=ENDE, wohnung_id=1,
                             grundpreis=grundpreis),),
        zaehler=zaehler,
    )


def _nachbar(grundpreis=None):
    """Abgerechnet wird Mieter 3 in Wohnung 2; dort steht der Leerstand (F-128)."""
    vorgang = _vorgang(grundpreis)
    zwei = Wohnung(id=2, name='Wohnung 2', qm=70.0)
    nachbar = Mieter(id=3, name='Mieter 3', einzug=BEGINN, auszug=None, wohnung_id=2)
    return replace(vorgang, mieter=nachbar, wohnung=zwei, beginn=BEGINN,
                   wohnungen=(vorgang.wohnung, zwei),
                   mieter_der_immobilie=(nachbar, vorgang.mieter))


def _hinweise(ergebnis):
    return [w for w in ergebnis['warnings'] if CODE in str(w)]


def test_mieter_zahlt_den_grundpreis_nur_fuer_seine_tage():
    """120 × 275/365 + 1080 × 900/1200 = 90,41 + 810,00 = 900,41 EUR.

    Vorher: 1200 × 900/1200 = 900,00. Der Grundpreis der drei Leermonate
    (29,59 EUR) stand zu drei Vierteln beim Mieter.
    """
    ergebnis = rechne(_vorgang(Decimal('120.00')))
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('900.41')
    assert not _hinweise(ergebnis)


def test_vermieter_traegt_den_grundpreis_der_leertage():
    """Verbrauch 1080 × 300/1200 = 270,00 plus Grundpreis 120 × 90/365 = 29,59."""
    anteil = rechne(_nachbar(Decimal('120.00')))['landlord_share']
    assert anteil['total_amount'] == Decimal('299.59')
    assert anteil['leerstand_amount'] == Decimal('299.59')
    assert any('Grundpreis' in p['description'] for p in anteil['positions'])


def test_mieter_und_vermieter_ergeben_die_rechnung():
    mieter = rechne(_vorgang(Decimal('120.00')))['line_items'][0]['tenant_cost']
    vermieter = rechne(_nachbar(Decimal('120.00')))['landlord_share']['total_amount']
    assert mieter + vermieter == Decimal('1200.00')


def test_vormieter_zahlt_seinen_grundpreis():
    """Kein Leerstand: der Vormieter zahlt 120 × 90/365 + 1080 × 300/1200."""
    vorgang = _vorgang(Decimal('120.00'), vormieter=True)
    vormieter = replace(vorgang, mieter=vorgang.mieter_der_immobilie[1],
                        beginn=BEGINN, ende=date(2025, 3, 31))
    ergebnis = rechne(vormieter)
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('299.59')
    assert not ergebnis['landlord_share']['positions']


def test_ohne_grundpreis_wie_bisher_mit_hinweis():
    """Fehlt die Angabe, rechnet die App wie vorher und sagt, was fehlt."""
    ergebnis = rechne(_vorgang())
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('900.00')
    hinweise = _hinweise(ergebnis)
    assert len(hinweise) == 1
    assert 'davon Grundpreis' in str(hinweise[0])


def test_ohne_leerstand_kein_hinweis():
    """Wohnte vorher jemand dort, gibt es keinen Leerstand, der Grundpreis braucht."""
    assert not _hinweise(rechne(_vorgang(vormieter=True)))


def test_ganzes_jahr_bewohnt_bleibt_unveraendert():
    """Deckt der Mieter die ganze Rechnung, zahlt er sie ganz -- mit und ohne Angabe."""
    vorgang = replace(_vorgang(Decimal('120.00')), beginn=BEGINN,
                      mieter=replace(_vorgang().mieter, einzug=BEGINN))
    vorgang = replace(vorgang, mieter_der_immobilie=(vorgang.mieter,))
    ergebnis = rechne(vorgang)
    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('1200.00')
    assert not _hinweise(ergebnis)


# --- Route ---------------------------------------------------------------

def _gas_rechnung(auth_client, **felder):
    prop = house(name='Grundpreishaus')
    wng = apt(prop, 'Grundpreis-EG', 50.0)
    tenant(wng, 'Grundpreismieter', move_in=date(2024, 1, 1))
    from nebenkostenfix.models import CostCategory
    kat = CostCategory.query.filter_by(name='Wasserversorgung').first()
    daten = {
        'category_id': kat.id, 'property_id': prop.id, 'apartment_id': wng.id,
        'amount': '1200.00', 'start_date': '2025-01-01', 'end_date': '2025-12-31',
    }
    daten.update(felder)
    return auth_client.post('/api/invoices', json=daten)


def test_route_speichert_und_liefert_den_grundpreis(auth_client, app_ctx):
    antwort = _gas_rechnung(auth_client, grundpreis='120,00')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    neu = antwort.get_json()['id']
    zeile = next(i for i in auth_client.get('/api/invoices').get_json() if i['id'] == neu)
    assert Decimal(str(zeile['grundpreis'])) == Decimal('120.00')


def test_route_ohne_grundpreis_bleibt_leer(auth_client, app_ctx):
    antwort = _gas_rechnung(auth_client)
    assert antwort.status_code == 201
    neu = antwort.get_json()['id']
    zeile = next(i for i in auth_client.get('/api/invoices').get_json() if i['id'] == neu)
    assert zeile['grundpreis'] is None


def test_route_lehnt_grundpreis_ueber_dem_betrag_ab(auth_client, app_ctx):
    antwort = _gas_rechnung(auth_client, grundpreis='1500.00')
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == 'grundpreis'


def test_route_lehnt_negativen_grundpreis_ab(auth_client, app_ctx):
    antwort = _gas_rechnung(auth_client, grundpreis='-1.00')
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == 'grundpreis'


def test_lader_reicht_den_grundpreis_durch(auth_client, app_ctx):
    from nebenkostenfix.abrechnungsdaten import _rechnung
    from nebenkostenfix.models import CostInvoice
    neu = _gas_rechnung(auth_client, grundpreis='120.00').get_json()['id']
    assert _rechnung(CostInvoice.query.get(neu)).grundpreis == Decimal('120.00')
