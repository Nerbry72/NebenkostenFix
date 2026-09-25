"""NK-077: Sicherung und Wiederherstellung in der Oberflaeche.

Die Mechanik dahinter ist die von NK-025 und dort bis ins Einzelne getestet.
Diese Tests stellen die Fragen der Oberflaeche: Weiß der Betreiber, wann er
zuletzt gesichert hat (Erinnerung)? Kann er das Ziel waehlen, und weicht die
Beschreibung davon ab, was der Server tut, wenn ein Ziel untauglich ist?
Und der schwierigste Knopf der Anwendung: Das Einspielen durch die HTTP-Schicht
muss am Ende genau den Stand des Archivs zeigen, Datenbank und Belege.

Stempel wie in test_backup.py: app_ctx baut das Schema ohne alembic_version,
ohne Stempel waere der Schemastand im Manifest leer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlalchemy import text

import backup
from backup import datenbankpfad


@pytest.fixture
def gestempelt(app_ctx):
    """app_ctx mit gesetztem Alembic-Stempel (Kopf der Kette, NK-165)."""
    from flask_migrate import stamp

    stamp(revision="head")
    return app_ctx


@pytest.fixture(autouse=True)
def _saubere_backup_spuren(app_ctx):
    """Archivreste und Merkdatei vor jedem Test weg.

    Der conftest-Datenordner lebt zwischen den Tests weiter: Wer hier nicht
    faegt, findet die Sicherungen des Vorgaengers in seiner Liste und die
    gewaehlte Zielvorgabe eines fremden Tests in seinem Status.
    """
    ordner = datenbankpfad(app_ctx.app).parent
    merken = ordner / backup.STAND_NAME
    if merken.exists():
        merken.unlink()
    # NK-132: Vorgabeziel ist DATA_DIR/backups.
    for rest in list(ordner.glob('sicherung*')) + \
            list(Path(backup.standardziel(app_ctx.app)).glob('sicherung*')):
        rest.unlink()
    yield


def _beleg_schreiben(wurzel: Path, relativ: str, inhalt: bytes = b'%PDF-1.4\n%%EOF\n') -> Path:
    pfad = wurzel / relativ
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    return pfad


def _dokument(property_id: int, pfad: str, name: str):
    from models import InvoiceDocument, db

    dokument = InvoiceDocument(
        property_id=property_id,
        filename=name,
        document_path=pfad,
        description='Wärmekostenrechnung',
    )
    db.session.add(dokument)
    db.session.commit()
    return dokument


def _dokumentpfade(app) -> list[str]:
    """Frische Verbindung in eigenem Kontext: die Fixture-Session zeigt nach
    dem Austausch der Datei noch den alten Stand (wie in test_backup.py)."""
    from models import db

    with app.app_context():
        with db.engine.connect() as verbindung:
            return sorted(
                z[0] for z in verbindung.execute(
                    text('SELECT document_path FROM invoice_documents')))


# --- Status und Erinnerung ---------------------------------------------------


def test_status_ohne_sicherung_erinnert_rot(gestempelt, auth_client):
    res = auth_client.get('/api/backup/status')
    assert res.status_code == 200
    status = res.get_json()
    assert status['letzte_sicherung'] is None
    assert status['erinnerung']['stufe'] == 'rot'
    assert 'keine Sicherung' in status['erinnerung']['text']
    assert status['zuletzt_gewaehltes_ziel'] is None
    # Das Vorgabeziel ist der Datenordner neben der Testdatenbank.
    assert status['standardziel'].endswith(str(Path(gestempelt.app.config['SQLALCHEMY_DATABASE_URI']).parent.name)) or \
        Path(status['standardziel']).is_dir()


def test_erstellen_am_standardziel_erzeugt_archiv(gestempelt, auth_client):
    res = auth_client.post('/api/backup/erstellen', json={})
    assert res.status_code == 201, res.get_data(as_text=True)
    bericht = res.get_json()
    archiv = Path(bericht['archiv'])
    assert archiv.is_file()
    assert archiv.name.startswith('sicherung-')
    assert bericht['belege'] == 0
    assert bericht['schemastand'] == gestempelt._kopfrevision()


def test_status_nach_sicherung_erinnert_gruen(gestempelt, auth_client):
    auth_client.post('/api/backup/erstellen', json={})
    status = auth_client.get('/api/backup/status').get_json()
    assert status['letzte_sicherung']['name'].startswith('sicherung-')
    assert status['erinnerung']['stufe'] == 'gruen'
    assert '0 Tage' in status['erinnerung']['text']


def test_ziel_waehlbar_und_gemerkt(gestempelt, auth_client, tmp_path, monkeypatch):
    monkeypatch.setenv('BACKUP_ZIELE', str(tmp_path))
    ziel = tmp_path / 'weggesichert'
    res = auth_client.post('/api/backup/erstellen', json={'ziel': str(ziel)})
    assert res.status_code == 201
    assert len(list(ziel.glob('sicherung-*.nkfix'))) == 1
    status = auth_client.get('/api/backup/status').get_json()
    assert status['zuletzt_gewaehltes_ziel'] == str(ziel.resolve())
    # Die Vorgabe zeigt dem Betreiber sein gewaehltes Ziel, nicht den
    # Datenordner.
    assert status['zuletzt_gewaehltes_ziel'] != status['standardziel']


def test_ziel_im_belegordner_verboten(gestempelt, auth_client, monkeypatch, tmp_path):
    """Eine Sicherung im Belegordner wirft sich beim Einspielen selbst weg."""
    belege = tmp_path / 'belege'
    belege.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(belege))
    res = auth_client.post('/api/backup/erstellen', json={'ziel': str(belege / 'unterordner')})
    assert res.status_code == 400
    assert 'Belegordner' in res.get_json()['error']
    assert not (belege / 'unterordner').exists()


def test_status_findet_sicherung_am_gewaehlten_ziel(gestempelt, auth_client, tmp_path,
                                                    monkeypatch):
    """Wer auf das NAS sichert, darf keine rote Erinnerung bekommen."""
    belege = tmp_path / 'belege'
    belege.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(belege))
    monkeypatch.setenv('BACKUP_ZIELE', str(tmp_path))
    ziel = tmp_path / 'nas-ablage'
    auth_client.post('/api/backup/erstellen', json={'ziel': str(ziel)})
    status = auth_client.get('/api/backup/status').get_json()
    assert status['letzte_sicherung']['pfad'].startswith(str(ziel.resolve()))
    assert status['erinnerung']['stufe'] == 'gruen'


# --- Liste -------------------------------------------------------------------


def test_liste_zeigt_archiv_und_liest_kein_kaputtes(gestempelt, auth_client):
    auth_client.post('/api/backup/erstellen', json={})
    ziel = Path(auth_client.get('/api/backup/status').get_json()['standardziel'])
    # Muell mit dem richtigen Namen: kein Manifest, keine Sicherung.
    (ziel / 'sicherung-19990101-000000.tar.gz').write_bytes(b'kaputt')
    liste = auth_client.get('/api/backup/liste').get_json()
    namen = [s['name'] for s in liste['sicherungen']]
    assert len(namen) == 1
    assert namen[0].startswith('sicherung-2')
    zeile = liste['sicherungen'][0]
    assert zeile['einspielbar'] is True
    assert zeile['belege'] == 0
    assert zeile['groesse'].endswith(('KB', 'Bytes'))


def test_liste_leer_ohne_verzeichnis(gestempelt, auth_client, tmp_path, monkeypatch):
    monkeypatch.setenv('BACKUP_ZIELE', str(tmp_path))
    liste = auth_client.get(
        f"/api/backup/liste?ziel={tmp_path / 'gibt-es-nicht'}").get_json()
    assert liste['sicherungen'] == []


# --- Einspielen durch die HTTP-Schicht ---------------------------------------


@pytest.fixture
def instanz_mit_beleg(gestempelt, tmp_path, monkeypatch):
    """Belegordner, Immobilie und ein Belegdokument: der Ausgangsstand."""
    belege = tmp_path / 'belege'
    belege.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(belege))
    from models import Property, db

    haus = Property(name='Haus Backupweg', is_standalone=False)
    db.session.add(haus)
    db.session.commit()
    _beleg_schreiben(belege, 'Haus Backupweg/Gas 2024.pdf')
    _dokument(haus.id, 'Haus Backupweg/Gas 2024.pdf', 'gas2024.pdf')
    return belege


def test_einspielen_stellt_archivstand_wieder_her(gestempelt, auth_client,
                                                  instanz_mit_beleg):
    """Der Fall aus der Karte: falsche Daten drin, Knopf druecken, altes
    Datum wieder da -- Datenbank und Belege zusammen."""
    belege = instanz_mit_beleg
    erstes = auth_client.post('/api/backup/erstellen', json={}).get_json()

    # Der "Unfall": ein zweiter Beleg kommt dazu und bleibt erhalten -- im
    # Archiv ist er nicht.
    _beleg_schreiben(belege, 'Haus Backupweg/Strom 2025.pdf')
    from models import Property, db
    haus = Property.query.filter_by(name='Haus Backupweg').one()
    _dokument(haus.id, 'Haus Backupweg/Strom 2025.pdf', 'strom2025.pdf')
    assert _dokumentpfade(gestempelt.app) == [
        'Haus Backupweg/Gas 2024.pdf', 'Haus Backupweg/Strom 2025.pdf']

    res = auth_client.post('/api/backup/einspielen', json={
        'ziel': str(Path(erstes['archiv']).parent), 'name': erstes['name']})
    assert res.status_code == 200, res.get_data(as_text=True)
    bericht = res.get_json()
    assert bericht['sicherheitskopie'] is not None
    assert Path(bericht['sicherheitskopie']).is_file()
    assert bericht['fehlende_verweise'] == []

    # Die Datenbank steht auf dem Archivstand: nur das erste Dokument.
    assert _dokumentpfade(gestempelt.app) == ['Haus Backupweg/Gas 2024.pdf']
    # Der Belegordner ebenso: der zweite Beleg ist weg.
    assert (belege / 'Haus Backupweg/Strom 2025.pdf').exists() is False
    assert (belege / 'Haus Backupweg/Gas 2024.pdf').is_file()

    # Die Erinnerung kennt jetzt die Vor-Einspielens-Kopie als juengste.
    status = auth_client.get('/api/backup/status').get_json()
    assert status['letzte_sicherung']['name'].startswith('sicherung-vor-einspielen')


def test_einspielen_ohne_archiv_lehnt_ab(gestempelt, auth_client):
    res = auth_client.post('/api/backup/einspielen', json={})
    assert res.status_code == 400
    assert res.get_json()['error']


def test_einspielen_verschollenem_pfad_lehnt_ab(gestempelt, auth_client):
    res = auth_client.post('/api/backup/einspielen',
                           json={'archiv': '/nirgendwo/sicherung-x.tar.gz'})
    assert res.status_code == 400
    assert 'nicht freigegeben' in res.get_json()['error']
    res = auth_client.post('/api/backup/einspielen',
                           json={'name': 'sicherung-19990101-000000.tar.gz'})
    assert res.status_code == 400
    assert 'nicht mehr da' in res.get_json()['error']


def test_einspielen_von_muell_lehnt_ab_und_behaelt_stand(gestempelt, auth_client,
                                                         tmp_path, monkeypatch):
    """Ein Archiv ohne Manifest wird abgelehnt; die Datenbank bleibt unberuehrt."""
    monkeypatch.setenv('BACKUP_ZIELE', str(tmp_path))
    muell = tmp_path / 'sicherung-muell.tar.gz'
    import tarfile
    with tarfile.open(muell, 'w:gz') as tar:
        fremd = tmp_path / 'fremd.txt'
        fremd.write_text('keine Sicherung')
        tar.add(fremd, arcname='fremd.txt')
    res = auth_client.post('/api/backup/einspielen', json={'archiv': str(muell)})
    assert res.status_code == 400
    from models import db
    assert db.session.execute(
        text('SELECT COUNT(*) FROM properties')).scalar() == 0


# --- Erlaubte Wurzeln (F-76, NK-149) -----------------------------------------


def test_ziel_ausserhalb_der_freigabe_wird_abgelehnt(gestempelt, auth_client, tmp_path):
    """Ohne Eintrag in BACKUP_ZIELE ist ein fremdes Verzeichnis tabu --
    weder sichern noch durchsuchen."""
    fremd = tmp_path / 'fremd'
    res = auth_client.post('/api/backup/erstellen', json={'ziel': str(fremd)})
    assert res.status_code == 400
    assert 'nicht freigegeben' in res.get_json()['error']
    assert not fremd.exists()
    res = auth_client.get('/api/backup/liste?ziel=/etc')
    assert res.status_code == 400


def test_status_nennt_die_freigegebenen_ziele(gestempelt, auth_client, tmp_path,
                                              monkeypatch):
    import os
    monkeypatch.setenv('BACKUP_ZIELE', os.pathsep.join([str(tmp_path / 'a'),
                                                        str(tmp_path / 'b')]))
    status = auth_client.get('/api/backup/status').get_json()
    # Erste Wurzel ist der Datenordner, das Vorgabeziel liegt darin (NK-132).
    assert Path(status['standardziel']).resolve().parent == \
        Path(status['erlaubte_ziele'][0])
    assert str((tmp_path / 'a').resolve()) in status['erlaubte_ziele']
    assert str((tmp_path / 'b').resolve()) in status['erlaubte_ziele']


def test_verknuepfung_aus_der_freigabe_heraus_zaehlt_nicht(gestempelt, auth_client,
                                                          tmp_path, monkeypatch):
    """realpath statt abspath: ein Symlink im freigegebenen Ordner, der nach
    draussen zeigt, oeffnet keine Tuer."""
    freigabe = tmp_path / 'freigabe'
    draussen = tmp_path / 'draussen'
    freigabe.mkdir()
    draussen.mkdir()
    (freigabe / 'tuer').symlink_to(draussen, target_is_directory=True)
    monkeypatch.setenv('BACKUP_ZIELE', str(freigabe))
    res = auth_client.get(f"/api/backup/liste?ziel={freigabe / 'tuer'}")
    assert res.status_code == 400
    res = auth_client.get(f"/api/backup/liste?ziel={freigabe / '..' / 'draussen'}")
    assert res.status_code == 400


def test_einspielen_nimmt_nur_archivnamen(gestempelt, auth_client):
    for name in ('../../etc/passwd', 'sicherung-x.tar.gz/../x',
                 'fremd.tar.gz', ''):
        res = auth_client.post('/api/backup/einspielen', json={'name': name})
        assert res.status_code == 400, name


# --- Schutz ------------------------------------------------------------------


def test_backup_routen_brauchen_anmeldung(app_ctx, anon_client):
    for adresse, methode in (
        ('/api/backup/status', 'get'),
        ('/api/backup/erstellen', 'post'),
        ('/api/backup/liste', 'get'),
        ('/api/backup/einspielen', 'post'),
    ):
        assert getattr(anon_client, methode)(adresse).status_code == 401


def test_einspielen_laesst_keine_verbindung_offen(gestempelt, auth_client,
                                                   instanz_mit_beleg, monkeypatch):
    """Windows (NK-151): jede offene Verbindung sperrt Datenbank und Journal
    gegen Ersetzen. SQLite loescht das WAL-Journal, sobald die letzte
    Verbindung schliesst -- liegt es nach dem Schliessen noch da, haelt
    jemand die Datei fest, und unter Windows scheitert das Einspielen."""
    import backup
    erstes = auth_client.post('/api/backup/erstellen', json={}).get_json()
    beobachtet = []
    original = backup._verbindungen_schliessen

    def schliessen_und_nachsehen(app):
        original(app)
        db_datei = backup.datenbankpfad(app)
        beobachtet.append(db_datei.with_name(db_datei.name + '-wal').exists())

    monkeypatch.setattr(backup, '_verbindungen_schliessen', schliessen_und_nachsehen)
    res = auth_client.post('/api/backup/einspielen', json={
        'ziel': str(Path(erstes['archiv']).parent), 'name': erstes['name']})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert beobachtet and beobachtet[0] is False, beobachtet
