from pathlib import Path
import sys

SIM=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SIM))
from scene_diff import diff_scenes


def test_scene_diff_reports_added_removed_and_changed_fields():
    a={'elements':[{'id':'x','type':'placeholder','x':1,'y':2,'w':3,'h':4},{'id':'old','type':'placeholder','x':0,'y':0,'w':1,'h':1}]}
    b={'elements':[{'id':'x','type':'placeholder','x':5,'y':2,'w':3,'h':4},{'id':'new','type':'placeholder','x':0,'y':0,'w':1,'h':1}]}
    d=diff_scenes(a,b)
    assert d.added==('new',)
    assert d.removed==('old',)
    assert d.changed['x']['x']==(1,5)
