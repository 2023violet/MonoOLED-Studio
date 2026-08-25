from __future__ import annotations

import json
from pathlib import Path

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS

SIM = Path(__file__).resolve().parents[1]
ROOT = SIM.parent


def test_v841_release_identity_and_documents():
    # Historical closure contract: later 8.4.x bugfix/GA releases must retain the
    # V8.4.1 state-model artifacts and API capabilities without forcing current
    # release identity back to 8.4.1.
    version = (SIM / 'VERSION').read_text(encoding='utf-8').strip()
    assert tuple(map(int, version.split('.')[:3])) >= (8, 4, 1)
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert f"APP_VERSION = '{version}'" in gui
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert str(manifest['automation_api']['version']).startswith('1.')
    for name in (
        'AUTOMATION_STATE_MODEL_CLOSURE_V841.md',
        'CODE_AI_AUTOMATION_API_V1.md',
        'AUTOMATION_API_V1.json',
        'TEST_MATRIX_V841.md',
        'FINAL_VERIFICATION_REPORT.md',
    ):
        assert (SIM / name).is_file(), name


def test_v841_machine_contract_matches_production_and_has_state_model_methods():
    assert AUTOMATION_API_VERSION.startswith('1.')
    contract = json.loads((SIM / 'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    assert contract['api_version'] == AUTOMATION_API_VERSION
    assert set(contract['methods']) == set(METHOD_SPECS)
    assert {'state.validate_schema', 'state.set_schema', 'state.validate'} <= set(contract['methods'])
    assert contract['methods']['state.set_schema']['transaction_supported'] is True
    assert contract['methods']['font.generate_glyphs']['params']['characters']['required'] is True


def test_v841_release_tools_and_windows_gate_include_state_model_graduation():
    for rel in (
        'Developer_Tools/VERIFY_V841_FINAL.py',
        'Developer_Tools/BUILD_DELIVERY_V841.py',
        'Developer_Tools/EXPORT_AUTOMATION_API_V1.py',
    ):
        assert (ROOT / rel).is_file(), rel
    builder = (ROOT / 'Developer_Tools' / 'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    assert 'MonoOLED Studio v8.4.' in builder
    assert 'VERIFY_V841_FINAL.py' in builder
    assert 'VERIFY_V84_FINAL.py' in builder
    assert 'test_qt_*.py' in builder
    assert 'VERIFY_JUNIT_NO_SKIPS.py' in builder


def test_v841_state_schema_module_is_product_independent():
    source = (SIM / 'state_schema.py').read_text(encoding='utf-8')
    assert 'total_cycles' not in source
    assert 'current_cycle' not in source
    assert "_RELATION_OPERATORS = {'<', '<=', '==', '!=', '>=', '>'}" in source
