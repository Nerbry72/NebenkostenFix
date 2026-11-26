"""Der PDF-Aufbau einer festgesetzten Abrechnung bleibt der, mit dem sie entstand.

Nacharbeit zum einstellbaren PDF-Aufbau. Geprüft wird:

* Die zweite Fassung einer bestehenden Abrechnung (einfach zu detailliert
  oder umgekehrt) setzt das Blatt mit dem Aufbau aus dem Schnappschuss der
  gültigen Version (``eingangsdaten['pdf_layout']``), nicht mit dem, der
  heute in den Einstellungen steht. Beide Fassungen sehen gleich aus.
* Eine Korrektur legt eine neue Version mit dem dann gültigen Aufbau an;
  die alte Version behält ihren. Eine spätere zweite Fassung folgt der
  neuen Version.
* Ein Sicherungspaket mit ``pdf_layout: None`` heißt „Standardaufbau“ und
  setzt einen eigenen Aufbau am Ziel auf den Standard zurück.
* Der GiroCode auf dem Deckblatt bleibt mit „Ihr Anteil“ auf einer Seite.
* Stehen die Verbrauchsnachweise nicht am Ende, steht kein Verweis „auf den
  folgenden Seiten“ allein auf einer Seite.

Alle Daten sind erfunden (Welt aus ``test_versionierung`` und
``test_pdf_standardlayout``).
"""

from __future__ import annotations

import copy

import pytest
import reportlab.rl_config

from nebenkostenfix import einstellungen, pdf_layout
from nebenkostenfix.pdf_generator import STANDARDLAYOUT, PDFGenerator
from nebenkostenfix.rechenkern import rechne
from test_pdf_standardlayout import (  # noqa: F401 -- feste_umgebung ist eine Fixture
    MIETERIN, OBJEKT, WOHNUNG, feste_umgebung, seiten, vorgang)
from test_versionierung import _bericht, _finalisiere, _welt

ROUTE = '/api/einstellungen/pdf-layout'

#: Ein eigener Aufbau: Belegliste vor der Aufstellung, Übersicht aus.
EIGENER = {'bloecke': [
    {'block': 'deckblatt', 'an': True},
    {'block': 'belegliste', 'an': True},
    {'block': 'kostenaufstellung', 'an': True},
    {'block': 'heizung_co2', 'an': True},
    {'block': 'ausweis_35a', 'an': True},
    {'block': 'uebersicht', 'an': False},
    {'block': 'zahlung', 'an': True},
    {'block': 'verbrauchsnachweise', 'an': True},
], 'girocode': 'aus'}


@pytest.fixture
def eigener_ordner(monkeypatch, tmp_path):
    """Die Einstellungsdatei liegt im eigenen Ordner, nicht im geteilten;
    die PDFs werden unkomprimiert geschrieben, damit der Text lesbar ist."""
    from nebenkostenfix import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)
    return tmp_path


def _flach(gelesen):
    return [zeile for seite in gelesen for zeile in seite]


def _zeilen(auth_client, bericht_id, art):
    antwort = auth_client.get(f'/api/dateien/{art}/{bericht_id}')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    return _flach(seiten(antwort.data))


def _wie_eigener(zeilen):
    """Das Blatt folgt ``EIGENER``: keine Übersicht, Belegliste vor Aufstellung."""
    assert 'Mieterdaten' not in zeilen, 'Übersicht ist im Schnappschuss aus'
    assert zeilen.index('Belegliste') < zeilen.index('Aufstellung der Kosten')


def _wie_standard(zeilen):
    assert 'Mieterdaten' in zeilen, 'Übersicht ist im Standard an'
    assert zeilen.index('Aufstellung der Kosten') < zeilen.index('Belegliste')


def _speichern(auth_client, layout):
    antwort = auth_client.put(ROUTE, json=layout)
    assert antwort.status_code == 200, antwort.get_data(as_text=True)


# --- Zweite Fassung: Schnappschuss statt heutiger Einstellung -------------


def test_die_zweite_fassung_folgt_dem_schnappschuss(auth_client, app_ctx, eigener_ordner):
    """Aufbau speichern, festsetzen, Aufbau ändern, zweite Fassung holen:
    das neue Blatt hat Reihenfolge und Blöcke des Schnappschusses."""
    _speichern(auth_client, EIGENER)
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id).id
    _wie_eigener(_zeilen(auth_client, bericht_id, 'abrechnung'))

    # Der Vermieter stellt den Aufbau zurück auf den Standard.
    assert auth_client.delete(ROUTE).status_code == 200
    assert einstellungen.lesen(eigener_ordner)['pdf_layout'] is None

    _finalisiere(auth_client, mieter_id, detailed=True)
    _wie_eigener(_zeilen(auth_client, bericht_id, 'abrechnung-detailliert'))
    # Der Schnappschuss selbst bleibt unberührt, es gibt keine neue Version.
    bericht = _bericht(bericht_id)
    assert len(bericht.versionen) == 1
    assert bericht.aktuelle_version.eingangsdaten['pdf_layout'] == EIGENER


def test_die_zweite_fassung_aus_dem_standard_bleibt_standard(
        auth_client, app_ctx, eigener_ordner):
    """Umgekehrt: festgesetzt im Standard, danach ein eigener Aufbau -- die
    zweite Fassung bleibt im Standard."""
    mieter_id, _, _ = _welt(app_ctx)
    bericht_id = _finalisiere(auth_client, mieter_id, detailed=True).id
    _speichern(auth_client, EIGENER)

    _finalisiere(auth_client, mieter_id)
    _wie_standard(_zeilen(auth_client, bericht_id, 'abrechnung'))


def test_version_ohne_layout_im_schnappschuss_gilt_als_standard(
        auth_client, app_ctx, eigener_ordner):
    """Versionen aus der Zeit vor dem einstellbaren Aufbau tragen keinen
    Aufbau im Schnappschuss; ihr Blatt entstand im Standard. Die zweite
    Fassung folgt dem, nicht der heutigen Einstellung."""
    from nebenkostenfix.models import db

    mieter_id, _, _ = _welt(app_ctx)
    bericht = _finalisiere(auth_client, mieter_id)
    bericht_id = bericht.id
    version = bericht.aktuelle_version
    eingangsdaten = dict(version.eingangsdaten)
    del eingangsdaten['pdf_layout']
    version.eingangsdaten = eingangsdaten
    db.session.commit()
    _speichern(auth_client, EIGENER)

    _finalisiere(auth_client, mieter_id, detailed=True)
    _wie_standard(_zeilen(auth_client, bericht_id, 'abrechnung-detailliert'))


def test_laden_aus_dem_schnappschuss_ist_tolerant():
    """Der Schnappschuss wird wie jede Einstellung tolerant gelesen."""

    class Version:
        def __init__(self, eingangsdaten):
            self.eingangsdaten = eingangsdaten

    assert pdf_layout.aus_schnappschuss(None) == pdf_layout.standard()
    assert pdf_layout.aus_schnappschuss(Version(None)) == pdf_layout.standard()
    assert pdf_layout.aus_schnappschuss(Version({})) == pdf_layout.standard()
    assert pdf_layout.aus_schnappschuss(Version({'pdf_layout': 'kaputt'})) == \
        pdf_layout.standard()
    assert pdf_layout.aus_schnappschuss(Version({'pdf_layout': EIGENER})) == EIGENER
    mit_fremdem = copy.deepcopy(EIGENER)
    mit_fremdem['bloecke'].append({'block': 'aus_der_zukunft', 'an': True})
    assert pdf_layout.aus_schnappschuss(Version({'pdf_layout': mit_fremdem})) == EIGENER


# --- Korrektur: neue Version, neuer Schnappschuss --------------------------


def test_die_korrektur_traegt_den_dann_gueltigen_aufbau(
        auth_client, app_ctx, eigener_ordner):
    """Version 1 behält ihren Aufbau, Version 2 trägt den von heute; die
    Korrektur setzt das Blatt mit dem neuen, und eine spätere zweite
    Fassung folgt Version 2, nicht der dann geänderten Einstellung."""
    from nebenkostenfix.models import BillingReportVersion, MeterReading, db

    _speichern(auth_client, EIGENER)
    mieter_id, _, lese_id = _welt(app_ctx)
    bericht = _finalisiere(auth_client, mieter_id)
    bericht_id, erste_id = bericht.id, bericht.aktuelle_version.id

    # Daten und Aufbau ändern sich, dann wird korrigiert.
    db.session.get(MeterReading, lese_id).value = 800.0
    db.session.commit()
    assert auth_client.delete(ROUTE).status_code == 200
    antwort = auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    bericht = _bericht(bericht_id)
    erste = db.session.get(BillingReportVersion, erste_id)
    zweite = bericht.aktuelle_version
    assert zweite.nummer == 2
    assert erste.eingangsdaten['pdf_layout'] == EIGENER
    assert zweite.eingangsdaten['pdf_layout'] == pdf_layout.standard()
    _wie_standard(_zeilen(auth_client, bericht_id, 'abrechnung'))

    # Danach wieder ein eigener Aufbau -- die zweite Fassung folgt Version 2.
    _speichern(auth_client, EIGENER)
    _finalisiere(auth_client, mieter_id, detailed=True)
    _wie_standard(_zeilen(auth_client, bericht_id, 'abrechnung-detailliert'))
    assert len(_bericht(bericht_id).versionen) == 2


# --- Sicherung: None heißt Standardaufbau -----------------------------------


def test_paket_mit_standardaufbau_setzt_eigenen_aufbau_zurueck(tmp_path):
    """Ein Paket nennt ``pdf_layout`` immer; ``None`` heißt, die Quelle lief
    im Standard. Einspielen ersetzt, also gilt danach auch hier der Standard."""
    from nebenkostenfix.backup import _anwendung_uebernehmen

    einstellungen.schreiben(tmp_path, pdf_layout=EIGENER)
    uebernommen = _anwendung_uebernehmen(tmp_path, {
        'updates_automatisch': True, 'pdf_layout': None})
    assert uebernommen == ['pdf_layout', 'updates_automatisch']
    assert einstellungen.lesen(tmp_path)['pdf_layout'] is None


@pytest.mark.parametrize('wert', ['kaputt', 42, ['deckblatt'], True])
def test_paket_mit_unbrauchbarem_aufbau_laesst_den_vorhandenen_stehen(tmp_path, wert):
    """Kein Objekt und nicht None: das ist kein Aufbau, sondern Unrat. Er
    überschreibt nichts -- wie ein fehlender Schlüssel in alten Paketen."""
    from nebenkostenfix.backup import _anwendung_uebernehmen

    einstellungen.schreiben(tmp_path, pdf_layout=EIGENER)
    assert _anwendung_uebernehmen(tmp_path, {'pdf_layout': wert}) == []
    assert einstellungen.lesen(tmp_path)['pdf_layout'] == EIGENER


# --- Das Blatt: GiroCode auf dem Deckblatt, Verweis der Nachweise -----------


def _seiten(fassung='einfach', layout=None, anschreiben=None):
    ergebnis = rechne(vorgang('nachzahlung'))
    erzeuger = PDFGenerator(
        property_name=OBJEKT, apartment_name=WOHNUNG, tenant_name=MIETERIN,
        start_date=ergebnis['start_date'], end_date=ergebnis['end_date'],
        detailliert=fassung == 'detailliert')
    return seiten(erzeuger.generate(
        ergebnis['line_items'], ergebnis['total_amount'], ergebnis['prepaid_amount'],
        co2_ausweis=ergebnis['co2'], landlord_share=ergebnis['landlord_share'],
        vorbehalt=ergebnis['vorbehalt'], ausweis_35a=ergebnis['ausweis_35a'],
        anschreiben=anschreiben, layout=layout))


def _brief(absaetze: int) -> str:
    fuell = ('Dies ist ein erfundener Absatz, der den Brief verlängert, damit '
             'der Betrag an das Seitenende rückt.')
    return '\n\n'.join(['Guten Tag,', *[fuell] * absaetze, 'Mit freundlichen Grüßen'])


def test_girocode_auf_dem_deckblatt_bleibt_beim_anteil(feste_umgebung):
    """Wie lang der Brief auch ist: „Ihr Anteil“, die Überschrift des
    GiroCodes und der Code selbst stehen auf derselben Seite."""
    layout = copy.deepcopy(pdf_layout.standard())
    layout['girocode'] = 'deckblatt'
    for absaetze in range(0, 24):
        gelesen = _seiten(layout=layout, anschreiben=_brief(absaetze))
        seite = next(s for s in gelesen if 'Ihr Anteil an den Nebenkosten' in s)
        assert 'Zahlung per GiroCode' in seite, absaetze
        assert '[Bild]' in seite, absaetze


def test_nachweise_vorn_ohne_verweis_auf_folgende_seiten(feste_umgebung):
    """Stehen die Nachweise direkt hinter dem Deckblatt, beginnen sie auf
    Seite 2; kein Verweis steht allein auf einer eigenen Seite."""
    folge = ['deckblatt', 'verbrauchsnachweise',
             *(b for b in STANDARDLAYOUT if b not in ('deckblatt', 'verbrauchsnachweise'))]
    layout = {'bloecke': [{'block': b, 'an': True} for b in folge], 'girocode': 'zahlung'}
    gelesen = _seiten(fassung='detailliert', layout=layout)
    assert 'Detaillierte Verbrauchsnachweise' in gelesen[1]
    zeilen = _flach(gelesen)
    assert not any('auf den folgenden Seiten' in z and 'Verbrauchsnachweise' in z
                   for z in zeilen)


def test_nachweise_am_ende_behalten_den_verweis(feste_umgebung):
    """Im Standard stehen die Nachweise am Ende; der Verweis bleibt."""
    zeilen = _flach(_seiten(fassung='detailliert'))
    assert 'Detaillierte Verbrauchsnachweise auf den folgenden Seiten' in zeilen


def test_uebersicht_hinter_der_aufstellung_verweist_auf_sie(feste_umgebung):
    """Die Fußnote der Übersicht nennt „die folgenden Seiten“ nur, wenn die
    Aufstellung der Kosten wirklich danach kommt."""
    def fussnote(layout):
        text = ' '.join(_flach(_seiten(layout=layout)))
        return text[text.index('Wie sich jede Position errechnet'):][:120]

    standard = fussnote(None)
    assert 'mit Rechenweg und Belegen, steht auf den folgenden Seiten.' in standard

    folge = ['deckblatt', 'kostenaufstellung', 'uebersicht',
             *(b for b in STANDARDLAYOUT
               if b not in ('deckblatt', 'kostenaufstellung', 'uebersicht'))]
    layout = {'bloecke': [{'block': b, 'an': True} for b in folge], 'girocode': 'zahlung'}
    hinten = fussnote(layout)
    assert 'mit Rechenweg und Belegen, steht in der Aufstellung der Kosten.' in hinten
    assert 'folgenden Seiten' not in hinten
