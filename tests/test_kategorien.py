"""Kostenarten eindeutig machen (NK-095).

Geprueft wird gegen eine von Hand gebaute SQLite-Datei, nicht gegen die
``app_ctx``-Fixture. Der Grund ist der Gegenstand selbst: ``models.py`` traegt
seit dieser Karte ``unique=True``, also legt ``db.create_all()`` eine Datenbank
an, in der sich die Dublette gar nicht mehr erzeugen laesst. Ein Test, der den
Fehlerfall nicht herstellen kann, prueft nichts. Hier steht deshalb das alte
Schema ohne ``UNIQUE`` -- so sieht die Instanz aus, die aktualisiert wird.
"""

from __future__ import annotations

import sqlite3

import pytest

from nebenkostenfix.kategorien import (
    KategorieFehler,
    dubletten_finden,
    fastdubletten_finden,
    meldung_zu_dubletten,
    zusammenfuehren,
)

# Das Schema von vor NK-095: name ohne UNIQUE, dazu die vier Tabellen, die
# auf eine Kostenart zeigen. Nur die Spalten, die zusammenfuehren() anfasst.
SCHEMA_ALT = """
CREATE TABLE cost_categories (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    allocation_method VARCHAR(50) NOT NULL DEFAULT 'PER_SQM',
    requires_meter BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE cost_invoices (id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL);
CREATE TABLE meters (id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL);
CREATE TABLE tenant_cost_profiles (
    id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, category_id INTEGER NOT NULL
);
CREATE TABLE billing_report_categories (
    id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL
);
"""


@pytest.fixture
def db():
    """Eine leere Datenbank im alten Schema, im Arbeitsspeicher."""
    verbindung = sqlite3.connect(':memory:')
    verbindung.executescript(SCHEMA_ALT)
    yield verbindung
    verbindung.close()


def kostenart(verbindung, name: str) -> int:
    zeiger = verbindung.execute(
        'INSERT INTO cost_categories (name) VALUES (?)', (name,))
    return zeiger.lastrowid


def anhaengen(verbindung, tabelle: str, kategorie: int, **weitere) -> int:
    spalten = ['category_id', *weitere]
    werte = [kategorie, *weitere.values()]
    zeiger = verbindung.execute(
        f'INSERT INTO {tabelle} ({", ".join(spalten)}) '
        f'VALUES ({", ".join("?" * len(spalten))})',
        werte,
    )
    return zeiger.lastrowid


# --- finden ---------------------------------------------------------------

def test_saubere_datenbank_hat_keine_dubletten(db):
    for name in ('Heizung', 'Wasser', 'Muell'):
        kostenart(db, name)
    assert dubletten_finden(db) == {}


def test_dubletten_kommen_mit_allen_ids(db):
    erste = kostenart(db, 'Heizung')
    kostenart(db, 'Wasser')
    zweite = kostenart(db, 'Heizung')
    dritte = kostenart(db, 'Heizung')

    assert dubletten_finden(db) == {'Heizung': [erste, zweite, dritte]}


def test_leere_datenbank_ist_kein_sonderfall(db):
    assert dubletten_finden(db) == {}
    assert fastdubletten_finden(db) == {}


def test_fastdubletten_melden_schreibweise_aber_keine_dublette(db):
    kostenart(db, 'Heizung')
    kostenart(db, 'heizung')
    kostenart(db, ' Heizung ')

    # Exakt verglichen sind das drei verschiedene Namen -- UNIQUE laesst sie zu.
    assert dubletten_finden(db) == {}
    fast = fastdubletten_finden(db)
    assert set(fast) == {'heizung'}
    assert sorted(fast['heizung']) == [' Heizung ', 'Heizung', 'heizung']


def test_gleiche_namen_sind_keine_fastdublette(db):
    """Wer schon exakt doppelt ist, soll nicht zweimal gemeldet werden."""
    kostenart(db, 'Heizung')
    kostenart(db, 'Heizung')

    assert dubletten_finden(db)
    assert fastdubletten_finden(db) == {}


# --- die Meldung ----------------------------------------------------------

def test_meldung_nennt_namen_ids_und_den_weg_der_funktioniert(db):
    erste = kostenart(db, 'Heizung')
    zweite = kostenart(db, 'Heizung')

    text = meldung_zu_dubletten(dubletten_finden(db))

    assert 'Heizung' in text
    assert str(erste) in text and str(zweite) in text
    # Der Skriptweg, nicht der flask-Weg: waehrend die Wanderung abbricht, ist
    # flask nicht erreichbar (F-16). Ein Verweis darauf waere eine Sackgasse.
    assert 'scripts/kostenarten.py' in text
    assert 'flask kategorien' not in text
    # Und ein Hinweis auf die Sicherung, bevor jemand etwas loescht.
    assert 'sichern' in text


# --- zusammenfuehren ------------------------------------------------------

def test_zusammenfuehren_haengt_alle_vier_tabellen_um(db):
    behalten = kostenart(db, 'Heizung')
    weg = kostenart(db, 'Heizung')
    unbeteiligt = kostenart(db, 'Wasser')

    anhaengen(db, 'cost_invoices', weg)
    anhaengen(db, 'meters', weg)
    anhaengen(db, 'tenant_cost_profiles', weg, tenant_id=1)
    anhaengen(db, 'billing_report_categories', weg)
    fremde = anhaengen(db, 'cost_invoices', unbeteiligt)

    bilanz = zusammenfuehren(db, 'Heizung')

    assert bilanz['Behalten als id'] == behalten
    assert bilanz['Gelöschte Kostenarten'] == 1
    for beschriftung in ('Rechnungen', 'Zaehler', 'Mieterprofile',
                         'Positionen in Abrechnungen'):
        assert bilanz[beschriftung] == 1, beschriftung

    # Nichts haengt mehr an der geloeschten id, und die Kostenart ist weg.
    for tabelle, _ in (('cost_invoices', ''), ('meters', ''),
                       ('tenant_cost_profiles', ''),
                       ('billing_report_categories', '')):
        rest = db.execute(
            f'SELECT COUNT(*) FROM {tabelle} WHERE category_id = ?', (weg,)
        ).fetchone()[0]
        assert rest == 0, tabelle
    assert db.execute('SELECT COUNT(*) FROM cost_categories').fetchone()[0] == 2

    # Die fremde Kostenart und ihre Rechnung sind unberuehrt.
    assert db.execute(
        'SELECT category_id FROM cost_invoices WHERE id = ?', (fremde,)
    ).fetchone()[0] == unbeteiligt


def test_zusammenfuehren_entdoppelt_die_mieterprofile(db):
    """Derselbe Mieter haengt an beiden Kostenarten -- danach nur noch einmal.

    Ohne diesen Schritt stuende die Kostenart zweimal im Profil desselben
    Mieters, und die Oberflaeche zeigte sie doppelt an.
    """
    behalten = kostenart(db, 'Heizung')
    weg = kostenart(db, 'Heizung')
    altes = anhaengen(db, 'tenant_cost_profiles', behalten, tenant_id=7)
    anhaengen(db, 'tenant_cost_profiles', weg, tenant_id=7)
    anderer = anhaengen(db, 'tenant_cost_profiles', weg, tenant_id=8)

    bilanz = zusammenfuehren(db, 'Heizung')

    assert bilanz['Entdoppelte Mieterprofile'] == 1
    uebrig = db.execute(
        'SELECT id, tenant_id FROM tenant_cost_profiles ORDER BY id').fetchall()
    # Mieter 7 einmal (das aeltere Profil), Mieter 8 einmal.
    assert uebrig == [(altes, 7), (anderer, 8)]


def test_zusammenfuehren_raeumt_nicht_bei_fremden_kostenarten_auf(db):
    """Der Fall, der den Fehler im ersten Entwurf gefunden hat.

    Dort stand ein ``DELETE ... WHERE id NOT IN (SELECT MIN(id) ... GROUP BY
    tenant_id, category_id)`` ohne Einschraenkung auf die betroffene
    Kostenart. Das haette hier die doppelte Zeile bei "Wasser" gleich mit
    geloescht -- eine Aenderung an Daten, um die niemand gebeten hat.
    """
    kostenart(db, 'Heizung')
    kostenart(db, 'Heizung')
    wasser = kostenart(db, 'Wasser')
    doppelt_a = anhaengen(db, 'tenant_cost_profiles', wasser, tenant_id=3)
    doppelt_b = anhaengen(db, 'tenant_cost_profiles', wasser, tenant_id=3)

    zusammenfuehren(db, 'Heizung')

    bei_wasser = db.execute(
        'SELECT id FROM tenant_cost_profiles WHERE category_id = ? ORDER BY id',
        (wasser,),
    ).fetchall()
    assert [z[0] for z in bei_wasser] == [doppelt_a, doppelt_b]


def test_drei_gleiche_ziehen_alle_auf_die_kleinste_id(db):
    behalten = kostenart(db, 'Heizung')
    zweite = kostenart(db, 'Heizung')
    dritte = kostenart(db, 'Heizung')
    anhaengen(db, 'cost_invoices', zweite)
    anhaengen(db, 'cost_invoices', dritte)

    bilanz = zusammenfuehren(db, 'Heizung')

    assert bilanz['Gelöschte Kostenarten'] == 2
    assert bilanz['Rechnungen'] == 2
    ziele = {z[0] for z in db.execute('SELECT category_id FROM cost_invoices')}
    assert ziele == {behalten}
    assert dubletten_finden(db) == {}


def test_zusammenfuehren_ohne_dublette_bricht_ab(db):
    kostenart(db, 'Heizung')

    with pytest.raises(KategorieFehler) as fehler:
        zusammenfuehren(db, 'Heizung')
    assert 'Heizung' in str(fehler.value)


def test_zusammenfuehren_eines_unbekannten_namens_bricht_ab(db):
    kostenart(db, 'Heizung')

    with pytest.raises(KategorieFehler):
        zusammenfuehren(db, 'Gibtsnicht')


def test_zusammenfuehren_committet_nicht_von_sich_aus(db):
    """Der Aufrufer entscheidet. Bei einem Fehler mittendrin soll nichts
    halb umgehaengt stehenbleiben."""
    kostenart(db, 'Heizung')
    kostenart(db, 'Heizung')
    db.commit()

    zusammenfuehren(db, 'Heizung')
    db.rollback()

    assert len(dubletten_finden(db)['Heizung']) == 2


# --- das CLI --------------------------------------------------------------
#
# Bis hierher lief alles direkt gegen sqlite3. Das CLI ist aber der Weg, den
# der Vermieter im Normalfall nimmt -- ungeprueft waere ausgerechnet die
# Bedienoberflaeche der Karte. Geprueft wird gegen eine eigene Flask-App mit
# dem alten Schema: die App aus app.py haengt an der Testdatenbank aus
# conftest.py, und die kennt seit NK-095 kein Schema mehr, in dem sich eine
# Dublette ueberhaupt anlegen liesse.

@pytest.fixture
def cli(tmp_path):
    """Eine kleine App mit dem alten Schema und registriertem kategorien-CLI."""
    from flask import Flask

    from nebenkostenfix.kategorien import init_kategorien
    from nebenkostenfix.models import db as modelldb

    datei = tmp_path / 'alt.db'
    verbindung = sqlite3.connect(datei)
    verbindung.executescript(SCHEMA_ALT)
    verbindung.commit()

    anwendung = Flask('kategorien_test')
    anwendung.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{datei}'
    anwendung.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    modelldb.init_app(anwendung)
    init_kategorien(anwendung)

    yield anwendung, verbindung
    verbindung.close()


def test_cli_meldet_eine_saubere_datenbank(cli):
    anwendung, verbindung = cli
    kostenart(verbindung, 'Heizung')
    verbindung.commit()

    ergebnis = anwendung.test_cli_runner().invoke(args=['kategorien', 'dubletten'])

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Keine gleichnamigen Kostenarten' in ergebnis.output


def test_cli_zeigt_dubletten_und_fastdubletten(cli):
    anwendung, verbindung = cli
    kostenart(verbindung, 'Heizung')
    kostenart(verbindung, 'Heizung')
    kostenart(verbindung, 'Wasser')
    kostenart(verbindung, 'wasser')
    verbindung.commit()

    ergebnis = anwendung.test_cli_runner().invoke(args=['kategorien', 'dubletten'])

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Heizung' in ergebnis.output
    assert 'Schreibweise' in ergebnis.output
    assert '"Wasser" / "wasser"' in ergebnis.output


def test_cli_fragt_vor_dem_zusammenfuehren_nach(cli):
    """Ohne --ja und ohne Zustimmung wird nichts angefasst."""
    anwendung, verbindung = cli
    kostenart(verbindung, 'Heizung')
    kostenart(verbindung, 'Heizung')
    verbindung.commit()

    ergebnis = anwendung.test_cli_runner().invoke(
        args=['kategorien', 'zusammenfuehren', 'Heizung'], input='n\n')

    assert ergebnis.exit_code != 0
    assert 'Sicherung' in ergebnis.output
    assert len(dubletten_finden(verbindung)['Heizung']) == 2


def test_cli_fuehrt_mit_ja_zusammen_und_committet(cli):
    anwendung, verbindung = cli
    behalten = kostenart(verbindung, 'Heizung')
    weg = kostenart(verbindung, 'Heizung')
    anhaengen(verbindung, 'cost_invoices', weg)
    verbindung.commit()

    ergebnis = anwendung.test_cli_runner().invoke(
        args=['kategorien', 'zusammenfuehren', 'Heizung', '--ja'])

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Rechnungen: 1' in ergebnis.output
    # Eine zweite, frische Verbindung -- nur so ist bewiesen, dass committet wurde.
    nachher = sqlite3.connect(verbindung.execute(
        'PRAGMA database_list').fetchone()[2])
    try:
        assert dubletten_finden(nachher) == {}
        assert nachher.execute(
            'SELECT category_id FROM cost_invoices').fetchone()[0] == behalten
    finally:
        nachher.close()


def test_cli_meldet_sauber_wenn_es_nichts_zusammenzufuehren_gibt(cli):
    anwendung, verbindung = cli
    kostenart(verbindung, 'Heizung')
    verbindung.commit()

    ergebnis = anwendung.test_cli_runner().invoke(
        args=['kategorien', 'zusammenfuehren', 'Heizung', '--ja'])

    assert ergebnis.exit_code != 0
    assert 'keine zwei Kostenarten' in ergebnis.output


# --- das Notfallskript ----------------------------------------------------
#
# scripts/kostenarten.py steht in coverage-omit und wird von keinem der Tests
# oben beruehrt. Es ist aber das Werkzeug fuer den Fall, dass die Anwendung
# nicht mehr hochkommt -- also genau das, dessen Defekt erst im Notfall
# auffaellt. Es laeuft hier als Unterprozess, so wie ein Mensch es aufruft.

def _skript(*argumente, datei, erwartet=0):
    import os
    import subprocess
    import sys
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1]
    ergebnis = subprocess.run(
        [sys.executable, str(wurzel / 'scripts' / 'kostenarten.py'), *argumente],
        cwd=str(wurzel),
        # Windows: ohne SYSTEMROOT kein Winsock, ohne PYTHONIOENCODING
        # schreibt das Kind in der ANSI-Codepage.
        env={'PATH': '/usr/bin:/bin', 'DATABASE_URL': f'sqlite:///{datei}',
             'PYTHONIOENCODING': 'utf-8',
             **{k: v for k, v in os.environ.items() if k == 'SYSTEMROOT'}},
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=60,
    )
    assert ergebnis.returncode == erwartet, (
        f'Exit {ergebnis.returncode}, erwartet {erwartet}:\n'
        f'{ergebnis.stdout}\n{ergebnis.stderr}'
    )
    return ergebnis.stdout


@pytest.fixture
def datei_db(tmp_path):
    """Eine Datei im alten Schema -- das Skript braucht einen Pfad, kein :memory:."""
    datei = tmp_path / 'notfall.db'
    verbindung = sqlite3.connect(datei)
    verbindung.executescript(SCHEMA_ALT)
    verbindung.commit()
    yield datei, verbindung
    verbindung.close()


def test_skript_meldet_dubletten_mit_exitcode_1(datei_db):
    """Der Exit-Code trennt die Faelle: 1 heisst "da ist etwas"."""
    datei, verbindung = datei_db
    kostenart(verbindung, 'Heizung')
    kostenart(verbindung, 'Heizung')
    verbindung.commit()

    ausgabe = _skript('dubletten', datei=datei, erwartet=1)
    assert 'Heizung' in ausgabe


def test_skript_meldet_saubere_datenbank_mit_exitcode_0(datei_db):
    datei, verbindung = datei_db
    kostenart(verbindung, 'Heizung')
    verbindung.commit()

    ausgabe = _skript('dubletten', datei=datei)
    assert 'Keine gleichnamigen' in ausgabe


def test_skript_fuehrt_zusammen_und_committet(datei_db):
    datei, verbindung = datei_db
    behalten = kostenart(verbindung, 'Heizung')
    weg = kostenart(verbindung, 'Heizung')
    anhaengen(verbindung, 'meters', weg)
    verbindung.commit()

    ausgabe = _skript('zusammenfuehren', 'Heizung', datei=datei)
    assert 'Zaehler: 1' in ausgabe

    pruef = sqlite3.connect(datei)
    try:
        assert dubletten_finden(pruef) == {}
        assert pruef.execute('SELECT category_id FROM meters').fetchone()[0] == behalten
    finally:
        pruef.close()


def test_skript_legt_eine_kopie_an(datei_db):
    """sichern ist der erste Befehl in jeder Anleitung -- er muss wirklich kopieren."""
    datei, verbindung = datei_db
    kostenart(verbindung, 'Heizung')
    verbindung.commit()

    ausgabe = _skript('sichern', datei=datei)

    kopien = sorted(datei.parent.glob(f'{datei.name}.vor-kostenarten-*'))
    assert len(kopien) == 1, ausgabe
    assert kopien[0].read_bytes() == datei.read_bytes()


def test_skript_ohne_namen_beim_zusammenfuehren(datei_db):
    datei, _ = datei_db
    ausgabe = _skript('zusammenfuehren', datei=datei, erwartet=2)
    assert 'braucht den Namen' in ausgabe


def test_skript_meldet_eine_fehlende_datei(tmp_path):
    ausgabe = _skript('dubletten', datei=tmp_path / 'gibtsnicht.db', erwartet=1)
    assert 'nicht gefunden' in ausgabe
