from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from framebuffer import FrameBuffer
from pixel_diff import diff_framebuffers, save_diff_png


def test_pixel_diff_reports_changed_pixels_and_bbox(tmp_path):
    a = FrameBuffer(16, 8); b = FrameBuffer(16, 8)
    a.set_pixel(1, 1); b.set_pixel(1, 1); b.set_pixel(4, 3); b.set_pixel(7, 5)
    diff = diff_framebuffers(a, b)
    assert diff.changed_pixels == 2
    assert diff.bbox == (4, 3, 8, 6)
    assert diff.percent == 2 / 128 * 100
    out = tmp_path / 'diff.png'
    save_diff_png(diff, out, scale=4)
    assert out.exists() and out.stat().st_size > 0


def test_pixel_diff_rejects_different_sizes():
    try:
        diff_framebuffers(FrameBuffer(16,8), FrameBuffer(32,8))
    except ValueError as exc:
        assert 'same size' in str(exc)
    else:
        raise AssertionError('size mismatch must fail')
