"""Store-Eintrag (NK-172): Längengrenzen des Partner Centers und der
Haftungshinweis im Wortlaut der App."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nebenkostenfix import haftung

EINTRAG = Path(__file__).resolve().parents[1] / 'packaging/windows/store/eintrag-de.md'

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
