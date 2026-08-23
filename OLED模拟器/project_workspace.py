from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil

PROJECT_FILENAME = 'project.oled.json'
PROJECT_SCHEMA_VERSION = 1
_WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
_FORBIDDEN_NAME_CHARS = set('<>:"/\\|?*')


class InvalidProjectPath(ValueError):
    pass


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.write('\n')
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def resolve_under_root(root: str | Path, member: str | Path, *, label: str = 'project path') -> Path:
    root_path = Path(root).resolve()
    rel = Path(member)
    if rel.is_absolute():
        raise InvalidProjectPath(f'{label} must be relative: {member}')
    try:
        resolved = (root_path / rel).resolve()
    except (OSError, RuntimeError) as exc:
        raise InvalidProjectPath(f'invalid {label}: {member}') from exc
    if resolved != root_path and root_path not in resolved.parents:
        raise InvalidProjectPath(f'{label} escapes project root: {member}')
    return resolved


def validate_screen_id(screen_id: str) -> str:
    value = str(screen_id)
    if not value or value in {'.', '..'}:
        raise InvalidProjectPath('screen id must not be empty or dot path')
    if value != value.strip() or value.endswith(('.', ' ')):
        raise InvalidProjectPath(f'unsafe screen id: {screen_id}')
    if any(ord(ch) < 32 or ch in _FORBIDDEN_NAME_CHARS for ch in value):
        raise InvalidProjectPath(f'unsafe screen id: {screen_id}')
    if Path(value).name != value or '..' in Path(value).parts:
        raise InvalidProjectPath(f'unsafe screen id: {screen_id}')
    stem = value.split('.', 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise InvalidProjectPath(f'Windows-reserved screen id: {screen_id}')
    if len(value) > 96:
        raise InvalidProjectPath('screen id is too long')
    return value


@dataclass(frozen=True)
class ScreenRef:
    id: str
    label: str
    path: str


class ProjectWorkspace:
    def __init__(self, path: Path, data: dict):
        self.path = path.resolve()
        self.root = self.path.parent
        self.data = data
        self._validate_members()

    @classmethod
    def load(cls, path: str | Path) -> 'ProjectWorkspace':
        p = Path(path).resolve()
        data = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('project file must contain a JSON object')
        try:
            schema = int(data.get('schema_version', 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f'unsupported project schema: {data.get("schema_version")}') from exc
        if schema != PROJECT_SCHEMA_VERSION:
            raise ValueError(f'unsupported project schema: {data.get("schema_version")}')
        return cls(p, data)

    def _validate_members(self) -> None:
        screens = self.data.get('screens', [])
        if not isinstance(screens, list):
            raise ValueError('project screens must be a list')
        seen: set[str] = set()
        for raw in screens:
            if not isinstance(raw, dict) or 'id' not in raw or 'path' not in raw:
                raise ValueError('invalid project screen entry')
            sid = validate_screen_id(str(raw['id']))
            if sid in seen:
                raise ValueError(f'duplicate screen id: {sid}')
            seen.add(sid)
            path = str(raw['path'])
            resolved = resolve_under_root(self.root, path, label=f'screen {sid} path')
            if resolved == self.root:
                raise InvalidProjectPath(f'screen {sid} path must identify a file')
        values = self.data.get('asset_dirs', ['assets'])
        if not isinstance(values, (list, tuple)):
            raise ValueError('asset_dirs must be a list')
        for value in values:
            resolve_under_root(self.root, str(value), label='asset directory')
        active = str(self.data.get('active_screen', ''))
        if active and screens and active not in seen:
            raise ValueError(f'active_screen does not exist: {active}')

    @property
    def name(self) -> str:
        return str(self.data.get('name', self.root.name))

    @property
    def active_screen(self) -> str:
        return str(self.data.get('active_screen', self.screens[0].id if self.screens else ''))

    @property
    def screens(self) -> list[ScreenRef]:
        return [ScreenRef(str(x['id']), str(x.get('label', x['id'])), str(x['path'])) for x in self.data.get('screens', [])]

    @property
    def asset_dirs(self) -> tuple[str, ...]:
        values = self.data.get('asset_dirs', ['assets'])
        return tuple(str(v) for v in values)

    def resolve_member(self, member: str | Path, *, label: str = 'project path') -> Path:
        return resolve_under_root(self.root, member, label=label)

    def set_asset_dirs(self, values) -> None:
        checked = []
        for value in values:
            text = str(value)
            resolve_under_root(self.root, text, label='asset directory')
            checked.append(text)
        self.data['asset_dirs'] = checked
        self.save()

    def screen(self, screen_id: str) -> ScreenRef:
        for item in self.screens:
            if item.id == screen_id:
                return item
        raise KeyError(f'unknown screen id: {screen_id}')

    def screen_path(self, screen_id: str) -> Path:
        ref = self.screen(screen_id)
        return resolve_under_root(self.root, ref.path, label=f'screen {screen_id} path')

    def save(self) -> Path:
        self._validate_members()
        _atomic_json_write(self.path, self.data)
        return self.path

    def set_active_screen(self, screen_id: str) -> None:
        self.screen(screen_id)
        self.data['active_screen'] = screen_id

    def add_screen(self, screen_id: str, *, label: str | None = None, source: str | Path | None = None, canvas: tuple[int, int] | None = None) -> ScreenRef:
        screen_id = validate_screen_id(screen_id)
        if any(s.id == screen_id for s in self.screens):
            raise ValueError(f'duplicate screen id: {screen_id}')
        rel = Path('scenes') / f'{screen_id}.json'
        target = resolve_under_root(self.root, rel, label='new screen path')
        target.parent.mkdir(parents=True, exist_ok=True)
        if source is not None:
            source_path = Path(source).resolve()
            if not source_path.exists() or not source_path.is_file():
                raise FileNotFoundError(source_path)
            shutil.copy2(source_path, target)
            payload = json.loads(target.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                target.unlink(missing_ok=True)
                raise ValueError('source scene must contain a JSON object')
            payload.pop('project_root', None)
            _atomic_json_write(target, payload)
        else:
            w, h = canvas or tuple(self.data.get('default_canvas', [128, 32]))
            payload = _blank_scene(self.name, int(w), int(h))
            _atomic_json_write(target, payload)
        item = {'id': screen_id, 'label': label or screen_id, 'path': rel.as_posix()}
        self.data.setdefault('screens', []).append(item)
        self.save()
        return ScreenRef(item['id'], item['label'], item['path'])

    def duplicate_screen(self, screen_id: str, *, new_id: str, label: str | None = None) -> ScreenRef:
        return self.add_screen(new_id, label=label or new_id, source=self.screen_path(screen_id))

    def rename_screen(self, screen_id: str, *, new_id: str, label: str | None = None) -> ScreenRef:
        """Rename a screen id and its project-owned scene file atomically enough to recover.

        The file move is rolled back if manifest persistence fails.  The target always
        remains under the project root and Windows-reserved ids are rejected by the
        same validator used for screen creation.
        """
        old = self.screen(screen_id)
        new_id = validate_screen_id(new_id)
        if new_id != screen_id and any(s.id == new_id for s in self.screens):
            raise ValueError(f'duplicate screen id: {new_id}')
        old_path = self.screen_path(screen_id)
        if new_id == screen_id:
            for item in self.data.get('screens', []):
                if str(item['id']) == screen_id:
                    item['label'] = label or str(item.get('label') or new_id)
                    break
            self.save()
            return self.screen(screen_id)
        new_rel = Path('scenes') / f'{new_id}.json'
        new_path = resolve_under_root(self.root, new_rel, label='renamed screen path')
        if new_path.exists():
            raise FileExistsError(new_path)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old_path, new_path)
        previous = json.loads(json.dumps(self.data, ensure_ascii=False))
        try:
            for item in self.data.get('screens', []):
                if str(item['id']) == screen_id:
                    item['id'] = new_id
                    item['label'] = label or new_id
                    item['path'] = new_rel.as_posix()
                    break
            if self.active_screen == screen_id:
                self.data['active_screen'] = new_id
            self.save()
        except Exception:
            self.data = previous
            if new_path.exists() and not old_path.exists():
                os.replace(new_path, old_path)
            raise
        return self.screen(new_id)

    def remove_screen(self, screen_id: str, *, delete_file: bool = True) -> None:
        screens = self.data.get('screens', [])
        if len(screens) <= 1:
            raise ValueError('project must keep at least one screen')
        ref = self.screen(screen_id)
        self.data['screens'] = [x for x in screens if str(x['id']) != screen_id]
        if self.active_screen == screen_id:
            self.data['active_screen'] = str(self.data['screens'][0]['id'])
        if delete_file:
            p = resolve_under_root(self.root, ref.path, label=f'screen {screen_id} path')
            if p.exists():
                p.unlink()
        self.save()


def _blank_scene(product: str, width: int, height: int) -> dict:
    if width <= 0 or height <= 0 or height % 8:
        raise ValueError('monochrome VLSB canvas height must be a positive multiple of 8')
    return {
        'schema_version': 1,
        'product': product,
        'canvas': {'w': width, 'h': height, 'preview_scale': 6},
        'storage': {'layout': 'VLSB column-page (SSD1306)', 'bytes_per_frame': width * (height // 8), 'polarity': '1 = lit'},
        'states': {},
        'elements': [],
        'timeline': [],
    }


def create_project(root: str | Path, *, name: str, canvas: tuple[int, int] = (128, 32)) -> ProjectWorkspace:
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / 'assets').mkdir(exist_ok=True)
    (root / 'exports').mkdir(exist_ok=True)
    data = {
        'schema_version': PROJECT_SCHEMA_VERSION,
        'name': name,
        'default_canvas': [int(canvas[0]), int(canvas[1])],
        'active_screen': 'main',
        'asset_dirs': ['assets'],
        'screens': [],
    }
    project = ProjectWorkspace(root / PROJECT_FILENAME, data)
    project.add_screen('main', label='Main', canvas=canvas)
    project.set_active_screen('main')
    project.save()
    return project
