from __future__ import annotations

import pytest

pytest.importorskip('PySide6')

from PySide6.QtGui import QImage, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from gui import OLEDDesignerWindow, _apply_application_theme


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


def test_dark_switch_changes_rendered_root_pixels_without_followup_input(qtbot) -> None:
    app = QApplication.instance()
    root = QWidget()
    root.setObjectName('AppRoot')
    root.resize(160, 100)
    qtbot.addWidget(root)
    root.show()
    qtbot.waitExposed(root)

    _apply_application_theme(app, 'monooled-light', 'comfortable', 1.0)
    light = root.grab().toImage().convertToFormat(QImage.Format_RGBA8888).pixelColor(80, 50)
    _apply_application_theme(app, 'monooled-dark', 'comfortable', 1.0)
    dark = root.grab().toImage().convertToFormat(QImage.Format_RGBA8888).pixelColor(80, 50)

    assert _luma(light) > 0.75
    assert _luma(dark) < 0.20


def _child_surface_lumas(root: QWidget) -> dict[str, float]:
    samples: dict[str, float] = {}
    for name, widget_type in (
        ('button', QPushButton),
        ('lineedit', QLineEdit),
        ('panel', QFrame),
    ):
        widget = root.findChild(widget_type)
        assert widget is not None, name
        image = widget.grab().toImage()
        samples[name] = _luma(image.pixelColor(2, max(0, image.height() // 2)))
    return samples


def test_theme_switch_repaints_child_widgets_not_only_the_top_level(qtbot) -> None:
    """A theme-only switch must repaint already-polished child widgets.

    With an application stylesheet active, swapping the QPalette alone does not
    make existing child widgets re-resolve ``palette()`` QSS rules (Qt 6.11);
    only the top-level background followed the palette.  This test pins the
    user-visible contract: every surface follows the theme in both directions.
    """
    app = QApplication.instance()
    root = QWidget()
    root.setObjectName('AppRoot')
    layout = QVBoxLayout(root)
    layout.addWidget(QPushButton('Action'))
    layout.addWidget(QLineEdit('value'))
    panel = QFrame()
    panel.setObjectName('ProfessionalPanel')
    panel.resize(200, 40)
    layout.addWidget(panel)
    qtbot.addWidget(root)
    root.resize(420, 280)
    root.show()
    qtbot.waitExposed(root)

    _apply_application_theme(app, 'one-dark-pro', 'comfortable', 1.0)
    dark = _child_surface_lumas(root)
    _apply_application_theme(app, 'monooled-light', 'comfortable', 1.0)
    light = _child_surface_lumas(root)
    _apply_application_theme(app, 'one-dark-pro', 'comfortable', 1.0)
    back_to_dark = _child_surface_lumas(root)

    for name in ('button', 'lineedit', 'panel'):
        assert dark[name] < 0.35, f'{name} did not render dark: {dark[name]:.3f}'
        assert light[name] > 0.6, f'{name} did not follow the light theme: {light[name]:.3f}'
        assert back_to_dark[name] < 0.35, f'{name} did not switch back to dark: {back_to_dark[name]:.3f}'


def _window_dark_fraction(window) -> float:
    image = window.grab().toImage()
    stride = 6
    dark = total = 0
    for y in range(0, image.height(), stride):
        for x in range(0, image.width(), stride):
            total += 1
            if _luma(image.pixelColor(x, y)) < 0.35:
                dark += 1
    return dark / max(1, total)


def test_designer_window_theme_switch_repaints_real_window(qtbot, tmp_path, monkeypatch) -> None:
    """Switching appearance mode on the real Designer window must repaint it."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    app = QApplication.instance()
    w = OLEDDesignerWindow('main_scene')
    qtbot.addWidget(w)
    w.resize(1440, 900)
    w.show()
    qtbot.wait(150)

    w.preferences.set('appearance.theme_mode', 'dark', save=False)
    w.apply_preferences()
    dark_fraction = _window_dark_fraction(w)
    w.preferences.set('appearance.theme_mode', 'light', save=False)
    w.apply_preferences()
    light_fraction = _window_dark_fraction(w)
    w.preferences.set('appearance.theme_mode', 'dark', save=False)
    w.apply_preferences()
    back_fraction = _window_dark_fraction(w)

    assert dark_fraction > 0.5, f'dark theme not painted: dark_frac={dark_fraction:.3f}'
    assert light_fraction < 0.2, f'light theme not painted: dark_frac={light_fraction:.3f}'
    assert back_fraction > 0.5, f'dark theme not restored: dark_frac={back_fraction:.3f}'
