"""Die Fristen des § 556 Abs. 3 BGB an der Abrechnung (NK-054)

Revision ID: c7e1a9f30d42
Revises: b8e2f41a90c3
Create Date: 2026-09-22

Die elfte Wanderung: zwei Spalten, die ueber Fristen sprechen.

§ 556 Abs. 3 BGB: die Abrechnung ist dem Mieter spaetestens bis zum Ablauf
des zwoelften Monats nach Ende des Abrechnungszeitraums mitzuteilen; nach
Ablauf ist die Geltendmachung einer Nachforderung ausgeschlossen. Die
Datenbank kannte bisher keine Frist: die Abrechnung stand da, aber die
Antwort auf "wie lange gilt sie noch?" stand nirgends (R-FRIST-02,
IST-Stand "Fehlt").

``frist_ende`` traegt den letzten gueltigen Tag der Abrechnungsfrist --
AZ-Ende + 12 Monate, kalendergerecht nach § 188 Abs. 2 BGB (der 29.02. eines
Schaltjahres fuehrt zum 28.02. des Folgejahres). Er wird bei jeder Erzeugung
gesetzt; der Altbestand wird hier mit denselben Regeln nachgezogen, denn der
Zeitraum steht ja in jeder Zeile -- NULL waere eine Luecke, keine Angabe.
Deshalb NOT NULL.

``zugestellt_am`` traegt das Zustelldatum, wenn der Vermieter es nachtraegt
(R-FRIST-02, "Achtung Auslegung"): massgeblich ist der Zugang beim Mieter,
nicht das Erstellungsdatum, und nur der Vermieter weiss, wann zugriffen
wurde. Es bleibt optional -- eine Abrechnung ohne Zustelldatum ist
vollstaendig, nur ihre Einwendungsfrist ist noch nicht lesbar.

Die Frist selbst zu rechnen, ist Sache von ``frist.py``. Die Wanderung
importiert es nicht -- sie rechnet den Altbestand mit derselben Regel nach,
inline: ein Schaltjahr-Randfall, wenige Zeilen, und der Nachbau veraltet
hier sichtbar, statt eine spaeter umgebaute Fristregel stumm zu erben.
"""

from datetime import date

from alembic import op
import sqlalchemy as sa

revision = 'c7e1a9f30d42'
down_revision = 'b8e2f41a90c3'
branch_labels = None
depends_on = None


def _frist_ende(end_date):
    """AZ-Ende + 12 Monate als Kalendertag (§ 188 Abs. 2 BGB).

    Dasselbe wie frist.frist_ende, inline: der Tag des Folgejahres, der
    dem Ereignistag entspricht; hat der Zielmonat ihn nicht (29.02.),
    endet die Frist mit dem letzten Tag des Monats. Rohe Abfragen liefern
    das Datum als Zeichenkette -- auch das wird hier genommen.
    """
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    jahr, monat, tag = end_date.year + 1, end_date.month, end_date.day
    try:
        return date(jahr, monat, tag)
    except ValueError:
        import calendar
        return date(jahr, monat, calendar.monthrange(jahr, monat)[1])


def upgrade() -> None:
    # Der Umweg ueber nullable=True ist SQLite geschuldet: eine NOT-NULL-
    # Spalte ohne Vorgabewert liesse die Tabelle mit Bestand nicht anlegen.
    # Der Altbestand wird gleich nachgezogen, dann wird die Tuer zugemacht.
    with op.batch_alter_table('tenant_billing_reports') as batch:
        batch.add_column(sa.Column('frist_ende', sa.Date(), nullable=True))
        batch.add_column(sa.Column('zugestellt_am', sa.Date(), nullable=True))

    verbindung = op.get_bind()
    zeilen = verbindung.execute(sa.text(
        'SELECT id, end_date FROM tenant_billing_reports '
        'WHERE frist_ende IS NULL')).fetchall()
    for zeile in zeilen:
        verbindung.execute(sa.text(
            'UPDATE tenant_billing_reports SET frist_ende = :frist '
            'WHERE id = :id'), {'frist': _frist_ende(zeile.end_date),
                                'id': zeile.id})

    with op.batch_alter_table('tenant_billing_reports') as batch:
        batch.alter_column('frist_ende', existing_type=sa.Date(),
                           nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('tenant_billing_reports') as batch:
        batch.drop_column('zugestellt_am')
        batch.drop_column('frist_ende')
