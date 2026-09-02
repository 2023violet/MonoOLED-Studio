from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Iterable

from atomic_io import atomic_write_json


class ExternalModificationError(RuntimeError):
    pass


class SceneDocument:
    def __init__(self, scene: dict, logger=None):
        self.scene = scene
        self.logger = logger
        self.dirty = False
        self.refresh_elements()
        current_path=Path(scene['_path']).resolve() if scene.get('_path') else None
        recorded_path=Path(scene['_disk_path']).resolve() if scene.get('_disk_path') else None
        self._disk_fingerprint = str(scene.get('_disk_sha256') or '') if current_path is not None and recorded_path == current_path else None
        if self._disk_fingerprint is None:self._disk_fingerprint=self._fingerprint_path()

    def _fingerprint_path(self) -> str | None:
        path=self.scene.get('_path')
        if not path:return None
        target=Path(path)
        try:return sha256(target.read_bytes()).hexdigest() if target.exists() else None
        except OSError:return None

    def refresh_elements(self) -> None:
        self._elements_by_id = {}
        for element in self.scene.get('elements', []):
            self._elements_by_id.setdefault(element.get('id'), element)

    def element(self, element_id: str) -> dict:
        try:
            return self._elements_by_id[element_id]
        except KeyError as exc:
            raise KeyError(f'unknown element id: {element_id}') from exc

    @staticmethod
    def _parts(path: str | Iterable[str]) -> list[str]:
        if isinstance(path, str):
            parts = [p for p in path.split('.') if p]
        else:
            parts = [str(p) for p in path]
        if not parts:
            raise ValueError('field path must not be empty')
        return parts

    @staticmethod
    def _get_nested(obj: dict, parts: list[str]):
        cur = obj
        for name in parts:
            cur = cur[name]
        return cur

    @staticmethod
    def _set_nested(obj: dict, parts: list[str], value) -> None:
        cur = obj
        for name in parts[:-1]:
            cur = cur[name]
        cur[parts[-1]] = value

    def set_field(self, element_id: str, path: str | Iterable[str], value) -> None:
        element = self.element(element_id)
        parts = self._parts(path)
        before = self._get_nested(element, parts)
        if before == value:
            return
        self._set_nested(element, parts, value)
        if parts == ['id']:
            self.refresh_elements()
        self.dirty = True
        if self.logger is not None:
            self.logger.log(
                'EDIT', element=element_id, field='.'.join(parts),
                before=before, after=value,
            )

    def move(self, element_id: str, dx: int = 0, dy: int = 0) -> None:
        if not isinstance(dx, int) or not isinstance(dy, int):
            raise TypeError('dx/dy must be integer pixels')
        element = self.element(element_id)
        zone = element.get('zone') if isinstance(element.get('zone'), dict) else None

        if dx:
            moved = False
            if zone is not None and 'x' in zone:
                self.set_field(element_id, 'zone.x', int(zone['x']) + dx)
                moved = True
            if 'x' in element:
                self.set_field(element_id, 'x', int(element['x']) + dx)
                moved = True
            if not moved:
                raise KeyError(f'{element_id} has no editable X coordinate')

        if dy:
            moved = False
            # A text zone is the authoring box while an explicit element.y is
            # the glyph baseline/top inside that box. Move both so their
            # relative offset remains invariant during visual drag operations.
            if zone is not None and 'y' in zone:
                self.set_field(element_id, 'zone.y', int(zone['y']) + dy)
                moved = True
            if 'y' in element:
                self.set_field(element_id, 'y', int(element['y']) + dy)
                moved = True
            if not moved:
                raise KeyError(f'{element_id} has no editable Y coordinate')

    def save(self) -> Path:
        if '_path' not in self.scene:
            raise ValueError('scene has no _path; load it through load_scene or assign a target')
        target = Path(self.scene['_path'])
        current=self._fingerprint_path()
        if self._disk_fingerprint is not None and current != self._disk_fingerprint:
            raise ExternalModificationError(f'scene was externally modified: {target}')
        if self._disk_fingerprint is None and current is not None:
            raise ExternalModificationError(f'scene file appeared externally: {target}')
        data = {k: v for k, v in self.scene.items() if not str(k).startswith('_')}
        atomic_write_json(target,data)
        self._disk_fingerprint=self._fingerprint_path()
        self.scene['_disk_path']=str(target.resolve())
        self.scene['_disk_sha256']=self._disk_fingerprint
        self.dirty = False
        if self.logger is not None:
            self.logger.log('SAVE', path=str(target))
        return target
