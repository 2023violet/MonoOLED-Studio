from __future__ import annotations

import json
from pathlib import Path

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS

SIM = Path(__file__).resolve().parents[1] / 'src'
ROOT = SIM.parent


def test_v841_release_identity_and_documents():
    version = (SIM / 'VERSION').read_text(encoding='utf-8').strip()
    parts = tuple(map(int, version.split('.')))
    assert len(parts) == 3 and all(p >= 0 for p in parts)
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = load_version()' in gui
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert str(manifest['automation_api']['version']).startswith('1.')
    assert (SIM / 'AUTOMATION_API_V1.json').is_file()
    assert (ROOT / 'docs' / 'AUTOMATION_API_V1.md').is_file()
    assert (ROOT / 'docs' / 'V12_GENERIC_PRODUCT_CLOSURE.md').is_file()

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
        'tools/VERIFY_V841_FINAL.py',
        'tools/BUILD_DELIVERY_V841.py',
        'tools/EXPORT_AUTOMATION_API_V1.py',
    ):
        assert (ROOT / rel).is_file(), rel
    builder = (ROOT / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'src\\VERSION' in builder
    assert 'MonoOLED Studio V%VER%' in builder
    assert 'VERIFY_V841_FINAL.py' in builder
    assert 'VERIFY_V84_FINAL.py' in builder
    assert 'test_qt_*.py' in builder
    assert 'VERIFY_JUNIT_NO_SKIPS.py' in builder


def test_v841_state_schema_module_is_product_independent():
    source = (SIM / 'state_schema.py').read_text(encoding='utf-8')
    assert 'total_cycles' not in source
    assert 'current_cycle' not in source
    assert "_RELATION_OPERATORS = {'<', '<=', '==', '!=', '>=', '>'}" in source
