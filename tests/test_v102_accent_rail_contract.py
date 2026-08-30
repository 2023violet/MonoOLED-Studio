from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_accent_rail_scope_and_state_language():
    from ui_controls import accent_rail_spec

    # Secondary text buttons use a left rail. Hover is deliberately softer;
    # pressed/checked states are full-strength and persistent.
    hover = accent_rail_spec('SecondaryButton', 120, 32, hovered=True)
    assert hover.orientation == 'left'
    assert hover.opacity == 0.68
    assert hover.width == 2
    assert 11 <= hover.height <= 15

    pressed = accent_rail_spec('SecondaryButton', 120, 32, pressed=True)
    assert pressed.opacity == 1.0

    # Icon/tool/segmented affordances use a short bottom rail.
    for object_name in ('GhostButton', 'ToolRailButton', 'StudioSegment'):
        checked = accent_rail_spec(object_name, 32 if object_name != 'StudioSegment' else 90, 32, checked=True)
        assert checked.orientation == 'bottom'
        assert checked.opacity == 1.0
        assert checked.height == 2
        assert 10 <= checked.width <= 14


def test_accent_rail_excludes_primary_danger_disabled_and_idle():
    from ui_controls import accent_rail_spec

    for object_name in ('PrimaryButton', 'DangerButton', 'StudioSelectButton', ''):
        assert accent_rail_spec(object_name, 100, 32, hovered=True).visible is False

    assert accent_rail_spec('SecondaryButton', 100, 32).visible is False
    assert accent_rail_spec('SecondaryButton', 100, 32, hovered=True, enabled=False).visible is False


def test_accent_rail_geometry_is_overlay_only_and_inside_button_bounds():
    from ui_controls import accent_rail_spec

    left = accent_rail_spec('SecondaryButton', 120, 36, checked=True)
    assert (left.x, left.width) == (3, 2)
    assert left.y >= 0 and left.y + left.height <= 36

    bottom = accent_rail_spec('ToolRailButton', 36, 36, checked=True)
    assert bottom.y == 31
    assert bottom.x >= 0 and bottom.x + bottom.width <= 36


def test_accent_rail_hover_animation_is_short_and_pressed_is_immediate():
    from ui_controls import ACCENT_RAIL_HOVER_MS, accent_rail_transition_ms

    assert 100 <= ACCENT_RAIL_HOVER_MS <= 120
    assert accent_rail_transition_ms(previous=0.0, target=0.68, pressed=False, checked=False) == ACCENT_RAIL_HOVER_MS
    assert accent_rail_transition_ms(previous=0.68, target=1.0, pressed=True, checked=False) == 0
    assert accent_rail_transition_ms(previous=0.68, target=1.0, pressed=False, checked=True) == 0


def test_qss_does_not_fake_accent_rail_with_border_or_padding_shift():
    src = (ROOT / 'qt_theme.py').read_text(encoding='utf-8')
    button_qss = src.split('QPushButton {{', 1)[1].split('QWidget#StudioSelect {{', 1)[0]
    assert 'border-left: 2px' not in button_qss
    assert 'border-bottom: 2px' not in button_qss
    assert 'ACCENT RAIL IS PAINTED AS AN OVERLAY' in src


def test_v102_delivery_contract_is_published_and_enforced():
    repo = ROOT.parent
    gate = repo / 'tools' / 'VERIFY_ACCENT_RAIL_V102.py'
    assert gate.is_file()
    assert not (repo / 'docs' / 'releases').exists()
    builder = (repo / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'VERIFY_ACCENT_RAIL_V102.py' in builder
    assert (repo / 'docs' / 'V12_GENERIC_PRODUCT_CLOSURE.md').is_file()

