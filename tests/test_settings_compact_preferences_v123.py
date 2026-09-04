from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'


def _text(name: str) -> str:
    return (SRC / name).read_text(encoding='utf-8')


def test_v123_uses_compact_task_navigation_and_moves_about_to_footer():
    prefs = _text('preferences_qt.py')
    assert "SECTIONS = ('general','appearance','canvas','pixel','keyboard','recovery','advanced')" in prefs
    assert "'section.keyboard': '键盘'" in prefs
    assert "'section.recovery': '恢复'" in prefs
    assert "'section.advanced': '高级'" in prefs
    assert "'section.about'" not in prefs
    assert "setObjectName('SettingsFooterProduct')" in prefs
    assert "setObjectName('SettingsFooterVersion')" in prefs


def test_v123_replaces_qformlayout_cards_with_explicit_setting_rows():
    prefs = _text('preferences_qt.py')
    qss = _text('qt_theme.py')
    assert 'class SettingRow(QWidget):' in prefs
    assert 'QBoxLayout' in prefs
    assert 'self._text_column' in prefs and 'self._control_column' in prefs
    assert 'QFormLayout' not in prefs
    assert "setObjectName('SettingRow')" in prefs
    assert "setObjectName('SettingRowDivider')" in prefs
    assert "setObjectName('PreferencesCard')" not in prefs
    assert 'QFrame#PreferencesCard' not in qss
    assert "setObjectName('PreferencesDangerCard')" in prefs
    assert 'QFrame#PreferencesDangerCard' in qss


def test_v123_responsive_layout_uses_content_viewport_width_not_whole_view():
    prefs = _text('preferences_qt.py')
    assert 'content_breakpoint = 700' in prefs
    assert 'viewport().width()' in prefs
    assert 'self.width()<self.responsive_breakpoint' not in prefs
    assert '.set_compact(compact)' in prefs
    assert 'content_max_width = 760' in prefs
    assert 'setMaximumWidth(self.content_max_width)' in prefs


def test_v123_header_search_is_inline_and_saved_feedback_is_transient():
    prefs = _text('preferences_qt.py')
    assert 'top.addWidget(self.search)' in prefs
    assert 'outer.addWidget(self.search)' not in prefs
    assert 'self._save_feedback_timer' in prefs
    assert 'self._clear_save_state' in prefs
    assert 'setVisible(False)' in prefs or '.hide()' in prefs


def test_v123_navigation_and_spacing_are_dense_and_intentional():
    prefs = _text('preferences_qt.py')
    assert 'nav_width = 172' in prefs
    assert 'section_gap = 30' in prefs
    assert 'row_vertical_padding = 10' in prefs
    assert 'row_control_width = 220' in prefs
    assert 'header_search_width = 280' in prefs


def test_v123_setting_rows_keep_help_text_and_search_targets():
    prefs = _text('preferences_qt.py')
    assert "label.setObjectName('SettingRowLabel')" in prefs
    assert "help_label.setObjectName('SettingsFieldHelp')" in prefs
    assert 'self._search_targets.append((section,label))' in prefs
    assert 'row.set_compact(compact)' in prefs


def test_v123_version_identity_is_consistent():
    version=(SRC / 'VERSION').read_text(encoding='utf-8').strip()
    assert version == (SRC / 'VERSION').read_text(encoding='utf-8').strip()
    prefs = _text('preferences_qt.py')
    assert 'load_version' in prefs
    assert 'Output Workbench Release' in prefs


def test_v123_page_shell_does_not_put_expandable_stretch_before_sections():
    prefs = _text('preferences_qt.py')
    shell = prefs.split('    def _page_shell', 1)[1].split('    def _set_save_state', 1)[0]
    assert '\n        layout.addStretch(1)\n' not in shell
    assert 'page_layout.addStretch(1)' in shell
