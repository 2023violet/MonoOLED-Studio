"""Recorded Automation API 1.3.0 JSON-RPC sessions (in-process, no socket).

Each case is an independent session on a fresh copy of `curing_lite`; every
method in `METHOD_SPECS` appears in at least one session. The recorded request
is exactly what was dispatched (no macros). V1 ids are deterministic
(`pixel:<path>`, `tx-<n>`, `job-<n>`) and are recorded as-is. The only
normalisation is the project root path and wall-clock `elapsed_ms`.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

from .common import ROOT, case, replace_root

from agent_bridge import dispatch_json_rpc
from automation_service import METHOD_SPECS, StudioAutomationService
from output_profiles import builtin_profiles
from project_workspace import ProjectWorkspace
from scene import load_scene

NAME = 'automation'
SOURCES = ('src/automation_service.py', 'src/automation_dispatch.py', 'src/automation_jobs.py', 'src/AUTOMATION_API_V1.json',
           'src/agent_bridge.py', 'src/c_export.py', 'src/output_formatter.py', 'src/output_profiles.py', 'src/pixel_studio.py',
           'src/selection_model.py', 'src/selection_tools.py', 'src/editor_model.py', 'src/document.py', 'src/font_pack.py')

CURING_LITE = ROOT / 'test_assets' / 'projects' / 'curing_lite'
VOLATILE_KEYS = frozenset({'elapsed_ms'})
STATE = {'mode': 'NORMAL', 'phase': 'standby', 'battery': 0, 'seconds': 0}
OTHER = {'mode': 'HIGH', 'phase': 'standby', 'battery': 3, 'seconds': 9}
ROW_PROFILE = builtin_profiles()['row_msb_c51'].to_dict()
ICON = 'pixel:assets/golden_icon.png'

SESSIONS: dict[str, list[tuple[str, dict]]] = {
    'meta': [
        ('automation.capabilities', {}),
        ('automation.describe_method', {'method': 'pixel.line'}),
        ('automation.describe_method', {'method': 'no.such_method'}),
        ('session.events', {}),
    ],
    'project': [
        ('project.get', {}),
        ('project.get_contract', {}),
        ('project.list_screens', {}),
        ('project.list_assets', {}),
        ('project.create_screen', {'screen_id': 'golden', 'label': 'Golden'}),
        ('project.duplicate_screen', {'screen_id': 'golden', 'new_id': 'golden_copy', 'label': 'Copy'}),
        ('project.rename_screen', {'screen_id': 'golden_copy', 'new_id': 'golden_renamed', 'label': 'Renamed'}),
        ('scene.update_element', {'id': 'mode_label', 'changes': {'x': 87}}),
        ('project.open_screen', {'screen_id': '123'}),
        ('project.open_screen', {'screen_id': '123', 'discard_current': True}),
        ('project.open_screen', {'screen_id': 'main'}),
        ('project.delete_screen', {'screen_id': 'golden_renamed'}),
        ('project.save', {}),
        ('project.save_all', {}),
        ('project.list_screens', {}),
        ('session.events', {'since': 0}),
    ],
    'scene': [
        ('scene.get', {}),
        ('scene.get_schema', {}),
        ('scene.list_elements', {}),
        ('scene.create_element', {'element': {'id': 'golden_box', 'type': 'placeholder', 'x': 2, 'y': 2, 'w': 10, 'h': 6, 'label': 'G'}}),
        ('scene.update_element', {'id': 'golden_box', 'changes': {'x': 4, 'w': 12}}),
        ('selection.get', {}),
        ('selection.set', {'ids': ['golden_box', 'battery'], 'primary_id': 'battery'}),
        ('selection.toggle', {'id': 'hero_digits'}),
        ('layout.measure', {}),
        ('layout.measure', {'ids': ['golden_box', 'hero_digits']}),
        ('layout.align', {'mode': 'top', 'reference': 'primary'}),
        ('layout.distribute', {'axis': 'horizontal'}),
        ('selection.clear', {}),
        ('scene.delete_elements', {'ids': ['golden_box']}),
        ('scene.update_element', {'id': 'missing_element', 'changes': {'x': 1}}),
        ('scene.list_elements', {}),
    ],
    'state': [
        ('state.get_schema', {}),
        ('state.list', {}),
        ('state.validate', {'state': STATE}),
        ('state.validate', {'state': {**STATE, 'battery': 99, 'extra': 1}}),
        ('state.validate_schema', {'schema': {'variables': {'n': {'type': 'int', 'min': 0, 'max': 3, 'init': 0}}}}),
        ('state.validate_schema', {'schema': {'variables': {'n': {'type': 'int', 'min': 5, 'max': 3, 'init': 9}},
                                              'relations': [{'left': 'n', 'operator': '~', 'right': 'm'}]}}),
        ('state.count', {'integer_policy': 'boundaries'}),
        ('state.count', {'integer_policy': 'representative'}),
        ('state.enumerate', {'integer_policy': 'boundaries', 'include_states': True}),
        ('state.enumerate', {'integer_policy': 'boundaries', 'summary_only': True}),
        ('state.count', {'integer_policy': 'full', 'max_cases': 10}),
    ],
    'state_set': [
        ('state.set_schema', {'schema': {'variables': {'mode': {'type': 'enum', 'values': ['NORMAL', 'HIGH'], 'init': 'NORMAL'},
                                                       'phase': {'type': 'enum', 'values': ['standby'], 'init': 'standby'},
                                                       'battery': {'type': 'int', 'min': 0, 'max': 1, 'init': 0},
                                                       'seconds': {'type': 'int', 'values': [0, 5], 'init': 0}}}}),
        ('state.list', {}),
        ('state.count', {'integer_policy': 'boundaries'}),
    ],
    'render': [
        ('render.current', {'state': STATE}),
        ('render.framebuffer', {'state': OTHER}),
        ('render.resolved_elements', {'state': STATE}),
        ('render.png', {'state': STATE}),
        ('render.preview_file', {'path': 'exports/preview.png', 'state': STATE}),
        ('render.annotated_preview', {'path': 'exports/annotated.png', 'state': STATE, 'scale': 3}),
        ('render.pixel_diff', {'before_state': STATE, 'after_state': OTHER}),
        ('render.all_states', {'integer_policy': 'boundaries', 'summary_only': True}),
        ('render.all_states', {'integer_policy': 'boundaries', 'summary_only': False, 'include_frames': True, 'max_cases': 200}),
        ('render.framebuffer', {'state': {**STATE, 'battery': 99}}),
    ],
    'validate': [
        ('validate.current', {'state': STATE}),
        ('validate.all_states', {'integer_policy': 'boundaries', 'summary_only': True}),
        ('validate.all_states', {'integer_policy': 'boundaries', 'include_cases': True, 'max_cases': 200}),
    ],
    'asset': [
        ('asset.create', {'path': 'assets/golden/blank.png', 'width': 8, 'height': 4, 'value': 1}),
        ('asset.import', {'source': '${PROJECT_ROOT}/assets/golden/blank.png', 'target': 'assets/golden/imported.png'}),
        ('asset.copy', {'path': 'assets/golden/imported.png', 'target': 'assets/golden/copied.png'}),
        ('asset.rename', {'path': 'assets/golden/copied.png', 'target': 'assets/golden/renamed.png'}),
        ('asset.delete', {'path': 'assets/golden/renamed.png'}),
        ('asset.delete', {'path': 'assets/golden/renamed.png'}),
        ('asset.create', {'path': '../escape.png', 'width': 1, 'height': 1}),
        ('project.list_assets', {}),
    ],
    'pixel': [
        ('pixel.create', {'path': 'assets/golden_icon.png', 'width': 10, 'height': 10}),
        ('pixel.paint', {'document_id': ICON, 'x': 0, 'y': 0, 'value': 1}),
        ('pixel.erase', {'document_id': ICON, 'x': 0, 'y': 0}),
        ('pixel.line', {'document_id': ICON, 'x0': 0, 'y0': 9, 'x1': 9, 'y1': 0, 'value': 1}),
        ('pixel.rect', {'document_id': ICON, 'x0': 1, 'y0': 1, 'x1': 5, 'y1': 4, 'filled': False}),
        ('pixel.rect', {'document_id': ICON, 'x0': 6, 'y0': 6, 'x1': 8, 'y1': 8, 'filled': True}),
        ('pixel.fill', {'document_id': ICON, 'x': 2, 'y': 2, 'value': 1}),
        ('pixel.undo', {'document_id': ICON}),
        ('pixel.redo', {'document_id': ICON}),
        ('pixel.rotate', {'document_id': ICON, 'angle': 90}),
        ('pixel.flip', {'document_id': ICON, 'axis': 'vertical'}),
        ('pixel.resize_canvas', {'document_id': ICON, 'width': 12, 'height': 8, 'anchor': 'top_left'}),
        ('pixel.rotate', {'document_id': ICON, 'angle': 45}),
        ('pixel.get_document', {'document_id': ICON}),
        ('pixel.save', {'document_id': ICON}),
        ('pixel.close', {'document_id': ICON}),
        ('pixel.open', {'path': 'assets/golden_icon.png'}),
        ('pixel.get_document', {'document_id': ICON}),
        ('pixel.paint', {'document_id': ICON, 'x': 1, 'y': 1, 'value': 1}),
        ('pixel.close', {'document_id': ICON}),
        ('pixel.close', {'document_id': ICON, 'discard': True}),
        ('pixel.get_document', {'document_id': 'pixel:missing.png'}),
    ],
    'font': [
        ('font.create_pack', {'path': 'fonts/golden', 'name': 'Golden', 'cell': [5, 8], 'baseline': 6, 'advance': 6}),
        ('font.list', {}),
        ('font.generate_glyphs', {'font_id': 'fonts/golden', 'characters': 'AB1/', 'font_path': None, 'font_size': 8,
                                  'threshold': 128, 'offset': [0, 0], 'alignment': 'glyph_width'}),
        ('font.get_pack', {'font_id': 'fonts/golden'}),
        ('font.get_glyph', {'font_id': 'fonts/golden', 'char': 'A'}),
        ('font.update_glyph', {'font_id': 'fonts/golden', 'char': 'Z', 'pixels': [[1, 0, 0, 0, 1]] * 8,
                               'metrics': {'bearing_x': 0, 'bearing_y': 0, 'advance': 6}}),
        ('font.set_metrics', {'font_id': 'fonts/golden', 'baseline': 7, 'advance': 7}),
        ('font.get_pack', {'font_id': 'fonts/golden'}),
        ('export.font_data', {'font_id': 'fonts/golden', 'characters': 'ABZ', 'profile_id': 'ssd1306_vlsb_c', 'path': 'exports/font.h', 'symbol': 'golden_font'}),
        ('export.font_pack', {'font_id': 'fonts/golden', 'path': 'exports/golden_font.zip'}),
        ('font.get_glyph', {'font_id': 'fonts/golden', 'char': 'Q'}),
    ],
    'output': [
        ('output.list_profiles', {}),
        ('output.get_profile', {'profile_id': 'ssd1306_vlsb_c'}),
        ('output.preview', {'source': {'kind': 'current_scene'}, 'profile_id': 'ssd1306_vlsb_c', 'symbol': 'preview frame'}),
        ('output.preview', {'source': {'kind': 'current_scene'}, 'profile_id': 'legacy_pixel_c', 'symbol': 'legacy'}),
        ('output.preview', {'source': {'kind': 'current_scene'}, 'profile': {**ROW_PROFILE, 'name': 'Draft'}}),
        ('output.upsert_profile', {'profile_id': 'golden_row', 'profile': ROW_PROFILE}),
        ('output.upsert_profile', {'profile_id': 'Bad-ID', 'profile': ROW_PROFILE}),
        ('output.set_active_profile', {'profile_id': 'golden_row'}),
        ('output.list_profiles', {}),
        ('output.set_active_profile', {'profile_id': 'ssd1306_vlsb_c'}),
        ('output.delete_profile', {'profile_id': 'golden_row'}),
        ('output.get_profile', {'profile_id': 'golden_row'}),
    ],
    'export': [
        ('export.c_header', {'path': 'exports/current.h', 'symbol': 'oled_frame', 'state': STATE}),
        ('export.current', {'output_dir': 'exports/current', 'state': STATE}),
        ('export.all', {'output_dir': 'exports/all', 'integer_policy': 'boundaries', 'summary_only': True, 'include_hashes': True, 'max_cases': 200}),
        ('export.bitmap_data', {'source': {'kind': 'current_scene'}, 'profile_id': 'ssd1306_vlsb_c', 'path': 'exports/bitmap.h', 'symbol': 'bitmap'}),
        ('pixel.create', {'path': 'assets/export_icon.png', 'width': 10, 'height': 10}),
        ('pixel.paint', {'document_id': 'pixel:assets/export_icon.png', 'x': 3, 'y': 4, 'value': 1}),
        ('export.bitmap_data', {'source': {'kind': 'pixel_document', 'document_id': 'pixel:assets/export_icon.png'},
                                'profile_id': 'raw_hex', 'path': 'exports/icon.txt'}),
        ('export.code_ai_handoff', {'path': 'exports/handoff.zip', 'integer_policy': 'boundaries', 'max_cases': 200}),
        ('export.c_header', {'path': '../outside.h'}),
    ],
    'history': [
        ('history.begin_transaction', {}),
        ('scene.update_element', {'id': 'mode_label', 'changes': {'x': 90}, '_transaction': 'tx-1'}),
        ('history.commit', {'transaction': 'tx-1'}),
        ('history.begin_transaction', {}),
        ('scene.update_element', {'id': 'mode_label', 'changes': {'x': 91}, '_transaction': 'tx-2'}),
        ('history.rollback', {'transaction': 'tx-2'}),
        ('history.commit', {'transaction': 'tx-99'}),
        ('scene.update_element', {'id': 'mode_label', 'changes': {'x': 1}, '_transaction': 'tx-99'}),
        ('scene.list_elements', {}),
    ],
    'jobs': [
        ('job.start', {'operation': 'render.all_states', 'arguments': {'integer_policy': 'boundaries', 'summary_only': True}}),
        ('job.status', {'job_id': 'job-1'}),
        ('job.result', {'job_id': 'job-1'}),
        ('job.release', {'job_id': 'job-1'}),
        ('job.start', {'operation': 'scene.get', 'arguments': {}}),
        ('job.cancel', {'job_id': 'job-404'}),
        ('job.status', {'job_id': 'job-404'}),
    ],
    'errors': [
        ('no.such_method', {}),
        ('render.framebuffer', {'state': STATE, '_expected_revision': -1}),
        ('pixel.paint', {'document_id': 'pixel:none', 'x': 0, 'y': 0}),
        ('scene.update_element', {'changes': {}}),
    ],
}

OBSERVE_SESSION = [
    ('scene.get', {}),
    ('scene.update_element', {'id': 'mode_label', 'changes': {'x': 1}}),
    ('export.c_header', {'path': 'exports/x.h'}),
    ('history.begin_transaction', {}),
    ('job.start', {'operation': 'export.all', 'arguments': {'output_dir': 'exports/all'}}),
]

RAW_REQUESTS = [
    ('invalid-jsonrpc', {'jsonrpc': '1.0', 'id': 1, 'method': 'scene.get'}),
    ('missing-method', {'jsonrpc': '2.0', 'id': 2}),
]


def _service(root: Path, permission: str = 'full') -> StudioAutomationService:
    project = ProjectWorkspace.load(root / 'project.oled.json')
    path = project.screen_path('main')
    scene = load_scene(path, project_root=project.root)
    return StudioAutomationService(scene, source_path=path, permission=permission, copy_scene=False, project_workspace=project)


def _normalize(value, root: Path):
    value = replace_root(value, root)
    if isinstance(value, list):
        return [_normalize(item, root) for item in value]
    if isinstance(value, dict):
        return {key: ('${ELAPSED_MS}' if key in VOLATILE_KEYS else _normalize(item, root)) for key, item in value.items()}
    return value


def _resolve(params: dict, root: Path) -> dict:
    """Substitute the literal `${PROJECT_ROOT}` token in request params with the real root."""
    return json.loads(json.dumps(params, ensure_ascii=False).replace('${PROJECT_ROOT}', root.as_posix()))


def _wait_for_jobs(service) -> None:
    deadline = time.monotonic() + 120
    manager = service._jobs
    while time.monotonic() < deadline:
        if all(job.state in manager.TERMINAL_STATES for job in manager._jobs.values()):
            return
        time.sleep(0.02)
    raise RuntimeError('automation job did not finish within 120 s')


def _run(service, root: Path, script) -> list[dict]:
    steps = []
    for index, (method, params) in enumerate(script, start=1):
        request = {'jsonrpc': '2.0', 'id': index, 'method': method, 'params': _resolve(params, root)}
        response = dispatch_json_rpc(service, json.loads(json.dumps(request)))
        if method == 'job.start':
            _wait_for_jobs(service)
        steps.append({'request': _normalize(request, root), 'response': _normalize(response, root)})
    return steps


def _files(root: Path) -> dict:
    tracked = {}
    for base in ('exports', 'assets/golden', 'fonts', 'scenes'):
        directory = root / base
        if directory.is_dir():
            for path in sorted(directory.rglob('*')):
                if path.is_file():
                    tracked[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
    tracked['project.oled.json'] = sha256((root / 'project.oled.json').read_bytes()).hexdigest()
    return tracked


def _fresh(work: Path, name: str) -> Path:
    root = work / name
    shutil.copytree(CURING_LITE, root)
    return root


def build(work: Path) -> list[dict]:
    covered = {method for script in [*SESSIONS.values(), OBSERVE_SESSION] for method, _ in script}
    missing = sorted(set(METHOD_SPECS) - covered)
    if missing:
        raise RuntimeError(f'automation corpus does not cover: {missing}')
    cases = []
    for name, script in SESSIONS.items():
        root = _fresh(work, name)
        steps = _run(_service(root), root, script)
        cases.append(case(f'api-{name}', 'automation_session', 'strict',
                          {'project': 'test_assets/projects/curing_lite', 'screen': 'main', 'permission': 'full'},
                          {'steps': steps, 'files_sha256': _files(root)},
                          note='PNG/ZIP file digests depend on the encoder; Rust compares them by content where applicable'))
    root = _fresh(work, 'observe')
    cases.append(case('api-permission-observe', 'automation_session', 'strict',
                      {'project': 'test_assets/projects/curing_lite', 'screen': 'main', 'permission': 'observe'},
                      {'steps': _run(_service(root, 'observe'), root, OBSERVE_SESSION), 'files_sha256': _files(root)}))
    root = _fresh(work, 'raw')
    service = _service(root)
    for label, request in RAW_REQUESTS:
        cases.append(case(f'api-raw-{label}', 'automation_raw', 'strict', {'request': request},
                          {'response': _normalize(dispatch_json_rpc(service, dict(request)), root)}))
    return cases
