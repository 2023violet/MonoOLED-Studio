from __future__ import annotations
import json
from pathlib import Path

SIM=Path(__file__).resolve().parents[1] / 'src'
ROOT=SIM.parent


def test_v83_release_identity_and_documents():
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    parts=tuple(map(int,version.split('.')))
    assert len(parts) == 3 and all(p >= 0 for p in parts)
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    prefs=(SIM/'preferences_qt.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = load_version()' in gui
    assert 'Version {APP_VERSION}' in prefs
    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert (ROOT/'docs/V12_GENERIC_PRODUCT_CLOSURE.md').is_file()

def test_v83_windows_release_gate_is_zero_skip_and_real_startup():
    workflow=(ROOT/'.github/workflows/release-windows.yml').read_text(encoding='utf-8')
    builder=(ROOT/'tools/BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    spec=(ROOT/'tools/MonoOLEDStudio.spec').read_text(encoding='utf-8')
    for marker in ('test_qt_v83_reliability.py','1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0'):
        assert marker in workflow and marker in builder
    for marker in ('VERIFY_JUNIT_NO_SKIPS.py','--startup-smoke','VERIFY_V83_STRESS.py'):
        assert marker in builder
    assert "ROOT / 'src' / 'gui.py'" in spec
    assert not (ROOT/'MonoOLEDStudio.exe').exists()
    assert (ROOT/'tools/CREATE_RUNTIME_ENV.bat').is_file()
    assert (ROOT/'tools/RUN_MONOOLED_DIAGNOSTIC.bat').is_file()

def test_v83_reliability_performance_modules_are_present():
    for name in ('resource_cache.py','atomic_io.py','diagnostics.py'):
        assert (SIM/name).is_file()
    assert (ROOT/'tools/VERIFY_V83_STRESS.py').is_file()
    assert (ROOT/'tools/BUILD_DELIVERY_V83.py').is_file()
    assert (ROOT/'tools/VERIFY_JUNIT_NO_SKIPS.py').is_file()
