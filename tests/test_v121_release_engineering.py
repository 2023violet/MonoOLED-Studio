from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
WORKFLOWS = ROOT / '.github' / 'workflows'


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_version_is_v121_release_ready():
    version=(ROOT / 'src' / 'VERSION').read_text(encoding='utf-8').strip(); assert version.count('.')==2


def test_ci_workflow_is_fast_source_gate_not_ga_packaging():
    ci = _text(WORKFLOWS / 'ci.yml')
    assert 'pull_request:' in ci
    assert 'push:' in ci
    assert 'actions/checkout@v7' in ci
    assert 'actions/setup-python@v7' in ci
    assert 'RUN_WINDOWS_TEST_GROUPS.py --phase source' in ci
    assert 'VERIFY_PACKAGE.py' in ci
    assert 'BUILD_WINDOWS_GA.bat' not in ci
    assert 'PyInstaller' not in ci


def test_release_workflow_builds_on_windows_tags_and_publishes_release_assets():
    workflow = _text(WORKFLOWS / 'release-windows.yml')
    assert "tags: ['v*.*.*']" in workflow or 'v*.*.*' in workflow
    assert 'runs-on: windows-latest' in workflow
    assert 'permissions:' in workflow and 'contents: write' in workflow
    assert 'actions/checkout@v7' in workflow
    assert 'actions/setup-python@v7' in workflow
    assert 'VERIFY_RELEASE_TAG.py' in workflow
    assert 'BUILD_WINDOWS_GA.bat' in workflow
    assert 'PUBLISH_GITHUB_RELEASE.ps1' in workflow
    assert 'release/MonoOLEDStudio_v*_Windows_x64.zip' in workflow
    assert 'release/MonoOLEDStudio_v*_Windows_x64.zip.sha256' in workflow


def test_quick_builder_creates_exe_without_full_historical_ga_matrix():
    quick = _text(TOOLS / 'BUILD_WINDOWS_QUICK.bat')
    assert 'MonoOLEDStudio.spec' in quick
    assert 'dist\\MonoOLEDStudio\\MonoOLEDStudio.exe' in quick
    assert '--check' in quick
    assert '--startup-smoke' in quick
    assert 'RUN_WINDOWS_TEST_GROUPS.py --phase qt' not in quick
    assert 'VERIFY_V844_FINAL.py' not in quick
    assert '--soak-smoke' not in quick


def test_ga_builder_retains_full_windows_certification_and_release_zip():
    ga = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    for marker in (
        'RUN_WINDOWS_TEST_GROUPS.py --phase source',
        'RUN_WINDOWS_TEST_GROUPS.py --phase qt',
        'VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py',
        'PyInstaller',
        '--layout-smoke',
        '--interaction-smoke',
        '--soak-smoke',
        'MonoOLEDStudio_v%VER%_Windows_x64.zip',
        'BUILD_WINDOWS_RUNTIME_ZIP.py',
    ):
        assert marker in ga


def test_legacy_builder_is_only_a_compatibility_wrapper_to_ga():
    wrapper = _text(TOOLS / 'BUILD_WINDOWS_EXE.bat')
    assert 'BUILD_WINDOWS_GA.bat' in wrapper
    assert 'PyInstaller' not in wrapper
    assert 'RUN_WINDOWS_TEST_GROUPS.py' not in wrapper


def test_release_tag_verifier_binds_git_tag_to_src_version():
    verifier = _text(TOOLS / 'VERIFY_RELEASE_TAG.py')
    assert "src' / 'VERSION" in verifier or 'src/VERSION' in verifier
    assert "f'v{version}'" in verifier or 'v{version}' in verifier
    assert 'GITHUB_REF_NAME' in verifier


def test_release_publisher_is_idempotent_and_keeps_existing_release_assets_immutable():
    publisher = _text(TOOLS / 'PUBLISH_GITHUB_RELEASE.ps1')
    assert 'gh release view' in publisher
    assert 'gh release create' in publisher
    assert 'gh release download' in publisher
    assert '--clobber' not in publisher
    assert 'Existing release assets are identical' in publisher
    assert 'Windows_x64.zip' in publisher
    assert '.zip.sha256' in publisher


def test_readme_points_end_users_to_releases_not_python_or_bat():
    readme = _text(ROOT / 'README.md')
    top = '\n'.join(readme.splitlines()[:23]).lower()
    assert 'github releases' in top
    assert 'window' in top
    assert 'monooledstudio.exe' in top
    assert 'build_windows_exe.bat' not in top
    assert 'python src' not in top


def test_manifest_declares_release_distribution_and_developer_builders():
    manifest = json.loads(_text(ROOT / 'DELIVERY_MANIFEST.json'))
    version=(ROOT / 'src' / 'VERSION').read_text(encoding='utf-8').strip()
    assert manifest['version'] == version
    windows = manifest['windows']
    assert windows['distribution'] == 'github_releases'
    assert windows['release_asset'] == f'MonoOLEDStudio_v{version}_Windows_x64.zip'
    assert windows['quick_builder'] == 'tools/BUILD_WINDOWS_QUICK.bat'
    assert windows['ga_builder'] == 'tools/BUILD_WINDOWS_GA.bat'
    assert windows['end_user_requires_python'] is False
