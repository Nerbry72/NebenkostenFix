"""F-113: Stromzaehler heissen in der Oberflaeche "Strom".

Befund aus dem Echtbetrieb: Haupt- und Wohnungszaehler fuer Strom haengen an
BetrKV Nr. 11 "Beleuchtung (Allgemeinstrom)", weil der Allgemeinstrom aus
ihnen gerechnet wird (Hauptzaehler minus Wohnungszaehler). Die Zaehlerliste
bot deshalb nur "Beleuchtung (Allgemeinstrom)" an -- fuer einen
Wohnungszaehler falsch. Eine neue Kostenart gibt es dafuer nicht (Entscheidung vom
30.09.2026); die Zaehleransicht zeigt einen Alltagsnamen, Kostenart,
Rechnungen und PDF behalten den Namen aus der BetrKV.

*Haette den Befund gefunden:* ``test_zaehlerstellen_zeigen_den_alltagsnamen``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / 'static' / 'app.js'
QUELLE = APP_JS.read_text(encoding='utf-8')


def _funktionsrumpf(name: str) -> str:
    beginn = re.search(rf'(async )?function {name}\(', QUELLE).start()
    return QUELLE[beginn:QUELLE.index('\n}', beginn)]


@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
def test_alltagsname_fuer_strom_sonst_unveraendert():
    beginn = QUELLE.index('const ZAEHLER_ANZEIGENAMEN')
    code = QUELLE[beginn:QUELLE.index('\n}', beginn) + 2] + (
        'console.log(JSON.stringify(['
        'zaehlerArtName("Beleuchtung (Allgemeinstrom)"),'
        'zaehlerArtName("Wasserversorgung"), zaehlerArtName(undefined)]));')
    aus = subprocess.run(['node', '-e', code], capture_output=True, text=True,
                         check=True).stdout
    assert json.loads(aus) == ['Strom', 'Wasserversorgung', None]


def test_zaehlerstellen_zeigen_den_alltagsnamen():
    """Jede Stelle, die einen Zaehler beschriftet, geht durch zaehlerArtName."""
    zaehlerliste = _funktionsrumpf('renderMeters')
    assert 'tdCat.textContent = zaehlerArtName(m.category_name)' in zaehlerliste
    auswahl = _funktionsrumpf('openAddMeterModal')
    assert auswahl.count('escapeHtml(zaehlerArtName(c.name))') == 2
    assert 'escapeHtml(c.name)' not in auswahl
    assert '(${zaehlerArtName(meter.category_name)})' in _funktionsrumpf('openHistoryModal')


def test_kostenart_behaelt_den_betrkv_namen():
    """Rechnungen buchen auf die Kostenart -- dort bleibt der BetrKV-Name."""
    assert 'escapeHtml(c.name)' in _funktionsrumpf('openAddInvoiceModal')
