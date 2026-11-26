"""Beleg-Erhalt: Bearbeiten einer Rechnung hängt ihren Beleg nicht still um.

Befund: Im Dialog „Rechnung bearbeiten“ blieb eine Datei aus einem früheren
Dialog im Dateifeld liegen. ``saveInvoice`` schickte sie mit, und
``PUT /api/invoices/<id>`` legte daraus ohne Rückfrage einen neuen Beleg an
und hängte die Rechnung darauf um. Die alte Verknüpfung war weg, die
Rechnung zeigte eine fremde PDF.

Die Oberfläche leert das Dateifeld jetzt beim Öffnen und Verwerfen (Wächter
im Rauchtest ``scripts/rauchtest_design.js``, „Beleg-Erhalt“). Der Server
sichert zusätzlich ab: Hat die Rechnung schon einen Beleg, ersetzt eine
mitgeschickte Datei ihn nur, wenn die Anfrage ``beleg_ersetzen`` setzt.
Ohne Beleg hängt eine Datei wie bisher ohne Rückfrage an.

Nur fiktive Daten, Dummy-PDFs.
"""

from __future__ import annotations

import io
import os

import billing_factories as f
from nebenkostenfix.models import CostInvoice, InvoiceDocument, db

PDF_A = b'%PDF-1.4\n%synthetisch A\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
PDF_B = b'%PDF-1.4\n%synthetisch B\n2 0 obj\n<</B 1>>\nendobj\n%%EOF\n'


def _stamm():
    haus = f.house('Testhaus Belegtausch')
    kat = f.category('Wartung')
    db.session.commit()
    return haus, kat


def _felder(haus, kat, **mehr):
    return {'category_id': str(kat.id), 'property_id': str(haus.id),
            'amount': '80.00', 'invoice_number': 'S-1',
            'start_date': '2024-01-01', 'end_date': '2024-12-31',
            'document_pages': '', **mehr}


def _rechnung_mit_beleg_a(auth_client, haus, kat):
    antwort = auth_client.post('/api/invoices', content_type='multipart/form-data',
                               data=_felder(haus, kat, file=(io.BytesIO(PDF_A), 'beleg-a.pdf')))
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    rechnung = db.session.get(CostInvoice, antwort.get_json()['id'])
    assert rechnung.invoice_document_id
    return rechnung.id, rechnung.invoice_document_id


def _inhalt(app_ctx, dokument_id):
    dok = db.session.get(InvoiceDocument, dokument_id)
    with open(os.path.join(app_ctx.ablage.wurzel, dok.document_path), 'rb') as datei:
        return datei.read()


def test_mitgeschickte_datei_haengt_den_einzelbeleg_nicht_still_um(app_ctx, auth_client):
    """Schritte 4 bis 6 aus dem Befund: eine liegengebliebene Datei B kommt
    beim Speichern von R1 mit. R1 bleibt bei A; B wird danach regulär als
    R2 erfasst, und es gibt genau zwei Belege."""
    haus, kat = _stamm()
    r1, beleg_a = _rechnung_mit_beleg_a(auth_client, haus, kat)

    antwort = auth_client.put(f'/api/invoices/{r1}', content_type='multipart/form-data',
                              data=_felder(haus, kat, amount='90.00',
                                           file=(io.BytesIO(PDF_B), 'beleg-b.pdf')))

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    assert 'Beleg' in antwort.get_json()['error']
    db.session.expire_all()
    rechnung = db.session.get(CostInvoice, r1)
    assert rechnung.invoice_document_id == beleg_a
    assert rechnung.amount == 80
    assert InvoiceDocument.query.count() == 1
    assert _inhalt(app_ctx, beleg_a) == PDF_A

    r2 = auth_client.post('/api/invoices', content_type='multipart/form-data',
                          data=_felder(haus, kat, invoice_number='S-2',
                                       file=(io.BytesIO(PDF_B), 'beleg-b.pdf')))
    assert r2.status_code == 201, r2.get_data(as_text=True)
    db.session.expire_all()
    assert InvoiceDocument.query.count() == 2
    assert _inhalt(app_ctx, db.session.get(CostInvoice, r1).invoice_document_id) == PDF_A
    assert _inhalt(app_ctx, db.session.get(CostInvoice, r2.get_json()['id']).invoice_document_id) == PDF_B


def test_bewusst_ersetzen_geht_weiter(app_ctx, auth_client):
    haus, kat = _stamm()
    r1, beleg_a = _rechnung_mit_beleg_a(auth_client, haus, kat)

    antwort = auth_client.put(f'/api/invoices/{r1}', content_type='multipart/form-data',
                              data=_felder(haus, kat, beleg_ersetzen='true',
                                           file=(io.BytesIO(PDF_B), 'beleg-b.pdf')))

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    neu = db.session.get(CostInvoice, r1).invoice_document_id
    assert neu and neu != beleg_a
    assert _inhalt(app_ctx, neu) == PDF_B
    # Der alte Beleg wird nicht gelöscht, er bleibt als Datensatz erhalten.
    assert db.session.get(InvoiceDocument, beleg_a) is not None


def test_ohne_datei_bleibt_der_einzelbeleg(app_ctx, auth_client):
    """Der Dialog schickt bei einem Einzelbeleg keine Beleg-Kennung mit."""
    haus, kat = _stamm()
    r1, beleg_a = _rechnung_mit_beleg_a(auth_client, haus, kat)

    antwort = auth_client.put(f'/api/invoices/{r1}', content_type='multipart/form-data',
                              data=_felder(haus, kat, amount='95.00'))

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    rechnung = db.session.get(CostInvoice, r1)
    assert rechnung.invoice_document_id == beleg_a
    assert rechnung.amount == 95
    assert InvoiceDocument.query.count() == 1


def test_rechnung_ohne_beleg_bekommt_die_datei_ohne_rueckfrage(app_ctx, auth_client):
    haus, kat = _stamm()
    rechnung = f.invoice(haus, kat, 80, invoice_number='S-1')
    db.session.commit()

    antwort = auth_client.put(f'/api/invoices/{rechnung.id}', content_type='multipart/form-data',
                              data=_felder(haus, kat, file=(io.BytesIO(PDF_B), 'beleg-b.pdf')))

    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    db.session.expire_all()
    neu = db.session.get(CostInvoice, rechnung.id).invoice_document_id
    assert neu and _inhalt(app_ctx, neu) == PDF_B


def test_auch_ein_sammelbeleg_wird_nicht_still_ersetzt(app_ctx, auth_client):
    haus, kat = _stamm()
    sammel = InvoiceDocument(property_id=haus.id, filename='sammel.pdf',
                             document_path='sammel.pdf', is_collective=True)
    db.session.add(sammel)
    db.session.flush()
    rechnung = f.invoice(haus, kat, 80, invoice_number='S-1')
    rechnung.invoice_document_id = sammel.id
    db.session.commit()

    antwort = auth_client.put(f'/api/invoices/{rechnung.id}', content_type='multipart/form-data',
                              data=_felder(haus, kat, file=(io.BytesIO(PDF_B), 'beleg-b.pdf')))

    assert antwort.status_code == 400, antwort.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(CostInvoice, rechnung.id).invoice_document_id == sammel.id
    assert InvoiceDocument.query.count() == 1
