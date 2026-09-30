"""Die Anlage traegt die Angaben zur Warmwassertrennung (NK-050)

Revision ID: c1d47e93a806
Revises: f3a9c05e8d72
Create Date: 2026-09-22

Die neunte Wanderung. Sechs Spalten an ``heizungsanlagen`` und drei
Bedingungen darauf.

§ 9 HeizkostenV verlangt bei einer **verbundenen Anlage** -- einer, die
Heizung und Warmwasser zugleich versorgt --, dass die Kosten des Warmwassers
**vor** der Verteilung abgetrennt werden. Dafuer ist die Waermemenge Q zu
ermitteln, die auf das Warmwasser entfaellt, und zwar auf einem von drei
Wegen: mit einem Waermezaehler gemessen, sonst nach der Formel
``Q = 2,5 * V * (tw - 10)``, und wo auch das Volumen fehlt, ersatzweise mit
32 kWh je Quadratmeter Wohnflaeche. Aus Q wird der Brennstoffanteil
``B = Q / Hi`` und daraus der Bruchteil am Gesamtverbrauch der Anlage.

**Diese Angaben stehen an der Anlage** und nicht an einem Zaehler (D-50).
Ein Anlagenzaehler ohne Wohnung waere ein neuer Begriff: ``meters`` traegt
heute entweder eine Wohnung oder ist Hauptzaehler, und die Abfrage nach den
Waermezaehlern einer Anlage muesste ihn ueberall wieder ausnehmen. Die Wege
'formel' und 'ersatz' haben ausserdem gar keinen Zaehler, an dem sie haengen
koennten -- der Weg selbst waere dann heimatlos.

**Die Werte tragen keine Historie** (F-35). Sie gelten fuer den
Abrechnungszeitraum, der gerade gerechnet wird, und muessen zu jeder
Abrechnung neu gepflegt werden -- anders als der Verbrauchsanteil daneben,
der ein Stammdatum ist. Eine eigene Tabelle mit Zeitraum nach dem Vorbild
der Haushaltsgroesse waere richtiger; sie ist als Befund eingestellt und
nicht Teil dieser Karte.

**Am Altbestand wird nichts geaendert**, aus demselben Grund wie in
e5b2c74f9a16 und f3a9c05e8d72: eine geratene Warmwassermenge verschoebe die
naechste Abrechnung gegenueber der des Vorjahres, ohne dass jemand sie
angeordnet haette. Alle sechs Spalten sind deshalb ``nullable`` und bleiben
leer. Eine verbundene Anlage ohne diese Angaben rechnet weiter wie bisher --
alles als Heizkosten -- und der Rechenkern setzt einen Hinweis in die
Abrechnung, statt sie zu verweigern (dieselbe Linie wie D-48).

``batch_alter_table`` ist auf SQLite noetig: die Bedingungen kommen nur beim
Neubau der Tabelle mit. Dabei wird ``copy_from`` uebergeben, und das ist
keine Bequemlichkeit, sondern notwendig: SQLite gibt reflektierte
CHECK-Bedingungen nicht heraus, und ohne die mitgegebene Tabellendefinition
verloere der Neubau stillschweigend die drei Bedingungen aus e5b2c74f9a16 --
der Rahmen des § 7 Abs. 1 stuende danach nicht mehr in der Datenbank.
"""

from alembic import op
import sqlalchemy as sa

revision = 'c1d47e93a806'
down_revision = 'f3a9c05e8d72'
branch_labels = None
depends_on = None

CK_WEG = 'ck_heizungsanlagen_ww_weg'
CK_NUR_VERBUNDEN = 'ck_heizungsanlagen_ww_nur_verbunden'
CK_MENGEN = 'ck_heizungsanlagen_ww_mengen'


def _vorzustand():
    """Die Tabelle, wie e5b2c74f9a16 sie hinterlassen hat.

    Der Import steht in der Funktion und nicht oben: eine Wanderung laeuft
    auch aus ``scripts/`` heraus, und ein Importfehler auf Modulebene machte
    dort das ganze Verzeichnis unbrauchbar (Vorbild: 9c1f4a2b7d33).
    """
    from nebenkostenfix.heizung import (
        ANTEIL_MAX, ANTEIL_MIN, ANTEIL_VORGABE, HEIZUNG, VERSORGT)

    return sa.Table(
        'heizungsanlagen', sa.MetaData(),
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
        sa.CheckConstraint(
            'versorgt IN (%s)' % ', '.join(
                "'%s'" % w for w in sorted(VERSORGT)),
            name='ck_heizungsanlagen_versorgt'),
        sa.CheckConstraint(
            'verbrauchsanteil_prozent BETWEEN %d AND %d' % (
                ANTEIL_MIN, ANTEIL_MAX),
            name='ck_heizungsanlagen_verbrauchsanteil'),
        sa.CheckConstraint(
            'NOT sonderfall_70 OR verbrauchsanteil_prozent = %d' % ANTEIL_MAX,
            name='ck_heizungsanlagen_sonderfall'),
    )


def upgrade():
    from nebenkostenfix.heizung import VERBUNDEN, WW_KALTWASSER_GRAD, WW_WEGE

    with op.batch_alter_table(
            'heizungsanlagen', schema=None,
            copy_from=_vorzustand()) as stapel:
        stapel.add_column(sa.Column(
            'warmwasser_weg', sa.String(length=20), nullable=True))
        stapel.add_column(sa.Column(
            'warmwasser_kwh', sa.Numeric(precision=12, scale=3),
            nullable=True))
        stapel.add_column(sa.Column(
            'warmwasser_volumen_m3', sa.Numeric(precision=12, scale=3),
            nullable=True))
        stapel.add_column(sa.Column(
            'warmwasser_temperatur_c', sa.Numeric(precision=5, scale=1),
            nullable=True))
        stapel.add_column(sa.Column(
            'brennstoff_menge', sa.Numeric(precision=14, scale=3),
            nullable=True))
        stapel.add_column(sa.Column(
            'heizwert_kwh', sa.Numeric(precision=8, scale=3), nullable=True))
        # Welche Wege es gibt, steht in heizung.py und nirgends sonst --
        # dieselbe Linie wie beim Rahmen des § 7 Abs. 1 in e5b2c74f9a16.
        stapel.create_check_constraint(
            CK_WEG,
            'warmwasser_weg IS NULL OR warmwasser_weg IN (%s)' % ', '.join(
                "'%s'" % w for w in WW_WEGE))
        # Zu trennen gibt es nur bei einer verbundenen Anlage etwas.
        stapel.create_check_constraint(
            CK_NUR_VERBUNDEN,
            "warmwasser_weg IS NULL OR versorgt = '%s'" % VERBUNDEN)
        # Keine negativen oder leeren Mengen, und keine Warmwassertemperatur
        # unterhalb der angenommenen Kaltwassertemperatur: die Formel des
        # § 9 Abs. 2 Satz 4 gaebe dann eine negative Waermemenge her.
        stapel.create_check_constraint(
            CK_MENGEN,
            '(warmwasser_kwh IS NULL OR warmwasser_kwh > 0) AND '
            '(warmwasser_volumen_m3 IS NULL OR warmwasser_volumen_m3 > 0) AND '
            '(warmwasser_temperatur_c IS NULL OR '
            'warmwasser_temperatur_c > %d) AND '
            '(brennstoff_menge IS NULL OR brennstoff_menge > 0) AND '
            '(heizwert_kwh IS NULL OR heizwert_kwh > 0)'
            % WW_KALTWASSER_GRAD)


def downgrade():
    # Zurueck geht es vollstaendig: was an Trennungsangaben gepflegt wurde,
    # ist danach weg. Vor dieser Wanderung gibt es keinen Ort, an dem es
    # stehen koennte. Die Anlagen selbst bleiben, sie verlieren nur diese
    # sechs Felder.
    with op.batch_alter_table(
            'heizungsanlagen', schema=None,
            copy_from=_nachzustand()) as stapel:
        stapel.drop_constraint(CK_MENGEN, type_='check')
        stapel.drop_constraint(CK_NUR_VERBUNDEN, type_='check')
        stapel.drop_constraint(CK_WEG, type_='check')
        stapel.drop_column('heizwert_kwh')
        stapel.drop_column('brennstoff_menge')
        stapel.drop_column('warmwasser_temperatur_c')
        stapel.drop_column('warmwasser_volumen_m3')
        stapel.drop_column('warmwasser_kwh')
        stapel.drop_column('warmwasser_weg')


def _nachzustand():
    """Die Tabelle, wie ``upgrade()`` sie hinterlaesst.

    Aus demselben Grund noetig wie ``copy_from`` beim Hinweg: der Neubau
    beim Zurueckdrehen wuerde die drei Bedingungen aus e5b2c74f9a16 sonst
    fallen lassen, und die Datenbank stuende ohne den Rahmen des § 7 Abs. 1
    da -- an einer Stelle, an der niemand mehr nachsieht.
    """
    from nebenkostenfix.heizung import VERBUNDEN, WW_KALTWASSER_GRAD, WW_WEGE

    tabelle = _vorzustand()
    for spalte in (
            sa.Column('warmwasser_weg', sa.String(length=20), nullable=True),
            sa.Column('warmwasser_kwh', sa.Numeric(precision=12, scale=3),
                      nullable=True),
            sa.Column('warmwasser_volumen_m3',
                      sa.Numeric(precision=12, scale=3), nullable=True),
            sa.Column('warmwasser_temperatur_c',
                      sa.Numeric(precision=5, scale=1), nullable=True),
            sa.Column('brennstoff_menge', sa.Numeric(precision=14, scale=3),
                      nullable=True),
            sa.Column('heizwert_kwh', sa.Numeric(precision=8, scale=3),
                      nullable=True)):
        tabelle.append_column(spalte)
    tabelle.append_constraint(sa.CheckConstraint(
        'warmwasser_weg IS NULL OR warmwasser_weg IN (%s)' % ', '.join(
            "'%s'" % w for w in WW_WEGE), name=CK_WEG))
    tabelle.append_constraint(sa.CheckConstraint(
        "warmwasser_weg IS NULL OR versorgt = '%s'" % VERBUNDEN,
        name=CK_NUR_VERBUNDEN))
    tabelle.append_constraint(sa.CheckConstraint(
        '(warmwasser_kwh IS NULL OR warmwasser_kwh > 0) AND '
        '(warmwasser_volumen_m3 IS NULL OR warmwasser_volumen_m3 > 0) AND '
        '(warmwasser_temperatur_c IS NULL OR '
        'warmwasser_temperatur_c > %d) AND '
        '(brennstoff_menge IS NULL OR brennstoff_menge > 0) AND '
        '(heizwert_kwh IS NULL OR heizwert_kwh > 0)' % WW_KALTWASSER_GRAD,
        name=CK_MENGEN))
    return tabelle
