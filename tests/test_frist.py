"""NK-054: die Fristen des § 556 Abs. 3 BGB, an ihren einen Ort geprueft.

Zwei Fristen haengen an derselben Abrechnung. Die Abrechnungsfrist des
Vermieters (Az-Ende + 12 Monate) entscheidet darueber, ob eine Nachforderung
noch geltend gemacht werden kann; die Einwendungsfrist des Mieters (Zugang
+ 12 Monate) ist informativ. Beide enden mit einem Kalendertag, nicht mit
einem Grenzdatum -- darum unterscheiden sie sich am Schalttag sichtbar von
``zeitraum.ein_jahr_nach``.

Die Proben hier halten die drei Ebenen fest, auf denen die Frist lebt:

1. das Modul ``frist`` (Arithmetik und Warnungen),
2. die Vorpruefung (Kacheln fuer Zeitraum-Überlappung, Luecke und Frist),
3. die Routen (Erzeugung mit Flag und Warnung, Festsetzung mit
   gespeichertem Fristende, Zustellung nachtraeglich).
"""

from __future__ import annotations

import ast
import pathlib
from datetime import date, timedelta

import pytest

import frist
from frist import (KENNUNG_NAHT, KENNUNG_VERPASST, einwendungsfrist,
                   frist_ende, frist_status)
from zeitraum import ein_jahr_nach

WURZEL = pathlib.Path(__file__).resolve().parents[1]


# --- Das Modul: Fristende als Kalendertag -----------------------------------


def test_frist_ende_ist_der_gleiche_tag_im_folgejahr():
    assert frist_ende(date(2025, 12, 31)) == date(2026, 12, 31)
    assert frist_ende(date(2025, 1, 31)) == date(2026, 1, 31)
    assert frist_ende(date(2025, 7, 15)) == date(2026, 7, 15)


def test_der_schalttag_endet_mit_dem_letzten_tag_des_monats():
    """§ 188 Abs. 2 BGB: der Zielmonat hat den Tag nicht -- Fristende ist
    der letzte Tag des Monats. Der 29.02.2024 fuehrt zum 28.02.2025."""
    assert frist_ende(date(2024, 2, 29)) == date(2025, 2, 28)
    # Der 28.02. eines normalen Jahres bleibt der 28.02.
    assert frist_ende(date(2024, 2, 28)) == date(2025, 2, 28)


def test_frist_ende_und_ein_jahr_nach_sind_absichtsvoll_verschieden():
    """Grenzdatum gegen Kalendertag: beide rechnen "zwoelf Monate", und
    genau am Schalttag liegen sie einen Tag auseinander. Wer die beiden
    vereinheitlicht, verschiebt eine der beiden Fristen -- dieser Test
    soll das rot machen lassen."""
    # ein_jahr_nach ist die GRENZE (halboffen): der 28.02.2025 zaehlt mit.
    assert ein_jahr_nach(date(2024, 2, 29)) == date(2025, 3, 1)
    # frist_ende ist der letzte gueltige TAG selbst.
    assert frist_ende(date(2024, 2, 29)) == date(2025, 2, 28)


def test_einwendungsfrist_laeuft_ab_dem_zugang():
    """Zwoelf Monate nach dem Zugang, als Kalendertag (R-FRIST-03).

    § 556 Abs. 3 BGB: der Mieter muss bis zum Ablauf des zwoelften Monats
    nach Zugang der Abrechnung Einwendungen mitteilen. Informativ -- die
    Zahl wirkt nicht auf die Rechnung, sie steht nur auf dem Blatt.
    """
    assert einwendungsfrist(date(2026, 1, 15)) == date(2027, 1, 15)
    assert einwendungsfrist(date(2024, 2, 29)) == date(2025, 2, 28)


# --- Das Modul: die Warnungen ------------------------------------------------


def test_ueberschrittene_frist_warnt_mit_ihrer_kennung():
    """AK: AZ-Ende 31.12.2025, Erstellung am 02.01.2027."""
    stand = frist_status(date(2025, 12, 31), date(2027, 1, 2))
    assert stand['ueberschritten'] is True
    assert stand['frist_ende'] == date(2026, 12, 31)
    assert stand['warnung'].startswith(KENNUNG_VERPASST)
    assert 'trotzdem' in stand['warnung']


def test_am_letzten_tag_ist_die_abrechnung_noch_rechtzeitig():
    """"Bis zum Ablauf" des Fristendes: am 31.12.2026 selbst zaehlt der
    Tag noch. Die Warnung sagt "heute", nicht "ueberschritten"."""
    stand = frist_status(date(2025, 12, 31), date(2026, 12, 31))
    assert stand['ueberschritten'] is False
    assert 'heute' in stand['warnung']


def test_frist_laueft_in_sechzehn_tagen_ab():
    """AK: AZ-Ende 31.12.2025, Erstellung am 15.12.2026."""
    stand = frist_status(date(2025, 12, 31), date(2026, 12, 15))
    assert stand['ueberschritten'] is False
    assert 'in 16 Tagen' in stand['warnung']


def test_mit_zeit_keine_warnung():
    assert frist_status(date(2025, 12, 31), date(2026, 6, 30))['warnung'] is None


def test_die_naht_warnt_ab_dreissig_tagen():
    """29 Tage vor dem Ende: Warnung. 30 Tage vor dem Ende: noch Ruhe."""
    assert frist_status(date(2025, 12, 31), date(2026, 12, 2))['warnung'] is not None
    assert frist_status(date(2025, 12, 31), date(2026, 12, 1))['warnung'] is None
    assert frist.WARN_TAGE == 30


def test_ohne_heute_wird_der_aktuelle_tag_genommen(monkeypatch):
    """Die Routen rechnen gegen den echten Tag; die Probe tauscht ihn."""
    monkeypatch.setattr(frist, '_heute', lambda: date(2027, 1, 2))
    assert frist_status(date(2025, 12, 31))['ueberschritten'] is True
    monkeypatch.setattr(frist, '_heute', lambda: date(2026, 6, 30))
    assert frist_status(date(2025, 12, 31))['warnung'] is None


def test_modul_haengt_an_nichts_als_der_zeit():
    """Kein ORM, kein Rechenkern: die Frist ist reine Arithmetik."""
    baum = ast.parse((WURZEL / 'frist.py').read_text(encoding='utf-8'))

    importiert = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            importiert.update(a.name.split('.')[0] for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            importiert.add(knoten.module.split('.')[0])

    assert importiert <= {'calendar', 'datetime'}, \
        f'frist.py zieht fremde Module herein: {importiert}'


# --- Die Vorpruefung: Zeitraum und Frist als Kacheln -------------------------

from billing_factories import apt, house, tenant  # noqa: E402


def _mieter(app_ctx, name='Fristmietern'):
    prop = house(name='Fristhaus')
    wng = apt(prop, 'Frist-EG', 60.0)
    return tenant(wng, name, move_in=date(2024, 1, 1))


def _report(modelle, mieter_id, start, ende, kategorie_id=None):
    from models import TenantBillingReport, db
    report = TenantBillingReport(
        tenant_id=mieter_id, start_date=start, end_date=ende,
        frist_ende=frist_ende(ende),
    )
    db.session.add(report)
    db.session.flush()
    if kategorie_id:
        from models import BillingReportCategory
        db.session.add(BillingReportCategory(
            report_id=report.id, category_id=kategorie_id,
            start_date=start, end_date=ende))
        db.session.commit()
    return report


def test_vorpruefung_warnt_bei_ueberlappenden_zeitraeumen(auth_client, app_ctx):
    """AK: Zwei Abrechnungen desselben Mieters mit überlappenden
    Zeiträumen erzeugen eine Warnung -- hier als Kachel, die blockiert,
    weil die Erzeugung denselben Antrag mit 400 abweisen wird."""
    from models import db

    mieter = _mieter(app_ctx)
    _report(None, mieter.id, date(2025, 1, 1), date(2025, 12, 31))

    antwort = auth_client.post('/api/billing/preflight', json={
        'tenant_id': mieter.id,
        'start_date': '2025-06-01', 'end_date': '2025-12-31'})
    assert antwort.status_code == 200
    kacheln = antwort.get_json()['checks']
    zeitraum = [k for k in kacheln if k['category'] == 'Zeitraum']
    assert len(zeitraum) == 1
    assert zeitraum[0]['blocking'] is True
    assert 'überschneidet sich' in zeitraum[0]['message']
    assert '01.01.2025' in zeitraum[0]['message']
    db.session.remove()


def test_erzeugung_weist_die_ueberlappung_ab(auth_client, app_ctx):
    """Dieselbe Regel an der Erzeugung: keine doppelte Abrechnung
    derselben Tage. Der Vermieter kann die Vorpruefung ueberspringen --
    die Absage darf er trotzdem nicht verfehlen (NK-096)."""
    mieter = _mieter(app_ctx)
    _report(None, mieter.id, date(2025, 1, 1), date(2025, 12, 31))

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id,
        'start_date': '2025-06-01', 'end_date': '2025-12-31'})
    assert antwort.status_code == 400
    assert 'überschneidet sich' in antwort.get_json()['error']


def test_an_andere_zeitraeume_stoesst_keine_kachel_an(auth_client, app_ctx):
    """Ein nahtloser Anschluss ist keine Luecke und keine Ueberschneidung."""
    mieter = _mieter(app_ctx)
    _report(None, mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    antwort = auth_client.post('/api/billing/preflight', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    kacheln = [k for k in antwort.get_json()['checks']
               if k['category'] == 'Zeitraum']
    assert kacheln == []


def test_vorpruefung_warnt_bei_einer_luecke(auth_client, app_ctx):
    """Vier Monate unbillt zwischen zwei Abrechnungen: Warnung, aber die
    Software sagt nicht ab -- die Tage duerfen spaeter abgerechnet werden."""
    mieter = _mieter(app_ctx)
    _report(None, mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    antwort = auth_client.post('/api/billing/preflight', json={
        'tenant_id': mieter.id,
        'start_date': '2025-05-01', 'end_date': '2025-12-31'})
    kacheln = [k for k in antwort.get_json()['checks']
               if k['category'] == 'Zeitraum']
    assert len(kacheln) == 1
    assert kacheln[0]['blocking'] is False
    assert '120 Tage' in kacheln[0]['message']  # Januar bis April 2025
    assert '31.12.2024' in kacheln[0]['message']


def test_vorpruefung_warnt_bei_ueberschrittener_frist(auth_client, app_ctx, monkeypatch):
    """Die Fristkachel erscheint nur, wenn es etwas zu sagen gibt."""
    monkeypatch.setattr(frist, '_heute', lambda: date(2027, 1, 2))
    mieter = _mieter(app_ctx)

    antwort = auth_client.post('/api/billing/preflight', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    assert antwort.status_code == 200
    kacheln = [k for k in antwort.get_json()['checks']
               if k['category'] == 'Frist']
    assert len(kacheln) == 1
    assert kacheln[0]['blocking'] is False
    assert kacheln[0]['message'].startswith(KENNUNG_VERPASST)


def test_vorpruefung_schweigt_in_der_fristfruehe(auth_client, app_ctx, monkeypatch):
    monkeypatch.setattr(frist, '_heute', lambda: date(2026, 3, 1))
    mieter = _mieter(app_ctx)

    antwort = auth_client.post('/api/billing/preflight', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    kacheln = [k for k in antwort.get_json()['checks']
               if k['category'] == 'Frist']
    assert kacheln == []


# --- Die Erzeugung: Flag, Warnung, Fristende im Ergebnis ---------------------


def test_erzeugung_nach_der_frist_traegt_flag_und_warnung(auth_client, app_ctx, monkeypatch):
    """AK: AZ-Ende 31.12.2025, Erstellung 02.01.2027 -> Abrechnung enthält
    Fristwarnung, Flag frist_ueberschritten = true. Erzeugt wird trotzdem."""
    monkeypatch.setattr(frist, '_heute', lambda: date(2027, 1, 2))
    mieter = _mieter(app_ctx)

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    assert antwort.status_code == 200
    ergebnis = antwort.get_json()
    assert ergebnis['frist_ueberschritten'] is True
    assert ergebnis['frist_ende'] == '2026-12-31'
    warnungen = [w for w in ergebnis['warnings'] if w.startswith(KENNUNG_VERPASST)]
    assert len(warnungen) == 1


def test_erzeugung_in_der_frist_hat_kein_flag_und_keine_warnung(
        auth_client, app_ctx, monkeypatch):
    monkeypatch.setattr(frist, '_heute', lambda: date(2026, 3, 1))
    mieter = _mieter(app_ctx)

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    ergebnis = antwort.get_json()
    assert ergebnis['frist_ueberschritten'] is False
    assert not [w for w in ergebnis['warnings']
                if w.startswith((KENNUNG_VERPASST, KENNUNG_NAHT))]


def test_erzeugung_naehrt_sich_der_frist(auth_client, app_ctx, monkeypatch):
    """15.12.2026: die Warnung aus der Vorpruefung ist dieselbe Textstelle
    wie die aus dem Modul (R-FRIST-02: "in weniger als 30 Tagen")."""
    monkeypatch.setattr(frist, '_heute', lambda: date(2026, 12, 15))
    mieter = _mieter(app_ctx)

    antwort = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    ergebnis = antwort.get_json()
    assert ergebnis['frist_ueberschritten'] is False
    assert [w for w in ergebnis['warnings'] if 'in 16 Tagen' in w]


def test_erzeugung_nimmt_366_tage_und_keinen_tag_mehr(auth_client, app_ctx, monkeypatch):
    """R-FRIST-01 an der Route: ein volles Schaltjahr bleibt ungeschaert,
    der 367. Tag wird auf die Jahresgrenze gestutzt (NK-041, gepinnt)."""
    monkeypatch.setattr(frist, '_heute', lambda: date(2026, 3, 1))
    mieter = _mieter(app_ctx)

    ok = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id,
        'start_date': '2024-01-01', 'end_date': '2024-12-31'})
    assert ok.status_code == 200
    assert ok.get_json()['end_date'] == '2024-12-31'

    zu_lang = auth_client.post('/api/billing/generate', json={
        'tenant_id': mieter.id,
        'start_date': '2024-01-01', 'end_date': '2025-01-01'})
    assert zu_lang.status_code == 200
    assert zu_lang.get_json()['end_date'] == '2024-12-31'


# --- Die Festsetzung: das Fristende wird geboren ------------------------------


def test_festsetzung_speichert_das_fristende(auth_client, app_ctx, monkeypatch):
    """Zu jeder Abrechnung wird ein Fristende berechnet und gespeichert --
    unabhaengig davon, ob die Frist noch laeuft (hier: laengst vorbei)."""
    monkeypatch.setattr(frist, '_heute', lambda: date(2027, 1, 2))
    from models import TenantBillingReport, db

    mieter = _mieter(app_ctx)
    antwort = auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter.id,
        'start_date': '2025-01-01', 'end_date': '2025-12-31'})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    report = TenantBillingReport.query.one()
    assert report.frist_ende == date(2026, 12, 31)
    assert report.zugestellt_am is None
    db.session.remove()


# --- Die Zustellung: das Datum, das nur der Vermieter kennt -------------------


def _bericht_mit_erstellung(app_ctx, erstellung):
    """Ein Bericht mit bekannten Eckdaten: Zeitraum 2025, erstellt am
    gegebenen Tag. Die Pruefungen an der Zustellung sind damit
    unabhängig vom echten heutigen Tag."""
    from models import TenantBillingReport, db

    mieter = _mieter(app_ctx)
    report = TenantBillingReport(
        tenant_id=mieter.id, start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31), frist_ende=frist_ende(date(2025, 12, 31)),
        created_at=erstellung)
    db.session.add(report)
    db.session.commit()
    return report


def test_zustellung_wird_gespeichert_und_nennt_die_einwendungsfrist(auth_client, app_ctx):
    """Die Antwort der Zustellungsroute nennt das Ende (R-FRIST-03)."""
    report = _bericht_mit_erstellung(app_ctx, date(2026, 1, 1))

    antwort = auth_client.post(f'/api/billing/reports/{report.id}/zustellung',
                               json={'zugestellt_am': '2026-01-15'})
    assert antwort.status_code == 200
    koerper = antwort.get_json()
    assert koerper['zugestellt_am'] == '2026-01-15'
    # Die Einwendungsfrist des Mieters: Zugang + 12 Monate (informativ).
    assert koerper['einwendungsfrist_ende'] == '2027-01-15'
    # Rechtzeitig zugestellt: keine Warnung (F-37).
    assert koerper['warnung'] is None


def test_zustellung_nach_der_frist_wird_gewarnt(auth_client, app_ctx):
    """F-37: der Zugang nach dem Fristende loest die Warnung aus.

    Die Abrechnung wurde rechtzeitig erzeugt, aber erst nach dem Ende der
    Nachforderungsfrist zugestellt -- die Erzeugung konnte das nicht
    wissen, erst der nachgetragene Zugang macht es sichtbar. Die Warnung
    ist informativ: die Zustellung wird trotzdem gespeichert.
    """
    # Zeitraum endet am 31.12.2024 -- die Frist endete am 31.12.2025.
    from billing_factories import apt, house, tenant
    from models import TenantBillingReport, db

    objekt = house(name='Zustellhaus')
    wohnung = apt(objekt, 'OG', 60.0)
    mieter = tenant(wohnung, 'Zustell-Mieter', move_in=date(2024, 1, 1))
    report = TenantBillingReport(
        tenant_id=mieter.id, start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31), frist_ende=frist_ende(date(2024, 12, 31)),
        created_at=date(2025, 1, 10))
    db.session.add(report)
    db.session.commit()

    antwort = auth_client.post(f'/api/billing/reports/{report.id}/zustellung',
                               json={'zugestellt_am': '2026-01-05'})
    assert antwort.status_code == 200
    koerper = antwort.get_json()
    assert koerper['zugestellt_am'] == '2026-01-05'
    assert koerper['warnung'].startswith('W-ZUSTELLUNG-NACHFRIST')
    assert '31.12.2025' in koerper['warnung']

    # Und der Datensatz traegt das Datum trotzdem:
    db.session.expunge_all()
    from models import TenantBillingReport as _bericht
    assert db.session.get(_bericht, report.id).zugestellt_am \
        == date(2026, 1, 5)


def test_zustellung_ohne_datum_wird_abgewiesen(auth_client, app_ctx):
    report = _bericht_mit_erstellung(app_ctx, date(2026, 1, 1))

    antwort = auth_client.post(f'/api/billing/reports/{report.id}/zustellung',
                               json={})
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == 'zugestellt_am'


def test_zustellung_in_der_zukunft_wird_abgewiesen(auth_client, app_ctx):
    """Die Software nimmt keine Zustellung vorweg, die noch nicht war."""
    report = _bericht_mit_erstellung(app_ctx, date(2026, 1, 1))
    morgen = date.today() + timedelta(days=1)

    antwort = auth_client.post(f'/api/billing/reports/{report.id}/zustellung',
                               json={'zugestellt_am': morgen.isoformat()})
    assert antwort.status_code == 400
    assert 'Zukunft' in antwort.get_json()['error']


def test_zustellung_vor_der_erstellung_wird_abgewiesen(auth_client, app_ctx):
    """Das PDF existiert erst seit created_at; davor kann nichts zugestellt
    worden sein -- nachgetragene Fehler fallen auf."""
    report = _bericht_mit_erstellung(app_ctx, date(2026, 2, 1))

    antwort = auth_client.post(f'/api/billing/reports/{report.id}/zustellung',
                               json={'zugestellt_am': '2026-01-15'})
    assert antwort.status_code == 400
    assert 'erstellt' in antwort.get_json()['error']


def test_zustellung_vor_dem_zeitraumende_wird_abgewiesen(auth_client, app_ctx):
    report = _bericht_mit_erstellung(app_ctx, date(2025, 12, 15))

    antwort = auth_client.post(f'/api/billing/reports/{report.id}/zustellung',
                               json={'zugestellt_am': '2025-12-31'})
    assert antwort.status_code == 400
    assert 'Abrechnungszeitraums' in antwort.get_json()['error']


def test_zustellung_einer_unbekannten_abrechnung_ist_eine_404(auth_client, app_ctx):
    antwort = auth_client.post('/api/billing/reports/999/zustellung',
                               json={'zugestellt_am': '2026-01-15'})
    assert antwort.status_code == 404


# --- F-37: die Zustellwarnung am Modul ---------------------------------------


def test_zustellwarnung_am_fristende_selbst_ist_still():
    """Am letzten Tag zugestellt reicht noch -- "bis zum Ablauf"."""
    assert frist.zustellwarnung(date(2026, 12, 31), date(2025, 12, 31)) is None


def test_zustellwarnung_einen_tag_nach_der_frist():
    """Ein Tag zu spaet: die Warnung nennt Kennung und Fristende."""
    warnung = frist.zustellwarnung(date(2027, 1, 1), date(2025, 12, 31))
    assert warnung.startswith('W-ZUSTELLUNG-NACHFRIST')
    assert '31.12.2026' in warnung
    assert '01.01.2027' in warnung


def test_zustellwarnung_schalttag():
    """Der 29.02. als Zeitraumende endet am 28.02. -- § 188 Abs. 2 BGB."""
    warnung = frist.zustellwarnung(date(2025, 3, 1), date(2024, 2, 29))
    assert '28.02.2025' in warnung
