"""Das Rechnungsdatum an der Kostenrechnung (NK-058)

Revision ID: d4e6f8a90b12
Revises: b6d4e2a71c58
Create Date: 2026-09-22

Die dreizehnte Wanderung: eine Spalte, das Datum des Belegs.

Die Belegliste je Position (R-DOC-01 Punkt 8) nennt Rechnungsnummer,
Anbieter, Datum und Dokumentseite. Nummer, Anbieter und Seiten standen
schon an der Rechnung; das Datum nicht -- es gab nur den
Rechnungszeitraum (``start_date``/``end_date``), und der ist etwas
anderes: eine Rechnung fuer Januar bis Maerz kann im April ausgestellt
sein. Wer dem Mieter den Zeitraum als "Datum" verkauft, nennt zwei
Sachen mit einem Wort.

Die Spalte bleibt nullable: der Altbestand traegt kein Datum, und aus
einem NULL nichts zu raten ist derselbe Grundsatz wie bei der
Heizkostenart, den CO2-Angaben und den Tarifpreisen. Das PDF weist das
Datum aus, wo es da ist, und schweigt, wo es fehlt -- einen Zeitraum
als Datum auszugeben waere die Erfindung, die die Spalte vermeiden soll.
"""

from alembic import op
import sqlalchemy as sa

revision = 'd4e6f8a90b12'
down_revision = 'b6d4e2a71c58'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cost_invoices') as batch:
        batch.add_column(sa.Column('rechnungsdatum', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cost_invoices') as batch:
        batch.drop_column('rechnungsdatum')
