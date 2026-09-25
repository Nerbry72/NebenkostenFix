"""Die Zwischenablesung als eigene Ablesungsart (NK-051)

Revision ID: 2514fdc3f655
Revises: c1d47e93a806
Create Date: 2026-09-22

Die neunte Wanderung: eine Spalte mit zwei Werten.

§ 9b HeizkostenV verlangt bei einem Nutzerwechsel innerhalb des
Abrechnungszeitraums eine Ablesung der Ausstattung zur Verbrauchserfassung --
die Zwischenablesung. Sie ist der einzige Messwert, der die Grenze zwischen
zwei Mietverhältnissen wirklich misst. Bisher kannte die Datenbank nur
Zaehlerstaende ohne Art: der Stand zum Wechseldatum war von jedem anderen
nicht zu unterscheiden, und der Rechenkern interpolierte still über die
Grenze hinweg (R-HK-04, IST-Stand "Kritisch").

Die Spalte ``ablesungsart`` kennt zwei Werte: ``ablesung`` -- der Regelfall,
jeder Stand, wie er anfaellt -- und ``zwischenablesung``. Der Altbestand
bekommt durch den serverseitigen Vorgabewert die gewoehnliche Ablesung; an
ihm wird sonst nichts geaendert, und keine Zahl einer bestehenden Abrechnung
rueckt dadurch (D-52 nennt, was sich durch die Art des Rechnens aendert).

Der CHECK haelt die Datenbank auf den zwei Werten fest, aus demselben Grund
wie bei den anderen Aufzaehlungen (NK-096): die Eingabepruefung deckt die
Oberflaeche ab, nicht die eingespielte Sicherung, den Import oder die Zeile
per sqlite3.

``batch_alter_table`` ist auf SQLite noetig, auch fuer eine einzelne Spalte:
SQLite kennt kein ALTER TABLE ADD CONSTRAINT.
"""

from alembic import op
import sqlalchemy as sa

revision = '2514fdc3f655'
down_revision = 'c1d47e93a806'
branch_labels = None
depends_on = None

CHECK_ART = 'ck_meter_readings_ablesungsart'


def upgrade():
    with op.batch_alter_table('meter_readings', schema=None) as stapel:
        stapel.add_column(sa.Column(
            'ablesungsart', sa.String(length=20), nullable=False,
            server_default='ablesung'))
        stapel.create_check_constraint(
            CHECK_ART,
            "ablesungsart IN ('ablesung', 'zwischenablesung')")


def downgrade():
    with op.batch_alter_table('meter_readings', schema=None) as stapel:
        stapel.drop_constraint(CHECK_ART, type_='check')
        stapel.drop_column('ablesungsart')
