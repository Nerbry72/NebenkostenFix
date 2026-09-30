"""Ein Anwendungsstart in einem Baum, wie ihn das Abbild hat (NK-040).

Laeuft als eigener Prozess, nicht als Test: geprueft werden soll, was beim
*Import* von ``app`` passiert, und der ist im Testprozess laengst geschehen.
Der Baum, in dem dieses Skript liegt, wird von ``test_produktionsbuild.py``
aus Symlinks gebaut -- einmal mit ``debug_routen.py`` darin und einmal ohne.

Ausgegeben wird eine Zeile JSON auf stdout.
"""

from __future__ import annotations

import json
import sys

import app as app_modul

regeln = list(app_modul.app.url_map.iter_rules())
sys.stdout.write(json.dumps({
    'debug_regeln': sorted(r.rule for r in regeln if r.rule.startswith('/api/debug/')),
    'hat_reset_db': any(r.endpoint == 'reset_db' for r in regeln),
    'anzahl_regeln': len(regeln),
    'modul_geladen': 'nebenkostenfix.debug_routen' in sys.modules,
}))
