#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt gate for the V11 Generic Workbench information architecture."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
STATIC_SCENE = 'frame+validation'
STATE_SCENE = 'frame+state+validation'
TIMELINE_SCENE = 'frame+state+timeline+validation'
SETTINGS_EDITOR_TAB = 'settings:preferences'


def _child() -> int:
    sys.path.insert(0, str(SIM))
    try:
        from copy import deepcopy
        from PySide6.QtWidgets import QApplication
        from gui import OLEDDesignerWindow
        from preferences_qt import PreferencesView
    except Exception as exc:
        print(f'FAIL: Real-Qt imports unavailable: {exc}', file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = OLEDDesignerWindow('main_scene', 'en_US')
        window.resize(1440, 900)
        window.show(); app.processEvents()
        base = deepcopy(window.scene)

        static_scene = deepcopy(base); static_scene['states'] = {}; static_scene['timeline'] = []
        window._reset_session(static_scene); app.processEvents()
        if 'timeline' in window.preview_capabilities or 'state' in window.preview_capabilities:
            raise AssertionError(f'{STATIC_SCENE}: unexpected capabilities {window.preview_capabilities}')

        state_scene = deepcopy(base); state_scene['timeline'] = []; state_scene['preview'] = {'capabilities': ['state']}
        window._reset_session(state_scene); app.processEvents()
        if state_scene.get('states') and 'state' not in window.preview_capabilities:
            raise AssertionError(f'{STATE_SCENE}: state capability missing')
        if 'timeline' in window.preview_capabilities:
            raise AssertionError(f'{STATE_SCENE}: timeline should be hidden')

        timeline_scene = deepcopy(base); timeline_scene.setdefault('states', {}); timeline_scene['timeline'] = [{'at': 2, 'set': {}}]
        timeline_scene['preview'] = {'capabilities': ['state', 'timeline'], 'timeline': {'step': 2, 'unit': 'tick', 'label': 'Step'}}
        window._reset_session(timeline_scene); app.processEvents()
        if 'timeline' not in window.preview_capabilities:
            raise AssertionError(f'{TIMELINE_SCENE}: timeline capability missing')
        before = window.session.runtime.elapsed
        window.step_runtime(); app.processEvents()
        if window.session.runtime.elapsed != before + 2:
            raise AssertionError('generic Step did not use project timeline metadata')
        if window.step_button.text() != 'Step':
            raise AssertionError(f'generic Step copy regressed: {window.step_button.text()!r}')

        first = window.open_preferences(); second = window.open_preferences(); app.processEvents()
        if first is not second or not isinstance(first, PreferencesView):
            raise AssertionError('SETTINGS_EDITOR_TAB is not single/reused PreferencesView')
        if getattr(first, 'document_id', None) != SETTINGS_EDITOR_TAB:
            raise AssertionError('Settings editor document id mismatch')
        print('PASS: V11 Generic Workbench Preview capabilities + Settings editor tab')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if window is not None:
            window.session.document.dirty = False
            window.close()
        app.processEvents()


def main() -> int:
    if os.name != 'nt':
        print('SKIP: V11 Generic Workbench Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-v11-') as td:
        env = os.environ.copy(); env['LOCALAPPDATA'] = td; env['QT_QPA_PLATFORM'] = 'windows'; env['MONOOLED_REDUCED_MOTION'] = '1'
        return subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'], cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--child':
        raise SystemExit(_child())
    raise SystemExit(main())
