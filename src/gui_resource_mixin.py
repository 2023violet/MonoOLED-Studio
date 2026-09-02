"""Asset, template, font, and resource export workflows."""

from copy import deepcopy
from pathlib import Path
import tempfile

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog, QListWidgetItem, QMessageBox

from asset_convert import convert_bitmap
from c_export import write_c_header
from export_matrix import build_export_states
from exporter import export_scene
from font_pack import FontPack, create_font_pack
from professional_workspace import WorkspaceMode
from scene import scene_root
from thumbnail_wall import build_thumbnail_wall


class ResourceWorkflowMixin:
    def _resource_sync_asset_directory_watchers(self):
        if getattr(self, '_closing', False):
            return
        wanted = []
        for rel in self.asset_library.asset_dirs:
            path = (self.asset_library.root / rel).resolve()
            if path.exists() and path.is_dir():
                wanted.append(str(path)); wanted.extend(str(p.resolve()) for p in path.rglob('*') if p.is_dir())
        current = set(self.asset_watcher.directories()); desired = set(wanted)
        remove = list(current - desired); add = list(desired - current)
        if remove: self.asset_watcher.removePaths(remove)
        if add: self.asset_watcher.addPaths(add)

    def _resource_scan_assets(self):
        if getattr(self, '_closing', False):
            return
        try:
            self.asset_library.scan(); self._sync_asset_directory_watchers(); self._filter_assets(self.asset_search.text() if hasattr(self, 'asset_search') else '')
        except Exception as exc:
            if hasattr(self, 'app_status'): self.app_status.setText(str(exc)); self.app_status.set_status('warning')

    def _resource_filter_assets(self, query):
        if not hasattr(self, 'asset_list'): return
        self.asset_list.clear(); entries = list(self.asset_library.search(query))
        empty = not entries; self.asset_empty_title.setVisible(empty); self.asset_empty_guidance.setVisible(empty); self.asset_list.setVisible(not empty)
        if not entries: return
        for entry in entries:
            label = f'{Path(entry.rel_path).name}   {entry.width}×{entry.height}' if entry.valid else f'! {Path(entry.rel_path).name}'
            item = QListWidgetItem(label); item.setData(Qt.UserRole, entry.rel_path); item.setToolTip(entry.rel_path if entry.valid else entry.error); self.asset_list.addItem(item)

    def _resource_import_asset(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr('asset.import'), str(Path.home()), self.tr('dialog.image_filter'))
        if path:
            try:
                entry = self.asset_library.import_asset(path); self._scan_assets(); self.app_status.setText(self.tr('status.asset_imported')); self.app_status.set_status('success'); return entry
            except Exception as exc: self._show_error(str(exc))

    def _resource_place_asset(self, item=None):
        item = item or self.asset_list.currentItem()
        if not item: return
        rel = str(item.data(Qt.UserRole)); path = scene_root(self.scene) / rel
        if self.selected_id and self.session.document.element(self.selected_id).get('type') == 'placeholder':
            try: self.session.assign_bitmap(self.selected_id, path); self._rebuild_elements(); self.refresh_all(keep_selection=True); return
            except Exception as exc: return self._show_error(str(exc))
        stem = Path(rel).stem; eid = stem; existing = {str(e.get('id')) for e in self.scene.get('elements', [])}; i = 2
        while eid in existing: eid = f'{stem}_{i}'; i += 1
        try:
            self.session.add_placeholder(eid, x=0, y=0, w=1, h=1); self.session.assign_bitmap(eid, path); self.selected_ids = [eid]; self.selected_id = eid; self._rebuild_elements(); self.refresh_all(keep_selection=True)
        except Exception as exc: self._show_error(str(exc))

    def _resource_asset_directory_changed(self, _path):
        if not getattr(self, '_closing', False):
            QTimer.singleShot(80, self._scan_assets)

    def _resource_show_asset_health(self):
        used = set()
        if hasattr(self, 'last_render'):
            for p in self.last_render.used_files:
                try: used.add(Path(p).resolve().relative_to(scene_root(self.scene)).as_posix())
                except ValueError: pass
        h = self.asset_library.health_report(used_paths=used)
        QMessageBox.information(self, self.tr('action.asset_health'), self.tr('asset.health_summary', count=len(self.asset_library.entries), duplicates=len(h.duplicates), unused=len(h.unused), invalid=len(h.invalid)))

    def _resource_save_template(self):
        if not self.selected_ids: return
        name, ok = QInputDialog.getText(self, self.tr('action.save_template'), self.tr('template.name'))
        if not ok or not name.strip(): return
        elements = [deepcopy(self.session.document.element(eid)) for eid in self.selected_ids]
        try:
            self.template_library.save_template(name.strip(), elements); self.app_status.setText(self.tr('template.saved', name=name.strip())); self.app_status.set_status('success')
        except Exception as exc: self._show_error(str(exc))

    def _resource_insert_template(self):
        names = self.template_library.names()
        if not names: return self._show_error(self.tr('template.none'))
        name, ok = QInputDialog.getItem(self, self.tr('action.insert_template'), self.tr('template.name'), names, 0, False)
        if not ok: return
        prefix, ok = QInputDialog.getText(self, self.tr('action.insert_template'), self.tr('template.prefix'), text=f'{name}_')
        if not ok: return
        try:
            items = self.template_library.instantiate(name, prefix=prefix, offset=(0, 0)); ids = self.session.add_elements(items, label='template_insert'); self.selected_ids = ids; self.selected_id = ids[-1] if ids else None; self._rebuild_elements(); self.refresh_all(keep_selection=True)
        except Exception as exc: self._show_error(str(exc))

    def _resource_convert_asset(self):
        source, _ = QFileDialog.getOpenFileName(self, self.tr('action.convert_asset'), str(scene_root(self.scene)), self.tr('dialog.image_filter'))
        if not source: return
        target_dir = scene_root(self.scene) / 'assets' / 'converted'; target = target_dir / (Path(source).stem + '.png')
        try:
            convert_bitmap(source, target)
            if self.project and 'assets' not in self.project.data.setdefault('asset_dirs', []): self.project.data['asset_dirs'].append('assets'); self.project.save()
            self.asset_library = self._make_asset_library(); self._scan_assets(); self.app_status.setText(self.tr('asset.converted', path=str(target))); self.app_status.set_status('success')
        except Exception as exc: self._show_error(str(exc))

    def _resource_project_symbol(self):
        raw = str(self.scene.get('product') or (self.project.data.get('name') if self.project else '') or 'monooled_project').strip().lower()
        clean = ''.join(ch if ch.isalnum() else '_' for ch in raw).strip('_')
        return clean or 'monooled_project'

    def _resource_export_c_header(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr('action.export_c_header'), str(scene_root(self.scene) / 'exports' / 'current_frame.h'), 'C Header (*.h)')
        if not path: return
        try:
            write_c_header(self.session.render().framebuffer, path, name=self._project_symbol() + '_oled_frame'); self.app_status.setText(self.tr('status.exported', path=path)); self.app_status.set_status('success')
        except Exception as exc: self._show_error(str(exc))

    def _resource_export_thumbnail_wall(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr('action.thumbnail_wall'), str(scene_root(self.scene) / 'exports' / 'screen_overview.png'), 'PNG (*.png)')
        if not path: return
        try:
            states = build_export_states(self.scene, integer_policy='representative', max_cases=5000)
            with tempfile.TemporaryDirectory(prefix='oled_wall_') as td:
                export_scene(self.scene, Path(td), states); refs = [Path(td) / 'reference' / f'{name}.png' for name in states]; build_thumbnail_wall(refs, path, columns=min(4, max(1, len(refs))), scale=4)
            self.app_status.setText(self.tr('status.exported', path=path)); self.app_status.set_status('success')
        except Exception as exc: self._show_error(str(exc))

    def _resource_font_root(self):
        root = scene_root(self.scene); target = root / '.oled' / 'fonts'; target.mkdir(parents=True, exist_ok=True); return target

    def _resource_scan_fonts(self):
        if getattr(self, '_closing', False):
            return
        if not hasattr(self, 'font_list'): return
        self.font_list.clear(); roots = []; base = scene_root(self.scene); candidates = [base / '.oled' / 'fonts', base / 'fonts']
        for element in self.scene.get('elements', []):
            rel = element.get('font_pack') if isinstance(element, dict) else None
            if rel:
                path = (base / str(rel)).resolve(); candidates.append(path if path.is_dir() else path.parent)
        seen = set()
        for candidate in candidates:
            try: candidate = candidate.resolve(); candidate.relative_to(base)
            except (OSError, ValueError): continue
            if candidate in seen or not candidate.exists(): continue
            seen.add(candidate); manifests = [candidate / 'fontpack.json'] if (candidate / 'fontpack.json').exists() else candidate.rglob('fontpack.json')
            for manifest in manifests:
                try: roots.append(manifest.parent.relative_to(base).as_posix())
                except ValueError: continue
        roots = sorted(dict.fromkeys(roots)); empty = not roots; self.font_empty_title.setVisible(empty); self.font_empty_guidance.setVisible(empty); self.font_list.setVisible(not empty)
        if roots: self.font_list.addItems(roots)

    def _resource_new_font_pack(self):
        name, ok = QInputDialog.getText(self, self.tr('font.new_title'), self.tr('font.pack_name'), text='Clinical 5x7')
        if not ok or not name.strip(): return
        safe = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name.strip()).strip('_') or 'font_pack'; root = self._font_root() / safe
        if (root / 'fontpack.json').exists(): return self._show_error(self.tr('font.exists', path=str(root)))
        try: create_font_pack(root, name.strip(), cell=(5, 8), baseline=6, advance=6).save()
        except Exception as exc: self._show_error(str(exc)); return
        self._scan_fonts(); self.open_font_lab(root)

    def _resource_insert_bitmap_text(self):
        if self.workspace_mode != WorkspaceMode.DESIGN: return
        root = QFileDialog.getExistingDirectory(self, self.tr('font.select_title'), str(self._font_root()))
        if not root: return
        try: pack = FontPack.load(root)
        except Exception as exc: self._show_error(str(exc)); return
        text, ok = QInputDialog.getText(self, self.tr('bitmap.text_title'), self.tr('bitmap.text'), text='TEXT')
        if not ok or not text: return
        missing = [ch for ch in text if ch not in pack.characters()]
        if missing: return self._show_error(self.tr('font.missing_glyphs', glyphs=str(missing)))
        eid, ok = QInputDialog.getText(self, self.tr('bitmap.text_title'), self.tr('bitmap.element_id'), text='bitmap_text_1')
        if not ok or not eid: return
        try: rel = Path(root).resolve().relative_to(scene_root(self.scene)).as_posix()
        except ValueError: return self._show_error(self.tr('font.inside_project'))
        try: self.session.add_elements([{'id': eid, 'type': 'bitmap_text', 'text': text, 'font_pack': rel, 'x': 0, 'y': 0}], label='bitmap_text_insert')
        except Exception as exc: self._show_error(str(exc)); return
        self._rebuild_elements(); self._set_selection([eid], source='api', primary=eid); self.refresh_all(keep_selection=True)
