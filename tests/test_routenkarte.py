"""Die Routenkarte im Kopf von app.py gegen die Wahrheit von Flask (NK-033).

NK-033 schreibt vier Diagramme in vier Dateikoepfe. Drei davon beschreiben
Ablaeufe und veralten langsam und sichtbar: wer ``calculate_bill`` umbaut,
liest den Kopf, weil er direkt darueber steht.

Die vierte ist anders. Eine Liste von 59 Adressen veraltet beim ersten
``@app.route``, das jemand ans Ende der Datei haengt -- 2000 Zeilen von der
Karte entfernt. Eine Karte, der man nicht glauben kann, ist schlimmer als
keine: sie beantwortet die Frage "gibt es dafuer eine Route?" mit einem
falschen Nein.

Darum dieser Test. Er liest ``app.__doc__``, zieht jede Zeile der Form
``METHODEN  PFAD  -> endpunkt`` heraus und stellt sie ``app.url_map``
gegenueber. Die Karte ist damit kein Kommentar mehr, sondern eine Behauptung
mit Beleg.

Abgrenzung zu ``tests/test_routentabelle.py`` (NK-020): der prueft, dass keine
Route **ohne Anmeldung** erreichbar ist -- eine Sicherheitsfrage. Dieser hier
prueft, dass die Doku stimmt. Beide laufen ueber ``url_map``, weil das die
einzige Quelle ist, die nicht luegen kann; sie ziehen daraus verschiedene
Schluesse. Sie teilen bewusst keine Liste: eine gemeinsame Konstante waere
eine dritte Stelle, die jemand pflegen muss.
"""

from __future__ import annotations

import re

import app as app_modul

# METHODEN  PFAD  -> endpunkt. Fuehrende Leerzeichen sind die Einrueckung im
# Docstring, der Rest der Zeile nach dem Endpunktnamen muss leer sein: sonst
# wuerde ein Fliesstext, der zufaellig einen Pfeil enthaelt, als Route gelesen.
ZEILE = re.compile(r'^\s*([A-Z]+(?:,[A-Z]+)*)\s+(/\S*)\s+->\s+([a-z_][a-z0-9_]*)\s*$')

# Die vergibt Flask zu jeder Regel von selbst. Sie in die Karte zu schreiben
# hiesse, 59 Zeilen um eine Information zu verlaengern, die immer dieselbe ist.
AUTOMATISCH = {'HEAD', 'OPTIONS'}


def karte_aus_docstring() -> set[tuple[str, str, str]]:
    """Die Karte als Menge (methoden, pfad, endpunkt)."""
    # app_modul.__doc__, nicht app_modul.app.__doc__: das zweite ist der
    # Docstring der Flask-Klasse aus der Bibliothek. Er ist nicht leer, also
    # haette ein ``or`` daneben den Fehler verdeckt -- gefunden hat ihn
    # test_karte_ist_nicht_leer beim ersten Lauf.
    doku = app_modul.__doc__ or ''
    gefunden = set()
    for zeile in doku.splitlines():
        treffer = ZEILE.match(zeile)
        if treffer:
            methoden, pfad, endpunkt = treffer.groups()
            gefunden.add((','.join(sorted(methoden.split(','))), pfad, endpunkt))
    return gefunden


def karte_aus_urlmap() -> set[tuple[str, str, str]]:
    """Dasselbe aus app.url_map."""
    echt = set()
    for regel in app_modul.app.url_map.iter_rules():
        methoden = sorted((regel.methods or set()) - AUTOMATISCH)
        echt.add((','.join(methoden), str(regel.rule), regel.endpoint))
    return echt


def test_karte_ist_nicht_leer():
    """Ein zerschossenes Muster darf nicht als 'alles stimmt' durchgehen.

    Ohne diesen Test wuerde ein Tippfehler in ZEILE beide Mengen auf leer
    ziehen -- und leer gleich leer ist gruen. Die Zahl steht bewusst niedrig:
    sie soll den Totalausfall fangen, nicht jede neue Route zaehlen.
    """
    assert len(karte_aus_docstring()) >= 50


def test_jede_route_steht_in_der_karte():
    fehlt = karte_aus_urlmap() - karte_aus_docstring()
    assert not fehlt, (
        'Diese Routen gibt es, aber die Karte im Kopf von app.py kennt sie '
        'nicht:\n' + '\n'.join(f'  {m:11} {p:45} -> {e}' for m, p, e in sorted(fehlt))
    )


def test_keine_karteileiche():
    """Der umgekehrte Weg: eine Zeile zu einer Route, die es nicht mehr gibt.

    Das ist der haeufigere Fall. Eine Route loeschen ist eine Zeile, die Karte
    dabei zu vergessen kostet nichts -- bis jemand nach einer Adresse sucht,
    die seit einem halben Jahr weg ist.
    """
    zu_viel = karte_aus_docstring() - karte_aus_urlmap()
    assert not zu_viel, (
        'Diese Zeilen stehen in der Karte, aber es gibt keine solche Route '
        '(Pfad, Methoden oder Endpunktname geaendert?):\n'
        + '\n'.join(f'  {m:11} {p:45} -> {e}' for m, p, e in sorted(zu_viel))
    )


def test_endpunktnamen_sind_eindeutig():
    """Zwei Zeilen mit demselben Endpunkt waeren ein Kopierfehler.

    Die Mengenvergleiche oben wuerden ihn nicht sehen: eine doppelte Zeile
    faellt beim Aufbau der Menge einfach weg.
    """
    namen = [e for _, _, e in karte_aus_docstring()]
    assert len(namen) == len(set(namen)), 'Endpunktname doppelt in der Karte'
