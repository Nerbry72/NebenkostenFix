"""Praxisprobe (NK-187): jeder Mieter, jeder sinnvolle Zeitraum, alle Meldungen.

Die Suite prueft Regeln, ein echter Bestand prueft Lagen. Das Werkzeug nimmt
eine Datenbank, arbeitet auf einer Kopie (die Quelle wird nur lesend
geoeffnet) und probiert fuer jeden Mieter:

- den Zeitraumvorschlag (NK-186) mit Gruenden,
- jedes vergangene Kalenderjahr und jedes Jahr im Rhythmus des Hauses
  (abgeleitet aus den bestehenden Abrechnungen),
- jede bestehende Abrechnung noch einmal, bei einem Auszug die Mietzeit.

Je Zeitraum: die Kacheln der Vorpruefung, die Rechnung mit ihren Meldungen,
die geschaetzten Zaehlerstaende, ob beide PDFs entstehen und wie viele Seiten
sie haben. Zum Schluss die Kostenerhaltung je Haus und Jahr: Mieteranteile
plus Vermieteranteil ergeben den Rechnungsbetrag im Jahr.

Aufruf (nur lokal, nicht in der CI -- der Bestand ist echt):

    python scripts/praxisprobe.py DB [--code CHECKOUT] [--aus DATEI.md]

``--code`` ist der Stand, gegen den geprobt wird (Vorgabe: dieses Repo);
so laeuft dieselbe Probe gegen einen Fix-Branch und gegen ``main``. Namen
werden in der Ausgabe ersetzt (Mieter N, Haus A, Wohnung N), Betraege nicht:
die Ausgabe gehoert in einen git-ignorierten Ordner.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
EIN_TAG = timedelta(days=1)


def _d(tag) -> str:
    return date.fromisoformat(str(tag)[:10]).strftime('%d.%m.%Y')


def _geld(wert):
    return None if wert is None else round(float(wert), 2)


def kopiere(quelle: Path, ziel: Path) -> None:
    """Kopie ueber die Backup-Schnittstelle; die Quelle nur lesend."""
    src = sqlite3.connect(f'file:{quelle}?mode=ro', uri=True)
    dst = sqlite3.connect(ziel)
    src.backup(dst)
    src.close()
    dst.close()


class Anonym:
    """Ersetzt Namen aus dem Bestand durch Platzhalter."""

    def __init__(self, erlaubt=()):
        from nebenkostenfix.models import (Apartment, CostInvoice, Meter,
                                           Property, Provider, Tenant)
        ersatz = {}
        for i, t in enumerate(Tenant.query.order_by(Tenant.id), 1):
            klar = next((e for e in erlaubt if e in t.name), None)
            if klar:
                # Der ganze Name wird zum erlaubten; sonst ersetzt ein
                # gleicher Vorname eines anderen Mieters die Haelfte.
                ersatz[t.name] = klar
                continue
            ersatz[t.name] = f'Mieter {i}'
            for teil in t.name.split():
                ersatz.setdefault(teil, f'Mieter {i}')
        for i, p in enumerate(Property.query.order_by(Property.id)):
            ersatz[p.name] = f'Haus {chr(65 + i)}'
        for i, a in enumerate(Apartment.query.order_by(Apartment.id), 1):
            ersatz[a.name] = f'Wohnung {i}'
        for i, v in enumerate(Provider.query.order_by(Provider.id), 1):
            ersatz[v.name] = f'Versorger {i}'
        for i, z in enumerate(Meter.query.order_by(Meter.id), 1):
            ersatz[z.meter_number] = f'Zähler {i}'
        for r in CostInvoice.query.filter(CostInvoice.invoice_number.isnot(None)):
            ersatz[r.invoice_number] = f'Rechnung {r.id}'
        # Kurze Namen ("EG", "1") verraten nichts und wuerden Text zerlegen.
        self.ersatz = {k: v for k, v in ersatz.items() if k and len(k.strip()) >= 3}
        muster = '|'.join(re.escape(k) for k in sorted(self.ersatz, key=len, reverse=True))
        self.muster = re.compile(rf'(?<!\w)(?:{muster})(?!\w)') if muster else None

    def text(self, text: str) -> str:
        if not self.muster:
            return text
        return self.muster.sub(lambda m: self.ersatz[m.group(0)], text)


def anmelden(app):
    """Ein Probekonto in der Kopie, ein angemeldeter Testclient."""
    from nebenkostenfix.models import User, db

    passwort = secrets.token_urlsafe(16)
    konto = User(username='praxisprobe')
    konto.set_password(passwort)
    db.session.add(konto)
    db.session.commit()
    client = app.test_client()
    antwort = client.post('/login', json={'username': 'praxisprobe', 'password': passwort})
    if antwort.status_code != 200:
        raise SystemExit(f'Anmeldung in der Kopie misslungen: {antwort.status_code}')
    return client


def _rhythmen(haus_id: int) -> set:
    """Jahresbeginne des Hauses: der 01.01. und jeder Beginn einer Abrechnung."""
    from nebenkostenfix.models import Apartment, Tenant, TenantBillingReport
    beginne = (TenantBillingReport.query.join(Tenant).join(Apartment)
               .filter(Apartment.property_id == haus_id)
               .with_entities(TenantBillingReport.start_date).all())
    return {(1, 1)} | {(b.month, b.day) for (b,) in beginne}


def _zeitraeume(t, vorschlag: dict | None, heute: date) -> dict:
    """``{(beginn, ende): [marke, ...]}``; Jahresmarken tragen ihr ganzes Jahr."""
    from nebenkostenfix.models import TenantBillingReport

    z = defaultdict(list)

    def dazu(beginn, ende, marke):
        beginn = max(beginn, t.move_in_date)
        ende = min(ende, t.move_out_date or ende)
        if beginn <= ende <= heute:
            z[(beginn, ende)].append(marke)

    if vorschlag and vorschlag.get('beginn'):
        z[(date.fromisoformat(vorschlag['beginn']),
           date.fromisoformat(vorschlag['ende']))].append({'art': 'Vorschlag'})
    for monat, tag in sorted(_rhythmen(t.apartment.property_id)):
        for jahr in range(t.move_in_date.year - 1, heute.year + 1):
            beginn = date(jahr, monat, tag)
            ende = date(jahr + 1, monat, tag) - EIN_TAG
            art = 'Kalenderjahr' if (monat, tag) == (1, 1) else 'Rhythmus'
            dazu(beginn, ende, {'art': art, 'jahr': [beginn.isoformat(), ende.isoformat()]})
    for r in TenantBillingReport.query.filter_by(tenant_id=t.id):
        dazu(r.start_date, r.end_date, {'art': 'bestehende Abrechnung'})
    if t.move_out_date:
        dazu(t.move_in_date, t.move_out_date, {'art': 'Mietzeit'})
    return dict(sorted(z.items()))


def _pdf_seiten(daten: dict, anschreiben) -> dict:
    from nebenkostenfix.pdf_generator import PDFGenerator

    # Aeltere Staende kennen nicht jeden Parameter (``vorbehalt`` erst nach 0.10.5).
    kennt = inspect.signature(PDFGenerator.generate).parameters
    extra = {k: v for k, v in (('co2_ausweis', daten.get('co2')),
                               ('landlord_share', daten.get('landlord_share')),
                               ('anschreiben', anschreiben),
                               ('vorbehalt', daten.get('vorbehalt'))) if k in kennt}
    seiten = {}
    for art, detailliert in (('einfach', False), ('detailliert', True)):
        try:
            roh = PDFGenerator(
                property_name=daten['property'], apartment_name=daten['apartment'],
                tenant_name=daten['tenant_name'], start_date=daten['start_date'],
                end_date=daten['end_date'], detailliert=detailliert,
            ).generate(
                daten['line_items'], daten['total_amount'], daten.get('prepaid_amount'), **extra)
            seiten[art] = len(re.findall(rb'/Type\s*/Page(?!s)', roh))
        except Exception as fehler:  # noqa: BLE001 -- die Probe sammelt, sie bricht nicht ab
            seiten[art] = f'Fehler: {type(fehler).__name__}: {fehler}'
    return seiten


def _probe(client, t, beginn: date, ende: date, marken: list) -> dict:
    from nebenkostenfix.billing_engine import BillingEngine
    from nebenkostenfix.rechenkern import BillingDataError

    auftrag = {'tenant_id': t.id, 'start_date': beginn.isoformat(), 'end_date': ende.isoformat()}
    erg = {'beginn': beginn.isoformat(), 'ende': ende.isoformat(), 'marken': marken}

    vor = client.post('/api/billing/preflight', json=auftrag)
    if vor.status_code == 200:
        kacheln = vor.get_json()['checks']
        erg['vorpruefung'] = [
            {'art': 'Sperre' if k.get('blocking') else k['status'],
             'kategorie': k.get('category'),
             # Zaehlerkacheln haben keinen Text; die Oberflaeche zeigt sie zugeklappt so.
             'text': k.get('message') or (
                 f"{k.get('meter_type')}: Keine ausreichenden Daten" if k['status'] == 'no_data'
                 else f"{k.get('meter_type')}: Abweichung Start {k.get('start_offset_days')}T, "
                      f"Ende {k.get('end_offset_days')}T")} for k in kacheln]
        erg['schaetzungen'] = [
            {'kategorie': k.get('category'), 'zaehler': k.get('meter_type'),
             'stuetzen': [k.get('r_start'), k.get('r_end')],
             'abstand_tage': [k.get('start_offset_days'), k.get('end_offset_days')]}
            for k in kacheln if k.get('is_interpolated')]
    else:
        erg['vorpruefung_fehler'] = (vor.get_json(silent=True) or {}).get('error', vor.status_code)

    # Die Meldungen so, wie die Vorschau sie zeigt (mit Frist und Ueberlaenge).
    gen = client.post('/api/billing/generate', json=auftrag)
    antwort = gen.get_json(silent=True) or {}
    if gen.status_code == 200:
        erg['meldungen'] = antwort.get('warnings', [])
    elif 'überschneidet' in str(antwort.get('error', '')):
        erg['ueberschneidung'] = True
    else:
        erg['fehler'] = antwort.get('error', gen.status_code)
        return erg

    # Rechnen und PDF wie bei der Festsetzung, aber ohne sie zu speichern.
    try:
        daten = BillingEngine(t.id, beginn.isoformat(), ende.isoformat()).calculate_bill()
    except BillingDataError as fehler:
        erg['fehler'] = str(fehler)
        return erg
    erg.setdefault('meldungen', daten.get('warnings', []))
    lastschrift = (daten.get('landlord_share') or {}).get('positions', [])
    erg['rechnung'] = {
        'summe': _geld(daten['total_amount']),
        'vorauszahlung': _geld(daten.get('prepaid_amount')),
        'saldo': _geld(daten.get('balance')),
        'zeilen': [{'kostenart': z.get('category'), 'rechnung': z.get('invoice_id'),
                    'zeitraum': z.get('period'), 'anteilig': _geld(z.get('prorated_amount')),
                    'mieter': _geld(z.get('tenant_cost'))} for z in daten['line_items']],
        'vermieter': [{'rechnung': p.get('invoice_id'), 'kostenart': p.get('category'),
                       'betrag': _geld(p.get('amount'))} for p in lastschrift],
    }
    anschreiben = getattr(sys.modules.get('app'), '_anschreiben_fuer', None)
    erg['pdf'] = _pdf_seiten(daten, anschreiben(t, daten) if anschreiben else None)
    return erg


def _erhaltung(mieter: list) -> list:
    """Je Haus und Jahr: Soll (Rechnungsbetrag anteilig) gegen Mieter plus Vermieter."""
    from nebenkostenfix.models import Apartment, CostInvoice, db

    gruppen = defaultdict(list)
    beteiligt = defaultdict(set)
    for i, m in enumerate(mieter):
        for p in m['proben']:
            for marke in p['marken']:
                if 'jahr' in marke and 'rechnung' in p:
                    gruppen[(m['haus_id'], tuple(marke['jahr']))].append(p['rechnung'])
                    beteiligt[(m['haus_id'], tuple(marke['jahr']))].add(i)

    def vollstaendig(haus_id, von, bis):
        # Alle Mieter, die im Jahr im Haus wohnten, haben eine Probe beigetragen;
        # sonst fehlt ein Mieteranteil und die Differenz sagt nichts.
        noetig = {i for i, m in enumerate(mieter) if m['haus_id'] == haus_id
                  and m['einzug'] <= bis and (m['auszug'] or bis) >= von}
        return noetig <= beteiligt[(haus_id, (von, bis))]
    befunde = []
    for (haus_id, (von, bis)), rechnungen in sorted(gruppen.items()):
        komplett = vollstaendig(haus_id, von, bis)
        von, bis = date.fromisoformat(von), date.fromisoformat(bis)
        mieter_je = Counter()
        vermieter_je = defaultdict(float)
        for r in rechnungen:
            for z in r['zeilen']:
                mieter_je[z['rechnung']] += z['mieter'] or 0
            # Der Vermieteranteil steht in jeder Abrechnung des Hauses; er
            # zaehlt einmal (der groesste, falls die Zeitraeume abweichen).
            # Eine Rechnung kann mehrere Positionen haben (F-120/F-121:
            # Allgemeinanteil und Eigenverbrauch), die innerhalb einer
            # Abrechnung zusammengehoeren.
            je_abrechnung = defaultdict(float)
            for p in r['vermieter']:
                je_abrechnung[p['rechnung']] += p['betrag'] or 0
            for inv_id, betrag in je_abrechnung.items():
                vermieter_je[inv_id] = max(vermieter_je[inv_id], betrag)
        for inv in CostInvoice.query.filter(CostInvoice.property_id == haus_id,
                                            CostInvoice.start_date <= bis,
                                            CostInvoice.end_date >= von):
            tage = (inv.end_date - inv.start_date).days + 1
            drin = (min(bis, inv.end_date) - max(von, inv.start_date)).days + 1
            soll = round(float(inv.amount) * drin / tage, 2)
            ist = round(mieter_je[inv.id] + vermieter_je[inv.id], 2)
            befunde.append({
                'haus_id': haus_id, 'jahr': [von.isoformat(), bis.isoformat()],
                'rechnung': inv.id, 'kostenart': inv.category.name,
                'rechnungszeitraum': [inv.start_date.isoformat(), inv.end_date.isoformat()],
                'wohnung': inv.apartment_id and db.session.get(Apartment, inv.apartment_id).name,
                'soll': soll, 'mieter': round(mieter_je[inv.id], 2),
                'vermieter': round(vermieter_je[inv.id], 2), 'differenz': round(soll - ist, 2),
                # Pruefbar nur, wenn alle Mieter beitragen und die Rechnung ganz
                # im Zeitraum liegt: seit F-128 gilt der Vermieteranteil dem
                # Zeitraum, bei Heizung und CO2 aber noch der ganzen Rechnung.
                'abrechnungen': len(rechnungen), 'vollstaendig': komplett and drin == tage})
    return befunde


def katalog(client, heute: date) -> dict:
    """Der ganze Fallkatalog; braucht App-Kontext und einen angemeldeten Client."""
    from nebenkostenfix.models import Tenant, TenantBillingReport

    mieter = []
    for t in Tenant.query.order_by(Tenant.id):
        antwort = client.get(f'/api/tenants/{t.id}/zeitraumvorschlag')
        vorschlag = antwort.get_json() if antwort.status_code == 200 else None
        berichte = TenantBillingReport.query.filter_by(tenant_id=t.id).order_by(
            TenantBillingReport.start_date)
        mieter.append({
            'name': t.name, 'haus_id': t.apartment.property_id,
            'haus': t.apartment.property.name, 'wohnung': t.apartment.name,
            'einzug': t.move_in_date.isoformat(),
            'auszug': t.move_out_date and t.move_out_date.isoformat(),
            'abgerechnet_bis': t.last_billed_until and t.last_billed_until.isoformat(),
            'abrechnungen': [[r.start_date.isoformat(), r.end_date.isoformat()] for r in berichte],
            'vorschlag': vorschlag,
            'proben': [_probe(client, t, b, e, marken)
                       for (b, e), marken in _zeitraeume(t, vorschlag, heute).items()],
        })
    return {'heute': heute.isoformat(), 'mieter': mieter, 'erhaltung': _erhaltung(mieter)}


def _marken(marken: list) -> str:
    return ', '.join(m['art'] + (f" {_d(m['jahr'][0])[-4:]}" if 'jahr' in m else '')
                     for m in marken)


def bericht(k: dict, stand: str) -> str:
    """Der Katalog als Markdown, eine Zeile je Mieter vorne, Einzelheiten danach."""
    zeilen = [f'# Praxisprobe {_d(k["heute"])} · Stand {stand}', '',
              'Nur lokal. Namen ersetzt (Mieter N, Haus X, Wohnung N), Beträge echt.', '',
              '## Übersicht', '',
              '| Mieter | Wohnung | Mietzeit | abgerechnet bis | Vorschlag | Proben '
              '| Sperren | Warnungen (Vorprüfung) | Meldungen (Rechnung, max.) | Fehler |',
              '|---|---|---|---|---|---|---|---|---|---|']
    for m in k['mieter']:
        v = m['vorschlag'] or {}
        vorschlag = (f"{_d(v['beginn'])}–{_d(v['ende'])}" if v.get('beginn')
                     else ('keiner' if m['vorschlag'] else 'kein Endpunkt'))
        proben = m['proben']
        arten = Counter(k['art'] for p in proben for k in p.get('vorpruefung', []))
        meldungen = max((len(p.get('meldungen', [])) for p in proben), default=0)
        fehler = sum(1 for p in proben if 'fehler' in p or 'vorpruefung_fehler' in p
                     or any(str(s).startswith('Fehler') for s in p.get('pdf', {}).values()))
        zeilen.append(
            f"| {m['name']} | {m['haus']} / {m['wohnung']} | {_d(m['einzug'])}–"
            f"{_d(m['auszug']) if m['auszug'] else 'heute'} | "
            f"{_d(m['abgerechnet_bis']) if m['abgerechnet_bis'] else '—'} | {vorschlag} | "
            f"{len(proben)} | {arten['Sperre']} | {arten['warning'] + arten['no_data']} | "
            f"{meldungen} | {fehler} |")

    for m in k['mieter']:
        zeilen += ['', f"## {m['name']} ({m['haus']} / {m['wohnung']})", '',
                   f"- Mietzeit {_d(m['einzug'])} bis "
                   f"{_d(m['auszug']) if m['auszug'] else 'heute'}; abgerechnet bis (Feld): "
                   f"{_d(m['abgerechnet_bis']) if m['abgerechnet_bis'] else '—'}",
                   '- Abrechnungen: ' + (', '.join(f'{_d(a)}–{_d(b)}' for a, b in m['abrechnungen'])
                                         or 'keine')]
        v = m['vorschlag']
        if v is None:
            zeilen.append('- Vorschlag: Endpunkt fehlt (Stand ohne NK-186)')
        else:
            zeilen.append('- Vorschlag: ' + (f"{_d(v['beginn'])}–{_d(v['ende'])}"
                                             if v.get('beginn') else 'keiner'))
            zeilen += [f'  - {g}' for g in v.get('gruende', [])]
        for p in m['proben']:
            zeilen += ['', f"### {_d(p['beginn'])}–{_d(p['ende'])} ({_marken(p['marken'])})", '']
            if 'vorpruefung_fehler' in p:
                zeilen.append(f"- Vorprüfung: Fehler {p['vorpruefung_fehler']}")
            kacheln = p.get('vorpruefung', [])
            arten = Counter(k['art'] for k in kacheln)
            zeilen.append(f'- Vorprüfung: {len(kacheln)} Kacheln ('
                          + ', '.join(f'{n}× {a}' for a, n in sorted(arten.items())) + ')')
            zeilen += [f"  - [{k['art']}] {k['kategorie']}: {k['text']}" for k in kacheln
                       if k['art'] not in ('excellent', 'good', 'acceptable')]
            for s in p.get('schaetzungen', []):
                zeilen.append(f"- Geschätzt: {s['kategorie']} ({s['zaehler']}), Stützstellen "
                              f"{s['stuetzen'][0]} / {s['stuetzen'][1]}, Abstand "
                              f"{s['abstand_tage'][0]} / {s['abstand_tage'][1]} Tage")
            if p.get('ueberschneidung'):
                zeilen.append('- Erzeugen: abgelehnt, überschneidet eine bestehende Abrechnung '
                              '(unten direkt gerechnet)')
            if 'fehler' in p:
                zeilen.append(f"- **Fehler:** {p['fehler']}")
                continue
            r = p['rechnung']
            zeilen.append(f"- Rechnung: Summe {r['summe']:.2f}, Vorauszahlung "
                          f"{r['vorauszahlung'] or 0:.2f}, Saldo {r['saldo'] or 0:.2f}")
            zeilen += [f"  - {z['kostenart']} ({z['zeitraum']}): {z['mieter']} von "
                       f"{z['anteilig']}" for z in r['zeilen']]
            if r['vermieter']:
                zeilen.append('  - Vermieter: ' + ', '.join(
                    f"{p_['kostenart'] or p_['rechnung']} {p_['betrag']}" for p_ in r['vermieter']))
            zeilen.append(f"- Meldungen der Rechnung: {len(p['meldungen'])}")
            zeilen += [f'  - {t}' for t in p['meldungen']]
            zeilen.append('- PDF: ' + ', '.join(f'{a} {s}' for a, s in p['pdf'].items()))

    zeilen += ['', '## Kostenerhaltung je Haus und Jahr', '',
               'Soll = Rechnungsbetrag anteilig im Jahr; Mieter = Summe der Mieteranteile '
               'aller Abrechnungen des Jahres; Vermieter = Leerstand und Eigennutzung. '
               'Fett nur, wenn alle Mieter des Jahres beigetragen haben; sonst „(teilweise)“.', '',
               '| Haus | Jahr | Kostenart | Rechnungszeitraum | Wohnung | Soll | Mieter '
               '| Vermieter | Differenz | Abr. |', '|---|---|---|---|---|---|---|---|---|---|']
    namen = {m['haus_id']: m['haus'] for m in k['mieter']}
    for b in k['erhaltung']:
        markiert = '**' if abs(b['differenz']) > 0.01 and b['vollstaendig'] else ''
        zeilen.append(
            f"| {namen[b['haus_id']]} | {_d(b['jahr'][0])}–{_d(b['jahr'][1])} | "
            f"{b['kostenart']} | {_d(b['rechnungszeitraum'][0])}–{_d(b['rechnungszeitraum'][1])} | "
            f"{b['wohnung'] or 'Haus'} | {b['soll']:.2f} | {b['mieter']:.2f} | "
            f"{b['vermieter']:.2f} | {markiert}{b['differenz']:.2f}{markiert} | "
            f"{b['abrechnungen']}{'' if b['vollstaendig'] else ' (nicht prüfbar)'} |")
    return '\n'.join(zeilen) + '\n'


def main(argv=None) -> int:
    auf = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    auf.add_argument('db', type=Path, help='Datenbank (wird nur lesend geöffnet)')
    auf.add_argument('--code', type=Path, default=WURZEL, help='Stand, gegen den geprobt wird')
    auf.add_argument('--aus', type=Path, help='Markdown-Datei (Vorgabe: Ausgabe auf stdout)')
    auf.add_argument('--json', type=Path, help='zusätzlich der anonymisierte Katalog als JSON')
    auf.add_argument('--klarname', action='append', default=[],
                     help='Mietername, der im Klartext bleiben darf (mehrfach möglich)')
    a = auf.parse_args(argv)

    # Die Kopie traegt Namen und Zugangsdaten: sie verschwindet mit dem Lauf.
    with tempfile.TemporaryDirectory(prefix='praxisprobe-', ignore_cleanup_errors=True) as tmp:
        return _lauf(a, Path(tmp))


def _lauf(a, ordner: Path) -> int:
    kopiere(a.db.resolve(), ordner / 'nebenkosten.db')
    os.environ.update(DATA_DIR=str(ordner), DATABASE_URL=f'sqlite:///{ordner}/nebenkosten.db',
                      SECRET_KEY=secrets.token_hex(32), LOGIN_VERZOEGERUNG_S='0')
    for alt in ('ENABLE_DEBUG_RESET', 'NAS_MOUNT_PATH', 'LOCAL_PDF_PATH', 'LOCAL_TEMP_PATH'):
        os.environ.pop(alt, None)
    code = a.code.resolve()
    sys.path.insert(0, str(code))
    stand = subprocess.run(['git', '-C', str(code), 'describe', '--tags', '--always', '--dirty'],
                           capture_output=True, text=True).stdout.strip() or 'unbekannt'
    import app as anwendung
    with anwendung.app.app_context():
        k = katalog(anmelden(anwendung.app), date.today())
        anonym = Anonym(a.klarname)
        text = anonym.text(bericht(k, stand))
        if a.json:
            a.json.write_text(anonym.text(json.dumps(k, ensure_ascii=False, indent=1)),
                              encoding='utf-8')
        anwendung.db.engine.dispose()  # sonst haelt Windows die Kopie fest
    if a.aus:
        a.aus.parent.mkdir(parents=True, exist_ok=True)
        a.aus.write_text(text, encoding='utf-8')
        print(f'{a.aus} ({len(k["mieter"])} Mieter, '
              f'{sum(len(m["proben"]) for m in k["mieter"])} Zeiträume)')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
