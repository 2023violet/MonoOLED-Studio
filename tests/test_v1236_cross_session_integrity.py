from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))


def test_preferences_set_save_failure_rolls_back_in_memory(tmp_path, monkeypatch):
    from preferences import PreferencesStore, default_preferences

    store = PreferencesStore(tmp_path / 'prefs.json', default_preferences())
    before = copy.deepcopy(store.data)
    monkeypatch.setattr(store, 'save', lambda: (_ for _ in ()).throw(OSError('disk full')))

    with pytest.raises(OSError, match='disk full'):
        store.set('appearance.theme_mode', 'dark', save=True)

    assert store.data == before


def test_preferences_reset_section_save_failure_rolls_back_in_memory(tmp_path, monkeypatch):
    from preferences import PreferencesStore, default_preferences

    data = default_preferences(); data['appearance']['theme_mode'] = 'dark'
    store = PreferencesStore(tmp_path / 'prefs.json', data)
    before = copy.deepcopy(store.data)
    monkeypatch.setattr(store, 'save', lambda: (_ for _ in ()).throw(OSError('disk full')))

    with pytest.raises(OSError, match='disk full'):
        store.reset_section('appearance')

    assert store.data == before


def test_project_rejects_case_insensitive_screen_id_collisions(tmp_path):
    from project_workspace import ProjectWorkspace, PROJECT_FILENAME

    root = tmp_path / 'demo'; root.mkdir(); (root / 'scenes').mkdir()
    for name in ('HOME.json', 'home.json'):
        (root / 'scenes' / name).write_text(json.dumps({'schema_version': 1, 'canvas': {'w': 128, 'h': 32}, 'elements': [], 'states': {}, 'timeline': []}), encoding='utf-8')
    payload = {
        'schema_version': 1, 'name': 'Demo', 'default_canvas': [128, 32],
        'active_screen': 'HOME', 'asset_dirs': ['assets'],
        'screens': [
            {'id': 'HOME', 'label': 'HOME', 'path': 'scenes/HOME.json'},
            {'id': 'home', 'label': 'home', 'path': 'scenes/home.json'},
        ],
    }
    path = root / PROJECT_FILENAME; path.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ValueError, match='case-insensitive|collision|duplicate'):
        ProjectWorkspace.load(path)


def test_project_rejects_case_insensitive_duplicate_screen_paths(tmp_path):
    from project_workspace import ProjectWorkspace, PROJECT_FILENAME

    root = tmp_path / 'demo'; root.mkdir(); (root / 'scenes').mkdir()
    (root / 'scenes' / 'main.json').write_text(json.dumps({'schema_version': 1, 'canvas': {'w': 128, 'h': 32}, 'elements': [], 'states': {}, 'timeline': []}), encoding='utf-8')
    payload = {
        'schema_version': 1, 'name': 'Demo', 'default_canvas': [128, 32],
        'active_screen': 'one', 'asset_dirs': ['assets'],
        'screens': [
            {'id': 'one', 'label': 'One', 'path': 'scenes/main.json'},
            {'id': 'two', 'label': 'Two', 'path': 'scenes/MAIN.json'},
        ],
    }
    path = root / PROJECT_FILENAME; path.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ValueError, match='path.*collision|duplicate.*path|case-insensitive'):
        ProjectWorkspace.load(path)


def test_same_id_screen_label_change_rolls_back_on_save_failure(tmp_path, monkeypatch):
    from project_workspace import create_project

    project = create_project(tmp_path / 'demo', name='Demo')
    before = copy.deepcopy(project.data)
    monkeypatch.setattr(project, 'save', lambda: (_ for _ in ()).throw(OSError('disk full')))

    with pytest.raises(OSError, match='disk full'):
        project.rename_screen('main', new_id='main', label='Renamed')

    assert project.data == before


def test_invalid_last_project_is_ignored_before_window_construction(tmp_path):
    import gui

    bad = tmp_path / 'broken.oled.json'; bad.write_text('{broken', encoding='utf-8')
    assert gui._validated_last_project_source(str(bad)) is None


def test_valid_last_project_is_selected_after_validation(tmp_path):
    from project_workspace import create_project
    import gui

    project = create_project(tmp_path / 'demo', name='Demo')
    assert gui._validated_last_project_source(str(project.path)) == str(project.path)


def test_atomic_write_uses_unique_temp_files_for_same_target(tmp_path, monkeypatch):
    import atomic_io

    target = tmp_path / 'artifact.bin'
    seen = []
    real_replace = atomic_io.os.replace

    def capture_replace(src, dst):
        seen.append(Path(src).name)
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, 'replace', capture_replace)
    atomic_io.atomic_write_bytes(target, b'one')
    atomic_io.atomic_write_bytes(target, b'two')

    assert target.read_bytes() == b'two'
    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert all(name.endswith('.tmp') for name in seen)


def _function_body(source: str, name: str) -> str:
    marker = f'def {name}('
    start = source.index(marker)
    lines = source[start:].splitlines()
    base = len(lines[0]) - len(lines[0].lstrip())
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= base and line.lstrip().startswith(('def ', 'class ')):
            break
        body.append(line)
    return '\n'.join(body)


def test_shutdown_session_markdown_failure_is_nonfatal_contract():
    source = (SRC / 'gui.py').read_text(encoding='utf-8')
    body = _function_body(source, 'closeEvent')
    assert 'SESSION_REPORT_FAIL' in body
    assert 'except' in body[body.index('write_markdown'):]
    assert body.index('event.accept()') > body.index('write_markdown')


def test_shortcut_repair_persistence_failure_is_nonfatal_during_startup():
    source = (SRC / 'gui.py').read_text(encoding='utf-8')
    region = source[source.index('if rejected:'):source.index('self._preferences_window')]
    assert 'SHORTCUT_REPAIR_SAVE_FAIL' in region
    assert 'try:' in region and 'except OSError' in region


def test_scene_save_refuses_to_overwrite_external_modification(tmp_path):
    from document import SceneDocument, ExternalModificationError

    target = tmp_path / 'scene.json'
    original = {'schema_version': 1, 'canvas': {'w': 128, 'h': 32}, 'elements': [{'id': 'a', 'x': 0}], 'states': {}, 'timeline': []}
    target.write_text(json.dumps(original), encoding='utf-8')
    scene = copy.deepcopy(original); scene['_path'] = str(target)
    doc = SceneDocument(scene)
    doc.set_field('a', 'x', 1)
    external = dict(original); external['product'] = 'changed-elsewhere'
    target.write_text(json.dumps(external), encoding='utf-8')

    with pytest.raises(ExternalModificationError, match='externally modified'):
        doc.save()

    assert json.loads(target.read_text(encoding='utf-8'))['product'] == 'changed-elsewhere'
    assert doc.dirty is True


def test_scene_save_refreshes_disk_fingerprint_after_success(tmp_path):
    from document import SceneDocument

    target = tmp_path / 'scene.json'
    original = {'schema_version': 1, 'canvas': {'w': 128, 'h': 32}, 'elements': [{'id': 'a', 'x': 0}], 'states': {}, 'timeline': []}
    target.write_text(json.dumps(original), encoding='utf-8')
    scene = copy.deepcopy(original); scene['_path'] = str(target)
    doc = SceneDocument(scene)
    doc.set_field('a', 'x', 1); doc.save()
    doc.set_field('a', 'x', 2); doc.save()
    assert json.loads(target.read_text(encoding='utf-8'))['elements'][0]['x'] == 2


def test_project_save_refuses_to_overwrite_external_manifest_change(tmp_path):
    from project_workspace import create_project, ExternalProjectModificationError

    project = create_project(tmp_path / 'demo', name='Demo')
    disk = json.loads(project.path.read_text(encoding='utf-8'))
    disk['external_note'] = 'other-instance'
    project.path.write_text(json.dumps(disk), encoding='utf-8')
    project.data['name'] = 'Local change'

    with pytest.raises(ExternalProjectModificationError, match='externally modified'):
        project.save()

    assert json.loads(project.path.read_text(encoding='utf-8'))['external_note'] == 'other-instance'


def test_project_save_refreshes_disk_fingerprint_after_success(tmp_path):
    from project_workspace import create_project

    project = create_project(tmp_path / 'demo', name='Demo')
    project.data['name'] = 'One'; project.save()
    project.data['name'] = 'Two'; project.save()
    assert json.loads(project.path.read_text(encoding='utf-8'))['name'] == 'Two'


def test_preferences_save_uses_unique_temp_siblings(tmp_path, monkeypatch):
    import preferences
    from preferences import PreferencesStore, default_preferences

    store = PreferencesStore(tmp_path / 'prefs.json', default_preferences())
    seen=[]; real_replace=preferences.os.replace
    def capture(src,dst):
        seen.append(Path(src).name); return real_replace(src,dst)
    monkeypatch.setattr(preferences.os,'replace',capture)
    store.save(); store.save()
    assert seen[0] != seen[1]
    assert all(name.endswith('.tmp') for name in seen)


def test_project_manifest_save_uses_unique_temp_siblings(tmp_path, monkeypatch):
    import project_workspace
    from project_workspace import create_project

    project=create_project(tmp_path/'demo',name='Demo')
    seen=[]; real_replace=project_workspace.os.replace
    def capture(src,dst):
        if Path(dst)==project.path: seen.append(Path(src).name)
        return real_replace(src,dst)
    monkeypatch.setattr(project_workspace.os,'replace',capture)
    project.data['name']='A'; project.save(); project.data['name']='B'; project.save()
    assert len(seen)==2 and seen[0] != seen[1]


def test_remaining_persistent_writers_use_unique_temp_siblings():
    for name in ('asset_library.py', 'autosave.py', 'handoff.py'):
        source=(SRC/name).read_text(encoding='utf-8')
        assert 'unique_temp_path' in source, name
        assert "with_name(target.name+'.tmp')" not in source
        assert "with_name(target.name + '.tmp')" not in source


def test_session_log_filename_has_subsecond_and_process_uniqueness_contract():
    source=(SRC/'gui.py').read_text(encoding='utf-8')
    region=source[source.index("stamp = datetime.now().strftime"):source.index('self.logger = SessionLogger')]
    assert '%f' in region
    assert 'os.getpid()' in region


def test_session_markdown_skips_truncated_jsonl_lines_instead_of_failing(tmp_path):
    from session_log import SessionLogger

    log=tmp_path/'session.jsonl'
    log.write_text('{"ts":"t","seq":1,"event":"OK"}\n{"ts":',encoding='utf-8')
    logger=SessionLogger(log); logger.close()
    out=tmp_path/'session.md'
    logger.write_markdown(out)
    text=out.read_text(encoding='utf-8')
    assert '**OK**' in text
    assert 'corrupt' in text.casefold() or 'skipped' in text.casefold()
