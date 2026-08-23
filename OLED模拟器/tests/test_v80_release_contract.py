from __future__ import annotations
import json
from pathlib import Path

SIM=Path(__file__).resolve().parents[1]
ROOT=SIM.parent


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.strip().split('.'))


def test_v80_unified_workspace_contract_survives_current_release():
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    assert _version_tuple(version) >= (8,0,0)
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    assert f"APP_VERSION = '{version}'" in gui
    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version']==version
    workflow=(ROOT/'.github/workflows/build-windows-exe.yml').read_text(encoding='utf-8')
    builder=(ROOT/'Developer_Tools/BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    for marker in ('test_qt_v80_unified_workspace.py','1.0','1.25','1.5','2.0'):
        assert marker in workflow and marker in builder
    assert (ROOT/'Developer_Tools/VERIFY_V80_STRESS.py').is_file()
    assert (ROOT/'Developer_Tools/BUILD_DELIVERY_V80.py').is_file()


def test_unified_workspace_architecture_contract_is_present():
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    canvas=(SIM/'qt_canvas.py').read_text(encoding='utf-8')
    for marker in ('self.editor_tabs','SelectionModel','align_to','FontLabEditor','QtAutomationBridge'):
        assert marker in gui
    assert 'elementSelected.connect(self.select_element)' not in gui
    assert 'Qt.ControlModifier' in canvas and '_marquee' in canvas
    pixel=(SIM/'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert 'Qt.Widget' in pixel and '_fit_zoom' in pixel and 'CanvasResizeDialog' in pixel
    automation=(SIM/'automation_service.py').read_text(encoding='utf-8')
    for marker in ('render.png','render.pixel_diff','font.generate_glyphs','pixel.resize_canvas'):
        assert marker in automation
