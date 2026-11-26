"""§ 2 HeizkostenV: Prozentumlage erst nach ausdrücklicher Bestätigung."""
from dataclasses import replace
from decimal import Decimal

import pytest

from nebenkostenfix.models import TenantCostProfile, db
from nebenkostenfix.rechenkern import BillingDataError, Kategorie, rechne
from tests.billing_factories import apt, house, tenant
from tests.test_gutschrift_umlage import _rechnung, _welt


@pytest.fixture
def heizprofil(auth_client):
    from nebenkostenfix.models import CostCategory
    mieter = tenant(apt(house(), 'Wohnung', 60), 'Mieter')
    kostenart = CostCategory.query.filter_by(betrkv_nr=4).first()
    return mieter, kostenart


def _profil(kat, bestaetigt=None):
    wert = {'billing_type': 'prozent', 'percentage': '30.25'}
    if bestaetigt is not None:
        wert['heizkostenv_bestaetigt'] = bestaetigt
    return {str(kat.id): wert}


@pytest.mark.parametrize('bestaetigt', [None, False, 'true', 1])
def test_ohne_aktive_bestaetigung_bleibt_altes_profil(auth_client, heizprofil, bestaetigt):
    mieter, kat = heizprofil
    url = f'/api/tenants/{mieter.id}/profiles'
    assert auth_client.post(url, json={str(kat.id): 'qm'}).status_code == 200
    antwort = auth_client.post(url, json=_profil(kat, bestaetigt))
    assert antwort.status_code == 400
    assert 'Heizkosten' in antwort.get_json()['error']
    assert auth_client.get(url).get_json() == {str(kat.id): 'qm'}


@pytest.mark.parametrize('nummer', [4, 5, 6])
def test_bestaetigung_wird_gespeichert_geladen_und_zurueckgesetzt(auth_client, heizprofil, nummer):
    from nebenkostenfix.models import CostCategory
    from nebenkostenfix.abrechnungsdaten import lade_vorgang
    mieter, _ = heizprofil
    kat = CostCategory.query.filter_by(betrkv_nr=nummer).first()
    url = f'/api/tenants/{mieter.id}/profiles'
    profil = _profil(kat, True)
    assert auth_client.post(url, json=profil).status_code == 200
    assert auth_client.get(url).get_json() == profil
    assert TenantCostProfile.query.filter_by(tenant_id=mieter.id).one().heizkostenv_bestaetigt is True
    vorgang = lade_vorgang(mieter.id, '2024-01-01', '2024-12-31')
    assert (mieter.id, kat.id) in vorgang.heizkostenv_bestaetigungen
    assert auth_client.post(url, json={str(kat.id): 'qm'}).status_code == 200
    assert TenantCostProfile.query.filter_by(tenant_id=mieter.id).one().heizkostenv_bestaetigt is False
    assert auth_client.post(url, json=_profil(kat)).status_code == 400


def test_kategorien_liefern_hinweis_auch_bei_umbenannten_heizkosten(auth_client, heizprofil):
    _, kat = heizprofil
    kat.name = 'Fernwärme vom Stadtwerk'
    db.session.commit()
    kategorien = auth_client.get('/api/categories').get_json()
    assert next(k for k in kategorien if k['id'] == kat.id)['heizkostenv_hinweis'] is True
    assert next(k for k in kategorien if k['betrkv_nr'] == 1)['heizkostenv_hinweis'] is False


def _heizwelt():
    kat = Kategorie(1, 'Heizung', False, 4)
    welt = _welt([_rechnung(1, kat, '1000', 'H-1')])
    return replace(welt, profile={1: 'prozent'}, prozentanteile={1: Decimal('30')})


def test_importiertes_heizprofil_ohne_bestaetigung_blockiert_abrechnung():
    with pytest.raises(BillingDataError, match='§ 2 HeizkostenV'):
        rechne(_heizwelt())


def test_bestaetigte_prozentumlage_nennt_nicht_mehr_wohnflaeche():
    ergebnis = rechne(replace(_heizwelt(), heizkostenv_bestaetigungen=frozenset({(1, 1)})))
    assert ergebnis['total_amount'] == Decimal('300.00')
    warnung = next(w for w in ergebnis['warnings'] if isinstance(w, str)
                   and 'W-HEIZKOSTEN-OHNE-ZUORDNUNG' in w)
    assert 'vereinbarten Prozentsatz' in warnung
    assert 'nach Wohnfläche' not in warnung


def test_unbestaetigtes_nachbarprofil_wird_ebenfalls_abgelehnt():
    welt = replace(_heizwelt(), heizkostenv_bestaetigungen=frozenset({(1, 1)}),
                   profile_der_immobilie={1: {1: 'prozent'}, 2: {1: 'prozent'}},
                   prozentanteile_der_immobilie={1: {1: Decimal('30')}, 2: {1: Decimal('70')}})
    with pytest.raises(BillingDataError, match='§ 2 HeizkostenV'):
        rechne(welt)


@pytest.mark.parametrize('name, nummer, erwartet', [
    ('Warmwasser', None, True), ('Heizung', None, True),
    ('Fernwärme', 4, True), ('Warmwasser', 17, False), ('Wasser', 2, False)])
def test_erkennung_nutzt_katalognummer_vor_altbestandsname(name, nummer, erwartet):
    from nebenkostenfix.betrkv import ist_heizkosten
    assert ist_heizkosten(name, nummer) is erwartet


@pytest.mark.parametrize('nummer', [4, 5])
@pytest.mark.parametrize('bestaetigt', [False, True])
def test_ignorierte_anlagenrechnung_hat_keinen_prozentrest(nummer, bestaetigt):
    """Nachbarprofile dürfen weder einen Prozentrest noch eine Sperre erzeugen."""
    from nebenkostenfix.rechenkern import Heizungsanlage

    kat = Kategorie(1, 'Heizung' if nummer == 4 else 'Warmwasser', False, nummer)
    rechnung = replace(_rechnung(1, kat, '1000', 'H-1'), heizungsanlage_id=7)
    welt = replace(
        _welt([rechnung]),
        heizungsanlagen=(Heizungsanlage(id=7, name='Zentrale Anlage'),),
        profile={1: 'ignoriert'},
        profile_der_immobilie={1: {1: 'ignoriert'}, 2: {1: 'prozent'}},
        prozentanteile_der_immobilie={2: {1: Decimal('70')}},
        heizkostenv_bestaetigungen=frozenset({(2, 1)} if bestaetigt else set()),
    )

    ergebnis = rechne(welt)

    assert ergebnis['total_amount'] == Decimal('0.00')
    assert ergebnis['landlord_share']['prozent_amount'] == Decimal('0.00')
    assert ergebnis['landlord_share']['positions'] == []
    assert len(ergebnis['line_items']) == 1
    assert ergebnis['line_items'][0]['billing_type'] == 'ignoriert'
