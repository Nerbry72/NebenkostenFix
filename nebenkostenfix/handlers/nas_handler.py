"""Alter Ort der Dateiablage (bis NK-132).

Die Klasse heisst jetzt ``ablage.Ablage``. Dieser Alias bleibt eine Version
lang, damit Skripte und Tests, die ``NASHandler`` importieren, weiterlaufen.
"""

from nebenkostenfix.ablage import Ablage as NASHandler  # noqa: F401
from nebenkostenfix.ablage import protokoll  # noqa: F401
