from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

pytest.importorskip('PySide6')

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from studio_icons import icon_names, studio_icon


@pytest.fixture(autouse=True)
def _ensure_qapp():
    # QPixmap/QIcon construction requires an application instance.
    if QApplication.instance() is None:
        QApplication([])


def _icon_has_opaque_pixel(icon, size: int = 16) -> bool:
    image = icon.pixmap(size, size).toImage().convertToFormat(QImage.Format_RGBA8888)
    for y in range(0, size, 2):
        for x in range(0, size, 2):
            if image.pixelColor(x, y).alphaF() > 0.2:
                return True
    return False


def test_every_registered_icon_renders_opaque_strokes():
    for name in icon_names():
        icon = studio_icon(name, '#ABB2BF')
        assert not icon.isNull(), name
        assert _icon_has_opaque_pixel(icon), f'{name} rendered fully transparent'


def test_unknown_name_falls_back_without_raising():
    fallback = studio_icon('no-such-icon', '#FFFFFF')
    assert not fallback.isNull()
    assert _icon_has_opaque_pixel(fallback)


def test_icon_recipe_recolors_with_theme_color():
    red = studio_icon('save', '#FF0000').pixmap(16, 16).toImage()
    green = studio_icon('save', '#00FF00').pixmap(16, 16).toImage()
    red_stroke = green_stroke = False
    for y in range(16):
        for x in range(16):
            if red.pixelColor(x, y).alphaF() > 0.5 and red.pixelColor(x, y).redF() > 0.8:
                red_stroke = True
            if green.pixelColor(x, y).alphaF() > 0.5 and green.pixelColor(x, y).greenF() > 0.8:
                green_stroke = True
    assert red_stroke and green_stroke


def test_window_recolors_button_icons_with_theme(tmp_path, qtbot):
    from PySide6.QtWidgets import QApplication

    from pixel_studio_qt import PixelStudioWindow
    from preferences import PreferencesStore, default_preferences

    preferences = PreferencesStore(tmp_path / 'preferences.json', default_preferences())
    window = PixelStudioWindow(preferences=preferences, project_root=tmp_path)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(30)

    window.preferences.set('appearance.theme_mode', 'light', save=False)
    window.apply_preferences()
    light = window.undo_btn.icon().pixmap(16, 16).toImage()
    light_pixels = {
        (x, y): light.pixelColor(x, y).rgba()
        for y in range(16) for x in range(16)
        if light.pixelColor(x, y).alphaF() > 0.5
    }
    assert light_pixels, 'undo icon has no strokes in light theme'

    window.preferences.set('appearance.theme_mode', 'dark', save=False)
    window.apply_preferences()
    dark = window.undo_btn.icon().pixmap(16, 16).toImage()
    dark_pixels = {
        (x, y): dark.pixelColor(x, y).rgba()
        for y in range(16) for x in range(16)
        if dark.pixelColor(x, y).alphaF() > 0.5
    }
    assert dark_pixels, 'undo icon has no strokes in dark theme'
    assert set(light_pixels.values()) != set(dark_pixels.values()), 'icons did not recolor with theme'
