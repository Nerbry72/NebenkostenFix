"""NK-193: Der Praxisbestand einmal ganz durch die App.

Je Mieter der Weg, den der Vermieter geht: Zeitraumvorschlag, Vorschau,
Abrechnung festschreiben, PDF laden, Daten ändern, Korrektur, löschen und neu
festschreiben. Die Erwartungen sind festgeschrieben: Zeitraum, Summe je
Kostenart, Nachzahlung oder Guthaben, die Meldungen und was das PDF sagt.
Der Bestand steht in ``tests/praxis/bestand.py``, alle Werte sind erfunden.
"""

from __future__ import annotations

import base64
import re
import zlib
from collections import defaultdict
from datetime import date, datetime

import pytest

from nebenkostenfix import frist
from tests.praxis import bestand

GESCHAETZT = 'Stichtag nach Gradtagszahlen geschätzt'
PREISWARNUNG = 'W-ZAEHLER-PREIS-HOCHGERECHNET'

#: Je Mieter: Zeitraum, Summe je Kostenart, Gesamt, Vorauszahlung, Saldo,
#: Meldungen (Kennung, Inhalt), Teile der Vorschlagsgründe, Teile des PDFs.
#: NK-213: Haupt- und Wohnungszähler haben keinen gemeinsamen Ablesetag, der
#: Allgemeinverbrauch der Wasserrechnung WA-33 ist also ein Abschnitt und geht
#: nach Personentagen: 1562,90 € / 282,3 m³ · 93,2 m³ · 275/1460 = 97,18 €.
#: Bis dahin schnitt F-122 am Einzug von Mieter 3 und schätzte den Hauptzähler.
ERWARTUNG = {
    'Mieter 1': dict(
        zeitraum=('2033-04-01', '2033-12-31'),
        kosten={'Wasserversorgung': 466.33, 'Heizung': 1269.11,
                'Beleuchtung (Allgemeinstrom)': 477.66, 'Sach- und Haftpflichtversicherung': 211.39},
        gesamt=2424.49, voraus=1305.0, saldo=1119.49,
        meldungen=[(PREISWARNUNG, 'HS-1')],
        gruende=['Abgerechnet ist bis 31.03.2033', 'WMZ-EG', 'Beleuchtung (Allgemeinstrom)'],
        pdf=['01.04.2033 bis 31.12.2033', 'Ihre Nachzahlung', 'WA-33', 'HZ-33', 'ST-33', 'VG-33',
             f'3371.9 kWh, {GESCHAETZT}']),
    'Mieter 2': dict(
        zeitraum=('2033-04-01', '2033-12-31'),
        kosten={'Wasserversorgung': 281.31, 'Heizung': 0.0,
                'Beleuchtung (Allgemeinstrom)': 26.37, 'Sach- und Haftpflichtversicherung': 116.78},
        gesamt=424.46, voraus=765.0, saldo=-340.54,
        meldungen=[(PREISWARNUNG, 'HS-1')],
        gruende=['Abgerechnet ist bis 31.03.2033', 'Beleuchtung (Allgemeinstrom)'],
        pdf=['01.04.2033 bis 31.12.2033', 'Ihr Guthaben', 'WA-33', 'VG-33']),
    'Mieter 3': dict(
        zeitraum=('2033-10-01', '2033-12-31'),
        kosten={'Wasserversorgung': 107.04, 'Heizung': 580.51,
                'Beleuchtung (Allgemeinstrom)': 109.29, 'Sach- und Haftpflichtversicherung': 57.37},
        gesamt=854.21, voraus=330.0, saldo=524.21,
        meldungen=[(PREISWARNUNG, 'HS-1')],
        gruende=['WMZ-W3', 'Den Rest bis zum Auszug (01.01.2034–31.07.2034)'],
        pdf=['01.10.2033 bis 31.12.2033', 'Ihre Nachzahlung', GESCHAETZT]),
    'Mieter 5': dict(
        zeitraum=('2033-01-01', '2033-12-31'),
        kosten={'Grundsteuer': 412.8, 'Straßenreinigung und Müllbeseitigung': 263.4},
        gesamt=676.2, voraus=720.0, saldo=-43.8,
        meldungen=[],
        gruende=[],
        pdf=['01.01.2033 bis 31.12.2033', 'Ihr Guthaben', 'GS-33', 'MU-33']),
}


def _pdftext(pdf: bytes) -> str:
    """Der Text eines reportlab-PDFs (ASCII85 + Flate), Umlaute aufgelöst und
    Zeilenumbrüche zu Leerzeichen, damit ein umbrochener Satz als einer zählt."""
    teile = []
    for roh in re.findall(rb'stream\r?\n(.*?)endstream', pdf, re.S):
        roh = roh.strip()
        if roh.endswith(b'~>'):
            roh = base64.a85decode(roh[:-2])
        try:
            roh = zlib.decompress(roh)
        except zlib.error:
            pass
        teile.append(roh.decode('latin-1'))
    stuecke = re.findall(r'\(((?:[^()\\]|\\.)*)\)\s*Tj', ' '.join(teile))
    text = ' '.join(' '.join(stuecke).split())
    text = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), text)
    text = re.sub(r'\\(.)', r'\1', text)
    return text.encode('latin-1').decode('cp1252')


@pytest.fixture
def praxis(auth_client, app_ctx, monkeypatch):
    """Der Bestand am Tag ``HEUTE``. Das Druckdatum im PDF bleibt das echte."""
    heute = bestand.HEUTE

    class D(date):
        @classmethod
        def today(cls):
            return heute

    class DT(datetime):
        @classmethod
        def today(cls):
            return datetime(heute.year, heute.month, heute.day, 10)

    monkeypatch.setattr(app_ctx, 'date', D)
    monkeypatch.setattr(app_ctx, 'datetime', DT)
    monkeypatch.setattr(frist, '_heute', lambda: heute)
    return auth_client, bestand.aufbauen()


def _euro(betrag: float) -> str:
    return f'{abs(betrag):,.2f}'.translate(str.maketrans(',.', '.,')) + ' €'


def _kosten(ergebnis) -> dict[str, float]:
    summe = defaultdict(float)
    for zeile in ergebnis['line_items']:
        summe[zeile['category']] += zeile['tenant_cost']
    return {k: round(v, 2) for k, v in summe.items()}


def _neuester_bericht(client, mieter_id) -> int:
    # Gleiche Zeit beim Anlegen: die neueste ist die mit der höchsten Nummer
    return max(r['id'] for r in client.get(f'/api/tenants/{mieter_id}/billing_reports').get_json())


@pytest.mark.parametrize('name', list(ERWARTUNG))
def test_mieter_ganz_durch_die_app(praxis, name):
    client, ids = praxis
    mid, soll = ids[name], ERWARTUNG[name]

    # 1. Der Vorschlag
    v = client.get(f'/api/tenants/{mid}/zeitraumvorschlag').get_json()
    assert (v['beginn'], v['ende']) == soll['zeitraum']
    for teil in soll['gruende']:
        assert any(teil in g for g in v['gruende']), (teil, v['gruende'])
    zeitraum = {'tenant_id': mid, 'start_date': v['beginn'], 'end_date': v['ende']}

    # 2. Die Vorschau
    antwort = client.post('/api/billing/generate', json=zeitraum)
    assert antwort.status_code == 200, antwort.get_json()
    e = antwort.get_json()
    assert _kosten(e) == soll['kosten']
    assert (e['total_amount'], e['prepaid_amount'], e['balance']) == (soll['gesamt'], soll['voraus'], soll['saldo'])
    assert len(e['warnings']) == len(soll['meldungen']), e['warnings']
    for (kennung, inhalt), w in zip(soll['meldungen'], e['warnings']):
        assert kennung in w and inhalt in w and 'Sie' in w

    # 3. Festschreiben und das PDF
    assert client.post('/api/billing/finalize', json=zeitraum).status_code == 201
    rid = _neuester_bericht(client, mid)
    pdf = client.get(f'/api/billing/reports/{rid}/download')
    assert pdf.status_code == 200
    text = _pdftext(pdf.data)
    for teil in [*soll['pdf'], _euro(soll['saldo'])]:
        assert teil in text, teil
    if GESCHAETZT not in ' '.join(soll['pdf']):
        assert GESCHAETZT not in text

    # 4. Eine Zahlung kommt nach, die Korrektur trägt sie
    zahlung = {'tenant_id': mid, 'amount': 50, 'type': 'Nebenkostenvorauszahlung',
               'payment_date': v['ende']}
    assert client.post('/api/payments', json=zahlung).status_code in (200, 201)
    k = client.post(f'/api/billing/reports/{rid}/korrektur')
    assert k.status_code == 201, k.get_json()
    assert k.get_json()['versionsnummer'] == 2
    korrigiert = _pdftext(client.get(f'/api/billing/reports/{rid}/download').data)
    assert _euro(soll['saldo'] - 50) in korrigiert

    # 5. Löschen und neu festschreiben
    assert client.delete(f'/api/billing/reports/{rid}').status_code == 200
    assert rid not in [r['id'] for r in client.get(f'/api/tenants/{mid}/billing_reports').get_json()]
    assert client.post('/api/billing/finalize', json=zeitraum).status_code == 201


def test_ohne_profil_und_rechnung_kein_vorschlag(praxis):
    client, ids = praxis
    v = client.get(f"/api/tenants/{ids['Mieter 4']}/zeitraumvorschlag").get_json()
    assert (v['beginn'], v['ende']) == (None, None)
    assert v['gruende']



def test_belegliste_zeigt_bei_zaehlern_keinen_tagesanteil(praxis):
    """Mieter 1 zahlt die Heizung nach Wärmezähler, am Stichtag nach
    Gradtagen geschätzt. Der lineare Tagesanteil der Rechnung ist nicht, was
    angesetzt wurde -- die ausführliche Belegliste sagt „nach Zähler“."""
    from decimal import Decimal
    from nebenkostenfix.pdf_generator import PDFGenerator
    client, ids = praxis
    mid = ids['Mieter 1']
    v = client.get(f'/api/tenants/{mid}/zeitraumvorschlag').get_json()
    import json
    e = json.loads(client.post('/api/billing/generate', json={
        'tenant_id': mid, 'start_date': v['beginn'], 'end_date': v['ende']}).data,
        parse_float=Decimal)
    heizung = next(z for z in e['line_items'] if z['category'] == 'Heizung')
    linear = f"{heizung['prorated_amount']:.2f}".replace('.', ',')
    pdf = PDFGenerator(property_name='Haus', apartment_name='EG', tenant_name='Mieter 1',
                       start_date=v['beginn'], end_date=v['ende'], detailliert=True,
                       ).generate(e['line_items'], e['total_amount'], Decimal('0'))
    text = _pdftext(pdf).replace(' ', '')  # die schmale Spalte bricht um
    assert 'nachZähler' in text
    assert linear not in text, linear
