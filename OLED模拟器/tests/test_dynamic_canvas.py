from copy import deepcopy
from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from framebuffer import FrameBuffer
from scene import load_scene
from validate import validate_scene


def _empty_scene(width, height):
    return {
        'schema_version': 1,
        'canvas': {'w': width, 'h': height, 'preview_scale': 6},
        'storage': {'layout': 'VLSB column-page', 'polarity': '1 = lit', 'bytes_per_frame': width * (height // 8)},
        'states': {},
        'elements': [],
        'timeline': [],
    }


def test_vlsb_framebuffer_supports_non_128x32_canvas():
    fb = FrameBuffer(96, 16)
    fb.set_pixel(95, 15)
    raw = fb.to_vlsb()
    assert len(raw) == 192
    assert raw[-1] == 0x80


def test_validator_accepts_dynamic_monochrome_canvas_size():
    findings = validate_scene(_empty_scene(96, 16), {})
    assert findings == []


def test_validator_rejects_vlsb_height_not_divisible_by_eight():
    findings = validate_scene(_empty_scene(96, 18), {})
    assert any(f.code == 'CANVAS_HEIGHT_NOT_PAGE_ALIGNED' and f.severity == 'BLOCKER' for f in findings)


def test_validator_detects_stale_bytes_per_frame_contract():
    scene = _empty_scene(128, 64)
    scene['storage']['bytes_per_frame'] = 512
    findings = validate_scene(scene, {})
    assert any(f.code == 'FRAMEBUFFER_SIZE_CONTRACT' for f in findings)
