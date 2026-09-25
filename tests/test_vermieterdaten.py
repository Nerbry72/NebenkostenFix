"""NK-124 — Vermieterdaten: API, IBAN-Prüfung und der Weg in den GiroCode.

Der GiroCode auf der Abrechnung (NK-055) las bisher nur Umgebungsvariablen
lesen — ein Fachfeld ohne Oberfläche (F-50). Jetzt führt die Tabelle
``vermieterdaten``; die Umgebung bleibt Rückfallebene, Feld für Feld
(D-81). Diese Tests prüfen:

* die Prüfung der IBAN (Form und Mod-97-Quersumme),
* das Auslesen des Vermieter-Ausweises mit Vorrang Datenbank vor Umgebung,
* die API /api/vermieter (lesen, schreiben, leeren),
* und dass der GiroCode die Datenbank tatsächlich benutzt.
"""

import pytest
from reportlab.platypus import Spacer

import girocode_generator
from girocode_generator import (
    EingabeFehler,
    iban_pruefen,
    iban_saeubern,
    vermieter_ausweis,
)
from models import Vermieterdaten, db


@pytest.fixture
def client(app_ctx, auth_client, monkeypatch):
    """Angemeldeter Test-Mandant mit aufgeraeumter Vermieter-Tabelle.

    Die .env des Behaelters setzt VERMIETER_NAME und VERMIETER_IBAN; die
    gehoeren nicht in die Tests, sonst prueft niemand den Fall "beides
    leer". Jeder Test startet deshalb ohne diese Variablen und mit
    leerer Tabelle.
    """
    monkeypatch.delenv('VERMIETER_NAME', raising=False)
    monkeypatch.delenv('VERMIETER_IBAN', raising=False)
    Vermieterdaten.query.delete()
    db.session.commit()
    return auth_client


# --- Die IBAN: Form und Quersumme (DIN ISO 13616, Mod 97) ---

def test_iban_saeubern_entfernt_leerzeichen_und_bindestriche():
    assert iban_saeubern(' DE89 3704-0044-0532 0130 00 ') == 'DE89370400440532013000'


def test_iban_pruefen_nimmt_echte_ibans():
    # Die Muster-IBAN der Bundesbank und eine mit Leerzeichen/Bindestrichen.
    iban_pruefen('DE89370400440532013000')
    iban_pruefen('de89 3704-0044 0532 0130 00')


def test_iban_pruefen_weist_falsche_quersumme_ab():
    # DE89 ... 013001: die letzte Stelle verdreht, die Quersumme kippt.
    with pytest.raises(EingabeFehler) as aufgetreten:
        iban_pruefen('DE89370400440532013001')
    assert aufgetreten.value.feld == 'iban'


def test_iban_pruefen_weist_falsche_form_ab():
    for kaputt in ['', 'DE89', 'DE8937040044053201300',      # zu kurz
                   'GG89370400440532013000',                 # kein Land
                   'DE8A370400440532013000']:                # Buchstabe in der Prüfziffer
        with pytest.raises(EingabeFehler):
            iban_pruefen(kaputt)


# --- Der Ausweis: Datenbank vor Umgebung (D-81) ---

def test_ausweis_fehlt_ohne_alles(client):
    assert vermieter_ausweis() == ('', '')


def test_ausweis_nimmt_umgebung(client, monkeypatch):
    monkeypatch.setenv('VERMIETER_NAME', 'Erika Musterfrau')
    monkeypatch.setenv('VERMIETER_IBAN', 'DE89370400440532013000')
    assert vermieter_ausweis() == ('Erika Musterfrau', 'DE89370400440532013000')


def test_ausweis_datenbank_gewinnt_gegen_umgebung(client, monkeypatch):
    db.session.add(Vermieterdaten(name='Vermieter Vornachweis',
                                  iban='DE02120300000000202051'))
    db.session.commit()
    monkeypatch.setenv('VERMIETER_NAME', 'Erika Musterfrau')
    monkeypatch.setenv('VERMIETER_IBAN', 'DE89370400440532013000')
    assert vermieter_ausweis() == ('Vermieter Vornachweis', 'DE02120300000000202051')


def test_ausweis_mischt_feldweise(client, monkeypatch):
    """Ohne IBAN in der Datenbank springt die Umgebung für dieses Feld ein."""
    db.session.add(Vermieterdaten(name='Vermieter Vornachweis', iban=None))
    db.session.commit()
    monkeypatch.setenv('VERMIETER_IBAN', 'DE89370400440532013000')
    assert vermieter_ausweis() == ('Vermieter Vornachweis', 'DE89370400440532013000')


# --- Die API /api/vermieter ---

def test_api_zeigt_quellen(client, monkeypatch):
    monkeypatch.setenv('VERMIETER_NAME', 'Erika Musterfrau')
    antwort = client.get('/api/vermieter')
    assert antwort.status_code == 200
    stand = antwort.get_json()
    assert stand['name'] == 'Erika Musterfrau'
    assert stand['name_quelle'] == 'umgebung'
    assert stand['iban_quelle'] == 'fehlt'
    assert stand['girocode_bereit'] is False


def test_api_speichert_und_liest_zurueck(client):
    gesendet = {'name': 'Vermieter Vornachweis', 'iban': 'DE89370400440532013000'}
    assert client.put('/api/vermieter', json=gesendet).status_code == 200
    stand = client.get('/api/vermieter').get_json()
    assert stand['name'] == 'Vermieter Vornachweis'
    assert stand['name_quelle'] == 'datenbank'
    assert stand['iban_quelle'] == 'datenbank'
    assert stand['girocode_bereit'] is True


def test_api_weist_falsche_iban_ab(client):
    antwort = client.put('/api/vermieter',
                         json={'name': 'Einer', 'iban': 'DE00370400440532013000'})
    assert antwort.status_code == 400
    fehler = antwort.get_json()
    assert fehler['feld'] == 'iban'
    # Die Anfrage starb vor dem Festsetzen; der Rueckbau der Anwendung
    # wirft die halbe Zeile weg — im Test passiert das von Hand:
    db.session.rollback()
    # Nichts durcheinander gerutscht:
    assert client.get('/api/vermieter').get_json()['name'] == ''


def test_api_leeren_laesst_umgebung_wieder_gelten(client, monkeypatch):
    monkeypatch.setenv('VERMIETER_NAME', 'Erika Musterfrau')
    client.put('/api/vermieter', json={'name': 'Vermieter Vornachweis', 'iban': ''})
    client.put('/api/vermieter', json={'name': '', 'iban': ''})
    stand = client.get('/api/vermieter').get_json()
    assert stand['name'] == 'Erika Musterfrau'
    assert stand['name_quelle'] == 'umgebung'


# --- Der GiroCode benutzt die Datenbank ---

def _girocode_ruf(monkeypatch):
    """Baut den GiroCode-Aufruf nach und faengt Empfaenger und IBAN ab."""
    gefangen = {}
    monkeypatch.setattr(
        girocode_generator, '_build_epc_payload',
        lambda name, iban, betrag, zweck:
            gefangen.update(name=name, iban=iban) or 'NK-TEST')
    # Kein echtes Bild noetig; ein Leerraum genuegt als Fluss-Element.
    monkeypatch.setattr(
        girocode_generator, '_generate_qr_image',
        lambda payload, size_mm=38: Spacer(1, 1))
    return gefangen


def test_girocode_liest_aus_datenbank(client, monkeypatch):
    db.session.add(Vermieterdaten(name='Vermieter Vornachweis',
                                  iban='DE02120300000000202051'))
    db.session.commit()
    gefangen = _girocode_ruf(monkeypatch)
    teile = girocode_generator.build_girocode_elements(
        balance=1851.22, tenant_name='Erika Musterfrau', apartment_name='EG',
        start_date='2024-01-01', end_date='2024-12-31')
    assert teile, 'Der GiroCode soll entstehen.'
    assert gefangen['name'] == 'Vermieter Vornachweis'
    assert gefangen['iban'] == 'DE02120300000000202051'


def test_girocode_ohne_vermieter_fehlt_hoeflich(client, monkeypatch):
    gefangen = _girocode_ruf(monkeypatch)
    teile = girocode_generator.build_girocode_elements(
        balance=1851.22, tenant_name='Erika Musterfrau', apartment_name='EG',
        start_date='2024-01-01', end_date='2024-12-31')
    assert teile == []
    assert gefangen == {}
