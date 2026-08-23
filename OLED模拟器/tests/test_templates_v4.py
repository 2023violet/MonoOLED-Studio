from pathlib import Path
import sys

SIM=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SIM))
from component_templates import TemplateLibrary


def test_template_library_saves_and_instantiates_elements(tmp_path):
    lib=TemplateLibrary(tmp_path/'templates.json')
    elements=[{'id':'battery','type':'image','asset':'a.png','x':1,'y':2,'w':3,'h':4}, {'id':'icon','type':'image','asset':'b.png','x':8,'y':2,'w':3,'h':4}]
    lib.save_template('status', elements)
    made=lib.instantiate('status', prefix='copy_', offset=(10,5))
    assert [e['id'] for e in made]==['copy_battery','copy_icon']
    assert (made[0]['x'], made[0]['y'])==(11,7)
    loaded=TemplateLibrary(tmp_path/'templates.json')
    assert loaded.names()==['status']
