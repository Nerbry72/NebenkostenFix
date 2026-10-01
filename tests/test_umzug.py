"""NK-164: Umzugspaket (.nkfix) -- exportieren, übernehmen, ablehnen.

Rundlauf Linux → Linux im selben Prozess (jede Tabelle, jede Datei, Anmeldung
mit altem Passwort, Vermieter aus der Umgebung festgeschrieben), die
Übernahme bei der Einrichtung (mit Einmal-Code, ohne in der App), Hochladen
in Stücken mit Fortsetzen, und jedes Paket, das abgelehnt gehört: ``../``,
Verknüpfung, Rückstrich, doppelter Name, ZIP-Bombe, falsche Größe, falsche
Prüfsumme, kaputte Datenbank, neuerer Schemastand -- jeweils ohne dass sich
am Bestand etwas ändert. Plattformübergreifend (Linux ↔ Windows) prüft die
CI mit ``packaging/windows/paketprobe.py umzug``.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from nebenkostenfix import backup
from nebenkostenfix import umzug

ALT_USER = 'alt-vermieter'
HAFTUNG = {'version': 1, 'bestaetigt_am': '2026-01-01T00:00:00+00:00'}
ALT_PASS = 'altes-passwort-123'
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00'
       b'\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05'
       b'\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


def _aufraeumen(app):
    from nebenkostenfix import datenordner
    from nebenkostenfix import einstellungen
    from nebenkostenfix import vermieter_logo

    ordner = datenordner.datenordner()
    while vermieter_logo.loeschen(ordner):
        pass
    (ordner / einstellungen.DATEINAME).unlink(missing_ok=True)
    (ordner / 'lizenz.nklizenz').unlink(missing_ok=True)
    for unter in (umzug.ARBEIT, umzug.IMPORT):
        shutil.rmtree(ordner / unter, ignore_errors=True)
    for rest in list(Path(backup.standardziel(app)).glob('sicherung*')):
        rest.unlink()
    umzug._freigegeben.clear()


@pytest.fixture
def bestand(app_ctx, monkeypatch):
    """Ein Bestand mit Konto, Immobilie, Beleg, Logo, Einstellungen und
    Umgebungswerten."""
    from flask_migrate import stamp

    from nebenkostenfix import datenordner
    from nebenkostenfix import einstellungen
    from nebenkostenfix.models import InvoiceDocument, Property, User, db

    stamp(revision='head')
    _aufraeumen(app_ctx.app)
    belege = backup.belegwurzel()
    shutil.rmtree(belege, ignore_errors=True)
    belege.mkdir(parents=True)
    (belege / '2025').mkdir()
    (belege / '2025' / 'gas.pdf').write_bytes(b'%PDF-1.4\nGasrechnung\n%%EOF\n')

    konto = User(username=ALT_USER)
    konto.set_password(ALT_PASS)
    db.session.add(konto)
    haus = Property(name='Musterhaus Lindenstraße', is_standalone=False)
    db.session.add(haus)
    db.session.flush()
    db.session.add(InvoiceDocument(property_id=haus.id, filename='gas.pdf',
                                   document_path='2025/gas.pdf'))
    db.session.commit()

    ordner = datenordner.datenordner()
    (ordner / 'vermieter-logo.png').write_bytes(PNG)
    einstellungen.schreiben(ordner, haftung=HAFTUNG, updates_automatisch=False,
                            update_geprueft='2026-01-01T00:00:00+00:00')
    monkeypatch.setenv('VERMIETER_NAME', 'Anna Vermieterin')
    monkeypatch.setenv('VERMIETER_IBAN', 'DE02 1203 0000 0000 2020 51')
    yield app_ctx
    _aufraeumen(app_ctx.app)


def _anmelden(client, name=ALT_USER, passwort=ALT_PASS):
    return client.post('/login', json={'username': name, 'password': passwort})


def _paket(bestand, tmp_path, **kwargs) -> Path:
    return umzug.paket_erstellen(bestand.app, tmp_path / 'NebenkostenFix-test.nkfix', **kwargs)


def _hausnamen(app):
    from sqlalchemy import text

    from nebenkostenfix.models import db
    with app.app_context():
        with db.engine.connect() as verbindung:
            return sorted(z[0] for z in verbindung.execute(text('SELECT name FROM properties')))


def _umbauen(paket: Path, ziel: Path, aendern=None, zusatz=()) -> Path:
    """Paket aus- und wieder einpacken; dazwischen darf man pfuschen."""
    with zipfile.ZipFile(paket) as quelle:
        inhalt = {name: quelle.read(name) for name in quelle.namelist()}
    if aendern:
        aendern(inhalt)
    with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as neu:
        for name, daten in inhalt.items():
            neu.writestr(name, daten)
        for eintrag, daten in zusatz:
            neu.writestr(eintrag, daten)
    return ziel


def _manifest_aendern(aendern):
    def schritt(inhalt):
        manifest = json.loads(inhalt[backup.MANIFEST_NAME])
        aendern(manifest, inhalt)
        inhalt[backup.MANIFEST_NAME] = json.dumps(manifest).encode()
    return schritt


# --- Format ----------------------------------------------------------------------

def test_paket_ist_zip_mit_allem(bestand, tmp_path):
    paket = _paket(bestand, tmp_path)
    assert zipfile.is_zipfile(paket)
    with zipfile.ZipFile(paket) as z:
        namen = set(z.namelist())
        manifest = json.loads(z.read(backup.MANIFEST_NAME))
        einstellungen = json.loads(z.read(backup.EINSTELLUNGEN_IM_ARCHIV))
        belegeintrag = z.getinfo('belege/2025/gas.pdf')
    assert {backup.MANIFEST_NAME, backup.DB_IM_ARCHIV, 'belege/2025/gas.pdf',
            'einstellungen.json', 'einstellungen/vermieter-logo.png'} <= namen
    assert 'lizenz.nklizenz' not in namen
    assert manifest['format'] == 2 and manifest['produkt'] == 'NebenkostenFix'
    assert manifest['quelle']['betrieb'] in ('docker', 'server', 'windows-app')
    assert manifest['zaehlwerte']['properties'] == 1
    assert manifest['zaehlwerte']['users'] == 1
    assert {e['pfad'] for e in manifest['zusatz']} >= {'einstellungen.json'}
    assert einstellungen['vermieter_umgebung'] == {'name': 'Anna Vermieterin',
                                                   'iban': 'DE02120300000000202051'}
    # Hinweis und Update-Einstellung wandern mit, der Zeitpunkt der letzten
    # Suche gehoert zum Rechner (NK-174, NK-175).
    assert einstellungen['anwendung'] == {'haftung': HAFTUNG, 'updates_automatisch': False}
    # PDFs werden gespeichert, nicht noch einmal komprimiert.
    assert belegeintrag.compress_type == zipfile.ZIP_STORED


def test_export_ueber_die_oberflaeche_liefert_download_und_raeumt_auf(bestand):
    client = bestand.app.test_client()
    assert _anmelden(client).status_code == 200
    antwort = client.get('/api/umzug/export')
    assert antwort.status_code == 200
    assert 'NebenkostenFix-' in antwort.headers['Content-Disposition']
    assert '.nkfix' in antwort.headers['Content-Disposition']
    inhalt = antwort.get_data()
    antwort.close()
    assert zipfile.is_zipfile(io.BytesIO(inhalt))
    assert list(umzug.arbeitsordner(bestand.app).glob('export-*')) == []


def test_export_verschluesselt(bestand):
    from nebenkostenfix import verschluesselung
    client = bestand.app.test_client()
    _anmelden(client)
    kurz = client.post('/api/umzug/export', json={'passphrase': 'kurz'})
    assert kurz.status_code == 400 and 'mindestens 12' in kurz.get_json()['error']
    antwort = client.post('/api/umzug/export', json={'passphrase': 'eine lange passphrase'})
    assert antwort.status_code == 200
    inhalt = antwort.get_data()
    antwort.close()
    assert inhalt.startswith(verschluesselung.KENNUNG)
    assert b'Musterhaus' not in inhalt


def test_export_ohne_anmeldung_gesperrt(bestand):
    assert bestand.app.test_client().get('/api/umzug/export').status_code == 401


# --- Rundlauf --------------------------------------------------------------------

def test_rundlauf_ueber_die_api_ersetzt_alles(bestand, tmp_path, monkeypatch):
    from nebenkostenfix import datenordner
    from nebenkostenfix import einstellungen
    from nebenkostenfix.models import Property, User, Vermieterdaten, db

    paket = _paket(bestand, tmp_path)
    # Der neue Rechner: anderer Bestand, anderes Konto, kein Logo, keine Umgebung.
    monkeypatch.delenv('VERMIETER_NAME')
    monkeypatch.delenv('VERMIETER_IBAN')
    ordner = datenordner.datenordner()
    (ordner / 'vermieter-logo.png').unlink()
    (ordner / einstellungen.DATEINAME).unlink()
    db.session.add(Property(name='Nur auf dem neuen Rechner'))
    neu = User(username='neu')
    neu.set_password('neues-passwort-1')
    db.session.add(neu)
    db.session.commit()
    (backup.belegwurzel() / '2025' / 'gas.pdf').unlink()

    client = bestand.app.test_client()
    assert _anmelden(client, 'neu', 'neues-passwort-1').status_code == 200
    umzug.importordner(bestand.app).mkdir(parents=True, exist_ok=True)
    shutil.copy2(paket, umzug.importordner(bestand.app) / paket.name)

    liste = client.get('/api/umzug/importordner').get_json()
    assert [p['name'] for p in liste['pakete']] == [paket.name]
    ohne = client.post('/api/umzug/uebernehmen', json={'importordner': paket.name})
    assert ohne.status_code == 400 and 'ERSETZEN' in ohne.get_json()['error']
    assert _hausnamen(bestand.app) == ['Musterhaus Lindenstraße', 'Nur auf dem neuen Rechner']

    antwort = client.post('/api/umzug/uebernehmen', json={
        'importordner': paket.name, 'bestaetigung': 'ERSETZEN'})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert bericht['anmelden'] is True
    assert bericht['belege'] == 1 and bericht['fehlende_verweise'] == []
    assert bericht['zusatz'] == {'logo': True,
                                 'einstellungen': ['haftung', 'updates_automatisch'],
                                 'vermieter_festgeschrieben': ['name', 'iban']}
    assert Path(bericht['sicherheitskopie']).is_file()
    assert bericht['nicht_im_paket']

    assert _hausnamen(bestand.app) == ['Musterhaus Lindenstraße']
    assert (backup.belegwurzel() / '2025' / 'gas.pdf').is_file()
    assert (ordner / 'vermieter-logo.png').read_bytes() == PNG
    stand = einstellungen.lesen(ordner)
    assert stand['haftung'] == HAFTUNG and stand['updates_automatisch'] is False
    assert stand['update_geprueft'] is None
    with bestand.app.app_context():
        zeile = Vermieterdaten.einziger()
        assert (zeile.name, zeile.iban) == ('Anna Vermieterin', 'DE02120300000000202051')
        db.session.remove()

    # Die alte Sitzung gilt nicht mehr, das alte Konto schon.
    assert client.get('/api/auth/me').status_code == 401
    assert _anmelden(client, 'neu', 'neues-passwort-1').status_code == 401
    assert _anmelden(client).status_code == 200


def test_vorhandene_vermieterwerte_bleiben(bestand, tmp_path, monkeypatch):
    from nebenkostenfix.models import Vermieterdaten, db
    db.session.add(Vermieterdaten(name='Schon eingetragen'))
    db.session.commit()
    paket = _paket(bestand, tmp_path)
    bericht = umzug.uebernehmen(bestand.app, paket)
    assert bericht['zusatz']['vermieter_festgeschrieben'] == ['iban']
    with bestand.app.app_context():
        assert Vermieterdaten.einziger().name == 'Schon eingetragen'
        db.session.remove()


def test_altes_paket_mit_lizenz_bleibt_einlesbar(bestand, tmp_path):
    """Pakete bis 0.9 tragen ``lizenz.nklizenz`` und keine App-Einstellungen;
    beides schadet nicht (NK-176)."""
    import hashlib

    from nebenkostenfix import datenordner
    from nebenkostenfix import einstellungen

    lizenz = b'{"format": "nk-lizenz-1", "daten": {}, "signatur": ""}'

    def alt(manifest, inhalt):
        manifest['zusatz'].append({'pfad': 'lizenz.nklizenz', 'groesse': len(lizenz),
                                   'sha256': hashlib.sha256(lizenz).hexdigest()})
        werte = json.loads(inhalt[backup.EINSTELLUNGEN_IM_ARCHIV])
        del werte['anwendung']
        neu = json.dumps(werte).encode()
        inhalt[backup.EINSTELLUNGEN_IM_ARCHIV] = neu
        for eintrag in manifest['zusatz']:
            if eintrag['pfad'] == backup.EINSTELLUNGEN_IM_ARCHIV:
                eintrag.update(groesse=len(neu), sha256=hashlib.sha256(neu).hexdigest())

    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'alt.nkfix',
                     _manifest_aendern(alt), zusatz=[('lizenz.nklizenz', lizenz)])
    ordner = datenordner.datenordner()
    bericht = umzug.uebernehmen(bestand.app, paket)
    assert bericht['zusatz']['einstellungen'] == []
    assert not (ordner / 'lizenz.nklizenz').exists()
    # Was hier schon bestaetigt war, bleibt.
    assert einstellungen.lesen(ordner)['haftung'] == HAFTUNG


def test_paket_ohne_logo_entfernt_das_logo(bestand, tmp_path):
    from nebenkostenfix import datenordner
    ordner = datenordner.datenordner()
    (ordner / 'vermieter-logo.png').unlink()
    paket = _paket(bestand, tmp_path)
    (ordner / 'vermieter-logo.jpg').write_bytes(b'\xff\xd8\xff\xe0 jpeg')
    umzug.uebernehmen(bestand.app, paket)
    assert not (ordner / 'vermieter-logo.jpg').exists()


def test_alte_tar_sicherung_bleibt_uebernehmbar(bestand, tmp_path):
    alt = backup.sicherung_erstellen(bestand.app, tmp_path, art='tar')
    assert alt.name.endswith('.tar.gz') and not zipfile.is_zipfile(alt)
    bericht = umzug.uebernehmen(bestand.app, alt)
    assert bericht['zusatz'] == {}
    assert _hausnamen(bestand.app) == ['Musterhaus Lindenstraße']


def test_verschluesseltes_paket_braucht_die_passphrase(bestand, tmp_path):
    paket = _paket(bestand, tmp_path, passphrase='eine lange passphrase')
    with pytest.raises(backup.SicherungsFehler, match='verschlüsselt'):
        umzug.uebernehmen(bestand.app, paket)
    bericht = umzug.uebernehmen(bestand.app, paket, 'eine lange passphrase')
    assert bericht['zusatz']['logo'] is True


# --- Einrichtung: frische Installation übernimmt den alten Bestand ---------------

def _frisch(bestand):
    """Alle Konten weg: die Instanz steht vor der Einrichtung."""
    from nebenkostenfix.models import User, db
    User.query.delete()
    db.session.commit()


def test_einrichtung_bietet_die_uebernahme_an(bestand):
    _frisch(bestand)
    seite = bestand.app.test_client().get('/einrichtung').get_data(as_text=True)
    assert 'Daten aus einer anderen Installation übernehmen' in seite
    assert '<script src="/static/umzug.js"></script>' in seite
    assert 'id="umzug-code"' in seite and 'data-desktop="0"' in seite
    antwort = bestand.app.test_client().get('/static/umzug.js')
    assert antwort.status_code == 200
    antwort.close()


def test_einrichtung_in_der_app_ohne_code(bestand, monkeypatch):
    _frisch(bestand)
    monkeypatch.setitem(bestand.app.config, 'DESKTOP', True)
    seite = bestand.app.test_client().get('/einrichtung').get_data(as_text=True)
    assert 'data-desktop="1"' in seite and 'id="umzug-code"' not in seite


def test_uebernahme_bei_der_einrichtung_mit_stuecken_und_code(bestand, tmp_path, monkeypatch):
    from nebenkostenfix import auth
    paket = _paket(bestand, tmp_path)
    _frisch(bestand)
    client = bestand.app.test_client()
    client.get('/einrichtung')
    code = auth._einmal_code_legen(bestand.app)
    daten = paket.read_bytes()

    # Ohne Code: abgelehnt, nichts angelegt.
    ohne = client.post('/api/umzug/hochladen', json={'groesse': len(daten), 'name': paket.name})
    assert ohne.status_code == 401 and ohne.get_json()['code'] == 'auth_required'
    falsch = client.post('/api/umzug/hochladen', headers={'X-Einmal-Code': 'falsch'},
                         json={'groesse': len(daten), 'name': paket.name})
    assert falsch.status_code == 403 and 'Einmal-Code' in falsch.get_json()['error']

    monkeypatch.setattr(umzug, 'STUECK', 4096)
    kopf = {'X-Einmal-Code': code}
    start = client.post('/api/umzug/hochladen', headers=kopf,
                        json={'groesse': len(daten), 'name': paket.name})
    assert start.status_code == 201, start.get_data(as_text=True)
    kennung, stueck = start.get_json()['id'], start.get_json()['stueck']
    assert stueck == 4096
    ab = 0
    while ab < len(daten):
        antwort = client.put(f'/api/umzug/hochladen/{kennung}?ab={ab}', headers=kopf,
                             data=daten[ab:ab + stueck])
        assert antwort.status_code == 200
        ab = antwort.get_json()['empfangen']
        if ab == stueck:
            # Ein wiederholtes Stück (Netz riss nach dem Senden ab) wird abgelehnt,
            # der Stand sagt, wo es weitergeht.
            doppelt = client.put(f'/api/umzug/hochladen/{kennung}?ab=0', headers=kopf,
                                 data=daten[:stueck])
            assert doppelt.status_code == 409
            assert client.get(f'/api/umzug/hochladen/{kennung}',
                              headers=kopf).get_json()['empfangen'] == stueck

    vorschau = client.post('/api/umzug/pruefen', headers=kopf, json={'hochgeladen': kennung})
    assert vorschau.get_json()['einspielbar'] is True
    antwort = client.post('/api/umzug/uebernehmen', headers=kopf, json={'hochgeladen': kennung})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert not list(umzug.arbeitsordner(bestand.app).glob(f'{kennung}*'))
    # Der Einmal-Code ist verbraucht, das alte Konto meldet sich an.
    assert Path(auth._code_ablage()).exists() is False
    assert _anmelden(client).status_code == 200
    # Nach der Einrichtung ist der Weg ohne Anmeldung zu.
    anonym = bestand.app.test_client()
    assert anonym.post('/api/umzug/hochladen', headers=kopf,
                       json={'groesse': 10}).status_code == 401


def test_uebernahme_nach_der_einrichtung_nur_angemeldet(bestand):
    client = bestand.app.test_client()
    for methode, pfad in (('post', '/api/umzug/hochladen'), ('post', '/api/umzug/pruefen'),
                          ('post', '/api/umzug/uebernehmen'),
                          ('get', '/api/umzug/importordner')):
        assert getattr(client, methode)(pfad, json={}).status_code == 401, pfad


def test_hochladen_grenzen(bestand, monkeypatch):
    client = bestand.app.test_client()
    _anmelden(client)
    assert client.post('/api/umzug/hochladen', json={'groesse': 0}).status_code == 400
    monkeypatch.setenv('UMZUG_MAX_GB', '0.000001')
    zu_gross = client.post('/api/umzug/hochladen', json={'groesse': 10_000})
    assert zu_gross.status_code == 400 and 'UMZUG_MAX_GB' in zu_gross.get_json()['error']
    monkeypatch.delenv('UMZUG_MAX_GB')
    start = client.post('/api/umzug/hochladen', json={'groesse': 4}).get_json()
    zuviel = client.put(f"/api/umzug/hochladen/{start['id']}?ab=0", data=b'12345')
    assert zuviel.status_code == 409
    halb = client.put(f"/api/umzug/hochladen/{start['id']}?ab=0", data=b'12')
    assert halb.status_code == 200
    unfertig = client.post('/api/umzug/uebernehmen', json={
        'hochgeladen': start['id'], 'bestaetigung': 'ERSETZEN'})
    assert unfertig.status_code == 400 and 'unvollständig' in unfertig.get_json()['error']
    for falsch in ('x' * 32, 'ABCDEF', 'a' * 31):
        assert client.get(f'/api/umzug/hochladen/{falsch}').status_code == 404
    # ``..`` normalisiert der Client weg; der fremde Pfad ist gesperrt.
    assert client.get('/api/umzug/hochladen/../../etc').status_code == 401


def test_hoechstens_drei_offene_uploads(bestand):
    client = bestand.app.test_client()
    _anmelden(client)
    kennungen = [client.post('/api/umzug/hochladen', json={'groesse': 4}).get_json()['id']
                 for _ in range(5)]
    offen = {p.stem for p in umzug.arbeitsordner(bestand.app).glob('*.json')}
    assert len(offen) == umzug.HOECHSTENS_OFFEN
    assert kennungen[-1] in offen and kennungen[0] not in offen


def test_der_aelteste_upload_faellt_auch_bei_gleicher_dateizeit(bestand):
    """F-119: die Reihenfolge kommt aus dem Eintrag, nicht aus der Dateizeit.

    Die Dateizeit ist grob (unter Windows bis 16 ms) und kann rückwärts
    laufen. Hier bekommt der neueste Upload die älteste Zeit -- gelöscht
    werden muss trotzdem der zuerst begonnene.
    """
    import os
    import time
    client = bestand.app.test_client()
    _anmelden(client)
    kennungen = [client.post('/api/umzug/hochladen', json={'groesse': 4}).get_json()['id']
                 for _ in range(umzug.HOECHSTENS_OFFEN)]
    ordner = umzug.arbeitsordner(bestand.app)
    jetzt = time.time()
    for alter, kennung in enumerate(kennungen):  # neuester = ältester Zeitstempel
        os.utime(ordner / f'{kennung}.json', (jetzt - alter, jetzt - alter))
    client.post('/api/umzug/hochladen', json={'groesse': 4})
    offen = {p.stem for p in ordner.glob('*.json')}
    assert kennungen[0] not in offen
    assert set(kennungen[1:]) <= offen


def test_parallele_starts_halten_die_grenze(bestand, monkeypatch):
    """PR #25 (Copilot, zweite Runde): Aufräumen, Zählen und Anlegen müssen
    unter einer Sperre laufen. Sonst zählen parallele Starts dieselben offenen
    Uploads, und danach legt jeder einen neuen an."""
    import shutil
    import threading
    import time

    echt = shutil.disk_usage

    def langsam(pfad):  # zwischen Zählen und Anlegen gibt jeder Thread ab
        time.sleep(0.02)
        return echt(pfad)

    monkeypatch.setattr(umzug.shutil, 'disk_usage', langsam)
    start = threading.Barrier(8)

    def beginnen():
        start.wait()
        umzug.hochladen_beginnen(bestand.app, 4, 'paket.zip')

    threads = [threading.Thread(target=beginnen) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    offen = list(umzug.arbeitsordner(bestand.app).glob('*.json'))
    assert len(offen) == umzug.HOECHSTENS_OFFEN


# --- Windows-App: Pfade nur aus dem Dialog der Hülle ----------------------------

def test_pfad_nur_in_der_app_und_nur_freigegeben(bestand, tmp_path, monkeypatch):
    paket = _paket(bestand, tmp_path)
    client = bestand.app.test_client()
    _anmelden(client)
    auftrag = {'pfad': str(paket), 'bestaetigung': 'ERSETZEN'}
    assert 'nicht freigegeben' in client.post('/api/umzug/uebernehmen', json=auftrag).get_json()['error']
    monkeypatch.setitem(bestand.app.config, 'DESKTOP', True)
    assert 'nicht freigegeben' in client.post('/api/umzug/uebernehmen', json=auftrag).get_json()['error']
    umzug.freigeben(paket)
    assert client.post('/api/umzug/uebernehmen', json=auftrag).status_code == 200


def test_export_an_freigegebenen_pfad(bestand, tmp_path, monkeypatch):
    client = bestand.app.test_client()
    _anmelden(client)
    ziel = tmp_path / 'woanders' / 'mein-umzug.nkfix'
    ziel.parent.mkdir()
    assert client.post('/api/umzug/export', json={'pfad': str(ziel)}).status_code == 400
    monkeypatch.setitem(bestand.app.config, 'DESKTOP', True)
    umzug.freigeben(ziel)
    antwort = client.post('/api/umzug/export', json={'pfad': str(ziel)})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    assert zipfile.is_zipfile(ziel)


def test_importordner_nimmt_nur_namen(bestand):
    client = bestand.app.test_client()
    _anmelden(client)
    for name in ('../nebenkosten.db', '/etc/passwd', 'x.exe', ''):
        antwort = client.post('/api/umzug/uebernehmen', json={
            'importordner': name, 'bestaetigung': 'ERSETZEN'})
        assert antwort.status_code == 400


# --- Ablehnungen: nichts wird verändert ------------------------------------------

def _abgelehnt(bestand, paket, muster):
    vorher = _hausnamen(bestand.app)
    with pytest.raises(backup.SicherungsFehler, match=muster):
        umzug.uebernehmen(bestand.app, paket)
    assert _hausnamen(bestand.app) == vorher
    assert (backup.belegwurzel() / '2025' / 'gas.pdf').is_file()


@pytest.mark.parametrize('name, muster', [
    ('../ausbruch.txt', 'heraus'),
    ('belege/../../ausbruch.txt', 'heraus'),
    ('/absolut.txt', 'heraus'),
    # Unter Windows macht zipfile selbst aus dem Rückstrich einen '/'
    # (beim Schreiben und beim Lesen): dort ist es eine zusätzliche Datei,
    # und die fällt am Manifest auf. Abgelehnt wird sie so oder so.
    ('belege\\\\windows.txt', 'heraus|im Manifest nicht'),
    ('C:/windows.txt', 'heraus'),
])
def test_boese_pfade_werden_abgelehnt(bestand, tmp_path, name, muster):
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'boese.nkfix', zusatz=[(name, b'x')])
    _abgelehnt(bestand, paket, muster)


def test_verknuepfung_im_zip_wird_abgelehnt(bestand, tmp_path):
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'link.nkfix')
    with zipfile.ZipFile(paket, 'a') as z:
        info = zipfile.ZipInfo('belege/link.pdf')
        info.external_attr = (0o120777 << 16)
        z.writestr(info, '/etc/passwd')
    _abgelehnt(bestand, paket, 'Verknüpfung')


def test_doppelter_name_wird_abgelehnt(bestand, tmp_path):
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'doppelt.nkfix')
    with pytest.warns(UserWarning):
        with zipfile.ZipFile(paket, 'a') as z:
            z.writestr('belege/2025/gas.pdf', b'anderer Inhalt')
    _abgelehnt(bestand, paket, 'doppelt')


def test_zip_bombe_wird_abgelehnt(bestand, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, 'ZIP_VERHAELTNIS_AB', 1024 * 1024)
    null = b'\0' * (8 * 1024 * 1024)

    def bombe(manifest, inhalt):
        manifest['belege'].append({'pfad': 'bombe.bin', 'groesse': len(null),
                                   'sha256': backup.hashlib.sha256(null).hexdigest()})
        inhalt['belege/bombe.bin'] = null
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'bombe.nkfix', _manifest_aendern(bombe))
    _abgelehnt(bestand, paket, 'Fache')


def test_gesamtgroesse_und_dateizahl_begrenzt(bestand, tmp_path, monkeypatch):
    paket = _paket(bestand, tmp_path)
    monkeypatch.setattr(backup, 'ZIP_MAX_DATEIEN', 2)
    _abgelehnt(bestand, paket, 'höchstens 2')
    monkeypatch.setattr(backup, 'ZIP_MAX_DATEIEN', 200_000)
    monkeypatch.setenv('UMZUG_MAX_GB', '0.000001')
    _abgelehnt(bestand, paket, 'UMZUG_MAX_GB')


def test_groesse_anders_als_im_manifest(bestand, tmp_path):
    def laenger(inhalt):
        inhalt['belege/2025/gas.pdf'] += b'angehaengt'
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'laenger.nkfix', laenger)
    _abgelehnt(bestand, paket, 'laut Manifest')


def test_manipulierte_datei_faellt_an_der_pruefsumme_auf(bestand, tmp_path):
    def verdrehen(inhalt):
        inhalt['belege/2025/gas.pdf'] = bytes(reversed(inhalt['belege/2025/gas.pdf']))
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'sha.nkfix', verdrehen)
    _abgelehnt(bestand, paket, 'Prüfsumme')


def test_kaputte_datenbank_faellt_am_integrity_check_auf(bestand, tmp_path):
    def zerstoeren(manifest, inhalt):
        kaputt = b'SQLite format 3\x00' + b'\xff' * 4080
        inhalt[backup.DB_IM_ARCHIV] = kaputt
        manifest['datenbank']['groesse'] = len(kaputt)
        manifest['datenbank']['sha256'] = backup.hashlib.sha256(kaputt).hexdigest()
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'db.nkfix', _manifest_aendern(zerstoeren))
    _abgelehnt(bestand, paket, 'Datenbank im Archiv')


def test_neuerer_schemastand_und_unbekanntes_format(bestand, tmp_path):
    def zukunft(manifest, _):
        manifest['alembic_revision'] = 'ffffffffffff'
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'neu.nkfix', _manifest_aendern(zukunft))
    _abgelehnt(bestand, paket, 'zuerst NebenkostenFix aktualisieren')
    vorschau = umzug.pruefen(bestand.app, paket)
    assert vorschau['einspielbar'] is False and 'aktualisieren' in vorschau['hinweis']

    def format9(manifest, _):
        manifest['format'] = 9
    paket = _umbauen(_paket(bestand, tmp_path), tmp_path / 'f9.nkfix', _manifest_aendern(format9))
    _abgelehnt(bestand, paket, 'Manifestformat 9')


def test_fremde_zip_ist_kein_paket(bestand, tmp_path):
    fremd = tmp_path / 'urlaub.nkfix'
    with zipfile.ZipFile(fremd, 'w') as z:
        z.writestr('foto.jpg', b'x')
    _abgelehnt(bestand, fremd, 'enthält kein manifest.json')


# --- Kommandozeile ---------------------------------------------------------------

def test_cli_export_und_import(bestand, tmp_path):
    runner = bestand.app.test_cli_runner()
    erg = runner.invoke(args=['umzug', 'export', '--ziel', str(tmp_path)])
    assert erg.exit_code == 0, erg.output
    paket = next(tmp_path.glob('NebenkostenFix-*.nkfix'))
    erg = runner.invoke(args=['umzug', 'import', str(paket), '--ja'])
    assert erg.exit_code == 0, erg.output
    assert '"belege": 1' in erg.output


def test_stempel_bleiben_bei_parallelen_uploads_eindeutig(monkeypatch):
    """PR #25 (Copilot): zwei Uploads zugleich lasen denselben letzten Stempel.

    Die Uhr steht still (grobes Ticken), und zwischen Lesen und Schreiben
    gibt jeder Thread ab -- ohne Sperre bekommen mehrere denselben Stempel.
    """
    import builtins
    import threading
    import time as zeit

    def langsam(*werte):
        zeit.sleep(0.005)
        return builtins.max(*werte)

    monkeypatch.setattr(umzug.time, 'time_ns', lambda: 1)
    monkeypatch.setattr(umzug, 'max', langsam, raising=False)
    stempel = []
    threads = [threading.Thread(target=lambda: stempel.append(umzug._stempel()))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(stempel)) == 8
