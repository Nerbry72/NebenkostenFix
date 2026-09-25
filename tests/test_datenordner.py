"""NK-132: ein Datenordner DATA_DIR (E-2 → D-90, F-61)."""

from pathlib import Path

import pytest

import datenordner


@pytest.fixture
def sauber(monkeypatch):
    for name in ('DATA_DIR', 'DATABASE_URL', 'NAS_MOUNT_PATH'):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_data_dir_bestimmt_alles(sauber, tmp_path):
    sauber.setenv('DATA_DIR', str(tmp_path / 'daten'))
    assert datenordner.datenordner() == tmp_path / 'daten'
    assert datenordner.datenbank_url() == f"sqlite:///{tmp_path / 'daten' / 'nebenkosten.db'}"
    assert datenordner.belegordner() == tmp_path / 'daten' / 'belege'
    assert datenordner.sicherungsordner() == tmp_path / 'daten' / 'backups'
    datenordner.anlegen()
    for teil in ('belege', 'backups'):
        assert (tmp_path / 'daten' / teil).is_dir()


def test_database_url_bleibt_vorrangig(sauber, tmp_path):
    sauber.setenv('DATA_DIR', str(tmp_path))
    sauber.setenv('DATABASE_URL', 'postgresql://nk@db/nk')
    assert datenordner.datenbank_url() == 'postgresql://nk@db/nk'
    assert datenordner.datenordner() == tmp_path


def test_uebergang_ohne_data_dir(sauber, tmp_path):
    """Eine Version lang: Ordner der SQLite-Datei, NAS_MOUNT_PATH als Alias."""
    sauber.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/alt/nebenkosten.db')
    assert datenordner.datenordner() == tmp_path / 'alt'
    assert datenordner.belegordner() == tmp_path / 'alt' / 'belege'
    (tmp_path / 'mnt').mkdir()
    sauber.setenv('NAS_MOUNT_PATH', str(tmp_path / 'mnt'))
    assert datenordner.belegordner() == tmp_path / 'mnt'
    assert 'NAS_MOUNT_PATH' in datenordner.veraltete_variablen()


def test_verwaister_nas_pfad_wird_ignoriert(sauber, tmp_path):
    """Alte .env mit NAS_MOUNT_PATH, neue Compose-Datei ohne /mnt-Einbindung:
    der Start brach mit PermissionError ab (Fund nach 0.9.1)."""
    gesperrt = tmp_path / 'gesperrt'
    gesperrt.mkdir(mode=0o500)
    sauber.setenv('DATA_DIR', str(tmp_path / 'daten'))
    sauber.setenv('NAS_MOUNT_PATH', str(gesperrt / 'nas' / 'belege'))
    assert datenordner.belegordner() == tmp_path / 'daten' / 'belege'
    assert datenordner.verwaister_nas_pfad() == str(gesperrt / 'nas' / 'belege')
    datenordner.anlegen()
    assert (tmp_path / 'daten' / 'belege').is_dir()


def test_ohne_jeden_hinweis_bricht_ab(sauber):
    with pytest.raises(datenordner.DatenordnerFehler, match='DATA_DIR'):
        datenordner.datenordner()


def test_die_ablage_folgt_dem_datenordner(sauber, tmp_path):
    from ablage import Ablage
    sauber.setenv('DATA_DIR', str(tmp_path))
    assert Ablage().wurzel == str(tmp_path / 'belege')


def test_kein_nas_sonderweg_mehr():
    wurzel = Path(__file__).resolve().parents[1]
    assert not (wurzel / 'docker-compose.cifs.yml').exists()
    compose = (wurzel / 'docker-compose.yml').read_text(encoding='utf-8')
    assert 'DATA_DIR=/data' in compose and 'NAS_MOUNT_PATH' not in compose
    assert './daten:/data' in compose
    env = (wurzel / '.env.example').read_text(encoding='utf-8')
    assert 'NAS_HOST=' not in env and 'NAS_PASSWORD=' not in env


def test_meldungen_ohne_nas():
    """F-61: in Meldungen an den Nutzer steht kein „NAS“ mehr."""
    import re
    wurzel = Path(__file__).resolve().parents[1]
    js = (wurzel / 'static' / 'app.js').read_text(encoding='utf-8')
    app = (wurzel / 'app.py').read_text(encoding='utf-8')
    assert not re.search(r"(showError|showSuccess)\([^)]*NAS", js)
    assert 'auf dem NAS' not in app and 'auf der NAS' not in app
