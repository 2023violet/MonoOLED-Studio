from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from editor_model import EditorSession
from selection_tools import align, distribute, measure, snap_positions


def _scene():
    return {
        '_path': '/tmp/scene.json', '_root': '/tmp',
        'canvas': {'w': 128, 'h': 32},
        'storage': {'layout': 'VLSB', 'polarity': '1 = lit', 'bytes_per_frame': 512},
        'states': {}, 'timeline': [],
        'elements': [
            {'id':'a','type':'placeholder','x':3,'y':2,'w':5,'h':5},
            {'id':'b','type':'placeholder','x':20,'y':8,'w':7,'h':4},
            {'id':'c','type':'placeholder','x':50,'y':15,'w':6,'h':3},
        ]
    }


def test_align_and_measure_selected_elements():
    s = EditorSession(_scene())
    align(s, ['a','b','c'], 'left')
    assert [s.geometry(i).x for i in ['a','b','c']] == [3,3,3]
    m = measure(s, 'a', 'b')
    assert m.dx == 0
    assert m.vertical_gap == 1


def test_distribute_and_grid_snap():
    s = EditorSession(_scene())
    distribute(s, ['a','b','c'], 'horizontal')
    xs = [s.geometry(i).x for i in ['a','b','c']]
    assert xs[0] == 3 and xs[-1] == 50
    snap_positions(s, ['b'], grid=8)
    assert s.geometry('b').x % 8 == 0
    assert s.geometry('b').y % 8 == 0
