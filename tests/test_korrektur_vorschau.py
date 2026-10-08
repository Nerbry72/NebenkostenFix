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


def test_gleiches_ergebnis_erledigt_den_hinweis(auth_client, app_ctx):
    """Rechnet der heutige Regelstand gleich, entfällt der Hinweis ohne neue Version.

    *Hätte den Fehler gefunden:* vorher blieb ``veraltet`` für immer stehen --
    die Korrektur lehnte eine unveränderte Abrechnung mit 400 ab.
    """
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    _bericht(bericht_id).aktuelle_version.regel_version = '2026-08-28'
    db.session.commit()
    assert _vorschau(auth_client, bericht_id)['unveraendert'] is True

    antwort = auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur')

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['unveraendert'] is True
    assert _kennzeichen(auth_client, bericht_id) == (False, False)
    assert BillingReportVersion.query.filter_by(report_id=bericht_id).count() == 1
    # Ein zweiter Versuch ist wieder die bloße Kopie und wird abgelehnt.
    assert auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur').status_code == 400


# --- NK-229: Richtung, Frist und was sich geändert hat (R-DOC-03) -------------


def test_weniger_saldo_ist_zugunsten_des_mieters(auth_client, app_ctx):
    mieter_id, _, lese_id = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    db.session.get(MeterReading, lese_id).value = 800.0
    db.session.commit()

    vorschau = _vorschau(auth_client, bericht_id)

    assert vorschau['richtung'] == 'zugunsten'
    assert vorschau['frist_warnung'] is None


def test_mehr_saldo_ist_zulasten_des_mieters(auth_client, app_ctx):
    mieter_id, _, lese_id = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    db.session.get(MeterReading, lese_id).value = 1200.0
    db.session.commit()

    vorschau = _vorschau(auth_client, bericht_id)

    assert vorschau['richtung'] == 'zulasten'
    # Das Fristende 31.12.2026 liegt noch vor uns: keine Warnung.
    assert vorschau['frist_warnung'] is None


def test_zulasten_nach_fristende_warnt(auth_client, app_ctx):
    from datetime import date
    mieter_id, _, lese_id = _welt(app_ctx)
    bericht = _finalisiere(auth_client, mieter_id)
    bericht.frist_ende = date(2026, 1, 1)
    db.session.get(MeterReading, lese_id).value = 1200.0
    db.session.commit()

    warnung = _vorschau(auth_client, bericht.id)['frist_warnung']

    assert '01.01.2026' in warnung and '§ 556 Abs. 3' in warnung
    # Zugunsten des Mieters ist auch nach Fristende frei.
    db.session.get(MeterReading, lese_id).value = 800.0
    db.session.commit()
    assert _vorschau(auth_client, bericht.id)['frist_warnung'] is None


def test_gleicher_saldo_hat_keine_richtung(auth_client, app_ctx):
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    vorschau = _vorschau(auth_client, bericht_id)
    assert (vorschau['richtung'], vorschau['frist_warnung']) == (None, None)


def test_jeder_regelstand_erklaert_seine_aenderung():
    """Wer REGEL_VERSION hebt, sagt dem Vermieter auch, was sich geändert hat."""
    from nebenkostenfix.abrechnung_version import REGEL_AENDERUNGEN
    assert REGEL_VERSION in REGEL_AENDERUNGEN
    assert all(len(text) > 40 for text in REGEL_AENDERUNGEN.values())


def test_veraltete_abrechnung_nennt_die_aenderungen_seitdem(auth_client, app_ctx):
    from nebenkostenfix.abrechnung_version import REGEL_AENDERUNGEN
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id

    def aenderungen():
        [eintrag] = [r for r in auth_client.get('/api/billing/reports').get_json()
                     if r['id'] == bericht_id]
        details = auth_client.get(f'/api/billing/reports/{bericht_id}/details').get_json()
        return eintrag['regelstand_aenderungen'], details['regelstand_aenderungen']

    assert aenderungen() == ([], [])
    _bericht(bericht_id).aktuelle_version.regel_version = '2026-08-28'
    db.session.commit()
    erwartet = [REGEL_AENDERUNGEN[REGEL_VERSION]]
    assert aenderungen() == (erwartet, erwartet)


# --- NK-235: geänderte Texte allein sind keine Änderung -----------------------


def _alte_texte(wert):
    """Das Ergebnis, wie es eine ältere Fassung beschrieben hätte."""
    if isinstance(wert, dict):
        return {k: (f'{v} (alter Text)' if k == 'description' else
                    [f'{s} qm' for s in v] if k == 'rechenweg' else _alte_texte(v))
                for k, v in wert.items()}
    if isinstance(wert, list):
        return [_alte_texte(v) for v in wert]
    return wert


def test_nur_andere_texte_sind_unveraendert(auth_client, app_ctx):
    """*Hätte den Fehler gefunden:* nach dem Update von 0.12 auf 0.13 galt jede
    alte Abrechnung als verändert, weil Beschreibung und Rechenweg „m²“ und
    deutsche Zahlen bekamen; der Hinweis auf den älteren Regelstand ließ sich
    nur mit einer Korrektur ohne neue Zahlen entfernen."""
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    version = _bericht(bericht_id).aktuelle_version
    version.ergebnis = _alte_texte(version.ergebnis)
    version.regel_version = '2026-08-28'
    db.session.commit()
    assert version.ergebnis['line_items'][0]['description'].endswith('(alter Text)')

    assert _vorschau(auth_client, bericht_id)['unveraendert'] is True
    antwort = auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['unveraendert'] is True
    assert BillingReportVersion.query.filter_by(report_id=bericht_id).count() == 1
