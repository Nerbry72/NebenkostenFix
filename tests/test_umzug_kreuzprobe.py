"""NK-164: die plattformübergreifende Umzugsprobe der CI.

Unter Linux läuft hier der Rundlauf Linux → Linux mit genau dem Skript, das
die CI zwischen Linux und Windows (Quellen und gebaute App) fährt. Dazu der
Vergleich selbst: er muss jede Abweichung melden, sonst wäre die CI grün,
ohne etwas zu prüfen.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    'umzug_kreuzprobe', WURZEL / 'scripts' / 'umzug_kreuzprobe.py')
kreuz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kreuz)

ERWARTET = {
    'zeilen': {'properties': 1, 'users': 1, 'cost_categories': 18, 'vermieterdaten': 0},
    'belege': {'a/b.pdf': 'aa'},
    'fehlend': 0,
}
ANGEKOMMEN = {
    'zeilen': {'properties': 1, 'users': 1, 'cost_categories': 19, 'vermieterdaten': 1},
    'belege': {'a/b.pdf': 'aa'},
    'fehlend': 0,
    'anmeldung': True,
    'vermieter': {'name': kreuz.VERMIETER['VERMIETER_NAME'],
                  'iban': kreuz.VERMIETER['VERMIETER_IBAN']},
    'logo': True,
    'lizenz': True,
}


def test_vergleich_besteht_bei_gleichem_bestand():
    assert kreuz.vergleichen(ERWARTET, ANGEKOMMEN) == []


def test_vergleich_meldet_jede_abweichung():
    faelle = [
        (lambda a: a['zeilen'].update(properties=0), 'properties'),
        (lambda a: a['zeilen'].pop('users'), 'users fehlt'),
        (lambda a: a['zeilen'].update(cost_categories=5), 'cost_categories'),
        (lambda a: a['belege'].update({'a/b.pdf': 'bb'}), 'bytegleich'),
        (lambda a: a.update(fehlend=2), 'Leere'),
        (lambda a: a.update(anmeldung=False), 'Passwort'),
        (lambda a: a.update(vermieter={'name': None, 'iban': None}), 'Vermieter'),
        (lambda a: a.update(logo=False), 'Logo'),
        (lambda a: a.update(lizenz=False), 'Lizenz'),
    ]
    for aendern, muster in faelle:
        angekommen = copy.deepcopy(ANGEKOMMEN)
        aendern(angekommen)
        fehler = kreuz.vergleichen(ERWARTET, angekommen)
        assert any(muster in f for f in fehler), (muster, fehler)


def test_gebaute_app_meldet_konten_statt_anmeldung():
    """Die gebaute App prüft kein Passwort (paketprobe), aber das Konto muss da sein."""
    angekommen = copy.deepcopy(ANGEKOMMEN)
    del angekommen['anmeldung']
    angekommen['konten'] = [kreuz.KONTO]
    assert kreuz.vergleichen(ERWARTET, angekommen) == []
    angekommen['konten'] = []
    assert kreuz.vergleichen(ERWARTET, angekommen) == [f'Konto {kreuz.KONTO} fehlt']


def test_rundlauf_linux_nach_linux(tmp_path):
    kreuz.bauen(tmp_path, 'quelle')
    assert (tmp_path / 'quelle.nkfix').is_file()
    bericht = kreuz.pruefen(tmp_path, tmp_path / 'quelle.nkfix', tmp_path / 'quelle.json')
    assert bericht['ergebnis'] == 'bestanden', bericht['fehler']
    assert bericht['belege'] >= 1
    assert bericht['bericht']['zusatz']['vermieter_festgeschrieben'] == ['name', 'iban']
    gespeichert = json.loads((tmp_path / 'quelle-pruefung.json').read_text(encoding='utf-8'))
    assert gespeichert['ergebnis'] == 'bestanden'


def test_ci_faehrt_beide_richtungen():
    workflow = (WURZEL / '.github' / 'workflows' / 'windows.yml').read_text(encoding='utf-8')
    assert 'umzug_kreuzprobe.py bauen --arbeit umzug --name linux' in workflow
    assert 'paketprobe.py umzug dist\\NebenkostenFix\\NebenkostenFix.exe' in workflow
    assert 'umzug_kreuzprobe.py bauen --arbeit umzug-windows --name windows' in workflow
    assert '--paket umzug-windows/windows.nkfix' in workflow
