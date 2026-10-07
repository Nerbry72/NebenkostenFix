"""Kleine Einstellungen der Anwendung, eine JSON-Datei im Datenordner.

Hier steht, was keine Tabelle braucht (NK-174, NK-175):

- ``haftung``: welche Fassung des Haftungshinweises bestätigt wurde und wann;
- ``updates_automatisch``: ob die App beim Start nach Updates sucht (ab Werk an);
- ``update_geprueft``: wann zuletzt gesucht wurde (nur für diesen Rechner);
- ``update_gefunden``: was diese Suche Neues gefunden hat, sonst ``None``;
- ``ohne_anmeldung`` (NK-197): ob die App ohne Anmeldung läuft. ``None``
  heißt „nie gewählt, es gilt die Vorgabe der Plattform“ (Windows ja,
  Docker nein), ``True``/``False`` heißt „ausdrücklich gewählt“.

``UEBERTRAGBAR`` wandert im ``.nkfix`` mit (D-96), die letzte Suche nicht --
auf dem neuen Rechner wird einfach wieder gesucht.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from nebenkostenfix.dateisperre import dateisperre

DATEINAME = 'app-einstellungen.json'
STANDARD = {'haftung': None, 'updates_automatisch': True, 'update_geprueft': None,
            'update_gefunden': None, 'ohne_anmeldung': None}
UEBERTRAGBAR = ('haftung', 'updates_automatisch', 'ohne_anmeldung')


def ohne_anmeldung_gewuenscht(stand: dict, desktop) -> bool:
    """Der wirksame Wert: ausdrücklich gewählt, sonst die Plattform-Vorgabe."""
    wert = stand.get('ohne_anmeldung')
    return wert if isinstance(wert, bool) else bool(desktop)


def uebertragbar(stand: dict, desktop, hat_konto: bool) -> dict:
    """Nur die Schluessel, die im Paket mitwandern; der Schalter wirksam --
    mit Konto also False (NK-206)."""
    wert = {k: stand.get(k) for k in UEBERTRAGBAR}
    wert['ohne_anmeldung'] = not hat_konto and ohne_anmeldung_gewuenscht(stand, desktop)
    return wert


def _datei(ordner: str | os.PathLike | None) -> Path:
    if ordner is None:
        from nebenkostenfix import datenordner
        ordner = datenordner.datenordner()
    return Path(ordner) / DATEINAME


def lesen(ordner: str | os.PathLike | None = None) -> dict:
    """Die Einstellungen; fehlende oder kaputte Datei heißt Werkseinstellung."""
    try:
        gelesen = json.loads(_datei(ordner).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        gelesen = {}
    if not isinstance(gelesen, dict):
        gelesen = {}
    return {**STANDARD, **{k: v for k, v in gelesen.items() if k in STANDARD
                           and (k != 'ohne_anmeldung' or v is None or isinstance(v, bool))}}


def schreiben(ordner: str | os.PathLike | None = None, **aenderungen) -> dict:
    unbekannt = set(aenderungen) - set(STANDARD)
    if unbekannt:
        raise KeyError(', '.join(sorted(unbekannt)))
    datei = _datei(ordner)
    datei.parent.mkdir(parents=True, exist_ok=True)
    # Am Stück: Suche beim Start, „Verstanden“ und der Schalter können
    # gleichzeitig kommen und überschrieben sich sonst gegenseitig.
    with dateisperre(str(datei) + '.lock'):
        stand = {**lesen(datei.parent), **aenderungen}
        temp = datei.with_name(datei.name + '.neu')
        temp.write_text(json.dumps(stand, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, datei)
    return stand
