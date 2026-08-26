from __future__ import annotations

from pathlib import Path
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QEvent, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout

SIM=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SIM))
from preferences import PreferencesStore, default_preferences
from qt_interaction import FocusOriginFilter
from qt_theme import build_stylesheet
from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas, PixelStudioWindow
from ui_controls import StudioButton


def _rgba(widget):
    image=widget.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    return bytes(image.bits())


def test_hover_leave_returns_to_exact_baseline(qtbot):
    app=QApplication.instance(); app.setStyleSheet(build_stylesheet('monooled-light'))
    f=FocusOriginFilter(app); app.installEventFilter(f)
    host=QWidget(); layout=QVBoxLayout(host); button=StudioButton('Test'); layout.addWidget(button); other=StudioButton('Other'); layout.addWidget(other); qtbot.addWidget(host); host.show(); qtbot.waitExposed(host)
    app.sendEvent(button,QEvent(QEvent.Leave)); app.processEvents()
    assert not bool(button.property('hoverVisible')); baseline=_rgba(button)
    app.sendEvent(button,QEvent(QEvent.Enter)); app.processEvents()
    assert bool(button.property('hoverVisible')); assert _rgba(button)!=baseline
    app.sendEvent(button,QEvent(QEvent.Leave)); app.processEvents()
    assert not bool(button.property('hoverVisible'))
    assert _rgba(button)==baseline


def test_mouse_focus_has_no_keyboard_ring_but_tab_focus_does(qtbot):
    app=QApplication.instance(); f=FocusOriginFilter(app); app.installEventFilter(f)
    host=QWidget(); layout=QVBoxLayout(host); a=StudioButton('A'); b=StudioButton('B'); layout.addWidget(a); layout.addWidget(b); qtbot.addWidget(host); host.show(); qtbot.waitExposed(host)
    QTest.mouseClick(a,Qt.LeftButton); app.processEvents(); assert not bool(a.property('keyboardFocusVisible'))
    a.clearFocus(); b.clearFocus(); QTest.keyClick(host,Qt.Key_Tab); app.processEvents()
    focused=app.focusWidget(); assert focused in (a,b); assert bool(focused.property('keyboardFocusVisible'))


def test_pixel_left_draw_right_erase_and_pan_do_not_corrupt_framebuffer(qtbot):
    d=PixelDocument(16,8); canvas=PixelCanvas(d); canvas.zoom=12; canvas._sync_size(); qtbot.addWidget(canvas); canvas.show(); qtbot.waitExposed(canvas)
    p=lambda x,y: QPoint(x*12+6,y*12+6)
    QTest.mousePress(canvas,Qt.LeftButton,pos=p(1,2)); QTest.mouseMove(canvas,p(7,2),delay=10); QTest.mouseRelease(canvas,Qt.LeftButton,pos=p(7,2)); assert all(d.get(x,2)==1 for x in range(1,8))
    QTest.mousePress(canvas,Qt.RightButton,pos=p(3,2)); QTest.mouseMove(canvas,p(5,2),delay=10); QTest.mouseRelease(canvas,Qt.RightButton,pos=p(5,2)); assert all(d.get(x,2)==0 for x in range(3,6))


@pytest.mark.parametrize('theme',['monooled-light','monooled-dark','one-dark-pro','high-contrast'])
@pytest.mark.parametrize('language',['zh_CN','en_US'])
@pytest.mark.parametrize('density',['compact','comfortable','spacious'])
def test_v7_visual_configuration_matrix_constructs_without_clipping(qtbot,tmp_path,theme,language,density):
    prefs=default_preferences(); prefs['language']=language; prefs['appearance']['color_theme']=theme; prefs['appearance']['density']=density
    store=PreferencesStore(tmp_path/'prefs.json',prefs); store.save(); w=PixelStudioWindow(language=language,preferences=store); qtbot.addWidget(w); w.resize(1000,700); w.show(); qtbot.waitExposed(w); assert not w.layout_violations()
