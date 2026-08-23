from pathlib import Path
import json
import socket
import threading

from agent_bridge import LocalAgentBridgeServer, dispatch_json_rpc
from automation_service import StudioAutomationService
from project_workspace import create_project
from scene import load_scene


def rpc(file, token, rid, method, params=None):
    req={'jsonrpc':'2.0','id':rid,'method':method,'params':params or {},'token':token}
    file.write((json.dumps(req,ensure_ascii=False)+'\n').encode('utf-8')); file.flush()
    return json.loads(file.readline().decode('utf-8'))


def test_socket_agent_can_discover_create_switch_render_validate_save(tmp_path):
    project=create_project(tmp_path/'project',name='Socket AI',canvas=(32,16))
    scene=load_scene(project.screen_path('main'),project_root=project.root)
    scene['_project_path']=str(project.path);scene['_asset_dirs']=list(project.asset_dirs);scene['_design_rules']={}
    svc=StudioAutomationService(scene,source_path=project.screen_path('main'),permission='full',copy_scene=False,project_workspace=project)
    server=LocalAgentBridgeServer(lambda req:dispatch_json_rpc(svc,req),port=0,session_token='final-token')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with socket.create_connection(('127.0.0.1',server.server_address[1]),timeout=3) as sock:
            f=sock.makefile('rwb')
            caps=rpc(f,'final-token',1,'automation.capabilities')['result']
            assert caps['api_version']=='1.0.0'
            made=rpc(f,'final-token',2,'project.create_screen',{'screen_id':'second','open':True})['result']
            assert made['active_screen']=='second'
            pix=rpc(f,'final-token',3,'pixel.create',{'path':'assets/x.png','width':8,'height':8})['result']
            rpc(f,'final-token',4,'pixel.paint',{'document_id':pix['document_id'],'x':1,'y':1,'value':1})
            rpc(f,'final-token',5,'pixel.save',{'document_id':pix['document_id']})
            created=rpc(f,'final-token',6,'scene.create_element',{'element':{'id':'x','type':'image','asset':'assets/x.png','x':1,'y':1}})['result']
            assert created['changed_elements']==['x']
            render=rpc(f,'final-token',7,'render.current')['result']
            assert render['framebuffer']['bytes']==64
            validation=rpc(f,'final-token',8,'validate.current')['result']
            assert validation['blockers']==0
            rpc(f,'final-token',9,'project.save_all')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    assert project.screen_path('second').exists()
    saved=json.loads(project.screen_path('second').read_text(encoding='utf-8'))
    assert any(e['id']=='x' for e in saved['elements'])
