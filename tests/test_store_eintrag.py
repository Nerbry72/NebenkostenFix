"""Store-Eintrag (NK-172): Längengrenzen des Partner Centers und der
Haftungshinweis im Wortlaut der App."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from nebenkostenfix import haftung
from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import store_neuerungen  # noqa: E402

EINTRAG = Path(__file__).resolve().parents[1] / 'packaging/windows/store/eintrag-de.md'
ZERTIFIZIERUNG = EINTRAG.with_name('zertifizierung-en.md')

# Grenzen laut Partner Center (Store listings), in Zeichen
GRENZEN = {
    'Beschreibung': 10000,
    'Kurzbeschreibung': 1000,
    'Neuerungen in dieser Version': 1500,
    'Copyright': 200,
    'Zusätzliche Lizenzbedingungen': 10000,
}


def _felder() -> dict[str, str]:
    teile = re.split(r'^## (.+)$', EINTRAG.read_text(encoding='utf-8'), flags=re.M)
    return {name.strip(): inhalt.strip() for name, inhalt in zip(teile[1::2], teile[2::2])}


def _liste(text: str) -> list[str]:
    return [zeile[2:].strip() for zeile in text.splitlines() if zeile.startswith('- ')]


@pytest.mark.parametrize('feld, grenze', GRENZEN.items())
def test_textfelder_passen(feld, grenze):
    text = _felder()[feld]
    assert 0 < len(text) <= grenze


def test_produktmerkmale():
    merkmale = _liste(_felder()['Produktmerkmale'])
    assert 1 <= len(merkmale) <= 20
    assert all(len(m) <= 200 for m in merkmale)


def test_suchbegriffe():
    begriffe = _liste(_felder()['Suchbegriffe'])
    assert 1 <= len(begriffe) <= 7
    assert all(len(b) <= 30 for b in begriffe)
    assert sum(len(b.split()) for b in begriffe) <= 21


def test_haftungshinweis_im_wortlaut_der_app():
    assert ' '.join(haftung.TEXT) in _felder()['Beschreibung']


def test_gesiezt():
    text = ' '.join(_felder().values())
    assert not re.search(r'\b(du|dein|deine|dir|dich)\b', text, flags=re.I)


def test_pruefer_hinweise_widersprechen_sich_nicht():
    """Copilot zu #23: „there is no server“ neben dem lokalen Webserver auf
    127.0.0.1. Gemeint ist: kein entfernter Server, keiner des Herausgebers."""
    notiz = ZERTIFIZIERUNG.read_text(encoding='utf-8').split('\n---\n', 1)[1]
    assert '127.0.0.1' in notiz
    assert not re.search(r'\bno server\b', notiz, flags=re.I)


def test_neuerungen_gehoeren_zur_aktuellen_version():
    """Der Release setzt diesen Abschnitt im Store als Neuerungen (Job store,
    scripts/store_neuerungen.py). Ohne neuen Text stuenden dort die alten."""
    text = store_neuerungen.neuerungen(EINTRAG.read_text(encoding='utf-8'))
    assert text == _felder()['Neuerungen in dieser Version']
    assert SOFTWARE_VERSION in text
    assert 'Erste Fassung' not in text


def _einreichung():
    return {
        'Pricing': {'PriceId': 'Free'},
        'Listings': {
            'de-de': {'BaseListing': {'Description': 'Beschreibung', 'ReleaseNotes': 'alt'}},
            'en-us': {'BaseListing': {'Description': 'Description', 'ReleaseNotes': 'old'}},
        },
    }


def test_neuerungen_nur_im_deutschen_eintrag():
    einreichung = _einreichung()
    store_neuerungen.setzen(einreichung, 'neu')
    erwartet = _einreichung()
    erwartet['Listings']['de-de']['BaseListing']['ReleaseNotes'] = 'neu'
    assert einreichung == erwartet


def test_ohne_deutschen_eintrag_bricht_der_release_ab():
    einreichung = _einreichung()
    del einreichung['Listings']['de-de']
    with pytest.raises(SystemExit):
        store_neuerungen.setzen(einreichung, 'neu')
