"""NK-210 (B3): die Abrechnung nennt den Vermieter beim Namen.

Befund der App-Analyse vom 2026-10-06: Briefkopf und Deckblatt trugen fest
„Hausverwaltung / Vermieter“, das Anschreiben unterschrieb mit dem Namen des
Hauses -- obwohl der Name in den Einstellungen steht (NK-124). Jetzt kommt er
aus ``vermieter_ausweis()``, maskiert; ohne Namen bleibt die Rolle stehen und
der Gruß ohne Unterschrift.

*Haette den Fehler gefunden:* jeder Test mit Namen -- vorher stand der Name
nirgends auf dem Blatt, und der Gruß endete mit „Haus am Anger“.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from nebenkostenfix.anschreiben import VORGABE, text_fuer
from nebenkostenfix.models import Vermieterdaten, db
from tests.test_anschreiben import _finalisiere, _welt
from tests.test_pdf_rechenweg import _erzeuge, _geklebt, unkomprimiert  # noqa: F401

NAME = 'Erika & Söhne <GbR>'


@pytest.fixture
def ohne_vermieter(monkeypatch):
    """Die .env des Behaelters setzt VERMIETER_NAME -- hier zaehlt nur der Test."""
    monkeypatch.delenv('VERMIETER_NAME', raising=False)
    monkeypatch.delenv('VERMIETER_IBAN', raising=False)


def test_ohne_namen_bleibt_die_rolle(ohne_vermieter, unkomprimiert):
    blatt = _geklebt(_erzeuge([]))
    # Deckblatt und Briefkopf
    assert blatt.count('Hausverwaltung/Vermieter') == 2


def test_der_name_steht_im_kopf_und_auf_dem_deckblatt(ohne_vermieter, monkeypatch, unkomprimiert):
    """Maskiert: ``&`` und ``<`` haetten den Satzer sonst abbrechen lassen."""
    monkeypatch.setenv('VERMIETER_NAME', NAME)
    blatt = _geklebt(_erzeuge([]))
    assert blatt.count('Erika&Söhne<GbR>') == 2
    assert 'Hausverwaltung/Vermieter' not in blatt


def test_der_gruss_traegt_den_namen():
    werte = dict(mieter_name='Anna', wohnung_name='EG links', objekt_name='Haus am Anger',
                 zeitraum='01.01.2025 bis 31.12.2025', gesamtsumme=Decimal('1200.00'),
                 vorauszahlungen=Decimal('300.00'), saldo=Decimal('900.00'))
    assert text_fuer(VORGABE, vermieter_name='Erika Musterfrau', **werte).endswith(
        'Mit freundlichen Grüßen\nErika Musterfrau')
    # Ohne Namen kein Haus an der Stelle der Unterschrift
    assert text_fuer(VORGABE, **werte).endswith('Mit freundlichen Grüßen\n')


def test_die_festsetzung_unterschreibt_mit_dem_namen_aus_den_einstellungen(
        auth_client, app_ctx, ohne_vermieter, unkomprimiert):
    Vermieterdaten.query.delete()
    db.session.add(Vermieterdaten(name=NAME, iban=None))
    db.session.commit()
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)

    blatt = _geklebt((Path(os.environ['NAS_MOUNT_PATH']) / report.document_path).read_bytes())
    assert 'MitfreundlichenGrüßenErika&Söhne<GbR>' in blatt
    assert 'MitfreundlichenGrüßenHaus' not in blatt
