"""UNIQUE auf cost_categories.name (NK-095)

Revision ID: 9c1f4a2b7d33
Revises: 63738d5329b4
Create Date: 2026-09-20

Die zweite Wanderung des Projekts. Die erste (``63738d5329b4``) hat nur den
Ist-Stand festgehalten; diese aendert zum ersten Mal wirklich etwas am Schema.

Warum ueberhaupt: zwei Kostenarten "Heizung" sind fuer die Datenbank zwei
Dinge und fuer den Vermieter eines. Er sieht sie doppelt in der Auswahlliste,
haengt die Rechnungen an die eine und die Zaehler an die andere, und die
Abrechnung rechnet dann mit der Haelfte. NK-024 hat den bekannten Weg dorthin
geschlossen (``seed_database()`` bei vier gunicorn-Arbeitern), aber nur den
einen. Im Schema gilt die Regel fuer alle Wege.

Warum nicht einfach ``create_unique_constraint``: eine Instanz, die seit
Monaten laeuft, kann die Dubletten schon haben. Dann scheitert die Wanderung
beim Hochfahren -- und ``IntegrityError: UNIQUE constraint failed`` sagt
niemandem, was zu tun ist. Deshalb prueft ``upgrade()`` **vor** dem Eingriff
und bricht mit einem deutschen Satz ab, der die Namen nennt und den Weg zum
Aufraeumen zeigt. Angefasst wird dabei kein einziger Datensatz.

``batch_alter_table`` ist auf SQLite Pflicht: ein ``ALTER TABLE ... ADD
CONSTRAINT`` kennt SQLite nicht. Alembic baut die Tabelle neu, kopiert die
Daten und tauscht sie -- deshalb steht ``render_as_batch=True`` seit NK-024
in ``env.py``.
"""

from alembic import op
import sqlalchemy as sa

revision = '9c1f4a2b7d33'
down_revision = '63738d5329b4'
branch_labels = None
depends_on = None

CONSTRAINT = 'uq_cost_categories_name'


def upgrade():
    # Der Import steht hier und nicht oben: eine Wanderung laeuft auch aus
    # scripts/ und aus dem Notfallweg heraus, und ein Importfehler auf
    # Modulebene wuerde dort das ganze Verzeichnis unbrauchbar machen.
    from kategorien import dubletten_finden, meldung_zu_dubletten

    verbindung = op.get_bind()
    dubletten = dubletten_finden(verbindung)
    if dubletten:
        raise RuntimeError(meldung_zu_dubletten(dubletten))

    with op.batch_alter_table('cost_categories', schema=None) as stapel:
        stapel.create_unique_constraint(CONSTRAINT, ['name'])


def downgrade():
    with op.batch_alter_table('cost_categories', schema=None) as stapel:
        stapel.drop_constraint(CONSTRAINT, type_='unique')
