"""§ 9a HeizkostenV: die Schätzquote im Prüfstand.

Je Heizungsanlage und Zweck (Wärme, Warmwasser) der Anteil der Fläche, deren
Verbrauch im Abrechnungsjahr nicht ordnungsgemäß erfasst ist. Über 25 %
verlangt § 9a Abs. 2 eine Verteilung nur nach Fläche -- das kann die App
noch nicht, der Prüfstand sagt es. Nur Anzeige: kein Betrag ändert sich.
Alle Werte sind erfunden.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nebenkostenfix import heizung
from nebenkostenfix.abrechnungsdaten import lade_vorgang
from nebenkostenfix.jahresabrechnung import stand
from nebenkostenfix.models import (Heizungsanlage, Meter, MeterReading, Property,
                                   TenantBillingReport, db)
from nebenkostenfix.rechenkern import schaetzquoten
from tests import billing_factories as f
from tests.praxis import bestand
from tests.test_musterabrechnung import kategorien, musterhaus  # noqa: F401
from tests.test_praxisbestand import praxis  # noqa: F401

D = date
JAHR = 2024
HEUTE = D(2025, 6, 1)
VON, BIS = D(2024, 1, 1), D(2024, 12, 31)
GEMESSEN = ((D(2024, 1, 1), 0), (D(2025, 1, 1), 300))
EINE_ABLESUNG = ((D(2024, 1, 1), 0),)


@pytest.fixture
def haus(app_ctx):
    h = f.house('Haus S')
    h.abrechnungsjahr_beginn = '01-01'
    db.session.commit()
    return h


def _anlage(h, name='Zentralheizung', versorgt=heizung.HEIZUNG, **angaben):
    a = Heizungsanlage(property_id=h.id, name=name, versorgt=versorgt,
                       verbrauchsanteil_prozent=heizung.ANTEIL_VORGABE, **angaben)
    db.session.add(a)
    db.session.commit()
    r = f.invoice(h, f.category('Heizung'), 1000, VON, BIS, invoice_number=f'GAS-{a.id}')
    r.heizungsanlage_id, r.heizkostenart = a.id, 'brennstoff'
    db.session.commit()
    return a


def _wohnung(h, name, qm, *, mieter=True, **kw):
    w = f.apt(h, name, qm, **kw)
    if mieter:
        f.tenant(w, f'Mieter {name}', D(2023, 1, 1))
    return w


def _zaehler(h, w, anlage, staende, nummer=None, art='Heizung', ersetzt=None):
    z = f.meter(h, f.category(art), nummer or f'{art[0]}-{w.name}', is_main=False, apartment=w)
    z.heizungsanlage_id, z.ersetzt_id = anlage.id, ersetzt
    db.session.commit()
    for tag, wert in staende:
        f.reading(z, tag, wert)
    return z


def _befunde(h):
    return [b for b in stand(h.id, JAHR, HEUTE)['pruefstand'] if b['art'] == 'schaetzquote']


def _einziger(h):
    befunde = _befunde(h)
    assert len(befunde) == 1, befunde
    return befunde[0]


def _quoten(h):
    mieter = [t for w in h.apartments for t in w.tenants][0]
    ids = {a.id for a in Heizungsanlage.query.filter_by(property_id=h.id)}
    return schaetzquoten(lade_vorgang(mieter.id, VON, BIS), ids, VON, BIS)


def _zwei(h, qm_gut, qm_luecke, staende=EINE_ABLESUNG, **anlage):
    a = _anlage(h, **anlage)
    _zaehler(h, _wohnung(h, 'A', qm_gut), a, GEMESSEN)
    z = _zaehler(h, _wohnung(h, 'B', qm_luecke), a, staende)
    return a, z


def test_alles_gemessen_keine_warnung(haus):
    a = _anlage(haus)
    for name in ('A', 'B'):
        _zaehler(haus, _wohnung(haus, name, 50), a, GEMESSEN)
    assert _befunde(haus) == []


# --- (a) Warmwasserzähler gehören nicht in die Wärme-Quote ----------------------


def test_warmwasserzaehler_zaehlt_nicht_zur_waerme(haus):
    a = _anlage(haus)
    for name in ('A', 'B'):
        w = _wohnung(haus, name, 50)
        _zaehler(haus, w, a, GEMESSEN)
    # Ein Warmwasserzähler an der reinen Heizung, fast ohne Ablesung.
    _zaehler(haus, w, a, EINE_ABLESUNG, art='Warmwasser')
    assert _befunde(haus) == []


def test_verbundene_anlage_je_zweck_getrennt(haus):
    a = _anlage(haus, versorgt=heizung.VERBUNDEN, warmwasser_weg='formel',
                warmwasser_volumen_m3=100, warmwasser_temperatur_c=50,
                brennstoff_menge=40000)
    for name, warm in (('A', GEMESSEN), ('B', EINE_ABLESUNG)):
        w = _wohnung(haus, name, 50)
        _zaehler(haus, w, a, GEMESSEN)
        _zaehler(haus, w, a, warm, art='Warmwasser')
    b = _einziger(haus)
    assert b['text'].startswith('Heizungsanlage „Zentralheizung“, Warmwasserverbrauch: ')
    assert 'Für 50 von 100 m² (50,0 %)' in b['text']


# --- (b) je Anlage, mit dem Nenner der Abrechnung -------------------------------


def test_selbstversorger_nicht_im_nenner(haus):
    _zwei(haus, 50, 20)
    _wohnung(haus, 'S', 30, selbstversorger=True)
    b = _einziger(haus)
    assert 'Für 20 von 70 m² (28,6 %)' in b['text']
    assert 'mehr als ein Viertel' in b['text']


def test_zwei_anlagen_getrennt(haus):
    vorn = _anlage(haus, 'Vorderhaus')
    hinten = _anlage(haus, 'Hinterhaus')
    _zaehler(haus, _wohnung(haus, 'V1', 50), vorn, GEMESSEN)
    _zaehler(haus, _wohnung(haus, 'V2', 50), vorn, EINE_ABLESUNG)
    for name in ('H1', 'H2'):
        _zaehler(haus, _wohnung(haus, name, 100), hinten, GEMESSEN)
    b = _einziger(haus)
    assert b['text'].startswith('Heizungsanlage „Vorderhaus“, Wärmeverbrauch: ')
    assert 'Für 50 von 100 m² (50,0 %)' in b['text']


# --- (c) Zählerwechsel ist keine Schätzung --------------------------------------


def test_zaehlerwechsel_ist_keine_schaetzung(haus):
    a = _anlage(haus)
    _zaehler(haus, _wohnung(haus, 'A', 50), a, GEMESSEN)
    w = _wohnung(haus, 'B', 50)
    # Der neue Zähler allein deckte nur 92 Tage: erst die Kette misst das Jahr.
    alt = _zaehler(haus, w, a, ((D(2024, 1, 1), 100), (D(2024, 10, 1), 250)), 'H-alt')
    _zaehler(haus, w, a, ((D(2024, 10, 1), 0), (D(2025, 1, 1), 50)), 'H-neu', ersetzt=alt.id)
    assert _befunde(haus) == []


# --- (d) ungerundet verglichen ---------------------------------------------------


def test_254_von_1000_ist_ueberschritten(haus):
    _zwei(haus, 746, 254)
    [q] = _quoten(haus)
    assert q['quote'] == Decimal('25.4') and q['ueberschritten']
    b = _einziger(haus)
    assert '(25,4 %)' in b['text'] and 'mehr als ein Viertel' in b['text']


def test_genau_ein_viertel_ist_nicht_ueberschritten(haus):
    _zwei(haus, 750, 250)
    [q] = _quoten(haus)
    assert q['quote'] == 25 and not q['ueberschritten']
    b = _einziger(haus)
    assert '(25,0 %)' in b['text'] and 'Bis zu einem Viertel' in b['text']
    assert 'ausschließlich nach Fläche' not in b['text']
    assert 'So schätzt die App nicht: sie setzt ohne zwei Ablesungen 0 an.' in b['text']


def test_luecke_bis_ein_viertel_sagt_hochrechnen_ohne_widerspruch(haus):
    # Die Lücke rechnet der Kern hoch -- „die App schätzt nicht“ wäre falsch.
    _zwei(haus, 80, 20, ((D(2024, 1, 1), 0), (D(2024, 3, 1), 50)))
    text = _einziger(haus)['text']
    assert 'den Rest rechnet die Abrechnung hoch' in text
    assert 'schätzt aber nicht selbst' not in text
    assert ('aus vergleichbaren früheren Zeiträumen oder Räumen. So schätzt die App '
            'nicht: sie rechnet Lücken nach Tagen bzw. Gradtagen hoch.') in text
    assert 'setzt ohne zwei Ablesungen 0 an' not in text


def test_knapp_ueber_ein_viertel_erscheint_nicht_als_25(haus):
    # 2501/10000 = 25,01 % -- kaufmännisch gerundet stünde „25,0 %“ da.
    _zwei(haus, 7499, 2501)
    b = _einziger(haus)
    assert '(25,1 %)' in b['text'] and 'mehr als ein Viertel' in b['text']


# --- (e) Randversatz ist erfasst, eine echte Lücke nicht ------------------------


def test_randversatz_ueber_sieben_tage_ist_erfasst(haus):
    _zwei(haus, 50, 50, ((D(2024, 1, 9), 20), (D(2024, 12, 23), 280)))
    assert _befunde(haus) == []


def test_luecke_ueber_den_halben_zeitraum_ist_nicht_erfasst(haus):
    _zwei(haus, 50, 50, ((D(2024, 1, 1), 0), (D(2024, 3, 1), 50)))
    b = _einziger(haus)
    assert 'B: die Ablesungen von Zähler H-B decken nur 60 von 366 Tagen' in b['text']
    assert 'den Rest rechnet die Abrechnung hoch' in b['text']


def test_genau_die_haelfte_abgedeckt_ist_erfasst(haus):
    _zwei(haus, 50, 50, ((D(2024, 1, 1), 0), (D(2024, 7, 2), 150)))
    assert _befunde(haus) == []


def test_waermezaehler_misst_die_haelfte_nach_gradtagen(haus):
    # 152 von 366 Tagen, aber rund 58 % des Jahreswärmebedarfs: erfasst.
    _zwei(haus, 50, 50, ((D(2024, 1, 1), 0), (D(2024, 6, 1), 200)))
    assert _befunde(haus) == []


def test_waermezaehler_ohne_winteranfang_ist_nicht_erfasst(haus):
    # 244 von 366 Tagen, aber unter der Hälfte der Gradtage: überwiegend hochgerechnet.
    _zwei(haus, 50, 50, ((D(2024, 5, 1), 0), (D(2024, 12, 31), 120)))
    assert 'decken nur 244 von 366 Tagen' in _einziger(haus)['text']


def test_warmwasser_misst_die_haelfte_nach_tagen(haus):
    a = _anlage(haus, versorgt=heizung.WARMWASSER)
    _zaehler(haus, _wohnung(haus, 'A', 50), a, GEMESSEN, art='Warmwasser')
    _zaehler(haus, _wohnung(haus, 'B', 50), a, ((D(2024, 1, 1), 0), (D(2024, 6, 1), 20)),
             art='Warmwasser')
    assert 'decken nur 152 von 366 Tagen' in _einziger(haus)['text']


# --- (f) und (g) die Texte sagen, was die App tut --------------------------------


def test_text_nennt_die_null_statt_einer_schaetzung(haus):
    _zwei(haus, 50, 50)
    b = _einziger(haus)
    assert 'ohne jede Ablesung' not in b['text']
    assert ('B: Zähler H-B hat weniger als zwei Ablesungen, die Abrechnung setzt dort '
            'keinen Verbrauch an') in b['text']


def test_ueber_einem_viertel_kein_versprechen_und_keine_sackgasse(haus):
    _, z = _zwei(haus, 50, 50)
    b = _einziger(haus)
    assert 'Das kann die App noch nicht – verschicken Sie die Abrechnung' in b['text']
    assert b['tun'] == ('Tragen Sie die fehlenden Ablesungen nach oder prüfen Sie die '
                        'Zählerstände.')
    assert b['ziel'] == {'aktion': 'ablesung', 'id': z.id}


# --- Grenzfälle -----------------------------------------------------------------


def test_leerstand_mit_ablesungen_ist_erfasst(haus):
    a = _anlage(haus)
    _zaehler(haus, _wohnung(haus, 'A', 50), a, GEMESSEN)
    _zaehler(haus, _wohnung(haus, 'Leer', 50, mieter=False), a, GEMESSEN)
    assert _befunde(haus) == []


def test_leerstand_ohne_ablesungen_zaehlt_mit(haus):
    a = _anlage(haus)
    _zaehler(haus, _wohnung(haus, 'A', 50), a, GEMESSEN)
    _zaehler(haus, _wohnung(haus, 'Leer', 50, mieter=False), a, EINE_ABLESUNG)
    assert 'Für 50 von 100 m²' in _einziger(haus)['text']


def test_mieterwechsel_ohne_zwischenablesung_ist_keine_schaetzung(haus):
    a = _anlage(haus)
    _zaehler(haus, _wohnung(haus, 'A', 50), a, GEMESSEN)
    w = _wohnung(haus, 'B', 50, mieter=False)
    f.tenant(w, 'Erste', D(2023, 1, 1), D(2024, 6, 30))
    f.tenant(w, 'Zweite', D(2024, 7, 1))
    _zaehler(haus, w, a, GEMESSEN)
    assert _befunde(haus) == []


def test_anlage_ohne_verbrauchsverteilung_warnt_hier_nicht(haus):
    # Ohne Zähler in B verteilt der Kern die ganze Masse nach Fläche und warnt selbst.
    a = _anlage(haus)
    _zaehler(haus, _wohnung(haus, 'A', 50), a, GEMESSEN)
    _wohnung(haus, 'B', 50)
    assert _befunde(haus) == []


def test_gar_nichts_gemessen_warnt_hier_nicht(haus):
    a = _anlage(haus)
    for name in ('A', 'B'):
        _zaehler(haus, _wohnung(haus, name, 50), a, EINE_ABLESUNG)
    assert _befunde(haus) == []


def test_ohne_flaeche_keine_quote(haus):
    _zwei(haus, 0, 0)
    assert _befunde(haus) == []


def test_ohne_anlage_und_ohne_mieter_nichts(haus):
    _zaehler(haus, _wohnung(haus, 'A', 50, mieter=False), _anlage(haus), EINE_ABLESUNG)
    assert _befunde(haus) == []
    Heizungsanlage.query.delete()
    assert _befunde(haus) == []


def test_warnung_aendert_nichts(haus):
    _zwei(haus, 50, 50)
    vorher = (Meter.query.count(), MeterReading.query.count())
    assert _befunde(haus)
    assert (Meter.query.count(), MeterReading.query.count()) == vorher
    assert TenantBillingReport.query.count() == 0


def test_route_liefert_den_befund(haus, auth_client):
    _zwei(haus, 50, 50)
    antwort = auth_client.get(f'/api/jahresabrechnung?property_id={haus.id}&jahr={JAHR}')
    assert antwort.status_code == 200
    assert antwort.get_json()['pruefstand'][0]['art'] == 'schaetzquote'


# --- dieselben Daten wie die Abrechnung -----------------------------------------


def test_musterhaus_ohne_warnung(musterhaus):
    haus = Property.query.filter_by(name='Musterweg 1').one()
    assert _befunde(haus) == []


def test_nenner_gleich_wie_in_der_abrechnung(musterhaus):
    # W4 verliert seine Endablesung: Wärme nicht erfasst, Warmwasser schon.
    haus = Property.query.filter_by(name='Musterweg 1').one()
    w4 = Meter.query.filter_by(meter_number='W-W4').one()
    MeterReading.query.filter_by(meter_id=w4.id, reading_date=D(2025, 1, 1)).delete()
    db.session.commit()

    zeilen = musterhaus['abrechnung'](musterhaus['anna'])['line_items']
    details = {d['zweck']: d for d in (
        z['heizung_details'] for z in zeilen if z.get('heizung_details'))}
    [q] = _quoten(haus)
    assert q['zweck'] == heizung.HEIZUNG and details[heizung.HEIZUNG]['erfasst']
    assert q['gesamt_qm'] == details[heizung.HEIZUNG]['total_sqm'] == 200
    assert details[heizung.HEIZUNG]['apartments'] == 4
    assert [w['wohnung'] for w in q['wohnungen']] == ['Kellerwohnung']
    assert 'Für 50 von 200 m² (25,0 %)' in _einziger(haus)['text']


def test_dieselben_zaehler_wie_in_der_abrechnung(musterhaus, monkeypatch):
    # Beide holen ihre Zähler aus demselben Helfer -- und bekommen dieselben.
    from nebenkostenfix import rechenkern
    w4 = Meter.query.filter_by(meter_number='W-W4').one()
    MeterReading.query.filter_by(meter_id=w4.id, reading_date=D(2025, 1, 1)).delete()
    db.session.commit()
    echt, gesehen = rechenkern.anlagen_zweckzaehler, []

    def spion(vorgang, anlage_id, zweck, ids):
        zaehler = echt(vorgang, anlage_id, zweck, ids)
        gesehen.append((anlage_id, zweck, sorted(z.id for z in zaehler.values())))
        return zaehler
    monkeypatch.setattr(rechenkern, 'anlagen_zweckzaehler', spion)

    musterhaus['abrechnung'](musterhaus['anna'])
    in_abrechnung, gesehen[:] = list(gesehen), []
    [q] = _quoten(Property.query.filter_by(name='Musterweg 1').one())
    assert gesehen and in_abrechnung
    assert all(g in in_abrechnung for g in gesehen)
    [ids] = [z for a, zweck, z in gesehen if (a, zweck) == (q['anlage_id'], q['zweck'])]
    assert {w['zaehler_id'] for w in q['wohnungen']} <= set(ids)


def test_praxisbestand_ohne_schaetzquote(praxis):
    for h in Property.query.all():
        for jahr in range(bestand.HEUTE.year - 2, bestand.HEUTE.year + 1):
            befunde = stand(h.id, jahr, bestand.HEUTE)['pruefstand']
            assert not [b for b in befunde if b['art'] == 'schaetzquote'], (h.name, jahr)
