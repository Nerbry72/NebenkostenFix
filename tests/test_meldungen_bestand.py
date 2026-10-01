"""NK-192: Meldungen nach den Richtwerten D-116.

Höchstens 3 Meldungen sichtbar, der Rest aufklappbar. Jede Meldung sagt,
was zu tun ist. Keine zwei Meldungen mit demselben Inhalt, keine Kennung
vorne. Die Praxisprobe fand (F-125): eine Preiswarnung je Rechnung statt je
Zähler, „Zähler Zähler 7“, Daten im ISO-Format und „Tragen Sie … und
erzeuge …“. Alle Werte sind erfunden.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from nebenkostenfix import co2, heizung, rechenkern
from nebenkostenfix.billing_engine import BillingEngine
from tests import billing_factories as f

APP_JS = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text(encoding='utf-8')

#: Texte fuer das PDF, keine Meldungen an den Vermieter.
FUSSNOTEN = {'HINWEIS_ANTEIL'}


def _vorlagen():
    for modul in (rechenkern, heizung, co2):
        for name, text in vars(modul).items():
            if name.startswith('HINWEIS') and isinstance(text, str) and name not in FUSSNOTEN:
                yield f'{modul.__name__}.{name}', text


@pytest.mark.parametrize(('name', 'text'), list(_vorlagen()))
def test_jede_meldung_sagt_was_zu_tun_ist(name, text):
    assert re.search(r'\bSie\b', text), name
    assert not re.search(r'\b(erzeuge|trage|du|dein\w*)\b', text), name


def _wasserhaus(nummer='Zähler 7'):
    """Der Hauptzähler ist nur vom 01.02. bis 01.11. abgelesen, zwei Halbjahresrechnungen."""
    haus = f.house()
    kat = f.category('Wasserversorgung')
    haupt = f.meter(haus, kat, nummer, is_main=True)
    f.reading(haupt, date(2025, 2, 1), 0.0)
    f.reading(haupt, date(2025, 11, 1), 90.0)
    mieter = []
    for i, name in enumerate(('EG', 'OG'), 1):
        wohnung = f.apt(haus, name, 50)
        m = f.tenant(wohnung, f'Mieter {i}', move_in=date(2020, 1, 1))
        z = f.meter(haus, kat, f'W-{i}', is_main=False, apartment=wohnung)
        f.reading(z, date(2025, 1, 1), 0.0)
        f.reading(z, date(2025, 12, 31), 40.0)
        f.profile(m, kat, 'direkt')
        mieter.append(m)
    f.invoice(haus, kat, 300.0, start=date(2025, 1, 1), end=date(2025, 6, 30), invoice_number='R-1')
    f.invoice(haus, kat, 300.0, start=date(2025, 7, 1), end=date(2025, 12, 31), invoice_number='R-2')
    return mieter[0]


def _preiswarnungen(mieter):
    ergebnis = BillingEngine(mieter.id, '2025-01-01', '2025-12-31').calculate_bill()
    return [w for w in ergebnis['warnings'] if 'W-ZAEHLER-PREIS-HOCHGERECHNET' in w]


def test_eine_preiswarnung_je_zaehler_nicht_je_rechnung(app_ctx):
    assert _preiswarnungen(_wasserhaus()) == [
        'W-ZAEHLER-PREIS-HOCHGERECHNET · Der Einheitspreis für „Wasserversorgung“ ist '
        'geschätzt: Die Ablesungen von Zähler 7 decken die Rechnungszeiträume '
        '01.01.2025–30.06.2025 und 01.07.2025–31.12.2025 nicht ab. Tragen Sie Ablesungen '
        'zu Beginn und Ende der Rechnungen nach und erstellen Sie die Abrechnung erneut.']


def test_zaehlernummer_ohne_wort_davor(app_ctx):
    [warnung] = _preiswarnungen(_wasserhaus(nummer='HWZ-3'))
    assert 'Zähler HWZ-3' in warnung


def test_keine_meldung_doppelt(app_ctx):
    warnungen = BillingEngine(_wasserhaus().id, '2025-01-01', '2025-12-31').calculate_bill()['warnings']
    assert len(warnungen) == len(set(warnungen))
    assert not any(re.search(r'\d{4}-\d{2}-\d{2}', w) for w in warnungen)
    assert not any('Zähler Zähler' in w for w in warnungen)


# --- Oberfläche: höchstens 3 sichtbar ------------------------------------------------

def _funktionsrumpf(name: str) -> str:
    beginn = re.search(rf'function {name}\(', APP_JS).start()
    return APP_JS[beginn:APP_JS.index('\n}', beginn) + 2]


@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
@pytest.mark.parametrize(('anzahl', 'sichtbar', 'weitere'), [(3, 3, None), (5, 3, '2 weitere Hinweise')])
def test_hoechstens_drei_hinweise_sichtbar(anzahl, sichtbar, weitere):
    warnungen = [f'Meldung {i} ist offen. Prüfen Sie Punkt {i}.' for i in range(anzahl)]
    code = ''.join(_funktionsrumpf(n) for n in ('escapeHtml', 'warnungenBuendeln', 'warnungenHtml'))
    html = subprocess.run(['node', '-e', code + f'console.log(JSON.stringify(warnungenHtml({json.dumps(warnungen)})));'],
                          capture_output=True, text=True, check=True).stdout
    html = json.loads(html)
    oben, _, zu = html.partition('<details class="weitere-hinweise">')
    assert oben.count('<li title=') == sichtbar
    assert (f'<summary>{weitere}</summary>' in zu) if weitere else not zu
    assert all(f'Meldung {i} ist offen.' in html for i in range(anzahl))
