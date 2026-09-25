"""Die CO2-Angaben an der Rechnung (NK-053)

Revision ID: b8e2f41a90c3
Revises: 2514fdc3f655
Create Date: 2026-09-22

Die zehnte Wanderung: zwei Spalten für den § 5 CO2KostAufG.

Die Kohlendioxidkostenaufteilung braucht zwei Zahlen, die nur der Beleg
kennt: die **Emissionsmenge** in Kilogramm und die **CO2-Kosten** in Euro,
wie die Lieferantenrechnung sie ausweist (R-CO2-02 nennt die Herkunft als
Teil des Ausweises). Beide stehen je Rechnung -- dieselbe Stelle wie die
Heizkostenart (D-44): unter der Kostenart "Heizung" laufen im Jahr der
Brennstoff, die Wartung und der Ablesedienst, aber nur der Brennstoff
emittiert.

Der Altbestand bleibt unberuehrt (derselbe Grundsatz wie bei NK-048 und
NK-096): beide Spalten sind NULL-faehig, und NULL heisst "keine Angabe".
Eine Wanderung, die Emissionen aus dem Brennstoffverbrauch rechnete,
haette Zahlen erfunden, die niemand belegt hat -- die Emission ist
Belegsache (Emissionsfaktor des Lieferanten), nicht Rechensache.

Zwei CHECKs halten die Qualitaet: keine negativen Angaben, und CO2-Angaben
nur an Rechnungen mit Heizkostenart -- eine Buerorechnung mit einer
Emissionsmenge waere entweder ein Tippfehler oder eine warme Vermutung.
``batch_alter_table`` ist auf SQLite noetig, auch fuer eine einzelne
Spalte: SQLite kennt kein ALTER TABLE ADD CONSTRAINT.
"""

from alembic import op
import sqlalchemy as sa

revision = 'b8e2f41a90c3'
down_revision = '2514fdc3f655'
branch_labels = None
depends_on = None

CHECK_NEGATIV = 'ck_cost_invoices_co2_nichtnegativ'
CHECK_HEIZUNG = 'ck_cost_invoices_co2_nur_heizung'


def upgrade():
    with op.batch_alter_table('cost_invoices', schema=None) as stapel:
        stapel.add_column(sa.Column('co2_kosten', sa.Numeric(12, 2), nullable=True))
        stapel.add_column(sa.Column(
            'co2_emission_kg', sa.Numeric(12, 2), nullable=True))
        stapel.create_check_constraint(
            CHECK_NEGATIV,
            '(co2_kosten IS NULL OR co2_kosten >= 0) AND '
            '(co2_emission_kg IS NULL OR co2_emission_kg >= 0)')
        stapel.create_check_constraint(
            CHECK_HEIZUNG,
            '(co2_kosten IS NULL AND co2_emission_kg IS NULL) '
            'OR heizkostenart IS NOT NULL')


def downgrade():
    with op.batch_alter_table('cost_invoices', schema=None) as stapel:
        stapel.drop_constraint(CHECK_HEIZUNG, type_='check')
        stapel.drop_constraint(CHECK_NEGATIV, type_='check')
        stapel.drop_column('co2_emission_kg')
        stapel.drop_column('co2_kosten')
