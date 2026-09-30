"""Die Weboberflaeche: jede Adresse der Anwendung an einer Stelle (NK-033).

Diese Datei ist mit Abstand die groesste im Projekt, und sie waechst weiter.
Wer etwas sucht, sucht eine Adresse -- "wo wird eine Rechnung geloescht?" --
und findet sie sonst nur mit ``grep``. Die Karte unten beantwortet das in einem
Blick, nach Bereichen geordnet statt nach Zeilennummer.

Sie veraltet nicht still: ``tests/test_routenkarte.py`` liest genau diesen
Docstring, stellt ihn ``app.url_map`` gegenueber und schlaegt bei jeder
Abweichung fehl. Eine neue Route ohne Zeile hier ist ein roter Test, kein
Schoenheitsfehler. Wer eine hinzufuegt, traegt sie ein; das ist der Preis
dafuer, dass man der Karte glauben darf.

Gelesen wird jede Zeile als ``METHODEN  PFAD  -> endpunkt``. ``HEAD`` und
``OPTIONS`` fehlen ueberall, die vergibt Flask von selbst.

Die Zugangssperre liegt nicht hier, sondern in ``auth.py``: ein
``before_request`` sperrt **jede** Route, und nur ``PUBLIC_ENDPOINTS``
(``health_check``, ``login``, ``einrichtung``) kommen ohne Sitzung durch.
Neue Routen sind damit von der ersten Zeile an geschuetzt -- man muss nichts
dazutun, sondern etwas weglassen, um ein Leck zu bauen.


Anmeldung, Ersteinrichtung und Konto -- alles in auth.py, nicht hier
--------------------------------------------------------------------
  GET,POST    /login                                       -> login
  GET,POST    /einrichtung                                 -> einrichtung
  GET,POST    /logout                                      -> logout
  GET         /api/auth/me                                 -> auth_me
  GET         /api/konten                                  -> konten_auflisten
  POST        /api/konten                                  -> konto_anlegen
  PUT         /api/konto/passwort                          -> konto_passwort_aendern
  GET,POST    /huelle/passwort                             -> huelle_passwort

Oberflaeche und Betrieb
-----------------------
  GET         /                                            -> index
  GET         /static/<path:filename>                      -> static
  GET         /api/health                                  -> health_check
  GET         /api/dateien/<art>/<int:kennung>             -> datei_ausliefern
  GET         /api/belege/export                           -> belege_exportieren
  GET         /api/haftung                                 -> haftung_anzeigen
  POST        /api/haftung                                 -> haftung_bestaetigen
  GET         /api/ueber                                   -> ueber_anzeigen
  GET         /api/drittlizenzen                           -> drittlizenzen_anzeigen
  GET         /api/aktualisierung/einstellung              -> update_einstellung_anzeigen
  PUT         /api/aktualisierung/einstellung              -> update_einstellung_setzen
  GET         /api/aktualisierung/automatisch              -> aktualisierung_automatisch
  GET         /api/aktualisierung                          -> aktualisierung_suchen
  POST        /api/aktualisierung/installieren             -> aktualisierung_installieren
  GET         /api/vermieter                               -> get_vermieterdaten
  PUT         /api/vermieter                               -> setze_vermieterdaten
  GET         /api/vermieter/logo                          -> vermieter_logo_zeigen
  POST        /api/vermieter/logo                          -> vermieter_logo_hochladen
  DELETE      /api/vermieter/logo                          -> vermieter_logo_loeschen
  GET         /api/properties/<int:property_id>/heizungsanlagen -> get_heizungsanlagen
  POST        /api/properties/<int:property_id>/heizungsanlagen -> create_heizungsanlage
  PUT         /api/heizungsanlagen/<int:id>                -> update_heizungsanlage
  DELETE      /api/heizungsanlagen/<int:id>                -> delete_heizungsanlage
  GET,POST    /api/export                                  -> export_data
  POST        /api/debug/reset_db                          -> reset_db

  ``get_vermieterdaten`` und ``setze_vermieterdaten`` tragen den Ausweis des Vermieters:
  Name und IBAN für Deckblatt und GiroCode (NK-124). Ohne eigenen Eintrag lesen
  beide aus den Umgebungsvariablen des Bestands; die PUT schreibt in die
  Tabelle, was die Oberflaeche eingibt.

  ``reset_db`` leert die Datenbank und das Belegverzeichnis. Sie steht seit
  NK-040 nicht mehr hier, sondern in ``debug_routen.py``, und diese Datei wird
  nicht ins Auslieferungsabbild kopiert: dort gibt es die Adresse nicht. In der
  Entwicklung gibt es sie, darum steht sie in dieser Karte.

Sicherung und Wiederherstellung -- alles in backup.py, nicht hier
-----------------------------------------------------------------
  GET         /api/backup/status                           -> backup_status
  POST        /api/backup/erstellen                        -> backup_erstellen
  GET         /api/backup/liste                            -> backup_liste
  POST        /api/backup/einspielen                       -> backup_einspielen

  Die Routen liegen in backup.py neben dem CLI aus NK-025. ``status`` traegt
  die Erinnerung (letzte Sicherung, rote Stufe wenn es keine gibt, gelbe ab
  30 Tagen), ``erstellen`` schreibt das Archiv zum gewaehlten Ziel -- verboten
  ist nur der Belegordner selbst, weil das Einspielen ihn leert. Die
  Merkdatei ``backup_stand.json`` im Datenordner haelt das zuletzt gewaehlte
  Ziel; sie braucht keine Wanderung.

Import aus Excel/CSV (NK-161) -- alles in tabellenimport.py
------------------------------------------------------------
  GET         /api/import/arten                            -> import_arten
  GET         /api/import/vorlage/<art>.<endung>           -> import_vorlage
  POST        /api/import/<art>/lesen                      -> import_lesen
  POST        /api/import/<art>/pruefen                    -> import_pruefen
  POST        /api/import/<art>/uebernehmen                -> import_uebernehmen
  POST        /api/import/<art>/tabelle                    -> import_tabelle

  Vorlage, Lesen, Zuordnen, Probelauf, Übernahme in einer Transaktion (nur
  ohne Fehler). ``tabelle`` ist die Tabellen-Erfassung der Rechnungen ohne
  Datei, über denselben Prüfweg.

Jahresabrechnungs-Assistent (NK-160) -- jahresabrechnung.py
------------------------------------------------------------
  GET         /api/jahresabrechnung                        -> jahresabrechnung_stand

  Nur der Stand eines Jahres (Kostenarten mit Vorjahr, Ablesungen zum
  Stichtag und bei Mieterwechseln, Mieter mit Zeitraum, Frist). Gerechnet
  und festgesetzt wird über /api/billing/generate und /api/billing/finalize.

Hilfe (NK-158) -- hilfe.py
--------------------------
  GET         /api/hilfe/kurzanleitung.pdf                 -> hilfe_kurzanleitung

  Die Kurzanleitung zum Ausdrucken (zehn Seiten, große Schrift). Der
  Hilfebereich selbst ist statisch (index.html, static/hilfe-begriffe.json).

Umzugspaket (NK-164) -- alles in umzug.py
------------------------------------------
  GET,POST    /api/umzug/export                            -> umzug_export
  POST        /api/umzug/hochladen                         -> umzug_hochladen_beginnen
  GET         /api/umzug/hochladen/<kennung>               -> umzug_hochladen_stand
  PUT         /api/umzug/hochladen/<kennung>               -> umzug_hochladen_stueck
  GET         /api/umzug/importordner                      -> umzug_importordner
  POST        /api/umzug/pruefen                           -> umzug_pruefen
  POST        /api/umzug/uebernehmen                       -> umzug_uebernehmen

  Ein .nkfix ist eine Sicherung (backup.py) und zugleich das Paket für den
  Weg auf einen anderen Rechner. Hochladen, Prüfen und Übernehmen sind vor
  der Einrichtung offen (frische Installation, im Server-Betrieb mit dem
  Einmal-Code), danach nur angemeldet.

Stammdaten -- Immobilie, Wohnung, Mieter, Anbieter, Kostenart
--------------------------------------------------------------
  GET         /api/properties                              -> get_properties
  POST        /api/properties                              -> create_property
  DELETE,PUT  /api/properties/<int:id>                     -> update_delete_property
  GET         /api/properties/<int:property_id>/apartments -> get_apartments
  GET         /api/apartments                              -> get_all_apartments
  POST        /api/apartments                              -> create_apartment
  DELETE,PUT  /api/apartments/<int:id>                     -> update_delete_apartment
  GET         /api/tenants                                 -> get_tenants
  POST        /api/tenants                                 -> create_tenant
  DELETE,PUT  /api/tenants/<int:id>                        -> update_delete_tenant
  GET         /api/tenants/<int:id>/contract               -> get_tenant_contract
  GET         /api/tenants/<int:tenant_id>/export          -> export_tenant
  GET         /api/tenants/<int:tenant_id>/profiles        -> get_tenant_profiles
  POST        /api/tenants/<int:tenant_id>/profiles        -> save_tenant_profiles
  GET         /api/tenants/<int:tenant_id>/haushaltsgroessen -> get_haushaltsgroessen
  POST        /api/tenants/<int:tenant_id>/haushaltsgroessen -> save_haushaltsgroesse
  DELETE      /api/haushaltsgroessen/<int:id>              -> delete_haushaltsgroesse
  GET         /api/providers                               -> get_providers
  POST        /api/providers                               -> create_provider
  DELETE      /api/providers/<int:id>                      -> delete_provider
  GET         /api/categories                              -> get_categories

  Vier Wege tragen ``DELETE`` und ``PUT`` auf derselben Adresse
  (``update_delete_*``). Das ist gewachsen, nicht entworfen: die Funktion
  verzweigt innen auf ``request.method``.

Zaehler und Staende
-------------------
  GET         /api/meters                                  -> get_meters
  POST        /api/meters                                  -> create_meter
  DELETE      /api/meters/<int:id>                         -> delete_meter
  GET         /api/readings                                -> get_readings
  POST        /api/readings                                -> create_reading
  PUT         /api/readings/<int:id>                       -> update_reading
  DELETE      /api/readings/<int:id>                       -> delete_reading
  POST        /api/readings/check_plausibility             -> check_plausibility

  ``check_plausibility`` speichert nichts. Sie sagt vor dem Speichern, ob ein
  Stand zum Vorgaenger passt -- ein Zaehler, der rueckwaerts laeuft, ist meist
  ein Zahlendreher und kein Defekt.

  ``export_tenant`` (NK-078) stellt die Auskunft des Mietverhaeltnisses als
  ZIP: JSON-Auszug der Zeilen plus die Dateien (Mietvertrag, Abrechnungen,
  Lesenachweise). Die Loeschung ueber ``update_delete_tenant`` traegt
  denselben Umfang: sie nimmt die Dateien mit und berichtet, welche weg sind
  und welche im Belegordner schon fehlten. Lesungen bleiben bewusst (D-82).

Rechnungen und Belege
---------------------
  GET         /api/invoices                                -> get_invoices
  POST        /api/invoices                                -> create_invoice
  GET         /api/invoices/zeitleiste                     -> zeitleiste_route
  PUT         /api/invoices/<int:id>                       -> update_invoice
  DELETE      /api/invoices/<int:id>                       -> delete_invoice
  GET         /api/invoice_documents                       -> get_invoice_documents
  POST        /api/invoice_documents                       -> create_invoice_document
  PUT         /api/invoice_documents/<int:doc_id>          -> update_invoice_document
  DELETE      /api/invoice_documents/<int:doc_id>          -> delete_invoice_document

  Zwei verschiedene Dinge mit aehnlichem Namen: ``invoices`` sind die Betraege,
  mit denen gerechnet wird, ``invoice_documents`` die PDFs und Fotos dazu auf
  dem NAS.

Abrechnung -- der Weg von den Rechnungen zum Schreiben an den Mieter
---------------------------------------------------------------------
  GET         /api/billing/suggestions                     -> billing_suggestions
  POST        /api/billing/preflight                       -> billing_preflight
  POST        /api/billing/generate                        -> generate_bill
  POST        /api/billing/finalize                        -> finalize_bill
  GET         /api/billing/reports                         -> get_all_billing_reports
  GET         /api/billing/reports/<int:id>/details        -> get_billing_report_details
  GET         /api/billing/reports/<int:id>/belege         -> get_billing_report_belege
  GET         /api/billing/reports/<int:id>/positionen.csv -> get_billing_report_csv
  GET         /api/properties/<int:property_id>/anschreiben -> get_anschreiben_vorlage
  PUT         /api/properties/<int:property_id>/anschreiben -> setze_anschreiben_vorlage
  DELETE      /api/properties/<int:property_id>/anschreiben -> loesche_anschreiben_vorlage
  POST        /api/billing/reports/<int:id>/korrektur      -> korrigiere_billing_report
  GET         /api/billing/reports/<int:id>/download       -> download_billing_report
  POST        /api/billing/reports/<int:id>/zustellung     -> zustellung_melden
  DELETE      /api/billing/reports/<int:id>                -> delete_billing_report
  GET         /api/billing/interpolation-audit             -> get_interpolation_audit
  GET         /api/tenants/<int:id>/billing_reports        -> get_tenant_billing_reports

  Die Reihenfolge ist die des Bildschirms: ``suggestions`` schlaegt Zeitraeume
  vor, ``preflight`` warnt vor fehlenden Daten, ``generate`` rechnet (siehe
  ``billing_engine.py``), ``finalize`` schreibt das PDF fest und legt es ab.
  Erst ``finalize`` erzeugt einen Bericht, den es danach zu holen und zu
  loeschen gibt.

Zahlungen -- Vorauszahlungen des Mieters
----------------------------------------
  GET         /api/payments                                -> get_payments
  POST        /api/payments                                -> add_payment
  DELETE      /api/payments/bulk                           -> bulk_delete_payments
  DELETE      /api/payments/<int:id>                       -> delete_payment

  ``/bulk`` steht bewusst vor ``/<int:id>`` in dieser Liste, obwohl die
  Reihenfolge fuer Flask egal ist: ``bulk`` ist kein ``int`` und kann die
  Regel darunter nicht verdecken.

Auswertung
----------
  GET         /api/analytics/building/<int:property_id>    -> analytics_building
  GET         /api/analytics/apartment/<int:apartment_id>  -> analytics_apartment
  GET         /api/analytics/data-quality/<int:property_id> -> analytics_data_quality
  POST        /api/analytics/beispiel-immobilie            -> beispielimmobilie_route
  DELETE      /api/analytics/beispiel-immobilie            -> beispielimmobilie_entfernen

  ``data-quality`` bewertet nicht Kosten, sondern die Daten selbst: fehlende
  Staende, Luecken in den Mietverhaeltnissen, Rechnungen ohne Beleg. Die
  Beispielimmobilie (NK-141) legt ein kleines Haus an, in dem alle Zustaende
  und eine Warnung sichtbar sind -- fuer den ersten Blick.
"""

import os
import re
import io
from decimal import Decimal
from pathlib import Path
from nebenkostenfix import zeit
from flask import Flask, jsonify, make_response, request, send_file
import click
import json
import tempfile
from nebenkostenfix import uploads
from nebenkostenfix import verschluesselung
from flask.json.provider import DefaultJSONProvider
from dotenv import load_dotenv
from nebenkostenfix.geld import NULL, runde
from nebenkostenfix import betrkv
from nebenkostenfix import mieter_daten
from nebenkostenfix import beispielimmobilie
from nebenkostenfix import zeitleiste
from nebenkostenfix.zeitraum import ein_jahr_nach, grenze, letzter_tag, tage
from nebenkostenfix.frist import frist_status, einwendungsfrist, zustellwarnung
from nebenkostenfix.heizung import (
    ABLESUNG, ABLESUNGSARTEN, HEIZUNG, VERBUNDEN, WARMWASSER,
    WW_ZAEHLER, KOSTENARTEN as HEIZKOSTENARTEN,
    HeizungsFehler, pruefe_anteil, pruefe_kostenart, pruefe_versorgungsart,
    pruefe_warmwasserweg,
)
from nebenkostenfix.models import db, User, Property, Apartment, Tenant, Haushaltsgroesse, CostCategory, CostInvoice, Meter, MeterReading, TenantCostProfile, InvoiceDocument, Provider, TenantBillingReport, BillingReportCategory, BillingReportVersion, AnschreibenVorlage, Vermieterdaten, Heizungsanlage
from nebenkostenfix.girocode_generator import iban_pruefen, iban_saeubern
from nebenkostenfix.abrechnung_version import schnappschuss, json_sicher, SOFTWARE_VERSION, REGEL_VERSION
from nebenkostenfix.anschreiben import VORGABE, PLATZHALTER, text_fuer
from nebenkostenfix.ablage import Ablage
from nebenkostenfix.auth import init_auth
from nebenkostenfix.backup import init_backup
from nebenkostenfix.umzug import init_umzug
from nebenkostenfix.tabellenimport import init_tabellenimport
from nebenkostenfix.hilfe import init_hilfe
from nebenkostenfix.jahresabrechnung import init_jahresabrechnung
from nebenkostenfix.kategorien import init_kategorien
from flask_migrate import Migrate
from contextlib import contextmanager
from nebenkostenfix.validation import Eingabe, EingabeFehler, init_validation, kostenprofile
from nebenkostenfix.nutzung import VORGABE as NUTZUNG_VORGABE
from nebenkostenfix.fehler import init_fehlerbehandlung, protokoll
from datetime import datetime, timedelta, date

# Load environment variables from .env file
load_dotenv()

UPLOAD_VORGABE_MB = 32


def max_upload_bytes(rohwert=None):
    """Wie gross ein Anfragerumpf hoechstens sein darf, in Bytes (NK-029).

    Liest MAX_UPLOAD_MB. Ein unbrauchbarer Wert (leer, Text, 0, negativ)
    faellt auf die Vorgabe zurueck statt den Start abzubrechen: ein Tippfehler
    in der .env soll keine laufende Instanz lahmlegen, und ein zu grosszuegiges
    Limit ist harmloser als gar keine Anwendung.
    """
    if rohwert is None:
        rohwert = os.environ.get('MAX_UPLOAD_MB', '')
    try:
        megabyte = int(str(rohwert).strip())
    except (TypeError, ValueError):
        megabyte = UPLOAD_VORGABE_MB
    if megabyte < 1:
        megabyte = UPLOAD_VORGABE_MB
    return megabyte * 1024 * 1024


class GeldJSON(DefaultJSONProvider):
    """Decimal geht als Zahl ueber die JSON-Grenze, nicht als Text (NK-036).

    Flask gibt ein Decimal von sich aus als String aus ("12.34" statt 12.34).
    Das waere hier still gefaehrlich: static/app.js rechnet an 37 Stellen mit
    diesen Feldern, und in JavaScript ergibt "12.34" + "5.00" nicht 17.34,
    sondern "12.345.00". Kein Test wuerde das bemerken, es gibt keine
    JS-Tests -- der Vermieter saehe einfach falsche Zahlen im Dashboard.

    Die Umwandlung verliert nichts: jeder Betrag, der hier vorbeikommt, ist
    vorher auf Cent gerundet worden (R-NUM-01), und ein double traegt
    zwei Nachkommastellen bis weit jenseits jeder Hausverwaltung exakt.
    Gerechnet wird trotzdem nirgends in float -- nur angezeigt.
    """

    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


app = Flask(__name__)
app.json = GeldJSON(app)

# Datenordner und Datenbank (NK-132, D-90): ein Ordner DATA_DIR fuer
# Datenbank, Belege, Sicherungen und Schluessel. Ohne DATABASE_URL liegt die
# SQLite-Datei darin; die .env ist dafuer nicht mehr noetig.
from nebenkostenfix import datenordner
from nebenkostenfix import vermieter_logo
from nebenkostenfix import aktualisierung
from nebenkostenfix import einstellungen
from nebenkostenfix import haftung
from nebenkostenfix import marke
from nebenkostenfix import drittlizenzen
import platform
from nebenkostenfix.aktualisierung import AktualisierungsFehler
if not (os.environ.get('DATABASE_URL') or '').strip() or \
        (os.environ.get('DATA_DIR') or '').strip():
    datenordner.anlegen()
app.config['SQLALCHEMY_DATABASE_URI'] = datenordner.datenbank_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Groessenlimit fuer Uploads (NK-029). Ohne den Wert nimmt Flask jeden Rumpf
# entgegen; acht Routen lesen Dateien, ein 800-MB-Video wuerde durchlaufen und
# im Belegordner landen. Werkzeug bricht die Anfrage schon an der
# Content-Length ab, der Rumpf wird also gar nicht erst gelesen.
app.config['MAX_CONTENT_LENGTH'] = max_upload_bytes()

# Initialize DB
db.init_app(app)


# SQLite im WAL-Modus (NK-076, E-3 → D-91): ein Prozess mit mehreren Threads
# (gunicorn --workers 1 --threads, unter Windows waitress) liest waehrend
# eines Schreibvorgangs weiter, statt "database is locked" zu melden. Der Modus
# steht danach in der Datei. SQLITE_JOURNAL=delete schaltet ihn ab -- noetig
# nur, wenn die Datei auf einer Netzfreigabe liegt, die mehrere Rechner
# zugleich oeffnen (WAL braucht gemeinsamen Speicher auf einem Rechner).
def _sqlite_einstellen(verbindung, _eintrag):
    import sqlite3

    if not isinstance(verbindung, sqlite3.Connection):
        return
    modus = (os.environ.get('SQLITE_JOURNAL') or 'wal').strip().lower()
    if modus not in ('wal', 'delete'):
        modus = 'wal'
    zeiger = verbindung.cursor()
    try:
        zeiger.execute('PRAGMA busy_timeout=10000')
        zeiger.execute(f'PRAGMA journal_mode={modus}')
        zeiger.execute('PRAGMA synchronous=NORMAL' if modus == 'wal'
                       else 'PRAGMA synchronous=FULL')
    finally:
        zeiger.close()


from sqlalchemy import event as _sa_event  # noqa: E402
from sqlalchemy.engine import Engine as _SaEngine  # noqa: E402

_sa_event.listen(_SaEngine, 'connect', _sqlite_einstellen)

# Schemawanderungen (NK-024). Bis hierher stand am Ende dieser Datei ein
# blindes db.create_all(). Das legt fehlende Tabellen an und aendert nie eine
# bestehende Spalte: die erste Aktualisierung beim Betreiber haette seine
# Instanz zerlegt, ohne dass jemand es merkt.
#
# Absoluter Pfad statt 'migrations': Flask-Migrate loest den Namen gegen das
# Arbeitsverzeichnis auf, nicht gegen die Anwendung. Im Container stimmt beides
# zufaellig ueberein, bei einem Start aus einem anderen Verzeichnis nicht mehr.
#
# render_as_batch ist fuer SQLite Pflicht. SQLite kann kein ALTER TABLE zum
# Aendern oder Loeschen einer Spalte. Alembic baut dafuer im Batch-Modus eine
# neue Tabelle, kopiert die Zeilen und benennt um. Ohne das Flag erzeugt die
# naechste Wanderung, die eine Spalte anfasst, Code, der beim Betreiber
# abbricht, und gemerkt wird das erst dort.
WANDERUNGSVERZEICHNIS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'migrations'
)

migrate = Migrate(app, db, directory=WANDERUNGSVERZEICHNIS, render_as_batch=True)

# Anmeldung und Zugangssperre (NK-019). Setzt SECRET_KEY fail-closed, haengt
# das deny-by-default before_request ein und registriert /login, /logout und
# das flask-users-CLI. Muss vor schema_aktualisieren() laufen, damit die
# Fehlermeldung zu einem fehlenden SECRET_KEY vor der DB-Arbeit kommt.
init_auth(app)

# Sichern und Zurueckholen (NK-025, Oberflaeche NK-077). Registriert das
# flask-backup-CLI und die vier Sicherungsrouten; beim Start passiert
# dadurch nichts.
init_backup(app)
# NK-164: Umzugspaket (.nkfix) exportieren und übernehmen.
init_umzug(app)
# NK-161: Import aus Excel/CSV und Tabellen-Erfassung.
init_tabellenimport(app)
# NK-158: Kurzanleitung als PDF.
init_hilfe(app)
# NK-160: Stand eines Abrechnungsjahres für den Assistenten.
init_jahresabrechnung(app)

# Kostenarten aufraeumen (NK-095). Wie init_backup nur ein CLI, beim Start
# passiert nichts. Muss vor schema_aktualisieren() stehen, damit der Befehl
# ueberhaupt registriert ist, wenn die Wanderung gleich darunter an Dubletten
# abbricht -- registriert heisst hier allerdings noch nicht erreichbar, siehe
# F-16 im Kopf von kategorien.py. Dafuer gibt es scripts/kostenarten.py.
init_kategorien(app)

# Eingabepruefung (NK-028). Registriert den errorhandler fuer EingabeFehler,
# damit ein raise in irgendeiner Route zu einer 400 mit deutschem Text wird,
# statt zu einer 500 mit Stapelabzug.
init_validation(app)

# Fehlerbehandlung und Protokoll (NK-030). Muss nach init_validation laufen,
# damit klar ist, was hier als letztes Netz haengt und was vorher schon
# abgefangen wird: EingabeFehler ist naeher an seiner Ausnahme als das
# Exception-Netz und gewinnt deshalb, egal in welcher Reihenfolge registriert
# wurde. Ab hier gibt es keine Antwort mehr ohne Text und keine abgebrochene
# Transaktion ohne rollback.
init_fehlerbehandlung(app)


@app.errorhandler(413)
def _upload_zu_gross(fehler):
    """Deutscher 413 statt der Flask-Standardseite (NK-029).

    Werkzeug wirft den Fehler auch, wenn ein einzelnes Formularfeld ueber
    max_form_memory_size (500 KB) liegt, nicht nur bei Dateien. Der Text nennt
    deshalb den Upload, nicht die Datei.
    """
    grenze_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({
        'error': f'Der Upload ist zu groß. Erlaubt sind höchstens {grenze_mb} MB.',
        'feld': None,
    }), 413


# Die Ablage im Datenordner (NK-132). ``nas_handler`` ist der alte Name und
# bleibt eine Version lang als Alias (mieter_daten, debug_routen, Tests).
ablage = Ablage()
nas_handler = ablage

def seed_database():
    """Legt den Katalog aus § 2 BetrKV an (NK-044, R-KAT-01; NK-117: 18 Eintraege).

    Bis hierher waren es acht frei benannte. Es fehlten Aufzug, Muell,
    Hauswart, Beleuchtung, Schornstein, Gartenpflege und Waeschepflege --
    lauter Posten, die in jeder zweiten Abrechnung stehen und die der
    Vermieter bisher von Hand nachtragen musste. Der Katalog steht in
    betrkv.py und nirgends sonst.

    Abgeglichen wird ueber die **Nummer**, nicht ueber den Namen. Eine
    Datenbank aus der Zeit davor traegt ihre Nummern seit der Wanderung
    c9a5d3f81e47: „Gebaeudeversicherung" ist dort Nr. 13. Ein Abgleich nach
    Namen wuerde daneben „Sach- und Haftpflichtversicherung" ins Haus holen --
    dieselbe Nummer, zwei Eintraege, und genau die Dublette, die NK-095
    beseitigt hat. Der gewachsene Name des Betreibers bleibt deshalb stehen;
    die amtliche Bezeichnung steht ohnehin in betrkv.bezeichnung().

    Der Name wird zusaetzlich geprueft, weil er eindeutig sein muss (NK-095).
    Zwei Eintraege mit derselben Nummer sind moeglich -- der alte Seed hatte
    „Abwasser" und „Niederschlagswasser", beide Nr. 3 --, zwei mit demselben
    Namen nicht.

    Seit NK-117 (D-72) traegt auch der Katalog zwei Eintraege unter Nr. 3.
    Der Schluessel ist darum die Nummer **und** ob die Kostenart das
    Niederschlagswasser meint: „Abwasser" deckt die Entwaesserung ab,
    „Regenwasser" das Niederschlagswasser. Eine Datenbank, die nur das
    Abwasser kennt, bekommt das Niederschlagswasser dazu -- eine, die beide
    hat, keine Dublette.
    """
    def schluessel(nr, name):
        return nr, betrkv.ist_niederschlag(name)

    vorhandene = {
        schluessel(nr, name) for (nr, name) in
        db.session.query(CostCategory.betrkv_nr, CostCategory.name).all()}
    vorhandene_namen = {
        name for (name,) in db.session.query(CostCategory.name).all()}

    for eintrag in betrkv.KATALOG:
        eigener = schluessel(eintrag['nr'], eintrag['name'])
        if eigener in vorhandene or eintrag['name'] in vorhandene_namen:
            continue
        db.session.add(CostCategory(
            name=eintrag['name'],
            allocation_method=eintrag['verteilung'],
            requires_meter=eintrag['zaehler'],
            betrkv_nr=eintrag['nr'],
        ))
        vorhandene.add(eigener)
        vorhandene_namen.add(eintrag['name'])
    db.session.commit()

# Basisrevision aus NK-024. Sie beschreibt models.py so, wie es beim Einfuehren
# von Alembic aussah. Eine bestehende Datenbank wird auf genau diese Revision
# gestempelt, nicht auf head: sie ist auf dem Stand von damals, und alles, was
# spaeter dazukommt, muss sie noch durchlaufen.
BASISREVISION = '63738d5329b4'


def schema_aktualisieren():
    """Bringt die Datenbank auf den neuesten Stand, ohne Daten anzutasten.

    Drei Faelle, und alle drei landen hier:

    - Leere Datenbank. Keine Tabellen, kein Stempel. upgrade() faehrt die
      Basisrevision und alles danach, legt also alles an.
    - Bestehende Datenbank aus der Zeit vor Alembic. Tabellen da, aber keine
      alembic_version. Die wird auf die Basisrevision gestempelt und sonst
      nicht angefasst. Das ist Kriterium 2 der Karte: die Instanz eines
      Betreibers wird bei einer Aktualisierung nicht neu aufgebaut.
    - Bereits gestempelte Datenbank. Nur die ausstehenden Wanderungen.

    Der Aufrufer haelt die Startsperre, siehe _startsperre().
    """
    from alembic.migration import MigrationContext
    from flask_migrate import stamp, upgrade
    from sqlalchemy import inspect

    if not os.path.isdir(WANDERUNGSVERZEICHNIS):
        # Ohne das Verzeichnis wirft Alembic "Path doesn't exist: migrations",
        # und wer das liest, sucht an der falschen Stelle. Es fehlt nicht die
        # Konfiguration, es fehlt ein Stueck des Pakets.
        raise RuntimeError(
            "Das Verzeichnis migrations/ fehlt. Es gehört ins Abbild und ins "
            "Repository (NK-024). Ohne es kann die Datenbank weder angelegt "
            "noch aktualisiert werden."
        )

    tabellen = set(inspect(db.engine).get_table_names())
    with db.engine.connect() as verbindung:
        gestempelt = MigrationContext.configure(verbindung).get_current_revision()

    if tabellen and gestempelt is None:
        stamp(revision=BASISREVISION)
        gestempelt = BASISREVISION
    if tabellen and gestempelt != _kopfrevision():
        vor_der_wanderung_sichern(gestempelt)
    upgrade()


def _kopfrevision():
    """Die neueste Revision, die diese Fassung mitbringt."""
    from alembic.script import ScriptDirectory

    konfiguration = app.extensions['migrate'].migrate.get_config()
    return ScriptDirectory.from_config(konfiguration).get_current_head()


def vor_der_wanderung_sichern(stand):
    """Automatische Sicherung vor jeder Wanderung (NK-081).

    Ein Update bringt neue Revisionen mit; beim ersten Start danach baut
    upgrade() die Datenbank um. Geht dabei etwas schief oder stellt sich die
    neue Version als die falsche heraus, liegt der Stand davor als ganz
    normale Sicherung (Datenbank und Belege) in der Liste der Einstellungen
    und laesst sich mit der alten Version einspielen. Scheitert die
    Sicherung, startet die Anwendung nicht -- lieber kein Start als eine
    umgebaute Datenbank ohne Rueckweg.
    """
    from nebenkostenfix import backup

    try:
        datei = backup.datenbankpfad(app)
    except backup.SicherungsFehler:
        return None  # Postgres im Entwicklerstapel: dort sichert der Betreiber
    if not datei.exists():
        return None
    try:
        archiv = backup.sicherung_erstellen(
            app, datenordner.sicherungsordner(), praefix='sicherung-vor-update')
    except (backup.SicherungsFehler, OSError) as fehler:
        raise RuntimeError(
            'Vor der Umstellung der Datenbank auf die neue Version ließ sich '
            f'keine Sicherung anlegen ({fehler}). Die Anwendung startet nicht, '
            'damit nichts ohne Rückweg umgebaut wird. Schaffen Sie Platz im '
            'Datenordner oder prüfen Sie die Schreibrechte.') from fehler
    app.logger.info('Vor der Wanderung von %s gesichert: %s (NK-081).', stand, archiv.name)
    return archiv


@contextmanager
def _startsperre():
    """Laesst nur einen Prozess gleichzeitig die Datenbank aufsetzen.

    gunicorn startet mit mehreren Arbeitern, und jeder faehrt diese Datei von
    oben durch. Ohne Sperre wandern alle gleichzeitig, was auf SQLite im besten
    Fall "database is locked" ergibt und im schlechteren eine halb gewanderte
    Datei. Auch seed_database() gehoert hier hinein: es liest erst und schreibt
    dann, und vier Arbeiter gleichzeitig legen die Kostenkategorien doppelt an
    (im Versuch mit vier Arbeitern gemessen, neun statt acht).

    Der zweite Prozess wartet, findet danach den Stempel und die Kategorien vor
    und hat nichts mehr zu tun.
    """
    # NK-151 (F-81): plattformneutral -- fcntl unter Linux, msvcrt unter
    # Windows. Bis hierher brach unter Windows schon der Import ab.
    from nebenkostenfix.dateisperre import dateisperre

    pfad = os.path.join(os.path.dirname(_datenbankdatei()) or '.', '.migration.lock')
    with dateisperre(pfad):
        yield


def _datenbankdatei():
    """Pfad der SQLite-Datei, fuer die Sperrdatei daneben."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if uri.startswith('sqlite:///'):
        return uri[len('sqlite:///'):]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nk')


def belege_migrieren():
    """Altbestand auf neutrale Dateinamen (NK-131). Scheitert die Wanderung,
    startet die Anwendung trotzdem: die Datenbank zeigt dann weiter auf die
    alten, vollstaendigen Dateien (siehe ablage_migration)."""
    from nebenkostenfix import ablage_migration

    if not os.path.isdir(nas_handler.nas_mount_path):
        return None
    try:
        return ablage_migration.migrieren(db.session, nas_handler.nas_mount_path)
    except Exception:
        db.session.rollback()
        app.logger.exception(
            'Umstellung der Belegablage auf neutrale Namen abgebrochen; die '
            'Belege bleiben unter ihren alten Namen erreichbar.')
        return None


def datenbestand_herrichten(belege: bool = True):
    """Schema, Katalog und Belegablage auf den Stand dieser Fassung bringen.

    Laeuft beim Start und nach dem Einspielen einer Sicherung (NK-165, F-86):
    ein aelteres Archiv -- die Sicherung vor einem Update, ein Umzugspaket
    von einem Rechner mit aelterer Version -- liesse die laufende Anwendung
    sonst mit neuem Code auf einem alten Schema zurueck. Unter der
    Startsperre, damit kein zweiter Prozess gleichzeitig wandert.

    ``belege=False`` nach dem Einspielen: das Archiv wird so zurueckgeholt,
    wie es war; alte Belegnamen stellt erst der naechste Start um (sie
    bleiben bis dahin erreichbar, NK-131).
    """
    with _startsperre():
        schema_aktualisieren()
        seed_database()
        if belege:
            belege_migrieren()


app.extensions['nk_herrichten'] = datenbestand_herrichten


_veraltet = datenordner.veraltete_variablen()
if _veraltet:
    app.logger.warning(
        'Veraltete Einstellungen gesetzt: %s. Seit NK-132 gibt es einen '
        'Datenordner DATA_DIR (Datenbank, Belege, Sicherungen); die alten '
        'Namen wirken nur noch eine Version lang.', ', '.join(_veraltet))
if datenordner.verwaister_nas_pfad():
    app.logger.warning(
        'NAS_MOUNT_PATH=%s ist kein Ordner und wird ignoriert; die Belege '
        'liegen in %s. Die Zeile kann aus der .env entfernt werden.',
        datenordner.verwaister_nas_pfad(), datenordner.belegordner())


with app.app_context():
    with _startsperre():
        schema_aktualisieren()
        seed_database()
        belege_migrieren()
        # NK-153 (D-89): nach Fristablauf endgueltig loeschen.
        _faellig = mieter_daten.abgelaufene_loeschen()
        if _faellig:
            app.logger.info('%d gesperrte Mietverhältnisse nach Ablauf der '
                            'Aufbewahrungsfrist gelöscht (NK-153).', _faellig)


@app.cli.command('belege-umstellen')
@click.option('--pruefen', is_flag=True,
              help='Probelauf: nur rechnen und Prüfsummen lesen, nichts ändern.')
def belege_umstellen_befehl(pruefen):
    """Belegablage auf neutrale Namen umstellen (NK-131).

    Läuft beim Start ohnehin; der Befehl ist für die Probe gegen eine Kopie
    des Bestands (Tor 0.8-S) und nennt nur Zahlen.
    """
    from nebenkostenfix import ablage_migration

    bericht = ablage_migration.migrieren(db.session, nas_handler.nas_mount_path,
                                         pruefen=pruefen)
    click.echo(json.dumps(bericht, ensure_ascii=False))

def _index_mit_kennung(basis_verz) -> str:
    """index.html mit Inhaltskennung hinter app.js und style.css (NK-140).

    Die Kennung wurde von Hand gepflegt („?v=26“) und nie erhöht -- ein
    Browser mit altem Cache zeigte die neue Oberfläche nicht. Jetzt
    rechnet der Server den sha256 der beiden Dateien (12 Zeichen) und
    setzt ihn ein: Ändert sich eine Datei, ändert sich die Kennung, und
    der Browser lädt neu. Ohne Änderung bleibt die Adresse gleich und der
    Cache gilt weiter.

    ``basis_verz`` ist der Static-Ordner; der Parameter hält die Funktion
    testbar -- der Wächtertest rechnet dieselbe Kennung in einem
    Probenverzeichnis nach.
    """
    import hashlib

    html = (Path(basis_verz) / 'index.html').read_text(encoding='utf-8')
    for name in ('app.js', 'style.css', 'umzug.js', 'formular.js'):
        datei = Path(basis_verz) / name
        if not datei.is_file():
            continue
        inhalte = datei.read_bytes()
        kennung = hashlib.sha256(inhalte).hexdigest()[:12]
        html = re.sub(rf'({re.escape(name)}\?v=)\w+', rf'\g<1>{kennung}',
                      html)
    return html


@app.route('/')
def index():
    return _index_mit_kennung(app.static_folder)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'NebenkostenFix läuft.'}), 200

# Die Entwicklerroute POST /api/debug/reset_db steht seit NK-040 in
# debug_routen.py, und .dockerignore haelt diese Datei aus dem Abbild heraus.
# R-DSGVO-01 verlangt, dass ein Reset-Endpunkt im Auslieferungsbuild nicht
# existiert -- nicht, dass er per Flag ausgeschaltet ist. Fehlt das Modul,
# faehrt die Anwendung ohne die Route weiter; im Entwicklungsstapel liegt das
# Arbeitsverzeichnis als Volume im Container, dort ist sie da.
try:
    from nebenkostenfix import debug_routen
except ImportError:
    # Kein ``pass``: dass die Entwicklerroute fehlt, ist der Normalfall im
    # Auslieferungsbuild und kein Fehler -- aber wer im Entwicklungsstapel
    # vergeblich auf sie zugreift, soll den Grund im Protokoll finden und
    # nicht bei der Route suchen, die es nie gab (NK-042).
    protokoll.debug(
        'debug_routen nicht vorhanden -- POST /api/debug/reset_db ist in '
        'diesem Build nicht angemeldet (NK-040, R-DSGVO-01).')
else:
    debug_routen.registriere(app, seed_database=seed_database, nas_handler=nas_handler)

# --- Property Routes ---
@app.route('/api/properties', methods=['GET'])
def get_properties():
    properties = Property.query.all()
    result = []
    for p in properties:
        result.append({
            'id': p.id,
            'name': p.name,
            'is_standalone': p.is_standalone,
            # NK-159: das Beispiel zählt in keiner Kennzahl der Übersicht.
            'ist_beispiel': beispielimmobilie.ist_beispiel(p),
        })
    return jsonify(result), 200

@app.route('/api/properties', methods=['POST'])
def create_property():
    eingabe = Eingabe.aus_request()
    new_prop = Property(
        name=eingabe.text('name', pflicht=True, maxlaenge=200),
        is_standalone=eingabe.wahrheit('is_standalone')
    )
    db.session.add(new_prop)
    db.session.commit()
    return jsonify({'message': 'Property created successfully', 'id': new_prop.id}), 201

@app.route('/api/properties/<int:id>', methods=['PUT', 'DELETE'])
def update_delete_property(id):
    prop = Property.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(prop)
        db.session.commit()
        return jsonify({'message': 'Property deleted'}), 200
    
    eingabe = Eingabe.aus_request()
    if eingabe.vorhanden('name'):
        prop.name = eingabe.text('name', pflicht=True, maxlaenge=200)
    if eingabe.vorhanden('is_standalone'):
        prop.is_standalone = eingabe.wahrheit('is_standalone')
    db.session.commit()
    return jsonify({'message': 'Property updated'}), 200

# --- Heizungsanlagen (NK-125): die Anlage als eigene Sache (NK-048) ---

def _anlage_zeile(anlage: 'Heizungsanlage') -> dict:
    """Eine Anlage, wie die Oberflaeche sie liest."""
    return {
        'id': anlage.id,
        'property_id': anlage.property_id,
        'name': anlage.name,
        'versorgt': anlage.versorgt,
        'verbrauchsanteil_prozent': anlage.verbrauchsanteil_prozent,
        'sonderfall_70': anlage.sonderfall_70,
        'warmwasser_weg': anlage.warmwasser_weg,
        'warmwasser_kwh': (float(anlage.warmwasser_kwh)
                           if anlage.warmwasser_kwh is not None else None),
        'warmwasser_volumen_m3': (float(anlage.warmwasser_volumen_m3)
                                  if anlage.warmwasser_volumen_m3 is not None
                                  else None),
        'warmwasser_temperatur_c': (float(anlage.warmwasser_temperatur_c)
                                    if anlage.warmwasser_temperatur_c is not None
                                    else None),
        'brennstoff_menge': (float(anlage.brennstoff_menge)
                             if anlage.brennstoff_menge is not None else None),
        'heizwert_kwh': (float(anlage.heizwert_kwh)
                         if anlage.heizwert_kwh is not None else None),
    }


def _dezimalfeld(eingabe, feld):
    """Eine Menge als Decimal oder None — fuer die Numeric-Spalten.

    ``kommazahl`` liest den Text; damit die Datenbank die versprochene
    Genauigkeit haelt (kein Float-Rest in einer Mengenspalte), geht der
    Wert ueber den Text in ein Decimal.
    """
    wert = eingabe.kommazahl(feld, min_wert=0.000001)
    return None if wert is None else Decimal(str(wert))


@app.route('/api/properties/<int:property_id>/heizungsanlagen', methods=['GET'])
def get_heizungsanlagen(property_id):
    """Die Anlagen einer Immobilie (NK-125)."""
    Property.query.get_or_404(property_id)
    anlagen = Heizungsanlage.query.filter_by(
        property_id=property_id).order_by(Heizungsanlage.id).all()
    return jsonify([_anlage_zeile(a) for a in anlagen])


def _anlage_aus_eingabe(eingabe, anlage: 'Heizungsanlage', property_id=None):
    """Nimmt die Felder des Anlagen-Dialogs, geprueft in heizung.py.

    Die Pruefregeln des § 7 Abs. 1 (Rahmen 50 bis 70, Sonderfall zwingend
    70) und des § 9 (der Weg nur an der verbundenen Anlage, seine Mengen
    positiv, die Temperatur ueber der Kaltwassergrenze) stehen im Fachmodul
    und nicht hier — dieselbe Regel wie beim Rechenkern: das Gesetz an
    einem Ort. Nur die Uebersetzung in den Fehlerkanal der Oberflaeche
    (EingabeFehler mit Feldnamen) geschieht hier.
    """
    def gesetzlich(aufruf, feld):
        try:
            return aufruf()
        except HeizungsFehler as fehler:
            raise EingabeFehler(str(fehler), feld) from fehler

    anlage.name = eingabe.text('name', pflicht=True, maxlaenge=100)
    anlage.versorgt = gesetzlich(
        lambda: pruefe_versorgungsart(
            eingabe.text('versorgt', pflicht=True)), 'versorgt')
    sonderfall = eingabe.wahrheit('sonderfall_70')
    anteil = eingabe.ganzzahl('verbrauchsanteil_prozent', pflicht=True)
    anlage.verbrauchsanteil_prozent = gesetzlich(
        lambda: pruefe_anteil(anteil, sonderfall), 'verbrauchsanteil_prozent')
    anlage.sonderfall_70 = sonderfall

    # Die Trennung (§ 9) gibt es nur an der verbundenen Anlage. Wird die
    # Anlage auf reine Heizung oder reines Warmwasser umgestellt, wandern
    # die Trennangaben fort — sonst stuende da ein Weg, der nie zur
    # Anwendung kaeme (derselbe CHECK wie in der Tabelle).
    if anlage.versorgt == VERBUNDEN:
        weg = eingabe.text('warmwasser_weg')
        if weg:
            anlage.warmwasser_weg = gesetzlich(
                lambda: pruefe_warmwasserweg(weg), 'warmwasser_weg')
            if anlage.warmwasser_weg == 'zaehler':
                anlage.warmwasser_kwh = _dezimalfeld(eingabe, 'warmwasser_kwh')
                if anlage.warmwasser_kwh is None:
                    raise EingabeFehler(
                        'Der Weg "Zähler" braucht die gemessene Wärmemenge '
                        'des Warmwassers in kWh.', 'warmwasser_kwh')
                anlage.warmwasser_volumen_m3 = None
                anlage.warmwasser_temperatur_c = None
            else:  # formel
                anlage.warmwasser_volumen_m3 = _dezimalfeld(
                    eingabe, 'warmwasser_volumen_m3')
                anlage.warmwasser_temperatur_c = _dezimalfeld(
                    eingabe, 'warmwasser_temperatur_c')
                if (anlage.warmwasser_volumen_m3 is None
                        or anlage.warmwasser_temperatur_c is None):
                    raise EingabeFehler(
                        'Der Weg "Formel" braucht das Warmwasservolumen in m³ '
                        'und die Warmwassertemperatur in Grad Celsius.',
                        'warmwasser_volumen_m3')
                anlage.warmwasser_kwh = None
        else:
            raise EingabeFehler(
                'Die verbundene Anlage braucht den Weg, mit dem die '
                'Wärmemenge des Warmwassers getrennt wird (§ 9 Abs. 2 '
                'HeizkostenV).', 'warmwasser_weg')
        anlage.brennstoff_menge = _dezimalfeld(eingabe, 'brennstoff_menge')
        if anlage.brennstoff_menge is None:
            raise EingabeFehler(
                'Die Trennung rechnet gegen den Gesamtverbrauch der Anlage. '
                'Tragen Sie die Brennstoffmenge des Zeitraums ein (Kilowattstunden '
                'von der Gasrechnung, Liter vom Lieferschein).', 'brennstoff_menge')
        anlage.heizwert_kwh = _dezimalfeld(eingabe, 'heizwert_kwh')
    else:
        anlage.warmwasser_weg = None
        anlage.warmwasser_kwh = None
        anlage.warmwasser_volumen_m3 = None
        anlage.warmwasser_temperatur_c = None
        anlage.brennstoff_menge = None
        anlage.heizwert_kwh = None

    if property_id is not None:
        anlage.property_id = property_id


@app.route('/api/properties/<int:property_id>/heizungsanlagen', methods=['POST'])
def create_heizungsanlage(property_id):
    """Legt eine Anlage an (NK-125)."""
    Property.query.get_or_404(property_id)
    eingabe = Eingabe.aus_request()
    anlage = Heizungsanlage(property_id=property_id)
    _anlage_aus_eingabe(eingabe, anlage)
    db.session.add(anlage)
    db.session.commit()
    return jsonify(_anlage_zeile(anlage)), 201


@app.route('/api/heizungsanlagen/<int:id>', methods=['PUT'])
def update_heizungsanlage(id):
    """Aendert eine Anlage (NK-125)."""
    anlage = Heizungsanlage.query.get_or_404(id)
    eingabe = Eingabe.aus_request()
    _anlage_aus_eingabe(eingabe, anlage)
    db.session.commit()
    return jsonify(_anlage_zeile(anlage))


@app.route('/api/heizungsanlagen/<int:id>', methods=['DELETE'])
def delete_heizungsanlage(id):
    """Loescht eine Anlage, solange nichts an ihr haengt (NK-125)."""
    anlage = Heizungsanlage.query.get_or_404(id)
    if anlage.invoices or Meter.query.filter_by(heizungsanlage_id=id).count():
        raise EingabeFehler(
            'An dieser Anlage hängen Rechnungen oder Zähler. Lösen Sie '
            'die Zuordnungen zuerst.', 'heizungsanlage')
    db.session.delete(anlage)
    db.session.commit()
    return jsonify({'message': 'gelöscht'})

# --- Apartment Routes ---
@app.route('/api/properties/<int:property_id>/apartments', methods=['GET'])
def get_apartments(property_id):
    apartments = Apartment.query.filter_by(property_id=property_id).all()
    result = []
    for a in apartments:
        result.append({
            'id': a.id,
            'name': a.name,
            'sqm': a.sqm,
            'is_active': a.is_active,
            'nutzungsart': a.nutzungsart,
            'selbstversorger': a.selbstversorger,
            'eigennutzung': a.eigennutzung
        })
    return jsonify(result), 200

@app.route('/api/apartments', methods=['GET'])
def get_all_apartments():
    apartments = Apartment.query.all()
    result = []
    for apt in apartments:
        result.append({
            'id': apt.id,
            'name': apt.name,
            'sqm': apt.sqm,
            'property_id': apt.property_id,
            'property_name': apt.property.name,
            'nutzungsart': apt.nutzungsart,
            'selbstversorger': apt.selbstversorger,
            'eigennutzung': apt.eigennutzung
        })
    return jsonify(result)

@app.route('/api/apartments', methods=['POST'])
def create_apartment():
    eingabe = Eingabe.aus_request()
    name = eingabe.text('name', pflicht=True, maxlaenge=200)
    # Die drei Stammdaten aus NK-045 sind freiwillig: wer nichts sagt, bekommt
    # eine Wohnung, die er selbst nicht bewohnt und nicht selbst beheizt. Das
    # ist der Normalfall eines Vermieters.
    new_apartment = Apartment(
        property_id=eingabe.ganzzahl('property_id', pflicht=True),
        name=name,
        sqm=eingabe.kommazahl('sqm', pflicht=True, min_wert=0),
        nutzungsart=eingabe.nutzungsart(standard=NUTZUNG_VORGABE, einheit=name),
        selbstversorger=eingabe.wahrheit('selbstversorger'),
        eigennutzung=eingabe.wahrheit('eigennutzung')
    )
    db.session.add(new_apartment)
    db.session.commit()
    return jsonify({'message': 'Apartment created successfully', 'id': new_apartment.id}), 201

@app.route('/api/apartments/<int:id>', methods=['PUT', 'DELETE'])
def update_delete_apartment(id):
    apt = Apartment.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(apt)
        db.session.commit()
        return jsonify({'message': 'Apartment deleted'}), 200
    
    eingabe = Eingabe.aus_request()
    if eingabe.vorhanden('name'):
        apt.name = eingabe.text('name', pflicht=True, maxlaenge=200)
    if eingabe.vorhanden('sqm'):
        apt.sqm = eingabe.kommazahl('sqm', pflicht=True, min_wert=0)
    if eingabe.vorhanden('nutzungsart'):
        apt.nutzungsart = eingabe.nutzungsart(pflicht=True, einheit=apt.name)
    if eingabe.vorhanden('selbstversorger'):
        apt.selbstversorger = eingabe.wahrheit('selbstversorger')
    if eingabe.vorhanden('eigennutzung'):
        apt.eigennutzung = eingabe.wahrheit('eigennutzung')
    db.session.commit()
    return jsonify({'message': 'Apartment updated'}), 200

# --- Tenant Routes ---
@app.route('/api/tenants', methods=['GET'])
def get_tenants():
    # NK-153: gesperrte Mietverhaeltnisse (geloescht, Aufbewahrung laeuft)
    # erscheinen nur auf ausdruecklichen Wunsch (?gesperrte=1), dann allein.
    if request.args.get('gesperrte') == '1':
        tenants = Tenant.query.filter(Tenant.gesperrt_bis.isnot(None)).all()
    else:
        tenants = Tenant.query.filter(Tenant.gesperrt_bis.is_(None)).all()
    result = []
    for t in tenants:
        result.append({
            'id': t.id,
            'apartment_id': t.apartment_id,
            'name': t.name,
            'move_in_date': t.move_in_date.isoformat(),
            'move_out_date': t.move_out_date.isoformat() if t.move_out_date else None,
            'last_billed_until': t.last_billed_until.isoformat() if t.last_billed_until else None,
            'contract_path': t.contract_path,
            'apartment_name': t.apartment.name if t.apartment else 'Unknown',
            'property_name': t.apartment.property.name if t.apartment and t.apartment.property else 'Unknown',
            'gesperrt_bis': t.gesperrt_bis.isoformat() if t.gesperrt_bis else None,
            'ist_beispiel': beispielimmobilie.ist_beispiel(
                t.apartment.property if t.apartment else None),
        })
    return jsonify(result), 200

@app.route('/api/tenants', methods=['POST'])
def create_tenant():
    eingabe = Eingabe.aus_request()

    new_tenant = Tenant(
        apartment_id=eingabe.ganzzahl('apartment_id', pflicht=True),
        name=eingabe.text('name', pflicht=True, maxlaenge=200),
        move_in_date=eingabe.datum('move_in_date', pflicht=True),
        move_out_date=eingabe.datum('move_out_date'),
        last_billed_until=eingabe.datum('last_billed_until')
    )
    db.session.add(new_tenant)
    db.session.flush() # get id

    vertrag = eingabe.datei('contract_file')
    if vertrag:
        apt = Apartment.query.get(new_tenant.apartment_id)
        if apt is None:
            db.session.rollback()
            raise EingabeFehler(
                'Die angegebene Wohnung gibt es nicht.', 'apartment_id')
        contract_path = nas_handler.save_tenant_contract(vertrag, apt.property.name, apt.name, new_tenant.name)
        new_tenant.contract_path = contract_path

    db.session.commit()
    return jsonify({'message': 'Tenant created successfully', 'id': new_tenant.id}), 201

@app.route('/api/tenants/<int:tenant_id>/export', methods=['GET'])
def export_tenant(tenant_id):
    """Auskunft fuer ein Mietverhaeltnis (NK-078, DSGVO Art. 15).

    Ein ZIP: die JSON-Auskunft mit allen Zeilen zum Mieter und die Dateien
    dazu (Mietvertrag, Abrechnungen, Lesenachweise). Das liefert mieter_daten;
    diese Route haelt nur das HTTP dazu.
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    zip_bytes, _inhalt = mieter_daten.export_erstellen(tenant)
    return send_file(
        io.BytesIO(zip_bytes),
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"mieter-export-{tenant_id}.zip",
    )


@app.route('/api/tenants/<int:id>', methods=['PUT', 'DELETE'])
def update_delete_tenant(id):
    tenant = Tenant.query.get_or_404(id)
    if request.method == 'DELETE':
        # NK-078: die Dateien gehoeren zur Loeschung -- ein geloeschter
        # Mieter mit Mietvertrag im Belegordner ist nicht geloescht.
        bericht = mieter_daten.loeschen(tenant)
        antwort = {
            'message': 'Mieter gelöscht',
            'geloeschte_dateien': bericht['geloeschte_dateien'],
            'fehlende_dateien': bericht['fehlende_dateien'],
            'gesperrt_bis': bericht['gesperrt_bis'],
        }
        if bericht['gesperrt_bis']:
            # NK-153 (D-89): Abrechnungen und Zahlungen unterliegen der
            # Aufbewahrung; gesperrt statt geloescht.
            frist = date.fromisoformat(bericht['gesperrt_bis']).strftime('%d.%m.%Y')
            antwort['message'] = (
                'Mieter gelöscht. Festgesetzte Abrechnungen und Zahlungen '
                'unterliegen der Aufbewahrungspflicht (§ 147 AO, § 257 HGB) '
                f'und bleiben bis {frist} gesperrt gespeichert; danach werden '
                'sie automatisch gelöscht.')
        if bericht['fehlende_dateien']:
            antwort['hinweis'] = (
                "Diese Dateien waren im Belegordner nicht mehr vorhanden: "
                + ", ".join(bericht['fehlende_dateien']))
        return jsonify(antwort), 200
    
    eingabe = Eingabe.aus_request()

    if eingabe.vorhanden('name'):
        tenant.name = eingabe.text('name', pflicht=True, maxlaenge=200)
    if eingabe.vorhanden('apartment_id'):
        tenant.apartment_id = eingabe.ganzzahl('apartment_id', pflicht=True)
    # Ein Pflichtdatum, das dasteht, muss lesbar sein. Bis NK-028 schluckte
    # ein except ValueError: pass das kaputte Datum und antwortete 200, ohne
    # etwas geaendert zu haben.
    if eingabe.vorhanden('move_in_date'):
        tenant.move_in_date = eingabe.datum('move_in_date', pflicht=True)
    # Auszug und Abrechnungsstand duerfen leer geschickt werden, das raeumt
    # sie aus. Etwas Unlesbares darin ist trotzdem eine Absage.
    if eingabe.vorhanden('move_out_date'):
        tenant.move_out_date = eingabe.datum('move_out_date')
    if eingabe.vorhanden('last_billed_until'):
        tenant.last_billed_until = eingabe.datum('last_billed_until')

    vertrag = eingabe.datei('contract_file')
    if vertrag:
        apt = Apartment.query.get(tenant.apartment_id)
        if apt is None:
            db.session.rollback()
            raise EingabeFehler(
                'Die angegebene Wohnung gibt es nicht.', 'apartment_id')
        contract_path = nas_handler.save_tenant_contract(vertrag, apt.property.name, apt.name, tenant.name)
        tenant.contract_path = contract_path

    db.session.commit()
    return jsonify({'message': 'Tenant updated'}), 200

@app.route('/api/tenants/<int:id>/contract', methods=['GET'])
def get_tenant_contract(id):
    tenant = Tenant.query.get_or_404(id)
    if not tenant.contract_path:
        return jsonify({'error': 'Zu diesem Mieter ist kein Mietvertrag hinterlegt.'}), 404
        
    # NK-129: dieselbe sichere Auslieferung wie /api/dateien/mietvertrag/<id>.
    return datei_antwort(tenant.contract_path)

# --- Haushaltsgroessen (NK-045) ---
# Die Personenzahl eines Haushalts aendert sich waehrend des Mietverhaeltnisses:
# ein Kind kommt, ein Partner zieht aus. Wer nur die heutige Zahl speichert,
# rechnet den ganzen Zeitraum mit ihr ab und liegt fuer die Monate davor falsch
# (R-NUM-04). Darum eine Zeile je Stichtag statt eines Feldes am Mietverhaeltnis
# -- ein zweites Feld waere die zweite Wahrheit.
@app.route('/api/tenants/<int:tenant_id>/haushaltsgroessen', methods=['GET'])
def get_haushaltsgroessen(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    return jsonify([
        {
            'id': h.id,
            'tenant_id': h.tenant_id,
            'gueltig_ab': h.gueltig_ab.isoformat(),
            'personenanzahl': h.personenanzahl
        }
        for h in sorted(tenant.haushaltsgroessen, key=lambda h: h.gueltig_ab)
    ]), 200


@app.route('/api/tenants/<int:tenant_id>/haushaltsgroessen', methods=['POST'])
def save_haushaltsgroesse(tenant_id):
    """Legt einen Stichtag an -- oder berichtigt den, der schon dasteht.

    Ein zweiter Eintrag zum selben Tag waere ein Widerspruch, den die
    Datenbank ohnehin abweist. Statt den Vermieter mit einem 409 stehen zu
    lassen, nimmt die Route die neue Zahl als Berichtigung: er wollte sagen,
    wie viele Koepfe ab diesem Tag im Haushalt leben.
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    eingabe = Eingabe.aus_request()

    gueltig_ab = eingabe.datum('gueltig_ab', pflicht=True)
    anzahl = eingabe.ganzzahl('personenanzahl', pflicht=True, min_wert=1)

    if gueltig_ab < tenant.move_in_date:
        raise EingabeFehler(
            f'Der Stichtag {gueltig_ab.isoformat()} liegt vor dem Einzug am '
            f'{tenant.move_in_date.isoformat()}. Vor dem Einzug wohnt niemand '
            f'in der Wohnung.', 'gueltig_ab')

    vorhanden = next(
        (h for h in tenant.haushaltsgroessen if h.gueltig_ab == gueltig_ab), None)
    if vorhanden:
        vorhanden.personenanzahl = anzahl
        db.session.commit()
        return jsonify({'message': 'Haushaltsgröße aktualisiert', 'id': vorhanden.id}), 200

    eintrag = Haushaltsgroesse(
        tenant_id=tenant.id, gueltig_ab=gueltig_ab, personenanzahl=anzahl)
    db.session.add(eintrag)
    db.session.commit()
    return jsonify({'message': 'Haushaltsgröße angelegt', 'id': eintrag.id}), 201


@app.route('/api/haushaltsgroessen/<int:id>', methods=['DELETE'])
def delete_haushaltsgroesse(id):
    eintrag = Haushaltsgroesse.query.get_or_404(id)
    db.session.delete(eintrag)
    db.session.commit()
    return jsonify({'message': 'Haushaltsgröße gelöscht'}), 200

# --- Providers ---
@app.route('/api/providers', methods=['GET'])
def get_providers():
    providers = Provider.query.all()
    return jsonify([{'id': p.id, 'name': p.name} for p in providers]), 200

@app.route('/api/providers', methods=['POST'])
def create_provider():
    eingabe = Eingabe.aus_request()
    new_provider = Provider(name=eingabe.text('name', pflicht=True, maxlaenge=200))
    db.session.add(new_provider)
    db.session.commit()
    return jsonify({'message': 'Provider created', 'id': new_provider.id}), 201

@app.route('/api/providers/<int:id>', methods=['DELETE'])
def delete_provider(id):
    provider = Provider.query.get_or_404(id)
    # Reassign to standard or null? Delete cascading is not set. Let's not delete if in use.
    if provider.invoices or provider.meter_readings:
        return jsonify({'error': 'Provider in use'}), 400
    db.session.delete(provider)
    db.session.commit()
    return jsonify({'message': 'deleted'})

# --- Categories ---
@app.route('/api/categories', methods=['GET'])
def get_categories():
    categories = CostCategory.query.all()
    result = []
    for c in categories:
        result.append({
            'id': c.id,
            'name': c.name,
            'allocation_method': c.allocation_method,
            'requires_meter': c.requires_meter,
            # Die Nummer und ihre amtliche Bezeichnung (NK-044). Der Vermieter
            # nennt seine Kostenart, wie er will; auf der Abrechnung muss aber
            # nachvollziehbar sein, welche Position aus § 2 BetrKV gemeint ist
            # (R-DOC-01). Beides geht deshalb mit ueber die Grenze.
            'betrkv_nr': c.betrkv_nr,
            'betrkv_bezeichnung': betrkv.bezeichnung(c.betrkv_nr),
        })
    return jsonify(result), 200

# --- Meters ---
@app.route('/api/meters', methods=['GET'])
def get_meters():
    meters = Meter.query.all()
    result = []
    for m in meters:
        result.append({
            'id': m.id,
            'category_id': m.category_id,
            'category_name': m.category.name,
            'property_id': m.property_id,
            'property_name': m.property.name,
            'apartment_id': m.apartment_id,
            'apartment_name': m.apartment.name if m.apartment else None,
            'is_main_meter': m.is_main_meter,
            'meter_number': m.meter_number,
            'has_dual_tariff': m.has_dual_tariff,
            'is_official': m.is_official,
            'heizungsanlage_id': m.heizungsanlage_id,
            'heizungsanlage_name': (m.heizungsanlage.name
                                    if m.heizungsanlage else None),
        })
    return jsonify(result), 200

@app.route('/api/meters', methods=['POST'])
def create_meter():
    eingabe = Eingabe.aus_request()
    new_meter = Meter(
        category_id=eingabe.ganzzahl('category_id', pflicht=True),
        property_id=eingabe.ganzzahl('property_id', pflicht=True),
        apartment_id=eingabe.ganzzahl('apartment_id'),
        is_main_meter=eingabe.wahrheit('is_main_meter'),
        meter_number=eingabe.text('meter_number', pflicht=True, maxlaenge=100),
        has_dual_tariff=eingabe.wahrheit('has_dual_tariff'),
        is_official=eingabe.wahrheit('is_official'),
        # Welche Anlage dieser Zaehler misst (NK-125, D-45): nicht aus der
        # Kostenart geraten, sondern vom Vermieter gewaehlt.
        heizungsanlage_id=eingabe.ganzzahl('heizungsanlage_id'),
    )
    if new_meter.heizungsanlage_id is not None:
        anlage = Heizungsanlage.query.get_or_404(new_meter.heizungsanlage_id)
        if anlage.property_id != new_meter.property_id:
            raise EingabeFehler(
                'Der Zähler kann nur eine Anlage derselben Immobilie messen.',
                'heizungsanlage_id')
    db.session.add(new_meter)
    db.session.commit()
    return jsonify({'id': new_meter.id}), 201

@app.route('/api/meters/<int:id>', methods=['DELETE'])
def delete_meter(id):
    m = Meter.query.get_or_404(id)
    db.session.delete(m)
    db.session.commit()
    return jsonify({'message': 'deleted'})

# --- Meter Readings ---
@app.route('/api/readings', methods=['GET'])
def get_readings():
    readings = MeterReading.query.all()
    result = []
    for r in readings:
        data = {
            'id': r.id,
            'meter_id': r.meter_id,
            'meter_number': r.meter.meter_number,
            'category_name': r.meter.category.name,
            'property_name': r.meter.property.name,
            'apartment_name': r.meter.apartment.name if r.meter.apartment else None,
            'reading_date': r.reading_date.isoformat(),
            'value': r.value,
            'value_nt': r.value_nt,
            'is_official_invoice': r.is_official_invoice,
            'provider_id': r.provider_id,
            'provider_name': r.provider.name if r.provider else None,
            'document_path': r.document_path,
            'ablesungsart': r.ablesungsart,
            'plausibility_status': 'unknown',
            'plausibility_message': ''
        }
        
        if r.is_official_invoice:
            manual_readings = [mr for mr in readings if mr.meter_id == r.meter_id and not mr.is_official_invoice]
            if manual_readings:
                closest = min(manual_readings, key=lambda mr: abs((mr.reading_date - r.reading_date).days))
                days_diff = abs((closest.reading_date - r.reading_date).days)
                
                if days_diff <= 30:
                    diff_abs = abs(closest.value - r.value)
                    diff_percent = (diff_abs / closest.value * 100) if closest.value != 0 else (100 if r.value > 0 else 0)
                    
                    if diff_percent > 10:
                        data['plausibility_status'] = 'warning'
                        data['plausibility_message'] = f'Abweichung: {diff_percent:.1f}% (Manueller Stand vom {closest.reading_date.strftime("%d.%m.%Y")} war {closest.value})'
                    else:
                        data['plausibility_status'] = 'success'
                        data['plausibility_message'] = f'Plausibel ({diff_percent:.1f}% Abweichung zu manuellem Stand)'
        
        result.append(data)
    return jsonify(result), 200

@app.route('/api/readings', methods=['POST'])
def create_reading():
    eingabe = Eingabe.aus_request()
    meter_id = eingabe.ganzzahl('meter_id', pflicht=True)
    reading_date = eingabe.datum('reading_date', pflicht=True)
    value = eingabe.kommazahl('value', pflicht=True)
    value_nt = eingabe.kommazahl('value_nt')
    is_official_invoice = eingabe.wahrheit('is_official_invoice')
    provider_id = eingabe.ganzzahl('provider_id') if is_official_invoice else None
    # Die Ablesungsart (NK-051): fehlt sie, ist es die gewoehnliche Ablesung.
    # Nur "zwischenablesung" markiert den Stand zum Datum eines
    # Nutzerwechsels als den Messwert der Grenze (§ 9b HeizkostenV).
    ablesungsart = eingabe.text('ablesungsart') or ABLESUNG
    if ablesungsart not in ABLESUNGSARTEN:
        raise EingabeFehler(
            f'Die Ablesungsart „{ablesungsart}“ gibt es nicht. Erlaubt sind: '
            f'{", ".join(ABLESUNGSARTEN)}.', 'ablesungsart')

    meter = Meter.query.get_or_404(meter_id)

    document_path = None
    foto = eingabe.datei('file')
    if foto:
        apt_name = meter.apartment.name if meter.apartment else None
        document_path = nas_handler.save_reading_photo(
            file=foto,
            category_name=meter.category.name,
            property_name=meter.property.name,
            apartment_name=apt_name,
            reading_date=reading_date
        )
            
    new_reading = MeterReading(
        meter_id=meter_id,
        reading_date=reading_date,
        value=value,
        value_nt=value_nt,
        is_official_invoice=is_official_invoice,
        provider_id=provider_id,
        document_path=document_path,
        ablesungsart=ablesungsart,
    )
    db.session.add(new_reading)
    db.session.commit()
    return jsonify({'id': new_reading.id}), 201

@app.route('/api/readings/<int:id>', methods=['PUT'])
def update_reading(id):
    reading = MeterReading.query.get_or_404(id)
    
    eingabe = Eingabe.aus_request()

    if eingabe.vorhanden('reading_date'):
        reading.reading_date = eingabe.datum('reading_date', pflicht=True)
    if eingabe.vorhanden('value'):
        reading.value = eingabe.kommazahl('value', pflicht=True)
    if eingabe.vorhanden('value_nt'):
        reading.value_nt = eingabe.kommazahl('value_nt')
    if eingabe.vorhanden('is_official_invoice'):
        reading.is_official_invoice = eingabe.wahrheit('is_official_invoice')
    if eingabe.vorhanden('provider_id'):
        # Der Anbieter haengt am Kennzeichen: ohne Abrechnung des Versorgers
        # gehoert kein Anbieter an den Stand.
        reading.provider_id = eingabe.ganzzahl('provider_id') if reading.is_official_invoice else None
    if eingabe.vorhanden('ablesungsart'):
        # Die Ablesungsart (NK-051) laesst sich nachtraeglich berichtigen:
        # wer bei einem Nutzerwechsel vergessen hat, die Zwischenablesung
        # als solche zu markieren, korrigiert hier, statt den Stand neu
        # anzulegen.
        art = eingabe.text('ablesungsart', pflicht=True)
        if art not in ABLESUNGSARTEN:
            raise EingabeFehler(
                f'Die Ablesungsart „{art}“ gibt es nicht. Erlaubt sind: '
                f'{", ".join(ABLESUNGSARTEN)}.', 'ablesungsart')
        reading.ablesungsart = art

    foto = eingabe.datei('file')
    if foto:
        meter = reading.meter
        apt_name = meter.apartment.name if meter.apartment else None
        new_path = nas_handler.save_reading_photo(
            file=foto,
            category_name=meter.category.name,
            property_name=meter.property.name,
            apartment_name=apt_name,
            reading_date=reading.reading_date
        )
        if new_path:
            reading.document_path = new_path
                
    db.session.commit()
    return jsonify({'id': reading.id}), 200

@app.route('/api/readings/<int:id>', methods=['DELETE'])
def delete_reading(id):
    reading = MeterReading.query.get_or_404(id)
    db.session.delete(reading)
    db.session.commit()
    return jsonify({'message': 'deleted'})

@app.route('/api/readings/check_plausibility', methods=['POST'])
def check_plausibility():
    # Die Oberflaeche fragt hier waehrend der Eingabe an und liest status und
    # message, nicht error. Der EingabeFehler wird darum hier abgefangen und
    # in genau diese Form uebersetzt, statt in die 400 aus init_validation zu
    # laufen.
    try:
        eingabe = Eingabe.aus_request()
        meter_id = eingabe.ganzzahl('meter_id', pflicht=True)
        reading_date = eingabe.datum('reading_date', pflicht=True)
        value = eingabe.kommazahl('value', standard=0.0)
    except EingabeFehler as fehler:
        return jsonify({'status': 'unknown', 'message': fehler.meldung}), 400
        
    meter = Meter.query.get(meter_id)
    if not meter:
        return jsonify({'status': 'unknown', 'message': 'Meter not found'}), 404
        
    if meter.is_main_meter:
        all_sub_meters = Meter.query.filter_by(property_id=meter.property_id, category_id=meter.category_id, is_main_meter=False).all()
        sub_meter_sum = 0.0
        all_found = True
        
        if len(all_sub_meters) > 0:
            for sub_m in all_sub_meters:
                sub_readings = MeterReading.query.filter_by(meter_id=sub_m.id).all()
                if not sub_readings:
                    all_found = False
                    break
                closest_sub = min(sub_readings, key=lambda r: abs((r.reading_date - reading_date).days))
                if abs((closest_sub.reading_date - reading_date).days) > 30:
                    all_found = False
                    break
                sub_meter_sum += closest_sub.value
                
            if all_found:
                diff = value - sub_meter_sum
                status = 'success' if diff >= 0 else 'warning'
                msg_prefix = 'Plausibel.' if diff >= 0 else 'Achtung: Negativer Allgemeinverbrauch!'
                return jsonify({
                    'status': status,
                    'message': f"{msg_prefix} Hauptzähler: {value:.1f} | Σ Unterzähler: {sub_meter_sum:.1f} | Differenz (Allgemein): {diff:.1f}",
                    'main_value': value,
                    'sub_sum': sub_meter_sum,
                    'diff': diff
                }), 200
                
    # Fallback to normal check
    # Find manual readings for this meter
    manual_readings = MeterReading.query.filter_by(
        meter_id=meter_id, 
        is_official_invoice=False
    ).all()
    
    if not manual_readings:
        return jsonify({'status': 'ok', 'message': 'Keine manuellen Vergleichswerte gefunden.'}), 200
        
    # Find closest reading
    closest_reading = min(manual_readings, key=lambda r: abs((r.reading_date - reading_date).days))
    days_diff = abs((closest_reading.reading_date - reading_date).days)
    
    if days_diff > 30:
        return jsonify({'status': 'ok', 'message': 'Keine zeitnahen Ablesungen gefunden.'}), 200
        
    # Calculate difference
    diff_abs = abs(closest_reading.value - value)
    if closest_reading.value == 0:
        diff_percent = 100 if value > 0 else 0
    else:
        diff_percent = (diff_abs / closest_reading.value) * 100
        
    if diff_percent > 10:
        return jsonify({
            'status': 'warning', 
            'message': f'Achtung! Der manuell abgelesene Wert am {closest_reading.reading_date.strftime("%d.%m.%Y")} war {closest_reading.value}. Die Abweichung beträgt {diff_percent:.1f}%.',
            'closest_value': closest_reading.value,
            'closest_date': closest_reading.reading_date.isoformat(),
            'diff_percent': diff_percent
        }), 200
        
    return jsonify({
        'status': 'success',
        'message': f'Plausibel. Manueller Wert vom {closest_reading.reading_date.strftime("%d.%m.%Y")}: {closest_reading.value} ({diff_percent:.1f}% Abweichung).',
        'closest_value': closest_reading.value,
        'closest_date': closest_reading.reading_date.isoformat(),
        'diff_percent': diff_percent
    }), 200


# Dateien nur per Kennung (NK-129, F-55, F-59). Bis hierher nahm /api/files
# einen Pfad aus der Anfrage und lieferte die Datei mit geratenem Typ aus.
# Jetzt nennt die Oberflaeche die Art und die Kennung des Datensatzes, der
# Pfad kommt aus der Datenbank und bleibt im Belegordner.
DATEIARTEN_AUSLIEFERUNG = ('ablesung', 'rechnung', 'dokument', 'abrechnung',
                           'abrechnung-detailliert', 'mietvertrag')


def _gespeicherter_pfad(art, kennung):
    """(Pfad aus der Datenbank, Anzeigename) fuer eine Datei, oder 404."""
    from flask import abort

    if art == 'ablesung':
        zeile = db.get_or_404(MeterReading, kennung)
        return zeile.document_path, None
    if art == 'rechnung':
        zeile = db.get_or_404(CostInvoice, kennung)
        if zeile.document is not None and zeile.document.document_path:
            return zeile.document.document_path, zeile.document.filename
        return zeile.document_path, None
    if art == 'dokument':
        zeile = db.get_or_404(InvoiceDocument, kennung)
        return zeile.document_path, zeile.filename
    if art in ('abrechnung', 'abrechnung-detailliert'):
        zeile = db.get_or_404(TenantBillingReport, kennung)
        if art == 'abrechnung':
            return zeile.document_path, None
        return zeile.document_path_detailed, None
    if art == 'mietvertrag':
        zeile = db.get_or_404(Tenant, kennung)
        return zeile.contract_path, None
    abort(404)


def datei_antwort(gespeichert, anzeigename=None):
    """Die sichere Antwort fuer einen Pfad aus der Datenbank (NK-129)."""
    pfad = uploads.pfad_aufloesen(nas_handler.nas_mount_path, gespeichert)
    if pfad is None:
        return jsonify({'error': 'Die Datei liegt nicht (mehr) im Belegordner.'}), 404
    return uploads.ausliefern(pfad, anzeigename)


@app.route('/api/belege/export', methods=['GET'])
def belege_exportieren():
    """Alle Belege (oder die einer Immobilie) als ZIP mit sprechenden Namen
    (NK-131, D-87). Die Ablage selbst kennt nur neutrale Namen."""
    from nebenkostenfix import belege_export

    property_id = request.args.get('property_id', type=int)
    if property_id is not None:
        db.get_or_404(Property, property_id)
    inhalt, _bericht = belege_export.zip_erstellen(nas_handler.nas_mount_path,
                                                  property_id)
    return send_file(io.BytesIO(inhalt), mimetype='application/zip',
                     as_attachment=True,
                     download_name=f'Belege_{date.today().isoformat()}.zip')


@app.route('/api/dateien/<art>/<int:kennung>', methods=['GET'])
def datei_ausliefern(art, kennung):
    """Eine abgelegte Datei, benannt nach Art und Kennung ihres Datensatzes."""
    if art not in DATEIARTEN_AUSLIEFERUNG:
        return jsonify({'error': 'Diese Dateiart gibt es nicht.'}), 404
    gespeichert, anzeigename = _gespeicherter_pfad(art, kennung)
    if not gespeichert:
        return jsonify({'error': 'Zu diesem Eintrag ist keine Datei hinterlegt.'}), 404
    return datei_antwort(gespeichert, anzeigename)

# --- Tenant Cost Profiles ---
@app.route('/api/tenants/<int:tenant_id>/profiles', methods=['GET'])
def get_tenant_profiles(tenant_id):
    profiles = TenantCostProfile.query.filter_by(tenant_id=tenant_id).all()
    result = {}
    for p in profiles:
        result[p.category_id] = p.billing_type
    return jsonify(result), 200

@app.route('/api/tenants/<int:tenant_id>/profiles', methods=['POST'])
def save_tenant_profiles(tenant_id):
    # Geprueft wird vor dem Loeschen: die alten Profile sind weg, sobald die
    # Schleife laeuft, und eine Absage mittendrin liesse den Mieter ohne
    # Kostenprofile zurueck. Die Namen der Kostenarten gehen mit in die
    # Pruefung, damit die Meldung die Zeile benennt (F-25, NK-096).
    namen = {k.id: k.name for k in CostCategory.query.all()}
    profile = kostenprofile(request.get_json(silent=True), namen)
    TenantCostProfile.query.filter_by(tenant_id=tenant_id).delete()

    for cat_id, billing_type in list(profile.items()):
        eintrag = TenantCostProfile(
            tenant_id=tenant_id,
            category_id=cat_id,
            billing_type=billing_type
        )
        db.session.add(eintrag)

    db.session.commit()
    return jsonify({'message': 'Profiles saved'}), 200

# --- Invoice Documents ---
@app.route('/api/invoice_documents', methods=['GET'])
def get_invoice_documents():
    docs = InvoiceDocument.query.filter_by(is_collective=True).all()
    result = []
    for d in docs:
        result.append({
            'id': d.id,
            'property_id': d.property_id,
            'property_name': d.property.name if d.property else 'Unknown',
            'filename': d.filename,
            'document_path': d.document_path,
            'upload_date': d.upload_date.isoformat(),
            'description': d.description
        })
    return jsonify(result), 200

@app.route('/api/invoice_documents', methods=['POST'])
def create_invoice_document():
    eingabe = Eingabe.aus_request()
    property_id = eingabe.ganzzahl('property_id', pflicht=True)
    description = eingabe.text('description', standard='', maxlaenge=1000)
    file = eingabe.datei('file', pflicht=True)

    prop = Property.query.get_or_404(property_id)

    document_path, filename = nas_handler.save_general_document(file, prop.name)
    
    doc = InvoiceDocument(
        property_id=property_id,
        filename=filename,
        document_path=document_path,
        description=description
    )
    db.session.add(doc)
    db.session.commit()
    
    return jsonify({'id': doc.id, 'filename': filename}), 201

@app.route('/api/invoice_documents/<int:doc_id>', methods=['DELETE'])
def delete_invoice_document(doc_id):
    doc = InvoiceDocument.query.get_or_404(doc_id)
    
    # Check if invoices use it
    if CostInvoice.query.filter_by(invoice_document_id=doc.id).first():
        return jsonify({'error': 'Document is in use by an invoice'}), 400
        
    try:
        # Delete file from NAS
        nas_handler.delete_file(doc.document_path)
    except Exception:
        # Der Datenbankeintrag verschwindet trotzdem: eine Karteileiche ohne
        # Datei ist besser als ein Beleg, der sich nicht loeschen laesst, weil
        # die NAS gerade nicht da ist. Die Datei bleibt liegen, das Protokoll
        # sagt welche.
        protokoll.warning('Datei blieb im Belegordner liegen: %s',
                          doc.document_path, exc_info=True)
        
    db.session.delete(doc)
    db.session.commit()
    
    return '', 204

@app.route('/api/invoice_documents/<int:doc_id>', methods=['PUT'])
def update_invoice_document(doc_id):
    doc = InvoiceDocument.query.get_or_404(doc_id)
    eingabe = Eingabe.aus_request()
    property_id = eingabe.ganzzahl('property_id', pflicht=True)
    description = eingabe.text('description', standard='', maxlaenge=1000)

    prop = Property.query.get_or_404(property_id)

    doc.property_id = property_id
    doc.description = description

    file = eingabe.datei('file')
    if file:
        # Delete old file
        try:
            nas_handler.delete_file(doc.document_path)
        except Exception:
            protokoll.warning('Alte Datei blieb im Belegordner liegen: %s',
                              doc.document_path, exc_info=True)

        # Upload new file
        document_path, filename = nas_handler.save_general_document(file, prop.name)
        doc.document_path = document_path
        doc.filename = filename
            
    db.session.commit()
    return jsonify({'id': doc.id, 'filename': doc.filename}), 200

# --- Invoices ---
def _rechnungsfelder(eingabe):
    """Die Felder einer Kostenrechnung, einmal gelesen fuer Anlegen und Aendern.

    Bis NK-028 standen dieselben dreizehn Felder in zwei fast gleichen
    Bloecken. Fast gleich heisst: bei der naechsten Aenderung wird einer von
    beiden vergessen.

    Die Tarifpreise gehoeren zusammen (NK-055, dieselbe Regel wie der CHECK
    in der Datenbank): ein Preis ohne seinen Partner wuerde eine Aufteilung
    des Rechnungsbetrags auf HT und NT behaupten, die der Beleg nicht
    hergibt.
    """
    preis_ht = eingabe.einheitspreis('preis_ht')
    preis_nt = eingabe.einheitspreis('preis_nt')
    if (preis_ht is None) != (preis_nt is None):
        raise EingabeFehler(
            'Die Tarifpreise gehören zusammen: Geben Sie sowohl den Hoch- als '
            'auch den Niedertarif an, oder keinen von beiden.')

    # Anlage und Posten des § 7 Abs. 2 (D-44): beide stehen an der Rechnung,
    # keins von beiden allein.
    anlage_id = eingabe.ganzzahl('heizungsanlage_id')
    art_roh = eingabe.text('heizkostenart')
    if (anlage_id is None) != (not art_roh):
        raise EingabeFehler(
            'Heizkostenrechnung braucht beides: die Anlage, die sie betrifft, '
            'und den Posten des § 7 Abs. 2 HeizkostenV, den sie trägt '
            '(Brennstoff, Betriebsstrom, Wartung, …).', 'heizkostenart')
    if art_roh:
        try:
            heizkostenart = pruefe_kostenart(art_roh)
        except HeizungsFehler as fehler:
            raise EingabeFehler(str(fehler), 'heizkostenart') from fehler
    else:
        heizkostenart = None
    if anlage_id is not None:
        Heizungsanlage.query.get_or_404(anlage_id)

    # Die CO2-Angaben des Lieferanten (NK-053, D-54): uebernehmen, was der
    # Beleg ausweist. Sie gehoeren zur Heizkostenrechnung; ohne Anlage
    # waeren sie ein Ausweis ohne Ort.
    co2_roh = eingabe.geldbetrag('co2_kosten', min_wert=0)
    emission_roh = eingabe.kommazahl('co2_emission_kg', min_wert=0)
    if co2_roh is not None or emission_roh is not None:
        if anlage_id is None:
            raise EingabeFehler(
                'Die CO2-Angaben gehören zu einer Heizkostenrechnung. '
                'Wählen Sie die Anlage, die der Beleg betrifft.',
                'heizungsanlage_id')
        if (co2_roh is None) != (emission_roh is None):
            raise EingabeFehler(
                'Die CO2-Angaben gehören zusammen: tragen Sie die Kosten und '
                'die Emissionen ein oder keine von beiden.', 'co2_kosten')
    co2_kosten = co2_roh
    co2_emission_kg = (None if emission_roh is None
                       else Decimal(str(emission_roh)))

    return {
        'category_id': eingabe.ganzzahl('category_id', pflicht=True),
        'property_id': eingabe.ganzzahl('property_id', pflicht=True),
        'amount': eingabe.geldbetrag('amount', pflicht=True),
        'invoice_number': eingabe.text('invoice_number', standard='', maxlaenge=100),
        'provider_id': eingabe.ganzzahl('provider_id'),
        'start_date': eingabe.datum('start_date', pflicht=True),
        'end_date': eingabe.datum('end_date', pflicht=True),
        # Das Datum des Belegs (NK-058). Freiwillig, weil der Altbestand
        # keines traegt; die Belegliste weist es aus, wo es da ist.
        'rechnungsdatum': eingabe.datum('rechnungsdatum'),
        'document_pages': eingabe.text('document_pages', standard='', maxlaenge=100),
        'description': eingabe.text('description', standard='', maxlaenge=1000),
        'apartment_id': eingabe.ganzzahl('apartment_id'),
        'invoice_document_id': eingabe.ganzzahl('invoice_document_id'),
        'preis_ht': preis_ht,
        'preis_nt': preis_nt,
        # Die Heizkosten-Felder (NK-125): Anlage und Kostenart gehoeren
        # zusammen (D-44), und die CO2-Angaben des Belegs haben ohne Anlage
        # nichts zu suchen (die Aufteilung des § 5 CO2KostAufG rechnet die
        # Anwendung nur, wo eine Anlage Heizkosten verteilt).
        'heizungsanlage_id': eingabe.ganzzahl('heizungsanlage_id'),
        'heizkostenart': heizkostenart,
        'co2_kosten': co2_kosten,
        'co2_emission_kg': co2_emission_kg,
    }


@app.route('/api/invoices', methods=['GET'])
def get_invoices():
    invoices = CostInvoice.query.all()
    result = []
    for i in invoices:
        result.append({
            'id': i.id,
            'category_id': i.category_id,
            'category_name': i.category.name,
            'property_id': i.property_id,
            'property_name': i.property.name,
            'start_date': i.start_date.isoformat(),
            'end_date': i.end_date.isoformat(),
            'amount': i.amount,
            'invoice_number': i.invoice_number,
            'rechnungsdatum': i.rechnungsdatum.isoformat() if i.rechnungsdatum else None,
            'provider_id': i.provider_id,
            'provider_name': i.provider.name if i.provider else None,
            'document_path': i.document.document_path if i.document else i.document_path, # fallback to legacy
            'invoice_document_id': i.invoice_document_id,
            'document_pages': i.document_pages,
            'filename': i.document.filename if i.document else None,
            'description': i.description,
            'apartment_id': i.apartment_id,
            'preis_ht': i.preis_ht,
            'preis_nt': i.preis_nt,
            # Die Heizkosten-Felder (NK-125, D-44): Anlage und Posten des
            # § 7 Abs. 2 stehen an der Rechnung; die CO2-Angaben kommen
            # vom Lieferantenbeleg (D-54, uebernehmen statt rechnen).
            'heizungsanlage_id': i.heizungsanlage_id,
            'heizungsanlage_name': (i.heizungsanlage.name
                                    if i.heizungsanlage else None),
            'heizkostenart': i.heizkostenart,
            'co2_kosten': i.co2_kosten,
            'co2_emission_kg': i.co2_emission_kg,
        })
    return jsonify(result), 200

@app.route('/api/invoices', methods=['POST'])
def create_invoice():
    eingabe = Eingabe.aus_request()
    felder = _rechnungsfelder(eingabe)
    invoice_document_id = felder['invoice_document_id']

    category = CostCategory.query.get_or_404(felder['category_id'])
    prop = Property.query.get_or_404(felder['property_id'])

    document_path = None
    file = eingabe.datei('file')
    if file:
        rel_path, filename = nas_handler.save_general_document(file, prop.name)
        doc = InvoiceDocument(
            property_id=felder['property_id'],
            filename=filename,
            document_path=rel_path,
            description=f"{category.name} Rechnung",
            is_collective=False
        )
        db.session.add(doc)
        db.session.flush() # get id
        invoice_document_id = doc.id
        document_path = rel_path

    invoice = CostInvoice(
        category_id=felder['category_id'],
        property_id=felder['property_id'],
        start_date=felder['start_date'],
        end_date=felder['end_date'],
        rechnungsdatum=felder['rechnungsdatum'],
        amount=felder['amount'],
        invoice_number=felder['invoice_number'],
        provider_id=felder['provider_id'],
        invoice_document_id=invoice_document_id,
        document_path=document_path,
        document_pages=felder['document_pages'],
        description=felder['description'],
        apartment_id=felder['apartment_id'],
        preis_ht=felder['preis_ht'],
        preis_nt=felder['preis_nt'],
        heizungsanlage_id=felder['heizungsanlage_id'],
        heizkostenart=felder['heizkostenart'],
        co2_kosten=felder['co2_kosten'],
        co2_emission_kg=felder['co2_emission_kg'],
    )
    db.session.add(invoice)
    db.session.commit()
    return jsonify({'id': invoice.id}), 201

@app.route('/api/invoices/<int:id>', methods=['PUT'])
def update_invoice(id):
    invoice = CostInvoice.query.get_or_404(id)

    eingabe = Eingabe.aus_request()
    felder = _rechnungsfelder(eingabe)
    invoice_document_id = felder['invoice_document_id']

    category = CostCategory.query.get_or_404(felder['category_id'])
    prop = Property.query.get_or_404(felder['property_id'])

    if invoice_document_id:
        invoice.invoice_document_id = invoice_document_id
        invoice.document_path = None
    else:
        file = eingabe.datei('file')
        if file:
            rel_path, filename = nas_handler.save_general_document(file, prop.name)
            doc = InvoiceDocument(
                property_id=felder['property_id'],
                filename=filename,
                document_path=rel_path,
                description=f"{category.name} Rechnung",
                is_collective=False
            )
            db.session.add(doc)
            db.session.flush()
            invoice.invoice_document_id = doc.id
            invoice.document_path = rel_path

    invoice.category_id = felder['category_id']
    invoice.property_id = felder['property_id']
    invoice.amount = felder['amount']
    invoice.invoice_number = felder['invoice_number']
    invoice.provider_id = felder['provider_id']
    invoice.start_date = felder['start_date']
    invoice.end_date = felder['end_date']
    invoice.rechnungsdatum = felder['rechnungsdatum']
    invoice.document_pages = felder['document_pages']
    invoice.description = felder['description']
    invoice.apartment_id = felder['apartment_id']
    invoice.preis_ht = felder['preis_ht']
    invoice.preis_nt = felder['preis_nt']
    invoice.heizungsanlage_id = felder['heizungsanlage_id']
    invoice.heizkostenart = felder['heizkostenart']
    invoice.co2_kosten = felder['co2_kosten']
    invoice.co2_emission_kg = felder['co2_emission_kg']
    
    db.session.commit()
    return jsonify({'id': invoice.id}), 200

@app.route('/api/invoices/<int:id>', methods=['DELETE'])
def delete_invoice(id):
    invoice = CostInvoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    return jsonify({'message': 'deleted'})

# --- Billing Logic ---
@app.route('/api/billing/suggestions', methods=['GET'])
def billing_suggestions():
    tenants = Tenant.query.filter(
        db.or_(Tenant.move_out_date == None, Tenant.move_out_date > datetime(2000, 1, 1).date()),
        Tenant.gesperrt_bis.is_(None)).all()
    suggestions = []
    all_categories = CostCategory.query.all()
    
    for t in tenants:
        tenant_categories = []
        has_invoices = False
        min_start = None
        max_end = None
        
        for cat in all_categories:
            cost_profile = TenantCostProfile.query.filter_by(tenant_id=t.id, category_id=cat.id).first()
            if cost_profile and cost_profile.billing_type == 'ignoriert':
                continue
                
            last_cat_report = BillingReportCategory.query.join(TenantBillingReport).filter(
                TenantBillingReport.tenant_id == t.id,
                BillingReportCategory.category_id == cat.id
            ).order_by(BillingReportCategory.end_date.desc()).first()
            
            billed_until = last_cat_report.end_date if last_cat_report else None
            
            latest_report = TenantBillingReport.query.filter_by(tenant_id=t.id).order_by(TenantBillingReport.end_date.desc()).first()
            global_billed = t.last_billed_until
            if latest_report and (not global_billed or latest_report.end_date > global_billed):
                global_billed = latest_report.end_date
                
            if global_billed:
                if not billed_until or global_billed > billed_until:
                    billed_until = global_billed
            
            if billed_until:
                start_date = max(t.move_in_date, billed_until + timedelta(days=1))
                query_date = billed_until
            else:
                start_date = t.move_in_date
                query_date = t.move_in_date - timedelta(days=1)
            
            invoices = CostInvoice.query.filter(
                CostInvoice.property_id == t.apartment.property_id,
                CostInvoice.category_id == cat.id,
                CostInvoice.end_date > query_date
            ).all()
            
            if invoices:
                has_invoices = True
                cat_max_end = min(max([i.end_date for i in invoices]), datetime.today().date())
                jahresgrenze = ein_jahr_nach(start_date)
                if grenze(cat_max_end) > jahresgrenze:
                    cat_max_end = letzter_tag(jahresgrenze)
                
                if not min_start or start_date < min_start:
                    min_start = start_date
                if not max_end or cat_max_end > max_end:
                    max_end = cat_max_end
                    
                tenant_categories.append({
                    'category_id': cat.id,
                    'category_name': cat.name,
                    'suggested_start': start_date.isoformat(),
                    'suggested_end': cat_max_end.isoformat(),
                    'invoice_count': len(invoices)
                })
        
        if has_invoices:
            suggestions.append({
                'tenant_id': t.id,
                'tenant_name': t.name,
                'apartment_name': t.apartment.name,
                'suggested_start': min_start.isoformat() if min_start else None,
                'suggested_end': max_end.isoformat() if max_end else None,
                'categories': tenant_categories
            })
            
    return jsonify(suggestions), 200

from nebenkostenfix.billing_engine import BillingEngine, BillingDataError


def _abrechnungsauftrag(eingabe):
    """Mieter, Zeitraum und Kostenarten, wie sie alle drei Abrechnungsrouten lesen.

    Die drei lasen dieselben vier Felder in drei gleichen Bloecken und sagten
    bei einer Luecke "Missing parameters". Ein krummes Datum kam dort gar
    nicht erst an: strptime warf einen ValueError, also eine 500.

    Die Datumswerte gehen als Zeichenkette zurueck, weil BillingEngine sie so
    erwartet. Umgewandelt wurden sie trotzdem, sonst waere die Pruefung keine.
    """
    tenant_id = eingabe.ganzzahl('tenant_id', pflicht=True)
    start = eingabe.datum('start_date', pflicht=True)
    ende = eingabe.datum('end_date', pflicht=True)
    category_ids = eingabe.ganzzahlliste('category_ids')
    return tenant_id, start.isoformat(), ende.isoformat(), category_ids


def _gekuerztes_ende(s_date, e_date):
    """Der Abrechnungszeitraum, wie ihn die Erzeugung wirklich rechnet.

    NK-054 holt das gemeinsame Ende-Kuerzen aus generate und finalize an
    eine Stelle und legt es der Vorpruefung in den Arm: die Kacheln zum
    Zeitraum und zur Frist muessen denselben Zeitraum sehen, den spaeter
    abgerechnet wird, sonst warnen sie ueber etwas anderes als gerechnet
    wird. Nicht nach vorne (heute).

    Ueber die Jahresgrenze wird nicht mehr gekuerzt (F-112): das Kuerzen
    geschah stillschweigend, der Vermieter gab den 30.09. ein und bekam den
    31.08. abgerechnet, ohne es zu sehen. Ein laengerer Zeitraum ist nach
    § 556 Abs. 3 BGB angreifbar, aber seine Entscheidung --
    ``_ueberlaenge_warnung`` sagt es ihm, die Erzeugung laeuft weiter.
    """
    if e_date > datetime.today().date():
        e_date = datetime.today().date()
    return e_date


def _ueberlaenge_warnung(vorgang):
    """Der Hinweis, wenn der Zeitraum laenger als ein Jahr ist -- oder None.

    Gemessen am gestutzten Vorgang (Einzug, Auszug), nicht am Auftrag: ein
    Auftrag ueber 19 Monate fuer einen Mieter, der erst seit 12 Monaten
    wohnt, rechnet ein Jahr und braucht keinen Hinweis.
    """
    if vorgang.ende_grenze <= ein_jahr_nach(vorgang.beginn):
        return None
    return (f'Der Abrechnungszeitraum umfasst {tage(vorgang.beginn, vorgang.ende_grenze)} '
            'Tage und ist damit länger als ein Jahr. Nach § 556 Abs. 3 BGB '
            'wird jährlich abgerechnet; ein längerer Zeitraum kann angefochten '
            'werden. Die Abrechnung wird trotzdem erstellt.')


def _ueberlappung(tenant_id, s_date, e_date, category_ids):
    """Die erste Abrechnung, die sich mit dem Zeitraum deckt -- oder None.

    Bei Kostenarten zaehlt nur die Deckung derselben Kostenart (die zweite
    PDF-Art darf denselben Zeitraum bekommen); ohne Kostenarten deckt
    schon irgendeine Abrechnung des Mieters.
    """
    if category_ids:
        return BillingReportCategory.query.join(TenantBillingReport).filter(
            TenantBillingReport.tenant_id == tenant_id,
            BillingReportCategory.category_id.in_(category_ids),
            BillingReportCategory.start_date <= e_date,
            BillingReportCategory.end_date >= s_date
        ).first()
    return TenantBillingReport.query.filter(
        TenantBillingReport.tenant_id == tenant_id,
        TenantBillingReport.start_date <= e_date,
        TenantBillingReport.end_date >= s_date
    ).first()


def _pruefkachel(kategorie, art, status, blocking, message):
    """Eine Kachel in der Form der Rechenkern-Vorpruefung.

    Die Felder, die es hier nicht gibt, bleiben NULL -- die Oberflaeche
    rendert jede Kachel aus derselben Form (NK-054).
    """
    return {
        'category': kategorie,
        'meter_type': art,
        'meter_number': None,
        'meter_id': None,
        'apartment': None,
        'invoice_period': None,
        'status': status,
        'blocking': blocking,
        'message': message,
        'r_start': None,
        'r_end': None,
        'start_offset_days': None,
        'end_offset_days': None,
        'reading_span_days': None,
        'target_days': None,
        'is_interpolated': False,
    }


def _zeitraum_tiles(tenant_id, s_date, e_date, category_ids):
    """Vorpruefungskacheln zum Abrechnungszeitraum (R-FRIST-01, NK-054).

    Ueberschneidung und Luecke "muessen als Fehler erkennbar sein". Die
    Ueberschneidung ist es doppelt: Kachel hier, und die Erzeugung sagt
    mit 400 ab -- dieselbe Regel an zwei Stellen, weil der Vermieter die
    Abrechnung auch ohne vorherige Vorpruefung anstossen kann (NK-096).
    Die Luecke wird nur gewarnt: eine Teilabrechnung je Kostenart ist
    rechtmassig, und ueber unbebillte Tage darf spaeter ein eigener
    Zeitraum abgerechnet werden -- die Software sagt hier nicht ab.
    """
    tiles = []
    ueberlappende = _ueberlappung(tenant_id, s_date, e_date, category_ids)
    if ueberlappende:
        tiles.append(_pruefkachel(
            'Zeitraum', '§ 556 Abs. 3 BGB', 'no_data', True,
            'Der Zeitraum überschneidet sich mit der Abrechnung vom '
            f'{ueberlappende.start_date:%d.%m.%Y} bis '
            f'{ueberlappende.end_date:%d.%m.%Y}. Über dieselben Tage wird '
            'nicht doppelt abgerechnet.'))
        return tiles

    # Luecke: was deckt der Bestand fuer diesen Mieter schon ab? Massgeblich
    # ist das spaeteste Ende aus Abrechnungen und Kostenart-Berichten --
    # genau die Zahl, mit der die Vorschlaege weiterrechnen.
    letzte = db.session.query(
        db.func.max(TenantBillingReport.end_date)).filter_by(
        tenant_id=tenant_id).scalar()
    letzte_kostenart = db.session.query(
        db.func.max(BillingReportCategory.end_date)).join(
        TenantBillingReport).filter(
        TenantBillingReport.tenant_id == tenant_id).scalar()
    enden = [v for v in (letzte, letzte_kostenart) if v is not None]
    if enden:
        letztes_ende = max(enden)
        luecke = (s_date - letztes_ende).days - 1
        if luecke > 0:
            tiles.append(_pruefkachel(
                'Zeitraum', '§ 556 Abs. 3 BGB', 'warning', False,
                'Zwischen der letzten Abrechnung (bis '
                f'{letztes_ende:%d.%m.%Y}) und diesem Zeitraum liegen '
                f'{luecke} Tage ohne Abrechnung. Diese Tage bleiben sonst '
                'unberücksichtigt; prüfen Sie, ob sie in einen der '
                'Zeiträume gehören.'))
    return tiles


def _frist_tiles(e_date):
    """Vorpruefungskachel zur Abrechnungsfrist (R-FRIST-02, NK-054).

    Die Software blockiert nie, sie vermerkt: auch nach Ablauf der Frist
    darf die Abrechnung erzeugt werden. Die Kachel erscheint nur, wenn es
    etwas zu sagen gibt.
    """
    stand = frist_status(e_date)
    if stand['warnung'] is None:
        return []
    return [_pruefkachel(
        'Frist', '§ 556 Abs. 3 BGB', 'warning', False, stand['warnung'])]


@app.route('/api/billing/preflight', methods=['POST'])
def billing_preflight():
    eingabe = Eingabe.aus_request()
    tenant_id, start_date, end_date, category_ids = _abrechnungsauftrag(eingabe)

    s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    e_date = _gekuerztes_ende(s_date, datetime.strptime(end_date, '%Y-%m-%d').date())

    # Dasselbe Ende wie die Erzeugung, sonst prueft die Vorpruefung einen
    # anderen Zeitraum, als spaeter gerechnet wird.
    engine = BillingEngine(tenant_id, start_date, e_date.isoformat())
    result = engine.preflight_check()
    ueberlaenge = _ueberlaenge_warnung(engine.vorgang)

    # Pruefklassen Zeitraum und Frist (R-FRIST-01/02, NK-054). Sie haengen
    # nicht am Rechenkern: der kennt keinen Datenbestand und kein Datum von
    # heute. Das Wissen "welche Abrechnungen gibt es schon" lebt hier.
    result['checks'] = (result['checks']
                        + _zeitraum_tiles(tenant_id, s_date, e_date, category_ids)
                        + _frist_tiles(e_date))
    if ueberlaenge:
        result['checks'].append(_pruefkachel(
            'Zeitraum', '§ 556 Abs. 3 BGB', 'warning', False, ueberlaenge))
    statuses = [c['status'] for c in result['checks']]
    if 'warning' in statuses or 'no_data' in statuses:
        result['overall'] = 'warning'
    elif 'acceptable' in statuses:
        result['overall'] = 'acceptable'
    elif result['checks']:
        result['overall'] = 'excellent'
    return jsonify(result), 200

@app.route('/api/billing/generate', methods=['POST'])
def generate_bill():
    eingabe = Eingabe.aus_request()
    tenant_id, start_date, end_date, category_ids = _abrechnungsauftrag(eingabe)

    s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    e_date = _gekuerztes_ende(s_date, datetime.strptime(end_date, '%Y-%m-%d').date())
        
    end_date = e_date.strftime('%Y-%m-%d')

    if _ueberlappung(tenant_id, s_date, e_date, category_ids):
        return jsonify({'error': f'Abrechnung überschneidet sich mit existierendem Zeitraum.'}), 400
        
    engine = BillingEngine(tenant_id, start_date, end_date, category_ids)
    try:
        bill_data = engine.calculate_bill()
    except BillingDataError as e:
        # Fehlende Stammdaten sind ein Eingabefehler des Vermieters, kein
        # Serverfehler. 400 mit deutschem Klartext statt 500 (NK-027).
        return jsonify({'error': str(e)}), 400

    # Die Abrechnungsfrist gehoert ins Ergebnis (R-FRIST-02, NK-054): das
    # Fristende ist berechenbar, der Zustand beim Erzeugen wird als Flag
    # mitgegeben, und die Warnung landet bei den anderen Warnungen. Die
    # Erzeugung selbst wird nicht blockiert -- ob der Vermieter die
    # Verspaetung zu vertreten hat, beurteilt die Software nicht.
    stand = frist_status(e_date)
    bill_data['frist_ende'] = stand['frist_ende'].isoformat()
    bill_data['frist_ueberschritten'] = stand['ueberschritten']
    if stand['warnung']:
        bill_data['warnings'].append(stand['warnung'])
    ueberlaenge = _ueberlaenge_warnung(engine.vorgang)
    if ueberlaenge:
        bill_data['warnings'].append(ueberlaenge)
    
    return jsonify(bill_data), 200

from nebenkostenfix.pdf_generator import PDFGenerator
import zipfile
from io import BytesIO

@app.route('/api/billing/finalize', methods=['POST'])
def finalize_bill():
    eingabe = Eingabe.aus_request()
    tenant_id, start_date, end_date, category_ids = _abrechnungsauftrag(eingabe)

    s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    e_date = _gekuerztes_ende(s_date, datetime.strptime(end_date, '%Y-%m-%d').date())
        
    end_date = e_date.strftime('%Y-%m-%d')
    
    # Die Frist gehoert in das Erzeugungsprotokoll (R-FRIST-02, NK-054):
    # ueberschritten heisst nicht abgelehnt, aber der Vermieter liest nach,
    # was die Software gewusst hat.
    stand = frist_status(e_date)
    if stand['ueberschritten']:
        protokoll.warning(
            'Frist ueberschritten: Abrechnung fuer Mieter %s, Zeitraum bis '
            '%s, Fristende war %s, erzeugt am %s.',
            tenant_id, end_date, stand['frist_ende'].isoformat(),
            datetime.today().date().isoformat())
    
    is_detailed = eingabe.wahrheit('detailed')
    
    # --- Dual-PDF overlap logic ---
    # Find existing report for the same tenant + period
    existing_report = None
    if category_ids:
        overlapping_cat = BillingReportCategory.query.join(TenantBillingReport).filter(
            TenantBillingReport.tenant_id == tenant_id,
            BillingReportCategory.category_id.in_(category_ids),
            BillingReportCategory.start_date <= e_date,
            BillingReportCategory.end_date >= s_date
        ).first()
        if overlapping_cat:
            existing_report = overlapping_cat.report
    else:
        existing_report = TenantBillingReport.query.filter(
            TenantBillingReport.tenant_id == tenant_id,
            TenantBillingReport.start_date <= e_date,
            TenantBillingReport.end_date >= s_date
        ).first()
    
    # Check if the requested PDF type already exists on the existing report
    if existing_report:
        if is_detailed and existing_report.document_path_detailed:
            return jsonify({'error': 'Die detaillierte PDF für diesen Zeitraum existiert bereits.'}), 400
        elif not is_detailed and existing_report.document_path:
            return jsonify({'error': 'Die einfache PDF für diesen Zeitraum existiert bereits.'}), 400
        # Otherwise, the OTHER type exists → we can add the missing one
        
    # Calculate
    engine = BillingEngine(tenant_id, start_date, end_date, category_ids)
    try:
        bill_data = engine.calculate_bill()
    except BillingDataError as e:
        return jsonify({'error': str(e)}), 400
    
    # Generate PDF (NK-057: ein Generator, der Umfang steht auf dem Schalter)
    pdf_gen = PDFGenerator(
        property_name=bill_data['property'],
        apartment_name=bill_data['apartment'],
        tenant_name=bill_data['tenant_name'],
        start_date=bill_data['start_date'],
        end_date=bill_data['end_date'],
        detailliert=is_detailed
    )
    
    # Kein eigenes try mehr (NK-030): der zentrale Handler rollt zurueck,
    # schreibt den Stapelabzug unter einer Vorgangsnummer ins Protokoll und
    # antwortet deutsch. Vorher ging der Abzug per print heraus und der
    # Vermieter bekam "PDF Error: list index out of range" zu lesen.
    # NK-064: das Anschreiben des Objekts (oder der Vorgabetext) spricht
    # auf dem Deckblatt, mit den Zahlen aus diesem Ergebnis.
    anschreiben_text = _anschreiben_fuer(Tenant.query.get(tenant_id), bill_data)
    pdf_bytes = pdf_gen.generate(
        bill_data['line_items'],
        bill_data['total_amount'],
        bill_data.get('prepaid_amount', NULL),
        # NK-060: der Ausweis des § 7 CO2KostAufG und der Vermieteranteil
        # (R-NUM-05) gehoeren in den Heizkosten- und CO2-Abschnitt des Blatts.
        co2_ausweis=bill_data.get('co2'),
        landlord_share=bill_data.get('landlord_share'),
        anschreiben=anschreiben_text,
    )
        
    # Save to NAS with type-specific filename
    tenant = Tenant.query.get(tenant_id)
    prop = tenant.apartment.property
    start_fmt = datetime.fromisoformat(bill_data['start_date']).strftime('%Y%m%d')
    end_fmt = datetime.fromisoformat(bill_data['end_date']).strftime('%Y%m%d')
    suffix = "_Detailliert" if is_detailed else "_Einfach"
    filename = f"Nebenkostenabrechnung_{tenant.name.replace(' ', '_')}_{start_fmt}-{end_fmt}{suffix}.pdf"
    
    class DummyFile:
        def __init__(self, name, content):
            self.filename = name
            self.content = content
        def save(self, path):
            with open(path, 'wb') as f:
                f.write(self.content)
            
    pdf_path, saved_name = nas_handler.save_billing_report(DummyFile(filename, pdf_bytes), prop.name, tenant.apartment.name, tenant.name)
    
    if existing_report:
        # Update existing report with the second PDF path
        if is_detailed:
            existing_report.document_path_detailed = pdf_path
        else:
            existing_report.document_path = pdf_path
        db.session.commit()
        return jsonify({'message': 'PDF erfolgreich hinzugefügt', 'pdf_path': pdf_path, 'filename': saved_name}), 201
    else:
        # Create new report
        report = TenantBillingReport(
            tenant_id=tenant_id,
            start_date=datetime.fromisoformat(start_date).date(),
            end_date=datetime.fromisoformat(end_date).date(),
            # Das Fristende wird mit der Abrechnung geboren (R-FRIST-02,
            # NK-054): AZ-Ende + 12 Monate, unabhaengig davon, wann und ob
            # zugestellt wird. Das Zustelldatum traegt der Vermieter nach.
            frist_ende=stand['frist_ende'],
            document_path=pdf_path if not is_detailed else None,
            document_path_detailed=pdf_path if is_detailed else None
        )
        db.session.add(report)
        db.session.flush() # to get report.id
        
        # Save Categories
        final_category_ids = category_ids
        if not final_category_ids:
            # If no explicit categories passed, assume all categories that were billed in line_items
            cats_billed = set([item['category'] for item in bill_data['line_items']])
            all_cats = CostCategory.query.filter(CostCategory.name.in_(cats_billed)).all()
            final_category_ids = [c.id for c in all_cats]
            
        for cid in final_category_ids:
            rc = BillingReportCategory(
                report_id=report.id,
                category_id=cid,
                start_date=report.start_date,
                end_date=report.end_date
            )
            db.session.add(rc)

        # Die erste Version entsteht mit der Festsetzung (R-DOC-02, NK-061):
        # Eingangsdaten und Ergebnis werden festgehalten, damit die Abrechnung
        # nicht stillschweigend anders berechnet werden kann, wenn sich später
        # Stammdaten ändern. Die Detailroute liefert ab hier den Schnappschuss.
        eingangsdaten, ergebnis = schnappschuss(engine.vorgang, bill_data)
        db.session.add(BillingReportVersion(
            report_id=report.id,
            nummer=1,
            eingangsdaten=eingangsdaten,
            ergebnis=ergebnis,
            software_version=SOFTWARE_VERSION,
            regel_version=REGEL_VERSION,
        ))

        db.session.commit()
        
        return jsonify({'message': 'Abrechnung erfolgreich erstellt', 'pdf_path': pdf_path, 'filename': saved_name}), 201

def _vermieter_stand():
    """Der Ausweis des Vermieters samt Herkunft je Feld (NK-124).

    "datenbank" heißt: die Oberflaeche hat ihn gespeichert; "umgebung":
    die Variablen des Bestands (D-81); "fehlt": beides leer. GET und PUT
    antworten mit demselben Stand — nach dem Speichern sieht die
    Oberflaeche sofort, was jetzt gilt.
    """
    zeile = Vermieterdaten.einziger()
    name_tabelle = (zeile.name or '').strip() if zeile else ''
    iban_tabelle = (zeile.iban or '').strip() if zeile else ''
    name_umgebung = os.environ.get('VERMIETER_NAME', '').strip()
    iban_umgebung = iban_saeubern(os.environ.get('VERMIETER_IBAN', ''))
    name = name_tabelle or name_umgebung
    iban = iban_tabelle or iban_umgebung

    def quelle(tab, umg):
        return 'datenbank' if tab else ('umgebung' if umg else 'fehlt')

    return {
        'name': name,
        'iban': iban,
        'name_quelle': quelle(name_tabelle, name_umgebung),
        'iban_quelle': quelle(iban_tabelle, iban_umgebung),
        'girocode_bereit': bool(name and iban),
        'logo': vermieter_logo.pfad() is not None,
    }


@app.route('/api/haftung', methods=['GET'])
def haftung_anzeigen():
    """Der Haftungshinweis und ob diese Fassung bestaetigt ist (NK-174)."""
    return jsonify(haftung.stand())


@app.route('/api/haftung', methods=['POST'])
def haftung_bestaetigen():
    """„Verstanden“ im Hinweis der App: bestaetigt nur die aktuelle Fassung."""
    daten = request.get_json(silent=True) or {}
    if daten.get('version') != haftung.VERSION:
        return jsonify({'error': 'Der Hinweis hat sich geändert. Bitte lesen Sie '
                                 'ihn noch einmal.'}), 409
    haftung.bestaetigen()
    return jsonify(haftung.stand())


@app.route('/api/ueber', methods=['GET'])
def ueber_anzeigen():
    """„Über NebenkostenFix“ im Hilfe-Tab (NK-179): Stand, feste Adressen,
    Haftungshinweis. Nichts aus der Datenbank."""
    if aktualisierung.paketmodus():
        weg = 'Microsoft Store'
    elif app.config.get('DESKTOP'):
        weg = 'Windows-App'
    else:
        weg = 'Docker'
    system = f'{platform.system()} {platform.release()}'
    return jsonify({
        'version': SOFTWARE_VERSION, 'weg': weg,
        'projektseite': marke.REPO_URL, 'neuigkeiten': marke.NEUIGKEITEN_URL,
        'fehler_melden': marke.fehler_melden_url(SOFTWARE_VERSION, weg, system),
        'unterstuetzen': marke.KOFI_URL, 'lizenz': marke.LIZENZ_URL,
        'haftung': list(haftung.TEXT)})


@app.route('/api/drittlizenzen', methods=['GET'])
def drittlizenzen_anzeigen():
    """Lizenzen der mitgelieferten Drittsoftware im Über-Dialog (NK-148)."""
    antwort = make_response(drittlizenzen.lesen())
    antwort.mimetype = 'text/plain'
    return antwort


def _update_einstellung():
    return {'automatisch': einstellungen.lesen()['updates_automatisch'],
            'paketmodus': aktualisierung.paketmodus(),
            'desktop': bool(app.config.get('DESKTOP'))}


@app.route('/api/aktualisierung/einstellung', methods=['GET'])
def update_einstellung_anzeigen():
    return jsonify(_update_einstellung())


@app.route('/api/aktualisierung/einstellung', methods=['PUT'])
def update_einstellung_setzen():
    """„Automatisch nach Updates suchen“ (NK-175), ab Werk an."""
    daten = request.get_json(silent=True) or {}
    if not isinstance(daten.get('automatisch'), bool):
        return jsonify({'error': 'Bitte an oder aus wählen.'}), 400
    einstellungen.schreiben(updates_automatisch=daten['automatisch'])
    return jsonify(_update_einstellung())


@app.route('/api/aktualisierung/automatisch', methods=['GET'])
def aktualisierung_automatisch():
    """Die Suche beim Start (NK-175): hoechstens alle 24 Stunden, still bei
    jedem Fehler. ``neu: false`` heisst: nichts zeigen."""
    ergebnis = aktualisierung.automatisch(
        SOFTWARE_VERSION, desktop=bool(app.config.get('DESKTOP')))
    return jsonify(ergebnis or {'neu': False})


@app.route('/api/aktualisierung', methods=['GET'])
def aktualisierung_suchen():
    """Nach Updates suchen auf Knopfdruck (NK-081, NK-175)."""
    try:
        ergebnis = aktualisierung.suchen(
            SOFTWARE_VERSION, desktop=bool(app.config.get('DESKTOP')))
    except AktualisierungsFehler as fehler:
        return jsonify({'error': str(fehler)}), 400
    except OSError:
        app.logger.warning('Update-Quelle nicht erreichbar', exc_info=True)
        return jsonify({'error': 'Die Update-Quelle ist nicht erreichbar. Prüfen Sie '
                                 'die Internetverbindung und versuchen Sie es später.'}), 502
    return jsonify(ergebnis)


@app.route('/api/aktualisierung/installieren', methods=['POST'])
def aktualisierung_installieren():
    """Windows-App: Installer laden, pruefen, Daten sichern, starten (NK-081,
    NK-175). Er schliesst die App selbst und installiert ueber die bestehende
    Installation."""
    if not app.config.get('DESKTOP'):
        return jsonify({'error': 'Installieren geht nur in der Windows-App. Im '
                                 'Docker-Betrieb aktualisieren Sie das Abbild.'}), 400
    from nebenkostenfix import backup

    try:
        datei = aktualisierung.installer_laden(SOFTWARE_VERSION)
        backup.sicherung_erstellen(
            app, datenordner.sicherungsordner(), praefix='sicherung-vor-update')
        aktualisierung.installer_starten(datei)
    except (AktualisierungsFehler, backup.SicherungsFehler) as fehler:
        return jsonify({'error': str(fehler)}), 400
    except OSError:
        app.logger.warning('Update nicht ladbar', exc_info=True)
        return jsonify({'error': 'Das Update ließ sich nicht laden. Ihre installierte '
                                 'Version bleibt unverändert.'}), 502
    app.logger.info('Update-Installer gestartet (NK-175).')
    return jsonify({'text': 'Ihre Daten sind gesichert, der Installer startet. Die '
                            'Anwendung schließt sich dafür kurz und kommt mit der '
                            'neuen Version wieder.'})


@app.route('/api/vermieter', methods=['GET'])
def get_vermieterdaten():
    """Der Ausweis des Vermieters fuer Deckblatt und GiroCode (NK-124).

    Die Antwort nennt je Feld, woher der Stand kommt — der Vermieter
    sieht so nicht nur die Werte, sondern auch, ob sein Eintrag
    wirklich drin ist.
    """
    return jsonify(_vermieter_stand())


@app.route('/api/vermieter', methods=['PUT'])
def setze_vermieterdaten():
    """Nimmt Name und IBAN aus der Oberflaeche (NK-124).

    Leeres Feld heißt: den gespeicherten Stand loeschen — die Umgebung
    tritt dann wieder ein, und wer alles leert, bekommt weiter keinen
    GiroCode, aber keine verlorene Zeile. Die IBAN wird auf Form und
    Pruefsumme geprueft, bevor sie steht: ein Vertipper faellt hier auf,
    nicht erst bei der Bank des Mieters.
    """
    eingabe = Eingabe.aus_request()
    name = eingabe.text('name', standard='', maxlaenge=200).strip()
    iban_roh = eingabe.text('iban', standard='', maxlaenge=50)

    zeile = Vermieterdaten.einziger()
    if zeile is None:
        zeile = Vermieterdaten()
        db.session.add(zeile)

    zeile.name = name or None
    zeile.iban = iban_pruefen(iban_roh) if iban_roh.strip() else None
    zeile.aktualisiert_am = date.today()
    db.session.commit()
    return jsonify(_vermieter_stand())


@app.route('/api/vermieter/logo', methods=['GET'])
def vermieter_logo_zeigen():
    """Das Logo des Vermieters für die Vorschau (NK-155)."""
    datei = vermieter_logo.pfad()
    if datei is None:
        return jsonify({'error': 'Es ist kein Logo hinterlegt.'}), 404
    # Aus dem Speicher statt send_file: unter Windows hielte die noch offene
    # Antwort die Datei fest, und "Logo löschen" scheiterte (WinError 32).
    inhalt = datei.read_bytes()
    antwort = make_response(inhalt)
    antwort.mimetype = uploads.ERLAUBT[uploads.erkenne(inhalt[:uploads.KOPF_BYTES])]
    antwort.headers['Content-Security-Policy'] = uploads.CSP_BILD
    antwort.headers['X-Content-Type-Options'] = 'nosniff'
    antwort.headers['Cache-Control'] = 'private, no-store'
    return antwort


@app.route('/api/vermieter/logo', methods=['POST'])
def vermieter_logo_hochladen():
    """Nimmt ein Logo (PNG/JPEG) für das Deckblatt der Abrechnung."""
    datei = request.files.get('logo')
    if datei is None or not datei.filename:
        return jsonify({'error': 'Bitte wählen Sie eine Bilddatei aus.'}), 400
    vermieter_logo.speichern(datei)
    app.logger.info('Vermieterlogo hinterlegt (NK-155).')
    return jsonify({'logo': True}), 201


@app.route('/api/vermieter/logo', methods=['DELETE'])
def vermieter_logo_loeschen():
    geloescht = vermieter_logo.loeschen()
    return jsonify({'logo': False, 'geloescht': geloescht})


@app.route('/api/export', methods=['GET', 'POST'])
def export_data():
    """Alle Daten als JSON. Per POST mit ``passphrase`` verschluesselt
    (NK-130, D-86): eine Datei .nkexp, lesbar mit
    ``flask backup entschluesseln`` oder dem Modul verschluesselung."""
    def to_dict(model_obj):
        d = {}
        for c in model_obj.__table__.columns:
            val = getattr(model_obj, c.name)
            if hasattr(val, 'isoformat'):
                val = val.isoformat()
            d[c.name] = val
        return d
        
    data = {
        'providers': [to_dict(x) for x in Provider.query.all()],
        'properties': [to_dict(x) for x in Property.query.all()],
        'apartments': [to_dict(x) for x in Apartment.query.all()],
        'tenants': [to_dict(x) for x in Tenant.query.all()],
        'cost_categories': [to_dict(x) for x in CostCategory.query.all()],
        'cost_invoices': [to_dict(x) for x in CostInvoice.query.all()],
        'invoice_documents': [to_dict(x) for x in InvoiceDocument.query.all()],
        'meters': [to_dict(x) for x in Meter.query.all()],
        'meter_readings': [to_dict(x) for x in MeterReading.query.all()],
        'tenant_cost_profiles': [to_dict(x) for x in TenantCostProfile.query.all()],
        'haushaltsgroessen': [to_dict(x) for x in Haushaltsgroesse.query.all()],
        'tenant_billing_reports': [to_dict(x) for x in TenantBillingReport.query.all()]
    }
    if request.method == 'GET':
        return jsonify(data)
    passphrase = (request.get_json(silent=True) or {}).get('passphrase')
    try:
        verschluesselung.passphrase_pruefen(passphrase)
    except verschluesselung.VerschluesselungsFehler as fehler:
        raise EingabeFehler(str(fehler), 'passphrase') from fehler
    heute = date.today().isoformat()
    with tempfile.TemporaryDirectory(prefix='nk-export-') as arbeit:
        klar = os.path.join(arbeit, 'export.json')
        with open(klar, 'w', encoding='utf-8') as datei:
            json.dump(data, datei, ensure_ascii=False, indent=2, default=str)
        ziel = os.path.join(arbeit, 'export.nkexp')
        verschluesselung.verschluesseln(klar, ziel, passphrase, {
            'anwendung': 'nebenkostenabrechnung', 'art': 'export',
            'erstellt_am': datetime.now().astimezone().isoformat(timespec='seconds'),
        })
        with open(ziel, 'rb') as datei:
            inhalt = datei.read()
    return send_file(io.BytesIO(inhalt), mimetype='application/octet-stream',
                     as_attachment=True,
                     download_name=f'nebenkosten-export-{heute}.nkexp')

@app.route('/api/billing/reports', methods=['GET'])
def get_all_billing_reports():
    reports = (TenantBillingReport.query.join(Tenant)
               .filter(Tenant.gesperrt_bis.is_(None))
               .order_by(TenantBillingReport.created_at.desc()).all())
    res = []
    for r in reports:
        res.append({
            'id': r.id,
            'tenant_id': r.tenant_id,
            'tenant_name': r.tenant.name,
            'property_name': r.tenant.apartment.property.name,
            'apartment_name': r.tenant.apartment.name,
            'start_date': r.start_date.isoformat(),
            'end_date': r.end_date.isoformat(),
            'created_at': zeit.als_ortszeit(r.created_at),
            'document_path': r.document_path,
            'document_path_detailed': r.document_path_detailed
        })
    return jsonify(res)

@app.route('/api/tenants/<int:id>/billing_reports', methods=['GET'])
def get_tenant_billing_reports(id):
    reports = TenantBillingReport.query.filter_by(tenant_id=id).order_by(TenantBillingReport.created_at.desc()).all()
    res = []
    for r in reports:
        res.append({
            'id': r.id,
            'start_date': r.start_date.isoformat(),
            'end_date': r.end_date.isoformat(),
            'created_at': zeit.als_ortszeit(r.created_at),
            'document_path': r.document_path,
            'document_path_detailed': r.document_path_detailed
        })
    return jsonify(res)

@app.route('/api/billing/reports/<int:id>', methods=['DELETE'])
def delete_billing_report(id):
    report = TenantBillingReport.query.get_or_404(id)
    if report.document_path:
        nas_handler.delete_file(report.document_path)
    if report.document_path_detailed:
        nas_handler.delete_file(report.document_path_detailed)
    db.session.delete(report)
    db.session.commit()
    return jsonify({'message': 'Abrechnung erfolgreich gelöscht'})

@app.route('/api/billing/reports/<int:id>/download', methods=['GET'])
def download_billing_report(id):
    report = TenantBillingReport.query.get_or_404(id)
    if not report.document_path:
        return jsonify({'error': 'Zu dieser Abrechnung gibt es kein PDF.'}), 404
        
    pfad = uploads.pfad_aufloesen(nas_handler.nas_mount_path, report.document_path)
    if pfad is None:
        return jsonify({'error': 'Die Datei liegt nicht (mehr) im Belegordner.'}), 404
    antwort = uploads.ausliefern(pfad)
    antwort.headers['Content-Disposition'] = \
        antwort.headers['Content-Disposition'].replace('inline', 'attachment', 1)
    return antwort

@app.route('/api/billing/reports/<int:id>/zustellung', methods=['POST'])
def zustellung_melden(id):
    """Der Vermieter traegt nach, wann die Abrechnung beim Mieter war.

    R-FRIST-02 (NK-054): massgeblich ist der Zugang beim Mieter, nicht das
    Erstellungsdatum -- und nur der Vermieter kennt ihn. Die Antwort
    nennt die Einwendungsfrist des Mieters, informativ (R-FRIST-03): sie
    wirkt auf keine Zahl. Seit F-37 warnt sie auch, wenn der Zugang erst
    nach dem Ende der Nachforderungsfrist lag.
    """
    eingabe = Eingabe.aus_request()
    datum = eingabe.datum('zugestellt_am', pflicht=True)
    report = TenantBillingReport.query.get_or_404(id)

    heute = datetime.today().date()
    if datum > heute:
        return jsonify({'error': 'Die Zustellung kann nicht in der Zukunft liegen.'}), 400
    # created_at kommt aus der Tabelle: Zeilen, die die Anwendung anlegt,
    # tragen eine Uhrzeit (datetime, UTC); Zeilen aus alten Sicherungen
    # koennen ein reines Datum sein. Massgeblich ist der Tag, den der
    # Vermieter in Berlin liest -- bei UTC kurz nach Mitternacht kann das
    # der Folgetag sein.
    erstellt = zeit.als_ortsdatum(report.created_at)
    if datum < erstellt:
        return jsonify({'error': 'Die Abrechnung wurde erst am '
                        f'{erstellt:%d.%m.%Y} erstellt; sie kann nicht '
                        'davor zugestellt worden sein.'}), 400
    if datum <= report.end_date:
        return jsonify({'error': 'Vor dem Ende des Abrechnungszeitraums '
                        f'({report.end_date:%d.%m.%Y}) kann keine Abrechnung '
                        'zugestellt werden.'}), 400

    report.zugestellt_am = datum
    db.session.commit()
    # F-37: der Zugang kann nach dem Ende der Nachforderungsfrist liegen,
    # obwohl die Erzeugung noch rechtzeitig war -- erst hier ist das
    # bekannt. Die Warnung ist informativ (R-FRIST-03) und wird nicht
    # gespeichert; sie gilt für die Antwort, nicht für den Datensatz.
    warnung = zustellwarnung(datum, report.end_date)
    return jsonify({
        'message': 'Zustellung gespeichert.',
        'zugestellt_am': datum.isoformat(),
        'frist_ende': report.frist_ende.isoformat(),
        'einwendungsfrist_ende': einwendungsfrist(datum).isoformat(),
        'warnung': warnung,
    }), 200


def _anschreiben_fuer(mieter, bill_data, report=None):
    """Das Anschreiben des Vermieters, ausgefüllt für diese Abrechnung (NK-064).

    Die Vorlage des Objekts, sonst der Vorgabetext aus ``anschreiben.py``;
    die Platzhalter kommen aus dem Ergebnis der Rechnung. Der Vermieter
    bestimmt den Ton, die Software nur die Zahlen.
    """
    vorlage_zeile = AnschreibenVorlage.query.filter_by(
        property_id=mieter.apartment.property_id).first()
    vorlage = vorlage_zeile.text if vorlage_zeile else VORGABE

    anfang = datetime.fromisoformat(bill_data['start_date']).strftime('%d.%m.%Y')
    ende = datetime.fromisoformat(bill_data['end_date']).strftime('%d.%m.%Y')
    vorauszahlungen = bill_data.get('prepaid_amount', NULL) or NULL

    # Die Einwendungsfrist des Mieters (R-FRIST-03) rechnet ab dem Zugang --
    # bekannt erst mit dem Zustelldatum; ohne es bleibt der Platzhalter
    # sichtbar stehen, ein sichtbares Loch schreit, ein leeres schweigt.
    frist_text = None
    if report is not None and report.zugestellt_am is not None:
        frist_text = einwendungsfrist(report.zugestellt_am).strftime('%d.%m.%Y')

    return text_fuer(
        vorlage,
        mieter_name=bill_data['tenant_name'],
        wohnung_name=bill_data['apartment'],
        objekt_name=bill_data['property'],
        zeitraum=f'{anfang} bis {ende}',
        gesamtsumme=bill_data['total_amount'],
        vorauszahlungen=vorauszahlungen,
        saldo=bill_data['total_amount'] - vorauszahlungen,
        einwendungsfrist=frist_text,
    )


def _bericht_ergebnis(report):
    """Das Ergebnis, auf dem die Abrechnung steht.

    Der Schnappschuss der gültigen Version, wenn es einen gibt (R-DOC-02,
    NK-061) -- sonst, beim Altbestand ohne Version (D-59), das Ergebnis
    einer frischen Rechnung gegen die heutigen Daten. Liefert das Paar
    (Ergebnis, Version); die Version ist beim Altbestand None.
    """
    version = report.aktuelle_version
    if version is not None:
        return version.ergebnis, version

    from nebenkostenfix.billing_engine import BillingEngine
    engine = BillingEngine(
        tenant_id=report.tenant_id,
        start_date=report.start_date,
        end_date=report.end_date,
        category_ids=[c.category_id for c in report.categories]
    )
    return engine.calculate_bill(), None


@app.route('/api/billing/reports/<int:id>/details', methods=['GET'])
def get_billing_report_details(id):
    report = TenantBillingReport.query.get_or_404(id)

    # Die finalisierte Abrechnung ist unveränderlich (R-DOC-02, NK-061):
    # die Detailroute liefert den Schnappschuss der gueltigen Version, nicht
    # das Ergebnis einer neuen Rechnung gegen die inzwischen vielleicht
    # geänderten Stammdaten. Der Regeltest der Regel: einen Zählerstand
    # ändern und die Abrechnung bleibt, wie sie war.
    version = report.aktuelle_version
    if version is not None:
        return jsonify({
            'version': version.nummer,
            'software_version': version.software_version,
            'regel_version': version.regel_version,
            'ergebnis': version.ergebnis,
            # NK-124: die Umschlagdaten und die Versionen, damit die
            # Oberflaeche Zustellung, Frist und Korrektur an diesem Ort
            # zeigen kann, statt nur die Zahlen.
            'start_date': report.start_date.isoformat(),
            'end_date': report.end_date.isoformat(),
            'zugestellt_am': (report.zugestellt_am.isoformat()
                              if report.zugestellt_am else None),
            'frist_ende': (report.frist_ende.isoformat()
                           if report.frist_ende else None),
            # Die Einwendungsfrist des Mieters (R-FRIST-03), informativ:
            # gerechnet wird im Regelwerk, nicht in der Oberflaeche.
            'einwendungsfrist_ende': (
                einwendungsfrist(report.zugestellt_am).isoformat()
                if report.zugestellt_am else None),
            'versionen': [
                {'nummer': v.nummer,
                 'erstellt_am': v.erstellt_am.isoformat() if v.erstellt_am else None,
                 'software_version': v.software_version,
                 'regel_version': v.regel_version}
                for v in report.versionen
            ],
        })

    # Altbestand ohne Schnappschuss (vor NK-061): es gibt nichts zu
    # liefern, was festgehalten waere -- hier wird weiter live gerechnet.
    # Die Luecke ist dokumentiert (D-59); neue Abrechnungen haben sie nicht.
    # BillingDataError bleibt hier: das ist eine Absage an den Vermieter
    # ("keine Flaeche hinterlegt"), kein Fehler der Anwendung, und deshalb 400
    # mit dem Text der Regel. Alles andere geht an den zentralen Handler.
    try:
        bill_data = _bericht_ergebnis(report)[0]
        return jsonify(bill_data)
    except BillingDataError as e:
        return jsonify({'error': str(e)}), 400


def _beleg_datei(pfad):
    """Löst den Pfad eines Belegs sicher auf und liefert ihn, wenn er liegt.

    Seit NK-129 mit realpath im Belegordner (uploads.pfad_aufloesen): ein
    Beleg außerhalb -- auch über ``..`` oder eine Verknüpfung -- wird wie
    ein fehlender behandelt, nicht ausgeliefert.
    """
    aufgeloest = uploads.pfad_aufloesen(nas_handler.nas_mount_path, pfad)
    return str(aufgeloest) if aufgeloest is not None else None


@app.route('/api/properties/<int:property_id>/anschreiben', methods=['GET'])
def get_anschreiben_vorlage(property_id):
    """Die Anschreiben-Vorlage des Objekts (NK-064).

    Ohne eigenen Eintrag antwortet die Route mit dem Vorgabetext aus
    ``anschreiben.py`` und der Marke ``ist_vorgabe`` -- der Vermieter
    sieht, dass er noch nichts Eigenes hinterlegt hat, und bekommt mit
    ``platzhalter`` dieselbe Liste, die die Renderfunktion füllt.
    """
    objekt = db.session.get(Property, property_id)
    if objekt is None:
        return jsonify({'error': 'Objekt nicht gefunden.'}), 404
    vorlage_zeile = AnschreibenVorlage.query.filter_by(property_id=property_id).first()
    return jsonify({
        'text': vorlage_zeile.text if vorlage_zeile else VORGABE,
        'ist_vorgabe': vorlage_zeile is None,
        'platzhalter': PLATZHALTER,
    })


@app.route('/api/properties/<int:property_id>/anschreiben', methods=['PUT'])
def setze_anschreiben_vorlage(property_id):
    """Hinterlegt (oder ändert) die Anschreiben-Vorlage des Objekts (NK-064).

    Der Text kommt als JSON {"text": ...}; eine leere Vorlage wird
    abgelehnt -- wer nichts sagen will, lässt die Route in Ruhe und der
    Vorgabetext spricht.
    """
    objekt = db.session.get(Property, property_id)
    if objekt is None:
        return jsonify({'error': 'Objekt nicht gefunden.'}), 404
    daten = request.get_json(silent=True) or {}
    text = daten.get('text')
    if not isinstance(text, str) or not text.strip():
        return jsonify({'error': 'Die Vorlage braucht einen Text.'}), 400

    vorlage_zeile = AnschreibenVorlage.query.filter_by(property_id=property_id).first()
    if vorlage_zeile is None:
        vorlage_zeile = AnschreibenVorlage(property_id=property_id)
        db.session.add(vorlage_zeile)
    vorlage_zeile.text = text
    vorlage_zeile.aktualisiert_am = date.today()
    db.session.commit()
    return jsonify({'text': text, 'ist_vorgabe': False, 'platzhalter': PLATZHALTER})


@app.route('/api/properties/<int:property_id>/anschreiben', methods=['DELETE'])
def loesche_anschreiben_vorlage(property_id):
    """Wirft die eigene Vorlage weg -- zurück zum Vorgabetext (NK-064).

    Löschen heißt nicht nichts sagen: es heißt wieder das sagen, was
    die Software vorschlägt.
    """
    vorlage_zeile = AnschreibenVorlage.query.filter_by(property_id=property_id).first()
    if vorlage_zeile is not None:
        db.session.delete(vorlage_zeile)
        db.session.commit()
    return jsonify({'text': VORGABE, 'ist_vorgabe': True, 'platzhalter': PLATZHALTER})


@app.route('/api/billing/reports/<int:id>/belege', methods=['GET'])
def get_billing_report_belege(id):
    """Alle Belege der Abrechnung als ZIP zum Mitgeben (§ 556 Abs. 4 BGB).

    Die Rechnungen der Abrechnung sind die, auf die die Zeilen des
    Ergebnisses verweisen -- gelesen aus dem gespeicherten Ergebnis,
    nicht aus dem, was heute in den Zeiträumen läge. Die Datei zur
    Rechnung wird frisch am Platz gesucht: die Rechnung ist die
    Identität, die Datei ihre aktuelle Fassung. Was fehlt -- gelöschte
    Rechnung, keine Datei, Datei weg -- steht als Liste in das Archiv,
    statt still zu fehlen: der Vermieter muss sehen können, dass etwas
    fehlt, bevor er das Paket dem Mieter gibt.
    """
    report = TenantBillingReport.query.get_or_404(id)
    ergebnis = _bericht_ergebnis(report)[0]

    rechnungs_ids = []
    for zeile in ergebnis.get('line_items', []):
        rid = zeile.get('invoice_id')
        if rid is not None and rid not in rechnungs_ids:
            rechnungs_ids.append(rid)

    eintraege = []  # (Name im Archiv, Pfad auf der Platte)
    fehlen = []
    for rid in rechnungs_ids:
        rechnung = db.session.get(CostInvoice, rid)
        name = (rechnung.invoice_number if rechnung is not None
                and rechnung.invoice_number else f'Rechnung Nr. {rid}')
        if rechnung is None:
            fehlen.append(f'{name}: ist nicht mehr vorhanden.')
            continue
        pfad = None
        if rechnung.document is not None and rechnung.document.document_path:
            pfad = rechnung.document.document_path
        elif rechnung.document_path:
            pfad = rechnung.document_path
        if not pfad:
            fehlen.append(f'{name}: zu dieser Rechnung ist keine Datei hinterlegt.')
            continue
        datei = _beleg_datei(pfad)
        if datei is None:
            fehlen.append(f'{name}: die Datei liegt nicht (mehr) am angegebenen Ort.')
            continue
        eintrag = os.path.basename(pfad)
        eintraege.append((eintrag, datei))

    if not eintraege and not fehlen:
        return jsonify({
            'error': 'Für diese Abrechnung gibt es keine Belege.'}), 404

    archiv = BytesIO()
    with zipfile.ZipFile(archiv, 'w', zipfile.ZIP_DEFLATED) as paket:
        vergeben = set()
        for name, datei in eintraege:
            ziel, n = name, 2
            while ziel in vergeben:
                stamm, end = os.path.splitext(name)
                ziel = f'{stamm} ({n}){end}'
                n += 1
            vergeben.add(ziel)
            paket.write(datei, arcname=ziel)
        if fehlen:
            paket.writestr(
                'FEHLENDE_BELEGE.txt',
                'Diese Belege der Abrechnung fehlen:\n'
                + '\n'.join(f'- {text}' for text in fehlen) + '\n')
    archiv.seek(0)

    mieter = report.tenant.name if report.tenant else 'Mieter'
    sicher = ''.join(
        zeichen if zeichen.isalnum() or zeichen in ' -_' else '_'
        for zeichen in mieter)
    download_name = (
        f'Belege_{sicher}_'
        f'{report.start_date.strftime("%Y%m%d")}-{report.end_date.strftime("%Y%m%d")}.zip')
    return send_file(archiv, mimetype='application/zip', as_attachment=True,
                     download_name=download_name)


@app.route('/api/billing/reports/<int:id>/positionen.csv', methods=['GET'])
def get_billing_report_csv(id):
    """Die Positionen der Abrechnung als CSV fuer die Tabellenkalkulation
    (NK-145). Gelesen wird das gespeicherte Ergebnis -- dieselben Zahlen wie
    auf dem Blatt des Mieters, nicht eine neue Rechnung."""
    from nebenkostenfix.csv_export import dateiname, positionen_csv

    report = TenantBillingReport.query.get_or_404(id)
    try:
        ergebnis = _bericht_ergebnis(report)[0]
    except BillingDataError as e:
        return jsonify({'error': str(e)}), 400
    inhalt = '\ufeff' + positionen_csv(ergebnis)
    return send_file(BytesIO(inhalt.encode('utf-8')),
                     mimetype='text/csv; charset=utf-8', as_attachment=True,
                     download_name=dateiname(report))


@app.route('/api/billing/reports/<int:id>/korrektur', methods=['POST'])
def korrigiere_billing_report(id):
    """Die Korrektur legt eine neue Version an (R-DOC-02, NK-061).

    Sie aendert nichts an der ersetzten: die bleibt mit ihrem Schnappschuss
    als Geschichte stehen. Die neue Version rechnet gegen die aktuellen
    Daten, verweist mit ``ersetzt_version_id`` auf die ersetzte und laesst
    die PDFs der Abrechnung neu erzeugen -- das Blatt, das der Mieter
    bekommt, muss die korrigierten Zahlen tragen. Hat sich an den Daten
    nichts geaendert, gibt es keine Korrektur: eine neue Version waere
    nur eine Kopie.
    """
    report = TenantBillingReport.query.get_or_404(id)

    category_ids = [c.category_id for c in report.categories] or None
    from nebenkostenfix.billing_engine import BillingEngine
    engine = BillingEngine(
        tenant_id=report.tenant_id,
        start_date=report.start_date,
        end_date=report.end_date,
        category_ids=category_ids
    )
    try:
        bill_data = engine.calculate_bill()
    except BillingDataError as e:
        return jsonify({'error': str(e)}), 400
    
    ersetzt = report.aktuelle_version
    neue_ergebnis = json_sicher(bill_data)
    if ersetzt is not None and ersetzt.ergebnis == neue_ergebnis:
        return jsonify({'error':
            'Die Abrechnung ist unverändert; eine neue Version wäre '
            'nur eine Kopie der alten.'}), 400
    
    eingangsdaten, ergebnis = schnappschuss(engine.vorgang, bill_data)
    version = BillingReportVersion(
        report_id=report.id,
        nummer=(ersetzt.nummer if ersetzt else 0) + 1,
        eingangsdaten=eingangsdaten,
        ergebnis=ergebnis,
        software_version=SOFTWARE_VERSION,
        regel_version=REGEL_VERSION,
        ersetzt_version_id=ersetzt.id if ersetzt else None,
    )
    db.session.add(version)
    
    # Die PDFs der Abrechnung tragen die korrigierten Zahlen. Wiederaufgesetzt
    # wird jede Fassung, die es gibt; die alten Dateien bleiben im Belegordner
    # stehen, der neue Lauf bekommt einen eigenen Namen.
    tenant = Tenant.query.get(report.tenant_id)
    prop = tenant.apartment.property
    start_fmt = report.start_date.strftime('%Y%m%d')
    end_fmt = report.end_date.strftime('%Y%m%d')
    zusatz = f"_Korrektur{version.nummer}" if version.nummer > 1 else ""
    
    class DummyFile:
        def __init__(self, name, content):
            self.filename = name
            self.content = content
        def save(self, path):
            with open(path, 'wb') as f:
                f.write(self.content)
    
    # NK-064: die Korrektur wickelt dieselbe Vorlage wie der erste Lauf;
    # bei zugestellter Abrechnung kennt sie auch die Einwendungsfrist.
    anschreiben_text = _anschreiben_fuer(tenant, bill_data, report=report)
    for detailliert, attribut in ((False, 'document_path'),
                                  (True, 'document_path_detailed')):
        if getattr(report, attribut) is None:
            continue
        pdf_gen = PDFGenerator(
            property_name=bill_data['property'],
            apartment_name=bill_data['apartment'],
            tenant_name=bill_data['tenant_name'],
            start_date=bill_data['start_date'],
            end_date=bill_data['end_date'],
            detailliert=detailliert
        )
        suffix = ("_Detailliert" if detailliert else "_Einfach") + zusatz
        dateiname = (f"Nebenkostenabrechnung_{tenant.name.replace(' ', '_')}"
                     f"_{start_fmt}-{end_fmt}{suffix}.pdf")
        pdf_bytes = pdf_gen.generate(
            bill_data['line_items'],
            bill_data['total_amount'],
            bill_data.get('prepaid_amount', NULL),
            co2_ausweis=bill_data.get('co2'),
            landlord_share=bill_data.get('landlord_share'),
            anschreiben=anschreiben_text,
        )
        pdf_path, _ = nas_handler.save_billing_report(
            DummyFile(dateiname, pdf_bytes), prop.name,
            tenant.apartment.name, tenant.name)
        setattr(report, attribut, pdf_path)
    
    db.session.commit()
    return jsonify({
        'message': 'Korrektur erfolgreich erstellt',
        'versionsnummer': version.nummer,
        'ersetzt_version_id': ersetzt.id if ersetzt else None,
        'software_version': SOFTWARE_VERSION,
        'regel_version': REGEL_VERSION,
    }), 201

@app.route('/api/billing/interpolation-audit', methods=['GET'])
def get_interpolation_audit():
    eingabe = Eingabe.aus_query()
    meter_id = eingabe.ganzzahl('meter_id', pflicht=True)
    start_date = eingabe.datum('start_date', pflicht=True)
    end_date = eingabe.datum('end_date', pflicht=True)

    from nebenkostenfix.billing_engine import BillingEngine
    result = BillingEngine.get_meter_consumption_detailed(meter_id, start_date, end_date)
    return jsonify(result)

@app.route('/api/payments', methods=['GET'])
def get_payments():
    # Import here to avoid circular imports if any, or just use the model
    from nebenkostenfix.models import Payment, Tenant
    payments = (db.session.query(Payment, Tenant)
                .join(Tenant, Payment.tenant_id == Tenant.id)
                .filter(Tenant.gesperrt_bis.is_(None)).all())
    result = []
    for p, t in payments:
        result.append({
            'id': p.id,
            'tenant_id': p.tenant_id,
            'tenant_name': t.name,
            'amount': p.amount,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'type': p.type,
            'ist_beispiel': beispielimmobilie.ist_beispiel(
                t.apartment.property if t.apartment else None)
        })
    # Sort by date descending
    result.sort(key=lambda x: x['payment_date'], reverse=True)
    return jsonify(result)

@app.route('/api/payments', methods=['POST'])
def add_payment():
    from nebenkostenfix.models import Payment
    from datetime import date
    import calendar
    
    def add_months(d, months):
        month = d.month - 1 + months
        year = d.year + month // 12
        month = month % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    # Die Pruefung steht bewusst vor dem try. Bis NK-028 fing ein
    # except Exception auch die Umwandlungsfehler ab und schickte deren
    # englischen Wortlaut als error zurueck, etwa
    # "invalid literal for int() with base 10".
    eingabe = Eingabe.aus_request()
    tenant_id = eingabe.ganzzahl('tenant_id', pflicht=True)
    amount = eingabe.geldbetrag('amount', pflicht=True)
    type_ = eingabe.text('type', pflicht=True, maxlaenge=100)
    start_date = eingabe.datum('payment_date', pflicht=True)
    is_recurring = eingabe.wahrheit('is_recurring')
    billing_report_id = eingabe.ganzzahl('billing_report_id')
    end_date = eingabe.datum('end_date')

    # Das umschliessende try ist weg (NK-030). Es machte aus jedem Fehler eine
    # 400 mit englischem Wortlaut -- auch aus einem Datenbankausfall, der
    # keine Absage an den Vermieter ist, sondern ein Fehler der Anwendung.
    # Was die Eingabe betrifft, hat die Pruefung oben schon abgelehnt.
    if is_recurring:
        if end_date is None:
            end_date = date(date.today().year + 1, 12, 31)

        current_date = start_date
        created_count = 0
        while current_date <= end_date:
            payment = Payment(
                tenant_id=tenant_id,
                amount=amount,
                payment_date=current_date,
                type=type_,
                billing_report_id=billing_report_id if type_ == 'Nebenkostenzahlung' else None
            )
            db.session.add(payment)
            current_date = add_months(current_date, 1)
            created_count += 1
            if created_count > 120:
                break
        db.session.commit()
        return jsonify({'message': f'{created_count} Zahlungen erfolgreich erfasst'}), 201
    else:
        payment = Payment(
            tenant_id=tenant_id,
            amount=amount,
            payment_date=start_date,
            type=type_,
            billing_report_id=billing_report_id if type_ == 'Nebenkostenzahlung' else None
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({'message': 'Zahlung erfolgreich erfasst', 'id': payment.id}), 201

@app.route('/api/payments/<int:id>', methods=['DELETE'])
def delete_payment(id):
    from nebenkostenfix.models import Payment
    payment = Payment.query.get_or_404(id)
    db.session.delete(payment)
    db.session.commit()
    return jsonify({'message': 'Zahlung gelöscht'}), 200


@app.route('/api/payments/bulk', methods=['DELETE'])
def bulk_delete_payments():
    from nebenkostenfix.models import Payment
    eingabe = Eingabe.aus_request()
    ids = eingabe.ganzzahlliste('ids', pflicht=True)
    Payment.query.filter(Payment.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'message': f'{len(ids)} Zahlungen gelöscht'}), 200

# --- Analytics Endpoints ---

def _map_category(cat_name):
    # Die Rubrik kommt aus dem Katalog (betrkv): die BetrKV-Nummer der
    # Kostenart entscheidet, nicht der Name (F-32, NK-121). Fuer einen
    # gewachsenen Namen ordnet ``zuordnung`` zu -- dieselbe Vermutung, die
    # der Abgleich beim Einspielen benutzt. Die Stichwortlisten sind weg:
    # sie wussten nichts voneinander und widersprachen sich ("Warmwasser"
    # hier Energie, dort Wasser).
    return betrkv.rubrik(betrkv.zuordnung(cat_name))


def _get_unit(cat_name):
    # Dieselbe Quelle (NK-121): die Einheit kommt aus der BetrKV-Nummer,
    # damit die Analytics dieselbe Einheit nennt wie der Rechenkern --
    # "Heizung" ist ein Wärmezähler und misst Kilowattstunden.
    return betrkv.einheit(betrkv.zuordnung(cat_name))


def _map_to_bucket(cat_name):
    # Auch hier der Katalog (NK-121): Strom ist allein die Nr. 11, alles
    # Brennende (Nr. 4, 5, 6) faellt unter "Gas" -- auch das Warmwasser,
    # das ein Brennstoffposten ist. Die Stichwortliste hatte es in die
    # Wasser-Spalte geräumt, waehrend _map_category dasselbe Wort nach
    # Energie schob. Sie stand in analytics_building und war deshalb
    # untestbar; jetzt liegt sie neben die anderen beiden.
    return betrkv.bereich(betrkv.zuordnung(cat_name))



@app.route('/api/analytics/building/<int:property_id>', methods=['GET'])
def analytics_building(property_id):
    from nebenkostenfix.models import CostInvoice, Payment, CostCategory, Meter, Tenant, Apartment, db
    import datetime
    from nebenkostenfix.billing_engine import BillingEngine
    
    def _zufluss_datum(inv):
        """Tag, an dem die Rechnung im Cashflow zählt (NK-120).

        Das Ausstellungsdatum des Belegs (``rechnungsdatum``, D-57) — es
        steht auf dem Beleg und hängt nicht davon ab, wann jemand ihn
        hochgeladen hat. Fehlt es (Altbestand, NULL), gilt der bisherige
        Rückfall: der Upload des verknüpften Belegs, sonst der Beginn des
        Rechnungszeitraums.
        """
        if inv.rechnungsdatum:
            return inv.rechnungsdatum
        if inv.document and inv.document.upload_date:
            return inv.document.upload_date
        return inv.start_date
    
    invoices = CostInvoice.query.filter_by(property_id=property_id).all()
    
    current_year = datetime.date.today().year
    
    # Determine reference_year: the latest year that actually has cost data
    years_with_costs = set(inv.start_date.year for inv in invoices if inv.amount > 0)
    if years_with_costs:
        reference_year = max(years_with_costs)
    else:
        reference_year = current_year - 1
        
    # --- KPIs ---
    payments = db.session.query(Payment).join(Tenant).join(Apartment).filter(Apartment.property_id == property_id).all()
    today = datetime.date.today()
    cashflow_in_current = sum(p.amount for p in payments if p.payment_date.year == current_year and p.type != 'Kaution')
    cashflow_out_current = sum(inv.amount for inv in invoices if _zufluss_datum(inv).year == current_year)
    cashflow_ytd = cashflow_in_current - cashflow_out_current
    
    # Betriebskosten: exact date range from invoices
    ref_invoices = [inv for inv in invoices if inv.start_date.year == reference_year]
    total_costs_last_year = sum(inv.amount for inv in ref_invoices)
    costs_period = ''
    if ref_invoices:
        min_start = min(inv.start_date for inv in ref_invoices)
        max_end = max(inv.end_date for inv in ref_invoices if inv.end_date)
        costs_period = f"{min_start.strftime('%d.%m.%Y')} - {max_end.strftime('%d.%m.%Y')}"
    
    # Costs history for modal
    costs_history = []
    for y in sorted(years_with_costs):
        y_invs = [inv for inv in invoices if inv.start_date.year == y]
        y_total = sum(inv.amount for inv in y_invs)
        y_start = min(inv.start_date for inv in y_invs)
        y_end = max(inv.end_date for inv in y_invs if inv.end_date)
        costs_history.append({
            'year': y,
            'value': runde(y_total),
            'period': f"{y_start.strftime('%d.%m.%Y')} - {y_end.strftime('%d.%m.%Y')}"
        })
    
    main_meters = Meter.query.filter_by(property_id=property_id, is_main_meter=True).all()
    general_power_last = 0
    general_power_prev = 0
    power_period = ''
    
    from nebenkostenfix.models import MeterReading
    
    general_power_is_interpolated = False
    
    for mm in main_meters:
        if mm.category and mm.category.betrkv_nr == betrkv.NR_ALLGEMEINSTROM:
            all_readings = MeterReading.query.filter_by(meter_id=mm.id).order_by(MeterReading.reading_date).all()
            sub_meters = Meter.query.filter_by(property_id=property_id, category_id=mm.category_id, is_main_meter=False).all()
            
            def is_main_reading_date(target_date):
                if not sub_meters: return True
                for sm in sub_meters:
                    sm_rs = MeterReading.query.filter_by(meter_id=sm.id).all()
                    if not sm_rs: continue
                    min_d = min(abs((sr.reading_date - target_date).days) for sr in sm_rs)
                    if min_d > 21: # 21 days tolerance
                        return False
                return True
                
            readings = [r for r in all_readings if is_main_reading_date(r.reading_date)]
            if len(readings) < 2:
                readings = all_readings
                general_power_is_interpolated = len(all_readings) >= 2
            else:
                general_power_is_interpolated = False
                
            if len(readings) >= 2:
                # Use last 2 readings for current period
                r_end = readings[-1]
                r_start = readings[-2]
                
                val_start = r_start.value + (getattr(r_start, 'value_nt', 0) or 0)
                val_end = r_end.value + (getattr(r_end, 'value_nt', 0) or 0)
                main_raw = val_end - val_start
                
                power_period = f"{r_start.reading_date.strftime('%d.%m.%Y')} - {r_end.reading_date.strftime('%d.%m.%Y')}"
                
                sub_total = 0
                for sm in sub_meters:
                    sm_rs = MeterReading.query.filter_by(meter_id=sm.id).all()
                    if not sm_rs: continue
                    sr_start = min(sm_rs, key=lambda sr: abs((sr.reading_date - r_start.reading_date).days))
                    sr_end = min(sm_rs, key=lambda sr: abs((sr.reading_date - r_end.reading_date).days))
                    s_val_start = sr_start.value + (getattr(sr_start, 'value_nt', 0) or 0)
                    s_val_end = sr_end.value + (getattr(sr_end, 'value_nt', 0) or 0)
                    sub_total += (s_val_end - s_val_start)
                
                general_power_last = max(0, main_raw - sub_total)
                
                # Previous period for trend (use readings[-3] to readings[-2] if available)
                if len(readings) >= 3:
                    r_prev_start = readings[-3]
                    val_prev_start = r_prev_start.value + (getattr(r_prev_start, 'value_nt', 0) or 0)
                    main_prev_raw = val_start - val_prev_start
                    
                    sub_prev_total = 0
                    for sm in sub_meters:
                        sm_rs = MeterReading.query.filter_by(meter_id=sm.id).all()
                        if not sm_rs: continue
                        sr_prev_start = min(sm_rs, key=lambda sr: abs((sr.reading_date - r_prev_start.reading_date).days))
                        sr_start = min(sm_rs, key=lambda sr: abs((sr.reading_date - r_start.reading_date).days))
                        s_val_prev_start = sr_prev_start.value + (getattr(sr_prev_start, 'value_nt', 0) or 0)
                        s_val_start = sr_start.value + (getattr(sr_start, 'value_nt', 0) or 0)
                        sub_prev_total += (s_val_start - s_val_prev_start)
                        
                    general_power_prev = max(0, main_prev_raw - sub_prev_total)
                    
                    # Normalize to same period length for fair comparison
                    current_days = (r_end.reading_date - r_start.reading_date).days
                    prev_days = (r_start.reading_date - r_prev_start.reading_date).days
                    if prev_days > 0 and current_days > 0:
                        general_power_prev = general_power_prev * (current_days / prev_days)
            
    general_power_trend = 0
    if general_power_prev > 0:
        general_power_trend = ((general_power_last - general_power_prev) / general_power_prev) * 100
    
    # Power history for modal — show actual readings pairs
    power_history = []
    for mm in main_meters:
        if mm.category and mm.category.betrkv_nr == betrkv.NR_ALLGEMEINSTROM:
            all_readings = MeterReading.query.filter_by(meter_id=mm.id).order_by(MeterReading.reading_date).all()
            sub_meters = Meter.query.filter_by(property_id=property_id, category_id=mm.category_id, is_main_meter=False).all()
            
            def is_main_reading_date(target_date):
                if not sub_meters: return True
                for sm in sub_meters:
                    sm_rs = MeterReading.query.filter_by(meter_id=sm.id).all()
                    if not sm_rs: continue
                    min_d = min(abs((sr.reading_date - target_date).days) for sr in sm_rs)
                    if min_d > 21: return False
                return True
                
            readings = [r for r in all_readings if is_main_reading_date(r.reading_date)]
            if len(readings) < 2: readings = all_readings
            
            for i in range(1, len(readings)):
                r_s = readings[i-1]
                r_e = readings[i]
                val_s = r_s.value + (getattr(r_s, 'value_nt', 0) or 0)
                val_e = r_e.value + (getattr(r_e, 'value_nt', 0) or 0)
                main_diff = val_e - val_s
                
                sub_diff = 0
                for sm in sub_meters:
                    sm_rs = MeterReading.query.filter_by(meter_id=sm.id).all()
                    if not sm_rs: continue
                    sr_s = min(sm_rs, key=lambda sr: abs((sr.reading_date - r_s.reading_date).days))
                    sr_e = min(sm_rs, key=lambda sr: abs((sr.reading_date - r_e.reading_date).days))
                    s_val_s = sr_s.value + (getattr(sr_s, 'value_nt', 0) or 0)
                    s_val_e = sr_e.value + (getattr(sr_e, 'value_nt', 0) or 0)
                    sub_diff += (s_val_e - s_val_s)
                    
                allgemein = max(0, main_diff - sub_diff)
                if allgemein > 0:
                    period_str = f"{r_s.reading_date.strftime('%d.%m.%Y')} - {r_e.reading_date.strftime('%d.%m.%Y')}"
                    power_history.append({
                        'year': f"{r_s.reading_date.year}/{r_e.reading_date.year}" if r_s.reading_date.year != r_e.reading_date.year else str(r_e.reading_date.year),
                        'value': round(allgemein, 2),
                        'unit': 'kWh',
                        'period': period_str
                    })
        
    active_tenants = Tenant.query.join(Apartment).filter(
        Apartment.property_id == property_id,
        db.or_(Tenant.move_out_date == None, Tenant.move_out_date > today)
    ).all()
    
    open_tasks = 0
    one_year_ago = today - datetime.timedelta(days=365)
    for t in active_tenants:
        if not t.last_billed_until or t.last_billed_until < one_year_ago:
            open_tasks += 1
            
    kpis = {
        'reference_year': reference_year,
        'cashflow_ytd': round(cashflow_ytd, 2),
        'total_costs_last_year': round(total_costs_last_year, 2),
        'costs_period': costs_period,
        'costs_history': costs_history,
        'general_power': round(general_power_last, 2),
        'general_power_trend': round(general_power_trend, 1),
        'power_period': power_period,
        'power_history': power_history,
        'general_power_is_interpolated': general_power_is_interpolated,
        'open_tasks': open_tasks
    }
    
    # --- Timeseries Data (grouped into 4 clean buckets) ---
    bucket_units = {'Strom': 'kWh', 'Gas': 'm³', 'Wasser': 'm³', 'Sonstige Kosten': '€'}
    
    # --- Timeseries: costs per year with actual date ranges ---
    cost_timeseries = {}
    for inv in invoices:
        y = inv.start_date.year
        bucket = _map_to_bucket(inv.category.name)
        key = (y, bucket)
        if key not in cost_timeseries:
            cost_timeseries[key] = {'cost': 0, 'start': inv.start_date, 'end': inv.end_date}
        cost_timeseries[key]['cost'] += inv.amount
        if inv.start_date < cost_timeseries[key]['start']:
            cost_timeseries[key]['start'] = inv.start_date
        if inv.end_date and inv.end_date > cost_timeseries[key]['end']:
            cost_timeseries[key]['end'] = inv.end_date
        
    timeseries_data = []
    for (y, bucket), data in cost_timeseries.items():
        period_str = f"{data['start'].strftime('%d.%m.%Y')} - {data['end'].strftime('%d.%m.%Y')}" if data['end'] else str(y)
        timeseries_data.append({
            'year': y,
            'label': f"{y}",
            'period': period_str,
            'category': bucket,
            'cost': round(data['cost'], 2),
            'consumption': 0,
            'unit': bucket_units.get(bucket, '€')
        })
    
    # --- Timeseries: consumption from RAW meter reading pairs ---
    for mm in main_meters:
        bucket = _map_to_bucket(mm.category.name)
        readings = MeterReading.query.filter_by(meter_id=mm.id).order_by(MeterReading.reading_date).all()
        sub_meters_list = Meter.query.filter_by(property_id=property_id, category_id=mm.category_id, is_main_meter=False).all()
        
        for i in range(1, len(readings)):
            r_s = readings[i-1]
            r_e = readings[i]
            val_s = r_s.value + (getattr(r_s, 'value_nt', 0) or 0)
            val_e = r_e.value + (getattr(r_e, 'value_nt', 0) or 0)
            main_diff = val_e - val_s
            # Use total main meter consumption (= entire building)
            net_consumption = max(0, main_diff)
            
            if net_consumption > 0:
                year_label = r_e.reading_date.year
                period_str = f"{r_s.reading_date.strftime('%d.%m.%Y')} - {r_e.reading_date.strftime('%d.%m.%Y')}"
                
                # Try to merge with existing cost entry for the same year/bucket
                found = False
                for entry in timeseries_data:
                    if entry['year'] == year_label and entry['category'] == bucket:
                        entry['consumption'] += round(net_consumption, 2)
                        if period_str not in entry['period']:
                            entry['period'] += ' | ' + period_str
                        found = True
                        break
                
                if not found:
                    timeseries_data.append({
                        'year': year_label,
                        'label': str(year_label),
                        'period': period_str,
                        'category': bucket,
                        'cost': 0,
                        'consumption': round(net_consumption, 2),
                        'unit': bucket_units.get(bucket, '€')
                    })
    
    # --- Timeseries: consumption from sub-meters for categories WITHOUT a main meter ---
    # (e.g. Gas with only apartment-level meters from the provider)
    main_meter_cat_ids = set(mm.category_id for mm in main_meters)
    all_sub_meters = Meter.query.filter_by(property_id=property_id, is_main_meter=False).all()
    orphan_cats = set()
    for sm in all_sub_meters:
        if sm.category_id not in main_meter_cat_ids:
            orphan_cats.add(sm.category_id)
    
    for cat_id in orphan_cats:
        cat_meters = [m for m in all_sub_meters if m.category_id == cat_id]
        cat = CostCategory.query.get(cat_id)
        if not cat:
            continue
        bucket = _map_to_bucket(cat.name)
        
        for sm in cat_meters:
            readings = MeterReading.query.filter_by(meter_id=sm.id).order_by(MeterReading.reading_date).all()
            for i in range(1, len(readings)):
                r_s = readings[i-1]
                r_e = readings[i]
                val_s = r_s.value + (getattr(r_s, 'value_nt', 0) or 0)
                val_e = r_e.value + (getattr(r_e, 'value_nt', 0) or 0)
                consumption = max(0, val_e - val_s)
                
                if consumption > 0:
                    year_label = r_e.reading_date.year
                    period_str = f"{r_s.reading_date.strftime('%d.%m.%Y')} - {r_e.reading_date.strftime('%d.%m.%Y')}"
                    
                    found = False
                    for entry in timeseries_data:
                        if entry['year'] == year_label and entry['category'] == bucket:
                            entry['consumption'] += round(consumption, 2)
                            if period_str not in entry['period']:
                                entry['period'] += ' | ' + period_str
                            found = True
                            break
                    
                    if not found:
                        timeseries_data.append({
                            'year': year_label,
                            'label': str(year_label),
                            'period': period_str,
                            'category': bucket,
                            'cost': 0,
                            'consumption': round(consumption, 2),
                            'unit': bucket_units.get(bucket, '€')
                        })
        
    timeseries_data.sort(key=lambda x: (x['year'], x['category']))
    
    # --- Apartment Comparison: RAW reading differences ---
    apartment_comparison = []
    apartments = Apartment.query.filter_by(property_id=property_id).all()
    
    for apt in apartments:
        sub_meters = Meter.query.filter_by(apartment_id=apt.id, is_main_meter=False).all()
        for sm in sub_meters:
            bucket = _map_to_bucket(sm.category.name)
            sm_readings = MeterReading.query.filter_by(meter_id=sm.id).order_by(MeterReading.reading_date).all()
            
            if len(sm_readings) >= 2:
                r_last = sm_readings[-1]
                r_prev = sm_readings[-2]
                val_last = r_last.value + (getattr(r_last, 'value_nt', 0) or 0)
                val_prev = r_prev.value + (getattr(r_prev, 'value_nt', 0) or 0)
                cons = val_last - val_prev
                
                if cons > 0:
                    period_str = f"{r_prev.reading_date.strftime('%d.%m.%y')} - {r_last.reading_date.strftime('%d.%m.%y')}"
                    apartment_comparison.append({
                        'apartment': apt.name,
                        'category': bucket,
                        'consumption': round(cons, 2),
                        'unit': bucket_units.get(bucket, ''),
                        'period': period_str,
                        'year': r_last.reading_date.year
                    })

    # --- Cashflow with actual vs. forecast ---
    cashflow_dict = {}
    for inv in invoices:
        zufluss_date = _zufluss_datum(inv)
        y = str(zufluss_date.year)
        is_past = zufluss_date <= today
        if y not in cashflow_dict:
            cashflow_dict[y] = {'in_actual': 0, 'in_forecast': 0, 'out_actual': 0, 'out_forecast': 0}
        if is_past:
            cashflow_dict[y]['out_actual'] += inv.amount
        else:
            cashflow_dict[y]['out_forecast'] += inv.amount
        
    for p in payments:
        if p.type == 'Kaution': continue
        y = str(p.payment_date.year)
        is_past = p.payment_date <= today
        if y not in cashflow_dict:
            cashflow_dict[y] = {'in_actual': 0, 'in_forecast': 0, 'out_actual': 0, 'out_forecast': 0}
        if is_past:
            cashflow_dict[y]['in_actual'] += p.amount
        else:
            cashflow_dict[y]['in_forecast'] += p.amount
        
    cashflow = [{'year': y, **data} for y, data in cashflow_dict.items()]
    cashflow.sort(key=lambda x: x['year'])

    return jsonify({
        'kpis': kpis,
        'timeseries_data': timeseries_data,
        'apartment_comparison': apartment_comparison,
        'cashflow': cashflow
    })

@app.route('/api/analytics/apartment/<int:apartment_id>', methods=['GET'])
def analytics_apartment(apartment_id):
    from nebenkostenfix.models import Meter, TenantBillingReport, db
    
    sub_meters = Meter.query.filter_by(apartment_id=apartment_id, is_main_meter=False).all()
    years = set(str(r.reading_date.year) for m in sub_meters for r in m.readings)
    
    own_consumption = []
    for m in sub_meters:
        cat_name = m.category.name
        readings = sorted(m.readings, key=lambda r: r.reading_date)
        for i in range(1, len(readings)):
            prev = readings[i - 1]
            curr = readings[i]
            
            prev_total = prev.value + (prev.value_nt or 0)
            curr_total = curr.value + (curr.value_nt or 0)
            diff = max(0, curr_total - prev_total)
            
            if diff > 0:
                period_str = f"{prev.reading_date.strftime('%d.%m.%Y')} - {curr.reading_date.strftime('%d.%m.%Y')}"
                own_consumption.append({
                    'period': period_str,
                    'category': cat_name,
                    'value': round(diff, 2),
                    'unit': _get_unit(cat_name)
                })
    from nebenkostenfix.models import Tenant
    tenants = Tenant.query.filter_by(apartment_id=apartment_id).all()
    tenant_ids = [t.id for t in tenants]
    
    latest_report = TenantBillingReport.query.filter(TenantBillingReport.tenant_id.in_(tenant_ids)).order_by(TenantBillingReport.end_date.desc()).first()
    
    cost_distribution = {'Energie': 0, 'Wasser & Abwasser': 0, 'Betriebskosten': 0}
    if latest_report:
        from nebenkostenfix.billing_engine import BillingEngine
        engine = BillingEngine(latest_report.tenant_id, latest_report.start_date, latest_report.end_date)
        try:
            bill_data = engine.calculate_bill()
        except BillingDataError:
            # Die Auswertung ist Beiwerk. Fehlen die Flaechendaten, bleibt die
            # Kostenverteilung leer statt die ganze Seite zu killen (NK-027).
            bill_data = None
        for item in (bill_data['line_items'] if bill_data else []):
            group = _map_category(item['category'])
            cost_distribution[group] += item['tenant_cost']
            
    return jsonify({
        'own_consumption': own_consumption,
        'cost_distribution': cost_distribution
    })

@app.route('/api/analytics/data-quality/<int:property_id>', methods=['GET'])
def analytics_data_quality(property_id):
    """Data quality dashboard: meter freshness + missing sub-meter warnings."""
    from nebenkostenfix.models import Meter, MeterReading, Tenant, TenantCostProfile, CostCategory, Apartment
    from datetime import date as date_type

    today = date_type.today()

    # --- 1. Meter freshness ---
    meters = Meter.query.filter_by(property_id=property_id).all()
    meter_data = []
    for m in meters:
        last_reading = (MeterReading.query
                        .filter_by(meter_id=m.id)
                        .order_by(MeterReading.reading_date.desc())
                        .first())

        reading_count = MeterReading.query.filter_by(meter_id=m.id).count()

        if last_reading:
            days_since = (today - last_reading.reading_date).days
            last_date = last_reading.reading_date.isoformat()
            if days_since < 90:
                status = 'green'
            elif days_since < 180:
                status = 'yellow'
            else:
                status = 'red'
        else:
            days_since = None
            last_date = None
            status = 'none'

        apt_name = None
        if m.apartment_id:
            apt = Apartment.query.get(m.apartment_id)
            if apt:
                apt_name = apt.name

        meter_data.append({
            'meter_id': m.id,
            'meter_number': m.meter_number,
            'category_name': m.category.name,
            'is_main_meter': m.is_main_meter,
            'apartment_name': apt_name,
            'last_reading_date': last_date,
            'days_since_reading': days_since,
            'status': status,
            'reading_count': reading_count,
        })

    # --- 2. Missing sub-meter warnings ---
    warnings = []
    apartments = Apartment.query.filter_by(property_id=property_id, is_active=True).all()

    for apt in apartments:
        active_tenants = Tenant.query.filter(
            Tenant.apartment_id == apt.id,
            Tenant.move_out_date.is_(None)
        ).all()

        for tenant in active_tenants:
            profiles = TenantCostProfile.query.filter_by(tenant_id=tenant.id).all()

            for profile in profiles:
                if profile.billing_type not in ('direkt', 'nur_allgemein'):
                    continue

                cat = CostCategory.query.get(profile.category_id)
                if not cat:
                    continue
                # NK-105 (D-63): requires_meter heisst nur "Pflicht", nicht
                # "erlaubt". Geprueft wird jede Kostenart, an der ein Zaehler
                # haengt; ohne Zaehler und ohne Pflicht bleibt es beim
                # bisherigen stillen Ueberspringen.
                zaehler_dazu = Meter.query.filter_by(
                    category_id=cat.id, property_id=property_id
                ).count() > 0
                if not cat.requires_meter and not zaehler_dazu:
                    continue

                sub_meter = Meter.query.filter_by(
                    category_id=cat.id,
                    apartment_id=apt.id,
                    is_main_meter=False,
                    property_id=property_id
                ).first()

                if profile.billing_type == 'direkt' and not sub_meter:
                    warnings.append({
                        'type': 'missing_submeter',
                        'severity': 'error',
                        'apartment_name': apt.name,
                        'tenant_name': tenant.name,
                        'category_name': cat.name,
                        'message': (
                            f"Wohnung {apt.name} rechnet {cat.name} nach Verbrauch ab, "
                            f"es ist jedoch kein Unterzähler zugewiesen!"
                        ),
                    })

                # Main meter is only needed for nur_allgemein billing
                # (shared consumption must be distributed).
                # For direkt billing, each apartment has its own meter/invoice
                # from the provider, so no main meter is required.
                if profile.billing_type == 'nur_allgemein':
                    main_meter = Meter.query.filter_by(
                        category_id=cat.id,
                        is_main_meter=True,
                        property_id=property_id
                    ).first()

                    if not main_meter:
                        warnings.append({
                            'type': 'missing_main_meter',
                            'severity': 'error',
                            'apartment_name': apt.name,
                            'tenant_name': tenant.name,
                            'category_name': cat.name,
                            'message': (
                                f"Für Kategorie {cat.name} ist kein Hauptzähler vorhanden, "
                                f"aber {apt.name} rechnet nach Allgemeinverbrauch ab!"
                            ),
                        })

    return jsonify({
        'meters': meter_data,
        'warnings': warnings,
    })


@app.route('/api/analytics/beispiel-immobilie', methods=['POST'])
def beispielimmobilie_route():
    """Legt die Beispielimmobilie an (NK-141); zweiter Aufruf wird gemeldet.

    NK-159: danach setzt dieselbe Route Annas Abrechnung des Vorjahres fest
    -- über ``finalize_bill``, den Weg jeder anderen Abrechnung, damit das
    Beispiel zeigt, was die Anwendung wirklich erzeugt.
    """
    try:
        bericht = beispielimmobilie.anlegen()
    except beispielimmobilie.BeispielExistiert as exc:
        return jsonify({
            'error': 'Die Beispielimmobilie existiert bereits.',
            'property_id': exc.property_id,
        }), 409
    auftrag = bericht.pop('abrechnung_auftrag')
    bericht['abrechnung'] = False
    with app.test_request_context('/api/billing/finalize', method='POST',
                                  json={**auftrag, 'detailed': True}):
        antwort = finalize_bill()
    status = antwort[1] if isinstance(antwort, tuple) else antwort.status_code
    if status == 201:
        bericht['abrechnung'] = True
    else:
        protokoll.warning('Beispielabrechnung nicht festgesetzt: %s', status)
    return jsonify(bericht), 201


@app.route('/api/analytics/beispiel-immobilie', methods=['DELETE'])
def beispielimmobilie_entfernen():
    """„Beispiel löschen“ (NK-159): alles, was zum Beispielhaus gehört."""
    return jsonify(beispielimmobilie.entfernen()), 200


@app.route('/api/invoices/zeitleiste', methods=['GET'])
def zeitleiste_route():
    """Die Rechnungen nach Ausstellungsdatum (NK-144, D-57): Jahre und
    Monate absteigend, Altbestand ohne Rechnungsdatum in einer eigenen
    Gruppe am Ende."""
    return jsonify(zeitleiste.erstellen()), 200


if __name__ == '__main__':
    # Nur der Entwicklungsweg `python app.py`; ausgeliefert wird ueber
    # gunicorn (Docker) bzw. waitress (Windows). Standard ist die eigene
    # Maschine, das Netz nur auf ausdruecklichen Wunsch (NK-146).
    port = int(os.environ.get('FLASK_PORT', 6060))
    app.run(host=os.environ.get('FLASK_HOST', '127.0.0.1'), port=port)
