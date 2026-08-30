#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt gate for V11.1 first-layout, chrome-state and hover responsiveness."""

import os
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'


def _child() -> int:
    sys.path.insert(0, str(SIM))
    try:
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from gui import OLEDDesignerWindow, WorkspaceMode
        from pixel_studio_qt import PixelStudioWindow
        from ui_metrics import build_ui_metrics
    except Exception as exc:
        print(f'FAIL: Real-Qt imports unavailable: {exc}', file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    window = None
    pixel = None
    try:
        window = OLEDDesignerWindow('main_scene', 'en_US')
        window.resize(1440, 900); window.show(); app.processEvents()

        # 1) Settings must be correct on the FIRST display, before any theme change.
        prefs = window.open_preferences(); app.processEvents()
        runtime = window._runtime_preferences
        metrics = build_ui_metrics(runtime.density, runtime.ui_scale)
        if prefs.nav.width() < metrics['nav_min']:
            raise AssertionError(f'SETTINGS_FIRST_LAYOUT navigation compressed: {prefs.nav.width()} < {metrics["nav_min"]}')
        for row in range(prefs.nav.count()):
            rect = prefs.nav.visualItemRect(prefs.nav.item(row))
            if rect.height() < max(20, metrics['row'] - 2):
                raise AssertionError(f'SETTINGS_FIRST_LAYOUT row {row} clipped: {rect.height()}')
        if prefs.layout_violations():
            raise AssertionError(f'SETTINGS_FIRST_LAYOUT violations: {prefs.layout_violations()}')
        if window.workspace_segment.currentIndex() != -1 or not window.header_settings.isChecked():
            raise AssertionError('SETTINGS_CHROME: Settings tab did not own header state')

        # 2) Generic Preview must not infer product-specific State/Timeline from raw scene data.
        generic = deepcopy(window.scene)
        generic['states'] = {'mode': {'type': 'enum', 'values': ['A', 'B'], 'init': 'A'}, 'battery': {'type': 'int', 'min': 0, 'max': 4, 'init': 4}}
        generic['timeline'] = [{'at': 1, 'set': {'mode': 'B'}}]
        generic.pop('preview', None)
        window._reset_session(generic); app.processEvents()
        if window.preview_capabilities != ('frame', 'validation'):
            raise AssertionError(f'GENERIC_PREVIEW leaked raw runtime semantics: {window.preview_capabilities}')
        if window.preview_state_section.isVisible() or window.preview_timeline_section.isVisible():
            raise AssertionError('GENERIC_PREVIEW showed State/Timeline without explicit capability opt-in')

        # Explicit project opt-in remains available for truly interactive previews.
        opted = deepcopy(generic); opted['preview'] = {'capabilities': ['state', 'timeline'], 'timeline': {'step': 1, 'unit': 'tick'}}
        window._reset_session(opted); app.processEvents()
        if 'state' not in window.preview_capabilities or 'timeline' not in window.preview_capabilities:
            raise AssertionError('GENERIC_PREVIEW explicit capability opt-in failed')

        # 3) Context bar shows only usable selection actions. No dead Pixel duplicate entry.
        window.set_workspace_mode(WorkspaceMode.DESIGN); app.processEvents()
        window._set_selection([], source='api'); app.processEvents()
        if window.context_bar.isVisible():
            raise AssertionError('CONTEXT_ACTIONS: empty selection still shows dead controls')
        first = next((str(e.get('id')) for e in window.scene.get('elements', []) if e.get('id')), None)
        if first:
            window._set_selection([first], source='api', primary=first); app.processEvents()
            if not window.context_bar.isVisible() or not window.context_duplicate.isVisible() or not window.context_lock.isVisible():
                raise AssertionError('CONTEXT_ACTIONS: usable actions did not appear for selection')
        if hasattr(window, 'context_pixel'):
            raise AssertionError('CONTEXT_ACTIONS: redundant Canvas Pixel Studio action still exists')

        # 4) Pixel hover must reuse cached base raster and follow the pointer without full-canvas rebuild.
        with tempfile.TemporaryDirectory(prefix='monooled-v111-pixel-') as td:
            png = Path(td) / 'probe.png'
            image = QImage(32, 16, QImage.Format_ARGB32); image.fill(QColor('black')); image.save(str(png))
            pixel = PixelStudioWindow(png, language='en_US', parent=window.editor_tabs, preferences=window.preferences, project_root=Path(td))
            window.editor_registry.open(pixel); pidx = window.editor_tabs.addTab(pixel, 'probe.png'); window.editor_tabs.setCurrentIndex(pidx); app.processEvents()
            canvas = pixel.canvas; canvas.zoom = 20; canvas._sync_size(); canvas.show(); app.processEvents(); canvas.grab(); app.processEvents()
            builds_before = canvas._base_cache_builds
            start = perf_counter()
            points = [QPoint((i % 24) * 20 + 10, ((i // 24) % 12) * 20 + 10) for i in range(120)]
            for point in points:
                QTest.mouseMove(canvas, point, delay=0)
            app.processEvents()
            elapsed_ms = (perf_counter() - start) * 1000.0
            if canvas._base_cache_builds != builds_before:
                raise AssertionError(f'PIXEL_HOVER rebuilt base raster {canvas._base_cache_builds-builds_before} time(s)')
            # Loose hardware-independent ceiling: this gate catches seconds-long lag, not benchmark noise.
            if elapsed_ms > 1200:
                raise AssertionError(f'PIXEL_HOVER 120 moves too slow: {elapsed_ms:.1f} ms')
            if window.workspace_segment.currentIndex() != 1 or window.header_settings.isChecked():
                raise AssertionError('PIXEL_CHROME: Pixel editor did not own header state')

            # 5) Closing Pixel returns to the underlying Settings tab and clears Pixel rail.
            settings_index = window.editor_tabs.indexOf(prefs)
            if settings_index < 0:
                raise AssertionError('SETTINGS_CHROME: Settings tab disappeared')
            # Put Settings immediately under Pixel so close semantics are deterministic.
            window.editor_tabs.setCurrentIndex(settings_index); window.editor_tabs.setCurrentIndex(pidx); app.processEvents()
            window._close_editor_tab(pidx); app.processEvents()
            if window.editor_tabs.currentWidget() is not prefs:
                raise AssertionError('EDITOR_CHROME: closing Pixel did not reveal Settings')
            if window.workspace_segment.currentIndex() != -1 or not window.header_settings.isChecked():
                raise AssertionError('EDITOR_CHROME: Pixel rail remained active after returning to Settings')
            pixel = None

        print('PASS: V11.1 first-layout + generic preview + context actions + Pixel hover + editor chrome')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if pixel is not None:
            try: pixel.close()
            except Exception: pass
        if window is not None:
            try:
                window.session.document.dirty = False; window.close()
            except Exception: pass
        app.processEvents()


def main() -> int:
    if os.name != 'nt':
        print('SKIP: V11.1 usability/stability Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-v111-') as td:
        env = os.environ.copy(); env['LOCALAPPDATA'] = td; env['QT_QPA_PLATFORM'] = 'windows'; env['MONOOLED_REDUCED_MOTION'] = '1'
        return subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'], cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--child':
        raise SystemExit(_child())
    raise SystemExit(main())
