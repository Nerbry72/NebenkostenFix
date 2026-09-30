"""NK-044: der Katalog des § 2 BetrKV, an seinem einen Ort geprueft.

Drei Dinge stehen hier auf dem Pruefstand:

1. der Katalog selbst -- siebzehn Nummern, keine mehr, keine weniger, und
   jede mit einer Bezeichnung, die der Vermieter lesen kann,
2. ``pruefe()`` und ``normiere()`` -- was durchgeht, was abgelehnt wird, und
   dass das Normieren nur Transportrauschen wegnimmt,
3. ``zuordnung()`` -- die Vermutung, mit der der Altbestand seine Nummer
   bekommt. Sie ist die einzige Stelle der Karte, die Daten anfasst, die
   jemand selbst eingetragen hat; ein falscher Treffer hier steht spaeter in
   einer Abrechnung.
"""

from __future__ import annotations

import doctest

import pytest

from nebenkostenfix import betrkv
from nebenkostenfix.betrkv import (
    BEZEICHNUNGEN,
    KATALOG,
    NUMMERN,
    SONSTIGE,
    BetrKVFehler,
    beschriftung,
    bezeichnung,
    ist_gueltig,
    ist_sonstige,
    katalogeintrag,
    normiere,
    pruefe,
    zuordnung,
)


def test_doctests_im_modul_laufen():
    ergebnis = doctest.testmod(betrkv, verbose=False)
    assert ergebnis.failed == 0, f'{ergebnis.failed} von {ergebnis.attempted} Doctests fehlgeschlagen'


# --- Der Katalog ---

def test_genau_siebzehn_nummern():
    """§ 2 BetrKV zaehlt abschliessend auf. Achtzehn waeren erfunden."""
    assert sorted(NUMMERN) == list(range(1, 18))


def test_jede_nummer_hat_eine_bezeichnung():
    for nr in NUMMERN:
        assert BEZEICHNUNGEN[nr].strip(), f'Nr. {nr} ohne Bezeichnung'


def test_keine_bezeichnung_doppelt():
    """Zwei gleich benannte Posten waeren in der Auswahlliste nicht zu unterscheiden."""
    assert len(set(BEZEICHNUNGEN.values())) == len(BEZEICHNUNGEN)


def test_sonstige_ist_die_letzte():
    assert SONSTIGE == 17
    assert SONSTIGE == max(NUMMERN)


def test_seed_deckt_jede_nummer_und_nur_nr_3_doppelt():
    """Jede Nummer mindestens einmal; zweimal nur die Nr. 3 (NK-117, D-72)."""
    nummern = [p['nr'] for p in KATALOG]
    assert sorted(set(nummern)) == list(range(1, 18))
    doppelt = sorted({nr for nr in nummern if nummern.count(nr) > 1})
    assert doppelt == [3]
    assert nummern.count(3) == 2


def test_niederschlagswasser_ist_eigener_eintrag_nach_flaeche():
    """Schmutzwasser nach Zaehler, Niederschlagswasser nach qm (NK-117).

    Liegen beide auf einer Kostenart, rechnet eine der beiden falsch: das
    war die Abweichungsgruppe G1 des Live-Abgleichs (Phase 6).
    """
    nr3 = {p['name']: p for p in KATALOG if p['nr'] == 3}
    assert set(nr3) == {'Entwässerung', 'Niederschlagswasser'}
    assert nr3['Entwässerung']['verteilung'] == 'METER_READING'
    assert nr3['Niederschlagswasser']['verteilung'] == 'PER_SQM'
    assert nr3['Niederschlagswasser']['zaehler'] is False


@pytest.mark.parametrize('name, erwartet', [
    ('Abwasser', 'Entwässerung'),
    ('Schmutzwasser', 'Entwässerung'),
    ('Kanalgebühr', 'Entwässerung'),
    ('Niederschlagswasser', 'Niederschlagswasser'),
    ('Regenwasser', 'Niederschlagswasser'),
    ('Oberflächenwasser', 'Niederschlagswasser'),
    ('Strom', 'Beleuchtung (Allgemeinstrom)'),
    ('Wasser', 'Wasserversorgung'),
    ('Dachterrasse', 'Sonstige Betriebskosten'),
])
def test_katalogeintrag_unterscheidet_die_nr_3(name, erwartet):
    assert katalogeintrag(name)['name'] == erwartet


def test_seed_namen_sind_eindeutig():
    """``cost_categories.name`` traegt seit NK-095 ein UNIQUE."""
    namen = [p['name'] for p in KATALOG]
    assert len(set(namen)) == len(namen)


def test_seed_namen_passen_in_die_spalte():
    """``name`` ist ``String(100)``."""
    for posten in KATALOG:
        assert len(posten['name']) <= 100, posten['name']


def test_seed_kennt_nur_die_drei_umlagewege():
    for posten in KATALOG:
        assert posten['verteilung'] in ('PER_SQM', 'PER_ACTIVE_HEAD', 'METER_READING')
        assert isinstance(posten['zaehler'], bool)


def test_heizung_und_warmwasser_verlangen_keinen_zaehler():
    """Sie werden nach HeizkostenV verteilt, nicht ueber einen Wohnungszaehler.

    Bis NK-049 das Modul baut, waere ``zaehler=True`` eine Behauptung, die
    die Anwendung nicht einloesen kann.
    """
    for posten in KATALOG:
        if posten['nr'] in (4, 5, 6):
            assert posten['zaehler'] is False, posten['name']


# --- pruefe / normiere / ist_gueltig ---

@pytest.mark.parametrize('nr', sorted(NUMMERN))
def test_jede_katalognummer_geht_durch(nr):
    assert pruefe(nr) == nr


@pytest.mark.parametrize('wert', [0, 18, -1, 100])
def test_nummern_ausserhalb_werden_abgelehnt(wert):
    with pytest.raises(BetrKVFehler):
        pruefe(wert)


@pytest.mark.parametrize('wert', [None, '', 'Aufzug', [7], {7}, 7.0])
def test_was_keine_nummer_ist_wird_abgelehnt(wert):
    with pytest.raises(BetrKVFehler):
        pruefe(wert)


def test_wahr_ist_keine_nummer():
    """``True`` ist in Python eine 1 -- in dieser Spalte waere es ein Fehler."""
    assert not ist_gueltig(True)
    with pytest.raises(BetrKVFehler):
        pruefe(True)


def test_meldung_nennt_die_kostenart_und_den_bereich():
    with pytest.raises(BetrKVFehler) as fehler:
        pruefe(18, kostenart='Kabelanschluss')
    text = str(fehler.value)
    assert 'Kabelanschluss' in text
    assert '18' in text
    assert '1 bis 17' in text


def test_meldung_ohne_kostenart_nennt_trotzdem_den_wert():
    with pytest.raises(BetrKVFehler) as fehler:
        pruefe(99)
    assert '99' in str(fehler.value)


@pytest.mark.parametrize('roh, erwartet', [
    (' 7 ', 7), ('7', 7), ('Nr. 7', 7), ('nr 17', 17), ('07', 7),
])
def test_normieren_nimmt_nur_rauschen_weg(roh, erwartet):
    assert normiere(roh) == erwartet


@pytest.mark.parametrize('roh', ['7 Aufzug', 'Aufzug', '17a', ''])
def test_normieren_deutet_nichts_um(roh):
    """Was neben der Zahl noch etwas aussagt, bleibt stehen und faellt durch."""
    assert normiere(roh) == roh
    with pytest.raises(BetrKVFehler):
        pruefe(roh)


def test_ist_gueltig_normiert_nicht():
    assert ist_gueltig(7)
    assert not ist_gueltig('7')


# --- Beschriftung ---

def test_beschriftung_nennt_nummer_und_sache():
    assert beschriftung(8) == 'Nr. 8 · Straßenreinigung und Müllbeseitigung'


def test_bezeichnung_lehnt_unbekannte_nummer_ab():
    with pytest.raises(BetrKVFehler):
        bezeichnung(18)


def test_ist_sonstige_trennt_den_offenen_posten():
    assert ist_sonstige(17)
    assert not ist_sonstige(1)
    assert not ist_sonstige(18)


# --- zuordnung: der Altbestand ---

@pytest.mark.parametrize('name, erwartet', [
    # Die acht Kostenarten des alten Seeds (app.py vor dieser Karte)
    ('Strom', 11),
    ('Wasser', 2),
    ('Abwasser', 3),
    ('Niederschlagswasser', 3),
    ('Gas', 4),
    ('Grundsteuer', 1),
    ('Gebäudeversicherung', 13),
    ('Sonstiges', 17),
])
def test_der_alte_seed_wird_vollstaendig_zugeordnet(name, erwartet):
    assert zuordnung(name) == erwartet


@pytest.mark.parametrize('name, erwartet', [
    ('Heizkosten', 4), ('Heizöl', 4), ('Fernwärme', 4), ('Pellets', 4),
    ('Warmwasser', 5), ('Warmwasseraufbereitung', 5),
    ('Aufzug', 7), ('Fahrstuhlwartung', 7),
    ('Müllabfuhr', 8), ('Straßenreinigung', 8), ('Winterdienst', 8),
    ('Treppenhausreinigung', 9), ('Ungezieferbekämpfung', 9),
    ('Gartenpflege', 10), ('Grünpflege', 10),
    ('Allgemeinstrom', 11), ('Beleuchtung Treppenhaus', 11),
    ('Schornsteinfeger', 12), ('Kaminkehrer', 12),
    ('Haftpflichtversicherung', 13), ('Sachversicherung', 13),
    ('Hausmeister', 14), ('Hauswart', 14),
    ('Kabelanschluss', 15), ('Antennenanlage', 15), ('Glasfaser', 15),
    ('Waschküche', 16), ('Wäschepflege', 16),
])
def test_gaengige_eigene_namen_finden_ihren_posten(name, erwartet):
    assert zuordnung(name) == erwartet


@pytest.mark.parametrize('name, erwartet', [
    ('Straßenreinigung', 8),        # nicht 9 (Reinigung)
    ('Schornsteinreinigung', 12),   # nicht 9 (Reinigung)
    ('Niederschlagswasser', 3),     # nicht 2 (Wasser)
    ('Warmwasser', 5),              # nicht 2 (Wasser)
    ('Abwasser', 3),                # nicht 2 (Wasser)
])
def test_das_genauere_wort_gewinnt(name, erwartet):
    """Sonst wird die Muellabfuhr zur Gebaeudereinigung und Regenwasser zur Wasserversorgung."""
    assert zuordnung(name) == erwartet


def test_gross_klein_und_umlaute_sind_egal():
    assert zuordnung('GRUNDSTEUER') == zuordnung('grundsteuer') == 1
    assert zuordnung('Gebaeudeversicherung') == zuordnung('Gebäudeversicherung') == 13
    assert zuordnung('Strassenreinigung') == zuordnung('Straßenreinigung') == 8


@pytest.mark.parametrize('name', ['Dachterrasse', 'Concierge', 'Sonstiges', 'xyz', '', '   ', None, 42])
def test_was_sich_nicht_zuordnen_laesst_wird_nr_17(name):
    """Der offene Posten ist der richtige Ort fuer das Unbekannte, nicht Nr. 1."""
    assert zuordnung(name) == SONSTIGE


def test_zuordnung_liefert_immer_eine_gueltige_nummer():
    for name in ['Strom', 'Quatsch', '', None, 'Müll', 'Wasser-Abrechnung 2024']:
        assert ist_gueltig(zuordnung(name))


@pytest.mark.parametrize('posten', KATALOG, ids=lambda p: p['name'])
def test_jeder_katalogname_ordnet_sich_seiner_eigenen_nummer_zu(posten):
    """Wer eine Seed-Kostenart loescht und neu anlegt, bekommt dieselbe Nummer.

    Der Fall, der das fast kippte: "Heizung und Warmwasser (verbundene
    Anlage)" enthaelt beide Woerter und landete auf Nr. 5. Deshalb steht
    "verbunden" in ``_SCHLUESSELWOERTER`` ganz oben.
    """
    getroffen = zuordnung(posten['name'])
    assert getroffen == posten['nr'], f"{posten['name']} -> {getroffen}, erwartet {posten['nr']}"


def test_die_verbundene_anlage_geht_nicht_an_warmwasser():
    assert zuordnung('Heizung und Warmwasser (verbundene Anlage)') == 6
    assert zuordnung('Verbundene Anlage') == 6
    assert zuordnung('Warmwasser') == 5
    assert zuordnung('Heizung') == 4
