"""Der Haftungshinweis beim ersten Start (NK-174, D-100).

Ein Text, eine Fassung. Die Oberfläche zeigt ihn beim ersten Öffnen nach
der Einrichtung als Dialog ohne Schließen-Knopf; weiter geht es nur mit
„Verstanden“. Einmal je Fassung: wieder, wenn die bestätigte nicht die
aktuelle ist (neuer Text, Umzug mit altem Paket). Ein Weg für Docker und
Windows-App, deshalb keine eigene Stufe in ``/einrichtung``.
Gesiezt wie jede andere Meldung (Glossar Par. 7).
Kein Haken, kein Vertrag, kein Vermerk auf dem PDF für den Mieter (F-97).
Derselbe Text steht im Über-Dialog (NK-179), in README und Store-Beschreibung.

Neue ``VERSION`` nur, wenn sich der Inhalt ändert -- dann sehen alle den
Hinweis noch einmal.
"""

from __future__ import annotations

from datetime import datetime, timezone

import einstellungen

VERSION = 1
TITEL = 'Bevor es losgeht'
TEXT = (
    'NebenkostenFix ist kostenlos und wird ohne Gewähr bereitgestellt.',
    'Der Entwickler übernimmt keine Haftung für die Richtigkeit Ihrer '
    'Abrechnungen, soweit das Gesetz das zulässt.',
    'Die Anwendung ist keine Rechtsberatung.',
    'Prüfen Sie jede Abrechnung selbst, bevor Sie sie verschicken.',
)


def stand(ordner=None) -> dict:
    gespeichert = einstellungen.lesen(ordner)['haftung'] or {}
    return {'version': VERSION, 'titel': TITEL, 'text': list(TEXT),
            'bestaetigt': gespeichert.get('version') == VERSION}


def bestaetigen(ordner=None) -> None:
    einstellungen.schreiben(ordner, haftung={
        'version': VERSION,
        'bestaetigt_am': datetime.now(timezone.utc).isoformat(timespec='seconds')})
