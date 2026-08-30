from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

SIM = Path(__file__).resolve().parents[1] / 'src'
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))

from framebuffer import FrameBuffer
from gui import OLEDDesignerWindow
from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas
from qt_canvas import OLEDCanvas
from qt_theme import build_stylesheet, build_theme_palette
from render import RenderResult
from ui_controls import StudioSelect


def _distance(a, b):
    return max(abs(a.red()-b.red()), abs(a.green()-b.green()), abs(a.blue()-b.blue()))


def _pixel(widget, x, y):
    image = widget.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    return image.pixelColor(int(x), int(y))


def _prepare(app):
    app.setPalette(build_theme_palette('monooled-dark'))
    app.setStyleSheet(build_stylesheet('monooled-dark'))


def test_dirty_and_inspector_modified_dots_are_live_and_geometry_stable(qtbot):
    app=QApplication.instance(); _prepare(app)
    window=OLEDDesignerWindow('main_scene'); qtbot.addWidget(window); window.show(); qtbot.wait(20)
    element=next(e for e in window.scene['elements'] if all(k in e for k in ('x','y')) and not e.get('locked'))
    eid=str(element['id']); window._set_selection([eid],source='api',primary=eid); app.processEvents()
    dirty_size=window.document_dirty_dot.size(); label_sizes={k:v.size() for k,v in window.geom_labels.items()}
    assert not window.document_dirty_dot.is_active()
    field='x'; before=window.session.geometry(eid).x
    window.session.set_geometry(eid, **{field: before+1}); window.refresh_all(keep_selection=True); app.processEvents()
    assert window.document_dirty_dot.is_active()
    assert window.geom_labels[field].is_marked()
    assert window.document_dirty_dot.size()==dirty_size
    assert {k:v.size() for k,v in window.geom_labels.items()}==label_sizes
    window.session.document.dirty=False


def test_primary_corner_and_smart_guide_anchor_render_with_accent(qtbot):
    app=QApplication.instance(); _prepare(app)
    canvas=OLEDCanvas(); qtbot.addWidget(canvas); fb=FrameBuffer(32,16)
    result=RenderResult(fb,(
        {'id':'a','type':'placeholder','visible':True,'x':2,'y':2,'w':4,'h':4,'assets':[]},
        {'id':'b','type':'placeholder','visible':True,'x':12,'y':4,'w':5,'h':4,'assets':[]},
    ),(),())
    canvas.set_zoom(10); canvas.set_frame(result,('a','b')); canvas.set_selection(('a','b'),'b'); canvas.set_guides({'x':(14,),'y':(6,)},anchors=True); canvas.show(); qtbot.waitExposed(canvas); app.processEvents()
    accent=canvas.palette().highlight().color(); ox,oy=canvas._origin()
    # L-corner starts at the primary selection's top-left.
    assert _distance(_pixel(canvas,ox+12*10-1,oy+4*10-1),accent)<=48
    # Snap dot is wider than the one-pixel dashed guide, so sample one pixel off center.
    assert _distance(_pixel(canvas,ox+14*10+1,oy+6*10),accent)<=48


def test_pixel_hover_cursor_is_visible_without_mutating_document(qtbot):
    app=QApplication.instance(); _prepare(app)
    document=PixelDocument(8,8); canvas=PixelCanvas(document); canvas.theme_name='monooled-dark'; canvas.zoom=20
    canvas._sync_size(); qtbot.addWidget(canvas); canvas.show(); qtbot.waitExposed(canvas)
    before=[row[:] for row in document.pixels]
    QTest.mouseMove(canvas,QPoint(2*20+10,3*20+10)); app.processEvents()
    accent=canvas.palette().highlight().color()
    assert _distance(_pixel(canvas,2*20+1,3*20+10),accent)<=64
    assert document.pixels==before


def test_studio_select_current_row_has_right_side_accent_dot(qtbot):
    app=QApplication.instance(); _prepare(app)
    combo=StudioSelect(); combo.addItems(['Compact','Comfortable','Spacious']); combo.setCurrentIndex(1); combo.resize(220,34)
    qtbot.addWidget(combo); combo.show(); qtbot.waitExposed(combo); combo.showPopup(); app.processEvents()
    rect=combo.list.visualItemRect(combo.list.item(1)); assert rect.isValid()
    accent=combo.palette().highlight().color(); x=rect.right()-12; y=rect.center().y()
    image=combo.list.viewport().grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    sample=image.pixelColor(max(0,x),max(0,y))
    assert _distance(sample,accent)<=64
    combo.hidePopup()
