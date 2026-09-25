"""NK-025: Sichern und Zurueckholen.

Die fuenf Kriterien der Karte, jedes mit mindestens einem Test, dazu die
Faelle, in denen ein Archiv abgelehnt gehoert. Wichtig ist bei den Ablehnungen
nicht nur, dass eine Ausnahme fliegt, sondern dass der Ist-Zustand danach noch
steht: ein Einspielen, das auf halbem Weg abbricht, ist schlimmer als eines,
das gar nicht erst anfaengt.
"""

from __future__ import annotations

import json
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest

import backup

# Eine der beiden Belegdateien traegt Umlaute, Leerzeichen und Klammern. Das
# ist der Normalfall bei einem Vermieter, nicht der Sonderfall.
GAS = 'Haus Müllerstraße 3/Allgemein/Rechnung_Gas (2025).pdf'
WASSER = 'Haus Müllerstraße 3/Allgemein/Wasser.pdf'


def _beleg_schreiben(wurzel: Path, relativ: str, inhalt: bytes) -> Path:
    pfad = wurzel / relativ
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    return pfad


def _auspacken(archiv: Path, ziel: Path) -> None:
    if zipfile.is_zipfile(archiv):
        with zipfile.ZipFile(archiv) as paket:
            paket.extractall(ziel)
    else:
        with tarfile.open(archiv) as tar:
            tar.extractall(ziel, filter='data')


def _namen(archiv: Path) -> set:
    if zipfile.is_zipfile(archiv):
        with zipfile.ZipFile(archiv) as paket:
            return set(paket.namelist())
    with tarfile.open(archiv) as tar:
        return set(tar.getnames())


def _umpacken(archiv: Path, ziel: Path, aendern=None, zusatz=None) -> Path:
    """Packt ein Archiv neu aus und wieder ein, dazwischen darf man pfuschen.

    aendern bekommt das entpackte Verzeichnis und darf darin herumschreiben,
    zusatz ist eine Liste (Name im Archiv, Inhalt) fuer Eintraege, die so
    niemals aus sicherung_erstellen kaemen. Der Behaelter bleibt derselbe
    (ZIP bleibt ZIP, tar.gz bleibt tar.gz).
    """
    als_zip = zipfile.is_zipfile(archiv)
    with tempfile.TemporaryDirectory() as arbeit:
        entpackt = Path(arbeit) / 'inhalt'
        entpackt.mkdir()
        _auspacken(archiv, entpackt)
        if aendern is not None:
            aendern(entpackt)
        if als_zip:
            with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as paket:
                for pfad in sorted(entpackt.rglob('*')):
                    if pfad.is_file():
                        paket.write(pfad, pfad.relative_to(entpackt).as_posix())
                for name, inhalt in (zusatz or []):
                    paket.writestr(name, inhalt)
            return ziel
        with tarfile.open(ziel, 'w:gz') as tar:
            for pfad in sorted(entpackt.rglob('*')):
                if pfad.is_file():
                    tar.add(pfad, arcname=str(pfad.relative_to(entpackt)))
            for name, inhalt in (zusatz or []):
                fremd = Path(arbeit) / 'fremd.bin'
                fremd.write_bytes(inhalt)
                tar.add(fremd, arcname=name)
    return ziel


@pytest.fixture
def stand(app_ctx, tmp_path, monkeypatch):
    """Eine kleine, aber vollstaendige Instanz: Stempel, Zeilen, Belege.

    app_ctx baut das Schema mit create_all() auf, also ohne alembic_version.
    Ohne Stempel haette jedes Archiv eine leere Kennung im Manifest, und das
    Einspielen wuerde es zu Recht ablehnen. Der Stempel wird darum hier
    nachgezogen, genau wie schema_aktualisieren() es beim Start tut.
    """
    from flask_migrate import stamp

    from models import InvoiceDocument, Property, db

    belege = tmp_path / 'belege'
    belege.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(belege))

    _beleg_schreiben(belege, GAS, b'%PDF-1.4\nGasrechnung 2025\n%%EOF\n')
    _beleg_schreiben(belege, WASSER, b'%PDF-1.4\nWasser\n%%EOF\n')

    stamp(revision="head")

    haus = Property(name='Haus Müllerstraße 3', is_standalone=False)
    db.session.add(haus)
    db.session.flush()
    db.session.add(InvoiceDocument(
        property_id=haus.id,
        filename='Rechnung_Gas (2025).pdf',
        document_path=GAS,
    ))
    db.session.commit()

    class Stand:
        app = app_ctx.app
        modul = app_ctx
        belegwurzel = belege
        archivordner = tmp_path / 'sicherungen'

    Stand.archivordner.mkdir()
    return Stand


def _hausnamen(app):
    from sqlalchemy import text

    from models import db

    with app.app_context():
        with db.engine.connect() as verbindung:
            return sorted(
                z[0] for z in verbindung.execute(text('SELECT name FROM properties'))
            )


# --- Kriterium 1: Archiv mit DB, Belegen und Manifest ----------------------


def test_archiv_enthaelt_datenbank_belege_und_manifest(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    assert archiv.exists()
    assert archiv.name.startswith('sicherung-')
    assert archiv.name.endswith('.nkfix')
    assert zipfile.is_zipfile(archiv)

    namen = _namen(archiv)

    assert backup.MANIFEST_NAME in namen
    assert backup.DB_IM_ARCHIV in namen
    assert f'{backup.BELEGE_IM_ARCHIV}/{GAS}' in namen
    assert f'{backup.BELEGE_IM_ARCHIV}/{WASSER}' in namen


def test_kein_teilarchiv_bleibt_liegen(stand):
    backup.sicherung_erstellen(stand.app, stand.archivordner)
    assert list(stand.archivordner.glob('*.teil')) == []


def test_zwei_sicherungen_in_derselben_sekunde_ueberschreiben_sich_nicht(stand):
    """Der Zeitstempel im Namen geht nur bis zur Sekunde.

    Beim Einspielen legt die Anwendung selbst eine Sicherung an. Wer zweimal
    hintereinander einspielt, landet genau in diesem Fall.
    """
    erste = backup.sicherung_erstellen(stand.app, stand.archivordner)
    zweite = backup.sicherung_erstellen(stand.app, stand.archivordner)

    assert erste != zweite
    assert erste.exists() and zweite.exists()


def test_ein_vorhandenes_archiv_wird_nicht_ueberschrieben(stand):
    backup.sicherung_erstellen(stand.app, stand.archivordner, name='fest.tar.gz')
    with pytest.raises(backup.SicherungsFehler, match='gibt es schon'):
        backup.sicherung_erstellen(stand.app, stand.archivordner, name='fest.tar.gz')


def test_symlinks_wandern_nicht_ins_archiv(stand):
    ziel = stand.belegwurzel / 'Haus Müllerstraße 3' / 'Allgemein' / 'Wasser.pdf'
    (stand.belegwurzel / 'abkuerzung.pdf').symlink_to(ziel)

    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    manifest = backup.manifest_lesen(archiv)

    assert 'abkuerzung.pdf' in manifest['uebersprungen']
    assert 'abkuerzung.pdf' not in {b['pfad'] for b in manifest['belege']}
    with zipfile.ZipFile(archiv) as paket:
        assert all((e.external_attr >> 16) & 0o170000 != 0o120000
                   for e in paket.infolist())


# --- Kriterium 2: Manifest mit Kennung, Zeit, Pruefsummen ------------------


def test_manifest_nennt_stempel_zeitpunkt_und_pruefsummen(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    manifest = backup.manifest_lesen(archiv)

    assert manifest['format'] == backup.MANIFEST_FORMAT
    assert manifest['alembic_revision'] == stand.modul._kopfrevision()
    # Mit Zeitzone, sonst ist der Zeitpunkt beim Lesen nicht einzuordnen.
    assert manifest['erstellt_am'][10] == 'T'
    assert manifest['erstellt_am'][-6] in '+-'

    assert len(manifest['datenbank']['sha256']) == 64
    assert manifest['datenbank']['groesse'] > 0

    belege = {b['pfad']: b for b in manifest['belege']}
    assert set(belege) == {GAS, WASSER}
    for eintrag in belege.values():
        assert len(eintrag['sha256']) == 64
        assert eintrag['groesse'] > 0
    assert manifest['zusammenfassung']['belege_anzahl'] == 2


def test_pruefsummen_im_manifest_gehoeren_zu_den_dateien(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    manifest = backup.manifest_lesen(archiv)

    for eintrag in manifest['belege']:
        gemessen = backup.pruefsumme(stand.belegwurzel / eintrag['pfad'])
        assert gemessen == eintrag['sha256']


# --- Kriterium 3: Sicherung des Ist-Zustands vor dem Einspielen ------------


def test_einspielen_sichert_vorher_den_ist_zustand(stand):
    from models import Property, db

    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    db.session.add(Property(name='Spaeter dazugekommen', is_standalone=True))
    db.session.commit()
    _beleg_schreiben(stand.belegwurzel, 'spaeter.pdf', b'%PDF-1.4\nspaeter\n')

    bericht = backup.sicherung_einspielen(stand.app, archiv)

    rueckweg = Path(bericht['sicherheitskopie'])
    assert rueckweg.exists()
    assert rueckweg.name.startswith('sicherung-vor-einspielen-')

    # Der eingespielte Stand kennt das zweite Haus nicht mehr.
    assert _hausnamen(stand.app) == ['Haus Müllerstraße 3']

    # Die Sicherheitskopie schon: der verworfene Stand ist nicht weg.
    zurueck = backup.sicherung_einspielen(stand.app, rueckweg)
    assert zurueck['fehlende_verweise'] == []
    assert _hausnamen(stand.app) == ['Haus Müllerstraße 3', 'Spaeter dazugekommen']
    assert (stand.belegwurzel / 'spaeter.pdf').is_file()


def test_einspielen_stellt_geloeschte_belege_wieder_her(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    (stand.belegwurzel / GAS).unlink()

    backup.sicherung_einspielen(stand.app, archiv)

    assert (stand.belegwurzel / GAS).is_file()
    assert (stand.belegwurzel / GAS).read_bytes().startswith(b'%PDF-1.4')


def test_umlaute_und_klammern_ueberleben_den_rundlauf(stand):
    vorher = backup.pruefsumme(stand.belegwurzel / GAS)
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    (stand.belegwurzel / GAS).write_bytes(b'kaputt')

    backup.sicherung_einspielen(stand.app, archiv)

    assert backup.pruefsumme(stand.belegwurzel / GAS) == vorher


# --- Kriterium 4: Archiv aus der Zukunft wird abgelehnt --------------------


def test_archiv_mit_unbekanntem_stempel_wird_abgelehnt(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def zukunft(entpackt: Path):
        datei = entpackt / backup.MANIFEST_NAME
        manifest = json.loads(datei.read_text(encoding='utf-8'))
        manifest['alembic_revision'] = 'ffffffffffff'
        datei.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    gefaelscht = _umpacken(archiv, stand.archivordner / 'zukunft.tar.gz', zukunft)

    with pytest.raises(backup.SicherungsFehler) as fehler:
        backup.sicherung_einspielen(stand.app, gefaelscht)

    meldung = str(fehler.value)
    assert 'ffffffffffff' in meldung
    assert 'zuerst NebenkostenFix aktualisieren' in meldung
    # Kein halber Vorgang: weder Sicherheitskopie noch veraenderte Belege.
    assert list(stand.archivordner.glob('sicherung-vor-einspielen-*')) == []
    assert (stand.belegwurzel / GAS).is_file()


def test_archiv_ohne_stempel_wird_abgelehnt(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def ohne(entpackt: Path):
        datei = entpackt / backup.MANIFEST_NAME
        manifest = json.loads(datei.read_text(encoding='utf-8'))
        manifest['alembic_revision'] = None
        datei.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    leer = _umpacken(archiv, stand.archivordner / 'ohne.tar.gz', ohne)

    with pytest.raises(backup.SicherungsFehler, match='keine Alembic-Kennung'):
        backup.sicherung_einspielen(stand.app, leer)


def test_fremdes_manifestformat_wird_abgelehnt(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def anderes_format(entpackt: Path):
        datei = entpackt / backup.MANIFEST_NAME
        manifest = json.loads(datei.read_text(encoding='utf-8'))
        manifest['format'] = backup.MANIFEST_FORMAT + 1
        datei.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    fremd = _umpacken(archiv, stand.archivordner / 'fremd.tar.gz', anderes_format)

    with pytest.raises(backup.SicherungsFehler, match='Manifestformat'):
        backup.sicherung_einspielen(stand.app, fremd)


def test_archiv_ohne_manifest_wird_abgelehnt(stand, tmp_path):
    fremd = stand.archivordner / 'irgendwas.tar.gz'
    beliebig = tmp_path / 'beliebig.txt'
    beliebig.write_text('kein Backup', encoding='utf-8')
    with tarfile.open(fremd, 'w:gz') as tar:
        tar.add(beliebig, arcname='beliebig.txt')

    with pytest.raises(backup.SicherungsFehler, match='keine Sicherung'):
        backup.sicherung_einspielen(stand.app, fremd)


# --- Beschaedigte und boesartige Archive -----------------------------------


def test_beschaedigtes_archiv_wird_abgelehnt_und_aendert_nichts(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    vorher = backup.pruefsumme(stand.belegwurzel / GAS)

    def verdrehen(entpackt: Path):
        # Gleich lang, anderer Inhalt: nur die Pruefsumme kann es merken.
        datei = entpackt / backup.BELEGE_IM_ARCHIV / GAS
        datei.write_bytes(bytes(reversed(datei.read_bytes())))

    kaputt = _umpacken(archiv, stand.archivordner / 'kaputt.tar.gz', verdrehen)

    with pytest.raises(backup.SicherungsFehler, match='Prüfsumme'):
        backup.sicherung_einspielen(stand.app, kaputt)

    assert backup.pruefsumme(stand.belegwurzel / GAS) == vorher
    assert _hausnamen(stand.app) == ['Haus Müllerstraße 3']


def test_fehlende_datei_im_archiv_wird_bemerkt(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def loeschen(entpackt: Path):
        (entpackt / backup.BELEGE_IM_ARCHIV / GAS).unlink()

    luecke = _umpacken(archiv, stand.archivordner / 'luecke.tar.gz', loeschen)

    with pytest.raises(backup.SicherungsFehler, match='fehlen'):
        backup.sicherung_einspielen(stand.app, luecke)


def test_pfad_aus_dem_zielverzeichnis_heraus_wird_abgelehnt(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    boese = _umpacken(
        archiv, stand.archivordner / 'boese.tar.gz',
        zusatz=[('../entwischt.txt', b'ausserhalb')],
    )

    with pytest.raises(backup.SicherungsFehler, match='heraus'):
        backup.sicherung_einspielen(stand.app, boese)

    assert not (stand.archivordner.parent / 'entwischt.txt').exists()


# --- Kriterium 5: Dateiverweise zeigen auf existierende Dateien ------------


def test_dateiverweise_zeigen_nach_dem_einspielen_auf_dateien(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    (stand.belegwurzel / GAS).unlink()
    assert len(backup.dateiverweise_pruefen(stand.app)) == 1

    bericht = backup.sicherung_einspielen(stand.app, archiv)

    assert bericht['fehlende_verweise'] == []
    assert backup.dateiverweise_pruefen(stand.app) == []


def test_dateiverweise_pruefen_nennt_tabelle_spalte_und_pfad(stand):
    (stand.belegwurzel / GAS).unlink()

    fehlend = backup.dateiverweise_pruefen(stand.app)

    assert len(fehlend) == 1
    assert fehlend[0]['tabelle'] == 'invoice_documents'
    assert fehlend[0]['spalte'] == 'document_path'
    assert fehlend[0]['pfad'] == GAS


def test_geprueft_werden_alle_pfadspalten_die_es_gibt(stand):
    """Jede Spalte in PFADSPALTEN existiert auch wirklich im Schema.

    Ein Tippfehler in der Tabelle wuerde stillschweigend uebersprungen: die
    Pruefung meldete dann 'alles gut', waehrend die Oberflaeche 404 liefert.
    """
    from sqlalchemy import inspect

    from models import db

    with stand.app.app_context():
        pruefer = inspect(db.engine)
        for tabelle, spalte in backup.PFADSPALTEN:
            spalten = {s['name'] for s in pruefer.get_columns(tabelle)}
            assert spalte in spalten, f'{tabelle}.{spalte} gibt es nicht'


# --- Fehlerfaelle an den Raendern -----------------------------------------


def test_sichern_lehnt_eine_nicht_sqlite_datenbank_ab(stand, monkeypatch):
    # setitem statt einer Zuweisung: app ist ein Modulobjekt und lebt laenger
    # als der Test. Eine Zuweisung wuerde jeden folgenden Test vergiften.
    monkeypatch.setitem(stand.app.config, 'SQLALCHEMY_DATABASE_URI', 'postgresql://x/y')
    with pytest.raises(backup.SicherungsFehler, match='nur SQLite'):
        backup.sicherung_erstellen(stand.app, stand.archivordner)


def test_sichern_ohne_datenbankdatei_sagt_das(stand, tmp_path, monkeypatch):
    fehlt = tmp_path / 'gibtsnicht.db'
    monkeypatch.setitem(
        stand.app.config, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{fehlt}'
    )
    with pytest.raises(backup.SicherungsFehler, match='Keine Datenbank'):
        backup.sicherung_erstellen(stand.app, stand.archivordner)


def test_verknuepfung_im_archiv_wird_abgelehnt(stand, tmp_path):
    """Ein Symlink im Archiv zeigt beim Auspacken irgendwohin.

    sicherung_erstellen packt keine ein, aber ein Archiv kann von woanders
    kommen. Geprueft wird vor dem Auspacken, nicht danach.
    """
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    boese = stand.archivordner / 'mit-verknuepfung.tar.gz'
    with tempfile.TemporaryDirectory() as arbeit:
        entpackt = Path(arbeit)
        _auspacken(archiv, entpackt)
        with tarfile.open(boese, 'w:gz') as tar:
            for pfad in sorted(entpackt.rglob('*')):
                if pfad.is_file():
                    tar.add(pfad, arcname=str(pfad.relative_to(entpackt)))
            eintrag = tarfile.TarInfo('belege/anderswo.pdf')
            eintrag.type = tarfile.SYMTYPE
            eintrag.linkname = '/etc/passwd'
            tar.addfile(eintrag)

    with pytest.raises(backup.SicherungsFehler, match='Verknüpfung'):
        backup.sicherung_einspielen(stand.app, boese)


def test_zusaetzliche_datei_im_archiv_wird_bemerkt(stand):
    """Eine Datei, die im Manifest nicht steht, ist nachtraeglich dazugekommen."""
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def dazu(entpackt: Path):
        (entpackt / backup.BELEGE_IM_ARCHIV / 'untergeschoben.pdf').write_bytes(b'x')

    zuviel = _umpacken(archiv, stand.archivordner / 'zuviel.tar.gz', dazu)

    with pytest.raises(backup.SicherungsFehler, match='im Manifest nicht'):
        backup.sicherung_einspielen(stand.app, zuviel)


def test_sichern_kommt_auch_ohne_belegordner_zurecht(stand, tmp_path, monkeypatch):
    """Eine frische Instanz hat noch keinen einzigen Beleg."""
    monkeypatch.setenv('NAS_MOUNT_PATH', str(tmp_path / 'noch-nichts'))

    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    manifest = backup.manifest_lesen(archiv)

    assert manifest['belege'] == []
    assert manifest['zusammenfassung']['belege_anzahl'] == 0


# --- Kommandozeile ---------------------------------------------------------


def test_groessenangabe_bleibt_bei_kleinen_archiven_lesbar():
    assert backup.lesbare_groesse(45) == '45 Bytes'
    assert backup.lesbare_groesse(81920) == '80.0 KB'
    assert backup.lesbare_groesse(5 * 1024 ** 2) == '5.0 MB'
    assert backup.lesbare_groesse(3 * 1024 ** 3) == '3.0 GB'


def test_flask_backup_kennt_die_befehle(stand):
    gruppe = stand.app.cli.commands.get('backup')
    assert gruppe is not None
    # NK-130: entschluesseln fuer verschluesselte Sicherungen und Exporte.
    assert set(gruppe.commands) == {'create', 'info', 'restore', 'entschluesseln'}


def _cli(stand, *argumente):
    laeufer = stand.app.test_cli_runner()
    return laeufer.invoke(args=['backup', *argumente])


def test_cli_create_nennt_ort_groesse_und_schemastand(stand):
    ergebnis = _cli(stand, 'create', '--ziel', str(stand.archivordner))

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Sicherung:' in ergebnis.output
    assert stand.modul._kopfrevision() in ergebnis.output
    assert 'Belege: 2' in ergebnis.output
    assert len(list(stand.archivordner.glob('sicherung-*.nkfix'))) == 1


def test_cli_info_sagt_ob_das_archiv_einspielbar_ist(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    ergebnis = _cli(stand, 'info', str(archiv))

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Einspielbar: ja' in ergebnis.output


def test_cli_info_warnt_bei_einem_archiv_aus_der_zukunft(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def zukunft(entpackt: Path):
        datei = entpackt / backup.MANIFEST_NAME
        manifest = json.loads(datei.read_text(encoding='utf-8'))
        manifest['alembic_revision'] = 'ffffffffffff'
        datei.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    neuer = _umpacken(archiv, stand.archivordner / 'neuer.tar.gz', zukunft)

    ergebnis = _cli(stand, 'info', str(neuer))

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Einspielbar: nein' in ergebnis.output


def test_cli_info_auf_einem_fremden_archiv_endet_mit_fehler(stand, tmp_path):
    fremd = stand.archivordner / 'fremd.tar.gz'
    beliebig = tmp_path / 'beliebig.txt'
    beliebig.write_text('kein Backup', encoding='utf-8')
    with tarfile.open(fremd, 'w:gz') as tar:
        tar.add(beliebig, arcname='beliebig.txt')

    ergebnis = _cli(stand, 'info', str(fremd))

    assert ergebnis.exit_code != 0
    assert 'keine Sicherung' in ergebnis.output


def test_cli_restore_ohne_ja_fragt_nach_und_aendert_nichts(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    (stand.belegwurzel / GAS).unlink()

    laeufer = stand.app.test_cli_runner()
    ergebnis = laeufer.invoke(args=['backup', 'restore', str(archiv)], input='n\n')

    assert ergebnis.exit_code != 0
    assert not (stand.belegwurzel / GAS).exists()


def test_cli_restore_mit_ja_spielt_ein_und_meldet_die_sicherheitskopie(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)
    (stand.belegwurzel / GAS).unlink()

    ergebnis = _cli(stand, 'restore', str(archiv), '--ja')

    assert ergebnis.exit_code == 0, ergebnis.output
    assert 'Ist-Zustand gesichert unter:' in ergebnis.output
    assert 'Alle Dateiverweise' in ergebnis.output
    assert (stand.belegwurzel / GAS).is_file()


def test_cli_restore_lehnt_ein_archiv_aus_der_zukunft_lesbar_ab(stand):
    archiv = backup.sicherung_erstellen(stand.app, stand.archivordner)

    def zukunft(entpackt: Path):
        datei = entpackt / backup.MANIFEST_NAME
        manifest = json.loads(datei.read_text(encoding='utf-8'))
        manifest['alembic_revision'] = 'ffffffffffff'
        datei.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    neuer = _umpacken(archiv, stand.archivordner / 'neuer.tar.gz', zukunft)

    ergebnis = _cli(stand, 'restore', str(neuer), '--ja')

    assert ergebnis.exit_code != 0
    assert 'zuerst NebenkostenFix aktualisieren' in ergebnis.output
    assert 'Traceback' not in ergebnis.output


def test_eine_unbekannte_spalte_wird_uebersprungen_und_protokolliert(stand):
    """Der stille Schlucker bekommt eine Stimme (NK-042).

    Die Pruefung liest ueber SQL, damit sie auch auf einem aelteren Schema
    laeuft -- eine Spalte, die es dort noch nicht gibt, ist also erwartbar und
    kein Grund zum Abbruch. Vorher stand hier ``except Exception: continue``,
    und damit verschwand auch der andere Fall lautlos: eine Datenbank, in die
    gar nicht hineingesehen werden konnte, meldete 'keine fehlenden Belege'.
    Jetzt steht der Grund wenigstens im Protokoll.
    """
    import logging

    # ``caplog`` sieht hier nichts: init_protokoll setzt propagate = False, und
    # pytest haengt seinen Mitschnitt an den Wurzel-Logger. Also direkt an den
    # Logger dieses Moduls.
    gesammelt = []

    class _Mitschnitt(logging.Handler):
        def emit(self, satz):
            gesammelt.append(satz.getMessage())

    mitschnitt = _Mitschnitt(level=logging.DEBUG)
    logger = logging.getLogger('nebenkosten.backup')
    vorherige_stufe = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(mitschnitt)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(backup, 'PFADSPALTEN',
                   backup.PFADSPALTEN + (('gibt_es_nicht', 'auch_nicht'),))
    try:
        fehlend = backup.dateiverweise_pruefen(stand.app)
    finally:
        monkey.undo()
        logger.removeHandler(mitschnitt)
        logger.setLevel(vorherige_stufe)

    # Die echten Spalten sind trotzdem geprueft worden.
    assert fehlend == []
    assert any('gibt_es_nicht' in zeile for zeile in gesammelt), gesammelt
