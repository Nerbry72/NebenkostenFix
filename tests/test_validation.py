"""Die gemeinsame Eingabepruefung (NK-028).

Zwei Ebenen, weil zwei Dinge schiefgehen koennen:

1. Die Lesemethoden selbst. Hier steht die Wahrheit ueber Pflichtfelder,
   leere Werte, deutsche Kommazahlen und die drei Schreibweisen eines
   Wahrheitswerts.
2. Die Routen. Wichtiger als jede Einheitspruefung ist der Nachweis, dass
   Aufrufe, die vor NK-028 eine 500 mit Stapelabzug ergaben, jetzt eine 400
   mit einem deutschen Satz ergeben, in dem das Feld steht. Diese Faelle sind
   unten einzeln aufgefuehrt, mit dem alten Verhalten im Kommentar.
"""

from decimal import Decimal

import pytest

from validation import (
    Eingabe,
    EingabeFehler,
    FELDNAMEN,
    benenne,
    kostenprofile,
    zahlenschluessel,
)


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------

def _eingabe(werte=None, dateien=None):
    return Eingabe(werte or {}, dateien or {})


def _fehler(aufruf):
    """Fuehrt den Aufruf aus und gibt den EingabeFehler zurueck."""
    with pytest.raises(EingabeFehler) as gefangen:
        aufruf()
    return gefangen.value


@pytest.fixture
def wohnung(app_ctx):
    """Eine Immobilie mit einer Wohnung, fuer die Routen, die beides brauchen."""
    from models import Apartment, Property, db
    haus = Property(name='Haus Müllerstraße 3')
    db.session.add(haus)
    db.session.flush()
    wng = Apartment(property_id=haus.id, name='EG links', sqm=72.5)
    db.session.add(wng)
    db.session.commit()
    return haus, wng


def _json(antwort):
    return antwort.get_json(silent=True) or {}


# --------------------------------------------------------------------------
# Feldnamen
# --------------------------------------------------------------------------

def test_benenne_nennt_beide_namen():
    """Der Vermieter sucht "Betrag", wer den Fehler meldet, schickt amount."""
    assert benenne('amount') == '"Betrag" (amount)'


def test_benenne_kommt_auch_ohne_eintrag_aus():
    assert benenne('irgendwas_neues') == '"irgendwas_neues"'


def test_die_feldnamen_sind_alle_deutsch():
    """Kein englischer Rest in der Tabelle, das ist der Sinn der Uebung."""
    englisch = {'name', 'file', 'type', 'amount', 'date', 'id'}
    treffer = [k for k, v in FELDNAMEN.items() if v.lower() in englisch and k != 'name']
    assert not treffer, treffer


# --------------------------------------------------------------------------
# Herkunft: json, form, files
# --------------------------------------------------------------------------

def test_json_und_form_ergeben_dasselbe(app_ctx):
    """Kriterium 1: derselbe Inhalt, zwei Verpackungen, ein Ergebnis."""
    with app_ctx.app.test_request_context(json={'sqm': '72,5', 'name': 'EG'}):
        aus_json = Eingabe.aus_request()
        assert aus_json.kommazahl('sqm') == 72.5
        assert aus_json.text('name') == 'EG'
    with app_ctx.app.test_request_context(data={'sqm': '72,5', 'name': 'EG'}):
        aus_form = Eingabe.aus_request()
        assert aus_form.kommazahl('sqm') == 72.5
        assert aus_form.text('name') == 'EG'


def test_kaputtes_json_ist_eine_absage_kein_absturz(app_ctx):
    with app_ctx.app.test_request_context(
            data='{nicht wirklich json', content_type='application/json'):
        fehler = _fehler(Eingabe.aus_request)
    assert 'JSON' in fehler.meldung


def test_json_liste_statt_objekt_wird_abgelehnt(app_ctx):
    with app_ctx.app.test_request_context(json=[1, 2, 3]):
        fehler = _fehler(Eingabe.aus_request)
    assert 'JSON-Objekt' in fehler.meldung


def test_dateien_kommen_aus_request_files(app_ctx):
    """Kriterium 1: files gehoert dazu, auch wenn der Rest ein Formular ist."""
    import io
    daten = {'name': 'Vertrag', 'contract_file': (io.BytesIO(b'%PDF-1.4'), 'v.pdf')}
    with app_ctx.app.test_request_context(
            data=daten, content_type='multipart/form-data'):
        eingabe = Eingabe.aus_request()
        assert eingabe.text('name') == 'Vertrag'
        assert eingabe.datei('contract_file').filename == 'v.pdf'


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------

def test_vorhanden_unterscheidet_fehlt_von_leer():
    """Teilaenderungen haengen daran: nur was dasteht, wird angefasst."""
    eingabe = _eingabe({'move_out_date': ''})
    assert eingabe.vorhanden('move_out_date') is True
    assert eingabe.vorhanden('move_in_date') is False
    assert 'move_out_date' in eingabe
    assert 'move_in_date' not in eingabe


def test_text_pflicht_fehlt():
    fehler = _fehler(lambda: _eingabe().text('name', pflicht=True))
    assert fehler.feld == 'name'
    assert fehler.meldung == 'Das Feld "Name" (name) fehlt.'


def test_text_pflicht_leer():
    fehler = _fehler(lambda: _eingabe({'name': '   '}).text('name', pflicht=True))
    assert 'darf nicht leer sein' in fehler.meldung


def test_text_wird_getrimmt():
    assert _eingabe({'name': '  Haus  '}).text('name') == 'Haus'


def test_text_ohne_pflicht_gibt_den_standard():
    assert _eingabe().text('description', standard='') == ''


def test_text_zu_lang():
    fehler = _fehler(
        lambda: _eingabe({'name': 'a' * 300}).text('name', maxlaenge=200))
    assert 'zu lang' in fehler.meldung
    assert '300' in fehler.meldung


# --------------------------------------------------------------------------
# ganzzahl
# --------------------------------------------------------------------------

def test_ganzzahl_aus_zeichenkette():
    assert _eingabe({'meter_id': '7'}).ganzzahl('meter_id') == 7


def test_ganzzahl_leer_ist_nicht_null():
    """Ein leeres Auswahlfeld heisst "nichts gewaehlt", nicht "die Null"."""
    assert _eingabe({'provider_id': ''}).ganzzahl('provider_id') is None


def test_ganzzahl_kaputt():
    fehler = _fehler(lambda: _eingabe({'meter_id': 'abc'}).ganzzahl('meter_id'))
    assert fehler.feld == 'meter_id'
    assert fehler.meldung == (
        'Das Feld "Zähler" (meter_id) braucht eine ganze Zahl, hier stand "abc".')


def test_ganzzahl_lehnt_wahrheitswert_ab():
    """True ist in Python eine 1. Als Fremdschluessel ist es ein Tippfehler."""
    fehler = _fehler(lambda: _eingabe({'meter_id': True}).ganzzahl('meter_id'))
    assert 'Ja/Nein' in fehler.meldung


def test_ganzzahl_untergrenze():
    fehler = _fehler(
        lambda: _eingabe({'sqm': '-3'}).ganzzahl('sqm', min_wert=0))
    assert 'kleiner als 0' in fehler.meldung


def test_lange_eingaben_kommen_gekuerzt_zurueck():
    """Die Meldung landet in einer Sprechblase und im Log, nicht in einem Buch."""
    fehler = _fehler(lambda: _eingabe({'meter_id': 'x' * 300}).ganzzahl('meter_id'))
    assert len(fehler.meldung) < 150
    assert '…' in fehler.meldung


# --------------------------------------------------------------------------
# kommazahl
# --------------------------------------------------------------------------

def test_kommazahl_mit_punkt():
    assert _eingabe({'amount': '1234.50'}).kommazahl('amount') == 1234.50


def test_kommazahl_mit_komma():
    """So steht der Betrag auf jeder deutschen Rechnung."""
    assert _eingabe({'amount': '1234,50'}).kommazahl('amount') == 1234.50


def test_kommazahl_kaputt():
    fehler = _fehler(lambda: _eingabe({'amount': 'viel'}).kommazahl('amount'))
    assert fehler.meldung == (
        'Das Feld "Betrag" (amount) braucht eine Zahl, hier stand "viel".')


def test_kommazahl_lehnt_unendlich_ab():
    """float("inf") laeuft durch und macht die Abrechnung stumm kaputt."""
    for wert in ('inf', '-inf', 'nan', 'Infinity'):
        fehler = _fehler(lambda w=wert: _eingabe({'amount': w}).kommazahl('amount'))
        assert 'endliche Zahl' in fehler.meldung or 'braucht eine Zahl' in fehler.meldung


def test_kommazahl_lehnt_wahrheitswert_ab():
    fehler = _fehler(lambda: _eingabe({'amount': True}).kommazahl('amount'))
    assert 'Ja/Nein' in fehler.meldung


def test_kommazahl_untergrenze():
    fehler = _fehler(
        lambda: _eingabe({'amount': '-5'}).kommazahl('amount', min_wert=0))
    assert 'kleiner als 0' in fehler.meldung


def test_kommazahl_pflicht_fehlt():
    fehler = _fehler(lambda: _eingabe().kommazahl('value', pflicht=True))
    assert fehler.meldung == 'Das Feld "Zählerstand" (value) fehlt.'


def test_kommazahl_ohne_pflicht_fehlt_still():
    """Der Nachttarif ist bei den meisten Zaehlern schlicht nicht belegt."""
    assert _eingabe().kommazahl('value_nt') is None


# --------------------------------------------------------------------------
# geldbetrag (NK-036)
# --------------------------------------------------------------------------

def test_geldbetrag_ist_ein_decimal_und_kein_float():
    """Der Unterschied, um den es bei R-NUM-01 geht.

    Derselbe Text durch ``kommazahl`` ergibt 1234.5699999999999 -- nah dran
    und trotzdem der falsche Betrag, sobald er mit einer Verteilquote
    multipliziert wird.
    """
    betrag = _eingabe({'amount': '1234,57'}).geldbetrag('amount')
    assert betrag == Decimal('1234.57')
    assert isinstance(betrag, Decimal)
    assert Decimal(_eingabe({'amount': '1234,57'}).kommazahl('amount')) != Decimal('1234.57')


def test_geldbetrag_deutsche_schreibweise_mit_tausenderpunkt():
    """So steht es auf der Heizkostenabrechnung des Versorgers."""
    assert _eingabe({'amount': '1.234,50'}).geldbetrag('amount') == Decimal('1234.50')


def test_geldbetrag_mit_punkt():
    assert _eingabe({'amount': '1234.50'}).geldbetrag('amount') == Decimal('1234.50')


def test_geldbetrag_rundet_die_dritte_stelle_kaufmaennisch():
    """Einmal und sichtbar hier, damit sie nicht im Rechenkern auftaucht."""
    assert _eingabe({'amount': '2,675'}).geldbetrag('amount') == Decimal('2.68')
    assert _eingabe({'amount': '2,674'}).geldbetrag('amount') == Decimal('2.67')


def test_geldbetrag_aus_json_nimmt_auch_zahlen():
    """Ein JSON-Aufruf schickt 89.29, kein "89,29"."""
    assert _eingabe({'amount': 89.29}).geldbetrag('amount') == Decimal('89.29')
    assert _eingabe({'amount': 90}).geldbetrag('amount') == Decimal('90.00')


def test_geldbetrag_kaputt():
    fehler = _fehler(lambda: _eingabe({'amount': 'viel'}).geldbetrag('amount'))
    assert fehler.meldung == (
        'Das Feld "Betrag" (amount) braucht einen Betrag, hier stand "viel".')


def test_geldbetrag_lehnt_unendlich_ab():
    for wert in ('inf', '-inf', 'nan', float('inf'), float('nan')):
        fehler = _fehler(lambda w=wert: _eingabe({'amount': w}).geldbetrag('amount'))
        assert 'braucht einen Betrag' in fehler.meldung


def test_geldbetrag_lehnt_wahrheitswert_ab():
    """True ist in Python ein int und waere sonst stillschweigend 1,00 EUR."""
    fehler = _fehler(lambda: _eingabe({'amount': True}).geldbetrag('amount'))
    assert 'Ja/Nein' in fehler.meldung


def test_geldbetrag_untergrenze():
    fehler = _fehler(
        lambda: _eingabe({'amount': '-5'}).geldbetrag('amount', min_wert=0))
    assert 'kleiner als 0' in fehler.meldung
    assert _eingabe({'amount': '0'}).geldbetrag('amount', min_wert=0) == Decimal('0.00')


def test_geldbetrag_pflicht_fehlt():
    fehler = _fehler(lambda: _eingabe().geldbetrag('amount', pflicht=True))
    assert fehler.meldung == 'Das Feld "Betrag" (amount) fehlt.'


def test_geldbetrag_ohne_pflicht_fehlt_still():
    assert _eingabe().geldbetrag('amount') is None


def test_geldbetrag_standard_kommt_unveraendert_zurueck():
    """Der Standard geht nicht durch die Umwandlung -- er ist schon Decimal."""
    assert _eingabe({'amount': ''}).geldbetrag(
        'amount', standard=Decimal('0.00')) == Decimal('0.00')


# --------------------------------------------------------------------------
# datum
# --------------------------------------------------------------------------

def test_datum_gut():
    from datetime import date
    assert _eingabe({'move_in_date': '2025-03-14'}).datum('move_in_date') == date(2025, 3, 14)


def test_datum_deutsche_schreibweise_wird_abgelehnt():
    """14.03.2025 ist nicht falsch, aber das Formular liefert JJJJ-MM-TT."""
    fehler = _fehler(
        lambda: _eingabe({'move_in_date': '14.03.2025'}).datum('move_in_date'))
    assert fehler.meldung == (
        'Das Feld "Einzugsdatum" (move_in_date) braucht ein Datum im Format '
        'JJJJ-MM-TT, hier stand "14.03.2025".')


def test_datum_31_februar():
    fehler = _fehler(
        lambda: _eingabe({'move_in_date': '2025-02-31'}).datum('move_in_date'))
    assert 'JJJJ-MM-TT' in fehler.meldung


def test_datum_aus_json_muss_eine_zeichenkette_sein():
    """JSON kann {"move_in_date": 20250314} schicken. Das ist kein Datum."""
    fehler = _fehler(lambda: _eingabe({'move_in_date': 20250314}).datum('move_in_date'))
    assert 'JJJJ-MM-TT' in fehler.meldung


def test_datum_leer_raeumt_aus():
    """Ein leeres Auszugsdatum heisst: der Mieter wohnt noch da."""
    assert _eingabe({'move_out_date': ''}).datum('move_out_date') is None


# --------------------------------------------------------------------------
# wahrheit
# --------------------------------------------------------------------------

@pytest.mark.parametrize('wert', [True, 'true', 'True', '1', 'ja', 'on', 1])
def test_wahrheit_ja(wert):
    assert _eingabe({'is_official': wert}).wahrheit('is_official') is True


@pytest.mark.parametrize('wert', [False, 'false', 'False', '0', 'nein', 'off', '', 0])
def test_wahrheit_nein(wert):
    assert _eingabe({'is_official': wert}).wahrheit('is_official') is False


def test_wahrheit_fehlt_gibt_den_standard():
    assert _eingabe().wahrheit('is_official') is False
    assert _eingabe().wahrheit('is_official', standard=True) is True


def test_wahrheit_unsinn():
    fehler = _fehler(lambda: _eingabe({'is_official': 'vielleicht'}).wahrheit('is_official'))
    assert 'ja oder nein' in fehler.meldung


# --------------------------------------------------------------------------
# datei
# --------------------------------------------------------------------------

class _Attrappe:
    def __init__(self, filename):
        self.filename = filename


def test_datei_leeres_feld_ist_kein_upload():
    """Der Browser schickt das leere Feld mit. Das ist kein Dokument."""
    assert _eingabe(dateien={'file': _Attrappe('')}).datei('file') is None


def test_datei_pflicht():
    fehler = _fehler(lambda: _eingabe(dateien={'file': _Attrappe('')}).datei('file', pflicht=True))
    assert fehler.feld == 'file'
    assert 'keine Datei ausgewählt' in fehler.meldung


def test_datei_vorhanden():
    datei = _Attrappe('Rechnung.pdf')
    assert _eingabe(dateien={'file': datei}).datei('file') is datei


# --------------------------------------------------------------------------
# Listen und Zahlenschluessel
# --------------------------------------------------------------------------

def test_ganzzahlliste_gut():
    assert _eingabe({'ids': [1, '2', 3]}).ganzzahlliste('ids') == [1, 2, 3]


def test_ganzzahlliste_fehlt_ganz():
    assert _eingabe().ganzzahlliste('ids') == []
    fehler = _fehler(lambda: _eingabe().ganzzahlliste('ids', pflicht=True))
    assert fehler.meldung == 'Das Feld "Auswahl" (ids) fehlt.'


def test_ganzzahlliste_mit_wahrheitswert_drin():
    fehler = _fehler(lambda: _eingabe({'ids': [True]}).ganzzahlliste('ids'))
    assert 'Ja/Nein' in fehler.meldung


def test_ganzzahlliste_keine_liste():
    fehler = _fehler(lambda: _eingabe({'ids': 'alle'}).ganzzahlliste('ids'))
    assert 'braucht eine Liste' in fehler.meldung


def test_ganzzahlliste_mit_unsinn_drin():
    fehler = _fehler(lambda: _eingabe({'ids': [1, 'zwei']}).ganzzahlliste('ids'))
    assert 'nur ganze Zahlen' in fehler.meldung


def test_ganzzahlliste_pflicht_und_leer():
    fehler = _fehler(lambda: _eingabe({'ids': []}).ganzzahlliste('ids', pflicht=True))
    assert 'darf nicht leer sein' in fehler.meldung


def test_zahlenschluessel_gut():
    assert zahlenschluessel({'3': 'PAUSCHALE'}, 'Kostenprofile') == {3: 'PAUSCHALE'}


def test_zahlenschluessel_ohne_json():
    """Ein POST ohne Rumpf soll keine 500 werden."""
    fehler = _fehler(lambda: zahlenschluessel(None, 'Kostenprofile'))
    assert 'JSON' in fehler.meldung


def test_zahlenschluessel_kein_objekt():
    fehler = _fehler(lambda: zahlenschluessel([1, 2], 'Kostenprofile'))
    assert 'JSON-Objekt' in fehler.meldung


def test_zahlenschluessel_kaputter_schluessel():
    fehler = _fehler(lambda: zahlenschluessel({'strom': 'x'}, 'Kostenprofile'))
    assert 'keine Kostenart-Nummer' in fehler.meldung


# --------------------------------------------------------------------------
# Der errorhandler
# --------------------------------------------------------------------------

def test_der_errorhandler_macht_aus_dem_fehler_eine_400(auth_client):
    """Kriterium 3 im Ganzen: 400, deutscher Satz, Feld im Rumpf."""
    antwort = auth_client.post('/api/properties', json={})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['error'] == 'Das Feld "Name" (name) fehlt.'
    assert rumpf['feld'] == 'name'


# --------------------------------------------------------------------------
# Routen: was vor NK-028 eine 500 war
# --------------------------------------------------------------------------

def test_zaehlerstand_ohne_zaehler(auth_client):
    """Vorher: int(None) -> TypeError -> 500."""
    antwort = auth_client.post('/api/readings', data={'value': '100'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'meter_id'
    assert 'Zähler' in _json(antwort)['error']


def test_zaehlerstand_mit_text_als_wert(auth_client):
    """Vorher: float("abc") -> ValueError -> 500."""
    antwort = auth_client.post(
        '/api/readings', data={'meter_id': '1', 'reading_date': '2025-01-01', 'value': 'abc'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'value'


def _zaehler_anlegen(auth_client, haus):
    from models import CostCategory
    kategorie = CostCategory.query.filter_by(name='Strom').first() or \
        CostCategory.query.first()
    antwort = auth_client.post('/api/meters', json={
        'category_id': kategorie.id, 'property_id': haus.id,
        'meter_number': 'W-1'})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return _json(antwort)['id']


def test_zaehlerstand_mit_unbekannter_ablesungsart(auth_client, wohnung):
    """Die Art der Ablesung wird geprueft (NK-051): eine dritte gibt es nicht."""
    haus, _ = wohnung
    zaehler = _zaehler_anlegen(auth_client, haus)
    antwort = auth_client.post(
        '/api/readings',
        data={'meter_id': str(zaehler), 'reading_date': '2025-01-01',
              'value': '100', 'ablesungsart': 'gefuehlt'})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['feld'] == 'ablesungsart'
    assert 'zwischenablesung' in rumpf['error']


def test_zaehlerstand_mit_zwischenablesung(auth_client, wohnung):
    """Die Art kommt in die Datenbank und wieder heraus (NK-051).

    Ohne Angabe gilt die gewoehnliche Ablesung -- der Altbestand kennt kein
    Feld, und kein Stand wird dadurch zur Zwischenablesung.
    """
    haus, _ = wohnung
    zaehler = _zaehler_anlegen(auth_client, haus)
    auth_client.post(
        '/api/readings',
        data={'meter_id': str(zaehler), 'reading_date': '2025-06-30',
              'value': '500', 'ablesungsart': 'zwischenablesung'})
    auth_client.post(
        '/api/readings',
        data={'meter_id': str(zaehler), 'reading_date': '2025-07-01',
              'value': '505'})
    from models import MeterReading
    arten = {r.reading_date.isoformat(): r.ablesungsart
             for r in MeterReading.query.order_by(MeterReading.reading_date)}
    assert arten == {'2025-06-30': 'zwischenablesung',
                     '2025-07-01': 'ablesung'}


def test_ablesungsart_wird_berichtigt(auth_client, wohnung):
    """Wer vergessen hat, die Zwischenablesung als solche zu markieren,
    korrigiert den Stand, statt ihn neu anzulegen (NK-051)."""
    haus, _ = wohnung
    zaehler = _zaehler_anlegen(auth_client, haus)
    auth_client.post(
        '/api/readings',
        data={'meter_id': str(zaehler), 'reading_date': '2025-06-30',
              'value': '500'})
    from models import MeterReading
    stand = MeterReading.query.order_by(MeterReading.id).first()
    assert stand.ablesungsart == 'ablesung'
    antwort = auth_client.put(
        f'/api/readings/{stand.id}', data={'ablesungsart': 'zwischenablesung'})
    assert antwort.status_code == 200
    assert stand.ablesungsart == 'zwischenablesung'
    antwort = auth_client.put(
        f'/api/readings/{stand.id}', data={'ablesungsart': 'geraten'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'ablesungsart'


def test_zaehlerstand_mit_krummem_datum(auth_client):
    """Vorher: strptime -> ValueError -> 500."""
    antwort = auth_client.post(
        '/api/readings', data={'meter_id': '1', 'reading_date': 'morgen', 'value': '100'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'reading_date'
    assert 'JJJJ-MM-TT' in _json(antwort)['error']


def test_rechnung_ohne_betrag(auth_client):
    """Vorher: float(None) -> TypeError -> 500."""
    antwort = auth_client.post('/api/invoices', data={'category_id': '1', 'property_id': '1'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'amount'


def test_rechnung_mit_deutschem_betrag(auth_client, wohnung):
    """1234,50 ist eine gueltige Eingabe und muss ankommen."""
    haus, _ = wohnung
    from models import CostCategory
    kategorie = CostCategory.query.filter_by(name='Grundsteuer').first()
    antwort = auth_client.post('/api/invoices', data={
        'category_id': str(kategorie.id),
        'property_id': str(haus.id),
        'amount': '1234,50',
        'start_date': '2025-01-01',
        'end_date': '2025-12-31',
    })
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    from models import CostInvoice
    assert CostInvoice.query.get(_json(antwort)['id']).amount == 1234.50


def test_beleg_ohne_datei(auth_client, wohnung):
    """Vorher englisch: "No file uploaded"."""
    haus, _ = wohnung
    antwort = auth_client.post('/api/invoice_documents', data={'property_id': str(haus.id)})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['feld'] == 'file'
    assert 'Datei' in rumpf['error']


def test_beleg_ohne_immobilie(auth_client):
    """Vorher: int(None) -> TypeError -> 500."""
    antwort = auth_client.post('/api/invoice_documents', data={'description': 'x'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'property_id'


def test_zaehler_ohne_nummer(auth_client, wohnung):
    """Vorher: data['meter_number'] -> KeyError -> 500."""
    haus, _ = wohnung
    antwort = auth_client.post('/api/meters', json={'category_id': 1, 'property_id': haus.id})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'meter_number'


def test_wohnung_ohne_flaeche(auth_client, wohnung):
    """Vorher englisch: "name, property_id, and sqm are required"."""
    haus, _ = wohnung
    antwort = auth_client.post('/api/apartments', json={'name': 'DG', 'property_id': haus.id})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['feld'] == 'sqm'
    assert rumpf['error'] == 'Das Feld "Wohnfläche" (sqm) fehlt.'


def test_mieter_mit_krummem_einzugsdatum(auth_client, wohnung):
    """Vorher englisch: "Invalid date format. Use YYYY-MM-DD"."""
    _, wng = wohnung
    antwort = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '14.03.2025'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'move_in_date'


def test_mieteraenderung_schluckt_ein_kaputtes_datum_nicht_mehr(auth_client, wohnung):
    """Der schlimmste der drei Faelle.

    Vorher fing ein except ValueError: pass das kaputte Datum ab und
    antwortete 200 "Tenant updated". Der Vermieter sah eine Bestaetigung und
    hatte einen unveraenderten Stand.
    """
    from datetime import date
    from models import Tenant
    _, wng = wohnung
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '2025-01-01'})
    mieter_id = _json(angelegt)['id']

    antwort = auth_client.put(f'/api/tenants/{mieter_id}', json={'move_in_date': 'irgendwann'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'move_in_date'
    assert Tenant.query.get(mieter_id).move_in_date == date(2025, 1, 1)


def test_mieteraenderung_raeumt_das_auszugsdatum_aus(auth_client, wohnung):
    """Leer heisst weiterhin: Feld leeren. Das darf die Pruefung nicht kippen."""
    from models import Tenant
    _, wng = wohnung
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id,
        'move_in_date': '2025-01-01', 'move_out_date': '2025-06-30'})
    mieter_id = _json(angelegt)['id']
    assert Tenant.query.get(mieter_id).move_out_date is not None

    antwort = auth_client.put(f'/api/tenants/{mieter_id}', json={'move_out_date': ''})
    assert antwort.status_code == 200
    assert Tenant.query.get(mieter_id).move_out_date is None


def test_zahlung_mit_text_als_betrag(auth_client, wohnung):
    """Vorher: der englische ValueError von float() ging als error hinaus."""
    _, wng = wohnung
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '2025-01-01'})
    antwort = auth_client.post('/api/payments', json={
        'tenant_id': _json(angelegt)['id'], 'amount': 'viel',
        'type': 'Miete', 'payment_date': '2025-01-01'})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['feld'] == 'amount'
    assert 'literal' not in rumpf['error']


def test_zahlungen_sammelloeschen_ohne_liste(auth_client):
    antwort = auth_client.delete('/api/payments/bulk', json={'ids': 'alle'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'ids'


def test_kostenprofile_mit_kaputtem_schluessel(auth_client, wohnung):
    """Vorher: int("strom") -> ValueError -> 500."""
    _, wng = wohnung
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '2025-01-01'})
    mieter_id = _json(angelegt)['id']
    antwort = auth_client.post(f'/api/tenants/{mieter_id}/profiles', json={'strom': 'PAUSCHALE'})
    assert antwort.status_code == 400
    assert 'Kostenart-Nummer' in _json(antwort)['error']


def test_abrechnung_mit_krummem_zeitraum(auth_client):
    """Vorher englisch, und ein krummes Datum war eine 500."""
    antwort = auth_client.post('/api/billing/preflight', json={
        'tenant_id': 1, 'start_date': '2025-01-01', 'end_date': 'Silvester'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'end_date'


def test_abrechnung_ohne_mieter(auth_client):
    antwort = auth_client.post('/api/billing/preflight', json={'start_date': '2025-01-01'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'tenant_id'


def test_plausibilitaet_behaelt_ihre_antwortform(auth_client):
    """Die Oberflaeche liest hier status und message, nicht error.

    Die Pruefung darf deutsch werden, die Form der Antwort nicht wechseln.
    """
    antwort = auth_client.post('/api/readings/check_plausibility', json={'value': 100})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['status'] == 'unknown'
    assert 'Zähler' in rumpf['message']


def test_pruefung_gilt_auch_fuer_die_adresszeile(auth_client):
    """Ein GET traegt seine Angaben hinter dem Fragezeichen.

    Vorher englisch: "Missing parameters" und "Invalid date format".
    """
    antwort = auth_client.get('/api/billing/interpolation-audit?meter_id=1&start_date=2025-01-01')
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'end_date'

    antwort = auth_client.get(
        '/api/billing/interpolation-audit'
        '?meter_id=1&start_date=2025-01-01&end_date=irgendwann')
    assert antwort.status_code == 400
    assert 'JJJJ-MM-TT' in _json(antwort)['error']


def test_immobilie_geht_auch_als_formular(auth_client):
    """Kriterium 1: form ist gleichberechtigt, vorher gab es dafuer eine 415."""
    antwort = auth_client.post('/api/properties', data={'name': 'Haus am See'})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)


def _texte_ausser_doku(pfad):
    """Alle Zeichenketten einer Datei, ohne die Dokumentationstexte.

    Ein blosses grep ueber die Quelle findet auch die Kommentare, die das
    alte Verhalten festhalten ("bei einer Luecke Missing parameters"). Genau
    die sollen bleiben duerfen.
    """
    import ast as _ast
    baum = _ast.parse(open(pfad, encoding='utf-8').read())
    doku = set()
    for knoten in _ast.walk(baum):
        if isinstance(knoten, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                               _ast.ClassDef)) and knoten.body:
            erster = knoten.body[0]
            if (isinstance(erster, _ast.Expr) and isinstance(erster.value, _ast.Constant)
                    and isinstance(erster.value.value, str)):
                doku.add(id(erster.value))
    return [k.value for k in _ast.walk(baum)
            if isinstance(k, _ast.Constant) and isinstance(k.value, str)
            and id(k) not in doku]


def test_keine_englische_pflichtfeldmeldung_mehr():
    """Kriterium 3 als Netz ueber alles: die alten Saetze sind weg."""
    alte_saetze = [
        'Name is required',
        'name, property_id, and sqm are required',
        'name, apartment_id, and move_in_date are required',
        'Invalid date format',
        'No file uploaded',
        'Empty filename',
        'Missing parameters',
        'No ids provided',
        'Path required',
        'Access denied',
        'File not found',
    ]
    vorhanden = set(_texte_ausser_doku('app.py'))
    treffer = [satz for satz in alte_saetze if satz in vorhanden]
    assert not treffer, treffer


# --------------------------------------------------------------------------
# NK-096: Abrechnungsarten an der Eingabe (F-25)
# --------------------------------------------------------------------------


def test_kostenprofile_nimmt_die_fuenf_arten():
    from abrechnungsart import ARTEN
    roh = {str(nummer): art for nummer, art in enumerate(ARTEN, start=1)}
    assert kostenprofile(roh) == dict(enumerate(ARTEN, start=1))


def test_kostenprofile_nimmt_leerzeichen_und_grossbuchstaben():
    """Transportrauschen aus einem Formular ist keine Aussage (NK-096)."""
    assert kostenprofile({'1': ' DIREKT ', '2': 'Qm'}) == {1: 'direkt', 2: 'qm'}


def test_kostenprofile_lehnt_eine_erfundene_art_ab():
    fehler = _fehler(lambda: kostenprofile({'1': 'verbrauch'}))
    assert 'verbrauch' in fehler.meldung
    assert fehler.feld == 'kostenart_1'


def test_kostenprofile_nennt_die_kostenart_beim_namen():
    """Ohne den Namen wuesste der Vermieter nicht, welche Zeile gemeint ist."""
    fehler = _fehler(lambda: kostenprofile({'7': 'verbrauch'}, {7: 'Wasser'}))
    assert 'Wasser' in fehler.meldung


def test_kostenprofile_prueft_alles_bevor_etwas_zurueckkommt():
    """Ein Abbruch in der Mitte liesse den Mieter ohne Profile zurueck.

    Die Route loescht die alten Profile, ehe sie die neuen anlegt -- deshalb
    muss die Pruefung vollstaendig sein, bevor der erste Eintrag entsteht.
    """
    fehler = _fehler(lambda: kostenprofile({'1': 'qm', '2': 'erfunden', '3': 'personen'}))
    assert 'erfunden' in fehler.meldung


def _kostenart(name='Wasser'):
    """Eine Kostenart, ohne die Grundausstattung der Testdatenbank zu stoeren.

    ``cost_categories.name`` ist seit NK-095 UNIQUE -- eine zweite 'Wasser'
    anzulegen waere ein IntegrityError, kein Testfall.
    """
    from models import CostCategory, db
    vorhanden = CostCategory.query.filter_by(name=name).first()
    if vorhanden:
        return vorhanden
    # Der Name wechselt je Fall, die Nummer nicht: Nr. 17 ist der offene
    # Posten und passt zu jedem erfundenen Namen (NK-044).
    kat = CostCategory(name=name, allocation_method='PER_SQM', betrkv_nr=17)
    db.session.add(kat)
    db.session.commit()
    return kat


def test_profilroute_lehnt_erfundene_art_mit_400_ab(auth_client, wohnung):
    """Vorher: der Wert ging ungeprueft in die Datenbank, und der Rechenkern
    liess die Kostenart spaeter lautlos aus dem Blatt fallen (F-25)."""
    from models import TenantCostProfile
    _, wng = wohnung
    kat = _kostenart()
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '2025-01-01'})
    mieter_id = _json(angelegt)['id']

    antwort = auth_client.post(f'/api/tenants/{mieter_id}/profiles',
                               json={str(kat.id): 'verbrauch'})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert kat.name in rumpf['error']
    assert 'verbrauch' in rumpf['error']
    assert TenantCostProfile.query.filter_by(tenant_id=mieter_id).count() == 0


def test_profilroute_laesst_die_alten_profile_stehen(auth_client, wohnung):
    """Eine abgelehnte Anfrage darf nichts loeschen."""
    from models import TenantCostProfile
    _, wng = wohnung
    kat = _kostenart()
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '2025-01-01'})
    mieter_id = _json(angelegt)['id']

    gut = auth_client.post(f'/api/tenants/{mieter_id}/profiles',
                           json={str(kat.id): 'personen'})
    assert gut.status_code == 200

    auth_client.post(f'/api/tenants/{mieter_id}/profiles',
                     json={str(kat.id): 'verbrauch'})

    geblieben = TenantCostProfile.query.filter_by(tenant_id=mieter_id).all()
    assert [p.billing_type for p in geblieben] == ['personen']


def test_profilroute_speichert_normiert(auth_client, wohnung):
    """Was in der Datenbank landet, ist immer die normierte Form -- nur
    deshalb darf die Bedingung im Schema hart sein."""
    from models import TenantCostProfile
    _, wng = wohnung
    kat = _kostenart()
    angelegt = auth_client.post('/api/tenants', json={
        'name': 'Müller', 'apartment_id': wng.id, 'move_in_date': '2025-01-01'})
    mieter_id = _json(angelegt)['id']

    antwort = auth_client.post(f'/api/tenants/{mieter_id}/profiles',
                               json={str(kat.id): ' DIREKT '})
    assert antwort.status_code == 200
    gespeichert = TenantCostProfile.query.filter_by(tenant_id=mieter_id).one()
    assert gespeichert.billing_type == 'direkt'
