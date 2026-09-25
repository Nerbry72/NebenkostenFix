"""Die Versionstabelle finalisierter Abrechnungen (NK-061)

Revision ID: b8f2c61a4e07
Revises: d4e6f8a90b12
Create Date: 2026-09-22

Die vierzehnte Wanderung: eine Tabelle, der Schnappschuss.

Eine finalisierte Abrechnung ist ein zugegangenes Dokument (R-DOC-02):
sie darf nachträglich nicht stillschweigend anders berechnet werden. Bis
hierher speicherte ``tenant_billing_reports`` nur den Pfad des PDFs --
der Rechenweg zur Zahl war nirgends festgehalten, und die Detailroute
rechnete bei jedem Aufruf frisch gegen die aktuelle Datenbank. Änderte
der Vermieter danach einen Zählerstand, antwortete die Route auf die
Frage "was steht in der Abrechnung?" mit etwas anderem als auf dem
Blatt, das der Mieter erhalten hat.

Die neue Tabelle ``billing_report_versions`` trägt je Abrechnung die
Versionen: nummer 1 entsteht mit der Festsetzung, jede Korrektur legt
die nächste an und verweist mit ``ersetzt_version_id`` auf die ersetzte.
Eingangsdaten und Ergebnis liegen als JSON-Schnappschuss bei; der
Software- und der Regelstand reisen mit. Der Altbestand bleibt ohne
Version -- aus dem nichts zu raten ist derselbe Grundsatz wie bei der
Heizkostenart; die Detailroute rechnet für ihn weiter live und die
Lücke ist dokumentiert (D-59).
"""

from alembic import op
import sqlalchemy as sa

revision = 'b8f2c61a4e07'
down_revision = 'd4e6f8a90b12'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'billing_report_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('report_id', sa.Integer(),
                  sa.ForeignKey('tenant_billing_reports.id'), nullable=False),
        sa.Column('nummer', sa.Integer(), nullable=False),
        sa.Column('eingangsdaten', sa.JSON(), nullable=False),
        sa.Column('ergebnis', sa.JSON(), nullable=False),
        sa.Column('software_version', sa.String(length=50), nullable=False),
        sa.Column('regel_version', sa.String(length=50), nullable=False),
        sa.Column('erstellt_am', sa.Date(), nullable=False),
        sa.Column('ersetzt_version_id', sa.Integer(),
                  sa.ForeignKey('billing_report_versions.id'), nullable=True),
        sa.UniqueConstraint('report_id', 'nummer',
                            name='uq_version_pro_abrechnung'),
    )


def downgrade():
    op.drop_table('billing_report_versions')
