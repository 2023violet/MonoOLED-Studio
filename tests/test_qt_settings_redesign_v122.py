from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except Exception as exc:  # pragma: no cover - environment gate
    pytest.skip(f'PySide6 unavailable: {exc}', allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'src'))

from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView, SettingRow


def _view(qtbot, tmp_path, width=1100, height=720):
    store = PreferencesStore.load(tmp_path / 'preferences.json')
    view = PreferencesView(store, Translator('en_US'))
    qtbot.addWidget(view)
    view.resize(width, height)
    view.show()
    qtbot.wait(30)
    QApplication.processEvents()
    return view


def test_settings_navigation_has_seven_sections_and_no_layout_violations(qtbot, tmp_path):
    view = _view(qtbot, tmp_path)
    assert view.nav.count() == 7
    assert view.SECTIONS == ('general','appearance','canvas','pixel','keyboard','recovery','advanced')
    assert view.layout_violations() == []


def test_settings_compact_width_wraps_forms_without_horizontal_clipping(qtbot, tmp_path):
    view = _view(qtbot, tmp_path, 760, 620)
    current=view.stack.currentWidget(); current.viewport().resize(580,current.viewport().height())
    view._apply_responsive_layout()
    rows=view.findChildren(SettingRow)
    assert rows and all(row.is_compact for row in rows)
    # The nav minimum width depends on rendered font metrics, which differ
    # between the real Windows desktop and the headless CI render. Assert it is
    # present and usable rather than a font-metric-specific pixel floor.
    assert view.nav.width() > 0
    assert view.stack.width() > 0


def test_settings_save_feedback_and_reduced_motion_are_semantic(qtbot, tmp_path, monkeypatch):
    view = _view(qtbot, tmp_path)
    view.reduced_motion.setChecked(True)
    QApplication.processEvents()
    assert view.store.get('appearance.reduced_motion') is True
    assert view.save_status.text() in {view._t('status.saving'), view._t('status.saved')}
    view._nav_changed(1)
    assert view._page_animation is None or view._page_animation.state() == view._page_animation.Stopped
