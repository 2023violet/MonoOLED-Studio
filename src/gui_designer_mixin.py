"""Selection and edit actions owned by the designer workspace."""

from copy import deepcopy

from PySide6.QtWidgets import QMessageBox


class DesignerActionsMixin:
    def _designer_duplicate_selected_elements(self):
        if not self.selected_ids:
            return
        copies = []; existing = {str(e.get('id')) for e in self.scene.get('elements', [])}
        for eid in self.selected_ids:
            element = deepcopy(self.session.document.element(eid)); base = f'{eid}_copy'; nid = base; index = 2
            while nid in existing:
                nid = f'{base}_{index}'; index += 1
            existing.add(nid); element['id'] = nid
            if 'x' in element: element['x'] = int(element['x']) + 1
            if 'y' in element: element['y'] = int(element['y']) + 1
            copies.append(element)
        ids = self.session.add_elements(copies, label='duplicate'); self.selected_ids = ids; self.selected_id = ids[-1] if ids else None; self._rebuild_elements(); self.refresh_all(keep_selection=True)

    def _designer_toggle_selected_lock(self):
        if not self.selected_ids:
            return
        locked = not all(bool(self.session.document.element(eid).get('locked')) for eid in self.selected_ids)
        self.session.set_locked(self.selected_ids, locked); self._rebuild_elements(); self.refresh_all(keep_selection=True)

    def _designer_undo(self):
        if self.session.undo():
            self._rebuild_elements(); self.refresh_all(keep_selection=True)

    def _designer_redo(self):
        if self.session.redo():
            self._rebuild_elements(); self.refresh_all(keep_selection=True)

    def _designer_remove_selected(self):
        if not self.selected_ids:
            return
        if QMessageBox.question(self, self.tr('action.delete'), self.tr('dialog.delete_multi', count=len(self.selected_ids)), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.session.remove_elements(self.selected_ids)
        except Exception as exc:
            self._show_error(str(exc)); return
        self.selected_ids = []; self.selected_id = None; self._rebuild_elements(); self.refresh_all(keep_selection=True)
