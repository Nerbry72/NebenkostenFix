"""Angemeldet bleiben in der Desktop-App (#52): Geraetetokens.

Im Servermodus meldet sich die Desktop-App an wie ein Browser, und die
Sitzung endet mit der App oder nach der Leerlauf-Grenze. Auf dem eigenen
Rechner ist das unbequem. Mit dem Haekchen „Angemeldet bleiben“ bekommt die
App ein Geraetetoken, das nur im Schluesselbund des Rechners liegt.

Der Ablauf, damit das Token nie in einer Adresse oder im Fenster steht:

1. Anmeldung mit Haekchen: der Server legt das Geraet an, bindet die
   Sitzung daran und haengt an das Ziel einen Abholcode (``?geraet=``,
   einmalig, eine Minute gueltig). Die App sieht ihn beim Laden und tauscht
   ihn per ``POST /api/geraete/abholen`` gegen das Token. Holt sie es nicht
   ab, verschwindet das Geraet mit dem Code wieder.
2. Start und Ablauf der Leerlauf-Grenze: ``POST /api/geraete/erneuern`` gibt
   ein neues Token und einen Einmalcode; ``GET /geraete/anmelden?code=``
   beginnt damit die Sitzung im Fenster. Die Leerlauf-Grenze bleibt, der
   Server braucht keine Ausnahme (Vorgabe des Maintainers in #52).
3. Jede Erneuerung ersetzt das Token (Rotation). Taucht ein ersetztes wieder
   auf, ist es kopiert worden: das Geraet ist abgemeldet (RFC 9700, 4.14.2).

Wie bei den Zugriffsschluesseln nur SHA-256 in der Datenbank, und falsche
Tokens oder Codes zaehlen im Anmeldeschutz. Die Routen zum Abholen,
Erneuern, Widerrufen und Anmelden stehen nicht in ``PUBLIC_ENDPOINTS``:
``auth._require_login`` laesst sie nur mit ihrem Ausweis (``AUSWEIS``)
durch, ob der stimmt, prueft die Route selbst.

Den Weg bietet der Server nur der App an (``APP_KENNUNG`` im User-Agent);
im Browser und unter Docker aendert sich nichts. Die Kennung ist kein
Schutz, nur ein Hinweis, ob das Haekchen Sinn ergibt.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import (has_request_context, jsonify, make_response, redirect, request,
                   session, url_for)

from nebenkostenfix import anmeldeschutz, zeit
from nebenkostenfix.models import Geraet, GeraetCode, GeraetErsetzt, User, db

PRAEFIX = 'nkg_'
APP_KENNUNG = 'NebenkostenFix-Desktop/'
SITZUNG_KEY = 'geraet'
ADRESS_PARAMETER = 'geraet'
CODE_GUELTIG_S = 60
OHNE_NUTZUNG = timedelta(days=30)
HOECHSTENS = 10
NAME_OHNE = 'Rechner ohne Namen'

# Route -> Feld, in dem sie ihren Ausweis mitbringt (GET: Adresse, sonst JSON).
AUSWEIS = {
    'geraet_abholen': 'code',
    'geraet_erneuern': 'token',
    'geraet_widerrufen': 'token',
    'geraet_anmelden': 'code',
}


def aus_der_app() -> bool:
    return has_request_context() and APP_KENNUNG in request.headers.get('User-Agent', '')


def ausweis() -> str | None:
    """Code oder Token der laufenden Anfrage, falls die Route einen kennt."""
    feld = AUSWEIS.get(request.endpoint)
    if feld is None:
        return None
    if request.method == 'GET':
        quelle = request.args
    else:
        quelle = request.get_json(silent=True)
        if not isinstance(quelle, dict):
            return None
    wert = quelle.get(feld)
    return wert if isinstance(wert, str) and wert else None


def _hash(wert: str) -> str:
    return hashlib.sha256(wert.encode()).hexdigest()


def _code_anlegen(zweck: str, geraet_id: int) -> str:
    code = secrets.token_urlsafe(24)
    db.session.add(GeraetCode(
        hash=_hash(code), zweck=zweck, geraet_id=geraet_id,
        gueltig_bis=zeit.jetzt_utc() + timedelta(seconds=CODE_GUELTIG_S)))
    return code


def _code_einloesen(roh: str, zweck: str) -> GeraetCode | None:
    """Der gueltige Code, schon geloescht (einmalig), sonst None."""
    if not roh or len(roh) > 100:
        return None
    # Abfrage statt session.get: die Massenloeschungen hier gehen am
    # Identity Map vorbei, ein dort liegengebliebener Code gaelte sonst noch.
    zeile = GeraetCode.query.filter_by(hash=_hash(roh)).first()
    if zeile is None or zeile.zweck != zweck:
        return None
    db.session.delete(zeile)
    if zeile.gueltig_bis < zeit.jetzt_utc():
        return None
    return zeile


def anmelden_mit_haekchen(user: User) -> str:
    """Nach der Anmeldung mit Haekchen: legt das Geraet an, bindet die
    laufende Sitzung daran und liefert den Code, den die App abholt.

    Gleich hier und nicht erst beim Abholen, das ohne das Cookie des Fensters
    kommt: sonst wuesste diese Sitzung nicht, zu welchem Geraet sie gehoert,
    und „Abmelden“ liesse das Token gueltig. Bis zum Abholen steht ein
    Zufallshash da, zu dem es kein Token gibt.
    """
    _aufraeumen()
    _platz_machen(user.id)
    geraet = Geraet(user_id=user.id, name=NAME_OHNE,
                    hash=_hash(PRAEFIX + secrets.token_urlsafe(32)))
    db.session.add(geraet)
    db.session.flush()
    code = _code_anlegen('abholen', geraet.id)
    session[SITZUNG_KEY] = geraet.id
    db.session.commit()
    return code


def ziel_mit_abholcode(ziel: str, code: str) -> str:
    # Ein alter Code fliegt raus: die Oberfläche lässt ihn in der Adresse
    # stehen, und nach einem 401 kommt er mit dem Ziel zurück.
    teile = urlsplit(ziel)
    paare = [(k, v) for k, v in parse_qsl(teile.query, keep_blank_values=True)
             if k != ADRESS_PARAMETER]
    return urlunsplit(teile._replace(query=urlencode(paare + [(ADRESS_PARAMETER, code)])))


def _geraet_zum_token(roh: str) -> Geraet | None:
    if not roh.startswith(PRAEFIX) or len(roh) > 100:
        return None
    return Geraet.query.filter_by(hash=_hash(roh)).first()


def _ersetzt(roh: str) -> GeraetErsetzt | None:
    if not roh.startswith(PRAEFIX) or len(roh) > 100:
        return None
    return GeraetErsetzt.query.filter_by(hash=_hash(roh)).first()


def loeschen(ids) -> int:
    """Meldet Geraete ab: Token, ersetzte Tokens und offene Codes."""
    ids = list(ids)
    if not ids:
        return 0
    GeraetErsetzt.query.filter(GeraetErsetzt.geraet_id.in_(ids)).delete(
        synchronize_session=False)
    GeraetCode.query.filter(GeraetCode.geraet_id.in_(ids)).delete(
        synchronize_session=False)
    return Geraet.query.filter(Geraet.id.in_(ids)).delete(synchronize_session=False)


def fuer_konto_loeschen(user_id: int) -> int:
    """Passwortwechsel, Stilllegen: alle Geraete des Kontos abmelden (#52).
    Der Aufrufer committet, zusammen mit seiner eigenen Aenderung."""
    ids = [z.id for z in db.session.query(Geraet.id).filter_by(user_id=user_id)]
    return loeschen(ids)


def alle_loeschen() -> None:
    """Anmeldung ausschalten, Sicherung einspielen: kein Geraet bleibt."""
    GeraetCode.query.delete()
    GeraetErsetzt.query.delete()
    Geraet.query.delete()


def sitzung_gilt(user_id: int) -> bool:
    """Eine Sitzung, die mit einem Geraet begann, endet mit dessen Abmeldung.
    Die Nummern vergibt SQLite nie zweimal (AUTOINCREMENT); das Konto muss
    trotzdem passen."""
    geraet_id = session.get(SITZUNG_KEY)
    if geraet_id is None:
        return True
    geraet = Geraet.query.filter_by(id=geraet_id).first()
    return geraet is not None and geraet.user_id == user_id


def _aufraeumen() -> None:
    jetzt = zeit.jetzt_utc()
    abgelaufen = GeraetCode.query.filter(GeraetCode.gueltig_bis < jetzt)
    # Ein Geraet, dessen Abholcode ungenutzt ablief, hat nie ein Token
    # bekommen.
    loeschen([z.geraet_id for z in abgelaufen.filter_by(zweck='abholen')])
    abgelaufen.delete(synchronize_session=False)
    # 30 Tage ohne Nutzung: abgemeldet. Hier und nicht erst beim Erneuern,
    # denn ein verlorener Rechner meldet sich nie wieder und stuende sonst
    # fuer immer in der Liste.
    loeschen([z.id for z in db.session.query(Geraet.id).filter(
        Geraet.zuletzt_benutzt_am < jetzt - OHNE_NUTZUNG)])
    # Ersetzte Tokens nur 30 Tage: ohne Grenze wuechse die Tabelle mit jedem
    # Start. Eine Kopie, die erst danach wieder auftaucht, zaehlt nur noch
    # als Fehlversuch; das Geraet selbst bleibt dann angemeldet.
    GeraetErsetzt.query.filter(GeraetErsetzt.ersetzt_am < jetzt - OHNE_NUTZUNG).delete(
        synchronize_session=False)


def _platz_machen(user_id: int) -> None:
    """Hoechstens HOECHSTENS je Konto: das am laengsten unbenutzte faellt weg.
    Wer sich oft neu mit Haekchen anmeldet, sammelt sonst Leichen."""
    zuviel = Geraet.query.filter_by(user_id=user_id).count() - HOECHSTENS + 1
    if zuviel > 0:
        alte = (db.session.query(Geraet.id).filter_by(user_id=user_id)
                .order_by(Geraet.zuletzt_benutzt_am).limit(zuviel))
        loeschen([z.id for z in alte])


def _name(roh) -> str:
    name = ' '.join(roh.split())[:60] if isinstance(roh, str) else ''
    return name or NAME_OHNE


def _zaehlen(ordner, roh: str) -> int:
    """Ein Fehlversuch im Anmeldeschutz, mit eigenem Topf wie bei den
    Zugriffsschluesseln (Merkmal und Adresse). Liefert die Restsperre in
    Sekunden, 0 wenn nicht gesperrt."""
    adresse = f'geraet@{request.remote_addr}'
    merkmal = f'geraet:{roh[:12]}'
    rest = anmeldeschutz.gesperrt_fuer(ordner, merkmal, adresse)
    if rest:
        return rest
    anzahl = anmeldeschutz.fehlversuch(ordner, merkmal, adresse)
    time.sleep(anmeldeschutz.wartezeit(anzahl))
    return 0


def _abgelehnt(ordner, roh: str):
    rest = _zaehlen(ordner, roh)
    if rest:
        minuten = max(1, (rest + 59) // 60)
        antwort = make_response(jsonify({
            'error': f'Zu viele Fehlversuche. Bitte warten Sie {minuten} Minuten.',
            'code': 'anmeldung_gesperrt'}), 429)
        antwort.headers['Retry-After'] = str(rest)
        return antwort
    return jsonify({
        'error': 'Diese Anmeldung gilt nicht mehr. Bitte melden Sie sich mit '
                 'Ihrem Passwort an.',
        'code': 'geraet_ungueltig'}), 401


def _zeile(geraet: Geraet, eigenes) -> dict:
    return {
        'id': geraet.id,
        'name': geraet.name,
        'konto': geraet.user.username if geraet.user else None,
        'angelegt_am': zeit.als_ortszeit(geraet.angelegt_am),
        'zuletzt_benutzt': zeit.als_ortszeit(geraet.zuletzt_benutzt_am),
        'dieses_geraet': geraet.id == eigenes,
    }


def init_geraete(app, sitzung_beginnen, sicheres_ziel, ohne_anmeldung_aktiv,
                 anmeldeschutz_ordner):
    """Die Routen. Die Helfer kommen aus ``auth`` herein, damit dieses Modul
    ``auth`` nicht importiert (auth importiert dieses)."""

    @app.route('/api/geraete/abholen', methods=['POST'])
    def geraet_abholen():
        """Der Abholcode gegen das Token. Das Token steht nur in dieser
        Antwort; die App legt es in den Schluesselbund."""
        roh = ausweis() or ''
        _aufraeumen()
        zeile = _code_einloesen(roh, 'abholen')
        geraet = db.session.get(Geraet, zeile.geraet_id) if zeile else None
        if geraet is None or not geraet.user.is_active:
            db.session.commit()
            return _abgelehnt(anmeldeschutz_ordner(), roh)
        token = PRAEFIX + secrets.token_urlsafe(32)
        geraet.hash = _hash(token)
        geraet.name = _name(request.get_json().get('name'))
        geraet.zuletzt_benutzt_am = zeit.jetzt_utc()
        db.session.commit()
        app.logger.info('Gerät „%s“ für Konto %s angemeldet.', geraet.name,
                        geraet.user.username)
        return jsonify({'id': geraet.id, 'name': geraet.name, 'token': token}), 201

    @app.route('/api/geraete/erneuern', methods=['POST'])
    def geraet_erneuern():
        """Neues Token gegen das alte, dazu der Einmalcode fuer die Sitzung."""
        roh = ausweis() or ''
        _aufraeumen()
        geraet = _geraet_zum_token(roh)
        if geraet is None:
            kopie = _ersetzt(roh)
            if kopie is not None:
                app.logger.warning(
                    'Ein schon ersetztes Gerätetoken wurde noch einmal benutzt, '
                    'vermutlich eine Kopie. Das Gerät ist abgemeldet.')
                loeschen([kopie.geraet_id])
            db.session.commit()
            return _abgelehnt(anmeldeschutz_ordner(), roh)
        if not geraet.user.is_active:
            db.session.commit()
            return _abgelehnt(anmeldeschutz_ordner(), roh)
        jetzt = zeit.jetzt_utc()
        token = PRAEFIX + secrets.token_urlsafe(32)
        db.session.add(GeraetErsetzt(hash=geraet.hash, geraet_id=geraet.id))
        geraet.hash = _hash(token)
        geraet.zuletzt_benutzt_am = jetzt
        code = _code_anlegen('anmelden', geraet_id=geraet.id)
        db.session.commit()
        return jsonify({'token': token, 'code': code}), 200

    @app.route('/api/geraete/widerrufen', methods=['POST'])
    def geraet_widerrufen():
        """„Abmelden“ in der App: lokal ist das Token schon geloescht. Die
        Antwort verraet nicht, ob es das Token gab."""
        roh = ausweis() or ''
        _aufraeumen()
        geraet = _geraet_zum_token(roh)
        kopie = _ersetzt(roh) if geraet is None else None
        geraet_id = geraet.id if geraet else (kopie.geraet_id if kopie else None)
        if geraet_id is not None:
            loeschen([geraet_id])
            db.session.commit()
            app.logger.info('Gerät in der App abgemeldet.')
        return jsonify({'status': 'abgemeldet'}), 200

    @app.route('/geraete/anmelden', methods=['GET'])
    def geraet_anmelden():
        """Der Einmalcode aus der Erneuerung beginnt die Sitzung im Fenster.
        Ein falscher fuehrt zur Anmeldung, mit demselben Ziel."""
        ziel = sicheres_ziel(request.args.get('next'))
        roh = ausweis()
        if roh is None:
            # Nur angemeldet erreichbar (sonst sperrt _require_login).
            return redirect(ziel)
        _aufraeumen()
        zeile = _code_einloesen(roh, 'anmelden')
        geraet = db.session.get(Geraet, zeile.geraet_id) if zeile else None
        if geraet is None or not geraet.user.is_active:
            db.session.commit()
            _zaehlen(anmeldeschutz_ordner(), roh)
            return redirect(url_for('login', next=ziel))
        sitzung_beginnen(geraet.user)
        session[SITZUNG_KEY] = geraet.id
        geraet.user.last_login_at = zeit.jetzt_utc()
        db.session.commit()
        return redirect(ziel)

    @app.route('/api/geraete', methods=['GET'])
    def geraete_auflisten():
        if ohne_anmeldung_aktiv(app):
            return jsonify([]), 200
        _aufraeumen()
        db.session.commit()
        eigenes = session.get(SITZUNG_KEY)
        eintraege = Geraet.query.order_by(Geraet.angelegt_am).all()
        return jsonify([_zeile(g, eigenes) for g in eintraege]), 200

    @app.route('/api/geraete/<int:id>', methods=['DELETE'])
    def geraet_abmelden(id):
        geraet = db.session.get(Geraet, id)
        if geraet is None:
            return jsonify({'error': 'Dieses Gerät gibt es nicht.'}), 404
        name = geraet.name
        loeschen([id])
        db.session.commit()
        app.logger.info('Gerät „%s“ in der Liste abgemeldet.', name)
        return jsonify({'status': 'abgemeldet'}), 200


__all__ = ['PRAEFIX', 'APP_KENNUNG', 'SITZUNG_KEY', 'AUSWEIS', 'aus_der_app', 'ausweis',
           'anmelden_mit_haekchen', 'ziel_mit_abholcode', 'loeschen', 'fuer_konto_loeschen',
           'alle_loeschen', 'sitzung_gilt', 'init_geraete']
