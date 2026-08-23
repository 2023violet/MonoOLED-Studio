#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'OLED模拟器'
sys.path.insert(0,str(SIM))

from agent_bridge import dispatch_json_rpc
from automation_service import StudioAutomationService
from font_pack import create_font_pack, rasterize_characters
from pixel_studio import PixelDocument
from preferences import normalize_preferences
from presets import clinical_states
from render import render_scene
from runtime_settings import RuntimeSettings
from scene import load_scene
from selection_model import SelectionModel


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen() -> dict:
    manifest=json.loads((SIM/'reports/frozen_product_assets_v70.json').read_text(encoding='utf-8'))
    bad=[]
    for rel,expected in manifest['files'].items():
        p=ROOT/rel
        if not p.is_file():bad.append({'path':rel,'status':'missing'})
        elif sha(p)!=expected:bad.append({'path':rel,'status':'changed'})
    golden=json.loads((SIM/'reports/frozen_golden_v70.json').read_text(encoding='utf-8'))
    gbad=[];gdir=SIM/'exports/clinical_14/golden'
    for name,expected in golden['files'].items():
        p=gdir/name
        if not p.is_file():gbad.append({'path':name,'status':'missing'})
        elif p.stat().st_size!=golden['bytes_each'] or sha(p)!=expected:gbad.append({'path':name,'status':'changed'})
    if bad or gbad:raise AssertionError(f'frozen drift: assets={bad[:4]} goldens={gbad[:4]}')
    return {'production_assets':len(manifest['files']),'goldens':len(golden['files']),'golden_bytes_each':golden['bytes_each']}


def fuzz_preferences(iterations:int=1000)->dict:
    rng=random.Random(0x800)
    weird=[None,True,False,-10,0,1,999999,3.14,'','future','999%',[],{},['x'],{'x':1}]
    keys=[('schema_version',),('language',),('startup','reopen_last_project'),('appearance','theme_mode'),('appearance','color_theme'),('appearance','density'),('appearance','ui_scale'),('input','wheel_action'),('input','middle_drag'),('canvas','snap'),('pixel_studio','brush_size'),('autosave','interval_minutes'),('autosave','snapshots'),('performance','undo_history'),('performance','asset_cache_mb'),('shortcuts','project.save')]
    for _ in range(iterations):
        raw={}
        for path in rng.sample(keys,k=rng.randint(1,min(7,len(keys)))):
            node=raw
            for part in path[:-1]:
                if not isinstance(node.get(part),dict):node[part]={}
                node=node[part]
            node[path[-1]]=rng.choice(weird)
        p=normalize_preferences(raw);runtime=RuntimeSettings.from_preferences(p)
        assert runtime.language in {'zh_CN','en_US'} and runtime.density in {'compact','comfortable','spacious'}
        assert 1<=runtime.brush_size<=8 and 10<=runtime.undo_history<=2000 and 32<=runtime.asset_cache_mb<=4096
    return {'iterations':iterations}


def selection_stress(iterations:int=10000)->dict:
    rng=random.Random(0x801);ids=[f'e{i}' for i in range(32)];model=SelectionModel()
    for _ in range(iterations):
        op=rng.randrange(4);eid=rng.choice(ids)
        if op==0:model.toggle(eid)
        elif op==1:model.add(eid)
        elif op==2:model.remove(eid)
        else:model.replace(rng.sample(ids,k=rng.randrange(0,9)))
        assert len(model.ids)==len(set(model.ids))
        assert model.primary_id is None or model.primary_id in model.ids
    return {'iterations':iterations}


def pixel_stress(documents:int=60,operations:int=500)->dict:
    rng=random.Random(0x802);total=0
    for _ in range(documents):
        w=rng.choice([16,32,64]);h=rng.choice([8,16,32]);d=PixelDocument(w,h,max_undo=64)
        for __ in range(operations):
            w,h=d.width,d.height;op=rng.randrange(12);x0=rng.randrange(w);y0=rng.randrange(h);x1=rng.randrange(w);y1=rng.randrange(h);value=rng.randrange(2)
            if op==0:d.pencil(x0,y0,value)
            elif op==1:d.line(x0,y0,x1,y1,value)
            elif op==2:d.rectangle(x0,y0,x1,y1,filled=False,value=value)
            elif op==3:d.rectangle(x0,y0,x1,y1,filled=True,value=value)
            elif op==4:d.flood_fill(x0,y0,value)
            elif op==5:d.brush(x0,y0,value,size=rng.randint(1,4))
            elif op==6:d.begin_gesture();d.brush_segment(x0,y0,x1,y1,value,size=rng.randint(1,3));d.end_gesture()
            elif op==7:d.undo()
            elif op==8:d.redo()
            elif op==9:d.rotate180()
            elif op==10:d.flip_horizontal()
            else:
                nw=rng.choice([16,32,64]);nh=rng.choice([8,16,32]);d.resize_canvas(nw,nh,anchor=rng.choice(['top-left','center','bottom-right']))
            assert all(v in (0,1) for row in d.pixels for v in row)
            assert len(d.to_vlsb())==d.width*(d.height//8);total+=1
    return {'documents':documents,'operations_per_document':operations,'operations_total':total}


def font_determinism()->dict:
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);hashes=[]
        for name in ('a','b'):
            pack=create_font_pack(root/name,'StressFont',cell=(8,16),baseline=13,advance=9);rasterize_characters(pack,'ABCxyz0123/+',font_size=12,threshold=128)
            hashes.append(hashlib.sha256((pack.root/'fontpack.json').read_bytes()+b''.join(p.read_bytes() for p in sorted((pack.root/'glyphs').glob('*.png')))).hexdigest())
        assert hashes[0]==hashes[1]
        return {'glyphs':12,'deterministic':True,'sha256':hashes[0]}


def automation_stress(iterations:int=1000)->dict:
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);scene_path=root/'scene.json';scene_path.write_text(json.dumps({'canvas':{'w':16,'h':8},'states':{},'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}]}),encoding='utf-8')
        svc=StudioAutomationService.for_scene(scene_path,permission='edit')
        for i in range(iterations):
            req={'jsonrpc':'2.0','id':i,'method':'scene.get' if i%5 else 'scene.update_element','params':{} if i%5 else {'id':'a','changes':{'x':i%14},'_expected_revision':svc.revision}}
            response=dispatch_json_rpc(svc,req);assert 'result' in response,response
            if i%17==0:
                rendered=dispatch_json_rpc(svc,{'jsonrpc':'2.0','id':'r','method':'render.framebuffer','params':{}});assert rendered['result']['framebuffer']['bytes']==16
        return {'jsonrpc_calls':iterations,'final_revision':svc.revision}


def renderer_stress(cycles:int=100)->dict:
    scene=load_scene('main_scene');states=clinical_states(scene,seconds=10,battery=3);expected=scene['canvas']['w']*(scene['canvas']['h']//8);first={};frames=0;timings=[]
    for cycle in range(cycles):
        for name,state in states.items():
            start=time.perf_counter();raw=render_scene(scene,state).framebuffer.to_vlsb();timings.append((time.perf_counter()-start)*1000);frames+=1;assert len(raw)==expected;digest=hashlib.sha256(raw).hexdigest()
            if cycle==0:first[name]=digest
            else:assert digest==first[name],(cycle,name)
    ordered=sorted(timings)
    return {'states':len(states),'cycles':cycles,'frames':frames,'bytes_each':expected,'deterministic_states':len(first),'avg_ms':sum(timings)/len(timings),'p95_ms':ordered[int(len(ordered)*0.95)-1]}


def main()->int:
    report={'version':'8.0.0','frozen':verify_frozen(),'preferences_fuzz':fuzz_preferences(),'selection_stress':selection_stress(),'pixel_stress':pixel_stress(),'font_determinism':font_determinism(),'automation_stress':automation_stress(),'renderer_stress':renderer_stress()}
    target=SIM/'reports/v80_stress_report.json';target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(report,indent=2,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
