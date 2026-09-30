"""Wo die Windows-App ihre Daten ablegt (NK-079, D-84, F-82, D-95).

D-84: Das Programm liegt unter ``C:\\Program Files\\NebenkostenFix``, die
Daten in ``Dokumente\\NebenkostenFix`` -- dort sucht der Vermieter seine
Belege und Sicherungen. D-95: Eine Installation aus der Zeit vor der
Umbenennung (Ordner ``Nebenkostenabrechnung``) behält ihren Datenordner; die
App übernimmt ihre ``einstellungen.ini`` einmal an den neuen Ort. Zwei Fallen
(F-82):

1. **OneDrive** („Bekannte Ordner verschieben“): „Dokumente“ liegt dann in
   OneDrive und wird synchronisiert. Eine SQLite-Datenbank im WAL-Modus
   verträgt das Sperren und Hochladen während des Schreibens nicht, und die
   Mieterdaten lägen ungefragt in der Cloud. Deshalb wird der echte Pfad über
   die Windows-Schnittstelle für bekannte Ordner ermittelt (nie
   ``%USERPROFILE%\\Documents`` geraten) und gegen die OneDrive-Wurzeln
   geprüft. Liegt er darin, bietet die App einen lokalen Ort an.
2. **Überwachter Ordnerzugriff** (Ransomware-Schutz des Defenders) sperrt
   Schreibzugriffe unbekannter Programme auf „Dokumente“. Eine Schreibprobe
   beim Start erkennt das und erklärt in Klartext, wie man die App zulässt.

Die Einstellungen (gewählter Datenordner, freigegebene Sicherungsziele)
stehen in ``%LOCALAPPDATA%\\NebenkostenFix\\einstellungen.ini`` --
der Installer schreibt den Ordner dorthin, die App liest ihn.

Alles hier ist ohne Windows prüfbar: die Windows-Aufrufe stehen in kleinen
Funktionen, die Tests ersetzen.
"""

from __future__ import annotations

import codecs
import configparser
import os
import sys
import uuid
from pathlib import Path

from nebenkostenfix import marke

APP_NAME = marke.PRODUKT
ALTER_NAME = marke.ALTER_NAME
# Trenner der Sicherungsziele in der INI: fest ';' (Windows-Pfade haben ':')
ZIELTRENNER = ';'


def _known_folder_dokumente() -> Path | None:  # pragma: no cover - Windows
    """SHGetKnownFolderPath(FOLDERID_Documents) -- der echte Ort, auch wenn
    er per Gruppenrichtlinie oder OneDrive verschoben ist."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                    ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]

    # {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
    guid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
    zeiger = ctypes.c_wchar_p()
    ergebnis = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(zeiger))
    try:
        if ergebnis != 0 or not zeiger.value:
            return None
        return Path(zeiger.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(zeiger)


def dokumente_ordner() -> Path:
    """Der Dokumente-Ordner des Nutzers."""
    if sys.platform == 'win32':  # pragma: no cover - Windows
        ort = _known_folder_dokumente()
        if ort is not None:
            return ort
    xdg = os.environ.get('XDG_DOCUMENTS_DIR')
    if xdg:
        return Path(xdg)
    return Path.home() / 'Documents'


def _lokale_basis() -> Path:
    basis = os.environ.get('LOCALAPPDATA')
    return Path(basis) if basis else Path.home() / '.local' / 'share'


def lokaler_ordner() -> Path:
    """%LOCALAPPDATA%\\NebenkostenFix -- nie synchronisiert."""
    return _lokale_basis() / APP_NAME


def alter_lokaler_ordner() -> Path:
    """Der lokale Ordner einer Installation vor der Umbenennung (D-95)."""
    return _lokale_basis() / ALTER_NAME


def vorgabe_datenordner() -> Path:
    """Dokumente\\NebenkostenFix -- außer eine ältere Installation hat ihre
    Daten schon in Dokumente\\Nebenkostenabrechnung (D-95: sie bleiben dort)."""
    alt = dokumente_ordner() / ALTER_NAME
    if (alt / 'nebenkosten.db').is_file():
        return alt
    return dokumente_ordner() / APP_NAME


def lokaler_ausweich() -> Path:
    """Angebot, wenn „Dokumente“ in OneDrive liegt."""
    return lokaler_ordner() / 'Daten'


def onedrive_wurzeln() -> list[Path]:
    wurzeln = []
    for name in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        wert = (os.environ.get(name) or '').strip()
        if wert:
            wurzeln.append(Path(wert))
    return wurzeln


def _normiert(pfad: Path) -> str:
    return os.path.normcase(os.path.abspath(str(pfad))).rstrip('\\/')


def liegt_in_onedrive(pfad: Path, wurzeln: list[Path] | None = None) -> bool:
    ziel = _normiert(pfad)
    for wurzel in (onedrive_wurzeln() if wurzeln is None else wurzeln):
        basis = _normiert(wurzel)
        if ziel == basis or ziel.startswith(basis + os.sep):
            return True
    return False


def schreibprobe(ordner: Path) -> str | None:
    """None, wenn der Ordner beschreibbar ist, sonst eine Erklärung für
    Menschen (überwachter Ordnerzugriff, fehlende Rechte)."""
    try:
        ordner.mkdir(parents=True, exist_ok=True)
        probe = ordner / f'.schreibprobe-{uuid.uuid4().hex}'
        probe.write_bytes(b'ok')
        probe.unlink()
        return None
    except OSError as fehler:
        return (
            f'{APP_NAME} kann nicht in „{ordner}“ schreiben '
            f'({fehler.strerror or fehler}).\n\n'
            'Häufigster Grund unter Windows ist der „Überwachte Ordnerzugriff“ '
            '(Windows-Sicherheit → Viren- & Bedrohungsschutz → Ransomware-Schutz). '
            'Lassen Sie dort unter „App durch überwachten Ordnerzugriff zulassen“ '
            f'{APP_NAME} zu, oder wählen Sie in den Einstellungen '
            'einen anderen Datenordner.')


# --- Einstellungen ----------------------------------------------------------

def einstellungen_datei() -> Path:
    return lokaler_ordner() / 'einstellungen.ini'


def _ini_text(datei: Path) -> str:
    """Der Inhalt der INI-Datei, gleich in welcher Kodierung.

    Die Datei schreiben zwei: der Installer über die Windows-Schnittstelle
    (legt sie neu in der ANSI-Codepage an, schreibt in eine vorhandene
    UTF-16-Datei aber Unicode) und die App. Die App schreibt deshalb UTF-16
    mit BOM -- danach bleiben Umlaute im Pfad auch nach einem Update heil.
    """
    roh = datei.read_bytes()
    if roh.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return roh.decode('utf-16')
    if roh.startswith(codecs.BOM_UTF8):
        return roh[len(codecs.BOM_UTF8):].decode('utf-8')
    try:
        return roh.decode('utf-8')
    except UnicodeDecodeError:
        return roh.decode('mbcs' if sys.platform == 'win32' else 'cp1252',
                          errors='replace')


def _ini_parser(datei: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    if datei.is_file():
        parser.read_string(_ini_text(datei))
    return parser


def _alte_einstellungen_uebernehmen() -> None:
    """Einmalig: die einstellungen.ini einer Installation vor der Umbenennung
    an den neuen Ort (D-95). Die alte bleibt liegen, falls jemand zurückgeht."""
    neu = einstellungen_datei()
    alt = alter_lokaler_ordner() / 'einstellungen.ini'
    if neu.is_file() or not alt.is_file():
        return
    parser = _ini_parser(alt)
    neu.parent.mkdir(parents=True, exist_ok=True)
    with open(neu, 'w', encoding='utf-16') as ausgabe:
        parser.write(ausgabe)


def einstellungen_lesen() -> dict:
    _alte_einstellungen_uebernehmen()
    datei = einstellungen_datei()
    parser = _ini_parser(datei)
    abschnitt = parser['Daten'] if parser.has_section('Daten') else {}
    ziele = [z for z in (abschnitt.get('Sicherungsziele', '') or '').split(ZIELTRENNER) if z]
    return {
        'datenordner': abschnitt.get('Ordner') or None,
        'sicherungsziele': ziele,
        'onedrive_bestaetigt': abschnitt.get('OneDriveBestaetigt', '') == '1',
    }


def einstellungen_schreiben(**werte) -> None:
    _alte_einstellungen_uebernehmen()
    datei = einstellungen_datei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    parser = _ini_parser(datei)
    if not parser.has_section('Daten'):
        parser.add_section('Daten')
    if 'datenordner' in werte:
        parser['Daten']['Ordner'] = str(werte['datenordner'])
    if 'sicherungsziele' in werte:
        parser['Daten']['Sicherungsziele'] = ZIELTRENNER.join(werte['sicherungsziele'])
    if 'onedrive_bestaetigt' in werte:
        parser['Daten']['OneDriveBestaetigt'] = '1' if werte['onedrive_bestaetigt'] else '0'
    with open(datei, 'w', encoding='utf-16') as ausgabe:
        parser.write(ausgabe)
