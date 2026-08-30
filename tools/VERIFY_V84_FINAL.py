#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'src'
sys.path.insert(0,str(SIM))

from agent_bridge import LocalAgentBridgeServer, dispatch_json_rpc
from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS, StudioAutomationService
from project_workspace import ProjectWorkspace, create_project
from scene import load_scene


def _svc(project: ProjectWorkspace) -> StudioAutomationService:
    path=project.screen_path(project.active_screen)
    scene=load_scene(path,project_root=project.root)
    scene['_project_path']=str(project.path); scene['_asset_dirs']=list(project.asset_dirs); scene['_design_rules']={}
    return StudioAutomationService(scene,source_path=path,permission='full',copy_scene=False,project_workspace=project)


def _rpc_line(sock, payload):
    sock.sendall((json.dumps(payload,separators=(',',':'))+'\n').encode())
    data=b''
    while not data.endswith(b'\n'):
        chunk=sock.recv(65536)
        if not chunk: raise RuntimeError('agent socket closed')
        data+=chunk
    return json.loads(data.decode())


def main()->int:
    report={'version':'8.4.0','automation_api':AUTOMATION_API_VERSION}
    assert AUTOMATION_API_VERSION.startswith('1.')
    contract=json.loads((SIM/'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    assert set(contract['methods'])==set(METHOD_SPECS)
    report['method_count']=len(METHOD_SPECS)

    # Canonical Curing-Lite state proof.
    clinical=StudioAutomationService.for_scene(SIM/'scenes/main_scene.json',permission='observe')
    states=clinical.call('state.enumerate',{'integer_policy':'representative','include_states':False})
    assert states['cases']==560,states
    rendered=clinical.call('render.all_states',{'integer_policy':'representative'})
    validated=clinical.call('validate.all_states',{'integer_policy':'representative'})
    assert rendered['cases']==560 and rendered['framebuffer_bytes']==512
    assert validated['cases']==560 and validated['blockers']==0
    report['clinical']={'states':560,'framebuffer_bytes':512,'blockers':0}

    with tempfile.TemporaryDirectory(prefix='monooled_v84_') as td:
        root=Path(td)
        project=create_project(root/'agent_project',name='Automation Graduation',canvas=(32,16))
        svc=_svc(project)
        caps=svc.call('automation.capabilities',{})
        assert caps['api_version'].startswith('1.')
        # Complete project lifecycle.
        svc.call('project.create_screen',{'screen_id':'agent','label':'Agent','open':True})
        icon=svc.call('pixel.create',{'path':'assets/agent_icon.png','width':8,'height':8})
        svc.call('pixel.line',{'document_id':icon['document_id'],'x0':0,'y0':0,'x1':7,'y1':7,'value':1})
        svc.call('pixel.save',{'document_id':icon['document_id']})
        tx=svc.begin_transaction(expected_revision=svc.revision)
        svc.call('scene.create_element',{'element':{'id':'agent_icon','type':'image','asset':'assets/agent_icon.png','x':2,'y':4}},transaction=tx)
        svc.commit_transaction(tx)
        assert svc.call('render.current',{})['framebuffer']['bytes']==64
        assert svc.call('validate.current',{})['blockers']==0
        svc.call('project.save_all',{})
        handoff=svc.call('export.code_ai_handoff',{'path':'exports/agent_handoff.zip'})
        assert Path(handoff['path']).is_file()
        assert ProjectWorkspace.load(project.path).active_screen=='agent'

        # Real localhost JSON-RPC transport proof, not just direct method calls.
        server=LocalAgentBridgeServer(lambda req:dispatch_json_rpc(svc,req),port=0,session_token='v84-token')
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            with socket.create_connection(('127.0.0.1',server.server_address[1]),timeout=5) as sock:
                bad=_rpc_line(sock,{'jsonrpc':'2.0','id':1,'method':'automation.capabilities','params':{},'token':'wrong'})
                assert 'error' in bad
            with socket.create_connection(('127.0.0.1',server.server_address[1]),timeout=5) as sock:
                ok=_rpc_line(sock,{'jsonrpc':'2.0','id':2,'method':'automation.capabilities','params':{},'token':'v84-token'})
                assert ok['result']['api_version'].startswith('1.')
                got=_rpc_line(sock,{'jsonrpc':'2.0','id':3,'method':'project.get','params':{},'token':'v84-token'})
                assert got['result']['active_screen']=='agent'
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()
        report['graduation']={'direct_project_flow':'PASS','localhost_json_rpc':'PASS','handoff':'PASS'}

    target=SIM/'reports/v84_final_report.json'; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
