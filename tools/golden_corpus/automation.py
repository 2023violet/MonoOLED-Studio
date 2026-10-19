"""Recorded Automation API 1.3.0 request/response sessions (in-process, no socket)."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

from .common import ROOT, case, replace_root

from agent_bridge import dispatch_json_rpc
from automation_service import StudioAutomationService
from project_workspace import ProjectWorkspace
from scene import load_scene

NAME = 'automation'
SOURCES = ('src/automation_service.py', 'src/automation_dispatch.py', 'src/automation_jobs.py', 'src/AUTOMATION_API_V1.json',
           'src/c_export.py', 'src/output_formatter.py', 'src/output_profiles.py', 'src/pixel_studio.py', 'src/agent_bridge.py')

CURING_LITE = ROOT / 'test_assets' / 'projects' / 'curing_lite'
VOLATILE_KEYS = frozenset({'elapsed_ms'})
STATE = {'mode': 'NORMAL', 'phase': 'standby', 'battery': 0, 'seconds': 0}

SESSION = [
    ('automation.capabilities', {}),
    ('project.get', {}),
    ('project.list_screens', {}),
    ('scene.get', {}),
    ('scene.list_elements', {}),
    ('state.list', {}),
    ('state.validate', {'state': STATE}),
    ('render.framebuffer', {'state': STATE}),
    ('render.current', {'state': STATE}),
    ('render.all_states', {'integer_policy': 'boundaries', 'summary_only': True}),
    ('output.list_profiles', {}),
    ('output.get_profile', {'profile_id': 'ssd1306_vlsb_c'}),
    ('output.preview', {'source': {'kind': 'current_scene'}, 'profile_id': 'ssd1306_vlsb_c', 'symbol': 'preview frame'}),
    ('output.preview', {'source': {'kind': 'current_scene'}, 'profile_id': 'legacy_pixel_c', 'symbol': 'legacy'}),
    ('output.upsert_profile', {'profile_id': 'golden_row', 'profile': '$builtin:row_msb_c51'}),
    ('output.set_active_profile', {'profile_id': 'golden_row'}),
    ('output.list_profiles', {}),
    ('output.set_active_profile', {'profile_id': 'ssd1306_vlsb_c'}),
    ('output.delete_profile', {'profile_id': 'golden_row'}),
    ('export.c_header', {'path': 'exports/current.h', 'symbol': 'oled_frame', 'state': STATE}),
    ('export.current', {'output_dir': 'exports/current', 'state': STATE}),
    ('export.bitmap_data', {'source': {'kind': 'current_scene'}, 'profile_id': 'ssd1306_vlsb_c', 'path': 'exports/bitmap.h', 'symbol': 'bitmap'}),
    ('pixel.create', {'path': 'assets/golden_icon.png', 'width': 10, 'height': 10}),
    ('pixel.paint', {'document_id': '$doc', 'x': 0, 'y': 0, 'value': 1}),
    ('pixel.line', {'document_id': '$doc', 'x0': 0, 'y0': 9, 'x1': 9, 'y1': 0, 'value': 1}),
    ('pixel.undo', {'document_id': '$doc'}),
    ('pixel.get_document', {'document_id': '$doc'}),
    ('history.begin_transaction', {}),
    ('history.rollback', {'transaction': '$transaction'}),
    ('render.framebuffer', {'state': STATE, '_expected_revision': -1}),
    ('no.such_method', {}),
]


def _service(root: Path) -> StudioAutomationService:
    project = ProjectWorkspace.load(root / 'project.oled.json')
    path = project.screen_path('main')
    scene = load_scene(path, project_root=project.root)
    return StudioAutomationService(scene, source_path=path, permission='full', copy_scene=False, project_workspace=project)


def _resolve(params: dict, memory: dict, service) -> dict:
    resolved = {}
    for key, value in params.items():
        if value == '$doc':
            value = memory['document_id']
        elif value == '$transaction':
            value = memory['transaction']
        elif isinstance(value, str) and value.startswith('$builtin:'):
            value = service.call('output.get_profile', {'profile_id': value.split(':', 1)[1]})['profile']
        resolved[key] = value
    return resolved


def _normalize(value, memory: dict, root: Path):
    """Replace the project root and run-specific identifiers with stable tokens."""
    value = replace_root(value, root)
    if isinstance(value, str):
        for key in ('document_id', 'transaction'):
            if key in memory and memory[key] and memory[key] in value:
                value = value.replace(memory[key], '${' + key.upper() + '}')
        return value
    if isinstance(value, list):
        return [_normalize(item, memory, root) for item in value]
    if isinstance(value, dict):
        # Wall-clock timings are the only volatile response fields; nothing else is dropped.
        return {key: ('${ELAPSED_MS}' if key in VOLATILE_KEYS else _normalize(item, memory, root)) for key, item in value.items()}
    return value


def _record(service, root: Path) -> list[dict]:
    memory: dict = {}
    steps = []
    for index, (method, params) in enumerate(SESSION, start=1):
        request = {'jsonrpc': '2.0', 'id': index, 'method': method, 'params': _resolve(params, memory, service)}
        response = dispatch_json_rpc(service, request)
        result = response.get('result')
        if isinstance(result, dict):
            if method == 'pixel.create':
                memory['document_id'] = result['document_id']
            if method == 'history.begin_transaction':
                memory['transaction'] = result['transaction']
        steps.append({'request': _normalize({**request, 'params': params}, memory, root),
                      'response': _normalize(response, memory, root)})
    files = {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
             for path in sorted((root / 'exports').rglob('*')) if path.is_file()}
    return steps, files


def build(work: Path) -> list[dict]:
    root = work / 'curing_lite'
    shutil.copytree(CURING_LITE, root)
    steps, files = _record(_service(root), root)
    return [case('api-session-curing_lite-main', 'automation_session', 'strict',
                 {'project': 'test_assets/projects/curing_lite', 'screen': 'main', 'permission': 'full'},
                 {'steps': steps, 'export_files': files})]
