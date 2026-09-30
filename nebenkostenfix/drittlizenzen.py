"""Lizenzen der mitgelieferten Drittsoftware (NK-148).

Docker-Abbild und Windows-App bringen Python, die Pakete aus requirements.txt
(unter Windows dazu requirements-desktop.txt) samt deren Abhängigkeiten und
die Bibliotheken in static/vendor/ mit. Die meisten dieser Lizenzen verlangen,
dass ihr Wortlaut der Weitergabe beiliegt. Der Bau schreibt ihn deshalb nach
``pip install`` aus genau dieser Installation::

    python -m nebenkostenfix.drittlizenzen --ausgabe THIRD_PARTY_LICENSES.txt \\
        requirements.txt [requirements-desktop.txt]

Die Datei liegt dann im Abbild, im Programmordner der Windows-App und am
Release. Fehlt dem Bau ein Lizenztext (von Python oder einem Paket), bricht
er ab, statt nur auf eine Webseite zu verweisen. Der Über-Dialog zeigt die
Datei (``/api/drittlizenzen``); ohne gebaute Datei, also in der Entwicklung,
entsteht der Text aus der laufenden Umgebung, dort mit Verweis statt Abbruch.
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import platform
import re
import sys
import sysconfig
from pathlib import Path

from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION

DATEINAME = 'THIRD_PARTY_LICENSES.txt'
# Im Quellbaum die Wurzel neben app.py, in der Windows-App der Ordner, in den
# PyInstaller die Daten legt (die Spec nimmt die Datei nach '.').
WURZEL = Path(__file__).resolve().parents[1]

# Lizenzdateien im .dist-info-Ordner: LICENSE, LICENCE.rst, COPYING, NOTICE,
# und alles unter licenses/ (PEP 639).
LIZENZDATEI = re.compile(r'^(LICEN[CS]E|COPYING|NOTICE)', re.IGNORECASE)
# Lizenzen der Bibliotheken in static/vendor/, gleiches Muster plus die
# Schriftlizenz (SIL OFL).
VENDOR_LIZENZ = re.compile(r'^(LICEN[CS]E|COPYING|OFL)', re.IGNORECASE)
VENDOR_NAMEN = {'chartjs': 'Chart.js', 'phosphor': 'Phosphor Icons', 'outfit': 'Schrift Outfit'}
PYTHON_LIZENZ_URL = 'https://docs.python.org/3/license.html'
# Pakete, deren Projekt einen Lizenztext hat, die ihn aber nicht mitliefern.
# Der Wortlaut liegt hier unverändert, Dateiname ist der PEP-503-Name:
#   proxy-tools.txt  proxy_tools 0.1.0 (von pywebview, nur Windows),
#                    github.com/jtushman/proxy_tools, LICENSE.txt @ ccd35a5
ERSATZ = Path(__file__).resolve().parent / 'lizenzen'


def _schluessel(name: str) -> str:
    """Paketnamen nach PEP 503 vergleichbar machen.

    >>> _schluessel('Flask_SQLAlchemy')
    'flask-sqlalchemy'
    """
    return re.sub(r'[-_.]+', '-', name).lower()


def _anforderungen(dateien) -> list:
    from packaging.requirements import Requirement

    liste = []
    for datei in dateien:
        for zeile in Path(datei).read_text(encoding='utf-8').splitlines():
            zeile = zeile.split('#', 1)[0].strip()
            if zeile and not zeile.startswith('-'):
                liste.append(Requirement(zeile))
    return liste


def pakete(dateien) -> list[md.Distribution]:
    """Alle installierten Pakete, die die Anforderungsdateien hereinziehen.

    Folgt den Abhängigkeiten aus den Metadaten; eine Bedingung (Plattform,
    Python-Version, Extra) wertet ``packaging`` für diese Umgebung aus. Was
    verlangt, aber nicht installiert ist, bricht ab: sonst fehlte es still.
    """
    from packaging.requirements import Requirement

    offen = [(anf, '') for anf in _anforderungen(dateien)]
    gefunden: dict[str, md.Distribution] = {}
    while offen:
        anf, extra = offen.pop()
        if anf.marker and not anf.marker.evaluate({'extra': extra}):
            continue
        schluessel = _schluessel(anf.name)
        if schluessel in gefunden:
            continue
        try:
            dist = md.distribution(anf.name)
        except md.PackageNotFoundError:
            raise LookupError(f'{anf.name} ist verlangt, aber nicht installiert.') from None
        gefunden[schluessel] = dist
        for abh in dist.requires or []:
            for e in ('', *anf.extras):
                offen.append((Requirement(abh), e))
    return [gefunden[k] for k in sorted(gefunden)]


def lizenzname(dist: md.Distribution) -> str:
    """SPDX-Ausdruck, sonst das Lizenzfeld, sonst der Klassifikator."""
    meta = dist.metadata
    if meta.get('License-Expression'):
        return meta['License-Expression']
    feld = (meta.get('License') or '').strip()
    if feld and '\n' not in feld and len(feld) <= 80:
        return feld
    for klasse in meta.get_all('Classifier') or []:
        if klasse.startswith('License ::'):
            return klasse.split('::')[-1].strip()
    return 'siehe Lizenztext'


def projektseite(dist: md.Distribution) -> str:
    meta = dist.metadata
    adressen = dict(
        (teil.strip() for teil in eintrag.split(',', 1))
        for eintrag in meta.get_all('Project-URL') or [] if ',' in eintrag)
    for name in ('Homepage', 'homepage', 'Source', 'Source Code', 'Repository', 'Code'):
        if adressen.get(name):
            return adressen[name]
    return meta.get('Home-page') or ''


def lizenztexte(dist: md.Distribution) -> list[tuple[str, str]]:
    """(Dateiname, Wortlaut) aus dem .dist-info-Ordner des Pakets.

    Bringt das Paket keinen mit, gilt der Wortlaut aus ``ERSATZ``, falls dort
    einer für das Paket liegt.
    """
    texte = []
    for datei in dist.files or []:
        if not datei.parts[0].endswith('.dist-info'):
            continue
        if LIZENZDATEI.match(datei.name) or 'licenses' in datei.parts[1:-1]:
            try:
                texte.append(('/'.join(datei.parts[1:]), datei.read_text(encoding='utf-8')))
            except (OSError, UnicodeDecodeError):
                continue
    ersatz = ERSATZ / f'{_schluessel(dist.metadata["Name"])}.txt'
    if not texte and ersatz.is_file():
        texte.append(('Lizenztext aus dem Quell-Repository, fehlt im Paket',
                      ersatz.read_text(encoding='utf-8')))
    return sorted(texte)


def _python_lizenz() -> str | None:
    kandidaten = (Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt',
                  Path(sys.base_prefix) / 'LICENSE.txt')
    for pfad in kandidaten:
        if pfad.is_file():
            return pfad.read_text(encoding='utf-8', errors='replace')
    return None


def _vendor(wurzel: Path) -> list[tuple[str, str, str]]:
    """(Name, Pfad, Wortlaut) der Lizenzen unter static/vendor/."""
    ordner = wurzel / 'static' / 'vendor'
    funde = []
    for pfad in sorted(ordner.rglob('*')):
        if pfad.is_file() and VENDOR_LIZENZ.match(pfad.name):
            name = VENDOR_NAMEN.get(pfad.parent.name, pfad.parent.name)
            funde.append((name, pfad.relative_to(wurzel).as_posix(),
                          pfad.read_text(encoding='utf-8')))
    return funde


def _kopf(titel: str, zeichen: str = '=') -> list[str]:
    return ['', titel, zeichen * len(titel), '']


def erzeugen(dateien, wurzel: Path = WURZEL, streng: bool = False) -> str:
    """Der ganze Text: Übersicht, dann jede Lizenz im Wortlaut.

    ``streng`` (der Bau): Fehlt ein Wortlaut, bricht es mit allen Lücken ab.
    """
    python = f'Python {platform.python_version()}'
    liste = pakete(dateien)
    vendor = _vendor(wurzel)
    python_lizenz = _python_lizenz()
    if streng:
        luecken = [] if python_lizenz else [python]
        luecken += [f'{d.metadata["Name"]} {d.version}' for d in liste if not lizenztexte(d)]
        if luecken:
            raise LookupError(f'Lizenztext fehlt: {", ".join(luecken)}.')

    zeilen = [f'Drittsoftware in NebenkostenFix {SOFTWARE_VERSION}', '=' * 40, '',
              'NebenkostenFix selbst steht unter der GPL-3.0 (Datei LICENSE im',
              'Quelltext). Es bringt Software anderer Urheber mit. Deren Lizenzen',
              'stehen unten im Wortlaut.']
    zeilen += _kopf('Übersicht', '-')
    zeilen.append(f'{python:<34} PSF-2.0  {PYTHON_LIZENZ_URL}')
    for dist in liste:
        eintrag = f'{dist.metadata["Name"]} {dist.version}'
        zeilen.append(f'{eintrag:<34} {lizenzname(dist)}  {projektseite(dist)}'.rstrip())
    for name, pfad, _ in vendor:
        zeilen.append(f'{name:<34} {pfad}')

    zeilen += _kopf(python)
    zeilen.append(python_lizenz or f'Der Lizenztext von Python steht unter {PYTHON_LIZENZ_URL}.')
    for dist in liste:
        texte = lizenztexte(dist)
        kopf = f'{dist.metadata["Name"]} {dist.version} ({lizenzname(dist)})'
        if not texte:
            zeilen += _kopf(kopf)
            zeilen.append(f'Das Paket bringt keinen Lizenztext mit. Siehe {projektseite(dist)}.')
        for datei, text in texte:
            zeilen += _kopf(f'{kopf}: {datei}')
            zeilen.append(text.rstrip())
    for name, pfad, text in vendor:
        zeilen += _kopf(f'{name}: {pfad}')
        zeilen.append(text.rstrip())
    return '\n'.join(zeilen) + '\n'


def lesen(wurzel: Path = WURZEL) -> str:
    """Die gebaute Datei, sonst der Text aus der laufenden Umgebung."""
    datei = wurzel / DATEINAME
    if datei.is_file():
        return datei.read_text(encoding='utf-8')
    return erzeugen([wurzel / 'requirements.txt'], wurzel)


def main(argumente=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('anforderungen', nargs='+', type=Path)
    parser.add_argument('--ausgabe', type=Path, default=WURZEL / DATEINAME)
    optionen = parser.parse_args(argumente)
    try:
        text = erzeugen(optionen.anforderungen, streng=True)
    except LookupError as fehler:
        sys.stderr.write(f'{fehler}\n')
        return 1
    optionen.ausgabe.write_text(text, encoding='utf-8', newline='\n')
    sys.stdout.write(f'{optionen.ausgabe}: {len(text.splitlines())} Zeilen\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
