"""Der Beleg-Export: alle Belege einer Abrechnung als ZIP (NK-063).

Der Mieter kann die Belage einsehen und prüfen (§ 556 Abs. 4 BGB): die
Rechnungen, auf die die Abrechnung verweist, müssen sich dem Mieter
gegenüber als Beleg vorlegen lassen. Die Route sammelt die Belege der
Abrechnung zu einem ZIP -- gelesen aus dem gespeicherten Ergebnis (R-
DOC-02): die Zeilen verweisen je auf ihre Rechnung (NK-058), und genau
diese Verweise zählen, nicht das, was heute in den Zeiträumen läge.

Was fehlt -- gelöschte Rechnung, keine Datei, Datei weg -- steht als
Liste in das Archiv, statt still zu fehlen: der Vermieter muss sehen
können, dass etwas fehlt, bevor er das Paket dem Mieter gibt.
"""

from datetime import date

from billing_factories import (
    apt,
    category,
    house,
    invoice,
    payment,
    profile,
    reading,
    tenant,
)

ZEITRAUM = {'start_date': '2025-01-01', 'end_date': '2025-12-31'}


def _welt(app_ctx, monkeypatch, nas):
    """Ein Mieter, zwei Wasser-Rechnungen mit Belegen, eine ohne Datei.

    Die Rechnungen laufen über 'direkt': die Zeile verweist je auf ihre
    Rechnung, das Ergebnis trägt die Verweise. Der NAS-Sandbox-Ordner
    nimmt zwei echte Dateien auf; die dritte Rechnung bleibt ohne Beleg.
    Liefert den Mieter."""
    from models import InvoiceDocument, db

    monkeypatch.setenv('NAS_MOUNT_PATH', str(nas))
    kategorie = category('Wasserversorgung')
    prop = house()
    wohnung = apt(prop, 'EG links', 50.0)
    mieter = tenant(wohnung, 'Anna Mieterin', move_in=date(2024, 1, 1))
    profile(mieter, kategorie, 'direkt')

    datei_1 = nas / 'stadtwerke-wasser-2025.pdf'
    datei_1.write_bytes(b'%PDF-1.4 Stadtwerke Wasser 2025')
    dokument_1 = InvoiceDocument(
        property_id=prop.id, filename='stadtwerke-wasser-2025.pdf',
        document_path=str(datei_1), upload_date=date(2025, 12, 31),
        is_collective=True)
    rechnung_1 = invoice(prop, kategorie, 600.0, date(2025, 1, 1),
                         date(2025, 6, 30), invoice_number='SW-2025-1')
    rechnung_1.document = dokument_1

    datei_2 = nas / 'wasserwerk-2025.pdf'
    datei_2.write_bytes(b'%PDF-1.4 Wasserwerk 2025')
    dokument_2 = InvoiceDocument(
        property_id=prop.id, filename='wasserwerk-2025.pdf',
        document_path=str(datei_2), upload_date=date(2025, 12, 31),
        is_collective=True)
    rechnung_2 = invoice(prop, kategorie, 600.0, date(2025, 7, 1),
                         date(2025, 12, 31), invoice_number='WW-2025-2')
    rechnung_2.document = dokument_2

    # Dritte Rechnung, deren Datei verschwunden ist: der Belegweh.
    rechnung_3 = invoice(prop, kategorie, 100.0, date(2025, 1, 1),
                         date(2025, 12, 31), invoice_number='X-2025-3')

    # Zählerstand, damit 'direkt' eine Zeile je Rechnung rechnet.
    from billing_factories import meter
    zaehler = meter(prop, kategorie, 'WA-1', is_main=False, apartment=wohnung)
    reading(zaehler, date(2025, 1, 1), 0.0)
    reading(zaehler, date(2025, 12, 31), 1200.0)
    payment(mieter, 300.0, date(2025, 6, 1))
    db.session.commit()
    return mieter


def _finalisiere(auth_client, mieter_id):
    from models import TenantBillingReport

    antwort = auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter_id, **ZEITRAUM})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return TenantBillingReport.query.one()


def _archiv_inhalt(antwort):
    """Name -> Inhalt des gelieferten ZIP."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(antwort.data)) as paket:
        return {name: paket.read(name) for name in paket.namelist()}


# --- Das Archiv: die Belege der Abrechnung ----------------------------------


def test_das_archiv_traegt_die_belege_der_abrechnung(auth_client, app_ctx,
                                                     monkeypatch, tmp_path):
    """Das ZIP enthält die Dateien zu den Rechnungen aus dem Ergebnis --
    unter ihrem eigenen Namen, aus der NAS-Sandbox geholt."""
    nas = tmp_path / 'nas'
    nas.mkdir()
    mieter = _welt(app_ctx, monkeypatch, nas)
    report = _finalisiere(auth_client, mieter.id)

    antwort = auth_client.get(f'/api/billing/reports/{report.id}/belege')
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    inhalt = _archiv_inhalt(antwort)
    assert 'stadtwerke-wasser-2025.pdf' in inhalt
    assert 'wasserwerk-2025.pdf' in inhalt
    assert inhalt['stadtwerke-wasser-2025.pdf'] == \
        b'%PDF-1.4 Stadtwerke Wasser 2025'

    # Der Name des Pakets nennt Mieter und Zeitraum; der Name des Mieters
    # bleibt lesbar, nur Sonderzeichen werden ersetzt.
    dateiname = antwort.headers['Content-Disposition']
    assert 'Belege_Anna Mieterin_20250101-20251231.zip' in dateiname


def test_was_fehlt_steht_im_archiv(auth_client, app_ctx, monkeypatch, tmp_path):
    """Die Rechnung ohne Datei fehlt nicht still: das Archiv trägt die
    Liste der fehlenden Belege als eigene Datei."""
    nas = tmp_path / 'nas'
    nas.mkdir()
    mieter = _welt(app_ctx, monkeypatch, nas)
    report = _finalisiere(auth_client, mieter.id)

    antwort = auth_client.get(f'/api/billing/reports/{report.id}/belege')
    inhalt = _archiv_inhalt(antwort)
    assert 'FEHLENDE_BELEGE.txt' in inhalt
    texte = inhalt['FEHLENDE_BELEGE.txt'].decode('utf-8')
    assert 'X-2025-3' in texte
    assert 'keine Datei hinterlegt' in texte


def test_die_verweise_kommen_aus_dem_ergebnis(auth_client, app_ctx,
                                              monkeypatch, tmp_path):
    """Zählt der Verweis oder der heutige Zeilenbestand? Der Beleg wird
    über die Rechnung aus dem Ergebnis geholt -- selbst wenn heute eine
    zweite Rechnung aus dem Zeiträumen liegen würde, die nicht in der
    Abrechnung steht."""
    from models import CostInvoice, db

    nas = tmp_path / 'nas'
    nas.mkdir()
    mieter = _welt(app_ctx, monkeypatch, nas)
    report = _finalisiere(auth_client, mieter.id)

    # Eine neue Rechnung, die nach der Abrechnung ins Haus kommt: sie
    # gehört in dieselben Zeiträume, hat einen Beleg -- und darf trotzdem
    # nicht ins Archiv der fertigen Abrechnung.
    kategorie = CostInvoice.query.first().category
    prop = kategorie.invoices[0].property
    datei_neu = nas / 'spaeter-kommend.pdf'
    datei_neu.write_bytes(b'%PDF-1.4 spaeter')
    from models import InvoiceDocument
    dokument = InvoiceDocument(
        property_id=prop.id, filename='spaeter-kommend.pdf',
        document_path=str(datei_neu), upload_date=date(2025, 12, 31),
        is_collective=True)
    rechnung_neu = CostInvoice(
        category_id=kategorie.id, property_id=prop.id,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        amount=50, invoice_number='NEU-1', document=dokument)
    db.session.add(rechnung_neu)
    db.session.commit()

    antwort = auth_client.get(f'/api/billing/reports/{report.id}/belege')
    inhalt = _archiv_inhalt(antwort)
    assert 'spaeter-kommend.pdf' not in inhalt
    assert 'NEU-1' not in inhalt.get('FEHLENDE_BELEGE.txt', b'').decode('utf-8')


def test_ohne_irgendwelche_belege_wird_abgesagt(auth_client, app_ctx):
    """Ein Ergebnis ohne Rechnungsverweise -- hier: ein handgesetzter
    Schnappschuss, dessen Zeile keine Rechnung nennt -- liefert keine
    Belege: die Route sagt ab, statt ein leeres Paket zu geben."""
    from models import BillingReportVersion, TenantBillingReport, db
    from frist import frist_ende

    prop = house()
    wohnung = apt(prop, 'EG links', 50.0)
    mieter = tenant(wohnung, 'Ohne Belege', move_in=date(2024, 1, 1))

    report = TenantBillingReport(
        tenant_id=mieter.id,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        frist_ende=frist_ende(date(2025, 12, 31)),
    )
    db.session.add(report)
    db.session.commit()
    version = BillingReportVersion(
        report_id=report.id, nummer=1,
        eingangsdaten={}, ergebnis={'line_items': [
            {'description': 'Zeile ohne Rechnung', 'invoice_id': None},
        ]},
        software_version='0.7.0', regel_version='2026-08-28')
    db.session.add(version)
    db.session.commit()

    antwort = auth_client.get(f'/api/billing/reports/{report.id}/belege')
    assert antwort.status_code == 404
    assert 'keine Belege' in antwort.get_json()['error']
