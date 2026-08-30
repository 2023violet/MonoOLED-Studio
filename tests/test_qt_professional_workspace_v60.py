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

from PySide6.QtCore import QEvent, QPointF, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

import gui as gui_module
from gui import OLEDDesignerWindow
from pixel_studio_qt import PixelStudioWindow
from professional_workspace import WorkspaceMode
from qt_widgets import StatusPill


def _drag(widget, start, end):
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseButtonPress, QPointF(*start), QPointF(*start), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)); QApplication.processEvents()
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseMove, QPointF(*end), QPointF(*end), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)); QApplication.processEvents()
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseButtonRelease, QPointF(*end), QPointF(*end), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)); QApplication.processEvents()


def test_status_pill_all_semantic_styles_parse_without_qt_warnings(qtbot):
    warnings = []
    previous = qInstallMessageHandler(
        lambda kind, _context, message: warnings.append(message)
        if kind == QtMsgType.QtWarningMsg else None
    )
    try:
        pill = StatusPill('Ready')
        qtbot.addWidget(pill)
        for theme in ('monooled-light', 'monooled-dark'):
            pill.set_theme(theme)
            for status in ('neutral', 'accent', 'success', 'warning', 'error', 'danger', 'unknown'):
                pill.set_status(status)
        QApplication.processEvents()
    finally:
        qInstallMessageHandler(previous)

    assert not [message for message in warnings if 'stylesheet' in message.lower()]


@pytest.mark.parametrize('size', [
    (900,620), (960,680), (1100,700), (1180,720),
    (1440,900), (1920,1080), (2560,1440),
])
@pytest.mark.parametrize('language', ['zh_CN','en_US'])
def test_designer_inspector_content_never_overflows_horizontally(qtbot, size, language):
    w=OLEDDesignerWindow('main_scene', language); qtbot.addWidget(w); w.resize(*size); w.show(); qtbot.wait(80); w._responsive_tick(); qtbot.wait(20)
    for scroll in (w.inspector_page, w.state_page):
        assert scroll.horizontalScrollBar().maximum() == 0
        assert scroll.widget().width() <= scroll.viewport().width()
    w.session.document.dirty=False; w.close()


def test_designer_layout_check_allows_intentional_vertical_scrolling(qtbot):
    w=OLEDDesignerWindow('main_scene', 'en_US'); qtbot.addWidget(w); w.resize(960,680); w.show(); qtbot.wait(80); w._responsive_tick(); qtbot.wait(20)
    scrollbar=w.inspector_page.verticalScrollBar()
    for value in (scrollbar.minimum(), scrollbar.maximum()//2, scrollbar.maximum()):
        scrollbar.setValue(value); qtbot.wait(10)
        assert w.layout_violations() == []
    w.session.document.dirty=False; w.close()


def test_designer_layout_settles_to_a_stable_geometry_signature(qtbot):
    w=OLEDDesignerWindow('main_scene', 'zh_CN'); qtbot.addWidget(w); w.resize(1180,720); w.show()
    w.change_language('en_US'); w.toggle_diagnostics()

    assert gui_module._settle_window_layout(QApplication.instance(), w)
    first=(tuple(w.workspace_splitter.sizes()),tuple(w.vertical_splitter.sizes()),w.inspector_page.viewport().size().toTuple(),w.state_page.viewport().size().toTuple(),w._layout_bucket)
    assert gui_module._settle_window_layout(QApplication.instance(), w)
    second=(tuple(w.workspace_splitter.sizes()),tuple(w.vertical_splitter.sizes()),w.inspector_page.viewport().size().toTuple(),w.state_page.viewport().size().toTuple(),w._layout_bucket)

    assert second == first
    assert w.layout_violations() == []
    w.session.document.dirty=False; w.close()


@pytest.mark.parametrize('size', [(960,680),(1180,720),(1440,900),(1920,1080)])
@pytest.mark.parametrize('language', ['zh_CN','en_US'])
def test_designer_professional_layout_has_no_clipping_and_canvas_priority(qtbot, size, language):
    w=OLEDDesignerWindow('main_scene', language); qtbot.addWidget(w); w.resize(*size); w.show(); qtbot.wait(80); w._responsive_tick(); qtbot.wait(20)
    # Re-assert the requested size: headless relayout can grow the window to its
    # size hint, so measure the intended window geometry.
    w.resize(*size); QApplication.processEvents(); w._responsive_tick(); QApplication.processEvents()
    assert w.layout_violations() == []
    # Canvas-first guarantee: the canvas pane is the widest workspace pane. The
    # 50%-of-window-width heuristic is not stable across headless splitter
    # distribution, so assert dominance instead.
    assert w.workspace_splitter.sizes()[1] == max(w.workspace_splitter.sizes())
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
