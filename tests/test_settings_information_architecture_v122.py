from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'


def test_settings_uses_seven_task_oriented_sections_and_keeps_shortcuts_reachable():
    source = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert "SECTIONS = ('general','appearance','canvas','pixel','keyboard','recovery','advanced')" in source
    assert "'group.shortcuts'" in source
    assert 'self.shortcut_edits' in source
    assert "'about'" not in source.split('SECTIONS =', 1)[1].split('\n', 1)[0]


def test_settings_has_compact_rows_helpers_transient_feedback_and_danger_zone():
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    qss = (SRC / 'qt_theme.py').read_text(encoding='utf-8')
    for marker in (
        "setObjectName('SettingRow')",
        "setObjectName('PreferencesDangerCard')",
        "setObjectName('SettingsSaveStatus')",
        "setObjectName('SettingsFieldHelp')",
        "setObjectName('SettingsFooterProduct')",
    ):
        assert marker in prefs
    assert "setObjectName('PreferencesCard')" not in prefs
    for marker in (
        'QFrame#PreferencesDangerCard', 'QFrame#SettingRowDivider',
        'QLabel#SettingsSaveStatus', 'QLabel#SettingsFieldHelp', 'QLabel#SettingsFooterProduct',
    ):
        assert marker in qss
    assert 'QFrame#PreferencesCard' not in qss
    assert "'status.saving'" in prefs and "'status.saved'" in prefs


def test_settings_adds_reduced_motion_as_real_runtime_preference():
    pref = (SRC / 'preferences.py').read_text(encoding='utf-8')
    runtime = (SRC / 'runtime_settings.py').read_text(encoding='utf-8')
    view = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert "'reduced_motion': False" in pref
    assert "'appearance.reduced_motion': _bool_validator" in pref
    assert "'appearance.reduced_motion':" in runtime
    assert 'reduced_motion: bool' in runtime
    assert "reduced_motion=bool(p['appearance']['reduced_motion'])" in runtime
    assert 'self.reduced_motion' in view
    assert 'runtime.reduced_motion' in view


def test_settings_responsive_layout_uses_content_viewport_and_explicit_rows():
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert 'def _apply_responsive_layout' in prefs
    assert 'def resizeEvent' in prefs
    assert 'content_breakpoint = 700' in prefs
    assert 'viewport().width()' in prefs
    assert 'row.set_compact(compact)' in prefs
    assert 'content_max_width = 760' in prefs
    assert 'content.setMaximumWidth(self.content_max_width)' in prefs
    assert 'setRowWrapPolicy' not in prefs
    assert 'content.setMinimumWidth(0)' in prefs


def test_settings_copy_explains_effects_not_just_field_names():
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    required = (
        'help.language', 'help.theme_mode', 'help.canvas_grid', 'help.shortcuts',
        'help.autosave', 'help.validation', 'help.asset_cache', 'help.reset_all',
    )
    for key in required:
        assert f"'{key}'" in prefs


def test_settings_dangerous_reset_requires_explicit_confirmation():
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert "'confirm.reset_all.title'" in prefs
    assert "'confirm.reset_all.body'" in prefs
    body = prefs.split('    def _reset_all(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'QMessageBox.question' in body
    assert 'QMessageBox.Yes|QMessageBox.No' in body
    assert '!=QMessageBox.Yes' in body
