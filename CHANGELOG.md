# Changelog

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
