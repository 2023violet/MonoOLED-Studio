"""Pixel Studio and Font Lab tab lifecycle for the Qt designer window."""

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtWidgets import QFileDialog

from scene import scene_root
from workspace_chrome import editor_chrome_state


class EditorTabsMixin:
    def _editor_tab_changed_impl(self, index):
        from professional_workspace import WorkspaceMode

        if index < 0:
            return
        widget = self.editor_tabs.widget(index); doc_id = getattr(widget, 'document_id', None)
        if doc_id and doc_id != 'settings:preferences': self._last_work_editor_doc_id = doc_id
        if doc_id and self.editor_registry.get(doc_id): self.editor_registry.activate(doc_id)
        if doc_id and (doc_id.startswith('asset:') or doc_id.startswith('pixel:')): self.workspace_mode = WorkspaceMode.PIXEL
        self._sync_editor_chrome()

    def _editor_sync_chrome(self):
        if not hasattr(self, 'editor_tabs'):
            return
        widget = self.editor_tabs.currentWidget(); doc_id = getattr(widget, 'document_id', None) if widget is not None else None
        state = editor_chrome_state(doc_id, self.workspace_mode.value)
        blocker = QSignalBlocker(self.workspace_segment); self.workspace_segment.setCurrentIndex(state.segment_index); del blocker
        self.header_settings.setChecked(state.settings_active); self.header_settings.setProperty('active', state.settings_active)
        self.header_undo.setEnabled(not state.settings_active); self.header_redo.setEnabled(not state.settings_active)
        if hasattr(self, '_actions'):
            for name in ('undo', 'redo'):
                action = self._actions.get(name)
                if action is not None: action.setEnabled(not state.settings_active)
        style = self.header_settings.style(); style.unpolish(self.header_settings); style.polish(self.header_settings); self.header_settings.update()

    def _editor_open_pixel_studio(self):
        from gui import PixelStudioWindow, WorkspaceMode

        path = None
        if self.selected_id:
            try:
                element = self.session.document.element(self.selected_id)
                if element.get('type') == 'image' and element.get('asset'): path = (scene_root(self.scene) / str(element.get('asset'))).resolve()
            except Exception:
                path = None
        if path is None:
            chosen, _ = QFileDialog.getOpenFileName(self, self.tr('action.pixel_studio'), str(scene_root(self.scene)), self.tr('dialog.image_filter')); path = Path(chosen).resolve() if chosen else None
            if path is None: return None
        doc_id = 'asset:' + str(path); existing = self.editor_registry.get(doc_id)
        if existing is not None:
            for index in range(self.editor_tabs.count()):
                if getattr(self.editor_tabs.widget(index), 'document_id', None) == doc_id:
                    self.editor_tabs.setCurrentIndex(index); self.workspace_mode = WorkspaceMode.PIXEL; self._sync_editor_chrome(); return self.editor_tabs.widget(index)
        try:
            editor = PixelStudioWindow(path, language=self.tr.language, parent=self.editor_tabs, preferences=self.preferences, project_root=scene_root(self.scene), project_workspace=self.project)
        except Exception as exc:
            self._show_error(str(exc)); return None
        editor.assetSaved.connect(lambda saved_path, current=editor: self._pixel_asset_saved(saved_path, current)); editor.documentIdentityChanged.connect(lambda changed_path, current=editor: self._pixel_editor_identity_changed(changed_path, current)); editor.document_id = doc_id
        self.editor_registry.open(editor); index = self.editor_tabs.addTab(editor, path.name); self.workspace_mode = WorkspaceMode.PIXEL; self.editor_tabs.setCurrentIndex(index); self._sync_editor_chrome(); return editor

    def _editor_open_font_lab(self, root=None):
        from gui import FontLabEditor, PreferenceDelta, RuntimeSettings

        if root is None:
            item = self.font_list.currentItem() if hasattr(self, 'font_list') else None
            if item: root = (scene_root(self.scene) / item.text()).resolve()
            else:
                chosen = QFileDialog.getExistingDirectory(self, self.tr('font.open_title'), str(self._font_root())); root = Path(chosen).resolve() if chosen else None
        if not root: return
        root = Path(root).resolve(); manifest = root / 'fontpack.json'
        if not manifest.exists(): self._show_error(self.tr('font.manifest_missing', path=str(root))); return
        doc_id = 'font:' + str(root)
        if self.editor_registry.get(doc_id):
            for index in range(self.editor_tabs.count()):
                if getattr(self.editor_tabs.widget(index), 'document_id', None) == doc_id: self.editor_tabs.setCurrentIndex(index); return
        try:
            editor = FontLabEditor(root, parent=self.editor_tabs, language=self.tr.language)
        except Exception as exc:
            self._show_error(str(exc)); return
        editor.fontSaved.connect(lambda _path: (self._scan_fonts(), self.refresh_all(keep_selection=True))); self.editor_registry.open(editor)
        runtime = self._runtime_preferences or RuntimeSettings.from_preferences(self.preferences); editor.apply_runtime_delta(PreferenceDelta(runtime, runtime, frozenset({'language', 'theme', 'metrics', 'performance'})))
        index = self.editor_tabs.addTab(editor, self.tr('panel.fonts') + ' · ' + root.name); self.editor_tabs.setCurrentIndex(index)

    def _editor_pixel_asset_saved(self, path, editor=None):
        if editor is not None:
            try: self.editor_registry.rekey(editor)
            except (KeyError, ValueError) as exc: self._show_error(str(exc))
        self.logger.log('PIXEL_ASSET_SAVED', path=str(path)); QTimer.singleShot(80, self._scan_assets); self.refresh_all(keep_selection=True)
