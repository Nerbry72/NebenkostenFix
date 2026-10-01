"""NK-188: der Zeitraumvorschlag gegen die Lagen aus einem echten Bestand.

Die Praxisprobe (NK-187) fand ein Haus, das April bis März abrechnet (H1),
Einheiten ohne Rechnungen (H8) und einen Vorschlag, der sich selbst
widersprach (F-126). Die Werte hier sind erfunden; nur die Form der Lagen
stammt aus dem Bestand. Jeder Test prüft die Gründe im Wortlaut, denn die
liest der Vermieter.
"""

from __future__ import annotations

import shutil
from datetime import date

import pytest

from nebenkostenfix.frist import frist_ende
from nebenkostenfix.models import TenantBillingReport, db
from nebenkostenfix.validation import EingabeFehler
from nebenkostenfix.zeitraumvorschlag import jahresbeginn_aus_text, vorschlag
from tests import billing_factories as f

HEUTE = date(2026, 9, 30)
APRIL = '04-01'


def _mieter(prop, name, move_in, move_out=None, wohnung='EG'):
    return f.tenant(f.apt(prop, wohnung, 60.0), name, move_in=move_in, move_out=move_out)


def _abgerechnet(mieter, von, bis):
    db.session.add(TenantBillingReport(tenant_id=mieter.id, start_date=von, end_date=bis,
                                       frist_ende=frist_ende(bis)))
    db.session.commit()


def _muell(prop, mieter, *zeitraeume):
    kat = f.category('Müllabfuhr')
    f.profile(mieter, kat, 'qm')
    for i, (von, bis) in enumerate(zeitraeume):
        f.invoice(prop, kat, 240.0, start=von, end=bis, invoice_number=f'M-{i}')
    return kat


# --- H1: Abrechnungsjahr April bis März (D-114) ------------------------------------

def test_rhythmus_aus_den_bisherigen_abrechnungen(app_ctx):
    """Vorher: 01.04.2025–31.12.2025, ein Rumpfzeitraum, den niemand wollte."""
    prop = f.house('Aprilhaus')
    mieter = _mieter(prop, 'Mieter 1', date(2020, 4, 1))
    _abgerechnet(mieter, date(2024, 4, 1), date(2025, 3, 31))
    _muell(prop, mieter, (date(2025, 4, 1), date(2026, 3, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-04-01', '2026-03-31')
    assert v['gruende'] == [
        'Abgerechnet ist bis 31.03.2025, weiter geht es ab 01.04.2025.',
        'Das Abrechnungsjahr beginnt am 01.04. (wie die bisherigen Abrechnungen des Hauses), '
        'höchstens zwölf Monate (§ 556 Abs. 3 BGB).',
        'Die vorhandenen Rechnungen decken den ganzen Zeitraum ab.',
        'Zustellen bis spätestens 31.03.2027 (§ 556 Abs. 3 BGB).',
    ]


def test_neuer_mieter_folgt_dem_haus(app_ctx):
    """Einzug mitten im Monat, eingestelltes Abrechnungsjahr: bis zu dessen Ende."""
    prop = f.house('Aprilhaus')
    prop.abrechnungsjahr_beginn = APRIL
    mieter = _mieter(prop, 'Mieter 2', date(2025, 6, 15))
    _muell(prop, mieter, (date(2025, 4, 1), date(2026, 3, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-06-15', '2026-03-31')
    assert v['gruende'][1] == ('Das Abrechnungsjahr beginnt am 01.04. (so eingestellt am Haus), '
                               'höchstens zwölf Monate (§ 556 Abs. 3 BGB).')


def test_wechsel_des_rhythmus_gibt_einen_rumpfzeitraum(app_ctx):
    """Bisher Kalenderjahr, jetzt April: einmal 01.01.–31.03., dann im neuen Takt."""
    prop = f.house('Wechselhaus')
    prop.abrechnungsjahr_beginn = APRIL
    mieter = _mieter(prop, 'Mieter 3', date(2020, 1, 1))
    _abgerechnet(mieter, date(2024, 1, 1), date(2024, 12, 31))
    _muell(prop, mieter, (date(2025, 1, 1), date(2025, 12, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-01-01', '2025-03-31')
    assert v['gruende'][-1] == 'Zustellen bis spätestens 31.03.2026 (§ 556 Abs. 3 BGB).'


def test_auszug_bestimmt_den_rhythmus_nicht(app_ctx):
    """Eine Schlussabrechnung zum Auszug am 15.08. ist kein Abrechnungsjahr."""
    prop = f.house('Auszugshaus')
    frueher = _mieter(prop, 'Mieter 4', date(2020, 1, 1), date(2024, 8, 15), 'OG')
    _abgerechnet(frueher, date(2024, 1, 1), date(2024, 8, 15))
    mieter = _mieter(prop, 'Mieter 5', date(2024, 9, 1))
    _muell(prop, mieter, (date(2024, 9, 1), date(2025, 12, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2024-09-01', '2024-12-31')
    assert v['gruende'][1] == ('Abgerechnet wird je Kalenderjahr, höchstens zwölf Monate '
                               '(§ 556 Abs. 3 BGB).')


@pytest.mark.parametrize('vorjahr', [False, True])
def test_kurze_abrechnung_bestimmt_den_rhythmus_nicht(app_ctx, vorjahr):
    """Copilot-Review zu PR #25: 01.01.–31.03. abgerechnet, weil die Rechnungen
    endeten. Vorher begann das Abrechnungsjahr danach am 01.04."""
    prop = f.house('Kalenderhaus')
    mieter = _mieter(prop, 'Mieter 12', date(2020, 1, 1))
    if vorjahr:
        _abgerechnet(mieter, date(2024, 1, 1), date(2024, 12, 31))
    _abgerechnet(mieter, date(2025, 1, 1), date(2025, 3, 31))
    _muell(prop, mieter, (date(2025, 1, 1), date(2025, 12, 31)),
           (date(2026, 1, 1), date(2026, 12, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-04-01', '2025-12-31')
    assert v['gruende'][1].startswith('Abgerechnet wird je Kalenderjahr')


def test_auszug_am_monatsletzten_vor_dem_jahresende(app_ctx):
    prop = f.house('Aprilhaus')
    prop.abrechnungsjahr_beginn = APRIL
    mieter = _mieter(prop, 'Mieter 6', date(2025, 4, 1), date(2025, 11, 30))
    _muell(prop, mieter, (date(2025, 4, 1), date(2026, 3, 31)))

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-04-01', '2025-11-30')
    assert v['gruende'][1] == 'Der letzte Miettag ist der 30.11.2025.'


# --- H8 und F-126: keine Rechnung, kein „deckt ab“ ------------------------------------

def test_ohne_rechnung_kein_vorschlag(app_ctx):
    """Vorher: 01.01.2025–31.12.2025, „decken den ganzen Zeitraum ab“ -- es gab keine."""
    prop = f.house('Leerhaus')
    mieter = _mieter(prop, 'Mieter 7', date(2025, 1, 1))

    v = vorschlag(mieter.id, HEUTE)

    assert v['beginn'] is None
    assert v['gruende'][-1] == ('Für 01.01.2025–31.12.2025 ist noch keine Rechnung erfasst. '
                                'Erfassen Sie die Rechnungen, dann schlägt die App den '
                                'Zeitraum vor.')


def test_vorjahreshinweis_ohne_widerspruch(app_ctx):
    """Vorher: „decken den ganzen Zeitraum ab“ und gleich danach „fehlen diese Kosten“."""
    prop = f.house('Vorjahrhaus')
    mieter = _mieter(prop, 'Mieter 8', date(2020, 1, 1))
    mieter.last_billed_until = date(2024, 12, 31)
    _muell(prop, mieter, (date(2025, 1, 1), date(2025, 12, 31)))
    sonst = f.category('Sonstige Betriebskosten')
    f.profile(mieter, sonst, 'qm')
    f.invoice(prop, sonst, 80.0, start=date(2024, 1, 1), end=date(2024, 12, 31),
              invoice_number='S-1')

    gruende = vorschlag(mieter.id, HEUTE)['gruende']

    assert 'Die vorhandenen Rechnungen decken den ganzen Zeitraum ab.' not in gruende
    assert gruende[2] == 'Jede Kostenart mit Rechnung ist für den ganzen Zeitraum belegt.'
    assert gruende[3].startswith('Für „Sonstige Betriebskosten“ gab es im Jahr davor')


# --- H12: eine alte Rechnung bleibt draußen ---------------------------------------------

def test_alte_rechnung_ist_kein_vorjahr(app_ctx):
    prop = f.house('Althaus')
    mieter = _mieter(prop, 'Mieter 9', date(2020, 1, 1))
    mieter.last_billed_until = date(2024, 12, 31)
    _muell(prop, mieter, (date(2025, 1, 1), date(2025, 12, 31)))
    alt = f.category('Gartenpflege')
    f.profile(mieter, alt, 'qm')
    f.invoice(prop, alt, 60.0, start=date(2021, 1, 1), end=date(2021, 12, 31),
              invoice_number='A-1')

    v = vorschlag(mieter.id, HEUTE)

    assert (v['beginn'], v['ende']) == ('2025-01-01', '2025-12-31')
    assert not any('Gartenpflege' in g for g in v['gruende'])


# --- Das Feld am Haus ----------------------------------------------------------------

@pytest.mark.parametrize('text, gespeichert', [
    ('01.04.', '04-01'), ('1.4', '04-01'), (' 15.10. ', '10-15'), ('', None), (None, None)])
def test_jahresbeginn_aus_text(text, gespeichert):
    assert jahresbeginn_aus_text(text) == gespeichert


@pytest.mark.parametrize('text', ['29.02.', '31.04.', 'April', '2025-04-01'])
def test_jahresbeginn_ungueltig(text):
    with pytest.raises(EingabeFehler, match='01.04.'):
        jahresbeginn_aus_text(text)


def test_feld_ueber_die_api(auth_client):
    prop = f.house('Feldhaus')
    _abgerechnet(_mieter(prop, 'Mieter 10', date(2020, 1, 1)), date(2024, 7, 1), date(2025, 6, 30))

    def gelesen():
        return next(p for p in auth_client.get('/api/properties').get_json() if p['id'] == prop.id)

    assert (gelesen()['abrechnungsjahr_beginn'], gelesen()['abrechnungsjahr_quelle']) == (
        '01.07.', 'abrechnungen')
    assert auth_client.put(f'/api/properties/{prop.id}',
                           json={'abrechnungsjahr_beginn': '01.04.'}).status_code == 200
    assert (gelesen()['abrechnungsjahr_beginn'], gelesen()['abrechnungsjahr_quelle']) == (
        '01.04.', 'feld')
    assert auth_client.put(f'/api/properties/{prop.id}',
                           json={'abrechnungsjahr_beginn': '30.02.'}).status_code == 400
    assert auth_client.put(f'/api/properties/{prop.id}',
                           json={'abrechnungsjahr_beginn': ''}).status_code == 200
    assert gelesen()['abrechnungsjahr_quelle'] == 'abrechnungen'



def test_vorschlagsliste_fragt_abgerechnet_bis_einmal_je_mieter(auth_client, monkeypatch):
    """Copilot-Review zu PR #25: nicht einmal je Mieter und Kostenart."""
    from nebenkostenfix import zeitraumvorschlag
    prop = f.house('Zaehlhaus')
    mieter = _mieter(prop, 'Mieter 11', date(2020, 1, 1))
    for name in ('Müllabfuhr', 'Grundsteuer', 'Wasser'):
        f.profile(mieter, f.category(name), 'qm')
    aufrufe = []
    echt = zeitraumvorschlag.abgerechnet_bis
    monkeypatch.setattr(zeitraumvorschlag, 'abgerechnet_bis',
                        lambda t: aufrufe.append(t.id) or echt(t))

    assert auth_client.get('/api/billing/suggestions').status_code == 200
    assert aufrufe == [mieter.id]

@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
def test_bearbeiten_macht_den_abgeleiteten_beginn_nicht_zum_feld():
    """PR #25 (Copilot): der Dialog trug den abgeleiteten Wert ins Feld ein.

    Wer danach nur den Namen aendert, speichert ihn als Feld -- spaetere
    Abrechnungen verschieben das Abrechnungsjahr dann nicht mehr. Der
    abgeleitete Wert steht nur als Platzhalter da.
    """
    from tests.test_vorschau_anzeige import _funktionsrumpf, _node
    code = ('const felder = {}; const document = {getElementById: id => '
            '(felder[id] = felder[id] || {value: "?", placeholder: "01.01."})};'
            'const propertyModal = {querySelector: () => ({}), classList: {add() {}}};'
            'let editingPropertyId; const zeige = prop => { openAddPropertyModal(prop);'
            'const f = felder["prop-jahresbeginn"]; return [f.value, f.placeholder]; };'
            + _funktionsrumpf('openAddPropertyModal')
            + 'console.log(JSON.stringify(['
            'zeige({id: 1, name: "A", abrechnungsjahr_beginn: "01.07.", abrechnungsjahr_quelle: "abrechnungen"}),'
            'zeige({id: 2, name: "B", abrechnungsjahr_beginn: "01.04.", abrechnungsjahr_quelle: "feld"}),'
            'zeige(null)]));')
    assert _node(code) == [['', '01.07.'], ['01.04.', '01.04.'], ['', '01.01.']]
