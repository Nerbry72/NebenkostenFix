"""Zahlungen: eine lange Serie bricht still nach 121 Zahlungen ab.

POST /api/payments mit is_recurring bucht Monat für Monat bis zum Enddatum,
hört aber nach 121 Buchungen auf (``if created_count > 120: break``), ohne
das zu melden: die Antwort lautet „121 Zahlungen erfolgreich erfasst“ und
ist 201. Bei einer Nebenkostenvorauszahlung bleibt das Soll ab Beginn der
Serie stehen (R-VZ-02). Die Monate nach dem stillen Abbruch stehen damit als
Rückstand in Soll und Ist, samt Zahlungserinnerung, obwohl der Vermieter die
Serie bis zum Enddatum angelegt hat.

Erwartet: entweder bucht die Serie bis zum Enddatum, oder sie wird mit einer
Absage abgelehnt und legt nichts an. Gebaut ist die Absage: Eine Serie
umfasst höchstens 120 Termine (``SERIE_MAX_TERMINE``). Mehr lehnt die Route
vor der ersten Buchung am Feld end_date ab, auch ohne Enddatum, und nennt
den letzten möglichen Termin. Genau 120 Termine bleiben erlaubt. Alle Namen,
Daten und Beträge sind erfunden.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix.models import Payment, VorauszahlungSoll, db
from nebenkostenfix.tabellenimport import ZAHLUNGSARTEN
from tests import billing_factories as f

VZ = 'Nebenkostenvorauszahlung'


def test_lange_serie_wird_nicht_still_abgeschnitten(auth_client, app_ctx):
    haus = f.house('Testhaus Langzeit')
    mieter = f.tenant(f.apt(haus, 'W1', 48), 'Mieter Langzeit', date(2014, 1, 1),
                      date(2025, 12, 31))
    db.session.commit()

    # 01.2015 bis 12.2025: 132 Monatstermine.
    antwort = auth_client.post('/api/payments', data={
        'tenant_id': str(mieter.id), 'is_recurring': 'true',
        'type': 'Nebenkostenvorauszahlung', 'amount': '100.00',
        'payment_date': '2015-01-01', 'end_date': '2025-12-01'})
    gebucht = Payment.query.filter_by(tenant_id=mieter.id).count()

    if antwort.status_code == 201:
        assert gebucht == 132, (
            f'Serie bis 12/2025 angelegt, gebucht sind {gebucht} Zahlungen; '
            f'Antwort: {antwort.get_json()}')
        stand = auth_client.get(f'/api/tenants/{mieter.id}/vorauszahlungen').get_json()
        assert stand['saldo'] == '0.00'
    else:
        assert 400 <= antwort.status_code < 500
        assert gebucht == 0 and VorauszahlungSoll.query.count() == 0


# --- Absage bei mehr als 120 Terminen ---------------------------------------------

@pytest.fixture
def mieter(app_ctx):
    """Mieter Eins wohnt seit dem 01.01.2015, ein Auszug ist nicht eingetragen."""
    haus = f.house('Testhaus Nachtweg')
    eins = f.tenant(f.apt(haus, 'W1', 45), 'Mieter Eins', date(2015, 1, 1))
    db.session.commit()
    return eins


def _serie(client, mieter, **felder):
    daten = {'tenant_id': str(mieter.id), 'is_recurring': 'true', 'type': VZ,
             'amount': '80.00'}
    daten.update(felder)
    return client.post('/api/payments', data=daten)


def _bestand(mieter):
    zahlungen = Payment.query.filter_by(tenant_id=mieter.id).count()
    soll = [(s.gueltig_ab, s.betrag) for s in
            VorauszahlungSoll.query.filter_by(tenant_id=mieter.id)
            .order_by(VorauszahlungSoll.gueltig_ab)]
    return zahlungen, soll


def _abgewiesen(antwort):
    assert antwort.status_code == 400, (antwort.status_code, antwort.get_json())
    fehler = antwort.get_json()
    assert fehler['feld'] == 'end_date', fehler
    return fehler['error']


def test_vorauszahlung_ueber_120_termine_wird_abgewiesen(auth_client, mieter):
    """Der Späherfall: 01.2015 bis 12.2025 sind 132 Termine."""
    antwort = _serie(auth_client, mieter, payment_date='2015-01-01',
                     end_date='2025-12-01')

    assert _abgewiesen(antwort) == (
        'Eine Serie umfasst höchstens 120 Zahlungen. Mit diesem Beginn endet '
        'sie spätestens am 01.12.2024. Bitte teilen Sie die Serie auf.')
    assert _bestand(mieter) == (0, [])

    # Ohne Soll und ohne Zahlung gibt es keinen Rückstand und keine Erinnerung.
    ansicht = auth_client.get(f'/api/tenants/{mieter.id}/vorauszahlungen').get_json()
    assert ansicht['soll'] == []
    assert not any(m['rueckstand'] for m in ansicht['monate'])
    assert ansicht['offen'] == '0.00'
    assert ansicht['erinnerung'] is None


@pytest.mark.parametrize('art', ZAHLUNGSARTEN)
def test_ueber_120_termine_gilt_fuer_jede_zahlungsart(auth_client, mieter, art):
    antwort = _serie(auth_client, mieter, type=art, payment_date='2015-01-01',
                     end_date='2025-12-01')

    assert '120' in _abgewiesen(antwort)
    assert _bestand(mieter) == (0, [])
    assert Payment.query.count() == 0


def test_ohne_enddatum_ueber_120_termine_wird_abgewiesen(auth_client, mieter):
    """Ohne Enddatum läuft die Serie bis Ende nächsten Jahres, ab 2015 also
    weit über 120 Termine."""
    antwort = _serie(auth_client, mieter, payment_date='2015-01-01')

    text = _abgewiesen(antwort)
    assert '120' in text
    assert '01.12.2024' in text
    assert f'31.12.{date.today().year + 1}' in text
    assert 'Enddatum' in text
    assert _bestand(mieter) == (0, [])


def test_121_termine_werden_abgewiesen(auth_client, mieter):
    antwort = _serie(auth_client, mieter, payment_date='2015-01-01',
                     end_date='2025-01-01')

    assert '120' in _abgewiesen(antwort)
    assert _bestand(mieter) == (0, [])


def test_genau_120_termine_bleiben_erlaubt(auth_client, mieter):
    antwort = _serie(auth_client, mieter, payment_date='2015-01-01',
                     end_date='2024-12-01')

    assert antwort.status_code == 201, antwort.get_json()
    assert antwort.get_json()['message'] == '120 Zahlungen erfolgreich erfasst'
    assert _bestand(mieter) == (120, [(date(2015, 1, 1), Decimal('80.00'))])

    ansicht = auth_client.get(f'/api/tenants/{mieter.id}/vorauszahlungen').get_json()
    gedeckt = [m for m in ansicht['monate'] if '2015-01' <= m['monat'] <= '2024-12']
    assert len(gedeckt) == 120
    assert all(m['ist'] == '80.00' and m['differenz'] == '0.00'
               and not m['rueckstand'] for m in gedeckt)


def test_grenze_zaehlt_mit_der_monatsende_kappung(auth_client, mieter):
    """Ab dem 31.03.2015 ist der 120. Termin der 28.02.2025, der 121. der
    31.03.2025. Die Absage nennt den gekappten Tag."""
    erlaubt = _serie(auth_client, mieter, payment_date='2015-03-31',
                     end_date='2025-03-30')
    assert erlaubt.status_code == 201, erlaubt.get_json()
    assert erlaubt.get_json()['message'] == '120 Zahlungen erfolgreich erfasst'
    letzte = (Payment.query.filter_by(tenant_id=mieter.id)
              .order_by(Payment.payment_date.desc()).first())
    assert letzte.payment_date == date(2025, 2, 28)

    Payment.query.delete()
    VorauszahlungSoll.query.delete()
    db.session.commit()

    zuviel = _serie(auth_client, mieter, payment_date='2015-03-31',
                    end_date='2025-03-31')
    assert 'spätestens am 28.02.2025' in _abgewiesen(zuviel)
    assert _bestand(mieter) == (0, [])


# --- Gegenprobe: kurze Serien und Einzelbuchungen bleiben, wie sie waren ---------

def test_jahresserie_zum_monatsende_bleibt_wie_bisher(auth_client, mieter):
    antwort = _serie(auth_client, mieter, type='Miete', payment_date='2024-01-31',
                     end_date='2024-12-31')

    assert antwort.status_code == 201, antwort.get_json()
    assert antwort.get_json()['message'] == '12 Zahlungen erfolgreich erfasst'
    termine = [p.payment_date for p in Payment.query.filter_by(tenant_id=mieter.id)
               .order_by(Payment.payment_date)]
    assert termine[:4] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31),
                           date(2024, 4, 30)]
    assert len(termine) == 12 and termine[-1] == date(2024, 12, 31)


def test_einzelbuchung_weit_zurueck_bleibt_wie_bisher(auth_client, mieter):
    antwort = auth_client.post('/api/payments', data={
        'tenant_id': str(mieter.id), 'amount': '80.00', 'type': VZ,
        'payment_date': '2015-01-01'})

    assert antwort.status_code == 201, antwort.get_json()
    assert antwort.get_json()['message'] == 'Zahlung erfolgreich erfasst'
    assert _bestand(mieter) == (1, [])
