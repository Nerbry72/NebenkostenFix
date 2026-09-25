"""Die Vorlagentabelle des Anschreibens (NK-064)

Revision ID: e9d3c72b5f81
Revises: b8f2c61a4e07
Create Date: 2026-09-22

Die fünfzehnte Wanderung: eine Tabelle für die Stimme des Vermieters.

Das Anschreiben mit Zahlungsaufforderung ist editierbar (NK-064): der
Vermieter bestimmt den Ton, die Software füllt die Platzhalter. Die
Tabelle ``anschreiben_vorlagen`` hält je Objekt den eigenen Text; ohne
Eintrag gilt der Vorgabetext aus ``anschreiben.py``. Kein Backfill: der
Vorgabetext lebt als Konstante weiter, eine Zeile entsteht erst mit dem
ersten PUT -- aus dem nichts zu kopieren wäre ein zweiter Ort für
denselben Text.
"""

from alembic import op
import sqlalchemy as sa

#Die Reihenfolge der Wanderungen: d4e6f8a90b12 (rechnungsdatum)
#-> b8f2c61a4e07 (versionstabelle) -> e9d3c72b5f81 (hier).
revision = 'e9d3c72b5f81'
down_revision = 'b8f2c61a4e07'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'anschreiben_vorlagen',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('aktualisiert_am', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', name='uq_vorlage_je_objekt'),
    )


def downgrade():
    op.drop_table('anschreiben_vorlagen')
