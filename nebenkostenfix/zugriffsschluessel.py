"""Zugriffsschluessel fuer Programme ohne Browser (API-Tokens).

Bis hierher kam man nur mit einer Sitzung an die API (NK-019). Ein Programm,
das im Hintergrund laeuft -- ein MCP-Server, ueber den ein KI-Assistent den
Bestand liest, ein Skript auf dem NAS --, kann kein Anmeldeformular
ausfuellen, und das eigene Passwort gehoert dort nicht hinein.

Ein Zugriffsschluessel gehoert zu einem Konto. Das Programm schickt ihn als
``Authorization: Bearer nkf_...`` mit, ohne Cookie und ohne Sitzung.

Nur ``Bearer nkf_...`` ist ein Schluessel; ein anderer Bearer-Kopf (etwa von
einem Reverse Proxy) laesst die Sitzung entscheiden wie bisher.

Deny-by-default wie die Anmeldung selbst: ein Schluessel erreicht nur, was in
``SCHLUESSEL_LESEN`` steht, mit Umfang "erfassen" zusaetzlich
``SCHLUESSEL_ERFASSEN``. Eine neue Route ist fuer Schluessel also gesperrt,
bis jemand sie bewusst in eine Liste schreibt. ``NIE_PER_SCHLUESSEL`` ist
das zweite Netz: was dort steht, darf in keine der beiden Listen, das prueft
``tests/test_zugriffsschluessel.py``, ebenso dass jede DELETE-Route dort
steht. „erfassen“ heisst anlegen, nie aendern: ``AENDERT_BESTEHENDES`` sperrt
Felder, mit denen ein Anlege-Endpunkt nebenbei Vorhandenes umschreibt. Wo
das am Bestand haengt und nicht an einem Feld, fragt der Endpunkt selbst
nach ``aktueller()``: eine Zahlungsserie mit Schluessel legt ein Soll an,
berichtigt aber keins (``add_payment`` in app.py).

Verwalten (anlegen, auflisten, widerrufen) geht nur mit Sitzung, also nur
durch den Menschen in der Oberflaeche. Im offenen Modus (NK-198) gibt es
keine Konten und darum keine Schluessel.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from flask import has_request_context, jsonify, make_response, request

from nebenkostenfix import anmeldeschutz, zeit
from nebenkostenfix.models import ApiSchluessel, db
from nebenkostenfix.validation import Eingabe, EingabeFehler

PRAEFIX = 'nkf_'
# Der Schluessel haengt an der Anfrage, nicht an ``g``: ``g`` lebt im
# App-Kontext, und den teilen sich im Testclient mehrere Anfragen.
UMGEBUNG = 'nebenkostenfix.zugriffsschluessel'
UMFAENGE = ('lesen', 'erfassen')
HOECHSTENS = 10
# „zuletzt benutzt“ hoechstens so oft schreiben: die Liste zeigt Minuten, und
# ein Assistent, der zwanzig Abrufe am Stueck macht, soll nicht zwanzigmal
# committen (wie SESSION_AKTIV_KEY in auth).
VERMERK_ABSTAND_S = 60

# Nur GET-Routen, die nichts schreiben. Ausnahme PRUEFEN: POST, weil die
# Oberflaeche dort einen Auftrag schickt, aber ohne Schreibzugriff.
PRUEFEN = frozenset({
    'billing_preflight',
    'check_plausibility',
    'hausgeld_pruefen',
})

SCHLUESSEL_LESEN = PRUEFEN | frozenset({
    'auth_me',
    'ueber_anzeigen',
    'get_properties',
    'get_apartments',
    'get_all_apartments',
    'get_heizungsanlagen',
    'get_tenants',
    'get_vorauszahlungen',
    'get_categories',
    'get_providers',
    'get_invoices',
    'get_invoice_documents',
    'get_meters',
    'get_readings',
    'get_payments',
    'get_fristen',
    'jahresabrechnung_stand',
    'analytics_data_quality',
    'billing_suggestions',
    'get_all_billing_reports',
    'get_billing_report_details',
})

# Anlegen, nie aendern oder loeschen: ein Programm ergaenzt den Bestand, die
# Korrektur bleibt beim Menschen. Der Sammelbeleg gehoert dazu, damit eine
# eingelesene Rechnung ihr Original mitbringt (die einzelne nimmt
# ``create_invoice`` selbst als Datei an).
SCHLUESSEL_ERFASSEN = frozenset({
    'create_invoice',
    'create_invoice_document',
    'create_reading',
    'add_payment',
})

NIE_PER_SCHLUESSEL = frozenset({
    # Zugang
    'konten_auflisten', 'konto_anlegen', 'konto_passwort_aendern',
    'anmeldung_ausschalten', 'logout', 'huelle_passwort',
    'zugriffsschluessel_auflisten', 'zugriffsschluessel_anlegen',
    'zugriffsschluessel_widerrufen',
    # Der ganze Bestand auf einmal
    'export_data', 'belege_exportieren', 'umzug_export', 'umzug_pruefen',
    'umzug_uebernehmen', 'umzug_hochladen_beginnen', 'umzug_hochladen_stueck',
    'backup_erstellen', 'backup_einspielen', 'reset_db',
    # Rechtswirksam oder nicht rueckholbar
    'finalize_bill', 'korrigiere_billing_report', 'zustellung_melden',
    'aktualisierung_installieren',
    # Loeschen
    'update_delete_property', 'update_delete_apartment', 'update_delete_tenant',
    'delete_invoice', 'delete_reading', 'delete_payment', 'bulk_delete_payments',
    'delete_billing_report', 'delete_meter', 'delete_category', 'delete_provider',
    'delete_invoice_document', 'beispielimmobilie_entfernen',
    'delete_haushaltsgroesse', 'delete_heizungsanlage', 'delete_kaltmiete_soll',
    'delete_vorauszahlung_soll', 'loesche_anschreiben_vorlage',
    'vermieter_logo_loeschen',
})

# Felder, mit denen ein Anlege-Endpunkt nebenbei Bestehendes aendert. Mit
# Schluessel abgelehnt, damit „erfassen“ wirklich nur anlegt: der Haken
# „Rechnungsdatum fuer alle Rechnungen des Belegs“ schreibt in Rechnungen,
# die schon da sind (app.py, _datum_fuer_den_beleg).
AENDERT_BESTEHENDES = {
    'create_invoice': ('rechnungsdatum_fuer_beleg',),
}


def im_kopf() -> str | None:
    """Der Schluessel aus ``Authorization: Bearer nkf_...``, sonst None.

    Nur das Praefix macht einen Bearer-Kopf zum Zugriffsschluessel. Ein
    Reverse Proxy vor Docker (etwa oauth2-proxy) kann einen eigenen Token
    weiterreichen; der darf die Sitzung im Browser nicht ausser Kraft setzen
    und nicht als Fehlversuch zaehlen.
    """
    art, _, wert = request.headers.get('Authorization', '').partition(' ')
    wert = wert.strip()
    if art.lower() != 'bearer' or not wert.startswith(PRAEFIX):
        return None
    return wert


def _hash(schluessel: str) -> str:
    return hashlib.sha256(schluessel.encode()).hexdigest()


def aktueller() -> ApiSchluessel | None:
    """Der Schluessel der laufenden Anfrage, sonst None."""
    if not has_request_context():
        return None
    return request.environ.get(UMGEBUNG)


def anfrage_pruefen(app, ordner):
    """Laesst eine Anfrage mit Schluessel durch (None) oder lehnt sie ab.

    Gerufen aus ``auth._require_login``, sobald ``Bearer nkf_...`` da ist. Ab
    hier entscheidet nur der Schluessel, eine Sitzung im selben Client
    spielt keine Rolle mehr.
    """
    roh = im_kopf() or ''
    zeile = None
    if len(roh) <= 100:
        zeile = ApiSchluessel.query.filter_by(hash=_hash(roh)).first()
    if zeile is None or zeile.user is None or not zeile.user.is_active:
        # Gezaehlt wird je Adresse und je Anfang des Schluessels: wer
        # denselben falschen Schluessel wiederholt, ist nach GRENZE_KONTO
        # gesperrt, wer beliebige probiert, nach GRENZE_IP. Die Adresse hat
        # einen eigenen Topf neben der Anmeldung: hinter einem Reverse Proxy
        # kommen alle von derselben, und ein Programm mit veralteten
        # Schluesseln soll den Menschen nicht aussperren.
        #
        # Ein gueltiger Schluessel geht an der Sperre vorbei und zaehlt
        # nicht, auch nicht zurueck (Review zu #48): 256 Bit Zufall raet
        # niemand, die Sperre daempft nur das Rauschen. Sie traefe sonst
        # hinter dem Proxy jedes Programm, sobald einer zwanzig falsche
        # schickt; und ein Erfolg, der den Zaehler leert, hielte sie fuer
        # den Falschen an derselben Adresse offen. Gesperrt antwortet sie
        # sofort und ohne Wartezeit: das Raten bremsen muss sie bei 256 Bit
        # nicht.
        adresse = f'schluessel@{request.remote_addr}'
        merkmal = f'schluessel:{roh[:12]}'
        rest = anmeldeschutz.gesperrt_fuer(ordner, merkmal, adresse)
        if rest:
            minuten = max(1, (rest + 59) // 60)
            antwort = make_response(jsonify({
                'error': f'Zu viele Fehlversuche. Bitte warten Sie {minuten} Minuten.',
                'code': 'anmeldung_gesperrt'}), 429)
            antwort.headers['Retry-After'] = str(rest)
            return antwort
        anzahl = anmeldeschutz.fehlversuch(ordner, merkmal, adresse)
        time.sleep(anmeldeschutz.wartezeit(anzahl))
        return jsonify({
            'error': 'Der Zugriffsschlüssel ist ungültig oder widerrufen.',
            'code': 'schluessel_ungueltig'}), 401
    request.environ[UMGEBUNG] = zeile
    endpunkt = request.endpoint
    if endpunkt in NIE_PER_SCHLUESSEL or \
            endpunkt not in SCHLUESSEL_LESEN | SCHLUESSEL_ERFASSEN:
        return jsonify({
            'error': 'Das geht nicht mit einem Zugriffsschlüssel, nur in der Oberfläche.',
            'code': 'nicht_per_schluessel'}), 403
    if endpunkt in SCHLUESSEL_ERFASSEN and zeile.umfang != 'erfassen':
        return jsonify({
            'error': 'Dieser Zugriffsschlüssel darf nur lesen.',
            'code': 'schluessel_umfang'}), 403
    felder = AENDERT_BESTEHENDES.get(endpunkt, ())
    if felder and any(Eingabe.aus_request().wahrheit(f) for f in felder):
        return jsonify({
            'error': 'Das ändert vorhandene Einträge und geht nur in der Oberfläche.',
            'code': 'nicht_per_schluessel'}), 403
    _vermerken(app, zeile, schreibt=endpunkt in SCHLUESSEL_ERFASSEN)
    return None


def _vermerken(app, zeile: ApiSchluessel, schreibt: bool) -> None:
    """Buchfuehrung nach bestandener Pruefung: „zuletzt benutzt“ fuer die
    Liste, und jeder schreibende Zugriff ins Protokoll."""
    jetzt = zeit.jetzt_utc()
    zuletzt = zeile.zuletzt_benutzt_am
    if zuletzt is None or (jetzt - zuletzt).total_seconds() >= VERMERK_ABSTAND_S:
        zeile.zuletzt_benutzt_am = jetzt
        db.session.commit()
    if schreibt:
        app.logger.info('Zugriffsschlüssel „%s“ (Konto %s): %s %s',
                        zeile.name, zeile.user.username, request.method, request.path)


def _zeile(eintrag: ApiSchluessel) -> dict:
    return {
        'id': eintrag.id,
        'name': eintrag.name,
        'umfang': eintrag.umfang,
        'konto': eintrag.user.username if eintrag.user else None,
        'angelegt_am': zeit.als_ortszeit(eintrag.angelegt_am),
        'zuletzt_benutzt': zeit.als_ortszeit(eintrag.zuletzt_benutzt_am)
                           if eintrag.zuletzt_benutzt_am else None,
    }


def init_zugriffsschluessel(app, current_user, ohne_anmeldung_aktiv, fehltext_konto):
    """Die Verwaltungsrouten. Die Helfer kommen aus ``auth`` herein, damit
    dieses Modul ``auth`` nicht importiert (auth importiert dieses)."""

    @app.route('/api/zugriffsschluessel', methods=['GET'])
    def zugriffsschluessel_auflisten():
        if ohne_anmeldung_aktiv(app):
            return jsonify([]), 200
        eintraege = ApiSchluessel.query.order_by(ApiSchluessel.angelegt_am).all()
        return jsonify([_zeile(e) for e in eintraege]), 200

    @app.route('/api/zugriffsschluessel', methods=['POST'])
    def zugriffsschluessel_anlegen():
        """Neuer Schluessel fuer das angemeldete Konto. Der Klartext steht
        nur in dieser Antwort; danach kennt ihn niemand mehr."""
        if ohne_anmeldung_aktiv(app):
            return jsonify({'error': fehltext_konto}), 409
        user = current_user()
        eingabe = Eingabe.aus_request()
        name = (eingabe.text('name', pflicht=True, maxlaenge=60) or '').strip()
        if not name:
            raise EingabeFehler('Bitte geben Sie dem Schlüssel einen Namen.', 'name')
        umfang = eingabe.text('umfang', pflicht=True)
        if umfang not in UMFAENGE:
            raise EingabeFehler('Der Umfang ist „lesen“ oder „erfassen“.', 'umfang')
        if db.session.query(ApiSchluessel.id).count() >= HOECHSTENS:
            return jsonify({'error': f'Mehr als {HOECHSTENS} Zugriffsschlüssel '
                                     'gibt es nicht. Löschen Sie einen, den '
                                     'Sie nicht mehr brauchen.'}), 400
        schluessel = PRAEFIX + secrets.token_urlsafe(32)
        eintrag = ApiSchluessel(user_id=user.id, name=name, umfang=umfang,
                                hash=_hash(schluessel))
        db.session.add(eintrag)
        db.session.commit()
        app.logger.info('Zugriffsschlüssel „%s“ (%s) für Konto %s angelegt.',
                        name, umfang, user.username)
        return jsonify({**_zeile(eintrag), 'schluessel': schluessel}), 201

    @app.route('/api/zugriffsschluessel/<int:id>', methods=['DELETE'])
    def zugriffsschluessel_widerrufen(id):
        eintrag = db.session.get(ApiSchluessel, id)
        if eintrag is None:
            return jsonify({'error': 'Diesen Zugriffsschlüssel gibt es nicht.'}), 404
        db.session.delete(eintrag)
        db.session.commit()
        app.logger.info('Zugriffsschlüssel „%s“ widerrufen.', eintrag.name)
        return jsonify({'status': 'widerrufen'}), 200


def alle_loeschen() -> int:
    """Fuer "Anmeldung ausschalten": ohne Konten keine Schluessel."""
    return ApiSchluessel.query.delete()


__all__ = ['SCHLUESSEL_LESEN', 'SCHLUESSEL_ERFASSEN', 'NIE_PER_SCHLUESSEL', 'PRUEFEN',
           'im_kopf', 'anfrage_pruefen', 'aktueller', 'init_zugriffsschluessel',
           'alle_loeschen']
