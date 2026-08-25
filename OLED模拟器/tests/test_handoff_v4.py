from pathlib import Path
import sys, zipfile

SIM=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SIM))
from handoff import build_handoff_package


def test_handoff_package_contains_contract_validation_and_golden(tmp_path):
    scene={'_path':str(tmp_path/'scene.json'),'_root':str(tmp_path),'product':'Demo','canvas':{'w':16,'h':8},'storage':{'bytes_per_frame':16},'states':{},'elements':[],'timeline':[]}
    out=tmp_path/'handoff.zip'
    summary=build_handoff_package(scene,out,states={'main':{}})
    assert summary.frame_count==1 and out.exists()
    with zipfile.ZipFile(out) as z:
        names=set(z.namelist())
    assert {'UI_SPEC.md','ui_contract.json','validation_report.md','golden/main.bin','reference/main.png','HANDOFF_README.md','batch_validation.md'} <= names


def test_handoff_adds_thumbnail_c_header_and_design_rule_report(tmp_path):
    scene={'_path':str(tmp_path/'scene.json'),'_root':str(tmp_path),'product':'Demo','canvas':{'w':16,'h':8},'storage':{'bytes_per_frame':16},'states':{},'elements':[], 'timeline':[], '_design_rules':{'required_elements':['hero']}}
    out=tmp_path/'handoff_plus.zip'
    build_handoff_package(scene,out,states={'main':{}})
    with zipfile.ZipFile(out) as z:
        names=set(z.namelist())
        report=z.read('design_rules.md').decode('utf-8')
    assert 'thumbnail_wall.png' in names
    assert 'c_headers/main.h' in names
    assert 'design_rules.md' in names
    assert 'REQUIRED_ELEMENT_MISSING' in report
