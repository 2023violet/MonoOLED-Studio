from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation_service import AUTOMATION_API_VERSION, StaleRevisionError, StudioAutomationService
from project_workspace import ProjectWorkspace, create_project
from scene import load_scene


def _service_for_project(tmp_path):
    project = create_project(tmp_path / 'demo', name='State Model Demo', canvas=(32, 16))
    scene = load_scene(project.screen_path('main'), project_root=project.root)
    scene['_project_path'] = str(project.path)
    scene['_asset_dirs'] = list(project.asset_dirs)
    scene['_design_rules'] = {}
    service = StudioAutomationService(
        scene,
        source_path=project.screen_path('main'),
        permission='full',
        copy_scene=False,
        project_workspace=project,
    )
    return project, service


def _ortho_schema():
    return {
        'variables': {
            'total_cycles': {
                'type': 'int',
                'values': [3, 5],
                'init': 3,
            },
            'current_cycle': {
                'type': 'int',
                'min': 1,
                'max': 5,
                'init': 1,
            },
        },
        'relations': [
            {
                'left': 'current_cycle',
                'operator': '<=',
                'right': 'total_cycles',
            }
        ],
    }


def test_v841_state_schema_api_is_discoverable_and_self_describing(tmp_path):
    _, service = _service_for_project(tmp_path)
    caps = service.call('automation.capabilities', {})
    assert AUTOMATION_API_VERSION.startswith('1.')
    assert caps['api_version'] == AUTOMATION_API_VERSION
    methods = {row['method']: row for row in caps['methods']}
    for name in ('state.validate_schema', 'state.set_schema', 'state.validate'):
        assert name in methods
        assert methods[name]['params']
    assert methods['state.set_schema']['transaction_supported'] is True
    schema_param = methods['state.set_schema']['params']['schema']
    assert schema_param['type'] == 'object'
    assert {'variables', 'relations'} <= set(schema_param['properties'])
    assert schema_param['properties']['relations']['items']['properties']['operator']['enum'] == ['<', '<=', '==', '!=', '>=', '>']


def test_v841_schema_validation_and_enumeration_support_discrete_values_and_relations(tmp_path):
    _, service = _service_for_project(tmp_path)
    schema = _ortho_schema()
    checked = service.call('state.validate_schema', {'schema': schema})
    assert checked['valid'] is True
    assert checked['errors'] == []

    service.call('state.set_schema', {'schema': schema}, expected_revision=0)
    current = service.call('state.get_schema', {})
    assert current['schema']['variables']['total_cycles']['values'] == [3, 5]
    assert current['schema']['relations'][0]['operator'] == '<='

    enumerated = service.call('state.enumerate', {'integer_policy': 'full', 'include_states': True})
    states = enumerated['states']
    assert enumerated['cases'] == 8
    assert {s['total_cycles'] for s in states} == {3, 5}
    assert all(s['current_cycle'] <= s['total_cycles'] for s in states)
    assert not [s for s in states if s['total_cycles'] == 4]
    assert not [s for s in states if s['total_cycles'] == 3 and s['current_cycle'] in {4, 5}]


def test_v841_state_validate_rejects_illegal_relation_and_accepts_legal_state(tmp_path):
    _, service = _service_for_project(tmp_path)
    service.call('state.set_schema', {'schema': _ortho_schema()})
    bad = service.call('state.validate', {'state': {'total_cycles': 3, 'current_cycle': 4}})
    assert bad['valid'] is False
    assert any(v['code'] == 'RELATION' for v in bad['violations'])

    good = service.call('state.validate', {'state': {'total_cycles': 5, 'current_cycle': 4}})
    assert good['valid'] is True
    assert good['violations'] == []


def test_v841_state_set_schema_obeys_revision_guard_and_transaction_rollback(tmp_path):
    _, service = _service_for_project(tmp_path)
    tx = service.begin_transaction(expected_revision=0)
    service.call('state.set_schema', {'schema': _ortho_schema()}, transaction=tx)
    assert service.call('state.get_schema', {})['schema']['variables']['total_cycles']['values'] == [3, 5]
    service.rollback_transaction(tx)
    assert service.call('state.get_schema', {})['schema']['variables'] == {}
    assert service.revision == 0

    service.call('state.set_schema', {'schema': _ortho_schema()}, expected_revision=0)
    assert service.revision == 1
    with pytest.raises(StaleRevisionError):
        service.call('state.set_schema', {'schema': _ortho_schema()}, expected_revision=0)


def test_v841_state_schema_save_reopen_round_trip(tmp_path):
    project, service = _service_for_project(tmp_path)
    service.call('state.set_schema', {'schema': _ortho_schema()})
    service.call('project.save', {})

    reopened_project = ProjectWorkspace.load(project.path)
    saved = json.loads(reopened_project.screen_path('main').read_text(encoding='utf-8'))
    assert saved['states']['total_cycles']['values'] == [3, 5]
    assert saved['state_relations'][0] == {
        'left': 'current_cycle',
        'operator': '<=',
        'right': 'total_cycles',
    }
    reopened = StudioAutomationService.for_scene(reopened_project.screen_path('main'), permission='observe')
    schema = reopened.call('state.get_schema', {})['schema']
    assert schema['variables']['current_cycle']['max'] == 5
    assert schema['relations'][0]['operator'] == '<='


def test_v841_invalid_state_schema_fails_closed_without_mutating_scene(tmp_path):
    _, service = _service_for_project(tmp_path)
    invalid = _ortho_schema()
    invalid['variables']['total_cycles']['values'] = [3, 4, 5]
    invalid['relations'][0]['right'] = 'missing_variable'
    checked = service.call('state.validate_schema', {'schema': invalid})
    assert checked['valid'] is False
    assert checked['errors']
    with pytest.raises(ValueError):
        service.call('state.set_schema', {'schema': invalid})
    assert service.call('state.get_schema', {})['schema']['variables'] == {}
    assert service.revision == 0


def test_v841_font_methods_publish_real_parameter_contracts(tmp_path):
    _, service = _service_for_project(tmp_path)
    expected = {
        'font.create_pack': {'path', 'name', 'cell', 'baseline', 'advance'},
        'font.get_pack': {'font_id'},
        'font.generate_glyphs': {'font_id', 'characters', 'font_path', 'font_size', 'threshold', 'offset', 'alignment', 'antialias_scale'},
        'font.get_glyph': {'font_id', 'char'},
        'font.update_glyph': {'font_id', 'char', 'pixels', 'metrics'},
        'font.set_metrics': {'font_id', 'baseline', 'advance'},
    }
    for method, names in expected.items():
        desc = service.call('automation.describe_method', {'method': method})['method']
        assert set(desc['params']) == names, method
        for name, spec in desc['params'].items():
            assert isinstance(spec, dict), (method, name)
            assert 'type' in spec, (method, name)
            assert 'required' in spec, (method, name)
        assert 'returns' in desc and isinstance(desc['returns'], dict), method

    glyphs = service.call('automation.describe_method', {'method': 'font.generate_glyphs'})['method']
    assert glyphs['params']['font_id']['required'] is True
    assert glyphs['params']['characters']['required'] is True
    assert glyphs['params']['font_size']['minimum'] == 1
    assert glyphs['params']['threshold']['minimum'] == 0
    assert glyphs['params']['threshold']['maximum'] == 255


def test_v841_committed_state_schema_transaction_is_one_designer_undo(tmp_path):
    from editor_model import EditorSession

    project = create_project(tmp_path / 'undo_demo', name='Undo State Schema', canvas=(32, 16))
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
    tx = service.begin_transaction(expected_revision=0)
    service.call('state.set_schema', {'schema': _ortho_schema()}, transaction=tx)
    service.commit_transaction(tx)
    assert scene['states']['total_cycles']['values'] == [3, 5]
    assert session.can_undo is True
    assert session.undo() is True
    assert scene.get('states', {}) == {}
    assert scene.get('state_relations', []) == []


def test_v841_localhost_jsonrpc_can_author_and_validate_state_schema(tmp_path):
    import socket
    import threading

    from agent_bridge import LocalAgentBridgeServer, dispatch_json_rpc

    _, service = _service_for_project(tmp_path)
    server = LocalAgentBridgeServer(lambda req: dispatch_json_rpc(service, req), port=0, session_token='state-token')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(('127.0.0.1', server.server_address[1]), timeout=3) as sock:
            stream = sock.makefile('rwb')

            def rpc(rid, method, params=None):
                payload = {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params or {}, 'token': 'state-token'}
                stream.write((json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8'))
                stream.flush()
                return json.loads(stream.readline().decode('utf-8'))['result']

            caps = rpc(1, 'automation.capabilities')
            assert caps['api_version'] == AUTOMATION_API_VERSION
            desc = rpc(2, 'automation.describe_method', {'method': 'font.generate_glyphs'})
            assert desc['method']['params']['characters']['required'] is True
            assert rpc(3, 'state.validate_schema', {'schema': _ortho_schema()})['valid'] is True
            changed = rpc(4, 'state.set_schema', {'schema': _ortho_schema()})
            assert changed['changed'] is True
            invalid = rpc(5, 'state.validate', {'state': {'total_cycles': 3, 'current_cycle': 5}})
            assert invalid['valid'] is False
            matrix = rpc(6, 'state.enumerate', {'integer_policy': 'full', 'include_states': True})
            assert matrix['cases'] == 8
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert not thread.is_alive()
