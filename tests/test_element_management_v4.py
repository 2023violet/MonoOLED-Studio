from pathlib import Path
import sys

SIM=Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0,str(SIM))
from editor_model import EditorSession
from render import render_scene


def scene():
    return {'_path':'/tmp/s.json','_root':'/tmp','canvas':{'w':32,'h':16},'storage':{'bytes_per_frame':64},'states':{},'timeline':[],
            'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}, {'id':'b','type':'placeholder','x':4,'y':1,'w':2,'h':2}, {'id':'c','type':'placeholder','x':7,'y':1,'w':2,'h':2}]}


def test_lock_hide_group_and_z_order():
    s=EditorSession(scene())
    s.set_locked(['a'], True)
    assert s.document.element('a')['locked'] is True
    try:
        s.move('a',1,0)
    except ValueError as exc:
        assert 'locked' in str(exc)
    else:
        raise AssertionError('locked element moved')
    s.set_hidden(['b'], True)
    result=s.render()
    rb=next(x for x in result.resolved_elements if x['id']=='b')
    assert rb['visible'] is False
    gid=s.group_elements(['a','c'], group_id='g1')
    assert gid=='g1' and s.document.element('a')['group']=='g1' and s.document.element('c')['group']=='g1'
    s.bring_to_front(['a'])
    assert s.scene['elements'][-1]['id']=='a'
