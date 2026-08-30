import copy
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from scene import load_scene, init_state
from validate import has_blockers, validate_scene
from support import load_curing_scene


def codes(findings):
    return {f.code for f in findings}


def test_current_main_scene_has_no_blockers():
    scene = load_scene()
    findings = validate_scene(scene, init_state(scene))
    assert not has_blockers(findings), [f'{f.severity}:{f.code}:{f.message}' for f in findings]


def test_out_of_bounds_element_is_blocker():
    scene = copy.deepcopy(load_scene())
    scene['elements'][0]['x'] = 125
    findings = validate_scene(scene, init_state(scene))
    assert 'OUT_OF_BOUNDS' in codes(findings)
    assert has_blockers(findings)


def test_missing_asset_is_blocker():
    scene = copy.deepcopy(load_curing_scene())
    mode_icon = next(e for e in scene['elements'] if e['id'] == 'mode_icon')
    mode_icon['asset'] = 'does-not-exist.png'
    findings = validate_scene(scene, init_state(scene))
    assert 'ASSET_NOT_FOUND' in codes(findings)


def test_native_size_mismatch_is_blocker():
    scene = copy.deepcopy(load_curing_scene())
    mode_icon = next(e for e in scene['elements'] if e['id'] == 'mode_icon')
    mode_icon['w'] = 23
    findings = validate_scene(scene, init_state(scene))
    assert 'ASSET_SIZE_MISMATCH' in codes(findings)


def test_placeholder_blocks_production_export_until_resource_is_resolved():
    import copy
    from scene import load_scene, init_state
    from validate import validate_scene

    scene = copy.deepcopy(load_scene())
    scene['elements'].append({
        'id': 'future_icon', 'type': 'placeholder',
        'x': 10, 'y': 5, 'w': 20, 'h': 8,
        'label': 'future asset'
    })
    findings = validate_scene(scene, init_state(scene))
    assert any(f.code == 'DRAFT_PLACEHOLDER' and f.severity == 'BLOCKER' for f in findings)
