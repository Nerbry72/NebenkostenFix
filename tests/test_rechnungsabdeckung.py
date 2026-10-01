"""Rechnungen gegen den Abrechnungszeitraum (F-114, F-115, F-117).

Befunde aus der Abrechnung Mieter 3 auf 6061:

* **F-115** -- Die Stromrechnung endete am 31.03., der Zeitraum lief bis
  30.09. Abgerechnet wurden nur die Tage mit Rechnung, die Vorauszahlungen
  zaehlten voll: ein Guthaben aus fehlenden Rechnungen, ohne jeden Hinweis.
  Jetzt nennt die Abrechnung die Luecke, schlaegt das Aufteilen des
  Zeitraums vor und das PDF traegt einen Vorbehalt.
* **F-117** -- Versicherung Rechnung 1 bis 01.01., Rechnung 2 ab 01.01.:
  der 01.01. wurde doppelt umgelegt, still.
* **F-114** -- Eine Gasrechnung direkt auf die Wohnung mit Zaehler, die
  ueber den Zeitraum hinausragt, wurde nach Tagen geteilt. Gas im Sommer ist
  nicht Gas im Winter; der Zaehler weiss es besser.

*Haetten diese Fehler gefunden:* jeder Test hier -- vor dem Fix gab es weder
Warnung noch Vorbehalt, und F-114 rechnete 501,37 EUR statt 200,00 EUR.

Die Daten sind synthetisch; jede Zahl ist von Hand nachgerechnet.
"""

import zlib
from dataclasses import replace
from datetime import date
from decimal import Decimal

import reportlab.rl_config

from nebenkostenfix.pdf_generator import PDFGenerator
from nebenkostenfix.rechenkern import (
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    pruefe,
    rechne,
)
from nebenkostenfix.zeitraum import grenze

STROM = Kategorie(id=5, name='Strom', braucht_zaehler=False)
VERSICHERUNG = Kategorie(id=7, name='Versicherung', braucht_zaehler=False)
GAS = Kategorie(id=9, name='Gas', braucht_zaehler=True)


def _vorgang(rechnungen, beginn=date(2025, 1, 1), ende=date(2025, 12, 31),
             zaehler=(), profile=None):
    links = Wohnung(id=1, name='EG links', qm=50.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=50.0)
    anna = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1), auszug=None, wohnung_id=1)
    bert = Mieter(id=2, name='Bert', einzug=date(2020, 1, 1), auszug=None, wohnung_id=2)
    return Vorgang(
        mieter=anna, wohnung=links, immobilie_id=1, immobilie_name='Hauptstrasse 1',
        beginn=beginn, ende=ende, wohnungen=(links, rechts),
        mieter_der_immobilie=(anna, bert),
        profile=profile or {STROM.id: 'qm', VERSICHERUNG.id: 'qm'},
        rechnungen=tuple(rechnungen), zaehler=tuple(zaehler),
    )


def _r(id, kat, beginn, ende, betrag='1000.00', wohnung_id=None):
    return Rechnung(id=id, kategorie=kat, betrag=Decimal(betrag),
                    beginn=beginn, ende=ende, wohnung_id=wohnung_id)


def _hinweise(pruefung):
    return [c['message'] for c in pruefung['checks'] if c['category'] == 'Rechnungen']


# --- F-115: Luecken im Zeitraum ------------------------------------------------

def test_fehlende_rechnung_wird_benannt_und_aufteilen_vorgeschlagen():
    v = _vorgang([_r(1, STROM, date(2025, 1, 1), date(2025, 3, 31))])
    ergebnis = rechne(v)

    warnung = next(w for w in ergebnis['warnings'] if 'nicht ganz ab' in w)
    assert '„Strom“ 90 von 365 Tagen (fehlt 01.04.2025–31.12.2025)' in warnung
    assert 'jetzt bis 31.03.2025 abrechnen' in warnung
    assert 'Strom (01.04.2025–31.12.2025)' in ergebnis['vorbehalt']

    hinweise = _hinweise(pruefe(v))
    assert hinweise == [warnung]
    kachel = next(c for c in pruefe(v)['checks'] if c['category'] == 'Rechnungen')
    assert kachel['blocking'] is False and kachel['meter_id'] is None


def test_luecke_in_der_mitte_und_fremde_wohnung_zaehlt_nicht():
    v = _vorgang([
        _r(1, STROM, date(2025, 1, 1), date(2025, 5, 31)),
        _r(2, STROM, date(2025, 7, 1), date(2025, 12, 31)),
        # Eine Rechnung der anderen Wohnung schliesst Annas Luecke nicht.
        _r(3, STROM, date(2025, 6, 1), date(2025, 6, 30), wohnung_id=2),
    ])
    warnung = next(w for w in rechne(v)['warnings'] if 'nicht ganz ab' in w)
    assert '(fehlt 01.06.2025–30.06.2025)' in warnung
    assert 'jetzt bis 31.05.2025 abrechnen' in warnung


def test_lueckenlose_rechnungen_bleiben_still():
    v = _vorgang([
        _r(1, STROM, date(2024, 10, 1), date(2025, 6, 30)),
        _r(2, STROM, date(2025, 7, 1), date(2026, 3, 31)),
    ])
    ergebnis = rechne(v)
    assert not [w for w in ergebnis['warnings'] if 'nicht ganz ab' in w]
    assert ergebnis['vorbehalt'] is None
    assert _hinweise(pruefe(v)) == []


def _pdf_text(pdf: bytes) -> str:
    stuecke = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            pass
        stuecke.append(roh.decode('latin-1', 'replace'))
    return ' '.join(stuecke)


def test_pdf_traegt_den_vorbehalt(monkeypatch):
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)
    posten = {'category': 'Strom', 'period': '01.01.2025 - 31.03.2025',
              'description': 'Umlage nach qm', 'tenant_cost': Decimal('100.00')}

    def text(vorbehalt):
        return _pdf_text(PDFGenerator(
            property_name='Haus', apartment_name='EG links', tenant_name='Anna',
            start_date='2025-01-01', end_date='2025-12-31',
        ).generate([posten], Decimal('100.00'), Decimal('0.00'), vorbehalt=vorbehalt))

    assert 'nachberechnet' in text('Vorbehalt: Strom fehlt, wird nachberechnet.')
    assert 'nachberechnet' not in text(None)


# --- F-117: doppelt gezaehlte Tage ---------------------------------------------

def test_ueberschneidung_um_einen_tag_wird_gemeldet():
    v = _vorgang([
        _r(1, VERSICHERUNG, date(2025, 1, 1), date(2025, 7, 1)),
        _r(2, VERSICHERUNG, date(2025, 7, 1), date(2025, 12, 31)),
    ])
    meldungen = [w for w in rechne(v)['warnings'] if 'überschneiden' in w]
    assert len(meldungen) == 1
    assert 'am 01.07.2025' in meldungen[0]
    assert '01.01.2025–01.07.2025 und 01.07.2025–31.12.2025' in meldungen[0]
    assert any('überschneiden' in h for h in _hinweise(pruefe(v)))


def test_angrenzende_und_parallele_rechnungen_bleiben_still():
    angrenzend = _vorgang([
        _r(1, VERSICHERUNG, date(2025, 1, 1), date(2025, 6, 30)),
        _r(2, VERSICHERUNG, date(2025, 7, 1), date(2025, 12, 31)),
    ])
    # Zwei Policen fuer dasselbe Jahr sind echt, keine Doppelzaehlung.
    parallel = _vorgang([
        _r(1, VERSICHERUNG, date(2025, 1, 1), date(2025, 12, 31)),
        _r(2, VERSICHERUNG, date(2025, 1, 1), date(2025, 12, 31)),
    ])
    for v in (angrenzend, parallel):
        assert not [w for w in rechne(v)['warnings'] if 'überschneiden' in w]


def _wechsel(auszug_vormieter, einzug_nachmieter):
    """EG links: Anna zieht aus, Carl zieht ein. Der Lader liefert ``auszug``
    schon als Grenze (F-118), deshalb hier ``grenze()`` auf den letzten Miettag."""
    v = _vorgang([_r(1, VERSICHERUNG, date(2025, 1, 1), date(2025, 12, 31))])
    anna = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1),
                  auszug=grenze(auszug_vormieter), wohnung_id=1)
    carl = Mieter(id=3, name='Carl', einzug=einzug_nachmieter, auszug=None, wohnung_id=1)
    return replace(v, mieter=anna, mieter_der_immobilie=(anna, carl, v.mieter_der_immobilie[1]))


def test_auszug_am_einzugstag_des_nachmieters_wird_gemeldet():
    """Altbestand vor F-118: Auszug 30.09. hiess „bis zum 29.09.“. Seit das
    Auszugsdatum der letzte Miettag ist, zaehlt der 30.09. doppelt."""
    v = _wechsel(date(2025, 9, 30), date(2025, 9, 30))
    meldungen = [w for w in rechne(v)['warnings'] if 'Mietverhältnisse' in w]
    assert meldungen == [
        'Zwei Mietverhältnisse in EG links überschneiden sich am 30.09.2025: Das '
        'eine endet am 30.09.2025, das nächste beginnt am 30.09.2025. Diese Tage '
        'zählen bei beiden. Das Auszugsdatum ist der letzte Miettag; tragen Sie '
        'beim Vormieter den Tag vor dem Einzug ein.']
    assert [c['category'] for c in pruefe(v)['checks']
            if 'Mietverhältnisse' in c['message']] == ['Mieter']


def test_lueckenloser_wechsel_und_andere_wohnung_bleiben_still():
    nahtlos = _wechsel(date(2025, 9, 30), date(2025, 10, 1))
    # Bert in EG rechts zieht am selben Tag ein, an dem Anna in EG links auszieht.
    v = _wechsel(date(2025, 9, 30), date(2025, 10, 1))
    bert = replace(v.mieter_der_immobilie[2], einzug=date(2025, 9, 30))
    nebenan = replace(v, mieter_der_immobilie=v.mieter_der_immobilie[:2] + (bert,))
    for fall in (nahtlos, nebenan):
        assert not [w for w in rechne(fall)['warnings'] if 'Mietverhältnisse' in w]
        assert not [c for c in pruefe(fall)['checks'] if 'Mietverhältnisse' in c['message']]


# --- F-114: Direktrechnung mit Zaehler ueber den Zeitraum hinaus ----------------

def _gas_vorgang(ende):
    """Gas direkt auf EG links, 01.04.2025-31.03.2026, 1000 EUR.

    Zaehler: 0 am 01.04.2025, 100 m³ am 01.10.2025, 500 m³ am 01.04.2026 --
    der Sommer braucht ein Fuenftel, der Winter den Rest.
    """
    zaehler = Zaehler(
        id=20, nummer='G-1', kategorie_id=GAS.id, kategorie_name=GAS.name,
        ist_hauptzaehler=False, immobilie_id=1, wohnung_id=1,
        staende=(Stand(date(2025, 4, 1), 0.0), Stand(date(2025, 10, 1), 100.0),
                 Stand(date(2026, 4, 1), 500.0)))
    return _vorgang(
        [_r(1, GAS, date(2025, 4, 1), date(2026, 3, 31), wohnung_id=1)],
        beginn=date(2025, 4, 1), ende=ende, zaehler=[zaehler],
        profile={GAS.id: 'direkt'})


def test_direktrechnung_ueber_den_zeitraum_hinaus_teilt_nach_verbrauch():
    """Sommerhalbjahr: 100 von 500 m³ -> 1000 · 1/5 = 200,00 EUR.

    Nach Tagen waeren es 1000 · 183/365 = 501,37 EUR gewesen.
    """
    ergebnis = rechne(_gas_vorgang(date(2025, 9, 30)))
    zeile = next(z for z in ergebnis['line_items'] if z['category'] == 'Gas')
    assert zeile['tenant_cost'] == Decimal('200.00')
    assert 'nach Verbrauch: 100 von 500 m³' in zeile['description']
    assert any('× 100 / 500' in s for s in zeile['rechenweg'])


def test_direktrechnung_im_zeitraum_bleibt_hundert_prozent():
    ergebnis = rechne(_gas_vorgang(date(2026, 3, 31)))
    zeile = next(z for z in ergebnis['line_items'] if z['category'] == 'Gas')
    assert zeile['tenant_cost'] == Decimal('1000.00')
    assert zeile['description'] == 'Direkt zugewiesen (100 % der Rechnung für diese Wohnung)'
