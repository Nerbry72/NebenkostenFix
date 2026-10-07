"""Zahlen in den Umlagetexten deutsch und mit m² (NK-222).

Die Vorschau zeigte „Umlage nach qm (52.0 von 113.0 qm)“: der Punkt eines
floats und das verworfene „qm“ (Glossar, Regel 5) standen im Text, den der
Mieter liest. Ein Text ohne Komma oder mit „qm“ fällt hier auf.
"""

from dataclasses import replace

from nebenkostenfix.rechenkern import Wohnung, menge_text, rechne, zahl_text

from tests.test_rechenkern import rechnung, vorgang


def test_zahl_text_deutsch_ohne_stellenverlust():
    assert zahl_text(52.0) == '52'
    assert zahl_text(113.25) == '113,25'
    assert zahl_text(1234567.5) == '1234567,5'
    assert zahl_text(100) == '100'


def test_menge_text_eine_stelle_mit_komma():
    assert menge_text(1234.56) == '1234,6'
    assert menge_text(0) == '0,0'


def test_umlage_nach_wohnflaeche_mit_komma_und_m2():
    meine = Wohnung(id=1, name='EG links', qm=52.5)
    andere = Wohnung(id=2, name='EG rechts', qm=60.75)
    v = replace(vorgang([rechnung('1132.50')]), wohnung=meine, wohnungen=(meine, andere))
    posten = rechne(v)['line_items'][0]
    assert posten['description'] == 'Umlage nach Wohnfläche (52,5 von 113,25 m²)'
    assert all('qm' not in s for s in posten.get('rechenweg', []))
