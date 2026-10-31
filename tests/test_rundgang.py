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


def test_rundgang_oeffnet_jeden_dialog():
    """#41: ``openAnschreibenModal`` fuhr der Rundgang nie an, der kaputte
    Dialog fiel keinem auf. Ausnahme: das Beispielhaus hat keinen faelligen
    Abrechnungsvorschlag, ohne den ``openBillingSelectionModal`` nichts zeigt."""
    oeffner = set(re.findall(r'function (open\w+Modal)\(', SKRIPT)) - {'openBillingSelectionModal'}
    gefahren = {aufruf.split('(')[0] for aufruf in rundgang.DIALOGE.values()}
    assert oeffner <= gefahren, sorted(oeffner - gefahren)


def test_rundgang_prueft_dass_der_dialog_aufgeht():
    """#41 warf keinen JS-Fehler: der Fehler landete im ``catch`` und als rote
    Meldung, der Dialog blieb zu. Beides muss ein Befund sein."""
    assert '.modal-overlay.active' in rundgang.DIALOG_NACHHER_JS
    assert '.toast-fehler' in rundgang.DIALOG_NACHHER_JS
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    assert 'gang.dialog(name, aufruf)' in quelle


def test_rundgang_in_drei_breiten():
    assert sorted(breite for breite, _ in rundgang.BREITEN) == [390, 768, 1440]


def test_rundgang_prueft_am_handy_die_zaehleraktionen():
    """NK-252: bei 390 px lagen die Zähleraktionen rechts außerhalb des Bilds."""
    assert '#meters-container button' in rundgang.ZAEHLER_AKTIONEN_JS
    assert 'window.innerWidth' in rundgang.ZAEHLER_AKTIONEN_JS
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    assert re.search(r'if breite < 720:\n\s+gang\.handy\(\)', quelle)


def test_rundgang_prueft_am_handy_das_kopfmenue():
    """NK-253: bei 390 px stapelten sich die Kopfknöpfe über dem Inhalt."""
    for merkmal in ('.kopf-menue-knopf', 'knopf.click()', 'titel.bottom', 'window.innerWidth'):
        assert merkmal in rundgang.KOPF_MENUE_JS, merkmal
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    handy = quelle[quelle.index('    def handy(self):'):]
    assert re.search(r'for bereich in BEREICHE:[^\n]*\n(.*\n){1,4}.*evaluate\(KOPF_MENUE_JS, bereich\)',
                     handy[:handy.index('\n    def ')])


def test_rundgang_prueft_die_zahlungskarten_auf_nullzeilen():
    """NK-256: Mieter ohne Mietzahlung hatten eine Zeile „Miete: 0,00 €“."""
    assert '#payments-grid .property-card' in rundgang.ZAHLUNG_NULLZEILEN_JS
    assert '0,00' in rundgang.ZAHLUNG_NULLZEILEN_JS
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    handy = quelle[quelle.index('    def handy(self):'):]
    assert 'self.seite.evaluate(ZAHLUNG_NULLZEILEN_JS)' in handy[:handy.index('\n    def ')]


def test_rundgang_prueft_den_ersten_stand():
    """NK-257: ein Zähler ohne Ablesung hatte weder Stift noch einen Knopf
    für den ersten Stand."""
    assert 'Ersten Stand erfassen' in rundgang.ERSTER_STAND_JS
    assert 'Letzten Stand bearbeiten' in rundgang.ERSTER_STAND_JS
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    handy = quelle[quelle.index('    def handy(self):'):]
    assert 'self.seite.evaluate(ERSTER_STAND_JS)' in handy[:handy.index('\n    def ')]


def test_leere_zeichenflaeche_bleibt_erhalten():
    """Ein Leerhinweis ersetzt die Zeichenfläche nicht per innerHTML: kommen
    später Daten, fände Chart.js sonst kein <canvas> mehr (Fund des Rundgangs).
    Den Wohnungsvergleich ohne Daten blendet NK-254 ganz aus."""
    assert not re.search(r'canvas\.parentElement\.innerHTML', SKRIPT)
    assert 'id="chart-building-comparison"' in SEITE


def test_rundgang_prueft_den_wohnungsvergleich():
    """NK-254: die Vergleichskarte stand auch ohne zwei Wohnungen mit Daten da."""
    assert "Chart.getChart(document.getElementById('chart-building-comparison'))" in rundgang.VERGLEICH_JS
    assert 'wohnungen < 2' in rundgang.VERGLEICH_JS
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    handy = quelle[quelle.index('    def handy(self):'):]
    assert 'self.seite.evaluate(VERGLEICH_JS)' in handy[:handy.index('\n    def ')]


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


def test_readme_bilder_kommen_aus_dem_rundgang():
    """README und Store zeigen dieselbe Oberfläche wie die App: der Rundgang
    nimmt sie mit --readme auf, die CI legt sie ins Artefakt."""
    readme = (WURZEL / 'README.md').read_text(encoding='utf-8')
    assert set(re.findall(r'docs/bilder/(\w+)\.png', readme)) == set(rundgang.README_BILDER)
    for bereich in [*rundgang.README_BILDER.values(), *rundgang.STORE_BILDER.values()]:
        assert bereich is None or bereich in rundgang.BEREICHE
    assert len(rundgang.STORE_BILDER) <= 10  # Grenze des Microsoft Store
    for name in ('tourBeenden', 'wechsleZuTab', 'zeigeHilfe'):
        assert re.search(rf'function {name}\(', SKRIPT), name
    workflow = (WURZEL / '.github' / 'workflows' / 'rundgang.yml').read_text(encoding='utf-8')
    assert '--readme rundgang-bilder/readme' in workflow


def test_rundgang_bestaetigt_den_haftungshinweis_mit_verstanden():
    """#45: Ein versteckter Knopf vor „Verstanden“ ließ den Klick auf den
    ersten Knopf bis zum Timeout warten. Der Rundgang zielt deshalb auf
    den Hauptknopf; im Dialog bleibt „Verstanden“ der einzige."""
    quelle = (WURZEL / 'scripts' / 'rundgang.py').read_text(encoding='utf-8')
    assert "seite.click('#haftung-modal [data-autofokus]')" in quelle
    assert "seite.click('#haftung-modal button')" not in quelle
    dialog = SEITE[SEITE.index('id="haftung-modal"'):SEITE.index('id="frage-modal"')]
    knoepfe = re.findall(r'<button[^>]*data-autofokus[^>]*>([^<]*)<', dialog)
    assert knoepfe == ['Verstanden']
