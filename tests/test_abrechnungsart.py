"""NK-096: die fuenf Abrechnungsarten, an ihrem einen Ort geprueft (F-25).

Der Befund war, dass ein Wort, das es nicht gibt, eine ganze Kostenart
lautlos aus dem Blatt fallen liess. Diese Datei prueft drei Dinge:

1. die Pruefung selbst -- was durchgeht, was abgelehnt wird, und dass die
   Meldung den Vermieter zur richtigen Zeile fuehrt,
2. dass ``normiere()`` nur Transportrauschen wegnimmt und nichts umdeutet,
3. den Waechter ``test_rechenkern_behandelt_genau_die_fuenf_arten``: er
   vergleicht ``ARTEN`` mit den Zeichenketten, die der Rechenkern wirklich
   abfragt. Die ersten beiden Punkte koennten gruen sein, waehrend im Kern
   eine sechste Art auftaucht, die hier niemand kennt -- oder eine der fuenf
   dort verschwindet.
"""

from __future__ import annotations

import ast
import doctest
import pathlib
import re

import pytest

import abrechnungsart
from abrechnungsart import (
    ARTEN,
    ERSATZ,
    GUELTIG,
    VORGABE,
    AbrechnungsartFehler,
    aufzaehlung,
    ist_gueltig,
    normiere,
    pruefe,
)

WURZEL = pathlib.Path(__file__).resolve().parent.parent


# --- Was das Modul ueber sich selbst sagt -----------------------------------


def test_doctests_im_modul_laufen():
    """Die Beispiele im Modulkopf sind Zusagen, keine Illustration."""
    ergebnis = doctest.testmod(abrechnungsart, verbose=False)
    assert ergebnis.failed == 0, f'{ergebnis.failed} Doctests in abrechnungsart.py sind rot'


def test_vorgabe_und_ersatz_sind_selbst_gueltig():
    """Sonst wuerde ausgerechnet die Reparatur einen ungueltigen Wert setzen."""
    assert ist_gueltig(VORGABE)
    assert ist_gueltig(ERSATZ)


def test_ersatz_kostet_nichts():
    """Die Wanderung darf niemandem still Geld berechnen (D-30).

    ``ignoriert`` behaelt das bisherige Ergebnis -- kein Posten --, ``qm``
    wuerde es aendern. Deshalb ist der Ersatz ausdruecklich nicht die Vorgabe.
    """
    assert ERSATZ == 'ignoriert'
    assert ERSATZ != VORGABE


def test_gueltig_ist_genau_die_beschriftete_menge():
    """Kein Wert ohne Beschriftung -- die Oberflaeche liest aus derselben Liste."""
    assert GUELTIG == set(ARTEN)
    assert all(beschriftung.strip() for beschriftung in ARTEN.values())


# --- Die Pruefung -----------------------------------------------------------


@pytest.mark.parametrize('wert', ['qm', 'personen', 'direkt', 'nur_allgemein', 'ignoriert'])
def test_die_fuenf_gehen_durch(wert):
    assert pruefe(wert) == wert


@pytest.mark.parametrize('roh,erwartet', [
    ('  qm ', 'qm'),
    ('Qm', 'qm'),
    ('DIREKT', 'direkt'),
    ('direkt ', 'direkt'),
    ('\tNur_Allgemein\n', 'nur_allgemein'),
])
def test_transportrauschen_wird_weggenommen(roh, erwartet):
    """Ein Leerzeichen aus einem Formular ist keine Aussage (F-25)."""
    assert pruefe(roh) == erwartet


@pytest.mark.parametrize('wert', [
    'verbrauch',      # der Fall aus F-25: klingt richtig, gibt es nicht
    'flaeche',
    'qm2',
    '',
    '   ',
    None,
    0,
    ['qm'],
])
def test_alles_andere_wird_abgelehnt(wert):
    with pytest.raises(AbrechnungsartFehler):
        pruefe(wert)


def test_meldung_nennt_wert_kostenart_und_alle_erlaubten():
    """Der Vermieter soll wissen, welche Zeile gemeint ist und was geht."""
    with pytest.raises(AbrechnungsartFehler) as fehler:
        pruefe('verbrauch', kostenart='Wasser')
    text = str(fehler.value)
    assert 'Wasser' in text
    assert 'verbrauch' in text
    for wert in ARTEN:
        assert wert in text


def test_meldung_ohne_kostenart_bleibt_lesbar():
    with pytest.raises(AbrechnungsartFehler) as fehler:
        pruefe('verbrauch')
    assert 'verbrauch' in str(fehler.value)
    assert aufzaehlung() in str(fehler.value)


def test_fehler_ist_ein_valueerror():
    """Wer schon ``ValueError`` faengt, faengt das hier mit."""
    assert issubclass(AbrechnungsartFehler, ValueError)


# --- Normieren deutet nicht um ----------------------------------------------


def test_normieren_erfindet_nichts():
    """Aus einem falschen Wort wird kein richtiges -- nur Klein und getrimmt."""
    assert normiere('verbrauch') == 'verbrauch'
    assert not ist_gueltig(normiere('verbrauch'))


def test_normieren_geht_an_nicht_zeichenketten_vorbei():
    """Kein ``AttributeError`` statt einer Meldung -- ``pruefe()`` sagt es."""
    assert normiere(None) is None
    assert normiere(7) == 7


def test_ist_gueltig_normiert_nicht():
    """Was in der Datenbank steht, muss exakt stimmen -- sonst waere die
    CHECK-Bedingung im Schema Theater."""
    assert ist_gueltig('qm')
    assert not ist_gueltig('Qm')
    assert not ist_gueltig(' qm')


# --- Der Waechter -----------------------------------------------------------


def _billing_type_literale(quelle: str) -> set[str]:
    """Alle Zeichenketten, mit denen ``quelle`` eine Abrechnungsart vergleicht.

    Gelesen wird der Syntaxbaum, nicht der Text: gesucht sind Vergleiche
    ``billing_type == '...'`` und ``billing_type in [...]`` -- genau die
    Stellen, an denen der Kern eine Art behandelt.
    """
    baum = ast.parse(quelle)
    gefunden: set[str] = set()

    def ist_die_variable(knoten) -> bool:
        return isinstance(knoten, ast.Name) and 'billing_type' in knoten.id

    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Compare) or not ist_die_variable(knoten.left):
            continue
        for vergleicher in knoten.comparators:
            if isinstance(vergleicher, ast.Constant) and isinstance(vergleicher.value, str):
                gefunden.add(vergleicher.value)
            elif isinstance(vergleicher, (ast.List, ast.Tuple, ast.Set)):
                gefunden.update(
                    teil.value for teil in vergleicher.elts
                    if isinstance(teil, ast.Constant) and isinstance(teil.value, str)
                )
    return gefunden


def test_rechenkern_behandelt_genau_die_fuenf_arten():
    """Keine sechste Art im Kern, keine der fuenf dort verschwunden (F-25).

    Ginge das auseinander, waere ``abrechnungsart.py`` nicht mehr der eine
    Ort, sondern der zweite -- und genau daran ist F-25 entstanden.
    """
    im_kern = _billing_type_literale(
        (WURZEL / 'rechenkern.py').read_text(encoding='utf-8')
    )
    fehlt = GUELTIG - im_kern
    zuviel = im_kern - GUELTIG
    assert not fehlt, (
        f'Der Rechenkern behandelt diese Abrechnungsarten nicht mehr: {sorted(fehlt)}. '
        'Sie stehen in abrechnungsart.ARTEN und waeren damit waehlbar, aber wirkungslos.'
    )
    assert not zuviel, (
        f'Der Rechenkern kennt Abrechnungsarten, die es nicht gibt: {sorted(zuviel)}. '
        'Jede Art gehoert nach abrechnungsart.ARTEN -- sonst kann sie niemand waehlen.'
    )


def test_modul_haengt_nur_an_der_standardbibliothek():
    """Der Rechenkern importiert dieses Modul -- und kein ORM (NK-037)."""
    baum = ast.parse((WURZEL / 'abrechnungsart.py').read_text(encoding='utf-8'))
    importiert = {
        (knoten.module or '').split('.')[0]
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.ImportFrom)
    } | {
        alias.name.split('.')[0]
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Import)
        for alias in knoten.names
    }
    assert importiert <= {'__future__'}, (
        f'abrechnungsart.py zieht fremde Module herein: {sorted(importiert)}'
    )


def test_auswahlliste_bietet_genau_die_fuenf_arten():
    """Der dritte Ort aus F-25: die Auswahlliste in der Oberflaeche.

    Kommentar am Schema, elif-Kette im Kern, Auswahlliste in app.js -- drei
    Orte, die auseinanderlaufen konnten. Die ersten beiden haengen jetzt an
    ARTEN; die Liste im Browser kann es nicht, also prueft sie dieser Test.
    Ein Knopf, den der Vermieter druecken kann und der an der Eingabe
    abprallt, waere die naechste Ungereimtheit.
    """
    quelle = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
    anfang = quelle.index('<select id="profile-cat-')
    ende = quelle.index('</select>', anfang)
    angeboten = set(re.findall(r'<option value="([^"]*)"', quelle[anfang:ende]))
    assert angeboten == GUELTIG, (
        f'Die Auswahlliste der Kostenprofile bietet {sorted(angeboten)}, '
        f'gueltig sind {sorted(GUELTIG)} (abrechnungsart.ARTEN).'
    )
