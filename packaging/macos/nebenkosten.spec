# PyInstaller-Spezifikation der macOS-App (#44, Schritt 2).
#
#   pyinstaller packaging/macos/nebenkosten.spec --noconfirm
#
# Wie die Windows-App: onedir, ohne Konsole, dieselbe Positivliste (der Teil
# von WURZEL bis einschliesslich Analysis ist wortgleich mit
# packaging/windows/nebenkosten.spec, tests/test_macos_paket.py hält das fest;
# darum nennt der Kommentar zur Lizenzdatei dort windows.yml, hier gilt macos.yml). Dazu das Bundle NebenkostenFix.app,
# nur für Apple Silicon (cryptography hat nur arm64-Wheels) und ab macOS 15.
# PyInstaller signiert das Bundle ad hoc; notarisiert ist es nicht.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

WURZEL = Path(SPECPATH).resolve().parents[1]

# Die eigenen Module: app.py und desktop.py in der Wurzel, dazu jedes Modul
# im Paket nebenkostenfix/ ausser Entwicklungswerkzeugen. Die Liste folgt dem
# Ordner: ein hier fehlendes Modul fehlt der EXE, ohne dass die Analyse es
# meldet (D-110).
PAKET = WURZEL / 'nebenkostenfix'
AUSGESCHLOSSEN = {'nebenkostenfix.debug_routen'}
paketmodule = {
    '.'.join(('nebenkostenfix', *p.relative_to(PAKET).with_suffix('').parts)).removesuffix('.__init__')
    for p in PAKET.rglob('*.py')
}
module = sorted(p.stem for p in WURZEL.glob('*.py')) + sorted(paketmodule - AUSGESCHLOSSEN)

daten = [
    (str(WURZEL / 'static'), 'static'),
    (str(WURZEL / 'migrations'), 'migrations'),
]
daten += collect_data_files('reportlab')
daten += collect_data_files('webview')
daten += collect_data_files('tzdata')
daten += collect_data_files('alembic')
# Lizenztexte der mitgelieferten Software (NK-148). windows.yml erzeugt die
# Datei vor dem Bau; fehlt sie, bricht PyInstaller ab, statt ohne zu bauen.
daten.append((str(WURZEL / 'THIRD_PARTY_LICENSES.txt'), '.'))

# migrations/ laeuft zur Laufzeit als Datei (alembic laedt env.py und die
# Versionen per Pfad) -- deren Importe sieht die Analyse nicht von selbst.
import ast
wanderungsimporte = set()
for datei in (WURZEL / 'migrations').rglob('*.py'):
    for knoten in ast.walk(ast.parse(datei.read_text(encoding='utf-8'))):
        if isinstance(knoten, ast.Import):
            wanderungsimporte.update(a.name for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module and not knoten.level:
            wanderungsimporte.add(knoten.module)

versteckt = module + ['waitress', 'logging.config']
versteckt += sorted(wanderungsimporte)
versteckt += collect_submodules('webview')
versteckt += collect_submodules('sqlalchemy.dialects.sqlite')
versteckt += collect_submodules('alembic')
versteckt += collect_submodules('reportlab.graphics.barcode')

a = Analysis(
    [str(WURZEL / 'desktop.py')],
    pathex=[str(WURZEL)],
    datas=daten,
    hiddenimports=versteckt,
    excludes=['nebenkostenfix.debug_routen', 'pytest', 'tkinter', 'gunicorn'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NebenkostenFix',
    console=False,
    disable_windowed_traceback=False,
    target_arch='arm64',
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='NebenkostenFix', upx=False)

sys.path.insert(0, str(WURZEL))
from nebenkostenfix.abrechnung_version import SOFTWARE_VERSION  # noqa: E402

app = BUNDLE(
    coll,
    name='NebenkostenFix.app',
    icon=str(WURZEL / 'packaging' / 'macos' / 'nebenkostenfix.icns'),
    bundle_identifier='de.nebenkostenfix.app',
    version=SOFTWARE_VERSION,
    info_plist={
        # Ohne Namen hiesse das App-Menue „Python“.
        'CFBundleName': 'NebenkostenFix',
        'CFBundleDisplayName': 'NebenkostenFix',
        'CFBundleShortVersionString': SOFTWARE_VERSION,
        'CFBundleVersion': SOFTWARE_VERSION,
        # Nur Systeme, die Apple noch mit Sicherheitsupdates versorgt (Okt. 2026: 15, 26, 27).
        'LSMinimumSystemVersion': '15.0',
        'NSHighResolutionCapable': True,
        'NSHumanReadableCopyright': 'NebenkostenFix, freie Software unter der GPL-3.0',
        # Texte der Rückfrage von macOS, wenn Sicherungen, Umzug oder Belege
        # in einem geschützten Ordner liegen.
        'NSDocumentsFolderUsageDescription':
            'NebenkostenFix legt Sicherungen und Umzugspakete dort ab, wo Sie es festlegen.',
        'NSDesktopFolderUsageDescription':
            'NebenkostenFix legt Sicherungen und Umzugspakete dort ab, wo Sie es festlegen.',
        'NSDownloadsFolderUsageDescription':
            'NebenkostenFix öffnet Belege und Umzugspakete, die Sie auswählen.',
        'NSRemovableVolumesUsageDescription':
            'NebenkostenFix legt Sicherungen auf dem Datenträger ab, den Sie festlegen.',
        'NSNetworkVolumesUsageDescription':
            'NebenkostenFix legt Sicherungen auf dem Netzlaufwerk ab, das Sie festlegen.',
        # Servermodus (#45): Der Server steht oft im Heimnetz. Apple empfiehlt
        # den Text (TN3179); macOS 26.5 fragte im Test nicht nach.
        'NSLocalNetworkUsageDescription':
            'NebenkostenFix verbindet sich mit Ihrem eigenen NebenkostenFix-Server im '
            'Heimnetz, zum Beispiel auf einem NAS. Ihre Daten bleiben dabei in Ihrem Netz.',
    },
)
