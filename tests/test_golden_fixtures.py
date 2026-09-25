"""NK-056: goldene Fixtures -- Festwerte, von Hand nach der Vorschrift gerechnet.

Die Goldens hier sind keine Charakterisierungstests: jede Zahl ist zuerst
auf dem Papier nach dem Regelwerk gerechnet worden (BetrKV, CO2KostAufG,
R-NUM-01 bis R-NUM-05) und erst danach mit dem Rechenkern abgeglichen. Die
Handrechnung steht als Kommentar neben jedem Fall -- wenn der Kern anders
rechnet als der Kommentar, ist das ein Befund und kein erwarteter Bruch.

Die Welten laufen ohne Datenbank (wie der ganze Kern seit NK-037). Jedes
Golden nennt:

* ``nr``/``titel`` -- Go-Nr. der Karte und was der Fall zeigt,
* ``welt`` -- ein Bauplan, der zum Mieternamen den ``Vorgang`` liefert,
* ``soll`` -- Mietername -> (Mieteranteil, Vermieteranteil) in EUR,
* ``bilanz`` -- die geschlossene Summe aus allen Mieteranteilen plus dem
  Vermieterrest **der laengsten Sicht**, oder ``None``, wenn das Fenster
  den Rechnungszeitraum nicht ueberdeckt (unterjaehrige Sichten lassen den
  Rest der Zeit offen -- dann gibt es keine Bilanz zu pruefen),
* ``saldo`` -- erwartete Balance nach Vorauszahlungen (erste Sicht),
* ``kennungen`` -- Warnungs-Bruchstuecke, die in der Sicht stehen muessen.

Zur Bilanzregel: Der Vermieterrest gehoert zur Zeit, nicht zu den
Mietern -- bei gestutzten Sichten sieht nur die laengste Sicht den ganzen
Rest (GO-04, GO-05). Deshalb wird er genau einmal gezaehlt.

Ein dokumentierter Befund bleibt offen: GO-06 (drei gleiche Wohnungen)
verteilt 1.000,00 EUR zu je 333,33 -- die Summe bleibt 999,99, weil ohne
Leerstand niemand den Restcent traegt (F-39). Das Golden pinselt das nicht
 schoen; es haelt es fest.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Mapping, Optional, Tuple

import heizung
import pytest

from rechenkern import (
    Heizungsanlage,
    Kategorie,
    Mieter,
    Rechnung,
    Stand,
    Vorgang,
    Wohnung,
    Zaehler,
    Zahlung,
    rechne,
)

JA = date(2024, 1, 1)
JE = date(2024, 12, 31)
JA5 = date(2025, 1, 1)
JE5 = date(2025, 12, 31)
JG = date(2025, 1, 1)
JG26 = date(2026, 1, 1)
WECHSEL24 = date(2024, 6, 30)
WECHSEL25 = date(2025, 6, 30)


# --- Bausteine der Welten ---------------------------------------------------


def kategorie(id, name, zaehler=False):
    return Kategorie(id=id, name=name, braucht_zaehler=zaehler)


GRUND = kategorie(1, 'Grundsteuer')
STROM = kategorie(5, 'Strom', zaehler=True)
WAERME = kategorie(9, 'Heizung', zaehler=True)
WARMWASSER = kategorie(10, 'Warmwasser', zaehler=True)


def wohnung(id, qm=50.0):
    return Wohnung(id=id, name=f'EG {id}', qm=qm)


def mieter(id, name, wohnung_id, einzug=date(2020, 1, 1), auszug=None,
           personen=None):
    """Ein Mietverhaeltnis; ``personen`` ist eine (gueltig_ab, Koepfe)-Liste."""
    return Mieter(id=id, name=name, einzug=einzug, auszug=auszug,
                  wohnung_id=wohnung_id,
                  haushaltsgroessen=tuple(personen) if personen else ())


def umlage(betrag, kategorie=GRUND, beginn=JA, ende=JE, **kw):
    return Rechnung(id=1, kategorie=kategorie, betrag=Decimal(betrag),
                    beginn=beginn, ende=ende, **kw)


def heizrechnung(betrag='10000.00', id=1, anlage_id=1, art='brennstoff',
                 beginn=JA, ende=JE, **kw):
    return Rechnung(id=id, kategorie=WAERME, betrag=Decimal(betrag),
                    beginn=beginn, ende=ende, heizungsanlage_id=anlage_id,
                    heizkostenart=art, **kw)


def stromstand(wert, wert_nt=None):
    """Ein Zaehlerstand, einheitstarifig oder dual."""
    if wert_nt is None:
        return Stand(datum=JA, wert=0.0) if wert == 0.0 else Stand(
            datum=JG, wert=wert)
    return Stand(datum=JA, wert=0.0, wert_nt=0.0) if wert == 0.0 else Stand(
        datum=JG, wert=wert, wert_nt=wert_nt)


def stromzaehler(id, wohnung_id, wert, wert_nt=None, haupt=False):
    return Zaehler(id=id, nummer=f'S-{id}', kategorie_id=STROM.id,
                   kategorie_name=STROM.name, ist_hauptzaehler=haupt,
                   immobilie_id=1, wohnung_id=None if haupt else wohnung_id,
                   staende=(stromstand(0.0), stromstand(wert, wert_nt)))


def warmezaehler(id, wohnung_id, wert, anlage_id=1, beginn=JA, grenze=JG):
    return Zaehler(id=id, nummer=f'W-{id}', kategorie_id=WAERME.id,
                   kategorie_name=WAERME.name, ist_hauptzaehler=False,
                   immobilie_id=1, wohnung_id=wohnung_id, heizungsanlage_id=anlage_id,
                   staende=(Stand(datum=beginn, wert=0.0),
                            Stand(datum=grenze, wert=wert)))


def wasserzaehler(id, wohnung_id, wert, anlage_id=1):
    return Zaehler(id=id, nummer=f'Z-{id}', kategorie_id=WARMWASSER.id,
                   kategorie_name=WARMWASSER.name, ist_hauptzaehler=False,
                   immobilie_id=1, wohnung_id=wohnung_id, heizungsanlage_id=anlage_id,
                   staende=(Stand(datum=JA, wert=0.0), Stand(datum=JG, wert=wert)))


def anlage(id=1, name='Zentralheizung', prozent=70, **kw):
    return Heizungsanlage(id=id, name=name, verbrauchsanteil_prozent=prozent, **kw)


def haus(fuer, alle, rechnungen=(), zaehler=(), anlagen=(), profile=None,
         wohnungen=None, beginn=JA, ende=JE, zahlungen=()):
    """Der Vorgang des Mieters ``fuer`` (Objekt) im Standardhaus."""
    flats = wohnungen or (wohnung(1), wohnung(2))
    m = next(m for m in alle if m.name == fuer)
    eig = next(w for w in flats if w.id == m.wohnung_id)
    return Vorgang(mieter=m, wohnung=eig, immobilie_id=1,
                   immobilie_name='Hauptstrasse 1', beginn=beginn, ende=ende,
                   wohnungen=tuple(flats), mieter_der_immobilie=tuple(alle),
                   profile=profile or {}, rechnungen=tuple(rechnungen),
                   zaehler=tuple(zaehler), heizungsanlagen=tuple(anlagen),
                   zahlungen=tuple(zahlungen))


ANNA = mieter(1, 'Anna', 1)
BERT = mieter(2, 'Bert', 2)


# --- Das Register -----------------------------------------------------------


@dataclass(frozen=True)
class Golden:
    """Ein goldener Fall: Welt, erwartete Betraege, Bilanz, Kennungen."""

    nr: str
    titel: str
    welt: Callable[[str], Vorgang]
    soll: Mapping[str, Tuple[Optional[str], Optional[str]]]
    bilanz: Optional[str] = None
    saldo: Optional[str] = None
    kennungen: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)


GOLDEN_VORTEIL: tuple = (

    # --- Umlage nach qm (§ 556 Abs. 1, R-NUM-01) -----------------------------

    # 600,00 auf 2 x 50 qm: Anna 300,00 + Bert 300,00 = 600,00. Niemand steht
    # leer, der Vermieterrest ist 0,00.
    Golden(
        nr='GO-01', titel='qm auf gleiche Wohnungen',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('600.00'),),
                            profile={1: 'qm'}),
        soll={'Anna': ('300.00', '0.00'), 'Bert': ('300.00', '0.00')},
        bilanz='600.00'),

    # 600,00 auf 60 + 40 qm: Anna 360,00 + Bert 240,00 = 600,00.
    Golden(
        nr='GO-02', titel='qm auf ungleiche Wohnungen',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('600.00'),),
                            profile={1: 'qm'},
                            wohnungen=(wohnung(1, 60.0), wohnung(2, 40.0))),
        soll={'Anna': ('360.00', '0.00'), 'Bert': ('240.00', '0.00')},
        bilanz='600.00'),

    # Wohnung 2 ohne Mietverhaeltnis (D-43, R-NUM-05): ihr qm-Teil bleibt
    # beim Vermieter -- 300,00 + 300,00 = 600,00.
    Golden(
        nr='GO-03', titel='qm, zweite Wohnung leer',
        welt=lambda n: haus(n, (ANNA,), (umlage('600.00'),), profile={1: 'qm'}),
        soll={'Anna': ('300.00', '300.00')},
        bilanz='600.00'),

    # Anna zieht zum 30.06.2024 aus. Ihr Fenster [01.01., 30.06.) hat 181
    # Tage (Schaltjahr, der Auszugstag zaehlt nicht, R-NUM-03): 600,00 *
    # 181/366 * 50/100 = 148,36. Berts Sicht sieht das ganze Jahr und den
    # Vermieterrest der ab 30.06. leeren Wohnung 1: 300,00 * 185/366 =
    # 151,64. Zusammen 600,00.
    Golden(
        nr='GO-04', titel='qm, Auszug unterjaehrig',
        welt=lambda n: haus(n, (
            mieter(1, 'Anna', 1, auszug=WECHSEL24), BERT),
            (umlage('600.00'),), profile={1: 'qm'},
            ende=JE if n == 'Bert' else WECHSEL24),
        soll={'Anna': ('148.36', '0.00'), 'Bert': ('300.00', '151.64')},
        bilanz='600.00'),

    # Bert zieht zum 01.07.2024 ein. Anna zahlt ihr ganzjaehriges Viertel
    # 300,00; Berts Fenster [01.07., JE) hat 184 Tage: 600,00 * 184/366 *
    # 50/100 = 150,82. Der Vermieter traegt Wohnung 2 fuer 182 Tage
    # (01.01. bis 30.06.): 300,00 * 182/366 = 149,18. Zusammen 600,00.
    Golden(
        nr='GO-05', titel='qm, Einzug unterjaehrig',
        welt=lambda n: haus(n, (
            ANNA, mieter(2, 'Bert', 2, einzug=date(2024, 7, 1))),
            (umlage('600.00'),), profile={1: 'qm'},
            beginn=JA if n == 'Anna' else date(2024, 7, 1)),
        soll={'Anna': ('300.00', '149.18'), 'Bert': ('150.82', '0.00')},
        bilanz='600.00'),

    # 1.000,00 auf drei gleiche Wohnungen: je 1.000/3 = 333,33. Die Zeilen
    # runden je fuer sich, die Summe bleibt 999,99 -- ohne Leerstand traegt
    # niemand den fehlenden Cent (F-39, vermieter_rest_flaeche -> None).
    Golden(
        nr='GO-06', titel='qm krumm, der verwaiste Restcent (F-39)',
        welt=lambda n: haus(n, (ANNA, BERT, mieter(3, 'Caesar', 3)),
                            (umlage('1000.00'),), profile={1: 'qm'},
                            wohnungen=(wohnung(1), wohnung(2), wohnung(3))),
        soll={'Anna': ('333.33', '0.00'), 'Bert': ('333.33', '0.00'),
              'Caesar': ('333.33', '0.00')},
        bilanz='999.99'),

    # Die Rechnung laeuft nur vom 01.07. bis 31.12. (184 Tage) und liegt
    # vollstaendig im Abrechnungsjahr -- kein Prorating: 200,00 zu je 50 %
    # = 100,00.
    Golden(
        nr='GO-07', titel='qm, unterjaehrige Rechnung',
        welt=lambda n: haus(n, (ANNA, BERT),
                            (umlage('200.00', beginn=date(2024, 7, 1)),),
                            profile={1: 'qm'}),
        soll={'Anna': ('100.00', '0.00'), 'Bert': ('100.00', '0.00')},
        bilanz='200.00'),

    # --- Umlage nach Personen (R-NUM-04) -------------------------------------

    # 600,00, je 1 Kopf: Nenner 732 Personentage, Anna 366/732 = 300,00,
    # Bert ebenso.
    Golden(
        nr='GO-08', titel='Personen, je ein Kopf',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('600.00'),),
                            profile={1: 'personen'}),
        soll={'Anna': ('300.00', '0.00'), 'Bert': ('300.00', '0.00')},
        bilanz='600.00'),

    # 600,00, Anna 1 Kopf, Bert 2: Nenner 366 + 732 = 1.098. Anna
    # 600 * 366/1098 = 200,00, Bert 400,00.
    Golden(
        nr='GO-09', titel='Personen, zwei Koepfe in einer Wohnung',
        welt=lambda n: haus(n, (
            ANNA, mieter(2, 'Bert', 2,
                         personen=((date(2020, 1, 1), 2),))),
            (umlage('600.00'),), profile={1: 'personen'}),
        soll={'Anna': ('200.00', '0.00'), 'Bert': ('400.00', '0.00')},
        bilanz='600.00'),

    # 900,00, Wohnung 2 leer (D-51): sie zaehlt wie ein Einpersonenhaushalt.
    # Nenner 366 + 366 = 732; Anna 450,00, der zweite Posten bleibt beim
    # Vermieter.
    Golden(
        nr='GO-10', titel='Personen, leere Wohnung zaehlt einen Kopf',
        welt=lambda n: haus(n, (ANNA,), (umlage('900.00'),),
                            profile={1: 'personen'}),
        soll={'Anna': ('450.00', '450.00')},
        bilanz='900.00'),

    # 916,00, Anna lebte bis 30.06. allein, danach zu zweit: ihre 550 PT
    # (182 + 2 * 184), Bert 366, Nenner 916. Bei 1,00 EUR je PT: Anna
    # 550,00, Bert 366,00.
    Golden(
        nr='GO-11', titel='Personen, Haushaltshistorie',
        welt=lambda n: haus(n, (
            mieter(1, 'Anna', 1, personen=(
                (JA, 1), (date(2024, 7, 1), 2))), BERT),
            (umlage('916.00'),), profile={1: 'personen'}),
        soll={'Anna': ('550.00', '0.00'), 'Bert': ('366.00', '0.00')},
        bilanz='916.00'),

    # 732,00, Nutzerwechsel in Wohnung 2 (Bert bis zum 30.06., Caesar ab
    # 01.07.): Anna 366 PT, Bert 181, Caesar 184; der 30.06. bleibt als
    # Leer-Tag (Vorgabe 1) beim Vermieter. 1,00 EUR je PT.
    Golden(
        nr='GO-12', titel='Personen, Nutzerwechsel mit Leer-Tag',
        welt=lambda n: haus(n, (
            ANNA, mieter(2, 'Bert', 2, auszug=WECHSEL24),
            mieter(3, 'Caesar', 2, einzug=date(2024, 7, 1))),
            (umlage('732.00'),), profile={1: 'personen'}),
        soll={'Anna': ('366.00', '1.00'), 'Bert': ('181.00', '1.00'),
              'Caesar': ('184.00', '1.00')},
        bilanz='732.00'),

    # 600,00, Anna zieht zum 30.06. aus, Wohnung 2 bleibt leer. Das
    # Verhaeltnis traegt die Zeit: Nenner 732 = Anna 181 PT + Leerstand 551
    # PT (Wohnung 1 ab 30.06.: 185 Tage, Wohnung 2 ganzjaehrig 366). Anna
    # 600 * 181/732 = 148,36, Vermieter 600 * 551/732 = 451,64.
    Golden(
        nr='GO-13', titel='Personen, Auszug mit Leerstand',
        welt=lambda n: haus(n, (mieter(1, 'Anna', 1, auszug=WECHSEL24),),
                            (umlage('600.00'),), profile={1: 'personen'},
                            ende=WECHSEL24),
        soll={'Anna': ('148.36', '451.64')},
        bilanz='600.00'),

    # --- Eigenverbrauch nach Zaehlerstand (§ 556a, NK-055) -------------------

    # Ohne Hauptzaehler kein Allgemeinanteil: 800,00 / 800 kWh = 1,00 EUR
    # je kWh; Anna 500 kWh = 500,00, Bert 300,00.
    Golden(
        nr='GO-15', titel='Strom ohne Hauptzaehler',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('800.00', STROM),),
                            profile={5: 'direkt'},
                            zaehler=(stromzaehler(11, 1, 500.0),
                                     stromzaehler(12, 2, 300.0))),
        soll={'Anna': ('500.00', '0.00'), 'Bert': ('300.00', '0.00')},
        bilanz='800.00'),

    # Hauptzaehler 1.300 kWh, Wohnungen 500 + 300: 500 kWh Allgemein.
    # 800,00/1.300 = 0,615385 je kWh. Anna 500 * 0,615385 = 307,69, Bert
    # 300 * 0,615385 = 184,62; die 500 Allgemein-kWh kosten 307,69, je 366
    # von 732 Personentagen = 153,85 -- Bert als letzter Posten 153,84
    # (R-NUM-02). Anna 461,54, Bert 338,46, zusammen 800,00.
    Golden(
        nr='GO-16', titel='Strom mit Allgemeinanteil',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('800.00', STROM),),
                            profile={5: 'direkt'},
                            zaehler=(stromzaehler(10, None, 1300.0, haupt=True),
                                     stromzaehler(11, 1, 500.0),
                                     stromzaehler(12, 2, 300.0))),
        soll={'Anna': ('461.54', '0.00'), 'Bert': ('338.46', '0.00')},
        bilanz='800.00'),

    # Dualtarif mit Preisen (NK-055): Haupt HT 2.000/NT 1.000, Wohnungen
    # Anna 1.500/200, Bert 500/800. Allgemein HT 0/NT 0. Preise 0,40/0,10
    # sind konsistent (2.000 * 0,40 + 1.000 * 0,10 = 900 < 1.000,00), der
    # Mischpreis der Rechnung fehlt: effektiv 0,4444/0,1111. Anna 1.500 *
    # 0,4444 + 200 * 0,1111 = 688,89, Bert 500 * 0,4444 + 800 * 0,1111 =
    # 311,11.
    Golden(
        nr='GO-17', titel='Strom dual mit Preisen',
        welt=lambda n: haus(n, (ANNA, BERT),
                            (umlage('1000.00', STROM, preis_ht=Decimal('0.40'),
                                    preis_nt=Decimal('0.10')),),
                            profile={5: 'direkt'},
                            zaehler=(stromzaehler(10, None, 2000.0, 1000.0, haupt=True),
                                     stromzaehler(11, 1, 1500.0, 200.0),
                                     stromzaehler(12, 2, 500.0, 800.0))),
        soll={'Anna': ('688.89', '0.00'), 'Bert': ('311.11', '0.00')},
        bilanz='1000.00'),

    # Dasselbe ohne Preise: Mischpreis 1.000,00/3.000 kWh = 0,3333 je kWh.
    # Anna (1.500 + 200) * 0,3333 = 566,67, Bert (500 + 800) * 0,3333 =
    # 433,33.
    Golden(
        nr='GO-18', titel='Strom dual ohne Preise (Mischpreis)',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('1000.00', STROM),),
                            profile={5: 'direkt'},
                            zaehler=(stromzaehler(10, None, 2000.0, 1000.0, haupt=True),
                                     stromzaehler(11, 1, 1500.0, 200.0),
                                     stromzaehler(12, 2, 500.0, 800.0))),
        soll={'Anna': ('566.67', '0.00'), 'Bert': ('433.33', '0.00')},
        bilanz='1000.00'),

    # Die NK-055-Welt mit Preisen: Haupt 3.000/1.000, Anna 1.200/800, Bert
    # 1.400/200; Allgemein HT 400. 1.300,00 konsistent: 0,40/0,10. Anna
    # 1.200 * 0,40 + 800 * 0,10 + 160/2 = 640,00, Bert 1.400 * 0,40 + 200 *
    # 0,10 + 160/2 = 660,00.
    Golden(
        nr='GO-19', titel='Strom HT/NT mit Preisen',
        welt=lambda n: haus(n, (ANNA, BERT),
                            (umlage('1300.00', STROM, preis_ht=Decimal('0.40'),
                                    preis_nt=Decimal('0.10')),),
                            profile={5: 'direkt'},
                            zaehler=(stromzaehler(10, None, 3000.0, 1000.0, haupt=True),
                                     stromzaehler(11, 1, 1200.0, 800.0),
                                     stromzaehler(12, 2, 1400.0, 200.0))),
        soll={'Anna': ('640.00', '0.00'), 'Bert': ('660.00', '0.00')},
        bilanz='1300.00'),

    # Dieselbe Welt ohne Preise: Mischpreis 1.300,00/4.000 kWh = 0,325. Der
    # Allgemeinanteil (400 kWh * 0,325 = 130,00) teilt sich je 65,00. Anna
    # 2.000 * 0,325 + 65,00 = 715,00, Bert 1.600 * 0,325 + 65,00 = 585,00.
    Golden(
        nr='GO-20', titel='Strom HT/NT ohne Preise',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('1300.00', STROM),),
                            profile={5: 'direkt'},
                            zaehler=(stromzaehler(10, None, 3000.0, 1000.0, haupt=True),
                                     stromzaehler(11, 1, 1200.0, 800.0),
                                     stromzaehler(12, 2, 1400.0, 200.0))),
        soll={'Anna': ('715.00', '0.00'), 'Bert': ('585.00', '0.00')},
        bilanz='1300.00'),

    # Verzicht: die Umlage wird nicht weitergegeben -- 0,00 fuer den Mieter,
    # nichts wird umgelegt, keine Bilanz.
    Golden(
        nr='GO-21', titel='Verzicht (ignoriert)',
        welt=lambda n: haus(n, (ANNA, BERT), (umlage('600.00'),),
                            profile={1: 'ignoriert'}),
        soll={'Anna': ('0.00', '0.00')},
        bilanz=None),
)


# --- Heizkosten nach § 7 HeizkostenV (NK-049) -------------------------------


def heizhaus(fuer, alle, rechnungen=None, zaehler=None, anlagen=None,
             wohnungen=None, beginn=JA, ende=JE, zahlungen=()):
    """Standard-Heizwelt: 2 x 50 qm, Anna 1.200/Bert 800 kWh, 70/30."""
    return haus(fuer, alle, rechnungen or (heizrechnung(),),
                zaehler or (warmezaehler(1, 1, 1200.0),
                            warmezaehler(2, 2, 800.0)),
                anlagen or (anlage(),), wohnungen=wohnungen,
                beginn=beginn, ende=ende, zahlungen=zahlungen)


GRUNDWELT = (ANNA, BERT)
ZAEHLER_WW = (warmezaehler(1, 1, 1200.0), warmezaehler(2, 2, 800.0),
              wasserzaehler(3, 1, 30.0), wasserzaehler(4, 2, 70.0))


GOLDEN_HEIZUNG: tuple = (

    # Nur Annas Zaehler ist erfasst: keine Verbrauchsteilung, alles nach
    # Flaeche -- 10.000,00 je 50 % = 5.000,00. Mit dem Mangel warnt der
    # Kern: Ausweis fehlt (E-CO2-AUSWEIS-FEHLT) und das 15-%-Kuerzungsrecht
    # (W-HKV-KUERZUNG-15).
    Golden(
        nr='GO-22', titel='Heizung, unvollstaendige Erfassung',
        welt=lambda n: heizhaus(n, GRUNDWELT,
                                zaehler=(warmezaehler(1, 1, 1200.0),)),
        soll={'Anna': ('5000.00', '0.00'), 'Bert': ('5000.00', '0.00')},
        bilanz='10000.00',
        kennungen={'Anna': ('E-CO2-AUSWEIS-FEHLT', 'KUERZUNG'),
                   'Bert': ('E-CO2-AUSWEIS-FEHLT', 'KUERZUNG')}),

    # Wohnung 2 ohne Mietverhaeltnis (D-43, R-NUM-05, NK-051): Verbrauchsteil
    # 7.000, Anna 1.200/2.000 * 7.000 = 4.200,00, Grundteil 3.000 * 0,5 =
    # 1.500,00 -- 5.700,00. Die leere Wohnung traegt ihren Verbrauchsrest
    # 800/2.000 * 7.000 = 2.800,00 und den Grundteil-Rest 1.500,00:
    # Vermieter 4.300,00.
    Golden(
        nr='GO-23', titel='Heizung, Leerstand traegt den Vermieter',
        welt=lambda n: heizhaus(n, (ANNA,)),
        soll={'Anna': ('5700.00', '4300.00')},
        bilanz='10000.00'),

    # Trennung gemessen (§ 9, Weg "gemessen"): Anlage 15.000 kWh WW von
    # 60.000 kWh. Wärme 5.250,00, davon Anna 1.200/2.000 * 5.250 = 3.150,00
    # + Grundteil 2.250 * 0,5 = 1.125,00 -> 4.275,00; Warmwasser 1.750,00,
    # davon 30/100 m3 = 525,00 + 750 * 0,5 = 375,00 -> 900,00. Anna
    # 5.175,00, Bert 800/2.000 * 5.250 = 2.100,00 + 1.125,00 + 70/100 *
    # 1.750,00 = 1.225,00 + 375,00 = 4.825,00.
    Golden(
        nr='GO-24', titel='Heizung, Trennung gemessen',
        welt=lambda n: heizhaus(n, GRUNDWELT, zaehler=ZAEHLER_WW,
                                anlagen=(anlage(versorgt=heizung.VERBUNDEN,
                                                warmwasser_weg=heizung.WW_ZAEHLER,
                                                warmwasser_kwh=Decimal('15000'),
                                                brennstoff_menge=Decimal('60000')),)),
        soll={'Anna': ('5175.00', '0.00'), 'Bert': ('4825.00', '0.00')},
        bilanz='10000.00'),

    # Trennung gerechnet (§ 9 Abs. 1): Q = 2,5 * 120 m3 * (60 - 10) C =
    # 15.000 kWh von 60.000 kWh Gesamtverbrauch -- dieselbe Menge wie
    # gemessen, dieselben 5.175,00/4.825,00.
    Golden(
        nr='GO-25', titel='Heizung, Trennung nach Formel',
        welt=lambda n: heizhaus(n, GRUNDWELT, zaehler=ZAEHLER_WW,
                                anlagen=(anlage(versorgt=heizung.VERBUNDEN,
                                                warmwasser_weg=heizung.WW_FORMEL,
                                                warmwasser_volumen_m3=Decimal('120'),
                                                warmwasser_temperatur_c=Decimal('60'),
                                                brennstoff_menge=Decimal('60000')),)),
        soll={'Anna': ('5175.00', '0.00'), 'Bert': ('4825.00', '0.00')},
        bilanz='10000.00'),

    # Trennung geschaetzt (§ 9 Abs. 2): 32 kWh/m2a * 250 m2 = 8.000 von
    # 32.000 kWh -- wieder ein Viertel, wieder 5.175,00/4.825,00.
    Golden(
        nr='GO-26', titel='Heizung, Trennung nach Ersatzformel',
        welt=lambda n: heizhaus(n, GRUNDWELT, zaehler=ZAEHLER_WW,
                                anlagen=(anlage(versorgt=heizung.VERBUNDEN,
                                                warmwasser_weg=heizung.WW_ERSATZ,
                                                brennstoff_menge=Decimal('32000')),),
                                wohnungen=(wohnung(1, 125.0),
                                           wohnung(2, 125.0))),
        soll={'Anna': ('5175.00', '0.00'), 'Bert': ('4825.00', '0.00')},
        bilanz='10000.00'),

    # Trennung ueber den Heizwert: 15.000 kWh je 10 kWh/l = 1.500 von 6.000
    # Litern Oel -- ein Viertel, 5.175,00/4.825,00.
    Golden(
        nr='GO-27', titel='Heizung, Trennung ueber den Heizwert',
        welt=lambda n: heizhaus(n, GRUNDWELT, zaehler=ZAEHLER_WW,
                                anlagen=(anlage(versorgt=heizung.VERBUNDEN,
                                                warmwasser_weg=heizung.WW_ZAEHLER,
                                                warmwasser_kwh=Decimal('15000'),
                                                brennstoff_menge=Decimal('6000'),
                                                heizwert_kwh=Decimal('10')),)),
        soll={'Anna': ('5175.00', '0.00'), 'Bert': ('4825.00', '0.00')},
        bilanz='10000.00'),

    # Reine Warmwasseranlage (§ 8, Nummer 5): alles nach m3 und Flaeche.
    # Verbrauchsteil 10.000 * 0,7 = 7.000, Anna 30/100 m3 = 2.100,00 +
    # Grundteil 3.000 * 0,5 = 1.500,00 -> 3.600,00; Bert 4.900,00 +
    # 1.500,00 = 6.400,00.
    Golden(
        nr='GO-28', titel='Heizung, reine Warmwasseranlage',
        welt=lambda n: heizhaus(n, GRUNDWELT, zaehler=ZAEHLER_WW,
                                anlagen=(anlage(
                                    versorgt=heizung.WARMWASSER,
                                    warmwasser_weg=None,
                                    warmwasser_kwh=None,
                                    brennstoff_menge=None),)),
        soll={'Anna': ('3600.00', '0.00'), 'Bert': ('6400.00', '0.00')},
        bilanz='10000.00'),

    # Kein Trennungsweg angegeben: alles als Heizkosten (Nummer 6) mit
    # Hinweis -- Anna 4.200,00 + 1.500,00 = 5.700,00, Bert 4.300,00.
    Golden(
        nr='GO-29', titel='Heizung, ohne Trennungsweg',
        welt=lambda n: heizhaus(n, GRUNDWELT,
                                anlagen=(anlage(versorgt=heizung.VERBUNDEN,
                                                warmwasser_weg=None,
                                                warmwasser_kwh=None,
                                                brennstoff_menge=None),)),
        soll={'Anna': ('5700.00', '0.00'), 'Bert': ('4300.00', '0.00')},
        bilanz='10000.00',
        kennungen={'Anna': ('versorgt Heizung und Warmwasser',)}),

    # Ablesung am 30.06.2025 (Anna zieht aus): ihr Zaehler misst 1.000 kWh
    # bis zum Wechsel.Verbrauchsteil 7.000 * 1.000/2.200 = 3.181,82,
    # Grundteil 3.000 * 181/365 * 0,5 = 739,73 -- 3.921,54. Die Zeile nennt
    # Datum und Stand; die Bilanz bleibt offen (Annas Verbrauch nach dem
    # Wechsel gehoert in keine Sicht dieser Welt).
    Golden(
        nr='GO-30', titel='Heizung, Zwischenablesung misst den Wechsel',
        welt=lambda n: heizhaus(n, (mieter(1, 'Anna', 1, auszug=WECHSEL25),
                                    BERT),
            rechnungen=(heizrechnung(beginn=JA5, ende=JE5),),
            zaehler=(
                Zaehler(id=1, nummer='W-1', kategorie_id=WAERME.id,
                        kategorie_name=WAERME.name, ist_hauptzaehler=False,
                        immobilie_id=1, wohnung_id=1, heizungsanlage_id=1,
                        staende=(Stand(datum=JA5, wert=0.0),
                                 Stand(datum=WECHSEL25, wert=1000.0,
                                       art=heizung.ZWISCHENABLESUNG),
                                 Stand(datum=JG26, wert=1400.0))),
                warmezaehler(2, 2, 800.0, beginn=JA5, grenze=JG26)),
            beginn=JA5, ende=WECHSEL25),
        soll={'Anna': ('3921.54', None)},
        bilanz=None),

    # Ohne Ablesung am Wechsel: der Ersatzmassstab verteilt zeitanteilig.
    # Annas
    # Mietverhaeltnis umfasst 1.400 * 180/365 = 690,4110 kWh, also 7.000 *
    # 690,4110/2.200 = 2.196,76 am Verbrauchsteil; Grundteil 3.000 *
    # 180/365 = 1.479,4521, halbiert 739,73 -- 2.936,49. Mit Hinweis.
    Golden(
        nr='GO-31', titel='Heizung, Ersatzmassstab ohne Ablesung',
        welt=lambda n: heizhaus(n, (mieter(1, 'Anna', 1, auszug=WECHSEL25),
                                    BERT),
            rechnungen=(heizrechnung(beginn=JA5, ende=JE5),),
            zaehler=(warmezaehler(1, 1, 1400.0, beginn=JA5, grenze=JG26),
                     warmezaehler(2, 2, 800.0, beginn=JA5, grenze=JG26)),
            beginn=JA5, ende=WECHSEL25),
        soll={'Anna': ('2936.49', None)},
        bilanz=None,
        kennungen={'Anna': ('Zwischenablesung',)}),

    # Bert zieht zum 30.06.2025 ein, ohne Ablesung: sein Fenster hat 185
    # Tage, 800 * 185/365 = 405,4795 kWh, 7.000 * 405,4795/2.200 =
    # 1.290,16; Grundteil 3.000 * 185/365 = 1.520,55, halbiert 760,28
    # (Zwischenrundung) -- 2.050,44.
    Golden(
        nr='GO-32', titel='Heizung, Einzug ohne Ablesung',
        welt=lambda n: heizhaus(n, (ANNA, mieter(2, 'Bert', 2,
                                                 einzug=WECHSEL25)),
            rechnungen=(heizrechnung(beginn=JA5, ende=JE5),),
            zaehler=(warmezaehler(1, 1, 1400.0, beginn=JA5, grenze=JG26),
                     warmezaehler(2, 2, 800.0, beginn=JA5, grenze=JG26)),
            beginn=WECHSEL25, ende=JE5),
        soll={'Bert': ('2050.44', None)},
        bilanz=None,
        kennungen={'Bert': ('Zwischenablesung',)}),
)


def co2rechnung(betrag='10000.00', id=1, kosten='2000.00', emission='2200.00',
                anlage_id=1):
    """Eine Heizkostenrechnung mit CO2-Angaben (Grundwelt: 22,0 kg/m2a)."""
    kw = {}
    if kosten is not None:
        kw['co2_kosten'] = Decimal(kosten)
    if emission is not None:
        kw['co2_emission_kg'] = Decimal(emission)
    return heizrechnung(betrag, id=id, anlage_id=anlage_id, **kw)


GOLDEN_CO2: tuple = (

    # Grundwelt (22,0 kg/m2a -> Stufe 4, 70/30): Masse 8.000,00 (Verbrauch
    # 5.600: Anna 3.360,00, Bert 2.240,00; Flaeche 2.400: je 1.200,00). Die
    # 1.400,00 CO2-Mieteranteile folgen demselben Schluessel: Anna 798,00,
    # Bert 602,00. Anna 4.560 + 798 = 5.358,00, Bert 3.440 + 602 = 4.042,00,
    # Vermieter 600,00.
    Golden(
        nr='GO-33', titel='CO2 Grundwelt, Stufe 4',
        welt=lambda n: heizhaus(n, GRUNDWELT,
                                rechnungen=(co2rechnung(),)),
        soll={'Anna': ('5358.00', '600.00'), 'Bert': ('4042.00', '600.00')},
        bilanz='10000.00'),

    # 1.000 kg -> 10,0 kg/m2a -> Stufe 1 (100 %): alles beim Mieter. Anna
    # 4.560 + 1.140 = 5.700,00, Bert 3.440 + 860 = 4.300,00, Vermieter 0,00.
    Golden(
        nr='GO-34', titel='CO2 Stufe 1',
        welt=lambda n: heizhaus(n, GRUNDWELT,
                                rechnungen=(co2rechnung(emission='1000.00'),)),
        soll={'Anna': ('5700.00', '0.00'), 'Bert': ('4300.00', '0.00')},
        bilanz='10000.00'),

    # 6.200 kg -> 62,0 kg/m2a -> Stufe 10 (5 %): Mieter 100,00, Vermieter
    # 1.900,00. Anna 4.560 + 57,00 = 4.617,00, Bert 3.440 + 43,00 = 3.483,00.
    Golden(
        nr='GO-35', titel='CO2 Stufe 10',
        welt=lambda n: heizhaus(n, GRUNDWELT,
                                rechnungen=(co2rechnung(emission='6200.00'),)),
        soll={'Anna': ('4617.00', '1900.00'), 'Bert': ('3483.00', '1900.00')},
        bilanz='10000.00'),

    # 1.196 kg -> 11,96 kg/m2a -> auf 12,0 gerundet -> Stufe 2 (90 %, nicht
    # 100 -- Runden vor dem Einstufen): Mieter 1.800,00, Vermieter 200,00.
    # Anna 4.560 + 1.026,00 = 5.586,00, Bert 3.440 + 774,00 = 4.214,00.
    Golden(
        nr='GO-36', titel='CO2 Grenzfall 11,96 rundet zu 12,0',
        welt=lambda n: heizhaus(n, GRUNDWELT,
                                rechnungen=(co2rechnung(emission='1196.00'),)),
        soll={'Anna': ('5586.00', '200.00'), 'Bert': ('4214.00', '200.00')},
        bilanz='10000.00'),

    # Ohne Emissions- und Kostenangaben bleibt es bei der reinen § 7-Verteil
    # (5.700,00/4.300,00) und die blockierende Warnung E-CO2-AUSWEIS-FEHLT
    # erscheint (NK-053, R-CO2-02).
    Golden(
        nr='GO-37', titel='CO2 ohne Ausweisangaben',
        welt=lambda n: heizhaus(n, GRUNDWELT),
        soll={'Anna': ('5700.00', '0.00'), 'Bert': ('4300.00', '0.00')},
        bilanz='10000.00',
        kennungen={'Anna': ('E-CO2-AUSWEIS-FEHLT',),
                   'Bert': ('E-CO2-AUSWEIS-FEHLT',)}),

    # Grundwelt mit leerer Wohnung 2: Anna wie in GO-33 (5.358,00), beim
    # Vermieter bleibt 4.642,00 -- Grundteil- und Verbrauchsrest samt Berts
    # CO2-Anteil, zusammen 10.000,00.
    Golden(
        nr='GO-38', titel='CO2 mit leerer Wohnung',
        welt=lambda n: heizhaus(n, (ANNA,), rechnungen=(co2rechnung(),)),
        soll={'Anna': ('5358.00', '4642.00')},
        bilanz='10000.00'),

    # Zwei Rechnungen, eine Anlage, je 1.000 kg/1.100 kg CO2: 2.200 kg ->
    # 22,0 -> Stufe 4. Dieselbe Masse und Aufteilung wie GO-33.
    Golden(
        nr='GO-39', titel='CO2 auf zwei Rechnungen',
        welt=lambda n: heizhaus(n, GRUNDWELT, rechnungen=(
            co2rechnung('5000.00', id=1, kosten='1000.00',
                        emission='1100.00'),
            co2rechnung('5000.00', id=2, kosten='1000.00',
                        emission='1100.00'))),
        soll={'Anna': ('5358.00', '600.00'), 'Bert': ('4042.00', '600.00')},
        bilanz='10000.00'),

    # Zwei Anlagen (je 70 %, je eigene Rechnung mit CO2): die Massen werden
    # je Anlage gezogen (6.000 - 1.200 = 4.800; 4.000 - 800 = 3.200), der
    # CO2-Mieteranteil je Zeile folgt ihrem § 7-Schluessel. Anna Kessel A
    # 1.344 + 720 + 840 * 0,43 = 2.425,20, Kessel B 896 + 480 + 560 * 0,43
    # = 1.616,80 -- 4.042,00. Bert 3.214,80 + 2.143,20 = 5.358,00. Vermieter
    # 360 + 240 = 600,00.
    Golden(
        nr='GO-40', titel='CO2 auf zwei Anlagen',
        welt=lambda n: heizhaus(n, GRUNDWELT, rechnungen=(
            co2rechnung('6000.00', id=1, kosten='1200.00',
                        emission='1320.00'),
            co2rechnung('4000.00', id=2, kosten='800.00', emission='880.00')),
            zaehler=(warmezaehler(1, 1, 800.0), warmezaehler(2, 2, 1200.0),
                     warmezaehler(3, 1, 400.0, anlage_id=2),
                     warmezaehler(4, 2, 600.0, anlage_id=2)),
            anlagen=(anlage(), anlage(id=2, name='Kessel B'))),
        soll={'Anna': ('4042.00', '600.00'), 'Bert': ('5358.00', '600.00')},
        bilanz='10000.00'),

    # Grundwelt mit 5.000,00 Vorauszahlung: 5.358,00 - 5.000,00 = 358,00
    # Nachzahlung.
    Golden(
        nr='GO-41', titel='CO2 mit Vorauszahlung',
        welt=lambda n: heizhaus(n, GRUNDWELT, rechnungen=(co2rechnung(),),
                                zahlungen=(Zahlung(datum=date(2024, 6, 1),
                                                   betrag=Decimal('5000.00')),)),
        soll={'Anna': ('5358.00', '600.00'), 'Bert': ('4042.00', '600.00')},
        bilanz='10000.00',
        saldo='358.00'),

    # Krumme Zahlungen (F-21): 1.000,00 + 0,01 = 1.000,01 angerechnet,
    # Nachzahlung 5.358,00 - 1.000,01 = 4.357,99.
    Golden(
        nr='GO-42', titel='CO2 mit krummen Vorauszahlungen',
        welt=lambda n: heizhaus(n, GRUNDWELT, rechnungen=(co2rechnung(),),
                                zahlungen=(Zahlung(datum=date(2024, 6, 1),
                                                   betrag=Decimal('1000.00')),
                                           Zahlung(datum=date(2024, 9, 1),
                                                   betrag=Decimal('0.01')))),
        soll={'Anna': ('5358.00', '600.00'), 'Bert': ('4042.00', '600.00')},
        bilanz='10000.00',
        saldo='4357.99'),
)


GOLDEN = GOLDEN_VORTEIL + GOLDEN_HEIZUNG + GOLDEN_CO2


# --- Die Pruefung -----------------------------------------------------------


def golden_von(nr):
    return next(g for g in GOLDEN if g.nr == nr)


@pytest.mark.parametrize('golden', GOLDEN, ids=lambda g: g.nr)
def test_goldener_wert(golden):
    """Jedes Golden: Betraege je Sicht, Kennungen, Bilanz, Saldo."""
    tenant_summen = []
    vermieter = []
    for name, (soll_mieter, soll_vermieter) in golden.soll.items():
        ergebnis = rechne(golden.welt(name))
        assert ergebnis['total_amount'] == Decimal(soll_mieter), (
            golden.nr, name, 'Mieteranteil')
        if soll_vermieter is not None:
            assert ergebnis['landlord_share']['total_amount'] \
                == Decimal(soll_vermieter), (golden.nr, name,
                                             'Vermieteranteil')
        tenant_summen.append(ergebnis['total_amount'])
        vermieter.append(ergebnis['landlord_share']['total_amount'])
        for kennung in golden.kennungen.get(name, ()):
            assert any(kennung in w for w in ergebnis['warnings']), (
                golden.nr, name, kennung, ergebnis['warnings'])
    if golden.bilanz is not None:
        # Der Vermieterrest gehoert zur Zeit: nur die laengste Sicht sieht
        # ihn ganz, er wird genau einmal gezaehlt.
        bilanz = sum(tenant_summen) + max(vermieter)
        assert bilanz == Decimal(golden.bilanz), (golden.nr, 'Bilanz')
    if golden.saldo is not None:
        erster = rechne(golden.welt(next(iter(golden.soll))))
        assert erster['balance'] == Decimal(golden.saldo), (golden.nr,
                                                            'Saldo')


def test_die_nummern_sind_eindeutig():
    """Keine Go-Nr. kommt doppelt vor."""
    nummern = [g.nr for g in GOLDEN]
    assert len(nummern) == len(set(nummern))


def test_die_karte_ist_abgedeckt():
    """Mindestens 40 Goldens, davon mindestens 10 mit Heizkosten und CO2."""
    assert len(GOLDEN) >= 40
    heiz_co2 = [g for g in GOLDEN if g.nr >= 'GO-33']
    assert len(heiz_co2) >= 10
    assert all('CO2' in g.titel for g in heiz_co2)


# --- Rechenwege im Detail (R-HK-03, R-CO2-02) -------------------------------


RECHENWEGE = (
    # Der dual berechnete Preis steht in den Details, der Mischpreis nicht.
    ('GO-17', lambda e: (
        e['line_items'][0]['meter_details']['preis_ht'] == Decimal('0.4444')
        and e['line_items'][0]['meter_details']['preis_nt'] == Decimal('0.1111')
        and e['line_items'][0]['meter_details']['cost_per_unit'] is None)),
    ('GO-18', lambda e: (
        e['line_items'][0]['meter_details']['cost_per_unit']
        == Decimal('0.3333'))),
    # Die Trennung zeigt beide Zeilen mit Zweck und Paragrafen-Nummer.
    ('GO-24', lambda e: (
        len([z for z in e['line_items']
             if z['billing_type'] == 'heizkosten']) == 2)),
    # Der Ersatzmassstab wird benannt und als Mangel gemeldet.
    ('GO-31', lambda e: (
        next(z for z in e['line_items']
             if z['billing_type'] == 'heizkosten')
        ['heizung_details']['ersatzmassstab'] is not None)),
    # Die CO2-Aufteilung steht im Ergebnis (R-CO2-02).
    ('GO-33', lambda e: (
        e['co2']['stufe'] == 4
        and e['co2']['mieter_anteil_euro'] == Decimal('798.00')
        and e['co2']['vermieter_anteil_euro'] == Decimal('600.00'))),
    ('GO-36', lambda e: e['co2']['stufe'] == 2),
)


@pytest.mark.parametrize('nr, pruefe', RECHENWEGE, ids=lambda x: str(x))
def test_goldene_rechenwege(nr, pruefe):
    """Der Weg zum goldenen Wert ist selbst Teil des Goldens."""
    golden = golden_von(nr)
    ergebnis = rechne(golden.welt('Anna'))
    assert pruefe(ergebnis), (nr, ergebnis['line_items'])
