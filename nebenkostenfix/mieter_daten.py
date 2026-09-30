"""Auskunft und Loeschung fuer ein Mietverhaeltnis (NK-078, DSGVO Art. 15/17).

Der Bestand gehoert dem Vermieter, die Daten zum Mietverhaeltnis dem Mieter:
Er darf sie abrufen, und wenn das Mietverhaeltnis endet, darf verlangt werden,
dass Personendaten verschwinden. Beides greift nicht nur in Zeilen, sondern
auch in die Dateien im Belegordner -- ein geloeschter Mieter, dessen Mietvertrag
weiter im Belegordner liegt, ist nicht geloescht.

Was hier "der Mieter" ist, ist genau umrissen:

    tenants-Zeile, Kostenprofile, Haushaltsgroessen, Zahlungen,
    Abrechnungsberichte (einfach und detailliert) und die Lesungen an den
    Zaehlern seiner Wohnung samt Lesenachweisen.

Nicht dazu gehoert die Messhistorie: Lesungen und Zaehler haengen an der
Wohnung, nicht an der Person -- sie tragen die Abrechnung der Nachmieter
(D-82). Die Loeschung laesst sie bewusst stehen; der Export nimmt sie auf,
damit der Auskunft das Mietverhaeltnis vollstaendig vorliegt.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Die Dateiarten des Mietverhaeltnisses in der Reihenfolge der Bedeutung.
# 'ablesung' wird exportiert, aber bei der Loeschung ausgelassen (D-82).
DATEIARTEN = ('mietvertrag', 'abrechnung')


def _als_wert(wert):
    """JSON-faehig: Datum und Zeit als ISO, Geld als Text."""
    if isinstance(wert, (date, datetime)):
        return wert.isoformat()
    if isinstance(wert, Decimal):
        return str(wert)
    return wert


def _zeile(model_obj) -> dict:
    return {
        c.name: _als_wert(getattr(model_obj, c.name))
        for c in model_obj.__table__.columns
    }


def _dateien_des_mieters(tenant) -> list[dict]:
    """Alle Dateien, die dieses Mietverhaeltnis im Belegordner hinterlassen hat.

    Lesenachweise zaehlen dazu, weil der Ablesungszettel mitunter Namen
    traegt; die Art merkt sich, was davon im Fall der Loeschung gelten soll.
    """
    dateien = []
    if tenant.contract_path:
        dateien.append({'art': 'mietvertrag', 'pfad': tenant.contract_path})
    for bericht in tenant.billing_reports:
        for feld, suffix in (('document_path', ''), ('document_path_detailed', ' (detailliert)')):
            pfad = getattr(bericht, feld)
            if pfad:
                dateien.append({'art': 'abrechnung', 'pfad': pfad, 'feld': f'{feld}{suffix}'})
    for lesung in _lesungen_des_mieters(tenant):
        if lesung.document_path:
            dateien.append({
                'art': 'ablesung',
                'pfad': lesung.document_path,
                'ablesung_am': lesung.reading_date.isoformat(),
            })
    return dateien


def _lesungen_des_mieters(tenant) -> list:
    """Die Ablesungen an den Zaehlern der Wohnung, **innerhalb der Mietzeit**.

    F-77 (NK-149): Bis hierher kamen alle Lesungen der Wohnung mit, also
    auch Verbrauch und Ablesefotos von Vor- und Nachmietern -- Daten Dritter
    in einer Auskunft nach Art. 15. Jetzt nur, was zwischen Einzug und Auszug
    abgelesen wurde, die Raender eingeschlossen (Einzugs- und Auszugsablesung,
    Zwischenablesung am Stichtag). Ohne Auszug laeuft die Mietzeit bis heute.
    """
    from nebenkostenfix.models import MeterReading

    wohnung = tenant.apartment
    if wohnung is None:
        return []
    zaehler_ids = [z.id for z in wohnung.meters]
    if not zaehler_ids:
        return []
    abfrage = MeterReading.query.filter(
        MeterReading.meter_id.in_(zaehler_ids),
        MeterReading.reading_date >= tenant.move_in_date)
    if tenant.move_out_date is not None:
        abfrage = abfrage.filter(
            MeterReading.reading_date <= tenant.move_out_date)
    return abfrage.order_by(MeterReading.reading_date, MeterReading.id).all()


def export_erstellen(tenant) -> tuple[bytes, dict]:
    """Das Auskunfts-Paket: JSON mit allen Zeilen, dazu die Dateien.

    Geliefert wird das ZIP als Bytes plus der Index, damit die Route beim
    Fehler frueh abbrechen kann, ohne schon Bytes zu halten.
    """
    from nebenkostenfix.models import db

    dateien = _dateien_des_mieters(tenant)
    im_archiv = {}
    eintraege = []
    for eintrag in dateien:
        relativ = eintrag['pfad']
        if relativ in im_archiv:
            continue
        archivname = f"dateien/{relativ}"
        voll = _aufloesen(relativ)
        if voll is not None:
            im_archiv[relativ] = archivname
            eintraege.append({'art': eintrag['art'], 'pfad': relativ,
                              'im_archiv': archivname})
        else:
            # Der Verweis steht in der Datenbank, die Datei fehlt. Die
            # Auskunft sagt das statt sie stillschweigend wegzulassen.
            eintraege.append({'art': eintrag['art'], 'pfad': relativ,
                              'fehlt': True})

    berichte = [_zeile(r) for r in tenant.billing_reports]
    zahlungen = [_zeile(z) for z in tenant.payments]
    inhalt = {
        'format': 'mieter-auskunft',
        'erstellt_am': datetime.now().astimezone().isoformat(timespec='seconds'),
        'mieter': _zeile(tenant),
        'kostenprofile': [_zeile(p) for p in tenant.cost_profiles],
        'haushaltsgroessen': [_zeile(h) for h in tenant.haushaltsgroessen],
        'zahlungen': zahlungen,
        'abrechnungsberichte': berichte,
        'ablesungen': [_zeile(l) for l in _lesungen_des_mieters(tenant)],
        'dateien': eintraege,
        # Bewusste Grenze, nicht Versehen: Zaehler und Lesungen gehoeren zur
        # Wohnung und bleiben bei einer Loeschung stehen (D-82).
        'hinweis': 'Die Auskunft enthält nur Ablesungen aus Ihrer Mietzeit '
                   '(Einzug bis Auszug, Ränder eingeschlossen). Zähler und '
                   'Lesungen gehören zur Wohnung und werden bei einer '
                   'Löschung nicht entfernt; sie tragen die Abrechnung der '
                   'Nachmieter.',
    }
    json_bytes = json.dumps(inhalt, indent=2, ensure_ascii=False).encode('utf-8')

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, 'w', zipfile.ZIP_DEFLATED) as archiv:
        archiv.writestr('mieter-auskunft.json', json_bytes)
        for relativ, archivname in im_archiv.items():
            archiv.write(_aufloesen(relativ), archivname)
    return puffer.getvalue(), inhalt


# --- Aufbewahrung (NK-153, E-11 → D-89) ------------------------------------
#
# Festgesetzte Abrechnungen und Zahlungen sind Buchungsbelege des Vermieters
# (§ 147 Abs. 1 AO, § 257 Abs. 1 HGB): bis zu zehn Jahre aufzubewahren, die
# Frist beginnt mit dem Schluss des Kalenderjahres (§ 147 Abs. 4 AO). Art. 17
# Abs. 3 lit. b DSGVO nimmt solche Pflichten von der Loeschung aus. Die
# Software haelt die laengste uebliche Frist und sagt es -- ob sie im
# Einzelfall kuerzer ist, gehoert fachlich geprueft, nicht geraten.
AUFBEWAHRUNG_JAHRE = 10


def aufbewahrung_bis(tenant) -> date | None:
    """Letzter Tag der Aufbewahrung, oder None, wenn nichts aufzubewahren ist."""
    jahre = [b.created_at.year for b in tenant.billing_reports if b.created_at]
    jahre += [z.payment_date.year for z in tenant.payments if z.payment_date]
    if not jahre:
        return None
    return date(max(jahre) + AUFBEWAHRUNG_JAHRE, 12, 31)


def loeschen(tenant, heute: date | None = None) -> dict:
    """Mietverhaeltnis loeschen -- oder sperren, solange eine Frist laeuft.

    Ohne festgesetzte Abrechnung und ohne Zahlung: alles weg wie bisher
    (Dateien und Zeilen, D-82 fuer Zaehler und Lesungen).

    Mit Aufbewahrungspflicht (D-89): sofort weg sind der Mietvertrag (Datei
    und Verweis) und die Kostenprofile. Die Zeile bleibt als Anker fuer
    Abrechnungen, Zahlungen und Haushaltsgroessen stehen (die tragen auch
    die Abrechnungen der Mitmieter im Personenschluessel), wird aus allen
    Listen ausgeblendet und am Tag nach ``gesperrt_bis`` beim Start ganz
    geloescht (``abgelaufene_loeschen``).
    """
    from nebenkostenfix.models import db

    heute = heute or date.today()
    frist = aufbewahrung_bis(tenant)
    if frist is None or frist < heute:
        return _endgueltig_loeschen(tenant)

    geloescht, fehlend = [], []
    if tenant.contract_path:
        pfad = tenant.contract_path
        if _aufloesen(pfad) is not None and _loesche(pfad):
            geloescht.append(pfad)
        else:
            fehlend.append(pfad)
        tenant.contract_path = None
    for profil in list(tenant.cost_profiles):
        db.session.delete(profil)
    tenant.gesperrt_bis = frist
    name = tenant.name
    wohnung = tenant.apartment.name if tenant.apartment else '?'
    db.session.commit()
    return {
        'tenant': name,
        'wohnung': wohnung,
        'geloeschte_dateien': geloescht,
        'fehlende_dateien': fehlend,
        'lesungen_verbleiben': True,
        'gesperrt_bis': frist.isoformat(),
    }


def abgelaufene_loeschen(heute: date | None = None) -> int:
    """Beim Start: gesperrte Mietverhaeltnisse nach Fristablauf ganz loeschen."""
    from nebenkostenfix.models import Tenant

    heute = heute or date.today()
    faellig = Tenant.query.filter(Tenant.gesperrt_bis.isnot(None),
                                  Tenant.gesperrt_bis < heute).all()
    for tenant in faellig:
        _endgueltig_loeschen(tenant)
    return len(faellig)


def _endgueltig_loeschen(tenant) -> dict:
    """Dateien und Zeilen des Mietverhaeltnisses entfernen.

    Erst die Dateien sammeln und loeschen, dann die Zeile -- mit den
    Kaskaden fuer Profile, Haushaltsgroessen, Zahlungen und Berichte. Eine
    Datei, die im Belegordner schon fehlt, bricht nichts ab: sie steht im
    Bericht unter 'fehlende_dateien', damit der Vermieter Bescheid weiß.
    """
    from nebenkostenfix.models import db

    bericht_dateien = []
    fehlende = []
    for eintrag in _dateien_des_mieters(tenant):
        if eintrag['art'] not in DATEIARTEN:
            continue  # Lesenachweise bleiben (D-82)
        pfad = eintrag['pfad']
        voll = _aufloesen(pfad)
        if voll is not None:
            if _loesche(pfad):
                bericht_dateien.append(pfad)
            else:
                fehlende.append(pfad)
        else:
            fehlende.append(pfad)

    name = tenant.name
    wohnung = tenant.apartment.name if tenant.apartment else '?'
    db.session.delete(tenant)
    db.session.commit()
    return {
        'tenant': name,
        'wohnung': wohnung,
        'geloeschte_dateien': bericht_dateien,
        'fehlende_dateien': fehlende,
        'lesungen_verbleiben': True,
        'gesperrt_bis': None,
    }


def _nas_wurzel() -> str:
    # Lazy: app.py haelt die Instanz und importiert dieses Modul beim Start.
    from app import nas_handler

    return nas_handler.nas_mount_path


def _aufloesen(relativ: str):
    """Pfad im Belegordner per realpath (NK-129), sonst None."""
    from nebenkostenfix.uploads import pfad_aufloesen

    return pfad_aufloesen(_nas_wurzel(), relativ)


def _loesche(relativer_pfad: str) -> bool:
    from app import nas_handler

    return nas_handler.delete_file(relativer_pfad)
