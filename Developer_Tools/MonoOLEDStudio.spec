# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for MonoOLED Studio v7.1.

Run from the delivery-project root on Windows:
    pyinstaller --clean --noconfirm MonoOLEDStudio.spec

The bundle intentionally uses onedir + contents_directory='.' so scene/assets
remain visible and editable next to the executable. A onefile build would unpack
mutable project data into a temporary directory and is therefore unsuitable for
this authoring workflow.
"""
from pathlib import Path

ROOT = Path.cwd()

DATA_DIRS = [
    'OLED模拟器/scenes',
    'OLED模拟器/branding',
    'Curing_Lite光固化机产品 - UI设计初稿',
    '中文 - 字宽12字高12',
    '字库转PNG脚本',
    '数字 - 字宽12字高16',
    '数字 - 字宽12字高28',
    '数字 - 字宽13字高27',
    '数字 - 字宽5字高11',
    '数字 - 字宽5字高7',
    '数字 - 字宽6字高8',
    '数字 - 字宽8字高16',
    '数字 - 字宽8字高17',
    '电池图标 - 字宽11字高28',
    '电池图标 - 字宽32字高16',
]
DATA_FILES = [
    'OLED模拟器/VERSION',
    'OLED模拟器/README.md',
    'OLED模拟器/USER_GUIDE_CN.md',
    'OLED模拟器/USER_GUIDE_EN.md',
    'OLED模拟器/CODE_AI_HANDOFF.md',
    'OLED模拟器/FINAL_VERIFICATION_REPORT.md',
    'OLED模拟器/TEST_MATRIX_V71.md',
    'OLED模拟器/SCENE_SCHEMA.md',
]

datas = []
for rel in DATA_DIRS:
    src = ROOT / rel
    if src.exists():
        datas.append((str(src), rel))
for rel in DATA_FILES:
    src = ROOT / rel
    if src.exists():
        datas.append((str(src), str(Path(rel).parent)))

a = Analysis(
    [str(ROOT / 'OLED模拟器' / 'gui.py')],
    pathex=[str(ROOT / 'OLED模拟器')],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MonoOLEDStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'OLED模拟器' / 'branding' / 'monooled_studio.ico'),
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MonoOLEDStudio',
)
