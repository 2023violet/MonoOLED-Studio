# MonoOLED Studio 7.1 — Preferences System

V7 removes language switching from the professional workspace header. Global user preferences live in a separate non-modal Preferences window (`Ctrl+,`).

## Information architecture

1. General
2. Appearance
3. Input
4. Shortcuts
5. Canvas
6. Pixel Studio
7. Autosave & Recovery
8. Performance
9. Advanced
10. About

Settings use a flat section hierarchy rather than nested dashboard cards.

## Ownership

`UserPreferences` contains personal application behavior: language, appearance, input, shortcuts, canvas overlays, Pixel Studio behavior, autosave and performance. Project resolution, render format, asset roots and validation contracts remain project-owned and are not duplicated in global Preferences.

## Themes

Semantic theme tokens are the single color vocabulary. V7 ships:

- MonoOLED Light
- MonoOLED Dark
- One Dark Pro
- High Contrast

Density is separate from theme: Compact / Comfortable / Spacious.

## Persistence

Preferences are JSON with `schema_version=1` and explicit migration. Unknown future keys are preserved instead of silently resetting the file.
