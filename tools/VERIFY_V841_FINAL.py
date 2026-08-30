#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
sys.path.insert(0, str(SIM))

from agent_bridge import LocalAgentBridgeServer, dispatch_json_rpc
from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS, StaleRevisionError, StudioAutomationService
from editor_model import EditorSession
from project_workspace import ProjectWorkspace, create_project
from scene import load_scene


def ortho_schema():
    return {
        'variables': {
            'total_cycles': {'type': 'int', 'values': [3, 5], 'init': 3},
            'current_cycle': {'type': 'int', 'min': 1, 'max': 5, 'init': 1},
        },
        'relations': [{'left': 'current_cycle', 'operator': '<=', 'right': 'total_cycles'}],
    }


def rpc(stream, token, rid, method, params=None):
    req = {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params or {}, 'token': token}
    stream.write((json.dumps(req, ensure_ascii=False) + '\n').encode('utf-8'))
    stream.flush()
    response = json.loads(stream.readline().decode('utf-8'))
    if 'error' in response:
        raise RuntimeError(response['error'])
    return response['result']


def main() -> int:
    assert AUTOMATION_API_VERSION.startswith('1.')
    contract = json.loads((SIM / 'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    assert contract['api_version'] == AUTOMATION_API_VERSION
    assert set(contract['methods']) == set(METHOD_SPECS)
    assert {'state.validate_schema', 'state.set_schema', 'state.validate'} <= set(METHOD_SPECS)
    assert contract['methods']['font.generate_glyphs']['params']['characters']['required'] is True

    report = {'version': '8.4.1', 'automation_api': AUTOMATION_API_VERSION, 'method_count': len(METHOD_SPECS)}

    # Frozen clinical baseline remains unchanged before Code AI edits product scenes.
    clinical = StudioAutomationService.for_scene(SIM / 'scenes/main_scene.json', permission='observe')
    states = clinical.call('state.enumerate', {'integer_policy': 'representative', 'include_states': False})
    rendered = clinical.call('render.all_states', {'integer_policy': 'representative'})
    validated = clinical.call('validate.all_states', {'integer_policy': 'representative'})
    assert states['cases'] == 560
    assert rendered['cases'] == 560 and rendered['framebuffer_bytes'] == 512
    assert validated['cases'] == 560 and validated['blockers'] == 0
    report['clinical_baseline'] = {'states': 560, 'framebuffer_bytes': 512, 'blockers': 0}

    with tempfile.TemporaryDirectory(prefix='monooled_v841_') as td:
        root = Path(td)
        project = create_project(root / 'state_project', name='State Model Graduation', canvas=(32, 16))
        scene = load_scene(project.screen_path('main'), project_root=project.root)
        scene['_project_path'] = str(project.path)
        session = EditorSession(scene)
        service = StudioAutomationService.for_editor(
            scene,
            source_path=project.screen_path('main'),
            editor_session=session,
            permission='full',
            project_workspace=project,
        )

        checked = service.call('state.validate_schema', {'schema': ortho_schema()})
        assert checked['valid'] and not checked['errors']

        tx = service.begin_transaction(expected_revision=0)
        service.call('state.set_schema', {'schema': ortho_schema()}, transaction=tx)
        service.rollback_transaction(tx)
        assert service.call('state.get_schema', {})['schema']['variables'] == {}

        service.call('state.set_schema', {'schema': ortho_schema()}, expected_revision=0)
        assert service.revision == 1
        try:
            service.call('state.set_schema', {'schema': ortho_schema()}, expected_revision=0)
            raise AssertionError('stale revision was accepted')
        except StaleRevisionError:
            pass

        matrix = service.call('state.enumerate', {'integer_policy': 'full', 'include_states': True})
        assert matrix['cases'] == 8
        assert {row['total_cycles'] for row in matrix['states']} == {3, 5}
        assert all(row['current_cycle'] <= row['total_cycles'] for row in matrix['states'])
        assert not any(row['total_cycles'] == 4 for row in matrix['states'])
        assert service.call('state.validate', {'state': {'total_cycles': 3, 'current_cycle': 4}})['valid'] is False
        assert service.call('state.validate', {'state': {'total_cycles': 5, 'current_cycle': 4}})['valid'] is True

        service.call('project.save', {})
        reopened = ProjectWorkspace.load(project.path)
        saved = json.loads(reopened.screen_path('main').read_text(encoding='utf-8'))
        assert saved['states']['total_cycles']['values'] == [3, 5]
        assert saved['state_relations'][0]['operator'] == '<='

        # A committed root schema mutation is one ordinary Designer undo.
        project2 = create_project(root / 'undo_project', name='Undo Graduation', canvas=(32, 16))
        scene2 = load_scene(project2.screen_path('main'), project_root=project2.root)
        session2 = EditorSession(scene2)
        service2 = StudioAutomationService.for_editor(scene2, source_path=project2.screen_path('main'), editor_session=session2, permission='full', project_workspace=project2)
        tx2 = service2.begin_transaction(expected_revision=0)
        service2.call('state.set_schema', {'schema': ortho_schema()}, transaction=tx2)
        service2.commit_transaction(tx2)
        assert session2.can_undo and session2.undo()
        assert scene2.get('states', {}) == {}

        # Transport parity: Code AI can discover and use the new contract over localhost JSON-RPC.
        server = LocalAgentBridgeServer(lambda req: dispatch_json_rpc(service, req), port=0, session_token='v841-token')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(('127.0.0.1', server.server_address[1]), timeout=5) as sock:
                stream = sock.makefile('rwb')
                caps = rpc(stream, 'v841-token', 1, 'automation.capabilities')
                assert caps['api_version'] == AUTOMATION_API_VERSION
                desc = rpc(stream, 'v841-token', 2, 'automation.describe_method', {'method': 'font.generate_glyphs'})
                assert desc['method']['params']['font_id']['required'] is True
                assert rpc(stream, 'v841-token', 3, 'state.validate', {'state': {'total_cycles': 3, 'current_cycle': 5}})['valid'] is False
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()

        report['state_model'] = {
            'legal_cases': 8,
            'discrete_total_cycles': [3, 5],
            'relation': 'current_cycle <= total_cycles',
            'revision_guard': 'PASS',
            'transaction_rollback': 'PASS',
            'designer_undo': 'PASS',
            'save_reopen': 'PASS',
            'localhost_json_rpc': 'PASS',
            'font_contract_discovery': 'PASS',
        }

    target = SIM / 'reports' / 'v841_final_report.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
