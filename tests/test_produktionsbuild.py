"""Im Auslieferungsbuild gibt es keine Entwicklerroute (NK-040).

R-DSGVO-01 verlangt woertlich: "Debug- und Reset-Endpunkte existieren in
Produktionsbuilds nicht." Das ist eine schaerfere Zusage als "sind
ausgeschaltet". Ein Schalter kann umgelegt werden -- durch eine .env, die
jemand aus der Entwicklung kopiert, durch eine Zeile im falschen
docker-compose, durch einen Menschen, der einen Fehler sucht und es
abends vergisst. Was nicht im Abbild liegt, laesst sich nicht umlegen.

Drei Lagen, die verschiedene Dinge beweisen:

1. **Struktur** -- welche Datei traegt ueberhaupt eine Adresse unter
   ``/api/debug/``? Der Waechter liest die Quelltexte, nicht eine Liste, und
   greift damit auch eine Debug-Route, die es heute noch nicht gibt.
2. **Auslieferung** -- jede solche Datei muss in ``.dockerignore`` stehen.
   Das ist der Schritt, der aus "in einer eigenen Datei" ein "nicht im
   Abbild" macht.
3. **Verhalten** -- die Anwendung wird in einem Baum gestartet, in dem
   ``debug_routen.py`` fehlt, und zwar mit gesetztem ``ENABLE_DEBUG_RESET``
   und gesetztem Geheimnis. Faehrt sie hoch und hat trotzdem keine
   Debug-Adresse, ist die Zusage eingeloest. Die Gegenprobe im selben Aufbau
   -- derselbe Baum, die Datei darin -- zeigt, dass der Nachweis nicht bloss
   deshalb gelingt, weil der Aufbau nichts startet.

Abgrenzung: ``tests/test_reset_db.py`` (NK-001) prueft die beiden
Laufzeitriegel, Flag und Geheimnis. Die bleiben stehen und sind jetzt der
zweite Boden fuer den Fall, dass jemand die Datei doch mitliefert.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
DEBUG_PRAEFIX = '/api/debug/'
LAUF = Path(__file__).resolve().parent / 'produktionsbuild_lauf.py'

# Verzeichnisse, die nie ins Abbild kommen und darum nicht geprueft werden
# muessen. Sie stehen aus demselben Grund schon in .dockerignore.
UEBERSPRUNGEN = {'tests', 'migrations', '.git', '__pycache__', 'htmlcov',
                 'nas-sandbox', 'backups', 'data', 'belege', '.venv',
                 'venv', 'docs', 'scripts'}


# --------------------------------------------------------------------------
# Lage 1 -- welche Datei traegt eine Debug-Adresse?
# --------------------------------------------------------------------------

def _routenpfade(quelle: str) -> set[str]:
    """Jeder Pfad, den diese Quelle als Adresse anmeldet.

    Gelesen wird das Argument von ``@irgendwas.route(...)`` und von
    ``add_url_rule(...)``. Ein blosser Textfund wuerde auch den Satz im
    Docstring treffen, der die Adresse nur erwaehnt -- und genau so einer
    steht in ``app.py``.
    """
    gefunden = set()
    for knoten in ast.walk(ast.parse(quelle)):
        if not isinstance(knoten, ast.Call):
            continue
        name = getattr(knoten.func, 'attr', None) or getattr(knoten.func, 'id', None)
        if name not in ('route', 'add_url_rule'):
            continue
        for arg in knoten.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                gefunden.add(arg.value)
    return gefunden


def _quelldateien() -> list[Path]:
    """Die Python-Dateien, die im Abbild landen wuerden."""
    dateien = []
    for pfad in sorted(WURZEL.rglob('*.py')):
        rel = pfad.relative_to(WURZEL)
        if set(rel.parts[:-1]) & UEBERSPRUNGEN:
            continue
        dateien.append(pfad)
    return dateien


def _traeger_von_debugrouten() -> dict[Path, set[str]]:
    treffer = {}
    for pfad in _quelldateien():
        pfade = {p for p in _routenpfade(pfad.read_text(encoding='utf-8'))
                 if p.startswith(DEBUG_PRAEFIX)}
        if pfade:
            treffer[pfad] = pfade
    return treffer


def test_der_waechter_liest_wirklich_quelltexte():
    """Ohne diese Zusicherung koennte der Filter oben stillschweigend leerlaufen."""
    dateien = _quelldateien()
    assert len(dateien) >= 10, [str(p) for p in dateien]
    assert WURZEL / 'app.py' in dateien


def test_app_py_meldet_selbst_keine_debugadresse_an():
    """Die Route steht seit NK-040 in einer eigenen Datei, nicht mehr hier."""
    pfade = _routenpfade((WURZEL / 'app.py').read_text(encoding='utf-8'))
    debug = {p for p in pfade if p.startswith(DEBUG_PRAEFIX)}
    assert not debug, (
        'app.py meldet wieder eine Debug-Adresse an: ' + ', '.join(sorted(debug)) +
        '. Sie gehoert in eine Datei, die .dockerignore ausschliesst.'
    )


def test_genau_eine_datei_traegt_die_reset_adresse():
    traeger = _traeger_von_debugrouten()
    assert set(traeger) == {WURZEL / 'nebenkostenfix' / 'debug_routen.py'}, {
        str(p): sorted(v) for p, v in traeger.items()}
    assert traeger[WURZEL / 'nebenkostenfix' / 'debug_routen.py'] == {'/api/debug/reset_db'}


# --------------------------------------------------------------------------
# Lage 2 -- die Auslieferung laesst sie weg
# --------------------------------------------------------------------------

def _dockerignore_zeilen() -> set[str]:
    text = (WURZEL / '.dockerignore').read_text(encoding='utf-8')
    return {z.strip() for z in text.splitlines()
            if z.strip() and not z.lstrip().startswith('#')}


def test_jede_datei_mit_debugadresse_steht_in_dockerignore():
    """Der eigentliche Schritt: eigene Datei allein genuegt nicht."""
    zeilen = _dockerignore_zeilen()
    fehlend = [
        pfad.relative_to(WURZEL).as_posix()
        for pfad in _traeger_von_debugrouten()
        if pfad.relative_to(WURZEL).as_posix() not in zeilen
    ]
    assert not fehlend, (
        'Diese Dateien melden eine Debug-Adresse an und wuerden mit ins '
        'Abbild kopiert: ' + ', '.join(fehlend) +
        '. Trage sie in .dockerignore ein (R-DSGVO-01).'
    )


def test_debug_routen_steht_namentlich_drin():
    """Doppelt zum Test darueber, aber namentlich lesbar im Bericht."""
    assert 'nebenkostenfix/debug_routen.py' in _dockerignore_zeilen()


def test_der_dockerfile_kopiert_pauschal():
    """Die Begruendung fuer Lage 2 haengt daran.

    ``COPY . .`` plus ``.dockerignore`` ist eine Negativliste: was nicht
    ausgeschlossen ist, kommt mit. Stellt jemand auf eine Positivliste um --
    einzelne ``COPY``-Zeilen --, traegt .dockerignore die Zusage nicht mehr
    allein, und dieser Test erinnert daran.
    """
    inhalt = (WURZEL / 'Dockerfile').read_text(encoding='utf-8')
    assert 'COPY . .' in inhalt


# --------------------------------------------------------------------------
# Lage 2b -- die Werkzeuge in scripts/ (F-26)
# --------------------------------------------------------------------------
#
# scripts/ stand in keiner Zeile von .dockerignore, also kam der ganze Ordner
# mit ins Abbild. Zwei der drei Dateien sind Entwicklungswerkzeug. Die dritte
# ist keines: kategorien.py verweist den Betreiber im Klartext darauf, wenn
# zwei Kostenarten denselben Namen tragen. Die Entscheidung faellt also je
# Datei und nicht fuer den Ordner -- und wer eine neue anlegt, soll sie
# treffen muessen.

NUR_ENTWICKLUNG = frozenset({
    'scripts/e2e.py',
    'scripts/update_signieren.py',  # NK-175: Werkzeug des Herausgebers
    # NK-155: erzeugt Icons und Bilder der Marke. Nicht „marke.py“: im
    # Ordner scripts/ verdeckte der Name das Modul marke (NK-161).
    'scripts/marke_bilder.py',
    'scripts/rundgang.py',  # NK-157: Browser-Rundgang der CI, braucht Playwright
    'scripts/umzug_kreuzprobe.py',  # NK-164: Umzug Linux <-> Windows, Probe der CI
    'scripts/hilfe_begriffe.py',  # NK-158: erzeugt static/hilfe-begriffe.json aus dem Glossar
    'scripts/einzelschwelle.py',
    # Beschriftungs-Pruefer (NK-074): liest static/ gegen den Begriffs-
    # katalog aus; Qualitaetstor der Entwicklung, nicht des Betriebs.
    'scripts/ui_beschriftungen.py',
    # Waechter gegen unmaskierte HTML-Einsetzungen (NK-149, F-78): liest
    # static/app.js, Qualitaetstor der Entwicklung.
    'scripts/html_maskierung.py',
    # Probe zu Tor 0.8-P (NK-145): startet gunicorn und Chromium auf dem
    # Entwicklungsrechner, nicht Teil des Betriebs.
    'scripts/probe_ersteinrichtung.py',
    # DOM-Rauchtest des Design-Systems (NK-067): braucht Node, der im
    # Container nicht laeuft; Wirtswerkzeug wie e2e.py.
    'scripts/rauchtest_design.js',
    # NK-187: Praxisprobe, liest eine Kopie der echten Datenbank und
    # schreibt einen Fallkatalog; Werkzeug der Entwicklung.
    'scripts/praxisprobe.py',
})
GEHOERT_INS_ABBILD = frozenset({
    'scripts/kostenarten.py',
})


def _skripte() -> set[str]:
    return {
        p.relative_to(WURZEL).as_posix()
        for glob in ('*.py', '*.js')
        for p in (WURZEL / 'scripts').glob(glob)
    }


def test_jedes_skript_ist_einsortiert():
    """Eine neue Datei in scripts/ ist ein roter Test, keine stille Mitnahme."""
    assert _skripte() == set(NUR_ENTWICKLUNG | GEHOERT_INS_ABBILD)


def test_die_entwicklungswerkzeuge_bleiben_draussen():
    zeilen = _dockerignore_zeilen()
    fehlend = sorted(NUR_ENTWICKLUNG - zeilen)
    assert not fehlend, (
        'Diese Entwicklungswerkzeuge wuerden mit ins Abbild kopiert: ' +
        ', '.join(fehlend))


def test_das_notfallwerkzeug_bleibt_drin():
    """Die Kehrseite: kategorien.py nennt es dem Betreiber."""
    zeilen = _dockerignore_zeilen()
    zuviel = sorted(GEHOERT_INS_ABBILD & zeilen)
    assert not zuviel, (
        'Diese Dateien braucht der Betreiber, sie duerfen nicht ausgeschlossen '
        'sein: ' + ', '.join(zuviel))


def test_die_anwendung_verweist_wirklich_auf_das_notfallwerkzeug():
    """Ohne diesen Beleg waere der Test darueber eine blosse Behauptung."""
    hinweise = (WURZEL / 'nebenkostenfix' / 'kategorien.py').read_text(encoding='utf-8')
    assert 'scripts/kostenarten.py' in hinweise


def test_der_ordner_selbst_ist_nicht_pauschal_ausgeschlossen():
    """``scripts/`` als Zeile wuerde das Notfallwerkzeug mit wegnehmen."""
    assert 'scripts/' not in _dockerignore_zeilen()
    assert 'scripts' not in _dockerignore_zeilen()


# --------------------------------------------------------------------------
# Lage 3 -- Start ohne die Datei
# --------------------------------------------------------------------------

# Was ein Anwendungsstart braucht. Bewusst eine Positivliste: ein pauschales
# Verlinken der Wurzel wuerde .env und data/ mit in den Probebaum ziehen.
VERZEICHNISSE = ('migrations', 'static')


def _baue_baum(ziel: Path, *, mit_debugmodul: bool) -> None:
    """Ein Arbeitsverzeichnis aus Symlinks -- die Datei fehlt wirklich."""
    ziel.mkdir(parents=True, exist_ok=True)
    for quelle in sorted(WURZEL.glob('*.py')):
        os.symlink(quelle, ziel / quelle.name)
    (ziel / 'nebenkostenfix').mkdir()
    for quelle in sorted((WURZEL / 'nebenkostenfix').iterdir()):
        if quelle.name == '__pycache__' or (
                quelle.name == 'debug_routen.py' and not mit_debugmodul):
            continue
        os.symlink(quelle, ziel / 'nebenkostenfix' / quelle.name)
    for name in VERZEICHNISSE:
        os.symlink(WURZEL / name, ziel / name)
    # Das Skript wird kopiert statt verlinkt: so ist sys.path[0] der Probebaum
    # und nicht tests/, und der Import von app kann nur hier fuendig werden.
    (ziel / LAUF.name).write_text(LAUF.read_text(encoding='utf-8'), encoding='utf-8')


def _starte(baum: Path) -> dict:
    """Startet die Anwendung im Probebaum -- mit scharfem Flag und Geheimnis."""
    tmp = baum.parent
    umgebung = {
        'PATH': os.environ.get('PATH', ''),
        # Windows: ohne SYSTEMROOT laedt Winsock nicht (WinError 10106).
        **({'SYSTEMROOT': os.environ['SYSTEMROOT']} if 'SYSTEMROOT' in os.environ else {}),
        'PYTHONDONTWRITEBYTECODE': '1',
        'NAS_MOUNT_PATH': str(tmp / 'nas'),
        'DATABASE_URL': f'sqlite:///{tmp / "probe.db"}',
        'SECRET_KEY': 'nkfix-pytest-secret-key-nur-fuer-tests',
        'FLASK_ENV': 'testing',
        'LOCAL_PDF_PATH': str(tmp / 'pdfs'),
        'LOCAL_TEMP_PATH': str(tmp / 'temp'),
        # Der Kern der Karte: beide Riegel sind offen. Trotzdem darf es die
        # Adresse nicht geben, wenn die Datei fehlt.
        'ENABLE_DEBUG_RESET': '1',
        'DEBUG_RESET_SECRET': 'egal-die-route-soll-nicht-existieren',
    }
    fertig = subprocess.run(
        [sys.executable, LAUF.name],
        cwd=baum, env=umgebung, capture_output=True, text=True,
    )
    assert fertig.returncode == 0, (
        f'Start im Probebaum fehlgeschlagen:\n{fertig.stderr[-3000:]}')
    return json.loads(fertig.stdout)


@pytest.fixture(scope='module')
def probelauf() -> dict:
    """Beide Laeufe einmal je Modul -- ein Start kostet die Wanderung."""
    with tempfile.TemporaryDirectory(prefix='nk-nk040-') as ablage:
        wurzel = Path(ablage)
        ohne = wurzel / 'ohne'
        mit = wurzel / 'mit'
        _baue_baum(ohne, mit_debugmodul=False)
        _baue_baum(mit, mit_debugmodul=True)
        yield {'ohne': _starte(ohne), 'mit': _starte(mit)}


def test_ohne_die_datei_gibt_es_keine_debugadresse(probelauf):
    """Der Nachweis, den die Karte verlangt."""
    ohne = probelauf['ohne']
    assert ohne['debug_regeln'] == []
    assert ohne['hat_reset_db'] is False
    assert ohne['modul_geladen'] is False


def test_ohne_die_datei_faehrt_die_anwendung_trotzdem_hoch(probelauf):
    """Kein halber Start, keine Ersatzroute, kein Fehler beim Import."""
    assert probelauf['ohne']['anzahl_regeln'] >= 55


def test_die_gegenprobe_findet_die_adresse(probelauf):
    """Sonst beweist der Test darueber nur, dass der Aufbau nichts startet."""
    mit = probelauf['mit']
    assert mit['debug_regeln'] == ['/api/debug/reset_db']
    assert mit['hat_reset_db'] is True
    assert mit['modul_geladen'] is True


def test_die_beiden_baeume_unterscheiden_sich_nur_in_der_einen_adresse(probelauf):
    """Der Probebaum soll die Anwendung nicht sonst noch veraendern."""
    ohne, mit = probelauf['ohne'], probelauf['mit']
    assert mit['anzahl_regeln'] == ohne['anzahl_regeln'] + 1
