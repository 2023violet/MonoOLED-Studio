from pathlib import Path
import json
import sys

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from project_workspace import ProjectWorkspace, create_project


def test_create_project_and_manage_multiple_screens(tmp_path):
    root = tmp_path / 'demo'
    project = create_project(root, name='Demo OLED', canvas=(128, 32))
    assert project.path == root / 'project.oled.json'
    assert project.name == 'Demo OLED'
    assert [s.id for s in project.screens] == ['main']
    assert project.screen_path('main').exists()

    second = project.duplicate_screen('main', new_id='running', label='Running')
    assert second.id == 'running'
    assert project.screen_path('running').exists()
    project.set_active_screen('running')
    project.save()

    loaded = ProjectWorkspace.load(project.path)
    assert loaded.active_screen == 'running'
    assert [s.id for s in loaded.screens] == ['main', 'running']


def test_project_rejects_duplicate_screen_ids_and_keeps_relative_paths(tmp_path):
    project = create_project(tmp_path / 'p', name='P', canvas=(96, 16))
    try:
        project.duplicate_screen('main', new_id='main')
    except ValueError as exc:
        assert 'duplicate screen id' in str(exc)
    else:
        raise AssertionError('duplicate id must be rejected')
    payload = json.loads(project.path.read_text(encoding='utf-8'))
    assert payload['screens'][0]['path'] == 'scenes/main.json'
