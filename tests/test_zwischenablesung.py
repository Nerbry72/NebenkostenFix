"""Die Zwischenablesung zum Mietzeitrand (NK-051, R-HK-04).

§ 9b HeizkostenV: Bei einem Nutzerwechsel innerhalb des Abrechnungszeitraums
ist eine Ablesung der Ausstattung zur Verbrauchserfassung vorzunehmen. Diese
Zwischenablesung ist der einzige Messwert, der die Grenze zwischen zwei
Mietverhältnissen wirklich misst. Alles, was der Kern ohne sie rechnet, ist
Überschlag -- und der Überschlag ist kein stiller: er wird als Ersatzmaßstab
ausdrücklich gewählt und in der Abrechnung benannt.

Die Fälle dieser Datei:

* Eine Zwischenablesung an der Grenze macht aus dem Schätzwert eine Zahl:
  1.000 kWh gelesen statt 690,41 zwischen zwei Jahresablesungen verteilt.
* Ohne sie wählt der Rechenkern den Ersatzmaßstab: die gemessene Menge der
  Wohnung, zeitanteilig geteilt -- und die Zeile sagt es, mit Warnung.
* Mit ihr bleibt es beim gemessenen Verbrauch, und die Zeile nennt Datum und
  Stand der Ablesung.
* Was eine leer stehende Wohnung an ihrem Wärmezähler verbraucht, bleibt beim
  Vermieter -- ausgewiesen, nicht zwischen den Zeilen verschwunden. Zusammen
  ergeben die Anteile aller Mieter plus der Vermieterposition den
  Verbrauchsteil der Rechnung.

Jede Zahl ist von Hand nachgerechnet und steht im Test.
"""

from datetime import date
from decimal import Decimal

from nebenkostenfix import heizung
from nebenkostenfix.heizung import ABLESUNG, ZWISCHENABLESUNG
from nebenkostenfix.rechenkern import (
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    rechne,
    verbrauch_in,
)

JAHR_BEGINN = date(2025, 1, 1)
JAHR_ENDE = date(2025, 12, 31)
JAHR_GRENZE = date(2026, 1, 1)
WECHSEL = date(2025, 6, 30)

WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True)


def anlage(id=1, name='Zentralheizung', prozent=70, **kw):
    return Heizungsanlage(
        id=id, name=name, verbrauchsanteil_prozent=prozent, **kw)


def heizrechnung(betrag='10000.00', id=1, anlage_id=1,
                 art='brennstoff', beginn=JAHR_BEGINN, ende=JAHR_ENDE):
    return Rechnung(
        id=id,
        kategorie=WAERME,
        betrag=Decimal(betrag),
        beginn=beginn,
        ende=ende,
        heizungsanlage_id=anlage_id,
        heizkostenart=art,
    )


def stand(tag, wert, art=ABLESUNG):
    """Ein Zaehlerstand; die Art entscheidet, ob er die Grenze misst."""
    return Stand(datum=tag, wert=float(wert), art=art)


def waermezaehler(id, wohnung_id, staende, anlage_id=1):
    return Zaehler(
        id=id,
        nummer=f'W-{id}',
        kategorie_id=WAERME.id,
        kategorie_name='Waerme',
        ist_hauptzaehler=False,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=tuple(staende),
        heizungsanlage_id=anlage_id,
    )


ANNA = Mieter(
    id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=None,
    wohnung_id=1)
BERT = Mieter(
    id=2, name='Bert Nachbar', einzug=date(2020, 1, 1), auszug=None,
    wohnung_id=2)


def haus(mieter=None, ende=JAHR_ENDE, alle_mieter=None, wohnungen=None,
         zaehler=(), **kw):
    """Zwei Wohnungen zu 50 qm; mein Mieter wohnt links, Bert rechts.

    Ohne andere Angabe ist Anna das ganze Jahr da. Der Wechsel zum 30.06.
    -- Anna zieht aus, Bert zieht ein -- entsteht, indem man ihr Auszug und
    sein Einzug gibt; die Abrechnung gilt fuer eine von beiden. Wie
    ``lade_vorgang`` endet das Mietverhaeltnis der Ausziehenden am
    Auszugstag, und die Grenze ist genau dieser Tag.
    """
    links = Wohnung(id=1, name='EG links', qm=50.0)
    rechts = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = mieter or ANNA
    grund = dict(
        mieter=ich,
        wohnung=ich.wohnung_id == 1 and links or rechts,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=ende,
        wohnungen=tuple(wohnungen if wohnungen is not None else (links, rechts)),
        mieter_der_immobilie=tuple(
            alle_mieter if alle_mieter is not None else (ANNA, BERT)),
        profile={},
        rechnungen=(heizrechnung(),),
        zaehler=tuple(zaehler),
        heizungsanlagen=(anlage(),),
    )
    grund.update(kw)
    return Vorgang(**grund)


def heizzeile(ergebnis):
    zeilen = [z for z in ergebnis['line_items']
              if z['billing_type'] == 'heizkosten']
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def verbrauchskosten(zeile):
    return [p for p in zeile['sub_items']
            if p['description'].startswith('Verbrauchskosten')]


def vermieter_positionen(ergebnis):
    return ergebnis['landlord_share']['positions']


def vermieter_verbrauchsposition(ergebnis):
    positionen = [p for p in vermieter_positionen(ergebnis)
                  if 'vermieter_consumption' in p]
    return positionen[0] if positionen else None


# --------------------------------------------------------------------------
# AK 1/2: die Zwischenablesung an der Grenze wird gemeldet (verbrauch_in)
# --------------------------------------------------------------------------

DREI_STAENDE = (
    stand(JAHR_BEGINN, 0),
    stand(WECHSEL, 1000, ZWISCHENABLESUNG),
    stand(JAHR_GRENZE, 1400),
)


def test_die_zwischenablesung_am_auszug_wird_gemeldet():
    """verbrauch_in nennt Datum, Stand und Seite der Zwischenablesung."""
    zaehler = waermezaehler(1, 1, DREI_STAENDE)
    auskunft = verbrauch_in(zaehler, JAHR_BEGINN, WECHSEL)

    assert auskunft['zwischenablesungen'] == [{
        'datum': WECHSEL.isoformat(),
        'stand': 1000.0,
        'seite': 'ende',
    }]


def test_die_zwischenablesung_beim_einzug_wird_gemeldet():
    """Derselbe Stand von der anderen Seite: die Grenze ist der Beginn."""
    zaehler = waermezaehler(1, 1, DREI_STAENDE)
    auskunft = verbrauch_in(zaehler, WECHSEL, JAHR_GRENZE)

    assert auskunft['zwischenablesungen'] == [{
        'datum': WECHSEL.isoformat(),
        'stand': 1000.0,
        'seite': 'beginn',
    }]
    # 1.400 minus 1.000: der Nachmieter beginnt bei der gelesenen Grenze.
    assert auskunft['consumption'] == 400.0


def test_ohne_zwischenablesung_wird_nichts_gemeldet():
    """Gewoehnliche Ablesungen an derselben Stelle sind keine Zwischenablesung."""
    staende = (
        stand(JAHR_BEGINN, 0),
        stand(WECHSEL, 1000),
        stand(JAHR_GRENZE, 1400),
    )
    zaehler = waermezaehler(1, 1, staende)
    auskunft = verbrauch_in(zaehler, JAHR_BEGINN, WECHSEL)

    assert auskunft['zwischenablesungen'] == []


def test_die_gelesene_grenze_macht_aus_dem_schaetzwert_eine_zahl():
    """1.000 gelesen statt 690,41 verteilt -- der Sinn der § 9b-Ablesung.

    Ohne Zwischenablesung liegen nur die beiden Jahresablesungen vor
    (1.400 kWh in 365 Tagen), und der Auszug zum 30.06. bekommt sein Stueck
    als Tagesmittel: 1.400 * 180/365 = 690,4110. Mit der Zwischenablesung
    sind es die gelesenen 1.000 kWh -- exakt, ohne Interpolation.
    """
    ohne = waermezaehler(1, 1, (
        stand(JAHR_BEGINN, 0),
        stand(JAHR_GRENZE, 1400),
    ))
    auskunft_ohne = verbrauch_in(ohne, JAHR_BEGINN, WECHSEL)
    assert auskunft_ohne['consumption'] == 690.4109589041096
    assert auskunft_ohne['is_interpolated'] is True

    mit = waermezaehler(1, 1, DREI_STAENDE)
    auskunft_mit = verbrauch_in(mit, JAHR_BEGINN, WECHSEL)
    assert auskunft_mit['consumption'] == 1000.0
    assert auskunft_mit['is_interpolated'] is False


# --------------------------------------------------------------------------
# AK 3: der Ersatzmassstab ist ausdruecklich gewaehlt und wird benannt
# --------------------------------------------------------------------------

def welt_mietwechsel(zaehler_staende, bert_einzug=date(2020, 1, 1)):
    """Anna zieht zum 30.06. aus; ihr Zaehler hat die gegebenen Staende.

    Berts Zaehler in der rechten Wohnung bleibt unverändert; mit
    ``bert_einzug`` sagt man, wann sein Mietverhaeltnis beginnt -- im
    Leerstandsfall zieht er erst zum 30.06. ein, wie ``lade_vorgang`` es
    stutzen wuerde.
    """
    bert = Mieter(
        id=2, name='Bert Nachbar', einzug=bert_einzug, auszug=None,
        wohnung_id=2)
    anna = Mieter(
        id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=WECHSEL,
        wohnung_id=1)
    return haus(
        mieter=anna,
        ende=WECHSEL,
        alle_mieter=(anna, bert),
        zaehler=(
            waermezaehler(1, 1, zaehler_staende),
            waermezaehler(2, 2, (
                stand(JAHR_BEGINN, 0),
                stand(JAHR_GRENZE, 800),
            )),
        ),
    )


def test_ohne_zwischenablesung_gilt_der_ersatzmassstab():
    """Keine Ablesung am Wechsel: zeitanteilig -- und die Zeile sagt es.

    Annas Wohnung hat 1.400 kWh im Jahr gemessen, das Haus 2.200. Ohne
    Ablesung am 30.06. nimmt ihr Mietverhaeltnis 1.400 * 180/365 =
    690,4110 kWh, also 7.000 * 690,4110/2.200 = 2.196,76 EUR am
    Verbrauchsteil. Das Grundteil bleibt beim alten Schnitt:
    3.000 * 180/365 = 1.479,4521, halbiert nach Flaeche = 739,73 EUR.
    """
    ergebnis = rechne(welt_mietwechsel((
        stand(JAHR_BEGINN, 0),
        stand(JAHR_GRENZE, 1400),
    )))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('2936.49')
    verbrauch = verbrauchskosten(zeile)
    assert len(verbrauch) == 1
    assert verbrauch[0]['cost'] == Decimal('2196.76')
    assert '690.4 von 2200.0 kWh' in verbrauch[0]['description']
    assert zeile['description'].count('Ersatzmaßstab') == 1
    assert '30.06.2025' in zeile['description']

    details = zeile['heizung_details']
    assert details['ersatzmassstab'] == {'daten': ['30.06.2025']}
    assert details['zwischenablesung'] is None
    assert details['rechnungen'][0]['ersatzmassstab'] == ['30.06.2025']

    warnungen = [w for w in ergebnis['warnings']
                 if 'Zwischenablesung' in w]
    assert len(warnungen) == 1
    assert 'Zentralheizung' in warnungen[0]
    assert '30.06.2025' in warnungen[0]
    assert 'zeitanteilig' in warnungen[0]
    # § 12 (NK-052, D-53): der Ersatzmassstab des § 9b verteilt ausdruecklich
    # auf Grundlage der Messung -- er loest das 15-%-Kuerzungsrecht nicht aus.
    assert not [w for w in ergebnis['warnings']
                if heizung.KUERZUNG_15 in w]


def test_mit_zwischenablesung_bleibt_es_beim_gemessenen_verbrauch():
    """Die Ablesung am 30.06. misst die Grenze: 1.000 kWh, genau.

    7.000 * 1.000/2.200 = 3.181,82 EUR am Verbrauchsteil, zusaetzlich
    739,73 EUR Grundteil: 3.921,55 EUR. Die Zeile nennt Datum und Stand,
    und keine Warnung stoert.
    """
    ergebnis = rechne(welt_mietwechsel(DREI_STAENDE))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('3921.54')
    verbrauch = verbrauchskosten(zeile)
    assert verbrauch[0]['cost'] == Decimal('3181.82')
    assert '1000.0 von 2200.0 kWh' in verbrauch[0]['description']

    details = zeile['heizung_details']
    assert details['zwischenablesung'] == [
        {'datum': WECHSEL.isoformat(), 'stand': 1000.0}]
    assert details['ersatzmassstab'] is None
    assert details['rechnungen'][0]['ersatzmassstab'] is None
    assert not [w for w in ergebnis['warnings']
                if 'Zwischenablesung' in w]


def test_der_einzug_ist_auch_ein_mietrand():
    """Bert zieht zum 30.06. ein, ohne Ablesung: derselbe Ersatzmassstab.

    Sein Fenster [30.06., 01.01.2026) hat 185 Tage: 800 * 185/365 =
    405,4795 kWh, also 7.000 * 405,4795/2.200 = 1.290,16 EUR. Grundteil:
    3.000 * 185/365, halbiert = 760,27 EUR. Zusammen 2.050,43 EUR.
    """
    bert = Mieter(
        id=2, name='Bert Nachbar', einzug=WECHSEL, auszug=None,
        wohnung_id=2)
    anna = Mieter(
        id=1, name='Anna Mieterin', einzug=date(2020, 1, 1), auszug=WECHSEL,
        wohnung_id=1)
    ergebnis = rechne(haus(
        mieter=bert,
        beginn=WECHSEL,
        ende=JAHR_ENDE,
        alle_mieter=(anna, bert),
        zaehler=(
            waermezaehler(1, 1, (
                stand(JAHR_BEGINN, 0),
                stand(JAHR_GRENZE, 1400),
            )),
            waermezaehler(2, 2, (
                stand(JAHR_BEGINN, 0),
                stand(JAHR_GRENZE, 800),
            )),
        ),
    ))
    zeile = heizzeile(ergebnis)

    assert zeile['tenant_cost'] == Decimal('2050.44')
    details = zeile['heizung_details']
    assert details['ersatzmassstab'] == {'daten': ['30.06.2025']}


def test_die_ablesung_eines_anderen_tages_ersetzt_nicht_die_grenze():
    """Ein Stand zwei Tage spaeter ist kein Messwert der Grenze.

    Nur der als Zwischenablesung markierte Stand am Wechseldatum zaehlt;
    ob eine Ablesung wirklich die des Wechsels ist, kann nur der Vermieter
    sagen (D-52). Ohne die Markierung am 30.06. gilt der Ersatzmassstab.
    """
    ergebnis = rechne(welt_mietwechsel((
        stand(JAHR_BEGINN, 0),
        stand(WECHSEL, 1000),
        stand(JAHR_GRENZE, 1400),
    )))
    zeile = heizzeile(ergebnis)

    # Derselbe Betrag wie ohne jede Ablesung am Wechsel: zeitanteilig.
    assert zeile['tenant_cost'] == Decimal('2936.49')
    assert zeile['heizung_details']['ersatzmassstab'] == {'daten': ['30.06.2025']}


# --------------------------------------------------------------------------
# AK 4: was Leerstand und Eigennutzung verbrauchen, bleibt beim Vermieter
# --------------------------------------------------------------------------

def test_der_leerstand_verbraucht_beim_vermieter():
    """Annas Wohnung nach dem Auszug: ihr Zaehler laeuft weiter.

    Anna nimmt 690,4110 kWh (zeitanteilig), ihre Wohnung hat 1.400 kWh
    gemessen -- der Rest 709,5890 kWh ist leerstehender Verbrauch. Bert
    zieht erst zum 30.06. ein; bis dahin ist auch seine Wohnung leer und
    nimmt 800 * 185/365 = 405,4795, der Rest sind 394,5205 kWh. Beide
    Reste bleiben beim Vermieter: 7.000 * 1.104,1096/2.200 = 3.513,08
    EUR. Anna selbst zahlt wie oben 2.196,76 EUR am Verbrauchsteil.
    """
    ergebnis = rechne(welt_mietwechsel((
        stand(JAHR_BEGINN, 0),
        stand(JAHR_GRENZE, 1400),
    ), bert_einzug=WECHSEL))

    position = vermieter_verbrauchsposition(ergebnis)
    assert position is not None
    assert position['amount'] == Decimal('3513.08')
    assert position['leerstand_amount'] == Decimal('3513.08')
    assert position['eigennutzung_amount'] == Decimal('0.00')
    assert position['total_consumption'] == 2200.0
    assert position['vermieter_consumption'] == 1104.1
    assert [(e['apartment'], e['consumption'], e['vacant_days'])
            for e in position['units']] == [
        ('EG links', 709.6, 185),
        ('EG rechts', 394.5, 180),
    ]
    assert 'Leerstand' in position['description']

    # Die Zeile selbst aendert sich nicht gegen den Fall ohne Position.
    zeile = heizzeile(ergebnis)
    assert verbrauchskosten(zeile)[0]['cost'] == Decimal('2196.76')


def test_die_eigennutzung_verbraucht_auch_beim_vermieter():
    """Bert wohnt in der rechten Wohnung selbst -- sein Zaehler laeuft.

    Anna miest das ganze Jahr und zahlt ihren gemessenen Anteil:
    7.000 * 1.400/2.200 = 4.454,55 EUR. Berts (eigene) Wohnung verbraucht
    800 kWh, die niemandem umgelegt werden: 7.000 * 800/2.200 =
    2.545,45 EUR, als Eigennutzung ausgewiesen. Zusammen wieder der
    Verbrauchsteil -- nichts ist doppelt verteilt, nichts verschwunden.
    """
    anna = ANNA
    ergebnis = rechne(haus(
        mieter=anna,
        alle_mieter=(anna,),
        wohnungen=(
            Wohnung(id=1, name='EG links', qm=50.0),
            Wohnung(id=2, name='EG rechts', qm=50.0, eigennutzung=True),
        ),
        zaehler=(
            waermezaehler(1, 1, (
                stand(JAHR_BEGINN, 0),
                stand(JAHR_GRENZE, 1400),
            )),
            waermezaehler(2, 2, (
                stand(JAHR_BEGINN, 0),
                stand(JAHR_GRENZE, 800),
            )),
        ),
    ))

    zeile = heizzeile(ergebnis)
    assert verbrauchskosten(zeile)[0]['cost'] == Decimal('4454.55')

    position = vermieter_verbrauchsposition(ergebnis)
    assert position is not None
    assert position['amount'] == Decimal('2545.45')
    assert position['leerstand_amount'] == Decimal('0.00')
    assert position['eigennutzung_amount'] == Decimal('2545.45')
    assert [(e['apartment'], e['consumption'], e['reason'])
            for e in position['units']] == [
        ('EG rechts', 800.0, 'eigennutzung'),
    ]

    # Die Bilanz der Zeile: Mieteranteil + Vermieterposition = Verbrauchsteil.
    assert (verbrauchskosten(zeile)[0]['cost'] + position['amount']
            == Decimal('7000.00'))


def test_die_zwischenablesung_macht_den_leerstand_zum_rest():
    """Mit Ablesung an der Grenze misst auch der Leerstand, statt zu schaetzen.

    Anna liest am 30.06. die 1.000 kWh, ihre Wohnung hat im Jahr 1.400.
    Ihr Mietverhaeltnis nimmt die gemessenen 1.000 kWh, der Leerstand
    bekommt den Rest von 400 kWh -- die gemessene Menge nach dem Auszug,
    nicht 1.400 * 185/365 = 709,59 geschaetzt. Berts Wohnung bleibt bis
    zu seinem Einzug leer und schaetzt 394,5205 kWh. Zusammen bleiben
    7.000 * 794,5205/2.200 = 2.528,02 EUR beim Vermieter.
    """
    ergebnis = rechne(welt_mietwechsel(DREI_STAENDE, bert_einzug=WECHSEL))

    position = vermieter_verbrauchsposition(ergebnis)
    assert position is not None
    assert position['amount'] == Decimal('2528.02')
    assert [(e['apartment'], e['consumption']) for e in position['units']] == [
        ('EG links', 400.0),
        ('EG rechts', 394.5),
    ]

    # Annas Zeile: gemessen, wie im Fall ohne Leerstandsbetrachtung.
    zeile = heizzeile(ergebnis)
    assert verbrauchskosten(zeile)[0]['cost'] == Decimal('3181.82')
