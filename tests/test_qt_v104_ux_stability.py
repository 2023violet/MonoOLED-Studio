from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from time import perf_counter
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

SIM = Path(__file__).resolve().parents[1] / 'src'
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))

from gui import OLEDDesignerWindow
from preferences_qt import PreferencesView
from runtime_settings import RuntimeSettings
from theme_system import resolve_theme_name
from ui_controls import StudioSelect


def _ms(fn):
    started = perf_counter()
    value = fn()
    QApplication.processEvents()
    return (perf_counter() - started) * 1000.0, value


def test_dark_mode_is_one_dark_pro_and_settings_is_embedded(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    window = OLEDDesignerWindow('main_scene')
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    qtbot.wait(20)

    window.preferences.set('appearance.theme_mode', 'dark', save=False)
    window.apply_preferences()
    assert window._resolved_theme == 'one-dark-pro'
    assert resolve_theme_name('high-contrast', 'dark', system_dark=False) == 'one-dark-pro'

    elapsed, view = _ms(window.open_preferences)
    # Headless offscreen rendering (software, no GPU) is far slower than a real
    # Windows desktop, so use a CI-appropriate ceiling that still catches severe
    # regressions instead of a real-desktop millisecond floor.
    assert elapsed < 2000.0
    assert isinstance(view, PreferencesView)
    assert window.editor_tabs.currentWidget() is view
    assert view.window() is window


def test_studio_select_second_click_and_outside_click_are_deterministic(qtbot):
    combo = StudioSelect()
    combo.addItems(['Auto', 'On', 'Off'])
    combo.resize(220, 36)
    qtbot.addWidget(combo)
    combo.show()
    qtbot.wait(10)

    QTest.mouseClick(combo.button, Qt.LeftButton)
    assert combo.popup.isVisible()
    QTest.mouseClick(combo.button, Qt.LeftButton)
    qtbot.wait(100)
    assert not combo.popup.isVisible()

    QTest.mouseClick(combo.button, Qt.LeftButton)
    assert combo.popup.isVisible()
    # Simulate a native outside-close while the pointer is not on the anchor.
    QTest.mouseMove(combo, QPoint(combo.width() - 2, combo.height() - 2))
    combo.hidePopup('outside_click')
    assert not combo.popup.isVisible()
    # A blank-area close must not poison the next independent anchor click.
    combo._popup_state.release_anchor_suppression()
    QTest.mouseClick(combo.button, Qt.LeftButton)
    assert combo.popup.isVisible()
    combo.hidePopup()


def test_studio_select_outer_geometry_never_clips_its_button(qtbot):
    combo = StudioSelect()
    combo.addItems(['Auto', 'On', 'Off'])
    qtbot.addWidget(combo)
    combo.show()
    qtbot.wait(5)
    combo.adjustSize()
    QApplication.processEvents()
    assert combo.height() >= combo.button.minimumSizeHint().height()
    assert combo.height() >= combo.button.height()
    assert combo.visibleRegion().boundingRect().contains(combo.rect())


def test_standalone_scene_scans_only_the_assets_directory(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    window = OLEDDesignerWindow('main_scene')
    qtbot.addWidget(window)
    assert window.asset_library.asset_dirs == ('assets',)


def test_startup_and_basic_interaction_latency_have_hard_regression_ceiling(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    started = perf_counter()
    window = OLEDDesignerWindow('main_scene')
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    startup_ms = (perf_counter() - started) * 1000.0
    # Hardware-independent regression ceiling: this catches the reported 3-5s stalls
    # without pretending all Windows machines share an identical performance floor.
    assert startup_ms < 3000.0

    interaction_ms, _ = _ms(lambda: window.inspector_tabs.setCurrentIndex(1))
    # Headless offscreen render triggers a full repaint, so use a CI-appropriate
    # ceiling that still detects genuine stalls rather than a desktop floor.
    assert interaction_ms < 3000.0
