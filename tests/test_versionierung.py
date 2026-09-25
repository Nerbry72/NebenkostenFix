"""Die Versionierung finalisierter Abrechnungen (R-DOC-02, NK-061).

Eine als final erzeugte Abrechnung ist ein zugegangenes Dokument: sie darf
nachträglich nicht stillschweigend anders berechnet werden. Die Festsetzung
schreibt deshalb einen Schnappschuss ihrer Eingangsdaten und ihres
Ergebnisses -- samt Software- und Regelstand. Der Regeltest der Regel:
Nach Änderung eines Zählerstands liefert eine bereits finalisierte
Abrechnung unverändert dasselbe Ergebnis. Eine Korrektur ändert nichts --
sie legt eine neue Version an, die auf die ersetzte verweist.
"""

import re
from datetime import date

from abrechnung_version import SOFTWARE_VERSION, REGEL_VERSION
from billing_factories import (
    apt,
    category,
    house,
    invoice,
    meter,
    payment,
    profile,
    reading,
    tenant,
)

ZEITRAUM = {'start_date': '2025-01-01', 'end_date': '2025-12-31'}


def _welt(app_ctx):
    """Zwei Mieter, je ein eigener Wasserzähler, eine Rechnung (2025).

    Die Kostenart läuft über 'direkt': die Zeile rechnet aus dem
    Zählerstand, und weil zwei Wohnungen teilen, ändert eine Änderung der
    Lesung auch den Anteil -- genau die Stelle, an der die Regel ihre
    Unveränderlichkeit misst. Liefert die drei Kennungen (Mieter A, dessen
    Zähler, dessen letzte Lesung); nach den Routen wird immer frisch
    nachgeladen, nichts bleibt über einen Request hinaus.
    """
    from models import db

    kategorie = category('Wasserversorgung')
    prop = house()
    wohnung_a = apt(prop, 'EG links', 50.0)
    wohnung_b = apt(prop, 'EG rechts', 50.0)
    mieter_a = tenant(wohnung_a, 'Anna Mieterin', move_in=date(2024, 1, 1))
    mieter_b = tenant(wohnung_b, 'Berta Mieterin', move_in=date(2024, 1, 1))
    profile(mieter_a, kategorie, 'direkt')
    profile(mieter_b, kategorie, 'direkt')
    zaehler_a = meter(prop, kategorie, 'WA-A', is_main=False, apartment=wohnung_a)
    zaehler_b = meter(prop, kategorie, 'WA-B', is_main=False, apartment=wohnung_b)
    reading(zaehler_a, date(2025, 1, 1), 0.0)
    lese_ende = reading(zaehler_a, date(2025, 12, 31), 1000.0)
    reading(zaehler_b, date(2025, 1, 1), 0.0)
    reading(zaehler_b, date(2025, 12, 31), 1000.0)
    invoice(prop, kategorie, 2400.0, date(2025, 1, 1), date(2025, 12, 31))
    payment(mieter_a, 300.0, date(2025, 6, 1))
    db.session.commit()
    return mieter_a.id, zaehler_a.id, lese_ende.id


def _finalisiere(auth_client, mieter_id, **zusatz):
    """Finalisiert einmal und liefert den Bericht."""
    from models import TenantBillingReport

    antwort = auth_client.post('/api/billing/finalize', json={
        'tenant_id': mieter_id, **ZEITRAUM, **zusatz})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    return TenantBillingReport.query.one()


def _bericht(bericht_id):
    """Lädt den Bericht frisch (nach Requests ist die Sitzung leer)."""
    from models import db, TenantBillingReport

    return db.session.get(TenantBillingReport, bericht_id)


# --- Die Festsetzung: der Schnappschuss entsteht ------------------------------


def test_die_festsetzung_schreibt_die_erste_version(auth_client, app_ctx):
    """Die erste Version trägt Nummer 1, beide Stände und den Verweis leer.

    Eingangsdaten und Ergebnis liegen als Schnappschuss bei -- der Zähler
    mit seinen beiden Lesungen in den Eingaben, der Gesamtbetrag im
    Ergebnis."""
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)

    versionen = list(report.versionen)
    assert len(versionen) == 1
    erste = versionen[0]
    assert erste.nummer == 1
    assert erste.software_version == SOFTWARE_VERSION
    assert erste.regel_version == REGEL_VERSION
    assert erste.ersetzt_version_id is None

    lesungen = erste.eingangsdaten['zaehler'][0]['staende']
    assert [l['wert'] for l in lesungen] == [0.0, 1000.0]
    assert erste.ergebnis['total_amount'] == '1200.00'


def test_der_schnappschuss_ist_echte_abschrift(auth_client, app_ctx):
    """Eingangsdaten zeigen den Vorgang, nicht die Datenbank: der gestutzte
    Zeitraum und der Mieter stehen in den Eingaben."""
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)

    erste = report.aktuelle_version
    assert erste.eingangsdaten['beginn'] == '2025-01-01'
    assert erste.eingangsdaten['ende'] == '2025-12-31'
    assert erste.eingangsdaten['mieter']['name'] == 'Anna Mieterin'
    assert erste.ergebnis['start_date'] == '2025-01-01'


# --- Der Regeltest: Änderung verändert die Abrechnung nicht -------------------


def test_geaenderter_zaehlerstand_laesst_die_abrechnung_unberuehrt(
        auth_client, app_ctx):
    """Der Regeltest von R-DOC-02: Nach Änderung eines Zählerstands liefert
    die finalisierte Abrechnung unverändert dasselbe Ergebnis."""
    from models import db, MeterReading
    from billing_engine import BillingEngine

    mieter_id, _, lese_id = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    bericht_id = report.id

    davor = auth_client.get(f'/api/billing/reports/{bericht_id}/details')
    assert davor.status_code == 200
    assert davor.get_json()['version'] == 1
    assert davor.get_json()['ergebnis']['total_amount'] == '1200.00'

    # Der Vermieter bessert einen Zählerstand nach.
    lese_ende = db.session.get(MeterReading, lese_id)
    lese_ende.value = 800.0
    db.session.commit()

    danach = auth_client.get(f'/api/billing/reports/{bericht_id}/details')
    assert danach.get_json()['version'] == 1
    assert danach.get_json()['ergebnis']['total_amount'] == '1200.00'

    # Und die Probe, dass der Test beißt: frisch gerechnet wäre es anders.
    engine = BillingEngine(mieter_id, ZEITRAUM['start_date'], ZEITRAUM['end_date'])
    frisch = engine.calculate_bill()
    assert str(frisch['total_amount']) != '1200.00'


def test_die_korrektur_legt_eine_neue_version_mit_verweis_an(
        auth_client, app_ctx):
    """Die Korrektur ändert die ersetzte Version nicht; sie legt Version 2
    an, die auf die ersetzte verweist, und setzt die PDFs neu auf."""
    from models import db, MeterReading
    from billing_engine import BillingEngine

    mieter_id, _, lese_id = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    bericht_id = report.id
    erste = report.aktuelle_version
    erste_id, alter_pfad = erste.id, report.document_path

    lese_ende = db.session.get(MeterReading, lese_id)
    lese_ende.value = 800.0
    db.session.commit()

    antwort = auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur')
    assert antwort.status_code == 201, antwort.get_data(as_text=True)
    koerper = antwort.get_json()
    assert koerper['versionsnummer'] == 2
    assert koerper['ersetzt_version_id'] == erste_id

    report = _bericht(bericht_id)
    erste = db.session.get(type(report.versionen[0]), erste_id)
    assert len(report.versionen) == 2

    # Die ersetzte Version steht unverändert als Geschichte.
    assert erste.nummer == 1
    assert erste.ergebnis['total_amount'] == '1200.00'

    # Die neue Version rechnet die aktuellen Daten.
    neue = report.aktuelle_version
    assert neue.nummer == 2
    assert neue.ersetzt_version_id == erste_id
    engine = BillingEngine(mieter_id, ZEITRAUM['start_date'], ZEITRAUM['end_date'])
    frisch = engine.calculate_bill()
    assert neue.ergebnis['total_amount'] == str(frisch['total_amount'])

    # Das Blatt trägt die korrigierten Zahlen: neues PDF, neuer Name.
    assert report.document_path != alter_pfad
    # Seit NK-131 neutral benannt; die Fassung nennt der sprechende
    # Export (belege_export: _Korrektur2).
    assert re.match(r'^\d{4}/[0-9a-f]{32}\.pdf$', report.document_path)

    # Und die Detailroute liefert fortan die neue Version.
    details = auth_client.get(f'/api/billing/reports/{bericht_id}/details')
    assert details.get_json()['version'] == 2
    assert details.get_json()['ergebnis']['total_amount'] == str(frisch['total_amount'])


def test_die_korrektur_ohne_aenderung_wird_abgelehnt(auth_client, app_ctx):
    """Ohne geänderte Daten wäre eine neue Version nur eine Kopie -- die
    Route lehnt ab, und es bleibt bei der einen Version."""
    from models import db

    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    bericht_id = report.id

    antwort = auth_client.post(f'/api/billing/reports/{bericht_id}/korrektur')
    assert antwort.status_code == 400
    assert 'Kopie' in antwort.get_json()['error']
    assert len(_bericht(bericht_id).versionen) == 1


def test_die_zweite_fassung_ist_keine_korrektur(auth_client, app_ctx):
    """Die detaillierte Fassung derselben Rechnung ergänzt nur das zweite
    PDF; das Ergebnis ist dasselbe, also keine neue Version."""
    mieter_id, _, _ = _welt(app_ctx)
    report = _finalisiere(auth_client, mieter_id)
    bericht_id = report.id
    report = _finalisiere(auth_client, mieter_id, detailed=True)

    assert report.document_path is not None
    assert report.document_path_detailed is not None
    assert len(report.versionen) == 1


# --- Der Altbestand: ohne Schnappschuss wird weiter live gerechnet ------------


def test_altbestand_ohne_version_wird_weiter_live_gerechnet(auth_client, app_ctx):
    """Abrechnungen aus der Zeit vor der Versionstabelle tragen keinen
    Schnappschuss -- die Detailroute rechnet für sie weiter live (D-59),
    erkennbar daran, dass keine Version mitkommt. Über die JSON-Grenze geht
    Geld als Zahl (NK-036), im Schnappschuss steht es als Zeichenkette
    (R-NUM-01): der Altbestand zeigt den Unterschied."""
    from models import TenantBillingReport, db
    from frist import frist_ende

    mieter_id, _, _ = _welt(app_ctx)
    report = TenantBillingReport(
        tenant_id=mieter_id,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        frist_ende=frist_ende(date(2025, 12, 31)),
    )
    db.session.add(report)
    db.session.commit()

    antwort = auth_client.get(f'/api/billing/reports/{report.id}/details')
    assert antwort.status_code == 200
    koerper = antwort.get_json()
    assert 'version' not in koerper
    assert koerper['total_amount'] == 1200.0
