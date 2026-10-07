"""NK-226: Vorschlag zur Anpassung der Vorauszahlung (R-VZ-01).

§ 560 Abs. 4 BGB erlaubt nach einer Abrechnung die Anpassung auf eine
angemessene Höhe. Die Software rechnet den Kostenanteil je Monat, ohne
pauschalen Zuschlag, und schlägt nur vor: gebucht und erklärt wird vom
Vermieter. Kein Vorschlag ohne vereinbarte Vorauszahlung, bei Auszug vor
dem Wirksamwerden und bei Teilauswahl der Kostenarten -- nichts still
schätzen.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from nebenkostenfix import vorauszahlung
from nebenkostenfix.anschreiben import PLATZHALTER, VORGABE, text_fuer
from nebenkostenfix.vorauszahlung import ab_datum, monate, vorschlag
from tests.test_anschreiben import _geklebt, unkomprimiert  # noqa: F401

JAHR_2025 = (date(2025, 1, 1), date(2025, 12, 31))
ACHTZIG = [(date(2025, m, 1), Decimal('80')) for m in range(1, 13)]


# --- Die Rechnung -------------------------------------------------------------


def test_ganze_monate_zaehlen_als_ganze():
    assert monate(*JAHR_2025) == 12


def test_angebrochene_monate_zaehlen_tagesgenau():
    # 15.–28.02.2025 sind 14 von 28 Tagen, dazu der volle März.
    assert monate(date(2025, 2, 15), date(2025, 3, 31)) == Decimal('1.5')


def test_wirksam_ab_dem_ersten_des_uebernaechsten_monats():
    assert ab_datum(date(2026, 3, 15)) == date(2026, 5, 1)
    assert ab_datum(date(2026, 3, 1)) == date(2026, 5, 1)
    assert ab_datum(date(2026, 11, 30)) == date(2027, 1, 1)
    assert ab_datum(date(2026, 12, 1)) == date(2027, 2, 1)


def test_der_vorschlag_ist_der_kostenanteil_je_monat():
    v = vorschlag(Decimal('1200'), *JAHR_2025, None, ACHTZIG, date(2026, 3, 15))
    assert v == {'ab': '2026-05-01', 'bisher': '80.00', 'neu': '100.00',
                 'kosten': '1200.00', 'monate': '12.00', 'kuenftige': 0,
                 'aenderung': True}


def test_teilmonate_gehen_in_den_monatsbetrag_ein():
    v = vorschlag(Decimal('150'), date(2025, 2, 15), date(2025, 3, 31), None,
                  ACHTZIG, date(2026, 3, 15))
    assert v['neu'] == '100.00'
    assert v['monate'] == '1.50'


def test_gerundet_wird_kaufmaennisch_auf_volle_euro():
    """Kein Sicherheitszuschlag: 100,50 € werden 101 €, 100,49 € werden 100 €."""
    assert vorschlag(Decimal('1206'), *JAHR_2025, None, ACHTZIG,
                     date(2026, 3, 15))['neu'] == '101.00'
    assert vorschlag(Decimal('1205.88'), *JAHR_2025, None, ACHTZIG,
                     date(2026, 3, 15))['neu'] == '100.00'


def test_bisher_ist_die_letzte_vorauszahlung_bis_zum_stichtag():
    zahlungen = ACHTZIG + [(date(2026, 1, 1), Decimal('95')),
                           (date(2026, 5, 1), Decimal('95')),
                           (date(2026, 6, 1), Decimal('95'))]
    v = vorschlag(Decimal('1200'), *JAHR_2025, None, zahlungen, date(2026, 3, 15))
    assert v['bisher'] == '95.00'
    # Zwei schon gebuchte Zahlungen ab dem Wirksamwerden: Doppelbuchung droht.
    assert v['kuenftige'] == 2


def test_gleicher_betrag_ist_keine_aenderung():
    v = vorschlag(Decimal('960'), *JAHR_2025, None, ACHTZIG, date(2026, 3, 15))
    assert v['aenderung'] is False


def test_ohne_vorauszahlung_kein_vorschlag():
    v = vorschlag(Decimal('1200'), *JAHR_2025, None, [], date(2026, 3, 15))
    assert set(v) == {'grund'}
    assert '§ 560' in v['grund']


def test_auszug_vor_dem_wirksamwerden_kein_vorschlag():
    v = vorschlag(Decimal('1200'), *JAHR_2025, date(2026, 4, 30), ACHTZIG,
                  date(2026, 3, 15))
    assert set(v) == {'grund'}
    # Wer erst danach auszieht, zahlt noch: dann gilt der Vorschlag.
    v = vorschlag(Decimal('1200'), *JAHR_2025, date(2026, 5, 31), ACHTZIG,
                  date(2026, 3, 15))
    assert v['neu'] == '100.00'


def test_teilauswahl_der_kostenarten_kein_vorschlag():
    v = vorschlag(Decimal('1200'), *JAHR_2025, None, ACHTZIG, date(2026, 3, 15),
                  teilauswahl=True)
    assert set(v) == {'grund'}
    assert 'Kostenarten' in v['grund']


# --- Der Platzhalter im Anschreiben --------------------------------------------


def _text(vorlage, **zusatz):
    return text_fuer(vorlage, mieter_name='A', wohnung_name='W', objekt_name='O',
                     zeitraum='Z', gesamtsumme=Decimal('1200'),
                     vorauszahlungen=Decimal('960'), saldo=Decimal('240'),
                     **zusatz)


def test_der_platzhalter_ist_bekannt_aber_nicht_in_der_vorgabe():
    assert 'vorauszahlung_anpassung' in PLATZHALTER
    assert '{vorauszahlung_anpassung}' not in VORGABE


def test_der_platzhalter_nennt_die_neue_hoehe():
    v = vorschlag(Decimal('1200'), *JAHR_2025, None, ACHTZIG, date(2026, 3, 15))
    assert _text('{vorauszahlung_anpassung}', vorauszahlung=v) == (
        'Ab dem 01.05.2026 beträgt Ihre monatliche Vorauszahlung 100,00 € '
        '(bisher 80,00 €).')


def test_der_platzhalter_bleibt_ohne_aenderung_gewollt_leer():
    gleich = vorschlag(Decimal('960'), *JAHR_2025, None, ACHTZIG, date(2026, 3, 15))
    keiner = vorschlag(Decimal('960'), *JAHR_2025, None, [], date(2026, 3, 15))
    assert _text('x{vorauszahlung_anpassung}x', vorauszahlung=gleich) == 'xx'
    assert _text('x{vorauszahlung_anpassung}x', vorauszahlung=keiner) == 'xx'
    assert _text('x{vorauszahlung_anpassung}x') == 'xx'


# --- Die Routen ---------------------------------------------------------------

from billing_factories import apt, category, house, invoice, payment, tenant  # noqa: E402

ZEITRAUM = {'start_date': '2025-01-01', 'end_date': '2025-12-31'}


def _welt(app_ctx):
    """Ein Mieter allein im Haus: 1200 € Grundsteuer, 600 € Müll, 80 € im Monat."""
    prop = house('Vorauszahlungshaus')
    mieter = tenant(apt(prop, 'EG', 50.0), 'Vera Vorauszahlerin',
                    move_in=date(2024, 1, 1))
    steuer = category('Grundsteuer')
    muell = category('Müllabfuhr')
    invoice(prop, steuer, 1200.0, *JAHR_2025)
    invoice(prop, muell, 600.0, *JAHR_2025, invoice_number='INV-2')
    for m in range(1, 13):
        payment(mieter, 80.0, date(2025, m, 1))
    return mieter, steuer, muell


def test_die_vorschau_liefert_den_vorschlag(auth_client, app_ctx, monkeypatch):
    monkeypatch.setattr(vorauszahlung, '_heute', lambda: date(2026, 3, 15))
    mieter, steuer, muell = _welt(app_ctx)

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id, **ZEITRAUM,
        'category_ids': [steuer.id, muell.id]})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    v = antwort.get_json()['vorauszahlung']
    assert (v['ab'], v['bisher'], v['neu']) == ('2026-05-01', '80.00', '150.00')


def test_die_vorschau_einer_teilauswahl_hat_keinen_vorschlag(
        auth_client, app_ctx, monkeypatch):
    monkeypatch.setattr(vorauszahlung, '_heute', lambda: date(2026, 3, 15))
    mieter, steuer, _ = _welt(app_ctx)

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id, **ZEITRAUM, 'category_ids': [steuer.id]})
    v = antwort.get_json()['vorauszahlung']
    assert set(v) == {'grund'}


def test_die_details_rechnen_ab_der_erstellung(auth_client, app_ctx):
    from nebenkostenfix.models import TenantBillingReport, db
    mieter, _, _ = _welt(app_ctx)
    assert auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter.id, **ZEITRAUM}).status_code == 201
    report = TenantBillingReport.query.one()
    report.aktuelle_version.erstellt_am = date(2026, 3, 15)
    db.session.commit()

    v = auth_client.get(f'/api/billing/reports/{report.id}/details') \
        .get_json()['vorauszahlung']
    assert (v['ab'], v['neu']) == ('2026-05-01', '150.00')


def test_die_festsetzung_erklaert_die_anpassung_im_anschreiben(
        auth_client, app_ctx, monkeypatch, unkomprimiert):  # noqa: F811
    from nebenkostenfix.models import TenantBillingReport
    monkeypatch.setattr(vorauszahlung, '_heute', lambda: date(2026, 3, 15))
    mieter, _, _ = _welt(app_ctx)
    auth_client.put(
        f'/api/properties/{mieter.apartment.property_id}/anschreiben',
        json={'text': 'Hallo.\n\n{vorauszahlung_anpassung}'})

    assert auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter.id, **ZEITRAUM}).status_code == 201
    report = TenantBillingReport.query.one()
    blatt = _geklebt((Path(os.environ['NAS_MOUNT_PATH'])
                      / report.document_path).read_bytes())
    assert 'Abdem01.05.2026beträgtIhremonatlicheVorauszahlung150,00€(bisher80,00€).' in blatt
