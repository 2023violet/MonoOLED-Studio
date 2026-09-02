"""Project persistence, workspace navigation, and export operations."""

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog, QListWidgetItem, QMessageBox

from export_matrix import build_export_states
from exporter import ExportBlockedError, export_scene
from handoff import build_handoff_package
from project_workspace import ProjectWorkspace, create_project
from scene import ROOT, load_scene, scene_root


def _decorate_project_scene(scene: dict, project: ProjectWorkspace | None) -> dict:
    if project is not None:
        scene['_project_path'] = str(project.path)
        scene['_asset_dirs'] = list(project.asset_dirs)
        scene['_design_rules'] = dict(project.data.get('design_rules') or {})
    return scene


class ProjectWorkspaceMixin:
    def _project_confirm_scene_transition(self):
        if not self.session.document.dirty:
            return True
        choice = QMessageBox.question(self, self.tr('dialog.unsaved_title'), self.tr('dialog.unsaved_message'), QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        if choice == QMessageBox.Cancel:
            return False
        if choice == QMessageBox.Save:
            self.save_scene()
            if self.session.document.dirty:
                return False
        return True

    def _project_confirm_project_transition(self):
        return self._confirm_open_editor_changes() and self._confirm_scene_transition()

    def _project_close_project_bound_editors(self):
        for i in range(self.editor_tabs.count() - 1, 0, -1):
            widget = self.editor_tabs.widget(i); doc_id = getattr(widget, 'document_id', None)
            if doc_id == 'settings:preferences':
                continue
            self.editor_tabs.removeTab(i)
            if doc_id:
                self.editor_registry.close(doc_id)
            widget.deleteLater()
        self._last_work_editor_doc_id = 'scene:active'
        if self.editor_tabs.count():
            self.editor_tabs.setCurrentIndex(0)
        self._sync_editor_chrome()

    def _project_open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr('dialog.open_project'), str(ROOT), 'OLED Project (*.oled.json);;JSON (*.json)')
        if not path:
            return
        try:
            project, scene = self._load_project_candidate(Path(path))
        except Exception as exc:
            self._show_error(str(exc)); return
        if not self._confirm_project_transition():
            return
        self._commit_project_candidate(project, scene); self._close_project_bound_editors()

    def _project_load_project_candidate(self, path: Path):
        project = ProjectWorkspace.load(path)
        scene = _decorate_project_scene(load_scene(project.screen_path(project.active_screen), project_root=project.root), project)
        return project, scene

    def _project_remember_last_project(self, value):
        self.preferences.set('startup.last_project', str(value), save=False)
        try:
            self.preferences.save()
        except OSError as exc:
            self.logger.log('PREFERENCES_SAVE_FAIL', error=str(exc))

    def _project_commit_project_candidate(self, project, scene):
        self.project = project; self._reset_session(scene); self._rebuild_screens(); self._remember_last_project(str(project.path)); self.logger.log('PROJECT_OPEN', path=str(project.path))

    def _project_open_project(self, path: Path):
        project, scene = self._load_project_candidate(path); self._commit_project_candidate(project, scene)

    def _project_new_project(self):
        root = QFileDialog.getExistingDirectory(self, self.tr('dialog.new_project'))
        if not root:
            return
        name, ok = QInputDialog.getText(self, self.tr('dialog.new_project'), self.tr('project.name'))
        if not (ok and name.strip() and self._confirm_project_transition()):
            return
        try:
            project = create_project(root, name=name.strip()); self._open_project(project.path)
        except Exception as exc:
            self._show_error(str(exc)); return
        self._close_project_bound_editors()

    def _project_rebuild_screens(self):
        blocker = QSignalBlocker(self.screen_list); self.screen_list.clear()
        if self.project:
            for ref in self.project.screens:
                item = QListWidgetItem(ref.label); item.setData(Qt.UserRole, ref.id); self.screen_list.addItem(item)
                if ref.id == self.project.active_screen: self.screen_list.setCurrentItem(item)
        else:
            item = QListWidgetItem(Path(self.scene.get('_path', 'scene')).stem); item.setData(Qt.UserRole, '__scene__'); self.screen_list.addItem(item); self.screen_list.setCurrentItem(item)
        del blocker

    def _project_screen_changed(self, current, _prev):
        if not current or not self.project: return
        sid = str(current.data(Qt.UserRole))
        if sid == self.project.active_screen: return
        old_sid = self.project.active_screen
        try: candidate = _decorate_project_scene(load_scene(self.project.screen_path(sid), project_root=self.project.root), self.project)
        except Exception as exc: self._rebuild_screens(); self._show_error(str(exc)); return
        if not self._confirm_scene_transition(): self._rebuild_screens(); return
        try: self.project.set_active_screen(sid); self.project.save()
        except Exception as exc: self.project.set_active_screen(old_sid); self._rebuild_screens(); self._show_error(str(exc)); return
        self._reset_session(candidate)

    def _project_new_screen(self):
        if not self.project: return self._show_error(self.tr('project.required'))
        sid, ok = QInputDialog.getText(self, self.tr('action.new_screen'), self.tr('screen.id'))
        if ok and sid.strip():
            try: self.project.add_screen(sid.strip(), label=sid.strip(), canvas=(int(self.scene['canvas']['w']), int(self.scene['canvas']['h']))); self._rebuild_screens()
            except Exception as exc: self._show_error(str(exc))

    def _project_duplicate_screen(self):
        if not self.project: return
        sid = self.project.active_screen; new_id, ok = QInputDialog.getText(self, self.tr('action.duplicate'), self.tr('screen.id'), text=sid + '_copy')
        if ok and new_id.strip():
            try: self.project.duplicate_screen(sid, new_id=new_id.strip(), label=new_id.strip()); self._rebuild_screens()
            except Exception as exc: self._show_error(str(exc))

    def _project_delete_screen(self):
        if not self.project: return
        current_sid = self.project.active_screen; remaining = [ref.id for ref in self.project.screens if ref.id != current_sid]
        if not remaining: return self._show_error('project must keep at least one screen')
        fallback_sid = remaining[0]
        try: candidate = _decorate_project_scene(load_scene(self.project.screen_path(fallback_sid), project_root=self.project.root), self.project)
        except Exception as exc: self._show_error(str(exc)); return
        if not self._confirm_scene_transition(): return
        try: self.project.remove_screen(current_sid); self._rebuild_screens(); self._reset_session(candidate)
        except Exception as exc: self._show_error(str(exc))

    def _project_open_scene_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr('dialog.open_scene'), str(scene_root(self.scene)), 'Scene JSON (*.json);;All Files (*)')
        if not path: return
        try: candidate = load_scene(Path(path))
        except Exception as exc: self._show_error(str(exc)); return
        if not self._confirm_project_transition(): return
        self._close_project_bound_editors(); self.project = None; self._reset_session(candidate); self._remember_last_project('')

    def _project_save_scene(self):
        try:
            path = self.session.save(); self._capture_saved_baseline(); self.logger.log('SAVE_UI', path=str(path)); self.app_status.setText(self.tr('status.saved')); self.app_status.set_status('success'); self.refresh_all(keep_selection=True)
        except Exception as exc: self._show_error(str(exc))

    def _project_export_current(self):
        output = QFileDialog.getExistingDirectory(self, self.tr('dialog.export_current'))
        if output: self._project_perform_export(Path(output), {'current': dict(self.session.runtime.state)})

    def _project_export_all(self):
        output = QFileDialog.getExistingDirectory(self, self.tr('dialog.export_all'))
        if output: self._project_perform_export(Path(output), build_export_states(self.scene, integer_policy='representative', max_cases=5000))

    def _project_perform_export(self, output, states):
        try: summary = export_scene(self.scene, output, states)
        except ExportBlockedError as exc: self._show_error(str(exc)); return
        except Exception as exc: self._show_error(str(exc)); return
        self.logger.log('EXPORT', output=str(summary.output_dir), frames=summary.frame_count); self.app_status.setText(self.tr('status.exported', path=str(summary.output_dir))); self.app_status.set_status('success')

    def _project_export_handoff(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr('action.handoff'), str(scene_root(self.scene) / 'exports' / 'OLED_Code_AI_Handoff.zip'), 'ZIP (*.zip)')
        if not path: return
        states = build_export_states(self.scene, integer_policy='representative', max_cases=5000)
        try:
            summary = build_handoff_package(self.scene, path, states=states, integer_policy='representative'); self.app_status.setText(self.tr('handoff.done', frames=summary.frame_count, path=path)); self.app_status.set_status('success')
        except Exception as exc: self._show_error(str(exc))
