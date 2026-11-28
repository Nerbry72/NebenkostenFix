"""Tabellenimport: „1,234.56“ wurde still zu 1,23 €.

Befund: Steht in einer Tabelle ein Betrag in englischer Schreibweise mit
Tausenderkomma („1,234.56“), strich ``_zahlentext`` bei genau einem Komma
alle Punkte und las das Komma als Dezimaltrenner. Aus 1.234,56 € wurde
„1.23456“, ``runde`` machte daraus still 1,23 €. Dasselbe traf
Zählerstände („1,234.5“ → 1,2345) und Ziffernfolgen mit kaputten Gruppen
(„1.23.45“ → 12.345).

Erwartet:

- Stehen Komma und Punkt beide da, trennt der **letzte** Trenner die
  Nachkommastellen, der andere Tausender (Gruppen zu drei Ziffern).
- Was sich nicht eindeutig lesen lässt (falsche Gruppen, zwei
  Dezimaltrenner, „1,000“ als Betrag) und ein Betrag mit mehr als zwei
  Nachkommastellen, der gerundet würde, wird mit einer verständlichen
  Meldung an der Zeile abgewiesen statt still verfälscht.
- Deutsche Schreibweisen und der einzelne Tausenderpunkt („1.200“) lesen
  sich wie bisher.

Alle Werte sind erfunden.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix import tabellenimport as ti
from nebenkostenfix.models import CostInvoice, Payment
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


# --- Beträge -----------------------------------------------------------------------

def test_englischer_betrag_mit_tausenderkomma_wird_nicht_zu_cent():
    assert ti.als_betrag('1,234.56', 'Betrag') == Decimal('1234.56')


@pytest.mark.parametrize('roh, erwartet', [
    ('1,234.56', '1234.56'), ('12,345.60 €', '12345.60'), ('-1,234.56', '-1234.56'),
    ('1,234,567.89', '1234567.89'), ('€ 2,500.00', '2500.00'), ('1,234,567', '1234567.00'),
])
def test_englische_schreibweise(roh, erwartet):
    assert ti.als_betrag(roh, 'Betrag') == Decimal(erwartet)


@pytest.mark.parametrize('roh, erwartet', [
    ('1.234,56', '1234.56'), ('1.234.567,89', '1234567.89'), ('1,5', '1.50'),
    ('1234,56', '1234.56'), ('1.200', '1200.00'), ('1.234.567', '1234567.00'),
    ('1234.56', '1234.56'), ('12.5', '12.50'), ('1 234,5', '1234.50'), ('-1.200', '-1200.00'),
    ('1234.500', '1234.50'), ('0,500', '0.50'), (1234.5, '1234.50'), (486, '486.00'),
])
def test_deutsche_und_eindeutige_schreibweisen_bleiben(roh, erwartet):
    assert ti.als_betrag(roh, 'Betrag') == Decimal(erwartet)


@pytest.mark.parametrize('roh', [
    '1,234,56',      # Komma-Gruppen, die letzte hat nur zwei Ziffern
    '1.23.45',       # Punkt-Gruppen ohne drei Ziffern
    '1.234.56',      # dito, letzte Gruppe zu kurz
    '12,34.56',      # Tausendergruppe mit zwei Ziffern
    '1,234.567.89',  # zwei Dezimalpunkte hinter dem Komma
    '1.234,567,89',  # zwei Dezimalkommas hinter dem Punkt
    '1.5,25',        # Punkt vor dem Komma, aber keine Dreiergruppe
    ',5.00',         # Trenner ganz vorn
])
def test_unlesbare_trenner_werden_abgewiesen(roh):
    with pytest.raises(ti.ZeilenFehler, match='Tausender') as fehler:
        ti.als_betrag(roh, 'Betrag')
    assert fehler.value.args[0].startswith(f'Betrag: „{roh}“')


@pytest.mark.parametrize('roh', ['0.125', '1.234,567', '12,3456', '1,234.567'])
def test_mehr_als_zwei_nachkommastellen_werden_nicht_still_gerundet(roh):
    with pytest.raises(ti.ZeilenFehler, match='mehr als zwei Nachkommastellen'):
        ti.als_betrag(roh, 'Betrag')


@pytest.mark.parametrize('roh', ['1,234', '1,000', '12,500', '-1,200', '999,999'])
def test_ein_komma_mit_drei_ziffern_ist_als_betrag_mehrdeutig(roh):
    """1,000 heißt englisch tausend, deutsch einen Euro -- keins von beiden raten."""
    with pytest.raises(ti.ZeilenFehler, match='nicht eindeutig'):
        ti.als_betrag(roh, 'Betrag')


def test_excel_zahlzelle_wird_weiter_auf_cent_gerundet():
    """Eine Zahlzelle (float) ist kein getippter Text: eine Formel wie =100/3
    zeigt 33,33 und speichert mehr Stellen. Sie wird wie bisher gerundet."""
    assert ti.als_betrag(100 / 3, 'Betrag') == Decimal('33.33')
    assert ti.als_betrag(0.1 + 0.2, 'Betrag') == Decimal('0.30')


# --- Zahlen (Zählerstände, Fläche) -----------------------------------------------------

@pytest.mark.parametrize('roh, erwartet', [
    ('1,234.5', 1234.5), ('1.234,5', 1234.5), ('1,234,567', 1234567.0),
    ('123.456', 123.456), ('1,234', 1.234), ('1.200', 1.2), ('62,5', 62.5),
])
def test_zahl_liest_beide_schreibweisen(roh, erwartet):
    assert ti.als_zahl(roh, 'Stand') == erwartet


@pytest.mark.parametrize('roh', ['1,234,56', '1.23.45', '1,234.5.6'])
def test_zahl_mit_unlesbaren_trennern_wird_abgewiesen(roh):
    with pytest.raises(ti.ZeilenFehler, match='Tausender') as fehler:
        ti.als_zahl(roh, 'Stand')
    assert fehler.value.args[0].startswith(f'Stand: „{roh}“')


# --- Durchlauf über die API ------------------------------------------------------------

def test_rechnungsimport_uebernimmt_englischen_betrag_voll(auth_client, app_ctx):
    f.house('Testhaus Trenner')
    inhalt = _csv('Immobilie,Kostenart,Betrag (€),Zeitraum von,Zeitraum bis',
                  'Testhaus Trenner,Grundsteuer,"1,234.56",2025-01-01,2025-12-31')
    antwort = _uebernehmen(auth_client, 'rechnungen', _lesen(auth_client, 'rechnungen', inhalt))
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['uebernommen'] is True
    assert CostInvoice.query.one().amount == Decimal('1234.56')


@pytest.mark.parametrize('roh', [
    '1.23.45',  # las der Import früher still als 12.345,00 €
    '1,000',    # las der Import früher still als 1,00 €
])
def test_zahlungsimport_weist_mehrdeutigen_betrag_an_der_zeile_ab(auth_client, app_ctx, roh):
    haus = f.house('Testhaus Trenner')
    f.tenant(f.apt(haus, 'W1', 45), 'Mieter Eins', date(2024, 1, 1))
    inhalt = _csv('Immobilie;Wohnung;Mieter;Datum;Betrag (€);Art',
                  f'Testhaus Trenner;W1;Mieter Eins;01.02.2024;{roh};Kaution')
    antwort = _uebernehmen(auth_client, 'zahlungen', _lesen(auth_client, 'zahlungen', inhalt))
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert bericht['uebernommen'] is False
    assert [z['zeile'] for z in bericht['fehler']] == [2]
    meldung = bericht['fehler'][0]['meldung']
    assert meldung.startswith(f'Betrag (€): „{roh}“')
    assert 'nicht eindeutig' in meldung
    assert Payment.query.count() == 0


def test_tabellen_erfassung_weist_betrag_mit_drei_nachkommastellen_ab(auth_client, app_ctx):
    f.house('Testhaus Trenner')
    antwort = auth_client.post('/api/import/rechnungen/tabelle', json={'zeilen': [{
        'immobilie': 'Testhaus Trenner', 'kostenart': 'Grundsteuer', 'betrag': '0,125',
        'von': '01.01.2025', 'bis': '31.12.2025'}], 'uebernehmen': True})
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    meldung = antwort.get_json()['fehler'][0]['meldung']
    assert 'mehr als zwei Nachkommastellen' in meldung
    assert CostInvoice.query.count() == 0
