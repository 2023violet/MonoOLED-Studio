# MonoOLED Studio 8.1 — Interaction & Visual Reliability Closure

## Scope

V8.1 deliberately freezes Renderer, VLSB framebuffer semantics, the 14 clinical Golden frames, and the 464 frozen product assets. It changes application-shell behavior only: popup lifecycle and geometry, preference effect routing, embedded-editor preference propagation, semantic status theming, i18n closure, and UI-scale-responsive metrics.

## StudioSelect lifecycle

`StudioSelect` no longer commits a selection while its popup is still visible. Item click/activation now closes the floating surface first and schedules the commit for the next event-loop turn. `PopupManager` enforces at most one active Studio popup. Popup placement is calculated by the UI-neutral `popup_geometry.place_popup()` primitive against `QScreen.availableGeometry()`: open below when possible, open above near the lower screen edge, clamp horizontally, and constrain oversized lists.

## Preference effect routing

V8.0 applied all preference effects for every change. V8.1 introduces `PreferenceDelta`, which separates language, theme, UI metrics, canvas overlays, Pixel input, autosave, performance, shortcuts, and startup effects. Application-only appearance changes do not trigger Renderer/Validation/Diff refresh and therefore cannot intentionally mutate OLED framebuffer truth.

The Preferences window uses a 150 ms atomic-save debounce. Runtime state changes are immediate because `PreferencesStore` is updated in memory; the disk write is coalesced and flushed on close.

## Unified Workspace propagation

`EditorRegistry.apply_runtime_delta()` is the single preference bus for embedded editors. The legacy `_pixel_windows` propagation path has been removed from preference application. Embedded Pixel and Font editors implement `apply_runtime_delta()`.

Pixel Workspace inherits the global application stylesheet when embedded and updates only its editor-overlay theme and input behavior. Font Lab now supports live language and theme propagation.

## Theme architecture

V8.1 adds semantic status tokens for neutral/accent/success/warning/error states and removes StatusPill's hard-coded light palette. `SystemThemeProvider` reads the OS color scheme independently from the current custom application stylesheet.

OLED content truth remains fixed black/white. Editor overlays (grid, guide, selection, chrome) remain theme-driven.

## UI scale

`ui_metrics.build_ui_metrics()` scales control height, row height, typography, icons, gaps, margins, navigation minimum width, and inspector minimum width. `responsive_layout.plan_layout()` now accepts density and user UI scale; DPI remains the responsibility of Qt/OS and is not conflated with the user scale factor.

## i18n closure

V8.1 moves the newly introduced Font Lab, bitmap-text, Pixel transform, Agent Bridge, close/save, and performance copy into the shared translator catalog. Font Lab has a real `retranslate_ui()` method rather than construction-time-only strings.

## Platform gate

The delivery contains Real-Qt tests and Windows release gates. A Linux source packaging host without PySide6 cannot be used as evidence that Windows native popup geometry, font metrics, mixed-DPI monitor changes, or raster appearance have passed. Those remain explicit Windows gates.
