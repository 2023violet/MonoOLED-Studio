from __future__ import annotations

import copy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'


def _text(name: str) -> str:
    return (SRC / name).read_text(encoding='utf-8')


def _function_body(source: str, name: str) -> str:
    marker = f'        def {name}'
    start = source.index(marker)
    rest = source[start + len(marker):]
    next_pos = rest.find('\n        def ')
    return source[start:] if next_pos < 0 else source[start:start + len(marker) + next_pos]


def test_command_palette_routes_save_undo_redo_to_active_editor():
    body = _function_body(_text('gui.py'), 'show_command_palette')
    assert "('save',self.tr('action.save'),self.route_save)" in body
    assert "('undo',self.tr('action.undo'),self.route_undo)" in body
    assert "('redo',self.tr('action.redo'),self.route_redo)" in body
    assert "('save',self.tr('action.save'),self.save_scene)" not in body


def test_pixel_open_image_guards_dirty_document_before_replacement():
    source = _text('pixel_studio_qt.py')
    body = source[source.index('    def open_image(self):'):source.index('    def _document_changed', source.index('    def open_image(self):'))]
    assert 'self.document.dirty' in body
    assert 'QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel' in body
    assert 'if choice==QMessageBox.Cancel:return' in body
    assert 'if choice==QMessageBox.Save and not self.save():return' in body
    assert body.index('self.document.dirty') < body.index('self.path=Path(path)')
    assert 'self.documentIdentityChanged.emit(str(self.path))' in body


def test_restore_autosave_uses_scene_transition_guard_before_replacing_session():
    body = _function_body(_text('gui.py'), 'restore_autosave')
    assert 'self._confirm_scene_transition()' in body
    assert body.index('self._confirm_scene_transition()') < body.index('self._reset_session(payload)')
    assert 'except Exception as exc' in body


def test_screen_change_preloads_scene_before_mutating_project_active_screen():
    body = _function_body(_text('gui.py'), '_screen_changed')
    assert 'candidate=' in body and 'load_scene(' in body
    assert body.index('load_scene(') < body.index('self.project.set_active_screen(sid)')
    assert 'old_sid=' in body
    assert 'self.project.set_active_screen(old_sid)' in body
    assert 'except Exception as exc' in body


def test_remove_screen_rolls_back_manifest_and_preserves_scene_if_manifest_save_fails(tmp_path, monkeypatch):
    from project_workspace import create_project

    project = create_project(tmp_path / 'demo', name='Demo')
    project.add_screen('second', label='Second', canvas=(128, 32))
    project.set_active_screen('second')
    project.save()
    target = project.screen_path('second')
    before_data = copy.deepcopy(project.data)
    before_bytes = target.read_bytes()

    real_save = project.save
    calls = {'n': 0}

    def failing_save():
        calls['n'] += 1
        raise OSError('disk full')

    monkeypatch.setattr(project, 'save', failing_save)
    with pytest.raises(OSError, match='disk full'):
        project.remove_screen('second')

    assert project.data == before_data
    assert target.exists()
    assert target.read_bytes() == before_bytes

    monkeypatch.setattr(project, 'save', real_save)
    project.save()


def test_pixel_identity_change_is_rekeyed_without_fake_save_side_effects():
    source=_text('gui.py')
    open_body=_function_body(source,'open_pixel_studio')
    assert 'documentIdentityChanged.connect' in open_body
    handler=_function_body(source,'_pixel_editor_identity_changed')
    assert 'self.editor_registry.rekey(editor)' in handler
    assert "PIXEL_ASSET_SAVED" not in handler


def test_screen_switch_validates_target_before_unsaved_prompt():
    body=_function_body(_text('gui.py'),'_screen_changed')
    assert body.index('load_scene(') < body.index('self._confirm_scene_transition()')


def test_open_scene_validates_target_before_unsaved_prompt():
    body=_function_body(_text('gui.py'),'open_scene_dialog')
    assert body.index('load_scene(') < body.index('self._confirm_project_transition()')


def test_open_project_validates_target_before_unsaved_prompt():
    body=_function_body(_text('gui.py'),'open_project_dialog')
    assert '_load_project_candidate' in body
    assert body.index('_load_project_candidate') < body.index('self._confirm_project_transition()')
    loader=_function_body(_text('gui.py'),'_load_project_candidate')
    assert 'ProjectWorkspace.load(path)' in loader
    assert 'load_scene(' in loader


def test_startup_recovery_handles_snapshot_race_or_read_failure():
    body=_function_body(_text('gui.py'),'_prompt_recovery_if_needed')
    assert 'try:payload=AutoSaveManager.load_snapshot(candidate)' in body
    assert 'except Exception as exc:self._show_error(str(exc));return' in body


def test_shutdown_preferences_persistence_failure_does_not_crash_close_event():
    body=_function_body(_text('gui.py'),'closeEvent')
    assert "PREFERENCES_SAVE_FAIL" in body
    assert 'except OSError as exc' in body


def test_add_screen_rolls_back_manifest_and_orphan_file_on_save_failure(tmp_path, monkeypatch):
    from project_workspace import create_project
    project=create_project(tmp_path/'demo',name='Demo')
    before=copy.deepcopy(project.data)
    target=project.root/'scenes'/'second.json'
    monkeypatch.setattr(project,'save',lambda: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError,match='disk full'):
        project.add_screen('second',label='Second',canvas=(128,32))
    assert project.data==before
    assert not target.exists()


def test_set_asset_dirs_rolls_back_in_memory_on_save_failure(tmp_path, monkeypatch):
    from project_workspace import create_project
    project=create_project(tmp_path/'demo',name='Demo')
    before=copy.deepcopy(project.data)
    monkeypatch.setattr(project,'save',lambda: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError,match='disk full'):
        project.set_asset_dirs(['assets','more-assets'])
    assert project.data==before


def test_delete_screen_preloads_fallback_before_removing_current_screen():
    body=_function_body(_text('gui.py'),'delete_screen')
    assert 'fallback_sid=' in body
    assert 'candidate=' in body and 'load_scene(' in body
    assert body.index('load_scene(') < body.index('self.project.remove_screen(')


def test_last_project_preference_persistence_is_nonfatal_and_shared():
    source=_text('gui.py')
    helper=_function_body(source,'_remember_last_project')
    assert "save=False" in helper
    assert 'except OSError as exc' in helper
    assert "PREFERENCES_SAVE_FAIL" in helper
    commit=_function_body(source,'_commit_project_candidate')
    assert 'self._remember_last_project(str(project.path))' in commit
    scene=_function_body(source,'open_scene_dialog')
    assert "self._remember_last_project('')" in scene


def test_new_font_pack_refuses_to_overwrite_existing_manifest_and_handles_io_errors():
    body=_function_body(_text('gui.py'),'new_font_pack')
    assert "fontpack.json" in body
    assert 'if (root/\'fontpack.json\').exists()' in body
    assert 'except Exception as exc:self._show_error(str(exc));return' in body


def test_open_font_lab_requires_existing_manifest_and_catches_constructor_errors():
    body=_function_body(_text('gui.py'),'open_font_lab')
    assert "manifest=root/'fontpack.json'" in body
    assert 'if not manifest.exists()' in body
    assert 'try:editor=FontLabEditor(' in body
    assert 'except Exception as exc:self._show_error(str(exc));return' in body


def test_main_open_pixel_studio_catches_corrupt_image_constructor_error():
    body=_function_body(_text('gui.py'),'open_pixel_studio')
    assert 'try:editor=PixelStudioWindow(' in body
    assert 'except Exception as exc:self._show_error(str(exc));return None' in body


def test_bitmap_text_insert_surfaces_element_validation_errors_instead_of_leaking():
    body=_function_body(_text('gui.py'),'insert_bitmap_text')
    assert 'try:self.session.add_elements(' in body
    assert 'except Exception as exc:self._show_error(str(exc));return' in body


def test_editor_session_batch_remove_is_atomic_and_one_undo_step(tmp_path):
    import json
    from editor_model import EditorSession
    scene_path=tmp_path/'scene.json'
    scene={
        'schema_version':1,'product':'T','canvas':{'w':128,'h':32},
        'storage':{'layout':'VLSB column-page (SSD1306)','bytes_per_frame':512,'polarity':'1 = lit'},
        'states':{},'timeline':[],
        'elements':[{'id':'a','type':'placeholder','x':0,'y':0,'w':1,'h':1},{'id':'b','type':'placeholder','x':1,'y':0,'w':1,'h':1},{'id':'c','type':'placeholder','x':2,'y':0,'w':1,'h':1}],
        '_path':str(scene_path),'_root':str(tmp_path),
    }
    scene_path.write_text(json.dumps({k:v for k,v in scene.items() if not k.startswith('_')}),encoding='utf-8')
    session=EditorSession(scene)
    session.remove_elements(['a','c'])
    assert [e['id'] for e in scene['elements']]==['b']
    assert session.undo() is True
    assert [e['id'] for e in scene['elements']]==['a','b','c']
    assert session.redo() is True
    assert [e['id'] for e in scene['elements']]==['b']


def test_gui_multi_delete_uses_batch_remove_and_surfaces_errors():
    body=_function_body(_text('gui.py'),'remove_selected')
    assert 'self.session.remove_elements(self.selected_ids)' in body
    assert 'for eid in list(self.selected_ids):self.session.remove_element(eid)' not in body
    assert 'except Exception as exc:self._show_error(str(exc));return' in body


def test_batch_edit_rolls_back_partial_mutation_when_mutator_raises(tmp_path):
    import json
    from editor_model import EditorSession
    scene_path=tmp_path/'scene.json'
    scene={
        'schema_version':1,'product':'T','canvas':{'w':128,'h':32},
        'storage':{'layout':'VLSB column-page (SSD1306)','bytes_per_frame':512,'polarity':'1 = lit'},
        'states':{},'timeline':[],
        'elements':[{'id':'a','type':'placeholder','x':0,'y':0,'w':1,'h':1},{'id':'b','type':'placeholder','x':1,'y':0,'w':1,'h':1}],
        '_path':str(scene_path),'_root':str(tmp_path),
    }
    scene_path.write_text(json.dumps({k:v for k,v in scene.items() if not k.startswith('_')}),encoding='utf-8')
    session=EditorSession(scene)
    before=copy.deepcopy(scene['elements'])
    with pytest.raises(KeyError):
        session.set_locked(['a','missing'],True)
    assert scene['elements']==before
    assert session.document.dirty is False
    assert session.undo() is False


def test_add_screen_refuses_to_overwrite_untracked_existing_scene_file(tmp_path):
    from project_workspace import create_project
    project=create_project(tmp_path/'demo',name='Demo')
    target=project.root/'scenes'/'second.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('DO-NOT-OVERWRITE',encoding='utf-8')
    with pytest.raises(FileExistsError):
        project.add_screen('second',label='Second',canvas=(128,32))
    assert target.read_text(encoding='utf-8')=='DO-NOT-OVERWRITE'
    assert all(ref.id!='second' for ref in project.screens)


def test_create_project_refuses_to_overwrite_existing_project_manifest(tmp_path):
    from project_workspace import PROJECT_FILENAME, create_project
    root=tmp_path/'existing'
    root.mkdir()
    manifest=root/PROJECT_FILENAME
    manifest.write_text('KEEP-ME',encoding='utf-8')
    with pytest.raises(FileExistsError):
        create_project(root,name='New')
    assert manifest.read_text(encoding='utf-8')=='KEEP-ME'


def test_pixel_open_and_save_as_block_paths_already_open_in_sibling_editor():
    source=_text('pixel_studio_qt.py')
    assert 'def _path_conflicts_with_open_editor(self,path):' in source
    open_body=source[source.index('    def open_image(self):'):source.index('    def _document_changed',source.index('    def open_image(self):'))]
    save_body=source[source.index('    def save_png(self):'):source.index('    def save_bin',source.index('    def save_png(self):'))]
    assert 'self._path_conflicts_with_open_editor(path)' in open_body
    assert open_body.index('self._path_conflicts_with_open_editor(path)') < open_body.index('self.path=Path(path)')
    assert 'self._path_conflicts_with_open_editor(path)' in save_body
    assert save_body.index('self._path_conflicts_with_open_editor(path)') < save_body.index('self.document.save_png(path)')
