from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from canvas_geometry import canvas_widget_size, fit_integer_zoom


def test_canvas_widget_size_uses_dynamic_dimensions():
    assert canvas_widget_size(256, 64, 4, margin=18) == (1060, 292)


def test_fit_integer_zoom_keeps_entire_canvas_visible():
    zoom = fit_integer_zoom(256, 64, viewport_w=1100, viewport_h=420, margin=18, min_zoom=1, max_zoom=16)
    assert zoom == 4


def test_fit_integer_zoom_handles_small_viewport_without_zero_zoom():
    assert fit_integer_zoom(512, 128, viewport_w=320, viewport_h=200, margin=18, min_zoom=1, max_zoom=16) == 1
