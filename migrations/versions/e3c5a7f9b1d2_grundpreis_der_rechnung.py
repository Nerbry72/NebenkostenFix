"""Grundpreis der Rechnung (F-137)

Revision ID: e3c5a7f9b1d2
Revises: a4d7e1c9b3f5
Create Date: 2026-10-01

Die vierundzwanzigste Wanderung: eine nullbare Spalte
``cost_invoices.grundpreis`` samt CHECK (nicht negativ, nicht ueber dem
Betrag). Eine Wohnungsrechnung mit Zaehler wurde ganz nach Verbrauch
geteilt; der Grundpreis der Leermonate landete so beim Mieter. Kein
Backfill: leer heisst keine Angabe, gerechnet wird wie bisher.
"""

from alembic import op
import sqlalchemy as sa

revision = 'e3c5a7f9b1d2'
down_revision = 'a4d7e1c9b3f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cost_invoices') as batch:
        batch.add_column(sa.Column('grundpreis', sa.Numeric(12, 2), nullable=True))
        batch.create_check_constraint(
            'ck_cost_invoices_grundpreis_im_betrag',
            'grundpreis IS NULL OR (grundpreis >= 0 AND grundpreis <= amount)')


def downgrade() -> None:
    with op.batch_alter_table('cost_invoices') as batch:
        batch.drop_constraint('ck_cost_invoices_grundpreis_im_betrag', type_='check')
        batch.drop_column('grundpreis')
