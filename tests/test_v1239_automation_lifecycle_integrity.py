from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
sys.path.insert(0, str(SIM))


def _scene(tmp_path: Path):
    return {
        '_root': str(tmp_path),
        'canvas': {'w': 128, 'h': 32},
        'states': {},
        'timeline': [],
        'elements': [],
    }


def test_pending_bridge_call_expired_before_claim_can_never_dispatch():
    from agent_bridge import PendingBridgeCall

    call = PendingBridgeCall({'jsonrpc': '2.0', 'id': 7, 'method': 'scene.get'})
    assert call.expire_if_queued() is True
    assert call.claim() is False
    assert call.state == 'expired'


def test_pending_bridge_call_started_before_timeout_cannot_be_marked_expired():
    from agent_bridge import PendingBridgeCall

    call = PendingBridgeCall({'jsonrpc': '2.0', 'id': 8, 'method': 'scene.get'})
    assert call.claim() is True
    assert call.expire_if_queued() is False
    response = {'jsonrpc': '2.0', 'id': 8, 'result': {'ok': True}}
    call.complete(response)
    assert call.done.wait(0.1) is True
    assert call.response == response
    assert call.state == 'done'


def test_qt_bridge_integrates_claim_expire_protocol_before_dispatch():
    source = (SIM / 'automation_qt.py').read_text(encoding='utf-8')
    assert 'PendingBridgeCall' in source
    assert 'expire_if_queued()' in source
    drain = source.split('    def _drain(self):', 1)[1]
    assert '.claim()' in drain
    assert drain.index('.claim()') < drain.index('dispatch_json_rpc(')


def _wait_terminal(manager, job_id: str, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = manager.status(job_id)['state']
        if state in {'completed', 'failed', 'cancelled'}:
            return state
        time.sleep(0.005)
    raise AssertionError(f'job {job_id} did not finish')


def test_job_manager_prunes_old_terminal_results_but_keeps_recent_jobs():
    from automation_jobs import AutomationJobManager

    manager = AutomationJobManager(max_terminal_jobs=2)

    def runner(operation, arguments, snapshot, progress, cancel_event):
        progress('done', 1, 1)
        return {'operation': operation}

    ids = []
    for i in range(4):
        jid = manager.start(f'op-{i}', {}, {}, runner)
        _wait_terminal(manager, jid)
        ids.append(jid)

    with pytest.raises(KeyError):
        manager.result(ids[0])
    with pytest.raises(KeyError):
        manager.result(ids[1])
    assert manager.result(ids[2])['state'] == 'completed'
    assert manager.result(ids[3])['state'] == 'completed'


def test_job_pruning_never_evicts_active_jobs():
    from automation_jobs import AutomationJobManager
    from threading import Event

    manager = AutomationJobManager(max_terminal_jobs=1)
    release = Event()

    def slow_runner(operation, arguments, snapshot, progress, cancel_event):
        release.wait(1.0)
        return {'ok': True}

    active = manager.start('slow', {}, {}, slow_runner)
    deadline = time.monotonic() + 1.0
    while manager.status(active)['state'] == 'queued' and time.monotonic() < deadline:
        time.sleep(0.005)

    def quick_runner(operation, arguments, snapshot, progress, cancel_event):
        return {'ok': True}

    for i in range(3):
        jid = manager.start(f'quick-{i}', {}, {}, quick_runner)
        _wait_terminal(manager, jid)

    assert manager.status(active)['state'] == 'running'
    release.set()
    _wait_terminal(manager, active)


def test_automation_service_caps_simultaneous_scene_transactions(tmp_path):
    from automation_service import StudioAutomationService, TransactionError

    service = StudioAutomationService(_scene(tmp_path), max_transactions=2)
    first = service.begin_transaction()
    second = service.begin_transaction()
    with pytest.raises(TransactionError, match='active transaction limit'):
        service.begin_transaction()
    service.rollback_transaction(first)
    third = service.begin_transaction()
    assert third != second


def test_session_events_are_bounded_and_expose_absolute_cursor(tmp_path):
    from automation_service import StudioAutomationService

    service = StudioAutomationService(_scene(tmp_path), event_limit=3)
    for i in range(5):
        service._notify('test.event', value=i)

    assert len(service.events) == 3
    payload = service.call('session.events', {'since': 0})
    assert [e['value'] for e in payload['events']] == [2, 3, 4]
    assert payload['dropped_before'] == 2
    assert payload['retained_from'] == 2
    assert payload['next_cursor'] == 5

    tail = service.call('session.events', {'since': 4})
    assert [e['value'] for e in tail['events']] == [4]
    assert tail['dropped_before'] == 0
    assert tail['next_cursor'] == 5


def test_job_manager_caps_active_threads_and_allows_new_job_after_completion():
    from automation_jobs import AutomationJobManager
    from threading import Event

    manager = AutomationJobManager(max_active_jobs=1, max_terminal_jobs=2)
    release = Event()

    def slow_runner(operation, arguments, snapshot, progress, cancel_event):
        release.wait(1.0)
        return {'ok': True}

    first = manager.start('slow', {}, {}, slow_runner)
    deadline = time.monotonic() + 1.0
    while manager.status(first)['state'] == 'queued' and time.monotonic() < deadline:
        time.sleep(0.005)
    with pytest.raises(RuntimeError, match='active job limit'):
        manager.start('second', {}, {}, slow_runner)
    release.set()
    _wait_terminal(manager, first)
    second = manager.start('second', {}, {}, lambda *_args: {'ok': True})
    _wait_terminal(manager, second)


def test_terminal_job_can_be_explicitly_released():
    from automation_jobs import AutomationJobManager

    manager = AutomationJobManager(max_terminal_jobs=4)
    jid = manager.start('quick', {}, {}, lambda *_args: {'payload': 'large-result'})
    _wait_terminal(manager, jid)
    released = manager.release(jid)
    assert released == {'job_id': jid, 'released': True}
    with pytest.raises(KeyError):
        manager.result(jid)


def test_active_job_cannot_be_released():
    from automation_jobs import AutomationJobManager
    from threading import Event

    manager = AutomationJobManager()
    release = Event()
    jid = manager.start('slow', {}, {}, lambda *_args: (release.wait(1.0), {'ok': True})[1])
    deadline = time.monotonic() + 1.0
    while manager.status(jid)['state'] == 'queued' and time.monotonic() < deadline:
        time.sleep(0.005)
    with pytest.raises(RuntimeError, match='cannot release active job'):
        manager.release(jid)
    release.set()
    _wait_terminal(manager, jid)


def test_automation_api_exposes_job_release(tmp_path):
    from automation_service import METHOD_SPECS, StudioAutomationService

    assert 'job.release' in METHOD_SPECS
    service = StudioAutomationService(_scene(tmp_path))
    jid = service._jobs.start('quick', {}, {}, lambda *_args: {'ok': True})
    _wait_terminal(service._jobs, jid)
    result = service.call('job.release', {'job_id': jid})
    assert result['released'] is True
    with pytest.raises(KeyError):
        service._jobs.result(jid)


def test_domain_dispatchers_do_not_delegate_back_to_the_monolithic_command_handler(tmp_path):
    from automation_service import StudioAutomationService

    service = StudioAutomationService(_scene(tmp_path))

    def legacy_handler(*_args, **_kwargs):
        raise AssertionError('domain dispatcher delegated to legacy command handler')

    service._dispatch_command = legacy_handler

    assert service.call('automation.capabilities')['api_version'] == '1.2.0'
    assert service.call('scene.get')['scene']['canvas'] == {'w': 128, 'h': 32}
    assert service.call('render.current')['framebuffer']['bytes'] == 512
    assert service.call('asset.create', {'path': 'assets/a.png', 'width': 4, 'height': 4})['bytes'] > 0
    assert service.call('session.events')['events'][0]['event'] == 'asset.create'


def test_pixel_document_registry_is_bounded_and_close_releases_capacity(tmp_path):
    from automation_service import StudioAutomationService

    service = StudioAutomationService(_scene(tmp_path), pixel_document_limit=2)
    a = service.call('pixel.create', {'path': 'assets/a.png', 'width': 8, 'height': 8})
    b = service.call('pixel.create', {'path': 'assets/b.png', 'width': 8, 'height': 8})
    with pytest.raises(ValueError, match='pixel document limit'):
        service.call('pixel.create', {'path': 'assets/c.png', 'width': 8, 'height': 8})
    closed = service.call('pixel.close', {'document_id': a['document_id']})
    assert closed['closed'] is True
    c = service.call('pixel.create', {'path': 'assets/c.png', 'width': 8, 'height': 8})
    assert c['document_id'] != b['document_id']


def test_pixel_close_refuses_dirty_document_without_explicit_discard(tmp_path):
    from automation_service import METHOD_SPECS, StudioAutomationService, UnsavedChangesError

    assert 'pixel.close' in METHOD_SPECS
    service = StudioAutomationService(_scene(tmp_path))
    created = service.call('pixel.create', {'path': 'assets/edit.png', 'width': 4, 'height': 4})
    did = created['document_id']
    service.call('pixel.paint', {'document_id': did, 'x': 1, 'y': 1, 'value': 1})
    with pytest.raises(UnsavedChangesError, match='unsaved pixel document'):
        service.call('pixel.close', {'document_id': did})
    assert service.call('pixel.close', {'document_id': did, 'discard': True})['closed'] is True
    with pytest.raises(KeyError):
        service.call('pixel.get_document', {'document_id': did})
