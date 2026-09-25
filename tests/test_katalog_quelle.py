"""Der Katalog ist die einzige Quelle fuer Einheit, Rubrik und Bereich.

NK-121 (F-32/F-51): fuenf Stellen rieten die Rubrik aus dem Namen -- vier
Stichwortlisten nebeneinander, die nichts voneinander wussten. Seit dieser
Karte entscheidet die BetrKV-Nummer aus ``betrkv``; ein Name ohne Nummer
geht durch ``zuordnung``, dieselbe Vermutung wie beim Einspielen eines
Altbestands.

Der Parametertest laeuft ueber alle 18 Katalogeintraege (17 Nummern, die
Nr. 3 doppelt) und nimmt die verbundene Anlage (Nr. 6) ausdruecklich
heraus: ihr Name enthaelt „Warmwasser", ihr Zaehler misst trotzdem
Kilowattstunden. Genau diese Verwechslung machte aus dem Wärmezähler des
§ 7 einen Warmwasserzähler des § 8 (F-51).
"""

from __future__ import annotations

import pytest

import betrkv
import rechenkern
from rechenkern import Kategorie, Zaehler, einheit_fuer, ist_warmwasserzaehler


def test_ueber_all_18_eintraege_ist_die_einheit_katalogsache(eintrag):
    """Einheit und Einheit_fuer sagen dasselbe -- aus der Nummer."""
    assert betrkv.einheit(eintrag['nr']) in ('kWh', 'm³', 'Einheiten')
    assert einheit_fuer(eintrag['name'], eintrag['nr']) \
        == betrkv.einheit(eintrag['nr'])


def test_ueber_all_18_eintraege_sagt_die_analytics_dasselbe(eintrag):
    """Rubrik, Einheit und Bereich der Analytics kommen aus dem Katalog.

    app.py traegt die drei Zuordnungen als duenne Aufrufe; die Pruefung
    laeuft ueber die Funktionen und nicht ueber eine Route, denn die
    Rueckreise durch die Datenbank wuerde nur Wasser transportieren.
    """
    from app import _get_unit, _map_category, _map_to_bucket

    nr = eintrag['nr']
    assert _map_category(eintrag['name']) == betrkv.rubrik(nr)
    assert _get_unit(eintrag['name']) == betrkv.einheit(nr)
    assert _map_to_bucket(eintrag['name']) == betrkv.bereich(nr)


def test_ueber_all_18_eintraege_sagen_analytics_und_kern_dasselbe(eintrag):
    """Die Einheit der Analytics ist die des Rechenkerns (F-51).

    Vorher nannte die Analytics fuer „Heizung“ „Einheiten“, der Kern
    Kilowattstunden -- dieselbe Kostenart, zwei Aussagen.
    """
    from app import _get_unit

    name, nr = eintrag['name'], eintrag['nr']
    assert _get_unit(name) == einheit_fuer(name, nr)


def test_ueber_all_18_eintraege_zaehlt_die_einheit_zum_posten(eintrag):
    """Umlagefreie Posten tragen die neutrale Einheit, Zählerposten ihre.

    Heizung und Warmwasser bekommen keinen Pflichtzähler (Katalog), aber
    wer einen anschliesst, misst Waermemenge (kWh) -- nicht „Einheiten“.
    """
    nr = eintrag['nr']
    if nr in (betrkv.NR_HEIZUNG, betrkv.NR_VERBUNDENE_ANLAGE,
              betrkv.NR_ALLGEMEINSTROM):
        assert betrkv.einheit(nr) == 'kWh'
    elif nr in (2, 3, 5):
        assert betrkv.einheit(nr) == 'm³'


def test_die_verbundene_anlage_ist_kein_warmwasserzaehler():
    """F-51: ihr Wärmezähler misst kWh, obwohl „Warmwasser“ im Namen steht.

    Der Zaehler der Nr. 6 zaehlt Wärmemenge (§ 7), der Warmwasserzähler
    derselben Anlage traegt die Nr. 5 und zaehlt Kubikmeter (§ 8). Vorher
    entschied „warmwasser“ im Namen -- beide Zaehler landeten im selben
    Topf und die Aufteilung war vertauscht.
    """
    name = 'Heizung und Warmwasser (verbundene Anlage)'
    assert betrkv.einheit(betrkv.NR_VERBUNDENE_ANLAGE) == 'kWh'
    assert einheit_fuer(name, betrkv.NR_VERBUNDENE_ANLAGE) == 'kWh'
    assert ist_warmwasserzaehler(
        _zaehler(name, betrkv.NR_VERBUNDENE_ANLAGE)) is False


def test_der_warmwasserzaehler_der_anlage_traegt_die_nr_5():
    """Und der Warmwasserzähler derselben Anlage bleibt beim Kubikmeter."""
    name = 'Warmwasser'
    assert betrkv.einheit(betrkv.NR_WARMWASSER) == 'm³'
    assert ist_warmwasserzaehler(
        _zaehler(name, betrkv.NR_WARMWASSER)) is True
    assert ist_warmwasserzaehler(
        _zaehler('Heizung', betrkv.NR_HEIZUNG)) is False


@pytest.mark.parametrize('nr,ist_warmwasser', [
    (4, False), (5, True), (6, False), (11, False), (17, False),
])
def test_nur_der_kubikmeter_des_warmwassers_zaehlt_fuer_paragraf_8(
        nr, ist_warmwasser):
    """Die Trennung § 7 / § 8 haengt allein an der Einheit aus dem Katalog."""
    kat = Kategorie(id=1, name=betrkv.bezeichnung(nr),
                    braucht_zaehler=False, betrkv_nr=nr)
    assert ist_warmwasserzaehler(
        _zaehler(kat.name, nr, kategorie_id=kat.id)) is ist_warmwasser


def test_jeder_kubikmeterzaehler_an_der_anlage_zaehlt_fuer_paragraf_8():
    """Die Regel bleibt eine Einheitsregel, keine Namensregel.

    An der Heizungsanlage zählen die Kubikmeter das Warmwasser -- gleich,
    welche Kostenart davor steht. Die verbundene Anlage ist der Fall,
    der die Regel braucht: ihr Wärmezähler heisst „Warmwasser“ und misst
    trotzdem Kilowattstunden.
    """
    assert ist_warmwasserzaehler(
        _zaehler('Wasserversorgung', 2)) is True
    assert ist_warmwasserzaehler(
        _zaehler('Entwässerung', 3)) is True


def test_ohne_nummer_raet_der_name_weiter():
    """Der Rueckfallweg fuer Proben ohne Katalog bleibt, wie er war.

    Er rät schlechter -- für die verbundene Anlage „m³“ -- und lebt nur,
    damit der Kern auch ohne Seed lesbar bleibt. Der Weg der Datenbank
    laeuft ueber die Nummer; der Lader in abrechnungsdaten traegt sie mit.
    """
    assert einheit_fuer('Heizung') == 'kWh'
    assert einheit_fuer('Warmwasser') == 'm³'
    assert einheit_fuer('Entwässerung') == 'm³'
    assert einheit_fuer('Gas') == 'm³'
    assert einheit_fuer('') == 'Einheiten'


def test_der_lader_traegt_die_katalognummer_in_den_zaehler():
    """``_zaehler`` in abrechnungsdaten liest die Nummer der Kostenart."""
    from types import SimpleNamespace

    from abrechnungsdaten import _zaehler

    meter = SimpleNamespace(
        id=7, meter_number='W-07', category_id=3,
        category=SimpleNamespace(name='Heizung', betrkv_nr=4),
        is_main_meter=True, property_id=1, apartment_id=None,
        heizungsanlage_id=None)
    geladen = _zaehler(meter, [])
    assert geladen.kategorie_betrkv_nr == 4
    assert einheit_fuer(geladen.kategorie_name,
                        geladen.kategorie_betrkv_nr) == 'kWh'
    assert ist_warmwasserzaehler(geladen) is False

    meter.category.betrkv_nr = 5
    assert ist_warmwasserzaehler(_zaehler(meter, [])) is True


def _zaehler(name: str, nr, kategorie_id: int = 1) -> Zaehler:
    """Ein Zaehler wie ihn der Lader baut: mit Name und Katalognummer."""
    return Zaehler(
        id=1, nummer='W-01', kategorie_id=kategorie_id, kategorie_name=name,
        ist_hauptzaehler=False, immobilie_id=1,
        kategorie_betrkv_nr=nr)


def pytest_generate_tests(metafunc):
    """Eine Fall je Katalogeintrag, benannt nach der Bezeichnung."""
    if 'eintrag' in metafunc.fixturenames:
        metafunc.parametrize('eintrag', betrkv.KATALOG,
                             ids=[e['name'] for e in betrkv.KATALOG])
