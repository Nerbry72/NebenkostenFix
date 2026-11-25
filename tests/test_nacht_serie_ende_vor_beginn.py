"""Zahlungen: eine Serie, die vor ihrem Beginn endet.

POST /api/payments mit is_recurring prüft nicht, ob end_date vor
payment_date liegt. Die Schleife legt dann keine einzige Zahlung an, die
Antwort meldet trotzdem 201 "0 Zahlungen erfolgreich erfasst" -- und bei
einer Nebenkostenvorauszahlung hinterlegt sie den Betrag dennoch als Soll
(R-VZ-02 Punkt 1). Ab diesem Stichtag zählt jeder Monat ohne Zahlung als
Rückstand, obwohl nichts gebucht ist: ein Vertipper beim Enddatum erzeugt
einen Rückstand und eine Zahlungserinnerung.

Erwartet: die Eingabe wird am Feld end_date abgewiesen, nichts wird
angelegt. Alle Werte sind erfunden.
"""

from __future__ import annotations

from datetime import date

from nebenkostenfix.models import Payment, VorauszahlungSoll, db
from tests import billing_factories as f


def test_serie_mit_ende_vor_beginn_wird_abgewiesen(auth_client, app_ctx):
    haus = f.house('Testhaus Nacht')
    mieter = f.tenant(f.apt(haus, 'DG', 40), 'Mieterin Test', date(2024, 1, 1))
    db.session.commit()

    antwort = auth_client.post('/api/payments', data={
        'tenant_id': str(mieter.id), 'amount': '110.00',
        'payment_date': '2024-06-01', 'end_date': '2024-01-01',
        'is_recurring': 'true', 'type': 'Nebenkostenvorauszahlung'})

    angelegt = (Payment.query.filter_by(tenant_id=mieter.id).count(),
                VorauszahlungSoll.query.filter_by(tenant_id=mieter.id).count())
    assert antwort.status_code == 400, (
        f'Serie mit Ende vor Beginn angenommen ({antwort.status_code}, '
        f'{antwort.get_json()}); angelegt (Zahlungen, Soll): {angelegt}')
    assert antwort.get_json().get('feld') == 'end_date'
    assert angelegt == (0, 0)
