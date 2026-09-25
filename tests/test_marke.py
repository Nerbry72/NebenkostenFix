"""Die Marke NebenkostenFix hält überall (NK-155, D-94, D-95)."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

import marke

WURZEL = Path(__file__).resolve().parents[1]


def _text(relativ: str) -> str:
    return (WURZEL / relativ).read_text(encoding='utf-8')


def test_die_svgs_sind_aus_marke_py_erzeugt():
    """Wer das Zeichen ändert, lässt scripts/marke_bilder.py laufen."""
    assert _text('static/marke/zeichen.svg').strip() == marke.zeichen_svg()
    assert _text('static/marke/favicon.svg').strip() == marke.zeichen_svg(titel=False)
    for datei in ('static/marke/favicon.ico', 'static/marke/zeichen-180.png',
                  'packaging/windows/nebenkostenfix.ico', 'packaging/windows/installer-gross.bmp',
                  'packaging/windows/installer-klein.bmp'):
        assert (WURZEL / datei).stat().st_size > 0, datei


def test_das_windows_icon_hat_alle_groessen():
    from PIL import Image
    with Image.open(WURZEL / 'packaging' / 'windows' / 'nebenkostenfix.ico') as icon:
        groessen = {g[0] for g in icon.info['sizes']}
    assert {16, 24, 32, 48, 64, 128, 256} <= groessen


def test_kein_alter_produktname_in_oberflaeche_und_paket():
    for relativ in ('static/index.html', 'static/app.js', 'static/style.css',
                    'static/anmeldung.css', 'auth.py', 'desktop.py'):
        assert 'ImmoCalc' not in _text(relativ), relativ


def test_die_oberflaeche_traegt_name_zeichen_und_favicon():
    seite = _text('static/index.html')
    assert '<title>NebenkostenFix</title>' in seite
    assert 'src="/static/marke/zeichen.svg"' in seite
    assert 'href="/static/marke/favicon.svg"' in seite
    assert 'Nebenkosten<span class="logo-fix">Fix</span>' in seite


@pytest.mark.parametrize('pfad', ['/login', '/einrichtung'])
def test_anmeldeseiten_im_design_der_anwendung(anon_client, pfad):
    if pfad == '/login':
        from models import User, db
        konto = User(username='anna')
        konto.set_password('anna-passwort-1')
        db.session.add(konto)
        db.session.commit()
    seite = anon_client.get(pfad).get_data(as_text=True)
    assert '– NebenkostenFix</title>' in seite
    assert '/static/anmeldung.css' in seite and '/static/marke/zeichen.svg' in seite
    assert '<style>' not in seite and '#2563eb' not in seite


def test_anmeldestil_und_zeichen_sind_ohne_anmeldung_erreichbar(anon_client):
    for pfad in ('/static/anmeldung.css', '/static/marke/zeichen.svg',
                 '/static/marke/favicon.ico', '/static/vendor/fonts/outfit/outfit.css'):
        assert anon_client.get(pfad).status_code == 200, pfad
    # alles andere bleibt hinter der Anmeldung, auch über Umwege
    for pfad in ('/static/app.js', '/static/index.html', '/static/marke/../app.js',
                 '/static/vendor/chartjs/chart.umd.min.js', '/static/marke%2F..%2Fapp.js'):
        assert anon_client.get(pfad).status_code in (302, 401), pfad


@pytest.mark.parametrize('name,frei', [
    ('anmeldung.css', True), ('marke/zeichen.svg', True), ('vendor/fonts/outfit/outfit.css', True),
    ('app.js', False), ('marke/../app.js', False), ('marke/..', False), ('../auth.py', False),
    ('marke\\..\\app.js', False), ('', False), (None, False), ('vendor/phosphor/x.css', False),
])
def test_oeffentliche_dateien(name, frei):
    import auth
    assert auth.oeffentliche_datei(name) is frei


def test_fenster_installer_und_paket_heissen_nebenkostenfix():
    import desktop
    assert desktop.TITEL == 'NebenkostenFix'
    installer = _text('packaging/windows/installer.iss')
    assert '#define AppName "NebenkostenFix"' in installer
    assert '#define AppExe "NebenkostenFix.exe"' in installer
    assert 'SetupIconFile=nebenkostenfix.ico' in installer
    # D-95: die AppId bleibt, sonst greift kein Update
    assert 'AppId={{6F1B2C4E-8D3A-4F7B-9E21-4C5D6A7B8C9D}' in installer
    spec = _text('packaging/windows/nebenkosten.spec')
    assert "name='NebenkostenFix'" in spec and 'nebenkostenfix.ico' in spec


def test_docker_abbild_nach_d95():
    compose = _text('docker-compose.yml')
    assert f'image: {marke.ABBILD}:' in compose
    assert re.search(r"ABBILD = '" + re.escape(marke.ABBILD) + "'", _text('scripts/e2e.py'))


# --- Logo des Vermieters ----------------------------------------------------------

def _png(breite=120, hoehe=40) -> bytes:
    from PIL import Image
    puffer = io.BytesIO()
    Image.new('RGB', (breite, hoehe), '#4F46E5').save(puffer, format='PNG')
    return puffer.getvalue()


@pytest.fixture
def logo_ordner(tmp_path, monkeypatch):
    import datenordner
    monkeypatch.setattr(datenordner, 'datenordner', lambda: tmp_path)
    return tmp_path


def test_logo_hochladen_zeigen_loeschen(auth_client, logo_ordner):
    assert auth_client.get('/api/vermieter').get_json()['logo'] is False
    assert auth_client.get('/api/vermieter/logo').status_code == 404
    antwort = auth_client.post('/api/vermieter/logo', data={
        'logo': (io.BytesIO(_png()), 'logo.png')}, content_type='multipart/form-data')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    assert (logo_ordner / 'vermieter-logo.png').is_file()
    assert auth_client.get('/api/vermieter').get_json()['logo'] is True
    bild = auth_client.get('/api/vermieter/logo')
    assert bild.status_code == 200 and bild.mimetype == 'image/png'
    assert bild.headers['X-Content-Type-Options'] == 'nosniff'
    # Unter Windows hielt eine offene Antwort die Datei fest (WinError 32):
    # die Antwort ist fertig gelesen, bevor gelöscht wird -- ohne close().
    assert auth_client.delete('/api/vermieter/logo').get_json()['geloescht'] is True
    assert not (logo_ordner / 'vermieter-logo.png').exists()


@pytest.mark.parametrize('inhalt,meldung', [
    (b'%PDF-1.4\n', 'PNG und JPEG'),
    (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'nicht erlaubt'),
    (b'\x89PNG\r\n\x1a\n' + b'kaputt' * 10, 'nicht als Bild'),
])
def test_logo_nur_echte_png_und_jpeg(auth_client, logo_ordner, inhalt, meldung):
    antwort = auth_client.post('/api/vermieter/logo', data={
        'logo': (io.BytesIO(inhalt), 'logo.png')}, content_type='multipart/form-data')
    assert antwort.status_code == 400
    assert meldung in antwort.get_json()['error']
    assert not list(logo_ordner.glob('vermieter-logo.*'))


def test_logo_auf_dem_deckblatt(logo_ordner):
    import vermieter_logo
    from pdf_cover_page import build_cover_page_elements
    assert vermieter_logo.deckblatt_bild() is None
    (logo_ordner / 'vermieter-logo.png').write_bytes(_png(600, 100))
    bild = vermieter_logo.deckblatt_bild()
    assert bild is not None
    assert bild.drawWidth <= 127.0 + 0.01 and bild.drawHeight <= 51.0 + 0.01
    elemente = build_cover_page_elements(
        'Musterhaus Lindenstraße', 'EG links', 'Anna Mieterin', '2025-01-01', '2025-12-31',
        1200, 1000, 200)
    kopf = elemente[0]
    assert any(isinstance(zelle, list) for zeile in kopf._cellvalues for zelle in zeile)
