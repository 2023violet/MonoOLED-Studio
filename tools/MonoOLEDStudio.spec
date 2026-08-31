# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir runtime build for MonoOLED Studio Windows releases."""
from pathlib import Path

ROOT = Path.cwd()

def add_tree(rel: str, dest: str | None = None):
    src=ROOT/rel
    return [(str(src), dest or rel)] if src.exists() else []

# Runtime-only bundled roots: product scenes/branding/docs; test fixtures are excluded.
# Frozen code resolves resources as Path(__file__).parent/..., which in an onedir
# build is the app root, so branding (icons + window icon) must land at the root.
datas=[]
datas += add_tree('src/scenes', 'src/scenes')
datas += add_tree('src/branding', 'branding')
datas += add_tree('docs', 'docs')
for rel in ('src/VERSION','src/AUTOMATION_API_V1.json'):
    p=ROOT/rel
    if p.exists(): datas.append((str(p),'.'))

a = Analysis(
    [str(ROOT / 'src' / 'gui.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[], datas=datas, hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=['tkinter','pydoc_data','pydoc','lib2to3','unittest',
                                'doctest','pdb','venv','ensurepip','distutils','pip'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='MonoOLEDStudio', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    icon=str(ROOT / 'src' / 'branding' / 'monooled_studio.ico'), contents_directory='.',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name='MonoOLEDStudio')
