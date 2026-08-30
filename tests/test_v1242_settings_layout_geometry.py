from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'


def _source(name: str) -> str:
    return (SRC / name).read_text(encoding='utf-8')


def test_settings_text_column_propagates_height_for_width_to_outer_row():
    source = _source('preferences_qt.py')
    assert 'class SettingsTextColumn(QWidget):' in source
    text_column = source.split('class SettingsTextColumn(QWidget):', 1)[1].split('\n\nclass SettingRow', 1)[0]
    assert 'def hasHeightForWidth(self)' in text_column
    assert 'def heightForWidth(self, width: int)' in text_column
    assert 'setMinimumHeight(required)' in text_column

    row = source.split('class SettingRow(QWidget):', 1)[1].split('\n\nclass PreferencesView', 1)[0]
    assert 'def hasHeightForWidth(self)' in row
    assert 'def heightForWidth(self, width: int)' in row
    assert 'self._text_column = SettingsTextColumn' in row


def test_desktop_preferences_content_uses_available_width_up_to_maximum():
    source = _source('preferences_qt.py')
    assert 'content_max_width = 760' in source
    responsive = source.split('def _apply_responsive_layout(self):', 1)[1].split('\n    def eventFilter', 1)[0]
    assert 'target_width' in responsive
    assert 'content.setMinimumWidth(target_width)' in responsive
    assert 'content.setMaximumWidth(self.content_max_width)' in responsive
    assert 'available = target_width' in responsive


def test_layout_violations_checks_text_column_height_not_only_individual_labels():
    source = _source('preferences_qt.py')
    body = source.split('def layout_violations(self)', 1)[1].split('\n\n\nclass PreferencesWindow', 1)[0]
    assert 'setting_text_column_vertical_clipping' in body
    assert 'row._text_column.heightForWidth' in body


def test_windows_real_qt_contract_includes_full_desktop_width_and_every_settings_page():
    source = (ROOT / 'tests' / 'test_qt_v1242_settings_layout_geometry.py').read_text(encoding='utf-8')
    assert '1680' in source
    assert "for page_name in view.SECTIONS" in source
    assert 'content.width() >= 740' in source
