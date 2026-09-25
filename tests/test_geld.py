"""NK-036: Geld ist Decimal, und zwar bis in die Datenbank hinein (R-NUM-01).

Diese Datei prueft drei Dinge getrennt voneinander:

1. die Umwandlung selbst -- ``dec``, ``runde``, ``summe``,
2. den Weg durch eine echte SQLite-Datei und zurueck,
3. dass am Ende einer vollstaendigen Abrechnung an keiner Geldstelle mehr
   ein ``float`` steht.

Der dritte Punkt ist der eigentliche Waechter. Die ersten beiden koennten
gruen sein, waehrend irgendwo im Rechenkern ein ``round(x, 2)``
zurueckgeschlichen kommt.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select

from geld import (
    CENT,
    NULL,
    Geld,
    GeldFehler,
    dec,
    restcent_auf_letzte,
    runde,
    runde_einheitspreis,
    summe,
)


# --------------------------------------------------------------------------
# 1. Umwandlung
# --------------------------------------------------------------------------

def test_dec_reicht_ein_decimal_unveraendert_durch():
    betrag = Decimal("12.34")
    assert dec(betrag) is betrag


def test_dec_nimmt_den_float_so_wie_er_getippt_wurde():
    """Der Kern der Karte: repr() statt Decimal(float).

    ``Decimal(0.1)`` ist die Zahl, die die Maschine aus der Eingabe gemacht
    hat. ``dec(0.1)`` ist die, die der Vermieter getippt hat.
    """
    assert dec(0.1) == Decimal("0.1")
    assert Decimal(0.1) != Decimal("0.1")
    assert dec(0.1) + dec(0.2) == dec(0.3)
    assert 0.1 + 0.2 != 0.3  # die Gegenprobe, wegen der es diese Datei gibt


def test_dec_versteht_die_deutsche_schreibweise():
    assert dec("1.234,50") == Decimal("1234.50")
    assert dec("12,34") == Decimal("12.34")
    assert dec("  12.34  ") == Decimal("12.34")
    assert dec("-5,00") == Decimal("-5")
    assert dec("1 234,56") == Decimal("1234.56")


def test_dec_nimmt_ganze_zahlen():
    assert dec(7) == Decimal("7")
    assert dec(-7) == Decimal("-7")


@pytest.mark.parametrize(
    "unfug",
    [None, True, False, "abc", "", "  ", [1], {"a": 1}, object()],
)
def test_dec_weist_zurueck_was_kein_betrag_ist(unfug):
    with pytest.raises(GeldFehler):
        dec(unfug)


@pytest.mark.parametrize(
    "nicht_endlich",
    [float("inf"), float("-inf"), float("nan"), "inf", "nan", "-Infinity"],
)
def test_dec_weist_unendlich_und_nan_zurueck(nicht_endlich):
    """NaN kommt durch Decimal("nan") anstandslos herein -- und nie wieder heraus.

    Ein NaN in einem Betrag bleibt bis ins PDF stehen, ohne dass irgendwo
    etwas abbricht: jeder Vergleich mit ihm ist falsch, jede Summe wird NaN.
    Deshalb faellt es hier und nicht spaeter.
    """
    with pytest.raises(GeldFehler):
        dec(nicht_endlich)


def test_runde_ist_kaufmaennisch_und_nicht_pythons_vorgabe():
    """2,675 ist der Fall, an dem man den Unterschied sieht.

    ``round(2.675, 2)`` ergibt 2.67, weil 2.675 als float knapp unter 2,675
    liegt. Der Vermieter erwartet 2,68, so wie auf jedem Kassenbon.
    """
    assert runde("2,675") == Decimal("2.68")
    assert round(2.675, 2) == 2.67  # was ohne diese Datei herauskaeme
    assert runde("0,005") == Decimal("0.01")
    assert runde("0,004") == Decimal("0.00")


def test_runde_rundet_negative_betraege_symmetrisch():
    """Eine Gutschrift wird nicht anders gerundet als eine Nachzahlung."""
    assert runde("-0,005") == Decimal("-0.01")
    assert runde("-2,675") == Decimal("-2.68")


def test_runde_liefert_immer_zwei_stellen():
    assert str(runde(7)) == "7.00"
    assert runde(7).as_tuple().exponent == CENT.as_tuple().exponent


def test_runde_einheitspreis_haelt_vier_stellen():
    """Ein Cent je kWh waere zu grob, siehe geld.ZEHNTELCENT."""
    assert runde_einheitspreis("0,12345") == Decimal("0.1235")
    assert str(runde_einheitspreis(10)) == "10.0000"


def test_summe_faengt_bei_decimal_an_und_nicht_bei_int():
    leer = summe([])
    assert leer == NULL
    assert isinstance(leer, Decimal)


def test_summe_addiert_ohne_float_drift():
    assert summe([0.1] * 10) == Decimal("1.0")
    assert sum([0.1] * 10) != 1.0  # die Gegenprobe


def test_summe_reicht_fehler_durch():
    with pytest.raises(GeldFehler):
        summe([Decimal("1.00"), None])


# --------------------------------------------------------------------------
# 1b. Die Restcent-Regel R1 (NK-038, R-NUM-02)
# --------------------------------------------------------------------------

def test_restcent_der_fall_aus_dem_betrieb():
    """Zwei Posten, einzeln gerundet einen Cent ueber dem Zeilenbetrag."""
    teile = [Decimal("273.965"), Decimal("1577.255")]
    ziel = runde(summe(teile))          # 1851.22

    assert summe(runde(t) for t in teile) != ziel   # die Gegenprobe
    assert restcent_auf_letzte(teile, ziel) == [Decimal("273.97"), Decimal("1577.25")]


def test_restcent_trifft_den_letzten_posten_und_nicht_den_groessten():
    """Welcher Posten den Cent traegt, muss vorhersagbar sein (Ziel 4, NK-039)."""
    teile = [Decimal("1000.005"), Decimal("0.005")]
    assert restcent_auf_letzte(teile, runde(summe(teile))) == [
        Decimal("1000.01"),
        Decimal("0.00"),
    ]


def test_restcent_laesst_in_ordnung_was_in_ordnung_ist():
    teile = [Decimal("10.00"), Decimal("5.50")]
    assert restcent_auf_letzte(teile, Decimal("15.50")) == teile


def test_restcent_haelt_die_summe_bei_zufallszahlen_ein():
    wuerfel = random.Random(20260921)
    for _ in range(2000):
        teile = [
            Decimal(wuerfel.randrange(0, 10_000_000)).scaleb(-4)
            for _ in range(wuerfel.randint(1, 6))
        ]
        ziel = runde(summe(teile))
        angeglichen = restcent_auf_letzte(teile, ziel)
        assert summe(angeglichen) == ziel
        assert all(-t.as_tuple().exponent == 2 for t in angeglichen)


def test_restcent_auf_nichts_bleibt_nichts():
    assert restcent_auf_letzte([], Decimal("0.00")) == []


def test_restcent_weist_zurueck_was_kein_rundungsrest_ist():
    """Ein Rechenfehler weiter oben darf nicht auf einen Posten rutschen."""
    with pytest.raises(GeldFehler, match="kein Rundungsrest"):
        restcent_auf_letzte([Decimal("10.00")], Decimal("99.00"))


def test_restcent_nimmt_die_volle_toleranz_an():
    """Ein Cent je Posten ist die Grenze -- genau dort noch zulaessig."""
    teile = [Decimal("1.00"), Decimal("1.00")]
    assert restcent_auf_letzte(teile, Decimal("2.02")) == [
        Decimal("1.00"),
        Decimal("1.02"),
    ]
    with pytest.raises(GeldFehler):
        restcent_auf_letzte(teile, Decimal("2.03"))

# --------------------------------------------------------------------------
# 2. Der Weg durch SQLite
# --------------------------------------------------------------------------

def _betraege_fuer_den_rundlauf(anzahl=20000):
    """Grenzwerte zuerst, dann Zufall mit festem Keim."""
    werte = [
        Decimal("0.00"),
        Decimal("0.01"),
        Decimal("-0.01"),
        Decimal("0.10"),
        Decimal("9999999999.99"),   # Numeric(12, 2) voll ausgereizt
        Decimal("-9999999999.99"),
        Decimal("1234.56"),
    ]
    wuerfel = random.Random(20260921)
    werte += [
        Decimal(wuerfel.randrange(-999999999999, 999999999999)).scaleb(-2)
        for _ in range(anzahl - len(werte))
    ]
    return werte


def test_geld_spalte_ueberlebt_den_weg_durch_sqlite(tmp_path):
    """Zwanzigtausend Betraege hinein und zurueck, ohne eine einzige Abweichung.

    Gemessen wird an einer echten Datei, nicht im Speicher: der Umweg ueber
    den Treiber ist genau die Stelle, an der ein Decimal sonst still zu einem
    float wird. Der Kopfkommentar in geld.py behauptet, dass das verlustfrei
    ist -- hier steht der Beleg.
    """
    motor = create_engine(f"sqlite:///{tmp_path / 'rundlauf.db'}")
    tabelle = Table(
        "betraege", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("betrag", Geld, nullable=False),
    )
    tabelle.create(motor)

    werte = _betraege_fuer_den_rundlauf()
    with motor.begin() as verbindung:
        verbindung.execute(
            tabelle.insert(),
            [{"id": i, "betrag": w} for i, w in enumerate(werte)],
        )

    with motor.connect() as verbindung:
        zurueck = dict(
            verbindung.execute(select(tabelle.c.id, tabelle.c.betrag)).all()
        )

    abweichungen = [
        (i, werte[i], zurueck[i]) for i in range(len(werte)) if zurueck[i] != werte[i]
    ]
    assert abweichungen == [], f"{len(abweichungen)} von {len(werte)} abgewichen"
    assert all(isinstance(b, Decimal) for b in zurueck.values())


def test_geld_spalte_haelt_null_offen(tmp_path):
    motor = create_engine(f"sqlite:///{tmp_path / 'leer.db'}")
    tabelle = Table(
        "betraege", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("betrag", Geld, nullable=True),
    )
    tabelle.create(motor)
    with motor.begin() as verbindung:
        verbindung.execute(tabelle.insert(), [{"id": 1, "betrag": None}])
    with motor.connect() as verbindung:
        assert verbindung.execute(select(tabelle.c.betrag)).scalar() is None


def test_geld_spalte_rueckt_beim_schreiben_auf_cent(tmp_path):
    """Mehr als zwei Nachkommastellen kommen gar nicht erst in die Datenbank.

    Numeric(12, 2) wuerde auf einem anderen Motor stillschweigend abschneiden
    (0,005 -> 0,00). Hier wird stattdessen kaufmaennisch gerundet, und zwar
    an einer Stelle, die man nachlesen kann.
    """
    motor = create_engine(f"sqlite:///{tmp_path / 'cent.db'}")
    tabelle = Table(
        "betraege", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("betrag", Geld, nullable=False),
    )
    tabelle.create(motor)
    with motor.begin() as verbindung:
        verbindung.execute(
            tabelle.insert(),
            [{"id": 1, "betrag": Decimal("0.005")},
             {"id": 2, "betrag": 89.28999999999999}],
        )
    with motor.connect() as verbindung:
        zurueck = dict(verbindung.execute(select(tabelle.c.id, tabelle.c.betrag)).all())
    assert zurueck[1] == Decimal("0.01")
    assert zurueck[2] == Decimal("89.29")


# --------------------------------------------------------------------------
# 3. Der Waechter: kein float mehr an einer Geldstelle
# --------------------------------------------------------------------------

#: Schluessel, unter denen in einer Abrechnung ein Euro-Betrag steht.
GELDFELDER = {
    "amount",
    "balance",
    "cost",
    "cost_per_unit",
    "invoice_total_amount",
    "prepaid_amount",
    "prorated_amount",
    "tenant_cost",
    "total_amount",
}


def _geldstellen(knoten, pfad="bill"):
    """Laeuft durch die Abrechnung und gibt jede Geldstelle mit ihrem Pfad aus."""
    if isinstance(knoten, dict):
        for schluessel, wert in knoten.items():
            unterpfad = f"{pfad}[{schluessel!r}]"
            if schluessel in GELDFELDER and not isinstance(wert, (dict, list)):
                yield unterpfad, wert
            else:
                yield from _geldstellen(wert, unterpfad)
    elif isinstance(knoten, list):
        for i, wert in enumerate(knoten):
            yield from _geldstellen(wert, f"{pfad}[{i}]")


def test_keine_geldstelle_einer_abrechnung_ist_ein_float(app_ctx):
    """Der Waechter ueber den ganzen Rechenkern.

    Aufgebaut wird bewusst der unbequeme Fall: Zeitanteil (Einzug zur
    Jahresmitte), Quadratmeterschluessel, Personenschluessel, Zaehler mit
    Allgemeinverbrauch und Vorauszahlungen -- damit moeglichst jeder Zweig,
    der einen Betrag erzeugt, auch wirklich durchlaufen wird.
    """
    from datetime import date

    from billing_engine import BillingEngine
    from tests.billing_factories import (
        YEAR_END,
        YEAR_START,
        apt,
        category,
        house,
        invoice,
        meter,
        payment,
        profile,
        reading,
        tenant,
    )

    prop = house()
    a = apt(prop, "A", 50)
    b = apt(prop, "B", 100)
    t = tenant(a, "Mieter A", move_in=date(2024, 7, 1))
    tenant(b, "Mieter B")

    grund = category("Grundsteuer")
    profile(t, grund, "qm")
    invoice(prop, grund, 1200.0, invoice_number="G-1")

    vers = category("Gebäudeversicherung")
    profile(t, vers, "personen")
    invoice(prop, vers, 777.77, invoice_number="V-1")

    strom = category("Strom")
    profile(t, strom, "direkt")
    haupt = meter(prop, strom, "H-1", is_main=True)
    eigen = meter(prop, strom, "W-1", is_main=False, apartment=a)
    reading(haupt, YEAR_START, 0.0)
    reading(haupt, YEAR_END, 1000.0)
    reading(eigen, YEAR_START, 0.0)
    reading(eigen, YEAR_END, 333.0)
    invoice(prop, strom, 1001.01, invoice_number="S-1")

    payment(t, 150.0, date(2024, 8, 1), "Nebenkostenvorauszahlung")
    payment(t, 33.33, date(2024, 9, 1), "Nebenkostenvorauszahlung")

    bill = BillingEngine(t.id, YEAR_START, YEAR_END).calculate_bill()

    stellen = list(_geldstellen(bill))
    assert stellen, "keine Geldstelle gefunden -- der Waechter misst nichts"

    floats = [(p, w) for p, w in stellen if isinstance(w, float)]
    assert floats == [], f"float an einer Geldstelle: {floats}"

    for pfad, wert in stellen:
        assert wert is None or isinstance(wert, Decimal), f"{pfad}: {wert!r}"


def test_ein_betrag_kommt_als_decimal_aus_der_datenbank_zurueck(app_ctx):
    """Nicht nur im Rechenkern, auch ueber die Sitzung hinweg."""
    from models import CostInvoice, db
    from tests.billing_factories import category, house, invoice

    prop = house()
    cat = category("Grundsteuer")
    invoice(prop, cat, "1.234,56", invoice_number="D-1")
    db.session.commit()
    db.session.expire_all()

    geladen = CostInvoice.query.filter_by(invoice_number="D-1").one()
    assert geladen.amount == Decimal("1234.56")
    assert isinstance(geladen.amount, Decimal)


# --------------------------------------------------------------------------
# 4. Die Grenze nach aussen
# --------------------------------------------------------------------------
#
# Decimal im Kern und in der Datenbank, Zahl auf dem Draht. Das ist die
# Auslegung von R-NUM-01, die NK-036 getroffen hat, und sie ist eine
# Entscheidung, keine Selbstverstaendlichkeit: Flask serialisiert ein Decimal
# von sich aus als Zeichenkette ("12.34"), und static/app.js rechnet an
# 37 Stellen mit diesen Feldern weiter. In JavaScript ergibt "12.34" + "5.00"
# nicht 17.34, sondern "12.345.00" -- still, ohne Fehlermeldung, und kein Test
# dieses Projekts kaeme daran vorbei, weil es fuer das Frontend keine gibt.
# Verlustfrei ist der Weg, weil jeder ausgewiesene Betrag vorher auf Cent
# gerundet wurde und zwei Nachkommastellen in einem double exakt aufgehoben
# sind. Gerechnet wird trotzdem nirgends mehr auf dieser Seite der Grenze.

def test_ein_betrag_geht_als_zahl_ueber_die_json_grenze(auth_client):
    """Der GeldJSON-Provider aus app.py, an einer echten Route gemessen."""
    from models import db
    from tests.billing_factories import category, house

    prop = house()
    cat = category("Grundsteuer")
    db.session.commit()

    antwort = auth_client.post("/api/invoices", json={
        "category_id": cat.id,
        "property_id": prop.id,
        "amount": "1.234,57",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "invoice_number": "JSON-1",
    })
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    liste = auth_client.get("/api/invoices")
    assert liste.status_code == 200
    rohtext = liste.get_data(as_text=True)

    zeile = [r for r in liste.get_json() if r["invoice_number"] == "JSON-1"][0]
    assert zeile["amount"] == 1234.57
    assert isinstance(zeile["amount"], float)
    # Und nicht als Zeichenkette: das waere der stille Rueckfall.
    assert '"amount": 1234.57' in rohtext or '"amount":1234.57' in rohtext
    assert '"1234.57"' not in rohtext


def test_die_json_grenze_verliert_keinen_cent(auth_client):
    """Zweistellige Betraege ueberleben den Weg durch JSON unveraendert.

    Gegenprobe zur Entscheidung oben: waere die Rundung nicht vorher passiert,
    stuende hier der Beweis, dass float doch etwas verschluckt.
    """
    from models import db
    from tests.billing_factories import category, house

    prop = house()
    cat = category("Grundsteuer")
    db.session.commit()

    betraege = ["0,01", "0,10", "99,99", "1234,57", "999999,99", "8,70"]
    for nummer, betrag in enumerate(betraege, start=1):
        antwort = auth_client.post("/api/invoices", json={
            "category_id": cat.id,
            "property_id": prop.id,
            "amount": betrag,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "invoice_number": f"CENT-{nummer}",
        })
        assert antwort.status_code == 201, antwort.get_data(as_text=True)

    gelesen = {r["invoice_number"]: r["amount"] for r in auth_client.get(
        "/api/invoices").get_json()}
    for nummer, betrag in enumerate(betraege, start=1):
        erwartet = Decimal(betrag.replace(".", "").replace(",", "."))
        zurueck = Decimal(repr(gelesen[f"CENT-{nummer}"]))
        assert zurueck == erwartet, f"{betrag}: {zurueck}"
