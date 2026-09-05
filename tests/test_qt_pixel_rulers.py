from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtWidgets import QApplication

from pixel_studio_qt import PixelRulerStrip, PixelStudioWindow
from preferences import PreferencesStore, default_preferences
from preferences_qt import _TEXT


def _window(tmp_path, qtbot, *, rulers=True):
    prefs_data = default_preferences()
    prefs_data['pixel_studio']['rulers'] = rulers
    preferences = PreferencesStore(tmp_path / 'preferences.json', prefs_data)
    window = PixelStudioWindow(preferences=preferences, project_root=tmp_path)
    qtbot.addWidget(window)
    window.show()
    return window


def test_ruler_strip_tick_math_is_isolated(qtbot):
    strip = PixelRulerStrip('horizontal')
    qtbot.addWidget(strip)
    strip.sync(document_size=64, zoom=8, scroll_offset=0, viewport_size=200, theme_name='monooled-dark')
    assert strip._tick_step() == 8      # 8 * 8 = 64 >= 40
    assert strip._first_tick() == 0

    strip.sync(document_size=64, zoom=8, scroll_offset=64, viewport_size=200, theme_name='monooled-dark')
    assert strip._first_tick() == 8     # floor(64/8/8)*8

    strip.sync(document_size=64, zoom=2, scroll_offset=0, viewport_size=200, theme_name='monooled-dark')
    assert strip._tick_step() == 32     # 8*2=16 < 40, 16*2=32*... 32*2=64 >= 40

    strip.sync(document_size=64, zoom=8, scroll_offset=0, viewport_size=200, theme_name='monooled-light')
    assert strip.theme_name == 'monooled-light'


def test_rulers_visible_by_default_and_follow_zoom(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    assert window.ruler_hr.isVisible() and window.ruler_vr.isVisible()
    assert window.ruler_hr.zoom == window.canvas.zoom

    window.set_zoom(24)
    assert window.ruler_hr.zoom == 24
    assert window.ruler_hr._tick_step() == 8


def test_rulers_track_scrollbar_offsets(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    window.resize(820, 560)
    window.set_zoom(40)
    QApplication.processEvents()

    hsb = window.canvas_scroll.horizontalScrollBar()
    vsb = window.canvas_scroll.verticalScrollBar()
    hsb.setValue(min(160, hsb.maximum()))
    vsb.setValue(min(160, vsb.maximum()))
    QApplication.processEvents()

    assert window.ruler_hr.scroll_offset == hsb.value()
    assert window.ruler_vr.scroll_offset == vsb.value()
    assert window.ruler_hr._first_tick() == (hsb.value() // 40 // window.ruler_hr._tick_step()) * window.ruler_hr._tick_step()


def test_rulers_toggle_through_preferences(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    window.preferences.set('pixel_studio.rulers', False, save=False)
    window.apply_preferences()
    assert not window.ruler_hr.isVisible()
    assert not window.ruler_vr.isVisible()

    window.preferences.set('pixel_studio.rulers', True, save=False)
    window.apply_preferences()
    assert window.ruler_hr.isVisible()
    assert window.ruler_vr.isVisible()


def test_rulers_off_layout_violations_stay_empty(tmp_path, qtbot):
    window = _window(tmp_path, qtbot, rulers=False)
    qtbot.wait(30)
    assert window.layout_violations() == []


def test_pixel_rulers_label_exists_in_both_catalogs():
    assert _TEXT['zh_CN']['check.pixel_rulers'] == '画布标尺'
    assert _TEXT['en_US']['check.pixel_rulers'] == 'Canvas rulers'
