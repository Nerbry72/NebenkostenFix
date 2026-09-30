"""NK-130: verschluesselte Sicherungen und Exporte (F-71, E-4 → D-86)."""

import io
import json
import os
import struct
import sys
from pathlib import Path

import pytest

from nebenkostenfix import verschluesselung as v
from nebenkostenfix.verschluesselung import VerschluesselungsFehler

PASS = 'korrekte pferdebatterie heftklammer'


@pytest.fixture
def datei(tmp_path):
    quelle = tmp_path / 'klar.bin'
    # drei Stuecke plus Rest, damit Stueckgrenzen und Schluss geprueft sind
    quelle.write_bytes(os.urandom(v.STUECK * 3 + 12345))
    return quelle


def test_rundlauf_bytegleich(datei, tmp_path):
    geheim = v.verschluesseln(datei, tmp_path / 'x.nkbak', PASS, {'erstellt_am': 'heute'})
    assert v.ist_verschluesselt(geheim)
    assert datei.read_bytes()[:64] not in geheim.read_bytes()
    zurueck = tmp_path / 'zurueck.bin'
    meta = v.entschluesseln(geheim, zurueck, PASS)
    assert zurueck.read_bytes() == datei.read_bytes()
    assert meta == {'erstellt_am': 'heute'}


def test_leere_datei(tmp_path):
    leer = tmp_path / 'leer'
    leer.write_bytes(b'')
    v.verschluesseln(leer, tmp_path / 'l.nkbak', PASS)
    v.entschluesseln(tmp_path / 'l.nkbak', tmp_path / 'l2', PASS)
    assert (tmp_path / 'l2').read_bytes() == b''


def test_falsche_passphrase_hinterlaesst_nichts(datei, tmp_path):
    geheim = v.verschluesseln(datei, tmp_path / 'x.nkbak', PASS)
    with pytest.raises(VerschluesselungsFehler, match='Passphrase stimmt nicht'):
        v.entschluesseln(geheim, tmp_path / 'z', 'falsche passphrase!!')
    assert not (tmp_path / 'z').exists()
    assert not (tmp_path / 'z.teil').exists()


def test_zu_kurze_passphrase(datei, tmp_path):
    with pytest.raises(VerschluesselungsFehler, match='mindestens 12'):
        v.verschluesseln(datei, tmp_path / 'x', 'kurz')


def _kopf_ende(roh: bytes) -> int:
    (laenge,) = struct.unpack('>I', roh[len(v.KENNUNG):len(v.KENNUNG) + 4])
    return len(v.KENNUNG) + 4 + laenge


@pytest.mark.parametrize('angriff', ['bit_im_chiffrat', 'abgeschnitten',
                                     'letztes_stueck_weg', 'angehaengt',
                                     'kopf_geaendert', 'stuecke_vertauscht'])
def test_veraenderung_faellt_auf(datei, tmp_path, angriff):
    geheim = v.verschluesseln(datei, tmp_path / 'x.nkbak', PASS, {'belege_anzahl': 3})
    roh = bytearray(geheim.read_bytes())
    start = _kopf_ende(bytes(roh))
    if angriff == 'bit_im_chiffrat':
        roh[start + 100] ^= 1
    elif angriff == 'abgeschnitten':
        roh = roh[:-50]
    elif angriff == 'letztes_stueck_weg':
        # die ersten drei vollen Stuecke behalten, das Schlussstueck weg
        stueck = 4 + v.STUECK + 16
        roh = roh[:start + 3 * stueck]
    elif angriff == 'angehaengt':
        roh += b'\x00\x00\x00\x10' + os.urandom(16)
    elif angriff == 'kopf_geaendert':
        text = roh[:start].replace(b'"belege_anzahl": 3', b'"belege_anzahl": 4')
        assert text != roh[:start]
        roh = bytearray(text) + roh[start:]
    elif angriff == 'stuecke_vertauscht':
        stueck = 4 + v.STUECK + 16
        a = roh[start:start + stueck]
        b = roh[start + stueck:start + 2 * stueck]
        roh[start:start + 2 * stueck] = b + a
    geheim.write_bytes(bytes(roh))
    with pytest.raises(VerschluesselungsFehler):
        v.entschluesseln(geheim, tmp_path / 'z', PASS)
    assert not (tmp_path / 'z').exists()


def test_keine_verschluesselte_datei(tmp_path):
    fremd = tmp_path / 'fremd'
    fremd.write_bytes(b'PK\x03\x04 kein nkbak')
    assert not v.ist_verschluesselt(fremd)
    with pytest.raises(VerschluesselungsFehler):
        v.entschluesseln(fremd, tmp_path / 'z', PASS)


# --- Sicherung ueber die Oberflaeche ----------------------------------------

@pytest.fixture
def gestempelt(app_ctx):
    from flask_migrate import stamp

    from nebenkostenfix import backup
    stamp(revision="head")
    ordner = backup.datenbankpfad(app_ctx.app).parent
    for rest in list(ordner.glob('sicherung*')) + \
            list(Path(backup.standardziel(app_ctx.app)).glob('sicherung*')):
        rest.unlink()
    merk = ordner / backup.STAND_NAME
    if merk.exists():
        merk.unlink()
    return app_ctx


def test_verschluesselte_sicherung_rundlauf_ueber_die_api(gestempelt, auth_client):
    from sqlalchemy import text

    from nebenkostenfix.models import Property, db
    db.session.add(Property(name='Vor der Sicherung'))
    db.session.commit()
    antwort = auth_client.post('/api/backup/erstellen', json={'passphrase': PASS})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    bericht = antwort.get_json()
    assert bericht['verschluesselt'] is True
    assert bericht['name'].endswith('.nkfix')
    archiv = Path(bericht['archiv'])
    inhalt = archiv.read_bytes()
    assert b'Vor der Sicherung' not in inhalt
    assert b'SQLite format' not in inhalt

    liste = auth_client.get('/api/backup/liste').get_json()['sicherungen']
    zeile = [z for z in liste if z['name'] == archiv.name][0]
    assert zeile['verschluesselt'] is True
    assert zeile['einspielbar'] is True
    status = auth_client.get('/api/backup/status').get_json()
    assert status['erinnerung']['stufe'] == 'gruen'
    assert status['festplatte']['status'] in ('ja', 'nein', 'unbekannt')

    db.session.add(Property(name='Nach der Sicherung'))
    db.session.commit()

    ohne = auth_client.post('/api/backup/einspielen', json={
        'ziel': str(archiv.parent), 'name': archiv.name})
    assert ohne.status_code == 400
    assert 'verschlüsselt' in ohne.get_json()['error']
    falsch = auth_client.post('/api/backup/einspielen', json={
        'ziel': str(archiv.parent), 'name': archiv.name,
        'passphrase': 'eine ganz andere passphrase'})
    assert falsch.status_code == 400
    assert 'Passphrase stimmt nicht' in falsch.get_json()['error']

    richtig = auth_client.post('/api/backup/einspielen', json={
        'ziel': str(archiv.parent), 'name': archiv.name, 'passphrase': PASS})
    assert richtig.status_code == 200, richtig.get_data(as_text=True)
    kopie = Path(richtig.get_json()['sicherheitskopie'])
    # Die Vor-Einspielens-Kopie neben dem Archiv ist ebenfalls verschluesselt.
    assert kopie.name.endswith('.nkfix') and v.ist_verschluesselt(kopie)
    with gestempelt.app.app_context():
        with db.engine.connect() as verbindung:
            namen = [z[0] for z in verbindung.execute(text('SELECT name FROM properties'))]
    assert namen == ['Vor der Sicherung']


def test_zu_kurze_passphrase_ueber_die_api(gestempelt, auth_client):
    antwort = auth_client.post('/api/backup/erstellen', json={'passphrase': 'kurz'})
    assert antwort.status_code == 400
    assert 'mindestens 12' in antwort.get_json()['error']


def test_cli_verschluesselt_und_entschluesselt(gestempelt, tmp_path):
    from nebenkostenfix import backup
    runner = gestempelt.app.test_cli_runner()
    erg = runner.invoke(args=['backup', 'create', '--ziel', str(tmp_path),
                              '--verschluesseln'], input=f'{PASS}\n{PASS}\n')
    assert erg.exit_code == 0, erg.output
    archiv = next(tmp_path.glob('sicherung-*.nkfix'))
    info = runner.invoke(args=['backup', 'info', str(archiv)])
    assert 'Verschlüsselt: ja' in info.output
    erg = runner.invoke(args=['backup', 'entschluesseln', str(archiv),
                              str(tmp_path / 'klar.zip'), '--passphrase', PASS])
    assert erg.exit_code == 0, erg.output
    manifest = backup.manifest_lesen(tmp_path / 'klar.zip')
    assert manifest['format'] == backup.MANIFEST_FORMAT


# --- Export -------------------------------------------------------------------

def test_export_verschluesselt(app_ctx, auth_client, tmp_path):
    from nebenkostenfix.models import Property, db
    db.session.add(Property(name='Exporthaus'))
    db.session.commit()
    antwort = auth_client.post('/api/export', json={'passphrase': PASS})
    assert antwort.status_code == 200
    assert antwort.headers['Content-Disposition'].endswith('.nkexp')
    assert b'Exporthaus' not in antwort.data
    geheim = tmp_path / 'e.nkexp'
    geheim.write_bytes(antwort.data)
    v.entschluesseln(geheim, tmp_path / 'e.json', PASS)
    daten = json.loads((tmp_path / 'e.json').read_text(encoding='utf-8'))
    assert daten['properties'][0]['name'] == 'Exporthaus'


def test_export_ohne_passphrase_bleibt_json(app_ctx, auth_client):
    assert auth_client.get('/api/export').is_json
    assert auth_client.post('/api/export', json={'passphrase': 'kurz'}).status_code == 400


# --- Festplatte ------------------------------------------------------------

@pytest.mark.skipif(sys.platform == 'win32', reason='liest /proc und /sys, nur Linux')
def test_festplatte_linux_erkennung(tmp_path):
    """dm-crypt meldet sich mit CRYPT- in der uuid des dm-Geraets."""
    from nebenkostenfix import festplatte
    sysb = tmp_path / 'sys'
    (sysb / 'dm-0' / 'dm').mkdir(parents=True)
    (sysb / 'dm-0' / 'dm' / 'uuid').write_text('CRYPT-LUKS2-abc')
    (sysb / 'dm-1' / 'dm').mkdir(parents=True)
    (sysb / 'dm-1' / 'dm' / 'uuid').write_text('LVM-xyz')
    daten = tmp_path / 'daten'
    lvm = tmp_path / 'lvm'
    netz = tmp_path / 'netz'
    for ordner in (daten, lvm, netz):
        ordner.mkdir()
    mounts = tmp_path / 'mounts'
    mounts.write_text(f'/dev/sda1 / ext4 rw 0 0\n/dev/dm-0 {daten} ext4 rw 0 0\n'
                      f'/dev/dm-1 {lvm} ext4 rw 0 0\n//nas/freigabe {netz} cifs rw 0 0\n')
    assert festplatte._linux(str(daten / 'db'), str(mounts), str(sysb)) == 'ja'
    assert festplatte._linux(str(lvm), str(mounts), str(sysb)) == 'nein'
    assert festplatte._linux(str(netz), str(mounts), str(sysb)) == 'unbekannt'
    assert festplatte._linux(str(tmp_path / 'sonst'), str(mounts), str(sysb)) == 'nein'


def test_festplatte_liefert_immer_ein_ergebnis(tmp_path):
    from nebenkostenfix import festplatte
    ergebnis = festplatte.pruefen(str(tmp_path))
    assert ergebnis['status'] in ('ja', 'nein', 'unbekannt')
    assert 'BitLocker' in ergebnis['hinweis']
