from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip('PySide6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QScrollArea

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView
from qt_theme import build_stylesheet
from runtime_settings import RuntimeSettings


@pytest.mark.parametrize('language', ['zh_CN', 'en_US'])
@pytest.mark.parametrize('ui_scale', ['100%', '125%', '150%'])
def test_every_settings_page_converges_at_reported_full_desktop_size(qtbot, tmp_path, language, ui_scale):
    store = PreferencesStore.load(tmp_path / f'{language}-{ui_scale}.json')
    store.set('language', language, save=False)
    store.set('appearance.ui_scale', ui_scale, save=False)
    store.set('appearance.density', 'comfortable', save=False)
    runtime = RuntimeSettings.from_preferences(store)
    app = QApplication.instance()
    app.setStyleSheet(build_stylesheet('monooled-light', runtime.density, runtime.ui_scale))

    view = PreferencesView(store, Translator(language)); qtbot.addWidget(view)
    view.resize(1680, 900); view.show(); qtbot.wait(30)
    view.apply_runtime_settings(runtime); view.stabilize_layout(); QApplication.processEvents()

    for page_name in view.SECTIONS:
        view.nav.setCurrentRow(view.SECTIONS.index(page_name))
        view.stabilize_layout(); QApplication.processEvents()
        scroll = view.stack.currentWidget()
        assert isinstance(scroll, QScrollArea)
        content = view._content_by_scroll[scroll]
        assert content.width() >= 740
        assert view.layout_violations() == [], (page_name, view.layout_violations())
        for row in view._rows_by_scroll[scroll]:
            required = row._text_column.heightForWidth(max(1, row._text_column.width())) if row._has_text else 0
            assert row._text_column.height() >= required
            content_rect = QRect(row._content.mapTo(row, QPoint(0, 0)), row._content.size())
            divider_rect = QRect(row.divider.mapTo(row, QPoint(0, 0)), row.divider.size())
            assert content_rect.intersected(divider_rect).isEmpty()
