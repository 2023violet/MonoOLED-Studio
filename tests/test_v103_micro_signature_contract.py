from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_dirty_dot_is_small_semantic_marker_with_reserved_slot():
    from micro_signature import state_dot_spec

    active = state_dot_spec('dirty', active=True)
    idle = state_dot_spec('dirty', active=False)
    assert active.diameter in (5, 6)
    assert active.visible is True
    assert active.opacity >= 0.9
    assert idle.visible is False
    # Slot never collapses, so save/dirty transitions cannot shift the title.
    assert active.slot == idle.slot >= active.diameter + 2


def test_inspector_modified_fields_compare_against_saved_element_baseline():
    from micro_signature import modified_geometry_fields

    baseline = {'id': 'hero', 'x': 8, 'y': 2, 'w': 24, 'h': 16}
    current = {'id': 'hero', 'x': 9, 'y': 2, 'w': 24, 'h': 18}
    assert modified_geometry_fields(current, baseline) == ('x', 'h')
    assert modified_geometry_fields(current, None) == ()


def test_primary_selection_corner_is_small_l_marker_not_full_extra_border():
    from micro_signature import primary_corner_spec

    spec = primary_corner_spec(zoom=8, selected=True, primary=True)
    assert spec.visible is True
    assert spec.stroke == 2
    assert 5 <= spec.arm <= 8
    assert primary_corner_spec(zoom=8, selected=True, primary=False).visible is False
    assert primary_corner_spec(zoom=8, selected=False, primary=True).visible is False


def test_pixel_hover_outline_is_one_pixel_and_stronger_while_drawing():
    from micro_signature import pixel_hover_spec

    hover = pixel_hover_spec(in_bounds=True, drawing=False)
    drawing = pixel_hover_spec(in_bounds=True, drawing=True)
    assert hover.visible is True and hover.stroke == 1
    assert 0.5 <= hover.opacity <= 0.7
    assert drawing.opacity == 1.0
    assert pixel_hover_spec(in_bounds=False, drawing=False).visible is False


def test_popup_selected_marker_is_small_right_side_dot():
    from micro_signature import popup_selected_dot_spec

    spec = popup_selected_dot_spec(selected=True)
    assert spec.visible is True
    assert spec.diameter in (4, 5)
    assert spec.right_margin >= 8
    assert popup_selected_dot_spec(selected=False).visible is False


def test_smart_guide_anchor_points_use_primary_geometry_without_visual_noise():
    from micro_signature import smart_guide_anchor_points

    # Intersections are preferred when both guide axes are active.
    assert smart_guide_anchor_points({'x': (10,), 'y': (6,)}, (8, 4, 6, 4)) == ((10, 6),)
    # A single-axis snap anchors at the primary object's center on the other axis.
    assert smart_guide_anchor_points({'x': (10,), 'y': ()}, (8, 4, 6, 4)) == ((10, 6),)
    assert smart_guide_anchor_points({'x': (), 'y': (6,)}, (8, 4, 6, 4)) == ((11, 6),)
    assert smart_guide_anchor_points({'x': (), 'y': ()}, (8, 4, 6, 4)) == ()


def test_gui_and_canvas_wiring_uses_micro_signature_without_replacing_existing_semantics():
    gui = (ROOT / 'gui.py').read_text(encoding='utf-8')
    canvas = (ROOT / 'qt_canvas.py').read_text(encoding='utf-8')
    pixel = (ROOT / 'pixel_studio_qt.py').read_text(encoding='utf-8')
    controls = (ROOT / 'ui_controls.py').read_text(encoding='utf-8')

    for marker in ('self.document_dirty_dot', '_update_document_dirty_marker', '_update_inspector_modified_markers'):
        assert marker in gui
    assert 'primary_corner_spec' in canvas
    assert 'smart_guide_anchor_points' in canvas
    assert 'pixel_hover_spec' in pixel
    assert 'popup_selected_dot_spec' in controls


def test_v103_delivery_contract_is_published_and_enforced():
    repo = ROOT.parent
    real_qt = repo / 'tests' / 'test_qt_micro_signature_v103.py'
    gate = repo / 'tools' / 'VERIFY_MICRO_SIGNATURE_V103.py'
    assert real_qt.is_file()
    assert gate.is_file()
    assert not (repo / 'docs' / 'releases').exists()
    builder = (repo / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'VERIFY_MICRO_SIGNATURE_V103.py' in builder
    assert (repo / 'docs' / 'ENGINEERING_HISTORY.md').is_file()
