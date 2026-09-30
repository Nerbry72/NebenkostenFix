"""Lizenzen der mitgelieferten Drittsoftware (NK-148).

Jedes Paket, das Abbild und Windows-App mitbringen, steht mit seinem
Lizenztext in THIRD_PARTY_LICENSES.txt; der Bau erzeugt die Datei, der
Über-Dialog zeigt sie.
"""

from __future__ import annotations

import importlib.metadata as md
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from nebenkostenfix import drittlizenzen

WURZEL = Path(__file__).resolve().parents[1]
ANFORDERUNGEN = WURZEL / 'requirements.txt'


@pytest.fixture(scope='module')
def text():
    return drittlizenzen.erzeugen([ANFORDERUNGEN])


def _direkte_pakete():
    for zeile in ANFORDERUNGEN.read_text(encoding='utf-8').splitlines():
        zeile = zeile.split('#', 1)[0].strip()
        if zeile:
            anf = Requirement(zeile)
            if not anf.marker or anf.marker.evaluate():
                yield md.distribution(anf.name)


def test_jede_laufzeitabhaengigkeit_steht_mit_lizenztext(text):
    for dist in _direkte_pakete():
        name = f'{dist.metadata["Name"]} {dist.version}'
        assert f'\n{name} ' in text, f'{name} fehlt in der Übersicht'
        assert drittlizenzen.lizenztexte(dist), f'{name} bringt keinen Lizenztext mit'
        assert f'\n{name} ({drittlizenzen.lizenzname(dist)}): ' in text, f'{name}: Wortlaut fehlt'


def test_auch_die_abhaengigkeiten_der_abhaengigkeiten(text):
    # Flask zieht Jinja2 und MarkupSafe, cryptography zieht cffi: nichts davon
    # steht in requirements.txt, mitgeliefert wird es trotzdem.
    for name in ('Jinja2', 'MarkupSafe', 'itsdangerous', 'cffi'):
        dist = md.distribution(name)
        assert f'\n{dist.metadata["Name"]} {dist.version} ' in text, name


def test_python_und_die_bibliotheken_der_oberflaeche(text):
    assert '\nPython ' in text
    for name in ('Chart.js', 'Phosphor Icons', 'Schrift Outfit'):
        assert f'\n{name}: static/vendor/' in text, name
    assert 'SIL OPEN FONT LICENSE' in text.upper()


def test_verlangt_aber_nicht_installiert_bricht_ab(tmp_path):
    datei = tmp_path / 'requirements.txt'
    datei.write_text('gibt-es-nicht-nk148==1.0\n', encoding='utf-8')
    with pytest.raises(LookupError, match='gibt-es-nicht-nk148'):
        drittlizenzen.pakete([datei])


def test_bedingung_einer_fremden_plattform_zaehlt_nicht(tmp_path):
    datei = tmp_path / 'requirements.txt'
    datei.write_text('# Kommentar\ngibt-es-nicht-nk148==1.0; sys_platform == "nirgendwo"\n'
                     'segno==1.6.6  # mit Kommentar\n', encoding='utf-8')
    assert [d.metadata['Name'] for d in drittlizenzen.pakete([datei])] == ['segno']


def test_lesen_nimmt_die_gebaute_datei(tmp_path):
    (tmp_path / drittlizenzen.DATEINAME).write_text('gebaut\n', encoding='utf-8')
    assert drittlizenzen.lesen(tmp_path) == 'gebaut\n'


def test_lesen_ohne_gebaute_datei_erzeugt_den_text(tmp_path):
    (tmp_path / 'requirements.txt').write_text('segno==1.6.6\n', encoding='utf-8')
    text = drittlizenzen.lesen(tmp_path)
    assert f'\nsegno {md.version("segno")} ' in text


def test_aufruf_schreibt_die_datei(tmp_path, capsys):
    ausgabe = tmp_path / 'THIRD_PARTY_LICENSES.txt'
    assert drittlizenzen.main([str(ANFORDERUNGEN), '--ausgabe', str(ausgabe)]) == 0
    assert '\nFlask ' in ausgabe.read_text(encoding='utf-8')
    assert 'Zeilen' in capsys.readouterr().out


def test_api_zeigt_die_lizenzen(auth_client):
    antwort = auth_client.get('/api/drittlizenzen')
    assert antwort.status_code == 200
    assert antwort.mimetype == 'text/plain'
    assert '\nFlask ' in antwort.get_data(as_text=True)


def test_ueber_dialog_laedt_die_lizenzen_beim_aufklappen():
    html = (WURZEL / 'static/index.html').read_text(encoding='utf-8')
    js = (WURZEL / 'static/app.js').read_text(encoding='utf-8')
    assert '<details id="ueber-drittlizenzen">' in html
    assert 'id="ueber-drittlizenzen-text"' in html
    assert "fetch('/api/drittlizenzen')" in js
    assert "getElementById('ueber-drittlizenzen').ontoggle = ladeDrittlizenzen" in js


def test_jeder_bau_legt_die_lizenzen_bei():
    befehl = 'python -m nebenkostenfix.drittlizenzen --ausgabe THIRD_PARTY_LICENSES.txt requirements.txt'
    docker = (WURZEL / 'Dockerfile').read_text(encoding='utf-8')
    # Nach COPY . ., sonst fehlen Modul und static/vendor.
    assert docker.index('COPY . .') < docker.index(f'RUN {befehl}\n')

    windows = (WURZEL / '.github/workflows/windows.yml').read_text(encoding='utf-8')
    assert windows.index(f'{befehl} requirements-desktop.txt') < windows.index('pyinstaller packaging')
    assert 'THIRD_PARTY_LICENSES.txt fehlt im Paket' in windows

    spec = (WURZEL / 'packaging/windows/nebenkosten.spec').read_text(encoding='utf-8')
    assert "daten.append((str(WURZEL / 'THIRD_PARTY_LICENSES.txt'), '.'))" in spec
    iss = (WURZEL / 'packaging/windows/installer.iss').read_text(encoding='utf-8')
    assert 'Source: "{#Quelle}\\_internal\\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"' in iss

    # Erzeugt, nie von Hand gepflegt.
    assert 'THIRD_PARTY_LICENSES.txt' in (WURZEL / '.gitignore').read_text(encoding='utf-8').splitlines()


def test_das_release_traegt_die_lizenzen():
    release = (WURZEL / '.github/workflows/release.yml').read_text(encoding='utf-8')
    assert 'find windows -name THIRD_PARTY_LICENSES.txt' in release
    assert 'dateien=("$exe" SHA256SUMS.txt THIRD_PARTY_LICENSES.txt)' in release
