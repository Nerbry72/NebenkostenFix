"""Der Waermezaehler haengt an der Heizungsanlage (NK-049)

Revision ID: f3a9c05e8d72
Revises: e5b2c74f9a16
Create Date: 2026-09-21

Die achte Wanderung, und die kleinste bisher: eine Spalte.

§ 7 Abs. 1 Satz 1 HeizkostenV verteilt 50 bis 70 vom Hundert der Heizkosten
nach **erfasstem Waermeverbrauch**. Erfasst wird er an Waermezaehlern oder
Heizkostenverteilern in den Wohnungen. Damit eine Anlage ihren Nenner bilden
kann -- die Summe dessen, was alle ihre Nutzer verbraucht haben --, muss sie
ihre Zaehler kennen.

**Die Zuordnung steht am Zaehler und wird nicht aus der Kostenart erraten**
(D-45). Ueber die Kostenart waere sie nur ein Umweg mit Ratefehler: ein Haus
mit Vorder- und Hinterhaus hat zwei Anlagen, die ihren Brennstoff auf
dieselbe Kostenart "Heizung" buchen, und ihre Zaehler liessen sich darueber
nicht trennen. Dieselbe Art zu raten hat das Projekt bei F-32 bereits als
Befund erhoben; sie wird hier nicht wiederholt.

Die Spalte ist ``nullable``, und das ist der Regelfall: ein Strom-, Wasser-
oder Gaszaehler gehoert zu keiner Heizungsanlage. Erst ein gesetzter Wert
macht einen Zaehler zum Waermezaehler dieser Anlage.

**Am Altbestand wird nichts geaendert**, aus demselben Grund wie in
e5b2c74f9a16: eine Zuordnung, die diese Wanderung raet, wuerde beim naechsten
Lauf nach Verbrauch verteilen statt nach Flaeche -- eine andere Abrechnung
als die des Vorjahres, ohne dass jemand sie angeordnet haette.

``batch_alter_table`` ist auf SQLite noetig, auch fuer eine einzelne Spalte:
SQLite kennt kein ALTER TABLE ADD CONSTRAINT, und der Fremdschluessel kommt
mit.
"""

from alembic import op
import sqlalchemy as sa

revision = 'f3a9c05e8d72'
down_revision = 'e5b2c74f9a16'
branch_labels = None
depends_on = None

FK_ZAEHLER_ANLAGE = 'fk_meters_heizungsanlage'


def upgrade():
    with op.batch_alter_table('meters', schema=None) as stapel:
        stapel.add_column(sa.Column(
            'heizungsanlage_id', sa.Integer(), nullable=True))
        stapel.create_foreign_key(
            FK_ZAEHLER_ANLAGE, 'heizungsanlagen',
            ['heizungsanlage_id'], ['id'])


def downgrade():
    with op.batch_alter_table('meters', schema=None) as stapel:
        stapel.drop_constraint(FK_ZAEHLER_ANLAGE, type_='foreignkey')
        stapel.drop_column('heizungsanlage_id')
