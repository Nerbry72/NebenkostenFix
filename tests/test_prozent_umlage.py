"""Vertragliche Anteile: 30/70 statt der Wohnflächen 60/40."""
from dataclasses import replace
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


@pytest.mark.parametrize('prozent, erwartet', [('0', '0'), ('100', '1000'), ('30.25', '302.50')])
def test_grenzen_und_nachkommastellen(prozent, erwartet):
    vorgang = replace(_welt([_rechnung(1, MUELL, '1000', 'P-2')]),
                      profile={MUELL.id: 'prozent'},
                      prozentanteile={MUELL.id: Decimal(prozent)})
    posten = rechne(vorgang)['line_items'][0]
    assert posten['tenant_cost'] == Decimal(erwartet)
    assert posten['rechenweg']
    from nebenkostenfix.pdf_uebersicht import schluessel_text, anteil_text
    assert schluessel_text(posten) == 'Umlage nach Prozentsatz'
    assert '%' in anteil_text(posten)


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
