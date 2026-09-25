"""Zentrale Fehlerbehandlung und Protokoll (NK-030).

Vorher endete jeder unvorhergesehene Fehler entweder in einem ``print`` auf
stdout oder als englischer Ausnahmetext im ``error``-Feld -- und die
Datenbanksitzung blieb dabei offen stehen. Diese Tests halten die vier
Zusagen der Karte fest:

1. Es wird zurueckgerollt.
2. Die Antwort ist ein deutscher Satz mit einer Vorgangsnummer.
3. Dieselbe Nummer steht im Protokoll, mitsamt Stapelabzug.
4. In der Antwort steht kein Stapelabzug und kein Innenleben.

Der Mitschnitt haengt direkt am Logger ``nebenkosten``: ``caplog`` sieht
nichts, weil ``init_protokoll`` bewusst ``propagate = False`` setzt.
"""

from __future__ import annotations

import logging

import pytest
from werkzeug.exceptions import HTTPException

import fehler


# Der Wortlaut, den eine geplatzte Anweisung mitbringt. Er darf im Protokoll
# stehen und nirgends sonst.
GEHEIM = 'Datei /mnt/nas/geheim.pdf nicht lesbar'


def _json(antwort):
    return antwort.get_json()


class _Mitschnitt(logging.Handler):
    """Sammelt Protokollzeilen, statt sie auszugeben."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.zeilen = []

    def emit(self, record):
        self.zeilen.append(record)

    def texte(self):
        return [z.getMessage() for z in self.zeilen]


@pytest.fixture
def mitschnitt():
    vorher = fehler.protokoll.level
    handler = _Mitschnitt()
    fehler.protokoll.setLevel(logging.DEBUG)
    fehler.protokoll.addHandler(handler)
    yield handler
    fehler.protokoll.removeHandler(handler)
    fehler.protokoll.setLevel(vorher)


@pytest.fixture
def platzende_route(monkeypatch):
    """Laesst ``/api/billing/interpolation-audit`` mitten im Aufruf platzen.

    Bewusst eine echte Route statt einer eigens angemeldeten: Flask nimmt nach
    der ersten Anfrage keine neue Regel mehr an, und die Karte will ohnehin
    wissen, was an einer bestehenden Route passiert.
    """
    from billing_engine import BillingEngine

    def knallt(*args, **kwargs):
        raise RuntimeError(GEHEIM)

    monkeypatch.setattr(
        BillingEngine, 'get_meter_consumption_detailed', staticmethod(knallt)
    )
    return '/api/billing/interpolation-audit?meter_id=1&start_date=2026-01-01&end_date=2026-01-31'


# --- Die Vorgangsnummer ------------------------------------------------------


def test_vorgangsnummer_ist_acht_stellen_hex():
    nummer = fehler.vorgangsnummer()

    assert len(nummer) == 8
    assert nummer == nummer.upper()
    int(nummer, 16)  # wirft, wenn dort etwas anderes als Hex steht


def test_vorgangsnummern_wiederholen_sich_nicht():
    """Sonst faende der Betreiber im Protokoll zwei Faelle unter einer Nummer."""
    nummern = {fehler.vorgangsnummer() for _ in range(500)}

    assert len(nummern) == 500


# --- Die Protokollstufe ------------------------------------------------------


@pytest.mark.parametrize(
    'wert,erwartet',
    [
        ('DEBUG', logging.DEBUG),
        (' warning ', logging.WARNING),
        ('error', logging.ERROR),
    ],
)
def test_gueltige_stufe_wird_uebernommen(wert, erwartet):
    assert fehler._stufe(wert) == erwartet


@pytest.mark.parametrize('murks', ['', '   ', 'laut', 'DEBUGG', '10', None, []])
def test_unbrauchbare_stufe_faellt_auf_info_zurueck(murks):
    """Wie bei MAX_UPLOAD_MB (NK-029): ein Tippfehler legt nichts lahm.

    ``None`` liest den echten Weg ueber die Umgebung; LOG_LEVEL ist in der
    Testumgebung nicht gesetzt, also greift ebenfalls die Vorgabe. Auch die
    Ziffernfolge '10' faellt durch: ``logging.getLevelName('10')`` kennt sie
    nicht, und eine halb verstandene Stufe waere schlimmer als INFO.
    """
    assert fehler._stufe(murks) == logging.INFO


def test_log_level_aus_der_umgebung_wirkt(monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'debug')

    assert fehler._stufe() == logging.DEBUG


# --- Der Logger selbst -------------------------------------------------------


def test_protokoll_haengt_an_stderr_nicht_an_stdout(app_ctx):
    """stdout gehoert den Nutzdaten, das Protokoll gehoert nach stderr.

    ``flask users list`` und ``flask backup info`` schreiben ihre Ausgabe nach
    stdout; wer sie weiterverarbeitet, bekommt sonst die Startzeile des
    Protokolls mit in den Datenstrom (F-30). ``docker compose logs`` zeigt
    beide Stroeme, fuer den Betreiber aendert sich dadurch nichts.
    """
    import sys

    ausgaenge = [a for a in fehler.protokoll.handlers if getattr(a, '_nk_ausgang', False)]

    assert len(ausgaenge) == 1
    assert ausgaenge[0].stream is sys.stderr


def test_init_protokoll_ist_idempotent(app_ctx):
    """Ein zweiter Aufruf darf nicht jede Zeile doppelt schreiben."""
    vorher = len(fehler.protokoll.handlers)

    fehler.init_protokoll(app_ctx.app)
    fehler.init_protokoll(app_ctx.app)

    assert len(fehler.protokoll.handlers) == vorher


def test_protokoll_gibt_nichts_an_den_wurzel_logger(app_ctx):
    assert fehler.protokoll.propagate is False


def test_das_protokoll_ueberlebt_die_wanderung(app_ctx):
    """Alembic hat das Protokoll beim Start stillgelegt (F-14).

    ``migrations/env.py`` ruft ``fileConfig()``, und dessen Vorgabe
    ``disable_existing_loggers=True`` schaltet jeden Logger ab, den es schon
    gibt. Da ``schema_aktualisieren()`` im selben Prozess laeuft wie die
    Anwendung, war ``nebenkosten`` ab der ersten Wanderung tot: die Anwendung
    lief, protokollierte aber keine Zeile mehr. Aufgefallen ist es hier, weil
    der Mitschnitt leer blieb.
    """
    assert fehler.protokoll.disabled is False


def test_die_dateiablage_schreibt_in_dasselbe_protokoll():
    """``nebenkosten.nas`` ist ein Kind und landet im selben Ausgang.

    Der NAS-Handler importiert ``fehler`` bewusst nicht -- er soll nicht die
    halbe Webschicht nachziehen. Der Name allein genuegt.
    """
    from handlers import nas_handler

    assert nas_handler.protokoll.name.startswith(fehler.PROTOKOLLNAME + '.')
    assert nas_handler.protokoll.parent is fehler.protokoll


# --- Unbehandelte Ausnahmen --------------------------------------------------


def test_unbehandelter_fehler_gibt_deutsche_500(auth_client, platzende_route, app_ctx):
    antwort = auth_client.get(platzende_route)

    assert antwort.status_code == 500
    rumpf = _json(antwort)
    assert rumpf['error'].startswith('Es ist ein Fehler aufgetreten.')
    assert 'nicht gespeichert' in rumpf['error']


def test_die_antwort_nennt_die_vorgangsnummer(auth_client, platzende_route, app_ctx):
    rumpf = _json(auth_client.get(platzende_route))

    assert len(rumpf['vorgang']) == 8
    assert f"Vorgangsnummer {rumpf['vorgang']}." in rumpf['error']


def test_die_antwort_verraet_kein_innenleben(auth_client, platzende_route, app_ctx):
    """Kein Stapelabzug, kein Pfad, kein englischer Ausnahmetext.

    Ein Stapelabzug im Browser ist eine Landkarte der Installation, und der
    Satz "RuntimeError: ..." hilft einem Vermieter ohnehin nicht weiter.
    """
    text = auth_client.get(platzende_route).get_data(as_text=True)

    assert 'Traceback' not in text
    assert 'RuntimeError' not in text
    assert GEHEIM not in text
    assert 'billing_engine' not in text


def test_dieselbe_nummer_steht_im_protokoll(auth_client, platzende_route, mitschnitt, app_ctx):
    nummer = _json(auth_client.get(platzende_route))['vorgang']

    passend = [z for z in mitschnitt.zeilen if nummer in z.getMessage()]
    assert len(passend) == 1
    zeile = passend[0]
    assert zeile.levelno == logging.ERROR
    assert '/api/billing/interpolation-audit' in zeile.getMessage()
    assert 'RuntimeError' in zeile.getMessage()


def test_der_stapelabzug_landet_im_protokoll(auth_client, platzende_route, mitschnitt, app_ctx):
    """Gegenprobe zur Antwort: ausgeblendet ist er nur nach aussen."""
    auth_client.get(platzende_route)

    zeile = mitschnitt.zeilen[-1]
    assert zeile.exc_info is not None
    assert GEHEIM in logging.Formatter().formatException(zeile.exc_info)


def test_nach_dem_fehler_wird_zurueckgerollt(auth_client, platzende_route, monkeypatch, app_ctx):
    """Ohne Rollback antwortet die Sitzung danach mit PendingRollbackError."""
    gerufen = []
    monkeypatch.setattr(fehler, '_zurueckrollen', lambda: gerufen.append(True))

    auth_client.get(platzende_route)

    assert gerufen == [True]


def test_die_anwendung_bedient_nach_einem_fehler_weiter(auth_client, platzende_route, app_ctx):
    """Der eigentliche Schaden vorher: ein Fehler legte die Sitzung lahm."""
    auth_client.get(platzende_route)

    weiter = auth_client.get('/api/properties')
    assert weiter.status_code == 200


# --- Der Rollback als solcher ------------------------------------------------


def test_zurueckrollen_verwirft_haengende_aenderungen(app_ctx):
    from models import Property, db

    db.session.add(Property(name='Haus Müllerstraße 3'))
    db.session.flush()
    assert Property.query.count() == 1

    fehler._zurueckrollen()

    assert Property.query.count() == 0


def test_zurueckrollen_ueberlebt_einen_kaputten_rollback(monkeypatch, mitschnitt):
    """Ist die Verbindung weg, scheitert auch der Rollback.

    Dann bleibt nur die Protokollzeile. Wer hier eine Ausnahme durchliesse,
    bekaeme statt der deutschen 500 wieder die Standardseite von Flask.
    """

    class KaputteSitzung:
        def rollback(self):
            raise RuntimeError('Verbindung weg')

    class KaputteDb:
        session = KaputteSitzung()

    monkeypatch.setattr(fehler, 'db', KaputteDb())

    fehler._zurueckrollen()  # darf nicht werfen

    assert any('Rollback' in t for t in mitschnitt.texte())


# --- HTTP-Fehler -------------------------------------------------------------


def test_unbekannter_datensatz_gibt_deutschen_404(auth_client, app_ctx):
    antwort = auth_client.delete('/api/properties/999999')

    assert antwort.status_code == 404
    assert _json(antwort)['error'] == 'Das Gesuchte gibt es nicht (mehr).'


def test_falsche_methode_endet_in_der_sperre(auth_client, app_ctx):
    """Vor dem 405 steht die Zugangssperre, und das bleibt so.

    Werkzeug entscheidet ueber die Methode erst beim Zuordnen der Regel; bis
    dahin ist ``request.endpoint`` None, und die Sperre aus NK-023 antwortet
    schon mit 401. Der 405 aus HTTP_MELDUNGEN ist deshalb heute ein Netz fuer
    spaeter, kein toter Text: er greift, sobald eine oeffentliche Route falsch
    aufgerufen wird.
    """
    antwort = auth_client.put('/api/properties')

    assert antwort.status_code == 401
    assert _json(antwort)['error'] == 'Nicht angemeldet.'


def test_browser_bekommt_bei_einem_404_weiter_eine_seite(auth_client, app_ctx):
    """Ein falscher Link soll keine geschweiften Klammern zeigen.

    ``/static/...`` ist eine Route ausserhalb von ``/api/``: dort entscheidet
    der Accept-Kopf, und ohne ihn gilt der Aufrufer als Browser.
    """
    antwort = auth_client.get('/static/gibtsnicht.js')

    assert antwort.status_code == 404
    assert antwort.mimetype == 'text/html'


def test_derselbe_pfad_als_json_gibt_den_deutschen_satz(auth_client, app_ctx):
    """Gegenprobe: am Accept-Kopf haengt es, nicht an der Route."""
    antwort = auth_client.get(
        '/static/gibtsnicht.js', headers={'Accept': 'application/json'}
    )

    assert antwort.status_code == 404
    assert _json(antwort)['error'] == 'Das Gesuchte gibt es nicht (mehr).'


def test_browser_bekommt_bei_einem_absturz_eine_notseite(auth_client, monkeypatch, app_ctx):
    """Auch die 500 kennt den Weg ohne JSON -- mit derselben Nummer."""
    import app as app_module

    def knallt(*args, **kwargs):
        raise RuntimeError(GEHEIM)

    # NK-140 liest index.html ueber _index_mit_kennung; die Notseite wird
    # ueber diese Funktion provoziert, nicht ueber einen toten Pfad.
    monkeypatch.setattr(app_module, '_index_mit_kennung', knallt)

    antwort = auth_client.get('/')
    text = antwort.get_data(as_text=True)

    assert antwort.status_code == 500
    assert antwort.mimetype == 'text/html'
    assert 'Es ist ein Fehler aufgetreten.' in text
    assert 'Vorgangsnummer' in text
    assert 'Traceback' not in text
    assert GEHEIM not in text


def test_serverfehler_steht_im_protokoll(auth_client, mitschnitt, monkeypatch, app_ctx):
    """Ein 5xx mit HTTP-Status ist kein Absturz, aber auch kein Alltag.

    Er bekommt keine Vorgangsnummer -- es gibt keinen Stapelabzug, den sie
    zuordnen koennte -- aber eine Zeile, sonst merkt der Betreiber nie, dass
    ein Dienst dahinter wegbleibt. 4xx bleiben bewusst still, sonst ersaeuft
    das Protokoll in Tippfehlern der Bedienung.
    """
    from billing_engine import BillingEngine
    from flask import abort

    monkeypatch.setattr(
        BillingEngine,
        'get_meter_consumption_detailed',
        staticmethod(lambda *a, **k: abort(503)),
    )

    antwort = auth_client.get(
        '/api/billing/interpolation-audit'
        '?meter_id=1&start_date=2026-01-01&end_date=2026-01-31'
    )

    assert antwort.status_code == 503
    assert _json(antwort)['error'].startswith('Die Anwendung ist gerade nicht bereit')
    assert any('503' in t for t in mitschnitt.texte())


def test_ein_404_bleibt_still(auth_client, mitschnitt, app_ctx):
    """Gegenprobe: falsche Adressen fuellen das Protokoll nicht."""
    auth_client.delete('/api/properties/999999')

    assert mitschnitt.zeilen == []


# --- Vorrang der spezielleren Handler ---------------------------------------


def test_eingabefehler_bleibt_bei_400(auth_client, app_ctx):
    """NK-028 ist naeher an seiner Ausnahme als HTTPException/Exception."""
    antwort = auth_client.post('/api/properties', json={})

    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'name'


def test_ohne_anmeldung_bleibt_es_bei_401(anon_client, app_ctx):
    antwort = anon_client.get('/api/properties')

    assert antwort.status_code == 401
    assert _json(antwort)['error'] == 'Nicht angemeldet.'


def test_413_behaelt_seinen_eigenen_handler(app_ctx):
    """Strukturprobe zu NK-029: der Code-Handler steht neben den Klassen."""
    from validation import EingabeFehler

    spec = app_ctx.app.error_handler_spec[None]

    assert 413 in spec
    assert EingabeFehler in spec[None]
    assert HTTPException in spec[None]
    assert Exception in spec[None]


# --- Das Frontend zeigt die Meldung auch an ---------------------------------
#
# Nebenbefund aus NK-028: die deutschen Meldungen kamen nie auf den Schirm,
# weil static/app.js an rund dreissig Stellen einen eigenen englischen Fehler
# warf und den Rumpf der Antwort gar nicht erst las. Fuer eine Datei ohne
# eigene Testumgebung ist die maschinelle Lesepruefung das, was geht -- sie
# haelt wenigstens fest, dass das Muster nicht zurueckkommt.


def _app_js():
    import os

    pfad = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'app.js')
    with open(pfad, encoding='utf-8') as datei:
        return datei.read()


def test_das_frontend_hat_die_beiden_helfer():
    text = _app_js()

    assert 'async function serverFehler(antwort)' in text
    assert 'function meldungZu(fehler, ersatz)' in text


def test_kein_eigener_fehler_mehr_statt_der_servermeldung():
    """``throw new Error('Failed to save ...')`` warf die Antwort weg."""
    assert 'throw new Error(' not in _app_js()


def test_keine_rohe_ausnahmemeldung_auf_dem_schirm():
    """``showError(e.message)`` zeigte bei einem Netzabriss "Failed to fetch"."""
    text = _app_js()

    assert 'showError(e.message)' not in text
    assert '${e.message}' not in text
