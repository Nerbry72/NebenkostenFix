"""Schemawanderungen (NK-024).

Die Karte hat vier Zusagen, und jede steht hier als Test:

1. ``migrations/`` mit Alembic, Basisrevision entspricht ``models.py``.
2. Eine bestehende Datenbank wird gestempelt, nicht angetastet.
3. Der Autostart wandert beim Hochfahren.
4. ``db.create_all()`` ist aus ``app.py`` raus.

Die ersten drei laufen in Unterprozessen. Der Grund: ``schema_aktualisieren()``
haengt am Import von ``app``, und ``DATABASE_URL`` wird beim Import gelesen.
Im laufenden pytest-Prozess ist ``app`` laengst importiert und zeigt auf die
Testdatenbank aus ``conftest.py``. Ein frischer Prozess je Fall ist der
einzige Weg, den echten Startvorgang gegen eine eigene Datei zu sehen.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]

BASISREVISION = "63738d5329b4"
# Der Kopf der Kette, also der Stand, auf dem eine Datenbank nach dem Start
# steht. Er wandert mit jeder neuen Revision; die Basis nie (NK-095).
# NK-058: ``d4e6f8a90b12`` fuehrt ``rechnungsdatum`` an der Rechnung ein
# (R-DOC-01 Punkt 8: Datum in der Belegliste).
# NK-061: ``b8f2c61a4e07`` legt die Versionstabelle finalisierter
# Abrechnungen an (R-DOC-02: Schnappschuss, Software- und Regelstand).
# NK-064: ``e9d3c72b5f81`` legt die Vorlagentabelle des Anschreibens an
# (je Objekt, ohne Backfill -- der Vorgabetext lebt als Konstante).
# NK-153: ``c7d8e9f0a1b2`` fuegt ``tenants.gesperrt_bis`` hinzu (D-89).
# NK-188: ``a4d7e1c9b3f5`` fuegt ``properties.abrechnungsjahr_beginn`` hinzu (D-114).
# F-137: ``e3c5a7f9b1d2`` fuegt ``cost_invoices.grundpreis`` hinzu.
# NK-217: ``670627ef0699`` fuegt ``tenant_billing_reports.regelstand_geprueft`` hinzu.
KOPFREVISION = "670627ef0699"


def _umgebung(dbdatei: Path, tmp_path: Path) -> dict:
    """Umgebung eines Unterprozesses: eigene Datenbank, eigene Verzeichnisse."""
    umgebung = dict(os.environ)
    umgebung.update(
        {
            "DATABASE_URL": f"sqlite:///{dbdatei}",
            # NK-081: die Sicherung vor der Wanderung landet im Datenordner
            # -- je Test ein eigener, nicht der gemeinsame aus conftest.
            "DATA_DIR": str(tmp_path),
            "NAS_MOUNT_PATH": str(tmp_path / "nas"),
            "LOCAL_PDF_PATH": str(tmp_path / "pdf"),
            "LOCAL_TEMP_PATH": str(tmp_path / "temp"),
            "SECRET_KEY": "nkfix-pytest-secret-key-nur-fuer-tests",
        }
    )
    umgebung.pop("ENABLE_DEBUG_RESET", None)
    return umgebung


def _lauf(code: str, dbdatei: Path, tmp_path: Path) -> dict:
    """Fuehrt ``code`` in einem eigenen Python gegen ``dbdatei`` aus."""
    ergebnis = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(WURZEL),
        env=_umgebung(dbdatei, tmp_path),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert ergebnis.returncode == 0, (
        f"Unterprozess brach ab:\n{ergebnis.stdout}\n{ergebnis.stderr}"
    )
    return json.loads(ergebnis.stdout.strip().splitlines()[-1])


# Startet die Anwendung wie gunicorn es tut und meldet, was danach dasteht.
CODE_START = """
import json
from sqlalchemy import inspect, text
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    tabellen = sorted(inspect(db.engine).get_table_names())
    stand = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    haeuser = [z[0] for z in db.session.execute(text("SELECT name FROM properties")).all()]
    kategorien = db.session.execute(text("SELECT COUNT(*) FROM cost_categories")).scalar()
    doppelte = db.session.execute(text(
        "SELECT COUNT(*) FROM (SELECT name FROM cost_categories"
        " GROUP BY name HAVING COUNT(*) > 1)"
    )).scalar()

print(json.dumps({"tabellen": tabellen, "stand": stand, "haeuser": haeuser,
                  "kategorien": kategorien, "doppelte_kategorien": doppelte}))
"""

# Baut eine Datenbank aus der Zeit vor Alembic: alle Tabellen, echte Zeile
# drin, keine alembic_version.
#
# Das Schema kommt aus der Basisrevision, nicht aus models.py (geaendert in
# NK-044). models.py ist inzwischen weitergezogen: es aus models.py
# aufzubauen gaebe einer angeblich alten Instanz Spalten, die es damals noch
# gar nicht gab -- und die Wanderung, die eine davon anlegt, liefe in
# "duplicate column name". Der Umweg ueber upgrade() und downgrade() bleibt
# richtig, auch wenn morgen die sechste Revision dazukommt.
CODE_ALTBESTAND = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="63738d5329b4")
    db.session.execute(text(
        "INSERT INTO properties (name, is_standalone) VALUES ('Musterhaus', 0)"))
    # Und den Stempel wieder weg: eine Instanz aus der Zeit vor Alembic hat
    # keine alembic_version, genau darum geht es im Test.
    db.session.execute(text("DROP TABLE alembic_version"))
    db.session.commit()

print(json.dumps({"angelegt": True}))
"""

# Vergleicht das gewanderte Schema mit models.py.
CODE_ABGLEICH = """
import json
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    with db.engine.connect() as verbindung:
        unterschiede = compare_metadata(
            MigrationContext.configure(verbindung), db.metadata
        )

print(json.dumps({"unterschiede": [repr(u) for u in unterschiede]}))
"""


def test_leere_datenbank_wird_von_der_wanderung_aufgebaut(tmp_path):
    """Erster Start beim Betreiber: nichts da, danach alles da."""
    datei = tmp_path / "neu.db"
    assert not datei.exists()

    stand = _lauf(CODE_START, datei, tmp_path)

    assert "alembic_version" in stand["tabellen"]
    assert stand["stand"] == KOPFREVISION
    # Stichproben aus allen Ecken des Schemas, nicht nur die erste Tabelle.
    for tabelle in ("users", "properties", "apartments", "tenants",
                    "cost_invoices", "meter_readings", "payments"):
        assert tabelle in stand["tabellen"], tabelle
    # seed_database() laeuft danach weiter wie bisher.
    assert stand["kategorien"] > 0


def test_bestehende_datenbank_wird_nur_gestempelt(tmp_path):
    """Kriterium 2 der Karte, der Fall, auf den es ankommt.

    Eine Instanz, die seit Monaten laeuft, hat alle Tabellen und keine
    alembic_version. Wuerde der Autostart hier die Basisrevision ausfuehren,
    liefe er in "table already exists" und die Instanz kaeme nicht mehr hoch.
    Wuerde er die Datenbank neu aufbauen, waere die Abrechnung des Betreibers
    weg. Richtig ist: stempeln und die Finger von den Daten lassen.
    """
    datei = tmp_path / "altbestand.db"
    _lauf(CODE_ALTBESTAND, datei, tmp_path)
    groesse_vorher = datei.stat().st_size

    stand = _lauf(CODE_START, datei, tmp_path)

    assert stand["stand"] == KOPFREVISION
    assert stand["haeuser"] == ["Musterhaus"]
    assert groesse_vorher > 0


def test_vor_der_wanderung_wird_gesichert(tmp_path):
    """NK-081: ein Update bringt neue Revisionen, der Start baut um -- vorher
    liegt der alte Stand als Sicherung in der Liste. Eine neue Datenbank
    und ein zweiter Start ohne neue Revision sichern nichts."""
    datei = tmp_path / "vor-update.db"
    _lauf(CODE_ALTBESTAND, datei, tmp_path)
    sicherungen = tmp_path / "backups"
    assert not list(sicherungen.glob("sicherung-vor-update-*"))

    _lauf(CODE_START, datei, tmp_path)
    archive = sorted(sicherungen.glob("sicherung-vor-update-*.nkfix"))
    assert len(archive) == 1

    from nebenkostenfix import backup
    manifest = backup.manifest_lesen(archive[0])
    assert manifest["alembic_revision"] == "63738d5329b4"

    _lauf(CODE_START, datei, tmp_path)
    assert len(list(sicherungen.glob("sicherung-vor-update-*"))) == 1


CODE_EINSPIELEN_ALT = """
import json, os
from pathlib import Path
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix import backup
from nebenkostenfix.models import Tenant, db

ordner = Path(os.environ['DATA_DIR']) / 'probe-sicherungen'
with anwendung.app.app_context():
    downgrade(revision="63738d5329b4")
    db.session.execute(text(
        "INSERT INTO properties (name, is_standalone) VALUES ('Musterhaus', 0)"))
    db.session.commit()
    archiv = backup.sicherung_erstellen(anwendung.app, ordner)
    upgrade()
    db.session.execute(text(
        "INSERT INTO properties (name, is_standalone) VALUES ('Nach dem Update', 0)"))
    db.session.commit()
    bericht = backup.sicherung_einspielen(anwendung.app, archiv)
    stand = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    Tenant.query.all()   # braucht Spalten, die es in der Basisrevision nicht gibt
    haeuser = [z[0] for z in db.session.execute(text("SELECT name FROM properties")).all()]
print(json.dumps({"stand": stand, "haeuser": haeuser, "bericht": bericht}))
"""


def test_einspielen_einer_alten_sicherung_wandert_das_schema(tmp_path):
    """NK-165 (F-86): ein Archiv auf der Basisrevision -- etwa die Sicherung
    vor einem Update -- laesst die laufende Anwendung nicht auf dem alten
    Schema zurueck."""
    ergebnis = _lauf(CODE_EINSPIELEN_ALT, tmp_path / "alt.db", tmp_path)
    assert ergebnis["bericht"]["alembic_revision"] == "63738d5329b4"
    assert ergebnis["stand"] == KOPFREVISION
    assert ergebnis["bericht"]["schemastand_nachher"] == KOPFREVISION
    assert ergebnis["haeuser"] == ["Musterhaus"]


def test_zweiter_start_wandert_nicht_noch_einmal(tmp_path):
    """Jeder Neustart laeuft durch dieselbe Funktion, auch der hundertste."""
    datei = tmp_path / "wiederholt.db"
    erster = _lauf(CODE_START, datei, tmp_path)
    zweiter = _lauf(CODE_START, datei, tmp_path)

    assert erster["stand"] == zweiter["stand"] == KOPFREVISION
    assert erster["tabellen"] == zweiter["tabellen"]
    # seed_database() legt die Kategorien nicht ein zweites Mal an.
    assert erster["kategorien"] == zweiter["kategorien"]


def test_zwei_starts_gleichzeitig_bauen_die_datenbank_nur_einmal(tmp_path):
    """gunicorn startet mit mehreren Arbeitern, alle importieren app.py.

    Ohne Sperre wandern sie gleichzeitig (auf SQLite "database is locked" oder
    schlimmer) und saeen gleichzeitig: seed_database() liest erst und schreibt
    dann, cost_categories.name hat keine Eindeutigkeit. Mit vier Arbeitern
    standen dort neun Kategorien statt acht. Hier zwei Prozesse ohne Vorsprung.

    Seit NK-044 sind es siebzehn: die Nummern aus § 2 BetrKV.
    """
    datei = tmp_path / "gleichzeitig.db"
    umgebung = _umgebung(datei, tmp_path)

    prozesse = [
        subprocess.Popen(
            [sys.executable, "-c", CODE_START],
            cwd=str(WURZEL),
            env=umgebung,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    ausgaben = [p.communicate(timeout=180) for p in prozesse]

    for prozess, (aus, fehler) in zip(prozesse, ausgaben):
        assert prozess.returncode == 0, f"{aus}\n{fehler}"

    letzter = json.loads(ausgaben[-1][0].strip().splitlines()[-1])
    assert letzter["stand"] == KOPFREVISION
    # 17 Nummern, die Nr. 3 zweimal (NK-117, D-72).
    assert letzter["kategorien"] == 18
    assert letzter["doppelte_kategorien"] == 0


def test_basisrevision_deckt_models_py_ab(tmp_path):
    """Abstandswaechter: gewandertes Schema gegen models.py.

    conftest.py baut die Testdatenbank aus Geschwindigkeitsgruenden weiter mit
    db.create_all(). Das ist nur dann kein Risiko, wenn beide Wege dieselben
    Tabellen ergeben. Genau das wird hier gemessen, und der Test faellt auch
    dann um, wenn jemand spaeter models.py aendert und die Wanderung vergisst.
    """
    datei = tmp_path / "abgleich.db"
    ergebnis = _lauf(CODE_ABGLEICH, datei, tmp_path)

    # alembic_version steht in keiner models.py und taucht als "zuviel" auf.
    unterschiede = [u for u in ergebnis["unterschiede"] if "alembic_version" not in u]
    assert unterschiede == [], "Schema und models.py laufen auseinander"


def test_app_py_legt_keine_tabellen_mehr_blind_an():
    """Kriterium 4: kein create_all() mehr in app.py.

    Gesucht wird der Aufruf im Syntaxbaum, nicht die Zeichenkette: der
    Kommentar, der erklaert warum das Ding raus ist, darf stehenbleiben.
    """
    baum = ast.parse((WURZEL / "app.py").read_text(encoding="utf-8"))
    aufrufe = [
        knoten
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Call)
        and isinstance(knoten.func, ast.Attribute)
        and knoten.func.attr == "create_all"
    ]
    assert aufrufe == [], f"create_all() in app.py, Zeile {[k.lineno for k in aufrufe]}"


def test_die_basisrevision_wird_nicht_veraendert():
    """Die Datei der Basisrevision hat keine Vorgaengerin und behaelt ihre Nummer.

    Wer die Nummer aendert, macht jede gestempelte Datenbank beim Betreiber
    unlesbar fuer Alembic. app.BASISREVISION und die Datei muessen deshalb
    zusammenpassen.
    """
    treffer = sorted((WURZEL / "migrations" / "versions").glob("*.py"))
    basis = [d for d in treffer if d.name.startswith(BASISREVISION)]
    assert len(basis) == 1, f"Basisrevision {BASISREVISION} nicht gefunden"

    quelle = basis[0].read_text(encoding="utf-8")
    assert f"revision = '{BASISREVISION}'" in quelle
    assert "down_revision = None" in quelle

    import app as anwendung

    assert anwendung.BASISREVISION == BASISREVISION


def test_die_kette_hat_genau_einen_kopf():
    """Kein Ast in der Wanderungskette, und KOPFREVISION zeigt darauf.

    Zwei Revisionen mit derselben ``down_revision`` sind ein Ast. Alembic
    weigert sich dann zu wandern ("Multiple head revisions are present"), und
    zwar erst beim Hochfahren beim Betreiber. Hier faellt es beim Testlauf auf.
    """
    verzeichnis = WURZEL / "migrations" / "versions"
    revisionen = {}
    for datei in sorted(verzeichnis.glob("*.py")):
        quelle = datei.read_text(encoding="utf-8")
        baum = ast.parse(quelle)
        werte = {}
        for knoten in baum.body:
            if isinstance(knoten, ast.Assign) and len(knoten.targets) == 1:
                ziel = knoten.targets[0]
                if isinstance(ziel, ast.Name) and ziel.id in ("revision", "down_revision"):
                    werte[ziel.id] = ast.literal_eval(knoten.value)
        if "revision" in werte:
            revisionen[werte["revision"]] = werte.get("down_revision")

    vorgaenger = {v for v in revisionen.values() if v is not None}
    koepfe = sorted(set(revisionen) - vorgaenger)
    assert koepfe == [KOPFREVISION], f"Koepfe: {koepfe}"

    wurzeln = sorted(r for r, d in revisionen.items() if d is None)
    assert wurzeln == [BASISREVISION], f"Wurzeln: {wurzeln}"


def test_die_neue_revision_setzt_das_unique(tmp_path):
    """Nach dem Start traegt cost_categories.name eine eindeutige Bedingung.

    Gemessen wird an der Datenbank, nicht an models.py: eine Zusage im Modell,
    die im Schema fehlt, ist genau der Fall, den NK-095 schliessen soll.
    """
    datei = tmp_path / "unique.db"
    _lauf(CODE_START, datei, tmp_path)

    import sqlite3

    verbindung = sqlite3.connect(datei)
    try:
        indizes = verbindung.execute(
            "PRAGMA index_list('cost_categories')").fetchall()
        eindeutige_spalten = set()
        for zeile in indizes:
            name, eindeutig = zeile[1], zeile[2]
            if eindeutig:
                eindeutige_spalten.update(
                    s[2] for s in verbindung.execute(
                        f"PRAGMA index_info('{name}')").fetchall()
                )
        assert "name" in eindeutige_spalten, f"Indizes: {indizes}"

        # Und die Bedingung greift auch wirklich.
        import pytest as _pytest
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "INSERT INTO cost_categories"
                " (name, allocation_method, requires_meter, betrkv_nr)"
                " SELECT name, allocation_method, requires_meter, betrkv_nr"
                " FROM cost_categories LIMIT 1"
            )
    finally:
        verbindung.close()


# Faehrt eine Datenbank auf den Stand vor NK-036 zurueck, legt dort
# Fliesskomma-Altbestand ab und wandert wieder hoch. Das ist der Weg, den die
# Datenbank des Betreibers beim naechsten Start geht.
CODE_GELD_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

# Betraege, wie sie nach Jahren Fliesskommarechnung in der Datei stehen. Die
# ersten drei sind keine erfundenen Krummheiten: so sieht 89,29 bzw. 1234,57
# als float wirklich aus, und 0.1 + 0.2 ist das Lehrbuchbeispiel.
BETRAEGE = [89.28999999999999, 0.1 + 0.2, 1234.5699999999999, 2.675, 150.0]


def _spaltentyp(tabelle):
    for zeile in db.session.execute(text("PRAGMA table_info('%s')" % tabelle)).all():
        if zeile[1] == "amount":
            return zeile[2]
    return None


with anwendung.app.app_context():
    downgrade(revision="9c1f4a2b7d33")
    typ_vorher = _spaltentyp("cost_invoices")

    db.session.execute(text(
        "INSERT INTO properties (name, is_standalone) VALUES ('Altbau', 0)"))
    haus = db.session.execute(text("SELECT id FROM properties")).scalar()
    db.session.execute(text(
        "INSERT INTO apartments (property_id, name, sqm, is_active)"
        " VALUES (:h, 'EG', 60.0, 1)"), {"h": haus})
    wohnung = db.session.execute(text("SELECT id FROM apartments")).scalar()
    db.session.execute(text(
        "INSERT INTO tenants (apartment_id, name, move_in_date)"
        " VALUES (:w, 'Frau Mueller', '2024-01-01')"), {"w": wohnung})
    mieter = db.session.execute(text("SELECT id FROM tenants")).scalar()
    kategorie = db.session.execute(text("SELECT id FROM cost_categories")).scalar()

    for nummer, betrag in enumerate(BETRAEGE, start=1):
        db.session.execute(text(
            "INSERT INTO cost_invoices"
            " (category_id, property_id, start_date, end_date, amount, invoice_number)"
            " VALUES (:k, :h, '2024-01-01', '2024-12-31', :b, :n)"),
            {"k": kategorie, "h": haus, "b": betrag, "n": "R-%d" % nummer})
        db.session.execute(text(
            "INSERT INTO payments (tenant_id, amount, payment_date, type)"
            " VALUES (:m, :b, '2024-03-01', 'Nebenkostenvorauszahlung')"),
            {"m": mieter, "b": betrag})
    db.session.commit()

    roh_vorher = [
        repr(z[0]) for z in db.session.execute(
            text("SELECT amount FROM cost_invoices ORDER BY id")).all()
    ]

    upgrade()

    typ_nachher = _spaltentyp("cost_invoices")
    rechnungen = [
        repr(z[0]) for z in db.session.execute(
            text("SELECT amount FROM cost_invoices ORDER BY id")).all()
    ]
    zahlungen = [
        repr(z[0]) for z in db.session.execute(
            text("SELECT amount FROM payments ORDER BY id")).all()
    ]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"typ_vorher": typ_vorher, "typ_nachher": typ_nachher,
                  "roh_vorher": roh_vorher, "rechnungen": rechnungen,
                  "zahlungen": zahlungen, "stand": stand}))
"""


def test_die_geldwanderung_rueckt_den_altbestand_auf_cent(tmp_path):
    """NK-036, der Teil der Wanderung, der nicht nur Schema ist.

    Den Spaltentyp zu tauschen ist die halbe Arbeit. Stuende danach weiter
    ``89.28999999999999`` in einer Spalte namens ``Numeric(12, 2)``, waere die
    Typzusage eine Behauptung. Deshalb geht hier eine Datenbank den echten Weg:
    herunter auf den Stand vor NK-036, Fliesskomma-Altbestand hinein, wieder
    hoch -- und danach muss jeder Betrag cent-genau sein.
    """
    from decimal import Decimal

    datei = tmp_path / "geldwanderung.db"
    _lauf(CODE_START, datei, tmp_path)

    stand = _lauf(CODE_GELD_WANDERUNG, datei, tmp_path)

    # Gegenprobe zuerst: der Altbestand war wirklich krumm. Ohne diese Zeile
    # koennte der Test auch dann gruen sein, wenn SQLite die Werte schon beim
    # Einfuegen zurechtgebogen haette und die Wanderung nichts tut.
    assert "89.28999999999999" in stand["roh_vorher"]
    assert "0.30000000000000004" in stand["roh_vorher"]

    assert stand["stand"] == KOPFREVISION
    assert "FLOAT" in stand["typ_vorher"].upper()
    assert "NUMERIC" in stand["typ_nachher"].upper()

    erwartet = ["89.29", "0.30", "1234.57", "2.68", "150.00"]
    for feld in ("rechnungen", "zahlungen"):
        gerundet = [str(Decimal(roh).quantize(Decimal("0.01"))) for roh in stand[feld]]
        assert gerundet == erwartet, f"{feld}: {stand[feld]}"
        # Und zwar gerundet vorgefunden, nicht erst hier gerundet: der Wert in
        # der Datei hat selbst schon hoechstens zwei Nachkommastellen.
        for roh in stand[feld]:
            assert Decimal(roh) == Decimal(roh).quantize(Decimal("0.01")), roh


def test_die_geldwanderung_rundet_kaufmaennisch(tmp_path):
    """2,675 wird 2,68 und nicht 2,67.

    Der Unterschied ist kein Haarspalten: ``round(2.675, 2)`` ergibt in Python
    2.67, weil der float knapp darunter liegt und ROUND_HALF_EVEN gilt. Die
    Wanderung geht ueber ``geld.runde``, also denselben kaufmaennischen Weg wie
    der Rechenkern. Waere sie ueber ``ROUND()`` von SQLite gegangen, stuende
    hier ein anderer Cent als in jeder spaeter erzeugten Abrechnung.
    """
    from decimal import Decimal

    datei = tmp_path / "kaufmaennisch.db"
    _lauf(CODE_START, datei, tmp_path)
    stand = _lauf(CODE_GELD_WANDERUNG, datei, tmp_path)

    assert Decimal(stand["rechnungen"][3]) == Decimal("2.68")
    assert round(2.675, 2) == 2.67  # was ohne geld.runde dort stuende


def test_die_geldwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() bringt den Spaltentyp zurueck, ohne die Daten zu verlieren.

    Zurueckgedreht wird beim Betreiber nur im Notfall, aber wenn, dann muss es
    gehen: eine Wanderung, deren Rueckweg beim ersten Versuch abbricht, laesst
    die Datenbank auf halbem Stand stehen. Die Rundung kommt dabei nicht
    zurueck -- aus 89,29 wird nicht wieder 89.28999999999999 -- und das ist so
    gewollt und im Kopf der Revision festgehalten.
    """
    datei = tmp_path / "zurueck.db"
    _lauf(CODE_START, datei, tmp_path)
    _lauf(CODE_GELD_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="9c1f4a2b7d33")
    typ = [z[2] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all() if z[1] == "amount"][0]
    betraege = [repr(z[0]) for z in db.session.execute(
        text("SELECT amount FROM cost_invoices ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"typ": typ, "betraege": betraege, "stand": stand}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "9c1f4a2b7d33"
    assert "FLOAT" in stand["typ"].upper()
    assert len(stand["betraege"]) == 5
    assert float(stand["betraege"][0]) == 89.29


# NK-096: CHECK auf tenant_cost_profiles.billing_type (F-25)

# Faehrt auf den Stand vor NK-096 zurueck, legt dort Kostenprofile mit
# Abrechnungsarten ab, die es nicht gibt, und wandert wieder hoch. Genau diesen
# Weg geht die Datenbank des Betreibers beim naechsten Start.
CODE_ART_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

# Was nach Jahren ohne Eingabepruefung in der Spalte stehen kann. Die ersten
# beiden sind offensichtlich gemeint und nur falsch geschrieben, die uebrigen
# drei sind nicht zu retten. Alle fuenf liessen die Kostenart bisher lautlos
# aus dem Blatt fallen.
ARTEN = ['Qm', 'direkt ', 'verbrauch', '', 'PER_SQM']

with anwendung.app.app_context():
    downgrade(revision="a7c3e91d4b28")

    db.session.execute(text(
        "INSERT INTO properties (name, is_standalone) VALUES ('Altbau', 0)"))
    haus = db.session.execute(text("SELECT id FROM properties")).scalar()
    db.session.execute(text(
        "INSERT INTO apartments (property_id, name, sqm, is_active)"
        " VALUES (:h, 'EG', 60.0, 1)"), {"h": haus})
    wohnung = db.session.execute(text("SELECT id FROM apartments")).scalar()
    db.session.execute(text(
        "INSERT INTO tenants (apartment_id, name, move_in_date)"
        " VALUES (:w, 'Frau Mueller', '2024-01-01')"), {"w": wohnung})
    mieter = db.session.execute(text("SELECT id FROM tenants")).scalar()
    kategorien = [z[0] for z in db.session.execute(
        text("SELECT id FROM cost_categories ORDER BY id")).all()]

    # Eine gueltige Zeile kommt mit: sie darf die Wanderung nicht bemerken.
    db.session.execute(text(
        "INSERT INTO tenant_cost_profiles (tenant_id, category_id, billing_type)"
        " VALUES (:m, :k, 'personen')"), {"m": mieter, "k": kategorien[0]})
    for nummer, art in enumerate(ARTEN, start=1):
        db.session.execute(text(
            "INSERT INTO tenant_cost_profiles (tenant_id, category_id, billing_type)"
            " VALUES (:m, :k, :a)"),
            {"m": mieter, "k": kategorien[nummer], "a": art})
    db.session.commit()

    vorher = [z[0] for z in db.session.execute(text(
        "SELECT billing_type FROM tenant_cost_profiles ORDER BY id")).all()]

    upgrade()

    nachher = [z[0] for z in db.session.execute(text(
        "SELECT billing_type FROM tenant_cost_profiles ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'tenant_cost_profiles'")).scalar()

print(json.dumps({"vorher": vorher, "nachher": nachher, "stand": stand,
                  "schema": schema}))
"""


def test_die_artwanderung_zieht_den_altbestand_gerade(tmp_path):
    """NK-096, der Teil der Wanderung, der nicht nur Schema ist.

    Den CHECK zu setzen ist die halbe Arbeit -- und ohne den ersten Teil ginge
    sie gar nicht: ``batch_alter_table`` kopiert die Daten in die neue Tabelle,
    und eine Zeile mit ``'verbrauch'`` liesse schon das Kopieren scheitern.
    Der Betreiber saehe einen ``IntegrityError`` beim Hochfahren und seine
    Instanz kaeme nicht mehr hoch.
    """
    datei = tmp_path / "artwanderung.db"
    _lauf(CODE_START, datei, tmp_path)

    stand = _lauf(CODE_ART_WANDERUNG, datei, tmp_path)

    # Gegenprobe zuerst: der Altbestand war wirklich kaputt. Ohne diese Zeile
    # waere der Test auch dann gruen, wenn gar nichts eingefuegt worden waere.
    assert stand["vorher"] == ["personen", "Qm", "direkt ", "verbrauch", "", "PER_SQM"]

    assert stand["stand"] == KOPFREVISION
    # Die gueltige Zeile bleibt, wie sie war. Was sich normieren laesst, wird
    # normiert. Der Rest bekommt 'ignoriert' (D-30) -- und behaelt damit
    # genau das Ergebnis, das er vorher hatte: der Mieter zahlt dafuer nichts.
    assert stand["nachher"] == [
        "personen", "qm", "direkt", "ignoriert", "ignoriert", "ignoriert"]


def test_die_artwanderung_setzt_den_check(tmp_path):
    """Nach dem Start weist die Datenbank selbst eine erfundene Art zurueck.

    Gemessen an der Datenbank, nicht an ``models.py``: eine Zusage im Modell,
    die im Schema fehlt, gilt nicht fuer die eingespielte Sicherung und nicht
    fuer die Zeile per ``sqlite3``.
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "artcheck.db"
    stand = _lauf(CODE_ART_WANDERUNG, datei, tmp_path)

    from nebenkostenfix.abrechnungsart import GUELTIG

    for art in GUELTIG:
        assert f"'{art}'" in stand["schema"], f"{art} fehlt im CHECK"

    verbindung = sqlite3.connect(datei)
    try:
        zeile = verbindung.execute(
            "SELECT tenant_id, category_id FROM tenant_cost_profiles LIMIT 1"
        ).fetchone()
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "INSERT INTO tenant_cost_profiles"
                " (tenant_id, category_id, billing_type) VALUES (?, ?, 'verbrauch')",
                zeile,
            )
        # Und eine gueltige Art geht weiterhin durch.
        verbindung.execute(
            "INSERT INTO tenant_cost_profiles"
            " (tenant_id, category_id, billing_type) VALUES (?, ?, 'nur_allgemein')",
            zeile,
        )
    finally:
        verbindung.close()


def test_die_artwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die Bedingung zurueck, ohne die Daten zu verlieren.

    Zurueckgedreht wird beim Betreiber nur im Notfall, aber dann muss es gehen.
    Die geradegezogenen Werte kommen dabei nicht zurueck -- aus 'ignoriert'
    wird nicht wieder 'verbrauch' -- und das ist so gewollt und im Kopf der
    Revision festgehalten.
    """
    datei = tmp_path / "artzurueck.db"
    _lauf(CODE_ART_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="a7c3e91d4b28")
    arten = [z[0] for z in db.session.execute(text(
        "SELECT billing_type FROM tenant_cost_profiles ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'tenant_cost_profiles'")).scalar()

print(json.dumps({"arten": arten, "stand": stand, "schema": schema}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "a7c3e91d4b28"
    assert "ck_tenant_cost_profiles_billing_type" not in stand["schema"]
    assert stand["arten"] == [
        "personen", "qm", "direkt", "ignoriert", "ignoriert", "ignoriert"]


# NK-044: BetrKV-Nummer auf cost_categories (R-KAT-01)

# Faehrt auf den Stand vor NK-044 zurueck, legt dort Kostenarten mit
# gewachsenen Namen ab und wandert wieder hoch. Genau diesen Weg geht die
# Datenbank des Betreibers beim naechsten Start.
CODE_BETRKV_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

# Die acht des alten Seeds, dazu vier, wie sie ein Vermieter selbst benennt,
# und eine, die sich beim besten Willen nicht zuordnen laesst.
NAMEN = ['Strom', 'Wasser', 'Abwasser', 'Niederschlagswasser', 'Gas',
         'Grundsteuer', 'Gebäudeversicherung', 'Sonstiges',
         'Aufzugswartung', 'Hausmeisterservice', 'Müllabfuhr',
         'Kaminkehrer', 'Dachterrasse']

with anwendung.app.app_context():
    downgrade(revision="b4e7f2a91c65")

    db.session.execute(text("DELETE FROM cost_categories"))
    for name in NAMEN:
        db.session.execute(text(
            "INSERT INTO cost_categories (name, allocation_method, requires_meter)"
            " VALUES (:n, 'PER_SQM', 0)"), {"n": name})
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_categories')")).all()]

    upgrade()

    nachher = [(z[0], z[1]) for z in db.session.execute(text(
        "SELECT name, betrkv_nr FROM cost_categories ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'cost_categories'")).scalar()
    indizes = [z[1] for z in db.session.execute(text(
        "PRAGMA index_list('cost_categories')")).all()]
    eindeutig = []
    for index in indizes:
        if db.session.execute(text(
                "SELECT \\"unique\\" FROM pragma_index_list('cost_categories')"
                " WHERE name = :i"), {"i": index}).scalar():
            eindeutig += [z[2] for z in db.session.execute(text(
                "PRAGMA index_info('%s')" % index)).all()]

print(json.dumps({"spalten_vorher": spalten_vorher, "nachher": nachher,
                  "stand": stand, "schema": schema, "eindeutig": eindeutig}))
"""


def test_die_betrkvwanderung_ordnet_den_altbestand_zu(tmp_path):
    """NK-044, der Teil der Wanderung, der nicht nur Schema ist.

    Die Spalte anzulegen ist die halbe Arbeit -- und ohne den Altbestand zu
    fuellen ginge die andere Haelfte gar nicht: ``batch_alter_table`` kopiert
    die Daten in die neue Tabelle, und eine leere Pflichtspalte liesse schon
    das Kopieren scheitern. Der Betreiber saehe einen ``IntegrityError`` beim
    Hochfahren, und seine Instanz kaeme nicht mehr hoch.
    """
    datei = tmp_path / "betrkvwanderung.db"
    _lauf(CODE_START, datei, tmp_path)

    stand = _lauf(CODE_BETRKV_WANDERUNG, datei, tmp_path)

    # Gegenprobe zuerst: vorher gab es die Spalte wirklich nicht. Ohne diese
    # Zeile waere der Test auch dann gruen, wenn gar nichts gewandert waere.
    assert "betrkv_nr" not in stand["spalten_vorher"]

    assert stand["stand"] == KOPFREVISION
    assert stand["nachher"] == [
        ["Strom", 11],
        ["Wasser", 2],
        ["Abwasser", 3],
        ["Niederschlagswasser", 3],   # Nr. 3, nicht Nr. 2: Regenwasser ist
                                      # Entwaesserung, keine Versorgung
        ["Gas", 4],
        ["Grundsteuer", 1],
        ["Gebäudeversicherung", 13],
        ["Sonstiges", 17],
        ["Aufzugswartung", 7],
        ["Hausmeisterservice", 14],
        ["Müllabfuhr", 8],
        ["Kaminkehrer", 12],
        # Nicht zuzuordnen -> der offene Posten, nicht irgendeine Nummer.
        ["Dachterrasse", 17],
    ]


def test_die_betrkvwanderung_setzt_pflicht_und_check(tmp_path):
    """Nach dem Start weist die Datenbank selbst eine Kostenart ohne Nummer ab.

    Gemessen an der Datenbank, nicht an ``models.py``: eine Zusage im Modell
    gilt nicht fuer die eingespielte Sicherung und nicht fuer die Zeile per
    ``sqlite3``. R-KAT-01: "Eine Kategorie ohne BetrKV-Nummer kann nicht
    gespeichert werden."
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "betrkvcheck.db"
    stand = _lauf(CODE_BETRKV_WANDERUNG, datei, tmp_path)

    assert "ck_cost_categories_betrkv_nr" in stand["schema"]

    verbindung = sqlite3.connect(datei)
    try:
        # Ohne Nummer: geht nicht.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "INSERT INTO cost_categories (name, allocation_method, requires_meter)"
                " VALUES ('Ohne Nummer', 'PER_SQM', 0)")
        # Mit einer Nummer, die es im Gesetz nicht gibt: geht auch nicht.
        for erfunden in (0, 18, -1):
            with _pytest.raises(sqlite3.IntegrityError):
                verbindung.execute(
                    "INSERT INTO cost_categories"
                    " (name, allocation_method, requires_meter, betrkv_nr)"
                    " VALUES (?, 'PER_SQM', 0, ?)", (f"Erfunden {erfunden}", erfunden))
        # Mit einer gueltigen Nummer: geht durch.
        verbindung.execute(
            "INSERT INTO cost_categories"
            " (name, allocation_method, requires_meter, betrkv_nr)"
            " VALUES ('Zweiter Aufzug', 'PER_SQM', 0, 7)")
    finally:
        verbindung.close()


def test_die_betrkvwanderung_laesst_das_unique_auf_dem_namen_stehen(tmp_path):
    """Der Tabellenneubau darf die Bedingung aus NK-095 nicht verschlucken.

    ``batch_alter_table`` baut die Tabelle neu. Alembic nimmt die bekannten
    Bedingungen mit -- aber das ist eine Zusage, die man pruefen muss und
    nicht glauben darf: faellt das UNIQUE hier lautlos weg, stehen beim
    Vermieter wieder zwei gleichnamige Kostenarten in der Auswahlliste, und
    niemand merkt es, bis er die falsche waehlt.
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "betrkvunique.db"
    stand = _lauf(CODE_BETRKV_WANDERUNG, datei, tmp_path)

    assert "name" in stand["eindeutig"], f"eindeutig: {stand['eindeutig']}"

    verbindung = sqlite3.connect(datei)
    try:
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "INSERT INTO cost_categories"
                " (name, allocation_method, requires_meter, betrkv_nr)"
                " VALUES ('Strom', 'PER_SQM', 0, 11)")
    finally:
        verbindung.close()


def test_die_betrkvwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die Spalte samt Bedingung zurueck.

    Zurueckgedreht wird beim Betreiber nur im Notfall, aber dann muss es
    gehen. Die Nummern gehen dabei verloren -- das ist unbedenklich, weil ein
    erneutes ``upgrade()`` dieselben Werte aus denselben Namen errechnet.
    """
    datei = tmp_path / "betrkvzurueck.db"
    _lauf(CODE_BETRKV_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="b4e7f2a91c65")
    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_categories')")).all()]
    namen = [z[0] for z in db.session.execute(text(
        "SELECT name FROM cost_categories ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"spalten": spalten, "namen": namen, "stand": stand}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "b4e7f2a91c65"
    assert "betrkv_nr" not in stand["spalten"]
    # Die Kostenarten selbst bleiben stehen. Es sind mehr als die dreizehn
    # gewachsenen: der Start vor dem Zurueckdrehen hat gesaet und die sechs
    # Nummern nachgelegt, die im Altbestand fehlten.
    assert set(stand["namen"]) >= {
        "Strom", "Wasser", "Abwasser", "Niederschlagswasser", "Gas",
        "Grundsteuer", "Gebäudeversicherung", "Sonstiges", "Aufzugswartung",
        "Hausmeisterservice", "Müllabfuhr", "Kaminkehrer", "Dachterrasse"}
    assert stand["namen"][0] == "Strom"


def test_der_seed_legt_alle_siebzehn_nummern_an(tmp_path):
    """R-KAT-01: "Der Seed erzeugt 17 Kategorien mit den Nummern 1-17."

    Seit NK-117 (D-72) sind es 18 Eintraege: die Nr. 3 traegt Entwaesserung
    und Niederschlagswasser.

    Gemessen an einer frisch aufgebauten Datenbank, nicht am Katalog in
    ``betrkv.py``: dass der Katalog siebzehn Eintraege hat, prueft
    ``tests/test_betrkv.py``. Hier geht es darum, dass sie auch wirklich
    ankommen.
    """
    datei = tmp_path / "seed.db"
    _lauf(CODE_START, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    zeilen = [(z[0], z[1], z[2], z[3]) for z in db.session.execute(text(
        "SELECT betrkv_nr, name, allocation_method, requires_meter"
        " FROM cost_categories ORDER BY betrkv_nr, id")).all()]

print(json.dumps({"zeilen": zeilen}))
"""
    stand = _lauf(code, datei, tmp_path)

    from nebenkostenfix.betrkv import KATALOG

    assert [z[0] for z in stand["zeilen"]] == [e["nr"] for e in KATALOG]
    assert sorted({z[0] for z in stand["zeilen"]}) == list(range(1, 18))
    assert [z[1] for z in stand["zeilen"]] == [e["name"] for e in KATALOG]
    assert [z[2] for z in stand["zeilen"]] == [e["verteilung"] for e in KATALOG]
    assert [bool(z[3]) for z in stand["zeilen"]] == [e["zaehler"] for e in KATALOG]


def test_der_seed_macht_aus_altbestand_keine_dubletten(tmp_path):
    """Ein Vermieter mit acht gewachsenen Kostenarten bekommt keine neun.

    Der Seed gleicht ueber die Nummer ab, nicht ueber den Namen. Sonst kaeme
    zu "Gebaeudeversicherung" (Nr. 13) noch "Sach- und Haftpflicht-
    versicherung" (Nr. 13) -- zwei Eintraege fuer dieselbe Position, und der
    Vermieter kann nicht erkennen, welcher die Rechnungen traegt (NK-095).
    """
    datei = tmp_path / "seedalt.db"
    _lauf(CODE_START, datei, tmp_path)
    _lauf(CODE_BETRKV_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    anwendung.seed_database()
    zeilen = [(z[0], z[1]) for z in db.session.execute(text(
        "SELECT name, betrkv_nr FROM cost_categories ORDER BY id")).all()]

print(json.dumps({"zeilen": zeilen}))
"""
    stand = _lauf(code, datei, tmp_path)

    namen = [z[0] for z in stand["zeilen"]]
    nummern = [z[1] for z in stand["zeilen"]]

    # Die gewachsenen Namen bleiben unangetastet, und zwar alle dreizehn.
    assert namen[:13] == [
        "Strom", "Wasser", "Abwasser", "Niederschlagswasser", "Gas",
        "Grundsteuer", "Gebäudeversicherung", "Sonstiges", "Aufzugswartung",
        "Hausmeisterservice", "Müllabfuhr", "Kaminkehrer", "Dachterrasse"]

    # Keine Nummer, die schon besetzt war, kommt ein zweites Mal dazu.
    assert "Sach- und Haftpflichtversicherung" not in namen
    assert nummern.count(13) == 1
    assert nummern.count(7) == 1

    # Was fehlte, ist jetzt da -- jede der siebzehn Nummern mindestens einmal.
    assert set(nummern) == set(range(1, 18))

    # Die Nr. 3 hat ihre zwei Eintraege schon aus dem Altbestand (Abwasser,
    # Niederschlagswasser) -- der Katalog legt keinen dritten dazu (NK-117).
    assert nummern.count(3) == 2
    assert "Entwässerung" not in namen

    # Und kein Name doppelt.
    assert len(namen) == len(set(namen))


def test_der_seed_ergaenzt_das_niederschlagswasser_neben_dem_abwasser(tmp_path):
    """Wer nur das Abwasser kennt, bekommt das Niederschlagswasser (NK-117).

    Die Entwaesserung kommt nicht dazu -- das Abwasser deckt sie ab --, das
    Niederschlagswasser schon: es wird nach Flaeche verteilt und gehoert
    nicht auf den Frischwasserzaehler (D-72).
    """
    datei = tmp_path / "seedabwasser.db"
    _lauf(CODE_START, datei, tmp_path)
    _lauf(CODE_BETRKV_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    db.session.execute(text(
        "DELETE FROM cost_categories WHERE name = 'Niederschlagswasser'"))
    db.session.commit()
    anwendung.seed_database()
    anwendung.seed_database()
    zeilen = [(z[0], z[1], z[2]) for z in db.session.execute(text(
        "SELECT name, betrkv_nr, allocation_method FROM cost_categories"
        " WHERE betrkv_nr = 3 ORDER BY id")).all()]

print(json.dumps({"zeilen": zeilen}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["zeilen"] == [
        ["Abwasser", 3, stand["zeilen"][0][2]],
        ["Niederschlagswasser", 3, "PER_SQM"],
    ]


# --- NK-045: die Stammdaten der Nutzung (d2f8b16c05a9) ----------------------

CODE_NUTZUNGS_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="c9a5d3f81e47")

    db.session.execute(text("DELETE FROM tenants"))
    db.session.execute(text("DELETE FROM apartments"))
    db.session.execute(text("DELETE FROM properties"))
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    # Zwei Einheiten, eine davon leer stehend -- so, wie sie ein Vermieter vor
    # NK-045 angelegt hat: ohne jede Angabe darueber, wofuer sie da sind.
    for kennung, name, qm, aktiv in ((1, 'EG', 62.5, 1), (2, 'OG', 48.0, 0)):
        db.session.execute(text(
            "INSERT INTO apartments (id, property_id, name, sqm, is_active)"
            " VALUES (:i, 1, :n, :q, :a)"),
            {"i": kennung, "n": name, "q": qm, "a": aktiv})
    for kennung, wohnung, name, einzug in (
            (1, 1, 'Anna Mieterin', '2022-04-15'),
            (2, 2, 'Bernd Mieter', '2019-01-01')):
        db.session.execute(text(
            "INSERT INTO tenants (id, apartment_id, name, move_in_date)"
            " VALUES (:i, :w, :n, :e)"),
            {"i": kennung, "w": wohnung, "n": name, "e": einzug})
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('apartments')")).all()]
    tabellen_vorher = [z[0] for z in db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type = 'table'")).all()]

    upgrade()

    wohnungen = [(z[0], z[1], z[2], z[3]) for z in db.session.execute(text(
        "SELECT name, nutzungsart, selbstversorger, eigennutzung"
        " FROM apartments ORDER BY id")).all()]
    haushalte = [(z[0], z[1], z[2]) for z in db.session.execute(text(
        "SELECT tenant_id, gueltig_ab, personenanzahl"
        " FROM haushaltsgroessen ORDER BY tenant_id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'apartments'")).scalar()
    schema_haushalte = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'haushaltsgroessen'")).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher,
                  "tabellen_vorher": tabellen_vorher,
                  "wohnungen": wohnungen, "haushalte": haushalte,
                  "stand": stand, "schema": schema,
                  "schema_haushalte": schema_haushalte}))
"""


def test_die_nutzungswanderung_laesst_den_altbestand_wo_er_war(tmp_path):
    """NK-045: ein Update darf keine einzige Abrechnung verschieben.

    Vor dieser Karte gab es die Frage nach der Nutzungsart nicht, und jedes
    Objekt wurde als Wohnhaus gerechnet. Setzte die Wanderung irgendetwas
    anderes -- oder liesse sie die Spalte leer --, bekaeme der Betreiber nach
    dem Einspielen eine andere Zahl auf demselben Zeitraum, ohne dass er
    etwas geaendert haette.
    """
    datei = tmp_path / "nutzungswanderung.db"
    _lauf(CODE_START, datei, tmp_path)

    stand = _lauf(CODE_NUTZUNGS_WANDERUNG, datei, tmp_path)

    # Gegenprobe: vorher gab es weder die Spalten noch die Tabelle.
    assert "nutzungsart" not in stand["spalten_vorher"]
    assert "haushaltsgroessen" not in stand["tabellen_vorher"]

    assert stand["stand"] == KOPFREVISION
    # Wohnraum, kein Selbstversorger, nicht eigengenutzt -- auch die leer
    # stehende Einheit, die niemand mehr angefasst hat.
    assert stand["wohnungen"] == [
        ["EG", "wohnen", 0, 0],
        ["OG", "wohnen", 0, 0],
    ]


def test_die_nutzungswanderung_gibt_jedem_mietverhaeltnis_einen_kopf(tmp_path):
    """Ein Kopf ab Einzug -- genau die Zahl, mit der bisher gerechnet wurde.

    Der Stichtag ist das Einzugsdatum und nicht der Tag der Wanderung: sonst
    haette ein Mietverhaeltnis aus 2019 fuer die Jahre davor keine Angabe,
    und eine Nachberechnung liefe auf den Notbehelf statt auf einen
    gepflegten Wert.
    """
    datei = tmp_path / "nutzungskoepfe.db"
    _lauf(CODE_START, datei, tmp_path)

    stand = _lauf(CODE_NUTZUNGS_WANDERUNG, datei, tmp_path)

    assert stand["haushalte"] == [
        [1, "2022-04-15", 1],
        [2, "2019-01-01", 1],
    ]


def test_die_nutzungswanderung_setzt_pflicht_und_check(tmp_path):
    """Nach dem Start weist die Datenbank selbst eine erfundene Art ab.

    Gemessen an der Datenbank, nicht an ``models.py`` und nicht an der
    Eingabepruefung: beide decken die Oberflaeche ab, nicht die eingespielte
    Sicherung und nicht die Zeile per ``sqlite3``.
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "nutzungscheck.db"
    stand = _lauf(CODE_NUTZUNGS_WANDERUNG, datei, tmp_path)

    assert "ck_apartments_nutzungsart" in stand["schema"]

    verbindung = sqlite3.connect(datei)
    try:
        for erfunden in ("buero", "gemischt", "", "Wohnen"):
            with _pytest.raises(sqlite3.IntegrityError):
                verbindung.execute(
                    "INSERT INTO apartments"
                    " (property_id, name, sqm, is_active, nutzungsart)"
                    " VALUES (1, ?, 40.0, 1, ?)", (f"Erfunden {erfunden}", erfunden))
        # Beide Arten des Katalogs gehen durch.
        for gueltig in ("wohnen", "gewerbe"):
            verbindung.execute(
                "INSERT INTO apartments"
                " (property_id, name, sqm, is_active, nutzungsart)"
                " VALUES (1, ?, 40.0, 1, ?)", (f"Neu {gueltig}", gueltig))
        # Und ohne Angabe greift die Vorgabe aus dem Schema.
        verbindung.execute(
            "INSERT INTO apartments (property_id, name, sqm, is_active)"
            " VALUES (1, 'Ohne Angabe', 40.0, 1)")
        art = verbindung.execute(
            "SELECT nutzungsart FROM apartments WHERE name = 'Ohne Angabe'").fetchone()
        assert art[0] == "wohnen"
    finally:
        verbindung.close()


def test_die_haushaltstabelle_haelt_ihre_beiden_bedingungen(tmp_path):
    """Kein Haushalt ohne Kopf, und kein Stichtag zweimal.

    Zwei Zeilen zum selben Tag waeren zwei Wahrheiten: welche gilt, koennte
    niemand sagen -- am wenigsten der Mieter, der die Abrechnung prueft.
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "haushaltscheck.db"
    stand = _lauf(CODE_NUTZUNGS_WANDERUNG, datei, tmp_path)

    assert "ck_haushaltsgroessen_personenanzahl" in stand["schema_haushalte"]
    assert "uq_haushaltsgroessen_tenant_gueltig_ab" in stand["schema_haushalte"]

    verbindung = sqlite3.connect(datei)
    try:
        for kopflos in (0, -1):
            with _pytest.raises(sqlite3.IntegrityError):
                verbindung.execute(
                    "INSERT INTO haushaltsgroessen"
                    " (tenant_id, gueltig_ab, personenanzahl)"
                    " VALUES (1, '2024-01-01', ?)", (kopflos,))
        verbindung.execute(
            "INSERT INTO haushaltsgroessen (tenant_id, gueltig_ab, personenanzahl)"
            " VALUES (1, '2024-01-01', 3)")
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "INSERT INTO haushaltsgroessen (tenant_id, gueltig_ab, personenanzahl)"
                " VALUES (1, '2024-01-01', 4)")
        # Derselbe Tag bei einem anderen Mietverhaeltnis ist kein Widerspruch.
        verbindung.execute(
            "INSERT INTO haushaltsgroessen (tenant_id, gueltig_ab, personenanzahl)"
            " VALUES (2, '2024-01-01', 4)")
    finally:
        verbindung.close()


def test_die_nutzungswanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die drei Spalten und die Tabelle zurueck.

    Zurueckgedreht wird beim Betreiber nur im Notfall, aber dann muss es
    gehen. Anders als bei NK-044 geht dabei wirklich etwas verloren: eine von
    Hand gepflegte Personenhistorie rechnet kein erneutes ``upgrade()``
    wieder aus. Das steht so in der Wanderung und gehoert in die Hinweise
    zum Zurueckdrehen.
    """
    datei = tmp_path / "nutzungzurueck.db"
    _lauf(CODE_NUTZUNGS_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="c9a5d3f81e47")
    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('apartments')")).all()]
    tabellen = [z[0] for z in db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type = 'table'")).all()]
    namen = [z[0] for z in db.session.execute(text(
        "SELECT name FROM apartments ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"spalten": spalten, "tabellen": tabellen,
                  "namen": namen, "stand": stand}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "c9a5d3f81e47"
    for spalte in ("nutzungsart", "selbstversorger", "eigennutzung"):
        assert spalte not in stand["spalten"]
    assert "haushaltsgroessen" not in stand["tabellen"]
    # Die Einheiten selbst bleiben stehen -- der Tabellenneubau darf sie nicht
    # verlieren.
    assert stand["namen"][:2] == ["EG", "OG"]


# --- NK-048: die Heizungsanlage (Revision e5b2c74f9a16) ---------------------

# Baut einen Bestand aus der Zeit vor NK-048 auf: ein Haus, zwei Rechnungen,
# von denen eine unter der Kostenart "Heizung" laeuft. Genau so sieht es bei
# einem Vermieter aus, der seit Jahren Gasrechnungen eintraegt. Dann wandert
# die Datenbank nach vorn und meldet, was aus dem Bestand geworden ist.
CODE_HEIZUNGS_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="d2f8b16c05a9")

    db.session.execute(text("DELETE FROM cost_invoices"))
    db.session.execute(text("DELETE FROM properties WHERE id = 1"))
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    kategorie = db.session.execute(text(
        "SELECT id FROM cost_categories WHERE betrkv_nr = 4 LIMIT 1")).scalar()
    for kennung, betrag, was in ((1, 8200.00, 'Gas 2024'), (2, 420.00, 'Wartung')):
        db.session.execute(text(
            "INSERT INTO cost_invoices"
            " (id, category_id, property_id, start_date, end_date, amount, description)"
            " VALUES (:i, :k, 1, '2024-01-01', '2024-12-31', :b, :d)"),
            {"i": kennung, "k": kategorie, "b": betrag, "d": was})
    db.session.commit()

    tabellen_vorher = [z[0] for z in db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type = 'table'")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]
    spalten_anlage = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('heizungsanlagen')")).all()]
    anlagen = db.session.execute(text(
        "SELECT COUNT(*) FROM heizungsanlagen")).scalar()
    rechnungen = [(z[0], z[1], z[2], float(z[3])) for z in db.session.execute(text(
        "SELECT description, heizungsanlage_id, heizkostenart, amount"
        " FROM cost_invoices ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'cost_invoices'")).scalar()
    schema_anlagen = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'heizungsanlagen'")).scalar()

print(json.dumps({"tabellen_vorher": tabellen_vorher, "spalten": spalten,
                  "spalten_anlage": spalten_anlage, "anlagen": anlagen,
                  "rechnungen": rechnungen, "stand": stand,
                  "schema": schema, "schema_anlagen": schema_anlagen}))
"""


def test_die_heizungswanderung_legt_die_anlage_an(tmp_path):
    """Tabelle und Spalten stehen danach da, der Stempel auch."""
    datei = tmp_path / "heizung.db"
    stand = _lauf(CODE_HEIZUNGS_WANDERUNG, datei, tmp_path)

    assert "heizungsanlagen" not in stand["tabellen_vorher"]
    # Der Lauf faehrt bis zum Kopf der Kette, nicht bis e5b2c74f9a16: seit
    # NK-049 haengt f3a9c05e8d72 dahinter, und ``upgrade()`` ohne Ziel nimmt
    # immer alles.
    assert stand["stand"] == KOPFREVISION
    # Die ersten sechs Spalten sind die dieser Wanderung, in dieser Folge.
    # Was spaetere Karten anhaengen -- seit NK-050 die sechs Felder des
    # § 9 -- steht dahinter und geht diesen Test nichts an.
    assert stand["spalten_anlage"][:6] == [
        "id", "property_id", "name", "versorgt",
        "verbrauchsanteil_prozent", "sonderfall_70",
    ]
    for spalte in ("heizungsanlage_id", "heizkostenart"):
        assert spalte in stand["spalten"]


def test_die_heizungswanderung_laesst_den_altbestand_in_ruhe(tmp_path):
    """Keine Anlage erfunden, keine Rechnung zugeordnet.

    Der Grund ist derselbe wie bei NK-045: wer hier raet, veraendert
    rueckwirkend eine bereits verschickte Abrechnung. Ordnete die Wanderung
    die Gasrechnung einer erfundenen Anlage zu, verteilte NK-049 sie beim
    naechsten Lauf zu 70 vom Hundert nach Verbrauch statt wie bisher nach
    Flaeche -- und der Mieter bekaeme fuer dasselbe Jahr zwei verschiedene
    Zahlen. Die Zuordnung ist eine Angabe des Vermieters, keine Vermutung
    des Programms.
    """
    datei = tmp_path / "heizungbestand.db"
    stand = _lauf(CODE_HEIZUNGS_WANDERUNG, datei, tmp_path)

    assert stand["anlagen"] == 0
    assert stand["rechnungen"] == [
        ["Gas 2024", None, None, 8200.00],
        ["Wartung", None, None, 420.00],
    ]


def test_die_heizungswanderung_setzt_ihre_fuenf_bedingungen(tmp_path):
    """Drei CHECKs an der Anlage, zwei an der Rechnung -- und sie greifen."""
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "heizungcheck.db"
    stand = _lauf(CODE_HEIZUNGS_WANDERUNG, datei, tmp_path)

    for name in ("ck_heizungsanlagen_versorgt",
                 "ck_heizungsanlagen_verbrauchsanteil",
                 "ck_heizungsanlagen_sonderfall"):
        assert name in stand["schema_anlagen"]
    for name in ("ck_cost_invoices_heizkostenart",
                 "ck_cost_invoices_heizung_vollstaendig",
                 "fk_cost_invoices_heizungsanlage"):
        assert name in stand["schema"]

    verbindung = sqlite3.connect(datei)
    verbindung.execute("PRAGMA foreign_keys = ON")
    try:
        anlegen = ("INSERT INTO heizungsanlagen"
                   " (id, property_id, name, versorgt,"
                   " verbrauchsanteil_prozent, sonderfall_70)"
                   " VALUES (?, 1, 'Kessel', ?, ?, ?)")
        # Eine vierte Versorgungsart gibt es nicht.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(anlegen, (1, "fernwaerme", 70, 0))
        # Der Rahmen des § 7 Abs. 1 gilt auch in der Datenbank.
        for daneben in (49, 71):
            with _pytest.raises(sqlite3.IntegrityError):
                verbindung.execute(anlegen, (1, "heizung", daneben, 0))
        # Im Sonderfall des Satzes 2 sind 70 zwingend.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(anlegen, (1, "heizung", 60, 1))

        verbindung.execute(anlegen, (1, "verbunden", 50, 0))
        verbindung.execute(anlegen, (2, "heizung", 70, 1))

        # An der Rechnung: beides oder keines.
        zuordnen = ("UPDATE cost_invoices SET heizungsanlage_id = ?,"
                    " heizkostenart = ? WHERE id = 1")
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(zuordnen, (1, None))
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(zuordnen, (None, "brennstoff"))
        # Und nur ein Posten, den § 7 Abs. 2 kennt.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(zuordnen, (1, "gartenpflege"))

        verbindung.execute(zuordnen, (1, "brennstoff"))
        verbindung.execute(
            "UPDATE cost_invoices SET heizungsanlage_id = 1,"
            " heizkostenart = 'bedienung' WHERE id = 2")
    finally:
        verbindung.close()


def test_die_heizungswanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt Tabelle, Spalten, Schluessel und Bedingungen zurueck.

    Die Rechnungen selbst bleiben stehen -- der Tabellenneubau darf sie nicht
    verlieren. Was an Anlagen gepflegt war, ist danach weg: vor dieser
    Wanderung gibt es keinen Ort, an dem die Angabe stehen koennte.
    """
    datei = tmp_path / "heizungzurueck.db"
    _lauf(CODE_HEIZUNGS_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    db.session.execute(text(
        "INSERT INTO heizungsanlagen (id, property_id, name, versorgt,"
        " verbrauchsanteil_prozent, sonderfall_70)"
        " VALUES (1, 1, 'Kessel', 'verbunden', 70, 0)"))
    db.session.execute(text(
        "UPDATE cost_invoices SET heizungsanlage_id = 1,"
        " heizkostenart = 'brennstoff' WHERE id = 1"))
    db.session.commit()

    downgrade(revision="d2f8b16c05a9")
    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]
    tabellen = [z[0] for z in db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type = 'table'")).all()]
    rechnungen = [(z[0], float(z[1])) for z in db.session.execute(text(
        "SELECT description, amount FROM cost_invoices ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'cost_invoices'")).scalar()

print(json.dumps({"spalten": spalten, "tabellen": tabellen,
                  "rechnungen": rechnungen, "stand": stand, "schema": schema}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "d2f8b16c05a9"
    assert "heizungsanlagen" not in stand["tabellen"]
    for spalte in ("heizungsanlage_id", "heizkostenart"):
        assert spalte not in stand["spalten"]
    for name in ("ck_cost_invoices_heizkostenart",
                 "ck_cost_invoices_heizung_vollstaendig",
                 "fk_cost_invoices_heizungsanlage"):
        assert name not in stand["schema"]
    assert stand["rechnungen"] == [["Gas 2024", 8200.00], ["Wartung", 420.00]]


# --- NK-053: die CO2-Angaben an der Rechnung (Revision b8e2f41a90c3) --------

# Baut einen Bestand aus der Zeit vor NK-053 auf: eine Rechnung mit
# Heizkostenart, eine ohne. Dann wandert die Datenbank nach vorn und
# meldet, was aus den Spalten und Bedingungen geworden ist.
CODE_CO2_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="2514fdc3f655")

    db.session.execute(text("DELETE FROM cost_invoices"))
    db.session.execute(text("DELETE FROM properties WHERE id = 1"))
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    kategorie = db.session.execute(text(
        "SELECT id FROM cost_categories WHERE betrkv_nr = 4 LIMIT 1")).scalar()
    for kennung, betrag, was in ((1, 8200.00, 'Gas 2024'), (2, 420.00, 'Wartung')):
        db.session.execute(text(
            "INSERT INTO cost_invoices"
            " (id, category_id, property_id, start_date, end_date, amount, description)"
            " VALUES (:i, :k, 1, '2024-01-01', '2024-12-31', :b, :d)"),
            {"i": kennung, "k": kategorie, "b": betrag, "d": was})
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]
    rechnungen = [(z[0], z[1], z[2]) for z in db.session.execute(text(
        "SELECT description, co2_kosten, co2_emission_kg"
        " FROM cost_invoices ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'cost_invoices'")).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher, "spalten": spalten,
                  "rechnungen": rechnungen, "stand": stand, "schema": schema}))
"""


def test_die_co2wanderung_legt_die_angaben_an(tmp_path):
    """Zwei Spalten, keine Pflicht, kein erfundener Wert.

    NULL heisst "keine Angabe" -- derselbe Grundsatz wie bei der
    Heizkostenart (NK-048): eine Wanderung, die Emissionen rechnete,
    haette Belegsachen erfunden (D-54). Der Altbestand bleibt, wie er ist.
    """
    datei = tmp_path / "co2.db"
    stand = _lauf(CODE_CO2_WANDERUNG, datei, tmp_path)

    assert "co2_kosten" not in stand["spalten_vorher"]
    for spalte in ("co2_kosten", "co2_emission_kg"):
        assert spalte in stand["spalten"]
    assert stand["stand"] == KOPFREVISION
    assert stand["rechnungen"] == [
        ["Gas 2024", None, None],
        ["Wartung", None, None],
    ]
    for name in ("ck_cost_invoices_co2_nichtnegativ",
                 "ck_cost_invoices_co2_nur_heizung"):
        assert name in stand["schema"]


def test_die_co2wanderung_setzt_ihre_bedingungen(tmp_path):
    """Kein Minus, und CO2 nur an einer Rechnung mit Heizkostenart.

    Emissionen und Kosten sind Mengen, keine Salden; ein Minus waere ein
    Vorzeichenfehler beim Erfassen. Und eine Buerorechnung mit
    Emissionsmenge waere entweder ein Tippfehler oder eine warme Vermutung
    -- nur der Brennstoff emittiert.
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "co2check.db"
    stand = _lauf(CODE_CO2_WANDERUNG, datei, tmp_path)

    verbindung = sqlite3.connect(datei)
    verbindung.execute("PRAGMA foreign_keys = ON")
    try:
        zuordnen = ("UPDATE cost_invoices SET co2_kosten = ?,"
                    " co2_emission_kg = ? WHERE id = ?")
        # Kein Minus unter null.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(zuordnen, (-10.00, 1000.00, 1))
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(zuordnen, (10.00, -1000.00, 1))
        # CO2-Angaben nur an der Rechnung mit Heizkostenart: die Wartung
        # (id 2) traegt keinen Posten und damit keine Emission.
        verbindung.execute(
            "INSERT INTO heizungsanlagen (id, property_id, name, versorgt,"
            " verbrauchsanteil_prozent, sonderfall_70)"
            " VALUES (1, 1, 'Kessel', 'heizung', 70, 0)")
        verbindung.execute(
            "UPDATE cost_invoices SET heizungsanlage_id = 1,"
            " heizkostenart = 'brennstoff' WHERE id = 1")
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(zuordnen, (10.00, 1000.00, 2))
        # Und der gueltige Fall steht danach drin.
        verbindung.execute(zuordnen, (820.00, 2200.00, 1))
    finally:
        verbindung.close()


def test_die_co2wanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die Spalten und Bedingungen zurueck, nicht mehr."""
    datei = tmp_path / "co2zurueck.db"
    _lauf(CODE_CO2_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="2514fdc3f655")
    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]
    rechnungen = [(z[0], float(z[1])) for z in db.session.execute(text(
        "SELECT description, amount FROM cost_invoices ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'cost_invoices'")).scalar()

print(json.dumps({"spalten": spalten, "rechnungen": rechnungen,
                  "stand": stand, "schema": schema}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "2514fdc3f655"
    for spalte in ("co2_kosten", "co2_emission_kg"):
        assert spalte not in stand["spalten"]
    for name in ("ck_cost_invoices_co2_nichtnegativ",
                 "ck_cost_invoices_co2_nur_heizung"):
        assert name not in stand["schema"]
    assert stand["rechnungen"] == [["Gas 2024", 8200.00], ["Wartung", 420.00]]


# --- NK-049: der Waermezaehler an der Anlage (Revision f3a9c05e8d72) --------

# Baut einen Bestand aus der Zeit vor NK-049 auf: ein Haus, eine Wohnung,
# zwei Zaehler -- einer fuer Strom, einer fuer die Waerme. Dann wandert die
# Datenbank nach vorn und meldet, was aus den Zaehlern geworden ist.
CODE_ZAEHLER_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="e5b2c74f9a16")

    db.session.execute(text("DELETE FROM meters"))
    db.session.execute(text("DELETE FROM apartments"))
    db.session.execute(text("DELETE FROM properties WHERE id = 1"))
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    db.session.execute(text(
        "INSERT INTO apartments (id, property_id, name, sqm, is_active)"
        " VALUES (1, 1, 'EG', 50, 1)"))
    kategorie = db.session.execute(text(
        "SELECT id FROM cost_categories WHERE betrkv_nr = 4 LIMIT 1")).scalar()
    for kennung, nummer in ((1, 'Strom EG'), (2, 'Waerme EG')):
        db.session.execute(text(
            "INSERT INTO meters (id, category_id, property_id, apartment_id,"
            " is_main_meter, meter_number, has_dual_tariff, is_official)"
            " VALUES (:i, :k, 1, 1, 0, :n, 0, 0)"),
            {"i": kennung, "k": kategorie, "n": nummer})
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('meters')")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('meters')")).all()]
    zaehler = [(z[0], z[1]) for z in db.session.execute(text(
        "SELECT meter_number, heizungsanlage_id FROM meters ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'meters'")).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher, "spalten": spalten,
                  "zaehler": zaehler, "stand": stand, "schema": schema}))
"""


def test_die_zaehlerwanderung_legt_die_spalte_an(tmp_path):
    """Die Spalte steht danach da, mitsamt ihrem Fremdschluessel."""
    datei = tmp_path / "zaehler.db"
    stand = _lauf(CODE_ZAEHLER_WANDERUNG, datei, tmp_path)

    assert "heizungsanlage_id" not in stand["spalten_vorher"]
    assert "heizungsanlage_id" in stand["spalten"]
    assert stand["stand"] == KOPFREVISION
    assert "fk_meters_heizungsanlage" in stand["schema"]


def test_die_zaehlerwanderung_ordnet_keinen_zaehler_zu(tmp_path):
    """Auch der Waermezaehler bleibt ohne Anlage -- raten waere hier teuer.

    Der Grund ist derselbe wie bei e5b2c74f9a16 (D-45): eine geratene
    Zuordnung macht aus einem Zaehler einen Waermezaehler, und NK-049
    verteilt die Heizkosten daraufhin zu 50 bis 70 vom Hundert nach seinem
    Verbrauch statt nach Flaeche. Derselbe Zeitraum bekaeme zwei verschiedene
    Abrechnungen, ohne dass jemand etwas angeordnet haette. Die Zuordnung ist
    eine Angabe des Vermieters.
    """
    datei = tmp_path / "zaehlerbestand.db"
    stand = _lauf(CODE_ZAEHLER_WANDERUNG, datei, tmp_path)

    assert stand["zaehler"] == [["Strom EG", None], ["Waerme EG", None]]


def test_die_zaehlerwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt Spalte und Schluessel zurueck, die Zaehler bleiben."""
    datei = tmp_path / "zaehlerzurueck.db"
    _lauf(CODE_ZAEHLER_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    db.session.execute(text(
        "INSERT INTO heizungsanlagen (id, property_id, name, versorgt,"
        " verbrauchsanteil_prozent, sonderfall_70)"
        " VALUES (1, 1, 'Kessel', 'heizung', 70, 0)"))
    db.session.execute(text(
        "UPDATE meters SET heizungsanlage_id = 1 WHERE id = 2"))
    db.session.commit()

    downgrade(revision="e5b2c74f9a16")

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('meters')")).all()]
    zaehler = [z[0] for z in db.session.execute(text(
        "SELECT meter_number FROM meters ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'meters'")).scalar()

print(json.dumps({"spalten": spalten, "zaehler": zaehler,
                  "stand": stand, "schema": schema}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "e5b2c74f9a16"
    assert "heizungsanlage_id" not in stand["spalten"]
    assert "fk_meters_heizungsanlage" not in stand["schema"]
    assert stand["zaehler"] == ["Strom EG", "Waerme EG"]


# --- NK-050: die Warmwassertrennung an der Anlage (Revision c1d47e93a806) ---

# Baut einen Bestand aus der Zeit vor NK-050 auf: ein Haus mit einer
# verbundenen Anlage, die Heizung und Warmwasser zugleich versorgt. Genau
# der Fall, den § 9 HeizkostenV meint -- und den das Programm bis hierher
# wie eine reine Heizung behandelt hat. Dann wandert die Datenbank nach vorn
# und meldet, was aus der Anlage geworden ist.
CODE_WARMWASSER_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="f3a9c05e8d72")

    db.session.execute(text("DELETE FROM heizungsanlagen"))
    db.session.execute(text("DELETE FROM properties WHERE id = 1"))
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    db.session.execute(text(
        "INSERT INTO heizungsanlagen (id, property_id, name, versorgt,"
        " verbrauchsanteil_prozent, sonderfall_70)"
        " VALUES (1, 1, 'Kessel', 'verbunden', 60, 0)"))
    db.session.execute(text(
        "INSERT INTO heizungsanlagen (id, property_id, name, versorgt,"
        " verbrauchsanteil_prozent, sonderfall_70)"
        " VALUES (2, 1, 'Hinterhaus', 'heizung', 70, 1)"))
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('heizungsanlagen')")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('heizungsanlagen')")).all()]
    anlagen = [tuple(z) for z in db.session.execute(text(
        "SELECT name, versorgt, verbrauchsanteil_prozent, sonderfall_70,"
        " warmwasser_weg, warmwasser_kwh, warmwasser_volumen_m3,"
        " warmwasser_temperatur_c, brennstoff_menge, heizwert_kwh"
        " FROM heizungsanlagen ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'heizungsanlagen'")).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher, "spalten": spalten,
                  "anlagen": anlagen, "stand": stand, "schema": schema}))
"""


def test_die_warmwasserwanderung_legt_die_sechs_spalten_an(tmp_path):
    """Die Felder des § 9 stehen danach an der Anlage, der Stempel auch."""
    datei = tmp_path / "warmwasser.db"
    stand = _lauf(CODE_WARMWASSER_WANDERUNG, datei, tmp_path)

    neu = ("warmwasser_weg", "warmwasser_kwh", "warmwasser_volumen_m3",
           "warmwasser_temperatur_c", "brennstoff_menge", "heizwert_kwh")
    for spalte in neu:
        assert spalte not in stand["spalten_vorher"]
        assert spalte in stand["spalten"]
    assert stand["stand"] == KOPFREVISION


def test_die_warmwasserwanderung_traegt_nichts_ein(tmp_path):
    """Auch die verbundene Anlage bleibt ohne Trennungsangaben.

    Der Grund ist derselbe wie bei e5b2c74f9a16 und f3a9c05e8d72: eine
    geratene Warmwassermenge verschoebe die naechste Abrechnung gegenueber
    der des Vorjahres, ohne dass jemand sie angeordnet haette. Was die
    Anlage vorher hatte -- Versorgungsart, Anteil, Sonderfall -- steht
    unveraendert da.
    """
    datei = tmp_path / "warmwasserbestand.db"
    stand = _lauf(CODE_WARMWASSER_WANDERUNG, datei, tmp_path)

    assert stand["anlagen"] == [
        ["Kessel", "verbunden", 60, 0, None, None, None, None, None, None],
        ["Hinterhaus", "heizung", 70, 1, None, None, None, None, None, None],
    ]


def test_die_warmwasserwanderung_setzt_ihre_drei_bedingungen(tmp_path):
    """Weg, Versorgungsart und Mengen werden in der Datenbank geprueft."""
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "warmwassercheck.db"
    stand = _lauf(CODE_WARMWASSER_WANDERUNG, datei, tmp_path)

    for name in ("ck_heizungsanlagen_ww_weg",
                 "ck_heizungsanlagen_ww_nur_verbunden",
                 "ck_heizungsanlagen_ww_mengen"):
        assert name in stand["schema"]

    verbindung = sqlite3.connect(datei)
    try:
        setzen = "UPDATE heizungsanlagen SET %s WHERE id = 1"
        # Einen vierten Weg gibt es nicht.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(setzen % "warmwasser_weg = 'gefuehlt'")
        # Die Mengen sind positiv oder gar nicht da.
        for daneben in ("warmwasser_kwh = 0", "warmwasser_kwh = -1",
                        "warmwasser_volumen_m3 = -0.5",
                        "brennstoff_menge = 0", "heizwert_kwh = -10"):
            with _pytest.raises(sqlite3.IntegrityError):
                verbindung.execute(setzen % daneben)
        # Unter zehn Grad gaebe die Formel eine negative Waermemenge her.
        for daneben in (10, 4):
            with _pytest.raises(sqlite3.IntegrityError):
                verbindung.execute(
                    setzen % ("warmwasser_temperatur_c = %d" % daneben))

        # Die verbundene Anlage darf alles davon tragen.
        verbindung.execute(setzen % (
            "warmwasser_weg = 'formel', warmwasser_volumen_m3 = 120,"
            " warmwasser_temperatur_c = 60, brennstoff_menge = 95000"))
        # Die reine Heizung nicht: zu trennen gibt es dort nichts.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "UPDATE heizungsanlagen SET warmwasser_weg = 'zaehler'"
                " WHERE id = 2")
    finally:
        verbindung.close()


def test_die_warmwasserwanderung_laesst_die_alten_bedingungen_stehen(tmp_path):
    """Der Neubau der Tabelle darf den Rahmen des § 7 Abs. 1 nicht verlieren.

    SQLite gibt reflektierte CHECK-Bedingungen nicht heraus. Ohne das
    ``copy_from`` in der Wanderung faende dieser Test eine Tabelle vor, in
    der ein Verbrauchsanteil von 200 vom Hundert durchginge -- und niemand
    haette es bemerkt, weil alle Tests gruen blieben.
    """
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "warmwasseraltecks.db"
    stand = _lauf(CODE_WARMWASSER_WANDERUNG, datei, tmp_path)

    for name in ("ck_heizungsanlagen_versorgt",
                 "ck_heizungsanlagen_verbrauchsanteil",
                 "ck_heizungsanlagen_sonderfall"):
        assert name in stand["schema"]

    verbindung = sqlite3.connect(datei)
    try:
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "UPDATE heizungsanlagen SET verbrauchsanteil_prozent = 200"
                " WHERE id = 1")
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "UPDATE heizungsanlagen SET versorgt = 'fernwaerme'"
                " WHERE id = 1")
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(
                "UPDATE heizungsanlagen SET sonderfall_70 = 1 WHERE id = 1")
    finally:
        verbindung.close()


def test_die_warmwasserwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die sechs Spalten zurueck, die Anlagen bleiben.

    Und auch hier ueberleben die drei alten Bedingungen den Neubau: der
    Rueckweg baut die Tabelle genauso neu wie der Hinweg.
    """
    datei = tmp_path / "warmwasserzurueck.db"
    _lauf(CODE_WARMWASSER_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    db.session.execute(text(
        "UPDATE heizungsanlagen SET warmwasser_weg = 'zaehler',"
        " warmwasser_kwh = 15000, brennstoff_menge = 95000 WHERE id = 1"))
    db.session.commit()

    downgrade(revision="f3a9c05e8d72")

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('heizungsanlagen')")).all()]
    anlagen = [tuple(z) for z in db.session.execute(text(
        "SELECT name, versorgt, verbrauchsanteil_prozent, sonderfall_70"
        " FROM heizungsanlagen ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'heizungsanlagen'")).scalar()

print(json.dumps({"spalten": spalten, "anlagen": anlagen,
                  "stand": stand, "schema": schema}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "f3a9c05e8d72"
    for spalte in ("warmwasser_weg", "warmwasser_kwh", "warmwasser_volumen_m3",
                   "warmwasser_temperatur_c", "brennstoff_menge",
                   "heizwert_kwh"):
        assert spalte not in stand["spalten"]
    assert stand["anlagen"] == [
        ["Kessel", "verbunden", 60, 0],
        ["Hinterhaus", "heizung", 70, 1],
    ]
    for name in ("ck_heizungsanlagen_versorgt",
                 "ck_heizungsanlagen_verbrauchsanteil",
                 "ck_heizungsanlagen_sonderfall"):
        assert name in stand["schema"]


CODE_ZWISCHENABLESUNG_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="c1d47e93a806")

    db.session.execute(text("DELETE FROM meter_readings"))
    db.session.execute(text("DELETE FROM meters WHERE id = 1"))
    db.session.execute(text("DELETE FROM properties WHERE id = 1"))
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    kategorie = db.session.execute(text(
        "SELECT id FROM cost_categories WHERE betrkv_nr = 4 LIMIT 1")).scalar()
    db.session.execute(text(
        "INSERT INTO meters (id, property_id, category_id, meter_number,"
        " is_main_meter, has_dual_tariff, is_official)"
        " VALUES (1, 1, :k, 'W-1', 0, 0, 0)"), {"k": kategorie})
    for kennung, tag, wert in ((1, "2024-01-01", 100.0), (2, "2024-12-31", 900.0)):
        db.session.execute(text(
            "INSERT INTO meter_readings"
            " (id, meter_id, reading_date, value, is_official_invoice)"
            " VALUES (:i, 1, :t, :w, 0)"),
            {"i": kennung, "t": tag, "w": wert})
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('meter_readings')")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('meter_readings')")).all()]
    staende = [tuple(z) for z in db.session.execute(text(
        "SELECT reading_date, value, ablesungsart"
        " FROM meter_readings ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'meter_readings'")).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher, "spalten": spalten,
                  "staende": staende, "stand": stand, "schema": schema}))
"""


def test_die_zwischenablesungswanderung_legt_die_spalte_an(tmp_path):
    """Die Art steht danach am Stand, der Stempel auch."""
    datei = tmp_path / "zwischenablesung.db"
    stand = _lauf(CODE_ZWISCHENABLESUNG_WANDERUNG, datei, tmp_path)

    assert "ablesungsart" not in stand["spalten_vorher"]
    assert "ablesungsart" in stand["spalten"]
    assert stand["stand"] == KOPFREVISION


def test_die_zwischenablesungswanderung_gibt_dem_altbestand_die_ablesung(tmp_path):
    """Jeder Stand des Altbestands ist die gewoehnliche Ablesung.

    Der Grund ist derselbe wie bei den Wanderungen davor: eine Art, die
    diese Wanderung raete, wuerde beim naechsten Lauf nach Verbrauch
    verteilen -- die Zwischenablesung ist der einzige Messwert der Grenze
    zwischen zwei Mietverhaeltnissen, und den setzt, wer ihn macht.
    """
    datei = tmp_path / "zwischenablesungbestand.db"
    stand = _lauf(CODE_ZWISCHENABLESUNG_WANDERUNG, datei, tmp_path)

    assert stand["staende"] == [
        ["2024-01-01", 100.0, "ablesung"],
        ["2024-12-31", 900.0, "ablesung"],
    ]


def test_die_zwischenablesungswanderung_haelt_die_art_fest(tmp_path):
    """Zwei Arten gibt es, und die Datenbank prueft sie."""
    import sqlite3

    import pytest as _pytest

    datei = tmp_path / "zwischenablesungcheck.db"
    stand = _lauf(CODE_ZWISCHENABLESUNG_WANDERUNG, datei, tmp_path)

    assert "ck_meter_readings_ablesungsart" in stand["schema"]

    verbindung = sqlite3.connect(datei)
    try:
        setzen = "UPDATE meter_readings SET ablesungsart = '%s' WHERE id = 1"
        verbindung.execute(setzen % "zwischenablesung")
        verbindung.execute(setzen % "ablesung")
        # Eine dritte Art gibt es nicht.
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(setzen % "gefuehlt")
        with _pytest.raises(sqlite3.IntegrityError):
            verbindung.execute(setzen % "")
    finally:
        verbindung.close()


def test_die_zwischenablesungswanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die Spalte und den CHECK zurueck."""
    datei = tmp_path / "zwischenablesungzurueck.db"
    _lauf(CODE_ZWISCHENABLESUNG_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="c1d47e93a806")

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('meter_readings')")).all()]
    staende = [tuple(z) for z in db.session.execute(text(
        "SELECT reading_date, value FROM meter_readings ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"spalten": spalten, "staende": staende, "stand": stand}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "c1d47e93a806"
    assert "ablesungsart" not in stand["spalten"]
    assert stand["staende"] == [
        ["2024-01-01", 100.0],
        ["2024-12-31", 900.0],
    ]


CODE_FRIST_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="b8e2f41a90c3")

    # Der Bestand, an dem die Frist nachgerechnet wird: zwei Abrechnungen
    # desselben Mieters, einer davon mit dem Schalttag als Zeitraumende.
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    db.session.execute(text(
        "INSERT INTO apartments (id, property_id, name, sqm, is_active)"
        " VALUES (1, 1, 'EG links', 60.0, 1)"))
    db.session.execute(text(
        "INSERT INTO tenants (id, apartment_id, name, move_in_date)"
        " VALUES (1, 1, 'Fristmieter', '2024-01-01')"))
    for kennung, ende in ((1, "2024-02-29"), (2, "2025-12-31")):
        db.session.execute(text(
            "INSERT INTO tenant_billing_reports"
            " (id, tenant_id, start_date, end_date, created_at)"
            " VALUES (:i, 1, '2024-01-01', :e, '2026-09-01')"),
            {"i": kennung, "e": ende})
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('tenant_billing_reports')")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('tenant_billing_reports')")).all()]
    berichte = [tuple(z) for z in db.session.execute(text(
        "SELECT end_date, frist_ende, zugestellt_am"
        " FROM tenant_billing_reports ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'tenant_billing_reports'"
    )).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher, "spalten": spalten,
                  "berichte": berichte, "stand": stand, "schema": schema}))
"""


def test_die_fristwanderung_legt_die_spalten_an(tmp_path):
    """Fristende und Zustelldatum stehen danach am Bericht."""
    datei = tmp_path / "frist.db"
    stand = _lauf(CODE_FRIST_WANDERUNG, datei, tmp_path)

    assert "frist_ende" not in stand["spalten_vorher"]
    assert "frist_ende" in stand["spalten"]
    assert "zugestellt_am" not in stand["spalten_vorher"]
    assert "zugestellt_am" in stand["spalten"]
    assert stand["stand"] == KOPFREVISION


def test_die_fristwanderung_rechnet_den_altbestand_nach(tmp_path):
    """AZ-Ende + 12 Monate, kalendergerecht (§ 188 Abs. 2 BGB).

    Der 29.02.2024 fuehrt zum 28.02.2025 -- die naive Rechnung
    ``date(end_date, '+1 year')`` von SQLite wuerde auf den 01.03.2025
    rollen, und genau darum laeuft die Nachrechnung in Python."""
    datei = tmp_path / "fristbestand.db"
    stand = _lauf(CODE_FRIST_WANDERUNG, datei, tmp_path)

    assert stand["berichte"] == [
        ["2024-02-29", "2025-02-28", None],
        ["2025-12-31", "2026-12-31", None],
    ]


def test_die_fristwanderung_zaemt_die_tuer_zu(tmp_path):
    """Jede Abrechnung hat ein Fristende -- NULL waere eine Luecke, keine
    Angabe. Das Zustelldatum bleibt dagegen optional."""
    datei = tmp_path / "fristnichtnull.db"
    stand = _lauf(CODE_FRIST_WANDERUNG, datei, tmp_path)

    assert "frist_ende DATE NOT NULL" in stand["schema"]
    assert "zugestellt_am DATE" in stand["schema"]


def test_die_fristwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt beide Spalten zurueck."""
    datei = tmp_path / "fristzurueck.db"
    _lauf(CODE_FRIST_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="b8e2f41a90c3")

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('tenant_billing_reports')")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"spalten": spalten, "stand": stand}))
"""
    datei = tmp_path / "fristzurueck2.db"
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "b8e2f41a90c3"
    assert "frist_ende" not in stand["spalten"]
    assert "zugestellt_am" not in stand["spalten"]


# --- Die Dualtarif-Wanderung (NK-055) ----------------------------------------

CODE_DUALTARIF_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="c7e1a9f30d42")

    # Ein Altbestand ohne Tarifpreise: seine Rechnungen bleiben Einheitstarif.
    # Die Kategorien stammen aus dem Seed des ersten Starts; die IDs hier
    # sind bewusst hoch, um nicht mit ihm zu kollidieren.
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (500, 'Tarifhaus', 0)"))
    db.session.execute(text(
        "INSERT INTO cost_invoices (id, category_id, property_id, amount,"
        " start_date, end_date)"
        " SELECT 9001, MIN(id), 500, 460.0, '2026-01-01', '2026-12-31'"
        " FROM cost_categories"))
    db.session.commit()

    spalten_vorher = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]
    preise = [tuple(z) for z in db.session.execute(text(
        "SELECT amount, preis_ht, preis_nt FROM cost_invoices"
        " ORDER BY id")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'cost_invoices'"
    )).scalar()

print(json.dumps({"spalten_vorher": spalten_vorher, "spalten": spalten,
                  "preise": preise, "stand": stand, "schema": schema}))
"""


def test_die_dualtarifwanderung_legt_die_preise_an(tmp_path):
    """preis_ht und preis_nt stehen danach an der Rechnung -- NULL beim Altbestand."""
    datei = tmp_path / "dualtarif.db"
    stand = _lauf(CODE_DUALTARIF_WANDERUNG, datei, tmp_path)

    assert "preis_ht" not in stand["spalten_vorher"]
    assert "preis_ht" in stand["spalten"]
    assert "preis_nt" not in stand["spalten_vorher"]
    assert "preis_nt" in stand["spalten"]
    # Der Altbestand hat keinen Preis je Tarif: aus einem NULL wird nichts geraten.
    assert stand["preise"] == [[460.0, None, None]]
    assert stand["stand"] == KOPFREVISION


def test_die_dualtarifwanderung_zaemt_sich_zu(tmp_path):
    """Beide Preise gehören zusammen und keines ist negativ."""
    datei = tmp_path / "dualtarifzaun.db"
    stand = _lauf(CODE_DUALTARIF_WANDERUNG, datei, tmp_path)

    assert "ck_cost_invoices_dualtarif_vollstaendig" in stand["schema"]
    assert "ck_cost_invoices_dualtarif_nichtnegativ" in stand["schema"]


def test_die_dualtarifwanderung_haelt_die_beiden_regeln_ein(tmp_path):
    """Ein Preis ohne seinen Partner und ein negativer Preis werden abgewiesen."""
    datei = tmp_path / "dualtarifregeln.db"
    _lauf(CODE_DUALTARIF_WANDERUNG, datei, tmp_path)
    code = """
import json
from sqlalchemy import text
import app as anwendung
from nebenkostenfix.models import db

fehler = []
with anwendung.app.app_context():
    for name, sql in (
        ("halb", "UPDATE cost_invoices SET preis_ht = 0.4 WHERE id = 9001"),
        ("negativ", "UPDATE cost_invoices SET preis_ht = -0.4, preis_nt = 0.3"
         " WHERE id = 9001"),
    ):
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception as ausnahme:
            db.session.rollback()
            fehler.append(name)

print(json.dumps({"fehler": fehler}))
"""
    stand = _lauf(code, datei, tmp_path)

    assert stand["fehler"] == ["halb", "negativ"]


def test_die_dualtarifwanderung_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt beide Preise zurueck."""
    datei = tmp_path / "dualtarifzurueck.db"
    _lauf(CODE_DUALTARIF_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="c7e1a9f30d42")

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('cost_invoices')")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()

print(json.dumps({"spalten": spalten, "stand": stand}))
"""
    datei = tmp_path / "dualtarifzurueck2.db"
    stand = _lauf(code, datei, tmp_path)

    assert stand["stand"] == "c7e1a9f30d42"
    assert "preis_ht" not in stand["spalten"]
    assert "preis_nt" not in stand["spalten"]


CODE_VERSION_WANDERUNG = """
import json
from sqlalchemy import text
from flask_migrate import downgrade, upgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="d4e6f8a90b12")

    # Der Altbestand: eine Abrechnung aus der Zeit vor der Versionstabelle.
    db.session.execute(text(
        "INSERT INTO properties (id, name, is_standalone) VALUES (1, 'Altbau', 0)"))
    db.session.execute(text(
        "INSERT INTO apartments (id, property_id, name, sqm, is_active)"
        " VALUES (1, 1, 'EG links', 60.0, 1)"))
    db.session.execute(text(
        "INSERT INTO tenants (id, apartment_id, name, move_in_date)"
        " VALUES (1, 1, 'Versionsmieter', '2024-01-01')"))
    db.session.execute(text(
        "INSERT INTO tenant_billing_reports"
        " (id, tenant_id, start_date, end_date, created_at, frist_ende)"
        " VALUES (1, 1, '2024-01-01', '2024-12-31', '2026-09-01', '2025-12-31')"))
    db.session.commit()

    upgrade()

    spalten = [z[1] for z in db.session.execute(
        text("PRAGMA table_info('billing_report_versions')")).all()]
    stand = db.session.execute(
        text("SELECT version_num FROM alembic_version")).scalar()
    schema = db.session.execute(text(
        "SELECT sql FROM sqlite_master WHERE name = 'billing_report_versions'"
    )).scalar()
    berichte = db.session.execute(
        text("SELECT COUNT(*) FROM tenant_billing_reports")).scalar()
    versionen = db.session.execute(
        text("SELECT COUNT(*) FROM billing_report_versions")).scalar()

print(json.dumps({"spalten": spalten, "stand": stand, "schema": schema,
                  "berichte": berichte, "versionen": versionen}))
"""


def test_die_versionstabelle_legt_sich_an(tmp_path):
    """Die Versionstabelle steht danach, der Altbestand bleibt ohne Version
    -- aus dem nichts zu raten ist derselbe Grundsatz wie bei der
    Heizkostenart; die Detailroute rechnet für ihn weiter live (D-59)."""
    datei = tmp_path / "versionen.db"
    stand = _lauf(CODE_VERSION_WANDERUNG, datei, tmp_path)

    for spalte in ("id", "report_id", "nummer", "eingangsdaten", "ergebnis",
                   "software_version", "regel_version", "erstellt_am",
                   "ersetzt_version_id"):
        assert spalte in stand["spalten"]
    assert stand["stand"] == KOPFREVISION
    assert "UNIQUE" in stand["schema"] and "uq_version_pro_abrechnung" in stand["schema"]
    assert stand["berichte"] == 1
    assert stand["versionen"] == 0


def test_die_versionstabelle_laesst_sich_zurueckdrehen(tmp_path):
    """downgrade() nimmt die Tabelle ganz zurück."""
    datei = tmp_path / "versionenzurueck.db"
    _lauf(CODE_VERSION_WANDERUNG, datei, tmp_path)

    code = """
import json
from sqlalchemy import text
from flask_migrate import downgrade
import app as anwendung
from nebenkostenfix.models import db

with anwendung.app.app_context():
    downgrade(revision="d4e6f8a90b12")

    tabellen = [z[0] for z in db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table'")).all()]

print(json.dumps({"tabellen": tabellen}))
"""
    stand = _lauf(code, datei, tmp_path)
    assert "billing_report_versions" not in stand["tabellen"]
