"""Welcher Abrechnungszeitraum passt für diesen Mieter -- und warum (NK-186).

Befund auf 6061: Mieter 3 zieht am 30.09.2026 aus. Abgerechnet wurde
01.09.2025–30.09.2026, aber die Rechnungen für 2026 fehlen noch zum Teil:
ein Guthaben, das nur aus fehlenden Rechnungen entstand. Sinnvoll wäre
01.09.2025–31.12.2025 gewesen, den Rest später. Das soll die App selbst
vorschlagen und den Vorschlag begründen.

Die Regeln, in dieser Reihenfolge:

1. **Beginn** -- der Tag nach der letzten Abrechnung, sonst der Einzug.
2. **Ziel** -- das Ende des Kalenderjahres, in dem der Beginn liegt; zieht
   der Mieter vorher aus, sein letzter Miettag. So bleibt der Zeitraum
   innerhalb der zwölf Monate des § 556 Abs. 3 BGB.
3. **Noch nicht vorbei** -- liegt das Ziel nach heute, gibt es keinen
   Vorschlag.
4. **Rechnungen** -- fehlt für eine Kostenart ab einem Tag die Rechnung,
   endet der Vorschlag am Tag davor.
5. **Vorjahr** -- hatte eine Kostenart im Jahr vor dem Beginn eine
   Rechnung, im Zeitraum aber keine, sagt der Vorschlag es dazu. Er endet
   deshalb nicht früher: Ob die Rechnung noch kommt, weiß nur der Vermieter
   (auf 6061: der Schornsteinfeger von 2024).
"""

from __future__ import annotations

from datetime import date, timedelta

from nebenkostenfix.abrechnungsdaten import lade_vorgang
from nebenkostenfix.frist import frist_ende
from nebenkostenfix.rechenkern import abdeckungsluecken, abrechnungsart_von

EIN_TAG = timedelta(days=1)


def _d(tag: date) -> str:
    return tag.strftime('%d.%m.%Y')


def _ohne(gruende: list) -> dict:
    return {'beginn': None, 'ende': None, 'gruende': gruende}


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

    jahresende = date(beginn.year, 12, 31)
    if auszug and auszug <= jahresende:
        ziel = auszug
        gruende.append(f'Der letzte Miettag ist der {_d(auszug)}.')
    else:
        ziel = jahresende
        gruende.append('Abgerechnet wird je Kalenderjahr, höchstens zwölf Monate '
                       '(§ 556 Abs. 3 BGB).')
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
        gruende.append('Die vorhandenen Rechnungen decken den ganzen Zeitraum ab.')
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
