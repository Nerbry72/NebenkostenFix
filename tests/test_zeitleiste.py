"""NK-144: Die Zeitleiste der Rechnungen, auf Basis des Rechnungsdatums.

Der Rechnungszeitraum sagt, wofuer ein Beleg gilt; das Rechnungsdatum sagt,
wann er ausgestellt wurde. Die Zeitleiste gruendet auf dem Ausstellungsdatum
und zeigt Jahre/Monate absteigend. Altbestand ohne Datum kommt in eine
eigene Gruppe am Ende -- aus einem NULL wird nichts geraten (D-57).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models import (Apartment, CostCategory, CostInvoice, Property, db)

KATEGORIE = 'Strom (Zeitleiste)'


def kategorie_name() -> str:
    """Der Eintrag-Test gleicht mit der Seed-Kategorie ab, ohne ihren
    Namen hier zu raten."""
    return CostCategory.query.first().name


def _vorbereitung() -> tuple[Property, Apartment, CostCategory]:
    immobilie = Property(name='Zeitleistenhof')
    db.session.add(immobilie)
    db.session.flush()
    wohnung = Apartment(name='Whg. 1', property_id=immobilie.id, sqm=60)
    db.session.add(wohnung)
    # Die Kostenart kommt aus dem Seed-Katalog (BetrKV); eine eigene
    # anzulegen muesste die BetrKV-Nummer und die Rueckfragen mitschleppen.
    kategorie = CostCategory.query.first()
    db.session.flush()
    return immobilie, wohnung, kategorie


def _rechnung(wohnung, kategorie, start, ende, datum, betrag) -> None:
    db.session.add(CostInvoice(
        property_id=wohnung.property_id, apartment_id=wohnung.id,
        category_id=kategorie.id,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(ende),
        rechnungsdatum=(date.fromisoformat(datum) if datum else None),
        amount=Decimal(betrag)))
    db.session.commit()


@pytest.fixture
def zwei_rechnungen(app_ctx):
    """Eine Rechnung im April 2025, eine im Maerz 2024 -- jeweils mit
    Ausstellungsdatum; die Zeitraeume sind bewusst andersherum."""
    _, wohnung, kategorie = _vorbereitung()
    _rechnung(wohnung, kategorie, '2024-03-01', '2024-03-31',
              '2025-04-10', '150.00')
    _rechnung(wohnung, kategorie, '2025-01-01', '2025-01-31',
              '2024-03-05', '300.00')


def test_leerer_bestand_gibt_eine_leere_zeitleiste(app_ctx, auth_client):
    antwort = auth_client.get('/api/invoices/zeitleiste')
    assert antwort.status_code == 200
    koerper = antwort.get_json()
    assert koerper['jahre'] == []
    assert koerper['ohne_datum'] is None
    assert koerper['gesamt'] == 0


def test_zeitraum_zaehlt_nicht_ausstellung_sortiert(app_ctx, auth_client,
                                                    zwei_rechnungen):
    """Die Maerz-2024-Rechnung (ausgestellt 2025) steht unter 2025, die
    Januar-2025-Rechnung (ausgestellt 2024) unter 2024."""
    koerper = auth_client.get('/api/invoices/zeitleiste').get_json()
    jahre = [j['jahr'] for j in koerper['jahre']]
    assert jahre == [2025, 2024]
    monate_2025 = koerper['jahre'][0]['monate']
    assert [m['monat'] for m in monate_2025] == [4]
    assert monate_2025[0]['label'] == 'April'
    assert monate_2025[0]['summe'] == 150.0


def test_monate_stehen_absteigend_und_summen_stimmen(app_ctx, auth_client,
                                                     zwei_rechnungen):
    _, wohnung, kategorie = _vorbereitung()
    _rechnung(wohnung, kategorie, '2025-02-01', '2025-02-28',
              '2025-02-20', '49.50')
    _rechnung(wohnung, kategorie, '2025-04-01', '2025-04-30',
              '2025-04-01', '10.00')

    koerper = auth_client.get('/api/invoices/zeitleiste').get_json()
    jahr_2025 = next(j for j in koerper['jahre'] if j['jahr'] == 2025)
    assert [m['monat'] for m in jahr_2025['monate']] == [4, 2]
    april = jahr_2025['monate'][0]
    assert april['summe'] == 160.0  # 150.00 (altes) + 10.00 (neues)
    assert jahr_2025['summe'] == 209.5
    assert koerper['gesamt'] == 509.5


def test_altbestand_ohne_datum_landet_am_ende(app_ctx, auth_client):
    _, wohnung, kategorie = _vorbereitung()
    wohnung.name = 'Whg. Alt'
    _rechnung(wohnung, kategorie, '2019-01-01', '2019-12-31',
              None, '120.00')

    koerper = auth_client.get('/api/invoices/zeitleiste').get_json()
    assert koerper['jahre'] == []
    rest = koerper['ohne_datum']
    assert rest['summe'] == 120.0
    assert rest['rechnungen'][0]['rechnungsdatum'] is None
    assert koerper['gesamt'] == 120.0


def test_eintraege_tragen_die_ansichtsfelder(app_ctx, auth_client,
                                             zwei_rechnungen):
    koerper = auth_client.get('/api/invoices/zeitleiste').get_json()
    eintrag = koerper['jahre'][0]['monate'][0]['rechnungen'][0]
    assert eintrag['rechnungsdatum'] == '2025-04-10'
    assert eintrag['kategorie_name'] == kategorie_name()
    assert eintrag['property_name'] == 'Zeitleistenhof'
    assert eintrag['hat_beleg'] is False


def test_ohne_anmeldung_gesperrt(app_ctx, anon_client):
    assert anon_client.get('/api/invoices/zeitleiste').status_code == 401


def test_umschalter_und_container_sind_verdrahtet():
    """Die Zeitleiste ist eine zweite Ansicht im Rechnungen-Tab: Umschalter
    (Auswahlpillen ohne Verb), verdeckter Container, Kennungen springen."""
    with open('static/index.html', encoding='utf-8') as datei:
        seite = datei.read()
    assert 'id="pills-invoice-zeitleiste"' in seite
    assert 'zeigeInvoiceZeitleiste()' in seite
    assert 'id="invoices-zeitleiste"' in seite
    assert 'style.css?v=12' in seite
    assert 'app.js?v=28' in seite
    with open('static/app.js', encoding='utf-8') as datei:
        skript = datei.read()
    assert "fetch('/api/invoices/zeitleiste')" in skript
    assert 'renderInvoiceZeitleiste' in skript
