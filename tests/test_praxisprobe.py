"""NK-187: Die Praxisprobe laeuft durch, rechnet die Summenprobe und verraet keine Namen.

Das Werkzeug liest im Alltag eine Kopie des echten Bestands; hier bekommt es
einen erfundenen: ein Haus, zwei Wohnungen, eine steht ab Juli leer.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from tests import billing_factories as f

WURZEL = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('praxisprobe', WURZEL / 'scripts' / 'praxisprobe.py')
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def _bestand():
    haus = f.house('Lindenallee 7')
    oben, unten = f.apt(haus, 'Dachgeschoss', 60.0), f.apt(haus, 'Erdgeschoss', 40.0)
    for wohnung, name, auszug in ((oben, 'Anna Kowalski', None),
                                  (unten, 'Bruno Heinemann', date(2025, 6, 30))):
        mieter = f.tenant(wohnung, name, move_in=date(2025, 1, 1), move_out=auszug)
        f.profile(mieter, f.category('Müllabfuhr'), 'qm')
    f.invoice(haus, f.category('Müllabfuhr'), 1000.0, start=date(2025, 1, 1),
              end=date(2025, 12, 31), invoice_number='RG-4711')


def test_summenprobe_geht_auf(auth_client):
    """Mieter plus Vermieter (Leerstand ab Juli) ergeben die Rechnung."""
    _bestand()
    k = probe.katalog(auth_client, date(2026, 9, 30))
    [jahr] = [b for b in k['erhaltung'] if b['jahr'] == ['2025-01-01', '2025-12-31']]
    assert jahr['vollstaendig']
    assert jahr['soll'] == 1000.0
    assert jahr['vermieter'] > 0
    assert jahr['differenz'] == 0


def test_bericht_ersetzt_namen(auth_client):
    _bestand()
    k = probe.katalog(auth_client, date(2026, 9, 30))
    text = probe.Anonym().text(probe.bericht(k, 'test'))
    for echt in ('Kowalski', 'Anna', 'Heinemann', 'Bruno', 'Lindenallee',
                 'Dachgeschoss', 'Erdgeschoss', 'RG-4711'):
        assert echt not in text
    assert 'Mieter 1' in text and 'Mieter 2' in text and 'Haus A' in text


def test_klarname_bleibt_stehen(app_ctx):
    _bestand()
    text = probe.Anonym(['Heinemann']).text('Bruno Heinemann und Anna Kowalski')
    assert text == 'Heinemann und Mieter 1'


def test_kopie_des_bestands_bleibt_nicht_liegen(tmp_path):
    """PR #25 (Copilot): die Kopie samt Zugangsdaten blieb im Temp-Ordner."""
    import os
    import sqlite3
    import subprocess
    import sys

    sqlite3.connect(tmp_path / 'leer.db').close()
    temp = tmp_path / 'temp'
    temp.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATA_DIR')}
    env.update(TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp))
    lauf = subprocess.run([sys.executable, str(WURZEL / 'scripts' / 'praxisprobe.py'),
                           str(tmp_path / 'leer.db'), '--aus', str(tmp_path / 'bericht.md')],
                          env=env, capture_output=True, text=True, timeout=120)
    assert lauf.returncode == 0, lauf.stderr[-2000:]
    assert (tmp_path / 'bericht.md').is_file()
    assert not list(temp.glob('praxisprobe-*'))
