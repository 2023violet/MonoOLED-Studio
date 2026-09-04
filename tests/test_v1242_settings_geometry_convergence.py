from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
VERSION = (SRC / 'VERSION').read_text(encoding='utf-8').strip()


def test_v1242_release_identity_and_current_documentation_contract():
    version = VERSION
    assert version == '1.1.0'
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert manifest['release_version'] == version
    assert manifest['release_name'] == f'V{version} Output Workbench Release'
    assert manifest['documentation_policy'] == f'current-v{version}-only'
    assert manifest['settings_information_architecture'].endswith('v100-initial-release')
    assert manifest['windows']['release_asset'] == f'MonoOLEDStudio_v{version}_Windows_x64.zip'
    assert (ROOT / 'docs' / 'ENGINEERING_HISTORY.md').is_file()


def test_package_verifier_requires_v1242_geometry_doc_and_current_real_qt_regression():
    verifier = (ROOT / 'VERIFY_PACKAGE.py').read_text(encoding='utf-8')
    assert "'ENGINEERING_HISTORY.md'" in verifier
    assert "'tests/test_qt_v1242_settings_layout_geometry.py'" in verifier


def test_current_windows_and_user_docs_reference_v100_public_asset():
    expected = f'MonoOLEDStudio_v{VERSION}_Windows_x64.zip'
    for rel in ('docs/WINDOWS_BUILD.md', 'docs/USER_GUIDE_EN.md', 'docs/USER_GUIDE_CN.md', 'DELIVERY_README.md'):
        text = (ROOT / rel).read_text(encoding='utf-8')
        assert expected in text, rel
    assert f'# Windows Build and Release — V{VERSION}' in (ROOT / 'docs' / 'WINDOWS_BUILD.md').read_text(encoding='utf-8')
    assert f'# V{VERSION} Output Workbench Release Delivery' in (ROOT / 'DELIVERY_README.md').read_text(encoding='utf-8')

def test_current_root_readme_and_about_surface_use_v100_identity():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert readme.startswith(f'# MonoOLED Studio V{VERSION} — Output Workbench Release')
    assert f'MonoOLEDStudio_v{VERSION}_Windows_x64.zip' in readme
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert '取模与输出工作台版本' in prefs
    assert 'Output Workbench Release' in prefs
