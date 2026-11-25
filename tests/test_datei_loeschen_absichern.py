"""Loeschen im Belegordner bleibt im Belegordner.

Befund 1: ``Ablage.delete_file`` lehnte nur Pfade mit ``..`` oder fuehrendem
``/`` ab und haengte alles andere an die Wurzel. Ein verknuepfter Ordner im
Belegordner fuehrte damit hinaus, unter Windows auch ein Laufwerkspfad
(``C:\\...``), ein UNC-Pfad (``\\\\server\\share``) oder ein Pfad ab der
Laufwerkswurzel (``\\Ordner``): ``os.path.join`` verwirft dort die Wurzel.
Ein absoluter Pfad aus dem Altbestand, der im Belegordner liegt, liess sich
dagegen nie loeschen.

Befund 2: ``PUT /api/invoice_documents/<id>`` mit neuer Datei loeschte die
alte Datei vor dem Commit. Scheiterte der Commit, war die Datei weg und die
Zeile zeigte noch auf sie; die neue Datei blieb verwaist liegen.

Geprueft wird:
- ``delete_file`` loest ueber ``uploads.pfad_aufloesen`` auf und loescht nur,
  was danach im Belegordner liegt -- feindliche Pfade loeschen nichts
  ausserhalb und liefern False;
- ein absoluter Pfad im Belegordner (Altbestand) wird geloescht;
- ein ersetzter Sammelbeleg verschwindet erst nach dem Commit;
- scheitert der Commit, bleibt die alte Datei und die neue verschwindet.

Die Faelle mit Laufwerks- und UNC-Pfaden gibt es nur unter Windows; sie
laufen in der Windows-CI.

Nur fiktive Daten.
"""

import io
import os
from pathlib import Path

import pytest

import billing_factories as f
from nebenkostenfix.models import InvoiceDocument, db

PDF_A = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<</A 1>>\nendobj\n%%EOF\n'
PDF_B = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n2 0 obj\n<</B 1>>\nendobj\n%%EOF\n'

NUR_WINDOWS = pytest.mark.skipif(
    os.name != 'nt', reason='Laufwerks- und UNC-Pfade gibt es nur unter Windows')


# --- Ablage.delete_file ----------------------------------------------------

@pytest.fixture
def ablage(tmp_path, monkeypatch):
    """Eine Ablage mit eigener, leerer Belegwurzel."""
    wurzel = tmp_path / 'belege'
    wurzel.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(wurzel))
    from nebenkostenfix.ablage import Ablage

    ablage = Ablage()
    assert os.path.realpath(ablage.wurzel) == os.path.realpath(wurzel)
    return ablage


@pytest.fixture
def aussen(tmp_path):
    """Eine Datei neben dem Belegordner, die nie geloescht werden darf."""
    ordner = tmp_path / 'aussen'
    ordner.mkdir()
    datei = ordner / 'opfer.pdf'
    datei.write_bytes(PDF_A)
    return datei


def _im_belegordner(ablage, relativ='2024/beleg.pdf'):
    voll = Path(ablage.wurzel) / relativ
    voll.parent.mkdir(parents=True, exist_ok=True)
    voll.write_bytes(PDF_A)
    return voll


def test_relativer_pfad_im_belegordner_wird_geloescht(ablage):
    voll = _im_belegordner(ablage)

    assert ablage.delete_file('2024/beleg.pdf') is True
    assert not voll.exists()


def test_absoluter_pfad_im_belegordner_wird_geloescht(ablage):
    """Altbestand: in der Datenbank steht ein absoluter Pfad, der im
    Belegordner liegt. Ausliefern kann ihn ``pfad_aufloesen`` schon, loeschen
    konnte ihn ``delete_file`` bisher nie."""
    voll = _im_belegordner(ablage)

    assert ablage.delete_file(str(voll)) is True
    assert not voll.exists()


def _feindlich(art, ablage, aussen):
    if art == 'absolut':
        return str(aussen)
    if art == 'punkte':
        return os.path.relpath(aussen, ablage.wurzel)
    if art == 'punkte_rueckwaerts':
        return os.path.relpath(aussen, ablage.wurzel).replace('/', '\\')
    if art == 'laufwerk':
        return str(aussen)  # unter Windows: C:\...
    if art == 'unc':
        laufwerk, rest = os.path.splitdrive(str(aussen))
        return f'\\\\localhost\\{laufwerk[0]}${rest}'
    if art == 'laufwerkswurzel':
        return os.path.splitdrive(str(aussen))[1]  # \Users\...
    raise AssertionError(art)


@pytest.mark.parametrize('art', [
    'absolut',
    'punkte',
    'punkte_rueckwaerts',
    pytest.param('laufwerk', marks=NUR_WINDOWS),
    pytest.param('unc', marks=NUR_WINDOWS),
    pytest.param('laufwerkswurzel', marks=NUR_WINDOWS),
])
def test_feindlicher_pfad_loescht_nichts_ausserhalb(ablage, aussen, art):
    pfad = _feindlich(art, ablage, aussen)

    assert ablage.delete_file(pfad) is False
    assert aussen.read_bytes() == PDF_A


def test_verknuepfter_ordner_fuehrt_nicht_aus_dem_belegordner(ablage, aussen):
    """Ein Ordner im Belegordner, der nach draussen zeigt: ``realpath`` sieht,
    wohin er wirklich fuehrt."""
    verknuepfung = Path(ablage.wurzel) / 'verknuepfung'
    try:
        os.symlink(aussen.parent, verknuepfung, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Verknuepfungen sind hier nicht erlaubt')

    assert ablage.delete_file('verknuepfung/opfer.pdf') is False
    assert aussen.read_bytes() == PDF_A


@pytest.mark.parametrize('pfad', ['', None, '.', '2024'])
def test_belegordner_und_unterordner_bleiben(ablage, pfad):
    _im_belegordner(ablage)

    assert ablage.delete_file(pfad) is False
    assert os.path.isfile(os.path.join(ablage.wurzel, '2024', 'beleg.pdf'))


def test_fehlende_datei_ist_kein_fehler(ablage):
    assert ablage.delete_file('2024/gibt-es-nicht.pdf') is False


def test_fehlschlag_beim_entfernen_wird_protokolliert(ablage, monkeypatch, caplog):
    voll = _im_belegordner(ablage)
    import logging

    from nebenkostenfix import ablage as ablage_modul

    def _klemmt(_pfad):
        raise PermissionError('Datei gesperrt')

    monkeypatch.setattr(ablage_modul.os, 'remove', _klemmt)
    # Der Handler haengt direkt am Logger: nach init_protokoll gibt
    # ``nebenkosten`` nichts mehr an den Wurzel-Logger weiter, an dem caplog
    # sonst mitschneidet.
    caplog.set_level(logging.WARNING, logger=ablage_modul.protokoll.name)
    ablage_modul.protokoll.addHandler(caplog.handler)
    try:
        assert ablage.delete_file('2024/beleg.pdf') is False
    finally:
        ablage_modul.protokoll.removeHandler(caplog.handler)

    assert voll.exists()
    assert any(r.name == 'nebenkosten.ablage' and r.levelno == logging.WARNING
               and 'Datei nicht loeschbar' in r.getMessage()
               for r in caplog.records)


# --- Ersetzter Sammelbeleg (PUT /api/invoice_documents/<id>) ----------------

def _belege(app_ctx):
    """Alle Dateien unter der Belegwurzel, als Menge relativer Pfade."""
    wurzel = app_ctx.nas_handler.wurzel
    gefunden = set()
    for ordner, _unter, dateien in os.walk(wurzel):
        for name in dateien:
            gefunden.add(os.path.relpath(os.path.join(ordner, name), wurzel))
    return gefunden


def _voll(app_ctx, relativ):
    return os.path.join(app_ctx.nas_handler.wurzel, relativ)


def _beleg_a(auth_client):
    haus = f.house('Testhaus Belegtausch')
    db.session.commit()
    antwort = auth_client.post('/api/invoice_documents', content_type='multipart/form-data',
                               data={'property_id': str(haus.id), 'description': 'Beispiel',
                                     'file': (io.BytesIO(PDF_A), 'beleg-alt.pdf')})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    doc_id = antwort.get_json()['id']
    alt = db.session.get(InvoiceDocument, doc_id).document_path
    assert alt
    return haus.id, doc_id, alt


def _beleg_b_hochladen(auth_client, haus_id, doc_id):
    return auth_client.put(f'/api/invoice_documents/{doc_id}',
                           content_type='multipart/form-data',
                           data={'property_id': str(haus_id), 'description': 'Beispiel',
                                 'file': (io.BytesIO(PDF_B), 'beleg-neu.pdf')})


def test_ersetzter_beleg_loescht_die_alte_datei(app_ctx, auth_client):
    haus_id, doc_id, alt = _beleg_a(auth_client)
    vorher = _belege(app_ctx)

    antwort = _beleg_b_hochladen(auth_client, haus_id, doc_id)

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    neu = db.session.get(InvoiceDocument, doc_id).document_path
    assert neu and neu != alt
    with open(_voll(app_ctx, neu), 'rb') as datei:
        assert datei.read() == PDF_B
    assert not os.path.exists(_voll(app_ctx, alt))
    assert _belege(app_ctx) == vorher - {os.path.normpath(alt)} | {os.path.normpath(neu)}


def test_scheitert_der_commit_bleibt_der_alte_beleg(app_ctx, auth_client, monkeypatch):
    haus_id, doc_id, alt = _beleg_a(auth_client)
    vorher = _belege(app_ctx)

    def _scheitert():
        raise RuntimeError('Datenbank nicht erreichbar')

    with monkeypatch.context() as m:
        m.setattr(db.session, 'commit', _scheitert)
        antwort = _beleg_b_hochladen(auth_client, haus_id, doc_id)

    assert antwort.status_code == 500
    db.session.rollback()
    db.session.expire_all()
    assert db.session.get(InvoiceDocument, doc_id).document_path == alt
    with open(_voll(app_ctx, alt), 'rb') as datei:
        assert datei.read() == PDF_A
    # Die neue Datei ist wieder weg: nichts Verwaistes im Belegordner.
    assert _belege(app_ctx) == vorher


def test_alter_beleg_bleibt_wenn_noch_etwas_darauf_zeigt(app_ctx, auth_client):
    haus_id, doc_id, alt = _beleg_a(auth_client)
    db.session.add(InvoiceDocument(property_id=haus_id, filename='zweit.pdf',
                                   document_path=alt))
    db.session.commit()

    antwort = _beleg_b_hochladen(auth_client, haus_id, doc_id)

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert os.path.isfile(_voll(app_ctx, alt))
