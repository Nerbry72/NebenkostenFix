"""CHECK auf tenant_cost_profiles.billing_type (NK-096)

Revision ID: b4e7f2a91c65
Revises: a7c3e91d4b28
Create Date: 2026-09-21

Die vierte Wanderung. Sie traegt ins Schema, was seit dieser Karte an der
Eingabe (``validation.kostenprofile``) und im Rechenkern
(``rechenkern.abrechnungsart_von``) ohnehin gilt: ``billing_type`` ist einer
von fuenf Werten und sonst nichts.

Warum das nicht am Anwendungscode haengen darf: bis hierher nahm die Route
jede Zeichenkette entgegen, und der Rechenkern liess die Kostenart lautlos
aus dem Blatt fallen, wenn er sie nicht kannte (F-25). Die Eingabepruefung
schliesst den Weg ueber die Oberflaeche. Sie schliesst nicht den Weg ueber
eine eingespielte Sicherung, einen Import oder eine Zeile per ``sqlite3`` --
und eine Bedingung in der Datenbank gilt auch fuer den Weg, an den niemand
gedacht hat. Dasselbe Argument wie beim UNIQUE in ``9c1f4a2b7d33``.

Der Altbestand wird hier **repariert, nicht abgelehnt**. Anders als bei den
Dubletten gibt es einen Wert, der nichts kaputtmacht:

* Was sich normieren laesst, wird normiert. ``'Qm'`` und ``'direkt '`` waren
  bisher unbekannt und fielen aus dem Blatt; sie sind aber offensichtlich
  gemeint und werden zu ``'qm'`` beziehungsweise ``'direkt'``. Das aendert das
  Ergebnis -- zugunsten dessen, was der Vermieter eingetragen hat.
* Alles Uebrige bekommt ``ERSATZ`` (``'ignoriert'``), siehe D-30. Bisher fiel
  die Kostenart aus dem Blatt, der Mieter zahlte also nichts. Auf ``'qm'`` zu
  stellen wuerde ihm beim Einspielen eines Updates stillschweigend Geld
  berechnen -- das waere eine Abrechnung, die niemand geprueft hat.
  ``'ignoriert'`` behaelt das bisherige Ergebnis bei und macht es zum ersten
  Mal sichtbar: die Zeile steht im Kostenprofil und der Vermieter kann sie
  aendern.

Jede Aenderung wird beim Hochfahren protokolliert, mit altem und neuem Wert.
Eine stille Datenaenderung waere genau der Fehler, den diese Karte schliesst.

``batch_alter_table`` ist auf SQLite Pflicht: ein CHECK laesst sich nicht
nachtraeglich per ``ALTER TABLE`` anhaengen. Alembic baut die Tabelle neu und
kopiert die Daten -- deshalb muss das Aufraeumen **vor** dem Eingriff laufen,
sonst scheitert schon das Kopieren.
"""

from alembic import op
import sqlalchemy as sa

revision = 'b4e7f2a91c65'
down_revision = 'a7c3e91d4b28'
branch_labels = None
depends_on = None

CONSTRAINT = 'ck_tenant_cost_profiles_billing_type'


def _bedingung(arten):
    """Der SQL-Text der Bedingung, erzeugt aus der einen Liste.

    Steht auch in ``models.py``; beide lesen ``abrechnungsart.GUELTIG``, damit
    eine sechste Art nicht an zwei Stellen nachgetragen werden muss.
    """
    return 'billing_type IN (%s)' % ', '.join("'%s'" % a for a in sorted(arten))


def _altbestand_geradeziehen(verbindung):
    """Setzt jeden unbekannten Wert auf etwas Gueltiges. Gibt die Zeilen zurueck."""
    # Der Import steht hier und nicht oben: eine Wanderung laeuft auch aus
    # scripts/ heraus, und ein Importfehler auf Modulebene machte dort das
    # ganze Verzeichnis unbrauchbar (Vorbild: 9c1f4a2b7d33).
    from abrechnungsart import ERSATZ, ist_gueltig, normiere

    zeilen = verbindung.execute(sa.text(
        'SELECT id, tenant_id, category_id, billing_type FROM tenant_cost_profiles'
    )).all()

    protokoll = []
    for kennung, mieter, kostenart, roh in zeilen:
        if ist_gueltig(roh):
            continue
        normiert = normiere(roh)
        neu = normiert if ist_gueltig(normiert) else ERSATZ
        verbindung.execute(
            sa.text('UPDATE tenant_cost_profiles SET billing_type = :wert WHERE id = :id'),
            {'wert': neu, 'id': kennung},
        )
        protokoll.append(
            f'NK-096: Kostenprofil {kennung} (Mieter {mieter}, Kostenart '
            f'{kostenart}): Abrechnungsart {roh!r} -> {neu!r}.'
        )
    return protokoll


def upgrade():
    from abrechnungsart import GUELTIG

    verbindung = op.get_bind()

    # Erst aufraeumen, dann die Bedingung setzen: batch_alter_table kopiert die
    # Daten in die neue Tabelle, und ungueltige Zeilen liessen schon das
    # Kopieren scheitern -- mit einem IntegrityError, der niemandem sagt, was
    # zu tun ist.
    for zeile in _altbestand_geradeziehen(verbindung):
        print(zeile)

    with op.batch_alter_table('tenant_cost_profiles', schema=None) as stapel:
        stapel.create_check_constraint(CONSTRAINT, _bedingung(GUELTIG))


def downgrade():
    # Zurueck geht nur die Bedingung. Was oben auf 'ignoriert' gesetzt wurde,
    # bleibt stehen: der alte Wert liess die Kostenart aus dem Blatt fallen,
    # ihn wiederherzustellen hiesse den Fehler wiederherstellen.
    with op.batch_alter_table('tenant_cost_profiles', schema=None) as stapel:
        stapel.drop_constraint(CONSTRAINT, type_='check')
