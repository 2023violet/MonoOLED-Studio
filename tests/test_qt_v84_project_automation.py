from __future__ import annotations

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtWidgets import QApplication


def test_real_gui_project_automation_switches_active_screen_and_refreshes_workspace(qtbot, tmp_path):
    from project_workspace import create_project
    from gui import OLEDDesignerWindow

    project = create_project(tmp_path / 'agent_gui_project', name='Agent GUI', canvas=(32, 16))
    w = OLEDDesignerWindow(str(project.path), 'en_US')
    qtbot.addWidget(w); w.show(); QApplication.processEvents()
    assert w.project is not None
    assert w.font_list.count() >= 0  # construction path must complete even for a blank project

    result = w.automation_service.call('project.create_screen', {
        'screen_id': 'agent_screen', 'label': 'Agent Screen', 'open': True,
    })
    w._agent_command_completed({'result': result})
    QApplication.processEvents()
    assert w.project.active_screen == 'agent_screen'
    assert w.automation_service.call('project.get', {})['active_screen'] == 'agent_screen'
    assert w.session.render().framebuffer.width == 32
    assert w.session.render().framebuffer.height == 16
    ids = {w.screen_list.item(i).data(0x0100) for i in range(w.screen_list.count())}
    assert 'agent_screen' in ids
    w.session.document.dirty = False
    w.close(); QApplication.processEvents()
