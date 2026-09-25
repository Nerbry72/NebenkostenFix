"""Basisrevision: IST-Stand von models.py (NK-024)

Diese Revision beschreibt das Schema, wie es vor Alembic gewachsen ist. Sie
wird auf zwei Wegen benutzt:

- Leere Datenbank: upgrade() legt hier alle Tabellen an, danach laufen die
  spaeteren Revisionen.
- Bestehende Datenbank eines Betreibers: die Tabellen sind schon da, deshalb
  stempelt app.schema_aktualisieren() nur diese Revisionsnummer in
  alembic_version, ohne eine der Anweisungen unten auszufuehren. Die Daten
  werden nicht angefasst.

Deshalb wird an dieser Datei nichts mehr geaendert. Wer das Schema aendert,
schreibt eine neue Revision darueber.

Revision ID: 63738d5329b4
Revises:
Create Date: 2026-08-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '63738d5329b4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cost_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('allocation_method', sa.String(length=50), nullable=False),
    sa.Column('requires_meter', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('properties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('is_standalone', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('providers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table('apartments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('property_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('sqm', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('invoice_documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('property_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('document_path', sa.String(length=500), nullable=False),
    sa.Column('upload_date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('is_collective', sa.Boolean(), server_default='true', nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('cost_invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('property_id', sa.Integer(), nullable=False),
    sa.Column('apartment_id', sa.Integer(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('invoice_number', sa.String(length=100), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('provider_id', sa.Integer(), nullable=True),
    sa.Column('document_path', sa.String(length=255), nullable=True),
    sa.Column('invoice_document_id', sa.Integer(), nullable=True),
    sa.Column('document_pages', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ),
    sa.ForeignKeyConstraint(['category_id'], ['cost_categories.id'], ),
    sa.ForeignKeyConstraint(['invoice_document_id'], ['invoice_documents.id'], ),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
    sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('meters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('property_id', sa.Integer(), nullable=False),
    sa.Column('apartment_id', sa.Integer(), nullable=True),
    sa.Column('is_main_meter', sa.Boolean(), nullable=False),
    sa.Column('meter_number', sa.String(length=100), nullable=False),
    sa.Column('has_dual_tariff', sa.Boolean(), nullable=False),
    sa.Column('is_official', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ),
    sa.ForeignKeyConstraint(['category_id'], ['cost_categories.id'], ),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tenants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('apartment_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('move_in_date', sa.Date(), nullable=False),
    sa.Column('move_out_date', sa.Date(), nullable=True),
    sa.Column('last_billed_until', sa.Date(), nullable=True),
    sa.Column('contract_path', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('meter_readings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meter_id', sa.Integer(), nullable=False),
    sa.Column('reading_date', sa.Date(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('value_nt', sa.Float(), nullable=True),
    sa.Column('is_official_invoice', sa.Boolean(), nullable=False),
    sa.Column('provider_id', sa.Integer(), nullable=True),
    sa.Column('document_path', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ),
    sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tenant_billing_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.Date(), nullable=False),
    sa.Column('document_path', sa.String(length=500), nullable=True),
    sa.Column('document_path_detailed', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tenant_cost_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('billing_type', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['cost_categories.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('billing_report_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['cost_categories.id'], ),
    sa.ForeignKeyConstraint(['report_id'], ['tenant_billing_reports.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('billing_report_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['billing_report_id'], ['tenant_billing_reports.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('payments')
    op.drop_table('billing_report_categories')
    op.drop_table('tenant_cost_profiles')
    op.drop_table('tenant_billing_reports')
    op.drop_table('meter_readings')
    op.drop_table('tenants')
    op.drop_table('meters')
    op.drop_table('cost_invoices')
    op.drop_table('invoice_documents')
    op.drop_table('apartments')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))

    op.drop_table('users')
    op.drop_table('providers')
    op.drop_table('properties')
    op.drop_table('cost_categories')
