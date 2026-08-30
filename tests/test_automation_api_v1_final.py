from pathlib import Path
import json
import zipfile

import pytest
from PIL import Image

from automation_service import StudioAutomationService
from project_workspace import create_project, ProjectWorkspace
from scene import load_scene
from support import load_curing_scene, CURING_SCENE


def _service_for_project(tmp_path):
    project=create_project(tmp_path/'demo',name='AI Demo',canvas=(32,16))
    scene=load_scene(project.screen_path('main'),project_root=project.root)
    scene['_project_path']=str(project.path)
    scene['_asset_dirs']=list(project.asset_dirs)
    scene['_design_rules']={}
    return project, StudioAutomationService(scene,source_path=project.screen_path('main'),permission='full',copy_scene=False,project_workspace=project)


def test_capabilities_and_machine_readable_contract_are_self_describing(tmp_path):
    project,svc=_service_for_project(tmp_path)
    caps=svc.call('automation.capabilities',{})
    assert caps['api_version'].startswith('1.')
    required={'project.open_screen','project.create_screen','state.enumerate','render.all_states','validate.all_states','pixel.create','asset.import','export.code_ai_handoff'}
    assert required <= {m['method'] for m in caps['methods']}
    desc=svc.call('automation.describe_method',{'method':'project.open_screen'})
    assert desc['method']['permission']=='edit' and desc['method']['params']
    contract=svc.call('project.get_contract',{})
    assert contract['coordinate_contract']['origin']=='top-left'
    assert contract['framebuffer_contract']['layout']=='VLSB page-major'
    schema=svc.call('scene.get_schema',{})
    assert 'bitmap_text' in schema['schema']['element_types']
    state_schema=svc.call('state.get_schema',{})
    assert state_schema['states']=={}


def test_project_screen_crud_and_open_switches_current_scene(tmp_path):
    project,svc=_service_for_project(tmp_path)
    made=svc.call('project.create_screen',{'screen_id':'running','label':'Running','open':True})
    assert made['active_screen']=='running'
    assert svc.source_path==project.screen_path('running')
    svc.call('scene.create_element',{'element':{'id':'x','type':'placeholder','x':1,'y':1,'w':2,'h':2,'draft':True,'allow_draft_export':True}})
    svc.call('project.save',{})
    dup=svc.call('project.duplicate_screen',{'screen_id':'running','new_id':'running_copy','label':'Copy'})
    assert dup['screen_id']=='running_copy'
    renamed=svc.call('project.rename_screen',{'screen_id':'running_copy','new_id':'review','label':'Review'})
    assert renamed['screen_id']=='review'
    opened=svc.call('project.open_screen',{'screen_id':'review'})
    assert opened['active_screen']=='review'
    assert any(e['id']=='x' for e in svc.call('scene.list_elements',{})['elements'])
    deleted=svc.call('project.delete_screen',{'screen_id':'running'})
    assert deleted['deleted_screen']=='running'
    assert {x['id'] for x in svc.call('project.list_screens',{})['screens']}=={'main','review'}
    # Manifest remains reopenable after the full lifecycle.
    reopened=ProjectWorkspace.load(project.path)
    assert {s.id for s in reopened.screens}=={'main','review'}


def test_representative_state_enumeration_matches_clinical_560_contract(tmp_path):
    scene=load_curing_scene()
    svc=StudioAutomationService(scene,source_path=CURING_SCENE,permission='observe')
    states=svc.call('state.enumerate',{'integer_policy':'representative','include_states':True})
    assert states['cases']==560
    assert len(states['states'])==560
    rendered=svc.call('render.all_states',{'integer_policy':'representative'})
    assert rendered['cases']==560 and rendered['framebuffer_bytes']==512
    assert len(rendered['frames'])==560
    validation=svc.call('validate.all_states',{'integer_policy':'representative'})
    assert validation['cases']==560 and validation['blockers']==0


def test_asset_and_pixel_lifecycle_can_create_import_copy_rename_delete(tmp_path):
    project,svc=_service_for_project(tmp_path)
    made=svc.call('pixel.create',{'path':'assets/new_icon.png','width':8,'height':8})
    did=made['document_id']
    svc.call('pixel.paint',{'document_id':did,'x':2,'y':3,'value':1})
    svc.call('pixel.save',{'document_id':did})
    assert (project.root/'assets/new_icon.png').exists()
    copied=svc.call('asset.copy',{'path':'assets/new_icon.png','target':'assets/new_icon_copy.png'})
    assert copied['sha256']
    renamed=svc.call('asset.rename',{'path':'assets/new_icon_copy.png','target':'assets/renamed.png'})
    assert renamed['path']=='assets/renamed.png'
    external=tmp_path/'external.png'; Image.new('1',(4,8),1).save(external)
    imported=svc.call('asset.import',{'source':str(external),'target':'assets/imported.png'})
    assert imported['path']=='assets/imported.png'
    listing=svc.call('project.list_assets',{})['assets']
    assert {'assets/new_icon.png','assets/renamed.png','assets/imported.png'} <= set(listing)
    svc.call('asset.delete',{'path':'assets/renamed.png'})
    assert not (project.root/'assets/renamed.png').exists()


def test_preview_and_export_surfaces_use_studio_truth(tmp_path):
    project,svc=_service_for_project(tmp_path)
    preview=svc.call('render.preview_file',{'path':'.oled/agent/preview/current.png'})
    assert Path(preview['path']).exists() and preview['sha256']
    annotated=svc.call('render.annotated_preview',{'path':'.oled/agent/preview/annotated.png','scale':4})
    assert Path(annotated['path']).exists() and annotated['sha256']
    current=svc.call('export.current',{'output_dir':'exports/current'})
    assert current['frame_count']==1 and (project.root/'exports/current/golden/current.bin').exists()
    all_export=svc.call('export.all',{'output_dir':'exports/all','integer_policy':'representative'})
    assert all_export['frame_count']==1  # empty-state blank project has one case
    header=svc.call('export.c_header',{'path':'exports/current.h','symbol':'ai_current'})
    assert Path(header['path']).exists()
    handoff=svc.call('export.code_ai_handoff',{'path':'exports/ai_handoff.zip','integer_policy':'representative'})
    hp=Path(handoff['path']); assert hp.exists()
    with zipfile.ZipFile(hp) as zf:
        names=set(zf.namelist())
        assert {'ui_contract.json','HANDOFF_README.md','validation_report.md'} <= names


def test_code_ai_project_graduation_flow(tmp_path):
    project,svc=_service_for_project(tmp_path)
    assert svc.call('automation.capabilities',{})['api_version'].startswith('1.')
    svc.call('project.create_screen',{'screen_id':'ortho_running','label':'ORTHO Running','open':True})
    icon=svc.call('pixel.create',{'path':'assets/cycle.png','width':8,'height':8})
    svc.call('pixel.line',{'document_id':icon['document_id'],'x0':0,'y0':0,'x1':7,'y1':7,'value':1})
    svc.call('pixel.save',{'document_id':icon['document_id']})
    tx=svc.begin_transaction(expected_revision=svc.revision)
    svc.call('scene.create_element',{'element':{'id':'cycle','type':'image','asset':'assets/cycle.png','x':2,'y':8}},transaction=tx)
    svc.commit_transaction(tx)
    rendered=svc.call('render.current',{})
    assert rendered['framebuffer']['bytes']==64 and rendered['framebuffer']['sha256']
    assert svc.call('validate.current',{})['blockers']==0
    svc.call('project.save_all',{})
    package=svc.call('export.code_ai_handoff',{'path':'exports/final_ai.zip'})
    assert Path(package['path']).exists()
    reopened=ProjectWorkspace.load(project.path)
    assert reopened.active_screen=='ortho_running'
    saved=json.loads(reopened.screen_path('ortho_running').read_text(encoding='utf-8'))
    assert any(e['id']=='cycle' for e in saved['elements'])
