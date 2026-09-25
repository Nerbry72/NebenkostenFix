"""Das Anschreiben mit Zahlungsaufforderung als editierbare Vorlage (NK-064).

Das Deckblatt trug einen festen Gruß; der Vermieter konnte den Ton
seines Anschreibens nicht bestimmen. Die Vorlage lebt je Objekt in der
Tabelle ``anschreiben_vorlagen``, ohne Eintrag spricht der Vorgabetext
aus ``anschreiben.py``. Die Platzhalter füllt ``text_fuer`` aus dem
Ergebnis der Abrechnung -- Geld in der Sprache des Dokuments, Komma
statt Punkt. Die Zahlungsaufforderung ist Teil der Vorlage; der
Platzhalter ``{aufforderung}`` bleibt bei einem Guthaben gewollt leer,
denn es gäbe nichts zu fordern.

Das Auslesen des PDF arbeitet wie in ``test_pdf_fuss.py``: Seiten
unkomprimiert, Textströme direkt gelesen, Umbrüche wieder
zusammengeklebt.
"""

from __future__ import annotations

import os
import re
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import reportlab.rl_config

from anschreiben import VORGABE, PLATZHALTER, fuelle, text_fuer, absaetze
from pdf_cover_page import build_cover_page_elements

ZEITRAUM = {'start_date': '2025-01-01', 'end_date': '2025-12-31'}


@pytest.fixture
def unkomprimiert(monkeypatch):
    """Seiten ohne Kompression, damit der Text lesbar im Strom steht."""
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)


def _entschluesselt(stueck: str) -> str:
    """Löst die Escapes eines PDF-Textstücks auf (Umlaute als Oktal)."""
    ausgabe = []
    i = 0
    while i < len(stueck):
        zeichen = stueck[i]
        if zeichen == '\\' and i + 1 < len(stueck):
            if stueck[i + 1] in '01234567':
                ziffern = ''
                j = i + 1
                while j < len(stueck) and len(ziffern) < 3 \
                        and stueck[j] in '01234567':
                    ziffern += stueck[j]
                    j += 1
                ausgabe.append(chr(int(ziffern, 8)))
                i = j
                continue
            ausgabe.append(stueck[i + 1])
            i += 2
            continue
        ausgabe.append(zeichen)
        i += 1
    return ''.join(ausgabe).replace(chr(0x80), '€')


def _blaetter(pdf: bytes) -> list[str]:
    """Der geklebte Text jedes Blatts, in der Reihenfolge des Zeichnens."""
    blaetter = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            # Unkomprimierter Inhalt (pageCompression 0) oder Bildstrom:
            # der rohe Inhalt bleibt, Klammern findet der Ausdruck dort
            # genauso.
            pass
        stuecke = [_entschluesselt(m) for m in re.findall(
            r'\(((?:\\.|[^\\)])*)\)', roh.decode('latin-1', 'replace'))]
        blaetter.append(re.sub(r'\s+', '', ''.join(stuecke)))
    return blaetter


def _geklebt(pdf: bytes) -> str:
    """Der Text des ganzen Dokuments, alle Stroeme zusammengeklebt.

    Der QR-Code zeichnet seinen Bildstrom vor den Inhalt des Deckblatts
    -- auf Position im Strom ist also kein Verlass; gezählt wird der
    Text, nicht der Ort.
    """
    return ''.join(_blaetter(pdf))


# --- Die Renderfunktion -------------------------------------------------------


def test_die_renderfunktion_fuellt_bekannte_platzhalter():
    """Bekannte Platzhalter bekommen ihren Wert, Geld in Dokumentsprache."""
    text = text_fuer(
        'Hallo {mieter_name}, Wohnung {wohnung_name}.',
        mieter_name='Anna Mieterin', wohnung_name='EG links',
        objekt_name='Haus am Anger', zeitraum='01.01.2025 bis 31.12.2025',
        gesamtsumme=Decimal('1200.00'), vorauszahlungen=Decimal('300.00'),
        saldo=Decimal('900.00'))
    assert text == 'Hallo Anna Mieterin, Wohnung EG links.'


def test_unbekannte_platzhalter_bleiben_sichtbar_stehen():
    """Ein Platzhalter ohne Wert wird nicht still gelöscht: die Lücke schreit."""
    text = fuelle('Gruß an {mieter_name}, Frist {einwendungsfrist}.',
                  {'mieter_name': 'Anna Mieterin'})
    assert '{einwendungsfrist}' in text
    assert 'Anna Mieterin' in text


def test_die_aufforderung_steht_nur_bei_nachzahlung():
    """Bei einer Nachzahlung fordert der Satz den Betrag, beim Guthaben schweigt er."""
    kwargs = dict(
        mieter_name='Anna', wohnung_name='EG links', objekt_name='Haus',
        zeitraum='2025', gesamtsumme=Decimal('1200.00'),
        vorauszahlungen=Decimal('300.00'))
    nachzahlung = text_fuer(VORGABE, saldo=Decimal('900.00'), **kwargs)
    assert 'Wir bitten Sie, den ausstehenden Betrag in Höhe von 900,00 €' in nachzahlung
    assert 'Nachzahlung' in nachzahlung

    guthaben = text_fuer(VORGABE, saldo=Decimal('-150.00'), **kwargs)
    assert 'Wir bitten Sie' not in guthaben
    assert 'Guthaben' in guthaben
    assert '150,00 €' in guthaben

    ausgeglichen = text_fuer(VORGABE, saldo=Decimal('0.00'), **kwargs)
    assert 'Wir bitten Sie' not in ausgeglichen
    assert 'Ausgleich' in ausgeglichen


def test_die_vorgabe_benutzt_nur_bekannte_platzhalter():
    """Der Vorgabetext kann nur Platzhalter tragen, die die Renderfunktion füllt."""
    assert re.findall(r'\{(\w+)\}', VORGABE), 'Der Vorgabetext trägt Platzhalter'
    for name in set(re.findall(r'\{(\w+)\}', VORGABE)):
        assert name in PLATZHALTER


def test_die_absaetze_bleiben_getrennt_und_werden_maskiert():
    """Leere Zeilen trennen Absätze; ``&`` stirbt nicht als XML-Stück."""
    stuecke = absaetze('Erster Absatz.\n\nZweiter & letzter.')
    assert stuecke == ['Erster Absatz.', 'Zweiter &amp; letzter.']
    # Eine gewollt leere Aufforderung hinterlässt keinen leeren Absatz.
    stuecke = absaetze('Vor der Lücke.\n\n\n\nNach der Lücke.')
    assert stuecke == ['Vor der Lücke.', 'Nach der Lücke.']


# --- Die Routen der Vorlage ---------------------------------------------------


def test_ohne_eigenen_text_antwortet_die_vorgabe(auth_client, app_ctx):
    """GET ohne Eintrag liefert den Vorgabetext samt Platzhalterliste."""
    from billing_factories import house

    objekt = house()
    from models import db
    db.session.commit()

    antwort = auth_client.get(f'/api/properties/{objekt.id}/anschreiben')
    assert antwort.status_code == 200
    koerper = antwort.get_json()
    assert koerper['ist_vorgabe'] is True
    assert koerper['text'] == VORGABE
    assert koerper['platzhalter'] == PLATZHALTER


def test_der_vermieter_hinterlegt_und_ändert_seinen_text(auth_client, app_ctx):
    """PUT speichert je Objekt; GET liefert den eigenen Text zurück."""
    from billing_factories import house

    objekt = house()
    from models import db
    db.session.commit()

    antwort = auth_client.put(
        f'/api/properties/{objekt.id}/anschreiben',
        json={'text': 'Liebe Anna, hier ist Ihre Abrechnung.'})
    assert antwort.status_code == 200
    assert antwort.get_json()['ist_vorgabe'] is False

    antwort = auth_client.get(f'/api/properties/{objekt.id}/anschreiben')
    koerper = antwort.get_json()
    assert koerper['ist_vorgabe'] is False
    assert koerper['text'] == 'Liebe Anna, hier ist Ihre Abrechnung.'

    # Ein zweites PUT ändert, statt zu verdoppeln: die Paarung ist einzigartig.
    auth_client.put(f'/api/properties/{objekt.id}/anschreiben',
                    json={'text': 'Und noch einmal.'})
    from models import AnschreibenVorlage
    zeilen = AnschreibenVorlage.query.filter_by(property_id=objekt.id).all()
    assert len(zeilen) == 1
    assert zeilen[0].text == 'Und noch einmal.'


def test_die_leere_vorlage_wird_abgelehnt(auth_client, app_ctx):
    """Ohne Text gibt es nichts zu sagen: die Route lehnt ab."""
    from billing_factories import house

    objekt = house()
    from models import db
    db.session.commit()

    for text in ('', '   '):
        antwort = auth_client.put(
            f'/api/properties/{objekt.id}/anschreiben', json={'text': text})
        assert antwort.status_code == 400


def test_loeschen_fuehrt_zurueck_zur_vorgabe(auth_client, app_ctx):
    """DELETE wirft den eigenen Text weg; danach spricht wieder die Vorgabe."""
    from billing_factories import house

    objekt = house()
    from models import db
    db.session.commit()

    auth_client.put(f'/api/properties/{objekt.id}/anschreiben',
                    json={'text': 'Mein Text.'})
    antwort = auth_client.delete(f'/api/properties/{objekt.id}/anschreiben')
    assert antwort.status_code == 200
    koerper = antwort.get_json()
    assert koerper['ist_vorgabe'] is True
    assert koerper['text'] == VORGABE


def test_ein_unbekanntes_objekt_wird_abgewiesen(auth_client):
    antwort = auth_client.get('/api/properties/424242/anschreiben')
    assert antwort.status_code == 404


# --- Die Einbindung ins PDF ---------------------------------------------------


def _deckblatt(unkomprimiert, anschreiben=None) -> str:
    """Das Deckblatt als geklebten Text, wie der Leser es sieht."""
    elemente = build_cover_page_elements(
        property_name='Haus am Anger', apartment_name='EG links',
        tenant_name='Anna Mieterin', start_date='2025-01-01',
        end_date='2025-12-31', total_amount=Decimal('1200.00'),
        prepaid_amount=Decimal('300.00'), balance=Decimal('900.00'),
        anschreiben=anschreiben)
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from io import BytesIO

    puffer = BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4)
    doc.build(elemente)
    return _blaetter(puffer.getvalue())[0]


def test_die_vorlage_spricht_auf_dem_deckblatt(unkomprimiert):
    """Mit Vorlage steht das Anschreiben statt des festen Grußes."""
    anschreiben = text_fuer(
        VORGABE, mieter_name='Anna Mieterin', wohnung_name='EG links',
        objekt_name='Haus am Anger', zeitraum='01.01.2025 bis 31.12.2025',
        gesamtsumme=Decimal('1200.00'), vorauszahlungen=Decimal('300.00'),
        saldo=Decimal('900.00'))
    blatt = _deckblatt(unkomprimiert, anschreiben)

    assert 'Sehrgeehrte/rAnnaMieterin,' in blatt
    assert 'DieAbrechnungergibtbeiGesamtkostenvon1200,00€' in blatt
    assert 'WirbittenSie,denausstehendenBetraginHöhevon900,00€auszugleichen.' in blatt
    # Der feste Gruß der Software ist verdrängt.
    assert 'ImFolgenden' not in blatt


def test_ohne_vorlage_bleibt_es_beim_festen_gruß(unkomprimiert):
    """Kein Anschreiben hinterlegt: der Deckblatt-Gruß wie bisher."""
    blatt = _deckblatt(unkomprimiert)
    assert 'Sehrgeehrte/rAnnaMieterin,' in blatt
    assert 'ImFolgenden' in blatt


# --- Die Welt: vom Vermieter bis zum Blatt des Mieters ------------------------


def _welt(app_ctx):
    """Zwei Mieter mit Wasserzählern, eine Rechnung, Vorauszahlung für A.

    Dieselbe Welt wie in ``test_versionierung.py``: Annas Abrechnung
    ergibt 1200,00 € bei 300,00 € Vorauszahlung -- eine Nachzahlung von
    900,00 €, genau der Fall, in dem das Anschreiben fordert.
    """
    from models import db
    from billing_factories import (
        apt, category, house, meter, payment, profile, reading, tenant,
    )

    kategorie = category('Wasserversorgung')
    prop = house()
    wohnung_a = apt(prop, 'EG links', 50.0)
    wohnung_b = apt(prop, 'EG rechts', 50.0)
    mieter_a = tenant(wohnung_a, 'Anna Mieterin', move_in=date(2024, 1, 1))
    mieter_b = tenant(wohnung_b, 'Berta Mieterin', move_in=date(2024, 1, 1))
    profile(mieter_a, kategorie, 'direkt')
    profile(mieter_b, kategorie, 'direkt')
    zaehler_a = meter(prop, kategorie, 'WA-A', is_main=False, apartment=wohnung_a)
    zaehler_b = meter(prop, kategorie, 'WA-B', is_main=False, apartment=wohnung_b)
    reading(zaehler_a, date(2025, 1, 1), 0.0)
    lese_ende = reading(zaehler_a, date(2025, 12, 31), 1000.0)
    reading(zaehler_b, date(2025, 1, 1), 0.0)
    reading(zaehler_b, date(2025, 12, 31), 1000.0)
    from billing_factories import invoice
    invoice(prop, kategorie, 2400.0, date(2025, 1, 1), date(2025, 12, 31))
    payment(mieter_a, 300.0, date(2025, 6, 1))
    db.session.commit()
    return mieter_a.id, prop.id, lese_ende.id


def _finalisiere(auth_client, mieter_id):
    """Finalisiert Annas Abrechnung und liefert den Bericht."""
    from models import TenantBillingReport

    antwort = auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter_id, **ZEITRAUM})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return TenantBillingReport.query.one()


def test_die_festsetzung_druckt_das_anschreiben_des_objekts(
        auth_client, app_ctx, unkomprimiert):
    """Das gespeicherte PDF trägt das Anschreiben -- mit den Zahlen dieses Laufs."""
    mieter_id, objekt_id, _ = _welt(app_ctx)

    auth_client.put(
        f'/api/properties/{objekt_id}/anschreiben',
        json={'text': 'Liebe/r {mieter_name},\n\n'
                      'Ihre Abrechnung für {zeitraum} liegt bei. '
                      '{aufforderung}\n\nIhr Vermieter'})
    report = _finalisiere(auth_client, mieter_id)

    pdf = (Path(os.environ['NAS_MOUNT_PATH']) / report.document_path).read_bytes()
    blatt = _geklebt(pdf)
    assert 'Liebe/rAnnaMieterin,' in blatt
    assert 'IhreAbrechnungfür01.01.2025bis31.12.2025liegtbei.' in blatt
    assert 'WirbittenSie,denausstehendenBetraginHöhevon900,00€auszugleichen.' in blatt
    assert 'IhrVermieter' in blatt
    # Der Platzhalter der Aufforderung ist gefüllt, nicht sichtbar stehen
    # geblieben -- bei einer Nachzahlung gibt es etwas zu fordern.
    assert '{aufforderung}' not in blatt


def test_ohne_eigene_vorlage_druckt_die_vorgabe(auth_client, app_ctx, unkomprimiert):
    """Ohne PUT spricht der Vorgabetext -- mit Gesamtsumme, Vorauszahlung, Saldo."""
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)

    pdf = (Path(os.environ['NAS_MOUNT_PATH']) / report.document_path).read_bytes()
    blatt = _geklebt(pdf)
    assert 'Sehrgeehrte/rAnnaMieterin,' in blatt
    assert 'WohnungEGlinks' in blatt
    assert 'Gesamtkostenvon1200,00€' in blatt
    assert 'Vorauszahlungenvon300,00€' in blatt
    assert '900,00€(Nachzahlung)' in blatt
    assert 'WirbittenSie,denausstehendenBetraginHöhevon900,00€auszugleichen.' in blatt


def test_die_korrektur_wickelt_dieselbe_vorlage(auth_client, app_ctx, unkomprimiert):
    """Die Korrektur liest die Vorlage neu; der eigene Text steht auch dann."""
    mieter_id, objekt_id, lese_id = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    alte_id = report.id

    auth_client.put(
        f'/api/properties/{objekt_id}/anschreiben',
        json={'text': 'Korrigierter Gruß an {mieter_name}.'})

    # Ohne geaenderte Eingaben waere die Korrektur nur eine Kopie (D-59);
    # ein geaenderter Zaehlerstand aendert das Ergebnis und macht den Lauf echt.
    from models import db, MeterReading, TenantBillingReport
    lese_ende = db.session.get(MeterReading, lese_id)
    lese_ende.value = 800.0
    db.session.commit()

    antwort = auth_client.post(f'/api/billing/reports/{alte_id}/korrektur')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    frisch = db.session.get(TenantBillingReport, alte_id)
    # Seit NK-131 neutral benannt (belege_export nennt die Fassung).
    assert re.match(r'^\d{4}/[0-9a-f]{32}\.pdf$', frisch.document_path)
    pdf = (Path(os.environ['NAS_MOUNT_PATH']) / frisch.document_path).read_bytes()
    blatt = _geklebt(pdf)
    assert 'KorrigierterGrußanAnnaMieterin.' in blatt
