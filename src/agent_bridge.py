from __future__ import annotations
import argparse, json, secrets, socketserver, threading
from automation_service import AUTOMATION_API_VERSION, PermissionDeniedError, StaleRevisionError, StudioAutomationService, TransactionError, UnsavedChangesError


class PendingBridgeCall:
    """One UI-thread bridge request with explicit queued/dispatch/expiry state.

    A caller may time out only while the request is still queued. Once the UI
    thread has claimed the request, the caller waits for the real response so
    an edit can never execute after a TIMEOUT was already returned.
    """

    def __init__(self, request: dict):
        self.request = dict(request)
        self.done = threading.Event()
        self._lock = threading.Lock()
        self._state = 'queued'
        self._response = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def response(self):
        with self._lock:
            return self._response

    def claim(self) -> bool:
        with self._lock:
            if self._state != 'queued':
                return False
            self._state = 'dispatching'
            return True

    def expire_if_queued(self) -> bool:
        with self._lock:
            if self._state != 'queued':
                return False
            self._state = 'expired'
            return True

    def complete(self, response: dict) -> None:
        with self._lock:
            if self._state == 'expired':
                return
            self._response = response
            self._state = 'done'
            self.done.set()

    def cancel_if_queued(self, response: dict) -> bool:
        with self._lock:
            if self._state != 'queued':
                return False
            self._response = response
            self._state = 'done'
            self.done.set()
            return True


def dispatch_json_rpc(service, request: dict) -> dict:
    rid=request.get('id')
    try:
        if request.get('jsonrpc')!='2.0': raise ValueError('jsonrpc must be 2.0')
        method=str(request['method']); params=dict(request.get('params') or {})
        expected=params.pop('_expected_revision',None); tx=params.pop('_transaction',None)
        if method=='history.begin_transaction': result={'ok':True,'revision':service.revision,'transaction':service.begin_transaction(expected_revision=expected)}
        elif method=='history.commit': result=service.commit_transaction(params['transaction'])
        elif method=='history.rollback': result=service.rollback_transaction(params['transaction'])
        else: result=service.call(method,params,expected_revision=expected,transaction=tx)
        return {'jsonrpc':'2.0','id':rid,'result':result}
    except PermissionDeniedError as exc: return {'jsonrpc':'2.0','id':rid,'error':{'code':'PERMISSION_DENIED','message':str(exc)}}
    except StaleRevisionError as exc: return {'jsonrpc':'2.0','id':rid,'error':{'code':'STALE_REVISION','message':str(exc)}}
    except TransactionError as exc: return {'jsonrpc':'2.0','id':rid,'error':{'code':'TRANSACTION_ERROR','message':str(exc)}}
    except UnsavedChangesError as exc: return {'jsonrpc':'2.0','id':rid,'error':{'code':'UNSAVED_CHANGES','message':str(exc)}}
    except KeyError as exc: return {'jsonrpc':'2.0','id':rid,'error':{'code':'METHOD_OR_FIELD_NOT_FOUND','message':str(exc)}}
    except Exception as exc: return {'jsonrpc':'2.0','id':rid,'error':{'code':'INVALID_REQUEST','message':str(exc)}}

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        server=self.server
        for raw in self.rfile:
            try:req=json.loads(raw.decode('utf-8')); token=req.pop('token',None)
            except Exception as exc:self.wfile.write((json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':'INVALID_JSON','message':str(exc)}})+'\n').encode());continue
            if token!=server.session_token:
                response={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':'UNAUTHORIZED','message':'invalid session token'}}
            else:response=server.dispatcher(req)
            self.wfile.write((json.dumps(response,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'));self.wfile.flush()

class LocalAgentBridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
    def __init__(self,dispatcher,*,host='127.0.0.1',port=0,session_token=None):
        if host not in {'127.0.0.1','localhost'}: raise ValueError('agent bridge is localhost-only')
        self.dispatcher=dispatcher;self.session_token=session_token or secrets.token_urlsafe(24);super().__init__((host,int(port)),_Handler)


def main(argv=None):
    from project_workspace import ProjectWorkspace
    from scene import load_scene
    ap=argparse.ArgumentParser(description=f'MonoOLED Studio Automation API {AUTOMATION_API_VERSION} bridge')
    source=ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--scene')
    source.add_argument('--project')
    ap.add_argument('--permission',choices=['observe','edit','full'],default='observe')
    ap.add_argument('--port',type=int,default=0)
    args=ap.parse_args(argv)
    if args.project:
        project=ProjectWorkspace.load(args.project)
        scene=load_scene(project.screen_path(project.active_screen),project_root=project.root)
        scene['_project_path']=str(project.path); scene['_asset_dirs']=list(project.asset_dirs); scene['_design_rules']=dict(project.data.get('design_rules') or {})
        svc=StudioAutomationService(scene,source_path=project.screen_path(project.active_screen),permission=args.permission,copy_scene=False,project_workspace=project)
    else:
        svc=StudioAutomationService.for_scene(args.scene,permission=args.permission)
    server=LocalAgentBridgeServer(lambda req:dispatch_json_rpc(svc,req),port=args.port)
    print(json.dumps({'host':'127.0.0.1','port':server.server_address[1],'token':server.session_token,'permission':args.permission,'automation_api':AUTOMATION_API_VERSION}),flush=True)
    server.serve_forever()
if __name__=='__main__':main()
