from __future__ import annotations

import pytest

pytest.importorskip('PySide6')

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from gui import _apply_application_theme


def _luma(color) -> float:
    return (0.2126 * color.redF()) + (0.7152 * color.greenF()) + (0.0722 * color.blueF())


def test_light_dark_switch_repaints_without_mouse_or_external_event_flush(qtbot) -> None:
    app = QApplication.instance()
    root = QWidget()
    layout = QVBoxLayout(root)
    layout.addWidget(QLabel('Theme transaction'))
    layout.addWidget(QLineEdit('value'))
    layout.addWidget(QPushButton('Action'))
    qtbot.addWidget(root)
    root.resize(420, 220)
    root.show()

    _apply_application_theme(app, 'monooled-light', 'comfortable', 1.0)
    light_window = root.palette().color(QPalette.Window)

    # No mouse move and no QApplication.processEvents() here. The production
    # transaction itself must make every existing widget adopt the new theme.
    _apply_application_theme(app, 'monooled-dark', 'comfortable', 1.0)
    dark_window = root.palette().color(QPalette.Window)

    assert _luma(light_window) > 0.75
    assert _luma(dark_window) < 0.20
    assert app.property('monooledAdaptiveStyleSignature') == 'monooled-dark:comfortable:1.0'
