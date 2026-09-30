"""NK-146: Sicherheitspruefung automatisiert.

- bandit ueber den ausgelieferten Code: kein Befund, jede Ausnahme im Code
  begruendet (Kommentarzeile "Bandit-Ausnahme" direkt ueber dem nosec).
- pip-audit ueber requirements.txt (braucht Netz; in der CI immer, hier nur
  mit NK_PIP_AUDIT=1).
- Alle Laufzeitabhaengigkeiten exakt gepinnt, sonst prueft pip-audit etwas
  anderes als das, was ausgeliefert wird.
- Kopfzeilen und HTML-Uploads pruefen tests/test_web_haertung.py und
  tests/test_uploads.py; hier nur die Gegenprobe, dass es sie gibt.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]


def _vorhanden(modul):
    try:
        __import__(modul)
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _vorhanden('bandit'), reason='bandit nicht installiert')
def test_bandit_ohne_befund():
    lauf = subprocess.run(
        [sys.executable, '-m', 'bandit', '-q', '-c', 'pyproject.toml', '-r', '.',
         '-f', 'custom', '--msg-template', '{relpath}:{line} {test_id} {msg}'],
        cwd=WURZEL, capture_output=True, text=True, timeout=300)
    befunde = [z for z in lauf.stdout.splitlines() if re.match(r'^\S+:\d+ B\d+', z)]
    assert lauf.returncode == 0 and not befunde, '\n'.join(befunde) or lauf.stderr


def test_jede_bandit_ausnahme_ist_begruendet():
    fehlend = []
    for pfad in [*WURZEL.glob('*.py'), *(WURZEL / 'nebenkostenfix').rglob('*.py')]:
        zeilen = pfad.read_text(encoding='utf-8').splitlines()
        for nummer, zeile in enumerate(zeilen):
            if '# nosec' not in zeile:
                continue
            davor = '\n'.join(zeilen[max(0, nummer - 3):nummer])
            if 'Bandit-Ausnahme' not in davor:
                fehlend.append(f'{pfad.name}:{nummer + 1}')
    assert fehlend == [], fehlend


@pytest.mark.skipif(os.environ.get('NK_PIP_AUDIT') != '1',
                    reason='pip-audit braucht Netz; NK_PIP_AUDIT=1 setzen (CI)')
def test_pip_audit_ohne_bekannte_schwachstelle():
    lauf = subprocess.run([sys.executable, '-m', 'pip_audit', '-r', 'requirements.txt'],
                          cwd=WURZEL, capture_output=True, text=True, timeout=600)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr


def test_laufzeitabhaengigkeiten_sind_exakt_gepinnt():
    for zeile in (WURZEL / 'requirements.txt').read_text().splitlines():
        zeile = zeile.split('#')[0].strip()
        if zeile:
            assert re.match(r'^[A-Za-z0-9_.\-\[\]]+==[0-9][^\s]*$', zeile), zeile


def test_check_enthaelt_die_sicherheitspruefung():
    makefile = (WURZEL / 'Makefile').read_text()
    assert re.search(r'\$\(MAKE\) install-dev lint ui sicherheit test', makefile)


def test_kopfzeilen_und_html_uploads_sind_getestet():
    tests = WURZEL / 'tests'
    assert 'test_sicherheitskoepfe_auf_jeder_antwort' in (tests / 'test_web_haertung.py').read_text()
    assert 'test_html_svg_und_getarntes_werden_abgelehnt' in (tests / 'test_uploads.py').read_text()
