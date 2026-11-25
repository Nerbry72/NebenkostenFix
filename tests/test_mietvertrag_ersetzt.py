"""Ein ersetzter Mietvertrag laesst keine verwaiste Datei zurueck (Datenschutz).

Befund: PUT /api/tenants/<id> mit einer neuen Vertragsdatei schrieb den neuen
Pfad nach ``tenants.contract_path``, die alte Datei blieb aber im Belegordner
liegen. Kein Verweis zeigte mehr auf sie, sie tauchte in keiner Auskunft und
keiner Loeschung (NK-078) mehr auf -- ein personenbezogenes Dokument, das
niemand mehr findet und niemand mehr loescht.

Geprueft wird:
- nach dem Ersetzen liegt nur noch der neue Vertrag im Belegordner;
- zeigt eine andere Pfadspalte (backup.PFADSPALTEN) noch auf die alte Datei,
  bleibt sie liegen;
- scheitert das Loeschen, scheitert die Anfrage nicht, und das Protokoll
  nennt die liegengebliebene Datei;
- scheitert der Commit, bleibt die alte Datei liegen und die neu
  geschriebene verschwindet wieder.

Nur fiktive Daten.
"""

import io
import logging
import os

import pytest

import billing_factories as f
from nebenkostenfix.models import InvoiceDocument, Tenant, db

VERTRAG_A = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
VERTRAG_B = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n2 0 obj\n<</B 1>>\nendobj\n%%EOF\n'


def _belege(app_ctx):
    """Alle Dateien unter der Belegwurzel, als Menge relativer Pfade."""
    wurzel = app_ctx.ablage.wurzel
    gefunden = set()
    for ordner, _unter, dateien in os.walk(wurzel):
        for name in dateien:
            gefunden.add(os.path.relpath(os.path.join(ordner, name), wurzel))
    return gefunden


def _voll(app_ctx, relativ):
    return os.path.join(app_ctx.ablage.wurzel, relativ)


def _mieter_mit_vertrag_a(auth_client):
    haus = f.house('Testhaus Vertragstausch')
    wohnung = f.apt(haus, 'OG rechts', 61)
    db.session.commit()
    antwort = auth_client.post('/api/tenants', content_type='multipart/form-data', data={
        'apartment_id': str(wohnung.id), 'name': 'Mieterin Beispiel',
        'move_in_date': '2024-05-01',
        'contract_file': (io.BytesIO(VERTRAG_A), 'vertrag-alt.pdf')})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    mieter_id = antwort.get_json()['id']
    alt = db.session.get(Tenant, mieter_id).contract_path
    assert alt
    return mieter_id, alt


def _vertrag_b_hochladen(auth_client, mieter_id):
    return auth_client.put(f'/api/tenants/{mieter_id}',
                           content_type='multipart/form-data',
                           data={'contract_file': (io.BytesIO(VERTRAG_B), 'vertrag-neu.pdf')})


def test_ersetzter_vertrag_loescht_die_alte_datei(app_ctx, auth_client):
    vorher = _belege(app_ctx)
    mieter_id, alt = _mieter_mit_vertrag_a(auth_client)
    assert os.path.isfile(_voll(app_ctx, alt))

    antwort = _vertrag_b_hochladen(auth_client, mieter_id)

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    neu = db.session.get(Tenant, mieter_id).contract_path
    assert neu and neu != alt
    with open(_voll(app_ctx, neu), 'rb') as datei:
        assert datei.read() == VERTRAG_B
    assert not os.path.exists(_voll(app_ctx, alt))
    assert _belege(app_ctx) - vorher == {os.path.normpath(neu)}


@pytest.mark.parametrize('verweis', ['anderer_mieter', 'beleg'])
def test_alte_datei_bleibt_wenn_noch_etwas_darauf_zeigt(app_ctx, auth_client, verweis):
    mieter_id, alt = _mieter_mit_vertrag_a(auth_client)
    mieter = db.session.get(Tenant, mieter_id)
    if verweis == 'anderer_mieter':
        db.session.add(Tenant(apartment_id=mieter.apartment_id, name='Mieter Zwei',
                              move_in_date=mieter.move_in_date, contract_path=alt))
    else:
        haus_id = mieter.apartment.property_id
        db.session.add(InvoiceDocument(property_id=haus_id, filename='x.pdf',
                                       document_path=alt))
    db.session.commit()

    antwort = _vertrag_b_hochladen(auth_client, mieter_id)

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(Tenant, mieter_id).contract_path != alt
    assert os.path.isfile(_voll(app_ctx, alt))


@pytest.fixture
def protokoll(caplog):
    """``caplog`` am Logger ``nebenkosten``.

    ``init_protokoll`` setzt dort ``propagate = False``; der Mitschnitt von
    pytest am Wurzel-Logger saehe nichts. Darum haengt sein Handler hier
    direkt am Logger.
    """
    from nebenkostenfix import fehler

    caplog.set_level(logging.WARNING, logger=fehler.PROTOKOLLNAME)
    fehler.protokoll.addHandler(caplog.handler)
    yield caplog
    fehler.protokoll.removeHandler(caplog.handler)


def _warnungen(caplog, text):
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and text in r.getMessage()]


def test_fehlschlag_beim_loeschen_laesst_die_anfrage_gelingen(app_ctx, auth_client, monkeypatch,
                                                             protokoll):
    mieter_id, alt = _mieter_mit_vertrag_a(auth_client)

    def _klemmt(_pfad):
        raise OSError('Datei gesperrt')

    monkeypatch.setattr(app_ctx.nas_handler, 'delete_file', _klemmt)
    antwort = _vertrag_b_hochladen(auth_client, mieter_id)

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    neu = db.session.get(Tenant, mieter_id).contract_path
    assert neu and neu != alt
    assert os.path.isfile(_voll(app_ctx, neu))
    # Die Datei bleibt liegen, und das Protokoll sagt welche -- mit Ursache.
    treffer = _warnungen(protokoll, 'Ersetzte Datei blieb im Belegordner liegen')
    assert treffer
    assert alt in treffer[0].getMessage()
    assert treffer[0].exc_info and 'Datei gesperrt' in str(treffer[0].exc_info[1])


def test_scheitert_der_commit_bleibt_die_alte_datei(app_ctx, auth_client, monkeypatch):
    mieter_id, alt = _mieter_mit_vertrag_a(auth_client)

    def _scheitert():
        raise RuntimeError('Datenbank nicht erreichbar')

    with monkeypatch.context() as m:
        m.setattr(db.session, 'commit', _scheitert)
        antwort = _vertrag_b_hochladen(auth_client, mieter_id)

    assert antwort.status_code == 500
    db.session.rollback()
    db.session.expire_all()
    assert db.session.get(Tenant, mieter_id).contract_path == alt
    assert os.path.isfile(_voll(app_ctx, alt))


def test_scheitert_der_commit_verschwindet_der_neue_vertrag(app_ctx, auth_client, monkeypatch):
    """Die neue Datei ist vor dem Commit geschrieben. Scheitert er, zeigt
    keine Zeile auf sie -- sie muss wieder weg, sonst liegt ein
    personenbezogenes Dokument verwaist im Belegordner."""
    mieter_id, alt = _mieter_mit_vertrag_a(auth_client)
    vorher = _belege(app_ctx)

    def _scheitert():
        raise RuntimeError('Datenbank nicht erreichbar')

    with monkeypatch.context() as m:
        m.setattr(db.session, 'commit', _scheitert)
        antwort = _vertrag_b_hochladen(auth_client, mieter_id)

    assert antwort.status_code == 500
    db.session.rollback()
    assert _belege(app_ctx) == vorher


def test_scheitert_auch_das_aufraeumen_bleibt_es_bei_500(app_ctx, auth_client, monkeypatch,
                                                       protokoll):
    """Laesst sich die neue Datei nach dem gescheiterten Commit nicht
    entfernen, verdeckt das nicht den eigentlichen Fehler; das Protokoll
    nennt die liegengebliebene Datei."""
    mieter_id, _alt = _mieter_mit_vertrag_a(auth_client)

    def _scheitert():
        raise RuntimeError('Datenbank nicht erreichbar')

    def _klemmt(_pfad):
        raise OSError('Datei gesperrt')

    with monkeypatch.context() as m:
        m.setattr(db.session, 'commit', _scheitert)
        m.setattr(app_ctx.nas_handler, 'delete_file', _klemmt)
        antwort = _vertrag_b_hochladen(auth_client, mieter_id)

    assert antwort.status_code == 500
    db.session.rollback()
    assert _warnungen(protokoll, 'Neue Datei blieb im Belegordner liegen')
