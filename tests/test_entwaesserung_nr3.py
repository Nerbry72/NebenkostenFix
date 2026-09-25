"""NK-114: die Entwässerung (Nr. 3) rechnet am Frischwasser.

Befund aus dem Live-Abgleich (Phase 6, NK-110/NK-111, Klasse B — Fehler im
neuen Stand): Seit dem Katalog (NK-044) heißt die Nr. 3 „Entwässerung“. Der
Rechenkern erkannte das Abwasser aber am Namen („abwasser“,
„schmutzwasser“). Eine Rechnung der Nr. 3 mit der Umlageart ``direkt`` fand
darum den Umweg über den Frischwasserzähler nicht (D-56), und die Position
stand still mit 0,00 im Bericht — der Vermieter blieb auf den Kosten sitzen.
``app.py`` hatte „entwäss“ mit NK-044 nachgezogen, der Rechenkern nicht.

Jetzt entscheidet die Katalognummer (``ist_abwasser``): Nr. 3 ist Abwasser,
außer dem Niederschlagswasser. Ohne Nummer (Proben ohne Katalog) bleibt der
Name die Auskunft, jetzt auch mit „entwäss“.

*Hätte diesen Fehler gefunden:* ``test_entwaesserung_rechnet_auf_dem_frischwasserzaehler``
— vor dem Fix kam dort 0,00 heraus.

Die Daten sind synthetisch; jede Zahl ist von Hand nachgerechnet.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from rechenkern import (
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    einheit_fuer,
    ist_abwasser,
    pruefe,
    rechne,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)

FRISCHWASSER = Kategorie(id=2, name='Wasserversorgung', braucht_zaehler=True,
                         betrkv_nr=2)
ENTWAESSERUNG = Kategorie(id=3, name='Entwässerung', braucht_zaehler=False,
                          betrkv_nr=3)


# --- Die Erkennung ----------------------------------------------------------


@pytest.mark.parametrize('name, nr, erwartet', [
    ('Entwässerung', 3, True),
    ('Kanalgebühren', 3, True),
    ('Schmutzwasser', 3, True),
    ('Niederschlagswasser', 3, False),
    ('Wasserversorgung', 2, False),
    # Die Nummer schlägt den Namen: ein Frischwasserposten „Wasser/Abwasser“
    # der Nr. 2 misst an seinen eigenen Zählern.
    ('Wasser/Abwasser', 2, False),
    # Ohne Katalognummer bleibt der Name die Auskunft.
    ('Abwasser', None, True),
    ('Schmutzwasser', None, True),
    ('Entwässerung', None, True),
    ('Niederschlagsabwasser', None, False),
    ('Hausmeister', None, False),
])
def test_ist_abwasser(name, nr, erwartet):
    kat = Kategorie(id=9, name=name, braucht_zaehler=False, betrkv_nr=nr)
    assert ist_abwasser(kat) is erwartet


def test_entwaesserung_misst_in_kubikmetern():
    assert einheit_fuer('Entwässerung') == 'm³'


# --- Der Rechenweg ----------------------------------------------------------


def _zaehler(id, haupt=False, wohnung_id=None, bis=0.0):
    return Zaehler(
        id=id, nummer=f'W-{id}', kategorie_id=FRISCHWASSER.id,
        kategorie_name=FRISCHWASSER.name, ist_hauptzaehler=haupt,
        immobilie_id=1, wohnung_id=wohnung_id,
        staende=(Stand(JAHR_BEGINN, 0.0), Stand(JAHR_ENDE, bis)))


def _vorgang(kat=ENTWAESSERUNG, **kw):
    """Ein Mieter in einer von zwei 50-qm-Wohnungen, Frischwasser 60 von 100 m³."""
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    andere = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = Mieter(id=1, name='Anna Mieterin', einzug=date(2020, 1, 1),
                 auszug=None, wohnung_id=1)
    grund = dict(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Rinnenhaus',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(meine, andere),
        mieter_der_immobilie=(ich,),
        profile={kat.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=kat, betrag=Decimal('1000.00'),
                             beginn=JAHR_BEGINN, ende=JAHR_ENDE),),
        zaehler=(_zaehler(10, haupt=True, bis=100.0),
                 _zaehler(11, wohnung_id=1, bis=60.0)),
        wasser_kategorie_id=FRISCHWASSER.id,
    )
    grund.update(kw)
    return Vorgang(**grund)


def test_entwaesserung_rechnet_auf_dem_frischwasserzaehler():
    """60 von 100 m³ eigen, der Rest ist Allgemein und geht beim einzigen
    Mieter ebenfalls an ihn: 1000,00 EUR. Vor NK-114 stand hier 0,00."""
    posten = rechne(_vorgang())['line_items'][0]

    assert posten['tenant_cost'] == Decimal('1000.00')
    assert 'Eigenverbrauch' in posten['description']
    assert posten['meter_details'] is not None


def test_nr3_unter_eigenem_namen_misst_in_kubikmetern():
    """Der Name trägt kein „wasser“ — die Einheit folgt trotzdem dem Frischwasser."""
    kanal = Kategorie(id=3, name='Kanalgebühren', braucht_zaehler=False,
                      betrkv_nr=3)
    posten = rechne(_vorgang(kat=kanal))['line_items'][0]

    assert posten['tenant_cost'] == Decimal('1000.00')
    assert 'm³' in posten['description']
    assert 'Einheiten' not in posten['description']


def test_niederschlagswasser_der_nr3_bleibt_vom_zaehler_fern():
    """Niederschlagswasser geht nach Fläche, nicht nach Frischwasser."""
    regen = Kategorie(id=3, name='Niederschlagswasser', braucht_zaehler=False,
                      betrkv_nr=3)
    posten = rechne(_vorgang(kat=regen))['line_items'][0]

    assert posten['meter_details'] is None
    assert 'Eigenverbrauch' not in posten['description']


# --- Die Vorprüfung ---------------------------------------------------------


def test_vorpruefung_folgt_der_entwaesserung_auf_den_wasserzaehler():
    ergebnis = pruefe(_vorgang())

    assert [c['meter_type'] for c in ergebnis['checks']] == [
        'Hauptzähler', 'Wohnungszähler']
    assert all(c['category'] == 'Entwässerung' for c in ergebnis['checks'])


def test_entwaesserung_ohne_frischwasser_zeigt_die_kachel():
    """Ohne Anknüpfung meldet die Vorprüfung es, statt still 0,00 zu rechnen."""
    ergebnis = pruefe(_vorgang(zaehler=(), wasser_kategorie_id=None))

    kacheln = [c for c in ergebnis['checks']
               if c.get('meter_type') == 'Frischwasser']
    assert len(kacheln) == 1
    assert kacheln[0]['category'] == 'Entwässerung'
    assert kacheln[0]['blocking'] is False


# --- Der Lader reicht die Nummer durch ----------------------------------------

from billing_factories import (  # noqa: E402
    apt, house, invoice, meter, profile, reading, tenant)


def test_lader_und_rechenweg_mit_dem_katalog(app_ctx):
    """Der ganze Weg über die Datenbank, mit den Kostenarten des Katalogs."""
    from abrechnungsdaten import lade_vorgang
    from models import CostCategory

    wasser = CostCategory.query.filter_by(betrkv_nr=2).first()
    entwaesserung = CostCategory.query.filter_by(betrkv_nr=3).first()
    haus = house(name='Rinnenhaus')
    links = apt(haus, 'EG links', 50.0)
    apt(haus, 'EG rechts', 50.0)
    anna = tenant(links, 'Anna Mieterin', move_in=date(2020, 1, 1))
    profile(anna, entwaesserung, 'direkt')
    invoice(haus, entwaesserung, 1000.00)
    haupt = meter(haus, wasser, 'W-HAUPT', is_main=True)
    eigen = meter(haus, wasser, 'W-EG-L', is_main=False, apartment=links)
    for z, bis in ((haupt, 100.0), (eigen, 60.0)):
        reading(z, JAHR_BEGINN, 0.0)
        reading(z, JAHR_ENDE, bis)

    vorgang = lade_vorgang(anna.id, JAHR_BEGINN, JAHR_ENDE)
    kat = vorgang.rechnungen[0].kategorie
    assert kat.betrkv_nr == 3
    assert vorgang.wasser_kategorie_id == wasser.id

    posten = rechne(vorgang)['line_items'][0]
    assert posten['tenant_cost'] == Decimal('1000.00')
