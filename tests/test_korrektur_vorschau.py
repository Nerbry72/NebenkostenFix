"""NK-217 (F2): veraltete Abrechnungen kennzeichnen, Korrektur mit Vorschau.

Befund der App-Analyse vom 2026-10-06: NK-208 und NK-213 ändern Zahlen, eine
finalisierte Abrechnung zeigt aber nicht, dass sie nach einem älteren
Regelstand gerechnet ist, und die Korrektur fragt nur „Erstellen?“, ohne zu
sagen, was sich ändert. Jetzt melden Liste und Details ``veraltet``, und
``/korrektur/vorschau`` rechnet neu, ohne zu speichern. Alle Werte sind erfunden.

*Hätte den Fehler gefunden:* jeder Test hier -- vorher gab es weder das
Kennzeichen noch die Route (404).
"""

from nebenkostenfix.abrechnung_version import REGEL_VERSION
from nebenkostenfix.models import BillingReportVersion, MeterReading, TenantBillingReport, db
from tests.test_versionierung import _bericht, _finalisiere, _welt


def _vorschau(client, bericht_id):
    antwort = client.get(f'/api/billing/reports/{bericht_id}/korrektur/vorschau')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    return antwort.get_json()


def test_vorschau_zeigt_alt_und_neu_und_speichert_nichts(auth_client, app_ctx):
    mieter_id, _, lese_id = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    db.session.get(MeterReading, lese_id).value = 800.0
    db.session.commit()

    vorschau = _vorschau(auth_client, bericht_id)

    assert vorschau['unveraendert'] is False
    assert vorschau['positionen'] == [
        {'kostenart': 'Wasserversorgung', 'alt': '1200.00', 'neu': '1066.67'}]
    assert vorschau['summe'] == {'alt': '1200.00', 'neu': '1066.67'}
    assert vorschau['vorauszahlungen'] == {'alt': '300.00', 'neu': '300.00'}
    assert vorschau['saldo'] == {'alt': '900.00', 'neu': '766.67'}
    # Nichts angelegt, die gültige Version trägt die alten Zahlen
    assert BillingReportVersion.query.filter_by(report_id=bericht_id).count() == 1
    assert _bericht(bericht_id).aktuelle_version.ergebnis['total_amount'] == '1200.00'


def test_ohne_aenderung_ist_die_vorschau_unveraendert(auth_client, app_ctx):
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id

    vorschau = _vorschau(auth_client, bericht_id)

    assert vorschau['unveraendert'] is True
    assert vorschau['veraltet'] is False
    assert vorschau['summe'] == {'alt': '1200.00', 'neu': '1200.00'}


def test_altbestand_ohne_version_hat_kein_alt(auth_client, app_ctx):
    from datetime import date
    from nebenkostenfix.frist import frist_ende
    mieter_id, _, _ = _welt(app_ctx)
    bericht = TenantBillingReport(tenant_id=mieter_id, start_date=date(2025, 1, 1),
                                  end_date=date(2025, 12, 31),
                                  frist_ende=frist_ende(date(2025, 12, 31)))
    db.session.add(bericht)
    db.session.commit()

    vorschau = _vorschau(auth_client, bericht.id)

    assert vorschau['unveraendert'] is False
    assert vorschau['veraltet'] is False
    assert vorschau['summe'] == {'alt': None, 'neu': '1200.00'}
    assert vorschau['positionen'] == [
        {'kostenart': 'Wasserversorgung', 'alt': None, 'neu': '1200.00'}]


def test_unbekannte_abrechnung_ist_404(auth_client, app_ctx):
    assert auth_client.get('/api/billing/reports/999/korrektur/vorschau').status_code == 404


def _kennzeichen(client, bericht_id):
    [eintrag] = [r for r in client.get('/api/billing/reports').get_json()
                 if r['id'] == bericht_id]
    details = client.get(f'/api/billing/reports/{bericht_id}/details').get_json()
    return eintrag['veraltet'], details['veraltet']


def test_aelterer_regelstand_ist_veraltet(auth_client, app_ctx):
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    assert _kennzeichen(auth_client, bericht_id) == (False, False)

    version = _bericht(bericht_id).aktuelle_version
    assert version.regel_version == REGEL_VERSION
    version.regel_version = '2026-08-28'
    db.session.commit()

    assert _kennzeichen(auth_client, bericht_id) == (True, True)
    assert _vorschau(auth_client, bericht_id)['veraltet'] is True


def test_die_korrektur_hebt_den_regelstand(auth_client, app_ctx):
    """Nach der Korrektur trägt die gültige Version den heutigen Regelstand."""
    mieter_id, _, lese_id = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    _bericht(bericht_id).aktuelle_version.regel_version = '2026-08-28'
    db.session.get(MeterReading, lese_id).value = 800.0
    db.session.commit()

    assert auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur').status_code == 201

    assert _kennzeichen(auth_client, bericht_id) == (False, False)
