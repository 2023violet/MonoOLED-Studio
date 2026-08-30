from __future__ import annotations

from pathlib import Path
import json
import random
import sys

SIM=Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0,str(SIM))


def test_preferences_defaults_migrate_and_persist(tmp_path):
    from preferences import PreferencesStore, default_preferences, migrate_preferences
    defaults=default_preferences()
    assert defaults['schema_version']==1
    assert defaults['pixel_studio']['left_button']=='draw'
    assert defaults['pixel_studio']['right_button']=='erase'
    migrated=migrate_preferences({'theme':'one-dark-pro','language':'en_US'})
    assert migrated['appearance']['color_theme']=='one-dark-pro'
    p=tmp_path/'prefs.json'; store=PreferencesStore(p,migrated); store.set('appearance.density','compact')
    loaded=PreferencesStore.load(p)
    assert loaded.get('appearance.density')=='compact'
    assert json.loads(p.read_text(encoding='utf-8'))['schema_version']==1


def test_all_themes_have_complete_semantic_tokens():
    from theme_system import THEME_NAMES, REQUIRED_TOKENS, get_theme
    assert set(THEME_NAMES)=={'monooled-light','monooled-dark','one-dark-pro','high-contrast'}
    for name in THEME_NAMES:
        theme=get_theme(name)
        assert all(token in theme and theme[token].startswith('#') for token in REQUIRED_TOKENS)


def test_control_state_separates_hover_selected_and_keyboard_focus():
    from interaction_state import ControlInteraction
    c=ControlInteraction(); c.mouse_enter(); assert c.visual_state=='hover'; c.mouse_leave(); assert c.visual_state=='normal'
    c.set_selected(True); assert c.visual_state=='selected'; c.mouse_enter(); assert c.visual_state=='selected_hover'; c.mouse_leave(); assert c.visual_state=='selected'
    c.mouse_focus(True); assert not c.keyboard_focus_visible
    c.keyboard_focus(True); assert c.keyboard_focus_visible
    c.set_enabled(False); assert c.visual_state=='disabled' and not c.hovered and not c.pressed and not c.keyboard_focus_visible


def test_control_state_fuzz_never_retains_impossible_disabled_state():
    from interaction_state import ControlInteraction
    rng=random.Random(7001); c=ControlInteraction()
    actions=[lambda:c.mouse_enter(),lambda:c.mouse_leave(),lambda:c.mouse_press(),lambda:c.mouse_release(),lambda:c.set_selected(rng.choice([True,False])),lambda:c.keyboard_focus(rng.choice([True,False])),lambda:c.mouse_focus(rng.choice([True,False])),lambda:c.set_enabled(rng.choice([True,False]))]
    for _ in range(10_000):
        rng.choice(actions)()
        if not c.enabled:
            assert not c.hovered and not c.pressed and not c.keyboard_focus_visible


def test_command_registry_rejects_shortcut_conflicts():
    import pytest
    from commands import CommandRegistry, ShortcutConflictError
    r=CommandRegistry(); r.register('a',shortcut='Ctrl+S'); r.register('b')
    with pytest.raises(ShortcutConflictError): r.bind('b','ctrl+s')


def test_pixel_stroke_interpolation_is_continuous_and_one_undo():
    from pixel_studio import PixelDocument
    d=PixelDocument(32,8,max_undo=10); before=[row[:] for row in d.pixels]
    d.begin_gesture(); d.pencil(1,2,1); d.stroke_segment(1,2,14,2,1); d.end_gesture()
    assert all(d.get(x,2)==1 for x in range(1,15))
    assert len(d._undo)==1
    assert d.undo() and d.pixels==before


def test_pixel_undo_history_limit_is_applied_immediately():
    from pixel_studio import PixelDocument
    d=PixelDocument(16,8,max_undo=20)
    for x in range(10): d.pencil(x,0,1)
    d.set_max_undo(3)
    assert len(d._undo)==3 and d.max_undo==3


def test_v7_gui_contract_removes_header_language_and_adds_preferences():
    source=(SIM/'gui.py').read_text(encoding='utf-8')
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    assert 'APP_VERSION = load_version()' in source
    build=source[source.index('        def _build_ui(self):'):source.index('        def _build_menu(self):')]
    assert 'language_combo' not in build
    assert 'header_settings' in build
    assert 'open_preferences' in source and 'PreferencesWindow' in source
    assert "command_registry.shortcut('workspace.canvas_only')" in source
    assert "'workspace.canvas_only': 'Ctrl+Space'" in (SIM/'preferences.py').read_text(encoding='utf-8')


def test_v7_pixel_qt_contract_is_mouse_first_and_flat_inspector():
    source=(SIM/'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert 'Qt.RightButton' in source
    assert 'brush_segment' in source
    assert 'wheelEvent' in source and 'Qt.MiddleButton' in source and 'Qt.Key_Space' in source
    assert 'self.inspector_scroll=QScrollArea()' in source
    assert 'self.inspector_tabs' not in source
    assert "self.tr('pixel.input_hint')" in source


def test_focus_styles_do_not_change_border_width():
    source=(SIM/'qt_theme.py').read_text(encoding='utf-8')
    assert 'QPushButton:focus { border: 2px' not in source
    assert 'QPushButton[keyboardFocusVisible="true"]:focus' in source
    assert 'border: 1px solid' in source
