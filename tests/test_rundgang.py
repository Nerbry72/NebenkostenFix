"""Der Browser-Rundgang (NK-157): reine Helfer und Abgleich mit der Oberfläche.

Der Rundgang selbst läuft in der CI (``.github/workflows/rundgang.yml``),
weil er Chromium braucht. Hier steht, was ohne Browser prüfbar ist: dass er
die Bereiche, Einstellungsgruppen und Dialoge anfährt, die es gibt -- sonst
würde er still an der Oberfläche vorbeilaufen.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
SEITE = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
SKRIPT = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')

_spec = importlib.util.spec_from_file_location('rundgang', WURZEL / 'scripts' / 'rundgang.py')
rundgang = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rundgang)


def test_stapel_stelle_nennt_eigenen_code():
    stapel = ("TypeError: x is null\n"
              "    at renderBuildingComparison (http://127.0.0.1:5000/static/app.js?v=92984f:5357:69)\n"
              "    at fetchAnalytics (http://127.0.0.1:5000/static/app.js?v=92984f:4477:9)")
    assert rundgang.stapel_stelle(stapel) == ' (app.js:5357)'


def test_stapel_stelle_ohne_query_und_ohne_treffer():
    assert rundgang.stapel_stelle('E\n    at f (http://h/static/app.js:12:3)') == ' (app.js:12)'
    assert rundgang.stapel_stelle('E\n    at <anonymous>:1:1') == ''
    assert rundgang.stapel_stelle('') == ''


def test_rundgang_faehrt_jeden_bereich():
    bereiche = re.findall(r'class="nav-item[^"]*" data-tab="([a-z]+)"', SEITE)
    assert bereiche == rundgang.BEREICHE


def test_rundgang_faehrt_jede_einstellungsgruppe():
    gruppen = re.findall(r'class="filter-pill" role="tab" data-gruppe="([a-z]+)"', SEITE)
    assert gruppen == rundgang.EINSTELLUNGS_GRUPPEN


def test_rundgang_ruft_nur_dialoge_die_es_gibt():
    for aufruf in rundgang.DIALOGE.values():
        name = aufruf.split('(')[0]
        assert re.search(rf'(?:async )?function {name}\(', SKRIPT), name


def test_rundgang_deckt_die_anlegen_dialoge_ab():
    """Jeder parameterlos öffnende ``openAdd…Modal`` gehört in den Rundgang."""
    oeffner = set(re.findall(r'function (openAdd\w+Modal)\(', SKRIPT))
    gefahren = {aufruf.split('(')[0] for aufruf in rundgang.DIALOGE.values()}
    assert oeffner <= gefahren, sorted(oeffner - gefahren)


def test_rundgang_in_drei_breiten():
    assert sorted(breite for breite, _ in rundgang.BREITEN) == [390, 768, 1440]


def test_leere_zeichenflaeche_bleibt_erhalten():
    """Ein Leerhinweis ersetzt die Zeichenfläche nicht per innerHTML: kommen
    später Daten, fände Chart.js sonst kein <canvas> mehr (Fund des Rundgangs)."""
    assert not re.search(r'canvas\.parentElement\.innerHTML', SKRIPT)
    assert 'id="chart-building-comparison-leer"' in SEITE


def test_rundgang_sieht_kaputte_werte():
    for muster in ('Invalid Date', 'NaN', 'undefined'):
        assert muster in rundgang.PRUEFUNG_JS


def test_kein_neues_datum_aus_deutsch_formatiertem_text():
    """created_at kommt als „25.09.2026“ (zeit.als_ortszeit); new Date() daraus
    ergibt „Invalid Date“."""
    skript = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'new Date(r.created_at)' not in skript



def _funktion(name: str) -> str:
    start = SKRIPT.index(f'function {name}(')
    return SKRIPT[start:SKRIPT.index('\n}\n', start)]


def test_rundgang_sieht_eine_festgesetzte_abrechnung_an():
    """Fund 0.9.1: „Abrechnung ansehen“ scheiterte an jeder festgesetzten
    Abrechnung. Der Rundgang öffnet sie nach dem Beispiel im Browser."""
    import inspect
    assert 'openReportDetails(' in inspect.getsource(rundgang.rundgang)


def test_abrechnung_ansehen_rechnet_nicht_mit_schnappschuss_text():
    """Der Schnappschuss hält Beträge als Text (json_sicher). ``"828.32".toFixed``
    wirft -- jede Formatierung muss vorher in eine Zahl wandeln."""
    for name in ('openReportDetails', 'openAddPaymentModal'):
        roh = re.findall(r'(?:item|sub|data|details)\.\w+\.toFixed\(', _funktion(name))
        assert not roh, (name, roh)


def test_ci_faehrt_den_dom_rauchtest():
    """F-108: Der DOM-Rauchtest lief nur von Hand und war unbemerkt rot.

    Seitdem fährt ihn der Rundgang-Workflow vor dem Browser-Rundgang.
    """
    workflow = (WURZEL / '.github' / 'workflows' / 'rundgang.yml').read_text(encoding='utf-8')
    assert 'run: node scripts/rauchtest_design.js' in workflow
