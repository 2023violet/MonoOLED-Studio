from __future__ import annotations

import json
from pathlib import Path

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS

SIM = Path(__file__).resolve().parents[1] / 'src'
ROOT = SIM.parent


def test_v842_release_identity_and_docs():
    version = (SIM / 'VERSION').read_text(encoding='utf-8').strip()
    parts = tuple(map(int, version.split('.')))
    assert len(parts) == 3 and all(p >= 0 for p in parts)
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = load_version()' in gui
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert manifest['automation_api']['version'] == '1.2.0'
    assert manifest['delivery_profile'] == 'source'
    assert (ROOT / 'docs' / 'AUTOMATION_API_V1.md').is_file()
    assert (ROOT / 'docs' / 'ENGINEERING_HISTORY.md').is_file()

def test_v842_api_contract_is_1_2_and_contains_reliability_methods():
    assert AUTOMATION_API_VERSION == '1.2.0'
    contract = json.loads((SIM / 'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    assert contract['api_version'] == AUTOMATION_API_VERSION
    assert set(contract['methods']) == set(METHOD_SPECS)
    required = {
        'state.count', 'job.start', 'job.status', 'job.result', 'job.cancel',
        'project.open_screen', 'history.commit', 'history.rollback',
    }
    assert required <= set(METHOD_SPECS)
    for name in ('history.commit', 'history.rollback'):
        assert contract['methods'][name]['params']['transaction']['required'] is True
    open_spec = contract['methods']['project.open_screen']['params']
    assert {'screen_id', 'save_current', 'discard_current'} <= set(open_spec)


def test_v842_windows_and_delivery_gates_are_present():
    builder = (ROOT / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'src\\VERSION' in builder
    assert 'MonoOLED Studio V%VER%' in builder
    assert 'VERIFY_V842_FINAL.py' in builder
    assert 'VERIFY_V841_FINAL.py' in builder
    assert 'VERIFY_JUNIT_NO_SKIPS.py' in builder
    workflow = (ROOT / '.github' / 'workflows' / 'release-windows.yml').read_text(encoding='utf-8')
    assert 'BUILD_WINDOWS_GA.bat' in workflow
    for rel in (
        'tools/VERIFY_V842_FINAL.py',
        'tools/BUILD_DELIVERY_V842.py',
    ):
        assert (ROOT / rel).is_file(), rel
