"""NK-216 (F1): Plausibilitaet beim Erfassen eines Zaehlerstands.

Befund der App-Analyse vom 2026-10-06: die Route nahm negative Staende,
Ablesungen in der Zukunft, rueckwaerts laufende Zaehler und doppelte Tage
ohne Wort an -- der Kern rechnete sie in jede Abrechnung. Jetzt: was nie
stimmt, ist 400; was fast nie stimmt, ist 409 mit einer Frage, und mit
``trotzdem`` wird gespeichert. Alle Werte sind erfunden.

*Haette den Fehler gefunden:* jeder Test hier -- vorher war jede Antwort 201/200.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from nebenkostenfix.models import MeterReading
from tests import billing_factories as f


@pytest.fixture
def zaehler(app_ctx):
    z = f.meter(f.house(), f.category('Wasser'), 'WZ-1', is_main=False)
    f.reading(z, date(2025, 1, 1), 100.0)
    f.reading(z, date(2025, 12, 31), 200.0)
    return z


def _neu(client, zaehler, datum, wert, **mehr):
    return client.post('/api/readings', data={
        'meter_id': str(zaehler.id), 'reading_date': datum, 'value': wert, **mehr})


def _anzahl(zaehler):
    return MeterReading.query.filter_by(meter_id=zaehler.id).count()


def test_passender_stand_geht_ohne_frage(auth_client, zaehler):
    assert _neu(auth_client, zaehler, '2025-06-30', '150').status_code == 201
    assert _anzahl(zaehler) == 3


def test_negativer_stand_ist_ein_fehler(auth_client, zaehler):
    antwort = _neu(auth_client, zaehler, '2024-06-30', '-1', trotzdem='1')
    assert antwort.status_code == 400
    assert antwort.get_json() == {'error': 'Ein Zählerstand kann nicht negativ sein.',
                                  'feld': 'value'}
    antwort = _neu(auth_client, zaehler, '2024-06-30', '1', value_nt='-0,5')
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == 'value_nt'
    assert _anzahl(zaehler) == 2


def test_datum_in_der_zukunft_ist_ein_fehler(auth_client, zaehler):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    antwort = _neu(auth_client, zaehler, morgen, '300', trotzdem='1')
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == 'reading_date'
    # Heute ist erlaubt
    assert _neu(auth_client, zaehler, date.today().isoformat(), '300').status_code == 201


@pytest.mark.parametrize('datum, wert, text', [
    ('2025-06-30', '99,5',
     'Der Stand 99,5 ist kleiner als der vorige vom 01.01.2025 (100). '
     'Ein Zähler läuft nicht rückwärts. Trotzdem speichern?'),
    ('2025-06-30', '200,25',
     'Der Stand 200,25 ist größer als der folgende vom 31.12.2025 (200). Trotzdem speichern?'),
    ('2025-12-31', '200',
     'Für diesen Zähler gibt es am 31.12.2025 schon einen Stand. '
     'Trotzdem einen zweiten speichern?'),
])
def test_unplausibel_wird_nachgefragt(auth_client, zaehler, datum, wert, text):
    antwort = _neu(auth_client, zaehler, datum, wert)
    assert antwort.status_code == 409
    assert antwort.get_json() == {'error': text, 'nachfrage': True}
    assert _anzahl(zaehler) == 2

    assert _neu(auth_client, zaehler, datum, wert, trotzdem='1').status_code == 201
    assert _anzahl(zaehler) == 3


def test_aendern_prueft_gegen_die_anderen_staende(auth_client, zaehler):
    mitte = f.reading(zaehler, date(2025, 6, 30), 150.0)

    # Der eigene Tag ist kein zweiter Stand
    assert auth_client.put(f'/api/readings/{mitte.id}', data={'value': '160'}).status_code == 200

    antwort = auth_client.put(f'/api/readings/{mitte.id}', data={'value': '250'})
    assert antwort.status_code == 409
    assert antwort.get_json()['nachfrage'] is True
    assert MeterReading.query.get(mitte.id).value == 160.0

    antwort = auth_client.put(f'/api/readings/{mitte.id}', data={'reading_date': '2025-01-01'})
    assert antwort.status_code == 409
    assert MeterReading.query.get(mitte.id).reading_date == date(2025, 6, 30)

    antwort = auth_client.put(f'/api/readings/{mitte.id}', data={'value': '250', 'trotzdem': 'true'})
    assert antwort.status_code == 200
    assert MeterReading.query.get(mitte.id).value == 250.0


def test_aendern_in_die_zukunft_ist_ein_fehler(auth_client, zaehler):
    stand = MeterReading.query.filter_by(meter_id=zaehler.id).first()
    morgen = (date.today() + timedelta(days=1)).isoformat()
    antwort = auth_client.put(f'/api/readings/{stand.id}', data={'reading_date': morgen})
    assert antwort.status_code == 400
    assert MeterReading.query.get(stand.id).reading_date == date(2025, 1, 1)


def test_andere_zaehler_zaehlen_nicht(auth_client, zaehler):
    anderer = f.meter(f.house('Nachbarhaus'), f.category('Strom'), 'SZ-1', is_main=False)
    assert _neu(auth_client, anderer, '2025-06-30', '5').status_code == 201
