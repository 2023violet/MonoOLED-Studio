from support import load_curing_scene
from itertools import product
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from render import render_scene
from scene import load_scene
from validate import validate_scene


def test_full_clinical_state_matrix_renders_without_blockers():
    scene = load_curing_scene()
    modes = scene['states']['mode']['values']
    phases = scene['states']['phase']['values']
    batteries = range(scene['states']['battery']['min'], scene['states']['battery']['max'] + 1)
    seconds_cases = (0, 1, 9, 10, 99, 100, 300, 999)
    checked = 0
    expected_bytes = scene['canvas']['w'] * (scene['canvas']['h'] // 8)
    for mode, phase, battery, seconds in product(modes, phases, batteries, seconds_cases):
        state = {'mode': mode, 'phase': phase, 'battery': battery, 'seconds': seconds}
        result = render_scene(scene, state)
        assert len(result.framebuffer.to_vlsb()) == expected_bytes
        findings = validate_scene(scene, state=state)
        assert not [f for f in findings if f.severity in {'ERROR', 'BLOCKER'}], (state, findings)
        checked += 1
    assert checked == 560
