"""NK-073-Rest: eine brauchbare Druckansicht (D-75).

Gedruckt wird die aktive Ansicht, nicht die Anwendung: Rahmen, Kopfzeile,
Schalter und Dialoge bleiben auf dem Papier weg, Karten drucken weiss statt
Glas. Der Sonderfall Pruef-Nachweis bleibt: Bei offenem
interpolation-audit-modal druckt nur das Modal -- der alte Print-Block
versteckte aber ALLES per body * visibility:hidden, d.h. ohne offenes Modal
kam eine leere Seite heraus. Genau das pinnt dieser Test als behoben.

Diese Regeln leben in CSS; getestet wird die Datei selbst. Ein
Browser-Rundlauf waere schoener, aber der Spieler traegt Szenarien fuer
Faechwege, nicht fuer Medienabfragen -- und die Regel ist eine Sache von
Selektoren und !important, also hier festzunageln.
"""

from __future__ import annotations

import re


def _css() -> str:
    with open('static/style.css', encoding='utf-8') as datei:
        return datei.read()


def _print_block() -> str:
    css = _css()
    start = css.index('@media print {')
    # Der Block ist der letzte seiner Art; die Schliessung findet sich per
    # Klammerzehlung, einfacher: der naechste "@media"-Beginn oder das Ende.
    rest = css[start:]
    ende = rest.index('\n@media', 1) if '\n@media' in rest[1:] else len(rest)
    return rest[:ende]


def test_druck_haelt_die_anwendung_zurueck():
    block = _print_block()
    for selektor in ('.sidebar', '.top-header', '.toast-stapel',
                     '.modal-overlay', '.kopf-aktionen', '.background-blobs'):
        # Der Selektor steht im Block und wird dort ausgeblendet.
        zeile = next(z for z in block.splitlines() if selektor in z
                     and 'display' not in z)
        assert '!' not in zeile  # die Versteck-Liste, nicht eine andere Regel
    assert 'display: none !important' in block


def test_druck_zeigt_die_aktive_ansicht():
    block = _print_block()
    assert '.tab-content {' in block
    assert '.tab-content.active {' in block
    aktiv = block[block.index('.tab-content.active'):]
    assert 'display: block !important' in aktiv


def test_karten_drucken_weiss_statt_glas():
    block = _print_block()
    karten = block[block.index('.dashboard-card'):]
    karten = karten[:karten.index('}')]
    assert 'background: white' in karten
    assert 'backdrop-filter: none' in karten
    assert 'box-shadow: none' in karten


def test_leere_seite_beim_drucken_geheilt():
    """Der Befund, den D-75 einfuhr: body * visibility:hidden galt immer --
    ohne offenes Modal kam eine leere Seite heraus. Die allgemeine Regel ist
    jetzt an den offenen Pruef-Nachweis gebunden."""
    block = _print_block()
    druck = block[block.index('{'):]
    assert '\n    body * {' not in druck
    assert 'body:has(#interpolation-audit-modal.active) * {' in druck


def test_pruef_nachweis_bleibt_sonderfall():
    """Bei offenem Nachweis druckt nur das Modal -- und seine Schliessknöpfe
    (no-print) bleiben trotzdem weg."""
    block = _print_block()
    assert '#interpolation-audit-modal.active {' in block
    nachweis = block[block.index('body:has(#interpolation-audit-modal.active)'):]
    assert 'visibility: visible' in nachweis
    assert '.no-print' in block.split('body:has(')[0]


def test_druckknopf_in_der_kopfzeile():
    with open('static/index.html', encoding='utf-8') as datei:
        zeilen = datei.readlines()
    stelle = next(i for i, z in enumerate(zeilen) if 'huelle.drucken()' in z)
    knopf = ''.join(zeilen[stelle - 1:stelle + 3])
    assert 'Drucken' in knopf
    assert 'btn-secondary' in knopf
    # Und die Stylesheet-Kennung ist da; sie springt mit jeder Aenderung
    # (NK-140), darum wird nur das Muster gepinnt, nicht die Zahl.
    with open('static/index.html', encoding='utf-8') as datei:
        seite = datei.read()
    assert re.search(r'style\.css\?v=\d+', seite)
