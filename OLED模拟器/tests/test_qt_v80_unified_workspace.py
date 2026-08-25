import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
PySide6=pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from framebuffer import FrameBuffer
from render import RenderResult
from gui import OLEDDesignerWindow
from qt_canvas import OLEDCanvas
from ui_controls import StudioSelect, StudioPopover
from font_lab_qt import FontLabEditor
from font_pack import create_font_pack


def test_studio_select_uses_frameless_translucent_owned_popover(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);combo.addItem('96×16',(96,16));combo.addItem('128×32',(128,32));combo.resize(220,34);combo.show()
    QTest.mouseClick(combo.button,Qt.LeftButton)
    assert isinstance(combo.popup,StudioPopover)
    assert combo.popup.testAttribute(Qt.WA_TranslucentBackground)
    assert bool(combo.popup.windowFlags() & Qt.FramelessWindowHint)
    assert combo.popup.isVisible()
    QTest.keyClick(combo.list,Qt.Key_Escape);combo.popup.hide()


def test_designer_opens_pixel_asset_as_workspace_tab_not_second_window(qtbot):
    window=OLEDDesignerWindow('main_scene');qtbot.addWidget(window);window.show();qtbot.wait(20)
    image=next(e for e in window.scene['elements'] if e.get('type')=='image' and e.get('asset'))
    window._set_selection([str(image['id'])],source='api',primary=str(image['id']))
    before=window.editor_tabs.count();window.open_pixel_studio();qtbot.wait(20)
    assert window.editor_tabs.count()==before+1
    editor=window.editor_tabs.currentWidget()
    assert getattr(editor,'document_id','').startswith('asset:')
    assert not editor.isWindow()
    same_count=window.editor_tabs.count();window.open_pixel_studio();assert window.editor_tabs.count()==same_count


def test_canvas_ctrl_click_uses_ordered_primary_selection(qtbot):
    canvas=OLEDCanvas();qtbot.addWidget(canvas);fb=FrameBuffer(32,16)
    result=RenderResult(fb,(
        {'id':'a','type':'placeholder','visible':True,'x':2,'y':2,'w':4,'h':4,'assets':[]},
        {'id':'b','type':'placeholder','visible':True,'x':12,'y':2,'w':4,'h':4,'assets':[]},
    ),(),())
    canvas.set_zoom(10);canvas.set_frame(result,());canvas.show();ox,oy=canvas._origin()
    QTest.mouseClick(canvas,Qt.LeftButton,Qt.NoModifier,QPoint(ox+3*10,oy+3*10))
    QTest.mouseClick(canvas,Qt.LeftButton,Qt.ControlModifier,QPoint(ox+13*10,oy+3*10))
    assert canvas.selected_ids==('a','b') and canvas.primary_id=='b'
    QTest.mouseClick(canvas,Qt.LeftButton,Qt.ControlModifier,QPoint(ox+13*10,oy+3*10))
    assert canvas.selected_ids==('a',) and canvas.primary_id=='a'


def test_canvas_marquee_selects_multiple_objects(qtbot):
    canvas=OLEDCanvas();qtbot.addWidget(canvas);fb=FrameBuffer(32,16)
    result=RenderResult(fb,(
        {'id':'a','type':'placeholder','visible':True,'x':3,'y':3,'w':3,'h':3,'assets':[]},
        {'id':'b','type':'placeholder','visible':True,'x':10,'y':4,'w':3,'h':3,'assets':[]},
    ),(),())
    canvas.set_zoom(10);canvas.set_frame(result,());canvas.show();ox,oy=canvas._origin()
    start=QPoint(ox+1*10,oy+1*10);end=QPoint(ox+14*10,oy+8*10)
    QTest.mousePress(canvas,Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(canvas,end,20);QTest.mouseRelease(canvas,Qt.LeftButton,Qt.NoModifier,end)
    assert canvas.selected_ids==('a','b') and canvas.primary_id=='b'


def test_font_lab_is_embeddable_editor(qtbot,tmp_path):
    from PySide6.QtWidgets import QTabWidget
    pack=create_font_pack(tmp_path/'font','Test',cell=(5,8),baseline=6,advance=6);pack.save()
    host=QTabWidget();qtbot.addWidget(host)
    editor=FontLabEditor(pack.root,parent=host);host.addTab(editor,'Font');host.show();qtbot.wait(10)
    assert editor.document_id.startswith('font:')
    assert not editor.isWindow()
    assert editor.pack.cell==(5,8)
