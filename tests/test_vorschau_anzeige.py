"""F-116: Die Vorschau zeigt Hinweise lesbar statt als Zaehlerkachel.

Befund aus der Abrechnung Mieter 3 auf 6061:

* Die Kachel "Zeitraum (§ 556 Abs. 3 BGB)" stand als Zaehler mit
  "Zähler: N/A" und "Keine ausreichenden Daten" da; ihre Meldung fehlte.
* Der Stromzaehler hiess "Beleuchtung (Allgemeinstrom)" (F-113 galt nur
  fuer die Zaehlerliste).
* Zwei gleiche Warnungen (Entwaesserung, Wasserversorgung) standen voll
  ausgeschrieben untereinander, mit der Kennung vorn.
* Betraege "€53,00", Daten "1.9.2025".

*Haette den Befund gefunden:* jeder Test hier.
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

NEGATIV = ('W-ZAEHLER-ALLGEMEIN-NEGATIV · Für „{}“ zeigen die Wohnungszähler '
           'mehr Verbrauch als der Hauptzähler: -1,3 m³. Andere Kostenarten '
           'bleiben unberührt.')


def _funktionsrumpf(name: str) -> str:
    beginn = re.search(rf'(async )?function {name}\(', QUELLE).start()
    return QUELLE[beginn:QUELLE.index('\n}', beginn) + 2]


def _konstante(name: str) -> str:
    beginn = QUELLE.index(f'const {name} =')
    return QUELLE[beginn:QUELLE.index('\n', beginn) + 1]


def _node(code: str):
    aus = subprocess.run(['node', '-e', code], capture_output=True, text=True, check=True)
    return json.loads(aus.stdout)


@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
def test_gleiche_warnungen_werden_gebuendelt_und_gekuerzt():
    warnungen = [NEGATIV.format('Entwässerung'), NEGATIV.format('Wasserversorgung'),
                 'Der Zeitraum ist länger als ein Jahr. Nach § 556 Abs. 3 BGB '
                 'wird jährlich abgerechnet.']
    ergebnis = _node(_funktionsrumpf('warnungenBuendeln')
                     + f'console.log(JSON.stringify(warnungenBuendeln({json.dumps(warnungen)})));')
    assert ergebnis == [
        {'kurz': 'Für „Entwässerung“ und „Wasserversorgung“ zeigen die Wohnungszähler '
                 'mehr Verbrauch als der Hauptzähler: -1,3 m³.',
         'tun': '',
         'rest': 'Andere Kostenarten bleiben unberührt.',
         'kennung': 'W-ZAEHLER-ALLGEMEIN-NEGATIV'},
        {'kurz': 'Der Zeitraum ist länger als ein Jahr.',
         'tun': '',
         'rest': 'Nach § 556 Abs. 3 BGB wird jährlich abgerechnet.',
         'kennung': ''},
    ]


@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
def test_was_tun_steht_sichtbar_vor_dem_aufklappen():
    """F-132: Die Handlung („Lesen Sie …“) stand unter „Mehr“ versteckt.
    Jetzt steht sie sichtbar; nur die Begründung klappt auf. „bzw.“ beendet
    keinen Satz."""
    warnung = ('W-ZAEHLER-ALLGEMEIN-NEGATIV · Für „Wasserversorgung“ zeigen die '
               'Wohnungszähler mehr Verbrauch als der Hauptzähler: -1,3 m³. '
               'Angesetzt wird nichts. Lesen Sie alle Zähler am selben Tag ab — am '
               'Einzugs- bzw. Auszugstag — und erstellen Sie die Abrechnung erneut.')
    html = _node(''.join(_funktionsrumpf(n) for n in ('escapeHtml', 'warnungenBuendeln', 'warnungenHtml'))
                 + f'console.log(JSON.stringify(warnungenHtml({json.dumps([warnung])})));')
    sichtbar, _, aufgeklappt = html.partition('<details>')
    assert '<strong>Was tun:</strong> Lesen Sie alle Zähler am selben Tag ab — am Einzugs- bzw. ' \
           'Auszugstag — und erstellen Sie die Abrechnung erneut.' in sichtbar
    assert 'Angesetzt wird nichts.' in aufgeklappt and 'Lesen Sie' not in aufgeklappt


@pytest.mark.skipif(shutil.which('node') is None, reason='node fehlt')
def test_datum_und_betrag_im_deutschen_format():
    ergebnis = _node(_konstante('euroText') + _konstante('datumText')
                     + 'console.log(JSON.stringify([datumText("2025-09-01"), euroText(53)]));')
    # toLocaleString trennt Betrag und Zeichen mit einem geschuetzten Leerzeichen.
    assert [t.replace(' ', ' ') for t in ergebnis] == ['01.09.2025', '53,00 €']


def test_vorschau_trennt_hinweise_von_zaehlern():
    vorschau = _funktionsrumpf('generateBillPreview')
    assert 'c.meter_id != null' in vorschau and 'c.meter_id == null && c.message' in vorschau
    assert 'Hinweise zur Abrechnung' in vorschau
    assert 'warnungenHtml(hinweise)' in vorschau
    assert '${escapeHtml(zaehlerArtName(c.category))} (${escapeHtml(c.meter_type)})' in vorschau
    assert "toFixed(2).replace('.', ',')" not in vorschau
    assert "toLocaleDateString('de-DE')" not in vorschau
    assert 'warnungenHtml(daten.warnings)' in _funktionsrumpf('jahrVorschauLaden')
