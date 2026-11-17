"""Angemeldete Geraete der Desktop-App

Revision ID: fc8938938dce
Revises: db48fb4e8716
Create Date: 2026-11-01

Die vierunddreissigste Wanderung: die Tabellen ``geraete``,
``geraete_ersetzt`` und ``geraete_codes`` (#52).

Mit dem Haekchen „Angemeldet bleiben“ bekommt die Desktop-App ein
Geraetetoken, mit dem sie sich still neu anmeldet
(``nebenkostenfix/geraete.py``). In ``geraete`` steht nur der SHA-256 des
aktuellen Tokens, dazu Rechnername und wann es zuletzt benutzt wurde, und
der Zufallswert, an dem eine Sitzung ihr Geraet erkennt.
``geraete_ersetzt`` haelt die ersetzten Tokens fuer die Erkennung von
Kopien, ``geraete_codes`` die kurzlebigen Codes zum Abholen und Anmelden,
beides ebenfalls nur als Hash.

Neue Tabellen ohne Bestand: es gibt nichts nachzutragen. Eine aeltere
Fassung der App laeuft unveraendert weiter, sie fragt die Tabellen nie an.
"""

from alembic import op
import sqlalchemy as sa

revision = 'fc8938938dce'
down_revision = 'db48fb4e8716'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'geraete',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('hash', sa.String(length=64), nullable=False, unique=True),
        # Daran erkennt die Sitzung ihr Geraet, nicht an der Nummer.
        sa.Column('sitzung', sa.String(length=32), nullable=False, unique=True),
        sa.Column('angelegt_am', sa.DateTime(), nullable=False),
        sa.Column('zuletzt_benutzt_am', sa.DateTime(), nullable=False),
        # Nummern trotzdem nicht wiederverwenden.
        sqlite_autoincrement=True,
    )
    op.create_index('ix_geraete_user_id', 'geraete', ['user_id'])
    op.create_table(
        'geraete_ersetzt',
        sa.Column('hash', sa.String(length=64), primary_key=True),
        sa.Column('geraet_id', sa.Integer(), sa.ForeignKey('geraete.id'), nullable=False),
        sa.Column('ersetzt_am', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_geraete_ersetzt_geraet_id', 'geraete_ersetzt', ['geraet_id'])
    op.create_table(
        'geraete_codes',
        sa.Column('hash', sa.String(length=64), primary_key=True),
        sa.Column('zweck', sa.String(length=10), nullable=False),
        sa.Column('geraet_id', sa.Integer(), sa.ForeignKey('geraete.id'), nullable=False),
        sa.Column('gueltig_bis', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_geraete_codes_geraet_id', 'geraete_codes', ['geraet_id'])


def downgrade() -> None:
    # Der Rueckweg meldet alle Geraete ab: die App fragt danach wieder nach
    # dem Passwort. Daten des Bestands kostet er keine.
    op.drop_index('ix_geraete_codes_geraet_id', table_name='geraete_codes')
    op.drop_table('geraete_codes')
    op.drop_index('ix_geraete_ersetzt_geraet_id', table_name='geraete_ersetzt')
    op.drop_table('geraete_ersetzt')
    op.drop_index('ix_geraete_user_id', table_name='geraete')
    op.drop_table('geraete')
