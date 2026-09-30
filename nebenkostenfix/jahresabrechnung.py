"""Jahresabrechnungs-Assistent: der Stand eines Jahres (NK-160).

„Jahr abrechnen“ führt in fünf Schritten durch ein Abrechnungsjahr einer
Immobilie. Dieses Modul liefert nur den **Stand**, den die Schritte 1–3 und
5 zeigen; gerechnet und festgesetzt wird über die vorhandenen Routen
(``/api/billing/generate`` und ``/api/billing/finalize``) -- kein zweiter
Rechenweg.

    GET /api/jahresabrechnung?property_id=<id>&jahr=<JJJJ>

- **Kostenarten** (Schritt 2): jede übliche Kostenart und jede, zu der es im
  Jahr oder im Vorjahr Rechnungen gibt, mit Summe, Anzahl und Vorjahres-
  summe. ``fehlt`` heißt: im Vorjahr gab es eine, in diesem Jahr keine.
- **Ablesungen** (Schritt 3): je Zähler, ob ein Stand zum Stichtag
  (±31 Tage um das Jahresende) da ist, und je Mieterwechsel im Jahr, ob der
  Zähler der Wohnung am Wechseltag (±7 Tage) abgelesen wurde.
- **Mieter** (Schritte 4 und 5): wer im Jahr dort wohnte, mit dem
  Zeitraum, der abzurechnen ist, und der Abrechnung, falls es sie schon gibt.
- **Frist**: Ende der Abrechnungsfrist nach § 556 Abs. 3 BGB.
"""

from __future__ import annotations

from datetime import date, timedelta

# Die Kostenarten, die in fast jedem Mietshaus anfallen: fehlen sie, fragt
# der Assistent nach, auch ohne Vorjahr.
UEBLICH = (
    'Grundsteuer',
    'Wasserversorgung',
    'Entwässerung',
    'Straßenreinigung und Müllbeseitigung',
    'Sach- und Haftpflichtversicherung',
    'Beleuchtung (Allgemeinstrom)',
)
STICHTAG_TOLERANZ = timedelta(days=31)
WECHSEL_TOLERANZ = timedelta(days=7)


class StandFehler(Exception):
    """Immobilie oder Jahr taugen nicht; Meldung für Menschen."""


def _ueberlappt(beginn: date, ende: date, von: date, bis: date) -> bool:
    return beginn <= bis and ende >= von


def stand(property_id: int, jahr: int, heute: date | None = None) -> dict:
    from nebenkostenfix.frist import frist_status
    from nebenkostenfix.models import (CostCategory, CostInvoice, Meter, Property, Tenant,
                        TenantBillingReport)

    heute = heute or date.today()
    if not 2000 <= jahr <= heute.year:
        raise StandFehler(f'Das Jahr {jahr} lässt sich nicht abrechnen.')
    haus = Property.query.get(property_id)
    if haus is None:
        raise StandFehler('Diese Immobilie gibt es nicht.')
    von, bis = date(jahr, 1, 1), date(jahr, 12, 31)
    vorjahr_von, vorjahr_bis = date(jahr - 1, 1, 1), date(jahr - 1, 12, 31)

    # --- Schritt 2: Kostenarten --------------------------------------------------
    rechnungen = CostInvoice.query.filter_by(property_id=haus.id).all()
    kostenarten = []
    for kat in CostCategory.query.order_by(CostCategory.name).all():
        diese = [r for r in rechnungen if r.category_id == kat.id
                 and _ueberlappt(r.start_date, r.end_date, von, bis)]
        vorige = [r for r in rechnungen if r.category_id == kat.id
                  and _ueberlappt(r.start_date, r.end_date, vorjahr_von, vorjahr_bis)]
        if not (diese or vorige or kat.name in UEBLICH):
            continue
        summe = sum((r.amount for r in diese), start=0)
        summe_vorjahr = sum((r.amount for r in vorige), start=0)
        if diese:
            zustand = 'erfasst'
        elif vorige:
            zustand = 'fehlt'
        else:
            zustand = 'offen'
        kostenarten.append({
            'id': kat.id, 'name': kat.name, 'zustand': zustand,
            'anzahl': len(diese), 'summe': float(summe),
            'summe_vorjahr': float(summe_vorjahr) if vorige else None,
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
                if tag and von < tag <= bis:
                    wechsel.append((wohnung.id, wohnung.name, tag))

    # --- Schritt 3: Ablesungen ----------------------------------------------------
    ablesungen = []
    for zaehler in Meter.query.filter_by(property_id=haus.id).order_by(Meter.meter_number).all():
        tage = sorted(a.reading_date for a in zaehler.readings)
        am_stichtag = any(abs(tag - bis) <= STICHTAG_TOLERANZ for tag in tage)
        fehlende_wechsel = [
            tag.isoformat() for (wohnung_id, _, tag) in wechsel
            if zaehler.apartment_id == wohnung_id
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
    return {
        'property_id': haus.id, 'immobilie': haus.name, 'jahr': jahr,
        'von': von.isoformat(), 'bis': bis.isoformat(),
        'kostenarten': kostenarten,
        'ablesungen': ablesungen,
        'mieter': mieter,
        'frist_ende': frist['frist_ende'].isoformat(),
        'frist_tage': (frist['frist_ende'] - heute).days,
        'frist_ueberschritten': frist['ueberschritten'],
    }


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
