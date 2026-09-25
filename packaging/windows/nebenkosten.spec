# PyInstaller-Spezifikation der Windows-App (NK-150, NK-079).
#
#   pyinstaller packaging/windows/nebenkosten.spec --noconfirm
#
# onedir (schneller Start, keine Entpackerei bei jedem Start), windowed (kein
# Konsolenfenster, D-84). Positivliste statt "alles": nur Code, migrations/,
# static/ und die Daten der Bibliotheken -- keine Tests, keine Doku, keine
# Planungsdateien, kein debug_routen.py (NK-040, NK-133).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

WURZEL = Path(SPECPATH).resolve().parents[1]

# Die eigenen Module: jede *.py der Wurzel ausser Entwicklungswerkzeugen.
AUSGESCHLOSSEN = {'debug_routen.py'}
module = sorted(p.stem for p in WURZEL.glob('*.py') if p.name not in AUSGESCHLOSSEN)

daten = [
    (str(WURZEL / 'static'), 'static'),
    (str(WURZEL / 'migrations'), 'migrations'),
]
daten += collect_data_files('reportlab')
daten += collect_data_files('webview')
daten += collect_data_files('tzdata')
daten += collect_data_files('alembic')

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

versteckt = module + ['handlers', 'handlers.nas_handler', 'waitress', 'logging.config']
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
    excludes=['debug_routen', 'pytest', 'tkinter', 'gunicorn'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NebenkostenFix',
    icon=str(WURZEL / 'packaging' / 'windows' / 'nebenkostenfix.ico'),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='NebenkostenFix', upx=False)
