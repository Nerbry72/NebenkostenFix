"""NK-187: der Datenwaechter findet echte Werte und laesst erfundene durch.

Alle Werte hier sind erfunden; die Tabelle ersetzt den echten Bestand.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import datenwaechter as w  # noqa: E402

SCHEMA = """
CREATE TABLE tenants (name, move_in_date, move_out_date);
CREATE TABLE properties (name);
CREATE TABLE apartments (name);
CREATE TABLE providers (name);
CREATE TABLE vermieterdaten (name);
CREATE TABLE users (username);
CREATE TABLE meters (meter_number);
CREATE TABLE cost_invoices (invoice_number, amount, co2_kosten, start_date, end_date, rechnungsdatum);
CREATE TABLE payments (amount, payment_date);
CREATE TABLE meter_readings (value, value_nt, reading_date);
"""


def _bestand():
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    db.execute("INSERT INTO tenants VALUES ('Quendolin Traxmeier', '2023-03-17', NULL)")
    db.execute("INSERT INTO properties VALUES ('Haus Vermieter')")
    db.execute("INSERT INTO meters VALUES ('ZX-77413')")
    db.execute("INSERT INTO cost_invoices VALUES (NULL, 873.46, 0, '2025-01-01', '2025-12-31', NULL)")
    db.execute("INSERT INTO meter_readings VALUES (4711.3, NULL, '2025-12-31')")
    db.execute("INSERT INTO meter_readings VALUES (121, NULL, '2025-12-31')")
    return w.werte(db)


def _arten(zeile):
    return [art for _, art, _ in w.treffer(_bestand(), [zeile])]


def test_echte_werte_schlagen_an():
    assert _arten("name='Traxmeier'") == ['Name']
    assert _arten("nummer='zx-77413'") == ['Name']
    assert _arten("betrag=Decimal('873,46')") == ['Betrag']
    assert _arten('stand = 4711.3') == ['Zählerstand']
    assert _arten('einzug = date(2023, 3, 17)') == ['Datum']
    assert _arten('Einzug am 17.03.2023') == ['Datum']


def test_alltag_und_runde_werte_bleiben_still():
    """Allerweltswoerter, Monatsgrenzen, kleine ganze Staende: stehen in jedem Test."""
    assert not _arten("Mieter 1 zahlt an den Vermieter im Haus")
    assert not _arten("BEGINN = date(2025, 1, 1); ENDE = date(2025, 12, 31)")
    assert not _arten("stand = 121; betrag = Decimal('873.00')")
    assert not _arten("name = 'Traxmeierstrasse'")  # Teil eines Worts ist kein Name
