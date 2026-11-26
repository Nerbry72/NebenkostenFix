"""Import: Zählerstände, die es nicht geben kann.

Die Handeingabe (``POST /api/readings`` -> ``_ablesung_pruefen``, NK-216)
lehnt hart ab, „was nie stimmen kann“: einen negativen Stand (HT oder NT)
und ein Ablesedatum in der Zukunft -- 400, auch mit ``trotzdem``. Der
Tabellenimport der Zählerstände prüft beides nicht und schreibt solche
Stände fest. Ein negativer Stand geht als Verbrauch (Stand minus Vorstand)
direkt in die Umlage der Wohnung; ein Stand vom 31.12.2099 wird zum
Endstand jeder künftigen Abrechnung.

Erwartet: ein Zeilenfehler an der Zeile, nichts übernommen -- wie bei den
anderen harten Absagen des Imports (Niedertarif am Eintarifzähler, Stand
vor dem Wechseltag). „Heute“ ist der Tag in Berlin (``nebenkostenfix.zeit``),
wie in der Handeingabe. Nur fiktive Daten (Fixture ``haus`` aus
test_tabellenimport: „Musterhaus Lindenstraße“, Zähler „WZ-10442“; dazu ein
Zweitarifzähler „SZ-20001“).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from tests.test_tabellenimport import _csv, _lauf, _lesen, haus  # noqa: F401

KOPF = 'Immobilie;Zählernummer;Ablesedatum;Stand;Stand Niedertarif;Zwischenablesung'


def _uebernehmen(client, *zeilen):
    gelesen = _lesen(client, 'zaehlerstaende', _csv(KOPF, *zeilen))
    return _lauf(client, 'zaehlerstaende', gelesen, 'uebernehmen')


def _staende():
    from nebenkostenfix.models import MeterReading
    return sorted((r.meter.meter_number, r.reading_date, r.value, r.value_nt)
                  for r in MeterReading.query.all())


def _feld(fehler):
    return [(f['zeile'], f['meldung'].split(':')[0]) for f in fehler]


@pytest.fixture
def strom(haus):  # noqa: F811
    """Dasselbe Haus mit einem Zweitarifzähler (HT/NT)."""
    from nebenkostenfix.models import CostCategory, Meter, Property, db
    hausrecord = Property.query.filter_by(name='Musterhaus Lindenstraße').one()
    kostenart = CostCategory.query.filter(CostCategory.name.ilike('%strom%')).first() \
        or CostCategory.query.first()
    db.session.add(Meter(property_id=hausrecord.id, category_id=kostenart.id,
                         meter_number='SZ-20001', is_main_meter=True, has_dual_tariff=True))
    db.session.commit()
    return haus


@pytest.fixture
def heute_26_11(monkeypatch):
    """Fester Zeitpunkt: 26.11.2026, 12:00 UTC (in Berlin derselbe Tag)."""
    from nebenkostenfix import zeit
    monkeypatch.setattr(zeit, 'jetzt_utc', lambda: datetime(2026, 11, 26, 12, 0, 0))


# --- Negative Stände -------------------------------------------------------------

def test_negativer_stand_wird_abgelehnt(haus):  # noqa: F811
    antwort = _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;31.12.2024;-1284,5;;nein')
    bericht = antwort.get_json()
    assert _staende() == [], (
        f'Ein negativer Zählerstand wurde per Import gespeichert: {_staende()}')
    assert antwort.status_code == 400 and bericht['uebernommen'] is False
    assert [f['zeile'] for f in bericht['fehler']] == [2]
    meldung = bericht['fehler'][0]['meldung']
    assert meldung.split(':')[0] == 'Stand', meldung
    assert 'negativ' in meldung, meldung


def test_probelauf_meldet_den_negativen_stand_schon(haus):  # noqa: F811
    """„Prüfen“ zeigt den Fehler, bevor jemand übernimmt."""
    inhalt = _csv(KOPF, 'Musterhaus Lindenstraße;WZ-10442;31.12.2024;-0,5;;nein')
    bericht = _lauf(haus, 'zaehlerstaende', _lesen(haus, 'zaehlerstaende', inhalt)).get_json()
    assert _feld(bericht['fehler']) == [(2, 'Stand')]
    assert bericht['fehlerfrei'] == 0
    assert _staende() == []


def test_negativer_nt_stand_wird_abgelehnt(strom):
    antwort = _uebernehmen(strom, 'Musterhaus Lindenstraße;SZ-20001;31.12.2024;1500;-10;nein')
    bericht = antwort.get_json()
    assert _staende() == [], (
        f'Ein negativer NT-Stand wurde per Import gespeichert: {_staende()}')
    assert antwort.status_code == 400 and bericht['uebernommen'] is False
    assert _feld(bericht['fehler']) == [(2, 'Stand Niedertarif')]
    assert 'negativ' in bericht['fehler'][0]['meldung'], bericht['fehler']


def test_negativer_ht_stand_am_zweitarifzaehler_wird_abgelehnt(strom):
    antwort = _uebernehmen(strom, 'Musterhaus Lindenstraße;SZ-20001;31.12.2024;-1500;800;nein')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert _feld(antwort.get_json()['fehler']) == [(2, 'Stand')]
    assert _staende() == []


def test_ein_negativer_stand_haelt_die_ganze_datei_auf(haus):  # noqa: F811
    antwort = _uebernehmen(haus,
                           'Musterhaus Lindenstraße;WZ-10442;30.06.2024;1100;;nein',
                           'Musterhaus Lindenstraße;WZ-10442;31.12.2024;-1284,5;;nein')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert _feld(bericht['fehler']) == [(3, 'Stand')]
    assert bericht['fehlerfrei'] == 1 and bericht['uebernommen'] is False
    assert _staende() == []


# --- Ablesedatum in der Zukunft --------------------------------------------------

def test_ablesedatum_in_der_zukunft_wird_abgelehnt(haus):  # noqa: F811
    antwort = _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;31.12.2099;1284,5;;nein')
    bericht = antwort.get_json()
    assert _staende() == [], (
        f'Ein Stand mit Ablesedatum in der Zukunft wurde per Import gespeichert: {_staende()}')
    assert antwort.status_code == 400 and bericht['uebernommen'] is False
    assert [f['zeile'] for f in bericht['fehler']] == [2]
    meldung = bericht['fehler'][0]['meldung']
    assert meldung.startswith('Ablesedatum'), meldung
    assert 'Zukunft' in meldung, meldung


def test_morgen_ist_abgelehnt(haus, heute_26_11):  # noqa: F811
    antwort = _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;27.11.2026;1284,5;;nein')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert _feld(antwort.get_json()['fehler']) == [(2, 'Ablesedatum')]
    assert _staende() == []


def test_heute_ist_erlaubt(haus, heute_26_11):  # noqa: F811
    antwort = _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;26.11.2026;1284,5;;nein')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert _staende() == [('WZ-10442', date(2026, 11, 26), 1284.5, None)]


def test_heute_gilt_der_tag_in_berlin(haus, monkeypatch):  # noqa: F811
    """26.11.2026, 23:30 UTC ist in Berlin schon der 27.11. (MEZ, +1 Stunde).

    Der Server-Tag (UTC) wäre noch der 26.; abgelesen am 27. ist also
    erlaubt, der 28. liegt in der Zukunft.
    """
    from nebenkostenfix import zeit
    monkeypatch.setattr(zeit, 'jetzt_utc', lambda: datetime(2026, 11, 26, 23, 30, 0))
    zukunft = _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;28.11.2026;1284,5;;nein')
    assert zukunft.status_code == 400, zukunft.get_data(as_text=True)
    assert _feld(zukunft.get_json()['fehler']) == [(2, 'Ablesedatum')]
    heute = _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;27.11.2026;1284,5;;nein')
    assert heute.status_code == 200, heute.get_data(as_text=True)
    assert _staende() == [('WZ-10442', date(2026, 11, 27), 1284.5, None)]


def test_zukunft_als_excel_datumszelle_wird_abgelehnt(haus):  # noqa: F811
    import io

    import openpyxl
    mappe = openpyxl.Workbook()
    blatt = mappe.active
    blatt.append(KOPF.split(';'))
    blatt.append(['Musterhaus Lindenstraße', 'WZ-10442', datetime(2099, 12, 31), 1284.5, None,
                  'nein'])
    puffer = io.BytesIO()
    mappe.save(puffer)
    gelesen = _lesen(haus, 'zaehlerstaende', puffer.getvalue(), 'staende.xlsx')
    antwort = _lauf(haus, 'zaehlerstaende', gelesen, 'uebernehmen')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert _feld(antwort.get_json()['fehler']) == [(2, 'Ablesedatum')]
    assert _staende() == []


# --- Gegenproben: was bisher ging, geht weiter -----------------------------------

def test_stand_null_und_fruehere_daten_werden_uebernommen(haus):  # noqa: F811
    antwort = _uebernehmen(haus,
                           'Musterhaus Lindenstraße;WZ-10442;01.01.2024;0;;nein',
                           'Musterhaus Lindenstraße;WZ-10442;31.12.2024;1284,5;;nein')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['uebernommen'] is True
    assert _staende() == [('WZ-10442', date(2024, 1, 1), 0.0, None),
                          ('WZ-10442', date(2024, 12, 31), 1284.5, None)]


def test_nt_stand_null_am_zweitarifzaehler_wird_uebernommen(strom):
    antwort = _uebernehmen(strom, 'Musterhaus Lindenstraße;SZ-20001;31.12.2024;1500;0;nein')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert _staende() == [('SZ-20001', date(2024, 12, 31), 1500.0, 0.0)]


def test_bekannte_fehler_bleiben(haus):  # noqa: F811
    assert _uebernehmen(haus, 'Musterhaus Lindenstraße;WZ-10442;31.12.2024;1284,5;;nein'
                        ).status_code == 200
    antwort = _uebernehmen(haus,
                           'Musterhaus Lindenstraße;WZ-10442;31.12.2024;1300;;nein',
                           'Musterhaus Lindenstraße;WZ-10442;30.06.2024;1100;400;nein')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    meldungen = {f['zeile']: f['meldung'] for f in antwort.get_json()['fehler']}
    assert meldungen == {
        2: 'Ablesedatum: für 31.12.2024 gibt es schon einen Stand.',
        3: 'Stand Niedertarif: der Zähler hat nur einen Tarif.',
    }
    assert _staende() == [('WZ-10442', date(2024, 12, 31), 1284.5, None)]
