from __future__ import annotations

import json
from pathlib import Path

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS

SIM = Path(__file__).resolve().parents[1] / 'src'
ROOT = SIM.parent


def test_v84_release_identity_and_final_documents():
    version=(SIM / 'VERSION').read_text(encoding='utf-8').strip()
    assert tuple(map(int,version.split('.'))) >= (8,4,0)
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = load_version()' in gui
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    for path in (
        ROOT/'docs/AUTOMATION_API_V1.md', ROOT/'docs/USER_GUIDE_CN.md',
        ROOT/'docs/V12_GENERIC_PRODUCT_CLOSURE.md', SIM/'AUTOMATION_API_V1.json',
    ):
        assert path.is_file(), path

def test_automation_api_v1_contract_file_matches_production_method_specs():
    assert AUTOMATION_API_VERSION .startswith('1.')
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
    builder = (ROOT / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'src\\VERSION' in builder
    assert 'MonoOLED Studio V%VER%' in builder
    assert 'VERIFY_V84_FINAL.py' in builder
    assert "test_qt_*.py" in builder
    assert 'VERIFY_JUNIT_NO_SKIPS.py' in builder
    for dpi in ('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0'):
        assert dpi in builder


def test_v84_project_agent_bridge_is_bound_to_project_workspace_and_fonts_scan_is_preserved_post_show():
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'project_workspace=self.project' in gui
    # V10.4 keeps Font Lab discovery but removes it from the constructor's
    # time-to-visible critical path. The post-show startup phase owns it.
    startup = gui[gui.index('def _schedule_post_show_startup'):gui.index('def _build_menu')]
    assert 'self._post_show_scan_fonts' in startup
    assert 'self._scan_fonts()' in startup
    init_slice = gui[gui.index('self._rebuild_screens()'):gui.index('self._capture_saved_baseline()')]
    assert 'self._scan_fonts()' not in init_slice
    bridge = (SIM / 'agent_bridge.py').read_text(encoding='utf-8')
    assert "--project" in bridge
    assert "automation_api" in bridge


def test_v84_release_tools_present():
    for rel in (
        'tools/VERIFY_V84_FINAL.py',
        'tools/BUILD_DELIVERY_V84.py',
        'tools/EXPORT_AUTOMATION_API_V1.py',
    ):
        assert (ROOT / rel).is_file(), rel
