"""IBAN-Prüfung: Nicht-ASCII-Ziffern wurden angenommen.

`iban_pruefen` prüft mit `\\d` (passt auf jede Unicode-Ziffer) und rechnet
mit `int()` (wandelt arabisch-indische und Vollbreiten-Ziffern um). Eine IBAN
mit solchen Ziffern besteht die Prüfsumme, wird unverändert gespeichert und
landet im GiroCode, den keine Banking-App lesen kann. Erwartet: 400, Feld iban,
und die vorher gespeicherte IBAN bleibt stehen.
Daten fiktiv (Beispiel-IBAN DE02120300000000202051).
"""

import pytest

from nebenkostenfix.girocode_generator import iban_pruefen
from nebenkostenfix.models import Vermieterdaten, db
from nebenkostenfix.validation import EingabeFehler

GUELTIG = 'DE02120300000000202051'
NAME = 'Fiktive Vermietung'

# "DE02120300000000202051" mit anderer Schreibweise einzelner Ziffern
ARABISCH = 'DE٠٢120300000000202051'          # Prüfziffern arabisch-indisch
VOLLBREITE = 'DE０２120300000000202051'       # Prüfziffern Vollbreite
ARABISCH_KONTO = 'DE0212030000000020205١'    # letzte Kontoziffer arabisch-indisch

NICHT_ASCII = pytest.mark.parametrize(
    'iban', [ARABISCH, VOLLBREITE, ARABISCH_KONTO],
    ids=['arabisch-indisch', 'vollbreite', 'arabisch-im-kontoteil'])

FORM_MELDUNG = 'Diese IBAN hat keine gültige Form'
PRUEFSUMME_MELDUNG = 'Diese IBAN hat eine falsche Prüfsumme'


@pytest.fixture
def client(app_ctx, auth_client, monkeypatch):
    """Angemeldet, ohne Vermieter aus der Umgebung, mit leerer Tabelle."""
    monkeypatch.delenv('VERMIETER_NAME', raising=False)
    monkeypatch.delenv('VERMIETER_IBAN', raising=False)
    Vermieterdaten.query.delete()
    db.session.commit()
    return auth_client


def _gespeicherte_iban():
    zeile = Vermieterdaten.einziger()
    return zeile.iban if zeile is not None else None


@NICHT_ASCII
def test_put_mit_nicht_ascii_ziffern_ergibt_400_und_laesst_iban_stehen(client, iban):
    vorher = client.put('/api/vermieter', json={'name': NAME, 'iban': GUELTIG})
    assert vorher.status_code == 200
    assert _gespeicherte_iban() == GUELTIG

    antwort = client.put('/api/vermieter', json={'name': NAME, 'iban': iban})
    assert antwort.status_code == 400, (
        f'IBAN mit Nicht-ASCII-Ziffern angenommen: {antwort.status_code} {antwort.get_json()}')
    fehler = antwort.get_json()
    assert fehler['feld'] == 'iban'
    assert fehler['error'].startswith(FORM_MELDUNG)

    # Die Anfrage starb vor dem Festsetzen; der Rückbau der Anwendung wirft
    # die halbe Zeile weg. Im Test passiert das von Hand (wie in
    # tests/test_vermieterdaten.py).
    db.session.rollback()
    assert _gespeicherte_iban() == GUELTIG
    stand = client.get('/api/vermieter').get_json()
    assert stand['iban'] == GUELTIG
    assert stand['girocode_bereit'] is True


@NICHT_ASCII
def test_iban_pruefen_direkt_lehnt_nicht_ascii_ab(iban):
    with pytest.raises(EingabeFehler) as aufgetreten:
        iban_pruefen(iban)
    assert aufgetreten.value.feld == 'iban'
    assert aufgetreten.value.meldung.startswith(FORM_MELDUNG)


# --- Gegenproben: gültige ASCII-IBANs gehen weiter durch ---

@pytest.mark.parametrize('eingabe', [GUELTIG, 'de02 1203-0000 0000 2020 51'],
                         ids=['sauber', 'klein-mit-leerraum'])
def test_gueltige_ascii_iban_wird_angenommen(eingabe):
    assert iban_pruefen(eingabe) == GUELTIG


def test_put_mit_gueltiger_iban_ist_girocode_bereit(client):
    antwort = client.put('/api/vermieter',
                         json={'name': NAME, 'iban': 'de02 1203-0000 0000 2020 51'})
    assert antwort.status_code == 200
    stand = antwort.get_json()
    assert stand['girocode_bereit'] is True
    assert _gespeicherte_iban() == GUELTIG


def test_falsche_pruefsumme_bleibt_pruefsummenfehler():
    with pytest.raises(EingabeFehler) as aufgetreten:
        iban_pruefen('DE02120300000000202052')
    assert aufgetreten.value.feld == 'iban'
    assert aufgetreten.value.meldung.startswith(PRUEFSUMME_MELDUNG)


def test_leeres_feld_leert_die_iban_wie_bisher(client):
    assert client.put('/api/vermieter', json={'name': NAME, 'iban': GUELTIG}).status_code == 200
    antwort = client.put('/api/vermieter', json={'name': NAME, 'iban': ''})
    assert antwort.status_code == 200
    assert _gespeicherte_iban() is None
    assert antwort.get_json()['girocode_bereit'] is False
