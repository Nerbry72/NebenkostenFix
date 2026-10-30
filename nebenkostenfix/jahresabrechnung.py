"""Jahresabrechnungs-Assistent: der Stand eines Jahres (NK-160).

„Jahr abrechnen“ führt in fünf Schritten durch ein Abrechnungsjahr einer
Immobilie. Dieses Modul liefert nur den **Stand**, den die Schritte 1–3 und
5 zeigen; gerechnet und festgesetzt wird über die vorhandenen Routen
(``/api/billing/generate`` und ``/api/billing/finalize``) -- kein zweiter
Rechenweg.

    GET /api/jahresabrechnung?property_id=<id>&jahr=<JJJJ>

Das Jahr ist das Abrechnungsjahr des Hauses (D-114), das in ``jahr``
beginnt, beim 01.01. also das Kalenderjahr. Summen sind zeitanteilig: eine
Rechnung über die Jahresgrenze zählt mit den Tagen im Jahr (NK-242).

- **Kostenarten** (Schritt 2): jede übliche Kostenart und jede, zu der es im
  Jahr oder im Vorjahr Rechnungen gibt, mit Summe, Anzahl und Vorjahres-
  summe. ``fehlt`` heißt: im Vorjahr gab es eine, in diesem Jahr keine.
  ``aenderung`` ist die Änderung zum Vorjahr in ganzen Prozent (nur wenn
  beide Jahre Rechnungen haben), ``sprung`` heißt: mehr als 20 % (NK-228).
- **Ablesungen** (Schritt 3): je Zähler, ob ein Stand zum Stichtag
  (±31 Tage um das Jahresende) da ist, und je Mieterwechsel im Jahr, ob der
  Zähler der Wohnung am Wechseltag (±7 Tage) abgelesen wurde.
- **Mieter** (Schritte 4 und 5): wer im Jahr dort wohnte, mit dem
  Zeitraum, der abzurechnen ist, und der Abrechnung, falls es sie schon gibt.
- **Frist**: Ende der Abrechnungsfrist nach § 556 Abs. 3 BGB.
- **Prüfstand** (Schritt 5, NK-265): die Warnungen vor dem Festsetzen, je
  Befund ein Satz, was auffällt, einer, was zu tun ist, und das Ziel, an dem
  es sich beheben lässt. Er blockiert nichts.
- **Schätzquote** (im Prüfstand, § 9a HeizkostenV): je Heizungsanlage und
  Zweck, wie viel Fläche im Jahr ohne ordnungsgemäß erfassten Verbrauch ist;
  über 25 % sagt er, dass die App die dann verlangte Verteilung nur nach
  Fläche noch nicht kann.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from nebenkostenfix import betrkv

# Die Kostenarten, die in fast jedem Mietshaus anfallen: fehlen sie, fragt
# der Assistent nach, auch ohne Vorjahr.
UEBLICH = (
    'Grundsteuer',
    'Wasserversorgung',
    'Entwässerung',
    'Straßenreinigung und Müllbeseitigung',
    'Sach- und Haftpflichtversicherung',
    'Allgemeinstrom',
)
STICHTAG_TOLERANZ = timedelta(days=31)
WECHSEL_TOLERANZ = timedelta(days=7)
SPRUNG_PROZENT = 20
# Verbrauch schwankt stärker als Kosten (Wetter, Haushaltsgröße): erst die
# Hälfte mehr oder weniger als im Vorjahr ist einen Blick wert.
ZAEHLER_SPRUNG_PROZENT = 50


class StandFehler(Exception):
    """Immobilie oder Jahr taugen nicht; Meldung für Menschen."""


def _ueberlappt(beginn: date, ende: date, von: date, bis: date) -> bool:
    return beginn <= bis and ende >= von


def _anteil(rechnung, von: date, bis: date) -> Decimal:
    """Der Teil der Rechnung in ``von``–``bis``, nach Tagen wie im Rechenkern."""
    from nebenkostenfix.geld import dec, runde
    from nebenkostenfix.rechenkern import ueberschneidungstage

    beginn, ende = rechnung.start_date, rechnung.end_date
    return runde(dec(rechnung.amount) * dec(ueberschneidungstage(beginn, ende, von, bis))
                 / dec(ueberschneidungstage(beginn, ende, beginn, ende)))


def stand(property_id: int, jahr: int, heute: date | None = None) -> dict:
    from nebenkostenfix.frist import frist_status
    from nebenkostenfix.models import (CostCategory, CostInvoice, Meter, Property, Tenant,
                        TenantBillingReport)
    from nebenkostenfix.zeitraumvorschlag import jahresbeginn

    heute = heute or date.today()
    if not 2000 <= jahr <= heute.year:
        raise StandFehler(f'Das Jahr {jahr} lässt sich nicht abrechnen.')
    haus = Property.query.get(property_id)
    if haus is None:
        raise StandFehler('Diese Immobilie gibt es nicht.')
    # NK-242: das Abrechnungsjahr des Hauses (D-114), das im Jahr ``jahr`` beginnt.
    monat, tag, _ = jahresbeginn(haus)
    von, bis = date(jahr, monat, tag), date(jahr + 1, monat, tag) - timedelta(days=1)
    vorjahr_von, vorjahr_bis = date(jahr - 1, monat, tag), von - timedelta(days=1)

    # --- Schritt 2: Kostenarten --------------------------------------------------
    rechnungen = CostInvoice.query.filter_by(property_id=haus.id).all()
    kostenarten = []
    for kat in CostCategory.query.order_by(CostCategory.name).all():
        diese = [r for r in rechnungen if r.category_id == kat.id
                 and _ueberlappt(r.start_date, r.end_date, von, bis)]
        vorige = [r for r in rechnungen if r.category_id == kat.id
                  and _ueberlappt(r.start_date, r.end_date, vorjahr_von, vorjahr_bis)]
        if not (diese or vorige or kat.name in UEBLICH
                or betrkv.FRUEHERE_NAMEN.get(kat.name) in UEBLICH):
            continue
        summe = sum((_anteil(r, von, bis) for r in diese), start=Decimal(0))
        summe_vorjahr = sum((_anteil(r, vorjahr_von, vorjahr_bis) for r in vorige), start=Decimal(0))
        if diese:
            zustand = 'erfasst'
        elif vorige:
            zustand = 'fehlt'
        else:
            zustand = 'offen'
        aenderung = None
        if diese and vorige and summe_vorjahr > 0:
            # Gemessen wird an der gerundeten Zahl: markiert wird, was man sieht.
            aenderung = int((Decimal(summe - summe_vorjahr) * 100 / summe_vorjahr)
                            .quantize(Decimal('1'), ROUND_HALF_UP))
        kostenarten.append({
            'id': kat.id, 'name': kat.name, 'zustand': zustand,
            'anzahl': len(diese), 'summe': float(summe),
            'summe_vorjahr': float(summe_vorjahr) if vorige else None,
            'aenderung': aenderung,
            'sprung': aenderung is not None and abs(aenderung) > SPRUNG_PROZENT,
        })

    # --- Schritt 4/5: Mieter ------------------------------------------------------
    mieter = []
    wechsel = []
    for wohnung in sorted(haus.apartments, key=lambda w: w.name):
        for t in sorted(wohnung.tenants, key=lambda t: t.move_in_date):
            if t.gesperrt_bis is not None:
                continue
            ende = t.move_out_date or date.max
            if not _ueberlappt(t.move_in_date, ende, von, bis):
                continue
            beginn_z, ende_z = max(t.move_in_date, von), min(ende, bis)
            vorhanden = TenantBillingReport.query.filter(
                TenantBillingReport.tenant_id == t.id,
                TenantBillingReport.start_date <= ende_z,
                TenantBillingReport.end_date >= beginn_z).first()
            mieter.append({
                'id': t.id, 'name': t.name, 'wohnung': wohnung.name,
                'von': beginn_z.isoformat(), 'bis': ende_z.isoformat(),
                'abrechnung_id': vorhanden.id if vorhanden else None,
                'einfach': bool(vorhanden and vorhanden.document_path),
                'detailliert': bool(vorhanden and vorhanden.document_path_detailed),
                'zugestellt_am': (vorhanden.zugestellt_am.isoformat()
                                  if vorhanden and vorhanden.zugestellt_am else None),
            })
            for tag in (t.move_in_date, t.move_out_date):
                # Auszug am 30.06. und Einzug am 01.07. sind ein Wechsel (NK-265, D-116).
                if tag and von < tag <= bis and not any(
                        w == wohnung.id and abs(tag - frueher) <= timedelta(days=1)
                        for w, _, frueher in wechsel):
                    wechsel.append((wohnung.id, wohnung.name, tag))

    # --- Schritt 3: Ablesungen ----------------------------------------------------
    ablesungen = []
    alle_zaehler = Meter.query.filter_by(property_id=haus.id).order_by(Meter.meter_number).all()
    # NK-258: ein abgeloester Zaehler endet mit dem Wechsel, sein Nachfolger
    # beginnt dort; davor bzw. danach ist an ihm nichts abzulesen.
    abgeloest = {z.ersetzt_id for z in alle_zaehler if z.ersetzt_id}
    for zaehler in alle_zaehler:
        tage = sorted(a.reading_date for a in zaehler.readings)
        ausgebaut = tage[-1] if tage and zaehler.id in abgeloest else None
        eingebaut = tage[0] if tage and zaehler.ersetzt_id else None
        if ausgebaut and ausgebaut < von:
            continue
        am_stichtag = (bool(ausgebaut and ausgebaut <= bis)
                       or any(abs(tag - bis) <= STICHTAG_TOLERANZ for tag in tage))
        fehlende_wechsel = [
            tag.isoformat() for (wohnung_id, _, tag) in wechsel
            if zaehler.apartment_id == wohnung_id
            and not (ausgebaut and tag > ausgebaut) and not (eingebaut and tag < eingebaut)
            and not any(abs(t - tag) <= WECHSEL_TOLERANZ for t in tage)
        ]
        ablesungen.append({
            'id': zaehler.id, 'nummer': zaehler.meter_number,
            'kostenart': zaehler.category.name if zaehler.category else '',
            'wohnung': zaehler.apartment.name if zaehler.apartment else 'ganzes Haus',
            'letzte': tage[-1].isoformat() if tage else None,
            'stichtag_ok': am_stichtag,
            'wechsel_fehlen': fehlende_wechsel,
        })

    frist = frist_status(bis, heute)
    pruefstand = _pruefstand(haus, rechnungen, kostenarten, ablesungen, mieter,
                             von, bis, vorjahr_von, vorjahr_bis)
    return {
        'property_id': haus.id, 'immobilie': haus.name, 'jahr': jahr,
        'von': von.isoformat(), 'bis': bis.isoformat(),
        'kostenarten': kostenarten,
        'ablesungen': ablesungen,
        'mieter': mieter,
        'frist_ende': frist['frist_ende'].isoformat(),
        'frist_tage': (frist['frist_ende'] - heute).days,
        'frist_ueberschritten': frist['ueberschritten'],
        'pruefstand': pruefstand,
    }


def _prozent(neu, alt) -> int:
    """Die Änderung von ``alt`` zu ``neu`` in ganzen Prozent."""
    neu, alt = Decimal(str(neu)), Decimal(str(alt))
    return int(((neu - alt) * 100 / alt).quantize(Decimal('1'), ROUND_HALF_UP))


def _befund(art, text, tun, aktion, kennung=None) -> dict:
    return {'art': art, 'text': text, 'tun': tun, 'ziel': {'aktion': aktion, 'id': kennung}}


def _schaetzquote(rechnungen, mieter, von, bis) -> list:
    """§ 9a HeizkostenV: je Anlage und Zweck, wie viel Fläche nicht erfasst ist.

    Die Quote rechnet der Kern aus demselben Vorgang wie die Abrechnung
    (``rechenkern.schaetzquoten``); hier entstehen nur die Sätze.
    """
    from nebenkostenfix import heizung
    from nebenkostenfix.abrechnungsdaten import lade_vorgang
    from nebenkostenfix.rechenkern import schaetzquoten, zahl_text

    anlage_ids = {r.heizungsanlage_id for r in rechnungen
                  if r.heizungsanlage_id and _ueberlappt(r.start_date, r.end_date, von, bis)}
    if not anlage_ids or not mieter:
        return []
    # shortcut: Wohnungen, Zähler und Anlagen sind für jeden Mieter des Hauses
    # dieselben; gerechnet wird über das Jahr, nicht über die Rechnungszeiträume.
    vorgang = lade_vorgang(mieter[0]['id'], von, bis)
    befunde = []
    for q in schaetzquoten(vorgang, anlage_ids, von, bis):
        gruende = []
        for w in q['wohnungen']:
            if w['abgedeckt'] is None:
                gruende.append(f'{w["wohnung"]}: Zähler {w["nummer"]} hat weniger als zwei '
                               'Ablesungen, die Abrechnung setzt dort keinen Verbrauch an')
            else:
                gruende.append(f'{w["wohnung"]}: die Ablesungen von Zähler {w["nummer"]} decken '
                               f'nur {w["abgedeckt"]} von {w["tage"]} Tagen, den Rest rechnet '
                               'die Abrechnung hoch')
        # Aufgerundet: eine Quote über 25 % soll nie als „25,0 %“ erscheinen.
        prozent = str(q['quote'].quantize(Decimal('0.1'), ROUND_CEILING)).replace('.', ',')
        text = (f'Heizungsanlage „{q["anlage"]}“, {heizung.VERBRAUCHSART[q["zweck"]]}: '
                f'Für {zahl_text(q["qm"])} von {zahl_text(q["gesamt_qm"])} m² ({prozent} %) '
                f'ist der Verbrauch im Abrechnungsjahr nicht ordnungsgemäß erfasst – '
                f'{"; ".join(gruende)}.')
        if q['ueberschritten']:
            text += (' Das ist mehr als ein Viertel der Fläche an dieser Anlage: Nach § 9a '
                     'Abs. 2 HeizkostenV sind diese Kosten dann ausschließlich nach Fläche zu '
                     'verteilen. Das kann die App noch nicht – verschicken Sie die Abrechnung '
                     'für diese Anlage so nicht.')
        else:
            # Der Kern schätzt durchaus, nur nicht nach § 9a Abs. 1: der Satz nennt, was er tut.
            tut = []
            if any(w['abgedeckt'] is None for w in q['wohnungen']):
                tut.append('setzt ohne zwei Ablesungen 0 an')
            if any(w['abgedeckt'] is not None for w in q['wohnungen']):
                tut.append('rechnet Lücken nach Tagen bzw. Gradtagen hoch')
            text += (' Bis zu einem Viertel der Fläche erlaubt § 9a Abs. 1 HeizkostenV eine '
                     'Schätzung aus vergleichbaren früheren Zeiträumen oder Räumen. So schätzt '
                     f'die App nicht: sie {" und ".join(tut)}.')
        befunde.append(_befund(
            'schaetzquote', text,
            'Tragen Sie die fehlenden Ablesungen nach oder prüfen Sie die Zählerstände.',
            'ablesung', q['wohnungen'][0]['zaehler_id']))
    return befunde


def _pruefstand(haus, rechnungen, kostenarten, ablesungen, mieter,
                von, bis, vorjahr_von, vorjahr_bis) -> list:
    """Die Warnungen vor dem Festsetzen (NK-265), in der Reihenfolge der Karte."""
    from nebenkostenfix.abrechnungsdaten import lade_zaehler
    from nebenkostenfix.leerstand import LEERSTAND, Einheit, bilanzen
    from nebenkostenfix.models import Payment
    from nebenkostenfix.rechenkern import (euro_text, menge_text, ueberschneidungstage,
                                           verbrauch_detail)
    from nebenkostenfix.zeitraum import grenze

    def tag(d):
        return d.strftime('%d.%m.%Y')

    befunde = _schaetzquote(rechnungen, mieter, von, bis)

    # €/m² gegen Vorjahr: die Kostenarten mit Sprung (NK-228), je Wohnfläche.
    flaeche = sum(Decimal(str(w.sqm or 0)) for w in haus.apartments if w.is_active)
    for k in kostenarten:
        if not k['sprung']:
            continue
        zeichen = '+' if k['aenderung'] > 0 else '−'
        if flaeche:
            jetzt = euro_text(Decimal(str(k['summe'])) / flaeche) + '/m²'
            vorher = euro_text(Decimal(str(k['summe_vorjahr'])) / flaeche) + '/m²'
        else:
            jetzt, vorher = euro_text(k['summe']), euro_text(k['summe_vorjahr'])
        befunde.append(_befund(
            'kosten_je_qm',
            f'„{k["name"]}“ kostet {jetzt} statt {vorher} im Vorjahr '
            f'({zeichen}{abs(k["aenderung"])} %).',
            'Prüfen Sie die Rechnungen und nennen Sie den Grund im Anschreiben.',
            'rechnungen'))

    # Zählersprünge: Verbrauch im Jahr gegen das Vorjahr, nach dem Rechenkern.
    for a in ablesungen:
        zaehler = lade_zaehler(a['id'])
        jetzt = verbrauch_detail(zaehler, von, bis)
        vorher = verbrauch_detail(zaehler, vorjahr_von, vorjahr_bis)
        if 'no_data' in (jetzt['status'], vorher['status']) or vorher['consumption'] <= 0:
            continue
        aenderung = _prozent(jetzt['consumption'], vorher['consumption'])
        if abs(aenderung) <= ZAEHLER_SPRUNG_PROZENT:
            continue
        einheit = f' {jetzt["unit"]}' if jetzt['unit'] else ''
        befunde.append(_befund(
            'zaehlersprung',
            f'Zähler {a["nummer"]} ({a["wohnung"]}) zeigt {menge_text(jetzt["consumption"])}{einheit} '
            f'statt {menge_text(vorher["consumption"])}{einheit} im Vorjahr '
            f'({"+" if aenderung > 0 else "−"}{abs(aenderung)} %).',
            'Prüfen Sie die Zählerstände auf Tippfehler.',
            'zaehler', a['id']))

    im_jahr = sorted((r for r in rechnungen if _ueberlappt(r.start_date, r.end_date, von, bis)),
                     key=lambda r: (r.start_date, r.id))

    # Rechnung ohne Beleg: weder eigene Datei noch ein Sammelbeleg mit Datei.
    for r in im_jahr:
        if r.document_path or (r.document is not None and r.document.document_path):
            continue
        befunde.append(_befund(
            'ohne_beleg',
            f'Die Rechnung „{r.category.name}“ über {euro_text(r.amount)} '
            f'({tag(r.start_date)} – {tag(r.end_date)}) hat keinen Beleg.',
            'Laden Sie den Beleg hoch: Ihre Mieter dürfen ihn einsehen.',
            'rechnung', r.id))

    # Rechnung außerhalb des Zeitraums: zählt nur mit ihren Tagen im Jahr.
    for r in im_jahr:
        if von <= r.start_date and r.end_date <= bis:
            continue
        drin = ueberschneidungstage(r.start_date, r.end_date, von, bis)
        alle = ueberschneidungstage(r.start_date, r.end_date, r.start_date, r.end_date)
        befunde.append(_befund(
            'ausserhalb',
            f'Die Rechnung „{r.category.name}“ ({tag(r.start_date)} – {tag(r.end_date)}) '
            f'reicht über das Abrechnungsjahr hinaus; es zählen {drin} von {alle} Tagen.',
            'Prüfen Sie den Zeitraum der Rechnung.',
            'rechnung', r.id))

    # Leerstand: unvermietete Tage einer Wohnung trägt der Vermieter.
    einheiten = [Einheit(wohnung_id=w.id, name=w.name, qm=w.sqm,
                         eigennutzung=bool(w.eigennutzung),
                         mietzeiten=[(t.move_in_date,
                                      grenze(t.move_out_date) if t.move_out_date else date.max)
                                     for t in w.tenants])
                 for w in sorted(haus.apartments, key=lambda w: w.name) if w.is_active]
    for b in bilanzen(einheiten, von, grenze(bis)):
        if b.grund != LEERSTAND:
            continue
        befunde.append(_befund(
            'leerstand',
            f'Die Wohnung {b.name} stand {b.unbelegt} Tage leer; diesen Anteil tragen Sie.',
            'Prüfen Sie Ein- und Auszug: fehlt ein Mieter, erfassen Sie ihn.',
            'mieter', b.wohnung_id))

    # Mieter ohne Vorauszahlung im Zeitraum (nur, wer noch abzurechnen ist).
    for m in mieter:
        if m['abrechnung_id']:
            continue
        gezahlt = Payment.query.filter(
            Payment.tenant_id == m['id'], Payment.type == 'Nebenkostenvorauszahlung',
            Payment.payment_date >= date.fromisoformat(m['von']),
            Payment.payment_date <= date.fromisoformat(m['bis'])).first()
        if gezahlt is None:
            befunde.append(_befund(
                'ohne_vorauszahlung',
                f'Für {m["name"]} ({m["wohnung"]}) ist im Zeitraum keine Vorauszahlung erfasst.',
                'Erfassen Sie die Zahlungen, sonst fehlen sie in der Abrechnung.',
                'zahlung', m['id']))

    # Fehlende Ablesung beim Mieterwechsel.
    for a in ablesungen:
        for wechsel in a['wechsel_fehlen']:
            befunde.append(_befund(
                'wechsel_ablesung',
                f'Zähler {a["nummer"]} ({a["wohnung"]}) hat keinen Stand zum Mieterwechsel '
                f'am {tag(date.fromisoformat(wechsel))}.',
                'Erfassen Sie den Zählerstand vom Wechseltag.',
                'ablesung', a['id']))
    return befunde


def init_jahresabrechnung(app):
    from flask import jsonify

    from nebenkostenfix.validation import Eingabe

    @app.route('/api/jahresabrechnung', methods=['GET'])
    def jahresabrechnung_stand():
        eingabe = Eingabe.aus_query()
        try:
            return jsonify(stand(eingabe.ganzzahl('property_id', pflicht=True),
                                 eingabe.ganzzahl('jahr', pflicht=True)))
        except StandFehler as fehler:
            return jsonify({'error': str(fehler)}), 400
