from __future__ import annotations

from pathlib import Path
import sys

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

SIM=Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0,str(SIM))


def test_real_main_window_constructs_and_initial_font_scan_matches_package(qtbot):
    from gui import OLEDDesignerWindow
    from scene import scene_root
    w=OLEDDesignerWindow('main_scene','zh_CN'); qtbot.addWidget(w); w.show(); QApplication.processEvents()
    expected=sum(1 for _ in scene_root(w.scene).rglob('fontpack.json'))
    assert w.font_list.count()==expected
    w.session.document.dirty=False; w.close(); QApplication.processEvents()


def test_agent_bridge_timer_is_off_until_started_and_stop_joins(qtbot):
    from gui import OLEDDesignerWindow
    w=OLEDDesignerWindow('main_scene','zh_CN'); qtbot.addWidget(w); w.show(); QApplication.processEvents()
    bridge=w.agent_bridge
    assert not bridge.timer.isActive() and bridge.thread is None
    endpoint=bridge.start(); assert endpoint['host']=='127.0.0.1'; assert bridge.timer.isActive(); assert bridge.thread is not None
    bridge.stop(); assert not bridge.timer.isActive(); assert bridge.thread is None and bridge.server is None
    w.session.document.dirty=False; w.close(); QApplication.processEvents()


def test_canvas_marquee_release_clears_gesture_state(qtbot):
    from qt_canvas import OLEDCanvas
    from framebuffer import FrameBuffer
    from render import RenderResult
    c=OLEDCanvas(); qtbot.addWidget(c); c.set_zoom(8); c.show()
    fb=FrameBuffer(128,32)
    resolved=(
        {'id':'a','type':'placeholder','visible':True,'x':1,'y':1,'w':4,'h':4,'assets':[]},
        {'id':'b','type':'placeholder','visible':True,'x':8,'y':1,'w':4,'h':4,'assets':[]},
    )
    c.set_frame(RenderResult(fb,resolved,(),()),[]); QApplication.processEvents()
    # Empty-space start followed by a marquee covering both objects.
    start=QPoint(c._margin+0*c.zoom+2,c._margin+0*c.zoom+2)
    end=QPoint(c._margin+12*c.zoom-2,c._margin+6*c.zoom-2)
    QTest.mousePress(c,Qt.LeftButton,Qt.NoModifier,start); QTest.mouseMove(c,end,20); QTest.mouseRelease(c,Qt.LeftButton,Qt.NoModifier,end); QApplication.processEvents()
    assert set(c.selected_ids)=={'a','b'}
    assert c._marquee_start is None and c._marquee_end is None


def test_startup_smoke_constructs_actual_window():
    from gui import run_startup_smoke
    assert run_startup_smoke('main_scene')==0
