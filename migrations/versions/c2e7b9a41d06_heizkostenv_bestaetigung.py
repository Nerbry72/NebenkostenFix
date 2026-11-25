"""Ausdrückliche Bestätigung zu § 2 HeizkostenV bei Prozentprofilen.

Revision ID: c2e7b9a41d06
Revises: a6d8f1c3b902
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2e7b9a41d06'
down_revision = 'a6d8f1c3b902'
branch_labels = None
depends_on = None


def upgrade():
    # Vorhandene Profile behalten ihre Anteile, aber bestätigen keinen Hinweis
    # stellvertretend für den Nutzer.
    with op.batch_alter_table('tenant_cost_profiles') as batch:
        batch.add_column(sa.Column('heizkostenv_bestaetigt', sa.Boolean(),
                                   nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('tenant_cost_profiles') as batch:
        batch.drop_column('heizkostenv_bestaetigt')
