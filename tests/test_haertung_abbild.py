"""NK-076: Härtungs-Checkliste des Produktionsbuilds (F-58).

Liest Dockerfile, Einstieg und Compose-Datei. Die CI faehrt dieselbe Liste
bei jedem Push; ein Rueckfall (root, Tag ohne Digest, zwei Worker auf
SQLite, .env-Pflicht) wird rot, bevor ein Abbild entsteht.
"""

import re
from pathlib import Path

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
    cmd = DOCKERFILE[DOCKERFILE.index('CMD ['):]
    assert '"--workers", "1"' in cmd and '"--threads"' in cmd


def test_healthcheck_und_datenvolume():
    assert 'HEALTHCHECK' in DOCKERFILE
    assert 'VOLUME ["/data"]' in DOCKERFILE
    assert 'DATA_DIR=/data' in DOCKERFILE


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
