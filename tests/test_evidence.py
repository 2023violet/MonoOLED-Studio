from support import load_curing_scene
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from evidence import frame_evidence
from render import render_scene
from scene import init_state, load_scene


def test_frame_evidence_contains_hash_pixel_count_state_and_visible_geometry():
    scene = load_curing_scene()
    state = init_state(scene)
    result = render_scene(scene, state)
    payload = frame_evidence(result, state, elapsed=7)
    assert payload['elapsed'] == 7
    assert payload['framebuffer_bytes'] == 512
    assert len(payload['sha256']) == 64
    assert payload['lit_pixels'] > 0
    assert payload['state']['mode'] == 'NORMAL'
    visible_ids = {item['id'] for item in payload['visible_elements']}
    assert {'battery', 'hero_digits', 'mode_label', 'mode_icon'} <= visible_ids
    assert 'running_icon' not in visible_ids
    assert all(set(('id', 'x', 'y', 'w', 'h')) <= set(item) for item in payload['visible_elements'])
