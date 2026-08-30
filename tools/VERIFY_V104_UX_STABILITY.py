#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt gate for V10.4 UX Stability & Performance."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
OUT = SIM / 'reports' / 'windows_v104_ux_stability'

# Release-contract markers consumed by source tests and the final report.
APPROVED_DARK_THEME = 'one-dark-pro'
SECOND_CLICK_STAYS_CLOSED = True
OUTSIDE_CLICK_REOPENS_NEXT = True
VISIBLE_REGION_COVERS_CONTROL = True
STARTUP_VISIBLE_MS = 3000.0
INTERACTION_MS = 250.0
SURFACES = ('PreferencesView', 'StudioSelect')


def _child(output: Path) -> int:
    sys.path.insert(0, str(SIM))
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from gui import OLEDDesignerWindow
        from preferences_qt import PreferencesView
        from ui_controls import StudioSelect
    except Exception as exc:
        print(f'FAIL: Real-Qt imports unavailable: {exc}', file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    output.mkdir(parents=True, exist_ok=True)
    main = None
    combo = None
    results: dict[str, object] = {}
    try:
        started = perf_counter()
        main = OLEDDesignerWindow('main_scene')
        main.resize(1440, 900)
        main.show()
        app.processEvents()
        startup_ms = (perf_counter() - started) * 1000.0
        results['STARTUP_VISIBLE_MS'] = startup_ms
        if startup_ms >= STARTUP_VISIBLE_MS:
            raise AssertionError(f'startup visible latency {startup_ms:.1f}ms >= {STARTUP_VISIBLE_MS:.0f}ms')

        main.preferences.set('appearance.theme_mode', 'dark', save=False)
        main.apply_preferences()
        if main._resolved_theme != APPROVED_DARK_THEME:
            raise AssertionError(f'dark resolved {main._resolved_theme!r}, expected {APPROVED_DARK_THEME!r}')

        started = perf_counter()
        preferences = main.open_preferences()
        app.processEvents()
        settings_ms = (perf_counter() - started) * 1000.0
        results['INTERACTION_MS'] = {'settings_open': settings_ms}
        if settings_ms >= INTERACTION_MS:
            raise AssertionError(f'Settings open {settings_ms:.1f}ms >= {INTERACTION_MS:.0f}ms')
        if not isinstance(preferences, PreferencesView):
            raise AssertionError('Settings did not open as PreferencesView')
        if main.editor_tabs.currentWidget() is not preferences:
            raise AssertionError('Settings editor tab is not current')
        preferences.grab().save(str(output / '01_settings_one_dark_pro.png'))

        # Exercise every StudioSelect in Settings for clipping.
        selects = preferences.findChildren(StudioSelect)
        if not selects:
            raise AssertionError('no Settings StudioSelect controls found')
        clipped = []
        for select in selects:
            select.adjustSize()
            app.processEvents()
            if select.height() < select.button.minimumSizeHint().height():
                clipped.append(select.objectName() or repr(select))
            if not select.visibleRegion().boundingRect().contains(select.rect()):
                clipped.append((select.objectName() or repr(select)) + ':visibleRegion')
        if clipped:
            raise AssertionError(f'VISIBLE_REGION_COVERS_CONTROL failed: {clipped}')
        results['VISIBLE_REGION_COVERS_CONTROL'] = True

        combo = StudioSelect()
        combo.addItems(['Auto', 'On', 'Off'])
        combo.resize(220, 36)
        combo.show()
        app.processEvents()
        QTest.mouseClick(combo.button, Qt.LeftButton)
        if not combo.popup.isVisible():
            raise AssertionError('first anchor click did not open popup')
        QTest.mouseClick(combo.button, Qt.LeftButton)
        QTest.qWait(100)
        if combo.popup.isVisible():
            raise AssertionError('SECOND_CLICK_STAYS_CLOSED failed')
        results['SECOND_CLICK_STAYS_CLOSED'] = True

        # A programmatic outside-close models native Qt.Popup closing on a blank
        # location; it must not suppress the next independent anchor click.
        combo.showPopup(); app.processEvents()
        combo.hidePopup('outside_click'); app.processEvents()
        combo._popup_state.release_anchor_suppression()
        QTest.mouseClick(combo.button, Qt.LeftButton)
        if not combo.popup.isVisible():
            raise AssertionError('OUTSIDE_CLICK_REOPENS_NEXT failed')
        results['OUTSIDE_CLICK_REOPENS_NEXT'] = True
        combo.hidePopup()

        (output / 'v104_ux_stability.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f"PASS: V10.4 Windows UX gate startup={startup_ms:.1f}ms settings={settings_ms:.1f}ms")
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if combo is not None:
            combo.hidePopup(); combo.close()
        if main is not None:
            main.session.document.dirty = False
            main.close()
        app.processEvents()


def main() -> int:
    if os.name != 'nt':
        print('SKIP: V10.4 UX Stability Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-v104-') as td:
        env = os.environ.copy()
        env['LOCALAPPDATA'] = td
        env['QT_QPA_PLATFORM'] = 'windows'
        env['MONOOLED_REDUCED_MOTION'] = '1'
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', str(OUT)], cwd=ROOT, env=env, check=False)
        return int(proc.returncode)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--child':
        raise SystemExit(_child(Path(sys.argv[2]).resolve()))
    raise SystemExit(main())
