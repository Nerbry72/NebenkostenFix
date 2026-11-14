"""Das Release bringt das DMG mit (Review zu #59).

``release.yml`` ruft ``macos.yml`` wie ``windows.yml`` mit ``nur_paket`` auf,
holt das DMG über seinen Dateinamen und nimmt es in ``SHA256SUMS.txt`` und
unter die Dateien des Release auf. Scheitert der Mac-Bau, erscheint nichts.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WURZEL = Path(__file__).resolve().parents[1]
RELEASE = WURZEL / '.github' / 'workflows' / 'release.yml'
MACOS = WURZEL / '.github' / 'workflows' / 'macos.yml'
DMG = 'NebenkostenFix-${{ needs.version.outputs.wert }}-macOS-arm64.dmg'


def _jobs(pfad: Path = RELEASE) -> dict:
    return yaml.safe_load(pfad.read_text(encoding='utf-8'))['jobs']


def _schritt(name: str) -> str:
    return next(s['run'] for s in _jobs()['release']['steps'] if s.get('name') == name)


def test_das_release_ruft_den_mac_bau_auf():
    assert _jobs()['macos'] == {
        'needs': 'version',
        'uses': './.github/workflows/macos.yml',
        'with': {'nur_paket': True},
    }


def test_ohne_mac_bau_kein_abbild_und_kein_release():
    """Wie bei Windows. Sonst stünde das Abbild schon in GHCR, und das Release
    fehlte, oder es erschiene ohne DMG, und die Anleitung führte ins Leere."""
    jobs = _jobs()
    assert {'windows', 'macos'} <= set(jobs['docker']['needs'])
    assert 'docker' in jobs['release']['needs']


def test_das_dmg_kommt_ueber_seinen_dateinamen():
    """``macos.yml`` lädt das DMG ohne ZIP hoch, der Name des Artefakts ist
    der Dateiname. ``download-artifact@v8`` holt es genau darüber."""
    hochladen = [s for s in _jobs(MACOS)['paket']['steps']
                 if s.get('uses', '').startswith('actions/upload-artifact@')
                 and s['with'].get('archive') is False]
    assert [Path(s['with']['path']).name for s in hochladen] == [
        DMG.replace('needs.version.outputs', 'steps.version.outputs')]
    holen = [s['with'] for s in _jobs()['release']['steps']
             if s.get('uses') == 'actions/download-artifact@v8']
    assert {'name': DMG, 'path': 'macos'} in holen


def test_pruefsummen_und_dateien_mit_dem_dmg():
    dateien = _schritt('Installer, DMG und Pruefsummen')
    assert 'dmg="NebenkostenFix-${VERSION}-macOS-arm64.dmg"' in dateien
    assert 'sha256sum "$exe" "$dmg" > SHA256SUMS.txt' in dateien
    anlegen = _schritt('Release anlegen')
    assert 'dateien=("$exe" "$dmg" SHA256SUMS.txt THIRD_PARTY_LICENSES.txt)' in anlegen


def test_der_release_text_nennt_das_dmg_und_die_anleitung():
    text = _schritt('Release anlegen')
    assert '**macOS:** \\`${dmg}\\`' in text
    assert 'Apple-Chip' in text and 'macOS 15' in text
    assert '/blob/v${VERSION}/docs/handbuch/mac-installation.md' in text
    # Beide Prüfsummen, nicht nur die erste Zeile der Datei.
    assert "cut -d' ' -f1 SHA256SUMS.txt" not in text
    assert '$(cat SHA256SUMS.txt)' in text
