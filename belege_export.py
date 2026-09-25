"""Belege mit sprechenden Namen als ZIP (NK-131, E-5 → D-87).

Die Ablage kennt seit NK-131 nur neutrale Namen. Fuer Menschen -- den
Steuerberater, den Umzug auf einen anderen Rechner, den Blick in den Ordner
-- baut dieser Export den gewohnten Baum aus der Datenbank nach:

  <Immobilie>/
    Allgemein/
      Rechnungen/     Rechnung_<Kostenart>_<TT.MM.JJJJ>-<TT.MM.JJJJ>.<endung>
      Dokumente/      <Anzeigename des Sammelbelegs>
      Zaehlerstaende/ Zaehlerstand_<Kostenart>_<Zaehler>_<TT.MM.JJJJ>.<endung>
    Wohnungen/
      <Wohnung>/
        Zaehlerstaende/
        <Mieter>/
          Mietvertraege/  Mietvertrag.<endung>
          Abrechnungen/   Abrechnung_<Beginn>-<Ende>[_Korrektur<n>][_detailliert].pdf

Doppelte Namen bekommen einen Zaehler, fehlende Dateien stehen in
FEHLENDE_DATEIEN.txt. Die Namen tragen Personendaten -- das ZIP ist fuer den
Menschen, der es anfordert, nicht fuer die Ablage.
"""

from __future__ import annotations

import io
import re
import zipfile

import uploads

_VERBOTEN = re.compile(r'[\x00-\x1f/\\:*?"<>|]')


def _name(text) -> str:
    """Ein Namensstueck fuer das ZIP: lesbar, Umlaute bleiben, keine
    Trennzeichen, die aus dem Ordner fuehren."""
    sauber = _VERBOTEN.sub('_', str(text or '')).strip(' .')
    return sauber[:120] or 'unbenannt'


def _datum(tag) -> str:
    return tag.strftime('%d.%m.%Y') if tag else 'ohne Datum'


def _endung(pfad) -> str:
    return pfad.suffix.lstrip('.') or 'bin'


def eintraege(property_id: int | None = None):
    """(Name im ZIP, Pfad in der Datenbank) fuer alle Belege."""
    from models import (CostInvoice, InvoiceDocument, MeterReading, Property,
                        Tenant, TenantBillingReport)

    abfrage = Property.query.order_by(Property.name)
    if property_id is not None:
        abfrage = abfrage.filter(Property.id == property_id)
    for objekt in abfrage:
        haus = _name(objekt.name)
        for dok in InvoiceDocument.query.filter_by(property_id=objekt.id):
            if dok.document_path:
                yield f'{haus}/Allgemein/Dokumente/{_name(dok.filename)}', dok.document_path
        for rechnung in CostInvoice.query.filter_by(property_id=objekt.id):
            if rechnung.document_path and not rechnung.invoice_document_id:
                kat = _name(rechnung.category.name if rechnung.category else 'Kosten')
                stamm = (f'Rechnung_{kat}_{_datum(rechnung.start_date)}-'
                         f'{_datum(rechnung.end_date)}')
                yield f'{haus}/Allgemein/Rechnungen/{stamm}', rechnung.document_path
        for wohnung in objekt.apartments:
            ort = f'{haus}/Wohnungen/{_name(wohnung.name)}'
            for mieter in Tenant.query.filter_by(apartment_id=wohnung.id):
                person = f'{ort}/{_name(mieter.name)}'
                if mieter.contract_path:
                    yield f'{person}/Mietvertraege/Mietvertrag', mieter.contract_path
                for bericht in TenantBillingReport.query.filter_by(tenant_id=mieter.id):
                    stamm = (f'Abrechnung_{_datum(bericht.start_date)}-'
                             f'{_datum(bericht.end_date)}')
                    version = bericht.aktuelle_version
                    if version is not None and version.nummer > 1:
                        stamm += f'_Korrektur{version.nummer}'

                    if bericht.document_path:
                        yield f'{person}/Abrechnungen/{stamm}', bericht.document_path
                    if bericht.document_path_detailed:
                        yield (f'{person}/Abrechnungen/{stamm}_detailliert',
                               bericht.document_path_detailed)
        for lesung in (MeterReading.query.join(MeterReading.meter)
                       .filter_by(property_id=objekt.id)):
            if not lesung.document_path:
                continue
            zaehler = lesung.meter
            ort = (f'{haus}/Wohnungen/{_name(zaehler.apartment.name)}'
                   if zaehler.apartment else f'{haus}/Allgemein')
            kat = _name(zaehler.category.name if zaehler.category else 'Zaehler')
            stamm = (f'Zaehlerstand_{kat}_{_name(zaehler.meter_number)}_'
                     f'{_datum(lesung.reading_date)}')
            yield f'{ort}/Zaehlerstaende/{stamm}', lesung.document_path


def zip_erstellen(wurzel, property_id: int | None = None) -> tuple[bytes, dict]:
    """Das ZIP als Bytes und ein Bericht (Anzahl, fehlend)."""
    puffer = io.BytesIO()
    vergeben: set[str] = set()
    fehlend: list[str] = []
    anzahl = 0
    with zipfile.ZipFile(puffer, 'w', zipfile.ZIP_DEFLATED) as archiv:
        for stamm, gespeichert in eintraege(property_id):
            pfad = uploads.pfad_aufloesen(wurzel, gespeichert)
            if pfad is None:
                fehlend.append(stamm)
                continue
            name = stamm
            # Sammelbelege tragen ihre Endung schon im Anzeigenamen.
            if not re.search(r'\.[A-Za-z0-9]{1,5}$', name) or '/Dokumente/' not in name:
                name = f'{stamm}.{_endung(pfad)}'
            basis, punkt, endung = name.rpartition('.')
            zaehler = 2
            while name in vergeben:
                name = f'{basis}_{zaehler}.{endung}'
                zaehler += 1
            vergeben.add(name)
            archiv.write(pfad, name)
            anzahl += 1
        if fehlend:
            archiv.writestr('FEHLENDE_DATEIEN.txt',
                            'Diese Belege stehen in der Datenbank, die Datei '
                            'fehlt im Belegordner:\n'
                            + '\n'.join(f'- {n}' for n in fehlend) + '\n')
    return puffer.getvalue(), {'anzahl': anzahl, 'fehlend': len(fehlend)}
