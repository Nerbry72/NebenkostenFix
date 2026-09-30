"""Die Abwasserkopplung misst am Frischwasser des Objekts (NK-055, D-56).

Abwasser hat keinen Zaehler: gemessen wird, was an den Frischwasserzaehlern
des Objekts hineingeht. Bis NK-055 suchte die Kopplung den Namen ueber den
ganzen Bestand -- und traf dabei auch Kostenarten, die an keinem Zaehler
des Objekts haengen, oder Warmwasserzaehler, die den Warmwasseranteil
des § 8 HeizkostenV messen, nicht das Frischwasser (IST-Stand, Risiko 7).

Die Faelle dieser Datei:

* Die Kopplung nimmt nur Kostenarten, die an **dieser** Immobilie einen
  Zaehler haben (App-Schicht, Lader).
* Warmwasser scheidet als Frischwassertraeger aus, Schmutz- und
  Niederschlagswasser ebenso.
* Findet sich am Objekt kein Frischwasserzaehler, bleibt die Kopplung leer
  und die Vorpruefung stellt eine nicht-blockierende Kachel -- die
  Abwasserkosten werden sonst still unbebilligt.
* Mit Anknuepfung rechnet die Abwasserposition am Frischwasserzaehler.

Jede Zahl ist von Hand nachgerechnet und steht im Test.
"""

from datetime import date
from decimal import Decimal

from nebenkostenfix.rechenkern import (
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    pruefe,
)

JAHR_BEGINN = date(2026, 1, 1)
JAHR_ENDE = date(2026, 12, 31)
JAHR_GRENZE = date(2027, 1, 1)

ABWASSER = Kategorie(id=2, name='Abwasser', braucht_zaehler=False)
FRISCHWASSER = Kategorie(id=3, name='Wasserversorgung', braucht_zaehler=True)


# --- AK: die Vorpruefungs-Kachel fuer das fehlende Frischwasser --------------

def abwasserhaus(**kw):
    """Ein Haus ohne Frischwasserzaehler, Abwasser wird abgerechnet."""
    links = Wohnung(id=1, name='EG links', qm=50.0)
    ich = Mieter(
        id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None,
        wohnung_id=1)
    grund = dict(
        mieter=ich,
        wohnung=links,
        immobilie_id=1,
        immobilie_name='Entwaesserungshaus',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=(links,),
        mieter_der_immobilie=(ich,),
        profile={ABWASSER.id: 'nur_allgemein'},
        rechnungen=(Rechnung(
            id=1, kategorie=ABWASSER, betrag=Decimal('300.00'),
            beginn=JAHR_BEGINN, ende=JAHR_ENDE),),
        zaehler=(),
        zahlungen=(),
        heizungsanlagen=(),
        wasser_kategorie_id=None,
    )
    grund.update(kw)
    return Vorgang(**grund)


def abwasserkachel(checks):
    kacheln = [c for c in checks
               if c.get('meter_type') == 'Frischwasser'
               and 'Abwasser' in c.get('category', '')]
    return kacheln[0] if kacheln else None


def test_ohne_frischwasserzaehler_warnt_die_vorpruefung():
    """Die Kachel nennt die Ursache -- ohne zu blockieren."""
    ergebnis = pruefe(abwasserhaus())
    kachel = abwasserkachel(ergebnis['checks'])

    assert kachel is not None
    assert kachel['status'] == 'no_data'
    assert kachel['blocking'] is False
    assert 'Frischwasserzähler' in kachel['message']
    assert kachel['apartment'] == 'EG links'


def test_die_kachel_erscheint_nur_einmal():
    """Zwei Abwasserrechnungen, ein Hinweis: die Kostenart wird gemeldet, nicht der Beleg."""
    rechnungen = (
        Rechnung(id=1, kategorie=ABWASSER, betrag=Decimal('300.00'),
                 beginn=JAHR_BEGINN, ende=JAHR_ENDE),
        Rechnung(id=2, kategorie=ABWASSER, betrag=Decimal('150.00'),
                 beginn=JAHR_BEGINN, ende=JAHR_ENDE),
    )
    ergebnis = pruefe(abwasserhaus(rechnungen=rechnungen))

    frischwasser_kacheln = [c for c in ergebnis['checks']
                            if c.get('meter_type') == 'Frischwasser']
    assert len(frischwasser_kacheln) == 1


def test_mit_anknuepfung_rechnet_abwasser_am_frischwasser():
    """Besteht die Kopplung, bleibt die Vorpruefung still und prueft den Zaehler.

    Der Frischwasserzaehler des Objekts (Hauptzaehler, 0 -> 100 m³) wird zur
    Abwassermenge; die Position verteilt 300,00 EUR auf die Wohnflaeche
    (nur_allgemein), nach Personentagen je die Haelfte.
    """
    vorgang = abwasserhaus(
        zaehler=(Zaehler(
            id=10, nummer='W-HAUPT', kategorie_id=FRISCHWASSER.id,
            kategorie_name='Wasserversorgung', ist_hauptzaehler=True,
            immobilie_id=1, staende=(
                Stand(datum=JAHR_BEGINN, wert=0.0),
                Stand(datum=JAHR_GRENZE, wert=100.0))),),
        wasser_kategorie_id=FRISCHWASSER.id,
    )
    ergebnis = pruefe(vorgang)

    assert abwasserkachel(ergebnis['checks']) is None
    kacheln = [c for c in ergebnis['checks'] if c.get('category') == 'Abwasser']
    assert not [k for k in kacheln if k.get('status') == 'no_data'], ergebnis['checks']


# --- AK: die Kopplung findet das Frischwasser des Objekts -------------------

from billing_factories import apt, house, meter, tenant  # noqa: E402


def test_die_kopplung_nimmt_nur_zaehler_des_objekts(app_ctx):
    """Zwei Objekte, zwei Frischwasserkategorien: jede haelt sich an ihre."""
    from nebenkostenfix.models import CostCategory, db
    from nebenkostenfix.abrechnungsdaten import _wasser_kategorie_id

    ost = house(name='Osthaus')
    west = house(name='Westhaus')
    wasser_ost = CostCategory(name='Wasser Ost', allocation_method='units',
                              requires_meter=True, betrkv_nr=2)
    db.session.add(wasser_ost)
    db.session.commit()
    wng = apt(ost, 'Ost-EG', 50.0)
    mieter = tenant(wng, 'Ostmieter', move_in=date(2024, 1, 1))

    meter(ost, wasser_ost, 'W-OST-1', is_main=True)

    vorgang_wasser = _wasser_kategorie_id(ost.id)
    assert vorgang_wasser == wasser_ost.id
    # Am Westhaus haengt kein Frischwasserzaehler: keine Kopplung.
    assert _wasser_kategorie_id(west.id) is None

    from nebenkostenfix.abrechnungsdaten import lade_vorgang
    vorgang = lade_vorgang(mieter.id, JAHR_BEGINN, JAHR_ENDE)
    assert vorgang.wasser_kategorie_id == wasser_ost.id


def test_warmwasser_ist_kein_frischwasser(app_ctx):
    """Der Warmwasserzaehler misst § 8, nicht den Abwasserfuss."""
    from nebenkostenfix.models import CostCategory, db
    from nebenkostenfix.abrechnungsdaten import _wasser_kategorie_id

    haus = house(name='Kopplungshaus')
    warm = CostCategory(name='Warmwasser Ost', allocation_method='units',
                        requires_meter=True, betrkv_nr=5)
    frisch = CostCategory(name='Kaltwasser Ost', allocation_method='units',
                          requires_meter=True, betrkv_nr=2)
    db.session.add_all([warm, frisch])
    db.session.commit()
    wng = apt(haus, 'K-EG', 50.0)
    tenant(wng, 'Kopplungsmieter', move_in=date(2024, 1, 1))

    # Warmwasser haengt frueher im Katalog und bekaeme die Kopplung sonst,
    # weil es dem Namen nach zuerst passt.
    meter(haus, warm, 'WW-1', is_main=False)
    meter(haus, frisch, 'KW-1', is_main=True)

    assert _wasser_kategorie_id(haus.id) == frisch.id


def test_schmutz_und_niederschlag_sind_kein_frischwasser(app_ctx):
    """Schmutzwasser und Niederschlagswasser sind Abwasserposten, keine Messung."""
    from nebenkostenfix.models import CostCategory, db
    from nebenkostenfix.abrechnungsdaten import _wasser_kategorie_id

    haus = house(name='Rinnenhaus')
    schmutz = CostCategory(name='Schmutzwasser Nord', allocation_method='units',
                           requires_meter=True, betrkv_nr=3)
    regen = CostCategory(name='Niederschlagswasser Nord',
                         allocation_method='units', requires_meter=True,
                         betrkv_nr=3)
    db.session.add_all([schmutz, regen])
    db.session.commit()
    wng = apt(haus, 'R-EG', 50.0)
    tenant(wng, 'Rinnenmieter', move_in=date(2024, 1, 1))
    meter(haus, schmutz, 'SW-1', is_main=True)
    meter(haus, regen, 'RW-1', is_main=True)

    assert _wasser_kategorie_id(haus.id) is None
