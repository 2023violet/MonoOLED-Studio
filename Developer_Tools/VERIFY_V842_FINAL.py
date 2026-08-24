#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'OLED模拟器'
sys.path.insert(0, str(SIM))

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS, StudioAutomationService, UnsavedChangesError
from project_workspace import ProjectWorkspace, create_project
from scene import load_scene


def service_for(project: ProjectWorkspace) -> StudioAutomationService:
    scene = load_scene(project.screen_path(project.active_screen), project_root=project.root)
    scene['_project_path'] = str(project.path)
    scene['_asset_dirs'] = list(project.asset_dirs)
    scene['_design_rules'] = {}
    return StudioAutomationService(
        scene,
        source_path=project.screen_path(project.active_screen),
        permission='full',
        copy_scene=False,
        project_workspace=project,
    )


def marker_data(path: Path) -> tuple[int, int]:
    raw = json.loads(path.read_text(encoding='utf-8'))
    for element in raw.get('elements', []):
        if element.get('id') == 'marker':
            return int(element['x']), int(element.get('audit_seq', -1))
    raise AssertionError(f'marker missing from {path}')


def wait_job(service: StudioAutomationService, job_id: str, timeout: float = 15.0) -> tuple[dict, list[int]]:
    deadline = time.time() + timeout
    progress = []
    while time.time() < deadline:
        row = service.call('job.status', {'job_id': job_id})
        progress.append(int(row['progress']['completed']))
        if row['state'] in {'completed', 'failed', 'cancelled'}:
            return row, progress
        time.sleep(0.01)
    raise AssertionError(f'job did not reach terminal state: {job_id}')


def main() -> int:
    current_version = (SIM / 'VERSION').read_text(encoding='utf-8').strip()
    assert tuple(map(int, current_version.split('.'))) >= (8, 4, 2)
    assert AUTOMATION_API_VERSION == '1.2.0'
    contract = json.loads((SIM / 'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    assert contract['api_version'] == AUTOMATION_API_VERSION
    assert set(contract['methods']) == set(METHOD_SPECS)
    for name in ('state.count', 'job.start', 'job.status', 'job.result', 'job.cancel'):
        assert name in METHOD_SPECS
    for name in ('history.commit', 'history.rollback'):
        assert contract['methods'][name]['params']['transaction']['required'] is True

    report = {
        'closure': '8.4.2',
        'current_version': current_version,
        'automation_api': AUTOMATION_API_VERSION,
        'method_count': len(METHOD_SPECS),
    }

    with tempfile.TemporaryDirectory(prefix='monooled_v842_') as td:
        root = Path(td)
        project = create_project(root / 'reliability_project', name='Reliability Graduation', canvas=(32, 16))
        project.add_screen('second', label='Second', canvas=(32, 16))
        project.add_screen('third', label='Third', canvas=(32, 16))
        service = service_for(project)

        # Seed one stable editable object on each screen through public Automation API.
        for sid in ('main', 'second', 'third'):
            if project.active_screen != sid:
                service.call('project.open_screen', {'screen_id': sid})
            service.call('scene.create_element', {'element': {'id': 'marker', 'type': 'placeholder', 'x': 0, 'y': 0, 'w': 2, 'h': 2}})
            assert service.call('project.get', {})['dirty'] is True
            service.call('project.save', {})
            assert service.call('project.get', {})['dirty'] is False
        service.call('project.open_screen', {'screen_id': 'main'})

        expected = {'main': (0, -1), 'second': (0, -1), 'third': (0, -1)}
        ids = ('main', 'second', 'third')
        rejected = 0
        for i in range(1000):
            current = service.call('project.get', {})['active_screen']
            value = i % 20
            tx = service.begin_transaction()
            service.call('scene.update_element', {'id': 'marker', 'changes': {'x': value, 'audit_seq': i}}, transaction=tx)
            service.commit_transaction(tx)
            assert service.call('project.get', {})['dirty'] is True
            target = ids[(ids.index(current) + 1) % len(ids)]
            if i % 7 == 0:
                try:
                    service.call('project.open_screen', {'screen_id': target})
                    raise AssertionError('dirty screen switched without explicit policy')
                except UnsavedChangesError:
                    rejected += 1
                assert service.call('project.get', {})['active_screen'] == current
            service.call('project.open_screen', {'screen_id': target, 'save_current': True})
            expected[current] = (value, i)
            assert service.call('project.get', {})['dirty'] is False

        # Explicit discard is deterministic and does not leak the discarded edit to disk.
        current = service.call('project.get', {})['active_screen']
        before_disk = marker_data(project.screen_path(current))
        service.call('scene.update_element', {'id': 'marker', 'changes': {'x': 31}})
        assert service.call('project.get', {})['dirty'] is True
        target = ids[(ids.index(current) + 1) % len(ids)]
        service.call('project.open_screen', {'screen_id': target, 'discard_current': True})
        assert marker_data(project.screen_path(current)) == before_disk

        reopened = ProjectWorkspace.load(project.path)
        for sid, value in expected.items():
            # The explicit discard case intentionally preserves the prior persisted value.
            if sid == current:
                value = before_disk
            assert marker_data(reopened.screen_path(sid)) == value, (sid, value)

        # Long-operation summary/job contract on a bounded matrix.
        service = service_for(reopened)
        service.call('state.set_schema', {'schema': {
            'variables': {'step': {'type': 'int', 'min': 0, 'max': 80, 'init': 0}},
            'relations': [],
        }})
        assert service.call('state.count', {'integer_policy': 'full'})['cases'] == 81
        sync = service.call('render.all_states', {'integer_policy': 'full', 'summary_only': True})
        assert sync['cases'] == 81 and sync['framebuffer_bytes'] == 64 and 'frames' not in sync
        jid = service.call('job.start', {'operation': 'render.all_states', 'arguments': {'integer_policy': 'full', 'summary_only': True}})['job_id']
        terminal, progress = wait_job(service, jid)
        assert terminal['state'] == 'completed'
        assert progress == sorted(progress)
        async_result = service.call('job.result', {'job_id': jid})
        assert async_result['result']['cases'] == sync['cases']
        assert async_result['result']['framebuffer_bytes'] == sync['framebuffer_bytes']

        # CLI bridge handshake must report the same public API version as capabilities.
        proc = subprocess.Popen(
            [sys.executable, '-B', str(SIM / 'agent_bridge.py'), '--project', str(reopened.path), '--permission', 'observe', '--port', '0'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            handshake = json.loads(proc.stdout.readline().strip())
            assert handshake['automation_api'] == AUTOMATION_API_VERSION
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=3)

        report['data_safety'] = {
            'cross_screen_iterations': 1000,
            'unsaved_switches_rejected': rejected,
            'silent_data_loss': 0,
            'save_current': 'PASS',
            'discard_current': 'PASS',
            'fresh_reopen': 'PASS',
        }
        report['long_jobs'] = {
            'state_count': 81,
            'summary_mode': 'PASS',
            'job_progress_monotonic': 'PASS',
            'stable_job_fields_match_sync': 'PASS',
        }
        report['contract'] = {
            'history_transaction_params': 'PASS',
            'bridge_handshake_version': 'PASS',
        }

    target = SIM / 'reports' / 'v842_final_report.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
