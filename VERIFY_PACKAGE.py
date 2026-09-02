#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import py_compile
import sys

ROOT=Path(__file__).resolve().parent
SRC=ROOT / 'src'
TESTS=ROOT / 'tests'
TOOLS=ROOT / 'tools'
REQUIRED_DIRS=('src','tests','tools','test_assets','docs','.github')
OBSOLETE_ROOTS=('OLED模拟器','Developer_Tools','Curing_Lite光固化机产品 - UI设计初稿','scenes')
CURRENT_DOCS={
    'README.md','USER_GUIDE_CN.md','USER_GUIDE_EN.md','SCENE_SCHEMA.md',
    'AUTOMATION_API_V1.md','DESIGN_SYSTEM.md','ENGINEERING_HISTORY.md','WINDOWS_BUILD.md',
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def verify_layout() -> None:
    for name in REQUIRED_DIRS:
        if not (ROOT/name).is_dir(): fail(f'missing required V12 directory: {name}')
    for name in OBSOLETE_ROOTS:
        if (ROOT/name).exists(): fail(f'obsolete V12 path still present: {name}')
    # The obsolete root MonoOLEDStudio.exe launcher is deliberately rejected.
    if (ROOT/'MonoOLEDStudio.exe').exists(): fail('obsolete root MonoOLEDStudio.exe must not be shipped; build Windows EXE from tools')
    if any(not p.relative_to(ROOT).as_posix().isascii() for p in ROOT.rglob('*') if '.git' not in p.parts):
        fail('non-ASCII distributed path detected')


def verify_docs() -> None:
    docs=ROOT/'docs'
    names={p.name for p in docs.iterdir() if p.is_file()}
    missing=CURRENT_DOCS-names
    if missing: fail(f'missing current V12 docs: {sorted(missing)}')
    for legacy in ('archive','releases','design','superpowers'):
        if (docs/legacy).exists(): fail(f'legacy documentation tree must not ship: docs/{legacy}')


def verify_source() -> None:
    version=(ROOT/'src/VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version): fail(f'invalid semantic VERSION: {version!r}')
    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    if manifest.get('version') != version or manifest.get('release_version') != version:
        fail(f'release identity mismatch: VERSION={version}, manifest={manifest.get("version")}/{manifest.get("release_version")}')
    modules=sorted((ROOT/'src').glob('*.py'))
    for path in modules: py_compile.compile(str(path),doraise=True)
    scene=json.loads((ROOT/'src/scenes/main_scene.json').read_text(encoding='utf-8'))
    if scene.get('states') != {} or scene.get('timeline') != []: fail('default V12 scene must be state/timeline-neutral')
    payload=json.dumps(scene,ensure_ascii=False).lower()
    if any(word in payload for word in ('curing','battery','countdown','clinical','turbo','ortho')): fail('product-specific content leaked into default scene')


def verify_frozen_assets() -> None:
    path=ROOT/'test_assets/manifests/frozen_product_assets_v70.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    files=data.get('files',{})
    if data.get('count') != 464 or len(files) != 464: fail('frozen asset manifest must contain exactly 464 assets')
    for rel,expected in files.items():
        if not rel.isascii() or not rel.startswith('test_assets/projects/curing_lite/'): fail(f'invalid V12 frozen path: {rel}')
        target=ROOT/rel
        if not target.is_file(): fail(f'missing frozen asset: {rel}')
        actual=sha256(target)
        if actual != expected: fail(f'frozen asset hash mismatch: {rel}')


def verify_build_contract() -> None:
    builder=(ROOT/'tools/BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    quick=(ROOT/'tools/BUILD_WINDOWS_QUICK.bat').read_text(encoding='utf-8')
    release=(ROOT/'.github/workflows/release-windows.yml').read_text(encoding='utf-8')
    spec=(ROOT/'tools/MonoOLEDStudio.spec').read_text(encoding='utf-8')
    for marker in ('requirements-build.txt','requirements-dev.txt','src\\gui.py','tests','VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py','VERIFY_SETTINGS_V1231.py','CAPTURE_V1231_SETTINGS_GOLDENS.py','BUILD_WINDOWS_RUNTIME_ZIP.py'):
        if marker not in builder: fail(f'Windows GA builder missing current marker: {marker}')
    for marker in ('MonoOLEDStudio.spec','MonoOLEDStudio.exe','--check','--startup-smoke'):
        if marker not in quick: fail(f'Windows quick builder missing current marker: {marker}')
    for marker in ('BUILD_WINDOWS_GA.bat','PUBLISH_GITHUB_RELEASE.ps1','contents: write'):
        if marker not in release: fail(f'GitHub Release workflow missing marker: {marker}')
    for marker in ("ref: ${{ github.event_name == 'push' && github.ref || inputs.tag }}", '--require-git-head', 'if: always()'):
        if marker not in release: fail(f'GitHub Release workflow missing release-integrity marker: {marker}')
    runtime_zip=(ROOT/'tools/BUILD_WINDOWS_RUNTIME_ZIP.py').read_text(encoding='utf-8')
    for marker in ('BUILD_INFO.json','expected_git_commit','extract_runtime_zip'):
        if marker not in runtime_zip: fail(f'Windows runtime ZIP tool missing release-integrity marker: {marker}')
    if "add_tree('test_assets'" in spec: fail('PyInstaller runtime must not bundle test_assets')
    for marker in ("ROOT / 'src' / 'gui.py'", "'src/scenes'", "'docs'"):
        if marker not in spec: fail(f'PyInstaller spec missing V12 marker: {marker}')
    for rel in ('tests/test_v1232_ux_hardening.py','tests/test_qt_v1232_ux_hardening.py','tests/test_v1233_resilience_hardening.py','tests/test_v1234_autonomous_quality_hardening.py','tests/test_v1235_artifact_integrity.py','tests/test_v1236_cross_session_integrity.py','tests/test_v1237_windows_release_integrity.py','tests/test_v1238_long_session_resilience.py','tests/test_v1239_automation_lifecycle_integrity.py','tests/test_qt_v1242_settings_layout_geometry.py'):
        if not (ROOT/rel).is_file(): fail(f'missing current V12 quality regression: {rel}')


def main() -> int:
    try:
        verify_layout(); verify_docs(); verify_source(); verify_frozen_assets(); verify_build_contract()
    except Exception as exc:
        print(f'[FAIL] V12 package verification: {exc}',file=sys.stderr); return 2
    print('[PASS] V12 package verification: layout, docs, source, 464 frozen hashes, and build contract are current.')
    return 0

if __name__=='__main__': raise SystemExit(main())
