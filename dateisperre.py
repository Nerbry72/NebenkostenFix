"""Exklusive Dateisperre fuer mehrere Prozesse, plattformneutral (NK-149, F-81).

Unter Linux (Docker, gunicorn mit mehreren Arbeitern) sperrt ``fcntl.flock``,
unter Windows (Desktop-App, ein Prozess mit Threads) ``msvcrt.locking`` auf
dem ersten Byte der Sperrdatei. Fehlt beides, bleibt eine Sperre innerhalb
des Prozesses -- mehr ist dort ohnehin nicht noetig, weil es ohne ``fcntl``
keinen Mehrprozessbetrieb gibt.

Die Sperre ist beratend: sie schuetzt nur vor Aufrufern, die sie ebenfalls
nehmen. Genau das ist der Zweck -- zwei Arbeiter derselben Anwendung sollen
eine Datei nicht gleichzeitig anlegen oder fortschreiben.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from contextlib import contextmanager

try:  # Linux, macOS
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:  # Windows
    import msvcrt
except ImportError:
    msvcrt = None

# Innerhalb eines Prozesses schuetzt flock nicht zwischen Threads, die
# dieselbe Datei getrennt oeffnen (je Oeffnung eigene Sperre auf Linux,
# aber msvcrt sperrt je Handle). Darum zusaetzlich eine Prozesssperre je Pfad.
_prozess_sperren: dict[str, threading.Lock] = {}
_verwaltung = threading.Lock()


def _prozess_sperre(pfad: str) -> threading.Lock:
    schluessel = os.path.abspath(pfad)
    with _verwaltung:
        sperre = _prozess_sperren.get(schluessel)
        if sperre is None:
            sperre = _prozess_sperren[schluessel] = threading.Lock()
        return sperre


@contextmanager
def dateisperre(pfad: str):
    """Haelt die Sperre auf ``pfad`` fuer die Dauer des ``with``-Blocks.

    Die Sperrdatei wird bei Bedarf angelegt und bleibt liegen; sie traegt
    keinen Inhalt. Der Ordner muss existieren.
    """
    with _prozess_sperre(pfad):
        with open(pfad, 'a+b') as datei:
            if fcntl is not None:
                fcntl.flock(datei.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(datei.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                datei.seek(0)
                while True:
                    try:
                        msvcrt.locking(datei.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    datei.seek(0)
                    msvcrt.locking(datei.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - weder fcntl noch msvcrt
                yield


def datei_einmalig_anlegen(pfad: str, inhalt: str, *, modus: int = 0o600,
                           warten_s: float = 5.0) -> tuple[str, bool]:
    """Legt ``pfad`` mit ``inhalt`` an, wenn es ihn noch nicht gibt (F-74).

    Rueckgabe: (Inhalt der Datei, neu_angelegt). Wer verliert, liest immer
    eine vollstaendige Datei: geschrieben wird in eine Temp-Datei im selben
    Ordner, die erst danach per ``os.link`` den endgueltigen Namen bekommt.
    ``os.link`` scheitert, wenn das Ziel schon existiert -- genau ein Aufrufer
    gewinnt, und sein Inhalt steht in dem Augenblick schon vollstaendig da.

    Kann das Dateisystem keine harten Verweise (manche Netzlaufwerke), faellt
    die Funktion auf ``O_EXCL`` zurueck; der Leser wartet dann bis zu
    ``warten_s`` Sekunden, bis die Datei Inhalt hat.
    """
    ordner = os.path.dirname(os.path.abspath(pfad))
    if os.path.exists(pfad):
        return _lies_vollstaendig(pfad, warten_s), False
    temp = os.path.join(
        ordner, f'.{os.path.basename(pfad)}.{os.getpid()}.'
                f'{threading.get_ident()}.tmp')
    kennung = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modus)
    with os.fdopen(kennung, 'w', encoding='utf-8') as datei:
        datei.write(inhalt)
        datei.flush()
        os.fsync(datei.fileno())
    try:
        try:
            os.link(temp, pfad)
            return inhalt, True
        except FileExistsError:
            return _lies_vollstaendig(pfad, warten_s), False
        except (OSError, NotImplementedError, AttributeError):
            return _anlegen_exklusiv(pfad, inhalt, modus, warten_s)
    finally:
        # Die Temp-Datei ist nach dem Verweis ueberfluessig; fehlt sie, ist
        # das Ergebnis dasselbe.
        with contextlib.suppress(OSError):
            os.unlink(temp)


def _anlegen_exklusiv(pfad, inhalt, modus, warten_s):
    """Rueckfall ohne harte Verweise: O_EXCL, Leser wartet auf Inhalt."""
    try:
        kennung = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, modus)
    except FileExistsError:
        return _lies_vollstaendig(pfad, warten_s), False
    with os.fdopen(kennung, 'w', encoding='utf-8') as datei:
        datei.write(inhalt)
    return inhalt, True


def _lies_vollstaendig(pfad, warten_s):
    """Liest die Datei; leer heisst: der Schreiber ist noch nicht fertig."""
    ende = time.monotonic() + warten_s
    while True:
        with open(pfad, encoding='utf-8') as datei:
            inhalt = datei.read()
        if inhalt.strip() or time.monotonic() >= ende:
            return inhalt
        time.sleep(0.02)
