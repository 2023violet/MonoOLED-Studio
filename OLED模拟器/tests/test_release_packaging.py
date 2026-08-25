from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / 'OLED模拟器'
DEV = ROOT / 'Developer_Tools'


def test_runtime_and_build_requirements_pin_qt_and_pyinstaller():
    runtime = (SIM / 'requirements.txt').read_text(encoding='utf-8')
    build = (SIM / 'requirements-build.txt').read_text(encoding='utf-8')
    assert 'PySide6-Essentials==6.11.2' in runtime
    assert 'PyInstaller==6.22.0' in build
    assert '-r requirements.txt' in build


def test_windows_build_script_builds_and_smoke_checks_exe():
    script = (DEV / 'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    assert 'MonoOLEDStudio.spec' in script
    assert 'MonoOLEDStudio.exe' in script
    assert '--check' in script
    assert '--smoke-ms' in script
    assert '--layout-smoke' in script
    assert '--interaction-smoke' in script
    assert 'Get-FileHash' in script


def test_pyinstaller_spec_is_onedir_and_bundles_required_data():
    spec = (DEV / 'MonoOLEDStudio.spec').read_text(encoding='utf-8')
    assert "name='MonoOLEDStudio'" in spec
    assert 'COLLECT(' in spec
    assert "'OLED模拟器/scenes'" in spec
    assert "'数字 - 字宽13字高27'" in spec
    assert "'电池图标 - 字宽11字高28'" in spec
    assert "'Curing_Lite光固化机产品 - UI设计初稿'" in spec
    assert "contents_directory='.'" in spec


def test_release_version_is_at_least_v5():
    version=(SIM / 'VERSION').read_text(encoding='utf-8').strip()
    assert tuple(map(int,version.split('.'))) >= (5,0,0)


def test_v5_user_root_has_only_one_launch_entry_and_developer_tools_are_nested():
    assert (ROOT / 'MonoOLEDStudio.exe').exists()
    assert not list(ROOT.glob('*.bat'))
    assert not (ROOT / 'MonoOLEDStudio.spec').exists()
    assert (DEV / 'BUILD_WINDOWS_EXE.bat').exists()
    assert (DEV / 'MonoOLEDStudio.spec').exists()
    assert not (ROOT / 'CuringLiteOLEDDesigner_SourceLauncher.exe').exists()
    assert not (ROOT / 'CuringLiteOLEDDesigner_SourceLauncher-script.pyw').exists()


def test_developer_windows_builder_runs_real_layout_and_interaction_gates():
    script = (DEV / 'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    assert '--check' in script
    assert '--layout-smoke' in script
    assert '--interaction-smoke' in script


def test_v5_manifest_declares_single_windows_user_entry():
    import json
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == (SIM / 'VERSION').read_text(encoding='utf-8').strip()
    assert manifest['windows']['user_entry'] == 'MonoOLEDStudio.exe'
    assert manifest['windows']['source_entry_for_developers_only'] is True
