from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter

import pytest

pytest.importorskip('PySide6')
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication

from font_lab_qt import FontLabEditor
from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView
from qt_theme import build_adaptive_stylesheet, build_theme_palette
from theme_system import THEME_NAMES
from version_info import APP_VERSION


def test_adaptive_theme_palette_and_stylesheet_construct_for_every_theme():
    for theme in THEME_NAMES:
        palette=build_theme_palette(theme)
        assert palette is not None
        css=build_adaptive_stylesheet('comfortable',1.0)
        assert 'palette(tooltip-base)' in css
        assert 'palette(tooltip-text)' in css


def test_settings_560_700_980_widths_all_pages_and_languages_have_no_violations(qtbot,tmp_path):
    store=PreferencesStore.load(tmp_path/'preferences.json')
    view=PreferencesView(store,Translator('en_US'));qtbot.addWidget(view);view.show()
    for width in (560,700,980):
        for language in ('zh_CN','en_US'):
            view.resize(width,720);view.set_language(language);view.stabilize_layout();QApplication.processEvents()
            for index in range(view.nav.count()):
                view.nav.setCurrentRow(index);view.stabilize_layout();QApplication.processEvents()
                assert view.layout_violations()==[],(width,language,index,view.layout_violations())
                assert not view.stack.currentWidget().horizontalScrollBar().isVisible()


def test_font_lab_generate_is_async_and_existing_pack_reopen_is_load_only(qtbot,tmp_path):
    root=tmp_path/'font'
    editor=FontLabEditor(root,name='Critical',cell=(16,16),language='en_US');qtbot.addWidget(editor);editor.show();qtbot.wait(10)
    editor.chars.setText('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'+''.join(chr(code) for code in range(0x400,0x600)))
    started=perf_counter();editor.generate();dispatch=perf_counter()-started
    assert dispatch<0.5
    if editor.generation_in_progress:
        assert editor.can_close() is False
    qtbot.waitUntil(lambda:not editor.generation_in_progress,timeout=30000)
    assert editor.can_close() is True
    for ch in '0123456789':
        assert ch in editor.pack.characters()
        assert any(any(row) for row in editor.pack.glyph(ch).pixels)
    manifest=root/'fontpack.json';before=manifest.stat().st_mtime_ns
    editor.close();QApplication.processEvents()
    started=perf_counter();reopened=FontLabEditor(root,language='en_US');elapsed=perf_counter()-started
    qtbot.addWidget(reopened);reopened.show();qtbot.wait(10)
    assert elapsed<2.0
    assert manifest.stat().st_mtime_ns==before
    assert reopened.glyphs.count()>0
    assert reopened.current_char is not None


def test_settings_footer_uses_current_version_ssot(qtbot,tmp_path):
    view=PreferencesView(PreferencesStore.load(tmp_path/'preferences.json'),Translator('en_US'));qtbot.addWidget(view)
    assert view.footer_version.text()==f'v{APP_VERSION}'
