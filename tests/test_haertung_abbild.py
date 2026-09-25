"""NK-076: Härtungs-Checkliste des Produktionsbuilds (F-58).

Liest Dockerfile, Einstieg und Compose-Datei. Die CI faehrt dieselbe Liste
bei jedem Push; ein Rueckfall (root, Tag ohne Digest, zwei Worker auf
SQLite, .env-Pflicht) wird rot, bevor ein Abbild entsteht.
"""

import os
import re
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
DOCKERFILE = (WURZEL / 'Dockerfile').read_text(encoding='utf-8')
EINSTIEG = (WURZEL / 'docker-entrypoint.sh').read_text(encoding='utf-8')
COMPOSE = (WURZEL / 'docker-compose.yml').read_text(encoding='utf-8')


def test_basisabbild_mit_digest():
    von = re.search(r'^FROM\s+(\S+)', DOCKERFILE, re.M).group(1)
    assert re.fullmatch(r'python:3\.11-slim@sha256:[0-9a-f]{64}', von), von


def test_anwendung_laeuft_nicht_als_root():
    assert 'useradd --system' in DOCKERFILE
    assert 'setpriv --reuid="$PUID" --regid="$PGID" --clear-groups' in EINSTIEG
    assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in DOCKERFILE


def test_ein_worker_mit_threads():
    cmd = DOCKERFILE[DOCKERFILE.index('\nCMD ['):]
    assert '--workers 1 ' in cmd and '--threads ' in cmd


def test_healthcheck_und_datenvolume():
    assert 'HEALTHCHECK' in DOCKERFILE
    assert 'VOLUME ["/data"]' in DOCKERFILE
    assert 'DATA_DIR=/data' in DOCKERFILE


def test_healthcheck_folgt_dem_port(tmp_path):
    """Dev (6061) und Abgleich (6062) binden gunicorn auf FLASK_PORT; ein fest
    verdrahtetes 6060 meldete sie als "unhealthy" (Fund nach 0.9.1)."""
    zeile = DOCKERFILE[DOCKERFILE.index('HEALTHCHECK'):].split('\n\n')[0]
    assert 'FLASK_PORT' in zeile
    assert 'healthcheck:' not in COMPOSE  # kein zweiter, fest verdrahteter
    code = re.search(r'"-c", "(.*)"\]', zeile).group(1)

    class Gesund(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == '/api/health' else 404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Gesund)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        umgebung = dict(os.environ, FLASK_PORT=str(server.server_port))
        assert subprocess.run([sys.executable, '-c', code], env=umgebung,
                              timeout=10).returncode == 0
    finally:
        server.shutdown()


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX-Shell')
def test_startbefehl_bindet_denselben_port_wie_der_healthcheck():
    """Der Healthcheck folgt FLASK_PORT; bindet gunicorn fest auf 6060, meldet
    Docker jeden Container mit anderem FLASK_PORT als "unhealthy" (Copilot-Review 0.9.2)."""
    befehl = re.search(r'^CMD \["sh", "-c", "exec (gunicorn [^"]+)"\]', DOCKERFILE, re.M).group(1)
    for port, erwartet in (('7123', '0.0.0.0:7123'), (None, '0.0.0.0:6060')):
        umgebung = {k: v for k, v in os.environ.items() if k != 'FLASK_PORT'}
        if port:
            umgebung['FLASK_PORT'] = port
        ausgabe = subprocess.run(['sh', '-c', f'echo {befehl}'], env=umgebung,
                                 capture_output=True, text=True, check=True).stdout
        assert f'--bind {erwartet} ' in ausgabe, ausgabe


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX-Einstieg')
def test_einstieg_prueft_den_inhalt_nicht_nur_den_ordner(tmp_path):
    """Nach einem Update von einem root-Container gehören Datenbank und Belege
    root, der Ordner selbst vielleicht nicht -- der Einstieg muss auf den
    Inhalt sehen (Fund nach 0.9.1). Ohne root nachgestellt: eine Datei mit
    fremder Gruppe, id/chown/setpriv als Attrappen."""
    eigene = os.getegid()
    fremde = next((g for g in os.getgroups() if g != eigene), None)
    if fremde is None:
        pytest.skip('Nutzer hat keine zweite Gruppe')
    daten = tmp_path / 'data'
    daten.mkdir()
    datei = daten / 'nebenkosten.db'
    datei.write_text('x')
    os.chown(datei, -1, fremde)
    attrappen = tmp_path / 'bin'
    attrappen.mkdir()
    protokoll = tmp_path / 'chown.log'
    for name, rumpf in (('id', 'echo 0'), ('chown', f'echo "$@" >> {protokoll}'),
                        ('setpriv', 'exit 0')):
        (attrappen / name).write_text(f'#!/bin/sh\n{rumpf}\n')
        (attrappen / name).chmod(0o755)

    def starten():
        umgebung = dict(os.environ, PATH=f'{attrappen}:{os.environ["PATH"]}',
                        DATA_DIR=str(daten), PUID=str(os.geteuid()), PGID=str(eigene))
        return subprocess.run(['sh', str(WURZEL / 'docker-entrypoint.sh'), 'true'],
                              env=umgebung, capture_output=True, text=True, timeout=10)

    assert starten().returncode == 0
    assert f'-R {os.geteuid()}:{eigene} {daten}' in protokoll.read_text()
    protokoll.unlink()
    os.chown(datei, -1, eigene)
    assert starten().returncode == 0
    assert not protokoll.exists()  # alles passt: kein chown bei jedem Start


def test_keine_env_pflicht_und_kein_secret_im_abbild():
    assert 'env_file' not in COMPOSE
    assert '.env' not in DOCKERFILE.split('COPY . .')[0].replace('.env-', '')
    dockerignore = (WURZEL / '.dockerignore').read_text(encoding='utf-8')
    assert re.search(r'^\.env$', dockerignore, re.M)
    assert re.search(r'^debug_routen\.py$', dockerignore, re.M)


def test_ohne_apt_schicht():
    assert 'apt-get' not in DOCKERFILE


def test_compose_nennt_das_registry_abbild():
    assert 'image: ghcr.io/nerbry72/nebenkostenfix:' in COMPOSE


def test_sqlite_laeuft_im_wal_modus(app_ctx):
    from sqlalchemy import text

    from models import db
    with db.engine.connect() as verbindung:
        modus = verbindung.execute(text('PRAGMA journal_mode')).scalar()
        warten = verbindung.execute(text('PRAGMA busy_timeout')).scalar()
    assert modus == 'wal'
    assert warten >= 5000


def test_einspielen_verwirft_das_alte_journal(tmp_path):
    """Nach dem Austausch der Datei duerfen -wal/-shm der alten nicht bleiben."""
    quelle = (WURZEL / 'backup.py').read_text(encoding='utf-8')
    rumpf = quelle[quelle.index('def _einspielen_klartext'):]
    assert "('-wal', '-shm')" in rumpf
