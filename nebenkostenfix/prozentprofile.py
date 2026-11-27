"""Objektweite Prüfung der vertraglichen Prozentsätze vor dem Speichern."""
from nebenkostenfix.models import Apartment, Tenant, db
from nebenkostenfix.prozent import pruefe_prozent, summenabschnitte
from nebenkostenfix.validation import EingabeFehler
from nebenkostenfix.zeitraum import grenze


def andere_anteile(mieter):
    # Über apartment_id laden: auch bei einer gerade geänderten Wohnung
    # darf eine bereits geladene Relationship nicht das alte Haus liefern.
    wohnung = db.session.get(Apartment, mieter.apartment_id)
    if wohnung is None:
        raise EingabeFehler('Die angegebene Wohnung gibt es nicht.', 'apartment_id')
    andere = Tenant.query.join(Apartment).filter(
        Apartment.property_id == wohnung.property_id,
        Tenant.id != mieter.id).all()
    anteile = {}
    for nachbar in andere:
        for profil in nachbar.cost_profiles:
            if profil.billing_type == 'prozent':
                anteile.setdefault(profil.category_id, []).append((
                    nachbar.move_in_date, grenze(nachbar.move_out_date) if nachbar.move_out_date else None,
                    pruefe_prozent(profil.percentage)))
    return anteile


def pruefe_summe(mieter, profile, namen):
    andere = andere_anteile(mieter)
    for kategorie, wert in profile.items():
        if not isinstance(wert, dict) or wert['billing_type'] != 'prozent':
            continue
        for von, _, summe in summenabschnitte(
                andere.get(kategorie, []), mieter.move_in_date,
                grenze(mieter.move_out_date) if mieter.move_out_date else None):
            gesamt = summe + wert['percentage']
            if gesamt > 100:
                text = format(gesamt.normalize(), 'f').replace('.', ',')
                raise EingabeFehler(
                    f'Kostenart „{namen.get(kategorie, kategorie)}“: Ab '
                    f'{von:%d.%m.%Y} sind insgesamt {text} % vergeben. '
                    'Die Summe darf 100 % nicht überschreiten.', 'profiles')
