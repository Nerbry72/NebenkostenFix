"""Zugriffsschlüssel für Programme ohne Browser (API-Tokens).

Bis hierher kam man nur mit einer Sitzung an die API: Anmeldung per
Formular, Cookie, Abmeldung nach Leerlauf. Ein Programm, das im Hintergrund
läuft -- etwa ein MCP-Server, über den ein KI-Assistent den Bestand liest --,
passt dazu nicht, und das eigene Passwort gehört dort nicht hinein.

Ein Zugriffsschlüssel gehört zu einem Konto und wird als
``Authorization: Bearer <schlüssel>`` mitgeschickt. Die Regeln, die hier
festgehalten werden:

    - Der Schlüssel steht genau einmal in der Antwort beim Anlegen. In der
      Datenbank liegt nur sein SHA-256.
    - Deny-by-default wie die Anmeldung selbst: Ein Schlüssel erreicht nur
      Endpunkte aus ``SCHLUESSEL_LESEN`` (Umfang „lesen“) und zusätzlich
      ``SCHLUESSEL_ERFASSEN`` (Umfang „erfassen“). Alles andere: 403.
    - ``NIE_PER_SCHLUESSEL`` ist das zweite Netz: Konten, Passwort,
      Anmeldung aus, Schlüssel verwalten, Umzug, Sicherung, Export,
      Festsetzen, Löschen. Ein Wächtertest hält es von den Listen fern.
    - Falsche Schlüssel zählen im Anmeldeschutz (NK-128). Ein gültiger
      geht an der Sperre vorbei und zählt nicht.
    - „erfassen“ legt an und ändert nichts: auch kein vorhandenes Soll.
    - Schlüssel verwalten geht nur mit Sitzung, im offenen Modus gar nicht.
"""

from __future__ import annotations

import hashlib
import io

import pytest

from nebenkostenfix import zugriffsschluessel as zs
from nebenkostenfix.models import ApiSchluessel, User, db

PFAD = '/api/zugriffsschluessel'


def _anlegen(client, name='MCP-Server', umfang='lesen'):
    antwort = client.post(PFAD, json={'name': name, 'umfang': umfang})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return antwort.get_json()


def _kopf(schluessel):
    return {'Authorization': f'Bearer {schluessel}'}


def _haus(client):
    antwort = client.post('/api/properties', json={'name': 'Testhaus Lindenweg'})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return antwort.get_json()['id']


def _rechnung(property_id):
    from nebenkostenfix.models import CostCategory
    kat = CostCategory.query.filter_by(name='Wasserversorgung').first()
    return {'category_id': kat.id, 'property_id': property_id,
            'amount': '120.00', 'start_date': '2025-01-01',
            'end_date': '2025-12-31'}


# --- Anlegen und Ablage ----------------------------------------------------------

def test_der_schluessel_steht_genau_einmal_in_der_antwort(auth_client):
    neu = _anlegen(auth_client)
    assert neu['schluessel'].startswith('nkf_')
    assert neu['name'] == 'MCP-Server'
    assert neu['umfang'] == 'lesen'

    liste = auth_client.get(PFAD).get_json()
    assert len(liste) == 1
    assert 'schluessel' not in liste[0]
    assert neu['schluessel'] not in auth_client.get(PFAD).get_data(as_text=True)
    # Auch keine ersten Zeichen: der Schlüssel erscheint genau einmal, danach
    # erkennt man ihn am Namen.
    assert 'anzeige' not in liste[0] and 'anzeige' not in neu
    assert liste[0]['konto'] == 'pytest-vermieter'
    assert liste[0]['zuletzt_benutzt'] is None


def test_in_der_datenbank_liegt_nur_der_hash(auth_client):
    neu = _anlegen(auth_client)
    zeile = ApiSchluessel.query.one()
    assert zeile.hash == hashlib.sha256(neu['schluessel'].encode()).hexdigest()
    werte = [str(w) for w in (zeile.name, zeile.hash, zeile.umfang)]
    assert all(neu['schluessel'] not in w for w in werte)
    assert 'anzeige' not in ApiSchluessel.__table__.columns


@pytest.mark.parametrize('eingabe, fehlerfeld', [
    ({'name': '', 'umfang': 'lesen'}, 'name'),
    ({'name': 'x' * 61, 'umfang': 'lesen'}, 'name'),
    ({'name': 'MCP', 'umfang': 'alles'}, 'umfang'),
    ({'name': 'MCP'}, 'umfang'),
])
def test_anlegen_prueft_die_eingabe(auth_client, eingabe, fehlerfeld):
    antwort = auth_client.post(PFAD, json=eingabe)
    assert antwort.status_code == 400
    assert antwort.get_json()['feld'] == fehlerfeld
    assert ApiSchluessel.query.count() == 0


def test_mehr_als_zehn_schluessel_gibt_es_nicht(auth_client):
    for nummer in range(zs.HOECHSTENS):
        _anlegen(auth_client, name=f'Programm {nummer}')
    antwort = auth_client.post(PFAD, json={'name': 'einer zu viel', 'umfang': 'lesen'})
    assert antwort.status_code == 400
    # Der Knopf in der Liste heißt „Löschen“, die Meldung sagt dasselbe.
    assert 'Löschen Sie einen' in antwort.get_json()['error']
    assert ApiSchluessel.query.count() == zs.HOECHSTENS


def test_widerrufen_macht_den_schluessel_wertlos(auth_client, anon_client):
    neu = _anlegen(auth_client)
    assert anon_client.get('/api/properties', headers=_kopf(neu['schluessel'])).status_code == 200
    assert auth_client.delete(f"{PFAD}/{neu['id']}").status_code == 200
    antwort = anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'schluessel_ungueltig'
    assert auth_client.delete(f"{PFAD}/{neu['id']}").status_code == 404


# --- Anmelden mit dem Schlüssel --------------------------------------------------

def test_lesen_mit_schluessel_ohne_sitzung(auth_client, anon_client):
    neu = _anlegen(auth_client)
    antwort = anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 200
    # Kein Cookie: der Schlüssel eröffnet keine Sitzung.
    assert 'Set-Cookie' not in antwort.headers
    assert anon_client.get('/api/properties').status_code == 401


def test_auth_me_nennt_konto_und_schluessel(auth_client, anon_client):
    neu = _anlegen(auth_client)
    daten = anon_client.get('/api/auth/me', headers=_kopf(neu['schluessel'])).get_json()
    assert daten['username'] == 'pytest-vermieter'
    assert daten['schluessel'] == {'name': 'MCP-Server', 'umfang': 'lesen'}


def test_zuletzt_benutzt_wird_vermerkt(auth_client, anon_client):
    neu = _anlegen(auth_client)
    anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    assert auth_client.get(PFAD).get_json()[0]['zuletzt_benutzt'] is not None


@pytest.mark.parametrize('kopf', [
    'Bearer nkf_gibtesnicht',
    'Bearer nkf_',
    'bearer nkf_gibtesnicht',
    'Bearer nkf_' + 'a' * 300,
])
def test_falscher_schluessel_401(anon_client, auth_client, kopf):
    antwort = anon_client.get('/api/properties', headers={'Authorization': kopf})
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'schluessel_ungueltig'


@pytest.mark.parametrize('kopf', [
    'Bearer eyJhbGciOiJSUzI1NiJ9.vom-proxy',
    'Bearer ',
    'Basic cHJveHk6Z2VoZWlt',
])
def test_fremder_bearer_vom_proxy_laesst_die_sitzung_gelten(auth_client, anon_client, kopf):
    """Ein Reverse Proxy (etwa oauth2-proxy) kann einen eigenen Token im
    Authorization-Kopf weiterreichen. Nur ``Bearer nkf_…`` ist ein
    Zugriffsschlüssel; alles andere entscheidet wie bisher die Sitzung."""
    assert auth_client.get('/api/properties', headers={'Authorization': kopf}).status_code == 200
    ohne = anon_client.get('/api/properties', headers={'Authorization': kopf})
    assert ohne.status_code == 401
    assert ohne.get_json()['code'] == 'auth_required'


def test_falsche_schluessel_zaehlen_im_anmeldeschutz(auth_client, anon_client):
    from nebenkostenfix import anmeldeschutz
    # Jedes Mal ein anderer falscher Schluessel: derselbe waere schon nach
    # GRENZE_KONTO Versuchen fuer sich gesperrt, die Adresse zaehlte nicht weiter.
    for nummer in range(anmeldeschutz.GRENZE_IP):
        anon_client.get('/api/properties', headers=_kopf(f'nkf_{nummer:02d}falsch'))
    antwort = anon_client.get('/api/properties', headers=_kopf('nkf_99falsch'))
    assert antwort.status_code == 429
    assert antwort.get_json()['code'] == 'anmeldung_gesperrt'
    assert 'Retry-After' in antwort.headers


def test_ein_gueltiger_schluessel_kommt_an_der_sperre_vorbei(auth_client, anon_client):
    """Review zu #48: Hinter einem Reverse Proxy kommen alle von derselben
    Adresse. Zwanzig falsche Schlüssel sperrten sonst jedes Programm mit
    gültigem Schlüssel für 15 Minuten aus."""
    from nebenkostenfix import anmeldeschutz
    neu = _anlegen(auth_client)
    for nummer in range(anmeldeschutz.GRENZE_IP):
        anon_client.get('/api/properties', headers=_kopf(f'nkf_{nummer:02d}falsch'))
    antwort = anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 200, antwort.get_data(as_text=True)


def test_ein_gueltiger_schluessel_hebt_die_zaehlung_nicht_auf(auth_client, anon_client):
    """Sonst setzte ein fleißiges Programm hinter dem Proxy den Zähler der
    Adresse laufend zurück, und die Sperre griffe nie."""
    from nebenkostenfix import anmeldeschutz
    neu = _anlegen(auth_client)
    for nummer in range(anmeldeschutz.GRENZE_IP - 1):
        anon_client.get('/api/properties', headers=_kopf(f'nkf_{nummer:02d}falsch'))
    assert anon_client.get('/api/properties',
                           headers=_kopf(neu['schluessel'])).status_code == 200
    anon_client.get('/api/properties', headers=_kopf('nkf_98falsch'))
    antwort = anon_client.get('/api/properties', headers=_kopf('nkf_99falsch'))
    assert antwort.status_code == 429


def test_falsche_schluessel_sperren_nicht_die_anmeldung(auth_client, anon_client):
    """Ein Programm mit veralteten Schlüsseln, das in einer Schleife hängt,
    sperrt hinter einem Reverse Proxy sonst den Menschen gleich mit: alle
    kommen von derselben Adresse. Schlüssel und Passwort zählen getrennt."""
    from nebenkostenfix import anmeldeschutz
    from tests.conftest import TEST_PASSWORD, TEST_USER
    for nummer in range(anmeldeschutz.GRENZE_IP):
        anon_client.get('/api/properties', headers=_kopf(f'nkf_{nummer:02d}falsch'))
    antwort = anon_client.post('/login', json={'username': TEST_USER, 'password': TEST_PASSWORD})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)


def test_schluessel_eines_stillgelegten_kontos_401(auth_client, anon_client):
    neu = _anlegen(auth_client)
    konto = User.query.filter_by(username='pytest-vermieter').one()
    konto.is_active = False
    db.session.commit()
    antwort = anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 401


def test_schluessel_eines_stillgelegten_kontos_kommt_nicht_an_der_sperre_vorbei(
        auth_client, anon_client):
    """Vorbei an der Sperre kommt nur, wer gültig ist und ein aktives Konto hat."""
    from nebenkostenfix import anmeldeschutz
    neu = _anlegen(auth_client)
    konto = User.query.filter_by(username='pytest-vermieter').one()
    konto.is_active = False
    db.session.commit()
    for nummer in range(anmeldeschutz.GRENZE_IP):
        anon_client.get('/api/properties', headers=_kopf(f'nkf_{nummer:02d}falsch'))
    antwort = anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 429


def test_der_schluessel_entscheidet_auch_neben_einer_sitzung(auth_client):
    """Ein Lese-Schlüssel bleibt ein Lese-Schlüssel, auch wenn derselbe Client
    eine Sitzung hat, die schreiben dürfte."""
    neu = _anlegen(auth_client)
    hid = _haus(auth_client)
    antwort = auth_client.post('/api/invoices', json=_rechnung(hid),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 403
    assert antwort.get_json()['code'] == 'schluessel_umfang'


def test_ein_falscher_schluessel_faellt_nicht_auf_die_sitzung_zurueck(auth_client):
    antwort = auth_client.get('/api/properties', headers=_kopf('nkf_gibtesnicht'))
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'schluessel_ungueltig'


def test_der_schluessel_verlaengert_die_sitzung_nicht(auth_client):
    from nebenkostenfix.auth import SESSION_AKTIV_KEY
    neu = _anlegen(auth_client)
    with auth_client.session_transaction() as sitzung:
        sitzung[SESSION_AKTIV_KEY] = 1000
    auth_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    with auth_client.session_transaction() as sitzung:
        assert sitzung[SESSION_AKTIV_KEY] == 1000


def test_schluessel_von_b_neben_sitzung_von_a_ist_b(auth_client, app_ctx):
    from tests.conftest import TEST_USER
    passwort = 'zweites-konto-1'
    assert auth_client.post('/api/konten', json={
        'username': 'partnerin', 'password': passwort}).status_code == 201
    b = app_ctx.app.test_client()
    assert b.post('/login', json={'username': 'partnerin', 'password': passwort}).status_code == 200
    schluessel_b = _anlegen(b)['schluessel']
    wer = auth_client.get('/api/auth/me', headers=_kopf(schluessel_b)).get_json()
    assert wer['username'] == 'partnerin' != TEST_USER


@pytest.mark.parametrize('vor_sekunden, neu_geschrieben', [(30, False), (120, True)])
def test_zuletzt_benutzt_hoechstens_einmal_pro_minute(auth_client, anon_client,
                                                      vor_sekunden, neu_geschrieben):
    from datetime import timedelta

    from nebenkostenfix import zeit
    neu = _anlegen(auth_client)
    zeile = ApiSchluessel.query.one()
    damals = zeit.jetzt_utc() - timedelta(seconds=vor_sekunden)
    zeile.zuletzt_benutzt_am = damals
    db.session.commit()
    anon_client.get('/api/properties', headers=_kopf(neu['schluessel']))
    db.session.expire_all()
    assert (ApiSchluessel.query.one().zuletzt_benutzt_am != damals) is neu_geschrieben


# --- Umfang ----------------------------------------------------------------------

def test_lese_schluessel_darf_nicht_erfassen(auth_client, anon_client):
    neu = _anlegen(auth_client, umfang='lesen')
    hid = _haus(auth_client)
    antwort = anon_client.post('/api/invoices', json=_rechnung(hid),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 403
    assert antwort.get_json()['code'] == 'schluessel_umfang'


def test_lese_schluessel_darf_pruefen(auth_client, anon_client):
    """Die Vorprüfung ist POST, schreibt aber nichts. Sie gehört zu „lesen“."""
    neu = _anlegen(auth_client, umfang='lesen')
    antwort = anon_client.post('/api/billing/preflight', json={},
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 400  # Pflichtfelder fehlen, aber durchgelassen


def test_erfassen_schluessel_legt_eine_rechnung_an(auth_client, anon_client):
    neu = _anlegen(auth_client, umfang='erfassen')
    hid = _haus(auth_client)
    antwort = anon_client.post('/api/invoices', json=_rechnung(hid),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)


# --- Belege: der Assistent liest eine Rechnung ein und hängt das Original an ----

PDF = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n'


def _beleg(**felder):
    return {**felder, 'file': (io.BytesIO(PDF), 'stadtwerke.pdf')}


def test_erfassen_schluessel_legt_rechnung_mit_beleg_an(auth_client, anon_client):
    from nebenkostenfix.models import CostInvoice
    neu = _anlegen(auth_client, umfang='erfassen')
    hid = _haus(auth_client)
    antwort = anon_client.post('/api/invoices', content_type='multipart/form-data',
                               data=_beleg(**_rechnung(hid)),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    rechnung = db.session.get(CostInvoice, antwort.get_json()['id'])
    assert rechnung.invoice_document_id is not None


def test_erfassen_schluessel_legt_einen_sammelbeleg_an(auth_client, anon_client):
    """Ein Papier, mehrere Rechnungen: erst den Beleg, dann die Rechnungen
    mit dessen Kennung. Die Liste der Sammelbelege braucht der Assistent,
    um einen vorhandenen wiederzufinden."""
    neu = _anlegen(auth_client, umfang='erfassen')
    hid = _haus(auth_client)
    beleg = anon_client.post('/api/invoice_documents', content_type='multipart/form-data',
                             data=_beleg(property_id=str(hid)),
                             headers=_kopf(neu['schluessel']))
    assert beleg.status_code == 201, beleg.get_data(as_text=True)
    doc_id = beleg.get_json()['id']
    rechnung = anon_client.post('/api/invoices',
                                json={**_rechnung(hid), 'invoice_document_id': doc_id},
                                headers=_kopf(neu['schluessel']))
    assert rechnung.status_code == 201, rechnung.get_data(as_text=True)
    liste = anon_client.get('/api/invoice_documents', headers=_kopf(neu['schluessel']))
    assert [d['id'] for d in liste.get_json()] == [doc_id]


def test_erfassen_schluessel_aendert_keine_bestehenden_rechnungen(auth_client, anon_client):
    """„Rechnungsdatum für alle Rechnungen des Belegs“ schreibt in
    Rechnungen, die schon da sind. Das ist kein Anlegen mehr und bleibt
    beim Menschen -- ob als JSON oder als Formular geschickt."""
    from nebenkostenfix.models import CostInvoice
    neu = _anlegen(auth_client, umfang='erfassen')
    hid = _haus(auth_client)
    doc_id = auth_client.post('/api/invoice_documents', content_type='multipart/form-data',
                              data=_beleg(property_id=str(hid))).get_json()['id']
    vorhanden = auth_client.post('/api/invoices', json={
        **_rechnung(hid), 'invoice_document_id': doc_id,
        'rechnungsdatum': '2025-02-01'}).get_json()['id']
    auftrag = {**_rechnung(hid), 'invoice_document_id': doc_id,
               'rechnungsdatum': '2019-09-09', 'rechnungsdatum_fuer_beleg': 'true'}
    for art in ('json', 'formular'):
        if art == 'json':
            antwort = anon_client.post('/api/invoices', json=auftrag,
                                       headers=_kopf(neu['schluessel']))
        else:
            antwort = anon_client.post('/api/invoices', data=auftrag,
                                       headers=_kopf(neu['schluessel']))
        assert antwort.status_code == 403, (art, antwort.get_data(as_text=True))
        assert antwort.get_json()['code'] == 'nicht_per_schluessel'
    db.session.expire_all()
    assert str(db.session.get(CostInvoice, vorhanden).rechnungsdatum) == '2025-02-01'
    assert CostInvoice.query.count() == 1


# --- Vorauszahlungen: eine Serie setzt das Soll, ein Schlüssel überschreibt keins ---

def _mieter_mit_soll(auth_client, *stichtage):
    """Einzug 01.01.2024; ohne Angabe ein Soll von 100 € ab dem Einzug."""
    from datetime import date
    from tests import billing_factories as f
    mieter = f.tenant(f.apt(f.house(), 'EG', 50), 'Mieter A', date(2024, 1, 1), None)
    for ab, betrag in stichtage or (('2024-01-01', '100'),):
        antwort = auth_client.post(f'/api/tenants/{mieter.id}/vorauszahlung_soll',
                                   data={'gueltig_ab': ab, 'betrag': betrag})
        assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return mieter


def _serie(mieter_id, betrag, ab='2024-01-01'):
    return {'tenant_id': mieter_id, 'amount': betrag, 'type': 'Nebenkostenvorauszahlung',
            'payment_date': ab, 'end_date': '2024-03-31', 'is_recurring': True}


def _soll(mieter):
    db.session.expire_all()
    return [(str(s.gueltig_ab), str(s.betrag)) for s in mieter.vorauszahlung_soll]


def test_erfassen_schluessel_ueberschreibt_kein_vorhandenes_soll(auth_client, anon_client):
    """Review zu #48: Eine Serie ab dem Stichtag eines Solls berichtigte
    dessen Betrag (100,00 € wurden 1,00 €). Mit Schlüssel bleibt das Soll,
    die Zahlungen sind trotzdem erfasst, und die Antwort sagt es."""
    from nebenkostenfix.models import Payment
    neu = _anlegen(auth_client, umfang='erfassen')
    mieter = _mieter_mit_soll(auth_client)
    antwort = anon_client.post('/api/payments', json=_serie(mieter.id, '1.00'),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-01-01', '100.00')]
    assert Payment.query.filter_by(tenant_id=mieter.id).count() == 3
    daten = antwort.get_json()
    assert daten['soll_unveraendert'] is True
    assert '100,00 €' in daten['message'] and 'Oberfläche' in daten['message']


def test_mit_sitzung_berichtigt_die_serie_das_soll_wie_bisher(auth_client):
    mieter = _mieter_mit_soll(auth_client)
    antwort = auth_client.post('/api/payments', json=_serie(mieter.id, '1.00'))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-01-01', '1.00')]
    assert 'soll_unveraendert' not in antwort.get_json()


def test_erfassen_schluessel_legt_kein_zweites_soll_an(auth_client, anon_client):
    """Zweites Review zu #48: Eine Serie einen Tag nach dem Stichtag legte
    einen neuen an, ab dem nur noch 1,00 € galt. Mit Schlüssel bleibt das
    Soll, wie es ist, sobald es eins gibt."""
    from nebenkostenfix.models import Payment
    neu = _anlegen(auth_client, umfang='erfassen')
    mieter = _mieter_mit_soll(auth_client)
    antwort = anon_client.post('/api/payments', json=_serie(mieter.id, '1.00', ab='2024-01-02'),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-01-01', '100.00')]
    assert Payment.query.filter_by(tenant_id=mieter.id).count() == 3
    daten = antwort.get_json()
    assert daten['soll_unveraendert'] is True
    assert '100,00 €' in daten['message']


def test_erfassen_schluessel_legt_das_erste_soll_an(auth_client, anon_client):
    """Ohne Soll ist die Serie die erste Vereinbarung: das ist Anlegen."""
    from datetime import date
    from tests import billing_factories as f
    neu = _anlegen(auth_client, umfang='erfassen')
    mieter = f.tenant(f.apt(f.house(), 'EG', 50), 'Mieter A', date(2024, 1, 1), None)
    antwort = anon_client.post('/api/payments', json=_serie(mieter.id, '80.00', ab='2024-01-02'),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-01-02', '80.00')]
    assert 'soll_unveraendert' not in antwort.get_json()


def test_mit_sitzung_legt_die_serie_einen_neuen_stichtag_an(auth_client):
    mieter = _mieter_mit_soll(auth_client)
    antwort = auth_client.post('/api/payments', json=_serie(mieter.id, '120.00', ab='2024-02-01'))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-01-01', '100.00'), ('2024-02-01', '120.00')]


def test_serie_vor_dem_ersten_soll_vergleicht_mit_dem_ersten(auth_client, anon_client):
    neu = _anlegen(auth_client, umfang='erfassen')
    mieter = _mieter_mit_soll(auth_client, ('2024-03-01', '100'))
    antwort = anon_client.post('/api/payments', json=_serie(mieter.id, '1.00'),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-03-01', '100.00')]
    assert antwort.get_json()['soll_unveraendert'] is True


def test_hinweis_nur_gegen_das_soll_am_startdatum(auth_client, anon_client):
    """Die Serie passt zur Vereinbarung an ihrem Startdatum; dass später
    ein anderer Betrag gilt, ist kein Widerspruch."""
    neu = _anlegen(auth_client, umfang='erfassen')
    mieter = _mieter_mit_soll(auth_client, ('2024-01-01', '100'), ('2024-03-01', '120'))
    antwort = anon_client.post('/api/payments', json=_serie(mieter.id, '100.00', ab='2024-01-02'),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert _soll(mieter) == [('2024-01-01', '100.00'), ('2024-03-01', '120.00')]
    assert 'soll_unveraendert' not in antwort.get_json()


def test_gleiches_soll_mit_schluessel_ist_kein_hinweis(auth_client, anon_client):
    neu = _anlegen(auth_client, umfang='erfassen')
    mieter = _mieter_mit_soll(auth_client)
    antwort = anon_client.post('/api/payments', json=_serie(mieter.id, '100.00'),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 201
    assert 'soll_unveraendert' not in antwort.get_json()


def test_lese_schluessel_sieht_belege_laedt_aber_keine_hoch(auth_client, anon_client):
    neu = _anlegen(auth_client, umfang='lesen')
    hid = _haus(auth_client)
    assert anon_client.get('/api/invoice_documents',
                           headers=_kopf(neu['schluessel'])).status_code == 200
    antwort = anon_client.post('/api/invoice_documents', content_type='multipart/form-data',
                               data=_beleg(property_id=str(hid)),
                               headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 403
    assert antwort.get_json()['code'] == 'schluessel_umfang'


def test_einen_beleg_ersetzen_darf_kein_schluessel(auth_client, anon_client):
    """Ersetzen löscht die alte Datei. Das bleibt beim Menschen."""
    neu = _anlegen(auth_client, umfang='erfassen')
    hid = _haus(auth_client)
    doc_id = auth_client.post('/api/invoice_documents', content_type='multipart/form-data',
                              data=_beleg(property_id=str(hid))).get_json()['id']
    antwort = anon_client.put(f'/api/invoice_documents/{doc_id}',
                              content_type='multipart/form-data',
                              data=_beleg(property_id=str(hid)),
                              headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 403


@pytest.mark.parametrize('methode, pfad', [
    ('get', '/api/konten'),
    ('post', '/api/konten'),
    ('put', '/api/konto/passwort'),
    ('post', '/api/anmeldung/aus'),
    ('get', '/api/zugriffsschluessel'),
    ('post', '/api/zugriffsschluessel'),
    ('delete', '/api/zugriffsschluessel/1'),
    ('get', '/api/umzug/export'),
    ('post', '/api/backup/einspielen'),
    ('get', '/api/export'),
    ('post', '/api/billing/finalize'),
    ('post', '/api/aktualisierung/installieren'),
    ('delete', '/api/invoices/1'),
    ('get', '/api/dateien/beleg/1'),
    ('get', '/'),
])
def test_was_kein_schluessel_darf(auth_client, anon_client, methode, pfad):
    neu = _anlegen(auth_client, umfang='erfassen')
    antwort = getattr(anon_client, methode)(pfad, headers=_kopf(neu['schluessel']))
    assert antwort.status_code == 403, f'{methode.upper()} {pfad}'


# --- Wächter über die Listen -----------------------------------------------------

def _regeln(app_ctx):
    regeln = {}
    for regel in app_ctx.app.url_map.iter_rules():
        regeln.setdefault(regel.endpoint, set()).update(
            (regel.methods or set()) - {'HEAD', 'OPTIONS'})
    return regeln


def test_jeder_endpunkt_der_listen_existiert(app_ctx):
    regeln = _regeln(app_ctx)
    alle = zs.SCHLUESSEL_LESEN | zs.SCHLUESSEL_ERFASSEN | zs.NIE_PER_SCHLUESSEL
    assert sorted(alle - set(regeln)) == []


def test_lesen_heisst_get_oder_ausdruecklich_pruefen(app_ctx):
    """Ein Endpunkt in „lesen“ ist GET-only oder steht in PRUEFEN -- dort
    steht nur, was nachweislich nichts schreibt."""
    regeln = _regeln(app_ctx)
    schreibend = sorted(e for e in zs.SCHLUESSEL_LESEN
                        if regeln[e] != {'GET'} and e not in zs.PRUEFEN)
    assert schreibend == []
    assert zs.PRUEFEN <= zs.SCHLUESSEL_LESEN


def test_jeder_loeschweg_steht_in_nie(app_ctx):
    """Das zweite Netz deckt jede DELETE-Route ab, auch neue aus Upstream."""
    fehlt = sorted(e for e, methoden in _regeln(app_ctx).items()
                   if 'DELETE' in methoden and e not in zs.NIE_PER_SCHLUESSEL)
    assert fehlt == []


def test_nie_bleibt_nie(app_ctx):
    assert zs.NIE_PER_SCHLUESSEL & (zs.SCHLUESSEL_LESEN | zs.SCHLUESSEL_ERFASSEN) == set()


# --- Offener Modus, Ausschalten, Export ------------------------------------------

def test_im_offenen_modus_gibt_es_keine_schluessel(app_ctx, monkeypatch, tmp_path):
    from nebenkostenfix import datenordner, einstellungen
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    monkeypatch.setitem(app_ctx.app.config, 'DESKTOP', True)
    einstellungen.schreiben(ohne_anmeldung=True)
    client = app_ctx.app.test_client()
    antwort = client.post(PFAD, json={'name': 'MCP', 'umfang': 'lesen'})
    assert antwort.status_code == 409
    assert client.get(PFAD).get_json() == []


def test_anmeldung_ausschalten_loescht_die_schluessel(auth_client, monkeypatch, tmp_path):
    from nebenkostenfix import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    _anlegen(auth_client)
    antwort = auth_client.post('/api/anmeldung/aus',
                               json={'password': 'pytest-passwort-1'})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert ApiSchluessel.query.count() == 0


def test_der_export_enthaelt_keine_schluessel(auth_client):
    _anlegen(auth_client)
    daten = auth_client.get('/api/export').get_json()
    assert ApiSchluessel.__tablename__ not in daten
    assert 'users' not in daten
