"""Jede Version braucht Release-Notizen, die sagen, was neu ist.

0.16.0 ging ohne sie hinaus. Der Release-Text bestand danach aus der
Installationsanleitung, der Pruefsumme und einer einzigen Zeile -- dem Titel
des Pull Requests, einsortiert unter "Intern", weil der PR keine Labels trug.
Wer wissen wollte, was die Version kann, fand es dort nicht.

Die Gliederung fuer ``--generate-notes`` war dabei die ganze Zeit korrekt
eingerichtet. Das ist die Lehre: ein Mechanismus, der von Labels abhaengt,
die niemand vergeben muss, schweigt lieber, als sich zu beschweren. Der
Release-Text kommt deshalb jetzt aus einer Datei im Repo, und diese Datei ist
Pflicht.

Der Test gehoert zum Pull Request und nicht zum Release: ``make check`` laeuft
an jedem PR, der Release-Workflow erst nach dem Merge. Wer es dort erst merkt,
hat die Nummer schon vergeben.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION

WURZEL = Path(__file__).resolve().parent.parent
ORDNER = WURZEL / 'docs' / 'release-notizen'

#: Mindestens eine davon muss vorkommen -- sonst steht in der Datei etwas,
#: aber nicht das, wofuer sie da ist.
UEBERSCHRIFTEN = ('## Neu', '## Behoben')


def notizen_datei(version: str = SOFTWARE_VERSION) -> Path:
    """Die Datei, die der Release-Workflow fuer diese Version anhaengt."""
    return ORDNER / f'{version}.md'


def test_die_laufende_version_hat_release_notizen():
    """Ohne diese Datei bricht der Release ab -- hier faellt es frueher auf."""
    datei = notizen_datei()

    assert datei.is_file(), (
        f'{datei.relative_to(WURZEL)} fehlt. Der Release-Text von '
        f'{SOFTWARE_VERSION} haengt daran; ohne sie steht dort nur die '
        'Installationsanleitung. Vorlage: docs/release-notizen/LIESMICH.md')


def test_die_notizen_sagen_was_neu_oder_behoben_ist():
    """Eine Datei, die nur existiert, erfuellt den Zweck nicht."""
    text = notizen_datei().read_text(encoding='utf-8')

    assert text.strip(), 'Die Release-Notizen sind leer.'
    assert any(kopf in text for kopf in UEBERSCHRIFTEN), (
        'Die Release-Notizen nennen weder „## Neu" noch „## Behoben". '
        'Auch eine Version ohne Nutzerwirkung bekommt einen Satz, der '
        'genau das sagt.')


def test_die_notizen_bringen_den_installationsteil_nicht_doppelt():
    """Windows, Docker und Pruefsumme setzt der Workflow selbst davor."""
    text = notizen_datei().read_text(encoding='utf-8')

    for doppelt in ('**Windows:**', 'docker pull', 'Prüfsumme (SHA256)'):
        assert doppelt not in text, (
            f'„{doppelt}" steht schon im Installationsteil, den der '
            'Release-Workflow erzeugt (.github/workflows/release.yml).')


def test_jede_veroeffentlichte_datei_traegt_eine_echte_nummer():
    """Im Ordner liegen Versionsdateien und die Anleitung, sonst nichts."""
    fremde = [p.name for p in ORDNER.glob('*.md')
              if p.name != 'LIESMICH.md'
              and not all(teil.isdigit() for teil in p.stem.split('.'))]

    assert not fremde, (
        f'Diese Dateien heissen nicht x.y.z.md: {fremde}. Der Workflow '
        'findet seine Notizen ueber die Versionsnummer.')


def _ohne_kommentare(text: str) -> str:
    """Nur die Zeilen, die der Runner ausfuehrt.

    Der Workflow erklaert in einem Kommentar, warum die eingebaute
    Notizen-Erzeugung nicht mehr benutzt wird, und nennt sie dabei beim
    Namen. Ein Test, der blind nach dem Wort sucht, wuerde genau diese
    Begruendung verbieten.
    """
    return '\n'.join(zeile for zeile in text.splitlines()
                     if not zeile.lstrip().startswith('#'))


@pytest.mark.parametrize('schalter', ['--generate-notes'])
def test_der_workflow_erzeugt_die_notizen_nicht_mehr_selbst(schalter):
    """Der Rueckfall auf die eingebaute Erzeugung waere still und englisch."""
    workflow = (WURZEL / '.github' / 'workflows' / 'release.yml').read_text(
        encoding='utf-8')

    assert schalter not in _ohne_kommentare(workflow), (
        f'{schalter} ist zurueck. Das erzeugt eine Zeile je Pull Request, '
        'haengt an dessen Labels und schreibt „What\'s Changed" auf Englisch.')
    assert 'docs/release-notizen/${VERSION}.md' in workflow, (
        'Der Release-Workflow haengt die Release-Notizen nicht mehr an.')
