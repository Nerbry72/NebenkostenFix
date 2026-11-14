"""Probe am gebauten macOS-Bundle mit echtem Fenster (#44) -- für die CI.

    python packaging/macos/fensterprobe.py <NebenkostenFix.app> <bericht.json>

Startet die App wie aus dem Finder (``open``), wartet auf ``instanz.json``
und prüft dann:
  - ``/huelle/nach-vorne`` mit dem Token: 204, also laufen Fenster und Server,
  - nach der Einrichtung eines Testkontos die Update-Suche: kein 502, also
    geht HTTPS im eingefrorenen Paket (Risiko B0.6),
  - Beenden wie Cmd-Q (Ereignis „Beenden“ an genau dieses Bundle): der Prozess endet, die WAL-Datei ist
    leer oder weg, ``instanz.json`` ist weg.

Erwartet einen frischen Runner: Die App nimmt ihren Vorgabeordner unter
``~/Library/Application Support/NebenkostenFix``. Ist ``LOCALAPPDATA``
gesetzt, bekommt die App es mit, und Probe wie App nehmen den Ordner dort
(eine Probe auf einem echten Mac berührt so dessen Daten nicht). Jede Prüfung schreibt eine
Zeile in die Zusammenfassung des Laufs; Exit 1, wenn eine nicht besteht.
Der Bericht entsteht auch, wenn unterwegs etwas scheitert, und eine App,
die danach noch läuft, wird beendet.
Nur Standardbibliothek.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

FRIST = 90


def _zusammenfassung(zeile: str) -> None:
    print(zeile)
    ziel = os.environ.get('GITHUB_STEP_SUMMARY')
    if ziel:
        with open(ziel, 'a', encoding='utf-8') as datei:
            datei.write(zeile + '\n')


def app_ordner() -> Path:
    """Wie ``windows_ordner.lokaler_ordner()`` der App."""
    basis = os.environ.get('LOCALAPPDATA')
    return (Path(basis) if basis else Path.home() / 'Library' / 'Application Support') / 'NebenkostenFix'


def startbefehl(app: Path) -> list[str]:
    """Wie ein Doppelklick im Finder; ``LOCALAPPDATA`` reicht ``open`` weiter."""
    befehl = ['/usr/bin/open', '-n']
    if os.environ.get('LOCALAPPDATA'):
        befehl += ['--env', f"LOCALAPPDATA={os.environ['LOCALAPPDATA']}"]
    return befehl + [str(app)]


def instanz_lesen(ordner: Path) -> tuple[int, str] | None:
    """Port und Token der laufenden App, sobald sie ``instanz.json`` geschrieben hat."""
    try:
        info = json.loads((ordner / 'instanz.json').read_text(encoding='utf-8'))
        return int(info['port']), str(info['token'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def wal_leer(datenordner: Path) -> bool:
    wal = datenordner / 'nebenkosten.db-wal'
    return not wal.exists() or wal.stat().st_size == 0


def update_suche_ok(code: int | None) -> bool:
    """Unter macOS antwortet die Suche mit 200; 400 kommt bei einem Manifest,
    das nicht passt -- auch dann war die Quelle erreicht. 502 heißt: keine
    Verbindung, etwa kein HTTPS im Paket (oder GitHub antwortet gerade nicht)."""
    return code in (200, 400)


def _warten(bedingung, frist: float):
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        ergebnis = bedingung()
        if ergebnis:
            return ergebnis
        time.sleep(0.5)
    return None


def _laeuft(programm: str) -> bool:
    return subprocess.run(['/usr/bin/pgrep', '-f', programm], stdout=subprocess.DEVNULL,  # noqa: S603
                          check=False).returncode == 0


def _status(oeffner, anfrage) -> int | None:
    try:
        with oeffner.open(anfrage, timeout=60) as antwort:
            return antwort.status
    except urllib.error.HTTPError as fehler:
        return fehler.code
    except OSError:
        return None


def _ablauf(app: Path, ordner: Path, programm: str, bericht: dict) -> None:
    subprocess.run(startbefehl(app), check=True)  # noqa: S603
    instanz = _warten(lambda: instanz_lesen(ordner), FRIST)
    bericht['instanz'] = instanz is not None
    if instanz:
        port, token = instanz
        basis = f'http://127.0.0.1:{port}'
        direkt = urllib.request.build_opener()
        bericht['nach_vorne'] = _status(direkt, urllib.request.Request(
            basis + '/huelle/nach-vorne', method='POST', headers={'X-Huelle-Token': token}))
        sitzung = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        _status(sitzung, basis + f'/huelle/start?t={token}')
        kennwort = secrets.token_urlsafe(16)
        bericht['einrichtung'] = _status(sitzung, urllib.request.Request(
            basis + '/einrichtung', method='POST', headers={'Content-Type': 'application/json'},
            data=json.dumps({'username': 'fensterprobe', 'password': kennwort,
                             'password2': kennwort}).encode()))
        bericht['update_suche'] = _status(sitzung, basis + '/api/aktualisierung')

    # Wie Cmd-Q: macOS schickt dem Programm das Ereignis „Beenden“ -- an
    # genau dieses Bundle, nicht an eine installierte App gleichen Namens.
    try:
        beenden = subprocess.run(  # noqa: S603
            ['/usr/bin/osascript', '-e', 'on run argv', '-e',
             'tell application (item 1 of argv) to quit', '-e', 'end run', str(app)],
            capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        # Etwa, wenn macOS erst eine Freigabe für die Automatisierung will.
        bericht['quit'] = 'zeitueberschreitung'
    else:
        bericht['quit'] = beenden.returncode
        if beenden.stderr.strip():
            bericht['quit_fehler'] = beenden.stderr.strip()
    bericht['beendet'] = bool(_warten(lambda: not _laeuft(programm), FRIST))


def probe(app: Path, bericht_datei: Path) -> bool:
    app = app.resolve()
    programm = str(app / 'Contents' / 'MacOS' / 'NebenkostenFix')
    ordner = app_ordner()
    bericht: dict = {}
    try:
        _ablauf(app, ordner, programm, bericht)
    except Exception as fehler:  # noqa: BLE001 -- der Bericht soll trotzdem entstehen
        bericht['fehler'] = f'{type(fehler).__name__}: {fehler}'
    finally:
        # Läuft die App noch, hielte sie den Schritt bis zum Zeitlimit offen.
        if _laeuft(programm):
            subprocess.run(['/usr/bin/pkill', '-9', '-f', programm], check=False)  # noqa: S603
            bericht['abgeschossen'] = True
        daten = ordner / 'Daten'
        bericht['datenbank'] = (daten / 'nebenkosten.db').is_file()
        bericht['wal_leer'] = wal_leer(daten)
        bericht['instanz_weg'] = not (ordner / 'instanz.json').exists()
        bericht_datei.write_text(json.dumps(bericht, ensure_ascii=False, indent=2),
                                 encoding='utf-8')

    ok = (bericht.get('instanz') and bericht.get('nach_vorne') == 204
          and update_suche_ok(bericht.get('update_suche')) and bericht.get('beendet')
          and bericht['datenbank'] and bericht['wal_leer'] and bericht['instanz_weg']
          and 'fehler' not in bericht)
    _zusammenfassung(f'- Fensterprobe: {"bestanden" if ok else "FEHLGESCHLAGEN"}, '
                     f'Bericht: `{json.dumps(bericht, ensure_ascii=False)}`')
    return bool(ok)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    return 0 if probe(Path(argv[0]), Path(argv[1])) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
