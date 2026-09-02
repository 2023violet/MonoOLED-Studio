import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6'); pytest.importorskip('pytestqt')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesWindow
from qt_theme import build_stylesheet
from ui_controls import StudioSelect


def _store(tmp_path):
    path=tmp_path/'prefs.json'
    return PreferencesStore.load(path)


def _luma(c): return 0.2126*c.red()+0.7152*c.green()+0.0722*c.blue()


def test_one_dark_preferences_content_page_is_dark_not_white(qtbot,tmp_path):
    app=QApplication.instance(); app.setStyleSheet(build_stylesheet('one-dark-pro','comfortable',1.0))
    w=PreferencesWindow(_store(tmp_path),Translator('zh_CN')); qtbot.addWidget(w); w.resize(920,660); w.show(); qtbot.wait(30)
    page=w.findChild(QWidget,'PreferencesPage'); viewport=w.findChild(QWidget,'PreferencesViewport')
    assert page is not None and viewport is not None
    # Sample the explicitly-themed blank lower content area.
    image=viewport.grab().toImage(); c=image.pixelColor(max(1,image.width()-30),max(1,image.height()-30))
    assert _luma(c) < 140, (c.red(),c.green(),c.blue())


def test_all_preferences_selects_follow_anchor_toggle_contract(qtbot,tmp_path):
    w=PreferencesWindow(_store(tmp_path),Translator('zh_CN')); qtbot.addWidget(w); w.show(); qtbot.wait(20)
    selects=w.findChildren(StudioSelect)
    assert set(selects)=={
        w.language,w.theme_mode,w.density,w.ui_scale,w.wheel,w.middle,w.snap,
        w.validation,w.drag_preview,
    }
    for combo in selects:
        if combo.count()==0: continue
        combo.showPopup(); qtbot.wait(1); assert combo.popup.isVisible()
        combo.hidePopup(); qtbot.wait(1); assert not combo.popup.isVisible()


def test_preferences_page_switch_closes_active_popup(qtbot,tmp_path):
    w=PreferencesWindow(_store(tmp_path),Translator('zh_CN')); qtbot.addWidget(w); w.show(); qtbot.wait(20)
    w.nav.setCurrentRow(1); combo=w.theme_mode; combo.showPopup(); qtbot.wait(2); assert combo.popup.isVisible()
    w.nav.setCurrentRow(2); qtbot.wait(2)
    assert not combo.popup.isVisible()
