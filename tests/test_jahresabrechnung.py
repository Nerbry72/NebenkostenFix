"""NK-160: der Stand eines Abrechnungsjahres für den Assistenten.

Am Beispielhaus (NK-159): das Vorjahr ist vollständig erfasst und für Anna
schon festgesetzt. Geprüft wird, was die Schritte 2, 3 und 5 zeigen --
gerechnet wird im Assistenten über die vorhandenen Routen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix import beispielimmobilie as demo


@pytest.fixture
def haus(auth_client):
    antwort = auth_client.post('/api/analytics/beispiel-immobilie')
    assert antwort.status_code == 201
    yield antwort.get_json()['property_id']
    demo.entfernen()


def _stand(client, haus, jahr):
    return client.get(f'/api/jahresabrechnung?property_id={haus}&jahr={jahr}')


def test_kostenarten_mit_vorjahr_und_luecken(auth_client, haus):
    from nebenkostenfix.models import CostCategory, CostInvoice, db
    jahr = date.today().year - 1
    # Im Vorvorjahr gab es eine Hauswart-Rechnung, im Jahr nicht: fehlt.
    hauswart = CostCategory.query.filter_by(name='Hauswart').one()
    db.session.add(CostInvoice(property_id=haus, category_id=hauswart.id, amount=Decimal('300'),
                               start_date=date(jahr - 1, 1, 1), end_date=date(jahr - 1, 12, 31)))
    db.session.commit()
    stand = _stand(auth_client, haus, jahr).get_json()
    arten = {k['name']: k for k in stand['kostenarten']}
    assert arten['Grundsteuer']['zustand'] == 'erfasst' and arten['Grundsteuer']['summe'] == 460.0
    assert arten['Grundsteuer']['summe_vorjahr'] is None
    assert arten['Hauswart']['zustand'] == 'fehlt' and arten['Hauswart']['summe_vorjahr'] == 300.0
    assert arten['Wasserversorgung']['zustand'] == 'offen'  # üblich, aber nie erfasst
    assert 'Aufzug' not in arten


def test_mieter_mit_zeitraum_und_vorhandener_abrechnung(auth_client, haus):
    jahr = date.today().year - 1
    stand = _stand(auth_client, haus, jahr).get_json()
    mieter = {m['name']: m for m in stand['mieter']}
    anna = mieter['Anna Beispiel']
    assert (anna['von'], anna['bis']) == (f'{jahr}-01-01', f'{jahr}-12-31')
    assert anna['abrechnung_id'] and anna['detailliert']
    assert stand['frist_ende'] == f'{jahr + 1}-12-31'


def test_ablesungen_zum_stichtag_und_beim_wechsel(auth_client, haus):
    from nebenkostenfix.models import Apartment, CostCategory, Meter, MeterReading, Tenant, db
    jahr = date.today().year - 1
    ben = Tenant.query.filter_by(name='Ben Beispiel').one()
    ben.move_in_date = date(jahr, 3, 1)          # ein Wechsel im Jahr
    og = Apartment.query.get(ben.apartment_id)
    wasser = CostCategory.query.filter_by(name='Wasserversorgung').one()
    og_zaehler = Meter(property_id=haus, category_id=wasser.id, apartment_id=og.id,
                       meter_number='H-OG-W', is_main_meter=False)
    db.session.add(og_zaehler)
    db.session.commit()

    stand = _stand(auth_client, haus, jahr).get_json()
    zeilen = {z['nummer']: z for z in stand['ablesungen']}
    assert set(zeilen) == {'H-Heiz-1', 'H-EG-1', 'H-WW-1', 'H-W-1', 'H-OG-W'}
    assert zeilen['H-WW-1']['letzte'] is None and not zeilen['H-WW-1']['stichtag_ok']
    assert zeilen['H-OG-W']['wechsel_fehlen'] == [f'{jahr}-03-01']
    assert zeilen['H-EG-1']['wechsel_fehlen'] == []   # andere Wohnung
    assert zeilen['H-OG-W']['wohnung'] == 'OG rechts'

    db.session.add(MeterReading(meter_id=og_zaehler.id, reading_date=date(jahr, 3, 2), value=1.0))
    db.session.add(MeterReading(meter_id=og_zaehler.id, reading_date=date(jahr, 12, 31), value=9.0))
    db.session.commit()
    zeile = {z['nummer']: z for z in _stand(auth_client, haus, jahr).get_json()['ablesungen']}['H-OG-W']
    assert zeile['wechsel_fehlen'] == [] and zeile['stichtag_ok'] is True


def test_ungueltige_anfragen(auth_client, haus):
    assert _stand(auth_client, haus, date.today().year + 1).status_code == 400
    assert _stand(auth_client, 99999, 2025).status_code == 400
    assert auth_client.get('/api/jahresabrechnung?jahr=2025').status_code == 400


def test_nur_angemeldet(anon_client):
    assert anon_client.get('/api/jahresabrechnung?property_id=1&jahr=2025').status_code == 401
