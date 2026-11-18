"""Vertraglicher Kostenanteil, exakt in Prozent mit zwei Nachkommastellen."""
from decimal import Decimal, InvalidOperation


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
