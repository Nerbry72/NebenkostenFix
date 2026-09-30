"""Welcher Abrechnungszeitraum passt für diesen Mieter -- und warum (NK-186).

Befund auf 6061: Mieter 3 zieht am 30.09.2026 aus. Abgerechnet wurde
01.09.2025–30.09.2026, aber die Rechnungen für 2026 fehlen noch zum Teil:
ein Guthaben, das nur aus fehlenden Rechnungen entstand. Sinnvoll wäre
01.09.2025–31.12.2025 gewesen, den Rest später. Das soll die App selbst
vorschlagen und den Vorschlag begründen.

Die Regeln, in dieser Reihenfolge:

1. **Beginn** -- der Tag nach der letzten Abrechnung, sonst der Einzug.
2. **Ziel** -- das Ende des Abrechnungsjahres des Hauses, in dem der Beginn
   liegt (D-114: eingestellt am Haus, sonst wie die bisherigen Abrechnungen,
   sonst das Kalenderjahr); zieht der Mieter vorher aus, sein letzter
   Miettag. So bleibt der Zeitraum innerhalb der zwölf Monate des
   § 556 Abs. 3 BGB.
3. **Noch nicht vorbei** -- liegt das Ziel nach heute, gibt es keinen
   Vorschlag.
4. **Rechnungen** -- fehlt für eine Kostenart ab einem Tag die Rechnung,
   endet der Vorschlag am Tag davor.
5. **Vorjahr** -- hatte eine Kostenart im Jahr vor dem Beginn eine
   Rechnung, im Zeitraum aber keine, sagt der Vorschlag es dazu. Er endet
   deshalb nicht früher: Ob die Rechnung noch kommt, weiß nur der Vermieter
   (auf 6061: der Schornsteinfeger von 2024).
6. **Keine Rechnung** -- liegt für den Zeitraum gar keine Rechnung vor, gibt
   es keinen Vorschlag (F-126: eine leere Menge hat keine Lücke, und der
   Vorschlag sagte „decken den ganzen Zeitraum ab“).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

from nebenkostenfix.abrechnungsdaten import lade_vorgang
from nebenkostenfix.frist import frist_ende
from nebenkostenfix.rechenkern import abdeckungsluecken, abrechnungsart_von
from nebenkostenfix.validation import EingabeFehler

EIN_TAG = timedelta(days=1)


def _d(tag: date) -> str:
    return tag.strftime('%d.%m.%Y')


def _ohne(gruende: list) -> dict:
    return {'beginn': None, 'ende': None, 'gruende': gruende}


def jahresbeginn(prop) -> tuple[int, int, str]:
    """(Monat, Tag, Quelle) des Abrechnungsjahres eines Hauses (D-114).

    Quelle ``feld``: am Haus eingestellt. ``abrechnungen``: so endeten die
    bisherigen Abrechnungen des Hauses, ein Auszug zählt nicht mit.
    ``vorgabe``: der 01.01.
    """
    from nebenkostenfix.models import Apartment, Tenant, TenantBillingReport

    if prop.abrechnungsjahr_beginn:
        monat, tag = map(int, prop.abrechnungsjahr_beginn.split('-'))
        return monat, tag, 'feld'
    enden = (TenantBillingReport.query.join(Tenant).join(Apartment)
             .filter(Apartment.property_id == prop.id)
             .with_entities(TenantBillingReport.end_date, Tenant.move_out_date).all())
    tage = [ende + EIN_TAG for ende, auszug in enden if ende != auszug]
    if not tage:
        return 1, 1, 'vorgabe'
    anzahl = Counter((t.month, t.day) for t in tage)
    # Der häufigste Beginn; bei Gleichstand der jüngste.
    bester = max(tage, key=lambda t: (anzahl[(t.month, t.day)], t))
    if (bester.month, bester.day) == (2, 29):
        return 3, 1, 'abrechnungen'
    return bester.month, bester.day, 'abrechnungen'


def jahresbeginn_aus_text(text: str | None) -> str | None:
    """'TT.MM.' aus dem Formular als 'MM-TT'; leer heißt: ableiten."""
    if not text or not text.strip():
        return None
    treffer = re.fullmatch(r'\s*(\d{1,2})\.(\d{1,2})\.?\s*', text)
    try:
        # Ein Jahr ohne 29. Februar: das Abrechnungsjahr beginnt jedes Jahr am selben Tag.
        tag = date(2025, int(treffer[2]), int(treffer[1])) if treffer else None
    except ValueError:
        tag = None
    if tag is None:
        raise EingabeFehler('Das Abrechnungsjahr beginnt an einem Tag wie 01.04. '
                            '(Tag und Monat, der 29.02. geht nicht).', 'abrechnungsjahr_beginn')
    return f'{tag.month:02d}-{tag.day:02d}'


def jahresbeginn_text(monat: int, tag: int) -> str:
    return f'{tag:02d}.{monat:02d}.'


def _jahresende(beginn: date, monat: int, tag: int) -> date:
    """Letzter Tag des Abrechnungsjahres, in dem ``beginn`` liegt."""
    start = date(beginn.year, monat, tag)
    if start > beginn:
        start = date(beginn.year - 1, monat, tag)
    return date(start.year + 1, monat, tag) - EIN_TAG


def vorschlag(tenant_id: int, heute: date) -> dict:
    """``{'beginn', 'ende', 'gruende'}``; ohne Vorschlag sind beide ``None``."""
    from nebenkostenfix.models import CostInvoice, Tenant, TenantBillingReport, db

    t = db.session.get(Tenant, tenant_id)
    gruende = []

    letzte = (TenantBillingReport.query.filter_by(tenant_id=t.id)
              .order_by(TenantBillingReport.end_date.desc()).first())
    abgerechnet = max(filter(None, (letzte and letzte.end_date, t.last_billed_until)),
                      default=None)
    if abgerechnet and abgerechnet >= t.move_in_date:
        beginn = abgerechnet + EIN_TAG
        gruende.append(f'Abgerechnet ist bis {_d(abgerechnet)}, '
                       f'weiter geht es ab {_d(beginn)}.')
    else:
        beginn = t.move_in_date
        gruende.append(f'Noch keine Abrechnung: Beginn ist der Einzug am {_d(beginn)}.')

    auszug = t.move_out_date
    if auszug and auszug < beginn:
        return _ohne([f'Das Mietverhältnis ist bis zum Auszug am {_d(auszug)} abgerechnet.'])

    monat, tag, quelle = jahresbeginn(t.apartment.property)
    jahresende = _jahresende(beginn, monat, tag)
    if auszug and auszug <= jahresende:
        ziel = auszug
        gruende.append(f'Der letzte Miettag ist der {_d(auszug)}.')
    else:
        ziel = jahresende
        if (monat, tag) == (1, 1):
            gruende.append('Abgerechnet wird je Kalenderjahr, höchstens zwölf Monate '
                           '(§ 556 Abs. 3 BGB).')
        else:
            woher = {'feld': 'so eingestellt am Haus',
                     'abrechnungen': 'wie die bisherigen Abrechnungen des Hauses'}[quelle]
            gruende.append(f'Das Abrechnungsjahr beginnt am {jahresbeginn_text(monat, tag)} '
                           f'({woher}), höchstens zwölf Monate (§ 556 Abs. 3 BGB).')
    if ziel > heute:
        return _ohne(gruende + [f'Der Zeitraum läuft noch bis {_d(ziel)}. '
                                'Abrechnen lässt er sich erst danach.'])

    vorgang = lade_vorgang(t.id, beginn, ziel)

    def zaehlt(kategorie):
        return abrechnungsart_von(vorgang.profile, kategorie) != 'ignoriert'

    rechnungen = [r for r in vorgang.rechnungen if zaehlt(r.kategorie)
                  and (not r.wohnung_id or r.wohnung_id == vorgang.wohnung.id)]
    fehlt_ab = {e['kategorie']: e['luecken'][0][0]
                for e in abdeckungsluecken(vorgang, rechnungen)}
    im_zeitraum = {r.kategorie.name for r in rechnungen}
    vorjahr = CostInvoice.query.filter(
        CostInvoice.property_id == vorgang.immobilie_id,
        CostInvoice.end_date >= beginn - timedelta(days=365),
        CostInvoice.end_date < beginn,
        db.or_(CostInvoice.apartment_id.is_(None),
               CostInvoice.apartment_id == vorgang.wohnung.id)).all()
    ohne_rechnung = sorted({r.category.name for r in vorjahr
                            if r.category.name not in im_zeitraum and zaehlt(r.category)})

    if not rechnungen:
        return _ohne(gruende + [f'Für {_d(beginn)}–{_d(ziel)} ist noch keine Rechnung erfasst. '
                                'Erfassen Sie die Rechnungen, dann schlägt die App den '
                                'Zeitraum vor.'])
    if fehlt_ab:
        erster = min(fehlt_ab.values())
        namen = ', '.join(f'„{n}“' for n in sorted(fehlt_ab) if fehlt_ab[n] == erster)
        if erster <= beginn:
            return _ohne(gruende + [f'Für {namen} liegt ab {_d(beginn)} noch keine '
                                    'Rechnung vor. Abrechnen, sobald sie da ist.'])
        ende = erster - EIN_TAG
        gruende.append(f'Ab {_d(erster)} fehlt die Rechnung für {namen}. '
                       f'Deshalb endet der Vorschlag am {_d(ende)}.')
    else:
        ende = ziel
        # F-126: neben dem Vorjahreshinweis wäre „decken ab“ ein Widerspruch.
        gruende.append('Die vorhandenen Rechnungen decken den ganzen Zeitraum ab.' if not ohne_rechnung
                       else 'Jede Kostenart mit Rechnung ist für den ganzen Zeitraum belegt.')
    if ohne_rechnung:
        gruende.append(f'Für {", ".join(f"„{n}“" for n in ohne_rechnung)} gab es im Jahr '
                       'davor eine Rechnung, für diesen Zeitraum noch nicht. Kommt sie noch, '
                       'warten Sie mit der Abrechnung; sonst fehlen diese Kosten.')

    rest_bis = auszug if auszug and auszug > ende else None
    if rest_bis:
        gruende.append(f'Den Rest bis zum Auszug ({_d(ende + EIN_TAG)}–{_d(rest_bis)}) '
                       'rechnen Sie getrennt ab, sobald die Rechnungen da sind.')
    elif not auszug and ende < ziel:
        gruende.append(f'Den Rest ab {_d(ende + EIN_TAG)} rechnen Sie mit dem '
                       'nächsten Zeitraum ab.')
    gruende.append(f'Zustellen bis spätestens {_d(frist_ende(ende))} (§ 556 Abs. 3 BGB).')
    return {'beginn': beginn.isoformat(), 'ende': ende.isoformat(), 'gruende': gruende}
