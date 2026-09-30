"""Nutzungsart, Selbstversorger, Eigennutzung und Haushaltsgroessen (NK-045)

Revision ID: d2f8b16c05a9
Revises: c9a5d3f81e47
Create Date: 2026-09-21

Die sechste Wanderung. Sie traegt vier Dinge nach, die das Gesetz
voraussetzt und die in den Stammdaten schlicht fehlten.

**nutzungsart** an der Wohnung (R-CO2-04). Das Programm rechnet nach dem
Recht fuer Wohngebaeude. Ohne dieses Feld sah jedes Objekt aus wie ein
Wohnhaus, auch das mit dem Laden im Erdgeschoss.

**selbstversorger** an der Wohnung (R-CO2-03, § 6 CO2KostAufG). Wer seine
Waerme selbst erzeugt, nimmt an der Heizungsanlage des Hauses nicht teil;
ihm duerfen deren Kosten nicht umgelegt werden.

**eigennutzung** an der Wohnung. Eine vom Vermieter bewohnte Einheit ist
nicht leer und hat doch keinen Mieter. Ohne das Feld sind beide Faelle nicht
zu trennen, und der Leerstandsanteil nach R-NUM-05 waere falsch ausgewiesen.

**haushaltsgroessen** als eigene Tabelle (R-NUM-04). Eine Kopfzahl am
Mietverhaeltnis genuegt nicht: zieht im Juli ein Kind aus, ist nach
Personentagen zu rechnen, nicht nach einer Momentaufnahme. Dafuer braucht es
die Aenderungen mit Datum.

Der Altbestand wird so eingetragen, dass sich **nichts** an einer bereits
erstellten Abrechnung aendert:

* Jede vorhandene Wohnung wird ``wohnen``, nicht Selbstversorger, nicht
  eigengenutzt. Genau so wurde sie bisher gerechnet.
* Jedes vorhandene Mietverhaeltnis bekommt einen Eintrag ueber **eine**
  Person ab seinem Einzugsdatum. Vor NK-045 zaehlte der Rechenkern die
  Mietverhaeltnisse, jedes also als einen Kopf. Ein Update, das daraus
  ploetzlich zwei machte, wuerde dem Vermieter die Nenner verschieben, ohne
  dass er etwas getan hat.

Reihenfolge wie in c9a5d3f81e47: erst die Spalten anlegen (mit
``server_default``, sonst scheitert das ALTER an den vorhandenen Zeilen),
dann die Bedingung festziehen. ``batch_alter_table`` ist auf SQLite noetig.
"""

from alembic import op
import sqlalchemy as sa

revision = 'd2f8b16c05a9'
down_revision = 'c9a5d3f81e47'
branch_labels = None
depends_on = None

CONSTRAINT_NUTZUNG = 'ck_apartments_nutzungsart'


def _bedingung(arten):
    """Der SQL-Text der Bedingung, erzeugt aus der einen Liste.

    Steht auch in ``models.py``; beide lesen ``nutzung.GUELTIG``, damit eine
    dritte Nutzungsart nicht an zwei Stellen nachgetragen werden muss.
    """
    return 'nutzungsart IN (%s)' % ', '.join("'%s'" % a for a in sorted(arten))


def _altbestand_haushalte(verbindung):
    """Gibt jedem vorhandenen Mietverhaeltnis eine Person ab Einzug.

    Gibt die Anzahl der angelegten Zeilen zurueck.
    """
    zeilen = verbindung.execute(sa.text(
        'SELECT t.id, t.move_in_date FROM tenants t '
        'WHERE NOT EXISTS ('
        '  SELECT 1 FROM haushaltsgroessen h WHERE h.tenant_id = t.id)'
    )).all()

    for kennung, einzug in zeilen:
        verbindung.execute(
            sa.text('INSERT INTO haushaltsgroessen '
                    '(tenant_id, gueltig_ab, personenanzahl) '
                    'VALUES (:id, :ab, 1)'),
            {'id': kennung, 'ab': einzug},
        )
    return len(zeilen)


def upgrade():
    # Der Import steht hier und nicht oben: eine Wanderung laeuft auch aus
    # scripts/ heraus, und ein Importfehler auf Modulebene machte dort das
    # ganze Verzeichnis unbrauchbar (Vorbild: 9c1f4a2b7d33).
    from nebenkostenfix.nutzung import GUELTIG, VORGABE

    verbindung = op.get_bind()

    with op.batch_alter_table('apartments', schema=None) as stapel:
        stapel.add_column(sa.Column(
            'nutzungsart', sa.String(length=20),
            nullable=False, server_default=VORGABE))
        stapel.add_column(sa.Column(
            'selbstversorger', sa.Boolean(),
            nullable=False, server_default='0'))
        stapel.add_column(sa.Column(
            'eigennutzung', sa.Boolean(),
            nullable=False, server_default='0'))
        stapel.create_check_constraint(CONSTRAINT_NUTZUNG, _bedingung(GUELTIG))

    op.create_table(
        'haushaltsgroessen',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('gueltig_ab', sa.Date(), nullable=False),
        sa.Column('personenanzahl', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'gueltig_ab',
                            name='uq_haushaltsgroessen_tenant_gueltig_ab'),
        sa.CheckConstraint('personenanzahl >= 1',
                           name='ck_haushaltsgroessen_personenanzahl'),
    )

    angelegt = _altbestand_haushalte(verbindung)
    if angelegt:
        print(f'NK-045: {angelegt} Mietverhaeltnisse auf eine Person ab '
              f'Einzug gesetzt. Das ist die bisherige Rechnung; trage die '
              f'wirklichen Haushaltsgroessen in den Stammdaten nach.')


def downgrade():
    # Zurueck gehen beide Teile vollstaendig. Die Haushaltsgroessen sind
    # dabei ein echter Verlust -- was der Vermieter gepflegt hat, ist danach
    # weg. Anders geht es nicht: vor dieser Wanderung gibt es keinen Ort,
    # an dem die Angabe stehen koennte.
    op.drop_table('haushaltsgroessen')

    with op.batch_alter_table('apartments', schema=None) as stapel:
        stapel.drop_constraint(CONSTRAINT_NUTZUNG, type_='check')
        stapel.drop_column('eigennutzung')
        stapel.drop_column('selbstversorger')
        stapel.drop_column('nutzungsart')
