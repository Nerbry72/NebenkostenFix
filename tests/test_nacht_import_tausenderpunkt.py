"""Tabellenimport: "1.200" wurde zu 1,20 €.

_zahlentext erkannte den Tausenderpunkt nur, wenn mehr als ein Punkt dastand
("1.234.567"). Ein einzelner Tausenderpunkt ohne Nachkommastellen -- so wie
eine deutsche Tabelle eine Kaution von 1.200 € ausgibt -- wurde als
Dezimalpunkt gelesen; "1.200" ergab 1.200 und runde() machte still 1,20 €
daraus. Drei Nachkommastellen gibt es bei einer Überweisung nicht
(geldbetrag in validation.py sagt das selbst), der Punkt kann hier also nur
Tausender trennen. Erwartet: 1.200,00 € (oder ein Fehler an der Zeile), nie
1,20 €. Alle Werte sind erfunden.

Nur Beträge lesen den einzelnen Punkt so. Ein Zählerstand „123.456“ m³ hat
zu Recht drei Nachkommastellen; ``als_zahl`` bleibt dabei.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix import tabellenimport as ti
from nebenkostenfix.models import CostInvoice, Payment, db
from tests import billing_factories as f


def _csv(*zeilen: str) -> bytes:
    return ('﻿' + '\r\n'.join(zeilen) + '\r\n').encode('utf-8')


def _lesen(client, art, inhalt):
    antwort = client.post(f'/api/import/{art}/lesen',
                          data={'datei': (io.BytesIO(inhalt), 'daten.csv')},
                          content_type='multipart/form-data')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    return antwort.get_json()


def _uebernehmen(client, art, gelesen):
    return client.post(f'/api/import/{art}/uebernehmen',
                       json={'kennung': gelesen['kennung'], 'zuordnung': gelesen['zuordnung']})


# --- Werte -----------------------------------------------------------------------

def test_einzelner_tausenderpunkt_ist_kein_dezimalpunkt():
    assert ti.als_betrag('1.200', 'Betrag') == Decimal('1200.00')


@pytest.mark.parametrize('roh, erwartet', [
    ('1.200', '1200.00'), ('2.500 €', '2500.00'), ('-1.200', '-1200.00'),
    ('€ 3.000', '3000.00'), ('100.000', '100000.00'), ('2.500 EUR', '2500.00'),
    ('+1.200', '1200.00'),
])
def test_betrag_mit_einem_tausenderpunkt(roh, erwartet):
    assert ti.als_betrag(roh, 'Betrag') == Decimal(erwartet)


def test_nur_drei_ziffern_hinter_einem_punkt_trennen_tausender():
    """Neben „1.200“ lesen sich die anderen Schreibweisen wie bisher.

    „0.125“ und „1,234“ wurden früher still auf 0,13 € und 1,23 € gerundet;
    sie werden jetzt abgewiesen (``tests/test_import_tausenderformat.py``).
    """
    assert ti.als_betrag('1.200', 'Betrag') == Decimal('1200.00')
    wie_bisher = [
        ('1.234.567', '1234567.00'), ('1.234,56', '1234.56'), ('1234.56', '1234.56'),
        ('12.5', '12.50'), ('1.20', '1.20'), ('1234.500', '1234.50'), (1234.5, '1234.50'),
        (1200.0, '1200.00'), (486, '486.00'), ('1.200,00', '1200.00'),
    ]
    for roh, erwartet in wie_bisher:
        assert ti.als_betrag(roh, 'Betrag') == Decimal(erwartet), roh


def test_zaehlerstand_behaelt_seine_drei_nachkommastellen():
    """Derselbe Text ist als Betrag 123.456,00 € und als Zählerstand 123,456."""
    assert ti.als_zahl('123.456', 'Stand') == 123.456
    assert ti.als_zahl('1.200', 'Fläche (m²)') == 1.2
    assert ti.als_betrag('123.456', 'Betrag') == Decimal('123456.00')


# --- Durchlauf über die API ------------------------------------------------------

def test_kaution_1200_kommt_nicht_als_1_20_an(auth_client, app_ctx):
    haus = f.house('Testhaus Nacht')
    f.tenant(f.apt(haus, 'EG links', 50), 'Anna Test', date(2024, 1, 1))
    db.session.commit()
    inhalt = ('﻿' + '\r\n'.join([
        'Immobilie;Wohnung;Mieter;Datum;Betrag (€);Art',
        'Testhaus Nacht;EG links;Anna Test;02.01.2024;1.200;Kaution',
    ]) + '\r\n').encode('utf-8')
    gelesen = auth_client.post('/api/import/zahlungen/lesen',
                               data={'datei': (io.BytesIO(inhalt), 'daten.csv')},
                               content_type='multipart/form-data')
    assert gelesen.status_code == 200, gelesen.get_data(as_text=True)
    g = gelesen.get_json()
    uebernahme = auth_client.post('/api/import/zahlungen/uebernehmen',
                                  json={'kennung': g['kennung'], 'zuordnung': g['zuordnung']})
    assert uebernahme.status_code in (200, 400), uebernahme.get_data(as_text=True)

    betraege = [z.amount for z in Payment.query.all()]
    assert Decimal('1.20') not in betraege, betraege


def test_zahlungsimport_uebernimmt_kaution_als_1200_euro(auth_client, app_ctx):
    haus = f.house('Testhaus Nachtweg')
    f.tenant(f.apt(haus, 'W1', 45), 'Mieter Eins', date(2024, 1, 1))
    inhalt = _csv('Immobilie;Wohnung;Mieter;Datum;Betrag (€);Art',
                  'Testhaus Nachtweg;W1;Mieter Eins;01.02.2024;1.200;Kaution')
    antwort = _uebernehmen(auth_client, 'zahlungen', _lesen(auth_client, 'zahlungen', inhalt))
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['uebernommen'] is True

    zahlung = Payment.query.one()
    assert zahlung.amount == Decimal('1200.00')
    assert zahlung.type == 'Kaution' and zahlung.payment_date == date(2024, 2, 1)


def test_rechnungsimport_uebernimmt_grundsteuer_als_2500_euro(auth_client, app_ctx):
    f.house('Testhaus Nachtweg')
    inhalt = _csv('Immobilie;Kostenart;Betrag (€);Zeitraum von;Zeitraum bis',
                  'Testhaus Nachtweg;Grundsteuer;2.500;01.01.2025;31.12.2025')
    antwort = _uebernehmen(auth_client, 'rechnungen', _lesen(auth_client, 'rechnungen', inhalt))
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['uebernommen'] is True

    rechnung = CostInvoice.query.one()
    assert rechnung.amount == Decimal('2500.00')
    assert (rechnung.start_date, rechnung.end_date) == (date(2025, 1, 1), date(2025, 12, 31))
