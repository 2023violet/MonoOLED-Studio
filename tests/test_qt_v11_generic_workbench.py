from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtWidgets import QApplication

SIM = Path(__file__).resolve().parents[1] / 'src'
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))

from gui import OLEDDesignerWindow
from preferences_qt import PreferencesView


def test_preview_sections_follow_scene_capabilities(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    window = OLEDDesignerWindow('main_scene')
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    qtbot.wait(20)
    base = deepcopy(window.scene)

    static_scene = deepcopy(base)
    static_scene['states'] = {}
    static_scene['timeline'] = []
    window._reset_session(static_scene)
    QApplication.processEvents()
    assert 'state' not in window.preview_capabilities
    assert 'timeline' not in window.preview_capabilities
    assert not window.preview_state_section.isVisible()
    assert not window.preview_timeline_section.isVisible()

    state_scene = deepcopy(base)
    state_scene['timeline'] = []
    window._reset_session(state_scene)
    QApplication.processEvents()
    if state_scene.get('states'):
        assert 'state' in window.preview_capabilities
        assert window.preview_state_section.isVisible()
    assert 'timeline' not in window.preview_capabilities

    timeline_scene = deepcopy(base)
    timeline_scene.setdefault('states', {})
    timeline_scene['timeline'] = [{'at': 2, 'set': {}}]
    timeline_scene['preview'] = {'timeline': {'step': 2, 'unit': 'tick', 'label': 'Step'}}
    window._reset_session(timeline_scene)
    QApplication.processEvents()
    assert 'timeline' in window.preview_capabilities
    assert window.preview_timeline_section.isVisible()
    before = window.session.runtime.elapsed
    window.step_runtime()
    assert window.session.runtime.elapsed == before + 2
    assert window.step_button.text() in {'Step', '步进'}


def test_settings_is_single_reused_editor_tab(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    window = OLEDDesignerWindow('main_scene')
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    qtbot.wait(20)
    first = window.open_preferences()
    second = window.open_preferences()
    assert first is second
    assert isinstance(first, PreferencesView)
    assert window.editor_tabs.currentWidget() is first
    assert sum(getattr(window.editor_tabs.widget(i), 'document_id', None) == 'settings:preferences' for i in range(window.editor_tabs.count())) == 1
