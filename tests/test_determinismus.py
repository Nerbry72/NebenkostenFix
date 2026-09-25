"""NK-039: gleiche Eingabe, gleiches Blatt.

Eine Abrechnung, die zweimal anders aussieht, ist vor dem Mieter nicht zu
vertreten. Widerspricht er, wird gerechnet und verglichen -- und wenn dabei
eine andere Zahl oder auch nur eine andere Reihenfolge herauskommt als auf dem
Blatt in seiner Hand, steht die Abrechnung als Ganzes in Frage.

Determinismus heisst hier: **dieselbe Eingabe ergibt dasselbe JSON**, Zeichen
fuer Zeichen. Er heisst ausdruecklich *nicht*, dass die Reihenfolge der
Eingabe egal waere -- die Posten stehen in der Reihenfolge, in der der Lader
sie liefert, und genau darum muss der Lader eine feste Reihenfolge liefern.
Das ist die zweite Haelfte dieser Karte (F-22, F-23, F-24).

Drei Lagen:

1. **Der Kern** rechnet zweimal dasselbe -- auch in einem zweiten Prozess mit
   anderem ``PYTHONHASHSEED``.
2. **Kein Wackelkandidat im Kern**: keine Uhr, kein Zufall, keine Schleife
   ueber eine Menge.
3. **Der Lader** ordnet jede Abfrage bis zur Eindeutigkeit.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

import abrechnungsdaten
import rechenkern
from abrechnungsdaten import lade_vorgang, lade_zaehler
from rechenkern import rechne
from tests import billing_factories as f
from tests.determinismus_lauf import als_json, baue_vorgang

LAUF = Path(__file__).resolve().parent / 'determinismus_lauf.py'


# --- 1. Der Kern rechnet zweimal dasselbe ----------------------------------


def test_zweimal_rechnen_gibt_dasselbe_json():
    """Der naheliegende Fall: derselbe Vorgang, zweimal durch den Kern."""
    vorgang = baue_vorgang()
    assert als_json(rechne(vorgang)) == als_json(rechne(vorgang))


def test_zwei_gleichwertige_vorgaenge_geben_dasselbe_json():
    """Nicht dasselbe Objekt, sondern ein zweites mit denselben Werten.

    Faellt ein Ergebnis an einer Objektkennung fest (``id()``, einem Hash oder
    einer Mengeniteration), bricht es hier und nicht oben.
    """
    assert als_json(rechne(baue_vorgang())) == als_json(rechne(baue_vorgang()))


@pytest.mark.parametrize('streuwert', ['0', '1', '42', '31337'])
def test_anderer_hashseed_gibt_dasselbe_json(streuwert):
    """Derselbe Lauf in einem eigenen Prozess mit anderem ``PYTHONHASHSEED``.

    Innerhalb eines Prozesses steht der Streuwert fest; erst ein zweiter
    Prozess deckt auf, wenn die Reihenfolge einer Menge oder eines Hashes ins
    Ergebnis durchschlaegt.
    """
    umgebung = dict(os.environ, PYTHONHASHSEED=streuwert, PYTHONDONTWRITEBYTECODE='1')
    lauf = subprocess.run(
        [sys.executable, str(LAUF)],
        capture_output=True, text=True, check=True, env=umgebung,
    )
    assert lauf.stdout == als_json(rechne(baue_vorgang()))


def test_das_blatt_ist_nicht_leer():
    """Damit die drei Proben oben nicht zwei leere Zeichenketten vergleichen."""
    ergebnis = rechne(baue_vorgang())
    assert len(ergebnis['line_items']) == 3
    assert ergebnis['total_amount'] > 0
    assert len(json.loads(als_json(ergebnis))['prepayments']) == 4


# --- 2. Kein Wackelkandidat im Kern ----------------------------------------


KERN_DATEIEN = ('rechenkern.py', 'geld.py', 'abrechnungsdaten.py')

# Uhr und Zufall. ``date.today()`` ist der gefaehrlichste davon: eine
# Abrechnung, die von ihrem Rechentag abhaengt, sieht ein Jahr spaeter anders
# aus als im Briefkasten.
VERBOTENE_AUFRUFE = frozenset({
    'today', 'now', 'utcnow', 'fromtimestamp', 'time', 'monotonic',
    'random', 'randint', 'choice', 'shuffle', 'sample', 'uuid1', 'uuid4',
})
VERBOTENE_MODULE = frozenset({'random', 'uuid', 'secrets'})


def _baum(dateiname):
    pfad = Path(rechenkern.__file__).resolve().parent / dateiname
    return ast.parse(pfad.read_text(encoding='utf-8'), filename=dateiname)


@pytest.mark.parametrize('dateiname', KERN_DATEIEN)
def test_keine_uhr_und_kein_zufall(dateiname):
    baum = _baum(dateiname)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for name in knoten.names:
                assert name.name.split('.')[0] not in VERBOTENE_MODULE, \
                    f'{dateiname} importiert {name.name}'
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            assert knoten.module.split('.')[0] not in VERBOTENE_MODULE, \
                f'{dateiname} importiert aus {knoten.module}'
        elif isinstance(knoten, ast.Call):
            aufgerufen = knoten.func
            name = aufgerufen.attr if isinstance(aufgerufen, ast.Attribute) else (
                aufgerufen.id if isinstance(aufgerufen, ast.Name) else None
            )
            assert name not in VERBOTENE_AUFRUFE, \
                f'{dateiname}:{knoten.lineno} ruft {name}() -- Uhr oder Zufall im Rechenweg'


def _mengen_namen(baum):
    """Namen, hinter denen nachweislich eine Menge steckt."""
    namen = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Assign):
            continue
        ist_menge = (
            isinstance(knoten.value, ast.Set)
            or isinstance(knoten.value, ast.SetComp)
            or (isinstance(knoten.value, ast.Call)
                and isinstance(knoten.value.func, ast.Name)
                and knoten.value.func.id in ('set', 'frozenset'))
        )
        if ist_menge:
            namen.update(z.id for z in knoten.targets if isinstance(z, ast.Name))
    return namen


@pytest.mark.parametrize('dateiname', KERN_DATEIEN)
def test_ueber_keine_menge_wird_iteriert(dateiname):
    """Mengen duerfen fragen ``ist x drin``, aber nicht die Reihenfolge setzen.

    Die Reihenfolge einer Menge haengt am Streuwert des Prozesses. Wer ueber
    eine Menge laeuft und dabei Posten aufbaut, baut sie in wechselnder
    Reihenfolge auf -- ``sorted()`` davor genuegt und kostet nichts.
    """
    baum = _baum(dateiname)
    mengen = _mengen_namen(baum)
    for knoten in ast.walk(baum):
        quellen = []
        if isinstance(knoten, (ast.For, ast.AsyncFor)):
            quellen.append(knoten.iter)
        elif isinstance(knoten, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            quellen.extend(g.iter for g in knoten.generators)
        for quelle in quellen:
            assert not isinstance(quelle, (ast.Set, ast.SetComp)), \
                f'{dateiname}:{knoten.lineno} laeuft ueber eine Menge'
            if isinstance(quelle, ast.Name):
                assert quelle.id not in mengen, \
                    f'{dateiname}:{knoten.lineno} laeuft ueber die Menge {quelle.id}'


# --- 3. Der Lader ordnet bis zur Eindeutigkeit -----------------------------


def _ketten(baum):
    """Jeder ``.all()``/``.first()``-Aufruf mit den Methoden davor.

    Liefert (Zeile, Endmethode, Liste der Methodennamen der Kette).
    """
    gefunden = []
    for knoten in ast.walk(baum):
        if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)):
            continue
        if knoten.func.attr not in ('all', 'first'):
            continue
        kette, stelle = [], knoten.func.value
        while isinstance(stelle, ast.Call) and isinstance(stelle.func, ast.Attribute):
            kette.append((stelle.func.attr, stelle))
            stelle = stelle.func.value
        gefunden.append((knoten.lineno, knoten.func.attr, list(reversed(kette))))
    return gefunden


def test_jede_abfrage_im_lader_endet_auf_der_kennung():
    """Ohne ``ORDER BY`` gibt die Datenbank *irgendeine* Reihenfolge zurueck.

    SQLite liefert meist die Einfuegereihenfolge, und darum faellt eine
    fehlende Ordnung im Alltag nicht auf -- bis ein Index dazukommt, die
    Datenbank wechselt oder eine Zeile nachtraeglich geaendert wird. Auch ein
    ``order_by`` auf einem Datum genuegt nicht: zwei Ablesungen am selben Tag
    stehen dann in unbestimmter Reihenfolge. Das letzte Ordnungskriterium
    muss eindeutig sein, also die Kennung.
    """
    baum = _baum('abrechnungsdaten.py')
    for zeile, endmethode, kette in _ketten(baum):
        namen = [name for name, _ in kette]
        assert 'order_by' in namen, \
            f'abrechnungsdaten.py:{zeile}: .{endmethode}() ohne order_by'
        letztes = [k for name, k in kette if name == 'order_by'][-1]
        schluessel = letztes.args[-1]
        assert isinstance(schluessel, ast.Attribute) and schluessel.attr == 'id', \
            (f'abrechnungsdaten.py:{zeile}: das letzte Ordnungskriterium ist nicht '
             f'die Kennung -- bei Gleichstand ist die Reihenfolge offen')


def test_zahlungen_kommen_chronologisch(app_ctx):
    """F-22: die Vorauszahlungen standen in der Reihenfolge der Eingabe.

    Wer eine vergessene Zahlung nachtraegt, bekam sie ans Ende des Blattes
    gesetzt statt an ihren Platz im Jahr.
    """
    prop = f.house()
    wohnung = f.apt(prop, 'EG links', 50.0)
    mieter = f.tenant(wohnung, 'Anna Mieterin')
    for tag in (6, 3, 12, 9):
        f.payment(mieter, 100.0, date(2024, tag, 1))

    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    assert [z.datum for z in vorgang.zahlungen] == [
        date(2024, 3, 1), date(2024, 6, 1), date(2024, 9, 1), date(2024, 12, 1),
    ]


def test_zwei_ablesungen_am_selben_tag_stehen_fest(app_ctx):
    """F-23: ``order_by(reading_date)`` allein laesst den Gleichstand offen.

    Zwei Ablesungen am selben Tag gibt es wirklich: beim Mieterwechsel liest
    der Vermieter fuer den Auszug ab und traegt kurz darauf den Einzug nach.
    Welcher Stand dann als der des Tages gilt, darf nicht davon abhaengen,
    wie die Datenbank den Gleichstand aufloest.

    Dieser Test haelt die Zusage fest, er beweist die Luecke nicht: SQLite
    liest die Tabelle in Zeilenfolge und trifft damit heute zufaellig das
    Richtige. Den Nachweis fuehrt der Waechter darueber -- eine Ordnung, die
    nur zufaellig stimmt, ist keine.
    """
    prop = f.house()
    wohnung = f.apt(prop, 'EG links', 50.0)
    kategorie = f.category('Wasser')
    zaehler = f.meter(prop, kategorie, 'W-1', is_main=False, apartment=wohnung)
    f.reading(zaehler, date(2024, 1, 1), 0.0)
    f.reading(zaehler, date(2024, 6, 30), 120.0)
    f.reading(zaehler, date(2024, 6, 30), 125.0)
    f.reading(zaehler, date(2024, 12, 31), 300.0)

    geladen = lade_zaehler(zaehler.id)

    assert [s.wert for s in geladen.staende] == [0.0, 120.0, 125.0, 300.0]


def test_die_wasserkategorie_ist_dieselbe_bei_jedem_lauf(app_ctx):
    """F-24, seit NK-055 am Objekt: die Kopplung waehlt fest und wiederholbar.

    Der Seed bringt ``Wasserversorgung`` und ``Warmwasser`` mit; kommt
    ``Wasser Garten`` dazu, entscheidet ohne ``order_by`` die Datenbank, an
    welchem Zaehler das Abwasser haengt. Die Kopplung sucht jetzt nur noch
    unter den Kostenarten, die an **dieser** Immobilie einen Zaehler haben
    (D-56), und nimmt unter ihnen die kleinste Kennung -- Warmwasser scheidet
    aus, denn sein Zaehler misst § 8, nicht das Frischwasser. Welches
    Frischwasser die richtige ist, wenn es mehrere sind, bleibt eine
    Sachfrage; dass es bei jedem Lauf dieselbe ist, gehoert hierher.
    """
    from models import CostCategory, Meter, db

    haus = f.house(name='Gartenhaus')
    wng = f.apt(haus, 'G-EG', 50.0)
    f.tenant(wng, 'Gartenmieter', move_in=date(2024, 1, 1))
    wasser = CostCategory.query.filter_by(name='Wasserversorgung').first()
    warm = CostCategory.query.filter_by(name='Warmwasser').first()
    garten = CostCategory(name='Wasser Garten', allocation_method='PER_SQM',
                          requires_meter=True, betrkv_nr=10)
    db.session.add(garten)
    db.session.commit()
    # Alle drei haengen am selben Objekt; ohne die neue Eingrenzung waere
    # Warmwasser (kleinste Kennung) der Name-nach-Treffer.
    for kat, nummer in ((wasser, 'W-1'), (garten, 'G-1'), (warm, 'WW-1')):
        db.session.add(Meter(category_id=kat.id, property_id=haus.id,
                             is_main_meter=True, meter_number=nummer))
    db.session.commit()

    treffer = {abrechnungsdaten._wasser_kategorie_id(haus.id)
               for _ in range(5)}

    assert len(treffer) == 1
    assert treffer == {wasser.id}
