"""Proben am gebauten Windows-Paket (NK-150, NK-079) -- für die CI.

    python packaging/windows/paketprobe.py fenster  dist/NebenkostenFix/NebenkostenFix.exe
    python packaging/windows/paketprobe.py groesse  dist/NebenkostenFix
    python packaging/windows/paketprobe.py selbsttest <exe> <datenordner> <bericht.json>
    python packaging/windows/paketprobe.py installieren <setup.exe> <protokoll>
    python packaging/windows/paketprobe.py update <datenordner> <sha256-vorher> <version>
    python packaging/windows/paketprobe.py datenordner <exe> <erwarteter-ordner> <bericht.json>
    python packaging/windows/paketprobe.py deinstallieren <programmordner> <datenordner>
    python packaging/windows/paketprobe.py umzug <exe> <paket.nkfix> <erwartet.json> <datenordner> <bericht.json>
    python packaging/windows/paketprobe.py msix <alias-exe> <paketfamilie> <datenordner> <berichtordner>
    python packaging/windows/paketprobe.py msix-entfernt <paketfamilie> <datenordner>

Jede Probe schreibt eine Zeile in die Zusammenfassung des Laufs
(``GITHUB_STEP_SUMMARY``) und endet mit Exit 1, wenn sie nicht besteht.
Nur Standardbibliothek; läuft auch unter Linux (Tests), soweit keine
Windows-Programme gestartet werden.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

GUI = 2        # IMAGE_SUBSYSTEM_WINDOWS_GUI: kein Konsolenfenster
KONSOLE = 3    # IMAGE_SUBSYSTEM_WINDOWS_CUI


def _zusammenfassung(zeile: str) -> None:
    print(zeile)
    ziel = os.environ.get('GITHUB_STEP_SUMMARY')
    if ziel:
        with open(ziel, 'a', encoding='utf-8') as datei:
            datei.write(zeile + '\n')


def subsystem(exe: Path) -> int:
    """Das Subsystem aus dem PE-Kopf: 2 = Fenster, 3 = Konsole."""
    with open(exe, 'rb') as datei:
        kopf = datei.read(4096)
    if kopf[:2] != b'MZ':
        raise ValueError(f'{exe} ist keine Windows-Programmdatei')
    (pe,) = struct.unpack_from('<I', kopf, 0x3C)
    if kopf[pe:pe + 4] != b'PE\0\0':
        raise ValueError(f'{exe}: PE-Kennung fehlt')
    optional = pe + 24
    return struct.unpack_from('<H', kopf, optional + 68)[0]


def groesse(ordner: Path) -> int:
    return sum(p.stat().st_size for p in ordner.rglob('*') if p.is_file())


def probe_fenster(exe: Path) -> bool:
    art = subsystem(exe)
    ok = art == GUI
    _zusammenfassung(f'- Konsolenfenster: {"keins (GUI-Subsystem)" if ok else f"JA (Subsystem {art})"}')
    return ok


def probe_groesse(ordner: Path) -> bool:
    mb = groesse(ordner) / 1024 / 1024
    _zusammenfassung(f'- Paketgröße (onedir): {mb:.1f} MB')
    return mb > 1


def probe_selbsttest(exe: Path, datenordner: Path, bericht: Path) -> bool:
    beginn = time.monotonic()
    lauf = subprocess.run(  # noqa: S603 -- feste Argumente aus der CI
        [str(exe), '--selbsttest', '--datenordner', str(datenordner),
         '--bericht', str(bericht)], timeout=300,
        # Wie die Verknüpfung: Start im Programmordner, nicht im Checkout mit
        # static/ daneben -- sonst fällt ein relativer Pfad nie auf (0.9.0).
        cwd=exe.parent)
    sekunden = time.monotonic() - beginn
    try:
        ergebnis = json.loads(bericht.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        ergebnis = {}
    ok = lauf.returncode == 0 and ergebnis.get('ergebnis') == 'bestanden'
    _zusammenfassung(
        f'- Selbsttest `{exe.name}`: {"bestanden" if ok else "FEHLGESCHLAGEN"} '
        f'in {sekunden:.1f} s (Kaltstart bis PDF), Bericht: `{json.dumps(ergebnis, ensure_ascii=False)}`')
    return ok


def probe_installieren(setup: Path, protokoll: Path) -> bool:
    lauf = subprocess.run(  # noqa: S603 -- feste Argumente aus der CI
        [str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
         f'/LOG={protokoll}'], timeout=600)
    ok = lauf.returncode == 0
    _zusammenfassung(f'- Stille Installation: {"ok" if ok else f"Exit {lauf.returncode}"}')
    return ok


APP_ID = '{6F1B2C4E-8D3A-4F7B-9E21-4C5D6A7B8C9D}_is1'


def installierte_versionen() -> list[str]:  # pragma: no cover - Windows
    """DisplayVersion jedes Uninstall-Eintrags mit unserer AppId."""
    import winreg
    versionen = []
    for wurzel, pfad in ((winreg.HKEY_LOCAL_MACHINE,
                          r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                         (winreg.HKEY_LOCAL_MACHINE,
                          r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
                         (winreg.HKEY_CURRENT_USER,
                          r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')):
        try:
            with winreg.OpenKey(wurzel, pfad + '\\' + APP_ID) as schluessel:
                versionen.append(winreg.QueryValueEx(schluessel, 'DisplayVersion')[0])
        except OSError:
            continue
    return versionen


def probe_update(datenordner: Path, vorher: str, version: str,
                 versionen=installierte_versionen) -> bool:
    """Nach dem Update: genau eine Installation in der neuen Version, die
    Datenbank der Vorversion bytegleich."""
    gefunden = versionen()
    datenbank = datenordner / 'nebenkosten.db'
    gleich = datenbank.is_file() and sha256_datei(datenbank).lower() == vorher.lower()
    ok = gefunden == [version] and gleich and (datenordner / 'belege').is_dir()
    _zusammenfassung(f'- Update über die Vorversion: Einträge {gefunden}, '
                     f'Daten {"unverändert" if gleich else "VERÄNDERT/FEHLEN"}')
    return ok


def sha256_datei(pfad: Path) -> str:
    import hashlib
    hasher = hashlib.sha256()
    with open(pfad, 'rb') as datei:
        for stueck in iter(lambda: datei.read(1024 * 1024), b''):
            hasher.update(stueck)
    return hasher.hexdigest()


def probe_deinstallieren(programm: Path, datenordner: Path) -> bool:
    deinstaller = programm / 'unins000.exe'
    subprocess.run(  # noqa: S603 -- feste Argumente aus der CI
        [str(deinstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], timeout=600)
    # Der Deinstaller kopiert sich nach %TEMP% und laeuft dort weiter; der
    # erste Prozess endet frueher. Warten, bis das Programm wirklich weg ist.
    frist = time.monotonic() + 120
    while time.monotonic() < frist and deinstaller.exists():
        time.sleep(1)
    weg = not deinstaller.exists() and not list(programm.glob('*.exe'))
    daten = (datenordner / 'nebenkosten.db').is_file()
    _zusammenfassung(f'- Deinstallation: Programm {"entfernt" if weg else "NOCH DA"}, '
                     f'Daten {"erhalten" if daten else "WEG"}')
    return weg and daten


def probe_datenordner(exe: Path, erwartet: Path, bericht: Path) -> bool:
    """Welchen Datenordner nimmt die installierte App? (D-95: nach dem Update
    über eine Installation vor der Umbenennung der alte.)"""
    subprocess.run(  # noqa: S603 -- feste Argumente aus der CI
        [str(exe), '--datenordner-zeigen', '--bericht', str(bericht)], timeout=120)
    try:
        ordner = json.loads(bericht.read_text(encoding='utf-8'))['datenordner']
    except (OSError, ValueError, KeyError):
        ordner = None
    ok = ordner is not None and Path(ordner).resolve() == erwartet.resolve()
    _zusammenfassung(f'- Datenordner nach dem Update: `{ordner}` '
                     f'({"wie erwartet" if ok else f"ERWARTET {erwartet}"})')
    return ok


def probe_umzug(exe: Path, paket: Path, erwartet: Path, datenordner: Path,
                bericht: Path) -> bool:
    """NK-164: ein Paket von einer anderen Plattform in der gebauten App übernehmen
    und mit dem vergleichen, was die Quelle versprochen hat."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    import umzug_kreuzprobe  # noqa: E402 -- Vergleich aus den Quellen

    lauf = subprocess.run(  # noqa: S603 -- feste Argumente aus der CI
        [str(exe), '--umzug-uebernehmen', str(paket), '--datenordner', str(datenordner),
         '--bericht', str(bericht)], timeout=600)
    try:
        angekommen = json.loads(bericht.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        angekommen = {'fehler': 'kein Bericht'}
    if lauf.returncode != 0 or 'fehler' in angekommen:
        fehler = [angekommen.get('fehler', f'Exit {lauf.returncode}')]
    else:
        fehler = umzug_kreuzprobe.vergleichen(
            json.loads(erwartet.read_text(encoding='utf-8')), angekommen)
    quelle = (angekommen.get('quelle') or {}).get('plattform', '?')
    _zusammenfassung(f'- Umzug {quelle} → gebaute App: '
                     f'{"bestanden" if not fehler else "FEHLGESCHLAGEN " + "; ".join(fehler)}')
    return not fehler


# NK-173: Name und Publisher aus dem Partner Center ergeben diese Familie. Ein
# Testzertifikat mit demselben Publisher ergibt dieselbe.
PAKETFAMILIE = 'NerbrY72.NebenkostenFix_r6jjzcw4f5yym'


def _json(datei: Path) -> dict:
    try:
        return json.loads(datei.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _umgeleitet(lokal: Path, familie: str) -> Path:
    """Wohin Windows (ab 10 1903) neue Dateien einer MSIX-App unter
    %LOCALAPPDATA% schreibt."""
    return lokal / 'Packages' / familie / 'LocalCache' / 'Local' / 'NebenkostenFix'


def msix_auswerten(selbst: dict, ordner: dict, familie: str, lokal: Path) -> tuple[bool, list[str]]:
    """Die Berichte der App mit Paketidentität lesen (Spike F-102).

    Muss: Selbsttest bestanden, Paketmodus (Updater aus) in beiden Läufen,
    richtige Paketfamilie, OneDrive-Ausweich außerhalb von %LOCALAPPDATA%
    (F-111). Nur festgehalten: ob Windows die Einstellungen umleitet.
    """
    ausweich = ordner.get('ausweich') or ''
    ausweich_ok = bool(ausweich) and not _normiert_in(Path(ausweich), lokal)
    pruefungen = {
        'Selbsttest': selbst.get('ergebnis') == 'bestanden',
        'Paketmodus (Updater aus)': selbst.get('paketmodus') is True and ordner.get('paketmodus') is True,
        f'Paketfamilie {PAKETFAMILIE}': familie == PAKETFAMILIE,
        'OneDrive-Ausweich außerhalb von %LOCALAPPDATA%': ausweich_ok,
    }
    zeilen = [f'- MSIX {name}: {"ok" if gut else "FEHLGESCHLAGEN"}' for name, gut in pruefungen.items()]
    umgeleitet = _umgeleitet(lokal, familie)
    virtuell = umgeleitet.is_dir() and not (lokal / 'NebenkostenFix').exists()
    zeilen.append(f'- MSIX Datenordner `{ordner.get("datenordner")}`, Ausweich `{ausweich}`')
    zeilen.append('- MSIX %LOCALAPPDATA%\\NebenkostenFix: '
                  + (f'umgeleitet nach `{umgeleitet}` (paketprivat)' if virtuell
                     else 'NICHT umgeleitet'))
    return all(pruefungen.values()), zeilen


def _normiert_in(pfad: Path, basis: Path) -> bool:
    ziel = os.path.normcase(os.path.abspath(str(pfad)))
    wurzel = os.path.normcase(os.path.abspath(str(basis))).rstrip('\\/')
    return ziel == wurzel or ziel.startswith(wurzel + os.sep)


def probe_msix(alias: Path, familie: str, datenordner: Path, berichte: Path) -> bool:
    """NK-173: die installierte MSIX-App, gestartet über ihren Alias, also
    mit Paketidentität."""
    lokal = Path(os.environ['LOCALAPPDATA'])
    selbst, ordner = berichte / 'bericht-msix.json', berichte / 'bericht-msix-ordner.json'
    probe_selbsttest(alias, datenordner, selbst)
    subprocess.run(  # noqa: S603 -- feste Argumente aus der CI
        [str(alias), '--datenordner-zeigen', '--bericht', str(ordner)], timeout=120)
    ok, zeilen = msix_auswerten(_json(selbst), _json(ordner), familie, lokal)
    for zeile in zeilen:
        _zusammenfassung(zeile)
    return ok


def probe_msix_entfernt(familie: str, datenordner: Path) -> bool:
    """Nach Remove-AppxPackage: der Paketordner ist weg, die Daten in einem
    echten Ordner bleiben. Beides muss stimmen: Bleibt der Paketordner, ist
    die Deinstallation gescheitert, und die Daten zeigen nichts."""
    paketordner = Path(os.environ['LOCALAPPDATA']) / 'Packages' / familie
    daten = (datenordner / 'nebenkosten.db').is_file()
    weg = not paketordner.exists()
    _zusammenfassung(f'- MSIX entfernt: Paketordner {"weg" if weg else "NOCH DA"}, '
                     f'Daten {"erhalten" if daten else "WEG"}')
    return weg and daten


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    befehl, *rest = argv
    proben = {
        'fenster': lambda: probe_fenster(Path(rest[0])),
        'groesse': lambda: probe_groesse(Path(rest[0])),
        'selbsttest': lambda: probe_selbsttest(Path(rest[0]), Path(rest[1]), Path(rest[2])),
        'installieren': lambda: probe_installieren(Path(rest[0]), Path(rest[1])),
        'update': lambda: probe_update(Path(rest[0]), rest[1], rest[2]),
        'datenordner': lambda: probe_datenordner(Path(rest[0]), Path(rest[1]), Path(rest[2])),
        'deinstallieren': lambda: probe_deinstallieren(Path(rest[0]), Path(rest[1])),
        'umzug': lambda: probe_umzug(*(Path(r) for r in rest[:5])),
        'msix': lambda: probe_msix(Path(rest[0]), rest[1], Path(rest[2]), Path(rest[3])),
        'msix-entfernt': lambda: probe_msix_entfernt(rest[0], Path(rest[1])),
    }
    if befehl not in proben:
        print(__doc__)
        return 2
    return 0 if proben[befehl]() else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
