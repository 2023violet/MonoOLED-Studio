import sys
from pathlib import Path
SIM=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SIM))
from editor_model import EditorSession


def _scene():
 return {'_path':'/tmp/s.json','_root':'/tmp','canvas':{'w':32,'h':16},'storage':{'bytes_per_frame':64},'states':{},'timeline':[], 'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}]}


def test_add_elements_is_one_undoable_batch_and_rejects_duplicate_ids():
    e=EditorSession(_scene())
    e.add_elements([{'id':'b','type':'placeholder','x':4,'y':1,'w':2,'h':2},{'id':'c','type':'placeholder','x':7,'y':1,'w':2,'h':2}],label='template')
    assert [x['id'] for x in e.scene['elements']] == ['a','b','c']
    e.undo(); assert [x['id'] for x in e.scene['elements']] == ['a']
    e.redo(); assert [x['id'] for x in e.scene['elements']] == ['a','b','c']
    try: e.add_elements([{'id':'a','type':'placeholder','x':0,'y':0,'w':1,'h':1}])
    except ValueError as exc: assert 'duplicate' in str(exc)
    else: raise AssertionError('duplicate id must be rejected')
