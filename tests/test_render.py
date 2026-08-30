from support import load_curing_scene
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from scene import load_scene, init_state
from render import render_scene


def _by_id(result, element_id):
    return next(e for e in result.resolved_elements if e['id'] == element_id)


def test_normal_standby_resolves_mode_icon_and_hides_running_icon():
    scene = load_curing_scene()
    state = init_state(scene)
    state.update(mode='NORMAL', phase='standby', seconds=10, battery=4)
    result = render_scene(scene, state)

    mode_icon = _by_id(result, 'mode_icon')
    running = _by_id(result, 'running_icon')
    assert mode_icon['visible'] is True
    assert mode_icon['assets'][0].endswith('/normal.png')
    assert running['visible'] is False
    assert len(result.framebuffer.to_vlsb()) == 512


def test_normal_running_swaps_context_to_running_icon():
    scene = load_curing_scene()
    state = init_state(scene)
    state.update(mode='NORMAL', phase='running', seconds=10, battery=3)
    result = render_scene(scene, state)

    assert _by_id(result, 'mode_icon')['visible'] is False
    running = _by_id(result, 'running_icon')
    assert running['visible'] is True
    assert running['assets'][0].endswith('/running.png')


def test_hero_digits_render_bound_value_using_native_digit_assets():
    scene = load_curing_scene()
    state = init_state(scene)
    state.update(seconds=10)
    result = render_scene(scene, state)
    hero = _by_id(result, 'hero_digits')

    assert hero['text'] == '10'
    assert hero['x'] == 45
    assert hero['y'] == 3
    assert hero['w'] == 28  # 13 + 2 tracking + 13
    assert hero['h'] == 27
    assert hero['assets'][0].endswith('/assets/digits/13x27/digit_1.png')
    assert hero['assets'][1].endswith('/assets/digits/13x27/digit_0.png')


def test_render_is_byte_deterministic_for_same_scene_and_state():
    scene = load_curing_scene()
    state = init_state(scene)
    a = render_scene(scene, state).framebuffer.to_vlsb()
    b = render_scene(scene, dict(state)).framebuffer.to_vlsb()
    assert a == b


def test_placeholder_is_editor_visible_but_draws_no_production_pixels():
    import copy
    from scene import load_scene, init_state
    from render import render_scene

    scene = copy.deepcopy(load_curing_scene())
    scene['elements'] = [{
        'id': 'future_icon', 'type': 'placeholder',
        'x': 10, 'y': 5, 'w': 20, 'h': 8,
        'label': 'future asset'
    }]
    result = render_scene(scene, init_state(scene))
    assert result.framebuffer.to_vlsb() == bytes(512)
    item = result.resolved_elements[0]
    assert item['id'] == 'future_icon'
    assert item['placeholder'] is True
    assert item['rendered'] is False
    assert (item['x'], item['y'], item['w'], item['h']) == (10, 5, 20, 8)
