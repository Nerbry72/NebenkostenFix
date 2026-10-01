"""Abrechnungsjahr je Haus (NK-188, D-114)

Revision ID: a4d7e1c9b3f5
Revises: c7d8e9f0a1b2
Create Date: 2026-09-30

Die dreiundzwanzigste Wanderung: eine nullbare Spalte
``properties.abrechnungsjahr_beginn`` ('MM-TT'). Der Zeitraumvorschlag
kannte nur das Kalenderjahr; ein Haus, das April bis Maerz abrechnet,
bekam Rumpfzeitraeume vorgeschlagen. Kein Backfill: leer heisst, die App
leitet den Beginn aus den bisherigen Abrechnungen ab, sonst 01.01.
"""

from alembic import op
import sqlalchemy as sa

revision = 'a4d7e1c9b3f5'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('properties') as batch:
        batch.add_column(sa.Column('abrechnungsjahr_beginn', sa.String(length=5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('properties') as batch:
        batch.drop_column('abrechnungsjahr_beginn')
