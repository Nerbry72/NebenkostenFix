"""Vermieterdaten in der Datenbank (NK-124)

Revision ID: b5c6d7e8f9a1
Revises: e9d3c72b5f81
Create Date: 2026-09-24

Die einundzwanzigste Wanderung: eine Tabelle mit hoechstens einer Zeile.

Name und IBAN des Vermieters standen bisher nur in Umgebungsvariablen
(VERMIETER_NAME/VERMIETER_IBAN). Ohne Terminal nicht zu setzen, und wenn
sie fehlten, verschwand der GiroCode still vom Blatt. Die neue Tabelle
traegt beides, einmal je Instanz; die Umgebungsvariablen bleiben
Rueckfall (D-81). Felder nullable: halb ausgefuellte Daten sind kein
Fehler, nur "noch kein GiroCode".
"""

from alembic import op
import sqlalchemy as sa

revision = 'b5c6d7e8f9a1'
down_revision = 'e9d3c72b5f81'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'vermieterdaten',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('iban', sa.String(length=34), nullable=True),
        sa.Column('aktualisiert_am', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('vermieterdaten')
