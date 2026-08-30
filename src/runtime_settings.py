from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from preferences import PreferencesStore, default_preferences, normalize_preferences


def _flatten(data: dict[str, Any], prefix: str = '') -> list[str]:
    out: list[str] = []
    for key, value in data.items():
        dotted = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            out.extend(_flatten(value, dotted))
        else:
            out.append(dotted)
    return out


def parse_ui_scale(value: Any) -> float:
    if value == 'auto' or value in (None, ''):
        return 1.0
    if isinstance(value, str) and value.endswith('%'):
        try:
            return max(0.75, min(2.0, float(value[:-1]) / 100.0))
        except ValueError:
            return 1.0
    try:
        return max(0.75, min(2.0, float(value)))
    except (TypeError, ValueError):
        return 1.0


EXPOSED_RUNTIME_KEYS = tuple(k for k in _flatten(default_preferences()) if k != 'schema_version')

RUNTIME_EFFECTS = {
    'language': 'Designer/Preferences/Pixel Studio live retranslation',
    'startup.reopen_last_project': 'gui.main startup source selection',
    'startup.last_project': 'project open/close persistence for startup source',
    'appearance.theme_mode': 'theme_system.resolve_theme_name system/light/dark policy',
    'appearance.color_theme': 'legacy compatibility field; ignored by appearance resolver',
    'appearance.density': 'qt_theme control metrics',
    'appearance.ui_scale': 'qt_theme scaled metrics and application font scale',
    'appearance.reduced_motion': 'Preferences navigation and optional UI motion suppression',
    'input.wheel_action': 'PixelCanvas.wheelEvent zoom gate',
    'input.middle_drag': 'PixelCanvas middle-button pan gate',
    'input.space_drag': 'PixelCanvas Space+left pan gate',
    'canvas.grid': 'OLEDCanvas editor grid visibility',
    'canvas.bounds': 'OLEDCanvas element bounds visibility',
    'canvas.rulers': 'OLEDCanvas ruler visibility',
    'canvas.zones': 'Designer zone overlay visibility',
    'canvas.snap': 'Designer snap increment',
    'pixel_studio.left_button': 'fixed product semantic: left mouse sets 1',
    'pixel_studio.right_button': 'fixed product semantic: right mouse clears 0',
    'pixel_studio.brush_size': 'PixelCanvas pencil brush footprint',
    'pixel_studio.stroke_interpolation': 'PixelCanvas Bresenham interpolation gate',
    'pixel_studio.pixel_grid': 'PixelCanvas grid visibility',
    'pixel_studio.actual_preview': 'Pixel Studio actual-size preview visibility',
    'autosave.enabled': 'Designer autosave timer enable gate',
    'autosave.interval_minutes': 'Designer autosave timer interval',
    'autosave.snapshots': 'AutoSaveManager retention limit',
    'autosave.prompt_recovery': 'startup recovery dialog gate',
    'performance.drag_preview': 'fast versus exact drag-preview refresh policy',
    'performance.validation_mode': 'continuous/edit-complete/idle validation policy',
    'performance.undo_history': 'EditorSession and PixelDocument history limits',
    'performance.asset_cache_mb': 'AssetLibrary persistent metadata cache bound',
    'performance.overlay': 'Designer performance status visibility',
    'shortcuts.preferences.open': 'CommandRegistry -> Preferences QAction',
    'shortcuts.workspace.canvas_only': 'CommandRegistry -> Canvas Only QAction',
    'shortcuts.project.save': 'CommandRegistry -> Save QAction',
    'shortcuts.designer.undo': 'CommandRegistry -> Undo QAction',
    'shortcuts.designer.redo': 'CommandRegistry -> Redo QAction',
    'shortcuts.pixel.pencil': 'Pixel Studio QShortcut -> Pencil',
    'shortcuts.pixel.select': 'Pixel Studio QShortcut -> Select',
    'shortcuts.pixel.fill': 'Pixel Studio QShortcut -> Fill',
}

# Fail fast during development if a default setting is added without an explicit
# runtime effect declaration.
if set(EXPOSED_RUNTIME_KEYS) != set(RUNTIME_EFFECTS):
    missing = sorted(set(EXPOSED_RUNTIME_KEYS) - set(RUNTIME_EFFECTS))
    extra = sorted(set(RUNTIME_EFFECTS) - set(EXPOSED_RUNTIME_KEYS))
    raise RuntimeError(f'preference runtime-effect registry drift: missing={missing}, extra={extra}')


@dataclass(frozen=True)
class RuntimeSettings:
    language: str
    reopen_last_project: bool
    last_project: str
    theme_mode: str
    color_theme: str
    density: str
    ui_scale: float
    reduced_motion: bool
    wheel_action: str
    middle_pan: bool
    space_pan: bool
    grid: bool
    bounds: bool
    rulers: bool
    zones: bool
    snap: int
    brush_size: int
    stroke_interpolation: bool
    pixel_grid: bool
    actual_preview: bool
    autosave_enabled: bool
    autosave_interval_ms: int
    autosave_snapshots: int
    prompt_recovery: bool
    drag_preview: str
    validation_mode: str
    undo_history: int
    asset_cache_mb: int
    performance_overlay: bool
    shortcuts: dict[str, str]

    @classmethod
    def from_preferences(cls, source: PreferencesStore | dict[str, Any]) -> 'RuntimeSettings':
        data = source.data if isinstance(source, PreferencesStore) else source
        p = normalize_preferences(data)
        return cls(
            language=p['language'],
            reopen_last_project=bool(p['startup']['reopen_last_project']),
            last_project=str(p['startup']['last_project']),
            theme_mode=str(p['appearance']['theme_mode']),
            color_theme=str(p['appearance']['color_theme']),
            density=str(p['appearance']['density']),
            ui_scale=parse_ui_scale(p['appearance']['ui_scale']),
            reduced_motion=bool(p['appearance']['reduced_motion']),
            wheel_action=str(p['input']['wheel_action']),
            middle_pan=p['input']['middle_drag'] == 'pan',
            space_pan=p['input']['space_drag'] == 'pan',
            grid=bool(p['canvas']['grid']), bounds=bool(p['canvas']['bounds']), rulers=bool(p['canvas']['rulers']), zones=bool(p['canvas']['zones']), snap=int(p['canvas']['snap']),
            brush_size=int(p['pixel_studio']['brush_size']), stroke_interpolation=bool(p['pixel_studio']['stroke_interpolation']), pixel_grid=bool(p['pixel_studio']['pixel_grid']), actual_preview=bool(p['pixel_studio']['actual_preview']),
            autosave_enabled=bool(p['autosave']['enabled']), autosave_interval_ms=int(p['autosave']['interval_minutes']) * 60_000, autosave_snapshots=int(p['autosave']['snapshots']), prompt_recovery=bool(p['autosave']['prompt_recovery']),
            drag_preview=str(p['performance']['drag_preview']), validation_mode=str(p['performance']['validation_mode']), undo_history=int(p['performance']['undo_history']), asset_cache_mb=int(p['performance']['asset_cache_mb']), performance_overlay=bool(p['performance']['overlay']),
            shortcuts=dict(p['shortcuts']),
        )
