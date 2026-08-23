#!/usr/bin/env python3
from __future__ import annotations

import hashlib,itertools,json,random,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SIM=ROOT/'OLED模拟器';sys.path.insert(0,str(SIM))
from agent_bridge import dispatch_json_rpc
from automation_service import StudioAutomationService
from font_pack import create_font_pack,rasterize_characters
from pixel_studio import PixelDocument
from popup_geometry import Rect,Size,place_popup
from preference_delta import PreferenceDelta
from preferences import default_preferences,normalize_preferences
from presets import clinical_states
from qt_theme import build_stylesheet
from render import render_scene
from responsive_layout import plan_layout
from runtime_settings import RuntimeSettings
from scene import load_scene
from selection_model import SelectionModel
from theme_system import THEME_NAMES,resolve_theme_name


def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def verify_frozen():
    a=json.loads((SIM/'reports/frozen_product_assets_v70.json').read_text(encoding='utf-8'));g=json.loads((SIM/'reports/frozen_golden_v70.json').read_text(encoding='utf-8'));bad=[]
    for rel,d in a['files'].items():
        p=ROOT/rel
        if not p.is_file() or sha(p)!=d:bad.append(rel)
    gb=[];gd=SIM/'exports/clinical_14/golden'
    for name,d in g['files'].items():
        p=gd/name
        if not p.is_file() or p.stat().st_size!=g['bytes_each'] or sha(p)!=d:gb.append(name)
    if bad or gb:raise AssertionError(f'frozen drift: assets={bad[:4]} goldens={gb[:4]}')
    return {'production_assets':len(a['files']),'goldens':len(g['files']),'golden_bytes_each':g['bytes_each']}

def fuzz_preferences(n=1000):
    rng=random.Random(0x810);weird=[None,True,False,-10,0,1,999999,3.14,'','future','999%',[],{},['x'],{'x':1}]
    paths=[('schema_version',),('language',),('appearance','theme_mode'),('appearance','color_theme'),('appearance','density'),('appearance','ui_scale'),('input','middle_drag'),('canvas','snap'),('pixel_studio','brush_size'),('autosave','interval_minutes'),('performance','asset_cache_mb'),('shortcuts','project.save')]
    for _ in range(n):
        raw={}
        for path in rng.sample(paths,k=rng.randint(1,min(7,len(paths)))):
            node=raw
            for part in path[:-1]:
                if not isinstance(node.get(part),dict):node[part]={}
                node=node[part]
            node[path[-1]]=rng.choice(weird)
        r=RuntimeSettings.from_preferences(normalize_preferences(raw));assert r.language in {'zh_CN','en_US'} and 1<=r.brush_size<=8
    return {'iterations':n}

def appearance_matrix():
    modes=('system','light','dark');langs=('zh_CN','en_US');dens=('compact','comfortable','spacious');scales=('auto','90%','100%','110%','125%','150%');count=0
    for theme,mode,lang,density,scale in itertools.product(THEME_NAMES,modes,langs,dens,scales):
        p=default_preferences();p['language']=lang;p['appearance'].update(theme_mode=mode,color_theme=theme,density=density,ui_scale=scale);r=RuntimeSettings.from_preferences(p);resolved=resolve_theme_name(r.color_theme,r.theme_mode,system_dark=False);css=build_stylesheet(resolved,r.density,r.ui_scale);assert 'StudioSelectPopup' in css;count+=1
    assert count==432;return {'combinations':count}

def preference_transitions(n=10000):
    rng=random.Random(0x811);themes=tuple(THEME_NAMES);modes=('system','light','dark');langs=('zh_CN','en_US');dens=('compact','comfortable','spacious');scales=('auto','90%','100%','110%','125%','150%')
    p=default_preferences();prev=RuntimeSettings.from_preferences(p);effects={}
    for _ in range(n):
        q=default_preferences();q['language']=rng.choice(langs);q['appearance'].update(theme_mode=rng.choice(modes),color_theme=rng.choice(themes),density=rng.choice(dens),ui_scale=rng.choice(scales));cur=RuntimeSettings.from_preferences(q);d=PreferenceDelta.between(prev,cur);assert not d.requires_product_render
        for e in d.effects:effects[e]=effects.get(e,0)+1
        prev=cur
    return {'iterations':n,'effect_counts':effects}

def popup_fuzz(n=20000):
    rng=random.Random(0x812)
    for _ in range(n):
        sx=rng.randint(-5000,2500);sy=rng.randint(-2000,2000);sw=rng.randint(320,5120);sh=rng.randint(240,2880);screen=Rect(sx,sy,sw,sh);anchor=Rect(rng.randint(sx-600,sx+sw+600),rng.randint(sy-600,sy+sh+600),rng.randint(30,900),rng.randint(20,100));desired=Size(rng.randint(40,1600),rng.randint(40,3000));r=place_popup(anchor,desired,screen,margin=4);assert r.x>=screen.x+4 and r.y>=screen.y+4 and r.right<=screen.right-4 and r.bottom<=screen.bottom-4
    return {'cases':n}

def responsive_matrix():
    sizes=((900,620),(1024,768),(1280,720),(1366,768),(1440,900),(1920,1080),(2560,1440),(3840,2160));count=0
    for (w,h),d,s in itertools.product(sizes,('compact','comfortable','spacious'),(.9,1.0,1.1,1.25,1.5)):
        p=plan_layout(w,h,d,s);assert p.left_width>0 and p.inspector_width>0 and p.canvas_width>=300 and p.diagnostics_height>=140;count+=1
    return {'cases':count}

def selection_stress(n=10000):
    rng=random.Random(0x813);ids=[f'e{i}' for i in range(32)];m=SelectionModel()
    for _ in range(n):
        eid=rng.choice(ids);op=rng.randrange(4)
        if op==0:m.toggle(eid)
        elif op==1:m.add(eid)
        elif op==2:m.remove(eid)
        else:m.replace(rng.sample(ids,k=rng.randrange(0,9)))
        assert len(m.ids)==len(set(m.ids)) and (m.primary_id is None or m.primary_id in m.ids)
    return {'iterations':n}

def pixel_stress(documents=60,operations=500):
    rng=random.Random(0x814);total=0
    for _ in range(documents):
        d=PixelDocument(rng.choice([16,32,64]),rng.choice([8,16,32]),max_undo=64)
        for __ in range(operations):
            w,h=d.width,d.height;x0=rng.randrange(w);y0=rng.randrange(h);x1=rng.randrange(w);y1=rng.randrange(h);v=rng.randrange(2);op=rng.randrange(12)
            if op==0:d.pencil(x0,y0,v)
            elif op==1:d.line(x0,y0,x1,y1,v)
            elif op==2:d.rectangle(x0,y0,x1,y1,filled=False,value=v)
            elif op==3:d.rectangle(x0,y0,x1,y1,filled=True,value=v)
            elif op==4:d.flood_fill(x0,y0,v)
            elif op==5:d.brush(x0,y0,v,size=rng.randint(1,4))
            elif op==6:d.begin_gesture();d.brush_segment(x0,y0,x1,y1,v,size=rng.randint(1,3));d.end_gesture()
            elif op==7:d.undo()
            elif op==8:d.redo()
            elif op==9:d.rotate180()
            elif op==10:d.flip_horizontal()
            else:d.resize_canvas(rng.choice([16,32,64]),rng.choice([8,16,32]),anchor=rng.choice(['top-left','center','bottom-right']))
            assert all(x in (0,1) for row in d.pixels for x in row);assert len(d.to_vlsb())==d.width*(d.height//8);total+=1
    return {'documents':documents,'operations_total':total}

def font_determinism():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);hs=[]
        for n in ('a','b'):
            pack=create_font_pack(root/n,'StressFont',cell=(8,16),baseline=13,advance=9);rasterize_characters(pack,'ABCxyz0123/+',font_size=12,threshold=128);hs.append(hashlib.sha256((pack.root/'fontpack.json').read_bytes()+b''.join(p.read_bytes() for p in sorted((pack.root/'glyphs').glob('*.png')))).hexdigest())
        assert hs[0]==hs[1];return {'glyphs':12,'sha256':hs[0]}

def automation_stress(n=1000):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);sp=root/'scene.json';sp.write_text(json.dumps({'canvas':{'w':16,'h':8},'states':{},'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}]}),encoding='utf-8');svc=StudioAutomationService.for_scene(sp,permission='edit')
        for i in range(n):
            req={'jsonrpc':'2.0','id':i,'method':'scene.get' if i%5 else 'scene.update_element','params':{} if i%5 else {'id':'a','changes':{'x':i%14},'_expected_revision':svc.revision}};res=dispatch_json_rpc(svc,req);assert 'result' in res,res
        return {'calls':n,'final_revision':svc.revision}

def renderer_stress(cycles=100):
    scene=load_scene('main_scene');states=clinical_states(scene,seconds=10,battery=3);expected=scene['canvas']['w']*(scene['canvas']['h']//8);first={};ts=[];frames=0
    for cycle in range(cycles):
        for name,state in states.items():
            t=time.perf_counter();raw=render_scene(scene,state).framebuffer.to_vlsb();ts.append((time.perf_counter()-t)*1000);frames+=1;assert len(raw)==expected;d=hashlib.sha256(raw).hexdigest()
            if cycle==0:first[name]=d
            else:assert d==first[name]
    ordered=sorted(ts);return {'states':len(states),'cycles':cycles,'frames':frames,'bytes_each':expected,'deterministic_states':len(first),'avg_ms':sum(ts)/len(ts),'p95_ms':ordered[int(len(ordered)*.95)-1]}

def main():
    report={'version':'8.1.0','frozen':verify_frozen(),'preferences_fuzz':fuzz_preferences(),'appearance_matrix':appearance_matrix(),'preference_transitions':preference_transitions(),'popup_geometry_fuzz':popup_fuzz(),'responsive_matrix':responsive_matrix(),'selection_stress':selection_stress(),'pixel_stress':pixel_stress(),'font_determinism':font_determinism(),'automation_stress':automation_stress(),'renderer_stress':renderer_stress()}
    target=SIM/'reports/v81_stress_report.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
