from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / 'src'


def _body(source: str, name: str) -> str:
    marker = f'def {name}'
    start = source.index(marker)
    next_start = source.find('\n    def ', start + len(marker))
    if next_start < 0:
        next_start = source.find('\n        def ', start + len(marker))
    return source[start:] if next_start < 0 else source[start:next_start]


def test_window_keeps_project_and_resource_entry_points_as_prefixed_delegates():
    gui = (SRC / 'gui.py').read_text(encoding='utf-8')
    expected = {
        '_confirm_scene_transition': '_project_confirm_scene_transition',
        '_confirm_project_transition': '_project_confirm_project_transition',
        '_close_project_bound_editors': '_project_close_project_bound_editors',
        'open_project_dialog': '_project_open_project_dialog',
        '_load_project_candidate': '_project_load_project_candidate',
        '_remember_last_project': '_project_remember_last_project',
        '_commit_project_candidate': '_project_commit_project_candidate',
        '_open_project': '_project_open_project',
        'new_project': '_project_new_project',
        '_rebuild_screens': '_project_rebuild_screens',
        '_screen_changed': '_project_screen_changed',
        'new_screen': '_project_new_screen',
        'duplicate_screen': '_project_duplicate_screen',
        'delete_screen': '_project_delete_screen',
        'open_scene_dialog': '_project_open_scene_dialog',
    }
    for name, target in expected.items():
        assert f'def {name}' in gui
        assert f'return self.{target}' in _body(gui, name)


def test_project_mixin_preserves_preflight_fallback_and_project_editor_boundaries():
    source = (SRC / 'gui_project_mixin.py').read_text(encoding='utf-8')
    assert 'class ProjectWorkspaceMixin:' in source
    transition = _body(source, '_project_confirm_scene_transition')
    assert 'self.session.document.dirty' in transition
    assert 'QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel' in transition
    assert 'self.save_scene()' in transition
    close = _body(source, '_project_close_project_bound_editors')
    assert "'settings:preferences'" in close
    assert 'editor_registry.close' in close
    open_project = _body(source, '_project_open_project_dialog')
    assert open_project.index('self._load_project_candidate') < open_project.index('self._confirm_project_transition()')
    assert open_project.index('self._confirm_project_transition()') < open_project.index('self._commit_project_candidate')
    screen = _body(source, '_project_screen_changed')
    assert screen.index('load_scene(') < screen.index('self._confirm_scene_transition()')
    assert screen.index('load_scene(') < screen.index('self.project.set_active_screen(sid)')
    delete = _body(source, '_project_delete_screen')
    assert delete.index('load_scene(') < delete.index('self.project.remove_screen(')


def test_resource_mixin_preserves_project_scoped_watchers_and_font_boundaries():
    source = (SRC / 'gui_resource_mixin.py').read_text(encoding='utf-8')
    assert 'class ResourceWorkflowMixin:' in source
    watcher = _body(source, '_resource_sync_asset_directory_watchers')
    assert 'self.asset_library.asset_dirs' in watcher
    assert 'self.asset_library.root' in watcher
    assert 'path.rglob' in watcher
    new_font = _body(source, '_resource_new_font_pack')
    assert "root / 'fontpack.json'" in new_font
    assert 'self._show_error' in new_font
    bitmap = _body(source, '_resource_insert_bitmap_text')
    assert 'relative_to(scene_root(self.scene))' in bitmap
    assert "self.tr('font.inside_project')" in bitmap
