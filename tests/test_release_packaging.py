from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
DEV = ROOT / 'tools'


def test_runtime_and_build_requirements_pin_qt_and_pyinstaller():
    runtime = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    build = (ROOT / 'requirements-build.txt').read_text(encoding='utf-8')
    assert 'PySide6-Essentials==6.11.2' in runtime
    assert 'PyInstaller==6.22.0' in build
    assert '-r requirements.txt' in build


def test_windows_build_script_builds_and_smoke_checks_exe():
    script = (DEV / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'MonoOLEDStudio.spec' in script
    assert 'MonoOLEDStudio.exe' in script
    assert '--check' in script
    assert '--smoke-ms' in script
    assert '--layout-smoke' in script
    assert '--interaction-smoke' in script
    assert 'BUILD_WINDOWS_RUNTIME_ZIP.py' in script
    assert '--checksum "%ZIP%.sha256"' in script


def test_pyinstaller_spec_is_onedir_and_bundles_required_data():
    spec = (DEV / 'MonoOLEDStudio.spec').read_text(encoding='utf-8')
    assert "name='MonoOLEDStudio'" in spec
    assert 'COLLECT(' in spec
    assert "'src/scenes'" in spec
    assert "'docs'" in spec
    assert "ROOT / 'src' / 'gui.py'" in spec
    assert "contents_directory='.'" in spec


def test_release_version_is_semantic():
    version=(SIM / 'VERSION').read_text(encoding='utf-8').strip()
    parts=tuple(map(int, version.split('.')))
    assert len(parts) == 3 and all(p >= 0 for p in parts)


def test_v5_user_root_has_only_one_launch_entry_and_developer_tools_are_nested():
    assert not (ROOT / 'MonoOLEDStudio.exe').exists()
    assert not list(ROOT.glob('*.bat'))
    assert not (ROOT / 'MonoOLEDStudio.spec').exists()
    assert (DEV / 'BUILD_WINDOWS_GA.bat').exists()
    assert (DEV / 'BUILD_WINDOWS_QUICK.bat').exists()
    assert (DEV / 'MonoOLEDStudio.spec').exists()
    assert not (ROOT / 'CuringLiteOLEDDesigner_SourceLauncher.exe').exists()
    assert not (ROOT / 'CuringLiteOLEDDesigner_SourceLauncher-script.pyw').exists()


def test_developer_windows_builder_runs_real_layout_and_interaction_gates():
    script = (DEV / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert '--check' in script
    assert '--layout-smoke' in script
    assert '--interaction-smoke' in script


def test_v5_manifest_declares_single_windows_user_entry():
    import json
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == (SIM / 'VERSION').read_text(encoding='utf-8').strip()
    assert manifest['windows']['user_entry'] == 'dist/MonoOLEDStudio/MonoOLEDStudio.exe'
    assert manifest['windows']['source_entry_for_developers_only'] is True
    assert manifest['windows']['root_launcher_shipped'] is False
