from pathlib import Path

import pytest

from theme_system import resolve_theme_name
from popup_state import CloseReason, PopupInteractionState, PopupStateMachine

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_dark_and_system_dark_resolve_to_one_dark_pro():
    assert resolve_theme_name('legacy', 'dark', system_dark=False) == 'one-dark-pro'
    assert resolve_theme_name('legacy', 'system', system_dark=True) == 'one-dark-pro'
    assert resolve_theme_name('legacy', 'light', system_dark=True) == 'monooled-light'


def test_popup_suppression_is_release_scoped_not_timer_scoped():
    source = (ROOT / 'ui_controls.py').read_text(encoding='utf-8')
    select_block = source[source.index('class StudioSelect'):source.index('class _MissingQt')]
    assert 'setMinimumHeight(30)' not in select_block
    assert 'singleShot(0, self._popup_state.clear_anchor_suppression)' not in select_block
    assert 'release_anchor_suppression' in source


def test_popup_state_machine_keeps_anchor_suppressed_until_release():
    sm = PopupStateMachine()
    assert sm.anchor_press() == 'open'
    sm.opened()
    assert sm.anchor_press() == 'close'
    sm.closed(CloseReason.ANCHOR_TOGGLE)
    assert sm.state is PopupInteractionState.CLOSED
    assert sm.anchor_suppressed is True
    # clicked/release is swallowed without clearing the state before the release boundary.
    assert sm.consume_anchor_click() is True
    assert sm.anchor_suppressed is True
    sm.release_anchor_suppression()
    assert sm.anchor_suppressed is False
    assert sm.anchor_press() == 'open'


def test_preferences_geometry_is_roomier_and_no_fixed_620_content_cap():
    source = (ROOT / 'preferences_qt.py').read_text(encoding='utf-8')
    assert 'self.resize(980, 720)' in source
    assert 'content_max_width = 760' in source
    assert 'content.setMaximumWidth(self.content_max_width)' in source
    assert 'QBoxLayout' in source
    assert 'self._text_column' in source
    assert 'self._control_column' in source
    assert 'row.set_compact(compact)' in source


def test_performance_pipeline_exists_and_separates_hot_path_from_deferred_work():
    from ui_performance import RefreshWorkPlan, InteractionTrace

    fast = RefreshWorkPlan.for_interaction('selection')
    assert fast.render is True
    assert fast.properties is True
    assert fast.validation is False
    assert fast.diff is False
    assert fast.evidence is False
    assert fast.asset_watcher is False

    commit = RefreshWorkPlan.for_scene_commit()
    assert commit.render is True
    assert commit.validation_deferred is True
    assert commit.diff_deferred is True
    assert commit.evidence_deferred is True

    trace = InteractionTrace('click')
    trace.mark('handler')
    trace.mark('paint_requested')
    payload = trace.as_dict()
    assert payload['name'] == 'click'
    assert payload['elapsed_ms'] >= 0
    assert [m['stage'] for m in payload['marks']] == ['handler', 'paint_requested']


def test_gui_startup_defers_asset_and_font_scans_until_after_first_show():
    source = (ROOT / 'gui.py').read_text(encoding='utf-8')
    assert 'def _schedule_post_show_startup' in source
    assert "QTimer.singleShot(0,self._schedule_post_show_startup)" in source.replace(' ', '') or 'QTimer.singleShot(0, self._schedule_post_show_startup)' in source
    init_region = source[source.index('class OLEDDesignerWindow'):source.index('def _schedule_post_show_startup')]
    # Constructor may build list widgets, but must not synchronously enumerate project assets/fonts.
    assert 'self._scan_assets(); self._scan_fonts()' not in init_region


def test_refresh_all_has_deferred_pipeline_hooks():
    source = (ROOT / 'gui.py').read_text(encoding='utf-8')
    assert 'def _schedule_deferred_refresh' in source
    assert 'def _run_deferred_refresh' in source
    refresh = source[source.index('def refresh_all'):source.index('def _update_asset_watcher')]
    assert 'frame_evidence(' not in refresh
    assert '_update_validation_panel()' not in refresh
    assert '_update_diff(' not in refresh


def test_asset_scan_reuses_decoded_cache_only_after_content_hash_matches():
    source = (ROOT / 'asset_library.py').read_text(encoding='utf-8')
    scan = source[source.index('    def scan(self)'):source.index('    @property\n    def entries')]
    # Performance may skip bitmap decoding, but never content verification:
    # same-size/same-mtime rewrites must still invalidate stale pixels.
    assert 'content_hash = sha256(resolved.read_bytes()).hexdigest()' in scan
    assert 'cached is not None and cached[2] == content_hash' in scan
    assert "cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size" not in scan


def test_outside_click_only_suppresses_when_pointer_is_on_select_anchor():
    source = (ROOT / 'ui_controls.py').read_text(encoding='utf-8')
    select = source[source.index('class StudioSelect'):source.index('class StudioSegmentedControl')]
    assert 'def _pointer_is_over_anchor' in select
    assert 'self._pointer_is_over_anchor()' in select
    assert 'owner_anchor=owner_anchor' in select


def test_windows_v104_gate_covers_dropdown_clipping_theme_and_latency():
    gate = ROOT.parent / 'tools' / 'VERIFY_V104_UX_STABILITY.py'
    assert gate.is_file()
    source = gate.read_text(encoding='utf-8')
    for marker in (
        'one-dark-pro', 'SECOND_CLICK_STAYS_CLOSED', 'OUTSIDE_CLICK_REOPENS_NEXT',
        'VISIBLE_REGION_COVERS_CONTROL', 'STARTUP_VISIBLE_MS', 'INTERACTION_MS',
        'PreferencesView', 'StudioSelect',
    ):
        assert marker in source


def test_windows_builder_runs_v104_gate():
    build = (ROOT.parent / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'VERIFY_V104_UX_STABILITY.py' in build
