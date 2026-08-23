#!/usr/bin/env python3
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'OLED模拟器'
sys.path.insert(0,str(SIM)); sys.path.insert(0,str(ROOT/'Developer_Tools'))

import VERIFY_V82_STRESS as v82
from editor_model import EditorSession
from gui import _load_source
from selection_tools import smart_guides


def _bench(fn,n):
    samples=[]
    for _ in range(n):
        t=time.perf_counter_ns(); fn(); samples.append((time.perf_counter_ns()-t)/1e6)
    ordered=sorted(samples); return {'iterations':n,'avg_ms':statistics.mean(samples),'p95_ms':ordered[max(0,int(.95*n)-1)],'max_ms':max(samples)}


def duplicate_method_gate():
    dup=[]
    for path in SIM.glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for cls in (n for n in ast.walk(tree) if isinstance(n,ast.ClassDef)):
            seen={}
            for child in cls.body:
                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    if child.name in seen:dup.append({'file':path.name,'class':cls.name,'method':child.name,'first':seen[child.name],'second':child.lineno})
                    else:seen[child.name]=child.lineno
    assert not dup,dup
    return {'duplicates':0}


def interactive_hot_path():
    _project,scene=_load_source(str(ROOT/'CuringLite.project.oled.json'))
    session=EditorSession(scene); target='battery' if any(e.get('id')=='battery' for e in scene['elements']) else str(scene['elements'][0]['id'])
    for _ in range(10):session.render();session.geometry(target);smart_guides(session,target)
    result={'elements':len(scene['elements']),'render':_bench(session.render,200),'geometry':_bench(lambda:session.geometry(target),2000),'smart_guides':_bench(lambda:smart_guides(session,target),1000),'cache':vars(session.resources.stats)}
    # Wide safety budgets still prove the old N×full-render coupling is gone.
    assert result['geometry']['p95_ms'] < 0.50,result
    assert result['smart_guides']['p95_ms'] < 2.00,result
    assert result['render']['p95_ms'] < 6.00,result
    assert result['cache']['bitmap_hits']+result['cache']['font_hits']>0,result
    return result


def twenty_object_guides():
    scene={'_path':str(ROOT/'tmp_v83_scene.json'),'_root':str(ROOT),'canvas':{'w':256,'h':64},'states':{},'timeline':[],'elements':[]}
    for i in range(20):scene['elements'].append({'id':f'e{i}','type':'placeholder','x':(i%10)*20,'y':(i//10)*20,'w':8,'h':8})
    session=EditorSession(scene)
    result=_bench(lambda:smart_guides(session,'e0'),2000)
    assert result['p95_ms'] < 2.00,result
    return result


def batch_history_gate():
    scene={'_path':str(ROOT/'tmp_v83_history.json'),'_root':str(ROOT),'canvas':{'w':128,'h':32},'states':{},'timeline':[],'elements':[
        {'id':'a','type':'placeholder','x':1,'y':1,'w':4,'h':4},{'id':'b','type':'placeholder','x':10,'y':2,'w':4,'h':4},{'id':'c','type':'placeholder','x':20,'y':3,'w':4,'h':4}]}
    before=deepcopy(scene['elements']); s=EditorSession(scene)
    for _ in range(100):s.batch_move(['a','b','c'],1,0,coalesce=True)
    s.end_coalesced_edit(); assert len(s._undo)==1; assert s.undo(); assert scene['elements']==before
    return {'coalesced_moves':100,'undo_commands':1}


def launcher_contract():
    text=(SIM/'windows_launcher.c').read_text(encoding='utf-8')
    for token in ('MONOOLED_PYTHON','.venv-runtime','startup_smoke_ok','--startup-smoke','GUI startup validation failed'):
        assert token in text,token
    assert (ROOT/'Developer_Tools/CREATE_RUNTIME_ENV.bat').exists()
    return {'startup_validation':True,'runtime_bootstrap':True}


def main():
    report={
        'version':'8.3.0',
        'frozen':v82.v81.verify_frozen(),
        'duplicate_method_gate':duplicate_method_gate(),
        'interactive_hot_path':interactive_hot_path(),
        'twenty_object_guides':twenty_object_guides(),
        'batch_history_gate':batch_history_gate(),
        'launcher_contract':launcher_contract(),
    }
    target=SIM/'reports/v83_stress_report.json'; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__':raise SystemExit(main())
