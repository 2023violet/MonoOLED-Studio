from __future__ import annotations
import json
from pathlib import Path

SIM=Path(__file__).resolve().parents[1]
ROOT=SIM.parent


def test_v83_release_identity_and_documents():
    assert tuple(map(int,(SIM/'VERSION').read_text(encoding='utf-8').strip().split('.'))) >= (8,3,0)
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    prefs=(SIM/'preferences_qt.py').read_text(encoding='utf-8')
    assert 'APP_VERSION' in gui
    assert 'Version 8.' in prefs
    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert tuple(map(int,manifest['version'].split('.'))) >= (8,3,0)
    for name in ('RELIABILITY_PERFORMANCE_CLOSURE_V83.md','TEST_MATRIX_V83.md','FINAL_VERIFICATION_REPORT.md','USER_GUIDE_CN.md'):
        assert (SIM/name).is_file()


def test_v83_windows_release_gate_is_zero_skip_and_real_startup():
    workflow=(ROOT/'.github/workflows/build-windows-exe.yml').read_text(encoding='utf-8')
    builder=(ROOT/'Developer_Tools/BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    launcher=(SIM/'windows_launcher.c').read_text(encoding='utf-8')
    for marker in ('test_qt_v83_reliability.py','1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0'):
        assert marker in workflow and marker in builder
    for marker in ('VERIFY_JUNIT_NO_SKIPS.py','--startup-smoke','VERIFY_V83_STRESS.py'):
        assert marker in builder
    assert 'startup_smoke_ok' in launcher
    assert '.venv-runtime' in launcher
    assert (ROOT/'Developer_Tools/CREATE_RUNTIME_ENV.bat').is_file()
    assert (ROOT/'Developer_Tools/RUN_MONOOLED_DIAGNOSTIC.bat').is_file()


def test_v83_reliability_performance_modules_are_present():
    for name in ('resource_cache.py','atomic_io.py','diagnostics.py'):
        assert (SIM/name).is_file()
    assert (ROOT/'Developer_Tools/VERIFY_V83_STRESS.py').is_file()
    assert (ROOT/'Developer_Tools/BUILD_DELIVERY_V83.py').is_file()
    assert (ROOT/'Developer_Tools/VERIFY_JUNIT_NO_SKIPS.py').is_file()
