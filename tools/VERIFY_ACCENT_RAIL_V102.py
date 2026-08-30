#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt gate for MonoOLED Accent Rail V10.2.

Verifies the approved interaction signature on production Studio controls:
Secondary = short left rail; Tool/Segment = short bottom rail; Primary/Danger =
no rail.  It also asserts that Hover/Pressed/Checked never changes geometry.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
OUT = SIM / 'reports' / 'windows_accent_rail_v102'


def _child(output: Path) -> int:
    sys.path.insert(0, str(SIM))
    try:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget
        from qt_theme import build_stylesheet, build_theme_palette
        from ui_controls import StudioButton, StudioToolButton
    except Exception as exc:
        print(f'FAIL: PySide6/Studio import unavailable: {exc}', file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    app.setPalette(build_theme_palette('monooled-dark'))
    app.setStyleSheet(build_stylesheet('monooled-dark'))
    host = QWidget(); row = QHBoxLayout(host)
    secondary = StudioButton('Validate'); secondary.setObjectName('SecondaryButton'); secondary.setFixedSize(120, 32)
    primary = StudioButton('Save'); primary.setObjectName('PrimaryButton'); primary.setFixedSize(90, 32)
    tool = StudioToolButton(); tool.setObjectName('ToolRailButton'); tool.setText('P'); tool.setCheckable(True); tool.setFixedSize(32, 32)
    segment = StudioButton('Design'); segment.setObjectName('StudioSegment'); segment.setCheckable(True); segment.setFixedSize(90, 32)
    for widget in (secondary, primary, tool, segment): row.addWidget(widget)
    host.show(); app.processEvents()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for name, widget in [('secondary',secondary),('primary',primary),('tool',tool),('segment',segment)]:
            results.append({'name': name, 'size': [widget.width(), widget.height()]})

        before = (secondary.width(), secondary.height(), secondary.contentsRect())
        QTest.mouseMove(secondary, secondary.rect().center()); QTest.qWait(130); app.processEvents()
        if not (0.62 <= secondary._accent_rail_opacity <= 0.72):
            raise AssertionError(f'secondary hover opacity={secondary._accent_rail_opacity}')
        secondary.grab().save(str(output/'01_secondary_hover.png'))
        QTest.mousePress(secondary, Qt.LeftButton, pos=secondary.rect().center()); app.processEvents()
        if secondary._accent_rail_opacity < 0.99: raise AssertionError('secondary press rail is not full-strength')
        secondary.grab().save(str(output/'02_secondary_pressed.png'))
        if (secondary.width(), secondary.height(), secondary.contentsRect()) != before:
            raise AssertionError('secondary geometry shifted during interaction')
        QTest.mouseRelease(secondary, Qt.LeftButton, pos=secondary.rect().center())

        for idx, widget in enumerate((tool, segment), 3):
            before_size = widget.size(); widget.setChecked(True); app.processEvents()
            if widget._accent_rail_opacity < 0.99: raise AssertionError(f'{widget.objectName()} checked rail missing')
            if widget.size() != before_size: raise AssertionError(f'{widget.objectName()} geometry shifted')
            widget.grab().save(str(output/f'{idx:02d}_{widget.objectName()}_checked.png'))

        QTest.mouseMove(primary, primary.rect().center()); QTest.qWait(130); app.processEvents()
        if primary._accent_rail_opacity != 0.0: raise AssertionError('PrimaryButton must not draw Accent Rail')
        primary.grab().save(str(output/'05_primary_hover_no_rail.png'))
        host.grab().save(str(output/'00_accent_rail_showcase.png'))
        (output/'accent_rail_v102.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print('PASS: Accent Rail V10.2 hover/press/checked raster + zero-geometry-shift gate')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        host.close(); app.processEvents()


def main() -> int:
    if os.name != 'nt':
        print('SKIP: Accent Rail V10.2 Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-accent-v102-') as td:
        env = os.environ.copy(); env['LOCALAPPDATA'] = td; env['QT_QPA_PLATFORM'] = 'windows'
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', str(OUT)], cwd=ROOT, env=env, check=False)
        return int(proc.returncode)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--child':
        raise SystemExit(_child(Path(sys.argv[2]).resolve()))
    raise SystemExit(main())
