from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from pixel_studio_qt import PixelStudioWindow
from preferences import PreferencesStore, default_preferences


def _window(tmp_path, qtbot):
    preferences = PreferencesStore(tmp_path / 'preferences.json', default_preferences())
    window = PixelStudioWindow(preferences=preferences, project_root=tmp_path)
    qtbot.addWidget(window)
    window.show()
    return window


def test_pixel_studio_exposes_daily_output_actions_and_grouped_controls(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)

    assert window.findChild(QPushButton, 'GenerateBitmapButton').text() == '生成字模'
    assert window.findChild(QPushButton, 'CopyArrayButton').text() == '复制数组'
    assert window.findChild(QPushButton, 'SaveBitmapButton').text() == '保存字模'
    assert window.findChild(QPushButton, 'ClearOutputButton').text() == '清除输出'
    assert window.output_workbench.group_titles() == ('来源', '字模与图片', '点阵', '格式', '显示')
    assert window.output_workbench.temporary is True


def test_generate_and_clear_output_never_clear_canvas(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    window.document.pencil(1, 1, 1)

    window.output_workbench.generate_now()
    qtbot.waitUntil(lambda: bool(window.output_workbench.output_text.toPlainText()), timeout=3000)
    generated = window.output_workbench.output_text.toPlainText()
    assert '0x' in generated

    qtbot.mouseClick(window.findChild(QPushButton, 'ClearOutputButton'), Qt.LeftButton)
    assert window.output_workbench.output_text.toPlainText() == ''
    assert window.document.get(1, 1) == 1


def test_selection_source_is_disabled_without_selection(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)

    window.output_workbench.source_combo.setCurrentIndex(
        window.output_workbench.source_combo.findData('selection')
    )

    assert window.output_workbench.generate_button.isEnabled() is False
    assert '选区' in window.output_workbench.validation_label.text()


def test_invalid_display_color_is_reported_and_not_applied(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    before = window.canvas.pixel_border_color

    window.output_workbench.border_color.setText('#FFFFO0')

    assert '颜色格式无效' in window.output_workbench.validation_label.text()
    assert window.canvas.pixel_border_color == before
