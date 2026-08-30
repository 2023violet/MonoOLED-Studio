from __future__ import annotations
import queue, threading
from PySide6.QtCore import QObject, QTimer, Signal
from agent_bridge import LocalAgentBridgeServer, PendingBridgeCall, dispatch_json_rpc


class QtAutomationBridge(QObject):
    """Local JSON-RPC transport with explicit start/stop lifecycle.

    The 100 Hz drain timer is inactive while the bridge is off.  Shutdown
    stops polling, closes the server, joins the transport thread, and resolves
    pending callers with a deterministic error instead of leaking work.
    """
    statusChanged = Signal(str)
    commandCompleted = Signal(object)

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.server = None
        self.thread = None
        self._requests = queue.Queue()
        self.timer = QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self._drain)

    @property
    def running(self):
        return self.server is not None

    @property
    def endpoint(self):
        if not self.server:
            return None
        return {
            'host': '127.0.0.1',
            'port': self.server.server_address[1],
            'token': self.server.session_token,
            'permission': self.service.permission,
        }

    def set_service(self, service):
        self.service = service

    def start(self, *, port=0):
        if self.server:
            return self.endpoint
        self.server = LocalAgentBridgeServer(self._dispatch_from_thread, port=port)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name='MonoOLED-AgentBridge', daemon=True
        )
        self.thread.start()
        self.timer.start()
        self.statusChanged.emit('connected')
        return self.endpoint

    def stop(self):
        self.timer.stop()
        server = self.server
        thread = self.thread
        self.server = None
        self.thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        while True:
            try:
                call = self._requests.get_nowait()
            except queue.Empty:
                break
            call.cancel_if_queued({
                'jsonrpc': '2.0', 'id': call.request.get('id'),
                'error': {'code': 'BRIDGE_STOPPED', 'message': 'Agent bridge stopped'},
            })
        self.statusChanged.emit('off')

    def _dispatch_from_thread(self, request):
        call = PendingBridgeCall(request)
        self._requests.put(call)
        if call.done.wait(10):
            return call.response
        if call.expire_if_queued():
            return {
                'jsonrpc': '2.0', 'id': request.get('id'),
                'error': {'code': 'TIMEOUT', 'message': 'UI thread did not process request'},
            }
        # The UI thread already claimed the operation. Waiting for the real
        # response is safer than returning TIMEOUT and allowing a ghost edit to
        # complete afterwards.
        call.done.wait()
        return call.response

    def _drain(self):
        for _ in range(32):
            try:
                call = self._requests.get_nowait()
            except queue.Empty:
                return
            if not call.claim():
                continue
            response = dispatch_json_rpc(self.service, call.request)
            call.complete(response)
            self.commandCompleted.emit(response)
