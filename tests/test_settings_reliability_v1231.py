from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
TOOLS = ROOT / 'tools'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_setting_row_only_rebuilds_when_responsive_mode_changes():
    src = _read(SRC / 'preferences_qt.py')
    body = src.split('    def set_compact(self, compact: bool):', 1)[1].split('\n\n\nclass PreferencesView', 1)[0]
    assert 'if self._layout_mode is compact:' in body
    assert 'return False' in body
    assert 'self._layout_mode = compact' in body


def test_responsive_breakpoint_uses_effective_content_width_and_forbids_horizontal_scroll():
    src = _read(SRC / 'preferences_qt.py')
    assert 'def _effective_content_width(self, scroll: QScrollArea) -> int:' in src
    assert 'page.layout().contentsMargins()' in src
    responsive = src.split('    def _apply_responsive_layout(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'self._effective_content_width(scroll)' in responsive
    assert 'scroll.viewport().width()' not in responsive
    assert 'setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)' in src


def test_scroll_viewports_drive_responsive_reflow_after_scrollbar_or_page_changes():
    src = _read(SRC / 'preferences_qt.py')
    assert 'scroll.viewport().installEventFilter(self)' in src
    assert 'def eventFilter(self, watched, event):' in src
    body = src.split('    def eventFilter(self, watched, event):', 1)[1].split('\n    def ', 1)[0]
    assert 'QEvent.Resize' in body
    assert 'QEvent.LayoutRequest' in body
    assert '_schedule_responsive_layout()' in body


def test_language_changes_always_schedule_geometry_settle():
    src = _read(SRC / 'preferences_qt.py')
    assert 'def _settle_after_text_change(self):' in src
    set_language = src.split('    def set_language(self, language: str):', 1)[1].split('\n    def ', 1)[0]
    assert '_settle_after_text_change()' in set_language
    controls = src.split('    def _controls_changed(self, *_):', 1)[1].split('\n    def ', 1)[0]
    assert '_settle_after_text_change()' in controls


def test_layout_violations_checks_current_page_overflow_row_order_sections_header_and_mode():
    src = _read(SRC / 'preferences_qt.py')
    body = src.split('    def layout_violations(self) -> list[str]:', 1)[1].split('\n\n\nclass PreferencesWindow', 1)[0]
    for marker in (
        'content_horizontal_overflow',
        'setting_row_horizontal_overflow',
        'setting_row_overlap',
        'setting_section_overlap',
        'header_overlap',
        'responsive_mode_mismatch',
    ):
        assert marker in body
    assert 'current_rows = self._rows_by_scroll.get(current, [])' in body


def test_qt_overlap_test_handles_label_less_boolean_rows_and_checks_all_pages():
    qt = _read(ROOT / 'tests' / 'test_qt_settings_compact_v123.py')
    # V12.4.1 rows isolate optional copy from controls into sibling columns, so
    # geometry tests must not dereference an optional row.label at all.
    assert 'row._text_column.mapTo(row' in qt
    assert 'row._control_column.mapTo(row' in qt
    assert 'row.label.geometry()' not in qt
    assert 'for page_index in range(view.nav.count()):' in qt
    assert 'view.layout_violations() == []' in qt


def test_settings_reliability_qt_matrix_and_soak_exist():
    qt = ROOT / 'tests' / 'test_qt_settings_reliability_v1231.py'
    assert qt.exists()
    text = _read(qt)
    for marker in ('700', '760', '900', '980', '1180', '1440', "'zh_CN'", "'en_US'", "'90%'", "'125%'", "'150%'", '500'):
        assert marker in text
    assert 'layout_violations()' in text


def test_executable_exposes_settings_smoke_and_settings_soak():
    gui = _read(SRC / 'gui.py')
    for marker in ('def run_settings_smoke(', 'def run_settings_soak(', "'--settings-smoke'", "'--settings-soak'"):
        assert marker in gui


def test_windows_ga_runs_settings_visual_reliability_and_executable_settings_gates():
    ga = _read(TOOLS / 'BUILD_WINDOWS_GA.bat')
    assert 'VERIFY_SETTINGS_V1231.py' in ga
    assert 'CAPTURE_V1231_SETTINGS_GOLDENS.py' in ga
    assert '--settings-smoke' in ga
    assert '--settings-soak' in ga


def test_v1231_version_identity():
    version=(SRC / 'VERSION').read_text(encoding='utf-8').strip(); assert version.count('.')==2
    src = _read(SRC / 'preferences_qt.py')
    assert 'load_version' in src
    assert 'Initial Release' in src


def test_boolean_settings_use_the_same_left_label_right_control_baseline_as_other_rows():
    src = _read(SRC / 'preferences_qt.py')
    check = src.split('    def _check(self, key: str) -> QCheckBox:', 1)[1].split('\n    def ', 1)[0]
    assert "setProperty('settingsTextKey', key)" in check
    assert '_bind_text(QCheckBox()' not in check
    row = src.split('    def _setting_row(', 1)[1].split('\n    def ', 1)[0]
    assert "widget.property('settingsTextKey')" in row


def test_borderless_settings_section_qss_matches_the_actual_qwidget_type():
    qss = _read(SRC / 'qt_theme.py')
    assert 'QWidget#PreferencesSection' in qss
    assert 'QFrame#PreferencesSection {' not in qss


def test_scroll_page_layout_uses_dynamic_size_constraint_for_text_reflow_and_vertical_scroll():
    src = _read(SRC / 'preferences_qt.py')
    assert 'QLayout' in src.split('from PySide6.QtWidgets import', 1)[1].split(')', 1)[0]
    shell = src.split('    def _page_shell(self, section: str):', 1)[1].split('\n    def ', 1)[0]
    assert 'page_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)' in shell


def test_stabilize_layout_activates_active_scroll_page_and_content_layouts():
    src = _read(SRC / 'preferences_qt.py')
    body = src.split('    def stabilize_layout(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'page=current.widget()' in body
    assert 'page.layout().invalidate(); page.layout().activate()' in body
    assert 'content=self._content_by_scroll.get(current)' in body
    assert 'content.layout().invalidate(); content.layout().activate()' in body


def test_package_verifier_requires_current_settings_reliability_doc_and_gates():
    verifier = _read(ROOT / 'VERIFY_PACKAGE.py')
    assert "'ENGINEERING_HISTORY.md'" in verifier
    assert "'VERIFY_SETTINGS_V1231.py'" in verifier
    assert "'CAPTURE_V1231_SETTINGS_GOLDENS.py'" in verifier
