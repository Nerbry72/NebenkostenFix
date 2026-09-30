"""Heizungsanlage als Entitaet, Heizkostenposten an der Rechnung (NK-048)

Revision ID: e5b2c74f9a16
Revises: d2f8b16c05a9
Create Date: 2026-09-21

Die siebte Wanderung. Sie legt den Ort an, an dem Heizkosten eine Masse
werden koennen.

**heizungsanlagen** als eigene Tabelle (R-HK-02). § 7 Abs. 2 HeizkostenV
zaehlt acht Posten auf -- Brennstoff, Betriebsstrom, Bedienung, Pruefung,
Reinigung, Messungen, Anmietung und Verwendung der Verbrauchserfassung --,
und § 7 Abs. 1 verteilt ihre **Summe** zu 50 bis 70 vom Hundert nach
Verbrauch. Ohne eine Anlage gibt es keinen Ort fuer diese Summe und keinen
fuer den Anteil; bisher lief Gas als gewoehnlicher Zaehlerschluessel und die
Wartungsrechnung als irgendeine Position nach Flaeche.

**heizungsanlage_id** und **heizkostenart** an der Rechnung. Die Zuordnung
haengt am Vorgang, nicht an der Kostenart (D-44): dieselbe Kostenart
"Heizung" traegt im Jahr die Brennstoffrechnung, die Wartungsrechnung und
die des Ablesedienstes. Der CHECK verlangt beides oder keines -- eine
Rechnung an einer Anlage ohne Posten laesst sich nicht ausweisen (R-DOC-01),
ein Posten ohne Anlage gehoert zu keiner Masse und verschwaende.

**Am Altbestand wird nichts geaendert.** Keine Anlage wird angelegt, keine
Rechnung zugeordnet. Das ist Absicht: sobald NK-049 rechnet, verteilt eine
zugeordnete Rechnung nach Verbrauch statt nach Flaeche, und das waere eine
andere Abrechnung als die, die der Vermieter im Jahr davor verschickt hat.
Wer seine Heizung erfassen will, legt die Anlage an und haengt die
Rechnungen um -- sichtbar, von Hand, mit einem Datum davor und danach.

Reihenfolge wie in d2f8b16c05a9: erst die Tabelle, dann die Spalten, dann
die Bedingungen. ``batch_alter_table`` ist auf SQLite noetig.
"""

from alembic import op
import sqlalchemy as sa

revision = 'e5b2c74f9a16'
down_revision = 'd2f8b16c05a9'
branch_labels = None
depends_on = None

CONSTRAINT_ART = 'ck_cost_invoices_heizkostenart'
CONSTRAINT_VOLLSTAENDIG = 'ck_cost_invoices_heizung_vollstaendig'


def _aufzaehlung(spalte, werte):
    """Der SQL-Text einer IN-Bedingung, erzeugt aus der einen Liste.

    Steht auch in ``models.py``; beide lesen ``heizung``, damit ein neunter
    Posten nicht an zwei Stellen nachgetragen werden muss.
    """
    return '%s IN (%s)' % (
        spalte, ', '.join("'%s'" % w for w in sorted(werte)))


def upgrade():
    # Der Import steht hier und nicht oben: eine Wanderung laeuft auch aus
    # scripts/ heraus, und ein Importfehler auf Modulebene machte dort das
    # ganze Verzeichnis unbrauchbar (Vorbild: 9c1f4a2b7d33).
    from nebenkostenfix.heizung import (
        ANTEIL_MAX, ANTEIL_MIN, ANTEIL_VORGABE, HEIZUNG, SCHLUESSEL, VERSORGT)

    op.create_table(
        'heizungsanlagen',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('versorgt', sa.String(length=20), nullable=False,
                  server_default=HEIZUNG),
        sa.Column('verbrauchsanteil_prozent', sa.Integer(), nullable=False,
                  server_default=str(ANTEIL_VORGABE)),
        sa.Column('sonderfall_70', sa.Boolean(), nullable=False,
                  server_default='0'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(_aufzaehlung('versorgt', VERSORGT),
                           name='ck_heizungsanlagen_versorgt'),
        sa.CheckConstraint(
            'verbrauchsanteil_prozent BETWEEN %d AND %d' % (
                ANTEIL_MIN, ANTEIL_MAX),
            name='ck_heizungsanlagen_verbrauchsanteil'),
        sa.CheckConstraint(
            'NOT sonderfall_70 OR verbrauchsanteil_prozent = %d' % ANTEIL_MAX,
            name='ck_heizungsanlagen_sonderfall'),
    )

    with op.batch_alter_table('cost_invoices', schema=None) as stapel:
        stapel.add_column(sa.Column(
            'heizungsanlage_id', sa.Integer(), nullable=True))
        stapel.add_column(sa.Column(
            'heizkostenart', sa.String(length=30), nullable=True))
        stapel.create_foreign_key(
            'fk_cost_invoices_heizungsanlage', 'heizungsanlagen',
            ['heizungsanlage_id'], ['id'])
        stapel.create_check_constraint(
            CONSTRAINT_ART,
            'heizkostenart IS NULL OR %s' % _aufzaehlung(
                'heizkostenart', SCHLUESSEL))
        stapel.create_check_constraint(
            CONSTRAINT_VOLLSTAENDIG,
            '(heizungsanlage_id IS NULL) = (heizkostenart IS NULL)')


def downgrade():
    # Zurueck geht beides vollstaendig. Was der Vermieter an Anlagen gepflegt
    # hat, ist danach weg -- vor dieser Wanderung gibt es keinen Ort, an dem
    # die Angabe stehen koennte. Die Rechnungen selbst bleiben unberuehrt,
    # sie verlieren nur ihre Zuordnung.
    with op.batch_alter_table('cost_invoices', schema=None) as stapel:
        stapel.drop_constraint(CONSTRAINT_VOLLSTAENDIG, type_='check')
        stapel.drop_constraint(CONSTRAINT_ART, type_='check')
        stapel.drop_constraint('fk_cost_invoices_heizungsanlage',
                               type_='foreignkey')
        stapel.drop_column('heizkostenart')
        stapel.drop_column('heizungsanlage_id')

    op.drop_table('heizungsanlagen')
