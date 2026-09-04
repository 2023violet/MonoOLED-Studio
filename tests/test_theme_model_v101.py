from __future__ import annotations

from pathlib import Path

from preference_delta import PreferenceDelta
from preferences import default_preferences
from runtime_settings import RuntimeSettings
from theme_system import THEME_NAMES, resolve_theme_name

SIM = Path(__file__).resolve().parents[1] / 'src'


def _runtime(*, mode: str = 'system', legacy_palette: str = 'monooled-light') -> RuntimeSettings:
    prefs = default_preferences()
    prefs['appearance']['theme_mode'] = mode
    prefs['appearance']['color_theme'] = legacy_palette
    return RuntimeSettings.from_preferences(prefs)


def _function_body(source: str, name: str) -> str:
    marker = f'def {name}('
    start = source.index(marker)
    tail = source[start:]
    lines = tail.splitlines()
    indent = len(lines[0]) - len(lines[0].lstrip())
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return '\n'.join(body)


def test_appearance_mode_is_the_only_user_theme_authority() -> None:
    for legacy_palette in THEME_NAMES:
        assert resolve_theme_name(legacy_palette, 'light', system_dark=True) == 'monooled-light'
        assert resolve_theme_name(legacy_palette, 'dark', system_dark=False) == 'one-dark-pro'
        assert resolve_theme_name(legacy_palette, 'system', system_dark=False) == 'monooled-light'
        assert resolve_theme_name(legacy_palette, 'system', system_dark=True) == 'one-dark-pro'


def test_legacy_palette_change_is_a_noop_for_runtime_theme_effects() -> None:
    before = _runtime(mode='system', legacy_palette='monooled-light')
    after = _runtime(mode='system', legacy_palette='high-contrast')
    delta = PreferenceDelta.between(before, after)
    assert not delta.theme_changed
    assert 'theme' not in delta.effects


def test_preferences_exposes_only_system_light_dark_not_palette_selector() -> None:
    source = (SIM / 'preferences_qt.py').read_text(encoding='utf-8')
    assert "for data in ('system','light','dark')" in source
    assert 'self.theme = QComboBox()' not in source
    assert "('label.theme',self.theme)" not in source
    assert 'appearance.palette_hint_light' not in source
    assert 'def _sync_theme_control_state' not in source


def test_preferences_change_handler_does_not_persist_legacy_palette() -> None:
    source = (SIM / 'preferences_qt.py').read_text(encoding='utf-8')
    body = _function_body(source, '_controls_changed')
    assert "appearance.theme_mode" in body
    assert 'appearance.color_theme' not in body


def test_application_theme_transaction_forces_immediate_repolish_and_repaint() -> None:
    source = (SIM / 'gui.py').read_text(encoding='utf-8')
    body = _function_body(source, '_apply_application_theme')
    assert "app.setStyleSheet('')" not in body
    assert body.count('app.processEvents()') >= 1
    assert 'app.topLevelWidgets()' in body
    assert '.unpolish(window)' in body
    assert '.polish(window)' in body
    assert 'window.update()' in body


def test_windows_theme_switch_gate_covers_system_light_dark_without_hover() -> None:
    gate = SIM.parent / 'tools' / 'VERIFY_THEME_SWITCH_V101.py'
    assert gate.is_file()
    source = gate.read_text(encoding='utf-8')
    for marker in ("('light','dark','light','system')", 'theme_mode.setCurrentIndex', 'high-contrast', 'NO_MOUSE_EVENT', 'main.grab()', 'preferences.grab()'):
        assert marker in source
