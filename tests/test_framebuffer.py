import importlib.util
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
SPEC = importlib.util.spec_from_file_location('oled_framebuffer', SIM / 'framebuffer.py')
fbmod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fbmod)
FrameBuffer = fbmod.FrameBuffer


def test_vlsb_maps_top_left_to_byte0_bit0():
    fb = FrameBuffer()
    fb.set_pixel(0, 0)
    out = fb.to_vlsb()
    assert len(out) == 512
    assert out[0] == 0x01
    assert sum(out[1:]) == 0


def test_vlsb_maps_bottom_right_to_byte511_bit7():
    fb = FrameBuffer()
    fb.set_pixel(127, 31)
    out = fb.to_vlsb()
    assert out[511] == 0x80
    assert sum(out[:511]) == 0


def test_or_mask_composes_without_clearing_existing_pixels():
    fb = FrameBuffer()
    fb.set_pixel(1, 1)
    fb.or_mask([[1, 0], [0, 1]], 0, 0)
    assert fb.get_pixel(0, 0) == 1
    assert fb.get_pixel(1, 1) == 1
    assert fb.get_pixel(1, 0) == 0
    assert fb.get_pixel(0, 1) == 0
