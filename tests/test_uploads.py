"""NK-129: Uploads nach Positivliste, Auslieferung nur per Kennung (F-55, F-59).

Eine hochgeladene HTML- oder SVG-Datei lief bis NK-129 unter der Adresse der
Anwendung mit der Sitzung des Vermieters. Jetzt entscheiden die ersten Bytes
ueber den Typ, und die Auslieferung setzt ihn fest.
"""

import io
import os

import pytest

import uploads

PDF = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 24
JPG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + b'\x00' * 20
WEBP = b'RIFF\x24\x00\x00\x00WEBPVP8 ' + b'\x00' * 20
HEIC = b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic' + b'\x00' * 8
HTML = b'<!doctype html><script>fetch("/api/tenants")</script>'
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
POLYGLOTT = b'<html><!-- %PDF-1.4 --><script>alert(1)</script></html>'


@pytest.mark.parametrize('inhalt,endung', [
    (PDF, 'pdf'), (PNG, 'png'), (JPG, 'jpg'), (WEBP, 'webp'), (HEIC, 'heic'),
    (HTML, None), (SVG, None), (POLYGLOTT, None), (b'', None),
    (b'PK\x03\x04', None), (b'MZ\x90\x00', None),
])
def test_erkennung_am_inhalt(inhalt, endung):
    assert uploads.erkenne(inhalt[:32]) == endung


def _haus(app_ctx):
    from models import Property, db
    prop = Property(name='Musterhaus Lindenstraße')
    db.session.add(prop)
    db.session.commit()
    return prop


def _hochladen(client, prop_id, inhalt, name):
    return client.post('/api/invoice_documents', content_type='multipart/form-data',
                       data={'property_id': str(prop_id),
                             'file': (io.BytesIO(inhalt), name)})


@pytest.mark.parametrize('inhalt,name', [
    (HTML, 'rechnung.html'), (SVG, 'logo.svg'), (HTML, 'getarnt.pdf'),
    (POLYGLOTT, 'poly.pdf'), (b'MZ\x90\x00' + b'\x00' * 40, 'setup.exe'),
])
def test_html_svg_und_getarntes_werden_abgelehnt(app_ctx, auth_client, inhalt, name):
    from models import InvoiceDocument
    prop = _haus(app_ctx)
    antwort = _hochladen(auth_client, prop.id, inhalt, name)
    assert antwort.status_code == 400
    assert 'Dateityp' in antwort.get_json()['error']
    assert InvoiceDocument.query.count() == 0


def test_die_endung_kommt_aus_dem_inhalt(app_ctx, auth_client):
    """Ein PNG namens beleg.pdf wird als .png abgelegt."""
    from models import InvoiceDocument
    prop = _haus(app_ctx)
    assert _hochladen(auth_client, prop.id, PNG, 'beleg.pdf').status_code == 201
    assert InvoiceDocument.query.one().document_path.endswith('.png')


def test_abgelehnter_upload_legt_keinen_ordner_an(app_ctx, auth_client):
    from app import nas_handler
    prop = _haus(app_ctx)
    vorher = set(os.listdir(nas_handler.nas_mount_path))
    _hochladen(auth_client, prop.id, HTML, 'x.html')
    assert set(os.listdir(nas_handler.nas_mount_path)) == vorher


def test_ablesefoto_als_html_wird_abgelehnt(app_ctx, auth_client):
    from billing_factories import category, house, meter
    from models import MeterReading
    prop = house('Fotohaus')
    zaehler = meter(prop, category('Wasserversorgung'), 'Z-1', is_main=True)
    antwort = auth_client.post('/api/readings', content_type='multipart/form-data', data={
        'meter_id': str(zaehler.id), 'reading_date': '2025-01-01', 'value': '1',
        'file': (io.BytesIO(SVG), 'foto.jpg')})
    assert antwort.status_code == 400
    assert MeterReading.query.count() == 0


# --- Auslieferung --------------------------------------------------------------

def test_pdf_wird_per_kennung_mit_festem_typ_ausgeliefert(app_ctx, auth_client):
    from models import InvoiceDocument
    prop = _haus(app_ctx)
    _hochladen(auth_client, prop.id, PDF, 'beleg.pdf')
    dok = InvoiceDocument.query.one()
    antwort = auth_client.get(f'/api/dateien/dokument/{dok.id}')
    assert antwort.status_code == 200
    assert antwort.mimetype == 'application/pdf'
    assert antwort.headers['X-Content-Type-Options'] == 'nosniff'
    assert antwort.headers['Content-Security-Policy'] == uploads.CSP_PDF
    assert antwort.headers['Content-Disposition'].startswith('inline')
    assert antwort.data == PDF


def test_bild_laeuft_in_der_sandbox(app_ctx, auth_client):
    from models import InvoiceDocument
    prop = _haus(app_ctx)
    _hochladen(auth_client, prop.id, PNG, 'foto.png')
    antwort = auth_client.get(f'/api/dateien/dokument/{InvoiceDocument.query.one().id}')
    assert antwort.mimetype == 'image/png'
    assert antwort.headers['Content-Security-Policy'].startswith('sandbox')


def test_heic_und_altbestand_nur_als_download(app_ctx, auth_client):
    """Eine Altdatei (vor NK-129 hochgeladen) mit HTML-Inhalt kommt nur als
    Download, als octet-stream, in der Sandbox -- nie als Seite."""
    from app import nas_handler
    from models import InvoiceDocument, db
    prop = _haus(app_ctx)
    for inhalt, name, mime in ((HEIC, 'bild.heic', 'image/heic'),
                               (HTML, 'alt.html', 'application/octet-stream')):
        pfad = os.path.join(nas_handler.nas_mount_path, 'alt', name)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, 'wb') as datei:
            datei.write(inhalt)
        dok = InvoiceDocument(property_id=prop.id, filename=name,
                              document_path=f'alt/{name}')
        db.session.add(dok)
        db.session.commit()
        antwort = auth_client.get(f'/api/dateien/dokument/{dok.id}')
        assert antwort.status_code == 200
        assert antwort.mimetype == mime
        assert antwort.headers['Content-Disposition'].startswith('attachment')
        assert antwort.headers['Content-Security-Policy'].startswith('sandbox')
        assert antwort.headers['X-Content-Type-Options'] == 'nosniff'


def test_pfad_aus_der_datenbank_bleibt_im_belegordner(app_ctx, auth_client, tmp_path):
    """Ein manipulierter Datenbankeintrag (../ oder absolut ausserhalb)
    liefert nichts aus."""
    from models import InvoiceDocument, db
    geheim = tmp_path / 'geheim.pdf'
    geheim.write_bytes(PDF)
    prop = _haus(app_ctx)
    for pfad in ('../../../../etc/passwd', str(geheim), '/etc/passwd'):
        dok = InvoiceDocument(property_id=prop.id, filename='x', document_path=pfad)
        db.session.add(dok)
        db.session.commit()
        assert auth_client.get(f'/api/dateien/dokument/{dok.id}').status_code == 404


def test_verknuepfung_aus_dem_belegordner_heraus_zaehlt_nicht(app_ctx, auth_client, tmp_path):
    from app import nas_handler
    from models import InvoiceDocument, db
    draussen = tmp_path / 'draussen.pdf'
    draussen.write_bytes(PDF)
    link = os.path.join(nas_handler.nas_mount_path, 'link.pdf')
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(draussen, link)
    prop = _haus(app_ctx)
    dok = InvoiceDocument(property_id=prop.id, filename='x', document_path='link.pdf')
    db.session.add(dok)
    db.session.commit()
    try:
        assert auth_client.get(f'/api/dateien/dokument/{dok.id}').status_code == 404
    finally:
        os.unlink(link)


def test_unbekannte_art_und_kennung(app_ctx, auth_client):
    assert auth_client.get('/api/dateien/passwd/1').status_code == 404
    assert auth_client.get('/api/dateien/dokument/999').status_code == 404


def test_der_alte_pfadweg_ist_weg(app_ctx):
    """/api/files gibt es nicht mehr; ein unbekannter Pfad faellt schon in
    die Sperre (deny-by-default antwortet vor dem 404)."""
    import app as app_module
    regeln = {r.rule for r in app_module.app.url_map.iter_rules()}
    assert '/api/files' not in regeln


def test_dateien_brauchen_anmeldung(app_ctx, anon_client):
    assert anon_client.get('/api/dateien/dokument/1').status_code == 401


def test_mietvertrag_ueber_beide_wege(app_ctx, auth_client):
    from billing_factories import apt, house
    prop = house('Vertragshaus')
    wohnung = apt(prop, 'EG', 40.0)
    antwort = auth_client.post('/api/tenants', content_type='multipart/form-data', data={
        'apartment_id': str(wohnung.id), 'name': 'Anna Mieterin',
        'move_in_date': '2025-01-01',
        'contract_file': (io.BytesIO(PDF), 'vertrag.pdf')})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    mieter_id = antwort.get_json()['id']
    for adresse in (f'/api/tenants/{mieter_id}/contract',
                    f'/api/dateien/mietvertrag/{mieter_id}'):
        antwort = auth_client.get(adresse)
        assert antwort.status_code == 200
        assert antwort.mimetype == 'application/pdf'
        assert antwort.headers['X-Content-Type-Options'] == 'nosniff'


def test_die_dateiauswahl_bietet_nur_erlaubte_typen():
    """Die Oberflaeche schlaegt vor, was der Server annimmt (kein .docx mehr
    beim Mietvertrag -- das haette der Server abgelehnt)."""
    import re
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / 'static' / 'index.html').read_text(
        encoding='utf-8')
    for feld in re.findall(r'<input[^>]*type="file"[^>]*>', html):
        if 'id="lizenz-datei"' in feld:
            # NK-080: die Lizenz ist kein Beleg. Der Browser liest sie und
            # schickt sie als Text an /api/lizenz; abgelegt wird sie nie
            # im Belegordner.
            continue
        if 'id="import-datei"' in feld:
            # NK-161: eine Tabelle ist kein Beleg; sie wird gelesen und
            # verworfen (uploads.pruefe_tabelle), nie abgelegt.
            continue
        if 'id="umzug-datei-einstellungen"' in feld:
            # NK-164: das Umzugspaket ist kein Beleg. Es geht in Stücken nach
            # umzug-arbeit/ und wird dort als Paket geprüft (backup.py).
            continue
        accept = re.search(r'accept="([^"]+)"', feld)
        for eintrag in (accept.group(1).split(',') if accept else []):
            assert eintrag in {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic',
                               '.heif', 'application/pdf', 'image/jpeg',
                               'image/png', 'image/webp', 'image/heic'}, eintrag
