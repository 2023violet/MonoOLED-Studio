from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from automation_service import StudioAutomationService
from project_workspace import create_project
from scene import load_scene


def _service(tmp_path, *, many_states: bool = False):
    project = create_project(tmp_path / 'project', name='Reliability', canvas=(32, 16))
    project.add_screen('second', label='Second', canvas=(32, 16))
    scene = load_scene(project.screen_path('main'), project_root=project.root)
    scene['_project_path'] = str(project.path)
    scene['_asset_dirs'] = list(project.asset_dirs)
    scene['_design_rules'] = {}
    if many_states:
        scene['states'] = {'step': {'type': 'int', 'min': 0, 'max': 400, 'init': 0}}
    service = StudioAutomationService(
        scene,
        source_path=project.screen_path('main'),
        permission='full',
        copy_scene=False,
        project_workspace=project,
    )
    return project, service


def _element(eid='box'):
    return {'id': eid, 'type': 'placeholder', 'x': 1, 'y': 1, 'w': 4, 'h': 4}


def test_transaction_commit_marks_unsaved_scene_dirty(tmp_path):
    _, service = _service(tmp_path)
    assert service.call('project.get', {})['dirty'] is False
    tx = service.begin_transaction()
    service.call('scene.create_element', {'element': _element()}, transaction=tx)
    service.commit_transaction(tx)
    assert service.call('project.get', {})['dirty'] is True
    service.call('project.save', {})
    assert service.call('project.get', {})['dirty'] is False


def test_open_screen_fails_closed_when_current_scene_is_dirty(tmp_path):
    project, service = _service(tmp_path)
    service.call('scene.create_element', {'element': _element()})
    with pytest.raises(Exception, match='UNSAVED_CHANGES'):
        service.call('project.open_screen', {'screen_id': 'second'})
    assert service.call('project.get', {})['active_screen'] == 'main'
    saved = json.loads(project.screen_path('main').read_text(encoding='utf-8'))
    assert saved['elements'] == []
    assert any(e['id'] == 'box' for e in service.scene['elements'])


def test_open_screen_can_explicitly_save_or_discard_dirty_scene(tmp_path):
    project, service = _service(tmp_path)
    service.call('scene.create_element', {'element': _element('saved')})
    opened = service.call('project.open_screen', {'screen_id': 'second', 'save_current': True})
    assert opened['active_screen'] == 'second'
    saved = json.loads(project.screen_path('main').read_text(encoding='utf-8'))
    assert any(e['id'] == 'saved' for e in saved['elements'])

    service.call('scene.create_element', {'element': _element('discarded')})
    service.call('project.open_screen', {'screen_id': 'main', 'discard_current': True})
    second = json.loads(project.screen_path('second').read_text(encoding='utf-8'))
    assert not any(e.get('id') == 'discarded' for e in second['elements'])
    assert service.call('project.get', {})['dirty'] is False


def test_open_screen_rejects_conflicting_unsaved_policies(tmp_path):
    _, service = _service(tmp_path)
    service.call('scene.create_element', {'element': _element()})
    with pytest.raises(ValueError, match='mutually exclusive'):
        service.call('project.open_screen', {'screen_id': 'second', 'save_current': True, 'discard_current': True})


def test_history_commit_and_rollback_contracts_describe_transaction_param(tmp_path):
    _, service = _service(tmp_path)
    for method in ('history.commit', 'history.rollback'):
        spec = service.call('automation.describe_method', {'method': method})['method']
        assert spec['params']['transaction']['type'] == 'string'
        assert spec['params']['transaction']['required'] is True


def test_bridge_handshake_reports_same_api_version_as_capabilities(tmp_path):
    project, service = _service(tmp_path)
    expected = service.call('automation.capabilities', {})['api_version']
    proc = subprocess.Popen(
        [sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'src' / 'agent_bridge.py'), '--project', str(project.path), '--permission', 'observe', '--port', '0'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = proc.stdout.readline().strip()
        handshake = json.loads(line)
        assert handshake['automation_api'] == expected
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def test_state_count_and_summary_mode_do_not_return_large_frame_lists(tmp_path):
    _, service = _service(tmp_path, many_states=True)
    count = service.call('state.count', {'integer_policy': 'full'})
    assert count['cases'] == 401
    rendered = service.call('render.all_states', {'integer_policy': 'full', 'summary_only': True})
    assert rendered['cases'] == 401
    assert rendered['framebuffer_bytes'] == 64
    assert 'frames' not in rendered
    validated = service.call('validate.all_states', {'integer_policy': 'full', 'summary_only': True})
    assert validated['cases'] == 401
    assert 'cases_with_findings' not in validated


def _wait_job(service, job_id, timeout=10.0):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        status = service.call('job.status', {'job_id': job_id})
        seen.append(status)
        if status['state'] in {'completed', 'failed', 'cancelled'}:
            return status, seen
        time.sleep(0.01)
    raise AssertionError(f'job did not finish: {seen[-1] if seen else None}')


def test_async_job_reports_progress_and_result_matches_sync_summary(tmp_path):
    _, service = _service(tmp_path, many_states=True)
    started = service.call('job.start', {
        'operation': 'render.all_states',
        'arguments': {'integer_policy': 'full', 'summary_only': True},
    })
    assert started['job_id']
    terminal, seen = _wait_job(service, started['job_id'])
    assert terminal['state'] == 'completed'
    completed_values = [row['progress']['completed'] for row in seen]
    assert completed_values == sorted(completed_values)
    result = service.call('job.result', {'job_id': started['job_id']})
    sync = service.call('render.all_states', {'integer_policy': 'full', 'summary_only': True})
    assert result['state'] == 'completed'
    assert result['result']['cases'] == sync['cases']
    assert result['result']['framebuffer_bytes'] == sync['framebuffer_bytes']


def test_job_cancel_is_cooperative(tmp_path):
    _, service = _service(tmp_path, many_states=True)
    started = service.call('job.start', {
        'operation': 'validate.all_states',
        'arguments': {'integer_policy': 'full', 'summary_only': True},
    })
    cancelled = service.call('job.cancel', {'job_id': started['job_id']})
    assert cancelled['cancel_requested'] is True
    terminal, _ = _wait_job(service, started['job_id'])
    assert terminal['state'] in {'cancelled', 'completed'}
    # If it completed before cancellation was observed, it must have completed normally;
    # otherwise cancellation must be an explicit terminal state, never a silent failure.
    if terminal['state'] == 'cancelled':
        result = service.call('job.result', {'job_id': started['job_id']})
        assert result['state'] == 'cancelled'


def test_jsonrpc_unsaved_changes_has_stable_error_code(tmp_path):
    from agent_bridge import dispatch_json_rpc
    _, service = _service(tmp_path)
    service.call('scene.create_element', {'element': _element()})
    response = dispatch_json_rpc(service, {
        'jsonrpc': '2.0', 'id': 1, 'method': 'project.open_screen',
        'params': {'screen_id': 'second'},
    })
    assert response['error']['code'] == 'UNSAVED_CHANGES'
    assert service.call('project.get', {})['active_screen'] == 'main'


def test_save_failure_never_switches_screen(tmp_path, monkeypatch):
    _, service = _service(tmp_path)
    service.call('scene.create_element', {'element': _element()})
    def fail_save():
        raise OSError('disk full')
    monkeypatch.setattr(service, '_save_current_scene', fail_save)
    with pytest.raises(OSError, match='disk full'):
        service.call('project.open_screen', {'screen_id': 'second', 'save_current': True})
    assert service.call('project.get', {})['active_screen'] == 'main'
    assert service.call('project.get', {})['dirty'] is True


def test_export_job_summary_uses_studio_exporter_and_omits_hash_payload(tmp_path):
    _, service = _service(tmp_path)
    started = service.call('job.start', {
        'operation': 'export.all',
        'arguments': {'output_dir': 'exports/job_export', 'summary_only': True},
    })
    terminal, _ = _wait_job(service, started['job_id'])
    assert terminal['state'] == 'completed'
    result = service.call('job.result', {'job_id': started['job_id']})['result']
    assert result['frame_count'] == 1
    assert 'frame_hashes' not in result
    assert Path(result['output_dir']).is_dir()
