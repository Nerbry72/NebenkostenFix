"""Isolate pytest from NAS/CIFS and the real SQLite file.

Must run before any `import app` / NASHandler: app.py calls load_dotenv()
(does not override existing env) then schema_aktualisieren() + seed (NK-024),
and NASHandler mkdirs NAS_MOUNT_PATH. Compose injects the sandbox mount and
sqlite:////app/data/nebenkosten.db — overwrite both here.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="nk-pytest-"))
_NAS = _TEST_ROOT / "nas"
_PDF = _TEST_ROOT / "pdfs"
_TMP = _TEST_ROOT / "temp"
_DB = _TEST_ROOT / "test.db"

for _p in (_NAS, _PDF, _TMP):
    _p.mkdir(parents=True, exist_ok=True)

# NK-132: ein Datenordner. NAS_MOUNT_PATH bleibt als Alias gesetzt (eine
# Version lang), weil etliche Tests den Belegordner darueber lesen.
os.environ["DATA_DIR"] = str(_TEST_ROOT)
os.environ["NAS_MOUNT_PATH"] = str(_NAS)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
# Die Umgebung genuegt: SECRET_KEY gesetzt heißt, keine Schluesseldatei im
# Datenordner der Test-DB (NK-127).
os.environ["SECRET_KEY"] = "nkfix-pytest-secret-key-nur-fuer-tests"
os.environ["FLASK_ENV"] = "testing"
# NK-128: keine Wartezeit nach Fehlversuchen im Testlauf; die Rechnung
# selbst prueft tests/test_web_haertung.py.
os.environ["LOGIN_VERZOEGERUNG_S"] = "0"
os.environ["LOCAL_PDF_PATH"] = str(_PDF)
os.environ["LOCAL_TEMP_PATH"] = str(_TMP)
# Do not enable the unprotected reset_db path in default tests (NK-001).
os.environ.pop("ENABLE_DEBUG_RESET", None)

import pytest


@pytest.fixture
def app_ctx():
    """Fresh schema + category seed on the temp SQLite for each test.

    Weiterhin create_all() statt der Wanderung: das ist pro Test deutlich
    schneller. Zulaessig ist es nur, weil tests/test_migrations.py misst, dass
    Wanderung und models.py dasselbe Schema ergeben.
    """
    import anmeldeschutz
    import app as app_module
    import auth
    from models import db

    # NK-128: der Zaehler der Fehlversuche liegt im Datenordner und
    # ueberlebte sonst den Test -- nach 20 Fehlversuchen im ganzen Lauf
    # waere 127.0.0.1 gesperrt.
    anmeldeschutz.zuruecksetzen(auth._anmeldeschutz_ordner())
    anmeldeschutz.zuruecksetzen(None)
    with app_module.app.app_context():
        db.drop_all()
        db.create_all()
        app_module.seed_database()
        yield app_module
        db.session.remove()


TEST_USER = "pytest-vermieter"
TEST_PASSWORD = "pytest-passwort-1"


@pytest.fixture
def auth_client(app_ctx):
    """Angemeldeter Testclient (NK-019).

    Seit deny-by-default antwortet jede Route ausser der Positivliste mit 401.
    Tests, die eine Fachroute aufrufen, brauchen eine Sitzung. Das Konto wird
    innerhalb von app_ctx angelegt, weil app_ctx vorher drop_all() faehrt.
    """
    from models import User, db

    user = User(username=TEST_USER)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post(
        "/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    return client


@pytest.fixture
def anon_client(app_ctx):
    """Nicht angemeldeter Testclient."""
    return app_ctx.app.test_client()


@pytest.fixture(autouse=True)
def kein_update_netz(monkeypatch):
    """Kein Test fragt GitHub nach Updates (NK-175).

    Mit eingebautem Herausgeberschlüssel ginge ``/api/aktualisierung`` sonst
    wirklich ins Netz. Wer ein Manifest braucht, gibt ``laden`` mit oder
    setzt ``_laden`` selbst. Die Fixture liefert das echte ``_laden``.
    """
    import aktualisierung

    echt = aktualisierung._laden

    def kein_netz(adresse, grenze, zeit=20):
        raise aktualisierung.AktualisierungsFehler('Tests laden nichts aus dem Netz.')
    monkeypatch.setattr(aktualisierung, '_laden', kein_netz)
    return echt
