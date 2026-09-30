"""Welche Module ein Quelltext importiert, fuer die Abhaengigkeitswaechter (NK-037).

Eigene Module zaehlen mit ihrem Namen im Paket: ``from nebenkostenfix import geld``
und ``from nebenkostenfix.geld import Geld`` ergeben beide ``geld`` (D-110). Sonst
stuende fuer jeden Baustein nur ``nebenkostenfix`` da, und ein Waechter koennte
``geld`` nicht mehr von ``models`` unterscheiden.
"""
import ast

PAKET = 'nebenkostenfix'


def importierte_module(baum):
    namen = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            namen.update(a.name.split('.')[0] for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            teile = knoten.module.split('.')
            if teile[0] != PAKET:
                namen.add(teile[0])
            elif len(teile) > 1:
                namen.add(teile[1])
            else:
                namen.update(a.name for a in knoten.names)
    return namen
