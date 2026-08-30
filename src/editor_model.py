from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Mapping

from assets import load_bitmap
from document import SceneDocument
from render import RenderResult, render_scene
from resource_cache import RenderResources
from scene import resolve, subst, when_match
from runtime import SceneRuntime
from scene import scene_root
from validate import Finding, validate_scene


@dataclass(frozen=True)
class Geometry:
    x: int
    y: int
    w: int
    h: int
    editable: dict[str, bool]


@dataclass(frozen=True)
class _EditCommand:
    element_id: str
    before: tuple[tuple[str, int], ...]
    after: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class _ElementCommand:
    element_id: str
    index: int
    before: dict | None
    after: dict | None


@dataclass(frozen=True)
class _BatchCommand:
    label: str
    before: tuple[dict, ...]
    after: tuple[dict, ...]


@dataclass(frozen=True)
class _SceneCommand:
    label: str
    before: dict
    after: dict


class EditorSession:
    """GUI-independent authoring session for the OLED UI editor.

    The scene model remains the single source of layout truth. GUI frontends
    call this class to edit geometry, drive UI state, render through the
    canonical framebuffer, validate, save, and undo/redo changes.
    """

    def __init__(self, scene: dict, logger=None, *, max_history: int = 500):
        self.scene = scene
        self.logger = logger
        self.document = SceneDocument(scene, logger=logger)
        self.runtime = SceneRuntime(scene, logger=logger)
        self.resources = RenderResources()
        self._undo: list[_EditCommand | _ElementCommand | _BatchCommand | _SceneCommand] = []
        self._redo: list[_EditCommand | _ElementCommand | _BatchCommand | _SceneCommand] = []
        self._coalesce_open = False
        self.max_history = max(1, int(max_history))

    def reset_scene(self, scene: dict) -> None:
        """Rebind this editor session to another scene without replacing the session object.

        The stable session identity lets the Automation service switch project screens
        while Qt widgets keep their existing references.  History/resources/runtime are
        scene-owned and therefore reset at the boundary.
        """
        self.scene = scene
        self.document = SceneDocument(scene, logger=self.logger)
        self.runtime = SceneRuntime(scene, logger=self.logger)
        self.resources = RenderResources()
        self._undo.clear()
        self._redo.clear()
        self._coalesce_open = False

    def _push_undo(self, command) -> None:
        self._undo.append(command)
        if len(self._undo) > self.max_history:
            del self._undo[:len(self._undo) - self.max_history]

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @staticmethod
    def _path_value(element: dict, path: str) -> int:
        cur = element
        for part in path.split('.'):
            cur = cur[part]
        return int(cur)

    def _resolved_item(self, element_id: str) -> dict:
        """Resolve editor geometry without rendering the framebuffer.

        Interactive alignment/drag queries must not invoke the full renderer.
        This mirrors the renderer's size/position rules while using the same
        content-safe resource cache for native bitmap/font metrics.
        """
        element = self.document.element(element_id)
        state = self.runtime.state
        hidden = bool(element.get('hidden')) or not when_match(element.get('visible_when'), state)
        kind = element.get('type')
        raw_x = element.get('x', element.get('zone', {}).get('x', 0))
        raw_y = element.get('y', element.get('zone', {}).get('y', 0))
        if hidden:
            return {'id': element_id, 'x': raw_x, 'y': raw_y, 'w': element.get('w', element.get('zone', {}).get('w', 0)), 'h': element.get('h', element.get('zone', {}).get('h', 0))}
        if kind == 'placeholder':
            return {'id': element_id, 'x': int(element['x']), 'y': int(element['y']), 'w': int(element['w']), 'h': int(element['h'])}
        if kind == 'image':
            path = resolve(subst(str(element['asset']), state, lower=bool(element.get('var_lower'))), scene=self.scene).resolve()
            asset = self.resources.bitmap(path)
            return {'id': element_id, 'x': int(element['x']), 'y': int(element['y']), 'w': int(element.get('w', asset.width)), 'h': int(element.get('h', asset.height))}
        if kind == 'image_seq':
            value = int(state[element['bind']]); filename = str(element['pattern']).replace('{n}', str(value))
            path = (resolve(element['dir'], scene=self.scene) / filename).resolve(); asset = self.resources.bitmap(path)
            return {'id': element_id, 'x': int(element['x']), 'y': int(element['y']), 'w': int(element.get('w', asset.width)), 'h': int(element.get('h', asset.height))}
        if kind == 'digits':
            raw = str(state[element['bind']]); min_digits = int(element.get('min_digits', 1))
            if raw.isdigit() and len(raw) < min_digits: raw = raw.rjust(min_digits, str(element.get('pad_char', '0')))
            digit_w = int(element['digit_w']); tracking = int(element.get('tracking', 0))
            width = 0 if not raw else len(raw) * digit_w + (len(raw)-1) * tracking
            return {'id': element_id, 'x': int(element['x']), 'y': int(element['y']), 'w': width, 'h': int(element['digit_h'])}
        if kind == 'text':
            text = subst(str(element['text']), state).upper(); cell_w = int(element.get('cell_w', 5)); cell_h = int(element.get('cell_h', 7)); advance = int(element.get('advance', cell_w + 1))
            width = 0 if not text else (len(text)-1) * advance + cell_w; zone = element.get('zone')
            if zone:
                align = element.get('align', 'left')
                if align == 'left': x = int(zone['x'])
                elif align == 'center': x = int(zone['x']) + (int(zone['w']) - width)//2
                elif align == 'right': x = int(zone['x']) + int(zone['w']) - width
                else: raise ValueError(f'unknown text align: {align}')
                y = int(element.get('y', zone['y']))
            else: x, y = int(element['x']), int(element['y'])
            return {'id': element_id, 'x': x, 'y': y, 'w': width, 'h': cell_h}
        if kind == 'bitmap_text':
            text = subst(str(element.get('text', '')), state); pack_root = resolve(element['font_pack'], scene=self.scene).resolve(); pack = self.resources.font_pack(pack_root)
            width = 0 if not text else sum(pack.glyph(ch).metrics.advance for ch in text[:-1]) + pack.cell[0]
            return {'id': element_id, 'x': int(element.get('x', 0)), 'y': int(element.get('y', 0)), 'w': width, 'h': int(pack.cell[1])}
        raise ValueError(f'unsupported element type: {kind}')

    def geometry(self, element_id: str) -> Geometry:
        element = self.document.element(element_id)
        zone = element.get('zone') if isinstance(element.get('zone'), dict) else None
        if zone is None and all(key in element for key in ('x', 'y', 'w', 'h')):
            native_locked = (
                element.get('type') == 'image'
                and element.get('resize_policy', 'native_only') == 'native_only'
            )
            return Geometry(
                int(element['x']), int(element['y']), int(element['w']), int(element['h']),
                {'x': True, 'y': True, 'w': not native_locked, 'h': not native_locked},
            )
        resolved = self._resolved_item(element_id)

        if zone is not None and all(k in zone for k in ('x', 'y', 'w', 'h')):
            return Geometry(
                int(zone['x']), int(zone['y']), int(zone['w']), int(zone['h']),
                {'x': True, 'y': True, 'w': True, 'h': True},
            )

        x = int(element.get('x', resolved.get('x', 0) or 0))
        y = int(element.get('y', resolved.get('y', 0) or 0))
        w_raw = element.get('w')
        h_raw = element.get('h')
        w = int(w_raw if w_raw is not None else resolved.get('w', 0) or 0)
        h = int(h_raw if h_raw is not None else resolved.get('h', 0) or 0)
        native_locked = element.get('type') == 'image' and element.get('resize_policy', 'native_only') == 'native_only'
        return Geometry(
            x, y, w, h,
            {
                'x': 'x' in element,
                'y': 'y' in element,
                'w': ('w' in element) and not native_locked,
                'h': ('h' in element) and not native_locked,
            },
        )

    def _geometry_changes(self, element_id: str, values: Mapping[str, int]) -> dict[str, int]:
        element = self.document.element(element_id)
        if element.get('locked'):
            raise ValueError(f'{element_id} is locked')
        zone = element.get('zone') if isinstance(element.get('zone'), dict) else None
        geom = self.geometry(element_id)
        editable = geom.editable
        changes: dict[str, int] = {}

        for name, value in values.items():
            if name not in {'x', 'y', 'w', 'h'}:
                raise KeyError(f'unknown geometry field: {name}')
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f'{name} must be an integer pixel value')
            if not editable[name]:
                raise ValueError(f'{element_id}.{name} is not editable')

            if zone is not None and name in {'x', 'y', 'w', 'h'}:
                changes[f'zone.{name}'] = value
                if name == 'y' and 'y' in element:
                    old_offset = int(element['y']) - int(zone['y'])
                    changes['y'] = value + old_offset
            else:
                changes[name] = value
        return changes

    def _record_and_apply(self, element_id: str, changes: Mapping[str, int], *, coalesce: bool = False) -> bool:
        element = self.document.element(element_id)
        before = {path: self._path_value(element, path) for path in changes}
        after = {path: int(value) for path, value in changes.items()}
        if before == after:
            return False

        for path, value in after.items():
            self.document.set_field(element_id, path, value)

        after_items = tuple(sorted(after.items()))
        if coalesce and self._coalesce_open and self._undo and isinstance(self._undo[-1], _EditCommand):
            previous = self._undo[-1]
            if previous.element_id == element_id and tuple(path for path, _ in previous.after) == tuple(path for path, _ in after_items):
                self._undo[-1] = _EditCommand(element_id, previous.before, after_items)
                if self.logger is not None:
                    self.logger.log('HISTORY_COALESCE', element=element_id, after=after)
                self._redo.clear()
                return True

        command = _EditCommand(
            element_id,
            tuple(sorted(before.items())),
            after_items,
        )
        self._push_undo(command)
        self._redo.clear()
        # Keep the latest geometry command eligible for subsequent coalesced
        # updates until the GUI explicitly closes the gesture. This supports
        # a first pointer/value event followed by high-frequency coalesced events.
        self._coalesce_open = True
        if self.logger is not None:
            self.logger.log('HISTORY_PUSH', element=element_id, before=before, after=after)
        return True

    def batch_set_geometry(self, changes_by_id: Mapping[str, Mapping[str, int]], *, label: str = 'geometry_batch', coalesce: bool = False) -> bool:
        """Apply geometry changes as one undoable user action.

        When ``coalesce`` is true, repeated batches with the same label keep the
        original before-snapshot and replace only the after-snapshot.  This
        makes a multi-selection pointer drag exactly one Ctrl+Z step.
        """
        prepared: dict[str, dict[str, int]] = {}
        for element_id, values in changes_by_id.items():
            changes = self._geometry_changes(element_id, values)
            if changes:
                prepared[element_id] = changes
        if not prepared:
            return False
        before = tuple(deepcopy(self.scene.get('elements', [])))
        by_id = {str(item.get('id')): item for item in self.scene.setdefault('elements', [])}
        for element_id, changes in prepared.items():
            element = by_id[element_id]
            for path, value in changes.items():
                node = element; parts = path.split('.')
                for part in parts[:-1]: node = node[part]
                node[parts[-1]] = int(value)
        after = tuple(deepcopy(self.scene.get('elements', [])))
        if before == after:
            return False
        self.document.dirty = True; self._redo.clear()
        if coalesce and self._coalesce_open and self._undo and isinstance(self._undo[-1], _BatchCommand) and self._undo[-1].label == label:
            previous = self._undo[-1]
            self._undo[-1] = _BatchCommand(label, previous.before, after)
            if self.logger is not None:self.logger.log('HISTORY_COALESCE',batch=label)
        else:
            self._push_undo(_BatchCommand(label, before, after))
            if self.logger is not None:self.logger.log('BATCH_EDIT',label=label)
        self._coalesce_open = bool(coalesce)
        return True

    def batch_move(self, element_ids, dx: int = 0, dy: int = 0, *, coalesce: bool = False) -> bool:
        if not isinstance(dx, int) or isinstance(dx, bool) or not isinstance(dy, int) or isinstance(dy, bool):
            raise TypeError('dx/dy must be integer pixels')
        changes = {}
        for element_id in element_ids:
            element = self.document.element(element_id)
            if element.get('locked'):
                continue
            geom = self.geometry(element_id); values = {}
            if dx and geom.editable['x']: values['x'] = geom.x + dx
            if dy and geom.editable['y']: values['y'] = geom.y + dy
            if values: changes[element_id] = values
        return self.batch_set_geometry(changes, label='move_batch', coalesce=coalesce) if changes else False

    def end_coalesced_edit(self) -> None:
        self._coalesce_open = False

    def set_geometry(self, element_id: str, *, coalesce: bool = False, **values: int) -> bool:
        if not values:
            return False
        return self._record_and_apply(element_id, self._geometry_changes(element_id, values), coalesce=coalesce)

    def move(self, element_id: str, dx: int = 0, dy: int = 0, *, coalesce: bool = False) -> bool:
        if not isinstance(dx, int) or isinstance(dx, bool) or not isinstance(dy, int) or isinstance(dy, bool):
            raise TypeError('dx/dy must be integer pixels')
        geom = self.geometry(element_id)
        values = {}
        if dx:
            if not geom.editable['x']:
                raise ValueError(f'{element_id}.x is not editable')
            values['x'] = geom.x + dx
        if dy:
            if not geom.editable['y']:
                raise ValueError(f'{element_id}.y is not editable')
            values['y'] = geom.y + dy
        return self.set_geometry(element_id, coalesce=coalesce, **values) if values else False

    def _apply_command_snapshot(self, command: _EditCommand, snapshot: tuple[tuple[str, int], ...]) -> None:
        for path, value in snapshot:
            self.document.set_field(command.element_id, path, value)

    def _restore_element(self, command: _ElementCommand, snapshot: dict | None) -> None:
        elements = self.scene.setdefault('elements', [])
        for index, item in enumerate(list(elements)):
            if item.get('id') == command.element_id:
                elements.pop(index)
                break
        if snapshot is not None:
            index = max(0, min(command.index, len(elements)))
            elements.insert(index, deepcopy(snapshot))
        self.document.dirty = True

    def _restore_batch(self, snapshot: tuple[dict, ...]) -> None:
        self.scene['elements'] = [deepcopy(item) for item in snapshot]
        self.document.dirty = True

    def _restore_scene(self, snapshot: dict) -> None:
        self.scene.clear()
        self.scene.update(deepcopy(snapshot))
        self.document.scene = self.scene
        self.runtime.scene = self.scene
        self.runtime.reset()
        self.resources = RenderResources()
        self.document.dirty = True

    def undo(self) -> bool:
        self.end_coalesced_edit()
        if not self._undo:
            return False
        command = self._undo.pop()
        if isinstance(command, _EditCommand):
            self._apply_command_snapshot(command, command.before)
            payload = {'fields': dict(command.before)}
        elif isinstance(command, _ElementCommand):
            self._restore_element(command, command.before)
            payload = {'element_snapshot': command.before}
        elif isinstance(command, _SceneCommand):
            self._restore_scene(command.before)
            payload = {'scene_snapshot': command.label}
        else:
            self._restore_batch(command.before)
            payload = {'batch': command.label}
        self._redo.append(command)
        if self.logger is not None:
            target = getattr(command, 'element_id', None)
            self.logger.log('UNDO', element=target, **payload)
        return True

    def redo(self) -> bool:
        self.end_coalesced_edit()
        if not self._redo:
            return False
        command = self._redo.pop()
        if isinstance(command, _EditCommand):
            self._apply_command_snapshot(command, command.after)
            payload = {'fields': dict(command.after)}
        elif isinstance(command, _ElementCommand):
            self._restore_element(command, command.after)
            payload = {'element_snapshot': command.after}
        elif isinstance(command, _SceneCommand):
            self._restore_scene(command.after)
            payload = {'scene_snapshot': command.label}
        else:
            self._restore_batch(command.after)
            payload = {'batch': command.label}
        self._push_undo(command)
        if self.logger is not None:
            target = getattr(command, 'element_id', None)
            self.logger.log('REDO', element=target, **payload)
        return True

    def record_external_batch(self, before_elements, *, label: str = 'external_transaction') -> bool:
        """Record externally-applied element mutations as one undo command.

        Automation services use this after an atomic transaction so one AI
        operation maps to one ordinary Designer Ctrl+Z step.
        """
        before=tuple(deepcopy(list(before_elements))); after=tuple(deepcopy(self.scene.get('elements',[])))
        if before==after:return False
        self._push_undo(_BatchCommand(str(label),before,after)); self._redo.clear(); self.document.dirty=True; self._coalesce_open=False
        if self.logger is not None:self.logger.log('HISTORY_PUSH',batch=str(label),source='external')
        return True

    def record_external_scene(self, before_scene: dict, *, label: str = 'external_scene_transaction') -> bool:
        """Record a root-level scene mutation as one Designer undo step.

        This is intentionally reserved for Automation operations that mutate
        scene-owned contracts such as the state schema. The scene dict identity
        remains stable so Qt/editor references do not drift across undo/redo.
        """
        before = deepcopy(dict(before_scene))
        after = deepcopy(dict(self.scene))
        if before == after:
            return False
        self._push_undo(_SceneCommand(str(label), before, after))
        self._redo.clear()
        self.document.dirty = True
        self._coalesce_open = False
        if self.logger is not None:
            self.logger.log('HISTORY_PUSH', batch=str(label), source='external_scene')
        return True

    def add_elements(self, elements: list[dict], *, label: str = 'add_elements') -> list[str]:
        if not elements:
            return []
        incoming=[str(item.get('id','')) for item in elements]
        if any(not value for value in incoming) or len(set(incoming)) != len(incoming):
            raise ValueError('duplicate or empty element id in inserted elements')
        existing={str(item.get('id')) for item in self.scene.get('elements',[])}
        duplicate=existing.intersection(incoming)
        if duplicate:
            raise ValueError(f'duplicate element ids: {sorted(duplicate)}')
        snapshots=[deepcopy(item) for item in elements]
        def mutate(current):
            current.extend(deepcopy(snapshots))
        self._batch_edit(label, mutate)
        return incoming

    def add_placeholder(self, element_id: str, *, x: int, y: int, w: int, h: int, label: str | None = None) -> str:
        if any(item.get('id') == element_id for item in self.scene.get('elements', [])):
            raise ValueError(f'duplicate element id: {element_id}')
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, w, h)):
            raise TypeError('placeholder X/Y/W/H must be integers')
        element = {
            'id': element_id, 'type': 'placeholder',
            'x': x, 'y': y, 'w': w, 'h': h,
            'label': label or element_id,
        }
        elements = self.scene.setdefault('elements', [])
        index = len(elements)
        elements.append(deepcopy(element))
        self.document.dirty = True
        self._push_undo(_ElementCommand(element_id, index, None, deepcopy(element)))
        self._redo.clear()
        if self.logger is not None:
            self.logger.log('ELEMENT_ADD', element=element_id, index=index, snapshot=element)
        return element_id

    def remove_element(self, element_id: str) -> None:
        elements = self.scene.get('elements', [])
        for index, item in enumerate(elements):
            if item.get('id') == element_id:
                before = deepcopy(item)
                elements.pop(index)
                self.document.dirty = True
                self._push_undo(_ElementCommand(element_id, index, before, None))
                self._redo.clear()
                if self.logger is not None:
                    self.logger.log('ELEMENT_REMOVE', element=element_id, index=index, snapshot=before)
                return
        raise KeyError(f'unknown element id: {element_id}')

    def remove_elements(self, element_ids) -> None:
        ids = {str(value) for value in element_ids}
        if not ids:
            return
        existing = {str(item.get('id')) for item in self.scene.get('elements', [])}
        missing = ids - existing
        if missing:
            raise KeyError(f'unknown element ids: {sorted(missing)}')
        def mutate(elements):
            elements[:] = [item for item in elements if str(item.get('id')) not in ids]
        self._batch_edit('remove_elements', mutate)

    def assign_bitmap(self, element_id: str, path: str | Path) -> None:
        elements = self.scene.get('elements', [])
        for index, item in enumerate(elements):
            if item.get('id') != element_id:
                continue
            if item.get('type') not in {'placeholder', 'image'}:
                raise ValueError(f'{element_id}: bitmap assignment is only valid for placeholder/image elements')
            source = Path(path).resolve()
            asset = load_bitmap(source)
            before = deepcopy(item)
            after = deepcopy(item)
            after['type'] = 'image'
            root = scene_root(self.scene)
            try:
                stored_path = source.relative_to(root)
            except ValueError:
                imported_dir = root / 'assets' / 'imported'
                imported_dir.mkdir(parents=True, exist_ok=True)
                target = imported_dir / source.name
                if target.exists() and target.read_bytes() != source.read_bytes():
                    target = imported_dir / f'{source.stem}_{asset.sha256[:8]}{source.suffix.lower()}'
                if not target.exists():
                    shutil.copy2(source, target)
                stored_path = target.relative_to(root)
            stored = stored_path.as_posix()
            after['asset'] = stored
            after['w'] = asset.width
            after['h'] = asset.height
            after.pop('label', None)
            after.setdefault('blend', 'or')
            after.setdefault('resize_policy', 'native_only')
            elements[index] = deepcopy(after)
            self.document.dirty = True
            self._push_undo(_ElementCommand(element_id, index, before, deepcopy(after)))
            self._redo.clear()
            if self.logger is not None:
                self.logger.log('ASSET_ASSIGN', element=element_id, asset=stored, width=asset.width, height=asset.height)
            return
        raise KeyError(f'unknown element id: {element_id}')

    def _batch_edit(self, label: str, mutator) -> None:
        elements = self.scene.setdefault('elements', [])
        before = tuple(deepcopy(elements))
        try:
            mutator(elements)
        except Exception:
            elements[:] = [deepcopy(item) for item in before]
            raise
        after = tuple(deepcopy(elements))
        if before == after:
            return
        self.document.dirty = True
        self._push_undo(_BatchCommand(label, before, after))
        self._redo.clear()
        if self.logger is not None:
            self.logger.log('BATCH_EDIT', label=label)

    def set_locked(self, element_ids, locked: bool) -> None:
        ids = set(element_ids)
        def mutate(elements):
            found = set()
            for item in elements:
                if item.get('id') in ids:
                    found.add(item.get('id'))
                    if locked:
                        item['locked'] = True
                    else:
                        item.pop('locked', None)
            missing = ids - found
            if missing:
                raise KeyError(f'unknown element ids: {sorted(missing)}')
        self._batch_edit('lock' if locked else 'unlock', mutate)

    def set_hidden(self, element_ids, hidden: bool) -> None:
        ids = set(element_ids)
        def mutate(elements):
            found = set()
            for item in elements:
                if item.get('id') in ids:
                    found.add(item.get('id'))
                    if hidden:
                        item['hidden'] = True
                    else:
                        item.pop('hidden', None)
            missing = ids - found
            if missing:
                raise KeyError(f'unknown element ids: {sorted(missing)}')
        self._batch_edit('hide' if hidden else 'show', mutate)

    def group_elements(self, element_ids, *, group_id: str) -> str:
        ids = set(element_ids)
        if len(ids) < 2:
            raise ValueError('group requires at least two elements')
        if not group_id:
            raise ValueError('group_id must not be empty')
        def mutate(elements):
            found = set()
            for item in elements:
                if item.get('id') in ids:
                    item['group'] = group_id
                    found.add(item.get('id'))
            if found != ids:
                raise KeyError(f'unknown element ids: {sorted(ids-found)}')
        self._batch_edit('group', mutate)
        return group_id

    def ungroup_elements(self, element_ids) -> None:
        ids = set(element_ids)
        def mutate(elements):
            for item in elements:
                if item.get('id') in ids:
                    item.pop('group', None)
        self._batch_edit('ungroup', mutate)

    def bring_to_front(self, element_ids) -> None:
        ids = set(element_ids)
        def mutate(elements):
            chosen = [item for item in elements if item.get('id') in ids]
            rest = [item for item in elements if item.get('id') not in ids]
            if len(chosen) != len(ids):
                raise KeyError('unknown element id')
            elements[:] = rest + chosen
        self._batch_edit('bring_to_front', mutate)

    def send_to_back(self, element_ids) -> None:
        ids = set(element_ids)
        def mutate(elements):
            chosen = [item for item in elements if item.get('id') in ids]
            rest = [item for item in elements if item.get('id') not in ids]
            if len(chosen) != len(ids):
                raise KeyError('unknown element id')
            elements[:] = chosen + rest
        self._batch_edit('send_to_back', mutate)

    def set_canvas_size(self, width: int, height: int) -> None:
        if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
            raise ValueError('canvas width must be a positive integer')
        if not isinstance(height, int) or isinstance(height, bool) or height <= 0 or height % 8 != 0:
            raise ValueError('canvas height must be a positive integer divisible by 8')
        before = (int(self.scene['canvas']['w']), int(self.scene['canvas']['h']))
        after = (width, height)
        if before == after:
            return
        self.scene['canvas']['w'] = width
        self.scene['canvas']['h'] = height
        self.scene.setdefault('storage', {})['bytes_per_frame'] = width * (height // 8)
        self.document.dirty = True
        if self.logger is not None:
            self.logger.log('CANVAS_SIZE', before={'w': before[0], 'h': before[1]}, after={'w': width, 'h': height})

    def set_state(self, name: str, value) -> None:
        self.runtime.set_state(name, value)

    def step(self, amount: int = 1) -> dict:
        return self.runtime.step(amount)

    def reset(self) -> dict:
        return self.runtime.reset()

    def render(self) -> RenderResult:
        return render_scene(self.scene, self.runtime.state, resources=self.resources)

    def validate(self) -> list[Finding]:
        return validate_scene(self.scene, dict(self.runtime.state))

    def save(self):
        return self.document.save()
