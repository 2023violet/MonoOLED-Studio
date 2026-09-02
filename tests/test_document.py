from support import load_curing_scene
import copy
import json
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from document import SceneDocument
from scene import load_scene
from session_log import SessionLogger


def test_document_edits_nested_fields_moves_text_and_saves_atomically(tmp_path):
    scene = copy.deepcopy(load_curing_scene())
    target = tmp_path / 'main_scene.json'
    scene['_path'] = str(target)
    log_path = tmp_path / 'session.jsonl'
    logger = SessionLogger(log_path)
    doc = SceneDocument(scene, logger=logger)

    assert doc.element('mode_icon')['x'] == 94
    doc.set_field('mode_icon', 'x', 95)
    assert doc.element('mode_icon')['x'] == 95
    assert doc.dirty is True

    doc.set_field('mode_label', 'zone.x', 89)
    doc.move('mode_label', dx=1, dy=2)
    label = doc.element('mode_label')
    assert label['zone']['x'] == 90
    assert label['y'] == 6

    doc.save()
    assert doc.dirty is False
    saved = json.loads(target.read_text(encoding='utf-8'))
    assert saved['elements'][3]['x'] == 95
    assert next(e for e in saved['elements'] if e['id'] == 'mode_label')['zone']['x'] == 90
    assert '_path' not in saved
    assert not list(tmp_path.glob('*.tmp'))

    logger.close()
    log_text = log_path.read_text(encoding='utf-8')
    assert '"event": "EDIT"' in log_text
    assert '"element": "mode_icon"' in log_text
    assert '"before": 94' in log_text
    assert '"after": 95' in log_text


def test_document_move_keeps_text_zone_and_glyph_y_together():
    scene = copy.deepcopy(load_curing_scene())
    doc = SceneDocument(scene)
    label = doc.element('mode_label')
    assert label['zone']['y'] == 2
    assert label['y'] == 4
    doc.move('mode_label', dx=2, dy=3)
    assert label['zone']['x'] == 90
    assert label['zone']['y'] == 5
    assert label['y'] == 7


def test_document_id_index_avoids_rescanning_and_tracks_editor_structure():
    from editor_model import EditorSession

    class CountingElements(list):
        def __init__(self, *args):
            super().__init__(*args)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    scene = {
        'canvas': {'w': 8, 'h': 8},
        'storage': {'bytes_per_frame': 8},
        'states': {},
        'elements': CountingElements([{'id': 'first', 'type': 'placeholder', 'x': 0, 'y': 0, 'w': 1, 'h': 1}]),
        'timeline': [],
    }
    session = EditorSession(scene)
    elements = scene['elements']
    elements.iterations = 0

    assert session.document.element('first')['id'] == 'first'
    assert elements.iterations == 0

    session.add_placeholder('second', x=1, y=0, w=1, h=1)
    elements.iterations = 0
    assert session.document.element('second')['id'] == 'second'
    assert elements.iterations == 0

    assert session.undo()
    elements.iterations = 0
    try:
        session.document.element('second')
    except KeyError:
        pass
    else:
        raise AssertionError('removed element remained in the document index')
    assert elements.iterations == 0
