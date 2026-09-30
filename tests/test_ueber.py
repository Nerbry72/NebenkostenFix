"""„Über NebenkostenFix“ im Hilfe-Tab (NK-179).

Alle Adressen kommen aus ``marke``; „Fehler melden“ füllt nur Version,
Auslieferungsweg und Betriebssystem vor -- nichts aus der Datenbank.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from nebenkostenfix import aktualisierung
import desktop
from nebenkostenfix import haftung
from nebenkostenfix import marke
from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION


def test_fehler_melden_fuellt_nur_stand_weg_und_system():
    adresse = marke.fehler_melden_url('1.2.3', 'Docker', 'Linux 6.1')
    teile = urlsplit(adresse)
    assert adresse.startswith(marke.REPO_URL + '/issues/new?')
    assert parse_qs(teile.query) == {'template': ['fehler.yml'], 'version': ['1.2.3'],
                                     'weg': ['Docker'], 'system': ['Linux 6.1']}


def test_api_ueber_zeigt_auf_die_konstanten(auth_client, monkeypatch):
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: False)
    ueber = auth_client.get('/api/ueber').get_json()
    assert ueber['version'] == SOFTWARE_VERSION
    assert ueber['weg'] == 'Docker'
    assert ueber['projektseite'] == marke.REPO_URL
    assert ueber['neuigkeiten'] == marke.NEUIGKEITEN_URL
    assert ueber['unterstuetzen'] == marke.KOFI_URL
    assert ueber['lizenz'] == marke.LIZENZ_URL
    assert ueber['haftung'] == list(haftung.TEXT)
    felder = parse_qs(urlsplit(ueber['fehler_melden']).query)
    assert set(felder) == {'template', 'version', 'weg', 'system'}
    assert felder['version'] == [SOFTWARE_VERSION] and felder['weg'] == ['Docker']
    # Jede Adresse darf die App im Standardbrowser öffnen (Brücke NK-152).
    for schluessel in ('projektseite', 'neuigkeiten', 'fehler_melden', 'unterstuetzen', 'lizenz'):
        assert desktop.extern_erlaubt(ueber[schluessel]), schluessel


def test_api_ueber_kennt_den_store(auth_client, monkeypatch):
    monkeypatch.setattr(aktualisierung, 'paketmodus', lambda: True)
    assert auth_client.get('/api/ueber').get_json()['weg'] == 'Microsoft Store'


def test_hilfe_laesst_den_haftungshinweis_offen():
    """„Über …“ im Menü ruft zeigeHilfe; der feste Dialog bleibt (NK-174)."""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / 'static/app.js').read_text(encoding='utf-8')
    rumpf = re.search(r'function zeigeHilfe\(abschnitt\) \{(.*?)\n\}', js, re.S).group(1)
    assert ".modal-overlay.active:not([data-fest])" in rumpf
    assert ".modal-overlay.active')" not in rumpf
