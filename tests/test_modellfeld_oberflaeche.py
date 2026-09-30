"""NK-124 — der Wächtertest „Modellfeld ohne Oberfläche“.

Der Befund F-50 war eine Liste von Fachfeldern, die das Modell kennt, die
aber niemand auf dem Bildschirm setzen konnte: Zustellung, Eigenutzung,
Zwischenablesung, Vermieterdaten und mehr. Solche Listen veralten —
dieser Wächter macht die Prüfung laufend:

1. **Jede Spalte jedes Modells** ist entweder in der Oberfläche setzbar
   (``OBERFLAECHE``) oder steht mit Begründung auf der Ausnahmeliste
   (``AUSNAHMEN``). Eine neue Spalte im Modell ohne Oberfläche lässt den
   Test rot — die Lücke wird beim Bau bemerkt, nicht beim Mieter.
2. Jede Belagstelle existiert wirklich (Nadel in index.html oder
   app.js). Wer ein Eingabefeld umbenennt, muss den Belag mitziehen —
   sonst rot.
3. Jede Ausnahme ist ein echtes Feld. Umbenannte oder weggefallene
   Felder hinterlassen keine toten Ausnahmen.
4. Jedes Modell des Projekts kommt vor. Ein neues Modell ohne Eintrag
   lässt den Test rot.

Die Ausnahmen sind keine Freibriefe: jedes trägt seinen Grund. Eine
Ausnahme streichen heißt, das Feld in die Oberfläche bringen oder den
Grund neu schreiben — beides ist eine Entscheidung, kein Zufall.
"""

import inspect
from pathlib import Path

from nebenkostenfix import models

WURZEL = Path(__file__).resolve().parents[1]
INDEX = (WURZEL / 'static' / 'index.html').read_text(encoding='utf-8')
APP_JS = (WURZEL / 'static' / 'app.js').read_text(encoding='utf-8')

# Modelle, deren Felder der Vermieter nicht setzen kann, weil sie der
# Anwendung gehören (Schnappschüsse, Kopplungstabellen). User zählt seit
# NK-127 nicht mehr dazu: Konto und Passwort leben in der Oberfläche (E-1).
SYSTEMMODELLE = {
    'BillingReportCategory': 'Kopplung Abrechnung/Kostenart: setzt die Anwendung mit der Festsetzung.',
    'BillingReportVersion': 'Schnappschüsse: schreibt nur die Anwendung (R-DOC-02).',
}

# Spalte → Belagstelle. Der Belag ist eine Nadel, die im HTML oder im
# JavaScript vorkommen muss: eine Eingabe-ID, ein Routenpfad, ein
# eindeutiger Ausdruck. Sie muss so eng am Feld bleiben, dass ihr
# Verschwinden eine Lücke anzeigt.
OBERFLAECHE = {
    'Provider': {
        'name': 'new-provider-name',
    },
    'Property': {
        'name': 'id="prop-name"',
        'is_standalone': 'id="prop-standalone"',
        'abrechnungsjahr_beginn': 'id="prop-jahresbeginn"',
    },
    'Apartment': {
        'property_id': 'property_id: currentPropertyId',
        'name': 'id="apt-name"',
        'sqm': 'id="apt-sqm"',
        'nutzungsart': 'id="apt-nutzungsart"',
        'eigennutzung': 'id="apt-eigennutzung"',
        'selbstversorger': 'id="apt-selbstversorger"',
    },
    'Tenant': {
        'apartment_id': 'id="tenant-apartment"',
        'name': 'id="tenant-name"',
        'move_in_date': 'id="tenant-move-in"',
        'move_out_date': 'id="tenant-move-out"',
        'last_billed_until': 'id="tenant-last-billed"',
        'contract_path': 'id="tenant-contract-file"',
    },
    'Haushaltsgroesse': {
        'tenant_id': '/haushaltsgroessen',
        'gueltig_ab': 'gueltig_ab',
        'personenanzahl': 'personenanzahl',
    },
    'TenantCostProfile': {
        'tenant_id': '/profiles`',
        'category_id': 'profile-cat-',
        'billing_type': 'profile-cat-',
    },
    'CostInvoice': {
        'category_id': 'id="invoice-category"',
        'property_id': 'id="invoice-property"',
        'amount': 'id="invoice-amount"',
        'invoice_number': 'id="invoice-number"',
        'provider_id': 'id="invoice-provider"',
        'start_date': 'id="invoice-start"',
        'end_date': 'id="invoice-end"',
        'rechnungsdatum': 'id="invoice-rechnungsdatum"',
        'document_pages': 'id="invoice-pages"',
        'description': 'id="invoice-description"',
        'apartment_id': 'id="invoice-apartment"',
        'invoice_document_id': 'id="invoice-document-id"',
        'preis_ht': 'id="invoice-preis-ht"',
        'preis_nt': 'id="invoice-preis-nt"',
        'heizungsanlage_id': 'id="invoice-heizungsanlage"',
        'heizkostenart': 'id="invoice-heizkostenart"',
        'co2_kosten': 'id="invoice-co2-kosten"',
        'co2_emission_kg': 'id="invoice-co2-emission"',
    },
    'Heizungsanlage': {
        'property_id': 'fetchHeizungsanlagen',
        'name': 'id="heizung-name"',
        'versorgt': 'id="heizung-versorgt"',
        'verbrauchsanteil_prozent': 'id="heizung-anteil"',
        'sonderfall_70': 'id="heizung-sonderfall"',
        'warmwasser_weg': 'id="heizung-ww-weg"',
        'warmwasser_kwh': 'id="heizung-ww-kwh"',
        'warmwasser_volumen_m3': 'id="heizung-ww-volumen"',
        'warmwasser_temperatur_c': 'id="heizung-ww-temperatur"',
        'brennstoff_menge': 'id="heizung-brennstoff"',
        'heizwert_kwh': 'id="heizung-heizwert"',
    },
    'CostCategory': {},
    'InvoiceDocument': {
        'property_id': 'id="doc-property"',
        'description': 'id="doc-description"',
    },
    'Meter': {
        'category_id': 'id="meter-category"',
        'property_id': 'id="meter-property"',
        'apartment_id': 'id="meter-apartment"',
        'is_main_meter': 'is_main_meter: aptId',
        'meter_number': 'id="meter-number"',
        'has_dual_tariff': 'id="meter-dual-tariff"',
        'is_official': 'id="meter-is-official"',
    },
    'MeterReading': {
        'meter_id': 'id="reading-meter"',
        'reading_date': 'id="reading-date"',
        'value': 'id="reading-value"',
        'value_nt': 'id="reading-value-nt"',
        'is_official_invoice': 'id="reading-is-official"',
        'provider_id': 'id="reading-provider"',
        'ablesungsart': 'id="reading-ablesungsart"',
    },
    'AnschreibenVorlage': {
        'property_id': '/anschreiben`',
        'text': 'id="anschreiben-text"',
    },
    'Vermieterdaten': {
        'name': 'id="vermieter-name"',
        'iban': 'id="vermieter-iban"',
    },
    'TenantBillingReport': {
        'zugestellt_am': 'zustellung-datum-',
        'document_path': 'generateMissingPdf',
        'document_path_detailed': 'generateMissingPdf',
    },
    'Payment': {
        'tenant_id': 'id="payment-tenant"',
        'billing_report_id': 'id="payment-billing-report"',
        'amount': 'id="payment-amount"',
        'payment_date': 'id="payment-date"',
        'type': 'id="payment-type"',
    },
    'User': {
        'username': 'k.username',
        'is_active': 'k.is_active',
        'last_login_at': 'k.last_login_at',
    },
}

# Spalte → Grund, warum sie keine Oberfläche hat.
AUSNAHMEN = {
    'Apartment': {
        'id': 'Schlüssel.',
        'is_active': 'Es gibt kein Anlegen inaktiver Wohnungen; das Feld bleibt aus dem Altbestand.',
    },
    'Tenant': {
        'id': 'Schlüssel.',
        'gesperrt_bis': 'Setzt die Anwendung bei der Löschung (NK-153, D-89); '
                        'angezeigt in der Karte „Gesperrte Mietverhältnisse“.',
    },
    'CostInvoice': {
        'id': 'Schlüssel.',
        'document_path': 'Altbestand: Dateien laufen über die Belegtabelle (InvoiceDocument).',
    },
    'Heizungsanlage': {
        'id': 'Schlüssel.',
    },
    'InvoiceDocument': {
        'id': 'Schlüssel.',
        'filename': 'Kommt vom Upload, nicht vom Vermieter.',
        'document_path': 'Legt der Upload-Handler am NAS (belege/).',
        'upload_date': 'Setzt die Anwendung beim Upload.',
        'is_collective': 'Setzt die Anwendung je nach Anlage der Rechnung.',
    },
    'Meter': {
        'id': 'Schlüssel.',
        'heizungsanlage_id': 'id="meter-heizungsanlage"',
    },
    'MeterReading': {
        'id': 'Schlüssel.',
        'document_path': 'Kommt vom Foto-Upload; in der Oberfläche über das Dateifeld (reading-file).',
    },
    'TenantBillingReport': {
        'id': 'Schlüssel.',
        'tenant_id': 'Entsteht mit der Festsetzung, nicht von Hand.',
        'start_date': 'Entsteht mit der Festsetzung (R-DOC-02).',
        'end_date': 'Entsteht mit der Festsetzung (R-DOC-02).',
        'created_at': 'Setzt die Anwendung.',
        'frist_ende': 'Entsteht mit der Festsetzung (R-FRIST-02): AZ-Ende + 12 Monate.',
    },
    'AnschreibenVorlage': {
        'id': 'Schlüssel.',
        'aktualisiert_am': 'Setzt die Anwendung beim Speichern.',
    },
    'Vermieterdaten': {
        'id': 'Schlüssel.',
        'aktualisiert_am': 'Setzt die Anwendung beim Speichern.',
    },
    'Payment': {
        'id': 'Schlüssel.',
    },
    'Provider': {
        'id': 'Schlüssel.',
    },
    'User': {
        'id': 'Schlüssel.',
        'password_hash': 'Der Hash entsteht im Server (set_password); die Oberfläche fragt Passwörter ab und schreibt nie Hashes.',
        'created_at': 'Setzt die Anwendung beim Anlegen.',
    },
    'Property': {
        'id': 'Schlüssel.',
    },
    'Haushaltsgroesse': {
        'id': 'Schlüssel.',
    },
    'TenantCostProfile': {
        'id': 'Schlüssel.',
    },
    'CostCategory': {
        'id': 'Schlüssel.',
        'name': 'Kostenarten werden über die Kommandozeile gefüttert (flask kategorien); die Art wählt die Oberfläche aus.',
        'allocation_method': 'Bestandteil der Kostenarten-Pflege, nicht des Vermieteralltags.',
        'requires_meter': 'Bestandteil der Kostenarten-Pflege, nicht des Vermieteralltags.',
        'betrkv_nr': 'Bestandteil der Kostenarten-Pflege, nicht des Vermieteralltags.',
    },
}


def _modell_klassen():
    """Alle Modellklassen aus models.py, automatisch — keine Handliste."""
    gefunden = {}
    for name, objekt in vars(models).items():
        if inspect.isclass(objekt) and issubclass(objekt, models.db.Model) \
                and objekt is not models.db.Model:
            gefunden[name] = objekt
    return gefunden


def test_jedes_modellfeld_ist_abgedeckt():
    """Keine Spalte bleibt weder Oberfläche noch Ausnahme (F-50)."""
    luecken = []
    for name, klasse in sorted(_modell_klassen().items()):
        if name in SYSTEMMODELLE:
            continue  # Systemtabellen: Modelle der Anwendung, nicht des Vermieters
        for spalte in klasse.__table__.columns.keys():
            if spalte in OBERFLAECHE.get(name, {}):
                continue
            if spalte in AUSNAHMEN.get(name, {}):
                continue
            luecken.append(f'{name}.{spalte}')
    assert luecken == [], (
        'Diese Modellfelder kann niemand in der Oberfläche setzen (F-50): '
        + '; '.join(luecken)
        + ' — entweder Oberfläche nachziehen oder hier mit Grund ausschließen.')


def test_jedes_modell_ist_betrachtet():
    """Jedes Modell des Projekts taucht in einer der Listen auf."""
    unbekannt = []
    for name in _modell_klassen():
        if name in SYSTEMMODELLE:
            continue
        if name not in OBERFLAECHE:
            unbekannt.append(name)
    assert unbekannt == [], (
        'Neue Modellklassen ohne Wächter-Eintrag: ' + ', '.join(unbekannt))


def test_jeder_belag_existiert():
    """Jede Nadel findet sich wirklich im HTML oder im JavaScript."""
    tote_belaege = []
    for name, spalten in sorted(OBERFLAECHE.items()):
        for spalte, belag in sorted(spalten.items()):
            if belag not in INDEX and belag not in APP_JS:
                tote_belaege.append(f'{name}.{spalte}: "{belag}"')
    assert tote_belaege == [], (
        'Die Oberfläche ist unter den Nadeln weggezogen: '
        + '; '.join(tote_belaege))


def test_keine_tote_ausnahme():
    """Jede Ausnahme ist ein echtes Feld; Gründe stehen daneben."""
    tote = []
    for name, spalten in sorted(AUSNAHMEN.items()):
        klasse = _modell_klassen().get(name)
        if klasse is None:
            tote.append(f'{name}: Modell fehlt')
            continue
        echt = set(klasse.__table__.columns.keys())
        for spalte in spalten:
            if spalte not in echt:
                tote.append(f'{name}.{spalte}: Feld fehlt')
    assert tote == [], '; '.join(tote)
