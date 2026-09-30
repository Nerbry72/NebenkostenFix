"""Routentabellentest (NK-020).

Die Sperre aus NK-019 arbeitet mit einer Positivliste. Eine Positivliste ist
nur so gut wie die Aufmerksamkeit dessen, der die naechste Route hinzufuegt.
Dieser Test nimmt ihm die Aufmerksamkeit ab: er laeuft ueber app.url_map,
also ueber die Wahrheit von Flask, und nicht ueber eine Liste, die jemand von
Hand pflegt.

Zwei Netze:

1. ROUTEN_INVENTAR haelt den Stand fest. Wer eine Route hinzufuegt oder
   entfernt, bekommt einen roten Test und muss sich entscheiden: oeffentlich
   oder gesperrt. Ohne Entscheidung kein gruener Lauf.
2. Fuer jede Route, die nicht auf der Positivliste steht, wird der Aufruf
   ohne Sitzung tatsaechlich abgesetzt, mit jeder erlaubten Methode. Eine
   versehentlich offene Route faellt hier auf, auch wenn jemand das Inventar
   pflichtschuldig mitgepflegt hat.
"""

import re

import pytest

from nebenkostenfix.auth import PUBLIC_ENDPOINTS


# Stand vom 30.09.2026, 116 Routen (NK-148: Drittlizenzen; NK-174/175: Haftung, Update-Einstellung, Suche beim Start; NK-176: Lizenzrouten entfernt; NK-145: CSV-Export; NK-129: /api/files -> /api/dateien; NK-131: Belege-Export). Aendert sich diese Menge, ist das kein
# Fehler im Test, sondern eine Entscheidung, die getroffen werden muss.
ROUTEN_INVENTAR = frozenset({
    'belege_exportieren',
    'huelle_passwort',
    'haftung_anzeigen',
    'haftung_bestaetigen',
    'ueber_anzeigen',
    'drittlizenzen_anzeigen',
    'update_einstellung_anzeigen',
    'update_einstellung_setzen',
    'aktualisierung_automatisch',
    'vermieter_logo_zeigen',
    'vermieter_logo_hochladen',
    'vermieter_logo_loeschen',
    'aktualisierung_suchen',
    'aktualisierung_installieren',
    'get_billing_report_csv',
    'add_payment',
    'analytics_apartment',
    'analytics_building',
    'analytics_data_quality',
    'auth_me',
    'backup_erstellen',
    'backup_einspielen',
    'umzug_export',
    'import_arten',
    'jahresabrechnung_stand',
    'beispielimmobilie_entfernen',
    'hilfe_kurzanleitung',
    'import_vorlage',
    'import_lesen',
    'import_pruefen',
    'import_uebernehmen',
    'import_tabelle',
    'umzug_hochladen_beginnen',
    'umzug_hochladen_stand',
    'umzug_hochladen_stueck',
    'umzug_importordner',
    'umzug_pruefen',
    'umzug_uebernehmen',
    'backup_liste',
    'backup_status',
    'konto_anlegen',
    'konto_passwort_aendern',
    'konten_auflisten',
    'billing_preflight',
    'billing_suggestions',
    'bulk_delete_payments',
    'check_plausibility',
    'create_apartment',
    'create_invoice',
    'create_invoice_document',
    'create_meter',
    'create_property',
    'create_provider',
    'create_reading',
    'create_tenant',
    'delete_billing_report',
    'delete_haushaltsgroesse',
    'delete_invoice',
    'delete_invoice_document',
    'delete_meter',
    'delete_payment',
    'delete_provider',
    'delete_reading',
    'download_billing_report',
    'einrichtung',
    'export_data',
    'finalize_bill',
    'generate_bill',
    'get_all_apartments',
    'get_all_billing_reports',
    'get_apartments',
    'get_billing_report_details',
    'get_billing_report_belege',
    'get_anschreiben_vorlage',
    'get_heizungsanlagen',
    'create_heizungsanlage',
    'update_heizungsanlage',
    'delete_heizungsanlage',
    'korrigiere_billing_report',
    'get_categories',
    'datei_ausliefern',
    'get_haushaltsgroessen',
    'get_interpolation_audit',
    'loesche_anschreiben_vorlage',
    'setze_anschreiben_vorlage',
    'get_invoice_documents',
    'get_invoices',
    'zeitleiste_route',
    'get_meters',
    'get_payments',
    'get_properties',
    'get_providers',
    'get_readings',
    'get_tenant_billing_reports',
    'get_tenant_contract',
    'export_tenant',
    'beispielimmobilie_route',
    'get_tenant_profiles',
    'get_tenants',
    'get_vermieterdaten',
    'get_zeitraumvorschlag',
    'health_check',
    'index',
    'login',
    'logout',
    'reset_db',
    'save_haushaltsgroesse',
    'save_tenant_profiles',
    'setze_vermieterdaten',
    'static',
    'update_delete_apartment',
    'update_delete_property',
    'update_delete_tenant',
    'update_invoice',
    'update_invoice_document',
    'update_reading',
    'zustellung_melden',
})


def _beispielpfad(regel):
    """Baut aus einer Regel einen aufrufbaren Pfad.

    /api/tenants/<int:id>/profiles wird zu /api/tenants/1/profiles. Die Werte
    muessen nicht existieren: die Sperre greift in before_request, also bevor
    irgendeine Ansichtsfunktion die Id zu sehen bekommt.
    """
    pfad = re.sub(r'<path:[^>]+>', 'beispiel.txt', regel.rule)
    pfad = re.sub(r'<int:[^>]+>', '1', pfad)
    pfad = re.sub(r'<float:[^>]+>', '1.0', pfad)
    return re.sub(r'<[^>]+>', 'beispiel', pfad)


def _aufrufbare_regeln(app):
    """Jede Regel mit jeder Methode, die ein Aufrufer wirklich schicken kann."""
    for regel in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        for methode in sorted(regel.methods - {'HEAD', 'OPTIONS'}):
            yield regel, methode


def _von_der_sperre_abgewiesen(antwort):
    """Wahr, wenn die Sperre aus NK-019 geantwortet hat.

    Der blosse Statuscode reicht nicht: POST /login antwortet auf falsche
    Zugangsdaten ebenfalls mit 401, das ist die Anmeldung selbst und nicht die
    Sperre. Unterschieden wird am Feld code, das nur _deny() setzt.
    """
    if antwort.status_code == 401:
        rumpf = antwort.get_json(silent=True) or {}
        return rumpf.get('code') == 'auth_required'
    if antwort.status_code in (301, 302, 303, 307, 308):
        return '/login' in antwort.headers.get('Location', '')
    return False


# --------------------------------------------------------------------------
# Inventar
# --------------------------------------------------------------------------

def test_das_inventar_deckt_sich_mit_der_routentabelle(app_ctx):
    """Neue oder entfernte Route ohne Eintrag: roter Test (Kriterium 4)."""
    ist = {regel.endpoint for regel in app_ctx.app.url_map.iter_rules()}
    neu = ist - ROUTEN_INVENTAR
    verschwunden = ROUTEN_INVENTAR - ist
    assert not neu, (
        'Neue Route(n) ohne Eintrag im Inventar: ' + ', '.join(sorted(neu)) +
        '. Entscheide, ob sie oeffentlich sein soll (dann zusaetzlich in '
        'auth.PUBLIC_ENDPOINTS), und trage sie hier ein.'
    )
    assert not verschwunden, (
        'Route(n) verschwunden, Inventar veraltet: ' +
        ', '.join(sorted(verschwunden))
    )


def test_die_positivliste_enthaelt_nur_existierende_routen(app_ctx):
    """Ein Tippfehler in PUBLIC_ENDPOINTS soll nicht still liegenbleiben."""
    ist = {regel.endpoint for regel in app_ctx.app.url_map.iter_rules()}
    assert PUBLIC_ENDPOINTS <= ist, (
        'Positivliste nennt Endpunkte, die es nicht gibt: ' +
        ', '.join(sorted(PUBLIC_ENDPOINTS - ist))
    )


def test_die_positivliste_bleibt_klein(app_ctx):
    """Drei offene Endpunkte, keiner mehr, keiner weniger.

    Doppelt zum Test in test_auth.py, aber hier aus der anderen Richtung: dort
    steht die Menge als Erwartung, hier haengt sie an der Routentabelle. Wer
    beide gleichzeitig aufweicht, tut es mit Absicht. Seit NK-127 gehoert
    /einrichtung dazu: der erste Start ohne Konto, durch den Einmal-Code
    gesichert, danach umgeleitet zur Anmeldung.
    """
    assert PUBLIC_ENDPOINTS == frozenset({'health_check', 'login', 'einrichtung'})


# --------------------------------------------------------------------------
# Sperre gegen die echte Routentabelle
# --------------------------------------------------------------------------

def test_jede_gesperrte_route_weist_den_anonymen_aufruf_ab(anon_client, app_ctx):
    """Kriterium 3: nicht die Liste pruefen, sondern jeden Aufruf absetzen.

    Faellt eine Route durch, wurde ihre Ansichtsfunktion in diesem Test
    wirklich ausgefuehrt. Das ist gewollt: genau dieser Schaden droht in der
    Auslieferung, und die Testdatenbank ist pro Test frisch.
    """
    durchgerutscht = []
    for regel, methode in _aufrufbare_regeln(app_ctx.app):
        if regel.endpoint in PUBLIC_ENDPOINTS:
            continue
        pfad = _beispielpfad(regel)
        antwort = anon_client.open(pfad, method=methode)
        if _von_der_sperre_abgewiesen(antwort):
            continue
        durchgerutscht.append(
            f'{methode} {pfad} ({regel.endpoint}) -> {antwort.status_code}')
    assert not durchgerutscht, (
        'Diese Aufrufe kamen ohne Anmeldung durch:\n' +
        '\n'.join(durchgerutscht)
    )


def test_die_offenen_routen_bleiben_ohne_anmeldung_erreichbar(anon_client, app_ctx):
    """Die Kehrseite: die Sperre darf die Anmeldung nicht selbst aussperren."""
    unerreichbar = []
    for regel, methode in _aufrufbare_regeln(app_ctx.app):
        if regel.endpoint not in PUBLIC_ENDPOINTS:
            continue
        pfad = _beispielpfad(regel)
        antwort = anon_client.open(pfad, method=methode)
        # 404 ist in Ordnung: /static/beispiel.txt gibt es nicht. Und der 401
        # von POST /login auf leere Zugangsdaten ist die Anmeldung selbst,
        # nicht die Sperre. Nur ein echtes Abweisen zaehlt hier als Fehler.
        if _von_der_sperre_abgewiesen(antwort):
            unerreichbar.append(f'{methode} {pfad} ({regel.endpoint})')
    assert not unerreichbar, (
        'Diese offenen Routen antworten mit 401:\n' + '\n'.join(unerreichbar))


@pytest.mark.parametrize('methode,pfad', [
    ('POST', '/api/debug/reset_db'),
    ('DELETE', '/api/payments/bulk'),
    ('DELETE', '/api/properties/1'),
    ('GET', '/api/export'),
])
def test_die_gefaehrlichen_routen_namentlich(anon_client, methode, pfad):
    """Vier Aufrufe, die ohne Sperre Daten loeschen oder mitnehmen.

    Der Schleifentest oben deckt sie mit ab. Sie stehen hier zusaetzlich
    namentlich, damit ein Ausfall im Testbericht sofort lesbar ist statt in
    einer Liste von 59 Zeilen.
    """
    antwort = anon_client.open(pfad, method=methode)
    assert antwort.status_code == 401
    assert antwort.get_json()['code'] == 'auth_required'


def test_der_schleifentest_prueft_wirklich_alle_routen(app_ctx):
    """Schutz gegen einen Filter, der versehentlich alles wegwirft."""
    paare = list(_aufrufbare_regeln(app_ctx.app))
    gesperrt = [p for p in paare if p[0].endpoint not in PUBLIC_ENDPOINTS]
    assert len(paare) >= 60
    assert len(gesperrt) >= 55


def test_beispielpfad_ersetzt_jeden_platzhalter(app_ctx):
    """Ein uebrig gebliebenes <int:id> wuerde 404 statt 401 liefern."""
    for regel in app_ctx.app.url_map.iter_rules():
        pfad = _beispielpfad(regel)
        assert '<' not in pfad and '>' not in pfad, regel.rule


# --------------------------------------------------------------------------
# Gegenprobe: die Sperre darf nichts Legitimes kaputtmachen
# --------------------------------------------------------------------------

def test_jede_lesende_route_antwortet_angemeldet_fachlich(auth_client, app_ctx):
    """Die andere Haelfte der Regression zu NK-019.

    Der Schleifentest oben beweist, dass niemand ohne Sitzung hereinkommt.
    Er beweist nicht, dass jemand mit Sitzung noch arbeiten kann. Genau dieser
    Fehler faellt sonst erst im Browser auf, und bis NK-021 sieht ihn dort
    niemand: das Frontend zeigt bei 401 stillschweigend leere Listen.

    Geprueft wird nur, was ohne Nebenwirkung geht, also GET. Erwartet wird eine
    fachliche Antwort: 200, oder 400 bei fehlendem Parameter, oder 404 fuer
    eine Id, die es im leeren Bestand nicht gibt. Nicht erwartet wird 401
    (die Sperre greift zu weit) und nicht 5xx (die Route ist kaputt).
    """
    auffaellig = []
    for regel, methode in _aufrufbare_regeln(app_ctx.app):
        if methode != 'GET':
            continue
        # static zeigt auf eine Datei, die es nicht gibt, und logout wuerde
        # die Sitzung mitten in der Schleife beenden. Beide stehen namentlich
        # in test_auth.py.
        if regel.endpoint in ('static', 'logout'):
            continue
        pfad = _beispielpfad(regel)
        antwort = auth_client.open(pfad, method='GET')
        if antwort.status_code == 401 or antwort.status_code >= 500:
            auffaellig.append(
                f'GET {pfad} ({regel.endpoint}) -> {antwort.status_code}')
    assert not auffaellig, (
        'Diese Routen antworten dem angemeldeten Benutzer nicht fachlich:\n' +
        '\n'.join(auffaellig)
    )


def test_die_gegenprobe_faehrt_genug_routen_an(app_ctx):
    """Ohne diese Zusicherung koennte der Filter oben stillschweigend leerlaufen."""
    lesend = [
        regel for regel, methode in _aufrufbare_regeln(app_ctx.app)
        if methode == 'GET' and regel.endpoint not in ('static', 'logout')
    ]
    assert len(lesend) >= 25
