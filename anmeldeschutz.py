"""Schutz der Anmeldung vor Durchprobieren (NK-128, F-56).

Bis NK-128 liess sich ein Passwort im LAN beliebig oft probieren. Jetzt
zaehlt die Anwendung Fehlversuche je Konto und je IP-Adresse:

    - Jeder Fehlversuch kostet eine kurze, wachsende Wartezeit
      (``VERZOEGERUNG_S`` je bisherigem Fehlversuch, hoechstens 2 s).
    - Nach ``GRENZE_KONTO`` Fehlversuchen fuer ein Konto oder
      ``GRENZE_IP`` von einer Adresse binnen ``FENSTER_S`` ist fuer
      ``SPERRE_S`` Schluss: die Anmeldung antwortet mit 429 und sagt, wie
      lange noch. Die Sperre steht im Protokoll.
    - Eine erfolgreiche Anmeldung setzt die Zaehler von Konto und Adresse
      zurueck.

Gezaehlt wird auch fuer Konten, die es nicht gibt -- sonst verriete die
Sperre, welche Namen existieren. Die Grenze je Adresse ist hoeher als die
je Konto, weil sich ein Haushalt hinter einer Adresse die Anmeldung teilt.

Der Zaehlerstand liegt als ``anmeldeschutz.json`` im Datenordner unter einer
Dateisperre, damit mehrere Arbeiter (gunicorn) dieselben Zahlen sehen. Ohne
Datenordner (Postgres im Entwicklerstapel) bleibt er im Prozess.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

from dateisperre import dateisperre

protokoll = logging.getLogger(__name__)

FENSTER_S = 15 * 60
SPERRE_S = 15 * 60
GRENZE_KONTO = 5
GRENZE_IP = 20
DATEINAME = 'anmeldeschutz.json'


def verzoegerung_s() -> float:
    """Wartezeit je bisherigem Fehlversuch; 0 schaltet sie ab (Tests)."""
    roh = (os.environ.get('LOGIN_VERZOEGERUNG_S') or '').strip()
    try:
        wert = float(roh) if roh else 0.25
    except ValueError:
        wert = 0.25
    return max(0.0, wert)


def wartezeit(fehlversuche: int) -> float:
    return min(2.0, verzoegerung_s() * max(0, fehlversuche))


_speicher: dict = {}
_speicher_sperre = threading.Lock()


class _Ablage:
    """Zaehlerstand lesen und schreiben, Datei oder Speicher."""

    def __init__(self, ordner: str | None):
        self.pfad = os.path.join(ordner, DATEINAME) if ordner else None

    def __enter__(self):
        if self.pfad is None:
            _speicher_sperre.acquire()
        else:
            self._sperre = dateisperre(self.pfad + '.lock')
            self._sperre.__enter__()
        return self

    def __exit__(self, *exc):
        if self.pfad is None:
            _speicher_sperre.release()
        else:
            self._sperre.__exit__(*exc)
        return False

    def lesen(self) -> dict:
        if self.pfad is None:
            return dict(_speicher)
        try:
            with open(self.pfad, encoding='utf-8') as datei:
                daten = json.load(datei)
            return daten if isinstance(daten, dict) else {}
        except (OSError, ValueError):
            return {}

    def schreiben(self, daten: dict) -> None:
        jetzt = time.time()
        # Alte Eintraege fallen heraus, die Datei waechst nicht endlos.
        daten = {k: v for k, v in daten.items()
                 if v.get('gesperrt_bis', 0) > jetzt
                 or v.get('erster', 0) + FENSTER_S > jetzt}
        if self.pfad is None:
            _speicher.clear()
            _speicher.update(daten)
            return
        temp = f'{self.pfad}.{os.getpid()}.tmp'
        kennung = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(kennung, 'w', encoding='utf-8') as datei:
            json.dump(daten, datei)
        os.replace(temp, self.pfad)


def _schluessel(konto: str, adresse: str | None) -> list[tuple[str, int]]:
    return [(f'konto:{konto.strip().lower()}', GRENZE_KONTO),
            (f'ip:{adresse or "?"}', GRENZE_IP)]


def gesperrt_fuer(ordner, konto: str, adresse: str | None) -> int:
    """Restsekunden der Sperre, 0 wenn frei."""
    jetzt = time.time()
    with _Ablage(ordner) as ablage:
        daten = ablage.lesen()
    rest = 0
    for schluessel, _ in _schluessel(konto, adresse):
        bis = daten.get(schluessel, {}).get('gesperrt_bis', 0)
        rest = max(rest, int(bis - jetzt + 0.999))
    return max(0, rest)


def fehlversuch(ordner, konto: str, adresse: str | None) -> int:
    """Zaehlt einen Fehlversuch; liefert die bisherige Zahl fuers Konto."""
    jetzt = time.time()
    anzahl_konto = 0
    with _Ablage(ordner) as ablage:
        daten = ablage.lesen()
        for schluessel, grenze in _schluessel(konto, adresse):
            eintrag = daten.get(schluessel) or {}
            if eintrag.get('erster', 0) + FENSTER_S <= jetzt:
                eintrag = {'fehl': 0, 'erster': jetzt}
            eintrag['fehl'] = int(eintrag.get('fehl', 0)) + 1
            if eintrag['fehl'] >= grenze and \
                    eintrag.get('gesperrt_bis', 0) <= jetzt:
                eintrag['gesperrt_bis'] = jetzt + SPERRE_S
                protokoll.warning(
                    'Anmeldung gesperrt für %d Minuten: %s nach %d '
                    'Fehlversuchen (NK-128).', SPERRE_S // 60, schluessel,
                    eintrag['fehl'])
            daten[schluessel] = eintrag
            if schluessel.startswith('konto:'):
                anzahl_konto = eintrag['fehl']
        ablage.schreiben(daten)
    return anzahl_konto


def erfolg(ordner, konto: str, adresse: str | None) -> None:
    with _Ablage(ordner) as ablage:
        daten = ablage.lesen()
        for schluessel, _ in _schluessel(konto, adresse):
            daten.pop(schluessel, None)
        ablage.schreiben(daten)


def zuruecksetzen(ordner=None) -> None:
    """Fuer Tests und `flask users passwd`: alle Zaehler weg."""
    with _Ablage(ordner) as ablage:
        ablage.schreiben({})
