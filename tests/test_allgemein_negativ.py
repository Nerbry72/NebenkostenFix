"""NK-115: eine rechnerisch negative Allgemeinmenge wird benannt.

Befund aus dem Live-Abgleich (Phase 6, NK-111, Klasse B — Fehler im neuen
Stand): Seit NK-097 misst der Zählerzweig Haupt- und Wohnungszähler im
Abrechnungszeitraum und schätzt zwischen den Ablesungen linear. Liegen die
Ablesetage auseinander, kann die Summe der Wohnungszähler im Fenster den
Hauptzähler übersteigen. Der Kern setzt die Allgemeinmenge dann auf 0 —
richtig, eine negative Menge lässt sich nicht verteilen. Er tat das aber
**still**: Die Zeile zeigte 0,00 € Allgemeinanteil ohne ein Wort, und die
Kosten des Allgemeinverbrauchs blieben unbemerkt beim Vermieter.

Jetzt steht die Warnung ``W-ZAEHLER-ALLGEMEIN-NEGATIV`` in der Abrechnung.
Der Betrag ändert sich nicht — die Methode (NK-097) bleibt, sie wird nur
sichtbar.

*Hätte diesen Fehler gefunden:* ``test_negative_allgemeinmenge_im_fenster_warnt``
— vor dem Fix gab es dort keine Warnung.

Die Daten sind synthetisch; jede Zahl ist von Hand nachgerechnet.
"""

from datetime import date
from decimal import Decimal

from nebenkostenfix.rechenkern import (
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    rechne,
)

KENNUNG = 'W-ZAEHLER-ALLGEMEIN-NEGATIV'

JAHR_BEGINN = date(2025, 1, 1)
JAHR_ENDE = date(2025, 12, 31)
JAHRSGRENZE = date(2026, 1, 1)

WASSER = Kategorie(id=2, name='Frischwasser', braucht_zaehler=True)
STROM = Kategorie(id=5, name='Strom', braucht_zaehler=True)


def _zaehler(id, kat, staende, haupt=False, wohnung_id=None):
    return Zaehler(
        id=id, nummer=f'Z-{id}', kategorie_id=kat.id, kategorie_name=kat.name,
        ist_hauptzaehler=haupt, immobilie_id=1, wohnung_id=wohnung_id,
        staende=tuple(staende))


def _vorgang(zaehler, kat=WASSER, beginn=JAHR_BEGINN, ende=JAHR_ENDE):
    """Zwei Wohnungen, je ein Mieter mit einer Person, Jahresrechnung 1000 EUR."""
    links = Wohnung(id=1, name='EG links', qm=50.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=50.0)
    anna = Mieter(id=1, name='Anna', einzug=date(2020, 1, 1), auszug=None,
                  wohnung_id=1)
    bert = Mieter(id=2, name='Bert', einzug=date(2020, 1, 1), auszug=None,
                  wohnung_id=2)
    return Vorgang(
        mieter=anna,
        wohnung=links,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=beginn,
        ende=ende,
        wohnungen=(links, rechts),
        mieter_der_immobilie=(anna, bert),
        profile={kat.id: 'direkt'},
        rechnungen=(Rechnung(id=1, kategorie=kat, betrag=Decimal('1000.00'),
                             beginn=JAHR_BEGINN, ende=JAHR_ENDE),),
        zaehler=tuple(zaehler),
    )


def _wasserzaehler():
    """Hauptzähler 0 -> 100 m³ übers Jahr, gleichmäßig geschätzt.

    Annas Zähler wurde zur Jahresmitte abgelesen: 45 m³ im ersten, 15 m³ im
    zweiten Halbjahr. Berts Zähler 0 -> 30 m³, nur an den Jahresenden.
    """
    return (
        _zaehler(10, WASSER, (Stand(JAHR_BEGINN, 0.0), Stand(JAHRSGRENZE, 100.0)),
                 haupt=True),
        _zaehler(11, WASSER, (Stand(JAHR_BEGINN, 0.0), Stand(date(2025, 7, 1), 45.0),
                              Stand(JAHRSGRENZE, 60.0)), wohnung_id=1),
        _zaehler(12, WASSER, (Stand(JAHR_BEGINN, 0.0), Stand(JAHRSGRENZE, 30.0)),
                 wohnung_id=2),
    )


def _warnungen(ergebnis):
    return [w for w in ergebnis['warnings'] if KENNUNG in w]


def test_negative_allgemeinmenge_im_fenster_warnt():
    """Erstes Halbjahr (181 Tage): Wohnungszähler 59,9 m³, Hauptzähler 49,6 m³.

    Von Hand: Hauptzähler 100 · 181/365 = 49,589 m³; Anna 45 m³ (Ablesung
    genau an der Grenze), Bert 30 · 181/365 = 14,877 m³. Allgemein
    rechnerisch 49,589 − 59,877 = −10,288 m³ → angesetzt 0.
    """
    ergebnis = rechne(_vorgang(_wasserzaehler(), ende=date(2025, 6, 30)))

    warnungen = _warnungen(ergebnis)
    assert len(warnungen) == 1
    assert '„Frischwasser“' in warnungen[0]
    assert 'Z-10' in warnungen[0]
    assert '01.01.2025 – 30.06.2025' in warnungen[0]
    assert '-10,3 m³' in warnungen[0]


def test_warnung_empfiehlt_ablesung_am_wechseltag():
    """D-73: 0 mit Warnung bleibt, die Warnung nennt den ordentlichen Weg.

    Kein Ersatzwert — der Vermieter liest beim Mieterwechsel alle Zähler am
    Einzugs- bzw. Auszugstag ab, dann misst die Software die Grenze. Der
    Fachbegriff „Zwischenablesung“ fällt nicht, weil die Oberfläche diese
    Ablesungsart nicht setzen kann; die Anrede ist das Sie (Glossar).
    """
    warnung = _warnungen(rechne(_vorgang(_wasserzaehler(), ende=date(2025, 6, 30))))[0]

    assert 'Lesen Sie alle Zähler am selben Tag ab' in warnung
    assert 'am Einzugs- bzw. Auszugstag' in warnung
    assert 'erstellen Sie die Abrechnung erneut' in warnung
    assert 'Zwischenablesung' not in warnung
    assert 'Lies ' not in warnung


def test_der_betrag_bleibt_der_der_methode():
    """Die Warnung ändert nichts an der Zahl: 45 m³ zu 10 EUR, Allgemein 0.

    Der Preis ist 1000 EUR durch 100 m³ des vollen Rechnungszeitraums.
    """
    posten = rechne(_vorgang(_wasserzaehler(), ende=date(2025, 6, 30)))['line_items'][0]

    assert posten['tenant_cost'] == Decimal('450.00')
    assert posten['meter_details']['allgemein_consumption'] == 0


def test_positive_allgemeinmenge_schweigt():
    """Ganzes Jahr: 100 − (60 + 30) = 10 m³ Allgemein — keine Warnung."""
    ergebnis = rechne(_vorgang(_wasserzaehler()))

    assert _warnungen(ergebnis) == []
    assert ergebnis['line_items'][0]['meter_details']['allgemein_consumption'] == 10.0


def test_dualtarif_warnt_auch_fuer_ein_einzelnes_register():
    """Gesamt positiv, aber der Hochtarif negativ: auch das wird benannt.

    Hauptzähler HT 60, NT 40 kWh; Annas Zähler HT 70, NT 0; Berts HT 0,
    NT 10. Gesamt 100 − 80 = 20 kWh, aber HT 60 − 70 = −10 kWh: ohne
    Hinweis bliebe der Hochtarif-Anteil still beim Vermieter.
    """
    zaehler = (
        _zaehler(20, STROM, (Stand(JAHR_BEGINN, 0.0, 0.0),
                             Stand(JAHRSGRENZE, 60.0, 40.0)), haupt=True),
        _zaehler(21, STROM, (Stand(JAHR_BEGINN, 0.0, 0.0),
                             Stand(JAHRSGRENZE, 70.0, 0.0)), wohnung_id=1),
        _zaehler(22, STROM, (Stand(JAHR_BEGINN, 0.0, 0.0),
                             Stand(JAHRSGRENZE, 0.0, 10.0)), wohnung_id=2),
    )
    warnungen = _warnungen(rechne(_vorgang(zaehler, kat=STROM)))

    assert len(warnungen) == 1
    assert 'im Hochtarif' in warnungen[0]
    assert '-10,0 kWh' in warnungen[0]


def test_gleiche_ursache_fuer_wasser_und_entwaesserung_ist_eine_meldung():
    """F-132: Wasserversorgung und Entwässerung lesen denselben Hauptzähler.
    Die Abrechnung meldete dieselbe Ursache zweimal; jetzt ist es eine
    Meldung, die beide Kostenarten nennt. Andere Meldungen bleiben getrennt."""
    from nebenkostenfix.rechenkern import HINWEIS_ALLGEMEIN_NEGATIV, meldungen_buendeln
    werte = dict(zaehler='WA-1', beginn='01.01.2025', ende='31.12.2025',
                 register='', menge='-1,3', einheit='m³')
    wasser = HINWEIS_ALLGEMEIN_NEGATIV.format(kategorie='Wasserversorgung', **werte)
    abwasser = HINWEIS_ALLGEMEIN_NEGATIV.format(kategorie='Entwässerung', **werte)
    anders = HINWEIS_ALLGEMEIN_NEGATIV.format(kategorie='Strom', **{**werte, 'menge': '-4,0'})
    gebuendelt = meldungen_buendeln([wasser, abwasser, anders, wasser])
    assert len(gebuendelt) == 2
    assert 'Für „Wasserversorgung“ und „Entwässerung“ zeigen' in gebuendelt[0]
    assert gebuendelt[1] == anders


def test_warnung_nennt_auch_falschen_stand_und_zuordnung():
    """F-134: Ein Hauptzähler unter seinen Wohnungszählern kommt nicht nur von
    verschiedenen Ablesetagen. Die Meldung nennt auch den falsch erfassten
    Stand und die falsche Zuordnung, mit einer Handlung dazu."""
    warnung = _warnungen(rechne(_vorgang(_wasserzaehler(), ende=date(2025, 6, 30))))[0]

    assert 'ist ein Stand falsch erfasst' in warnung
    assert 'Prüfen Sie die Stände und die Zuordnung der Zähler.' in warnung


STAND_FAELLT = 'W-ZAEHLER-STAND-FAELLT'


def _fallender_annazaehler():
    """Wie oben, nur fällt Annas Zähler im Juli von 45 auf 40 m³ (Tippfehler)."""
    haupt, _, bert = _wasserzaehler()
    anna = _zaehler(11, WASSER, (Stand(JAHR_BEGINN, 0.0), Stand(date(2025, 7, 1), 45.0),
                                 Stand(date(2025, 8, 1), 40.0), Stand(JAHRSGRENZE, 60.0)),
                    wohnung_id=1)
    return haupt, anna, bert


def test_fallender_stand_wird_gemeldet():
    """F-134: Ein Stand, der fällt, rechnete still einen negativen Verbrauch.
    Jetzt steht er als Meldung da, mit beiden Ständen und einer Handlung."""
    ergebnis = rechne(_vorgang(_fallender_annazaehler()))
    warnungen = [w for w in ergebnis['warnings'] if STAND_FAELLT in w]

    assert warnungen == [
        'W-ZAEHLER-STAND-FAELLT · Zähler Z-11 fällt vom 01.07.2025 (45) auf den '
        '01.08.2025 (40). Ein Zähler zählt nur vorwärts; gerechnet wird damit ein '
        'negativer Verbrauch. Prüfen Sie beide Stände auf Tippfehler und korrigieren '
        'Sie den falschen. Wurde der Zähler getauscht, legen Sie den neuen Zähler an '
        'und tragen Sie seine Stände dort ein.']


def test_fallender_stand_wird_nicht_korrigiert():
    """Keine Auto-Korrektur: über das Jahr bleibt Annas Verbrauch 60 m³."""
    posten = rechne(_vorgang(_fallender_annazaehler()))['line_items'][0]

    assert posten['meter_details']['tenant_consumption'] == 60.0


def test_fallender_stand_ausserhalb_des_zeitraums_schweigt():
    """Ein Rückgang vor allen Rechnungen und vor dem Zeitraum ist alt -- still."""
    haupt, _, bert = _wasserzaehler()
    anna = _zaehler(11, WASSER, (Stand(date(2023, 1, 1), 50.0), Stand(date(2023, 6, 1), 0.0),
                                 Stand(JAHR_BEGINN, 0.0), Stand(JAHRSGRENZE, 60.0)),
                    wohnung_id=1)
    ergebnis = rechne(_vorgang((haupt, anna, bert)))

    assert not [w for w in ergebnis['warnings'] if STAND_FAELLT in w]


def test_fallender_stand_steht_in_der_pruefung():
    from nebenkostenfix.rechenkern import pruefe
    meldungen = [c.get('message') or '' for c in pruefe(_vorgang(_fallender_annazaehler()))['checks']]

    assert any(STAND_FAELLT in m for m in meldungen)
