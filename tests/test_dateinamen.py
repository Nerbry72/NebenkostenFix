"""NK-026: Dateinamen, wie sie wirklich vorkommen, durch den ganzen Weg.

Zwei Wege werden gemessen. Der eine ist der Upload: ein Name kommt von aussen,
NASHandler macht daraus einen Pfad. Der andere ist der Rundlauf aus NK-025:
sichern, alles wegwerfen, zurueckholen, Pruefsummen vergleichen. Was zwischen
beiden nicht identisch herauskommt, ist ein verlorener Beleg.
"""

from __future__ import annotations

import io
import os
import unicodedata
from pathlib import Path

import pytest

import backup
from tests.dateinamen import (
    BOESE_NAMEN,
    BOESE_ORDNER,
    belege_anlegen,
    echtes_jpg,
    echtes_pdf,
    ist_jpg,
    ist_pdf,
    pruefsumme,
)


@pytest.fixture
def belegordner(tmp_path, monkeypatch):
    """Ein Belegordner voller schwieriger Namen, samt Soll-Pruefsummen."""
    wurzel = tmp_path / 'belege'
    wurzel.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(wurzel))
    erwartet = belege_anlegen(wurzel)
    return wurzel, erwartet


# --- Kriterium 1: die Namensarten sind abgedeckt ---------------------------


def test_fixture_deckt_die_geforderten_namensarten_ab():
    namen = [name for name, _ in BOESE_NAMEN]
    alles = ' '.join(namen)

    assert any('ä' in n or 'ü' in n or 'ö' in n for n in namen), 'Umlaute'
    assert 'ß' in alles, 'scharfes s'
    assert any(' ' in n for n in namen), 'Leerzeichen'
    assert any('(' in n and ')' in n for n in namen), 'Klammern'
    assert any(n.count('.') >= 3 for n in namen), 'Mehrfachpunkte'
    assert any(len(n.encode()) > 200 for n in namen), 'Langname'
    assert any(n.lower().endswith('.jpg') for n in namen), 'JPEG dabei'
    assert any(n.lower().endswith('.pdf') for n in namen), 'PDF dabei'


def test_nfc_und_nfd_sind_zwei_verschiedene_namen():
    """Derselbe Umlaut, zwei Bytefolgen.

    macOS legt Namen in NFD ab, Linux nimmt, was kommt. Wer die beiden fuer
    gleich haelt, verliert beim Zurueckholen einen der Belege.
    """
    namen = [name for name, _ in BOESE_NAMEN]
    nfc = [n for n in namen if 'NFC' in n]
    nfd = [n for n in namen if 'NFD' in n]

    assert nfc and nfd
    assert nfc[0].encode() != nfd[0].encode()
    assert unicodedata.normalize('NFC', nfd[0]).replace('NFD', 'NFC') == nfc[0]


def test_alle_namen_landen_auf_der_platte(belegordner):
    wurzel, erwartet = belegordner

    assert len(erwartet) == len(BOESE_NAMEN) * len(BOESE_ORDNER)
    for pfad in erwartet:
        assert (wurzel / pfad).is_file()


# --- Kriterium 2: echte Binaerdaten ----------------------------------------


def test_die_testdaten_sind_echte_pdf_und_jpeg_dateien(belegordner):
    wurzel, erwartet = belegordner

    pdfs = [p for p in erwartet if p.lower().endswith('.pdf')]
    jpgs = [p for p in erwartet if p.lower().endswith('.jpg')]
    assert pdfs and jpgs

    for pfad in pdfs:
        assert ist_pdf((wurzel / pfad).read_bytes()), pfad
    for pfad in jpgs:
        assert ist_jpg((wurzel / pfad).read_bytes()), pfad


def test_jpeg_ist_wirklich_dekodierbar():
    """Marker allein beweisen nichts, das Bild muss sich oeffnen lassen."""
    from PIL import Image

    bild = Image.open(io.BytesIO(echtes_jpg((12, 5))))
    bild.load()
    assert bild.format == 'JPEG'
    assert bild.size == (12, 5)


def test_pdf_hat_seiten_und_ist_kein_text_mit_endung():
    daten = echtes_pdf('Nebenkosten 2025')
    assert ist_pdf(daten)
    assert b'/Type /Page' in daten or b'/Type/Page' in daten
    assert len(daten) > 500


# --- Kriterium 3: Rundlauf mit Pruefsummenvergleich ------------------------


def _stempeln(app_modul):
    from flask_migrate import stamp

    stamp(revision="head")


def test_rundlauf_erhaelt_jede_einzelne_pruefsumme(app_ctx, belegordner, tmp_path):
    """Sichern, alles wegwerfen, zurueckholen. 60 Dateien, 60 Pruefsummen."""
    wurzel, erwartet = belegordner
    _stempeln(app_ctx)
    archivordner = tmp_path / 'sicherungen'

    archiv = backup.sicherung_erstellen(app_ctx.app, archivordner)

    for pfad in erwartet:
        (wurzel / pfad).unlink()
    assert not any(wurzel.rglob('*.pdf'))

    backup.sicherung_einspielen(app_ctx.app, archiv)

    fehlend = [p for p in erwartet if not (wurzel / p).is_file()]
    assert fehlend == [], f'{len(fehlend)} Dateien fehlen, zuerst: {fehlend[:3]}'

    abweichend = [
        p for p, summe in erwartet.items()
        if pruefsumme((wurzel / p).read_bytes()) != summe
    ]
    assert abweichend == [], f'{len(abweichend)} Dateien veraendert: {abweichend[:3]}'


def test_kein_beleg_kommt_zuviel_zurueck(app_ctx, belegordner, tmp_path):
    wurzel, erwartet = belegordner
    _stempeln(app_ctx)

    archiv = backup.sicherung_erstellen(app_ctx.app, tmp_path / 'sicherungen')
    backup.sicherung_einspielen(app_ctx.app, archiv)

    danach = {
        p.relative_to(wurzel).as_posix()
        for p in wurzel.rglob('*') if p.is_file()
    }
    assert danach == set(erwartet)


def test_manifest_nennt_jeden_namen_unveraendert(app_ctx, belegordner, tmp_path):
    """Kein stilles Normalisieren, kein Umschreiben, kein Abschneiden."""
    wurzel, erwartet = belegordner
    _stempeln(app_ctx)

    archiv = backup.sicherung_erstellen(app_ctx.app, tmp_path / 'sicherungen')
    manifest = backup.manifest_lesen(archiv)

    assert {b['pfad'] for b in manifest['belege']} == set(erwartet)
    assert {b['pfad']: b['sha256'] for b in manifest['belege']} == erwartet


def test_lange_und_mehrbytige_namen_ueberleben_das_archiv(app_ctx, belegordner, tmp_path):
    """tar hat ein Namensfeld von 100 Bytes, laengeres braucht eine Erweiterung."""
    wurzel, erwartet = belegordner
    _stempeln(app_ctx)
    lang = [p for p in erwartet if len(p.split('/')[-1].encode()) > 150]
    assert lang, 'kein langer Name im Bestand'

    archiv = backup.sicherung_erstellen(app_ctx.app, tmp_path / 'sicherungen')
    for pfad in lang:
        (wurzel / pfad).unlink()
    backup.sicherung_einspielen(app_ctx.app, archiv)

    for pfad in lang:
        assert (wurzel / pfad).is_file(), pfad
        assert pruefsumme((wurzel / pfad).read_bytes()) == erwartet[pfad]


# --- Der Weg herein: Uploads mit schwierigen Namen -------------------------


@pytest.fixture
def nas(tmp_path, monkeypatch):
    monkeypatch.setenv('NAS_MOUNT_PATH', str(tmp_path / 'nas'))
    from handlers.nas_handler import NASHandler

    return NASHandler()


def _hochladen(name: str):
    from werkzeug.datastructures import FileStorage

    daten = echtes_jpg() if name.lower().endswith('.jpg') else echtes_pdf()
    return FileStorage(io.BytesIO(daten), filename=name), daten


@pytest.mark.parametrize('name', [name for name, _ in BOESE_NAMEN])
def test_upload_landet_unter_der_belegwurzel(nas, name):
    """Jeder Name aus dem Bestand muss sich hochladen lassen.

    Geprueft wird zweierlei: es kracht nicht, und der Pfad bleibt innerhalb
    des Belegordners. Ein relativer Pfad, der herausfuehrt, landet spaeter so
    in der Datenbank und zeigt beim Ausliefern irgendwohin.
    """
    datei, daten = _hochladen(name)

    relativ = nas.save_tenant_contract(datei, 'Haus Müllerstraße 3', 'EG links', 'Familie Schmitt')

    wurzel = Path(nas.nas_mount_path).resolve()
    voll = (wurzel / relativ).resolve()
    assert voll.is_file()
    assert wurzel in voll.parents
    assert voll.read_bytes() == daten


@pytest.mark.parametrize('name', [
    'rechnung.pdf/../../../../../../tmp/entwischt',
    'a.b/../../../../../../../tmp/uebernommen',
    '../../../../etc/cron.d/uebernahme.pdf',
    'x.' + 'a' * 300,
    'ohnepunkt',
    '.',
    '..',
])
def test_boesartiger_uploadname_bleibt_im_belegordner(nas, name, tmp_path):
    """Namen, die kein Vermieter tippt, aber jeder Client schicken kann.

    Verlangt wird nicht, dass die Datei ankommt, sondern dass nichts ausserhalb
    des Belegordners entsteht und die Anwendung nicht mit einem ungefangenen
    OSError stehenbleibt.
    """
    datei, _ = _hochladen(name)

    relativ = nas.save_tenant_contract(datei, 'Haus', 'EG', 'Mieter')

    wurzel = Path(nas.nas_mount_path).resolve()
    voll = (wurzel / relativ).resolve()
    assert wurzel in voll.parents
    assert voll.is_file()
    assert not Path('/tmp/entwischt').exists()
    assert not Path('/tmp/uebernommen').exists()


def test_endung_wird_nicht_ungeprueft_uebernommen(nas):
    """Die Endung kam bis NK-026 roh aus dem Uploadnamen in den Pfad.

    Ein Name wie 'x.<300 Zeichen>' warf damit einen ungefangenen OSError
    (Errno 36) bis in die Route, also 500 statt einer lesbaren Absage.
    """
    datei, _ = _hochladen('scan.' + 'z' * 300)

    relativ = nas.save_tenant_contract(datei, 'Haus', 'EG', 'Mieter')

    endung = relativ.rsplit('.', 1)[-1]
    assert len(endung) <= 16
    assert endung.isalnum()
    assert (Path(nas.nas_mount_path) / relativ).is_file()


def test_grossgeschriebene_endung_wird_klein(nas):
    datei, _ = _hochladen('Rechnung.PDF')

    relativ = nas.save_tenant_contract(datei, 'Haus', 'EG', 'Mieter')

    assert relativ.endswith('.pdf')


def test_zwei_gleiche_namen_ueberschreiben_sich_nicht(nas):
    ersteangabe, _ = _hochladen('Rechnung.pdf')
    zweite, _ = _hochladen('Rechnung.pdf')

    a = nas.save_tenant_contract(ersteangabe, 'Haus', 'EG', 'Mieter')
    b = nas.save_tenant_contract(zweite, 'Haus', 'EG', 'Mieter')

    assert a != b
    assert (Path(nas.nas_mount_path) / a).is_file()
    assert (Path(nas.nas_mount_path) / b).is_file()


def test_harter_verweis_im_belegordner_bleibt_einspielbar(app_ctx, belegordner, tmp_path):
    """NK-147: zwei Namen fuer eine Datei (harter Verweis) wurden als
    Verweis archiviert, und das Einspielen lehnte das Archiv ab. Jetzt steht
    jede Datei vollstaendig im Archiv."""
    import os
    import zipfile
    wurzel, erwartet = belegordner
    _stempeln(app_ctx)
    erste = next(iter(erwartet))
    os.link(wurzel / erste, wurzel / 'zweiter-name.pdf')

    archiv = backup.sicherung_erstellen(app_ctx.app, tmp_path / 'sicherungen')
    with zipfile.ZipFile(archiv) as paket:
        assert sorted(paket.namelist()).count('belege/zweiter-name.pdf') == 1
        assert all((e.external_attr >> 16) & 0o170000 != 0o120000
                   for e in paket.infolist())

    backup.sicherung_einspielen(app_ctx.app, archiv)
    assert (wurzel / 'zweiter-name.pdf').read_bytes() == (wurzel / erste).read_bytes()
    assert pruefsumme((wurzel / erste).read_bytes()) == erwartet[erste]
