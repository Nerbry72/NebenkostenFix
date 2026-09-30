"""NK-001: POST /api/debug/reset_db is gated (404/401) and does not wipe on deny."""

from __future__ import annotations

import os
from pathlib import Path

RESET_URL = "/api/debug/reset_db"
KEEP_NAME = "NK001-KeepMe"


# Seit NK-019 ist jede Fachroute gesperrt. Diese Tests brauchen eine Sitzung,
# sonst antwortet /api/properties mit 401 statt mit den Nutzdaten und der Test
# prueft nicht mehr, was er pruefen soll.


def _nas_keep_file() -> Path:
    nas = Path(os.environ["NAS_MOUNT_PATH"])
    nas.mkdir(parents=True, exist_ok=True)
    path = nas / "nk001-keep.txt"
    path.write_text("do-not-wipe", encoding="utf-8")
    return path


def test_reset_db_without_flag_returns_404(monkeypatch, auth_client):
    monkeypatch.delenv("ENABLE_DEBUG_RESET", raising=False)
    monkeypatch.delenv("DEBUG_RESET_SECRET", raising=False)
    res = auth_client.post(RESET_URL)
    assert res.status_code == 404


def test_reset_db_without_flag_does_not_drop_property(monkeypatch, auth_client):
    monkeypatch.delenv("ENABLE_DEBUG_RESET", raising=False)
    monkeypatch.delenv("DEBUG_RESET_SECRET", raising=False)
    client = auth_client
    created = client.post("/api/properties", json={"name": KEEP_NAME})
    assert created.status_code == 201
    prop_id = created.get_json()["id"]

    res = client.post(RESET_URL)
    assert res.status_code == 404

    listing = client.get("/api/properties")
    assert listing.status_code == 200
    names = {row["name"] for row in listing.get_json()}
    ids = {row["id"] for row in listing.get_json()}
    assert KEEP_NAME in names
    assert prop_id in ids


def test_reset_db_without_flag_does_not_wipe_nas(monkeypatch, auth_client):
    monkeypatch.delenv("ENABLE_DEBUG_RESET", raising=False)
    monkeypatch.delenv("DEBUG_RESET_SECRET", raising=False)
    keep = _nas_keep_file()
    res = auth_client.post(RESET_URL)
    assert res.status_code == 404
    assert keep.is_file()
    assert keep.read_text(encoding="utf-8") == "do-not-wipe"


def test_reset_db_flag_without_secret_returns_401_no_wipe(monkeypatch, auth_client):
    monkeypatch.setenv("ENABLE_DEBUG_RESET", "1")
    monkeypatch.setenv("DEBUG_RESET_SECRET", "nkfix-reset-secret")
    client = auth_client
    created = client.post("/api/properties", json={"name": KEEP_NAME + "-401"})
    assert created.status_code == 201
    keep = _nas_keep_file()

    res = client.post(RESET_URL)
    assert res.status_code == 401

    listing = client.get("/api/properties")
    names = {row["name"] for row in listing.get_json()}
    assert KEEP_NAME + "-401" in names
    assert keep.is_file()
    assert keep.read_text(encoding="utf-8") == "do-not-wipe"


def test_reset_db_authorized_resets_db_and_reseeds(monkeypatch, auth_client):
    secret = "nkfix-reset-secret"
    monkeypatch.setenv("ENABLE_DEBUG_RESET", "1")
    monkeypatch.setenv("DEBUG_RESET_SECRET", secret)
    client = auth_client
    created = client.post("/api/properties", json={"name": "NK001-WipeMe"})
    assert created.status_code == 201

    res = client.post(RESET_URL, headers={"X-Debug-Secret": secret})
    assert res.status_code == 200

    listing = client.get("/api/properties")
    assert listing.status_code == 200
    names = {row["name"] for row in listing.get_json()}
    assert "NK001-WipeMe" not in names

    categories = client.get("/api/categories")
    assert categories.status_code == 200
    cat_names = {row["name"] for row in categories.get_json()}
    # Seit NK-044 legt der Seed die siebzehn Nummern aus § 2 BetrKV an; der
    # frei gewaehlte Name „Strom" ist dabei zur amtlichen Nr. 11 geworden.
    # NK-117 (D-72): die Nr. 3 traegt zwei Eintraege, Entwaesserung und
    # Niederschlagswasser -- achtzehn Namen.
    assert len(cat_names) == 18
    assert "Niederschlagswasser" in cat_names
    assert "Beleuchtung (Allgemeinstrom)" in cat_names


# --- NK-123: der Knopf folgt der Route, nicht einer Umgebungsvariablen -----


def test_ohne_entwicklerroute_ist_kein_entwicklermodus():
    """Eine Anwendung ohne /api/debug/reset_db meldet keinen Entwicklermodus.

    Ein nacktes Flask-Objekt genügt: der Helfer fragt die Routentabelle
    ab, nichts weiter. Genau so sieht die laufende Anwendung im
    Auslieferungsbuild aus -- die Datei fehlt, die Route existiert nicht.
    """
    from nebenkostenfix.auth import entwicklung_angemeldet
    from flask import Flask

    nacktes_app = Flask(__name__)
    assert entwicklung_angemeldet(nacktes_app) is False


def test_mit_entwicklerroute_ist_entwicklermodus_angemeldet():
    """Im Entwicklungsstapel ist die Route da, der Helfer meldet das."""
    from nebenkostenfix.auth import entwicklung_angemeldet
    from flask import Flask

    entwickler_app = Flask(__name__)

    @entwickler_app.route('/api/debug/reset_db', methods=['POST'])
    def reset_db():
        return '', 204

    assert entwicklung_angemeldet(entwickler_app) is True


def test_auth_me_nennt_den_entwicklermodus(auth_client):
    """/api/auth/me verrät der Oberfläche, ob der Knopf gezeigt werden darf.

    Im Teststapel ist debug_routen.py importierbar, also ist die Route
    angemeldet und die Meldung wahr. Im Auslieferungsbuild fehlt die Datei
    (.dockerignore, NK-040) und dieselbe Antwort lautet falsch.
    """
    res = auth_client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.get_json()["entwicklung"] is True
