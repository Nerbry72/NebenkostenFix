"""Zugriffsschluessel fuer Programme ohne Browser

Revision ID: db48fb4e8716
Revises: f2a6c8b4d013
Create Date: 2026-10-27

Die dreiunddreissigste Wanderung: die Tabelle ``api_schluessel``.

Ein Programm, das im Hintergrund laeuft (etwa ein MCP-Server), meldet sich
nicht per Formular an, sondern schickt einen Zugriffsschluessel mit
(``nebenkostenfix/zugriffsschluessel.py``). In der Tabelle steht nur dessen
SHA-256, dazu Name, Umfang (``lesen``/``erfassen``) und wann er zuletzt
benutzt wurde. Der Schluessel selbst erscheint nur einmal beim Anlegen.

Eine neue Tabelle ohne Bestand: es gibt nichts nachzutragen.
"""

from alembic import op
import sqlalchemy as sa

revision = 'db48fb4e8716'
down_revision = 'f2a6c8b4d013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'api_schluessel',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('umfang', sa.String(length=10), nullable=False),
        sa.Column('angelegt_am', sa.DateTime(), nullable=False),
        sa.Column('zuletzt_benutzt_am', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_api_schluessel_user_id', 'api_schluessel', ['user_id'])


def downgrade() -> None:
    # Der Rueckweg nimmt die Schluessel mit. Programme, die einen benutzt
    # haben, kommen danach nicht mehr hinein; Daten des Bestands kostet er
    # keine.
    op.drop_index('ix_api_schluessel_user_id', table_name='api_schluessel')
    op.drop_table('api_schluessel')
