"""Vertragliche Anteile: 30/70 statt der Wohnflächen 60/40."""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from tests.test_gutschrift_umlage import _welt, _rechnung, MUELL
from nebenkostenfix.rechenkern import rechne
from nebenkostenfix.validation import kostenprofile, EingabeFehler


@pytest.mark.parametrize('betrag', ['1000', '-1000'])
def test_dreissig_siebzig(betrag):
    rechnung = _rechnung(1, MUELL, betrag, 'P-1')
    kosten = []
    for wer, prozent in [(1, '30'), (2, '70')]:
        vorgang = replace(_welt([rechnung], wer=wer),
                          profile={MUELL.id: 'prozent'},
                          prozentanteile={MUELL.id: Decimal(prozent)})
        posten = rechne(vorgang)['line_items'][0]
        assert posten['tenant_cost'] == Decimal(betrag) * Decimal(prozent) / 100
        assert prozent in posten['description']
        assert posten['sub_items']
        kosten.append(posten['tenant_cost'])
    assert sum(kosten) == Decimal(betrag)


@pytest.mark.parametrize('wert', [None, '', '-1', '100.01', 'NaN', 'Infinity', True, '30.001'])
def test_ungueltige_prozente(wert):
    with pytest.raises(EingabeFehler):
        kostenprofile({'1': {'billing_type': 'prozent', 'percentage': wert}})


def test_komma_und_bisheriges_format():
    assert kostenprofile({'1': 'qm', '2': {'billing_type': 'prozent', 'percentage': '30,25'}}) == {
        1: 'qm', 2: {'billing_type': 'prozent', 'percentage': Decimal('30.25')}}


def test_prozent_braucht_wert():
    with pytest.raises(EingabeFehler):
        kostenprofile({'1': 'prozent'})


@pytest.mark.parametrize('prozent, erwartet', [('100', '1000'), ('30.25', '302.50')])
def test_grenzen_und_nachkommastellen(prozent, erwartet):
    vorgang = replace(_welt([_rechnung(1, MUELL, '1000', 'P-2')]),
                      profile={MUELL.id: 'prozent'},
                      prozentanteile={MUELL.id: Decimal(prozent)})
    posten = rechne(vorgang)['line_items'][0]
    assert posten['tenant_cost'] == Decimal(erwartet)
    assert posten['rechenweg']
    from nebenkostenfix.pdf_uebersicht import schluessel_text, anteil_text
    assert schluessel_text(posten) == 'Umlage nach Prozentsatz'
    assert anteil_text(posten) == prozent.replace('.', ',') + ' %'


def test_null_prozent_erzeugt_keine_abrechnungszeile():
    vorgang = replace(_welt([_rechnung(1, MUELL, '1000', 'P-Null')]),
                      profile={MUELL.id: 'prozent'}, prozentanteile={MUELL.id: Decimal('0')})
    ergebnis = rechne(vorgang)
    assert ergebnis['line_items'] == []
    assert ergebnis['total_amount'] == 0
    assert ergebnis['landlord_share']['total_amount'] == Decimal('1000.00')


@pytest.mark.parametrize('betrag', ['0.03', '-0.03', '1000'])
def test_vereinbarter_satz_bleibt_trotz_eurorundung_exakt(betrag):
    from nebenkostenfix.pdf_uebersicht import anteil_text
    vorgang = replace(_welt([_rechnung(1, MUELL, betrag, 'P-Exakt')]),
                      profile={MUELL.id: 'prozent'}, prozentanteile={MUELL.id: Decimal('30.25')})
    posten = rechne(vorgang)['line_items'][0]
    assert posten['percentage'] == Decimal('30.25')
    assert anteil_text(posten) == '30,25 %'


def test_prozentwert_steht_exakt_im_pdf_uebersichtsblatt(monkeypatch):
    import reportlab.rl_config
    from nebenkostenfix.pdf_generator import PDFGenerator
    from tests.test_pdf_uebersicht import _blaetter
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)
    vorgang = replace(_welt([_rechnung(1, MUELL, '0.03', 'P-PDF')]),
                      profile={MUELL.id: 'prozent'}, prozentanteile={MUELL.id: Decimal('30.25')})
    ergebnis = rechne(vorgang)
    pdf = PDFGenerator('Haus', 'Wohnung', 'Mieter', '2025-01-01', '2025-12-31').generate(
        ergebnis['line_items'], ergebnis['total_amount'])
    uebersicht = next(blatt for blatt in _blaetter(pdf) if 'Kostenposition' in blatt)
    assert '30,25%' in uebersicht
    assert '33,3%' not in uebersicht


def test_zeitanteil():
    from datetime import date
    # 1000 EUR für 365 Tage, davon 181 Tage abgerechnet, davon 30 %.
    vorgang = replace(_welt([_rechnung(1, MUELL, '1000', 'P-3')]),
                      ende=date(2025, 6, 30), profile={MUELL.id: 'prozent'},
                      prozentanteile={MUELL.id: Decimal('30')})
    assert rechne(vorgang)['line_items'][0]['tenant_cost'] == Decimal('148.77')


def test_fehlender_anteil_im_kern_ist_fehler():
    from nebenkostenfix.rechenkern import BillingDataError
    vorgang = replace(_welt([_rechnung(1, MUELL, '1000', 'P-4')]),
                      profile={MUELL.id: 'prozent'})
    with pytest.raises(BillingDataError, match='Müllabfuhr'):
        rechne(vorgang)


def test_prozentbaustein_braucht_nur_standardbibliothek():
    import ast
    from pathlib import Path
    from nebenkostenfix import prozent
    from tests.importwaechter import importierte_module

    quelle = Path(prozent.__file__).read_text(encoding='utf-8')
    assert importierte_module(ast.parse(quelle)) <= {'decimal'}


def _prozentwelt(anteil1='30', anteil2='50', betrag='1000'):
    welt = _welt([_rechnung(1, MUELL, betrag, 'P-Rest')])
    profile = {m.id: {MUELL.id: 'prozent'} for m in welt.mieter_der_immobilie}
    prozente = {1: {MUELL.id: Decimal(anteil1)}, 2: {MUELL.id: Decimal(anteil2)}}
    return replace(welt, profile=profile[1], prozentanteile=prozente[1],
                   profile_der_immobilie=profile, prozentanteile_der_immobilie=prozente)


@pytest.mark.parametrize('betrag', ['1000', '-1000'])
def test_rest_ist_vermieteranteil_auch_bei_gutschrift(betrag):
    welt = _prozentwelt(betrag=betrag)
    ergebnis = rechne(welt)
    assert ergebnis['total_amount'] == Decimal(betrag) * Decimal('.3')
    assert ergebnis['landlord_share']['total_amount'] == Decimal(betrag) * Decimal('.2')
    assert ergebnis['landlord_share']['prozent_amount'] == Decimal(betrag) * Decimal('.2')
    assert 'Prozentanteile' in ergebnis['landlord_share']['positions'][0]['description']
    nachbar = replace(welt, mieter=welt.mieter_der_immobilie[1], wohnung=welt.wohnungen[1],
                      prozentanteile=welt.prozentanteile_der_immobilie[2])
    assert (ergebnis['total_amount'] + rechne(nachbar)['total_amount']
            + ergebnis['landlord_share']['total_amount']) == Decimal(betrag)


def test_hundert_prozent_hat_keinen_vermieterrest():
    assert rechne(_prozentwelt('30.25', '69.75'))['landlord_share']['total_amount'] == 0


def test_ueber_hundert_prozent_aus_import_blockiert_auch_im_kern():
    from nebenkostenfix.rechenkern import BillingDataError
    with pytest.raises(BillingDataError, match='110 %'):
        rechne(_prozentwelt('40', '70'))


def test_leerstand_und_nachmieter_werden_taggenau_beruecksichtigt():
    from nebenkostenfix.rechenkern import Mieter
    welt = _prozentwelt('30', '70', '36500')
    # 181 Tage vollständig verteilt, 31 Tage Leerstand, dann Nachmieter.
    mieter = (welt.mieter, replace(welt.mieter_der_immobilie[1], auszug=date(2025, 7, 1)),
              Mieter(3, 'Nachmieter', date(2025, 8, 1), None, 2))
    welt = replace(welt, mieter_der_immobilie=mieter,
                   profile_der_immobilie={**welt.profile_der_immobilie, 3: {MUELL.id: 'prozent'}},
                   prozentanteile_der_immobilie={**welt.prozentanteile_der_immobilie,
                                                3: {MUELL.id: Decimal('70')}})
    assert rechne(welt)['landlord_share']['total_amount'] == Decimal('2170.00')
    # Außerhalb des Abrechnungsfensters darf kein Leerstand ausgewiesen werden.
    assert rechne(replace(welt, ende=date(2025, 6, 30)))['landlord_share']['total_amount'] == 0


def test_gemischte_umlage_verhindert_falschen_rest():
    from nebenkostenfix.rechenkern import BillingDataError
    welt = _prozentwelt()
    with pytest.raises(BillingDataError, match='gemischt'):
        rechne(replace(welt, profile_der_immobilie={1: {MUELL.id: 'prozent'}, 2: {}}))


def test_vergangene_prozentumlage_blockiert_spaetere_flaechenumlage_nicht():
    welt = _prozentwelt()
    mieter = (welt.mieter, replace(welt.mieter_der_immobilie[1], auszug=date(2025, 7, 1)))
    welt = replace(welt, beginn=date(2025, 7, 1), profile={MUELL.id: 'qm'},
                   mieter_der_immobilie=mieter,
                   profile_der_immobilie={1: {MUELL.id: 'qm'}, 2: {MUELL.id: 'prozent'}})
    assert rechne(welt)['landlord_share']['prozent_amount'] == 0


def test_vermieterrest_steht_im_pdf(monkeypatch):
    import reportlab.rl_config
    from nebenkostenfix.pdf_generator import PDFGenerator
    from tests.test_pdf_gutschrift import _geklebt
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)
    ergebnis = rechne(_prozentwelt())
    pdf = PDFGenerator('Haus', 'Wohnung', 'Mieter', '2025-01-01', '2025-12-31').generate(
        ergebnis['line_items'], ergebnis['total_amount'],
        landlord_share=ergebnis['landlord_share'])
    text = _geklebt(pdf)
    assert 'Vermieteranteil' in text
    assert 'RestdervereinbartenProzentanteile' in text
    assert 'Prozentrest200,00€' in text


@pytest.fixture
def prozentmieter(auth_client):
    from tests.billing_factories import house, apt, tenant, category
    haus = house()
    return (tenant(apt(haus, 'A', 60), 'A', date(2025, 1, 1)),
            tenant(apt(haus, 'B', 40), 'B', date(2025, 1, 1)), category('Müll'))


def _speichere(client, mieter, kat, wert):
    return client.post(f'/api/tenants/{mieter.id}/profiles', json={
        str(kat.id): {'billing_type': 'prozent', 'percentage': wert}})


def test_server_lehnt_ueberschreitung_ab_und_erhaelt_profil(auth_client, prozentmieter):
    a, b, kat = prozentmieter
    assert _speichere(auth_client, a, kat, '30.25').status_code == 200
    assert _speichere(auth_client, b, kat, '69.75').status_code == 200
    antwort = _speichere(auth_client, b, kat, '69.76')
    assert antwort.status_code == 400
    assert '100,01 %' in antwort.get_json()['error']
    assert kat.name in antwort.get_json()['error']
    assert auth_client.get(f'/api/tenants/{b.id}/profiles').get_json()[str(kat.id)]['percentage'] == '69.75'


def test_api_summen_sind_objektbezogen_und_ohne_eigenen_anteil(auth_client, prozentmieter):
    from tests.billing_factories import house, apt, tenant
    a, b, kat = prozentmieter
    fremd = tenant(apt(house('Anderes Haus'), 'C', 50), 'C', date(2025, 1, 1))
    assert _speichere(auth_client, fremd, kat, '100').status_code == 200
    assert _speichere(auth_client, a, kat, '30').status_code == 200
    assert _speichere(auth_client, b, kat, '50').status_code == 200
    segmente = auth_client.get(f'/api/tenants/{a.id}/profiles/percentages').get_json()[str(kat.id)]
    assert segmente == [{'start': '2025-01-01', 'end': None, 'percentage': '50.00'}]


def test_nachmieter_darf_selben_anteil_speichern_ueberlappung_nicht(auth_client, prozentmieter):
    from nebenkostenfix.models import db
    from tests.billing_factories import tenant
    a, b, kat = prozentmieter
    b.move_out_date = date(2025, 6, 30)
    db.session.commit()
    nachmieter = tenant(b.apartment, 'Nachmieter', date(2025, 7, 1))
    assert _speichere(auth_client, a, kat, '30').status_code == 200
    assert _speichere(auth_client, b, kat, '70').status_code == 200
    assert _speichere(auth_client, nachmieter, kat, '70').status_code == 200
    # Auch eine nachträgliche Verlängerung darf die Sperre nicht umgehen.
    antwort = auth_client.put(f'/api/tenants/{b.id}', json={'move_out_date': '2025-07-01'})
    assert antwort.status_code == 400
    assert '170 %' in antwort.get_json()['error']
    assert db.session.get(type(b), b.id).move_out_date == date(2025, 6, 30)


def test_datenbankprofile_fliessen_in_den_vermieterrest_ein(auth_client, prozentmieter):
    from tests.billing_factories import invoice
    from nebenkostenfix.billing_engine import BillingEngine
    a, b, kat = prozentmieter
    assert _speichere(auth_client, a, kat, '30').status_code == 200
    assert _speichere(auth_client, b, kat, '50').status_code == 200
    invoice(a.apartment.property, kat, 1000, date(2025, 1, 1), date(2025, 12, 31))
    ergebnis = BillingEngine(a.id, '2025-01-01', '2025-12-31').calculate_bill()
    assert ergebnis['total_amount'] == Decimal('300.00')
    assert ergebnis['landlord_share']['total_amount'] == Decimal('200.00')


def test_auszugstag_zaehlt_auch_bei_der_summenpruefung(auth_client, prozentmieter):
    from nebenkostenfix.models import db
    from tests.billing_factories import tenant
    a, b, kat = prozentmieter
    b.move_out_date = date(2025, 6, 30)
    db.session.commit()
    nachmieter = tenant(b.apartment, 'Zu früher Einzug', date(2025, 6, 30))
    assert _speichere(auth_client, a, kat, '30').status_code == 200
    assert _speichere(auth_client, b, kat, '70').status_code == 200
    antwort = _speichere(auth_client, nachmieter, kat, '70')
    assert antwort.status_code == 400
    assert '30.06.2025' in antwort.get_json()['error']
