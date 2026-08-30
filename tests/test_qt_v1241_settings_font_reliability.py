from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter

import pytest

pytest.importorskip('PySide6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from font_lab_qt import FontLabEditor
from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView, SettingRow
from qt_theme import build_stylesheet
from runtime_settings import RuntimeSettings


def _assert_text_fits(widget):
    width = max(1, widget.width())
    needed = widget.heightForWidth(width) if widget.hasHeightForWidth() else widget.sizeHint().height()
    assert widget.height() >= needed, (widget.text(), widget.size(), needed)


def _assert_row_disjoint(row: SettingRow):
    text_rect = QRect(row._text_column.mapTo(row, QPoint(0, 0)), row._text_column.size())
    control_rect = QRect(row._control_column.mapTo(row, QPoint(0, 0)), row._control_column.size())
    if row.is_compact:
        assert control_rect.top() > text_rect.bottom() or text_rect.height() == 0
    else:
        assert text_rect.intersected(control_rect).isEmpty()
    if row.label is not None:
        _assert_text_fits(row.label)
    if row.help_label is not None:
        _assert_text_fits(row.help_label)


@pytest.mark.parametrize('language', ['zh_CN', 'en_US'])
@pytest.mark.parametrize('ui_scale', ['100%', '125%', '150%'])
def test_reported_settings_pages_have_no_overlap_at_desktop_viewport(qtbot, tmp_path, language, ui_scale):
    store = PreferencesStore.load(tmp_path / f'{language}-{ui_scale}.json')
    store.set('language', language, save=False)
    store.set('appearance.ui_scale', ui_scale, save=False)
    store.set('appearance.density', 'comfortable', save=False)
    runtime = RuntimeSettings.from_preferences(store)
    app = QApplication.instance()
    app.setStyleSheet(build_stylesheet('monooled-light', runtime.density, runtime.ui_scale))
    view = PreferencesView(store, Translator(language)); qtbot.addWidget(view)
    view.resize(1600, 780); view.show(); qtbot.wait(20)
    view.apply_runtime_settings(runtime); view.stabilize_layout(); QApplication.processEvents()
    for page_name in ('appearance', 'canvas', 'recovery'):
        view.nav.setCurrentRow(view.SECTIONS.index(page_name))
        view.stabilize_layout(); QApplication.processEvents()
        assert view.layout_violations() == [], (page_name, language, ui_scale, view.layout_violations())
        for row in view._rows_by_scroll[view.stack.currentWidget()]:
            _assert_row_disjoint(row)


def test_font_lab_cell_resize_auto_updates_baseline_advance_and_font_size_until_user_override(qtbot, tmp_path):
    editor = FontLabEditor(tmp_path / 'font', name='Clinical 5x7', cell=(5, 8), language='zh_CN')
    qtbot.addWidget(editor); editor.show(); qtbot.wait(10)
    assert editor.baseline.value() == 6
    assert editor.advance.value() == 6
    editor.cell_w.setValue(8); editor.cell_h.setValue(12); QApplication.processEvents()
    assert editor.baseline.value() == 10
    assert editor.advance.value() == 9
    assert editor.font_size.value() <= 12

    editor.baseline.setValue(7); editor._baseline_edited()
    editor.advance.setValue(8); editor._advance_edited()
    editor.cell_w.setValue(10); editor.cell_h.setValue(16); QApplication.processEvents()
    assert editor.baseline.value() == 7
    assert editor.advance.value() == 8


def test_font_lab_default_generation_is_async_single_dispatch_and_reopen_load_only(qtbot, tmp_path):
    root = tmp_path / 'font'
    editor = FontLabEditor(root, name='Clinical 5x7', cell=(5, 8), language='zh_CN')
    qtbot.addWidget(editor); editor.show(); qtbot.wait(10)
    assert not editor.font_path.text()
    assert editor.font_path.placeholderText()
    started = perf_counter(); editor.generate(); dispatch = perf_counter() - started
    assert dispatch < 0.5
    first_thread = editor._generation_thread
    editor.generate()
    assert editor._generation_thread is first_thread
    qtbot.waitUntil(lambda: not editor.generation_in_progress, timeout=5000)
    assert len(editor.pack.characters()) >= 37
    for ch in 'ABEN08/':
        assert any(any(row) for row in editor.pack.glyph(ch).pixels)
    manifest = root / 'fontpack.json'; before = manifest.stat().st_mtime_ns
    editor.close(); QApplication.processEvents()
    reopened = FontLabEditor(root, language='zh_CN'); qtbot.addWidget(reopened)
    assert manifest.stat().st_mtime_ns == before
