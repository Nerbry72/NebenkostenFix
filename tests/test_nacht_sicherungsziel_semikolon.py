"""Sicherungsziel mit ';' im Ordnernamen überstand die INI nicht.

Unter Windows ist ';' in Ordnernamen erlaubt (z. B. „Sicherung;2026“).
``windows_ordner`` speichert die freigegebenen Sicherungsziele mit dem festen
Trenner ';' in einer Zeile und zerlegt sie beim Lesen wieder daran. Ein so
benannter Ordner, der im Dialog „Ordner auswählen“ freigegeben wurde
(desktop.Bruecke.ordner_waehlen), kommt nach dem Neustart als zwei falsche
Teilpfade zurück: der gewählte Ordner ist nicht mehr freigegeben, dafür gilt
ein abgeschnittener Pfad als erlaubte Wurzel.

In derselben Sitzung dasselbe: die Desktop-App gab ihre Ziele über
``BACKUP_ZIELE`` mit ``os.pathsep`` (unter Windows ';') an
``backup.erlaubte_wurzeln`` weiter. Jetzt nimmt sie ``NK_SICHERUNGSZIELE``,
ein Ziel je Zeile.

Nur fiktive Pfade unter ``tmp_path``, keine Datenbankinhalte.
"""

from __future__ import annotations

import configparser
import os
import sys
import types
from pathlib import Path

import pytest

import desktop
from nebenkostenfix import backup
from nebenkostenfix import windows_ordner


@pytest.fixture
def lokal(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    return tmp_path / 'lokal'


def _ini_von_hand(text: str) -> Path:
    datei = windows_ordner.einstellungen_datei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(text, encoding='utf-16')
    return datei


def _daten_schluessel(datei: Path) -> dict:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(datei.read_text(encoding='utf-16'))
    return dict(parser.items('Daten', raw=True)) if parser.has_section('Daten') else {}


def _real(pfad) -> Path:
    return Path(os.path.realpath(str(pfad)))


# --- INI: ein Schlüssel je Ziel --------------------------------------------

def test_sicherungsziel_mit_semikolon_bleibt_ein_ziel(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    ziel = str(tmp_path / 'Sicherung;2026')

    windows_ordner.einstellungen_schreiben(sicherungsziele=[ziel])
    gelesen = windows_ordner.einstellungen_lesen()['sicherungsziele']

    assert gelesen == [ziel], (
        f'Gespeichert wurde ein Ziel {ziel!r}, gelesen kommt {gelesen!r} zurück')


def test_zwei_ziele_eines_mit_semikolon(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lokal'))
    ziele = [str(tmp_path / 'USB-Stick'), str(tmp_path / 'Büro;Archiv')]

    windows_ordner.einstellungen_schreiben(sicherungsziele=ziele)
    gelesen = windows_ordner.einstellungen_lesen()['sicherungsziele']

    assert gelesen == ziele
    # Kein abgeschnittener Teilpfad darf als freigegebenes Ziel auftauchen.
    assert str(tmp_path / 'Büro') not in gelesen


def test_elf_ziele_kommen_in_der_reihenfolge_zurueck(lokal, tmp_path):
    """Sicherungsziel10 steht nach Sicherungsziel9, nicht nach Sicherungsziel1."""
    ziele = [str(tmp_path / f'Z{i}') for i in range(11)]

    windows_ordner.einstellungen_schreiben(sicherungsziele=ziele)

    assert windows_ordner.einstellungen_lesen()['sicherungsziele'] == ziele
    schluessel = _daten_schluessel(windows_ordner.einstellungen_datei())
    assert schluessel['sicherungsziel1'] == ziele[0]
    assert schluessel['sicherungsziel11'] == ziele[10]

    # Die Reihenfolge kommt aus der Nummer, nicht aus der Lage in der Datei.
    # Ein leerer Wert zählt nicht als Ziel.
    a, b, c = (str(tmp_path / n) for n in ('A', 'B', 'C;D'))
    _ini_von_hand(f'[Daten]\nSicherungsziel10 = {c}\nSicherungsziel2 = {b}\n'
                  f'Sicherungsziel3 =\nSicherungsziel1 = {a}\n')
    assert windows_ordner.einstellungen_lesen()['sicherungsziele'] == [a, b, c]


def test_altformat_wird_gelesen_und_beim_schreiben_ersetzt(lokal, tmp_path):
    a, b = str(tmp_path / 'A'), str(tmp_path / 'B')
    datei = _ini_von_hand(f'[Daten]\nSicherungsziele = {a};{b}\n')

    assert windows_ordner.einstellungen_lesen()['sicherungsziele'] == [a, b]

    windows_ordner.einstellungen_schreiben(sicherungsziele=[a, b])
    schluessel = _daten_schluessel(datei)
    assert 'sicherungsziele' not in schluessel
    assert schluessel == {'sicherungsziel1': a, 'sicherungsziel2': b}
    assert windows_ordner.einstellungen_lesen()['sicherungsziele'] == [a, b]


def test_altformat_gilt_nur_ohne_neue_schluessel(lokal, tmp_path):
    neu, alt = str(tmp_path / 'Neu;Ziel'), str(tmp_path / 'Alt')
    _ini_von_hand(f'[Daten]\nSicherungsziele = {alt}\nSicherungsziel1 = {neu}\n')

    assert windows_ordner.einstellungen_lesen()['sicherungsziele'] == [neu]


def test_andere_werte_bleiben_und_leere_liste_hinterlaesst_nichts(lokal, tmp_path):
    ordner = tmp_path / 'Dokumente' / 'NebenkostenFix'
    windows_ordner.einstellungen_schreiben(datenordner=ordner, onedrive_bestaetigt=True,
                                           server='https://nk.example')
    windows_ordner.einstellungen_schreiben(
        sicherungsziele=[str(tmp_path / 'Erst;Ziel'), str(tmp_path / 'Zweit')])
    windows_ordner.einstellungen_schreiben(sicherungsziele=[str(tmp_path / 'Nur;Eins')])

    gelesen = windows_ordner.einstellungen_lesen()
    assert gelesen['datenordner'] == str(ordner)
    assert gelesen['onedrive_bestaetigt'] is True
    assert gelesen['server'] == 'https://nk.example'
    assert gelesen['sicherungsziele'] == [str(tmp_path / 'Nur;Eins')]
    # Das zweite Ziel des vorigen Schreibens ist weg, nicht liegen geblieben.
    assert 'sicherungsziel2' not in _daten_schluessel(windows_ordner.einstellungen_datei())

    windows_ordner.einstellungen_schreiben(sicherungsziele=[])
    gelesen = windows_ordner.einstellungen_lesen()
    assert gelesen['sicherungsziele'] == []
    assert gelesen['datenordner'] == str(ordner)
    assert gelesen['onedrive_bestaetigt'] is True
    assert gelesen['server'] == 'https://nk.example'
    reste = [s for s in _daten_schluessel(windows_ordner.einstellungen_datei())
             if s.startswith('sicherungsziel')]
    assert reste == []


# --- Sitzung: NK_SICHERUNGSZIELE -------------------------------------------

def test_sitzungsziele_geben_den_ordner_mit_semikolon_frei(app_ctx, tmp_path, monkeypatch):
    usb, buero = tmp_path / 'USB-Stick', tmp_path / 'Büro;Archiv'
    monkeypatch.setenv('BACKUP_ZIELE', '')
    monkeypatch.setenv('NK_SICHERUNGSZIELE', f'{usb}\n {buero} \n\n{usb}\n')

    wurzeln = backup.erlaubte_wurzeln(app_ctx.app)

    assert _real(usb) in wurzeln and _real(buero) in wurzeln
    assert wurzeln.count(_real(usb)) == 1
    assert _real(tmp_path / 'Büro') not in wurzeln
    assert _real(Path.cwd() / 'Archiv') not in wurzeln
    assert backup._ziel_pruefen(app_ctx.app, buero) == _real(buero)
    with pytest.raises(backup.SicherungsFehler, match='nicht freigegeben'):
        backup._ziel_pruefen(app_ctx.app, tmp_path / 'Büro')


def test_backup_ziele_wirkt_daneben_wie_bisher(app_ctx, tmp_path, monkeypatch):
    nas, platte = tmp_path / 'nas', tmp_path / 'platte'
    gewaehlt = tmp_path / 'Sicherung;2026'
    monkeypatch.setenv('BACKUP_ZIELE', os.pathsep.join([str(nas), str(platte)]))
    monkeypatch.setenv('NK_SICHERUNGSZIELE', f'{gewaehlt}\n{nas}')

    wurzeln = backup.erlaubte_wurzeln(app_ctx.app)

    assert wurzeln[1:] == [_real(nas), _real(platte), _real(gewaehlt)]
    assert backup._ziel_pruefen(app_ctx.app, platte / 'unter') == _real(platte / 'unter')
    assert backup._ziel_pruefen(app_ctx.app, gewaehlt) == _real(gewaehlt)


def test_ordner_waehlen_merkt_den_ordner_mit_semikolon(lokal, tmp_path, monkeypatch):
    gewaehlt = str(tmp_path / 'Sicherung;2026')

    class Fenster:
        def create_file_dialog(self, art, **_):
            assert art == 20
            return [gewaehlt]

    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(FOLDER_DIALOG=20))
    monkeypatch.setenv('NK_SICHERUNGSZIELE', '')
    monkeypatch.setenv('BACKUP_ZIELE', '')
    bruecke = desktop.Bruecke()
    bruecke._fenster = Fenster()

    assert bruecke.ordner_waehlen() == gewaehlt
    assert windows_ordner.einstellungen_lesen()['sicherungsziele'] == [gewaehlt]
    assert os.environ['NK_SICHERUNGSZIELE'].split('\n') == [gewaehlt]
    # Die Desktop-App reicht ihre Ziele nicht mehr über BACKUP_ZIELE weiter.
    assert os.environ['BACKUP_ZIELE'] == ''


def test_anwendung_laden_reicht_die_ziele_zeilenweise_weiter(lokal, tmp_path, monkeypatch):
    ziele = [str(tmp_path / 'USB-Stick'), str(tmp_path / 'Büro;Archiv')]
    windows_ordner.einstellungen_schreiben(sicherungsziele=ziele)
    for name in ('NK_DESKTOP', 'DATA_DIR', 'DATABASE_URL', 'NK_SICHERUNGSZIELE', 'BACKUP_ZIELE'):
        monkeypatch.setenv(name, '')
    attrappe = types.ModuleType('app')
    monkeypatch.setitem(sys.modules, 'app', attrappe)

    assert desktop.anwendung_laden(tmp_path / 'daten') is attrappe
    assert os.environ['NK_SICHERUNGSZIELE'].split('\n') == ziele
    assert os.environ['BACKUP_ZIELE'] == ''


def test_neustart_umgebung_entfernt_die_sitzungsziele():
    umgebung = desktop.neustart_umgebung({'NK_SICHERUNGSZIELE': 'x\ny', 'PATH': 'p'})
    assert 'NK_SICHERUNGSZIELE' not in umgebung
    assert umgebung['PATH'] == 'p'
