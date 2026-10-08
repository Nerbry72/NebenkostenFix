"""Der Rechenweg je Zeile im Klartext (R-DOC-01 Punkt 6/7, NK-059).

Die Qualitaetsregel der Dokumentation lautet: "Aus dem erzeugten PDF
laesst sich jede Zeile ohne weitere Information nachrechnen." Schluessel
(Punkt 3), Zeitraum (Punkt 1) und Beleg (Punkt 8) stehen schon an der
Zeile -- was fehlte, war der Weg selbst: welcher Betrag ging ein, um
welchen Anteil wurde er gekuerzt, und was kam als Zwischenergebnis
heraus.

Der Kern liefert die Schritte als Satz (``rechenweg``), das PDF haengt
sie unter die Zeile. Diese Datei haelt beide Enden fest: die Sätze am
Kern (ohne Datenbank, wie der ganze Kern seit NK-037) und die Darstellung
im erzeugten Dokument. Das Auslesen des PDF arbeitet wie in
``test_pdf_belegliste.py``: Seiten unkomprimiert, Textstroeme direkt
gelesen, umbrueche wieder zusammengeklebt.
"""

from __future__ import annotations

import re
import zlib
from datetime import date
from decimal import Decimal

import pytest
import reportlab.rl_config

from nebenkostenfix.pdf_generator import PDFGenerator
from nebenkostenfix.rechenkern import (
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    euro_text,
    rechne,
    zahl_text,
)

JAHR_BEGINN = date(2024, 1, 1)
JAHR_ENDE = date(2024, 12, 31)

WASSER = Kategorie(id=10, name='Wasserversorgung', braucht_zaehler=False)
WAERME = Kategorie(id=9, name='Heizung', braucht_zaehler=True)


# --- Der Kern: die Schritte stehen an der Zeile -----------------------------


def welt(rechnungen=(), zaehler=(), anlagen=(), profile=None,
         einzug=JAHR_BEGINN, **kw):
    """Zwei Wohnungen zu 50 qm; mein Mieter wohnt in der linken."""
    meine = Wohnung(id=1, name='EG links', qm=50.0)
    andere = Wohnung(id=2, name='EG rechts', qm=50.0)
    ich = Mieter(id=1, name='Anna Mieterin', einzug=einzug, auszug=None,
                 wohnung_id=1)
    nachbar = Mieter(id=2, name='Bert Nachbar', einzug=JAHR_BEGINN,
                     auszug=None, wohnung_id=2)
    grund = dict(
        mieter=ich,
        wohnung=meine,
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN if einzug < JAHR_BEGINN else einzug,
        ende=JAHR_ENDE,
        wohnungen=(meine, andere),
        mieter_der_immobilie=(ich, nachbar),
        profile=profile or {},
        rechnungen=tuple(rechnungen),
        zaehler=tuple(zaehler),
        heizungsanlagen=tuple(anlagen),
    )
    grund.update(kw)
    return Vorgang(**grund)


def wasserrechnung(betrag='1200.00'):
    return Rechnung(
        id=1,
        kategorie=WASSER,
        betrag=Decimal(betrag),
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        nummer='R-2024-041',
    )


def wasserzeile(ergebnis):
    zeilen = [z for z in ergebnis['line_items']
              if z['billing_type'] == 'qm']
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def test_ganzjaehriger_mieter_hat_einen_schritt():
    """Rechnungsbetrag mal Schluessel: der Weg in einem Satz.

    1200,00 Euro, 50 von 100 qm: 600,00. Die Rechnung deckt den ganzen
    Zeitraum -- ein Zeitanteilsschritt waere nur Blei ohne Info.
    """
    zeile = wasserzeile(rechne(welt(rechnungen=(wasserrechnung(),))))

    assert zeile['tenant_cost'] == Decimal('600.00')
    assert zeile['rechenweg'] == [
        '1200,00 € nach Wohnfläche 50 von 100 m² = 600,00 €',
    ]


def test_unterjaehriges_verhaeltnis_zeigt_tage_und_zwischenergebnis():
    """R-DOC-01 Punkt 7: "184 von 366 Tagen" -- und was dabei herauskam.

    Einzug am 1. Juli: 1200,00 Euro werden zuerst zeitanteilig gekuerzt
    (603,28 -- das Zwischenergebnis, nicht der runde Betrag), erst dann
    folgt der Flachenschluessel.
    """
    zeile = wasserzeile(rechne(welt(
        rechnungen=(wasserrechnung(),), einzug=date(2024, 7, 1))))

    assert zeile['overlap_days'] == 184
    assert zeile['invoice_days'] == 366
    assert zeile['tenant_cost'] == Decimal('301.64')
    assert zeile['rechenweg'] == [
        '1200,00 € Rechnungsbetrag, anteilig 184 von 366 Tagen = 603,28 €',
        '603,28 € nach Wohnfläche 50 von 100 m² = 301,64 €',
    ]


def test_personen_rechnen_ueber_den_personentaganteil():
    """R-NUM-04: die Zeit steckt in den Personentagen, nicht in Tagen.

    Zwei Einpersonenhaushalte, beide das ganze Jahr: 1200,00 Euro nach
    Personentagen 366 von 732 = 600,00. Ein zweiter, zeitlicher Schritt
    wuerde denselben Mieter zweimal kuerzen.
    """
    zeile = next(
        z for z in rechne(welt(
            rechnungen=(wasserrechnung(),),
            profile={WASSER.id: 'personen'},
        ))['line_items']
        if z['billing_type'] == 'personen')

    assert zeile['tenant_cost'] == Decimal('600.00')
    assert zeile['rechenweg'] == [
        '1200,00 € nach Personentagen 366 von 732 = 600,00 €',
    ]


def heizwelt(rechnungen=(), zaehler=(), anlagen=(), einzug=JAHR_BEGINN):
    """Dasselbe Haus mit einer Gaszentralheizung: 10.000, 70/30."""
    return welt(
        rechnungen=rechnungen,
        zaehler=zaehler,
        anlagen=anlagen or (Heizungsanlage(
            id=1, name='Zentralheizung', verbrauchsanteil_prozent=70),),
        einzug=einzug,
    )


def heizrechnung(betrag='10000.00', beginn=JAHR_BEGINN, ende=JAHR_ENDE):
    return Rechnung(
        id=1,
        kategorie=WAERME,
        betrag=Decimal(betrag),
        beginn=beginn,
        ende=ende,
        heizungsanlage_id=1,
        heizkostenart='brennstoff',
    )


def waermezaehler(zaehler_id, wohnung_id, verbraucht):
    return Zaehler(
        id=zaehler_id,
        nummer=f'W-{zaehler_id}',
        kategorie_id=WAERME.id,
        kategorie_name='Waerme',
        ist_hauptzaehler=False,
        immobilie_id=1,
        wohnung_id=wohnung_id,
        staende=(Stand(datum=JAHR_BEGINN, wert=0.0),
                 Stand(datum=date(2025, 1, 1), wert=verbraucht)),
        heizungsanlage_id=1,
    )


def heizzeile(ergebnis):
    zeilen = [z for z in ergebnis['line_items']
              if z['billing_type'] == 'heizkosten']
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def test_heizung_traegt_die_masse_als_ausgangswert():
    """Die Teilposten zeigen die Aufteilung; der Rechenweg die Masse.

    10.000 Euro Masse, 70 nach Verbrauch (1.200 von 2.000 kWh = 4.200),
    30 nach Wohnfläche (50 von 100 m² = 1.500): die Schritte stehen in
    den Teilposten -- aber die Masse selbst, von der beide Prozente
    genommen werden, fehlte bisher. Sie steht jetzt als erster Satz.
    """
    zeile = heizzeile(rechne(heizwelt(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
    )))

    assert zeile['tenant_cost'] == Decimal('5700.00')
    assert zeile['rechenweg'] == ['10000,00 € Rechnungsbetrag']
    assert [p['cost'] for p in zeile['sub_items']] == [
        Decimal('4200.00'), Decimal('1500.00')]


def test_unterjaehrige_heizung_kuerzt_die_masse_mit_tagen():
    """Auch die Heizmasse wird beim unterjaehrigen Mieter mit Tagen gesagt.

    Einzug am 1. Juli: 10.000,00 Euro, anteilig 184 von 366 Tagen =
    5.027,32 -- erst diese Masse teilt sich dann in Grund- und
    Verbrauchsteil.
    """
    zeile = heizzeile(rechne(heizwelt(
        rechnungen=(heizrechnung(),),
        zaehler=(waermezaehler(1, 1, 1200.0), waermezaehler(2, 2, 800.0)),
        einzug=date(2024, 7, 1),
    )))

    assert zeile['overlap_days'] == 184
    assert zeile['rechenweg'] == [
        '10000,00 € Rechnungsbetrag, anteilig 184 von 366 Tagen = 5027,32 €',
    ]


def test_direkt_und_zaehlerzeilen_erzaehlen_keinen_zweiten_weg():
    """Wo die Teilposten und Zaelerdetails den Weg zeigen, bleibt er leer.

    Eine Wohnungsrechnung traegt den vollen Betrag, der Satz darueber
    sagt es (100 % der Rechnung) -- ein Rechenweg-Duplikat waere ein
    zweites Wort fuer dieselbe Sache (glossar).
    """
    eigene = Rechnung(
        id=2, kategorie=WASSER, betrag=Decimal('460.00'),
        beginn=JAHR_BEGINN, ende=JAHR_ENDE, wohnung_id=1,
    )
    zeilen = rechne(welt(rechnungen=(eigene,)))['line_items']
    posten = next(z for z in zeilen if z['billing_type'] == 'direkt')

    assert posten['tenant_cost'] == Decimal('460.00')
    assert posten['rechenweg'] == []


def test_euro_text_und_zahl_text_sprechen_deutsch():
    """Die Betraege im Satz sehen aus wie die in der Spalte."""
    assert euro_text(Decimal('1200')) == '1200,00 €'
    assert euro_text(Decimal('603.2787')) == '603,28 €'
    assert zahl_text(50.0) == '50'
    assert zahl_text(0.5) == '0,5'


# --- Das PDF: die Schritte stehen unter der Zeile ---------------------------


@pytest.fixture
def unkomprimiert(monkeypatch):
    """Seiten ohne Kompression, damit der Text lesbar im Strom steht."""
    monkeypatch.setattr(reportlab.rl_config, 'pageCompression', 0)


def _text(pdf: bytes) -> str:
    stuecke = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            pass
        stuecke.append(roh.decode('latin-1', 'replace'))
    return ' '.join(stuecke)


def _entschluesselt(stueck: str) -> str:
    """Loest die Escapes eines PDF-Textstuecks auf (Umlaute als Oktal).

    WinAnsi schreibt das Eurozeichen als \200; die Rohform ist kein
    Zeichen, das ein Test vergleichen koennte -- darum zurueck nach €.
    """
    ausgabe = []
    i = 0
    while i < len(stueck):
        zeichen = stueck[i]
        if zeichen == '\\' and i + 1 < len(stueck):
            if stueck[i + 1] in '01234567':
                ziffern = ''
                j = i + 1
                while j < len(stueck) and len(ziffern) < 3 \
                        and stueck[j] in '01234567':
                    ziffern += stueck[j]
                    j += 1
                ausgabe.append(chr(int(ziffern, 8)))
                i = j
                continue
            ausgabe.append(stueck[i + 1])
            i += 2
            continue
        ausgabe.append(zeichen)
        i += 1
    # WinAnsi 0x80 ist das Eurozeichen -- es kommt als Oktal \200 durch.
    return ''.join(ausgabe).replace(chr(0x80), '€')


def _geklebt(pdf: bytes) -> str:
    """Der Text ohne Zeilenumbrueche, in der Reihenfolge des Zeichnens."""
    stuecke = []
    for roh in pdf.split(b'stream')[1:]:
        roh = roh.split(b'endstream')[0]
        try:
            roh = zlib.decompress(roh.strip())
        except zlib.error:
            pass
        stuecke.extend(_entschluesselt(m) for m in re.findall(
            r'\(((?:\\.|[^\\)])*)\)', roh.decode('latin-1', 'replace')))
    return re.sub(r'\s+', '', ''.join(stuecke))


def _erzeuge(posten: list[dict], detailliert: bool = False) -> bytes:
    erzeuger = PDFGenerator(
        property_name='Haus am Anger',
        apartment_name='Wohnung 1',
        tenant_name='Mustermann',
        start_date='2024-01-01',
        end_date='2024-12-31',
        detailliert=detailliert,
    )
    return erzeuger.generate(posten, Decimal('900.00'), Decimal('0.00'))


def _qmzeile() -> dict:
    """Eine qm-Zeile mit ihrem Rechenweg, wie der Kern sie liefert."""
    return {
        'category': 'Wasserversorgung',
        'period': '01.01.2024 - 31.12.2024',
        'description': 'Umlage nach Wohnfläche (50 von 100 m²)',
        'tenant_cost': Decimal('301.64'),
        'invoice_days': 366,
        'overlap_days': 184,
        'billing_type': 'qm',
        'provider_name': 'Stadtwerke Musterstadt',
        'invoice_total_amount': Decimal('1200.00'),
        'prorated_amount': Decimal('603.28'),
        'rechenweg': [
            '1200,00 € Rechnungsbetrag, anteilig 184 von 366 Tagen = 603,28 €',
            '603,28 € nach Wohnfläche 50 von 100 m² = 301,64 €',
        ],
        'sub_items': [
            {
                'type': 'allgemein',
                'description': 'Umlage nach Wohnfläche (50 von 100 m²)',
                'cost': Decimal('301.64'),
            },
        ],
    }


@pytest.mark.parametrize('detailliert', [False, True], ids=['einfach', 'detailliert'])
def test_die_schritte_stehen_unter_der_zeile(unkomprimiert, detailliert):
    """Zeitanteil mit Tagen und Zwischenergebnis, dann der Schluessel."""
    text = _text(_erzeuge([_qmzeile()], detailliert))
    geklebt = _geklebt(_erzeuge([_qmzeile()], detailliert))

    assert '184von366Tagen' in geklebt
    assert '1200,00€Rechnungsbetrag,anteilig184von366Tagen=603,28€' in geklebt
    assert '603,28€nachWohnfläche50von100m²=301,64€' in geklebt
    assert '301,64' in text


def test_der_wiederholende_teilposten_schweigt(unkomprimiert):
    """Ein Teilposten, der nur die Zeile wiederholt, sagt nichts Neues.

    Der Kern haelt ihn (Restcent-Regel R1, Bilanzsummen); das Dokument
    zeigt an seiner Stelle den Rechenweg -- derselbe Satz steht nicht
    zweimal untereinander (glossar).
    """
    text = _text(_erzeuge([_qmzeile()]))
    assert 'Umlage nach Wohnfläche (50 von 100 m²)' not in text


def test_echte_teilposten_bleiben_neben_dem_rechenweg(unkomprimiert):
    """Die Heizzeile zeigt Masse-Satz und die Grund-/Verbrauchsteile.

    Ihr einziger Teilposten wiederholt die Zeile nicht -- er teilt sie:
    Verbrauchskosten 70 %, Grundkosten 30 %. Beides gehoert aufs Blatt.
    """
    zeile = {
        'category': 'Heizung (Gas-Zentrale)',
        'period': '01.01.2024 - 31.12.2024',
        'description': 'Heizung nach § 7 HeizkostenV: 70 % nach erfasstem '
                       'Verbrauch, 30 % nach Wohnfläche',
        'tenant_cost': Decimal('5700.00'),
        'invoice_days': 366,
        'overlap_days': 366,
        'billing_type': 'heizkosten',
        'invoice_total_amount': Decimal('10000.00'),
        'prorated_amount': Decimal('10000.00'),
        'rechenweg': ['10000,00 € Rechnungsbetrag'],
        'sub_items': [
            {
                'type': 'heizung_verbrauch',
                'description': 'Verbrauchskosten 70 % (1200,0 von 2000,0 kWh)',
                'cost': Decimal('4200.00'),
            },
            {
                'type': 'heizung_flaeche',
                'description': 'Grundkosten 30 % nach Wohnfläche (50.0 von 100.0 qm)',
                'cost': Decimal('1500.00'),
            },
        ],
    }
    geklebt = _geklebt(_erzeuge([zeile]))

    assert '10000,00€Rechnungsbetrag' in geklebt
    assert 'Verbrauchskosten70%' in geklebt
    assert '4200,00' in _text(_erzeuge([zeile]))
    assert 'Grundkosten30%' in geklebt
    assert '1500,00' in _text(_erzeuge([zeile]))


def test_ohne_rechenweg_zeigt_die_zeile_den_alten_anhang(unkomprimiert):
    """Zeilen ohne Schritte (Direkt, Zaeler) aendern sich nicht.

    Ihr Zeitanteil steht weiterhin als Anhang an der Beschreibung -- der
    Rechenweg hat ihn dort nicht zu ersetzen, weil es ihn dort nicht gibt.
    """
    zeile = {
        'category': 'Wasserversorgung',
        'period': '01.01.2024 - 31.12.2024',
        'description': 'Direkt zugewiesen (100 % der Rechnung für diese Wohnung)',
        'tenant_cost': Decimal('603.28'),
        'invoice_days': 366,
        'overlap_days': 184,
        'billing_type': 'direkt',
        'provider_name': 'Stadtwerke Musterstadt',
        'invoice_total_amount': Decimal('1200.00'),
        'prorated_amount': Decimal('603.28'),
        'sub_items': [],
    }
    geklebt = _geklebt(_erzeuge([zeile]))

    assert 'anteilig184von366Tagen' in geklebt
    assert '100%' in geklebt


def test_der_rechenweg_erfindet_keinen_zeitanteil(unkomprimiert):
    """Eine Rechnung ueber den ganzen Zeitraum traegt keinen Tagesanhang.

    In der Zeile selbst wie im Rechenweg: was nicht gekuerzt wurde, wird
    nicht so getan, als sei es gekuerzt worden.
    """
    zeile = _qmzeile()
    zeile['overlap_days'] = 366
    zeile['rechenweg'] = [
        '1200,00 € nach Wohnfläche 50 von 100 m² = 600,00 €',
    ]
    geklebt = _geklebt(_erzeuge([zeile]))

    assert 'anteilig' not in geklebt
    assert '1200,00€nachWohnfläche50von100m²=600,00€' in geklebt
