import sys
from pathlib import Path
SIM=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SIM))
from editor_model import EditorSession

class Logger:
    def __init__(self): self.rows=[]
    def log(self,event,**payload): self.rows.append((event,payload))

def _scene():
    return {'_path':'/tmp/s.json','_root':'/tmp','canvas':{'w':32,'h':16},'storage':{'bytes_per_frame':64},'states':{},'timeline':[],
            'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2},{'id':'b','type':'placeholder','x':5,'y':1,'w':2,'h':2}]}

def test_batch_undo_redo_logs_without_assuming_element_id():
    logger=Logger(); editor=EditorSession(_scene(),logger=logger)
    editor.group_elements(['a','b'],group_id='g1')
    assert editor.undo() is True
    assert editor.redo() is True
    assert [e for e,_ in logger.rows if e in {'UNDO','REDO'}] == ['UNDO','REDO']
