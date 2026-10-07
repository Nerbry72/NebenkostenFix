"""Regelstand geprueft (NK-217)

Revision ID: 670627ef0699
Revises: e3c5a7f9b1d2
Create Date: 2026-10-07

Die fuenfundzwanzigste Wanderung: eine nullbare Spalte
``tenant_billing_reports.regelstand_geprueft``. Rechnet eine Abrechnung
nach dem heutigen Regelstand gleich, gibt es keine Korrektur -- der
Hinweis „älterer Regelstand“ blieb dann fuer immer stehen. Die Spalte
haelt fest, gegen welchen Regelstand die Abrechnung ohne Unterschied
geprueft wurde. Kein Backfill: leer heisst nie geprueft.
"""

from alembic import op
import sqlalchemy as sa

revision = '670627ef0699'
down_revision = 'e3c5a7f9b1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('tenant_billing_reports') as batch:
        batch.add_column(sa.Column('regelstand_geprueft', sa.String(50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tenant_billing_reports') as batch:
        batch.drop_column('regelstand_geprueft')
