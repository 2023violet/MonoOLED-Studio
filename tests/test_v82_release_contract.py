from pathlib import Path
import json

SIM=Path(__file__).resolve().parents[1] / 'src'
ROOT=SIM.parent


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.strip().split('.'))


def test_v82_native_interaction_contract_survives_current_release():
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    parts=_version_tuple(version)
    assert len(parts) == 3 and all(p >= 0 for p in parts)
    assert 'APP_VERSION = load_version()' in (SIM/'gui.py').read_text(encoding='utf-8')
    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version']==version
    assert (ROOT/'docs/V12_GENERIC_PRODUCT_CLOSURE.md').is_file()
    assert (ROOT/'tools/VERIFY_V82_STRESS.py').is_file()


def test_v82_windows_gate_includes_native_select_and_theme_surface_tests():
    workflow=(ROOT/'.github/workflows/release-windows.yml').read_text(encoding='utf-8')
    builder=(ROOT/'tools/BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    for marker in ('test_qt_v82_studio_select_state_machine.py','test_qt_v82_preferences_theme_surface.py','VERIFY_V82_STRESS.py'):
        assert marker in workflow
        assert marker in builder
    for scale in ('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0'):
        assert scale in workflow and scale in builder


def test_v82_delivery_tools_exist():
    assert (ROOT/'tools/BUILD_DELIVERY_V82.py').is_file()
    assert (ROOT/'tools/VERIFY_V82_STRESS.py').is_file()
