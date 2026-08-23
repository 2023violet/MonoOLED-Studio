from __future__ import annotations
from dataclasses import dataclass
from runtime_settings import RuntimeSettings

@dataclass(frozen=True)
class PreferenceDelta:
    before: RuntimeSettings
    after: RuntimeSettings
    effects: frozenset[str]

    @classmethod
    def between(cls,before:RuntimeSettings,after:RuntimeSettings)->'PreferenceDelta':
        effects=set()
        if before.language!=after.language: effects.add('language')
        if (before.theme_mode,before.color_theme)!=(after.theme_mode,after.color_theme): effects.add('theme')
        if (before.density,before.ui_scale)!=(after.density,after.ui_scale): effects.add('metrics')
        if (before.grid,before.bounds,before.rulers,before.zones,before.snap)!=(after.grid,after.bounds,after.rulers,after.zones,after.snap): effects.add('canvas')
        if (before.wheel_action,before.middle_pan,before.space_pan,before.brush_size,before.stroke_interpolation,before.pixel_grid,before.actual_preview)!=(after.wheel_action,after.middle_pan,after.space_pan,after.brush_size,after.stroke_interpolation,after.pixel_grid,after.actual_preview): effects.add('pixel')
        if (before.autosave_enabled,before.autosave_interval_ms,before.autosave_snapshots,before.prompt_recovery)!=(after.autosave_enabled,after.autosave_interval_ms,after.autosave_snapshots,after.prompt_recovery): effects.add('autosave')
        if (before.drag_preview,before.validation_mode,before.undo_history,before.asset_cache_mb,before.performance_overlay)!=(after.drag_preview,after.validation_mode,after.undo_history,after.asset_cache_mb,after.performance_overlay): effects.add('performance')
        if before.shortcuts!=after.shortcuts: effects.add('shortcuts')
        if (before.reopen_last_project,before.last_project)!=(after.reopen_last_project,after.last_project): effects.add('startup')
        return cls(before,after,frozenset(effects))

    @property
    def language_changed(self): return 'language' in self.effects
    @property
    def theme_changed(self): return 'theme' in self.effects
    @property
    def ui_metrics_changed(self): return 'metrics' in self.effects
    @property
    def canvas_changed(self): return 'canvas' in self.effects
    @property
    def pixel_changed(self): return 'pixel' in self.effects
    @property
    def autosave_changed(self): return 'autosave' in self.effects
    @property
    def performance_changed(self): return 'performance' in self.effects
    @property
    def shortcuts_changed(self): return 'shortcuts' in self.effects
    @property
    def startup_changed(self): return 'startup' in self.effects
    @property
    def appearance_changed(self): return bool(self.effects & {'theme','metrics'})
    @property
    def requires_product_render(self):
        # Application preferences must never mutate the OLED product framebuffer.
        return False
