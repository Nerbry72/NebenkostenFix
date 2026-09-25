"""Sperre statt Loeschung waehrend der Aufbewahrungsfrist (NK-153)

Revision ID: c7d8e9f0a1b2
Revises: b5c6d7e8f9a1
Create Date: 2026-09-24

Die zweiundzwanzigste Wanderung: eine nullbare Spalte ``tenants.gesperrt_bis``.
Die DSGVO-Loeschung (NK-078) entfernte bis hierher auch festgesetzte
Abrechnungen und Zahlungen, obwohl § 147 AO und § 257 HGB bis zu zehn Jahre
Aufbewahrung verlangen (E-11). Jetzt bleibt das Mietverhaeltnis bis zum
Fristende gesperrt stehen. Kein Backfill: bestehende Mieter sind nicht
gesperrt.
"""

from alembic import op
import sqlalchemy as sa

revision = 'c7d8e9f0a1b2'
down_revision = 'b5c6d7e8f9a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('tenants') as batch:
        batch.add_column(sa.Column('gesperrt_bis', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tenants') as batch:
        batch.drop_column('gesperrt_bis')
