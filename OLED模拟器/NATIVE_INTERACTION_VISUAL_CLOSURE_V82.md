# MonoOLED Studio 8.2 — Native Interaction & Visual Closure

## Purpose

V8.2 is driven by actual Windows screenshots from V8.1, not by a generic style refresh. The screenshots demonstrated four product defects: popup content visually bleeding into underlying controls, narrow selects opening unnecessarily wide lists, a second anchor click reopening instead of closing, and Preferences content surfaces staying light under dark themes.

## StudioSelect V2

`StudioSelect` now owns an explicit Qt-independent `PopupStateMachine` with closed/opening/open/closing/commit-pending/disabled states and typed close reasons. The owner button installs an event filter so a second anchor **mouse press** closes the popup before `QAbstractButton.clicked` can reopen it. This also covers the Windows-native `Qt.Popup` sequence where the popup may auto-hide before the anchor receives its click callback.

The product interaction contract is:

- first anchor click → open;
- second anchor click → close and remain closed;
- item click → close first, commit on next event-loop turn;
- Escape → close without changing value;
- outside click → close;
- opening another StudioSelect → old popup closes;
- owner/page hide → popup closes;
- theme/language/metric changes → transient popup closes before application restyling.

## Opaque Popup Surface

V8.1 used `WA_TranslucentBackground` on the top-level popup and a transparent `QListWidget`. Windows screenshots showed the underlying property form through the dropdown. V8.2 removes that combination. The popup and list viewport are semantic opaque panel surfaces. Rounded corners use a QPainterPath/QRegion window mask; no child list is allowed to paint beyond the rounded native region.

## Content-aware Geometry

V8.1 forced every popup to at least 180 px. V8.2 measures the current UI font and item labels and chooses:

`max(anchor width, content width + padding, compact minimum)`

bounded by the active screen. A Snap select containing `Off / 1 px / 2 px / 4 px / 8 px` therefore remains compact instead of covering nearby buttons. Popup height sums actual item/font row metrics, preventing row overlap after DPI, density or font changes.

## Preferences Theme Surface

Preferences now declares explicit semantic surfaces:

- `PreferencesRoot`
- `PreferencesNavigation`
- `PreferencesStack`
- `PreferencesScroll`
- `PreferencesViewport`
- `PreferencesPage`

Dark/One Dark/High Contrast themes no longer depend on the native/Fusion default palette for the right-side page background.

## Frozen OLED Truth

No changes to Renderer, VLSB layout, clinical state semantics, 14 Golden frames or the 464 frozen product assets are permitted by this release. UI-only changes must leave the product framebuffer byte-identical.

## Release policy

Host/Core and adversarial state/geometry tests are executable on the Linux packaging host. Native popup raster and mouse lifecycle tests require PySide6/pytest-qt and Windows. The Windows gate is part of the delivery and is mandatory for a Windows GA standalone artifact.
