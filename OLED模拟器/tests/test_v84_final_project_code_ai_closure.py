from __future__ import annotations

import json
from pathlib import Path

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS

SIM = Path(__file__).resolve().parents[1]
ROOT = SIM.parent


def test_v84_release_identity_and_final_documents():
    assert (SIM / 'VERSION').read_text(encoding='utf-8').strip() == '8.4.0'
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert "APP_VERSION = '8.4.0'" in gui
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == '8.4.0'
    assert manifest['release_name'] == 'Final Project & Code AI Closure'
    for name in (
        'FINAL_PROJECT_CODE_AI_CLOSURE_V84.md',
        'CODE_AI_AUTOMATION_API_V1.md',
        'TEST_MATRIX_V84.md',
        'FINAL_VERIFICATION_REPORT.md',
        'USER_GUIDE_CN.md',
    ):
        assert (SIM / name).is_file(), name


def test_automation_api_v1_contract_file_matches_production_method_specs():
    assert AUTOMATION_API_VERSION == '1.0.0'
    contract_path = SIM / 'AUTOMATION_API_V1.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    assert contract['api_version'] == AUTOMATION_API_VERSION
    assert set(contract['methods']) == set(METHOD_SPECS)
    required = {
        'automation.capabilities', 'automation.describe_method',
        'project.open_screen', 'project.create_screen', 'project.duplicate_screen',
        'project.rename_screen', 'project.delete_screen', 'project.save_all',
        'state.enumerate', 'render.all_states', 'validate.all_states',
        'asset.create', 'asset.import', 'asset.rename', 'asset.delete',
        'pixel.create', 'render.preview_file', 'render.annotated_preview',
        'export.current', 'export.all', 'export.code_ai_handoff',
    }
    assert required <= set(contract['methods'])


def test_v84_windows_gate_runs_automation_graduation_and_all_real_qt_zero_skip():
    builder = (ROOT / 'Developer_Tools' / 'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    assert 'MonoOLED Studio v8.4' in builder
    assert 'VERIFY_V84_FINAL.py' in builder
    assert "test_qt_*.py" in builder
    assert 'VERIFY_JUNIT_NO_SKIPS.py' in builder
    for dpi in ('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0'):
        assert dpi in builder


def test_v84_project_agent_bridge_is_bound_to_project_workspace_and_initial_fonts_scan():
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'project_workspace=self.project' in gui
    init_slice = gui[gui.index('self._rebuild_screens()'):gui.index('self._capture_saved_baseline()')]
    assert 'self._scan_fonts()' in init_slice
    bridge = (SIM / 'agent_bridge.py').read_text(encoding='utf-8')
    assert "--project" in bridge
    assert "automation_api" in bridge


def test_v84_release_tools_present():
    for rel in (
        'Developer_Tools/VERIFY_V84_FINAL.py',
        'Developer_Tools/BUILD_DELIVERY_V84.py',
        'Developer_Tools/EXPORT_AUTOMATION_API_V1.py',
    ):
        assert (ROOT / rel).is_file(), rel
