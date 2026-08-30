#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt gate for V11.2 Pixel Canvas truth + GitHub release hygiene."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'


def _child() -> int:
    sys.path.insert(0, str(SIM))
    try:
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        from pixel_studio import PixelDocument
        from pixel_studio_qt import PixelCanvas
    except Exception as exc:
        print(f'FAIL: Real-Qt imports unavailable: {exc}', file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication([])
    canvas = None
    try:
        for theme_name in ('monooled-light', 'one-dark-pro'):
            document = PixelDocument(2, 1)
            document.pixels[0][0] = 0
            document.pixels[0][1] = 1
            canvas = PixelCanvas(document)
            canvas.theme_name = theme_name
            canvas.show_grid = False
            canvas.zoom = 20
            canvas._sync_size()
            canvas.show(); app.processEvents()
            image = canvas.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
            off = image.pixelColor(10, 10)
            on = image.pixelColor(30, 10)
            if (off.red(), off.green(), off.blue()) != (0, 0, 0):
                raise AssertionError(f'{theme_name}: Pixel OFF raster is not black: {off.getRgb()}')
            if (on.red(), on.green(), on.blue()) != (255, 255, 255):
                raise AssertionError(f'{theme_name}: Pixel ON raster is not white: {on.getRgb()}')
            canvas.close(); canvas = None; app.processEvents()

        root_md = sorted(p.name for p in ROOT.glob('*.md'))
        if root_md != ['DELIVERY_README.md', 'README.md']:
            raise AssertionError(f'GitHub root markdown is not curated: {root_md}')
        for rel in ('.oled/logs', '.oled/autosave', '.oled/asset_cache_v1.json'):
            if (ROOT / rel).exists():
                raise AssertionError(f'Runtime artifact leaked into release tree: {rel}')

        print('PASS: V11.2 Pixel Canvas black/white truth + GitHub release hygiene')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if canvas is not None:
            try: canvas.close()
            except Exception: pass
        app.processEvents()


def main() -> int:
    if os.name != 'nt':
        print('SKIP: V11.2 Pixel/GitHub Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-v112-') as td:
        env = os.environ.copy()
        env['LOCALAPPDATA'] = td
        env['QT_QPA_PLATFORM'] = 'windows'
        env['MONOOLED_REDUCED_MOTION'] = '1'
        return subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'], cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--child':
        raise SystemExit(_child())
    raise SystemExit(main())
