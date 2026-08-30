from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'


def test_v1242_release_identity_and_current_documentation_contract():
    version = (SRC / 'VERSION').read_text(encoding='utf-8').strip()
    assert version == '1.0.0'
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert manifest['release_version'] == version
    assert manifest['release_name'] == 'V1.0.0 Initial Release'
    assert manifest['documentation_policy'] == 'current-v1.0.0-only'
    assert manifest['settings_information_architecture'].endswith('v100-initial-release')
    assert manifest['windows']['release_asset'] == 'MonoOLEDStudio_v1.0.0_Windows_x64.zip'
    assert (ROOT / 'docs' / 'V12_4_2_SETTINGS_GEOMETRY_CONVERGENCE.md').is_file()


def test_package_verifier_requires_v1242_geometry_doc_and_current_real_qt_regression():
    verifier = (ROOT / 'VERIFY_PACKAGE.py').read_text(encoding='utf-8')
    assert "'V12_4_2_SETTINGS_GEOMETRY_CONVERGENCE.md'" in verifier
    assert "'tests/test_qt_v1242_settings_layout_geometry.py'" in verifier


def test_current_windows_and_user_docs_reference_v100_public_asset():
    expected = 'MonoOLEDStudio_v1.0.0_Windows_x64.zip'
    for rel in ('docs/WINDOWS_BUILD.md', 'docs/USER_GUIDE_EN.md', 'docs/USER_GUIDE_CN.md', 'DELIVERY_README.md'):
        text = (ROOT / rel).read_text(encoding='utf-8')
        assert expected in text, rel
    assert '# Windows Build and Release — V1.0.0' in (ROOT / 'docs' / 'WINDOWS_BUILD.md').read_text(encoding='utf-8')
    assert '# V1.0.0 Initial Release Delivery' in (ROOT / 'DELIVERY_README.md').read_text(encoding='utf-8')

def test_current_root_readme_and_about_surface_use_v100_identity():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert readme.startswith('# MonoOLED Studio V1.0.0 — Initial Release')
    assert 'MonoOLEDStudio_v1.0.0_Windows_x64.zip' in readme
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert prefs.count('Initial Release') >= 2

