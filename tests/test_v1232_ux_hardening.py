from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'


def read(name: str) -> str:
    return (SRC / name).read_text(encoding='utf-8')


def test_settings_search_scrolls_matched_row_and_searches_help_text_without_geometry_changing_highlight():
    prefs = read('preferences_qt.py')
    assert 'self._search_rows' in prefs
    body = prefs.split('    def _search_changed(self, text: str):', 1)[1].split('\n    def ', 1)[0]
    assert 'help_label.text()' in body
    assert 'ensureWidgetVisible' in body
    assert "setProperty('searchMiss'" in body
    qss = read('qt_theme.py')
    search_match = qss.split('QLabel#SearchMatch', 1)[1].split('}', 1)[0]
    assert 'padding:' not in search_match
    assert 'QLineEdit#SettingsSearch[searchMiss="true"]' in qss


def test_setting_rows_associate_labels_help_and_controls_for_accessibility_and_focus():
    prefs = read('preferences_qt.py')
    body = prefs.split('    def _setting_row(', 1)[1].split('\n    def ', 1)[0]
    assert 'label.setBuddy(widget)' in body
    helper = prefs.split('    def _sync_row_accessibility(', 1)[1].split('\n    def ', 1)[0]
    assert 'row.control.setAccessibleName' in helper
    assert 'row.control.setAccessibleDescription' in helper
    retranslate = prefs.split('    def _retranslate(self):', 1)[1].split('\n    def ', 1)[0]
    assert '_sync_row_accessibility' in retranslate


def test_settings_search_supports_ctrl_f_and_escape_clear():
    prefs = read('preferences_qt.py')
    assert 'QKeySequence' in prefs
    assert 'QShortcut' in prefs
    assert 'QKeySequence.Find' in prefs
    event_filter = prefs.split('    def eventFilter(self, watched, event):', 1)[1].split('\n    def ', 1)[0]
    assert 'watched is self.search' in event_filter
    assert 'Qt.Key_Escape' in event_filter
    assert 'self.search.clear()' in event_filter


def test_shortcut_conflict_marks_originating_field_and_scrolls_feedback_into_view():
    prefs = read('preferences_qt.py')
    body = prefs.split('    def _shortcuts_changed(self):', 1)[1].split('\n    def ', 1)[0]
    assert "setProperty('validationState','error')" in body
    assert 'ensureWidgetVisible(self.shortcut_error' in body
    assert "setProperty('validationState','')" in body
    qss = read('qt_theme.py')
    assert 'QLineEdit[validationState="error"]' in qss


def test_studio_select_keyboard_contract_is_owned_by_the_actual_focus_button():
    controls = read('ui_controls.py')
    init = controls.split('    class StudioSelect(QWidget):', 1)[1].split('        @property\n        def popup_state', 1)[0]
    assert 'self.setFocusProxy(self.button)' in init
    event_filter = controls.split('        def eventFilter(self, obj, event):', 1)[1].split('\n        def ', 1)[0]
    assert 'QEvent.KeyPress' in event_filter
    assert 'Qt.Key_Down' in event_filter
    assert 'Qt.Key_Return' in event_filter
    assert 'Qt.Key_Escape' in event_filter


def test_preferences_save_failure_has_visible_nonblocking_feedback_and_retry_path():
    prefs = read('preferences_qt.py')
    assert "'status.failed'" in prefs
    body = prefs.split('    def _save_now(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'except OSError' in body
    assert "_set_save_state('failed')" in body
    assert 'self._last_save_error' in body
    qss = read('qt_theme.py')
    assert 'QLabel#SettingsSaveStatus[saveState="failed"]' in qss


def test_navigation_selected_rail_reserves_border_width_to_avoid_text_jitter():
    qss = read('qt_theme.py')
    assert 'QListWidget#PreferencesNavigation::item {{' in qss
    assert 'border-left: 2px solid transparent' in qss
    assert 'QListWidget#PreferencesNavigation::item:selected {{' in qss
    assert "border-left: 2px solid {c['accent.primary']}" in qss


def test_settings_find_shortcut_is_scoped_to_the_preferences_view_not_the_whole_window():
    prefs = read('preferences_qt.py')
    assert 'Qt.WidgetWithChildrenShortcut' in prefs
    assert 'self._find_shortcut.setContext' in prefs


def test_settings_search_indexes_both_supported_languages_for_each_row():
    prefs = read('preferences_qt.py')
    assert 'self._search_aliases_by_row' in prefs
    row = prefs.split('    def _setting_row(', 1)[1].split('\n    def ', 1)[0]
    assert "for lang in ('zh_CN','en_US')" in row
    search = prefs.split('    def _search_changed(self, text: str):', 1)[1].split('\n    def ', 1)[0]
    assert 'self._search_aliases_by_row.get(row' in search


def test_settings_toggle_tracks_the_previous_editor_by_document_id_not_fragile_tab_index():
    gui = read('gui.py')
    toggle = gui.split('        def toggle_preferences(', 1)[1].split('\n        def ', 1)[0]
    assert '_last_work_editor_doc_id' in toggle
    assert '_last_work_editor_index' not in toggle
    opened = gui.split('        def open_preferences(', 1)[1].split('\n        def ', 1)[0]
    assert '_last_work_editor_doc_id' in opened
    changed = gui.split('        def _editor_tab_changed(', 1)[1].split('\n        def ', 1)[0]
    assert 'self._editor_tab_changed_impl(index)' in changed


def test_retranslation_preserves_the_users_current_preferences_shortcut_in_tooltip():
    gui = read('gui.py')
    body = gui.split('        def retranslate_ui(self):', 1)[1].split('\n        def ', 1)[0]
    assert "self.command_registry.shortcut('preferences.open')" in body
    assert "t('action.preferences')+' (Ctrl+,)'" not in body


def test_reset_all_uses_the_same_save_error_feedback_and_text_layout_settle_path():
    prefs = read('preferences_qt.py')
    body = prefs.split('    def _reset_all(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'self._save_now()' in body
    assert 'self.store.save()' not in body
    assert 'self._settle_after_text_change()' in body


def test_search_miss_and_save_failure_expose_nonlayout_feedback_for_accessibility_and_diagnostics():
    prefs = read('preferences_qt.py')
    assert "'search.no_results'" in prefs
    search = prefs.split('    def _search_changed(self, text: str):', 1)[1].split('\n    def ', 1)[0]
    assert 'self.search.setAccessibleDescription' in search
    assert 'self.search.setToolTip' in search
    save = prefs.split('    def _set_save_state(self,state: str):', 1)[1].split('\n    def ', 1)[0]
    assert 'self.save_status.setToolTip' in save
    assert 'self.save_status.setAccessibleDescription' in save


def test_language_retranslation_updates_scene_and_font_editor_tab_titles_not_only_settings():
    gui = read('gui.py')
    body = gui.split('        def retranslate_ui(self):', 1)[1].split('\n        def ', 1)[0]
    assert "doc_id=='scene:active'" in body
    assert "doc_id.startswith('font:')" in body
    assert "t('panel.fonts')" in body
    open_font = gui.split('        def open_font_lab(self,root=None):', 1)[1].split('\n        def ', 1)[0]
    assert 'self._editor_open_font_lab(root)' in open_font


def test_pixel_document_save_png_never_overwrites_non_png_source(tmp_path):
    from pixel_studio import PixelDocument
    source = tmp_path / 'imported.jpg'
    source.write_bytes(b'ORIGINAL-JPEG-SENTINEL')
    doc = PixelDocument(8, 8)
    result = doc.save_png(source)
    assert result == tmp_path / 'imported.png'
    assert source.read_bytes() == b'ORIGINAL-JPEG-SENTINEL'
    assert result.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_pixel_studio_save_reuses_only_png_paths_and_prompts_for_imported_formats():
    source = read('pixel_studio_qt.py')
    body = source.split('    def save_png(self):', 1)[1].split('\n    def ', 1)[0]
    assert ".suffix.lower()=='.png'" in body or ".suffix.lower() == '.png'" in body
    assert "self._pick(save=True" in body


def test_editor_registry_rekeys_saved_as_editor_without_leaving_stale_identity():
    from workspace_host import EditorRegistry

    class Editor:
        document_id = 'asset:/tmp/source.jpg'

    editor = Editor()
    registry = EditorRegistry()
    registry.open(editor)
    editor.document_id = 'asset:/tmp/source.png'
    registry.rekey(editor)
    assert registry.get('asset:/tmp/source.jpg') is None
    assert registry.get('asset:/tmp/source.png') is editor
    assert registry.active_id == 'asset:/tmp/source.png'


def test_pixel_asset_save_callback_rekeys_host_registry_after_save_as():
    source = read('gui.py')
    body = source.split('        def _pixel_asset_saved(self,path', 1)[1].split('\n        def ', 1)[0]
    assert 'self._editor_pixel_asset_saved(path, editor)' in body


def test_editor_dirty_helper_prefers_editor_level_dirty_state_for_font_lab_metrics():
    from workspace_host import editor_is_dirty

    class Document:
        dirty = False

    class Editor:
        document = Document()
        dirty = True

    assert editor_is_dirty(Editor()) is True


def test_close_editor_rechecks_dirty_after_save_and_aborts_if_save_was_cancelled():
    source = read('gui.py')
    body = source.split('        def _close_editor_tab(self,index):', 1)[1].split('\n        def ', 1)[0]
    assert 'editor_is_dirty(widget)' in body
    assert body.count('editor_is_dirty(widget)') >= 2
    assert 'except Exception as exc' in body


def test_font_lab_marks_pack_metric_edits_dirty_until_saved():
    source = read('font_lab_qt.py')
    assert 'def _metrics_changed' in source
    assert 'self.baseline.valueChanged.connect(self._metrics_changed)' in source
    assert 'self.advance.valueChanged.connect(self._metrics_changed)' in source
    body = source.split('    def _metrics_changed', 1)[1].split('\n    def ', 1)[0]
    assert 'self.pack.baseline' in body and 'self.pack.advance' in body


def test_main_window_exit_checks_dirty_embedded_editors_before_closing():
    source = read('gui.py')
    assert 'def _confirm_open_editor_changes(self):' in source
    helper = source.split('        def _confirm_open_editor_changes(self):', 1)[1].split('\n        def ', 1)[0]
    assert 'editor_is_dirty(widget)' in helper
    assert "'settings:preferences'" in helper
    assert "dialog.unsaved_editor_message" in helper
    assert 'QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel' in helper
    assert helper.count('editor_is_dirty(widget)') >= 2
    close = source.split('        def closeEvent(self,event:QCloseEvent):', 1)[1].split('\n\n', 1)[0]
    assert 'if not self._confirm_open_editor_changes()' in close


def test_scene_replacement_actions_share_unsaved_transition_guards():
    source = read('gui.py')
    assert 'def _confirm_scene_transition(self):' in source
    assert 'self._project_confirm_scene_transition()' in source
    project_source = read('gui_project_mixin.py')
    scene_guard = project_source.split('    def _project_confirm_scene_transition(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'self.session.document.dirty' in scene_guard
    assert 'QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel' in scene_guard
    assert 'self.save_scene()' in scene_guard
    assert scene_guard.count('self.session.document.dirty') >= 2
    assert 'def _confirm_project_transition(self):' in source
    assert 'self._project_confirm_project_transition()' in source
    project_guard = project_source.split('    def _project_confirm_project_transition(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'self._confirm_open_editor_changes()' in project_guard
    assert 'self._confirm_scene_transition()' in project_guard


def test_project_transition_closes_old_project_bound_editors_only_after_confirmation():
    source = read('gui.py')
    assert 'def _close_project_bound_editors(self):' in source
    project_source = read('gui_project_mixin.py')
    closer = project_source.split('    def _project_close_project_bound_editors(self):', 1)[1].split('\n    def ', 1)[0]
    assert "'settings:preferences'" in closer
    assert 'editor_registry.close' in closer
    for name in ('open_project_dialog', 'new_project', 'open_scene_dialog'):
        body = source.split(f'        def {name}(self', 1)[1].split('\n        def ', 1)[0]
        target = name.lstrip('_')
        assert f'self._project_{target}' in body, name
    for name in ('_project_open_project_dialog', '_project_new_project', '_project_open_scene_dialog'):
        body = project_source.split(f'    def {name}(self', 1)[1].split('\n    def ', 1)[0]
        assert '_confirm_project_transition()' in body, name
        assert '_close_project_bound_editors()' in body, name
    for name in ('_screen_changed', 'delete_screen'):
        body = source.split(f'        def {name}(self', 1)[1].split('\n        def ', 1)[0]
        assert f'self._project_{name.lstrip("_")}' in body, name
    for name in ('_project_screen_changed', '_project_delete_screen'):
        body = project_source.split(f'    def {name}(self', 1)[1].split('\n    def ', 1)[0]
        assert '_confirm_scene_transition()' in body, name


def test_settings_tab_is_a_command_boundary_not_a_pass_through_to_hidden_editor():
    source = read('gui.py')
    save = source.split('        def route_save(self):', 1)[1].split('\n        def ', 1)[0]
    undo = source.split('        def route_undo(self):', 1)[1].split('\n        def ', 1)[0]
    redo = source.split('        def route_redo(self):', 1)[1].split('\n        def ', 1)[0]
    for body in (save, undo, redo):
        assert "'settings:preferences'" in body
    assert 'flush_pending_save' in save
    chrome = source.split('        def _sync_editor_chrome(self):', 1)[1].split('\n        def ', 1)[0]
    assert 'self._editor_sync_chrome()' in chrome


def test_project_and_scene_open_preflight_before_committing_workspace_transition():
    source = read('gui_project_mixin.py')
    open_project = source.split('    def _project_open_project_dialog(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'try:' in open_project and 'except Exception as exc' in open_project
    assert open_project.index('self._load_project_candidate') < open_project.index('self._confirm_project_transition()')
    assert open_project.index('self._confirm_project_transition()') < open_project.index('self._commit_project_candidate')
    assert open_project.index('self._commit_project_candidate') < open_project.index('self._close_project_bound_editors')
    new_project = source.split('    def _project_new_project(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'try:' in new_project and 'except Exception as exc' in new_project
    assert new_project.index('create_project') < new_project.index('self._close_project_bound_editors')
    open_scene = source.split('    def _project_open_scene_dialog(self):', 1)[1].split('\n    def ', 1)[0]
    assert 'candidate = load_scene(Path(path))' in open_scene
    assert 'except Exception as exc' in open_scene
    assert open_scene.index('candidate = load_scene(Path(path))') < open_scene.index('self._close_project_bound_editors')
    low_level = source.split('    def _project_open_project(self, path: Path):', 1)[1].split('\n    def ', 1)[0]
    assert low_level.index('self._load_project_candidate') < low_level.index('self._commit_project_candidate')
