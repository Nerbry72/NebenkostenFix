"""Fremde Pakete im Sicherungsordner.

Befund: Lag im Sicherungsordner ein Paket, das nach einer Sicherung heisst,
aber keine dieser Anwendung ist (ein beliebiges tar.gz, ein Manifest mit
kaputtem JSON oder fehlenden Feldern, das Paket einer anderen Anwendung),
brachen ``/api/backup/liste`` und ``/api/backup/status`` mit 500 ab. Die
Sicherungskarte war damit tot, obwohl die eigenen Sicherungen daneben heil
lagen.

Erwartet: Solche Pakete fallen aus der Liste und zaehlen fuer die
Erinnerung nicht als "letzte Sicherung". ``manifest_lesen`` meldet sie als
``SicherungsFehler``, und das Einspielen weist sie mit 400 ab, ohne den
Bestand anzufassen.
"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text

from nebenkostenfix import backup, verschluesselung
from nebenkostenfix.backup import datenbankpfad

FREMD = 'sicherung-29990101-000000'
PASSPHRASE = 'eine lange passphrase fuer den test'
_WEG = object()  # Feld im Manifest ganz weglassen


@pytest.fixture
def gestempelt(app_ctx):
    """app_ctx mit gesetztem Alembic-Stempel, wie in test_backup_oberflaeche."""
    from flask_migrate import stamp

    stamp(revision="head")
    return app_ctx


def _spuren_weg(app):
    ordner = datenbankpfad(app).parent
    merken = ordner / backup.STAND_NAME
    if merken.exists():
        merken.unlink()
    for rest in list(ordner.glob('sicherung*')) + \
            list(Path(backup.standardziel(app)).glob('sicherung*')):
        rest.unlink()


@pytest.fixture(autouse=True)
def _saubere_backup_spuren(app_ctx):
    """Vorher und nachher aufraeumen: Ein liegengebliebenes Fremdpaket waere
    sonst im naechsten Test (auch in anderen Dateien) mit in der Liste."""
    _spuren_weg(app_ctx.app)
    yield
    _spuren_weg(app_ctx.app)


def _vollstaendig(revision: str, **aenderungen) -> dict:
    """Ein Manifest, das in jeder Hinsicht wie eines dieser Anwendung aussieht."""
    manifest = {
        'format': 1,
        'anwendung': backup.ANWENDUNG,
        'erstellt_am': '2999-01-01T00:00:00+01:00',
        'alembic_revision': revision,
        'datenbank': {'pfad': backup.DB_IM_ARCHIV, 'groesse': 4, 'sha256': '0' * 64},
        'belege': [],
        'uebersprungen': [],
        'zusammenfassung': {'belege_anzahl': 0, 'belege_groesse': 0},
    }
    for feld, wert in aenderungen.items():
        if wert is _WEG:
            manifest.pop(feld)
        else:
            manifest[feld] = wert
    return manifest


def _tar(ziel: Path, eintraege: dict[str, bytes]) -> Path:
    with tarfile.open(ziel, 'w:gz') as tar:
        for name, inhalt in eintraege.items():
            info = tarfile.TarInfo(name)
            info.size = len(inhalt)
            tar.addfile(info, io.BytesIO(inhalt))
    return ziel


def _zip(ziel: Path, eintraege: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(ziel, 'w') as paket:
        for name, inhalt in eintraege.items():
            paket.writestr(name, inhalt)
    return ziel


def _json(manifest) -> bytes:
    return json.dumps(manifest).encode('utf-8')


def _abgeschnitten(ordner: Path, revision: str) -> Path:
    voll = _tar(ordner / 'voll.tar.gz',
                {backup.MANIFEST_NAME: _json(_vollstaendig(revision)) * 50})
    roh = voll.read_bytes()
    voll.unlink()
    ziel = ordner / f'{FREMD}.tar.gz'
    ziel.write_bytes(roh[:len(roh) // 2])
    return ziel


def _zip_manifest_mit_passwort(ordner: Path, revision: str) -> Path:
    """Der Manifest-Eintrag traegt das Verschluesselungs-Bit: zipfile will
    ohne Passwort gar nicht lesen (RuntimeError)."""
    ziel = ordner / f'{FREMD}.nkfix'
    with zipfile.ZipFile(ziel, 'w') as paket:
        paket.writestr(backup.MANIFEST_NAME, _json(_vollstaendig(revision)))
    # zipfile setzt die Bits beim Schreiben selbst zurueck; also danach im
    # lokalen Kopf (Versatz 6) und im Zentralverzeichnis (Versatz 8) setzen.
    roh = bytearray(ziel.read_bytes())
    for kennung, versatz in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
        stelle = roh.index(kennung) + versatz
        roh[stelle] |= 0x1
    ziel.write_bytes(bytes(roh))
    with zipfile.ZipFile(ziel) as paket:
        assert paket.getinfo(backup.MANIFEST_NAME).flag_bits & 0x1
    return ziel


def _zip_manifest_beschaedigt(ordner: Path, revision: str) -> Path:
    """Das Manifest ist deflate-gepackt, seine gepackten Bytes sind Muell
    (wie nach Bitfaeule): zlib wirft beim Entpacken."""
    ziel = ordner / f'{FREMD}.nkfix'
    with zipfile.ZipFile(ziel, 'w', compression=zipfile.ZIP_DEFLATED) as paket:
        paket.writestr(backup.MANIFEST_NAME, _json(_vollstaendig(revision)) * 20)
    with zipfile.ZipFile(ziel) as paket:
        info = paket.getinfo(backup.MANIFEST_NAME)
    roh = bytearray(ziel.read_bytes())
    kopf = info.header_offset
    namenlaenge = int.from_bytes(roh[kopf + 26:kopf + 28], 'little')
    extralaenge = int.from_bytes(roh[kopf + 28:kopf + 30], 'little')
    anfang = kopf + 30 + namenlaenge + extralaenge
    roh[anfang:anfang + info.compress_size] = b'\xff' * info.compress_size
    ziel.write_bytes(bytes(roh))
    return ziel


def _tar_beschaedigt(ordner: Path, revision: str) -> Path:
    """Ein gueltiger gzip-Kopf, dahinter keine Deflate-Daten."""
    ziel = ordner / f'{FREMD}.tar.gz'
    ziel.write_bytes(b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff' + b'\xff' * 512)
    return ziel


# Jede Variante: Name -> Bauer(ordner, revision) -> Pfad im Sicherungsordner.
FREMDPAKETE = {
    'tar-ohne-manifest': lambda o, r: _tar(
        o / f'{FREMD}.tar.gz', {'liesmich.txt': b'kein Paket dieser Anwendung'}),
    'tar-kaputtes-json': lambda o, r: _tar(
        o / f'{FREMD}.tar.gz', {backup.MANIFEST_NAME: b'{"format": 1,'}),
    'tar-kein-utf8': lambda o, r: _tar(
        o / f'{FREMD}.tar.gz', {backup.MANIFEST_NAME: b'\xff\xfe\x00{'}),
    'tar-liste-statt-objekt': lambda o, r: _tar(
        o / f'{FREMD}.tar.gz', {backup.MANIFEST_NAME: b'[1, 2, 3]'}),
    'tar-nur-format': lambda o, r: _tar(
        o / f'{FREMD}.tar.gz', {backup.MANIFEST_NAME: _json({'format': 1})}),
    'tar-andere-anwendung': lambda o, r: _tar(
        o / f'{FREMD}.tar.gz',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, anwendung='eine-andere-anwendung')),
         backup.DB_IM_ARCHIV: b'leer'}),
    'tar-abgeschnitten': _abgeschnitten,
    'tar-beschaedigt': _tar_beschaedigt,
    'zip-manifest-mit-passwort': _zip_manifest_mit_passwort,
    'zip-manifest-beschaedigt': _zip_manifest_beschaedigt,
    'zip-ohne-zusammenfassung': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, zusammenfassung=_WEG))}),
    'zip-ohne-zeitpunkt': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, erstellt_am=_WEG))}),
    'zip-zeitpunkt-als-zahl': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, erstellt_am=29990101))}),
    'zip-zeitpunkt-kein-datum': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, erstellt_am='irgendwann'))}),
    'zip-stempel-als-liste': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, alembic_revision=[r]))}),
    'zip-format-als-liste': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, format=[2]))}),
    'zip-ohne-datenbankangabe': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, datenbank=_WEG))}),
    'zip-belege-kein-verzeichnis': lambda o, r: _zip(
        o / f'{FREMD}.nkfix',
        {backup.MANIFEST_NAME: _json(_vollstaendig(r, belege={'pfad': 'x'}))}),
}


def _sicherungsordner(app) -> Path:
    ordner = Path(backup.standardziel(app))
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _eigene_sicherung(auth_client) -> str:
    res = auth_client.post('/api/backup/erstellen', json={})
    assert res.status_code == 201, res.get_data(as_text=True)
    return res.get_json()['name']


# --- manifest_lesen ----------------------------------------------------------


@pytest.mark.parametrize('variante', sorted(FREMDPAKETE))
def test_manifest_lesen_meldet_ein_fremdes_paket_als_sicherungsfehler(
        gestempelt, tmp_path, variante):
    paket = FREMDPAKETE[variante](tmp_path, gestempelt._kopfrevision())
    with pytest.raises(backup.SicherungsFehler):
        backup.manifest_lesen(paket)


def test_paket_einer_anderen_anwendung_wird_so_benannt(gestempelt, tmp_path):
    paket = FREMDPAKETE['tar-andere-anwendung'](tmp_path, gestempelt._kopfrevision())
    with pytest.raises(backup.SicherungsFehler, match='keine Sicherung dieser Anwendung'):
        backup.manifest_lesen(paket)


def test_manifest_ohne_anwendungsfeld_bleibt_lesbar(gestempelt, tmp_path):
    """Alte Sicherungen bleiben einspielbar: Fehlt nur die Kennung, ist das
    kein Grund, ein sonst vollstaendiges Manifest zu verwerfen."""
    revision = gestempelt._kopfrevision()
    paket = _tar(tmp_path / f'{FREMD}.tar.gz',
                 {backup.MANIFEST_NAME: _json(_vollstaendig(revision, anwendung=_WEG))})
    assert backup.manifest_lesen(paket)['alembic_revision'] == revision


def _anwendung_entfernen(archiv: Path) -> dict:
    """Schreibt das Paket neu, mit einem Manifest ohne 'anwendung' -- so, wie
    Sicherungen aus der Zeit vor dieser Kennung aussehen."""
    neu = archiv.with_name(archiv.name + '.neu')
    if backup.behaelter(archiv) == 'zip':
        with zipfile.ZipFile(archiv) as alt, zipfile.ZipFile(neu, 'w') as paket:
            manifest = json.loads(alt.read(backup.MANIFEST_NAME))
            manifest.pop('anwendung')
            for info in alt.infolist():
                inhalt = (_json(manifest) if info.filename == backup.MANIFEST_NAME
                          else alt.read(info))
                paket.writestr(info, inhalt)
    else:
        with tarfile.open(archiv, 'r:gz') as alt, tarfile.open(neu, 'w:gz') as tar:
            manifest = json.loads(alt.extractfile(backup.MANIFEST_NAME).read())
            manifest.pop('anwendung')
            for info in alt.getmembers():
                if info.name == backup.MANIFEST_NAME:
                    inhalt = _json(manifest)
                    info.size = len(inhalt)
                    tar.addfile(info, io.BytesIO(inhalt))
                elif info.isfile():
                    tar.addfile(info, alt.extractfile(info))
                else:
                    tar.addfile(info)
    neu.replace(archiv)
    return manifest


@pytest.mark.parametrize('art', ['tar', 'nkfix'])
def test_echte_sicherung_ohne_anwendungsfeld_bleibt_in_liste_status_und_einspielbar(
        gestempelt, auth_client, art):
    """Eine echte, alte Sicherung ohne Kennung: Liste, Status und Einspielen
    behandeln sie wie jede eigene Sicherung."""
    ordner = _sicherungsordner(gestempelt.app)
    archiv = backup.sicherung_erstellen(gestempelt.app, ordner, art=art)
    manifest = _anwendung_entfernen(archiv)
    assert 'anwendung' not in backup.manifest_lesen(archiv)
    if art == 'tar':
        assert manifest['format'] == 1
        assert 'zusatz' not in manifest

    liste = auth_client.get('/api/backup/liste')
    assert liste.status_code == 200, liste.get_data(as_text=True)
    eintraege = {s['name']: s for s in liste.get_json()['sicherungen']}
    assert archiv.name in eintraege
    assert eintraege[archiv.name]['einspielbar'] is True

    status = auth_client.get('/api/backup/status')
    assert status.status_code == 200, status.get_data(as_text=True)
    assert status.get_json()['letzte_sicherung']['name'] == archiv.name

    res = auth_client.post('/api/backup/einspielen',
                           json={'ziel': str(ordner), 'name': archiv.name})
    assert res.status_code == 200, res.get_data(as_text=True)


# --- Liste -------------------------------------------------------------------


@pytest.mark.parametrize('variante', sorted(FREMDPAKETE))
def test_liste_uebergeht_ein_fremdes_paket(gestempelt, auth_client, variante):
    eigene = _eigene_sicherung(auth_client)
    FREMDPAKETE[variante](_sicherungsordner(gestempelt.app), gestempelt._kopfrevision())

    res = auth_client.get('/api/backup/liste')
    assert res.status_code == 200, res.get_data(as_text=True)
    assert [s['name'] for s in res.get_json()['sicherungen']] == [eigene]


# --- Status ------------------------------------------------------------------


@pytest.mark.parametrize('variante', sorted(FREMDPAKETE))
def test_status_zaehlt_ein_fremdes_paket_nicht_als_letzte_sicherung(
        gestempelt, auth_client, variante):
    eigene = _eigene_sicherung(auth_client)
    FREMDPAKETE[variante](_sicherungsordner(gestempelt.app), gestempelt._kopfrevision())

    res = auth_client.get('/api/backup/status')
    assert res.status_code == 200, res.get_data(as_text=True)
    status = res.get_json()
    assert status['letzte_sicherung']['name'] == eigene
    assert status['erinnerung']['stufe'] == 'gruen'


@pytest.mark.parametrize('variante', ['tar-andere-anwendung', 'zip-ohne-zusammenfassung',
                                      'zip-zeitpunkt-kein-datum'])
def test_status_nur_mit_fremdem_paket_erinnert_rot(gestempelt, auth_client, variante):
    FREMDPAKETE[variante](_sicherungsordner(gestempelt.app), gestempelt._kopfrevision())

    res = auth_client.get('/api/backup/status')
    assert res.status_code == 200, res.get_data(as_text=True)
    status = res.get_json()
    assert status['letzte_sicherung'] is None
    assert status['erinnerung']['stufe'] == 'rot'


def test_zeitpunkt_ohne_zeitzone_bricht_die_erinnerung_nicht(gestempelt, auth_client):
    """Ein Zeitpunkt ohne Zeitzone gilt als Ortszeit, statt beim Abziehen von
    der jetzigen Zeit einen TypeError zu werfen."""
    revision = gestempelt._kopfrevision()
    _tar(_sicherungsordner(gestempelt.app) / f'{FREMD}.tar.gz',
         {backup.MANIFEST_NAME: _json(_vollstaendig(
             revision, erstellt_am='2000-01-01T00:00:00'))})

    res = auth_client.get('/api/backup/status')
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()['erinnerung']['stufe'] == 'gelb'


def test_zeitpunkt_im_jahr_eins_ohne_zeitzone_bricht_die_erinnerung_nicht(
        gestempelt, auth_client):
    """Jahr 1 ohne Zeitzone: Die Umrechnung in Ortszeit laeuft ueber den
    Wertebereich (OverflowError, unter Windows OSError vor 1970). Dann gilt
    UTC, statt dass der Status mit 500 abbricht."""
    revision = gestempelt._kopfrevision()
    _tar(_sicherungsordner(gestempelt.app) / f'{FREMD}.tar.gz',
         {backup.MANIFEST_NAME: _json(_vollstaendig(
             revision, erstellt_am='0001-01-01T00:00:00'))})

    res = auth_client.get('/api/backup/status')
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()['erinnerung']['stufe'] == 'gelb'


# --- Verschluesselter Umschlag ------------------------------------------------


def _umschlag(ordner: Path, metadaten: dict) -> Path:
    klar = _tar(ordner / 'klar.tar.gz', {'liesmich.txt': b'egal'})
    ziel = ordner / f'{FREMD}.nkfix'
    verschluesselung.verschluesseln(klar, ziel, PASSPHRASE, metadaten)
    klar.unlink()
    return ziel


@pytest.mark.parametrize('metadaten', [
    {'format': 2, 'anwendung': backup.ANWENDUNG},
    {'format': 2, 'anwendung': backup.ANWENDUNG, 'erstellt_am': 'irgendwann'},
    {'format': 2, 'anwendung': backup.ANWENDUNG,
     'erstellt_am': '2999-01-01T00:00:00+01:00', 'alembic_revision': ['x']},
    {'format': 2, 'anwendung': backup.ANWENDUNG,
     'erstellt_am': '2999-01-01T00:00:00+01:00', 'belege_anzahl': 'viele'},
], ids=['ohne-zeitpunkt', 'zeitpunkt-kein-datum', 'stempel-als-liste', 'belege-kein-wert'])
def test_umschlag_mit_unvollstaendigem_kopf_bricht_liste_und_status_nicht(
        gestempelt, auth_client, metadaten):
    eigene = _eigene_sicherung(auth_client)
    _umschlag(_sicherungsordner(gestempelt.app), metadaten)

    liste = auth_client.get('/api/backup/liste')
    assert liste.status_code == 200, liste.get_data(as_text=True)
    assert [s['name'] for s in liste.get_json()['sicherungen']] == [eigene]
    status = auth_client.get('/api/backup/status')
    assert status.status_code == 200, status.get_data(as_text=True)
    assert status.get_json()['letzte_sicherung']['name'] == eigene


def _roher_umschlag(ordner: Path, kopf: bytes) -> Path:
    """Die Kennung verschluesselter Dateien, dahinter ein beliebiger Kopf."""
    import struct

    ziel = ordner / f'{FREMD}.nkfix'
    ziel.write_bytes(verschluesselung.KENNUNG + struct.pack('>I', len(kopf)) + kopf)
    return ziel


@pytest.mark.parametrize('kopf', [
    b'["kein", "objekt"]',
    b'{"verfahren": "scrypt+aes-256-gcm", "metadaten": "nur text"}',
    b'{"verfahren": "scrypt+aes-256-gcm", "metadaten": [1, 2]}',
], ids=['kopf-als-liste', 'metadaten-als-text', 'metadaten-als-liste'])
def test_umschlag_mit_fremdem_kopf_bricht_liste_und_status_nicht(
        gestempelt, auth_client, kopf):
    eigene = _eigene_sicherung(auth_client)
    paket = _roher_umschlag(_sicherungsordner(gestempelt.app), kopf)

    with pytest.raises(backup.SicherungsFehler):
        backup.manifest_lesen(paket)
    liste = auth_client.get('/api/backup/liste')
    assert liste.status_code == 200, liste.get_data(as_text=True)
    assert [s['name'] for s in liste.get_json()['sicherungen']] == [eigene]
    status = auth_client.get('/api/backup/status')
    assert status.status_code == 200, status.get_data(as_text=True)
    assert status.get_json()['letzte_sicherung']['name'] == eigene


# --- Einspielen ----------------------------------------------------------------


@pytest.mark.parametrize('variante', sorted(FREMDPAKETE))
def test_einspielen_eines_fremden_pakets_lehnt_ab_und_behaelt_stand(
        gestempelt, auth_client, variante):
    from nebenkostenfix.models import Property, db

    db.session.add(Property(name='Haus Fremdpaketweg', is_standalone=False))
    db.session.commit()
    ordner = _sicherungsordner(gestempelt.app)
    paket = FREMDPAKETE[variante](ordner, gestempelt._kopfrevision())

    res = auth_client.post('/api/backup/einspielen',
                           json={'ziel': str(ordner), 'name': paket.name})
    assert res.status_code == 400, res.get_data(as_text=True)
    assert res.get_json()['error']
    with gestempelt.app.app_context():
        with db.engine.connect() as verbindung:
            namen = [z[0] for z in verbindung.execute(text('SELECT name FROM properties'))]
    assert namen == ['Haus Fremdpaketweg']
