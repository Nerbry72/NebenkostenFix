"""Zeit: UTC speichern, Ortszeit zeigen (NK-094).

Die Zeitstempel der Anwendung stehen in UTC in der Datenbank
(``datetime.utcnow`` -- naive Zeit ohne Offset). Ein Zeitstempel, der den
Vermieter erreicht -- die letzte Anmeldung in der Auswertung, das
Erstellungsdatum auf dem Deckblatt -- ist aber eine Ortszeit: Die
Abrechnung gilt in Deutschland, und „Erstellt am 24.09.2026 08:15“ muss
die Uhrzeit zeigen, die der Vermieter auf seiner Uhr liest, nicht die des
Servers in einem Rechenzentrum in einer anderen Zone.

Der Unterschied ist im Sommer zwei Stunden und im Winter einer
(MEZ/MESZ, Europe/Berlin). Genau deshalb ist er nicht durch Verschieben
um eine feste Zahl zu haben -- ein Sommerzeitstempel, der um genau eine
Stunde verschoben wird, liegt im Winter falsch.

Diese Regeln gelten:

  * Speichern: UTC, naive Zeit (``jetzt_utc``) -- so steht es heute in
    den Tabellen, und daran aendert dieses Modul nichts.
  * Anzeigen: erst UTC anheften, dann nach Europe/Berlin wandeln
    (``als_ortszeit``).
  * Datumsangaben ohne Uhrzeit (Fristen, Zeitraeume) bleiben Kalender-
   daten und laufen nicht durch dieses Modul.

Geprueft in ``tests/test_ortszeit.py``: Sommer und Winter gepinnt, die
Anmeldung wandert vom Speichern zur Anzeige.
"""

from __future__ import annotations

from datetime import datetime, timezone
from datetime import date
from zoneinfo import ZoneInfo

#: Die Zone, in der die Abrechnung gilt. Die HeizkostenV wird nicht in
#: Zeitzonen unterteilt; die Anwendung schon gar nicht.
ORTSZONE = ZoneInfo('Europe/Berlin')

#: Das Anzeigeformat fuer Zeitstempel mit Uhrzeit.
FORMAT = '%d.%m.%Y %H:%M'

#: Das Anzeigeformat fuer reine Kalenderdaten.
DATUMSFORMAT = '%d.%m.%Y'


def jetzt_utc() -> datetime:
    """Der Zeitpunkt jetzt, zum Speichern: naive Zeit in UTC."""
    return datetime.utcnow()


def als_ortszeit(zeitpunkt: datetime | None,
                 format: str = FORMAT) -> str | None:
    """Ein gespeicherter UTC-Zeitpunkt, wie der Vermieter ihn liest.

    Die Datenbank traegt naive UTC-Zeit (R-DSGVO egal, aber die
    Konvention des Schemas); ohne angeheftete Zone gilt hier genau das.
    Ein Zeitpunkt, der schon eine Zone traegt, wird unverändert
    uebernommen und nur gewandelt -- so akzeptiert der Weg auch bewusste
    aware-Zeiten, ohne sie zu verdrehen. Reine Datumswerte, wie sie aus
    Tabellen mit DATE-Spalte zurueckkommen, sind Kalenderdaten: sie
    werden ohne Zone nur formatiert.

        >>> als_ortszeit(datetime(2026, 7, 15, 10, 30))
        '15.07.2026 12:30'
        >>> als_ortszeit(datetime(2026, 1, 15, 10, 30))
        '15.01.2026 11:30'
        >>> als_ortszeit(None) is None
        True
        >>> als_ortszeit(date(2026, 7, 15))
        '15.07.2026'
    """
    if zeitpunkt is None:
        return None
    if not isinstance(zeitpunkt, datetime):
        # Ein reines Datum (alte Zeilen: die Tabelle traegt DATE) ist
        # Kalenderdaten und braucht keine Zone -- es wird ohne Uhrzeit
        # formatiert, auch wenn der Aufrufer ein Uhrzeitformat verlangt.
        return zeitpunkt.strftime(DATUMSFORMAT)
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return zeitpunkt.astimezone(ORTSZONE).strftime(format)


def als_ortsdatum(zeitpunkt: date | datetime | None) -> date | None:
    """Der Tag, an dem der Zeitpunkt in Berlin liegt -- zum Vergleichen.

    Reine Datumswerte (alte Zeilen ohne Uhrzeit) bleiben, wie sie sind;
    UTC-Zeitpunkte werden erst nach Berlin gewandelt und dann auf den
    Tag gekürzt. So vergleicht die Anwendung Kalenderdaten und nicht
    Datum mit Uhrzeit -- und der Tag ist der, den der Vermieter liest.

        >>> als_ortsdatum(datetime(2026, 7, 14, 23, 30))
        datetime.date(2026, 7, 15)
        >>> als_ortsdatum(date(2026, 7, 14))
        datetime.date(2026, 7, 14)
    """
    if zeitpunkt is None:
        return None
    if not isinstance(zeitpunkt, datetime):
        return zeitpunkt
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return zeitpunkt.astimezone(ORTSZONE).date()


__all__ = ['ORTSZONE', 'FORMAT', 'DATUMSFORMAT', 'jetzt_utc',
           'als_ortszeit', 'als_ortsdatum']
