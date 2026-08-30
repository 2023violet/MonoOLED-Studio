from pathlib import Path
import sys
SIM=Path(__file__).resolve().parents[1] / 'src'; sys.path.insert(0,str(SIM))
from editor_model import EditorSession


def _scene():
 return {'_path':'/tmp/s.json','_root':'/tmp','canvas':{'w':32,'h':16},'storage':{'bytes_per_frame':64},'states':{},'timeline':[], 'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}]}


def test_continuous_drag_coalesces_but_separate_drags_make_separate_undo_steps():
 s=EditorSession(_scene())
 s.move('a',1,0,coalesce=True); s.move('a',1,0,coalesce=True); s.end_coalesced_edit()
 assert s.geometry('a').x==3
 s.move('a',1,0,coalesce=True); s.end_coalesced_edit()
 assert s.geometry('a').x==4
 s.undo(); assert s.geometry('a').x==3
 s.undo(); assert s.geometry('a').x==1
