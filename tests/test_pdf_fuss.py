"""Der Fuß jedes Blatts: Software- und Regelstand (R-DOC-02, NK-062).

Wer das Blatt später prüft -- der Mieter, ein Gericht, der Vermieter
selbst -- soll ohne Rückfrage sehen, mit welchem Stand der Software und
welchem Rechenstand der Regeln es entstanden ist. Dieselben Stände
speichert NK-061 mit der Version der finalisierten Abrechnung: Blatt und
Versionssatz erzählen dieselbe Sache. Der Fuß steht auf jedem Blatt --
nicht nur auf dem ersten, denn Blätter werden kopiert und einzeln
weitergegeben.

Das Auslesen des PDF arbeitet wie in ``test_pdf_rechenweg.py``: Seiten
unkomprimiert, Textströme direkt gelesen, Umbrüche wieder
zusammengeklebt. Ein Blatt zeichnet seinen Text in einen eigenen
Strom; Bildströme (der QR-Code) liegen dazwischen und tragen den Fuß
nicht -- gezählt wird deshalb, in wie vielen Strömen der Fuß steht,
gegen die Zahl der Blätter (``/Type /Page``).
"""

from __future__ import annotations

import re
import zlib
from decimal import Decimal

import pytest
import reportlab.rl_config

from abrechnung_version import SOFTWARE_VERSION, REGEL_VERSION
from pdf_generator import PDFGenerator

FARM = 'Haus am Anger'


@pytest.fixture
def unkomprimiert(monkeypatch):
    """Seiten ohne Kompression, damit der Text lesbar im Strom steht."""
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)


def _entschluesselt(stueck: str) -> str:
    """Löst die Escapes eines PDF-Textstücks auf (Umlaute als Oktal)."""
    ausgabe = []
    i = 0
    while i < len(stueck):
        zeichen = stueck[i]
        if zeichen == '\\' and i + 1 < len(stueck):
            if stueck[i + 1] in '01234567':
                ziffern = ''
                j = i + 1
                while j < len(stueck) and len(ziffern) < 3 \
                        and stueck[j] in '01234567':
                    ziffern += stueck[j]
                    j += 1
                ausgabe.append(chr(int(ziffern, 8)))
                i = j
                continue
            ausgabe.append(stueck[i + 1])
            i += 2
            continue
        ausgabe.append(zeichen)
        i += 1
    return ''.join(ausgabe).replace(chr(0x80), '€')


def _blaetter(pdf: bytes) -> list[str]:
    """Der geklebte Text jedes Blatts, in der Reihenfolge des Zeichnens."""
    blaetter = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            # Unkomprimierter Inhalt (pageCompression 0) oder Bildstrom:
            # der rohe Inhalt bleibt, Klammern findet der Ausdruck dort
            # genauso.
            pass
        stuecke = [_entschluesselt(m) for m in re.findall(
            r'\(((?:\\.|[^\\)])*)\)', roh.decode('latin-1', 'replace'))]
        blaetter.append(re.sub(r'\s+', '', ''.join(stuecke)))
    return blaetter


def _zeile(nummer: int) -> dict:
    """Eine qm-Zeile mit ihrem Rechenweg, wie der Kern sie liefert."""
    return {
        'category': 'Wasserversorgung',
        'period': '01.01.2024 - 31.12.2024',
        'description': f'Umlage nach qm, Posten {nummer}',
        'tenant_cost': Decimal('301.64'),
        'invoice_days': 366,
        'overlap_days': 184,
        'billing_type': 'qm',
        'provider_name': 'Stadtwerke Musterstadt',
        'invoice_total_amount': Decimal('1200.00'),
        'prorated_amount': Decimal('603.28'),
        'rechenweg': [
            '1200,00 € Rechnungsbetrag, anteilig 184 von 366 Tagen = 603,28 €',
            '603,28 € nach Wohnfläche 50 von 100 qm = 301,64 €',
        ],
        'sub_items': [
            {
                'type': 'allgemein',
                'description': f'Umlage nach qm, Posten {nummer}',
                'cost': Decimal('301.64'),
            },
        ],
    }


def _erzeuge(posten: list[dict], detailliert: bool = False) -> bytes:
    erzeuger = PDFGenerator(
        property_name=FARM,
        apartment_name='Wohnung 1',
        tenant_name='Mustermann',
        start_date='2024-01-01',
        end_date='2024-12-31',
        detailliert=detailliert,
    )
    return erzeuger.generate(posten, Decimal('900.00'), Decimal('0.00'))


def _viele_zeilen() -> list[dict]:
    """Genug Posten, dass das Dokument mehrere Blätter bekommt."""
    return [_zeile(n) for n in range(1, 13)]


def _fuss(sftware: str, regelstand: str) -> str:
    """Die Fußzeile so, wie sie geklebt im PDF-Text steht."""
    import pdf_generator as generator

    try:
        stand = generator.datetime.strptime(
            regelstand, '%Y-%m-%d').strftime('%d.%m.%Y')
    except ValueError:
        stand = regelstand
    return (f'ErstelltmitNebenkostenFix{sftware}'
            f'·RechenstandderRegeln:{stand}')


# --- Der Fuß: beide Stände, auf jedem Blatt ---------------------------------


def test_der_fuss_traegt_software_und_rechenstand(unkomprimiert):
    """Software-Stand und Regelstand stehen lesbar im Fuß -- dieselben
    Stände, die NK-061 in die Version der finalisierten Abrechnung
    schreibt."""
    erwartet = _fuss(SOFTWARE_VERSION, REGEL_VERSION)
    assert erwartet == f'ErstelltmitNebenkostenFix{SOFTWARE_VERSION}·RechenstandderRegeln:28.08.2026'

    for detailliert in (False, True):
        pdf = _erzeuge(_viele_zeilen(), detailliert)
        alle = ''.join(_blaetter(pdf))
        assert erwartet in alle, f'detailliert={detailliert}'


def test_der_fuss_steht_auf_jedem_blatt(unkomprimiert):
    """Jedes Blatt trägt den Fuß -- nicht nur das erste: Blätter werden
    kopiert und einzeln weitergegeben. Gezählt wird je Textstrom, ob der
    Fuß drinsteht; Bildströme (QR-Code) tragen ihn nie."""
    pdf = _erzeuge(_viele_zeilen())
    # /Type /Page, nicht /Type /Pages: das negative Lookahead haelt den
    # Seitenbaum selbst aus der Zahl heraus.
    seiten = len(re.findall(rb'/Type /Page(?![sA-Za-z])', pdf))
    assert seiten >= 2, f'nur {seiten} Blatt/Blätter -- der Test misst nichts'

    erwartet = _fuss(SOFTWARE_VERSION, REGEL_VERSION)
    traeger = [b for b in _blaetter(pdf) if erwartet in b]
    assert len(traeger) == seiten, (
        f'{len(traeger)} von {seiten} Blättern tragen den Fuß')
