"""Der Betriebskostenkatalog des § 2 BetrKV. Der eine Ort (NK-044).

§ 2 BetrKV zaehlt siebzehn Arten von Betriebskosten auf, und diese Aufzaehlung
ist **abschliessend**: was dort nicht steht, ist nicht umlagefaehig (R-KAT-01).
Nr. 17 ist der einzige offene Posten, und auch der nur, wenn die Kostenart im
Mietvertrag ausdruecklich benannt ist (R-KAT-02).

Bis hierher kannte die Anwendung den Katalog nicht. Der Seed legte acht frei
benannte Kostenarten an -- Strom, Wasser, Abwasser, Niederschlagswasser, Gas,
Grundsteuer, Gebaeudeversicherung, Sonstiges -- und die Zeichenkette "BetrKV"
kam im ganzen Bestand nicht vor. Es fehlten Aufzug, Muell, Hauswart,
Beleuchtung, Schornstein, Gartenpflege und Waeschepflege: sieben Posten, die
in fast jeder Abrechnung vorkommen, und der Vermieter musste sie unter
"Sonstiges" verbuchen oder gar nicht.

Zwei Dinge haengen daran, und beide sind keine Formsache:

* **Die Abrechnung muss die Kostenart benennen** (R-DOC-01, BGH). Eine Zeile
  "Sonstiges 1.240,00 EUR" ist keine Angabe, sondern eine Summe. Mit der
  Nummer steht daneben, welcher Posten des Gesetzes gemeint ist.
* **Nr. 17 ist der Sonderfall, nicht der Normalfall.** Solange alles unter
  "Sonstiges" laeuft, faellt nicht auf, dass gerade der Posten, der eine
  ausdrueckliche Vereinbarung braucht, der meistbenutzte ist.

Die Bezeichnungen in ``BEZEICHNUNGEN`` sind am Verordnungstext gekuerzt: sie
nennen die Sache, nicht die vier Abrechnungsvarianten, die § 2 Nr. 4 und 5
jeweils aufzaehlen. Wer den vollen Wortlaut braucht, findet ihn in
der BetrKV selbst (R-KAT-01).

Die Datei haengt an nichts als der Standardbibliothek. Der Rechenkern
importiert kein ORM (NK-037), und diese Regel gilt fuer seine Bausteine mit --
dasselbe Versprechen wie in ``geld.py``, ``zeitraum.py`` und
``abrechnungsart.py``.
"""

from __future__ import annotations

__all__ = [
    'BEZEICHNUNGEN',
    'NUMMERN',
    'SONSTIGE',
    'KATALOG',
    'NR_HEIZUNG',
    'NR_WARMWASSER',
    'NR_VERBUNDENE_ANLAGE',
    'NR_ALLGEMEINSTROM',
    'EINHEITEN',
    'RUBRIKEN',
    'BEREICHE',
    'BetrKVFehler',
    'bezeichnung',
    'beschriftung',
    'ist_gueltig',
    'normiere',
    'pruefe',
    'ist_sonstige',
    'zuordnung',
    'ist_niederschlag',
    'katalogeintrag',
    'einheit',
    'rubrik',
    'bereich',
]


#: Die Nummern, hinter denen die Anwendung an mehreren Stellen raten
#: musste (F-32). Wer nur einen Namen sieht -- eine Zeile aus einem
#: fremden Bericht, eine Probe ohne Seed -- ordnet mit ``zuordnung``;
#: wer das Datenbankfeld in der Hand hat, liest die Nummer selbst.
NR_HEIZUNG = 4
NR_WARMWASSER = 5
NR_VERBUNDENE_ANLAGE = 6
NR_ALLGEMEINSTROM = 11

#: Nummer aus § 2 BetrKV -> was der Vermieter dazu liest. Am Verordnungstext
#: gekuerzt: die Sache, nicht die Abrechnungsvarianten.
BEZEICHNUNGEN = {
    1: 'Laufende öffentliche Lasten des Grundstücks (Grundsteuer)',
    2: 'Wasserversorgung',
    3: 'Entwässerung',
    4: 'Betrieb der zentralen Heizungsanlage',
    5: 'Betrieb der zentralen Warmwasserversorgungsanlage',
    6: 'Verbundene Heizungs- und Warmwasserversorgungsanlagen',
    7: 'Betrieb des Personen- oder Lastenaufzugs',
    8: 'Straßenreinigung und Müllbeseitigung',
    9: 'Gebäudereinigung und Ungezieferbekämpfung',
    10: 'Gartenpflege',
    11: 'Beleuchtung',
    12: 'Schornsteinreinigung',
    13: 'Sach- und Haftpflichtversicherung',
    14: 'Hauswart',
    15: 'Betrieb der Antennen-, Breitband- oder Glasfaseranlage',
    16: 'Betrieb der Einrichtungen für die Wäschepflege',
    17: 'Sonstige Betriebskosten',
}

NUMMERN = frozenset(BEZEICHNUNGEN)

#: Die einzige offene Position. Alles, was sich keiner der sechzehn benannten
#: Nummern zuordnen laesst, landet hier -- und braucht dann eine ausdrueckliche
#: Vereinbarung im Mietvertrag (R-KAT-02).
SONSTIGE = 17

#: Was der Seed anlegt: eine Kostenart je Nummer, in der Sprache, in der der
#: Vermieter sie auf seinen Rechnungen wiederfindet -- mit einer Ausnahme:
#: Nr. 3 traegt zwei Eintraege (NK-117, D-72). Das Schmutzwasser geht nach
#: dem Frischwasserzaehler, das Niederschlagswasser nach der Flaeche; beide
#: sind "Entwaesserung", aber eine Kostenart mit einer Vorgabe kann nicht
#: beides sein. Wer sie zusammenlegt, rechnet eine der beiden falsch. ``verteilung`` ist die
#: Vorgabe der Kostenart; womit ein einzelner Mieter belastet wird, entscheidet
#: sein Kostenprofil (``abrechnungsart.py``).
#:
#: ``zaehler=True`` nur dort, wo eine Abrechnung ohne Zaehlerstand gar nicht
#: geht. Heizung und Warmwasser bekommen ihn **nicht**: sie werden nicht ueber
#: einen Zaehler je Wohnung abgerechnet, sondern ueber die Verteilung nach
#: HeizkostenV -- das baut NK-049, und bis dahin waere ein Pflichtzaehler eine
#: Behauptung, die die Anwendung nicht einloesen kann.
KATALOG = (
    {'nr': 1, 'name': 'Grundsteuer', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 2, 'name': 'Wasserversorgung', 'verteilung': 'METER_READING', 'zaehler': True},
    {'nr': 3, 'name': 'Entwässerung', 'verteilung': 'METER_READING', 'zaehler': False},
    {'nr': 3, 'name': 'Niederschlagswasser', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 4, 'name': 'Heizung', 'verteilung': 'METER_READING', 'zaehler': False},
    {'nr': 5, 'name': 'Warmwasser', 'verteilung': 'METER_READING', 'zaehler': False},
    {'nr': 6, 'name': 'Heizung und Warmwasser (verbundene Anlage)', 'verteilung': 'METER_READING', 'zaehler': False},
    {'nr': 7, 'name': 'Aufzug', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 8, 'name': 'Straßenreinigung und Müllbeseitigung', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 9, 'name': 'Gebäudereinigung und Ungezieferbekämpfung', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 10, 'name': 'Gartenpflege', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 11, 'name': 'Beleuchtung (Allgemeinstrom)', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 12, 'name': 'Schornsteinreinigung', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 13, 'name': 'Sach- und Haftpflichtversicherung', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 14, 'name': 'Hauswart', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 15, 'name': 'Antenne, Breitband oder Glasfaser', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 16, 'name': 'Wäschepflege', 'verteilung': 'PER_SQM', 'zaehler': False},
    {'nr': 17, 'name': 'Sonstige Betriebskosten', 'verteilung': 'PER_SQM', 'zaehler': False},
)


class BetrKVFehler(ValueError):
    """Eine Nummer, die § 2 BetrKV nicht kennt."""


def bezeichnung(nr) -> str:
    """Die Bezeichnung zur Nummer -- oder ``BetrKVFehler``.

        >>> bezeichnung(10)
        'Gartenpflege'
    """
    return BEZEICHNUNGEN[pruefe(nr)]


def beschriftung(nr) -> str:
    """Nummer und Bezeichnung, wie sie auf der Abrechnung stehen.

        >>> beschriftung(8)
        'Nr. 8 · Straßenreinigung und Müllbeseitigung'
    """
    geprueft = pruefe(nr)
    return f'Nr. {geprueft} · {BEZEICHNUNGEN[geprueft]}'


def ist_gueltig(nr) -> bool:
    """Ob ``nr`` **genau so** eine Katalognummer ist -- ohne Normieren.

        >>> ist_gueltig(1), ist_gueltig(17), ist_gueltig(18), ist_gueltig(0)
        (True, True, False, False)

    ``True`` ist in Python eine 1, und ein ``True`` in dieser Spalte waere ein
    Fehler, kein Posten des Gesetzes:

        >>> ist_gueltig(True), ist_gueltig('4'), ist_gueltig(None)
        (False, False, False)
    """
    return isinstance(nr, int) and not isinstance(nr, bool) and nr in NUMMERN


def normiere(nr):
    """Transportrauschen wegnehmen: eine Nummer aus einem Formular ist Text.

        >>> normiere(' 7 ')
        7
        >>> normiere('Nr. 7')
        7

    Was sich nicht in eine Zahl aufloesen laesst, geht unveraendert durch --
    ``pruefe()`` sagt dann, was daran falsch ist:

        >>> normiere('Aufzug')
        'Aufzug'
    """
    if isinstance(nr, str):
        ziffern = ''.join(z for z in nr if z.isdigit())
        buchstaben = ''.join(z for z in nr if z.isalpha())
        # Alles ausser Ziffern und einem vorangestellten "Nr." ist eine
        # Aussage, kein Rauschen: "7 Aufzug" geht unveraendert weiter.
        if ziffern and buchstaben.lower() in ('', 'nr'):
            return int(ziffern)
    return nr


def pruefe(nr, *, kostenart: str | None = None) -> int:
    """Die geprüfte Katalognummer -- oder ``BetrKVFehler``.

        >>> pruefe(' 15 ')
        15

    Die Meldung nennt den abgelehnten Wert und den erlaubten Bereich; wer eine
    Kostenart uebergibt, bekommt sie im Satz genannt:

        >>> try:
        ...     pruefe(18, kostenart='Kabelanschluss')
        ... except BetrKVFehler as fehler:
        ...     print(fehler)
        Die Kostenart „Kabelanschluss“ hat die BetrKV-Nummer „18“. \
§ 2 BetrKV kennt nur die Nummern 1 bis 17.
    """
    normiert = normiere(nr)
    if ist_gueltig(normiert):
        return normiert

    gezeigt = nr if isinstance(nr, (str, int)) and not isinstance(nr, bool) else repr(nr)
    wo = f'Die Kostenart „{kostenart}“ hat' if kostenart else 'Es gibt'
    raise BetrKVFehler(
        f'{wo} die BetrKV-Nummer „{gezeigt}“. '
        f'§ 2 BetrKV kennt nur die Nummern 1 bis 17.'
    )


def ist_sonstige(nr) -> bool:
    """Ob die Nummer der offene Posten ist (Nr. 17, R-KAT-02).

        >>> ist_sonstige(17), ist_sonstige(9)
        (True, False)
    """
    return ist_gueltig(nr) and nr == SONSTIGE


#: Schluesselwort -> Nummer, in der Reihenfolge, in der gesucht wird: das
#: Genauere zuerst. "Niederschlagswasser" muss vor "Wasser" stehen, sonst wird
#: Regenwasser zur Wasserversorgung; "Strassenreinigung" vor "Reinigung",
#: sonst wird die Muellabfuhr zur Gebaeudereinigung.
_SCHLUESSELWOERTER = (
    # Die verbundene Anlage steht ganz oben: ihr Name enthaelt "Warmwasser"
    # und "Heizung" und traefe sonst Nr. 5 oder Nr. 4.
    ('verbunden', 6), ('heizungundwarmwasser', 6),
    ('niederschlagswasser', 3), ('regenwasser', 3), ('oberflaechenwasser', 3),
    ('abwasser', 3), ('schmutzwasser', 3), ('entwaesserung', 3), ('kanal', 3),
    ('warmwasser', 5), ('brauchwasser', 5),
    ('wasserversorgung', 2), ('frischwasser', 2), ('kaltwasser', 2),
    ('trinkwasser', 2),
    ('grundsteuer', 1), ('oeffentlichelasten', 1),
    ('heizung', 4), ('heizkosten', 4), ('brennstoff', 4), ('heizoel', 4),
    ('fernwaerme', 4), ('pellets', 4), ('erdgas', 4), ('gas', 4),
    ('aufzug', 7), ('fahrstuhl', 7), ('lift', 7),
    ('strassenreinigung', 8), ('muell', 8), ('abfall', 8), ('winterdienst', 8),
    ('schornstein', 12), ('kaminkehrer', 12), ('kamin', 12),
    ('gebaeudereinigung', 9), ('hausreinigung', 9), ('ungeziefer', 9),
    ('schaedling', 9), ('reinigung', 9),
    ('gartenpflege', 10), ('gruenpflege', 10), ('baumpflege', 10),
    ('garten', 10),
    ('allgemeinstrom', 11), ('hausstrom', 11), ('beleuchtung', 11),
    ('strom', 11),
    ('haftpflicht', 13), ('versicherung', 13),
    ('hauswart', 14), ('hausmeister', 14),
    ('antenne', 15), ('kabelfernsehen', 15), ('breitband', 15),
    ('glasfaser', 15), ('kabel', 15),
    ('waschkueche', 16), ('waeschepflege', 16), ('waschmaschine', 16),
    ('trockner', 16), ('waesche', 16),
    # Nur Wasser: steht ganz unten, damit jede genauere Wasser-Kostenart
    # vorher greift.
    ('wasser', 2),
)

_UMSCHRIFT = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'})


def _vergleichsform(name: str) -> str:
    """Kleingeschrieben, Umlaute aufgeloest, ohne alles ausser Buchstaben."""
    klein = name.lower().translate(_UMSCHRIFT)
    return ''.join(z for z in klein if z.isalpha())


def zuordnung(name) -> int:
    """Welche Katalognummer zu einem frei benannten Altbestand passt.

    Das ist eine **Vermutung fuer den Altbestand**, keine Rechtsauskunft: die
    acht Kostenarten des alten Seeds und alles, was ein Vermieter seit Jahren
    selbst eingetragen hat, brauchen beim Einspielen dieser Karte eine Nummer.
    Wer nachher eine andere fuer richtig haelt, aendert sie.

        >>> zuordnung('Grundsteuer'), zuordnung('Gebäudeversicherung')
        (1, 13)
        >>> zuordnung('Niederschlagswasser'), zuordnung('Wasser')
        (3, 2)

    Das Genauere gewinnt, auch wenn das allgemeinere Wort enthalten ist:

        >>> zuordnung('Straßenreinigung'), zuordnung('Treppenhausreinigung')
        (8, 9)

    Was sich keinem Posten zuordnen laesst, wird Nr. 17 -- der offene Posten
    ist der richtige Ort fuer das Unbekannte, nicht Nr. 1:

        >>> zuordnung('Sonstiges'), zuordnung('Dachterrasse')
        (17, 17)
        >>> zuordnung(None), zuordnung('')
        (17, 17)
    """
    if not isinstance(name, str):
        return SONSTIGE
    form = _vergleichsform(name)
    if not form:
        return SONSTIGE
    for wort, nr in _SCHLUESSELWOERTER:
        if wort in form:
            return nr
    return SONSTIGE


#: Woran das Niederschlagswasser zu erkennen ist -- in der Vergleichsform
#: (``_vergleichsform``), also ohne Umlaute und Leerzeichen.
_NIEDERSCHLAG = ('niederschlag', 'regenwasser', 'oberflaechenwasser')


def ist_niederschlag(name) -> bool:
    """Meint der Name das Niederschlagswasser der Nr. 3 (NK-117, D-72)?

        >>> ist_niederschlag('Niederschlagswasser'), ist_niederschlag('Regenwasser')
        (True, True)
        >>> ist_niederschlag('Abwasser'), ist_niederschlag(None)
        (False, False)
    """
    if not isinstance(name, str):
        return False
    form = _vergleichsform(name)
    return any(wort in form for wort in _NIEDERSCHLAG)


def katalogeintrag(name) -> dict:
    """Der Katalogeintrag, auf den ein frei benannter Altbestand faellt.

    Die Nummer allein reicht nicht mehr, seit Nr. 3 zwei Eintraege hat
    (NK-117): ``zuordnung`` sagt die Nummer, das Niederschlagswasser
    entscheidet innerhalb der Nr. 3 der Name.

        >>> katalogeintrag('Abwasser')['name'], katalogeintrag('Regenwasser')['name']
        ('Entwässerung', 'Niederschlagswasser')
        >>> katalogeintrag('Strom')['name']
        'Beleuchtung (Allgemeinstrom)'
    """
    nr = zuordnung(name)
    passend = [e for e in KATALOG if e['nr'] == nr]
    if len(passend) > 1:
        niederschlag = ist_niederschlag(name)
        passend = [e for e in passend
                   if ist_niederschlag(e['name']) == niederschlag]
    return passend[0]


#: Die Einheit, die ein Zaehler der jeweiligen BetrKV-Nummer misst. Nr. 4
#: und Nr. 6 sind Wärmezähler: sie zählen Wärmemenge, und die misst die
#: HeizkostenV in Kilowattstunden (§ 5 Abs. 1 nennt Wärmezähler
#: ausdrücklich). Nr. 2, Nr. 3 und Nr. 5 zählen Kubikmeter Wasser -- das
#: Warmwasser der Nr. 5 auch, es ist Wasser, wenn auch ein versorgter
#: Posten. Alles andere umlagt ohne Zähler und trägt die neutrale Einheit.
#: Das ist der eine Ort hinter ``einheit_fuer`` und der Analytics-Einheit
#: (F-32/F-51, NK-121).
EINHEITEN = {
    1: 'Einheiten',
    2: 'm³', 3: 'm³',
    4: 'kWh', 5: 'm³', 6: 'kWh',
    7: 'Einheiten', 8: 'Einheiten', 9: 'Einheiten', 10: 'Einheiten',
    11: 'kWh',
    12: 'Einheiten', 13: 'Einheiten', 14: 'Einheiten', 15: 'Einheiten',
    16: 'Einheiten', 17: 'Einheiten',
}

#: Die Rubrik der Auswertung (Analytics), in die die Nummer fällt. Energie
#: sind die vier brennenden Posten samt Allgemeinstrom; Wasser & Abwasser
#: sind Wasserversorgung und Entwässerung (beide Nr.-3-Eintraege); alles
#: andere sind Betriebskosten.
RUBRIKEN = {
    2: 'Wasser & Abwasser', 3: 'Wasser & Abwasser',
    4: 'Energie', 5: 'Energie', 6: 'Energie', 11: 'Energie',
}

#: Der Bereich der Zeitreihe (Analytics). Strom ist allein die Nr. 11;
#: alles, was brennt, fällt unter „Gas“ -- auch das Warmwasser der Nr. 5,
#: das ein Brennstoffposten ist, kein Wasserposten (F-32: die alte
#: Stichwortliste räumte es in die Wasser-Spalte). Wasserversorgung und
#: Entwässerung sind Wasser; der Rest ist Sonstige Kosten.
BEREICHE = {
    2: 'Wasser', 3: 'Wasser',
    4: 'Gas', 5: 'Gas', 6: 'Gas',
    11: 'Strom',
}


def einheit(nr) -> str:
    """Die Mengeneinheit, die ein Zaehler dieser Nummer misst.

    Der Schlusspunkt der Nr. 6: die verbundene Anlage heizt und wärmt das
    Wasser, aber ihr Zaehler am § 7 misst Kilowattstunden -- der Name
    enthält „Warmwasser“, und die alte Stichwortliste machte daraus Kubik-
    meter (F-51). Damit wird der Wärmezähler zum Warmwasserzähler und die
    Aufteilung nach § 7 und § 8 vertauscht.

        >>> einheit(5), einheit(6), einheit(11)
        ('m³', 'kWh', 'kWh')
    """
    return EINHEITEN[pruefe(nr)]


def rubrik(nr) -> str:
    """Die Rubrik der Auswertung, in die diese Nummer gehört.

        >>> rubrik(2), rubrik(6), rubrik(1)
        ('Wasser & Abwasser', 'Energie', 'Betriebskosten')
    """
    return RUBRIKEN.get(pruefe(nr), 'Betriebskosten')


def bereich(nr) -> str:
    """Der Bereich der Zeitreihe, in den diese Nummer gehört.

        >>> bereich(5), bereich(11), bereich(9)
        ('Gas', 'Strom', 'Sonstige Kosten')
    """
    return BEREICHE.get(pruefe(nr), 'Sonstige Kosten')
