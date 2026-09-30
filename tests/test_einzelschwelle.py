"""Die harte Abdeckungsschwelle je Datei (NK-032).

Die Karte verspricht dreierlei: dass ``auth.py`` und ``backup.py`` je eine
eigene 90-Prozent-Marke haben, dass ``make check`` durchfaellt, wenn eine
darunter liegt, und dass beide heute darueber liegen.

Der dritte Punkt braucht keinen Test -- ``make check`` misst ihn bei jedem
Lauf selbst, das ist ja der Sinn der Karte. Was hier geprueft wird, ist das,
was ein Lauf **nicht** zeigt: dass ein Unterschreiten tatsaechlich in einem
Fehlschlag endet. Solange nichts unterschreitet, sieht eine kaputte Schwelle
genauso aus wie eine funktionierende.
"""

import importlib.util
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent


def _laden():
    """scripts/ liegt nicht im Importpfad -- die Datei direkt laden.

    Sie dort hineinzunehmen waere der groessere Eingriff: ``scripts`` ist
    Werkzeug rund um das Projekt, kein Teil der Anwendung, und steht deshalb
    auch in der omit-Liste von coverage.
    """
    pfad = WURZEL / 'scripts' / 'einzelschwelle.py'
    spec = importlib.util.spec_from_file_location('einzelschwelle', pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


einzelschwelle = _laden()


# --- Akzeptanzpunkt 1: die Regeln stehen da, wo die Karte sie verlangt -------

def test_beide_dateien_haben_eine_eigene_schwelle():
    regeln = einzelschwelle.regeln_lesen()
    assert regeln['nebenkostenfix/auth.py'] == 90
    assert regeln['nebenkostenfix/backup.py'] == 90


def test_die_projektschwelle_bleibt_daneben_bestehen():
    """Die Einzelregel ersetzt die gestaffelte Projektschwelle nicht.

    Beides zusammen ist der Punkt: die eine haelt das Ganze in Bewegung, die
    andere haelt zwei Dateien fest.
    """
    text = (WURZEL / 'pyproject.toml').read_text(encoding='utf-8')
    assert '[tool.coverage.report]' in text
    assert 'fail_under = 55' in text


# --- Die Entscheidung, mit erfundenen Zahlen --------------------------------

def test_darueber_haelt():
    zeilen = einzelschwelle.bewerten({'auth.py': 98.77}, {'auth.py': 90.0})
    assert zeilen == [('auth.py', 98.77, 90.0, True)]


def test_darunter_haelt_nicht():
    zeilen = einzelschwelle.bewerten({'auth.py': 89.99}, {'auth.py': 90.0})
    assert zeilen[0][3] is False


def test_genau_auf_der_marke_haelt():
    """90,0 ist nicht weniger als 90 -- die Grenze gehoert noch dazu."""
    zeilen = einzelschwelle.bewerten({'auth.py': 90.0}, {'auth.py': 90.0})
    assert zeilen[0][3] is True


def test_knapp_darunter_wird_nicht_aufgerundet():
    """89,97 Prozent sind ein Durchfall, auch wenn der Report '90%' anzeigt.

    coverage rundet in seiner Tabelle auf ganze Prozent. Wer sich darauf
    verliesse, haette eine Schwelle, die ein halbes Prozent Rueckfall
    durchwinkt.
    """
    zeilen = einzelschwelle.bewerten({'backup.py': 89.97}, {'backup.py': 90.0})
    assert zeilen[0][3] is False


def test_gar_nicht_gemessen_gilt_als_durchgefallen():
    """Eine Datei ohne Messwert ist der vollstaendige Rueckfall, nicht 'egal'."""
    zeilen = einzelschwelle.bewerten({'auth.py': None}, {'auth.py': 90.0})
    assert zeilen[0][3] is False


def test_jede_regel_kommt_in_der_ausgabe_vor():
    """Auch eine Datei, zu der gar keine Messung vorliegt, fehlt nicht."""
    zeilen = einzelschwelle.bewerten({}, {'auth.py': 90.0, 'backup.py': 90.0})
    assert [z[0] for z in zeilen] == ['auth.py', 'backup.py']


# --- Akzeptanzpunkt 2: ein Unterschreiten endet wirklich im Fehlschlag ------

def _pyproject_mit(inhalt: str, tmp_path: Path) -> Path:
    pfad = tmp_path / 'pyproject.toml'
    pfad.write_text(inhalt, encoding='utf-8')
    return pfad


def test_main_meldet_fehlschlag_wenn_eine_datei_faellt(tmp_path, capsys):
    pfad = _pyproject_mit(
        '[tool.nk.einzelschwelle]\n"auth.py" = 90\n"backup.py" = 90\n', tmp_path)
    schluss = einzelschwelle.main(
        pyproject=pfad,
        messer=lambda regeln: {'auth.py': 98.7, 'backup.py': 61.0},
    )
    assert schluss == 1
    ausgabe = capsys.readouterr().out
    assert 'FEHL' in ausgabe
    assert 'backup.py' in ausgabe


def test_main_ist_zufrieden_wenn_beide_halten(tmp_path, capsys):
    pfad = _pyproject_mit(
        '[tool.nk.einzelschwelle]\n"auth.py" = 90\n"backup.py" = 90\n', tmp_path)
    schluss = einzelschwelle.main(
        pyproject=pfad,
        messer=lambda regeln: {'auth.py': 98.7, 'backup.py': 94.4},
    )
    assert schluss == 0
    assert 'FEHL' not in capsys.readouterr().out


def test_ohne_regeln_faellt_nichts_durch(tmp_path):
    """Eine leere Tabelle ist kein Fehler, sondern nur nichts zu tun."""
    pfad = _pyproject_mit('[tool.nk]\n', tmp_path)
    assert einzelschwelle.main(pyproject=pfad, messer=lambda r: {}) == 0


# --- Akzeptanzpunkt 2, zweite Haelfte: make check ruft das auch auf ---------

def test_make_check_ruft_die_schwelle_auf():
    """Ohne diese Zeile im Makefile waere die ganze Pruefung tote Konfiguration."""
    makefile = (WURZEL / 'Makefile').read_text(encoding='utf-8')
    zeile = [z for z in makefile.splitlines()
             if z.strip().startswith('$(MAKE) install-dev')]
    assert zeile, 'Das Ziel check ruft install-dev nicht mehr auf.'
    assert 'schwelle' in zeile[0], (
        'make check laeuft ohne den Schwellenschritt — die Einzelregel '
        'waere damit unverbindlich.')


def test_das_schwellenziel_startet_das_skript():
    makefile = (WURZEL / 'Makefile').read_text(encoding='utf-8')
    assert 'scripts/einzelschwelle.py' in makefile


@pytest.mark.parametrize('name', ['nebenkostenfix/auth.py', 'nebenkostenfix/backup.py'])
def test_die_genannten_dateien_gibt_es_wirklich(name):
    """Ein Tippfehler im Dateinamen waere eine Schwelle, die nie greift."""
    assert (WURZEL / name).exists()
