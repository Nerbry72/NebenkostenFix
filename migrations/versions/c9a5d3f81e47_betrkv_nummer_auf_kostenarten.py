"""BetrKV-Nummer auf cost_categories (NK-044)

Revision ID: c9a5d3f81e47
Revises: b4e7f2a91c65
Create Date: 2026-09-21

Die fuenfte Wanderung. Sie gibt jeder Kostenart die Nummer, unter der sie in
§ 2 BetrKV steht -- und macht sie zur Pflicht.

Warum Pflicht und nicht "kann": die Aufzaehlung des Gesetzes ist
abschliessend (R-KAT-01). Eine Kostenart ohne Nummer ist eine Kostenart, von
der niemand sagen kann, ob sie ueberhaupt umgelegt werden darf -- und auf der
Abrechnung muss sie benannt sein (R-DOC-01). ``nullable=True`` haette genau
den Zustand festgeschrieben, den diese Karte beendet.

Der Altbestand wird **zugeordnet, nicht abgelehnt**. Der alte Seed legte acht
frei benannte Kostenarten an, und ein Vermieter, der die Anwendung seit Jahren
benutzt, hat eigene dazugebaut. ``betrkv.zuordnung()`` sucht in einer nach
Genauigkeit geordneten Liste von Schluesselwoertern: "Gebaeudeversicherung"
wird Nr. 13, "Niederschlagswasser" wird Nr. 3 und nicht Nr. 2.

Was sich nicht zuordnen laesst, wird **Nr. 17** (sonstige Betriebskosten).
Das ist die ehrliche Vermutung: Nr. 17 ist der offene Posten, der ohnehin eine
ausdrueckliche Vereinbarung im Mietvertrag verlangt (R-KAT-02). Eine falsche
benannte Nummer waere schlimmer -- sie saehe geprueft aus.

Jede Zuordnung wird beim Hochfahren protokolliert, mit Name und Nummer. Der
Vermieter soll nachlesen koennen, was die Anwendung ueber seine Kostenarten
angenommen hat; korrigieren kann er es danach in den Stammdaten.

Drei Schritte, und die Reihenfolge ist Pflicht: erst die Spalte anlegen (noch
ohne NOT NULL, sonst scheitert schon das ALTER an den vorhandenen Zeilen),
dann fuellen, dann festziehen. ``batch_alter_table`` ist auf SQLite noetig --
NOT NULL und CHECK lassen sich nicht nachtraeglich anhaengen, Alembic baut die
Tabelle neu und kopiert die Daten. Deshalb muss das Fuellen **vor** dem
Eingriff laufen.
"""

from alembic import op
import sqlalchemy as sa

revision = 'c9a5d3f81e47'
down_revision = 'b4e7f2a91c65'
branch_labels = None
depends_on = None

CONSTRAINT = 'ck_cost_categories_betrkv_nr'


def _bedingung(nummern):
    """Der SQL-Text der Bedingung, erzeugt aus der einen Liste.

    Steht auch in ``models.py``; beide lesen ``betrkv.NUMMERN``, damit eine
    Aenderung des Katalogs nicht an zwei Stellen nachgetragen werden muss.
    """
    return 'betrkv_nr BETWEEN %d AND %d' % (min(nummern), max(nummern))


def _altbestand_zuordnen(verbindung):
    """Gibt jeder vorhandenen Kostenart ihre Nummer. Gibt die Zeilen zurueck."""
    # Der Import steht hier und nicht oben: eine Wanderung laeuft auch aus
    # scripts/ heraus, und ein Importfehler auf Modulebene machte dort das
    # ganze Verzeichnis unbrauchbar (Vorbild: 9c1f4a2b7d33).
    from nebenkostenfix.betrkv import SONSTIGE, bezeichnung, zuordnung

    zeilen = verbindung.execute(sa.text(
        'SELECT id, name FROM cost_categories WHERE betrkv_nr IS NULL'
    )).all()

    protokoll = []
    for kennung, name in zeilen:
        nr = zuordnung(name)
        verbindung.execute(
            sa.text('UPDATE cost_categories SET betrkv_nr = :nr WHERE id = :id'),
            {'nr': nr, 'id': kennung},
        )
        nachsatz = ' (nicht zuzuordnen, bitte pruefen)' if nr == SONSTIGE else ''
        protokoll.append(
            f'NK-044: Kostenart {kennung} „{name}“ -> § 2 BetrKV Nr. {nr}, '
            f'{bezeichnung(nr)}{nachsatz}.'
        )
    return protokoll


def upgrade():
    from nebenkostenfix.betrkv import NUMMERN

    verbindung = op.get_bind()

    # Erst die Spalte, noch ohne NOT NULL: eine Tabelle mit Zeilen nimmt keine
    # Pflichtspalte ohne Vorgabewert an.
    with op.batch_alter_table('cost_categories', schema=None) as stapel:
        stapel.add_column(sa.Column('betrkv_nr', sa.Integer(), nullable=True))

    # Dann fuellen. Das muss vor dem Festziehen laufen: batch_alter_table
    # kopiert die Daten in die neue Tabelle, und eine leere Spalte liesse
    # schon das Kopieren scheitern -- mit einem IntegrityError, der niemandem
    # sagt, was zu tun ist.
    for zeile in _altbestand_zuordnen(verbindung):
        print(zeile)

    # Zum Schluss festziehen: Pflicht und Wertebereich.
    with op.batch_alter_table('cost_categories', schema=None) as stapel:
        stapel.alter_column('betrkv_nr', existing_type=sa.Integer(), nullable=False)
        stapel.create_check_constraint(CONSTRAINT, _bedingung(NUMMERN))


def downgrade():
    # Zurueck geht die ganze Spalte. Anders als bei der Abrechnungsart bleibt
    # hier nichts stehen, was man behalten muesste: die Nummern waren vorher
    # nicht da, und die Zuordnung ist reproduzierbar -- ein erneutes upgrade()
    # errechnet dieselben Werte aus denselben Namen.
    with op.batch_alter_table('cost_categories', schema=None) as stapel:
        stapel.drop_constraint(CONSTRAINT, type_='check')
        stapel.drop_column('betrkv_nr')
