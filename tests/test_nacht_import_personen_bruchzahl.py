"""Mieterimport: eine Personenzahl mit Nachkommastellen ist keine gültige
Eingabe. Heute schneidet der Import „2,5“ stillschweigend auf 2 ab
(int(float)) und legt die Haushaltsgröße so an. Die Personenzahl geht über
die Personentage (R-NUM-04) direkt in die Umlage ein; ein stilles Abrunden
verschiebt Geld zwischen den Mietern. Die Eingabe von Hand (validation
.ganzzahl) lehnt „2,5“ ab.

Erwartet: ein Zeilenfehler, der mit „Personen“ beginnt, und weil der Import
nur ohne Fehler festschreibt, kein Mieter und keine Haushaltsgröße aus dieser
Datei. Ganze Zahlen („2“, „2,0“, Excel-Zelle 2.0) gehen wie bisher durch.

Nur fiktive Daten (Fixture ``haus`` aus test_tabellenimport, Haus
„Testhaus Nachtweg“ mit W1 und W2).
"""

from __future__ import annotations

import io
from datetime import date

import pytest

from tests.test_tabellenimport import _csv, _lauf, _lesen, haus  # noqa: F401

KOPF = 'Immobilie;Wohnung;Name;Einzug;Auszug;Personen'


def test_personen_mit_nachkommastelle_wird_nicht_abgeschnitten(haus):
    from nebenkostenfix.models import Haushaltsgroesse, Tenant
    inhalt = _csv(KOPF, 'Musterhaus Lindenstraße;EG links;Erika Beispiel;01.01.2025;;2,5')
    gelesen = _lesen(haus, 'mieter', inhalt)
    antwort = _lauf(haus, 'mieter', gelesen, 'uebernehmen')
    gespeichert = [h.personenanzahl for h in Haushaltsgroesse.query.all()]
    assert gespeichert != [2], ('„2,5“ Personen wurden stillschweigend als 2 '
                                'übernommen')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert Tenant.query.count() == 0


# --- Testhaus Nachtweg -----------------------------------------------------------

@pytest.fixture
def nachtweg(auth_client):
    from nebenkostenfix.models import Apartment, Property, db
    haus = Property(name='Testhaus Nachtweg')
    db.session.add(haus)
    db.session.flush()
    db.session.add_all([Apartment(property_id=haus.id, name='W1', sqm=45),
                        Apartment(property_id=haus.id, name='W2', sqm=55)])
    db.session.commit()
    return auth_client


def _zaehlen():
    from nebenkostenfix.models import Haushaltsgroesse, Tenant
    return Tenant.query.count(), Haushaltsgroesse.query.count()


def _xlsx(*zeilen) -> bytes:
    import openpyxl
    mappe = openpyxl.Workbook()
    blatt = mappe.active
    blatt.append(KOPF.split(';'))
    for zeile in zeilen:
        blatt.append(list(zeile))
    puffer = io.BytesIO()
    mappe.save(puffer)
    return puffer.getvalue()


@pytest.mark.parametrize('wert', ['2,5', '1,9', '2.5'])
def test_bruchzahl_aus_csv_ist_ein_zeilenfehler(nachtweg, wert):
    inhalt = _csv(KOPF, f'Testhaus Nachtweg;W1;Mieter Bruch;01.03.2024;;{wert}')
    antwort = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt), 'uebernehmen')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert bericht['uebernommen'] is False
    assert [f['zeile'] for f in bericht['fehler']] == [2], bericht['fehler']
    meldung = bericht['fehler'][0]['meldung']
    assert meldung.startswith('Personen'), meldung
    assert 'ganze Zahl' in meldung and f'„{wert}“' in meldung, meldung
    assert _zaehlen() == (0, 0)


def test_probelauf_meldet_die_bruchzahl_schon(nachtweg):
    """Der Probelauf („Prüfen“) zeigt den Fehler, bevor jemand übernimmt."""
    inhalt = _csv(KOPF, 'Testhaus Nachtweg;W1;Mieter Bruch;01.03.2024;;2,5')
    bericht = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt)).get_json()
    assert [(f['zeile'], f['meldung'].split(':')[0]) for f in bericht['fehler']] == [
        (2, 'Personen')]
    assert bericht['fehlerfrei'] == 0
    assert _zaehlen() == (0, 0)


def test_eine_bruchzahl_haelt_die_ganze_datei_auf(nachtweg):
    inhalt = _csv(KOPF,
                  'Testhaus Nachtweg;W1;Mieter Eins;01.03.2024;;2',
                  'Testhaus Nachtweg;W2;Mieter Zwei;01.03.2024;;2,5')
    antwort = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt), 'uebernehmen')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert [f['zeile'] for f in bericht['fehler']] == [3], bericht['fehler']
    assert bericht['fehler'][0]['meldung'].startswith('Personen')
    assert bericht['fehlerfrei'] == 1
    assert _zaehlen() == (0, 0)


def test_excel_zelle_mit_2_5_ist_ein_zeilenfehler(nachtweg):
    inhalt = _xlsx(('Testhaus Nachtweg', 'W1', 'Mieter Bruch', date(2024, 3, 1), None, 2.5))
    gelesen = _lesen(nachtweg, 'mieter', inhalt, 'mieter.xlsx')
    antwort = _lauf(nachtweg, 'mieter', gelesen, 'uebernehmen')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    fehler = antwort.get_json()['fehler']
    assert [f['zeile'] for f in fehler] == [2], fehler
    assert fehler[0]['meldung'].startswith('Personen'), fehler
    assert _zaehlen() == (0, 0)


def test_tabellen_erfassung_mit_float_2_5_ist_ein_zeilenfehler(nachtweg):
    """Derselbe Prüfweg ohne Datei: der Rohwert 2.5 kommt als float an."""
    zeile = {'immobilie': 'Testhaus Nachtweg', 'wohnung': 'W1', 'name': 'Mieter Bruch',
             'einzug': '01.03.2024', 'personen': 2.5}
    antwort = nachtweg.post('/api/import/mieter/tabelle',
                            json={'zeilen': [zeile], 'uebernehmen': True})
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    fehler = antwort.get_json()['fehler']
    assert [f['zeile'] for f in fehler] == [1], fehler
    assert fehler[0]['meldung'].startswith('Personen'), fehler
    assert _zaehlen() == (0, 0)


# --- Gegenproben: was bisher ging, geht weiter -----------------------------------

@pytest.mark.parametrize('wert', ['2', '2,0', '2.0'])
def test_ganze_personenzahl_aus_csv_wird_uebernommen(nachtweg, wert):
    from nebenkostenfix.models import Tenant
    inhalt = _csv(KOPF, f'Testhaus Nachtweg;W1;Mieter Ganz;01.03.2024;;{wert}')
    antwort = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt), 'uebernehmen')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    mieter = Tenant.query.filter_by(name='Mieter Ganz').one()
    assert mieter.personenanzahl_am(date(2024, 6, 1)) == 2
    assert _zaehlen() == (1, 1)


def test_excel_zelle_mit_2_0_wird_uebernommen(nachtweg):
    from nebenkostenfix.models import Tenant
    inhalt = _xlsx(('Testhaus Nachtweg', 'W1', 'Mieter Ganz', date(2024, 3, 1), None, 2.0))
    antwort = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt, 'mieter.xlsx'),
                    'uebernehmen')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    mieter = Tenant.query.filter_by(name='Mieter Ganz').one()
    assert mieter.personenanzahl_am(date(2024, 6, 1)) == 2


def test_tabellen_erfassung_mit_float_2_0_wird_uebernommen(nachtweg):
    from nebenkostenfix.models import Tenant
    zeile = {'immobilie': 'Testhaus Nachtweg', 'wohnung': 'W2', 'name': 'Mieter Ganz',
             'einzug': '01.03.2024', 'personen': 2.0}
    antwort = nachtweg.post('/api/import/mieter/tabelle',
                            json={'zeilen': [zeile], 'uebernehmen': True})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert Tenant.query.filter_by(name='Mieter Ganz').one().personenanzahl_am(
        date(2024, 6, 1)) == 2


def test_leere_personenzelle_legt_keine_haushaltsgroesse_an(nachtweg):
    from nebenkostenfix.models import Tenant
    inhalt = _csv(KOPF, 'Testhaus Nachtweg;W1;Mieter Leer;01.03.2024;;')
    antwort = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt), 'uebernehmen')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert _zaehlen() == (1, 0)
    assert Tenant.query.one().personenanzahl_am(date(2024, 6, 1)) == 1


def test_null_personen_bleibt_mindestens_eins(nachtweg):
    inhalt = _csv(KOPF, 'Testhaus Nachtweg;W1;Mieter Null;01.03.2024;;0')
    antwort = _lauf(nachtweg, 'mieter', _lesen(nachtweg, 'mieter', inhalt), 'uebernehmen')
    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    fehler = antwort.get_json()['fehler']
    assert fehler == [{'zeile': 2, 'meldung': 'Personen: mindestens 1.'}]
    assert _zaehlen() == (0, 0)
