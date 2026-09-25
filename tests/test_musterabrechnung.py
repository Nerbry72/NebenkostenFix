"""Das Musterhaus: eine komplette Heizungsabrechnung, von Hand nachgerechnet (NK-125).

Befund F-64 stellte fest, dass der Heizungs-/CO2-Pfad des Rechenkerns nie mit
echten, zusammenhaengenden Daten gelaufen war. Diese Karte pinnt deshalb eine
komplette Abrechnung als Rechenprobe: ein Haus mit einer verbundenen
Zentralheizung, vier Wohnungen, einem Mietjahr-Mieter mit Zwischenablesung,
Eigennutzung und Leerstand. Jede Zahl ist **vorher von Hand abgeleitet** --
nur mit den Regeln des Kerns, ohne ihn aufzurufen -- und steht hier mit ihrem
Rechenweg. Der Test ist das Muster, an dem sich der Kern spaeter messen laesst.

Aufbau des Musterhauses "Musterweg 1" (4 Wohnungen je 50 m2, alle aktiv):

    W1 Erdgeschoss   Anna Muster,  ganzjaehrig (366 Tage, Zeitanteil 1)
    W2 Obergeschoss  Bernd Muster, 01.07.2024 - 31.12.2024 (184 Tage)
    W3 Dachgeschoss  Eigennutzung des Vermieters (366 Tage)
    W4 Kellerwohnung leer (366 Tage)

Anlage "Zentralheizung": verbunden, Verbrauchsanteil 70 % (Sonderfall des
§ 7 Abs. 1 HeizkostenV), Warmwasser-Weg Formel: V = 100 m3, t = 50 Grad C ->
Waerme des Warmwassers Q = 1,163 x 100 x (50 - 10) = 10.000 kWh (§ 9).
Brennstoffmenge 40.000 kWh -> Warmwasseranteil ww = 10.000/40.000 = 1/4.

Zaehler (je Wohnung ein Waermezaehler in kWh, ein Warmwasserzaehler in m3;
Ablesedaten auf den Fensterrand des Abrechnungszeitraums gelegt, damit der
Interpolationsrand nicht anspringt und die Mengen exakte Standdifferenzen
sind):

    Waerme   W1: 10.000 -> 16.000 (6.000 kWh)  W3: 30.000 -> 31.000 (1.000)
             W2: 20.000 -> 22.000 (2.000), Zwischenablesung 20.800 am 01.07.
             W4: 40.000 -> 41.000 (1.000)  -- Summe 10.000 kWh
    Warmw.   W1: 1.000 -> 1.060 (60 m3)        W3: 3.000 -> 3.006 (6)
             W2: 2.000 -> 2.030 (30), Zwischenablesung 2.012 am 01.07.
             W4: 4.000 -> 4.004 (4)        -- Summe 100 m3

Belege 01.01.2024 - 31.12.2024: Gas 8.000,00 EUR (brennstoff, CO2-Kosten
1.000,00 EUR auf 10.000 kg Emission), Grundsteuer 1.200,00 EUR.

--- Die Trennung § 9 vor § 7 (§ 6 kommt zuerst) ---

Die verbundene Anlage teilt jeden Betrag der Rechnung nach dem Warmwasser-
anteil: Heizung 8.000,00 x 3/4 = 6.000,00, Warmwasser 8.000,00 x 1/4
= 2.000,00. Dasselbe gilt fuer die CO2-Kosten: 1.000,00 -> 750,00 (Heizung)
und 250,00 (Warmwasser). Die Stufe des Gebäudes: 10.000 kg auf 200 m2
= 50,0 kg/m2 -> Stufe 9, Mieter 20 %, Vermieter 80 % (§ 6 CO2KostAufG).

Der Mieteranteil der CO2-Kosten laeuft durch dieselbe § 7-Maschinerie, der
Vermieteranteil wird als flache Position ausgewiesen ("Vermieteranteil an
den CO2-Kosten nach § 6 CO2KostAufG (Stufe 9)"). Der Rest der Zeile
(Zeilenkosten minus CO2-Teil) wird nach § 7 gespalten: 70 % nach erfasstem
Verbrauch, 30 % nach Wohnflaeche. Der Verbrauchsteil kennt keine
Zeitanteiligkeit -- die Zeit steckt in der gemessenen Menge; nur der
Grundteil faellt zeitanteilig (§ 7a).

--- Anna: Zeitanteil 1 ---

Heizung: Zeile 6.000,00, CO2-Teil 750,00, Mieteranteil 150,00 (20 %),
Vermieter 600,00 (flat). Rest 5.250,00 -> Verbrauchsteil 3.675,00 (70 %),
Grundteil 1.575,00 (30 %).
    Verbrauchsteil: 3.675,00 x 6000/10.000 kWh = 2.205,00
    Grundteil:      1.575,00 x 50/200 m2    =   393,75
    CO2: 150,00 -> 70 % 105,00 x 6000/10.000 = 63,00; 30 % 45,00
         x 50/200 = 11,25 -> zusammen 74,25
    Zeile: 2.205,00 + 393,75 + 74,25 = 2.673,00

Warmwasser: Zeile 2.000,00, CO2-Teil 250,00, Mieter 50,00, flat 200,00.
Rest 1.750,00 -> 1.225,00 (70 %) und 525,00 (30 %).
    Verbrauchsteil: 1.225,00 x 60/100 m3 = 735,00
    Grundteil:        525,00 x 50/200 m2 = 131,25
    CO2: 35,00 x 60/100 = 21,00; 15,00 x 50/200 = 3,75 -> 24,75
    Zeile: 735,00 + 131,25 + 24,75 = 891,00

Grundsteuer (qm): 1.200,00 x 50/200 = 300,00.

    Anna gesamt: 2.673,00 + 891,00 + 300,00 = 3.864,00 EUR.

--- Bernd: Zeitanteil tf = 184/366 (Mietjahr mit Zwischenablesung) ---

Die Zwischenablesung am 01.07. misst die Grenze (§ 9b): Waerme
22.000 - 20.800 = 1.200 kWh, Warmwasser 2.030 - 2.012 = 18 m3. Die
Anlagenmenge bleibt ganzjaehrig (10.000 kWh bzw. 100 m3).

Heizung: CO2-Teil 750,00 x tf = 377,05 (genauer 377,0492); Mieteranteil
75,4098, Vermieter flat 301,64. Rest 6.000,00 - 377,0492 = 5.622,9508 ->
Verbrauchsteil 70 % = 3.936,0656 (nicht zeitanteilig!), Grundteil 30 %
= 1.686,8852.
    Verbrauchsteil: 3.936,0656 x 1200/10.000 = 472,3279 -> 472,33
    Grundteil:      1.686,8852 x tf x 50/200 = 848,0494 x 0,25 = 212,0124
    CO2: 75,4098 -> 70 % 52,7869 x 1200/10.000 = 6,3344; 30 % 22,6230
         x tf x 50/200 = 2,8433 -> zusammen 9,1779 -> 9,18
    Zeile: 472,33 + 212,01 + 9,18 = 693,52

Hier zeigt sich der Quirk, den dieses Muster festhaelt: der
Kern zieht den ZEITANTEILIGEN CO2-Teil vom vollen Zeilenbetrag ab, bevor er
spaltet. Annas Verbrauchs-Einheitspreis ist 3.675,00/10.000 = 0,3675
EUR/kWh, Bernds aber 3.936,07/10.000 = 0,3936 -- sein Verbrauchsteil ist
hoeher, als die saubere Rechnung ergeben wuerde (441,00). Die Summen
stimmen trotzdem, denn der CO2-Unterposten bringt den Unterschied wieder
herein. Das Muster pinnt das tatsaechliche Verhalten mit expliziter
Arithmetik -- geaendert werden darf es nur mit einer eigenen Karte.

Warmwasser: CO2-Teil 250,00 x tf = 125,6831; Mieter 25,1366, flat 100,55.
Rest 1.874,3169 -> 1.312,0219 (70 %) und 562,2951 (30 %).
    Verbrauchsteil: 1.312,0219 x 18/100 = 236,1639 -> 236,16
    Grundteil: 562,2951 x tf x 50/200 = 282,6838 x 0,25 = 70,6710 -> 70,67
    CO2: 17,5956 x 18/100 = 3,1672; 7,5410 x tf x 50/200 = 0,9478 -> 4,1150
    Zeile: 236,16 + 70,67 + 4,11 = 310,94 -> das Restcent des § 9b-Ausgleichs
    richtet den letzten Unterposten auf die Zeile: 4,12.

Grundsteuer: 1.200,00 x tf x 50/200 = 150,8197 -> 150,82.

    Bernd gesamt: 693,52 + 310,95 + 150,82 = 1.155,29 EUR.

--- Die Vermieteranteile (R-NUM-05: ausgewiesen, nicht verschwunden) ---

Gemessen wird im Fenster des jeweiligen Vorgangs. Annas Fenster ist das
ganze Jahr: Leer-Flaechentage 27.400 (W2 182 Tage bis zum Einzug Bernds,
W4 ganzjaehrig, je 50 m2), Eigennutzung 18.300 (W3), Nenner 73.200
(200 m2 x 366). Bernds Fenster [01.07., 01.01.): W4 leer (9.200), W3 eigen
(9.200), Nenner 36.800.

Grundteil-Anteile (je Zeile: anteiliger Grundteil x Flaechentage/Nenner):
    Anna:  Grundsteuer 1.200,00:      449,18 / 300,00 (749,18)
           Heizgrund 1.575,00:        589,55 / 393,75 (983,30)
           WW-Grund   525,00:         196,52 / 131,25 (327,77)
           CO2-Grund    45,00:         16,84 /  11,25 ( 28,09)
           CO2-WW-Grund  15,00:          5,61 /   3,75 (  9,36)
    Bernd: Grundsteuer 603,2787:      150,82 / 150,82 (301,64)
           Heizgrund 848,0494:         212,01 / 212,01 (424,02)
           WW-Grund   282,6838:         70,67 /  70,67 (141,34)
           CO2-Grund    11,3733:          2,84 /   2,84 (  5,68)
           CO2-WW-Grund   3,7910:          0,95 /   0,95 (  1,90)

Verbrauchsanteile (Restverbrauch der Zaehler, die nicht dem Mieter gehoeren:
W2-Rest 800 kWh (2.000 - 1.200) bzw. 12 m3 (30 - 18), W4 1.000 kWh bzw.
4 m3, W3 1.000 kWh bzw. 6 m3):
    Anna:  Heizverbrauch 3.675,00 x 1800/10.000 = 661,50 / x 1000/10.000
           = 367,50 (1.029,00)
           WW-Verbrauch 1.225,00 x 16/100 = 196,00 / x 6/100 = 73,50
           (269,50)
           CO2-Verbrauch 105,00 x 2800/10.000 = 29,40 (18,90 / 10,50)
           CO2-WW-Verbrauch 35,00 x 22/100 = 7,70 (5,60 / 2,10)
    Bernd: Heizverbrauch 3.936,0656 x 1800/10.000 = 708,49 / x 1000/10.000
           = 393,61 (1.102,10)
           WW-Verbrauch 1.312,0219 x 16/100 = 209,92 / x 6/100 = 78,72
           (288,64)
           CO2-Verbrauch 52,7869 x 1800/10.000 = 9,5016 -> 9,50 /
           x 1000/10.000 = 5,2787 -> 5,28 (14,78)
           CO2-WW-Verbrauch 17,5956 x 16/100 = 2,8153 -> 2,82 / x 6/100
           = 1,0557 -> 1,06 (3,88)

Flache CO2-Positionen: Anna 600,00 + 200,00, Bernd 301,64 + 100,55.

Summen der Vermieterpositionen:
    Anna: 749,18 + 983,30 + 1.029,00 + 28,09 + 29,40 + 600,00 + 327,77
          + 269,50 + 9,36 + 7,70 + 200,00 = 4.233,30 EUR
          (Leerstand 2.139,70, Eigennutzung 1.293,60)
    Bernd: 301,64 + 424,02 + 1.102,10 + 5,68 + 14,78 + 301,64 + 141,34
           + 288,64 + 1,90 + 3,88 + 100,55 = 2.686,17 EUR
          (Leerstand 1.368,02, Eigennutzung 915,96)
"""

import pytest
from decimal import Decimal


def betrag(x):
    """JSON-Zahl als Decimal, fuer Cent-Vergleiche."""
    return Decimal(str(x))


@pytest.fixture
def kategorien(app_ctx):
    """Der Gesetzeskatalog des Seeds, per Name greifbar."""
    from models import CostCategory
    return {k.name: k for k in CostCategory.query.all()}


def _post(client, path, daten):
    antwort = client.post(path, json=daten)
    assert antwort.status_code in (200, 201), (
        path, antwort.status_code, antwort.get_data(as_text=True))
    return antwort.get_json()


@pytest.fixture
def musterhaus(app_ctx, auth_client, kategorien):
    """Das Musterhaus, komplett ueber die API aufgebaut (siehe Modulkopf)."""
    client = auth_client
    prop = _post(client, '/api/properties', {'name': 'Musterweg 1'})['id']
    w1 = _post(client, '/api/apartments', {
        'property_id': prop, 'name': 'Erdgeschoss', 'sqm': 50})['id']
    w2 = _post(client, '/api/apartments', {
        'property_id': prop, 'name': 'Obergeschoss', 'sqm': 50})['id']
    w3 = _post(client, '/api/apartments', {
        'property_id': prop, 'name': 'Dachgeschoss', 'sqm': 50,
        'eigennutzung': True})['id']
    w4 = _post(client, '/api/apartments', {
        'property_id': prop, 'name': 'Kellerwohnung', 'sqm': 50})['id']

    anlage = _post(client, f'/api/properties/{prop}/heizungsanlagen', {
        'name': 'Zentralheizung', 'versorgt': 'verbunden',
        'verbrauchsanteil_prozent': 70, 'sonderfall_70': True,
        'warmwasser_weg': 'formel', 'warmwasser_volumen_m3': 100,
        'warmwasser_temperatur_c': 50, 'brennstoff_menge': 40000})['id']

    anna = _post(client, '/api/tenants', {
        'apartment_id': w1, 'name': 'Anna Muster',
        'move_in_date': '2024-01-01'})['id']
    bernd = _post(client, '/api/tenants', {
        'apartment_id': w2, 'name': 'Bernd Muster',
        'move_in_date': '2024-07-01'})['id']
    _post(client, f'/api/tenants/{anna}/haushaltsgroessen',
          {'gueltig_ab': '2024-01-01', 'personenanzahl': 2})
    _post(client, f'/api/tenants/{bernd}/haushaltsgroessen',
          {'gueltig_ab': '2024-07-01', 'personenanzahl': 2})

    def zaehler(wohnung, kategorie, nummer, staende):
        meter = _post(client, '/api/meters', {
            'category_id': kategorien[kategorie].id, 'property_id': prop,
            'apartment_id': wohnung, 'meter_number': nummer,
            'heizungsanlage_id': anlage})['id']
        for datum, wert, art in staende:
            lesung = {'meter_id': meter, 'reading_date': datum, 'value': wert}
            if art:
                lesung['ablesungsart'] = art
            _post(client, '/api/readings', lesung)

    # Ablesedaten auf den Fensterrand: die Menge im Abrechnungszeitraum ist
    # dann die exakte Standdifferenz (kein Interpolationsrand, kein
    # Ersatzmassstab).
    zaehler(w1, 'Heizung', 'W-W1',
            [('2024-01-01', 10000, None), ('2025-01-01', 16000, None)])
    zaehler(w2, 'Heizung', 'W-W2',
            [('2024-01-01', 20000, None),
             ('2024-07-01', 20800, 'zwischenablesung'),
             ('2025-01-01', 22000, None)])
    zaehler(w3, 'Heizung', 'W-W3',
            [('2024-01-01', 30000, None), ('2025-01-01', 31000, None)])
    zaehler(w4, 'Heizung', 'W-W4',
            [('2024-01-01', 40000, None), ('2025-01-01', 41000, None)])
    zaehler(w1, 'Warmwasser', 'WW-W1',
            [('2024-01-01', 1000, None), ('2025-01-01', 1060, None)])
    zaehler(w2, 'Warmwasser', 'WW-W2',
            [('2024-01-01', 2000, None),
             ('2024-07-01', 2012, 'zwischenablesung'),
             ('2025-01-01', 2030, None)])
    zaehler(w3, 'Warmwasser', 'WW-W3',
            [('2024-01-01', 3000, None), ('2025-01-01', 3006, None)])
    zaehler(w4, 'Warmwasser', 'WW-W4',
            [('2024-01-01', 4000, None), ('2025-01-01', 4004, None)])

    _post(client, '/api/invoices', {
        'category_id': kategorien['Heizung'].id, 'property_id': prop,
        'start_date': '2024-01-01', 'end_date': '2024-12-31', 'amount': 8000,
        'invoice_number': 'GAS-2024', 'heizungsanlage_id': anlage,
        'heizkostenart': 'brennstoff', 'co2_kosten': 1000,
        'co2_emission_kg': 10000})
    _post(client, '/api/invoices', {
        'category_id': kategorien['Grundsteuer'].id, 'property_id': prop,
        'start_date': '2024-01-01', 'end_date': '2024-12-31', 'amount': 1200,
        'invoice_number': 'GST-2024'})

    for monat in range(1, 13):
        _post(client, '/api/payments', {
            'tenant_id': anna, 'amount': 100,
            'type': 'Nebenkostenvorauszahlung',
            'payment_date': f'2024-{monat:02d}-01'})
    for monat in range(7, 13):
        _post(client, '/api/payments', {
            'tenant_id': bernd, 'amount': 100,
            'type': 'Nebenkostenvorauszahlung',
            'payment_date': f'2024-{monat:02d}-01'})

    def abrechnung(mieter):
        antwort = client.post('/api/billing/generate', json={
            'tenant_id': mieter, 'start_date': '2024-01-01',
            'end_date': '2024-12-31'})
        assert antwort.status_code == 200, antwort.get_data(as_text=True)
        return antwort.get_json()

    return {'anna': anna, 'bernd': bernd, 'abrechnung': abrechnung}


def zeile_von(bericht, kategorie):
    """Die Berichtszeile mit genau dieser Kategorie."""
    treffer = [z for z in bericht['line_items'] if z['category'] == kategorie]
    assert len(treffer) == 1, (kategorie, [z['category'] for z in
                                           bericht['line_items']])
    return treffer[0]


def ohne_fristwarnung(bericht):
    """Die Frist-Warnung haengt am heutigen Datum (der 31.12.2025 liegt
    hinter dem Lauf des Tests); alles andere muss leer sein."""
    return [w for w in bericht['warnings']
            if not w.startswith('W-FRIST-VERPASST')]


def unterposten(zeile):
    return [(s['type'], betrag(s['cost'])) for s in zeile['sub_items']]


def test_muster_anna_ganzjahr(app_ctx, musterhaus):
    """Anna, ganzjaehrig: Grundsteuer, Heizung und Warmwasser, auf den Cent.

    Rechenweg im Modulkopf ("Anna: Zeitanteil 1").
    """
    bericht = musterhaus['abrechnung'](musterhaus['anna'])

    assert ohne_fristwarnung(bericht) == []
    assert betrag(bericht['total_amount']) == Decimal('3864.00')
    assert betrag(bericht['prepaid_amount']) == Decimal('1200.00')
    assert betrag(bericht['balance']) == Decimal('2664.00')

    # Grundsteuer: 1200,00 x 50/200 m2 = 300,00.
    gs = zeile_von(bericht, 'Grundsteuer')
    assert betrag(gs['tenant_cost']) == Decimal('300.00')
    assert unterposten(gs) == [('allgemein', Decimal('300.00'))]

    # Heizkosten: Rest 6000,00 - 750,00 = 5250,00 -> 3675,00 (70 %) und
    # 1575,00 (30 %); siehe Modulkopf.
    heiz = zeile_von(bericht, 'Heizkosten (Zentralheizung)')
    assert betrag(heiz['tenant_cost']) == Decimal('2673.00')
    assert unterposten(heiz) == [
        ('heizung_verbrauch', Decimal('2205.00')),
        ('heizung_flaeche', Decimal('393.75')),
        ('heizung_co2', Decimal('74.25'))]
    detail = heiz['heizung_details']
    assert detail['verbrauchsanteil_prozent'] == 70
    assert betrag(detail['warmwasser_anteil_prozent']) == Decimal('25.00')
    assert betrag(detail['tenant_consumption']) == Decimal('6000.0')
    assert betrag(detail['total_consumption']) == Decimal('10000.0')
    assert detail['unit'] == 'kWh'
    # Kein Mietrand in der Mitte des Zeitraums: kein Ausweis.
    assert detail['zwischenablesung'] is None
    assert detail['ersatzmassstab'] is None
    assert detail['co2']['stufe'] == 9
    assert detail['co2']['mieter_prozent'] == 20
    assert detail['co2']['vermieter_prozent'] == 80
    assert betrag(detail['co2']['anteil']) == Decimal('74.25')
    assert betrag(detail['co2']['vermieteranteil']) == Decimal('600.00')
    # Die Unterposten tragen die Zeile komplett (Restcent-Ausgleich: hier
    # ohne Rest, 2205,00 + 393,75 + 74,25 = 2673,00 exakt).
    assert sum(b for _, b in unterposten(heiz)) == betrag(heiz['tenant_cost'])

    # Warmwasser: Rest 2000,00 - 250,00 = 1750,00 -> 1225,00 und 525,00.
    ww = zeile_von(bericht, 'Warmwasserkosten (Zentralheizung)')
    assert betrag(ww['tenant_cost']) == Decimal('891.00')
    assert unterposten(ww) == [
        ('heizung_verbrauch', Decimal('735.00')),
        ('heizung_flaeche', Decimal('131.25')),
        ('heizung_co2', Decimal('24.75'))]
    detail = ww['heizung_details']
    assert betrag(detail['tenant_consumption']) == Decimal('60.0')
    assert betrag(detail['total_consumption']) == Decimal('100.0')
    assert detail['unit'] == 'm³'
    assert betrag(detail['co2']['anteil']) == Decimal('24.75')
    assert betrag(detail['co2']['vermieteranteil']) == Decimal('200.00')
    assert sum(b for _, b in unterposten(ww)) == betrag(ww['tenant_cost'])


def test_muster_anna_vermieteranteile(app_ctx, musterhaus):
    """Die Vermieteranteile auf Annas Blatt, Position fuer Position.

    Rechenweg im Modulkopf ("Die Vermieteranteile"); Leer-Flaechentage
    27.400, Eigennutzung 18.300, Nenner 73.200.
    """
    bericht = musterhaus['abrechnung'](musterhaus['anna'])
    vs = bericht['landlord_share']
    assert betrag(vs['total_amount']) == Decimal('4233.30')
    assert betrag(vs['leerstand_amount']) == Decimal('2139.70')
    assert betrag(vs['eigennutzung_amount']) == Decimal('1293.60')

    erwartet = [
        # (Kategorie, Leerstand, Eigennutzung, Summe = gerundete Teile)
        ('Grundsteuer', '449.18', '300.00', '749.18'),
        ('Heizkosten (Zentralheizung)', '589.55', '393.75', '983.30'),
        ('Heizkosten (Zentralheizung)', '661.50', '367.50', '1029.00'),
        ('CO2-Kosten (Zentralheizung)', '16.84', '11.25', '28.09'),
        ('CO2-Kosten (Zentralheizung)', '18.90', '10.50', '29.40'),
        ('CO2-Kosten (Zentralheizung)', '0.00', '0.00', '600.00'),
        ('Warmwasserkosten (Zentralheizung)', '196.52', '131.25', '327.77'),
        ('Warmwasserkosten (Zentralheizung)', '196.00', '73.50', '269.50'),
        ('CO2-Kosten (Zentralheizung)', '5.61', '3.75', '9.36'),
        ('CO2-Kosten (Zentralheizung)', '5.60', '2.10', '7.70'),
        ('CO2-Kosten (Zentralheizung)', '0.00', '0.00', '200.00'),
    ]
    wirklich = [(p['category'], betrag(p['leerstand_amount']),
                 betrag(p['eigennutzung_amount']), betrag(p['amount']))
                for p in vs['positions']]
    assert wirklich == [(k, Decimal(a), Decimal(b), Decimal(s))
                        for k, a, b, s in erwartet]
    # Die Summe der Positionen ist das Total (keine Position zwischen den
    # Zeilen verschwunden).
    assert sum(betrag(p['amount']) for p in vs['positions']) == \
        betrag(vs['total_amount'])

    # Der gebaeudeweite CO2-Ausweis (§ 6 CO2KostAufG): 50,0 kg/m2 -> Stufe 9.
    co2 = bericht['co2']
    assert co2['stufe'] == 9
    assert betrag(co2['kg_pro_qm']) == Decimal('50.0')
    assert betrag(co2['emission_kg']) == Decimal('10000.0')
    assert betrag(co2['kosten']) == Decimal('1000.00')
    assert co2['mieter_prozent'] == 20
    assert betrag(co2['mieter_anteil_euro']) == Decimal('99.00')
    assert betrag(co2['vermieter_anteil_euro']) == Decimal('800.00')
    assert [(q['invoice_number'], betrag(q['kosten']),
             betrag(q['emission_kg'])) for q in co2['quellen']] == [
        ('GAS-2024', Decimal('1000.00'), Decimal('10000.0'))]


def test_muster_bernd_mietjahr(app_ctx, musterhaus):
    """Bernd, Mietjahr mit Zwischenablesung: der § 9b-Pfad mit gemessener
    Grenze und zeitanteiligen Kosten. Rechenweg im Modulkopf ("Bernd")."""
    bericht = musterhaus['abrechnung'](musterhaus['bernd'])

    assert ohne_fristwarnung(bericht) == []
    assert betrag(bericht['total_amount']) == Decimal('1155.29')
    assert betrag(bericht['prepaid_amount']) == Decimal('600.00')
    assert betrag(bericht['balance']) == Decimal('555.29')

    # Grundsteuer: 1200,00 x 184/366 x 50/200 = 150,8197 -> 150,82.
    gs = zeile_von(bericht, 'Grundsteuer')
    assert betrag(gs['tenant_cost']) == Decimal('150.82')

    # Heizkosten: siehe Modulkopf ("Bernd"). Die Zwischenablesung misst die
    # Grenze (§ 9b): 22.000 - 20.800 = 1200 kWh.
    heiz = zeile_von(bericht, 'Heizkosten (Zentralheizung)')
    assert betrag(heiz['tenant_cost']) == Decimal('693.52')
    assert unterposten(heiz) == [
        ('heizung_verbrauch', Decimal('472.33')),
        ('heizung_flaeche', Decimal('212.01')),
        ('heizung_co2', Decimal('9.18'))]
    detail = heiz['heizung_details']
    assert betrag(detail['tenant_consumption']) == Decimal('1200.0')
    assert betrag(detail['total_consumption']) == Decimal('10000.0')
    assert detail['zwischenablesung'] == [
        {'datum': '2024-07-01', 'stand': 20800.0}]
    assert detail['ersatzmassstab'] is None
    assert betrag(detail['co2']['anteil']) == Decimal('9.18')
    assert betrag(detail['co2']['vermieteranteil']) == Decimal('301.64')
    assert sum(b for _, b in unterposten(heiz)) == betrag(heiz['tenant_cost'])

    # Warmwasser: 2030 - 2012 = 18 m3. Das Restcent der Zeile (310,95 gegen
    # 236,16 + 70,67 + 4,11 = 310,94) rutscht auf den letzten Unterposten.
    ww = zeile_von(bericht, 'Warmwasserkosten (Zentralheizung)')
    assert betrag(ww['tenant_cost']) == Decimal('310.95')
    assert unterposten(ww) == [
        ('heizung_verbrauch', Decimal('236.16')),
        ('heizung_flaeche', Decimal('70.67')),
        ('heizung_co2', Decimal('4.12'))]
    detail = ww['heizung_details']
    assert betrag(detail['tenant_consumption']) == Decimal('18.0')
    assert betrag(detail['total_consumption']) == Decimal('100.0')
    assert detail['zwischenablesung'] == [
        {'datum': '2024-07-01', 'stand': 2012.0}]
    assert betrag(detail['co2']['anteil']) == Decimal('4.11')
    assert betrag(detail['co2']['vermieteranteil']) == Decimal('100.55')


def test_muster_bernd_vermieteranteile(app_ctx, musterhaus):
    """Die Vermieteranteile auf Bernds Blatt: nur das restliche Haus.

    Bernds Fenster [01.07., 01.01.): W4 leer (9.200 Flaechentage), W3
    eigengenutzt (9.200), Nenner 36.800; der W2-Restverbrauch (800 kWh bzw.
    12 m3) bleibt als Leerstandsanteil beim Vermieter."""
    bericht = musterhaus['abrechnung'](musterhaus['bernd'])
    vs = bericht['landlord_share']
    assert betrag(vs['total_amount']) == Decimal('2686.17')
    assert betrag(vs['leerstand_amount']) == Decimal('1368.02')
    assert betrag(vs['eigennutzung_amount']) == Decimal('915.96')

    erwartet = [
        ('Grundsteuer', '150.82', '150.82', '301.64'),
        ('Heizkosten (Zentralheizung)', '212.01', '212.01', '424.02'),
        ('Heizkosten (Zentralheizung)', '708.49', '393.61', '1102.10'),
        ('CO2-Kosten (Zentralheizung)', '2.84', '2.84', '5.68'),
        ('CO2-Kosten (Zentralheizung)', '9.50', '5.28', '14.78'),
        ('CO2-Kosten (Zentralheizung)', '0.00', '0.00', '301.64'),
        ('Warmwasserkosten (Zentralheizung)', '70.67', '70.67', '141.34'),
        ('Warmwasserkosten (Zentralheizung)', '209.92', '78.72', '288.64'),
        ('CO2-Kosten (Zentralheizung)', '0.95', '0.95', '1.90'),
        ('CO2-Kosten (Zentralheizung)', '2.82', '1.06', '3.88'),
        ('CO2-Kosten (Zentralheizung)', '0.00', '0.00', '100.55'),
    ]
    wirklich = [(p['category'], betrag(p['leerstand_amount']),
                 betrag(p['eigennutzung_amount']), betrag(p['amount']))
                for p in vs['positions']]
    assert wirklich == [(k, Decimal(a), Decimal(b), Decimal(s))
                        for k, a, b, s in erwartet]
    assert sum(betrag(p['amount']) for p in vs['positions']) == \
        betrag(vs['total_amount'])

    # Bernds CO2-Ausweis: derselbe Gebaeudeausweis, sein Anteil klein.
    co2 = bericht['co2']
    assert co2['stufe'] == 9
    assert betrag(co2['mieter_anteil_euro']) == Decimal('13.29')
    assert betrag(co2['vermieter_anteil_euro']) == Decimal('402.19')


def test_muster_mengen_invarianten(app_ctx, musterhaus):
    """Die Mengen-Invariante: die Anlagenmenge sieht jeder, den Rest traegt
    Leerstand (W4, W2 vor dem Einzug) und Eigennutzung (W3)."""
    a = musterhaus['abrechnung'](musterhaus['anna'])
    b = musterhaus['abrechnung'](musterhaus['bernd'])

    def mengen(bericht, kategorie):
        d = zeile_von(bericht, kategorie)['heizung_details']
        return betrag(d['tenant_consumption']), betrag(d['total_consumption'])

    # Waerme: 10.000 kWh = Anna 6.000 + Bernd 1.200 + W3 1.000 + W4 1.000
    # + W2-Rest 800.
    assert mengen(a, 'Heizkosten (Zentralheizung)') == (
        Decimal('6000.0'), Decimal('10000.0'))
    assert mengen(b, 'Heizkosten (Zentralheizung)') == (
        Decimal('1200.0'), Decimal('10000.0'))
    # Warmwasser: 100 m3 = 60 + 18 + 6 + 4 + W2-Rest 12.
    assert mengen(a, 'Warmwasserkosten (Zentralheizung)') == (
        Decimal('60.0'), Decimal('100.0'))
    assert mengen(b, 'Warmwasserkosten (Zentralheizung)') == (
        Decimal('18.0'), Decimal('100.0'))

    # Bernds Grenze ist gemessen (§ 9b), nicht ersatzzugemessen.
    assert zeile_von(b, 'Heizkosten (Zentralheizung)')[
        'heizung_details']['ersatzmassstab'] is None
