from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from responsive_layout import plan_layout
from theme_system import get_theme
from ui_metrics import build_ui_metrics


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding='utf-8')


def test_semantic_spacing_scale_is_explicit_and_density_aware() -> None:
    m = build_ui_metrics('comfortable', 1.0)
    assert [m[key] for key in (
        'space_micro', 'space_tight', 'space_compact', 'space_normal',
        'space_group', 'space_section', 'space_section_large', 'space_page', 'space_macro',
    )] == [2, 4, 6, 8, 12, 16, 20, 24, 32]
    assert m['radius_menu'] in (5, 6)
    assert m['radius_control'] == 6
    assert m['radius_panel'] == 8
    assert m['radius_pill'] == 10


def test_light_theme_has_distinct_app_panel_canvas_and_control_surfaces() -> None:
    light = get_theme('monooled-light')
    assert len({
        light['app.background'], light['surface.panel'], light['surface.canvas'], light['surface.toolbar']
    }) == 4
    assert light['surface.selected'] != light['surface.hover']
    assert light['surface.pressed'] != light['surface.hover']


def test_typography_and_control_weight_follow_three_level_contract() -> None:
    qss = source('qt_theme.py')
    assert 'QLabel#CardTitle' not in qss
    assert 'QLabel#CardSubtitle' not in qss
    assert "QLabel#PanelTitle" in qss and 'font-weight: 600' in qss
    assert 'QPushButton {' in qss and 'font-weight: 500' in qss
    assert 'QLabel#TechnicalValue' in qss
    assert '"Cascadia Code", "Consolas"' in qss


def test_canvas_boundary_is_subtle_and_focus_does_not_change_geometry() -> None:
    qss = source('qt_theme.py')
    gui = source('gui.py')
    assert 'QFrame#CanvasWorkspace {' in qss
    assert 'border: 1px solid' in qss
    assert 'QFrame#CanvasWorkspace[canvasFocus="true"]' in qss
    assert "self.canvas_card.setProperty('canvasFocus'," in gui
    assert 'event.type() in (QEvent.FocusIn,QEvent.FocusOut)' in gui.replace(' ', '') or 'QEvent.FocusIn' in gui


def test_command_bar_has_explicit_left_center_right_groups() -> None:
    gui = source('gui.py')
    for marker in ('CommandBarLeft', 'CommandBarCenter', 'CommandBarRight'):
        assert marker in gui
    assert "self.header_save.setObjectName('PrimaryButton')" in gui
    assert "self.header_validate.setObjectName('SecondaryButton')" in gui
    assert "self.header_handoff.setObjectName('SecondaryButton')" in gui
    assert "self.header_settings.setObjectName('GhostButton')" in gui


def test_main_layout_preserves_canvas_floor_and_semantic_breathing_room() -> None:
    for width, height in ((900, 620), (1280, 720), (1440, 900), (1920, 1080)):
        plan = plan_layout(width, height, 'comfortable', 1.0)
        assert plan.canvas_width >= 300
    gui = source('gui.py')
    assert "setObjectName('CanvasViewport')" in gui
    assert "m['space_section']" in gui


def test_settings_uses_compact_rows_without_losing_responsive_bounds() -> None:
    prefs = source('preferences_qt.py')
    qss = source('qt_theme.py')
    assert 'nav_width = 172' in prefs
    assert 'content_max_width = 760' in prefs
    assert 'setMaximumWidth(self.content_max_width)' in prefs
    assert "setObjectName('SettingRow')" in prefs
    assert "setObjectName('PreferencesCard')" not in prefs
    assert "setObjectName('PreferencesDangerCard')" in prefs
    assert "QFrame#PreferencesCard" not in qss and "QFrame#PreferencesDangerCard" in qss
    assert "palette_hint" not in prefs


def test_light_mode_explains_why_dark_palette_is_disabled() -> None:
    prefs = source('preferences_qt.py')
    assert 'self.theme = QComboBox()' not in prefs
    assert "for data in ('system','light','dark')" in prefs


def test_pixel_studio_uses_canvas_first_tool_and_technical_roles() -> None:
    pixel = source('pixel_studio_qt.py')
    assert "setObjectName('PixelCommandBar')" in pixel
    assert "setObjectName('ToolRailButton')" in pixel
    assert "setFixedSize(" in pixel and "tool_buttons" in pixel
    assert "self.pixel_status.setObjectName('TechnicalValue')" in pixel
    assert "self.info.setObjectName('TechnicalValue')" in pixel
    assert "self.selection_info.setObjectName('TechnicalValue')" in pixel
    assert "clearFocus()" in pixel


def test_popup_radius_and_row_geometry_follow_transient_surface_contract() -> None:
    controls = source('ui_controls.py')
    qss = source('qt_theme.py')
    assert 'float(self.width()), float(self.height()), 6.0, 6.0' in controls
    assert "QFrame#StudioSelectPopup" in qss
    assert 'border-radius: {r_popup}px' in qss
    assert 'min-height: {d[\'row\']}px' in qss


def test_empty_and_error_states_have_semantic_roles() -> None:
    gui = source('gui.py')
    qss = source('qt_theme.py')
    assert 'EmptyStateTitle' in gui
    assert 'EmptyStateGuidance' in gui
    assert 'ErrorSummary' in gui
    assert 'QLabel#EmptyStateTitle' in qss
    assert 'QLabel#ErrorSummary' in qss


def test_windows_visual_gate_covers_spec_matrix_and_pixel_studio() -> None:
    gate = (REPO / 'tools' / 'CAPTURE_V9_UI_GOLDENS.py').read_text(encoding='utf-8')
    for marker in (
        "'1.0','1.25','1.5','1.75','2.0'",
        "'zh_CN','en_US'",
        "'light','dark'",
        "'compact','comfortable','spacious'",
        "(1280,720)", "(1440,900)", "(1920,1080)",
        'pixel_studio.png', 'preferences.png', 'main.png',
    ):
        assert marker in gate


def test_runtime_density_and_scale_reapply_layout_metrics_without_rebuilding_product_state() -> None:
    gui = source('gui.py')
    pixel = source('pixel_studio_qt.py')
    widgets = source('qt_widgets.py')
    assert 'def _apply_ui_metrics(self,runtime):' in gui
    assert 'panel.apply_metrics(m)' in gui
    assert 'if initial or metrics_changed:self._apply_ui_metrics(runtime)' in gui
    assert 'def _apply_ui_metrics(self,runtime):' in pixel
    assert 'if delta.ui_metrics_changed:self._apply_ui_metrics(runtime)' in pixel
    assert 'def apply_metrics(self, metrics:' in widgets


def test_preferences_reapplies_semantic_layout_metrics_for_live_scale_changes() -> None:
    prefs = source('preferences_qt.py')
    assert 'self._page_layouts' in prefs
    assert 'self._setting_rows' in prefs
    assert 'def _apply_layout_metrics(self):' in prefs
    assert 'row.set_compact(compact)' in prefs
    assert 'self._outer_layout.setSpacing(18)' in prefs
    assert 'self._apply_layout_metrics()' in prefs


def test_icon_system_uses_16px_default_and_vector_pixel_tools_instead_of_unicode_glyphs() -> None:
    compact = build_ui_metrics('compact', 1.0)
    comfortable = build_ui_metrics('comfortable', 1.0)
    spacious = build_ui_metrics('spacious', 1.0)
    assert (compact['icon'], comfortable['icon'], spacious['icon']) == (16, 16, 18)
    pixel = source('pixel_studio_qt.py')
    assert 'def _tool_icon(' in pixel
    assert 'setIcon(' in pixel and 'setIconSize(' in pixel
    assert "symbols={'Pencil'" not in pixel
    assert 'QPainterPath' in pixel


def test_pixel_canvas_focus_state_is_explicit_and_geometry_stable() -> None:
    pixel = source('pixel_studio_qt.py')
    assert "self.canvas_frame.setProperty('canvasFocus',focused)" in pixel
    assert 'QEvent.FocusIn' in pixel and 'QEvent.FocusOut' in pixel
    assert 'self.canvas.installEventFilter(self)' in pixel


def test_zoom_controls_use_technical_monospace_variant_without_new_type_size() -> None:
    gui = source('gui.py')
    pixel = source('pixel_studio_qt.py')
    qss = source('qt_theme.py')
    assert "self.zoom_combo.button.setProperty('technicalValue',True)" in gui
    assert "self.zoom_combo.button.setProperty('technicalValue',True)" in pixel
    assert 'QPushButton#StudioSelectButton[technicalValue="true"]' in qss
    assert 'font_metadata' in qss


def test_stylesheet_avoids_unapproved_7_or_9px_spacing_literals() -> None:
    qss = source('qt_theme.py')
    for literal in ('padding: 2px 7px', 'padding: 2px 9px', 'spacing: 7px'):
        assert literal not in qss
    assert "padding: {d['space_micro']}px {d['space_normal']}px" in qss
    assert "spacing: {d['space_compact']}px" in qss


def test_interaction_state_is_cleared_when_controls_hide_or_disable() -> None:
    controls = source('ui_controls.py')
    mixin = controls.split('class _InteractionMixin',1)[1].split('class StudioButton',1)[0]
    assert 'def hideEvent(self, event)' in mixin
    hide = mixin.split('def hideEvent(self, event)',1)[1].split('def ',1)[0]
    for state in ('hoverVisible','pressedVisible','keyboardFocusVisible'):
        assert state in hide
    change = mixin.split('def changeEvent(self, event)',1)[1]
    for state in ('hoverVisible','pressedVisible','keyboardFocusVisible'):
        assert state in change


def test_delivery_metadata_and_verifier_publish_v10_ui_craft_contract() -> None:
    # V12 retains the UI-craft behavior and visual gate, but not transitional V10 reports.
    assert not (REPO / 'docs' / 'releases').exists()
    assert not (REPO / 'docs' / 'design').exists()
    assert (REPO / 'docs' / 'DESIGN_SYSTEM.md').is_file()
    assert (REPO / 'tools' / 'CAPTURE_V9_UI_GOLDENS.py').is_file()
    verifier = (REPO / 'VERIFY_PACKAGE.py').read_text(encoding='utf-8')
    assert 'documentation_policy' not in verifier or 'V12' in verifier
    assert 'CURRENT_DOCS' in verifier

