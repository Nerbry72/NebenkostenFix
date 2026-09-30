"""NK-186: Die App schlaegt den Abrechnungszeitraum vor und begruendet ihn.

Befund auf 6061: Mieter 3 (Einzug 01.09.2025, letzter Miettag 30.09.2026)
wurde 01.09.2025-30.09.2026 abgerechnet, obwohl die Rechnungen fuer 2026
noch zum Teil fehlten. Sinnvoll war 01.09.2025-31.12.2025.

*Haette den Befund verhindert:* ``test_mieter_3_bis_jahresende``.
"""

from __future__ import annotations

import shutil
from datetime import date

import pytest

from nebenkostenfix.frist import frist_ende
from nebenkostenfix.models import TenantBillingReport, db
from nebenkostenfix.zeitraumvorschlag import vorschlag
from tests import billing_factories as f
from tests.test_vorschau_anzeige import _funktionsrumpf, _konstante, _node

HEUTE = date(2026, 9, 30)


def _haus(move_in=date(2025, 9, 1), move_out=date(2026, 9, 30)):
    prop = f.house('Vorschlagshaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Mieter 3', move_in=move_in, move_out=move_out)
    return prop, mieter


def _art(prop, mieter, name, *zeitraeume):
    kat = f.category(name)
    f.profile(mieter, kat, 'qm')
    for i, (von, bis) in enumerate(zeitraeume):
        f.invoice(prop, kat, 100.0, start=von, end=bis, invoice_number=f'{name}-{i}')
    return kat


def test_mieter_3_bis_jahresende(app_ctx):
    prop, mieter = _haus()
    _art(prop, mieter, 'Müllabfuhr', (date(2025, 1, 1), date(2025, 12, 31)),
         (date(2026, 1, 1), date(2026, 12, 31)))
    _art(prop, mieter, 'Allgemeinstrom', (date(2025, 1, 1), date(2025, 12, 31)),
         (date(2026, 1, 1), date(2026, 3, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-09-01', '2025-12-31')
    assert v['gruende'] == [
        'Noch keine Abrechnung: Beginn ist der Einzug am 01.09.2025.',
        'Abgerechnet wird je Kalenderjahr, höchstens zwölf Monate (§ 556 Abs. 3 BGB).',
        'Die vorhandenen Rechnungen decken den ganzen Zeitraum ab.',
        'Den Rest bis zum Auszug (01.01.2026–30.09.2026) rechnen Sie getrennt ab, '
        'sobald die Rechnungen da sind.',
        'Zustellen bis spätestens 31.12.2026 (§ 556 Abs. 3 BGB).',
    ]


def test_zweiter_zeitraum_endet_vor_der_luecke(app_ctx):
    """Nach der Abrechnung 2025: Strom nur bis 31.03.2026 -> Vorschlag bis dahin."""
    prop, mieter = _haus()
    _art(prop, mieter, 'Müllabfuhr', (date(2026, 1, 1), date(2026, 12, 31)))
    _art(prop, mieter, 'Allgemeinstrom', (date(2026, 1, 1), date(2026, 3, 31)))
    db.session.add(TenantBillingReport(
        tenant_id=mieter.id, start_date=date(2025, 9, 1), end_date=date(2025, 12, 31),
        frist_ende=frist_ende(date(2025, 12, 31))))
    db.session.commit()

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2026-01-01', '2026-03-31')
    assert v['gruende'][0] == 'Abgerechnet ist bis 31.12.2025, weiter geht es ab 01.01.2026.'
    assert v['gruende'][1] == 'Der letzte Miettag ist der 30.09.2026.'
    assert v['gruende'][2] == ('Ab 01.04.2026 fehlt die Rechnung für „Beleuchtung (Allgemeinstrom)“. '
                               'Deshalb endet der Vorschlag am 31.03.2026.')
    assert v['gruende'][3].startswith('Den Rest bis zum Auszug (01.04.2026–30.09.2026)')


def test_kostenart_aus_dem_vorjahr_ohne_rechnung_wird_genannt(app_ctx):
    """Auf 6061: Schornsteinfeger nur 2024. Kein Grund, gar nichts vorzuschlagen."""
    prop, mieter = _haus(move_in=date(2020, 1, 1), move_out=None)
    _art(prop, mieter, 'Müllabfuhr', (date(2024, 1, 1), date(2024, 12, 31)),
         (date(2025, 1, 1), date(2025, 12, 31)))
    _art(prop, mieter, 'Grundsteuer', (date(2024, 1, 1), date(2024, 12, 31)))
    mieter.last_billed_until = date(2024, 12, 31)
    db.session.commit()

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-01-01', '2025-12-31')
    assert ('Für „Grundsteuer“ gab es im Jahr davor eine Rechnung, für diesen Zeitraum '
            'noch nicht. Kommt sie noch, warten Sie mit der Abrechnung; sonst fehlen '
            'diese Kosten.') in v['gruende']


def test_laufendes_jahr_gibt_keinen_vorschlag(app_ctx):
    prop, mieter = _haus(move_in=date(2026, 1, 1), move_out=None)
    v = vorschlag(mieter.id, HEUTE)
    assert v['beginn'] is None
    assert v['gruende'][-1] == ('Der Zeitraum läuft noch bis 31.12.2026. '
                                'Abrechnen lässt er sich erst danach.')


def test_letzter_miettag_heute_ist_abrechenbar(app_ctx):
    prop, mieter = _haus(move_in=date(2026, 1, 1))
    _art(prop, mieter, 'Müllabfuhr', (date(2026, 1, 1), date(2026, 12, 31)))
    v = vorschlag(mieter.id, HEUTE)
    assert (v['beginn'], v['ende']) == ('2026-01-01', '2026-09-30')


def test_nach_dem_auszug_abgerechnet(app_ctx):
    prop, mieter = _haus()
    mieter.last_billed_until = date(2026, 9, 30)
    db.session.commit()
    assert vorschlag(mieter.id, HEUTE)['gruende'] == [
        'Das Mietverhältnis ist bis zum Auszug am 30.09.2026 abgerechnet.']


def test_endpunkt(auth_client):
    prop, mieter = _haus()
    _art(prop, mieter, 'Müllabfuhr', (date(2025, 1, 1), date(2025, 12, 31)))
    antwort = auth_client.get(f'/api/tenants/{mieter.id}/zeitraumvorschlag')
    assert antwort.status_code == 200
    assert antwort.get_json()['beginn'] == '2025-09-01'
    assert auth_client.get('/api/tenants/99999/zeitraumvorschlag').status_code == 404


# --- Anzeige -------------------------------------------------------------------

@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
def test_anzeige_zeigt_zeitraum_und_maskierte_gruende():
    code = (_konstante('datumText') + _funktionsrumpf('escapeHtml')
            + _funktionsrumpf('zeitraumVorschlagHtml')
            + 'console.log(JSON.stringify([zeitraumVorschlagHtml({beginn: "2025-09-01", '
            'ende: "2025-12-31", gruende: ["<b>x</b>"]}), zeitraumVorschlagHtml('
            '{beginn: null, ende: null, gruende: ["Läuft noch."]})]));')
    mit, ohne = _node(code)
    assert 'Vorschlag: 01.09.2025 – 31.12.2025' in mit
    assert '&lt;b&gt;x&lt;/b&gt;' in mit and 'Übernehmen' in mit
    assert 'Zurzeit kein Vorschlag' in ohne and 'button' not in ohne


def test_beide_dialoge_holen_den_vorschlag():
    assert "zeitraumVorschlagen(auswahl.value, 'frei-zeitraumvorschlag'" in \
        _funktionsrumpf('openFreieAbrechnung')
    assert "zeitraumVorschlagen(suggestion.tenant_id, 'billing-zeitraumvorschlag'" in \
        _funktionsrumpf('openBillingSelectionModal')
