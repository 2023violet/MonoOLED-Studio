from __future__ import annotations

from pathlib import Path
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from qt_theme import build_stylesheet, build_theme_palette
from ui_controls import StudioButton, StudioToolButton, accent_rail_spec


def _distance(a, b):
    return max(abs(a.red()-b.red()), abs(a.green()-b.green()), abs(a.blue()-b.blue()))


def _pixel(widget, x, y):
    image = widget.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    px = min(image.width() - 1, max(0, int((float(x) + 0.5) * image.width() / widget.width())))
    py = min(image.height() - 1, max(0, int((float(y) + 0.5) * image.height() / widget.height())))
    return image.pixelColor(px, py)


def _prepare(app, theme='monooled-dark'):
    app.setPalette(build_theme_palette(theme))
    app.setStyleSheet(build_stylesheet(theme))


def test_secondary_accent_rail_is_real_raster_and_never_moves_geometry(qtbot):
    app = QApplication.instance(); _prepare(app)
    button = StudioButton('Validate'); button.setObjectName('SecondaryButton'); button.setCheckable(True); button.resize(120, 32)
    qtbot.addWidget(button); button.show(); qtbot.waitExposed(button)
    before = (button.pos(), button.size(), button.contentsRect())
    button.setChecked(True); app.processEvents()
    accent = button.palette().highlight().color()
    sample = _pixel(button, 4, button.height() // 2)
    assert _distance(sample, accent) <= 32
    assert (button.pos(), button.size(), button.contentsRect()) == before


def test_tool_and_segment_style_bottom_rail_persists_when_checked(qtbot):
    app = QApplication.instance(); _prepare(app)
    host = QWidget(); row = QHBoxLayout(host)
    tool = StudioToolButton(); tool.setObjectName('ToolRailButton'); tool.setText('P'); tool.setCheckable(True); tool.setFixedSize(32, 32)
    segment = StudioButton('Design'); segment.setObjectName('StudioSegment'); segment.setCheckable(True); segment.setFixedSize(90, 32)
    row.addWidget(tool); row.addWidget(segment); qtbot.addWidget(host); host.show(); qtbot.waitExposed(host)
    for widget in (tool, segment):
        widget.setChecked(True); app.processEvents()
        accent = widget.palette().highlight().color()
        rail = accent_rail_spec(widget.objectName(), widget.width(), widget.height(), checked=True)
        sample = _pixel(widget, rail.x + rail.width // 2, rail.y)
        assert _distance(sample, accent) <= 32
        QTest.mouseMove(host, QPoint(0, 0)); app.processEvents()
        assert widget._accent_rail_opacity >= 0.99


def test_hover_is_soft_pressed_is_full_and_primary_danger_are_excluded(qtbot):
    app = QApplication.instance(); _prepare(app)
    host = QWidget(); row = QHBoxLayout(host)
    secondary = StudioButton('Validate'); secondary.setObjectName('SecondaryButton')
    primary = StudioButton('Save'); primary.setObjectName('PrimaryButton')
    danger = StudioButton('Delete'); danger.setObjectName('DangerButton')
    for widget in (secondary, primary, danger): row.addWidget(widget)
    qtbot.addWidget(host); host.show(); qtbot.waitExposed(host)
    baseline = secondary.size()
    QTest.mouseMove(secondary, secondary.rect().center()); qtbot.wait(130)
    assert 0.62 <= secondary._accent_rail_opacity <= 0.72
    assert secondary.size() == baseline
    QTest.mousePress(secondary, Qt.LeftButton, pos=secondary.rect().center()); app.processEvents()
    assert secondary._accent_rail_opacity >= 0.99
    assert secondary.size() == baseline
    QTest.mouseRelease(secondary, Qt.LeftButton, pos=secondary.rect().center())
    for excluded in (primary, danger):
        QTest.mouseMove(excluded, excluded.rect().center()); qtbot.wait(130)
        assert excluded._accent_rail_opacity == 0.0
