"""NK-019: deny-by-default, Positivliste, fail-closed SECRET_KEY.

Vor dieser Karte war jede der 55 Routen ohne Anmeldung erreichbar, inklusive
Dateileser und Export. Diese Tests halten die Sperre fest.
"""

from __future__ import annotations

import os

import pytest

import auth
from auth import AuthConfigError, PUBLIC_ENDPOINTS, _loese_secret_key
from models import User, db

from tests.conftest import TEST_PASSWORD, TEST_USER


# --- Sperre ---

def test_fachroute_ohne_anmeldung_ist_401(anon_client):
    res = anon_client.get("/api/properties")
    assert res.status_code == 401
    assert res.get_json()["code"] == "auth_required"


def test_fachroute_mit_anmeldung_ist_200(auth_client):
    assert auth_client.get("/api/properties").status_code == 200


def test_unbekannter_pfad_verraet_nichts(anon_client):
    """404 wuerde einem Fremden sagen, welche Pfade es gibt."""
    res = anon_client.get("/api/gibt-es-nicht")
    assert res.status_code == 401


def test_schreibende_route_ohne_anmeldung_legt_nichts_an(anon_client):
    res = anon_client.post("/api/properties", json={"name": "Einbruchhaus"})
    assert res.status_code == 401
    from models import Property
    assert Property.query.filter_by(name="Einbruchhaus").first() is None


# --- Positivliste ---

def test_positivliste_ist_genau_diese_drei(app_ctx):
    """Seit NK-021 waren es zwei; NK-127 nahm /einrichtung auf, den ersten
    Start ohne Konto. index und static sind bewusst gefallen."""
    assert PUBLIC_ENDPOINTS == {"health_check", "login", "einrichtung"}


def test_startseite_leitet_ohne_anmeldung_zur_anmeldung(anon_client):
    """Kriterium 1 von NK-021.

    Bis dahin war / offen und lieferte die Oberflaeche aus. Sie lud, blieb
    aber leer, weil jeder /api/-Aufruf darin mit 401 antwortete. Ein Gast sah
    ein kaputtes Programm statt eines Anmeldefeldes.
    """
    res = anon_client.get("/")
    assert res.status_code in (301, 302, 303, 307, 308)
    assert "/login" in res.headers["Location"]


def test_die_oberflaeche_ist_nicht_ueber_static_zu_haben(anon_client):
    """Ohne das waere die Umleitung von / ein Feigenblatt.

    /static/index.html liefert genau dieselbe Seite wie /. Und in app.js
    stehen 188 KB Geschaeftslogik samt jedem Routennamen.
    """
    for pfad in ("/static/index.html", "/static/app.js", "/static/style.css"):
        res = anon_client.get(pfad)
        assert res.status_code != 200, pfad


def test_die_umleitung_haengt_kein_leeres_fragezeichen_an(anon_client):
    """request.full_path liefert '/?' auch ohne Parameter.

    Ohne Zurechtstutzen steht /login?next=/? in der Adresszeile und die
    Anmeldung wirft einen danach auf /? statt auf /.
    """
    res = anon_client.get("/")
    assert res.headers["Location"].endswith("/login?next=/")

    # Echte Parameter bleiben aber stehen.
    res = anon_client.get("/api/properties?jahr=2025")
    assert res.status_code == 401


def test_die_anmeldeseite_braucht_kein_static(anon_client):
    """Sonst haette das Sperren von static das Anmeldefeld unlesbar gemacht."""
    seite = anon_client.get("/login").get_data(as_text=True)
    assert "/static/" not in seite


def test_health_bleibt_ohne_anmeldung_erreichbar(anon_client):
    res = anon_client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_anmeldeseite_bleibt_ohne_anmeldung_erreichbar(anon_client, app_ctx):
    """Ohne Konto (erster Start) leitet die Anmeldung zur Einrichtung, mit
    Konto zeigt sie das Anmeldefeld. Beides ist ohne Sitzung erreichbar
    (NK-127, E-1); gesperrt sein darf keines von beiden."""
    from models import User, db
    assert User.query.count() == 0
    erster = anon_client.get("/login")
    assert erster.status_code in (301, 302, 303, 307, 308)
    assert "/einrichtung" in erster.headers["Location"]

    user = User(username=TEST_USER)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()
    res = anon_client.get("/login")
    assert res.status_code == 200
    assert b"Benutzername" in res.data


# --- Anmelden und abmelden ---

def test_falsches_passwort_gibt_401(app_ctx):
    user = User(username=TEST_USER)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post("/login", json={"username": TEST_USER, "password": "falsch"})
    assert res.status_code == 401
    assert client.get("/api/properties").status_code == 401


def test_unbekannter_benutzer_gibt_401(anon_client):
    res = anon_client.post("/login", json={"username": "niemand", "password": "egal"})
    assert res.status_code == 401


def test_abmelden_beendet_die_sitzung(auth_client):
    """So ruft die Oberflaeche ab: mit ausdruecklichem Accept."""
    assert auth_client.get("/api/properties").status_code == 200
    res = auth_client.post("/logout", headers={"Accept": "application/json"})
    assert res.status_code == 200
    assert auth_client.get("/api/properties").status_code == 401


def test_abmelden_per_formular_landet_auf_der_anmeldung(auth_client):
    """Ohne Accept-Wunsch ist eine Seite die richtige Antwort, kein JSON."""
    assert auth_client.get("/api/properties").status_code == 200
    res = auth_client.post("/logout")
    assert res.status_code in (301, 302, 303, 307, 308)
    assert "/login" in res.headers["Location"]
    assert auth_client.get("/api/properties").status_code == 401


def test_ein_link_auf_logout_meldet_nicht_ab(auth_client):
    """NK-128 (F-57): Ein GET -- ein Bild oder Link auf einer fremden Seite
    -- beendet die Sitzung nicht mehr, er fuehrt zur Oberflaeche zurueck."""
    res = auth_client.get("/logout")
    assert res.status_code in (301, 302, 303, 307, 308)
    assert res.headers["Location"].rstrip('/') in ('', 'http://localhost')
    assert auth_client.get("/api/properties").status_code == 200


def test_stillgelegtes_konto_verliert_die_laufende_sitzung(auth_client):
    assert auth_client.get("/api/properties").status_code == 200
    User.query.filter_by(username=TEST_USER).first().is_active = False
    db.session.commit()
    assert auth_client.get("/api/properties").status_code == 401


def test_auth_me_nennt_den_angemeldeten_benutzer(auth_client):
    res = auth_client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.get_json()["username"] == TEST_USER


# --- Passwoerter ---

def test_passwort_steht_nie_im_klartext_in_der_datenbank(app_ctx):
    user = User(username="hashprobe")
    user.set_password("geheim-und-lang-genug")
    db.session.add(user)
    db.session.commit()

    gelesen = User.query.filter_by(username="hashprobe").first()
    assert "geheim-und-lang-genug" not in gelesen.password_hash
    assert gelesen.password_hash.startswith("scrypt:")
    assert gelesen.check_password("geheim-und-lang-genug")
    assert not gelesen.check_password("geheim-und-lang-genu")


def test_gleiches_passwort_ergibt_zwei_verschiedene_hashes(app_ctx):
    """Ohne Salz waere ein Hash-Vergleich ueber Konten hinweg moeglich."""
    a, b = User(username="a"), User(username="b")
    a.set_password("dasselbe-passwort")
    b.set_password("dasselbe-passwort")
    assert a.password_hash != b.password_hash


# --- Sitzungsschluessel: Umgebung, Datei, Erzeugung (NK-127, E-1) ---
# Frueher brach der Start ohne SECRET_KEY ab (NK-019). Das war fail-closed,
# warf aber jeden Laien auf die Kommandozeile (F-62). Jetzt: Umgebung hat
# Vorrang, sonst Datei im Datenordner, sonst erzeugen und ablegen. Abbrechen
# tut der Start nur noch, wenn ein gesetzter Wert unbrauchbar ist.

def _ohne_schluessel(monkeypatch, tmp_path):
    """Umgebung wie ein erster Start: kein SECRET_KEY, Datenordner = tmp_path."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    # Uebergangsweg (NK-132): ohne DATA_DIR gilt der Ordner der SQLite-Datei.
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/kasse.db")


def test_ohne_umgebung_entsteht_eine_schluesseldatei(monkeypatch, tmp_path):
    _ohne_schluessel(monkeypatch, tmp_path)
    schluessel, pfad, neu = _loese_secret_key()
    datei = tmp_path / "secret_key"
    assert pfad == str(datei)
    assert datei.read_text() == schluessel
    assert len(schluessel) == 64
    assert neu is True  # der Start soll im Protokoll vom Erzeugen reden


def test_die_schluesseldatei_ist_nur_fuer_den_besitzer_lesbar(monkeypatch, tmp_path):
    _ohne_schluessel(monkeypatch, tmp_path)
    _, pfad, _ = _loese_secret_key()
    if os.name != "posix":
        pytest.skip("Unter Windows schuetzt der Nutzerordner, nicht der Modus (F-81)")
    rechte = os.stat(pfad).st_mode & 0o777
    assert rechte == 0o600


def test_zweiter_start_liest_die_datei_wieder(monkeypatch, tmp_path):
    _ohne_schluessel(monkeypatch, tmp_path)
    erster, pfad, _ = _loese_secret_key()
    zweiter, _, neu = _loese_secret_key()
    assert erster == zweiter  # sonst waeren Cookies nach jedem Neustart wertlos
    assert pfad == str(tmp_path / "secret_key")
    assert neu is False  # der zweite Start erzeugt nichts nach


def test_parallele_starts_lesen_denselben_vollstaendigen_schluessel(
        monkeypatch, tmp_path):
    """F-74: Zwei Arbeiter starten gleichzeitig gegen einen leeren Ordner.
    Bis NK-149 las der Verlierer eine leere oder halbe Datei und startete mit
    einem anderen Schluessel. Jetzt gewinnt genau einer, und alle lesen den
    vollstaendigen Wert."""
    import threading

    _ohne_schluessel(monkeypatch, tmp_path)
    start = threading.Barrier(8)
    ergebnisse, fehler = [], []

    def arbeiter():
        start.wait()
        try:
            ergebnisse.append(_loese_secret_key())
        except Exception as ausnahme:  # pragma: no cover - Befund
            fehler.append(ausnahme)

    faeden = [threading.Thread(target=arbeiter) for _ in range(8)]
    for faden in faeden:
        faden.start()
    for faden in faeden:
        faden.join()
    assert fehler == []
    schluessel = {e[0] for e in ergebnisse}
    assert len(schluessel) == 1
    assert len(next(iter(schluessel))) == 64
    assert sum(1 for e in ergebnisse if e[2]) == 1  # genau einer erzeugt
    # keine Temp-Reste im Datenordner
    assert sorted(p.name for p in tmp_path.iterdir()) == ["secret_key"]


def test_die_umgebung_hat_vorrang_vor_der_datei(monkeypatch, tmp_path):
    _ohne_schluessel(monkeypatch, tmp_path)
    (tmp_path / "secret_key").write_text("b" * 64)
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    schluessel, pfad, neu = _loese_secret_key()
    assert schluessel == "a" * 64
    assert pfad is None
    assert neu is False


def test_echter_wert_in_der_umgebung_geht_durch(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    assert _loese_secret_key() == ("a" * 64, None, False)


def test_beispielwert_in_der_umgebung_bricht_ab(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "default-fallback-secret-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/kasse.db")
    with pytest.raises(AuthConfigError):
        _loese_secret_key()


def test_zu_kurzer_wert_in_der_umgebung_bricht_ab(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "kurz")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/kasse.db")
    with pytest.raises(AuthConfigError):
        _loese_secret_key()


def test_beispielwert_in_der_datei_bricht_ab(monkeypatch, tmp_path):
    _ohne_schluessel(monkeypatch, tmp_path)
    (tmp_path / "secret_key").write_text("secret")
    with pytest.raises(AuthConfigError):
        _loese_secret_key()


def test_leere_datei_bricht_ab(monkeypatch, tmp_path):
    _ohne_schluessel(monkeypatch, tmp_path)
    (tmp_path / "secret_key").write_text("   ")
    with pytest.raises(AuthConfigError) as exc:
        _loese_secret_key()
    assert "ist leer" in str(exc.value)


def test_data_dir_bestimmt_den_ort_des_schluessels(monkeypatch, tmp_path):
    """NK-132: DATA_DIR hat Vorrang vor dem Ordner der Datenbank."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "daten"))
    (tmp_path / "daten").mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/anderswo.db")
    _, pfad, _ = _loese_secret_key()
    assert pfad == str(tmp_path / "daten" / "secret_key")


def test_ohne_erkennbaren_datenordner_bricht_ab(monkeypatch):
    """Kein SQLite, kein NAS: es gibt keinen Ort, an dem der Schluessel den
    Neustart ueberlebt. Dann lieber laut Abbrechen als still jeden Start neu."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://nk:nk@db:5432/nk")
    monkeypatch.delenv("NAS_MOUNT_PATH", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    with pytest.raises(AuthConfigError) as exc:
        _loese_secret_key()
    assert "SECRET_KEY" in str(exc.value)


# --- Cookie-Haerte ---

def test_sitzungscookie_ist_httponly_und_samesite(app_ctx):
    assert app_ctx.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app_ctx.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_secure_flag_haengt_an_der_umgebung(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("SECRET_KEY", "b" * 64)
    monkeypatch.setenv("BEHIND_HTTPS", "1")
    probe = Flask(__name__)
    auth.init_auth(probe)
    assert probe.config["SESSION_COOKIE_SECURE"] is True


# --- Konten ueberleben den Datenbank-Reset ---

def test_reset_db_loescht_die_konten_nicht(monkeypatch, auth_client):
    """drop_all() nahm sonst die Tabelle users mit und sperrte alle aus."""
    monkeypatch.setenv("ENABLE_DEBUG_RESET", "1")
    monkeypatch.setenv("DEBUG_RESET_SECRET", "nk-019-reset")

    res = auth_client.post("/api/debug/reset_db", headers={"X-Debug-Secret": "nk-019-reset"})
    assert res.status_code == 200
    assert User.query.filter_by(username=TEST_USER).first() is not None
    # Die Sitzung laeuft weiter, weil die Id erhalten bleibt.
    assert auth_client.get("/api/properties").status_code == 200


# --- Kontenverwaltung ueber die Kommandozeile ---

def _runner(app_ctx):
    return app_ctx.app.test_cli_runner()


def test_cli_legt_konto_an_und_die_anmeldung_geht(app_ctx):
    res = _runner(app_ctx).invoke(args=["users", "add", "neuer", "--password", "langes-passwort"])
    assert res.exit_code == 0, res.output
    assert "angelegt" in res.output

    client = app_ctx.app.test_client()
    anmeldung = client.post("/login", json={"username": "neuer", "password": "langes-passwort"})
    assert anmeldung.status_code == 200
    assert client.get("/api/properties").status_code == 200


def test_cli_lehnt_doppelten_benutzernamen_ab(app_ctx):
    runner = _runner(app_ctx)
    runner.invoke(args=["users", "add", "doppelt", "--password", "langes-passwort"])
    res = runner.invoke(args=["users", "add", "doppelt", "--password", "anderes-passwort"])
    assert res.exit_code != 0
    assert "gibt es schon" in res.output


def test_cli_lehnt_kurzes_passwort_ab(app_ctx):
    res = _runner(app_ctx).invoke(args=["users", "add", "kurz", "--password", "kurz"])
    assert res.exit_code != 0
    assert "10 Zeichen" in res.output
    assert User.query.filter_by(username="kurz").first() is None


def test_cli_aendert_das_passwort(app_ctx):
    runner = _runner(app_ctx)
    runner.invoke(args=["users", "add", "wechsler", "--password", "erstes-passwort"])
    res = runner.invoke(args=["users", "passwd", "wechsler", "--password", "zweites-passwort"])
    assert res.exit_code == 0, res.output

    client = app_ctx.app.test_client()
    assert client.post("/login", json={"username": "wechsler", "password": "erstes-passwort"}).status_code == 401
    assert client.post("/login", json={"username": "wechsler", "password": "zweites-passwort"}).status_code == 200


def test_cli_passwd_meldet_unbekanntes_konto(app_ctx):
    res = _runner(app_ctx).invoke(args=["users", "passwd", "niemand", "--password", "langes-passwort"])
    assert res.exit_code != 0
    assert "gibt es nicht" in res.output


def test_cli_passwd_lehnt_kurzes_passwort_ab(app_ctx):
    runner = _runner(app_ctx)
    runner.invoke(args=["users", "add", "kurzwechsel", "--password", "erstes-passwort"])
    res = runner.invoke(args=["users", "passwd", "kurzwechsel", "--password", "kurz"])
    assert res.exit_code != 0
    assert "10 Zeichen" in res.output


def test_cli_list_ohne_konto_sagt_wie_es_geht(app_ctx):
    res = _runner(app_ctx).invoke(args=["users", "list"])
    assert res.exit_code == 0
    assert "flask users add" in res.output


def test_cli_list_zeigt_konten_mit_zustand(app_ctx):
    runner = _runner(app_ctx)
    runner.invoke(args=["users", "add", "sichtbar", "--password", "langes-passwort"])
    res = runner.invoke(args=["users", "list"])
    assert "sichtbar" in res.output
    assert "aktiv" in res.output
    assert "nie" in res.output


def test_cli_disable_sperrt_die_anmeldung(app_ctx):
    runner = _runner(app_ctx)
    runner.invoke(args=["users", "add", "gesperrt", "--password", "langes-passwort"])
    res = runner.invoke(args=["users", "disable", "gesperrt"])
    assert res.exit_code == 0
    assert "stillgelegt" in res.output

    client = app_ctx.app.test_client()
    assert client.post("/login", json={"username": "gesperrt", "password": "langes-passwort"}).status_code == 401


def test_cli_disable_meldet_unbekanntes_konto(app_ctx):
    res = _runner(app_ctx).invoke(args=["users", "disable", "niemand"])
    assert res.exit_code != 0
    assert "gibt es nicht" in res.output


# --- Browserpfade, nicht API ---

def test_browser_wird_zur_anmeldeseite_geschickt(anon_client):
    res = anon_client.get("/logout", headers={"Accept": "text/html"})
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_formularanmeldung_mit_falschem_passwort_zeigt_den_fehler(app_ctx):
    user = User(username="formular")
    user.set_password("langes-passwort")
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post("/login", data={"username": "formular", "password": "falsch"},
                      headers={"Accept": "text/html"})
    assert res.status_code == 401
    assert "stimmt nicht".encode() in res.data


def test_formularanmeldung_leitet_auf_das_ziel_weiter(app_ctx):
    user = User(username="formular2")
    user.set_password("langes-passwort")
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post("/login?next=/api/health",
                      data={"username": "formular2", "password": "langes-passwort"},
                      headers={"Accept": "text/html"})
    assert res.status_code == 302
    assert res.headers["Location"] == "/api/health"


def test_angemeldeter_besucher_sieht_die_anmeldeseite_nicht_mehr(auth_client):
    res = auth_client.get("/login", headers={"Accept": "text/html"})
    assert res.status_code == 302
    assert res.headers["Location"] == "/"


def test_login_required_dekorator_sperrt_auch_ausserhalb(app_ctx):
    """Fuer Routen, die spaeter am before_request vorbeilaufen."""
    from auth import login_required

    aufgerufen = []

    @login_required
    def geschuetzt():
        aufgerufen.append(True)
        return "geheim"

    with app_ctx.app.test_request_context("/api/irgendwas"):
        antwort, status = geschuetzt()
        assert status == 401
        assert aufgerufen == []


# ---------------------------------------------------------------------------
# next-Parameter: keine offene Umleitung (NK-021)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("boeses_ziel", [
    "https://boese.example/",
    "//boese.example/",
    "/\\boese.example",
    "http://boese.example",
    "javascript:alert(1)",
    "boese.example",
])
def test_next_fuehrt_niemals_aus_dem_programm_heraus(app_ctx, boeses_ziel):
    """Der Wert kommt vom Aufrufer, und der baut sich seinen Link selbst.

    Ohne die Pruefung landet der Gast nach einer echten, erfolgreichen
    Anmeldung auf einer fremden Seite und merkt den Wechsel nicht, weil er
    gerade sein Passwort auf der richtigen Seite eingegeben hat.
    """
    from models import User, db

    user = User(username="umleitungstest")
    user.set_password("passwort-fuer-test")
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post(
        "/login?next=" + boeses_ziel,
        data={"username": "umleitungstest", "password": "passwort-fuer-test"},
    )
    assert res.status_code in (301, 302, 303, 307, 308)
    ziel = res.headers["Location"]
    assert ziel == "/", ziel


def test_next_behaelt_ein_ziel_innerhalb_des_programms(app_ctx):
    """Die Umleitung soll ja etwas nuetzen: zurueck, wo man hinwollte."""
    from models import User, db

    user = User(username="umleitungstest2")
    user.set_password("passwort-fuer-test")
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post(
        "/login?next=/api/properties",
        data={"username": "umleitungstest2", "password": "passwort-fuer-test"},
    )
    assert res.headers["Location"] == "/api/properties"


def test_next_auf_die_anmeldung_selbst_landet_auf_der_startseite(app_ctx):
    """Sonst steht man nach dem Anmelden wieder vor dem Anmeldefeld."""
    from models import User, db

    user = User(username="umleitungstest3")
    user.set_password("passwort-fuer-test")
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    res = client.post(
        "/login?next=/login%3Fnext%3D/",
        data={"username": "umleitungstest3", "password": "passwort-fuer-test"},
    )
    assert res.headers["Location"] == "/"


# ---------------------------------------------------------------------------
# Gegenprobe: angemeldet muss die Oberflaeche vollstaendig laden
# ---------------------------------------------------------------------------

def test_angemeldet_liefert_die_startseite_die_oberflaeche(auth_client):
    res = auth_client.get("/")
    assert res.status_code == 200
    assert "app.js" in res.get_data(as_text=True)


@pytest.mark.parametrize("pfad", [
    "/static/index.html",
    "/static/app.js",
    "/static/style.css",
])
def test_angemeldet_laden_die_dateien_der_oberflaeche(auth_client, pfad):
    """Das Sperren von static darf die Anwendung nicht selbst lahmlegen."""
    assert auth_client.get(pfad).status_code == 200
