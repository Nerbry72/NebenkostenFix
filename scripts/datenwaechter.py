"""Datenwaechter (NK-187): kein Wert aus dem echten Bestand in einem Diff.

Die Praxisprobe stellt Lagen aus dem Bestand mit erfundenen Daten nach.
Dabei rutscht leicht ein echter Wert in einen Test: ein Name, ein krummer
Betrag, ein Zaehlerstand, ein Ablesetag. Der Waechter liest diese Werte aus
einer Kopie der Datenbank und sucht sie in den hinzugefuegten Zeilen eines
Diffs. Jeder Treffer muss begruendet oder ersetzt werden.

Aufruf (nur lokal, die Datenbank liegt nicht im Repo):

    python scripts/datenwaechter.py DB [--bereich A..B]

Ohne ``--bereich`` prueft er, was fuer den naechsten Commit vorgemerkt ist.
Runde Betraege, ganze Zaehlerstaende unter 1000, Monatsanfaenge und
Monatsenden prueft er nicht: die stehen in jedem erfundenen Fall.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Woerter, die in Namen stehen, aber nichts verraten.
ALLTAG = {'wohnung', 'haus', 'straße', 'strasse', 'weg', 'platz', 'erdgeschoss',
          'obergeschoss', 'dachgeschoss', 'untergeschoss', 'keller', 'links', 'rechts',
          'mitte', 'zähler', 'zaehler', 'stadtwerke', 'gmbh', 'versicherung',
          'wasser', 'strom', 'heizung', 'garage', 'einheit', 'mieter', 'vermieter', 'admin'}

ZAHL = re.compile(r'(?<![\w.,])\d{1,7}(?:[.,]\d{1,3})?(?![\w]|[.,]\d)')
TAG = re.compile(r'(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\.(\d{1,2})\.(\d{4})'
                 r'|date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)')
WORT = re.compile(r'[^\W\d_]{4,}')


def _zahl(text) -> Decimal | None:
    try:
        return Decimal(str(text).replace(',', '.'))
    except InvalidOperation:
        return None


def _stichtag(tag: date) -> bool:
    """Ein Tag, der nur im Bestand vorkommt: weder Monatsanfang noch -ende."""
    return tag.day != 1 and (tag + timedelta(days=1)).day != 1


def werte(db: sqlite3.Connection) -> dict[str, set]:
    """Namen, krumme Betraege, Zaehlerstaende und Stichtage aus dem Bestand."""
    def spalte(sql):
        return [r[0] for r in db.execute(sql) if r[0] not in (None, '')]

    namen = set()
    for text in spalte('SELECT name FROM tenants UNION ALL SELECT name FROM properties '
                       'UNION ALL SELECT name FROM apartments UNION ALL SELECT name FROM providers '
                       'UNION ALL SELECT name FROM vermieterdaten UNION ALL SELECT username FROM users '
                       'UNION ALL SELECT meter_number FROM meters '
                       'UNION ALL SELECT invoice_number FROM cost_invoices'):
        namen |= {w.casefold() for w in WORT.findall(str(text))} - ALLTAG
        if any(c.isdigit() for c in str(text)) and len(str(text)) >= 5:
            namen.add(str(text).casefold())  # Zaehler- und Rechnungsnummern ganz
    # grundpreis gibt es erst seit e3c5a7f9b1d2; aeltere Kopien haben ihn nicht.
    grundpreis = any(r[1] == 'grundpreis' for r in db.execute('PRAGMA table_info(cost_invoices)'))
    betraege = {_zahl(b).quantize(Decimal('0.01')) for b in spalte(
        'SELECT amount FROM cost_invoices UNION ALL SELECT co2_kosten FROM cost_invoices '
        + ('UNION ALL SELECT grundpreis FROM cost_invoices ' if grundpreis else '')
        + 'UNION ALL SELECT amount FROM payments')}
    betraege = {b for b in betraege if b % 1}
    staende = {Decimal(repr(float(s))).normalize() for s in spalte(
        'SELECT value FROM meter_readings UNION ALL SELECT value_nt FROM meter_readings')}
    # Dreistellige ganze Zahlen stehen in jedem Test; erst krumme oder grosse verraten etwas.
    staende = {s for s in staende if s % 1 or s >= 1000}
    tage = {date.fromisoformat(str(t)[:10]) for t in spalte(
        'SELECT move_in_date FROM tenants UNION ALL SELECT move_out_date FROM tenants '
        'UNION ALL SELECT reading_date FROM meter_readings '
        'UNION ALL SELECT start_date FROM cost_invoices UNION ALL SELECT end_date FROM cost_invoices '
        'UNION ALL SELECT rechnungsdatum FROM cost_invoices UNION ALL SELECT payment_date FROM payments')}
    return {'namen': namen, 'betraege': betraege, 'staende': staende,
            'tage': {t for t in tage if _stichtag(t)}}


def treffer(bestand: dict[str, set], zeilen: list[str]) -> list[tuple[int, str, str]]:
    """(Zeilennummer, Art, Wert) fuer jeden Wert aus dem Bestand in den Zeilen."""
    gefunden = []
    for nr, zeile in enumerate(zeilen, 1):
        klein = zeile.casefold()
        woerter = {w.casefold() for w in WORT.findall(zeile)}
        for name in sorted(bestand['namen']):
            ganz = ' ' in name or any(c.isdigit() for c in name)
            if name in klein if ganz else name in woerter:
                gefunden.append((nr, 'Name', name))
        for text in ZAHL.findall(zeile):
            zahl = _zahl(text)
            if re.search(r'[.,]\d\d$', text) and zahl in bestand['betraege']:
                gefunden.append((nr, 'Betrag', text))
            if zahl.normalize() in bestand['staende']:
                gefunden.append((nr, 'Zählerstand', text))
        for m in TAG.finditer(zeile):
            j, mo, t = ((m[1], m[2], m[3]) if m[1] else (m[6], m[5], m[4]) if m[4]
                        else (m[7], m[8], m[9]))
            try:
                tag = date(int(j), int(mo), int(t))
            except ValueError:
                continue
            if tag in bestand['tage']:
                gefunden.append((nr, 'Datum', m[0]))
    return gefunden


def diff_zeilen(bereich: str | None) -> list[str]:
    """Die hinzugefuegten Zeilen, als 'datei: text'."""
    befehl = ['git', 'diff', '-U0', '--no-color'] + ([bereich] if bereich else ['--cached'])
    datei, zeilen = '?', []
    for z in subprocess.run(befehl, capture_output=True, text=True, check=True).stdout.splitlines():
        if z.startswith('+++ '):
            datei = z[6:] if z.startswith('+++ b/') else z[4:]
        elif z.startswith('+'):
            zeilen.append(f'{datei}: {z[1:]}')
    return zeilen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('db', type=Path)
    ap.add_argument('--bereich', help='Commit-Bereich wie main..HEAD; ohne: vorgemerkte Änderungen')
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='datenwaechter-') as ordner:
        kopie = Path(ordner) / 'kopie.db'
        src = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
        dst = sqlite3.connect(kopie)
        src.backup(dst)
        src.close()
        bestand = werte(dst)
        dst.close()
    zeilen = diff_zeilen(args.bereich)
    funde = treffer(bestand, zeilen)
    for nr, art, wert in funde:
        # Der Wert selbst bleibt aus der Ausgabe: sie landet gern in einem Protokoll.
        print(f'{art} aus dem Bestand: {zeilen[nr - 1].split(": ", 1)[0]} '
              f'(hinzugefügte Zeile {nr}, {len(wert)} Zeichen)')
    print(f'{len(zeilen)} Zeilen geprüft, {len(funde)} Treffer.')
    return 1 if funde else 0


if __name__ == '__main__':
    sys.exit(main())
