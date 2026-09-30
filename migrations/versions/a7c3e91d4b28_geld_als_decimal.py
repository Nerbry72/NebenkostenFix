"""Geldspalten von Float auf Numeric(12, 2) (NK-036)

Revision ID: a7c3e91d4b28
Revises: 9c1f4a2b7d33
Create Date: 2026-09-21

Die dritte Wanderung. Sie zieht die Zusage aus R-NUM-01 in das Schema nach:
``cost_invoices.amount`` und ``payments.amount`` sind Geld, also
``Numeric(12, 2)`` und in Python ``Decimal`` -- siehe ``geld.py``.

Zwei Schritte, und der zweite ist der eigentliche Grund:

1. **Typ tauschen.** ``batch_alter_table`` ist auf SQLite Pflicht, ein
   ``ALTER TABLE ... ALTER COLUMN`` kennt es nicht. Alembic baut die Tabelle
   neu, kopiert die Daten und tauscht sie.

2. **Die Betraege auf Cent gerade ruecken.** Der Altbestand wurde mit
   Fliesskomma gerechnet und gespeichert. Darin stehen Werte wie
   ``89.28999999999999``, weil 89,29 als float nicht existiert. Bliebe das so,
   hiesse die Spalte ``Numeric(12, 2)`` und enthielte Zahlen mit siebzehn
   Stellen -- eine Typzusage, die nur auf dem Papier steht. Gerundet wird mit
   ``geld.runde``, also demselben kaufmaennischen Weg wie im Rechenkern, nicht
   mit ``ROUND()`` von SQLite, dessen Ergebnis wieder an der binaeren
   Darstellung haengt.

Was das fuer Daten heisst: Ein Betrag aendert sich hoechstens um den halben
Cent, den die Fliesskommadarstellung vorher danebenlag. Ein Betrag, der schon
cent-genau war, bleibt Zeichen fuer Zeichen derselbe. Die Wanderung meldet,
wie viele Zeilen sie angefasst hat, und schweigt, wenn es keine gab.

``downgrade()`` gibt den Spaltentyp zurueck, die Rundung nicht: aus 89,29
laesst sich ``89.28999999999999`` nicht wiederherstellen, und niemand will
das. Der Weg zurueck fuehrt ueber die Sicherung, nicht ueber diese Funktion.
"""

from alembic import op
import sqlalchemy as sa

revision = 'a7c3e91d4b28'
down_revision = '9c1f4a2b7d33'
branch_labels = None
depends_on = None

#: Tabelle und Spalte jedes Euro-Betrags im Schema.
GELDSPALTEN = (
    ('cost_invoices', 'amount'),
    ('payments', 'amount'),
)


def _auf_cent_ruecken(verbindung, tabelle, spalte):
    """Schreibt jeden Betrag cent-genau zurueck. Gibt die Anzahl zurueck."""
    # Der Import steht hier und nicht oben: eine Wanderung laeuft auch aus
    # scripts/ heraus, und ein Importfehler auf Modulebene machte dort das
    # ganze Verzeichnis unbrauchbar (Vorbild: 9c1f4a2b7d33).
    from nebenkostenfix.geld import dec, runde

    zeilen = verbindung.execute(
        sa.text(f'SELECT id, {spalte} FROM {tabelle} WHERE {spalte} IS NOT NULL')
    ).all()
    geaendert = 0
    for kennung, roh in zeilen:
        vorher = dec(roh)
        nachher = runde(vorher)
        if vorher == nachher:
            continue
        verbindung.execute(
            sa.text(f'UPDATE {tabelle} SET {spalte} = :wert WHERE id = :id'),
            {'wert': str(nachher), 'id': kennung},
        )
        geaendert += 1
    return geaendert


def upgrade():
    verbindung = op.get_bind()

    for tabelle, spalte in GELDSPALTEN:
        with op.batch_alter_table(tabelle, schema=None) as stapel:
            stapel.alter_column(
                spalte,
                existing_type=sa.Float(),
                type_=sa.Numeric(precision=12, scale=2),
                existing_nullable=False,
            )

    gesamt = sum(
        _auf_cent_ruecken(verbindung, tabelle, spalte)
        for tabelle, spalte in GELDSPALTEN
    )
    if gesamt:
        print(f'NK-036: {gesamt} Betraege auf Cent gerade gerueckt.')


def downgrade():
    for tabelle, spalte in GELDSPALTEN:
        with op.batch_alter_table(tabelle, schema=None) as stapel:
            stapel.alter_column(
                spalte,
                existing_type=sa.Numeric(precision=12, scale=2),
                type_=sa.Float(),
                existing_nullable=False,
            )
