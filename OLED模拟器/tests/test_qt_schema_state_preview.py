import json
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from gui import OLEDDesignerWindow
from ui_controls import StudioNumericInput, StudioSelect


GENERIC_STATES = {
    'page': {'type': 'enum', 'values': ['HOME', 'SETTINGS'], 'init': 'HOME'},
    'channel': {'type': 'int', 'min': 1, 'max': 4, 'init': 2},
    'level': {'type': 'int', 'values': [0, 25, 50, 75, 100], 'init': 50},
    'alarm': {'type': 'enum', 'values': ['OFF', 'ON'], 'init': 'OFF'},
}


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([sys.argv[0]])


def _scene_file(tmp_path, *, states=None, timeline=None):
    path = tmp_path / 'generic_scene.json'
    path.write_text(json.dumps({
        'canvas': {'w': 128, 'h': 32},
        'storage': {'layout': 'VLSB', 'polarity': '1 = lit'},
        'states': GENERIC_STATES if states is None else states,
        'elements': [],
        'timeline': [] if timeline is None else timeline,
    }), encoding='utf-8')
    return path


def _window(app, path):
    window = OLEDDesignerWindow(str(path), 'en_US')
    window.resize(900, 620)
    window.show()
    window.inspector_tabs.setCurrentIndex(1)
    app.processEvents()
    return window


def _close(window, app):
    window.session.document.dirty = False
    window.close()
    app.processEvents()


def test_generic_schema_builds_ordered_editors_and_writes_typed_values(app, tmp_path):
    window = _window(app, _scene_file(tmp_path))
    try:
        assert list(window.state_editors) == ['page', 'channel', 'level', 'alarm']
        assert [binding['editor'].objectName() for binding in window.state_editors.values()] == [
            'StateEditor_page', 'StateEditor_channel', 'StateEditor_level', 'StateEditor_alarm',
        ]
        assert isinstance(window.state_editors['page']['editor'], StudioSelect)
        assert isinstance(window.state_editors['alarm']['editor'], StudioSelect)
        assert isinstance(window.state_editors['level']['editor'], StudioSelect)
        assert isinstance(window.state_editors['channel']['editor'], StudioNumericInput)
        assert window.session.runtime.state == {
            'page': 'HOME', 'channel': 2, 'level': 50, 'alarm': 'OFF',
        }
        assert window.state_editors['page']['editor'].currentData() == 'HOME'
        assert window.state_editors['channel']['editor'].value() == 2

        window.state_editors['page']['editor'].setCurrentIndex(1)
        window.state_editors['channel']['editor'].setValue(4)
        app.processEvents()
        assert window.session.runtime.state['page'] == 'SETTINGS'
        assert window.session.runtime.state['channel'] == 4
        assert not hasattr(window, 'mode_combo')
        assert not hasattr(window, 'phase_combo')
        assert not hasattr(window, 'battery_spin')
        assert not hasattr(window, 'seconds_spin')
    finally:
        _close(window, app)


def test_empty_schema_is_fail_closed_and_has_no_curing_controls(app, tmp_path):
    window = _window(app, _scene_file(tmp_path, states={}))
    try:
        assert window.state_editors == {}
        assert window.state_status_label.isVisible()
        assert window.state_status_label.text()
        assert not window.play_button.isVisible()
        assert not window.step_button.isVisible()
        assert not window.reset_button.isVisible()
    finally:
        _close(window, app)


def test_timeline_controls_are_generic_and_use_arbitrary_state_names(app, tmp_path):
    timeline = [{'at': 1, 'set': {'page': 'SETTINGS'}}]
    window = _window(app, _scene_file(tmp_path, timeline=timeline))
    try:
        assert window.play_button.isVisible()
        assert window.step_button.isVisible()
        assert window.reset_button.isVisible()
        assert 'Standby' not in window.elapsed_label.text()
        assert 'Running' not in window.elapsed_label.text()
        window.step_runtime()
        assert window.session.runtime.elapsed == 1
        assert window.session.runtime.state['page'] == 'SETTINGS'
        window.reset_runtime()
        assert window.session.runtime.elapsed == 0
        assert window.session.runtime.state['page'] == 'HOME'
    finally:
        _close(window, app)


def test_invalid_schema_disables_state_editing_without_curing_fallback(app, tmp_path):
    states = {'level': {'type': 'int', 'min': 10, 'max': 1, 'init': 3}}
    window = _window(app, _scene_file(tmp_path, states=states))
    try:
        assert window.state_editors == {}
        assert window.state_status_label.isVisible()
        assert 'RANGE' in window.state_status_label.text()
    finally:
        _close(window, app)


@pytest.mark.parametrize('size', [(900, 620), (1440, 900), (1920, 1080)])
def test_state_panel_has_no_horizontal_overflow_for_long_generic_fields(app, tmp_path, size):
    states = {
        f'channel_configuration_{index}_with_a_long_name': {
            'type': 'int', 'min': 0, 'max': 9, 'init': index,
        }
        for index in range(8)
    }
    window = _window(app, _scene_file(tmp_path, states=states))
    try:
        window.resize(*size)
        app.processEvents()
        assert window.state_page.horizontalScrollBar().maximum() == 0
        assert not any('horizontal' in issue for issue in window.layout_violations())
    finally:
        _close(window, app)
