# V12.3 Compact Preferences Closure

MonoOLED Studio V12.3 replaces the V12.2 SaaS-card Settings presentation with a compact professional desktop-preferences system inspired by Linear/Raycast density and developer-tool information architecture.

## Frozen presentation contract

- Top-level pages: General, Appearance, Canvas & Input, Pixel Studio, Keyboard, Recovery, Advanced.
- About is not a full settings page; product/version metadata lives at the bottom of the navigation column.
- Ordinary settings are borderless `SettingRow` units. Only the Danger Zone uses a bordered card.
- Main settings content is centered and capped at 760 px; navigation is 172 px; header search is capped at 280 px.
- Section-to-section rhythm is 30 px. Rows use 10 px vertical padding with restrained 1 px dividers.
- Standard rows place copy on the left and a 220 px control column on the right.
- Compact rows explicitly stack label/help/control. The breakpoint is based on the active `QScrollArea.viewport().width()` at 620 px, not the entire Preferences view.
- Search remains bilingual and jumps to matching settings. Saved feedback is transient. Reduced Motion and reset confirmation remain real runtime behaviors.

## Overlap prevention

V12.3 intentionally removes `QFormLayout` from Settings. Each `SettingRow` owns its standard and compact geometry through `QGridLayout`. This avoids deferred form-row wrapping and height recalculation when language, DPI, theme, density, and UI scale change together.

The Real-Qt Windows gate must continue checking Settings at all release DPI scales; source contracts additionally reject reintroduction of ordinary cards, `QFormLayout`, whole-view breakpoints, and 1120 px content width.


## V12.3.1 reliability addendum

The V12.3 visual/IA contract remains current. Geometry reliability, viewport-driven reflow, overlap invariants, Settings-specific soak, and Windows visual evidence are now governed by `V12_3_1_SETTINGS_RELIABILITY.md`.
