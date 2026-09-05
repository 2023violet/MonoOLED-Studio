from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from pixel_studio_qt import PixelStudioWindow
from preferences import PreferencesStore, default_preferences


def _window(tmp_path, qtbot):
    preferences = PreferencesStore(tmp_path / 'preferences.json', default_preferences())
    window = PixelStudioWindow(preferences=preferences, project_root=tmp_path)
    qtbot.addWidget(window)
    window.show()
    return window


def test_arrow_keys_move_cursor_and_enter_delete_paint(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    canvas = window.canvas
    canvas.setFocus()
    qtbot.wait(20)

    QTest.keyClick(canvas, Qt.Key_Right)   # establishes the cursor at (0, 0)
    assert canvas._key_cursor == (0, 0)
    QTest.keyClick(canvas, Qt.Key_Right)
    QTest.keyClick(canvas, Qt.Key_Down)
    assert canvas._key_cursor == (1, 1)

    QTest.keyClick(canvas, Qt.Key_Return)
    assert window.document.get(1, 1) == 1
    qtbot.wait(30)

    QTest.keyClick(canvas, Qt.Key_Delete)
    assert window.document.get(1, 1) == 0

    # one undo entry per key paint: undo removes the delete, second undo the draw
    assert window.document.undo() and window.document.get(1, 1) == 1
    assert window.document.undo() and window.document.get(1, 1) == 0

    QTest.keyClick(canvas, Qt.Key_Escape)
    assert canvas._key_cursor is None


def test_keyboard_paint_updates_preview_and_output_workbench(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    canvas = window.canvas
    canvas.setFocus()
    qtbot.wait(20)

    QTest.keyClick(canvas, Qt.Key_Right)   # cursor defaults to (0, 0)
    QTest.keyClick(canvas, Qt.Key_Return)
    assert window.document.get(0, 0) == 1
    qtbot.waitUntil(lambda: window.output_workbench.output_text.toPlainText() != '', timeout=3000)


def test_zoom_controls_stay_in_sync_across_every_entry_point(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    qtbot.wait(30)

    window.set_zoom(12)
    assert window.canvas.zoom == 12
    assert window.zoom_combo.currentText() == '12×'
    assert window.output_workbench.pixel_size.value() == 12

    window.output_workbench.pixel_size.setValue(8)
    assert window.canvas.zoom == 8
    assert window.zoom_combo.currentText() == '8×'

    window.zoom_combo.setCurrentIndex(window.zoom_combo.findData(24))
    assert window.canvas.zoom == 24
    assert window.output_workbench.pixel_size.value() == 24


def test_fit_mode_survives_its_own_zoom_recalculation(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    qtbot.wait(30)

    window.zoom_combo.setCurrentIndex(window.zoom_combo.findData('fit'))
    assert window._zoom_mode == 'fit'
    assert window.zoom_combo.currentText() == 'Fit'

    window._apply_fit_zoom()  # viewport-driven recalculation
    assert window._zoom_mode == 'fit'
    assert window.zoom_combo.currentText() == 'Fit'
