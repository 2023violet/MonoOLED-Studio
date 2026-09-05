from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from atomic_io import unique_temp_path

SCHEMA_VERSION = 1


def _defaults() -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'language': 'zh_CN',
        'startup': {'reopen_last_project': False, 'last_project': ''},
        'appearance': {
            'theme_mode': 'system',
            # Legacy compatibility only; hidden from Preferences and ignored by Theme Closure V10.1.
            'color_theme': 'monooled-light',
            'density': 'comfortable',
            'ui_scale': '100%',
            'reduced_motion': False,
        },
        'input': {'wheel_action': 'zoom', 'middle_drag': 'pan', 'space_drag': 'pan'},
        'canvas': {'grid': True, 'bounds': True, 'rulers': True, 'zones': False, 'snap': 0},
        'pixel_studio': {
            # Product interaction is intentionally fixed: left draws, right erases.
            # These legacy keys remain for backward compatibility but are normalized.
            'left_button': 'draw', 'right_button': 'erase', 'brush_size': 1,
            'stroke_interpolation': True, 'pixel_grid': True, 'actual_preview': True,
            'rulers': True,
        },
        'autosave': {'enabled': True, 'interval_minutes': 3, 'snapshots': 10, 'prompt_recovery': True},
        'performance': {
            'drag_preview': 'fast', 'validation_mode': 'edit_complete', 'undo_history': 200,
            'asset_cache_mb': 512, 'overlay': False,
        },
        'shortcuts': {
            'preferences.open': 'Ctrl+,', 'workspace.canvas_only': 'Ctrl+Space',
            'project.save': 'Ctrl+S', 'designer.undo': 'Ctrl+Z', 'designer.redo': 'Ctrl+Y',
            'pixel.pencil': 'B', 'pixel.select': 'M', 'pixel.fill': 'F',
        },
    }


def default_preferences() -> dict[str, Any]:
    return deepcopy(_defaults())


def preferences_path() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MonoOLEDStudio'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'monooled-studio'
    return base / 'preferences.json'


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _path_get(data: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = data
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _path_set(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split('.')
    node = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _enum_validator(allowed: set[Any]) -> Callable[[Any, Any], Any]:
    def validate(value: Any, default: Any) -> Any:
        try:
            return value if value in allowed else default
        except TypeError:
            return default
    return validate


def _bool_validator(value: Any, default: Any) -> bool:
    return value if isinstance(value, bool) else bool(default)


def _int_range(lo: int, hi: int) -> Callable[[Any, Any], int]:
    def validate(value: Any, default: Any) -> int:
        if isinstance(value, bool):
            return int(default)
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return int(default)
        return parsed if lo <= parsed <= hi else int(default)
    return validate


def _ui_scale_validator(value: Any, default: Any) -> str:
    if value == 'auto':
        return 'auto'
    if isinstance(value, str) and value in {'90%', '100%', '110%', '125%', '150%'}:
        return value
    return str(default)


def _shortcut_validator(value: Any, default: Any) -> str:
    if not isinstance(value, str):
        return str(default)
    value = value.strip()
    if not value or value.casefold() in {'none', 'null'}:
        # Historical writers emitted str(None); a shortcut can never be that
        # string, so treat it as the untouched default binding.
        return str(default)
    return value


_VALIDATORS: dict[str, Callable[[Any, Any], Any]] = {
    'language': _enum_validator({'zh_CN', 'en_US'}),
    'startup.reopen_last_project': _bool_validator,
    'startup.last_project': lambda value, default: value if isinstance(value, str) else str(default),
    'appearance.theme_mode': _enum_validator({'system', 'light', 'dark'}),
    'appearance.color_theme': _enum_validator({'monooled-light', 'monooled-dark', 'one-dark-pro', 'high-contrast'}),
    'appearance.density': _enum_validator({'compact', 'comfortable', 'spacious'}),
    'appearance.ui_scale': _ui_scale_validator,
    'appearance.reduced_motion': _bool_validator,
    'input.wheel_action': _enum_validator({'zoom', 'none'}),
    'input.middle_drag': _enum_validator({'pan', 'none'}),
    'input.space_drag': _enum_validator({'pan', 'none'}),
    'canvas.grid': _bool_validator,
    'canvas.bounds': _bool_validator,
    'canvas.rulers': _bool_validator,
    'canvas.zones': _bool_validator,
    'canvas.snap': _enum_validator({0, 1, 2, 4, 8}),
    'pixel_studio.left_button': _enum_validator({'draw'}),
    'pixel_studio.right_button': _enum_validator({'erase'}),
    'pixel_studio.brush_size': _int_range(1, 8),
    'pixel_studio.stroke_interpolation': _bool_validator,
    'pixel_studio.pixel_grid': _bool_validator,
    'pixel_studio.actual_preview': _bool_validator,
    'pixel_studio.rulers': _bool_validator,
    'autosave.enabled': _bool_validator,
    'autosave.interval_minutes': _int_range(1, 60),
    'autosave.snapshots': _int_range(1, 100),
    'autosave.prompt_recovery': _bool_validator,
    'performance.drag_preview': _enum_validator({'fast', 'exact'}),
    'performance.validation_mode': _enum_validator({'edit_complete', 'idle', 'continuous'}),
    'performance.undo_history': _int_range(10, 2000),
    'performance.asset_cache_mb': _int_range(32, 4096),
    'performance.overlay': _bool_validator,
}

for _shortcut_key in _defaults()['shortcuts']:
    _VALIDATORS[f'shortcuts.{_shortcut_key}'] = _shortcut_validator


PUBLIC_PREFERENCE_KEYS = tuple(_VALIDATORS)


def _sanitize_shortcuts_section(merged: dict[str, Any]) -> None:
    """Keep the shortcuts section flat with one entry per known command.

    The preferences UI writes dotted command ids (``shortcuts.designer.undo``),
    which the generic dotted setter stores as nested dicts, and historical
    writers emitted literal ``'None'`` strings.  Resolve both spellings into
    flat keys, prefer the nested spelling when it carries a usable value (it is
    what the UI last wrote), drop unknown commands, and reset junk values to
    the default binding.  The "retain future keys" promise applies to unknown
    top-level fields, not to this closed command namespace.
    """
    shortcuts = merged.get('shortcuts')
    if not isinstance(shortcuts, dict):
        return
    known = _defaults()['shortcuts']
    junk_markers = {'', 'none', 'null'}

    def usable(candidate: Any) -> bool:
        return isinstance(candidate, str) and bool(candidate.strip()) and candidate.strip().casefold() not in junk_markers

    cleaned: dict[str, Any] = {}
    for command_id, default_value in known.items():
        nested: Any = shortcuts
        for part in command_id.split('.'):
            if isinstance(nested, dict) and part in nested:
                nested = nested[part]
            else:
                nested = None
                break
        if usable(nested):
            value = nested
        elif usable(shortcuts.get(command_id)):
            value = shortcuts[command_id]
        else:
            value = default_value
        value = value.strip()
        cleaned[command_id] = value if value else default_value
    merged['shortcuts'] = cleaned


def normalize_preferences(raw: Any) -> dict[str, Any]:
    """Merge and semantically validate preferences without deleting future keys.

    A syntactically-valid JSON file is not automatically a valid preferences file.
    Each known field is normalized independently; unknown/future fields are retained.
    """
    incoming = deepcopy(raw) if isinstance(raw, dict) else {}
    merged = _deep_merge(_defaults(), incoming)
    merged['schema_version'] = SCHEMA_VERSION
    defaults = _defaults()
    for dotted, validator in _VALIDATORS.items():
        default = _path_get(defaults, dotted)
        value = _path_get(merged, dotted, default)
        _path_set(merged, dotted, validator(value, default))
    _sanitize_shortcuts_section(merged)
    # Fixed product semantics cannot be reconfigured by stale/future files.
    _path_set(merged, 'pixel_studio.left_button', 'draw')
    _path_set(merged, 'pixel_studio.right_button', 'erase')
    return merged


def migrate_preferences(raw: dict[str, Any] | None) -> dict[str, Any]:
    # Keep legacy migration intentionally small. Semantic normalization below is
    # the authority and is safe even when schema_version itself is malformed.
    migrated = deepcopy(raw) if isinstance(raw, dict) else {}
    try:
        version = int(migrated.get('schema_version', 0) or 0)
    except (TypeError, ValueError, OverflowError):
        version = 0
    if version <= 0 and 'theme' in migrated:
        appearance = migrated.get('appearance')
        if not isinstance(appearance, dict):
            appearance = {}
            migrated['appearance'] = appearance
        appearance['color_theme'] = migrated.pop('theme')
    return normalize_preferences(migrated)


@dataclass
class PreferencesStore:
    path: Path = field(default_factory=preferences_path)
    data: dict[str, Any] = field(default_factory=default_preferences)

    @classmethod
    def load(cls, path: str | Path | None = None) -> 'PreferencesStore':
        target = Path(path) if path else preferences_path()
        try:
            raw = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        except (json.JSONDecodeError, UnicodeError):
            # Preserve corrupt user data for diagnosis before falling back.
            try:
                quarantine = target.parent / 'quarantine'
                quarantine.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
                copy = quarantine / f'preferences.corrupt.{stamp}.json'
                copy.write_bytes(target.read_bytes())
            except OSError:
                pass
            raw = {}
        except OSError:
            raw = {}
        return cls(target, migrate_preferences(raw))

    def save(self) -> Path:
        self.data = normalize_preferences(self.data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = unique_temp_path(self.path)
        try:
            with tmp.open('w', encoding='utf-8', newline='\n') as fp:
                json.dump(self.data, fp, ensure_ascii=False, indent=2)
                fp.write('\n')
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        return self.path

    @staticmethod
    def _shortcut_command_id(dotted: str) -> str | None:
        prefix = 'shortcuts.'
        if not dotted.startswith(prefix):
            return None
        return dotted[len(prefix):]

    def get(self, dotted: str, default=None):
        command_id = self._shortcut_command_id(dotted)
        if command_id is not None:
            # Shortcut bindings live as flat keys inside the shortcuts section;
            # the dotted path spells the command id, not a nested dict.
            section = self.data.get('shortcuts')
            if isinstance(section, dict) and command_id in section:
                return section[command_id]
            return default
        return _path_get(self.data, dotted, default)

    def set(self, dotted: str, value: Any, *, save: bool = True) -> None:
        previous = deepcopy(self.data) if save else None
        command_id = self._shortcut_command_id(dotted)
        if command_id is not None:
            known = _defaults()['shortcuts']
            validated = _shortcut_validator(value, known.get(command_id, ''))
            section = self.data.get('shortcuts')
            if not isinstance(section, dict):
                section = {}
                self.data['shortcuts'] = section
            section[command_id] = validated
        else:
            _path_set(self.data, dotted, value)
            # Normalize only known fields immediately; future keys are untouched.
            if dotted in _VALIDATORS:
                default = _path_get(_defaults(), dotted)
                _path_set(self.data, dotted, _VALIDATORS[dotted](value, default))
            if dotted == 'pixel_studio.left_button':
                _path_set(self.data, dotted, 'draw')
            elif dotted == 'pixel_studio.right_button':
                _path_set(self.data, dotted, 'erase')
        if save:
            try:
                self.save()
            except Exception:
                self.data = previous
                raise

    def reset_section(self, section: str) -> None:
        defaults = _defaults()
        if section not in defaults:
            raise KeyError(section)
        previous = deepcopy(self.data)
        self.data[section] = deepcopy(defaults[section])
        try:
            self.save()
        except Exception:
            self.data = previous
            raise
