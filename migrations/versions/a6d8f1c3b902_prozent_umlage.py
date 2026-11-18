"""Vertraglicher Prozentsatz im Kostenprofil.

Revision ID: a6d8f1c3b902
Revises: db48fb4e8716
"""
from alembic import op
import sqlalchemy as sa

revision = 'a6d8f1c3b902'
down_revision = 'db48fb4e8716'
branch_labels = None
depends_on = None

ALT = ('qm', 'personen', 'direkt', 'nur_allgemein', 'ignoriert')
ART_CHECK = 'ck_tenant_cost_profiles_billing_type'
PROZENT_CHECK = 'ck_tenant_cost_profiles_percentage'


def _arten(werte):
    return 'billing_type IN (%s)' % ', '.join("'%s'" % wert for wert in sorted(werte))


def upgrade():
    with op.batch_alter_table('tenant_cost_profiles') as batch:
        batch.add_column(sa.Column('percentage', sa.Numeric(5, 2), nullable=True))
        batch.drop_constraint(ART_CHECK, type_='check')
        batch.create_check_constraint(ART_CHECK, _arten((*ALT, 'prozent')))
        batch.create_check_constraint(
            PROZENT_CHECK,
            "(billing_type = 'prozent' AND percentage IS NOT NULL "
            "AND percentage BETWEEN 0 AND 100) OR "
            "(billing_type <> 'prozent' AND percentage IS NULL)")


def downgrade():
    # Keine stillschweigende Umdeutung vertraglicher Anteile beim Rückbau.
    anzahl = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM tenant_cost_profiles WHERE billing_type = 'prozent'"
    )).scalar()
    if anzahl:
        raise RuntimeError('Vor dem Rückbau die prozentualen Kostenprofile umstellen.')
    with op.batch_alter_table('tenant_cost_profiles') as batch:
        batch.drop_constraint(PROZENT_CHECK, type_='check')
        batch.drop_constraint(ART_CHECK, type_='check')
        batch.create_check_constraint(ART_CHECK, _arten(ALT))
        batch.drop_column('percentage')
