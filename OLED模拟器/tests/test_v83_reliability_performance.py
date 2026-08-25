from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))


def _duplicate_methods(path: Path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            seen = {}
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name in seen:
                        found.append((node.name, child.name, seen[child.name], child.lineno))
                    else:
                        seen[child.name] = child.lineno
    return found


def test_no_duplicate_class_methods_in_production_python():
    duplicates = []
    for path in SIM.glob('*.py'):
        duplicates.extend((path.name, *item) for item in _duplicate_methods(path))
    assert duplicates == []


def test_studio_select_is_fully_initialized_before_event_filters_are_installed():
    source = (SIM / 'ui_controls.py').read_text(encoding='utf-8')
    class_body = source.split('class StudioSelect(QWidget):', 1)[1].split('        @property\n        def popup_state', 1)[0]
    assert class_body.index('self.popup =') < class_body.index('self.button.installEventFilter(self)')
    assert class_body.index('self.list =') < class_body.index('self.button.installEventFilter(self)')
    assert class_body.index('self.list =') < class_body.index('self.list.installEventFilter(self)')


def test_english_workspace_labels_are_english():
    from i18n import EN
    assert EN['workspace.design'] == 'Design'
    assert EN['workspace.review'] == 'Review'


def test_qt_automation_bridge_does_not_poll_when_stopped_and_shutdown_is_joined():
    source = (SIM / 'automation_qt.py').read_text(encoding='utf-8')
    init = source.split('def __init__', 1)[1].split('    @property', 1)[0]
    assert 'self.timer.start()' not in init
    stop = source.split('def stop(self):', 1)[1].split('    def _dispatch_from_thread', 1)[0]
    assert 'self.timer.stop()' in stop
    assert '.join(' in stop
    assert 'self.thread=None' in stop or 'self.thread = None' in stop


def test_main_window_close_stops_agent_bridge():
    source = (SIM / 'gui.py').read_text(encoding='utf-8')
    close = source.split('        def closeEvent(self,event:QCloseEvent):', 1)[1].split('\n\ndef check_environment', 1)[0]
    assert 'agent_bridge.stop()' in close


def test_system_theme_provider_does_not_capture_window_owned_self_in_lambda():
    source = (SIM / 'system_theme.py').read_text(encoding='utf-8')
    assert 'colorSchemeChanged.connect(lambda' not in source
    assert 'def close(' in source or 'def dispose(' in source


def _small_scene(tmp_path: Path):
    path = tmp_path / 'scene.json'
    scene = {
        '_path': str(path), '_root': str(tmp_path),
        'canvas': {'w': 128, 'h': 32},
        'states': {}, 'timeline': [],
        'elements': [
            {'id': 'a', 'type': 'placeholder', 'x': 1, 'y': 2, 'w': 5, 'h': 6},
            {'id': 'b', 'type': 'placeholder', 'x': 20, 'y': 4, 'w': 7, 'h': 8},
            {'id': 'c', 'type': 'placeholder', 'x': 40, 'y': 6, 'w': 9, 'h': 10},
        ],
    }
    path.write_text(json.dumps({k:v for k,v in scene.items() if not k.startswith('_')}), encoding='utf-8')
    return scene


def test_geometry_query_does_not_render_full_scene(tmp_path):
    from editor_model import EditorSession
    session = EditorSession(_small_scene(tmp_path))
    def fail_render():
        raise AssertionError('geometry must not render the full scene')
    session.render = fail_render
    g = session.geometry('a')
    assert (g.x, g.y, g.w, g.h) == (1, 2, 5, 6)


def test_smart_guides_do_not_render_full_scene(tmp_path):
    from editor_model import EditorSession
    from selection_tools import smart_guides
    session = EditorSession(_small_scene(tmp_path))
    def fail_render():
        raise AssertionError('smart guides must not render the full scene')
    session.render = fail_render
    result = smart_guides(session, 'a')
    assert isinstance(result, dict)


def test_align_to_is_one_undo_command(tmp_path):
    from editor_model import EditorSession
    from selection_tools import align_to
    scene = _small_scene(tmp_path)
    before = deepcopy(scene['elements'])
    session = EditorSession(scene)
    align_to(session, ['a', 'b', 'c'], 'left', reference='selection')
    assert len(session._undo) == 1
    assert session.undo() is True
    assert scene['elements'] == before


def test_distribute_is_one_undo_command(tmp_path):
    from editor_model import EditorSession
    from selection_tools import distribute
    scene = _small_scene(tmp_path)
    scene['elements'][1]['x'] = 10
    scene['elements'][2]['x'] = 50
    before = deepcopy(scene['elements'])
    session = EditorSession(scene)
    distribute(session, ['a', 'b', 'c'], 'horizontal')
    assert len(session._undo) == 1
    assert session.undo() is True
    assert scene['elements'] == before


def test_corrupt_preferences_are_quarantined_before_default_fallback(tmp_path):
    from preferences import PreferencesStore
    p = tmp_path / 'preferences.json'
    p.write_text('{broken', encoding='utf-8')
    store = PreferencesStore.load(p)
    assert store.get('language') == 'zh_CN'
    quarantine = tmp_path / 'quarantine'
    assert quarantine.is_dir()
    copies = list(quarantine.glob('preferences.corrupt.*.json'))
    assert len(copies) == 1
    assert copies[0].read_text(encoding='utf-8') == '{broken'


def test_gui_exposes_real_startup_smoke_separate_from_core_check():
    source = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'def run_startup_smoke(' in source
    assert "'--startup-smoke'" in source or '"--startup-smoke"' in source
    startup = source.split('def run_startup_smoke(', 1)[1].split('\ndef ', 1)[0]
    assert 'OLEDDesignerWindow(' in startup
    assert 'processEvents()' in startup


def test_shortcut_conflict_recovery_preserves_non_conflicting_custom_bindings():
    from commands import CommandRegistry
    r = CommandRegistry()
    for cid, default in {'a':'Ctrl+A','b':'Ctrl+B','c':'Ctrl+C'}.items():
        r.register(cid, shortcut=default)
    accepted, rejected = r.apply_bindings_best_effort({'a':'Ctrl+X','b':'Ctrl+X','c':'Ctrl+Y'})
    assert r.shortcut('a') == 'Ctrl+X'
    assert r.shortcut('b') == 'Ctrl+B'
    assert r.shortcut('c') == 'Ctrl+Y'
    assert accepted == {'a':'Ctrl+X','c':'Ctrl+Y'}
    assert set(rejected) == {'b'}
