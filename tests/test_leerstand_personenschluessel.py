"""NK-098: der Personenschlüssel weist den Leerstand beim Vermieter aus.

Der Befund F-34 (erhoben bei NK-047): der Nenner des Flächenschlüssels ist
die volle Gesamtfläche, eine leerstehende Wohnung steht darin und ihr Anteil
bleibt beim Vermieter. Der Nenner des Personenschlüssels war dagegen die
Summe der Personentage **aller Mietverhältnisse** -- eine Wohnung ohne
laufendes Mietverhältnis tauchte darin gar nicht auf, und ihr Anteil
verteilte sich stillschweigend auf die übrigen Mieter. Dieselbe Welt,
derselbe Leerstand, zwei verschiedene Antworten darauf, wer ihn trägt.

Seit NK-098 zählt eine Wohnung ohne Mietverhältnis im Personennenner wie ein
Einpersonenhaushalt (``haushalt.VORGABE``) -- derselbe Vorgabewert, den jedes
Mietverhältnis ohne Haushaltseintrag hat. Ihre Personentage stehen im
Nenner, ihr Anteil bleibt beim Vermieter und wird ausgewiesen (R-NUM-05).
Die Mieter zahlen dadurch **weniger** als vorher; anders als bei der Fläche
(NK-047) ändert diese Karte die Zahlen jedes Mieters, und das ist die
beabsichtigte Korrektur.

Die Fälle hier sind der Probelauf aus F-34 und seine Ränder, gerechnet in
2025 (365 Tage).
"""

from datetime import date
from decimal import Decimal

from leerstand import EIGENNUTZUNG, LEERSTAND
from rechenkern import Kategorie, Mieter, Rechnung, Vorgang, Wohnung, rechne

JAHR_BEGINN = date(2025, 1, 1)
JAHR_ENDE = date(2025, 12, 31)

GRUNDSTEUER = Kategorie(id=1, name='Grundsteuer', braucht_zaehler=False)


def _welt(wer=1, auszug_dritte=None, eigennutzung_dritte=False,
          haushalt_erste=None, dritte_vermietet=False):
    """Drei Wohnungen zu je 50 qm, zwei vermietet, 300,00 EUR nach Personen.

    Der Fall aus F-34: derselbe wie in R-NUM-05, nur mit dem Personenschlüssel
    statt der Fläche. ``wer`` wählt, für welchen Mieter abgerechnet wird,
    ``auszug_dritte`` lässt den zweiten Mieter vor Jahresende gehen,
    ``eigennutzung_dritte`` stellt die dritte Wohnung ins Eigenheim des
    Vermieters, ``haushalt_erste`` setzt eine Haushaltshistorie für den
    ersten Mieter und ``dritte_vermietet`` vermietet die dritte Wohnung mit
    aus, damit die Faälle mit ganzem Haus bauen können.
    """
    wohnungen = (
        Wohnung(id=1, name='Wohnung 1', qm=50.0),
        Wohnung(id=2, name='Wohnung 2', qm=50.0),
        Wohnung(id=3, name='Wohnung 3', qm=50.0,
                eigennutzung=eigennutzung_dritte),
    )
    mieter = (
        Mieter(id=1, name='Mieter 1', einzug=JAHR_BEGINN, auszug=None,
               wohnung_id=1, haushaltsgroessen=haushalt_erste or ()),
        Mieter(id=2, name='Mieter 2', einzug=JAHR_BEGINN,
               auszug=auszug_dritte, wohnung_id=2),
    )
    if dritte_vermietet:
        mieter = mieter + (
            Mieter(id=3, name='Mieter 3', einzug=JAHR_BEGINN, auszug=None,
                   wohnung_id=3),
        )
    ich = mieter[wer - 1]
    return Vorgang(
        mieter=ich,
        wohnung=wohnungen[wer - 1],
        immobilie_id=1,
        immobilie_name='Hauptstrasse 1',
        beginn=JAHR_BEGINN,
        ende=JAHR_ENDE,
        wohnungen=wohnungen,
        mieter_der_immobilie=mieter,
        profile={GRUNDSTEUER.id: 'personen'},
        rechnungen=(
            Rechnung(id=1, kategorie=GRUNDSTEUER, betrag=Decimal('300.00'),
                     beginn=JAHR_BEGINN, ende=JAHR_ENDE),
        ),
    )


def test_der_fall_aus_dem_befund():
    """F-34 woertlich: drei Wohnungen, eine leer, 300,00 EUR nach Personen.

    Vor NK-098 zahlte jeder Mieter 150,00 EUR und der Vermieter nichts -- der
    Leerstand verteilte sich still auf die beiden. Jetzt zählt die leere
    Wohnung wie ein Einpersonenhaushalt: 365 + 365 + 365 = 1095 Personentage,
    jeder Mieter trägt ein Drittel (100,00 EUR), der Rest bleibt beim
    Vermieter. Nach Personen kommt jetzt dieselbe Antwort heraus wie nach
    Fläche -- wie es sein soll, denn der Leerstand ist derselbe.
    """
    ergebnis = rechne(_welt(wer=1))

    posten = ergebnis['line_items'][0]
    assert posten['tenant_cost'] == Decimal('100.00')
    assert posten['description'] == (
        'Umlage nach Personen (365 von 1095 Personentagen)')

    anteil = ergebnis['landlord_share']
    assert anteil['total_amount'] == Decimal('100.00')
    assert anteil['leerstand_amount'] == Decimal('100.00')
    assert anteil['eigennutzung_amount'] == Decimal('0.00')

    # Die Aufgeh-Probe: beide Mieterzeilen plus der Vermieteranteil ergeben
    # wieder die Rechnung.
    erster = ergebnis
    zweiter = rechne(_welt(wer=2))
    assert (
        erster['line_items'][0]['tenant_cost']
        + zweiter['line_items'][0]['tenant_cost']
        + erster['landlord_share']['total_amount']
    ) == Decimal('300.00')


def test_die_position_nennt_wohnung_tage_und_vorgabe():
    """Der Ausweis sagt, mit wie vielen Köpfen die leere Wohnung zählt.

    Die Frage aus F-34 -- mit wie vielen Personen zählt eine leere Wohnung --
    muss in der Abrechnung stehen, nicht nur in der Antwort. Die Position
    nennt deshalb die Vorgabe von einer Person je leerer Wohnung und die
    Tage, über die sie zählt.
    """
    ergebnis = rechne(_welt(wer=1))
    position = ergebnis['landlord_share']['positions'][0]

    assert position['category'] == 'Grundsteuer'
    assert position['prorated_amount'] == Decimal('100.00')
    assert position['total_person_days'] == 1095
    assert position['vermieter_personentage'] == 365
    assert [e['apartment'] for e in position['units']] == ['Wohnung 3']
    assert position['units'][0]['personen'] == 1
    assert position['units'][0]['vacant_days'] == 365
    assert position['units'][0]['period_days'] == 365
    assert position['units'][0]['reason'] == LEERSTAND
    assert 'Leerstand (Wohnung 3)' in position['description']


def test_eigennutzung_zaehlt_auch_wie_ein_einpersonenhaushalt():
    """Die selbst bewohnte Einheit fällt nicht aus dem Nenner.

    Auch in ihr wohnen Menschen; dass ihre Köpfe nicht erfasst sind, heißt
    nicht, dass sie nicht existieren. Es gilt dieselbe Vorgabe wie beim
    Leerstand, und der Anteil steht getrennt als Eigennutzung.
    """
    ergebnis = rechne(_welt(wer=1, eigennutzung_dritte=True))

    posten = ergebnis['line_items'][0]
    assert posten['tenant_cost'] == Decimal('100.00')

    anteil = ergebnis['landlord_share']
    assert anteil['eigennutzung_amount'] == Decimal('100.00')
    assert anteil['leerstand_amount'] == Decimal('0.00')
    assert anteil['positions'][0]['units'][0]['reason'] == EIGENNUTZUNG
    assert 'Eigennutzung (Wohnung 3)' in anteil['positions'][0]['description']


def test_teilweiser_leerstand_zaehlt_nur_die_unvermieteten_tage():
    """Wer zur Jahresmitte auszieht, hinterlässt ein Vierteljahr Leerstand.

    Alle drei Wohnungen sind vermietet, aber der zweite Mieter zieht zum
    30.9. aus (Auszugsgrenze 1.10.), niemand nach. Sein Mietverhältnis trug
    273 Personentage bei, die verwaiste Wohnung zählt die übrigen 92 Tage
    mit einer Person. 365 + 273 + 365 + 92 = 1095 Personentage: jeder
    ganzjährige Mieter zahlt 300 × 365/1095 = 100,00 EUR, und der Vermieter
    trägt 300 × 92/1095 = 25,21 EUR -- nur für die Tage ohne Mietverhältnis.
    """
    welt = _welt(wer=1, auszug_dritte=date(2025, 10, 1), dritte_vermietet=True)
    ergebnis = rechne(welt)

    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('100.00')

    anteil = ergebnis['landlord_share']
    assert anteil['total_amount'] == Decimal('25.21')
    assert anteil['positions'][0]['vermieter_personentage'] == 92
    assert anteil['positions'][0]['units'][0]['vacant_days'] == 92
    assert anteil['positions'][0]['units'][0]['apartment'] == 'Wohnung 2'


def test_voll_vermietetes_haus_rechnet_wie_vorher():
    """Kein Leerstand, kein Ausweis -- und die alten Zahlen.

    Der häufigste Fall. Ohne leerstehende Wohnung ist der Nenner derselbe wie
    vor NK-098, und die Abrechnung redet nicht von etwas, das es nicht gibt.
    Drei Einpersonenhaushalte: 1095 Personentage, je Mieter ein Drittel.
    """
    ergebnis = rechne(_welt(wer=1, dritte_vermietet=True))

    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('100.00')
    assert ergebnis['line_items'][0]['description'] == (
        'Umlage nach Personen (365 von 1095 Personentagen)')
    assert ergebnis['landlord_share']['positions'] == []
    assert ergebnis['landlord_share']['total_amount'] == Decimal('0.00')


def test_die_leere_wohnung_zaehlt_unabhaengig_von_den_anderen_haushalten():
    """Eine Wohnung ohne Mietverhältnis zählt eine Person, nicht mehr.

    Der erste Haushalt ist zu dritt, der zweite allein. Die leere Wohnung
    zählt trotzdem nur mit der Vorgabe -- nicht mit der größten, nicht mit
    der durchschnittlichen Kopfzahl des Hauses. 3 × 365 + 365 + 365 = 1825
    Personentage: der Dreierhaushalt trägt 180,00 EUR, der Single 60,00 EUR,
    der Vermieter 60,00 EUR.
    """
    welt = _welt(
        wer=1,
        haushalt_erste=((date(2025, 1, 1), 3),),
    )
    ergebnis = rechne(welt)

    assert ergebnis['line_items'][0]['tenant_cost'] == Decimal('180.00')
    assert ergebnis['line_items'][0]['description'] == (
        'Umlage nach Personen (1095 von 1825 Personentagen)')

    anteil = ergebnis['landlord_share']
    assert anteil['total_amount'] == Decimal('60.00')

    zweiter = rechne(_welt(wer=2, haushalt_erste=((date(2025, 1, 1), 3),)))
    assert zweiter['line_items'][0]['tenant_cost'] == Decimal('60.00')
