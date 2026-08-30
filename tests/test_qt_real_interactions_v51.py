from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

PySide6 = pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen' if os.name != 'nt' else 'windows')

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from gui import OLEDDesignerWindow


def _send_drag(widget, start, end):
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(*start), QPointF(*start), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    move = QMouseEvent(QEvent.MouseMove, QPointF(*end), QPointF(*end), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(*end), QPointF(*end), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(widget, press); QApplication.processEvents()
    QApplication.sendEvent(widget, move); QApplication.processEvents()
    QApplication.sendEvent(widget, release); QApplication.processEvents()


@pytest.fixture
def window(qtbot):
    w = OLEDDesignerWindow('main_scene', 'zh_CN')
    qtbot.addWidget(
        w,
        before_close_func=lambda widget: setattr(widget.session.document, 'dirty', False),
    )
    w.resize(1440, 900); w.show(); qtbot.wait(80)
    yield w


def test_real_mouse_drag_updates_scene_and_undo(window, qtbot):
    target = 'battery' if any(e.get('id') == 'battery' for e in window.scene['elements']) else str(window.scene['elements'][0]['id'])
    window.select_element(target); QApplication.processEvents()
    before = window.session.geometry(target)
    ox, oy = window.canvas._origin(); z = window.canvas.zoom
    start = (ox + (before.x + 1) * z, oy + (before.y + 1) * z)
    end = (start[0] + 2 * z, start[1])
    _send_drag(window.canvas, start, end)
    assert window.session.geometry(target).x == before.x + 2
    window.undo(); QApplication.processEvents()
    assert window.session.geometry(target).x == before.x


def test_compact_header_and_full_header_are_behaviorally_applied(window, qtbot):
    window.resize(960, 680); window._responsive_tick(); qtbot.wait(30)
    assert not window.hero_subtitle.isVisible()
    assert not window.header_project.isVisible()
    assert not window.header_validate.isVisible()
    assert window.header_save.isVisible()
    assert window.header_handoff.isVisible()
    assert window.layout_violations() == []

    window.resize(1600, 1000); window._responsive_tick(); qtbot.wait(30)
    assert window.hero_subtitle.isVisible()
    assert window.header_project.isVisible()
    assert window.header_validate.isVisible()
    assert window.layout_violations() == []


def test_live_spinbox_edit_rerenders_and_language_switches(window, qtbot):
    target = 'battery' if any(e.get('id') == 'battery' for e in window.scene['elements']) else str(window.scene['elements'][0]['id'])
    window.select_element(target); QApplication.processEvents()
    before = window.session.geometry(target)
    raw0 = window.session.render().framebuffer.to_vlsb()
    window.geom_spins['x'].setValue(before.x + 1); qtbot.wait(20)
    raw1 = window.session.render().framebuffer.to_vlsb()
    assert raw0 != raw1
    assert window.session.geometry(target).x == before.x + 1
    window.change_language('en_US'); qtbot.wait(20)
    assert window.tr.language == 'en_US'
    assert window.layout_violations() == []


def test_asset_directory_watcher_discovers_new_nested_asset(qtbot, tmp_path):
    from PIL import Image
    from project_workspace import create_project
    project=create_project(tmp_path/'watch_project',name='Watcher Test',canvas=(128,32))
    Image.new('1',(8,8),255).save(project.root/'assets'/'initial.png')
    w=OLEDDesignerWindow(str(project.path),'en_US'); qtbot.addWidget(w); w.resize(1180,720); w.show(); qtbot.wait(100)
    assert any(e.rel_path.endswith('initial.png') for e in w.asset_library.entries)
    nested=project.root/'assets'/'new_folder'; nested.mkdir()
    Image.new('1',(8,8),0).save(nested/'fresh.png')
    qtbot.waitUntil(lambda:any(e.rel_path.endswith('fresh.png') for e in w.asset_library.entries),timeout=4000)
    w.session.document.dirty=False; w.close()
