from support import load_curing_scene, CURING_ROOT
import copy
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from editor_model import EditorSession
from scene import load_scene
from session_log import SessionLogger


def test_text_geometry_uses_zone_and_geometry_edit_preserves_glyph_offset_with_undo_redo(tmp_path):
    scene = copy.deepcopy(load_curing_scene())
    logger = SessionLogger(tmp_path / 'editor.jsonl')
    editor = EditorSession(scene, logger=logger)

    geom = editor.geometry('mode_label')
    assert (geom.x, geom.y, geom.w, geom.h) == (88, 2, 36, 12)
    assert geom.editable == {'x': True, 'y': True, 'w': True, 'h': True}

    editor.set_geometry('mode_label', x=90, y=6, w=34, h=10)
    label = editor.document.element('mode_label')
    assert label['zone'] == {'x': 90, 'y': 6, 'w': 34, 'h': 10}
    assert label['y'] == 8  # original glyph offset was +2 from zone top
    assert editor.can_undo is True
    assert editor.can_redo is False

    editor.undo()
    label = editor.document.element('mode_label')
    assert label['zone'] == {'x': 88, 'y': 2, 'w': 36, 'h': 12}
    assert label['y'] == 4
    assert editor.can_redo is True

    editor.redo()
    label = editor.document.element('mode_label')
    assert label['zone'] == {'x': 90, 'y': 6, 'w': 34, 'h': 10}
    assert label['y'] == 8
    logger.close()


def test_image_move_is_single_undoable_command_and_runtime_state_renders(tmp_path):
    scene = copy.deepcopy(load_curing_scene())
    logger = SessionLogger(tmp_path / 'editor.jsonl')
    editor = EditorSession(scene, logger=logger)

    editor.move('mode_icon', dx=3, dy=-2)
    icon = editor.document.element('mode_icon')
    assert (icon['x'], icon['y']) == (97, 17)

    editor.undo()
    assert (icon['x'], icon['y']) == (94, 19)
    editor.redo()
    assert (icon['x'], icon['y']) == (97, 17)

    editor.set_state('phase', 'running')
    result = editor.render()
    visible = {item['id']: item['visible'] for item in result.resolved_elements}
    assert visible['mode_icon'] is False
    assert visible['running_icon'] is True

    findings = editor.validate()
    assert isinstance(findings, list)
    logger.close()


def test_digits_report_resolved_size_but_do_not_allow_direct_wh_edit(tmp_path):
    scene = copy.deepcopy(load_curing_scene())
    editor = EditorSession(scene)
    editor.set_state('seconds', 10)
    geom = editor.geometry('hero_digits')
    assert (geom.x, geom.y, geom.w, geom.h) == (45, 3, 28, 27)
    assert geom.editable == {'x': True, 'y': True, 'w': False, 'h': False}

    try:
        editor.set_geometry('hero_digits', w=30)
    except ValueError as exc:
        assert 'not editable' in str(exc)
    else:
        raise AssertionError('editing dynamic digit width must be rejected')


def test_drag_style_geometry_updates_can_coalesce_into_one_undo_step():
    import copy
    from scene import load_scene

    editor = EditorSession(copy.deepcopy(load_curing_scene()))
    editor.set_geometry('mode_icon', x=95)
    editor.set_geometry('mode_icon', x=96, coalesce=True)
    editor.set_geometry('mode_icon', x=97, coalesce=True)
    assert editor.document.element('mode_icon')['x'] == 97
    editor.undo()
    assert editor.document.element('mode_icon')['x'] == 94
    assert editor.can_undo is False


def test_placeholder_can_be_added_removed_and_undone():
    import copy
    from scene import load_scene

    editor = EditorSession(copy.deepcopy(load_curing_scene()))
    element_id = editor.add_placeholder('future_icon', x=12, y=6, w=20, h=8)
    assert element_id == 'future_icon'
    assert editor.document.element('future_icon')['type'] == 'placeholder'
    assert editor.geometry('future_icon').w == 20

    editor.undo()
    try:
        editor.document.element('future_icon')
    except KeyError:
        pass
    else:
        raise AssertionError('undo add should remove placeholder')

    editor.redo()
    assert editor.document.element('future_icon')['type'] == 'placeholder'
    editor.remove_element('future_icon')
    try:
        editor.document.element('future_icon')
    except KeyError:
        pass
    else:
        raise AssertionError('remove_element should remove selected element')
    editor.undo()
    assert editor.document.element('future_icon')['type'] == 'placeholder'


def test_placeholder_can_be_resolved_to_native_bitmap_and_undone():
    import copy
    from scene import load_scene, resolve

    editor = EditorSession(copy.deepcopy(load_curing_scene()))
    editor.add_placeholder('future_icon', x=12, y=6, w=20, h=8)
    asset = CURING_ROOT / 'assets/clinical_ui/normal.png'
    editor.assign_bitmap('future_icon', asset)
    item = editor.document.element('future_icon')
    assert item['type'] == 'image'
    assert item['w'] == 24 and item['h'] == 12
    assert item['x'] == 12 and item['y'] == 6
    assert item['asset'].endswith('/normal.png') or item['asset'].endswith('normal.png')
    editor.undo()
    assert editor.document.element('future_icon')['type'] == 'placeholder'
