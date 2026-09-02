#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt gate for Theme Closure V10.1.

The regression reproduced by users was event-order dependent: switching
appearance did not repaint the whole UI until the mouse hovered individual
controls.  This gate therefore changes the real Preferences combo and captures
Main + Preferences immediately after the signal returns.  Deliberately no
mouse event and no external QApplication.processEvents() occurs between the
mode change and the assertions/captures.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
OUT = SIM / 'reports' / 'windows_theme_switch_v101'
TRANSITIONS=('light','dark','light','system')
NO_MOUSE_EVENT = True


def _child(output: Path) -> int:
    sys.path.insert(0, str(SIM))
    try:
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QApplication
        from gui import OLEDDesignerWindow
        from runtime_settings import RuntimeSettings
        from theme_system import resolve_theme_name
    except Exception as exc:
        print(f'FAIL: PySide6/Studio import unavailable: {exc}', file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    main = OLEDDesignerWindow(str(ROOT / 'test_assets/projects/curing_lite/project.oled.json'), language='zh_CN')
    main.resize(1440, 900)
    main.show()
    preferences = main.open_preferences()
    # Initial window construction may settle normally.  The no-event constraint
    # begins at each theme-mode change below.
    for _ in range(8):
        app.processEvents()

    output.mkdir(parents=True, exist_ok=True)
    results=[]
    try:
        for step, mode in enumerate(TRANSITIONS, 1):
            # A stale legacy palette must not override System mode.
            if mode == 'system':
                main.preferences.set('appearance.color_theme', 'high-contrast', save=False)

            index = preferences.theme_mode.findData(mode)
            if index < 0:
                raise AssertionError(f'missing appearance mode: {mode}')

            # NO_MOUSE_EVENT: changing the real Settings control synchronously
            # emits preferencesChanged -> main.apply_preferences -> theme transaction.
            preferences.theme_mode.setCurrentIndex(index)

            runtime = RuntimeSettings.from_preferences(main.preferences)
            system_dark = main.system_theme.is_dark()
            expected = resolve_theme_name(runtime.color_theme, runtime.theme_mode, system_dark=system_dark)
            actual = main._resolved_theme
            if actual != expected:
                raise AssertionError(f'{mode}: resolved {actual!r}, expected {expected!r}')

            signature = app.property('monooledAdaptiveStyleSignature')
            expected_signature = f'{runtime.density}:{runtime.ui_scale}'
            if signature != expected_signature:
                raise AssertionError(f'{mode}: signature {signature!r}, expected {expected_signature!r}')

            window_luma = app.palette().color(QPalette.Window).value()
            if expected == 'monooled-light' and window_luma < 128:
                raise AssertionError(f'{mode}: application palette stayed dark')
            if expected == 'one-dark-pro' and window_luma >= 128:
                raise AssertionError(f'{mode}: One Dark Pro palette stayed light')

            # Capture immediately after setCurrentIndex returns: no mouse move,
            # no hover and no caller-side processEvents are allowed here.
            main_path = output / f'{step:02d}_{mode}_main.png'
            pref_path = output / f'{step:02d}_{mode}_preferences.png'
            ok_main = main.grab().save(str(main_path))
            ok_preferences = preferences.grab().save(str(pref_path))
            if not (ok_main and ok_preferences):
                raise AssertionError(f'{mode}: screenshot capture failed')
            results.append({'mode':mode,'resolved':expected,'signature':str(signature),'main':main_path.name,'preferences':pref_path.name})

        (output / 'theme_switch_v101.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'PASS: Theme Closure V10.1 transitions={len(results)}; no-hover immediate repaint gate')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        main.session.document.dirty=False
        main.close()
        app.processEvents()


def main() -> int:
    if os.name != 'nt':
        print('SKIP: Theme Closure V10.1 Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-theme-v101-') as td:
        env=os.environ.copy()
        env['LOCALAPPDATA']=td
        env['QT_QPA_PLATFORM']='windows'
        env['MONOOLED_REDUCED_MOTION']='1'
        proc=subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', str(OUT)], cwd=ROOT, env=env, check=False)
        return int(proc.returncode)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--child':
        raise SystemExit(_child(Path(sys.argv[2]).resolve()))
    raise SystemExit(main())
