"""Der Wächter über den Fehlerkanal im Quellbaum (NK-042).

NK-030 hat fünf ``print(`` und elf blanke ``except Exception`` beseitigt,
NK-042 die letzten drei Reste. Damit ist die Abnahmebedingung der Phase 2
erfüllt — aber eine einmal aufgeräumte Datei bleibt nicht von selbst
aufgeräumt. Ein ``print`` beim Suchen eines Fehlers ist in fünf Sekunden
geschrieben und wird in fünf Monaten nicht mehr gefunden.

Deshalb misst dieser Wächter den Quellbaum bei jedem Lauf gegen vier Regeln:

1. **Kein blankes ``except:``.** Es fängt auch ``KeyboardInterrupt`` und
   ``SystemExit`` — wer den Container anhält, sieht sein Signal verschwinden.
2. **Kein ``except …: pass``.** Ein Fehler, über den nirgends etwas steht,
   ist ein Fehler, den niemand findet.
3. **Kein ``print(``.** ``docker logs`` zeigt es zwar an, aber ohne
   Zeitstempel, ohne Stufe, ohne Herkunft, und abdrehen lässt es sich nicht.
4. **Jedes ``except Exception`` protokolliert oder reicht weiter.** Wer so
   breit fängt, fängt auch das, was er nicht gemeint hat; dann muss wenigstens
   eine Zeile darüber existieren.

Geprüft wird der **Anwendungsquellbaum**: die Module, die im Abbild landen und
zur Laufzeit beim Vermieter laufen. ``tests/`` fällt heraus (dort ist ein
``print`` beim Suchen legitim und ein ``except: pass`` manchmal der Kern der
Prüfung), ``scripts/`` ebenso — das sind Werkzeuge, die auf einer Konsole
laufen und ihre Ausgabe genau dorthin schreiben sollen. ``migrations/env.py``
gehört Alembic.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


WURZEL = Path(__file__).resolve().parents[1]

# Verzeichnisse, die nicht zum Anwendungsquellbaum zaehlen. Jeder Eintrag ist
# eine Entscheidung, keine Bequemlichkeit -- der Kopf dieser Datei begruendet
# sie einzeln.
AUSSERHALB = {
    'tests', 'scripts', 'migrations',
    '.venv', 'venv', 'node_modules', '.git', 'static', 'frontend',
    '__pycache__', 'nas-sandbox', 'backups', 'data',
    # NK-079: Bauwerkzeug der Windows-App (Spezifikation, Paketprobe der CI).
    # Laeuft auf der Konsole des Bauers wie scripts/, nie beim Vermieter.
    'packaging',
}

# Womit eine Zeile ins Protokoll kommt.
PROTOKOLLRUFE = {'debug', 'info', 'warning', 'warn', 'error', 'exception', 'critical'}

BREIT = {'Exception', 'BaseException'}


def quelldateien() -> list[Path]:
    return sorted(
        pfad for pfad in WURZEL.rglob('*.py')
        if not set(pfad.relative_to(WURZEL).parts) & AUSSERHALB
    )


def _ort(pfad: Path, knoten) -> str:
    return f'{pfad.relative_to(WURZEL)}:{knoten.lineno}'


def _protokolliert_oder_reicht_weiter(handler: ast.ExceptHandler) -> bool:
    """Steht im Rumpf irgendwo eine Protokollzeile oder ein ``raise``?

    Rekursiv, weil das Protokollieren oft in einem ``if`` steht -- und ein
    ``raise`` zaehlt mit: wer weiterreicht, ueberlaesst die Zeile der zentralen
    Fehlerbehandlung in fehler.py, die genau dafuer da ist.
    """
    for knoten in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(knoten, ast.Raise):
            return True
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute):
            if knoten.func.attr in PROTOKOLLRUFE:
                return True
    return False


def pruefe(quelltext: str, name: str = '<test>') -> list[str]:
    """Die vier Regeln gegen einen Quelltext. Leere Liste heisst: sauber.

    Als eigene Funktion, damit die Regeln selbst pruefbar sind: ein Waechter,
    der gegen einen sauberen Baum gruen ist, koennte auch schlicht kaputt sein.
    """
    verstoesse = []
    baum = ast.parse(quelltext, filename=name)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ExceptHandler):
            ort = f'{name}:{knoten.lineno}'
            if knoten.type is None:
                verstoesse.append(f'{ort}: blankes except')
                continue
            if all(isinstance(satz, ast.Pass) for satz in knoten.body):
                verstoesse.append(f'{ort}: except ohne Rumpf (pass)')
                continue
            typen = ast.unparse(knoten.type).strip('()')
            if any(t.strip() in BREIT for t in typen.split(',')):
                if not _protokolliert_oder_reicht_weiter(knoten):
                    verstoesse.append(f'{ort}: except {typen} ohne Protokollzeile')
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name):
            if knoten.func.id == 'print':
                verstoesse.append(f'{name}:{knoten.lineno}: print als Ausgabekanal')
    return verstoesse


# --- Der Waechter selbst -----------------------------------------------------


def test_der_waechter_sieht_ueberhaupt_etwas():
    """Sonst waere er gruen, weil er nichts findet.

    Ein Waechter, dessen Dateiliste leer laeuft -- verschobener Ordner,
    vertippter Ausschluss -- meldet genau so lange nichts, bis es zu spaet ist.
    """
    dateien = quelldateien()

    assert len(dateien) >= 10
    namen = {pfad.name for pfad in dateien}
    assert {'app.py', 'fehler.py', 'backup.py', 'rechenkern.py'} <= namen


@pytest.mark.parametrize('murks,erwartet', [
    ('try:\n    x()\nexcept:\n    pass\n', 'blankes except'),
    ('try:\n    x()\nexcept ValueError:\n    pass\n', 'ohne Rumpf'),
    ('print("Fehler beim Speichern")\n', 'print als Ausgabekanal'),
    ('try:\n    x()\nexcept Exception:\n    return None\n', 'ohne Protokollzeile'),
    ('try:\n    x()\nexcept (OSError, Exception):\n    return None\n', 'ohne Protokollzeile'),
])
def test_der_waechter_schlaegt_an(murks, erwartet):
    verstoesse = pruefe(murks)

    assert len(verstoesse) == 1, verstoesse
    assert erwartet in verstoesse[0]


@pytest.mark.parametrize('sauber', [
    'try:\n    x()\nexcept ValueError:\n    return "-"\n',
    'try:\n    x()\nexcept Exception:\n    protokoll.exception("ging nicht")\n',
    'try:\n    x()\nexcept Exception:\n    if laut:\n        log.warning("ging nicht")\n',
    'try:\n    x()\nexcept Exception:\n    raise\n',
    'try:\n    x()\nexcept OSError as f:\n    protokoll.warning("%s", f)\n',
])
def test_der_waechter_laesst_richtiges_durch(sauber):
    assert pruefe(sauber) == []


# --- Der Quellbaum -----------------------------------------------------------


def test_kein_blankes_except_kein_print_kein_stiller_schlucker():
    """Die Abnahmebedingung der Phase 2, jeden Lauf neu gemessen."""
    verstoesse = []
    for pfad in quelldateien():
        verstoesse += pruefe(pfad.read_text(encoding='utf-8'),
                             str(pfad.relative_to(WURZEL)))

    assert verstoesse == [], 'Fehlerkanal am Protokoll vorbei:\n' + '\n'.join(verstoesse)
