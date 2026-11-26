"""Mieter und Verträge: Kostenprofile für einen Mieter, den es nicht gibt.

``POST /api/tenants/<id>/profiles`` fragte nicht, ob es den Mieter gibt. SQLite
setzt den Fremdschlüssel ohne PRAGMA foreign_keys nicht durch, also landeten die
Profile mit 200 in der Datenbank. SQLite vergibt die höchste freie Nummer neu:
Der nächste Mieter, der diese Nummer bekam, erbte die Profile -- etwa
„ignoriert“ für eine Kostenart, die ihm dann in der Abrechnung fehlte.

Die übrigen Mieter-Unterrouten (Haushaltsgrößen, Soll, Kaltmiete,
Zeitraumvorschlag) antworten bei einer unbekannten Nummer mit 404. Die
Profilroute tut es jetzt auch, für POST und für GET.

Alle Werte sind erfunden.
"""

from __future__ import annotations

from datetime import date

from nebenkostenfix.models import TenantCostProfile, db
from tests import billing_factories as f


def _haus_mit_mieter():
    """Testhaus mit zwei Wohnungen, Mieter Eins in W1 mit Profil Grundsteuer = qm."""
    haus = f.house('Testhaus Nachtweg')
    w1 = f.apt(haus, 'W1', 45)
    w2 = f.apt(haus, 'W2', 55)
    mieter = f.tenant(w1, 'Mieter Eins', date(2024, 1, 1))
    grundsteuer = f.category('Grundsteuer')
    hauswart = f.category('Hauswart')
    db.session.add(TenantCostProfile(tenant_id=mieter.id,
                                     category_id=grundsteuer.id,
                                     billing_type='qm'))
    db.session.commit()
    return {'w1': w1, 'w2': w2, 'mieter': mieter,
            'grundsteuer': grundsteuer, 'hauswart': hauswart}


def _profilzeilen(tenant_id):
    db.session.expire_all()
    return TenantCostProfile.query.filter_by(tenant_id=tenant_id).count()


def test_profile_fuer_unbekannten_mieter_werden_abgewiesen(auth_client, app_ctx):
    d = _haus_mit_mieter()
    unbekannt = d['mieter'].id + 1

    antwort = auth_client.post(f'/api/tenants/{unbekannt}/profiles',
                               json={str(d['grundsteuer'].id): 'ignoriert'})

    assert antwort.status_code == 404, antwort.get_json()
    assert _profilzeilen(unbekannt) == 0


def test_neuer_mieter_erbt_keine_profile_der_freien_nummer(auth_client, app_ctx):
    d = _haus_mit_mieter()
    auth_client.post(f'/api/tenants/{d["mieter"].id + 1}/profiles',
                     json={str(d['grundsteuer'].id): 'ignoriert'})

    antwort = auth_client.post('/api/tenants', data={
        'apartment_id': str(d['w2'].id), 'name': 'Mieterin Zwei',
        'move_in_date': '2025-01-01'})
    assert antwort.status_code == 201, antwort.get_json()
    neu_id = antwort.get_json()['id']
    assert neu_id == d['mieter'].id + 1  # SQLite vergibt die freie Nummer

    gelesen = auth_client.get(f'/api/tenants/{neu_id}/profiles')
    assert gelesen.status_code == 200
    assert gelesen.get_json() == {}, (
        f'Der neue Mieter erbt fremde Kostenprofile: {gelesen.get_json()}')


def test_abgewiesene_anfrage_laesst_vorhandene_profile_stehen(auth_client, app_ctx):
    d = _haus_mit_mieter()
    mieter = d['mieter']

    auth_client.post(f'/api/tenants/{mieter.id + 1}/profiles',
                     json={str(d['grundsteuer'].id): 'ignoriert'})

    gelesen = auth_client.get(f'/api/tenants/{mieter.id}/profiles')
    assert gelesen.status_code == 200
    assert gelesen.get_json() == {str(d['grundsteuer'].id): 'qm'}


def test_profile_lesen_fuer_unbekannten_mieter_ist_404(auth_client, app_ctx):
    _haus_mit_mieter()

    antwort = auth_client.get('/api/tenants/9999/profiles')

    assert antwort.status_code == 404


# --------------------------------------------------------------------------
# Gegenproben: für vorhandene Mieter bleibt alles, wie es war
# --------------------------------------------------------------------------


def test_profile_fuer_vorhandenen_mieter_werden_gespeichert(auth_client, app_ctx):
    d = _haus_mit_mieter()
    mieter = d['mieter']
    gs, hw = str(d['grundsteuer'].id), str(d['hauswart'].id)

    antwort = auth_client.post(f'/api/tenants/{mieter.id}/profiles',
                               json={gs: 'direkt', hw: 'ignoriert'})
    assert antwort.status_code == 200, antwort.get_json()

    gelesen = auth_client.get(f'/api/tenants/{mieter.id}/profiles')
    assert gelesen.status_code == 200
    assert gelesen.get_json() == {gs: 'direkt', hw: 'ignoriert'}


def test_ungueltige_art_bleibt_400_und_loescht_nichts(auth_client, app_ctx):
    d = _haus_mit_mieter()
    mieter = d['mieter']

    antwort = auth_client.post(f'/api/tenants/{mieter.id}/profiles',
                               json={str(d['hauswart'].id): 'erfunden'})
    assert antwort.status_code == 400

    gelesen = auth_client.get(f'/api/tenants/{mieter.id}/profiles')
    assert gelesen.get_json() == {str(d['grundsteuer'].id): 'qm'}


def test_mieter_loeschen_raeumt_seine_profile_ab(auth_client, app_ctx):
    d = _haus_mit_mieter()
    mieter_id = d['mieter'].id
    assert _profilzeilen(mieter_id) == 1

    antwort = auth_client.delete(f'/api/tenants/{mieter_id}')
    assert antwort.status_code == 200, antwort.get_json()

    assert _profilzeilen(mieter_id) == 0
