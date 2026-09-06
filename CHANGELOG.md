# Changelog

## 1.2.2 - 2026-09-06

### Fixes

- Set the first-run and corrupted-preference defaults to Simplified Chinese, Light appearance, and 100% UI scale.

## 1.2.1 - 2026-09-06

### Fixes

- Keep the Windows GA Real-Qt gate strict while allowing only the documented CI-only Font Lab skip in `test_qt_v1240_windows_critical_paths.py`.

## 1.2.0 - 2026-09-06

### Features

- Add an image file output source to the workbench: color images are thresholded to 1-bit with luma/RGB thresholds and inversion; raster controls activate only for this source.
- Add viewport-edge pixel rulers to Pixel Studio with adaptive tick steps, togglable from preferences.
- Add keyboard painting: arrow keys place a canvas cursor, Enter lights, Delete/Backspace clears, Esc hides.
- Add a deterministic studio icon registry; inspector, command bar, and workbench actions recolor with the theme.
- Add a color-swatch picker for canvas background, grid, pixel fill, and pixel border colors.

### Performance

- Rebuild the pixel canvas base cache through C-level bytes expansion and an indexed QImage color table (~3x faster on large canvases); wheel zoom no longer stalls.
- Skip set_zoom work for unchanged values so Fit-mode refits stop invalidating the pixel cache.
- Patch the output preview per stroke damage instead of full rebuilds.
- Defer the theme-switch paint flush to the next event-loop frame (theme p95 at 2.5x DPI: 126ms -> 46ms).

### Fixes

- Hold the in-flight generation task until its queued completion event is delivered; busy UI threads no longer drop completions and stall the output panel.
- Theme switches now repolish every widget (Qt 6.11 keeps stale palette() rules on palette swaps alone).
- Standalone Pixel Studio windows resolve their own theme instead of inheriting a stale one.
- Clean corrupted shortcut preferences (nested dicts / 'None' values), store shortcut bindings flat, and reset the default ui_scale to 100%.
- Remove the permanently disabled raster decoration controls; pixel borders render from the visible-region pass.

### Compatibility

- Preserve the existing export.c_header, legacy Pixel C header, project schema version, Code AI handoff outputs, and the Automation API surface; RasterProfile fields remain in persisted profiles.

## 1.1.0 - 2026-09-04

### Features

- Add a unified bitmap output workbench for Pixel Studio, Designer frames, image sources, selections, and Font Packs.
- Add configurable rasterization, four bitmap traversal modes, bit order, polarity, padding, binary/text output, C51 formatting, custom wrappers, and Font Pack indexes.
- Add project-persisted output profiles and Automation API 1.3.0 methods for profile management, previews, bitmap export, and font export.
- Add trace-driven extraction animation plus direct generate, copy, save, and clear-output actions in Pixel Studio.

### Performance

- Update Pixel Studio incrementally during drawing and debounce expensive preview and byte generation work.
- Keep theme switching within the interaction budget by reusing palette-driven QSS and repolishing only top-level windows.

### Fixes

- Apply light and dark themes immediately without requiring a follow-up mouse or keyboard event.
- Handle missing GitHub release probes without failing the release check.

### Compatibility

- Preserve the existing `export.c_header`, legacy Pixel C header, project schema version, and Code AI handoff outputs.
