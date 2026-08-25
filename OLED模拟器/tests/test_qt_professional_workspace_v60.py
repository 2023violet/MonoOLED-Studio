from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

PySide6 = pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen' if os.name != 'nt' else 'windows')

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from gui import OLEDDesignerWindow
from pixel_studio_qt import PixelStudioWindow
from professional_workspace import WorkspaceMode


def _drag(widget, start, end):
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseButtonPress, QPointF(*start), QPointF(*start), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)); QApplication.processEvents()
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseMove, QPointF(*end), QPointF(*end), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)); QApplication.processEvents()
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseButtonRelease, QPointF(*end), QPointF(*end), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)); QApplication.processEvents()


@pytest.mark.parametrize('size', [(960,680),(1180,720),(1440,900),(1920,1080)])
@pytest.mark.parametrize('language', ['zh_CN','en_US'])
def test_designer_professional_layout_has_no_clipping_and_canvas_priority(qtbot, size, language):
    w=OLEDDesignerWindow('main_scene', language); qtbot.addWidget(w); w.resize(*size); w.show(); qtbot.wait(80); w._responsive_tick(); qtbot.wait(20)
    assert w.layout_violations() == []
    assert w.canvas_scroll.viewport().width() >= int(w.width()*0.50)
    w.session.document.dirty=False; w.close()


def test_drag_defers_validation_until_release(qtbot):
    w=OLEDDesignerWindow('main_scene','en_US'); qtbot.addWidget(w); w.resize(1440,900); w.show(); qtbot.wait(80)
    target=str(w.scene['elements'][0]['id']); w.select_element(target); QApplication.processEvents()
    counts={'validation':0}; original=w._update_validation_panel
    def counted(): counts['validation']+=1; return original()
    w._update_validation_panel=counted
    before=w.session.geometry(target); ox,oy=w.canvas._origin(); z=w.canvas.zoom
    _drag(w.canvas,(ox+(before.x+1)*z,oy+(before.y+1)*z),(ox+(before.x+3)*z,oy+(before.y+1)*z))
    assert counts['validation'] == 1
    assert w.profiler.summary('drag_preview').count >= 1
    w.session.document.dirty=False; w.close()


def test_review_mode_is_read_only_and_opens_diff(qtbot):
    w=OLEDDesignerWindow('main_scene','en_US'); qtbot.addWidget(w); w.resize(1440,900); w.show(); qtbot.wait(50)
    w.set_workspace_mode(WorkspaceMode.REVIEW); QApplication.processEvents()
    assert not w.add_button.isEnabled()
    assert not w.geom_spins['x'].isEnabled()
    assert w.diagnostics_tabs.currentIndex() == 1
    w.set_workspace_mode(WorkspaceMode.DESIGN); QApplication.processEvents()
    assert w.add_button.isEnabled()
    w.session.document.dirty=False; w.close()


def test_pixel_studio_professional_workspace_and_selection_drag(qtbot):
    w=PixelStudioWindow(language='en_US'); qtbot.addWidget(w); w.resize(1180,780); w.show(); qtbot.wait(50)
    assert w.layout_violations() == []
    w.set_tool('Pencil'); z=w.canvas.zoom
    _drag(w.canvas,(2*z+2,2*z+2),(4*z+2,4*z+2))
    w.set_tool('Select')
    _drag(w.canvas,(2*z+2,2*z+2),(4*z+2,4*z+2))
    before=w.canvas.selection
    _drag(w.canvas,(3*z+2,3*z+2),(6*z+2,3*z+2))
    assert before is not None and w.canvas.selection[0] > before[0]
    w.close()
