"""NK-094: UTC speichern, Ortszeit zeigen.

Die Zeitstempel stehen in UTC in der Datenbank. Was der Vermieter liest --
die letzte Anmeldung, das Erstellungsdatum einer Abrechnung -- ist eine
Ortszeit (Europe/Berlin). Der Unterschied ist nicht konstant: Im Sommer
sind es zwei Stunden, im Winter einer. Genau daran hängt der Wächtertest:
beide Fälle sind gepinnt, ein fester Offset fiele durch.

Geprüft wird die ganze Bahn: das Modul ``zeit``, die Anmeldung
(``/api/auth/me`` und die Kontenliste auf der Kommandozeile), die
Erstellungszeit in den Berichtslisten und der Vergleich an der
Zustellungsroute, der seit NK-137 auch mit Zeilen aus der Produktion
(datetime) klarommt, nicht nur mit reinen Datumswerten aus alten
Sicherungen.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import zeit
from billing_factories import apt, house, tenant
from frist import frist_ende
from models import TenantBillingReport, User, db
from test_auth import TEST_PASSWORD, TEST_USER


# --- Das Modul zeit ---

def test_jetzt_utc_liefert_naive_utc_zeit():
    """Zum Speichern: keine Zone angeheftet, dicht an der echten UTC-Uhr."""
    vorher = datetime.utcnow()
    stempel = zeit.jetzt_utc()
    nachher = datetime.utcnow()
    assert stempel.tzinfo is None
    assert vorher <= stempel <= nachher


def test_sommer_ist_zwei_stunden_vor_utc():
    """MESZ (Juli): UTC 10:30 zeigt als 12:30."""
    assert zeit.als_ortszeit(datetime(2026, 7, 15, 10, 30)) \
        == '15.07.2026 12:30'


def test_winter_ist_eine_stunde_vor_utc():
    """MEZ (Januar): UTC 10:30 zeigt als 11:30 -- der feste Offset fiele hier durch."""
    assert zeit.als_ortszeit(datetime(2026, 1, 15, 10, 30)) \
        == '15.01.2026 11:30'


def test_ohne_zeitpunkt_bleibt_die_anzeige_leer():
    assert zeit.als_ortszeit(None) is None


def test_ein_reines_datum_wird_ohne_zone_formatiert():
    """Datumswerte aus DATE-Spalten sind Kalenderdaten, keine Uhrzeiten."""
    assert zeit.als_ortszeit(date(2026, 7, 15)) == '15.07.2026'


def test_zeitpunkt_mit_zone_wird_nicht_doppelt_verschoben():
    """Eine aware-Zeit wird nur gewandelt, nicht nochmal als UTC gelesen."""
    aware = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
    assert zeit.als_ortszeit(aware) == '15.07.2026 12:30'


# --- Die Anmeldung ---

def test_die_anmeldung_steht_in_ortszeit(auth_client, app_ctx):
    """Der Stempel der laufenden Sitzung wird als Berliner Zeit angezeigt.

    Der Testclient meldet sich beim Aufbau an; danach wird der Stempel
    auf einen bekannten Sommerzeitpunkt gesetzt und die Anzeige
    dagegen gepinnt.
    """
    nutzer = User.query.filter_by(username=TEST_USER).first()
    nutzer.last_login_at = datetime(2026, 7, 15, 10, 30)
    db.session.commit()

    daten = auth_client.get('/api/auth/me').get_json()
    assert daten['last_login_at'] == '15.07.2026 12:30'


def test_ohne_anmeldung_bleibt_die_anzeige_leer(auth_client):
    """Noch nie angemeldet: kein Datum, auch kein 'None' als Text."""
    nutzer = User.query.filter_by(username=TEST_USER).first()
    nutzer.last_login_at = None
    db.session.commit()

    daten = auth_client.get('/api/auth/me').get_json()
    assert daten['last_login_at'] is None


def test_die_kontenliste_nennt_die_ortszeit(app_ctx):
    """Auch die Kommandozeile zeigt MEZ/MESZ, nicht die Server-Uhr."""
    nutzer = User(username=TEST_USER)
    nutzer.set_password(TEST_PASSWORD)
    nutzer.last_login_at = datetime(2026, 1, 15, 10, 30)
    db.session.add(nutzer)
    db.session.commit()

    ergebnis = app_ctx.app.test_cli_runner().invoke(
        args=['users', 'list'])
    assert ergebnis.exit_code == 0
    assert 'letzte Anmeldung: 15.01.2026 11:30' in ergebnis.output


# --- Die Erstellungszeit der Abrechnungen ---

def test_die_erstellungszeit_wird_in_ortszeit_angezeigt(auth_client, app_ctx):
    """Beide Berichtslisten zeigen 'TT.MM.JJJJ' statt ISO-Text.

    Die Tabelle traegt created_at als Datum; was die Liste zeigt, ist
    derselbe Tag im deutschen Format. (SQLite rundet Uhrzeiten an dieser
    Spalte weg -- genau darum zeigt der Weg hier nur den Tag.)
    """
    mieter = _mieter(app_ctx)
    bericht = TenantBillingReport(
        tenant_id=mieter.id, start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31), frist_ende=frist_ende(date(2025, 12, 31)),
        created_at=date(2026, 7, 15))
    db.session.add(bericht)
    db.session.commit()

    for weg in (f'/api/tenants/{mieter.id}/billing_reports',
                '/api/billing/reports'):
        daten = auth_client.get(weg).get_json()
        treffer = [r for r in daten if r['id'] == bericht.id]
        assert treffer, weg
        assert treffer[0]['created_at'] == '15.07.2026'


# --- Der Vergleich an der Zustellungsroute ---

def test_zustellung_mit_uhrzeit_in_created_at_bricht_nicht_ab(auth_client, app_ctx):
    """Der Vergleich an der Route vergleicht Tag mit Tag.

    ``datum`` ist ein Datum, ``created_at`` kommt je nach Tabelle als
    Datum oder als UTC-Zeitpunkt an -- ein direkter Vergleich von Datum
    mit Zeitpunkt bricht mit TypeError ab (500 statt 400). Seit NK-137
    wird created_at erst auf den Tag in Berlin gekürzt, dann verglichen;
    die Meldung zeigt genau diesen Tag.
    """
    mieter = _mieter(app_ctx)
    bericht = TenantBillingReport(
        tenant_id=mieter.id, start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31), frist_ende=frist_ende(date(2025, 12, 31)),
        created_at=datetime(2026, 7, 14, 23, 30))
    db.session.add(bericht)
    db.session.commit()

    # Der Tag vor der Erstellung wird abgewiesen, die Meldung nennt den
    # Erstellungstag:
    abweisung = auth_client.post(
        f'/api/billing/reports/{bericht.id}/zustellung',
        json={'zugestellt_am': '2026-07-13'})
    assert abweisung.status_code == 400
    assert '14.07.2026' in abweisung.get_json()['error']

    # Am Erstellungstag selbst klappt die Nachtragung (kein Absturz):
    okay = auth_client.post(
        f'/api/billing/reports/{bericht.id}/zustellung',
        json={'zugestellt_am': '2026-07-14'})
    assert okay.status_code == 200


from billing_factories import apt, house, tenant


def _mieter(app_ctx):
    """Ein Objekt mit Wohnung und Mieter, wie in den Frist-Tests."""
    objekt = house(name='Zeit-Objekt')
    wohnung = apt(objekt, 'EG links', 60.0)
    return tenant(wohnung, 'Zeit-Mieter', move_in=date(2025, 1, 1))
