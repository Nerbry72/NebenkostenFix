"""Alter Ort der Dateiablage (bis NK-132).

Die Klasse heisst jetzt ``ablage.Ablage``. Dieser Alias bleibt eine Version
lang, damit Skripte und Tests, die ``NASHandler`` importieren, weiterlaufen.
"""

from ablage import Ablage as NASHandler  # noqa: F401
from ablage import protokoll  # noqa: F401
