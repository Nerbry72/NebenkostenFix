"""Die Entwicklerroute -- eine Datei, die im Auslieferungsabbild fehlt (NK-040).

``POST /api/debug/reset_db`` leert die Datenbank und raeumt das Belegverzeichnis
leer. Sie existiert fuer die Entwicklung: ein Handgriff, und der Stapel steht
wieder auf dem leeren Bestand, ohne dass jemand Tabellen von Hand loescht.

Bis NK-040 stand sie mitten in ``app.py``, gesperrt durch zwei Riegel zur
Laufzeit: ein Flag ``ENABLE_DEBUG_RESET`` und ein Geheimnis im Kopf der
Anfrage (NK-001). Das ist ein guter Schutz und trotzdem der falsche. Ein Flag
ist eine Zeile in einer Umgebungsdatei; wer sie versehentlich setzt -- beim
Kopieren einer ``.env`` aus der Entwicklung etwa --, hat einen Endpunkt
scharf, der den ganzen Bestand loescht. R-DSGVO-01 verlangt darum nicht
"ausgeschaltet", sondern **"existiert nicht"**: was nicht im Abbild liegt,
laesst sich auch durch keine Fehlkonfiguration aufwecken.

Der Weg dahin ist die Datei selbst. ``.dockerignore`` nennt sie namentlich,
also kopiert ``COPY . .`` sie nicht ins Abbild. ``app.py`` versucht den Import
und faehrt ohne das Modul einfach weiter -- ohne Route, ohne Meldung, ohne
Unterschied im uebrigen Verhalten. Im Entwicklungsstapel liegt das
Arbeitsverzeichnis als Volume im Container, die Datei ist also da; genauso
haelt es das Projekt schon mit ``tests/``.

Die beiden Laufzeitriegel bleiben stehen. Sie sind jetzt der zweite Boden: wer
die Datei doch mitliefert, hat sie immer noch vor sich.

Geprueft in ``tests/test_produktionsbuild.py``.
"""

from __future__ import annotations

import os
import shutil

from flask import jsonify, request

from fehler import protokoll
from models import User, db


def _flag_gesetzt(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


def registriere(app, *, seed_database, nas_handler) -> None:
    """Haengt die Route an die Anwendung.

    ``seed_database`` und ``nas_handler`` kommen von aussen herein, statt aus
    ``app`` importiert zu werden: ein Import zurueck nach ``app.py`` waere
    zirkulaer, und dieses Modul soll ohne die Anwendung lesbar bleiben.
    """

    @app.route('/api/debug/reset_db', methods=['POST'])
    def reset_db():
        # NK-001: deny before drop_all / NAS wipe. Flag + secret are read per
        # request so tests can toggle env after import.
        if not _flag_gesetzt('ENABLE_DEBUG_RESET'):
            return jsonify({'error': 'Not found'}), 404
        expected = os.environ.get('DEBUG_RESET_SECRET', '')
        provided = request.headers.get('X-Debug-Secret', '')
        if not expected or provided != expected:
            return jsonify({'error': 'Unauthorized'}), 401

        # Anmeldekonten ueberleben den Reset (NK-019). drop_all() nimmt sonst
        # die Tabelle users mit und sperrt jeden aus, der die Anwendung gerade
        # nutzt. Die Ids werden mit uebernommen, damit laufende Sitzungen
        # gueltig bleiben.
        bewahrte_konten = [
            {
                'id': u.id,
                'username': u.username,
                'password_hash': u.password_hash,
                'is_active': u.is_active,
                'created_at': u.created_at,
                'last_login_at': u.last_login_at,
            }
            for u in User.query.all()
        ]
        db.drop_all()
        # drop_all() nimmt alembic_version nicht mit: die Tabelle gehoert
        # keinem Modell. Ohne das Zuruecksetzen haelt Alembic die jetzt leere
        # Datenbank fuer aktuell, upgrade() legt keine einzige Tabelle mehr an,
        # und der Reset laesst eine tote Instanz zurueck (NK-024).
        from flask_migrate import stamp as _stamp, upgrade as _upgrade
        _stamp(revision='base')
        _upgrade()
        for konto in bewahrte_konten:
            db.session.add(User(**konto))
        db.session.commit()
        seed_database()

        # Wipe the NAS directory safely
        try:
            if os.path.exists(nas_handler.nas_mount_path):
                # Only delete the contents, not the base mount folder itself to
                # avoid wiping wrong things
                for filename in os.listdir(nas_handler.nas_mount_path):
                    file_path = os.path.join(nas_handler.nas_mount_path, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception:
                        # Weiterraeumen statt abbrechen: eine Datei, die haengt,
                        # soll die uebrigen nicht stehen lassen. Was blieb, steht
                        # namentlich im Protokoll.
                        protokoll.exception(
                            'Beim Zuruecksetzen nicht loeschbar: %s', file_path)
        except Exception:
            protokoll.exception('NAS-Verzeichnis liess sich nicht zuruecksetzen')

        return jsonify({
            'message': 'Datenbank und alle im Belegordner gespeicherten Dateien '
                       'erfolgreich gelöscht.'
        }), 200
