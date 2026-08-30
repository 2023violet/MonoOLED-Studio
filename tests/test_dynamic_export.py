from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from exporter import export_scene


def _scene(width=96, height=16):
    return {
        '_root': str(SIM.parent),
        'schema_version': 1,
        'product': 'dynamic monochrome test',
        'canvas': {'w': width, 'h': height, 'preview_scale': 6},
        'storage': {'layout': 'VLSB', 'polarity': '1 = lit', 'bytes_per_frame': width * (height // 8)},
        'states': {},
        'elements': [],
        'timeline': [],
    }


def test_export_scene_uses_dynamic_framebuffer_contract(tmp_path):
    summary = export_scene(_scene(), tmp_path, {'frame': {}})
    raw = (tmp_path / 'golden' / 'frame.bin').read_bytes()
    assert len(raw) == 192
    import json
    contract = json.loads((tmp_path / 'ui_contract.json').read_text(encoding='utf-8'))
    assert contract['framebuffer_contract']['width'] == 96
    assert contract['framebuffer_contract']['height'] == 16
    assert contract['framebuffer_contract']['bytes'] == 192
    assert contract['framebuffer_contract']['byte_offset'] == '(y // 8) * width + x'
