import os
from pathlib import Path

import pytest

pytest.importorskip('PySide6')
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView, SettingRow
from version_info import APP_VERSION


def _view(qtbot, tmp_path, *, language='en_US'):
    store = PreferencesStore.load(tmp_path / 'preferences.json')
    store.set('language', language, save=False)
    view = PreferencesView(store, Translator(language))
    qtbot.addWidget(view)
    view.resize(980, 720)
    view.show()
    qtbot.wait(20)
    QApplication.processEvents()
    return view


def test_standard_setting_rows_do_not_overlap_and_controls_align(qtbot, tmp_path):
    view = _view(qtbot, tmp_path)
    rows = view.findChildren(SettingRow)
    assert rows
    for row in rows:
        row.set_compact(False)
        QApplication.processEvents()
        text_rect=QRect(row._text_column.mapTo(row,QPoint(0,0)),row._text_column.size())
        control_rect=QRect(row._control_column.mapTo(row,QPoint(0,0)),row._control_column.size())
        assert text_rect.intersected(control_rect).isEmpty()


def test_compact_setting_rows_stack_control_below_copy_without_overlap(qtbot, tmp_path):
    view = _view(qtbot, tmp_path)
    current = view.stack.currentWidget()
    assert current is not None
    current.viewport().resize(580, current.viewport().height())
    view._apply_responsive_layout()
    QApplication.processEvents()
    rows = view.findChildren(SettingRow)
    assert rows and all(row.is_compact for row in rows)
    for row in rows:
        text_rect=QRect(row._text_column.mapTo(row,QPoint(0,0)),row._text_column.size())
        control_rect=QRect(row._control_column.mapTo(row,QPoint(0,0)),row._control_column.size())
        assert control_rect.top() > text_rect.bottom()


def test_about_is_footer_metadata_not_a_navigation_page(qtbot, tmp_path):
    view = _view(qtbot, tmp_path)
    assert view.nav.count() == 7
    labels = [view.nav.item(i).text() for i in range(view.nav.count())]
    assert 'About' not in labels
    assert 'MonoOLED Studio' in view.footer_product.text()
    assert view.footer_version.text() == f'v{APP_VERSION}'


def test_saved_feedback_hides_after_feedback_timer(qtbot, tmp_path):
    view = _view(qtbot, tmp_path)
    view._set_save_state('saved')
    assert view.save_status.isVisible()
    view._clear_save_state()
    assert not view.save_status.isVisible()


def test_all_settings_pages_have_no_geometry_violations(qtbot, tmp_path):
    view = _view(qtbot, tmp_path)
    for page_index in range(view.nav.count()):
        view.nav.setCurrentRow(page_index)
        view.stabilize_layout()
        QApplication.processEvents()
        assert view.layout_violations() == [], (page_index, view.layout_violations())
