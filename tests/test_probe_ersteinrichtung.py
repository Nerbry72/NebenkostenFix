"""Tor 0.8-P Punkt 1 als wiederholbare Probe (NK-149/NK-145).

Faehrt ``scripts/probe_ersteinrichtung.py``: gunicorn mit zwei Arbeitern,
frischer Datenordner, Einrichtung im Browser mit dem Code aus dem
Protokoll, Abrechnung mit Heizkosten in der Oberflaeche. Braucht Playwright
und einen Chromium; wo beides fehlt (Dev-Container), wird uebersprungen.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get('NK_CHROMIUM', '/opt/pw-browsers/chromium')


def _vorhanden():
    try:
        import gunicorn  # noqa: F401
        import playwright  # noqa: F401
    except ImportError:
        return False
    return os.path.exists(CHROMIUM)


@pytest.mark.skipif(not _vorhanden(), reason='Playwright/Chromium/gunicorn fehlen')
@pytest.mark.skipif(sys.platform == 'win32', reason='gunicorn gibt es unter Windows nicht')
def test_einrichtung_und_heizkostenabrechnung_mit_zwei_arbeitern():
    lauf = subprocess.run(
        [sys.executable, 'scripts/probe_ersteinrichtung.py', '--workers', '2',
         '--chromium', CHROMIUM],
        cwd=WURZEL, capture_output=True, text=True, timeout=300)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert 'ERGEBNIS: bestanden' in lauf.stdout
    assert 'genau einen Einmal-Code' in lauf.stdout
