from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import sys

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'README.md').is_file() and (parent / 'DELIVERY_README.md').is_file():
            return parent
    raise RuntimeError('repository root not found')


REPO = _repo_root()
SRC = REPO / 'src' if (REPO / 'src').is_dir() else REPO / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui import OLEDDesignerWindow, _apply_application_theme
from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas, PixelStudioWindow
from ui_controls import StudioSelect


def _rgb(canvas, x: int, y: int) -> tuple[int, int, int]:
    image = canvas.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    px = min(image.width() - 1, max(0, int((x + 0.5) * image.width() / canvas.width())))
    py = min(image.height() - 1, max(0, int((y + 0.5) * image.height() / canvas.height())))
    c = image.pixelColor(px, py)
    return c.red(), c.green(), c.blue()


def _drag(qtbot, widget, start: QPoint, end: QPoint):
    qtbot.mousePress(widget, Qt.LeftButton, pos=start)
    qtbot.mouseMove(widget, pos=end)
    qtbot.wait(5)


def test_line_drag_renders_live_pixels_without_committing_until_release(qtbot):
    document = PixelDocument(8, 4)
    canvas = PixelCanvas(document)
    canvas.tool = 'Line'; canvas.show_grid = False; canvas.zoom = 20; canvas._sync_size()
    qtbot.addWidget(canvas); canvas.show(); qtbot.waitExposed(canvas)

    _drag(qtbot, canvas, QPoint(10, 10), QPoint(70, 10))
    assert document.pixels[0][1] == 0
    assert _rgb(canvas, 30, 10) == (255, 255, 255)
    qtbot.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(70, 10))
    assert document.pixels[0][1] == 1


def test_rectangle_drag_renders_live_outline_without_committing_until_release(qtbot):
    document = PixelDocument(8, 4)
    canvas = PixelCanvas(document)
    canvas.tool = 'Rectangle'; canvas.show_grid = False; canvas.zoom = 20; canvas._sync_size()
    qtbot.addWidget(canvas); canvas.show(); qtbot.waitExposed(canvas)

    _drag(qtbot, canvas, QPoint(10, 10), QPoint(70, 50))
    assert document.pixels[0][1] == 0
    assert _rgb(canvas, 30, 10) == (255, 255, 255)
    assert _rgb(canvas, 30, 30) == (0, 0, 0)
    qtbot.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(70, 50))
    assert document.pixels[0][1] == 1
    assert document.pixels[1][1] == 0


def test_main_and_pixel_splitters_keep_canvas_non_collapsible(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('MONOOLED_CONFIG_DIR', str(tmp_path / 'cfg'))
    window = OLEDDesignerWindow('main_scene', 'en_US')
    pixel = PixelStudioWindow(language='en_US', project_root=tmp_path)
    qtbot.addWidget(window); qtbot.addWidget(pixel)
    window.show(); pixel.show(); qtbot.wait(10)
    assert window.workspace_splitter.childrenCollapsible() is False
    assert window.canvas_card.minimumWidth() >= 300
    assert pixel.workspace_splitter.childrenCollapsible() is False
    assert pixel.canvas_frame.minimumWidth() >= 300


def test_settings_button_toggles_back_and_design_review_activate_scene_editor(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('MONOOLED_CONFIG_DIR', str(tmp_path / 'cfg'))
    window = OLEDDesignerWindow('main_scene', 'en_US')
    qtbot.addWidget(window); window.show(); qtbot.wait(10)
    assert window.editor_tabs.currentIndex() == 0

    qtbot.mouseClick(window.header_settings, Qt.LeftButton)
    qtbot.wait(10)
    settings_index = window.editor_tabs.currentIndex()
    assert settings_index > 0 and window.header_settings.isChecked()

    qtbot.mouseClick(window.header_settings, Qt.LeftButton)
    qtbot.wait(10)
    assert window.editor_tabs.currentIndex() == 0
    assert not window.header_settings.isChecked()

    window.open_preferences(); qtbot.wait(10)
    qtbot.mouseClick(window.header_review, Qt.LeftButton); qtbot.wait(10)
    assert window.editor_tabs.currentIndex() == 0
    assert window.workspace_mode.value == 'review'

    window.open_preferences(); qtbot.wait(10)
    qtbot.mouseClick(window.header_design, Qt.LeftButton); qtbot.wait(10)
    assert window.editor_tabs.currentIndex() == 0
    assert window.workspace_mode.value == 'design'


def test_theme_transaction_never_installs_empty_qss_and_select_uses_polished_hint(qtbot, monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    calls = []
    original = app.setStyleSheet

    def record(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(app, 'setStyleSheet', record)
    app.setProperty('monooledAdaptiveStyleSignature', 'force-different')
    _apply_application_theme(app, 'one-dark-pro', 'comfortable', 1.0)
    assert calls and all(value != '' for value in calls)

    select = StudioSelect(); select.addItem('Off', 0); select.addItem('8 px', 8)
    qtbot.addWidget(select); select.show(); select.ensurePolished(); select.button.ensurePolished(); qtbot.wait(5)
    assert select.minimumSizeHint().height() >= select.button.minimumSizeHint().height()
    assert select.sizeHint().height() >= select.button.sizeHint().height()
