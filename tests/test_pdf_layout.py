"""Das Layout der Abrechnungs-PDF ist einstellbar: Blöcke, Reihenfolge, GiroCode.

Vorbereitung eines PDF-Layout-Editors, Schritt 2a (Server, ohne
Oberfläche). Geprüft wird:

* die Einstellung ``pdf_layout`` mit Werkseinstellung, und dass sie bei
  Sicherung und Umzug mitwandert;
* das strenge Prüfen beim Speichern (Pflichtblock aus, fester Block
  verschoben, unbekannter oder doppelter Block, unbekannter GiroCode-Ort)
  und das tolerante Laden (Unbekanntes fällt weg, Fehlendes rückt an seine
  Standardstelle, Pflicht bleibt an);
* dass ``generate()`` die Blöcke in der Reihenfolge des Layouts baut und der
  GiroCode beim Zahlungshinweis, auf dem Deckblatt oder gar nicht steht;
* die vier Routen unter ``/api/einstellungen/pdf-layout``;
* dass die Festsetzung das verwendete Layout im Schnappschuss ablegt.

Die Welt der PDF-Tests ist die erfundene aus ``test_pdf_standardlayout``.
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
from test_versionierung import _finalisiere, _welt

ROUTE = '/api/einstellungen/pdf-layout'


def _layout(*reihenfolge, aus=(), girocode='zahlung'):
    """Ein Layout in Speicherform: die Blöcke in dieser Reihenfolge."""
    return {'bloecke': [{'block': b, 'an': b not in aus} for b in reihenfolge],
            'girocode': girocode}


def _standard_mit(**aenderung):
    layout = copy.deepcopy(pdf_layout.standard())
    layout.update(aenderung)
    return layout


@pytest.fixture
def eigener_ordner(monkeypatch, tmp_path):
    """Die Einstellungsdatei liegt im eigenen Ordner, nicht im geteilten."""
    from nebenkostenfix import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    return tmp_path


# --- Blöcke und Einstellung ----------------------------------------------


def test_standardlayout_und_blockmethoden_haben_dieselben_schluessel():
    """Jeder Block des Standards hat eine Methode und umgekehrt."""
    erzeuger = PDFGenerator('Haus', 'EG', 'Mieter', '2024-01-01', '2024-12-31')
    assert set(erzeuger._bloecke()) == set(STANDARDLAYOUT)
    assert len(STANDARDLAYOUT) == len(set(STANDARDLAYOUT))
    assert tuple(b.id for b in pdf_layout.BLOECKE) == STANDARDLAYOUT


def test_pdf_layout_ist_einstellung_und_wandert_mit(tmp_path):
    assert 'pdf_layout' in einstellungen.STANDARD
    assert einstellungen.STANDARD['pdf_layout'] is None
    assert 'pdf_layout' in einstellungen.UEBERTRAGBAR

    layout = _standard_mit(girocode='aus')
    einstellungen.schreiben(tmp_path, pdf_layout=layout)
    paket = einstellungen.uebertragbar(einstellungen.lesen(tmp_path), False, True)
    assert paket['pdf_layout'] == layout


def test_eine_sicherung_bringt_das_layout_zurueck(tmp_path):
    """Einspielen übernimmt das Layout -- tolerant, wie beim Laden."""
    from nebenkostenfix.backup import _anwendung_uebernehmen

    layout = _layout(*reversed(STANDARDLAYOUT[1:]))
    layout['bloecke'].insert(0, {'block': 'deckblatt', 'an': True})
    layout['bloecke'].append({'block': 'aus_der_zukunft', 'an': True})
    assert 'pdf_layout' in _anwendung_uebernehmen(tmp_path, {'pdf_layout': layout})
    gelesen = einstellungen.lesen(tmp_path)['pdf_layout']
    assert [b['block'] for b in gelesen['bloecke']] == \
        ['deckblatt', *reversed(STANDARDLAYOUT[1:])]

    # Ein altes Paket ohne Layout lässt das vorhandene stehen.
    assert _anwendung_uebernehmen(tmp_path, {'updates_automatisch': True}) == \
        ['updates_automatisch']
    assert einstellungen.lesen(tmp_path)['pdf_layout'] == gelesen


# --- Prüfen beim Speichern -----------------------------------------------


FEHLERFAELLE = {
    'pflichtblock_aus': (
        _layout(*STANDARDLAYOUT, aus=('kostenaufstellung',)),
        'Aufstellung der Kosten'),
    'fester_block_verschoben': (
        _layout('uebersicht', 'deckblatt', *STANDARDLAYOUT[2:]),
        'erster Stelle'),
    'unbekannter_block': (
        _layout(*STANDARDLAYOUT, 'werbung'),
        'werbung'),
    'doppelter_block': (
        _layout(*STANDARDLAYOUT, 'belegliste'),
        'doppelt'),
    'unbekannter_girocode_ort': (
        _layout(*STANDARDLAYOUT, girocode='rueckseite'),
        'GiroCode'),
    'keine_liste': ({'bloecke': 'deckblatt'}, 'Liste'),
}


@pytest.mark.parametrize('fall', sorted(FEHLERFAELLE))
def test_pruefen_weist_jeden_fehlerfall_ab(fall):
    daten, stichwort = FEHLERFAELLE[fall]
    with pytest.raises(pdf_layout.LayoutFehler) as fehler:
        pdf_layout.pruefen(daten)
    assert stichwort in str(fehler.value)


def test_pruefen_nimmt_ein_gueltiges_layout_an():
    daten = _layout('deckblatt', 'kostenaufstellung', 'belegliste', 'zahlung',
                    'heizung_co2', 'ausweis_35a', 'uebersicht', 'verbrauchsnachweise',
                    aus=('uebersicht', 'ausweis_35a'), girocode='deckblatt')
    assert pdf_layout.pruefen(daten) == daten


# --- Tolerantes Laden ----------------------------------------------------


def test_laden_ohne_einstellung_ist_der_standard():
    for roh in (None, 'kaputt', 42, [], {}, {'bloecke': None}):
        assert pdf_layout.laden(roh) == pdf_layout.standard(), roh
    assert pdf_layout.standard() == _layout(*STANDARDLAYOUT)


def test_laden_ignoriert_unbekannte_und_doppelte_bloecke():
    roh = _layout(*STANDARDLAYOUT, 'aus_der_zukunft', 'belegliste')
    roh['bloecke'].insert(3, 'kein_eintrag')
    assert pdf_layout.laden(roh) == pdf_layout.standard()


def test_laden_setzt_fehlende_bloecke_an_ihre_standardstelle():
    roh = _layout('deckblatt', 'belegliste', 'kostenaufstellung', 'zahlung',
                  aus=('belegliste',))
    geladen = pdf_layout.laden(roh)
    assert [b['block'] for b in geladen['bloecke']] == [
        'deckblatt', 'uebersicht', 'belegliste', 'kostenaufstellung',
        'heizung_co2', 'ausweis_35a', 'zahlung', 'verbrauchsnachweise']
    an = {b['block']: b['an'] for b in geladen['bloecke']}
    assert an['belegliste'] is False and an['uebersicht'] is True


def test_laden_haelt_pflicht_und_feste_stelle_ein():
    roh = _layout('uebersicht', 'deckblatt', *STANDARDLAYOUT[2:],
                  aus=('deckblatt', 'zahlung'), girocode='irgendwo')
    geladen = pdf_layout.laden(roh)
    assert geladen['bloecke'][0] == {'block': 'deckblatt', 'an': True}
    assert {'block': 'zahlung', 'an': True} in geladen['bloecke']
    assert geladen['girocode'] == 'zahlung'
    assert pdf_layout.aktive_bloecke(geladen)[:2] == ['deckblatt', 'uebersicht']


# --- Das Blatt folgt dem Layout ------------------------------------------


def _text(fall='nachzahlung', fassung='detailliert', layout=None):
    ergebnis = rechne(vorgang(fall))
    erzeuger = PDFGenerator(
        property_name=OBJEKT, apartment_name=WOHNUNG, tenant_name=MIETERIN,
        start_date=ergebnis['start_date'], end_date=ergebnis['end_date'],
        detailliert=fassung == 'detailliert')
    pdf = erzeuger.generate(
        ergebnis['line_items'], ergebnis['total_amount'], ergebnis['prepaid_amount'],
        co2_ausweis=ergebnis['co2'], landlord_share=ergebnis['landlord_share'],
        vorbehalt=ergebnis['vorbehalt'], ausweis_35a=ergebnis['ausweis_35a'],
        layout=layout)
    return seiten(pdf)


def _flach(gelesen):
    return [zeile for seite in gelesen for zeile in seite]


def test_ohne_layout_und_mit_standard_entsteht_dasselbe_blatt(feste_umgebung):
    assert _text() == _text(layout=pdf_layout.standard())


def test_die_reihenfolge_im_blatt_folgt_dem_layout(feste_umgebung):
    layout = _layout('deckblatt', 'belegliste', 'zahlung', 'kostenaufstellung',
                     'heizung_co2', 'ausweis_35a', 'uebersicht', 'verbrauchsnachweise',
                     aus=('uebersicht', 'ausweis_35a'))
    zeilen = _flach(_text(layout=layout))
    stelle = {marke: zeilen.index(marke) for marke in (
        'Ihr Anteil an den Nebenkosten', 'Belegliste', 'Zahlung per GiroCode',
        'Aufstellung der Kosten', 'Heizkosten und CO2',
        'Detaillierte Verbrauchsnachweise')}
    assert sorted(stelle, key=stelle.get) == list(stelle)
    assert 'Mieterdaten' not in zeilen, 'Übersicht ist aus'
    assert 'Lohnanteile nach § 35a EStG' not in zeilen, '§ 35a ist aus'


def test_girocode_auf_dem_deckblatt(feste_umgebung):
    gelesen = _text(fassung='einfach', layout=_standard_mit(girocode='deckblatt'))
    zeilen = _flach(gelesen)
    assert zeilen.count('Zahlung per GiroCode') == 1
    assert zeilen.count('[Bild]') == 1
    giro = zeilen.index('Zahlung per GiroCode')
    assert zeilen.index('Ihr Anteil an den Nebenkosten') < giro \
        < zeilen.index('Mit freundlichen Grüßen')
    # Der Zahlungshinweis steht weiter am Ende, nur ohne Kasten.
    assert giro < zeilen.index('Rückfragen zur Abrechnung beantworte ich gern.')


def test_girocode_aus(feste_umgebung):
    zeilen = _flach(_text(fassung='einfach', layout=_standard_mit(girocode='aus')))
    assert 'Zahlung per GiroCode' not in zeilen and '[Bild]' not in zeilen
    assert any(z.startswith('Bitte überweisen') for z in zeilen)


def test_girocode_beim_zahlungshinweis_ist_der_standard(feste_umgebung):
    zeilen = _flach(_text(fassung='einfach'))
    assert zeilen.index('Rückfragen zur Abrechnung beantworte ich gern.') \
        < zeilen.index('Zahlung per GiroCode')


# --- Die Routen ----------------------------------------------------------


def test_get_zeigt_layout_standard_und_bloecke(auth_client, eigener_ordner):
    antwort = auth_client.get(ROUTE)
    assert antwort.status_code == 200
    daten = antwort.get_json()
    assert daten['layout'] == daten['standard'] == pdf_layout.standard()
    assert daten['ist_standard'] is True
    bloecke = {b['block']: b for b in daten['bloecke']}
    assert list(bloecke) == list(STANDARDLAYOUT)
    assert bloecke['deckblatt']['fest'] is True and bloecke['deckblatt']['pflicht'] is True
    assert bloecke['kostenaufstellung']['pflicht'] is True
    assert bloecke['uebersicht']['pflicht'] is False
    assert all(b['titel'] for b in daten['bloecke'])
    assert [o['ort'] for o in daten['girocode_orte']] == ['zahlung', 'deckblatt', 'aus']


def test_put_speichert_und_delete_setzt_zurueck(auth_client, eigener_ordner):
    layout = _standard_mit(girocode='aus')
    layout['bloecke'][1]['an'] = False
    antwort = auth_client.put(ROUTE, json=layout)
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.get_json()['layout'] == layout
    assert antwort.get_json()['ist_standard'] is False
    assert einstellungen.lesen(eigener_ordner)['pdf_layout'] == layout
    assert auth_client.get(ROUTE).get_json()['layout'] == layout

    zurueck = auth_client.delete(ROUTE)
    assert zurueck.status_code == 200
    assert zurueck.get_json()['ist_standard'] is True
    assert einstellungen.lesen(eigener_ordner)['pdf_layout'] is None


@pytest.mark.parametrize('fall', sorted(FEHLERFAELLE))
def test_put_antwortet_bei_jedem_fehlerfall_mit_400(auth_client, eigener_ordner, fall):
    daten, stichwort = FEHLERFAELLE[fall]
    antwort = auth_client.put(ROUTE, json=daten)
    assert antwort.status_code == 400
    assert stichwort in antwort.get_json()['error']
    assert einstellungen.lesen(eigener_ordner)['pdf_layout'] is None


def test_put_ohne_json_ist_400(auth_client, eigener_ordner):
    assert auth_client.put(ROUTE, data='kein json').status_code == 400


def test_vorschau_erzeugt_pdf_ohne_zu_speichern(auth_client, eigener_ordner, monkeypatch):
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)
    layout = _standard_mit()
    layout['bloecke'][1]['an'] = False  # Übersicht aus
    antwort = auth_client.post(ROUTE + '/vorschau', json=layout)
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert antwort.mimetype == 'application/pdf'
    assert antwort.data.startswith(b'%PDF')
    zeilen = _flach(seiten(antwort.data))
    assert 'Aufstellung der Kosten' in zeilen and 'Mieterdaten' not in zeilen
    assert einstellungen.lesen(eigener_ordner)['pdf_layout'] is None

    mit_uebersicht = auth_client.post(ROUTE + '/vorschau', json=pdf_layout.standard())
    assert 'Mieterdaten' in _flach(seiten(mit_uebersicht.data))


def test_vorschau_prueft_wie_speichern(auth_client, eigener_ordner):
    daten, stichwort = FEHLERFAELLE['pflichtblock_aus']
    antwort = auth_client.post(ROUTE + '/vorschau', json=daten)
    assert antwort.status_code == 400
    assert stichwort in antwort.get_json()['error']


# --- Schnappschuss -------------------------------------------------------


def test_die_festsetzung_legt_das_layout_im_schnappschuss_ab(
        auth_client, app_ctx, eigener_ordner):
    layout = _standard_mit(girocode='deckblatt')
    layout['bloecke'][5]['an'] = False  # Belegliste aus
    einstellungen.schreiben(eigener_ordner, pdf_layout=layout)
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    assert report.aktuelle_version.eingangsdaten['pdf_layout'] == layout


def test_ohne_einstellung_steht_der_standard_im_schnappschuss(
        auth_client, app_ctx, eigener_ordner):
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    assert report.aktuelle_version.eingangsdaten['pdf_layout'] == pdf_layout.standard()
