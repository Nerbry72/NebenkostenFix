"""Groessenlimit fuer Uploads und der 413 dazu (NK-029).

Vor dieser Karte gab es nirgends ein Limit. Acht Routen lesen Dateien, und
jede haette einen beliebig grossen Rumpf angenommen: erst in den Speicher,
dann als Beleg ins NAS-Verzeichnis. Die Tests halten beides fest, das Limit
selbst und die Antwort daran.
"""

from __future__ import annotations

import io

import pytest

from conftest import TEST_PASSWORD, TEST_USER


MB = 1024 * 1024


def _json(antwort):
    return antwort.get_json()


def _datei(groesse_bytes, name='beleg.pdf'):
    """Ein Upload der gewuenschten Rumpfgroesse. Seit NK-129 mit PDF-Kopf,
    sonst lehnt die Ablage ihn am Inhalt ab, bevor die Groesse zaehlt."""
    kopf = b'%PDF-1.4\n'
    return (io.BytesIO(kopf + b'x' * max(0, groesse_bytes - len(kopf))), name)


@pytest.fixture
def kleines_limit(app_ctx):
    """Limit auf 1 MB, damit ein Test keine 32 MB durch den Client schiebt.

    Flask liest MAX_CONTENT_LENGTH bei jeder Anfrage neu aus der Config
    (flask.wrappers.Request.max_content_length), ein Wert hier wirkt also
    sofort. Danach steht wieder der Wert aus der Umgebung.
    """
    vorher = app_ctx.app.config['MAX_CONTENT_LENGTH']
    app_ctx.app.config['MAX_CONTENT_LENGTH'] = 1 * MB
    yield 1 * MB
    app_ctx.app.config['MAX_CONTENT_LENGTH'] = vorher


# --- Der Wert selbst ---------------------------------------------------------


def test_vorgabe_sind_32_megabyte():
    import app as app_module

    assert app_module.max_upload_bytes('') == 32 * MB
    assert app_module.UPLOAD_VORGABE_MB == 32


def test_eigener_wert_wird_uebernommen():
    import app as app_module

    assert app_module.max_upload_bytes('64') == 64 * MB
    assert app_module.max_upload_bytes(' 8 ') == 8 * MB


@pytest.mark.parametrize('murks', ['viel', '0', '-5', '12,5', None, [], '32.5'])
def test_unbrauchbarer_wert_faellt_auf_die_vorgabe(murks):
    """Ein Tippfehler in der .env legt keine Instanz lahm.

    None bedeutet hier den echten Standardweg (Umgebungsvariable lesen); in
    der Testumgebung ist MAX_UPLOAD_MB nicht gesetzt, also greift ebenfalls
    die Vorgabe.
    """
    import app as app_module

    assert app_module.max_upload_bytes(murks) == 32 * MB


def test_die_anwendung_hat_ein_limit(app_ctx):
    """Ohne den Config-Schluessel prueft Werkzeug gar nichts."""
    assert app_ctx.app.config['MAX_CONTENT_LENGTH'] == 32 * MB


# --- Die Antwort an der Grenze ----------------------------------------------


def test_zu_grosser_beleg_gibt_413_auf_deutsch(auth_client, kleines_limit, app_ctx):
    from models import Property, db

    prop = Property(name='Haus Müllerstraße 3')
    db.session.add(prop)
    db.session.commit()

    antwort = auth_client.post(
        '/api/invoice_documents',
        data={'property_id': str(prop.id), 'file': _datei(kleines_limit + 1)},
        content_type='multipart/form-data',
    )

    assert antwort.status_code == 413
    rumpf = _json(antwort)
    assert rumpf['error'] == 'Der Upload ist zu groß. Erlaubt sind höchstens 1 MB.'
    assert rumpf['feld'] is None


def test_die_meldung_nennt_das_eingestellte_limit(auth_client, app_ctx):
    """Der Text ist keine feste Zeichenkette, er rechnet den Config-Wert um."""
    app_ctx.app.config['MAX_CONTENT_LENGTH'] = 5 * MB
    try:
        antwort = auth_client.post(
            '/api/invoice_documents',
            data={'property_id': '1', 'file': _datei(5 * MB + 1)},
            content_type='multipart/form-data',
        )
        assert antwort.status_code == 413
        assert '5 MB' in _json(antwort)['error']
    finally:
        app_ctx.app.config['MAX_CONTENT_LENGTH'] = 32 * MB


def test_datei_knapp_unter_dem_limit_geht_durch(auth_client, kleines_limit, app_ctx):
    """Gegenprobe: das Limit sperrt nicht einfach alles."""
    from models import InvoiceDocument, Property, db

    prop = Property(name='Haus Müllerstraße 3')
    db.session.add(prop)
    db.session.commit()

    antwort = auth_client.post(
        '/api/invoice_documents',
        data={'property_id': str(prop.id), 'file': _datei(kleines_limit - 8192)},
        content_type='multipart/form-data',
    )

    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert InvoiceDocument.query.count() == 1


def test_413_gilt_auch_fuer_json(auth_client, kleines_limit):
    """Das Limit haengt am Rumpf, nicht am Formular.

    Eine aufgeblaehte JSON-Anfrage laeuft in dieselbe Antwort. Wichtig, weil
    das Frontend die meisten Routen mit JSON bedient.
    """
    antwort = auth_client.post(
        '/api/properties',
        data=b'{"name": "' + b'x' * kleines_limit + b'"}',
        content_type='application/json',
    )

    assert antwort.status_code == 413
    assert 'zu groß' in _json(antwort)['error']


def test_grosses_formularfeld_gibt_dieselbe_antwort(auth_client, app_ctx):
    """Werkzeug 3.1 wirft den 413 auch unterhalb von MAX_CONTENT_LENGTH.

    max_form_memory_size steht bei 500 KB und gilt fuer Formularfelder ohne
    Datei. Flask 3.0 verdrahtet den Wert nicht mit der Config, er ist also
    nicht abschaltbar. Deshalb nennt die Meldung den Upload und nicht die
    Datei: sonst stuende hier ein Satz ueber eine Datei, die es nicht gibt.
    """
    antwort = auth_client.post(
        '/api/properties',
        data={'name': 'x' * (600 * 1024)},
        content_type='multipart/form-data',
    )

    assert antwort.status_code == 413
    assert _json(antwort)['error'].startswith('Der Upload ist zu groß.')


def test_ohne_anmeldung_bleibt_es_bei_401(anon_client, kleines_limit):
    """Die Sperre kommt vor der Groessenpruefung.

    Ein Fremder soll an einem 413 nicht ablesen koennen, welche Routen es
    gibt und wie gross Uploads sein duerfen.
    """
    antwort = anon_client.post(
        '/api/invoice_documents',
        data={'property_id': '1', 'file': _datei(kleines_limit + 1)},
        content_type='multipart/form-data',
    )

    assert antwort.status_code == 401


def test_anmeldung_selbst_faellt_nicht_unter_das_limit(app_ctx, kleines_limit):
    """Gegenprobe zur Reihenfolge: /login ist oeffentlich und klein."""
    from models import User, db

    user = User(username=TEST_USER)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()

    client = app_ctx.app.test_client()
    antwort = client.post(
        '/login', json={'username': TEST_USER, 'password': TEST_PASSWORD}
    )
    assert antwort.status_code == 200
