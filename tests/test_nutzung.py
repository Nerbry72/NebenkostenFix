"""NK-045: die Nutzungsart an ihrem einen Ort, im Schema und im Kern.

Der Befund war keine falsche Rechnung, sondern eine fehlende Frage: bis zu
dieser Karte gab es kein Feld dafuer, wofuer eine Einheit da ist. Jedes
Objekt sah aus wie ein Wohnhaus -- auch das mit dem Laden im Erdgeschoss --
und der Vermieter bekam eine Abrechnung, die nach nichts aussah, aber nach
dem falschen Gesetz gerechnet war (R-CO2-04, § 8 CO2KostAufG).

Diese Datei prueft die ganze Kette, von unten nach oben:

1. ``nutzung.py`` selbst -- was durchgeht, was abgelehnt wird, und welchen
   Befund die Einheiten ueber ihr Objekt ergeben,
2. das Schema -- dass die Datenbank eine erfundene Nutzungsart auch dann
   abweist, wenn niemand durch die Eingabepruefung gekommen ist,
3. den Rechenkern -- dass ein Objekt, das dieses Programm nicht abrechnen
   darf, keine halbe Zeile bekommt,
4. die Wege nach aussen -- die drei Stammdaten an der Wohnung und die
   Haushaltsgroessen mit ihrer Historie (R-NUM-04).
"""

from __future__ import annotations

import ast
from tests.importwaechter import importierte_module
import doctest
import pathlib
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from nebenkostenfix import nutzung
from nebenkostenfix.nutzung import (
    ABRECHENBAR,
    ARTEN,
    GEMISCHT,
    GUELTIG,
    OBJEKTARTEN,
    VORGABE,
    NutzungsartFehler,
    aufzaehlung,
    ist_abrechenbar,
    ist_gueltig,
    normiere,
    objektart,
    objektart_beschriftung,
    pruefe,
)

from nebenkostenfix.abrechnungsdaten import lade_vorgang
from nebenkostenfix.rechenkern import BillingDataError, rechne
from nebenkostenfix.rechenkern import pruefe as vorpruefung

from tests import billing_factories as f

WURZEL = pathlib.Path(__file__).resolve().parent.parent


# --- Was das Modul ueber sich selbst sagt -----------------------------------


def test_doctests_im_modul_laufen():
    """Die Beispiele im Modul sind Zusagen, keine Illustration."""
    ergebnis = doctest.testmod(nutzung, verbose=False)
    assert ergebnis.failed == 0, f'{ergebnis.failed} Doctests in nutzung.py sind rot'


def test_vorgabe_ist_selbst_eine_nutzungsart():
    """Sonst setzte ausgerechnet die Wanderung einen ungueltigen Wert."""
    assert ist_gueltig(VORGABE)


def test_vorgabe_ist_wohnen():
    """Nicht Geschmack, sondern Vertraeglichkeit (D-36).

    Vor NK-045 gab es das Feld nicht, und alles wurde als Wohnraum
    gerechnet. Ein anderer Vorgabewert wuerde beim Einspielen eines Updates
    stillschweigend das Ergebnis aendern.
    """
    assert VORGABE == 'wohnen'


def test_gemischt_ist_keine_nutzungsart_einer_einheit():
    """``gemischt`` ist ein Befund ueber ein Haus, kein Wert fuer eine Spalte.

    Stuende es in ``GUELTIG``, liesse die CHECK-Bedingung es in die Spalte --
    und niemand koennte sagen, was eine zur Haelfte gemischte Wohnung ist.
    """
    assert GEMISCHT not in GUELTIG
    assert not ist_gueltig(GEMISCHT)


def test_jede_art_und_jeder_befund_hat_eine_beschriftung():
    """Kein Wert ohne Satz -- die Oberflaeche liest aus derselben Liste."""
    assert GUELTIG == set(ARTEN)
    assert all(beschriftung.strip() for beschriftung in ARTEN.values())
    # Die Befunde decken die Einheitenarten ab, dazu gemischt und leer.
    assert set(OBJEKTARTEN) == GUELTIG | {GEMISCHT, 'leer'}
    assert all(beschriftung.strip() for beschriftung in OBJEKTARTEN.values())


def test_nur_wohnen_ist_abrechenbar():
    """Die Entscheidung der Karte, als Test: ein Wohnhaus, sonst nichts.

    Fuer Nichtwohngebaeude sieht § 8 CO2KostAufG eine haelftige Teilung vor,
    bis ein Stufenmodell fuer sie in Kraft tritt, das es noch nicht gibt. Ein
    halb richtig gerechnetes Gewerbeobjekt waere schlimmer als gar keines.
    """
    assert ABRECHENBAR == {'wohnen'}
    assert ist_abrechenbar('wohnen')
    assert not ist_abrechenbar('gewerbe')
    assert not ist_abrechenbar(GEMISCHT)
    assert not ist_abrechenbar('leer')


def test_modul_haengt_nur_an_der_standardbibliothek():
    """Der Rechenkern importiert dieses Modul -- und kein ORM (NK-037)."""
    baum = ast.parse((WURZEL / 'nebenkostenfix' / 'nutzung.py').read_text(encoding='utf-8'))
    importiert = importierte_module(baum)
    assert importiert <= {'__future__'}, (
        f'nutzung.py zieht fremde Module herein: {sorted(importiert)}'
    )


# --- Die Pruefung -----------------------------------------------------------


@pytest.mark.parametrize('wert', sorted(GUELTIG))
def test_die_beiden_arten_gehen_durch(wert):
    assert pruefe(wert) == wert


@pytest.mark.parametrize('roh, erwartet', [
    ('  wohnen  ', 'wohnen'),
    ('WOHNEN', 'wohnen'),
    ('Gewerbe', 'gewerbe'),
    ('\tGEWERBE\n', 'gewerbe'),
])
def test_transportrauschen_wird_weggenommen(roh, erwartet):
    """Gross/klein und Leerzeichen sind Transport, kein Sachfehler."""
    assert pruefe(roh) == erwartet


@pytest.mark.parametrize('wert', [
    'buero', 'gemischt', 'leer', 'wohn', '', '   ', None, 1, True, ['wohnen'],
])
def test_alles_andere_wird_abgelehnt(wert):
    with pytest.raises(NutzungsartFehler):
        pruefe(wert)


def test_meldung_nennt_einheit_wert_und_alle_erlaubten():
    """Der Vermieter soll wissen, welche Zeile gemeint ist und was geht."""
    with pytest.raises(NutzungsartFehler) as fehler:
        pruefe('buero', einheit='Wohnung 3')
    text = str(fehler.value)
    assert 'Wohnung 3' in text
    assert 'buero' in text
    assert aufzaehlung() in text


def test_meldung_ohne_einheit_bleibt_lesbar():
    """Ueber die Schnittstelle kommt ein Wert auch ohne Wohnungsnamen."""
    with pytest.raises(NutzungsartFehler) as fehler:
        pruefe('buero')
    text = str(fehler.value)
    assert 'buero' in text
    assert 'Einheit „None“' not in text


def test_fehler_ist_ein_valueerror():
    """Damit ein ``except ValueError`` im Altbestand ihn weiter faengt."""
    assert issubclass(NutzungsartFehler, ValueError)


def test_normieren_erfindet_nichts():
    """Nur Rauschen weg -- kein Erraten, was gemeint gewesen sein koennte."""
    assert normiere('buero') == 'buero'
    assert normiere('Laden') == 'laden'


def test_normieren_geht_an_nicht_zeichenketten_vorbei():
    assert normiere(None) is None
    assert normiere(7) == 7


# --- Der Befund ueber das Objekt --------------------------------------------


@pytest.mark.parametrize('einheiten, erwartet', [
    (['wohnen'], 'wohnen'),
    (['wohnen', 'wohnen', 'wohnen'], 'wohnen'),
    (['gewerbe'], 'gewerbe'),
    (['gewerbe', 'gewerbe'], 'gewerbe'),
    (['wohnen', 'gewerbe'], GEMISCHT),
    (['gewerbe', 'wohnen', 'wohnen'], GEMISCHT),
    ([], 'leer'),
])
def test_objektart_ergibt_sich_aus_den_einheiten(einheiten, erwartet):
    assert objektart(einheiten) == erwartet


def test_leere_eintraege_zaehlen_als_wohnraum():
    """Eine Zeile aus einer Sicherung ohne gesetztes Feld ist Wohnraum.

    So wurde sie vor NK-045 gerechnet; ein ``None`` darf daraus kein
    gemischt genutztes Haus machen und die Abrechnung sperren.
    """
    assert objektart([None, '', 'wohnen']) == 'wohnen'
    assert objektart([None]) == 'wohnen'


def test_objektart_beschriftung_ist_deutsch_und_vollstaendig():
    for art in OBJEKTARTEN:
        assert objektart_beschriftung(art) == OBJEKTARTEN[art]
    # Was nicht im Katalog steht, kommt unveraendert zurueck statt als KeyError.
    assert objektart_beschriftung('erfunden') == 'erfunden'


@pytest.mark.parametrize('art', [GEMISCHT, 'gewerbe', 'leer'])
def test_ablehnung_nennt_objekt_gesetz_und_ausweg(art):
    """Eine Absage ohne Ausweg ist keine Hilfe."""
    satz = nutzung.ablehnung('Hauptstr. 5', art)
    assert 'Hauptstr. 5' in satz
    assert '§ 8 CO2KostAufG' in satz
    assert 'Wohnteil' in satz


def test_ablehnung_unterscheidet_gemischt_von_gewerbe():
    """Zwei Faelle, zwei Saetze: der Vermieter soll wissen, was los ist."""
    gemischt = nutzung.ablehnung('Haus', GEMISCHT)
    gewerbe = nutzung.ablehnung('Haus', 'gewerbe')
    assert 'Wohn- und Gewerbeeinheiten' in gemischt
    assert 'Wohn- und Gewerbeeinheiten' not in gewerbe
    assert 'Gewerbeobjekt' in gewerbe


# --- Das Schema -------------------------------------------------------------


def test_neue_wohnung_ist_wohnraum_ohne_eigenheiten(app_ctx):
    """Die Vorgabe am Modell ist der Normalfall eines Vermieters."""
    prop = f.house('Vorgabehaus')
    from nebenkostenfix.models import Apartment, db

    wohnung = Apartment(property_id=prop.id, name='EG', sqm=50.0)
    db.session.add(wohnung)
    db.session.commit()

    assert wohnung.nutzungsart == VORGABE
    assert wohnung.selbstversorger is False
    assert wohnung.eigennutzung is False


def test_die_datenbank_weist_eine_erfundene_nutzungsart_ab(app_ctx):
    """Gemessen an der Datenbank, nicht an der Eingabepruefung.

    Die Eingabepruefung deckt die Oberflaeche ab -- nicht die eingespielte
    Sicherung, nicht den Import, nicht die Zeile per ``sqlite3``. Dasselbe
    Argument wie beim CHECK auf der Abrechnungsart (NK-096).
    """
    from nebenkostenfix.models import Apartment, db

    prop = f.house('Checkhaus')
    db.session.add(Apartment(
        property_id=prop.id, name='Laden', sqm=30.0, nutzungsart='buero'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_ein_haushalt_ohne_kopf_wird_abgewiesen(app_ctx):
    """Null Personen ist kein Haushalt -- wer weg ist, hat ein Auszugsdatum."""
    from nebenkostenfix.models import Haushaltsgroesse, db

    prop = f.house('Kopfhaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Anna Mieterin')

    db.session.add(Haushaltsgroesse(
        tenant_id=mieter.id, gueltig_ab=date(2024, 1, 1), personenanzahl=0))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_zwei_eintraege_auf_denselben_tag_gehen_nicht(app_ctx):
    """Zwei Wahrheiten zum selben Stichtag -- welche gilt, koennte niemand sagen."""
    from nebenkostenfix.models import Haushaltsgroesse, db

    prop = f.house('Doppelhaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Anna Mieterin')
    f.haushalt(mieter, date(2024, 1, 1), 2)

    db.session.add(Haushaltsgroesse(
        tenant_id=mieter.id, gueltig_ab=date(2024, 1, 1), personenanzahl=3))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_personenanzahl_am_nimmt_den_juengsten_gueltigen_eintrag(app_ctx):
    """R-NUM-04: ein Haushalt aendert sich waehrend der Mietzeit.

    Zieht im Juli ein Kind aus, sind die Monate davor mit drei und die danach
    mit zwei Koepfen zu rechnen. Das Rechnen daraus ist NK-046; dass die
    Auskunft stimmt, gehoert hierher.
    """
    prop = f.house('Haushaltshaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Familie Berger', move_in=date(2024, 1, 1))
    f.haushalt(mieter, date(2024, 1, 1), 3)
    f.haushalt(mieter, date(2024, 7, 1), 2)

    assert mieter.personenanzahl_am(date(2024, 1, 1)) == 3
    assert mieter.personenanzahl_am(date(2024, 6, 30)) == 3
    # Der Stichtag selbst gilt schon: ``gueltig_ab``, nicht ``gueltig_nach``.
    assert mieter.personenanzahl_am(date(2024, 7, 1)) == 2
    assert mieter.personenanzahl_am(date(2024, 12, 31)) == 2


def test_personenanzahl_ohne_eintrag_ist_eins(app_ctx):
    """Das bisherige Verhalten (D-36): vor NK-045 zaehlte jedes Mietverhaeltnis
    als ein Kopf. Ein Update darf die Nenner nicht stillschweigend verschieben.
    """
    prop = f.house('Altbestandshaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Anna Mieterin', move_in=date(2024, 1, 1))

    assert mieter.haushaltsgroessen == []
    assert mieter.personenanzahl_am(date(2024, 6, 1)) == 1


def test_ein_stichtag_in_der_zukunft_zaehlt_noch_nicht(app_ctx):
    """Wer ab Juli zu dritt ist, ist es im Maerz noch nicht."""
    prop = f.house('Zukunftshaus')
    wohnung = f.apt(prop, 'EG', 50.0)
    mieter = f.tenant(wohnung, 'Anna Mieterin', move_in=date(2024, 1, 1))
    f.haushalt(mieter, date(2024, 7, 1), 3)

    assert mieter.personenanzahl_am(date(2024, 3, 1)) == 1
    assert mieter.personenanzahl_am(date(2024, 8, 1)) == 3


# --- Der Rechenkern ---------------------------------------------------------


def _objekt(arten, name='Hauptstr. 5', aktiv=None):
    """Baut ein Haus mit einer Einheit je Art und gibt den Mieter der ersten.

    Der Mieter sitzt immer in der ersten Einheit; die uebrigen stehen nur da,
    damit das Objekt den Befund bekommt, den der Fall braucht.
    """
    prop = f.house(name)
    aktiv = aktiv or [True] * len(arten)
    einheiten = [
        f.apt(prop, f'Einheit {nr}', 50.0, is_active=ist_aktiv, nutzungsart=art)
        for nr, (art, ist_aktiv) in enumerate(zip(arten, aktiv), start=1)
    ]
    mieter = f.tenant(einheiten[0], 'Anna Mieterin')
    kat = f.category('Grundsteuer')
    f.profile(mieter, kat, 'qm')
    f.invoice(prop, kat, 1200.0, invoice_number='N-1')
    return mieter


def test_gemischtes_haus_wird_nicht_gerechnet(app_ctx):
    """Abnahme 0.6: erkannt und mit klarer Meldung abgelehnt (R-CO2-04)."""
    mieter = _objekt(['wohnen', 'gewerbe'])
    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    with pytest.raises(BillingDataError) as fehler:
        rechne(vorgang)
    text = str(fehler.value)
    assert 'Hauptstr. 5' in text
    assert 'gemischt genutztes Gebäude' in text
    assert '§ 8 CO2KostAufG' in text


def test_gewerbeobjekt_wird_nicht_gerechnet(app_ctx):
    mieter = _objekt(['gewerbe', 'gewerbe'])
    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    with pytest.raises(BillingDataError) as fehler:
        rechne(vorgang)
    assert 'Gewerbeobjekt' in str(fehler.value)


def test_die_absage_kommt_vor_jeder_zeile(app_ctx):
    """Kein halbes Blatt: die Nutzungsart wird vor allem anderen geprueft.

    Waere die Reihenfolge anders, saehe der Vermieter zuerst eine Meldung
    ueber fehlende Quadratmeter -- auf einem Haus, das ohnehin nicht zu
    rechnen ist -- und haette den falschen Mangel behoben.
    """
    prop = f.house('Ohne Flaeche')
    laden = f.apt(prop, 'Laden', 0.0, nutzungsart='gewerbe')
    f.apt(prop, 'EG', 0.0)
    mieter = f.tenant(laden, 'Anna Mieterin')
    kat = f.category('Grundsteuer')
    f.profile(mieter, kat, 'qm')
    f.invoice(prop, kat, 1200.0, invoice_number='N-2')

    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))
    with pytest.raises(BillingDataError) as fehler:
        rechne(vorgang)
    assert '§ 8 CO2KostAufG' in str(fehler.value)


def test_wohnhaus_wird_gerechnet(app_ctx):
    """Die Gegenprobe: die Sperre darf nicht auf den Normalfall zuschlagen."""
    mieter = _objekt(['wohnen', 'wohnen'])
    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    ergebnis = rechne(vorgang)
    assert ergebnis['line_items'], 'Das Wohnhaus muss gerechnet werden'


def test_die_inaktive_einheit_zaehlt_mit(app_ctx):
    """Ein leer stehender Laden macht das Haus nicht zum Wohngebaeude.

    Die Kosten, die auf ihn entfallen, fallen trotzdem an -- und das Recht,
    nach dem sie zu verteilen sind, haengt nicht daran, ob der Laden gerade
    vermietet ist.
    """
    mieter = _objekt(['wohnen', 'gewerbe'], aktiv=[True, False])
    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    with pytest.raises(BillingDataError):
        rechne(vorgang)


def test_die_vorpruefung_zeigt_die_absage_als_kachel(app_ctx):
    """Der Vermieter soll sie lesen, bevor er auf "Abrechnung erstellen" klickt."""
    mieter = _objekt(['wohnen', 'gewerbe'])
    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    bericht = vorpruefung(vorgang)
    kacheln = [k for k in bericht['checks'] if k['category'] == 'Nutzungsart']
    assert len(kacheln) == 1
    assert kacheln[0]['blocking'] is True
    assert 'gemischt genutztes Gebäude' in kacheln[0]['message']


def test_die_vorpruefung_schweigt_beim_wohnhaus(app_ctx):
    mieter = _objekt(['wohnen', 'wohnen'])
    vorgang = lade_vorgang(mieter.id, date(2024, 1, 1), date(2024, 12, 31))

    bericht = vorpruefung(vorgang)
    assert [k for k in bericht['checks'] if k['category'] == 'Nutzungsart'] == []


# --- Die Wege nach aussen ---------------------------------------------------


def _json(antwort):
    return antwort.get_json()


def test_wohnung_anlegen_ohne_angabe_ist_wohnraum(auth_client, app_ctx):
    prop = f.house('Anlegehaus')
    antwort = auth_client.post('/api/apartments', json={
        'property_id': prop.id, 'name': 'EG links', 'sqm': 50})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    liste = _json(auth_client.get(f'/api/properties/{prop.id}/apartments'))
    assert liste[0]['nutzungsart'] == VORGABE
    assert liste[0]['selbstversorger'] is False
    assert liste[0]['eigennutzung'] is False


def test_wohnung_anlegen_mit_gewerbe(auth_client, app_ctx):
    prop = f.house('Ladenhaus')
    antwort = auth_client.post('/api/apartments', json={
        'property_id': prop.id, 'name': 'Laden', 'sqm': 30,
        'nutzungsart': 'GEWERBE', 'selbstversorger': True})
    assert antwort.status_code == 201, antwort.get_data(as_text=True)

    liste = _json(auth_client.get(f'/api/properties/{prop.id}/apartments'))
    # Normiert gespeichert -- nur deshalb darf die CHECK-Bedingung hart sein.
    assert liste[0]['nutzungsart'] == 'gewerbe'
    assert liste[0]['selbstversorger'] is True


def test_erfundene_nutzungsart_wird_abgewiesen(auth_client, app_ctx):
    """400 mit Feldnamen statt 500 aus der Datenbank."""
    prop = f.house('Fehlerhaus')
    antwort = auth_client.post('/api/apartments', json={
        'property_id': prop.id, 'name': 'Wohnung 3', 'sqm': 50,
        'nutzungsart': 'buero'})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['feld'] == 'nutzungsart'
    assert 'Wohnung 3' in rumpf['error']


def test_wohnung_aendern_setzt_die_stammdaten(auth_client, app_ctx):
    prop = f.house('Aenderungshaus')
    wohnung = f.apt(prop, 'EG', 50.0)

    antwort = auth_client.put(f'/api/apartments/{wohnung.id}', json={
        'nutzungsart': 'gewerbe', 'selbstversorger': True, 'eigennutzung': True})
    assert antwort.status_code == 200, antwort.get_data(as_text=True)

    liste = _json(auth_client.get(f'/api/properties/{prop.id}/apartments'))
    assert liste[0]['nutzungsart'] == 'gewerbe'
    assert liste[0]['selbstversorger'] is True
    assert liste[0]['eigennutzung'] is True


def test_aenderung_mit_erfundener_nutzungsart_prallt_ab(auth_client, app_ctx):
    prop = f.house('Aenderungshaus 2')
    wohnung = f.apt(prop, 'EG', 50.0)

    antwort = auth_client.put(f'/api/apartments/{wohnung.id}',
                              json={'nutzungsart': 'praxis'})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'nutzungsart'


def _mieter_mit_haushalt(einzug=date(2024, 1, 1)):
    prop = f.house('Haushaltswege')
    wohnung = f.apt(prop, 'EG', 50.0)
    return f.tenant(wohnung, 'Familie Berger', move_in=einzug)


def test_haushaltsgroessen_anlegen_und_lesen(auth_client, app_ctx):
    mieter = _mieter_mit_haushalt()
    weg = f'/api/tenants/{mieter.id}/haushaltsgroessen'

    # Verkehrte Reihenfolge hinein -- die Auskunft ordnet nach Stichtag.
    for ab, kopf in (('2024-07-01', 2), ('2024-01-01', 3)):
        antwort = auth_client.post(weg, json={'gueltig_ab': ab, 'personenanzahl': kopf})
        assert antwort.status_code == 201, antwort.get_data(as_text=True)

    liste = _json(auth_client.get(weg))
    assert [(z['gueltig_ab'], z['personenanzahl']) for z in liste] == [
        ('2024-01-01', 3), ('2024-07-01', 2)]


def test_zweiter_eintrag_auf_denselben_tag_berichtigt(auth_client, app_ctx):
    """D-40: der POST berichtigt, statt mit einem 409 stehen zu lassen.

    Wer denselben Stichtag noch einmal schickt, wollte die Zahl
    richtigstellen -- nicht eine zweite Wahrheit anlegen.
    """
    mieter = _mieter_mit_haushalt()
    weg = f'/api/tenants/{mieter.id}/haushaltsgroessen'

    erst = auth_client.post(weg, json={'gueltig_ab': '2024-01-01', 'personenanzahl': 3})
    assert erst.status_code == 201
    zweit = auth_client.post(weg, json={'gueltig_ab': '2024-01-01', 'personenanzahl': 4})
    assert zweit.status_code == 200
    assert _json(zweit)['id'] == _json(erst)['id']

    liste = _json(auth_client.get(weg))
    assert [(z['gueltig_ab'], z['personenanzahl']) for z in liste] == [('2024-01-01', 4)]


def test_stichtag_vor_dem_einzug_wird_abgewiesen(auth_client, app_ctx):
    """Vor dem Einzug wohnt niemand in der Wohnung."""
    mieter = _mieter_mit_haushalt(einzug=date(2024, 3, 1))
    antwort = auth_client.post(
        f'/api/tenants/{mieter.id}/haushaltsgroessen',
        json={'gueltig_ab': '2024-01-01', 'personenanzahl': 2})
    assert antwort.status_code == 400
    rumpf = _json(antwort)
    assert rumpf['feld'] == 'gueltig_ab'
    assert '2024-03-01' in rumpf['error']


def test_haushalt_ohne_kopf_prallt_an_der_eingabe_ab(auth_client, app_ctx):
    mieter = _mieter_mit_haushalt()
    antwort = auth_client.post(
        f'/api/tenants/{mieter.id}/haushaltsgroessen',
        json={'gueltig_ab': '2024-01-01', 'personenanzahl': 0})
    assert antwort.status_code == 400
    assert _json(antwort)['feld'] == 'personenanzahl'


def test_haushaltsgroesse_loeschen(auth_client, app_ctx):
    mieter = _mieter_mit_haushalt()
    weg = f'/api/tenants/{mieter.id}/haushaltsgroessen'
    kennung = _json(auth_client.post(
        weg, json={'gueltig_ab': '2024-01-01', 'personenanzahl': 3}))['id']

    assert auth_client.delete(f'/api/haushaltsgroessen/{kennung}').status_code == 200
    assert _json(auth_client.get(weg)) == []


def test_die_haushaltswege_sind_gesperrt(anon_client, app_ctx):
    """Haushaltsdaten gehen niemanden an, der nicht angemeldet ist."""
    assert anon_client.get('/api/tenants/1/haushaltsgroessen').status_code == 401
    assert anon_client.post('/api/tenants/1/haushaltsgroessen',
                            json={'gueltig_ab': '2024-01-01',
                                  'personenanzahl': 2}).status_code == 401
    assert anon_client.delete('/api/haushaltsgroessen/1').status_code == 401


def test_die_ausfuhr_nimmt_die_haushaltsgroessen_mit(auth_client, app_ctx):
    """Sonst verloere ein Export die Personenhistorie (D-41).

    Sie ist kein zweites Mal zu beschaffen: wer im Nachhinein wissen will,
    wie viele Koepfe 2024 im Haushalt lebten, hat keine Quelle mehr.
    """
    mieter = _mieter_mit_haushalt()
    auth_client.post(f'/api/tenants/{mieter.id}/haushaltsgroessen',
                     json={'gueltig_ab': '2024-01-01', 'personenanzahl': 3})

    ausfuhr = _json(auth_client.get('/api/export'))
    assert 'haushaltsgroessen' in ausfuhr
    assert [(z['gueltig_ab'], z['personenanzahl'])
            for z in ausfuhr['haushaltsgroessen']] == [('2024-01-01', 3)]
    # Und die drei Stammdaten der Wohnung haengen an der Wohnung.
    assert 'nutzungsart' in ausfuhr['apartments'][0]
