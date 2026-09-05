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
    assert window.output_workbench.group_titles() == ('来源', '图片栅格化', '点阵', '格式', '显示')
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


def test_trace_animation_ui_and_canvas_overlay_are_removed(tmp_path, qtbot):
    """The extraction demo area is gone: no play controls, no canvas blue cells."""
    window = _window(tmp_path, qtbot)

    for name in ('PlayButton', 'PreviousStepButton', 'NextStepButton'):
        assert window.findChild(QPushButton, name) is None
    assert not hasattr(window.output_workbench, 'animation_label')
    assert not hasattr(window.output_workbench, '_animation_timer')
    assert not hasattr(window.canvas, 'trace_points')

    window.output_workbench.generate_now()
    qtbot.waitUntil(lambda: bool(window.output_workbench.output_text.toPlainText()), timeout=3000)
    assert not hasattr(window.canvas, 'trace_points')


def test_color_swatch_previews_and_edits_display_colors(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)

    swatch = window.output_workbench.border_color
    assert '#FFFF00' in swatch.swatch.toolTip().upper()

    swatch.setText('#FF8800')
    assert window.canvas.pixel_border_color == '#FF8800'
    assert '#FF8800' in swatch.swatch.toolTip().upper()
    assert 'background: #ff8800' in swatch.swatch.styleSheet()

    swatch.setText('not-a-color')
    assert swatch.edit.property('validationState') == 'error'
    assert window.canvas.pixel_border_color == '#FF8800'


def test_dead_alignment_and_antialias_controls_are_removed(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    workbench = window.output_workbench
    # these two were permanently disabled decorations: alignment is a font
    # metric and antialias belongs to TTF rasterization, never consumed here
    assert not hasattr(workbench, 'alignment_combo')
    assert not hasattr(workbench, 'antialias')


def test_image_source_rasterizes_color_image_by_threshold(tmp_path, qtbot):
    from PIL import Image as PILImage

    image_path = tmp_path / 'probe.png'
    image = PILImage.new('RGB', (8, 4))
    for x in range(8):
        for y in range(4):
            image.putpixel((x, y), (0, 0, 0) if x < 4 else (255, 255, 255))
    image.save(image_path)

    window = _window(tmp_path, qtbot)
    workbench = window.output_workbench
    workbench.source_combo.setCurrentIndex(workbench.source_combo.findData('image'))
    workbench.image_path.setText(str(image_path))

    specs = workbench._source_bitmaps()
    rows = specs[0]['bitmap'].rows
    assert specs[0]['name'] == 'probe'
    assert all(value == 0 for row in rows for value in row[:4])
    assert all(value == 1 for row in rows for value in row[4:])

    workbench.generate_now()
    qtbot.waitUntil(lambda: workbench.output_text.toPlainText() != '', timeout=3000)
    assert 'probe' in workbench.output_text.toPlainText()


def test_image_source_threshold_mode_gates_rgb_channels(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    workbench = window.output_workbench
    workbench.source_combo.setCurrentIndex(workbench.source_combo.findData('image'))

    workbench.threshold_mode.setCurrentIndex(workbench.threshold_mode.findData('luma'))
    assert workbench.threshold.isEnabled() and not workbench.red.isEnabled()

    workbench.threshold_mode.setCurrentIndex(workbench.threshold_mode.findData('rgb_all'))
    assert not workbench.threshold.isEnabled() and workbench.red.isEnabled()


def test_image_source_other_sources_keep_raster_disabled(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    workbench = window.output_workbench
    workbench.source_combo.setCurrentIndex(workbench.source_combo.findData('canvas'))
    assert not workbench.threshold_mode.isEnabled()
    assert '不会再次阈值化' in workbench.raster_hint.text()


def test_image_source_missing_file_reports_validation(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    workbench = window.output_workbench
    workbench.source_combo.setCurrentIndex(workbench.source_combo.findData('image'))
    assert not workbench.generate_button.isEnabled()
    assert '请先选择图片文件' in workbench.validation_label.text()

    workbench.image_path.setText(str(tmp_path / 'missing.png'))
    assert '图片文件不存在' in workbench.validation_label.text()
