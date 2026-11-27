"""Vertraglicher Kostenanteil, exakt in Prozent mit zwei Nachkommastellen."""
from decimal import Decimal, InvalidOperation


def summenabschnitte(anteile, von, bis=None):
    """Summen je halboffenem Mietzeitraum; ein Auszugstag zählt nicht mehr.

    Anteile sind (Einzug, Auszug oder None, Prozentsatz). Auch Lücken
    erscheinen mit null, damit Leerstand beim Vermieter verbleibt.
    """
    anteile = list(anteile)
    grenzen = {von}
    for einzug, auszug, _ in anteile:
        for datum in (einzug, auszug):
            if datum is not None and datum > von and (bis is None or datum < bis):
                grenzen.add(datum)
    grenzen = sorted(grenzen)
    ergebnis = []
    for index, start in enumerate(grenzen):
        ende = grenzen[index + 1] if index + 1 < len(grenzen) else bis
        if ende is not None and start >= ende:
            continue
        summe = sum((wert for einzug, auszug, wert in anteile
                     if einzug <= start and (auszug is None or start < auszug)), Decimal(0))
        if ergebnis and ergebnis[-1][2] == summe:
            ergebnis[-1] = (ergebnis[-1][0], ende, summe)
        else:
            ergebnis.append((start, ende, summe))
    return ergebnis


def pruefe_prozent(wert) -> Decimal:
    try:
        if isinstance(wert, bool) or wert is None:
            raise ValueError
        zahl = Decimal(str(wert).strip().replace(',', '.'))
        if (not zahl.is_finite() or not 0 <= zahl <= 100
                or zahl != zahl.quantize(Decimal('0.01'))):
            raise ValueError
        return zahl
    except (ValueError, InvalidOperation):
        raise ValueError('Bitte einen Prozentsatz von 0 bis 100 mit höchstens zwei Nachkommastellen eingeben.') from None
