"""NK-131: neutrale Dateinamen, Wanderung des Bestands, sprechender Export
(F-60, E-5 → D-87)."""

import io
import os
import zipfile
from datetime import date
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from nebenkostenfix import ablage_migration
from nebenkostenfix.handlers.nas_handler import NASHandler

PDF = b'%PDF-1.4\n%Probe\n%%EOF\n'
JPG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + b'\x01' * 40


@pytest.fixture
def nas(tmp_path, monkeypatch):
    monkeypatch.setenv('NAS_MOUNT_PATH', str(tmp_path / 'belege'))
    return NASHandler()


def _datei(inhalt=PDF, name='Mietvertrag Müller.pdf'):
    return FileStorage(io.BytesIO(inhalt), filename=name)


def test_kein_name_im_pfad(nas):
    """Weder Mieter noch Wohnung noch Immobilie stehen im Pfad."""
    pfade = [
        nas.save_tenant_contract(_datei(), 'Haus Müllerstraße 3', 'EG links', 'Familie Schmitt'),
        nas.save_reading_photo(_datei(JPG, 'foto.jpg'), 'Wasser', 'Haus Müllerstraße 3',
                               'EG links', date(2024, 3, 1)),
        nas.save_invoice_document(_datei(), 'Heizung', 'Haus Müllerstraße 3',
                                  date(2024, 1, 1), date(2024, 12, 31)),
        nas.save_general_document(_datei(), 'Haus Müllerstraße 3')[0],
        nas.save_billing_report(_datei(), 'Haus Müllerstraße 3', 'EG links', 'Familie Schmitt')[0],
    ]
    for pfad in pfade:
        assert NASHandler.NEUTRAL.match(pfad), pfad
        for teil in ('Schmitt', 'Muell', 'EG', 'Haus', 'Mietvertrag'):
            assert teil not in pfad
    assert pfade[1].startswith('2024/')  # Jahr des Ablesedatums
    assert pfade[2].startswith('2024/')  # Ende des Rechnungszeitraums
    # Nur Jahresordner unter der Wurzel
    assert all(p.name.isdigit() for p in Path(nas.nas_mount_path).iterdir())


# --- Wanderung ---------------------------------------------------------------

def _alt_anlegen(wurzel: Path, relativ: str, inhalt: bytes) -> str:
    pfad = wurzel / relativ
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    return relativ


@pytest.fixture
def altbestand(app_ctx, monkeypatch, tmp_path):
    """Ein Bestand im Baum vor NK-131, mit geteiltem und fehlendem Pfad."""
    from billing_factories import apt, category, house, meter, tenant
    from nebenkostenfix.models import (CostInvoice, InvoiceDocument, MeterReading,
                        TenantBillingReport, db)

    wurzel = tmp_path / 'belege'
    wurzel.mkdir()
    monkeypatch.setenv('NAS_MOUNT_PATH', str(wurzel))
    haus = house('Haus Lindenstraße')
    wohnung = apt(haus, 'EG links', 50.0)
    mieter = tenant(wohnung, 'Anna Mieterin')
    kat = category('Wasserversorgung')
    inhalte = {}

    mieter.contract_path = _alt_anlegen(
        wurzel, 'Haus_Lindenstrasse/Wohnungen/EG_links/Anna_Mieterin/Mietvertraege/Vertrag.pdf',
        PDF + b'vertrag')
    inhalte['vertrag'] = PDF + b'vertrag'
    geteilt = _alt_anlegen(wurzel, 'Haus_Lindenstrasse/Allgemein/Dokumente/Sammel.pdf',
                           PDF + b'sammel')
    dok = InvoiceDocument(property_id=haus.id, filename='Sammel.pdf', document_path=geteilt)
    db.session.add(dok)
    db.session.flush()
    db.session.add(CostInvoice(category_id=kat.id, property_id=haus.id,
                               start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
                               amount=100, invoice_number='R1', document_path=geteilt,
                               invoice_document_id=dok.id))
    zaehler = meter(haus, kat, 'WZ-1', is_main=True)
    db.session.add(MeterReading(meter_id=zaehler.id, reading_date=date(2024, 5, 1),
                                value=1.0, document_path=_alt_anlegen(
                                    wurzel, 'Haus_Lindenstrasse/Allgemein/Zaehlerstaende/Z.jpg', JPG)))
    # absoluter Altpfad innerhalb der Wurzel
    absolut = str(wurzel / _alt_anlegen(
        wurzel, 'Haus_Lindenstrasse/Wohnungen/EG_links/Anna_Mieterin/Abrechnungen/A.pdf',
        PDF + b'abrechnung'))
    db.session.add(TenantBillingReport(tenant_id=mieter.id, start_date=date(2024, 1, 1),
                                       end_date=date(2024, 12, 31), frist_ende=date(2025, 12, 31),
                                       document_path=absolut,
                                       document_path_detailed='weg/fehlt.pdf'))
    db.session.commit()
    return wurzel


def _alle_pfade():
    from nebenkostenfix.models import db
    return {pfad for modell, spalte in ablage_migration._spalten()
            for (pfad,) in db.session.query(getattr(modell, spalte))
            if pfad}


def test_wanderung_bringt_jeden_beleg_bytegleich_auf_neutrale_namen(altbestand):
    from nebenkostenfix.models import db
    vorher = {}
    for pfad in _alle_pfade():
        voll = Path(pfad) if os.path.isabs(pfad) else altbestand / pfad
        if voll.exists():
            vorher[pfad] = voll.read_bytes()

    bericht = ablage_migration.migrieren(db.session, altbestand)
    assert bericht['fehlend'] == 1          # weg/fehlt.pdf
    assert bericht['umbenannt'] == 4        # Vertrag, Sammel (geteilt), Foto, Abrechnung
    assert bericht['abweichend'] == 0
    nachher = _alle_pfade()
    for pfad in nachher - {'weg/fehlt.pdf'}:
        assert ablage_migration.NEUTRAL.match(pfad), pfad
    # bytegleich: jede alte Datei liegt mit ihrem Inhalt unter einem neuen Namen
    inhalte = sorted((altbestand / p).read_bytes() for p in nachher if p != 'weg/fehlt.pdf')
    assert inhalte == sorted(set(vorher.values()))
    # der alte Baum ist weg, nur Jahresordner bleiben
    assert all(p.name.isdigit() for p in altbestand.iterdir())


def test_geteilter_pfad_bleibt_geteilt(altbestand):
    from nebenkostenfix.models import CostInvoice, InvoiceDocument, db
    ablage_migration.migrieren(db.session, altbestand)
    assert CostInvoice.query.one().document_path == InvoiceDocument.query.one().document_path


def test_zweiter_lauf_tut_nichts(altbestand):
    from nebenkostenfix.models import db
    ablage_migration.migrieren(db.session, altbestand)
    stand = _alle_pfade()
    bericht = ablage_migration.migrieren(db.session, altbestand)
    assert bericht['umbenannt'] == 0
    assert _alle_pfade() == stand


def test_probelauf_aendert_nichts(altbestand):
    from nebenkostenfix.models import db
    vorher = _alle_pfade()
    dateien = sorted(p for p in altbestand.rglob('*') if p.is_file())
    bericht = ablage_migration.migrieren(db.session, altbestand, pruefen=True)
    assert bericht['probelauf'] and bericht['umbenannt'] == 4
    assert _alle_pfade() == vorher
    assert sorted(p for p in altbestand.rglob('*') if p.is_file()) == dateien


def test_abbruch_vor_dem_festschreiben_verliert_nichts(altbestand, monkeypatch):
    """Faellt der Lauf beim Festschreiben, zeigt die Datenbank weiter auf
    vollstaendige alte Dateien."""
    from nebenkostenfix.models import db
    vorher = _alle_pfade()

    def kaputt():
        raise RuntimeError('Stromausfall')
    monkeypatch.setattr(db.session, 'commit', kaputt)
    with pytest.raises(RuntimeError):
        ablage_migration.migrieren(db.session, altbestand)
    db.session.rollback()
    monkeypatch.undo()
    assert _alle_pfade() == vorher
    for pfad in vorher - {'weg/fehlt.pdf'}:
        voll = Path(pfad) if os.path.isabs(pfad) else altbestand / pfad
        assert voll.is_file(), pfad
    # NK-147: keine verwaisten neuen Verweise -- sonst legte jeder Start
    # weitere an, und harte Verweise landeten in der Sicherung.
    assert not [p for p in altbestand.rglob('*')
                if p.is_file() and ablage_migration.NEUTRAL.match(
                    p.relative_to(altbestand).as_posix())]


def test_die_anwendung_liefert_nach_der_wanderung_aus(altbestand, auth_client):
    from nebenkostenfix.models import Tenant, db
    ablage_migration.migrieren(db.session, altbestand)
    mieter = Tenant.query.one()
    antwort = auth_client.get(f'/api/dateien/mietvertrag/{mieter.id}')
    assert antwort.status_code == 200
    assert antwort.data == PDF + b'vertrag'


# --- Sprechender Export --------------------------------------------------------

def test_belege_exportieren_mit_sprechenden_namen(altbestand, auth_client):
    from nebenkostenfix.models import db
    ablage_migration.migrieren(db.session, altbestand)
    antwort = auth_client.get('/api/belege/export')
    assert antwort.status_code == 200
    assert antwort.mimetype == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(antwort.data)) as paket:
        namen = paket.namelist()
        assert 'Haus Lindenstraße/Wohnungen/EG links/Anna Mieterin/Mietvertraege/Mietvertrag.pdf' in namen
        assert paket.read('Haus Lindenstraße/Wohnungen/EG links/Anna Mieterin/Mietvertraege/Mietvertrag.pdf') \
            == PDF + b'vertrag'
        assert 'Haus Lindenstraße/Allgemein/Dokumente/Sammel.pdf' in namen
        assert any(n.startswith('Haus Lindenstraße/Allgemein/Zaehlerstaende/Zaehlerstand_')
                   and n.endswith('.jpg') for n in namen)
        assert 'FEHLENDE_DATEIEN.txt' in namen
        assert all('..' not in n and not n.startswith('/') for n in namen)


def test_belege_export_je_immobilie_und_unbekannt(altbestand, auth_client):
    from nebenkostenfix.models import Property
    haus = Property.query.one()
    assert auth_client.get(f'/api/belege/export?property_id={haus.id}').status_code == 200
    assert auth_client.get('/api/belege/export?property_id=999').status_code == 404


def test_namen_im_export_sind_entschaerft():
    from nebenkostenfix import belege_export
    name = belege_export._name('../../etc/passwd')
    assert '/' not in name and not name.startswith('.')
    assert '/' not in belege_export._name('a/b\\c:d')
    assert belege_export._name('') == 'unbenannt'


def test_befehl_mit_probelauf(altbestand):
    import json

    import app as app_module
    runner = app_module.app.test_cli_runner()
    erg = runner.invoke(args=['belege-umstellen', '--pruefen'])
    assert erg.exit_code == 0, erg.output
    bericht = json.loads(erg.output)
    assert bericht['probelauf'] is True and bericht['umbenannt'] == 4
    erg = runner.invoke(args=['belege-umstellen'])
    assert json.loads(erg.output)['umbenannt'] == 4


@pytest.mark.parametrize('alte_wurzel,umgebung', [
    ('/mnt/nas/nebenkostenabrechnung', None),
    ('/srv/alte-instanz/belege', '/srv/alte-instanz/belege'),
])
def test_absoluter_pfad_der_alten_instanz_wird_gefunden(app_ctx, monkeypatch, tmp_path,
                                                        alte_wurzel, umgebung):
    """NK-147: die alte Instanz speicherte manche Pfade absolut unter ihrem
    Einhaengepunkt. Nach dem Umzug liegt der Baum unter der neuen Wurzel."""
    from billing_factories import house
    from nebenkostenfix.models import InvoiceDocument, db

    wurzel = tmp_path / 'belege'
    _alt_anlegen(wurzel, 'Haus/Allgemein/Dokumente/Strom.pdf', PDF + b'strom')
    if umgebung:
        monkeypatch.setenv('ALTE_BELEGWURZEL', umgebung)
    haus = house('Haus')
    dok = InvoiceDocument(property_id=haus.id, filename='Strom.pdf',
                          document_path=f'{alte_wurzel}/Haus/Allgemein/Dokumente/Strom.pdf')
    fremd = InvoiceDocument(property_id=haus.id, filename='x.pdf',
                            document_path=f'{alte_wurzel}/../../../etc/passwd')
    db.session.add_all([dok, fremd])
    db.session.commit()

    bericht = ablage_migration.migrieren(db.session, wurzel)

    assert bericht['umbenannt'] == 1 and bericht['fehlend'] == 1
    db.session.refresh(dok)
    assert ablage_migration.NEUTRAL.match(dok.document_path)
    assert (wurzel / dok.document_path).read_bytes() == PDF + b'strom'
