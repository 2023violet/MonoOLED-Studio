import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from gui import OLEDDesignerWindow
from ui_controls import PopupManager, StudioSelect
from preferences import default_preferences
from runtime_settings import RuntimeSettings
from preference_delta import PreferenceDelta
from font_pack import create_font_pack
from font_lab_qt import FontLabEditor


def test_select_closes_before_current_index_callback_executes(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);combo.addItems(['A','B','C']);combo.resize(220,34);combo.show();qtbot.wait(5)
    seen=[]
    combo.currentIndexChanged.connect(lambda _i:seen.append(combo.popup.isVisible()))
    QTest.mouseClick(combo.button,Qt.LeftButton);qtbot.wait(5)
    item=combo.list.item(1);rect=combo.list.visualItemRect(item)
    QTest.mouseClick(combo.list.viewport(),Qt.LeftButton,Qt.NoModifier,rect.center());qtbot.wait(10)
    assert combo.currentIndex()==1
    assert seen[-1] is False
    assert PopupManager.visible_count()==0


def test_only_one_studio_popup_can_be_visible(qtbot):
    a=StudioSelect();b=StudioSelect();qtbot.addWidget(a);qtbot.addWidget(b)
    for c in (a,b):c.addItems(['A','B']);c.resize(200,34);c.show()
    QTest.mouseClick(a.button,Qt.LeftButton);qtbot.wait(2);assert a.popup.isVisible()
    QTest.mouseClick(b.button,Qt.LeftButton);qtbot.wait(2)
    assert not a.popup.isVisible() and b.popup.isVisible() and PopupManager.visible_count()==1


def test_popup_rect_stays_inside_available_screen(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);[combo.addItem(f'Item {i}') for i in range(40)];combo.resize(260,34);combo.show();qtbot.wait(5)
    QTest.mouseClick(combo.button,Qt.LeftButton);qtbot.wait(5)
    screen=combo.screen().availableGeometry();rect=combo.popup.frameGeometry()
    assert screen.contains(rect.topLeft()) and screen.contains(rect.bottomRight())


def test_ui_only_language_change_does_not_call_full_refresh(qtbot):
    w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.show();qtbot.wait(20)
    called=[]; original=w.refresh_all
    w.refresh_all=lambda *a,**k:called.append(1)
    w.preferences.set('language','en_US' if w.tr.language=='zh_CN' else 'zh_CN',save=False)
    w.apply_preferences();qtbot.wait(10)
    w.refresh_all=original
    assert called==[]


def test_embedded_pixel_and_font_receive_language_and_theme_delta(qtbot,tmp_path):
    w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.show();qtbot.wait(20)
    pack=create_font_pack(tmp_path/'font','Test',cell=(5,8),baseline=6,advance=6);pack.save()
    editor=FontLabEditor(pack.root,parent=w.editor_tabs,language=w.tr.language);w.editor_tabs.addTab(editor,'Font');w.editor_registry.open(editor)
    before=w._runtime_preferences
    data=default_preferences();data['language']='en_US';data['appearance']['color_theme']='monooled-dark';after=RuntimeSettings.from_preferences(data)
    delta=PreferenceDelta.between(before,after)
    w._resolved_theme='monooled-dark';w.editor_registry.apply_runtime_delta(delta);qtbot.wait(5)
    assert editor.tr.language=='en_US'
    assert editor.canvas.theme_name=='monooled-dark'


def test_repeated_popup_open_close_has_no_visible_popup_leak(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);combo.addItems(['A','B','C']);combo.resize(220,34);combo.show()
    for _ in range(100):
        QTest.mouseClick(combo.button,Qt.LeftButton);qtbot.wait(1);combo.popup.hide()
    assert PopupManager.visible_count()==0
