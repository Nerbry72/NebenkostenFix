"""Die Preise je Tarif einer Dualtarifrechnung (NK-055)

Revision ID: b6d4e2a71c58
Revises: c7e1a9f30d42
Create Date: 2026-09-22

Die zwoelfte Wanderung: zwei Spalten, die Tarife unterscheiden.

Ein Zaehler mit Hoch- und Niedertarif (Spalte ``meters.has_dual_tariff``
gab es immer) liefert zwei Mengen, und der Versorger stellt ihnen zwei
Preise. Die Rechnung trug bisher nur den Gesamtbetrag -- der Rechenkern
teilte ihn durch die addierte Gesamtmenge und rechnete einem NT-Kunden den
HT-Anteil mit unter (IST-Stand, Risiko 8). Nun traegt die Rechnung ihre
beiden Preise selbst.

``preis_ht`` und ``preis_nt`` bleiben nullable: NULL heisst Einheitstarif
oder keine Angabe, und der Altbestand hat keinen -- aus einem NULL nichts
zu raten ist derselbe Grundsatz wie bei der Heizkostenart und den
CO2-Angaben. Der Rechenkern faellt in diesem Fall auf den einen Mischpreis
zurueck, den es bisher gab.

Die Wanderrichtung ist rein schematisch: es gibt keinen Altbestand, der
sich aus vorhandenen Spalten nachrechnen liesse -- ein Preis je Tarif
steht nur auf dem Beleg, nicht in der Datenbank. Der Spaltentyp ist
deshalb hier direkt `NUMERIC(12, 4)` -- derselbe, den der Typ
`Einheitspreis` in `geld.py` an der ORM-Seite behauptet; eine Wanderung
importiert nichts aus der App (Vorbild: b4e7f2a91c65), und das Schema
braucht den TypeDecorator nicht, nur die Stellen.
"""

from alembic import op
import sqlalchemy as sa

revision = 'b6d4e2a71c58'
down_revision = 'c7e1a9f30d42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cost_invoices') as batch:
        batch.add_column(sa.Column('preis_ht', sa.Numeric(12, 4), nullable=True))
        batch.add_column(sa.Column('preis_nt', sa.Numeric(12, 4), nullable=True))
        batch.create_check_constraint(
            'ck_cost_invoices_dualtarif_vollstaendig',
            '(preis_ht IS NULL) = (preis_nt IS NULL)')
        batch.create_check_constraint(
            'ck_cost_invoices_dualtarif_nichtnegativ',
            '(preis_ht IS NULL OR preis_ht >= 0) AND '
            '(preis_nt IS NULL OR preis_nt >= 0)')


def downgrade() -> None:
    with op.batch_alter_table('cost_invoices') as batch:
        batch.drop_constraint('ck_cost_invoices_dualtarif_nichtnegativ')
        batch.drop_constraint('ck_cost_invoices_dualtarif_vollstaendig')
        batch.drop_column('preis_nt')
        batch.drop_column('preis_ht')
