from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_preview_state_and_timeline_require_explicit_preview_capabilities():
    from preview_capabilities import preview_capabilities

    curing_like = {
        'states': {'mode': {'type': 'enum', 'values': ['NORMAL'], 'init': 'NORMAL'}},
        'timeline': [{'at': 0, 'set': {'mode': 'NORMAL'}}],
    }
    assert preview_capabilities(curing_like) == ('frame', 'validation')
    opted_in = {
        **curing_like,
        'preview': {'capabilities': ['state', 'timeline']},
    }
    assert preview_capabilities(opted_in) == ('frame', 'state', 'timeline', 'validation')


def test_canvas_context_actions_hide_unavailable_instead_of_showing_dead_buttons():
    from workspace_chrome import canvas_context_actions

    assert canvas_context_actions([], 'design', []) == ()
    assert canvas_context_actions(['a'], 'review', [False]) == ()
    actions = canvas_context_actions(['a'], 'design', [False])
    assert actions == ('duplicate', 'lock')
    actions_locked = canvas_context_actions(['a', 'b'], 'design', [True, True])
    assert actions_locked == ('duplicate', 'unlock')
    assert 'pixel' not in actions


def test_editor_tab_is_single_source_for_header_chrome_state():
    from workspace_chrome import editor_chrome_state

    settings = editor_chrome_state('settings:preferences', 'pixel')
    assert settings.segment_index == -1
    assert settings.settings_active is True

    pixel = editor_chrome_state('asset:C:/x.png', 'design')
    assert pixel.segment_index == 1
    assert pixel.settings_active is False

    scene = editor_chrome_state('scene:active', 'review')
    assert scene.segment_index == 2
    assert scene.settings_active is False


def test_pixel_hover_damage_is_local_and_does_not_require_full_canvas_repaint():
    from pixel_hover_performance import hover_damage_rects

    assert hover_damage_rects(None, (3, 4), 20) == ((59, 79, 22, 22),)
    assert hover_damage_rects((3, 4), (4, 4), 20) == ((59, 79, 22, 22), (79, 79, 22, 22))
    assert hover_damage_rects((3, 4), (3, 4), 20) == ()


def test_preferences_first_display_has_explicit_layout_stabilization_contract():
    source = (ROOT / 'preferences_qt.py').read_text(encoding='utf-8')
    gui = (ROOT / 'gui.py').read_text(encoding='utf-8')
    assert 'def stabilize_layout(self)' in source
    assert 'def showEvent(self,event)' in source or 'def showEvent(self, event)' in source
    assert 'view.stabilize_layout()' in gui
    assert 'QSizePolicy.Fixed' in source


def test_pixel_canvas_uses_cached_base_and_local_hover_update_path():
    source = (ROOT / 'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert '_base_cache' in source
    assert 'def _invalidate_base_cache' in source
    assert 'def _set_hover_state' in source
    assert 'hover_damage_rects' in source
    # The hover-only path must not call an unconditional full widget update.
    body = source.split('def _set_hover_state', 1)[1].split('def ', 1)[0]
    assert 'self.update()' not in body


def test_workspace_mode_switch_does_not_force_scene_render_and_context_has_no_duplicate_pixel_entry():
    source = (ROOT / 'gui.py').read_text(encoding='utf-8')
    region = source[source.index('def set_workspace_mode'):source.index('def _workspace_segment_changed')]
    assert 'refresh_all(' not in region
    context_region = source[source.index("self.context_bar=QWidget()"):source.index('self.canvas=OLEDCanvas()')]
    assert 'context_pixel' not in context_region
    assert 'context_duplicate' in context_region and 'context_lock' in context_region


def test_segmented_control_can_clear_selection_for_non_workspace_editor_tabs():
    source = (ROOT / 'ui_controls.py').read_text(encoding='utf-8')
    assert 'requested=int(index)' in source
    assert 'index=-1 if requested<0' in source
    assert 'def clearSelection(self)' in source


def test_windows_builder_runs_v111_real_qt_gate():
    gate = ROOT.parent / 'tools' / 'VERIFY_V111_USABILITY_STABILITY.py'
    build = ROOT.parent / 'tools' / 'BUILD_WINDOWS_GA.bat'
    assert gate.is_file()
    source = gate.read_text(encoding='utf-8')
    for marker in ('SETTINGS_FIRST_LAYOUT', 'GENERIC_PREVIEW', 'CONTEXT_ACTIONS', 'PIXEL_HOVER', 'EDITOR_CHROME'):
        assert marker in source
    assert 'VERIFY_V111_USABILITY_STABILITY.py' in build.read_text(encoding='utf-8')
