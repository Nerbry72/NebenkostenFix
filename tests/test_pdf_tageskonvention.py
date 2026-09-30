"""Das Dokument benennt die Tageskonvention im Klartext (R-NUM-03, NK-041).

Die Regel verlangt nicht nur, dass richtig gezaehlt wird, sondern dass der
Mieter die Tageszahl **nachrechnen** kann: "181 von 366 Tagen" laesst offen,
ob der Auszugstag mitzaehlt. Wer das nicht weiss, kann die Abrechnung nur
glauben.

Fuer das Auslesen des erzeugten PDF gibt es hier keine Bibliothek (kein
pypdf, kein pdfminer), und fuer eine Fussnote lohnt keine neue Abhaengigkeit.
Stattdessen werden die Seiten unkomprimiert erzeugt und die Textstroeme
direkt gelesen -- reportlab legt den Text dann als Klartext ab.
"""

from __future__ import annotations

import zlib
from decimal import Decimal

import pytest
import reportlab.rl_config

from nebenkostenfix.pdf_generator import PDFGenerator
from nebenkostenfix.zeitraum import HINWEIS_TAGESKONVENTION


@pytest.fixture
def unkomprimiert(monkeypatch):
    """Seiten ohne Kompression, damit der Text lesbar im Strom steht."""
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)


def _text(pdf: bytes) -> str:
    stuecke = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            pass
        stuecke.append(roh.decode('latin-1', 'replace'))
    return ' '.join(stuecke)


def _posten(*, anteilig: bool) -> dict:
    """Ein Kostenposten -- anteilig heisst: weniger Tage als die Rechnung."""
    return {
        'category': 'Hausmeister',
        'period': '01.01.2024 - 31.12.2024',
        'description': 'Umlage nach Wohnflaeche',
        'tenant_cost': Decimal('600.00'),
        'invoice_days': 366,
        'overlap_days': 181 if anteilig else 366,
        # Die ausfuehrliche Variante weist die Rechnung zusaetzlich einzeln aus.
        'provider_name': 'Hausmeisterdienst Meier',
        'invoice_total_amount': Decimal('1200.00'),
        'prorated_amount': Decimal('600.00'),
    }


def _erzeuge(detailliert: bool, *, anteilig: bool) -> str:
    erzeuger = PDFGenerator(
        property_name='Haus am Anger',
        apartment_name='Wohnung 1',
        tenant_name='Mustermann',
        start_date='2024-01-01',
        end_date='2024-12-31',
        detailliert=detailliert,
    )
    pdf = erzeuger.generate([_posten(anteilig=anteilig)], Decimal('600.00'), Decimal('0.00'))
    return _text(pdf)


@pytest.mark.parametrize('detailliert', [False, True], ids=['einfach', 'detailliert'])
def test_anteilige_abrechnung_erklaert_die_zaehlweise(unkomprimiert, detailliert):
    text = _erzeuge(detailliert, anteilig=True)
    assert 'Tagesangaben' in text, (
        f'{"Detaillierte" if detailliert else "Einfache"} Variante weist "181 von 366 Tagen" aus, '
        'ohne zu sagen, wie gezaehlt wird (R-NUM-03)'
    )
    assert 'Auszugstag' in text
    assert 'Einzugstag' in text


@pytest.mark.parametrize('detailliert', [False, True], ids=['einfach', 'detailliert'])
def test_ohne_anteilige_position_keine_ueberfluessige_fussnote(unkomprimiert, detailliert):
    """Wer die ganze Rechnung traegt, braucht die Erlaeuterung nicht."""
    text = _erzeuge(detailliert, anteilig=False)
    assert 'Tagesangaben' not in text


def test_der_hinweis_nennt_beide_raender():
    """Der Satz muss die Frage beantworten, die die Tageszahl offen laesst."""
    assert 'Einzugstag' in HINWEIS_TAGESKONVENTION
    assert 'Auszugstag' in HINWEIS_TAGESKONVENTION
    assert 'zweimal' in HINWEIS_TAGESKONVENTION


def test_die_eine_klasse_traegt_den_gemeinsamen_satz():
    """Zwei Formulierungen fuer dieselbe Regel waeren eine Ungereimtheit."""
    from nebenkostenfix import pdf_generator

    assert pdf_generator.HINWEIS_TAGESKONVENTION is HINWEIS_TAGESKONVENTION
