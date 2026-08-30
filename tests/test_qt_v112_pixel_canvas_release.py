from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtGui import QImage

SIM = Path(__file__).resolve().parents[1] / 'src'
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))

from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas


def _rgb(image: QImage, x: int, y: int) -> tuple[int, int, int]:
    c = image.pixelColor(x, y)
    return c.red(), c.green(), c.blue()


@pytest.mark.parametrize('theme_name', ['monooled-light', 'one-dark-pro'])
def test_pixel_canvas_raster_keeps_oled_black_white_truth_across_themes(qtbot, theme_name):
    document = PixelDocument(2, 1)
    document.pixels[0][0] = 0
    document.pixels[0][1] = 1
    canvas = PixelCanvas(document)
    canvas.theme_name = theme_name
    canvas.show_grid = False
    canvas.zoom = 20
    canvas._sync_size()
    qtbot.addWidget(canvas)
    canvas.show()
    qtbot.waitExposed(canvas)

    image = canvas.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    assert _rgb(image, 10, 10) == (0, 0, 0)
    assert _rgb(image, 30, 10) == (255, 255, 255)
