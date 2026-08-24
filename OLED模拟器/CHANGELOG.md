# Changelog

## 8.4.3 — 2026-08-24

### Windows Release & Real-Qt GA Closure

- Enforced CRLF delivery for every `.bat` / `.cmd` source-package script and added a Git EOL contract.
- Replaced the monolithic Windows pytest invocation with bounded source groups and isolated per-module Real-Qt processes with explicit timeouts, logs and JUnit evidence.
- Added repository-root pytest import isolation through `pytest.ini`, so selected Automation tests no longer depend on `cd OLED模拟器`.
- Added Windows release-text, bounded-runner and V8.4.3 release gates without changing Automation API 1.2, Renderer semantics, Golden frames or frozen clinical assets.

## 8.4.2 — 2026-08-24

### Automation Reliability & GA Closure

- Fixed the real ORTHO graduation data-loss path: transaction commit no longer implies persistence and dirty state stays true until save.
- Made `project.open_screen` fail closed on unsaved Scene changes, with explicit `save_current` / `discard_current` policies and stable `UNSAVED_CHANGES` JSON-RPC error.
- Added required transaction parameter contracts for `history.commit` / `history.rollback`.
- Unified bridge handshake and machine-contract version discovery under Automation API 1.2.0.
- Added `state.count`, summary-oriented matrix responses, and bounded server-owned `job.start/status/result/cancel` for long render/validate/export/handoff work.
- Added V8.4.2 1,000-iteration cross-screen data-safety graduation and Windows release-gate integration.
- Preserved Renderer/VLSB semantics, 464 frozen product assets and 14 Clinical Golden frames.

## 8.4.1 — 2026-08-23

### Automation State Model Closure

- Upgraded Automation API to 1.1.0 while preserving all 1.0 project/scene/pixel/font/export methods.
- Added atomic `state.validate_schema`, `state.set_schema`, and `state.validate`.
- Added explicit discrete integer domains and simple state-to-state relational constraints.
- State enumeration/render-all/validate-all now exclude illegal relational combinations deterministically.
- State-schema transactions support rollback and one Designer undo after commit.
- Font automation methods now publish real required/optional parameter contracts from the production method registry.
- Added V8.4.1 graduation/release gates without changing Renderer/Golden/product assets.

## 8.4.0 — 2026-08-23

### Final Project & Code AI Closure

- Froze Automation API 1.0 as a machine-readable contract.
- Added complete project Screen orchestration for Code AI.
- Added deterministic state enumeration and all-state render/validation.
- Added asset/pixel lifecycle, Studio-owned export and annotated preview feedback.
- Added direct and localhost JSON-RPC Code AI graduation gates.
- Extended Windows zero-skip Real-Qt release gate with project automation integration.

## 8.3.0 — 2026-08-23

### Reliability & Performance Closure

- Removed the duplicate `OLEDCanvas.mouseReleaseEvent` override and restored real marquee-release selection semantics.
- Hardened StudioSelect construction so event filters/signals are activated only after popup/list state is fully initialized.
- Added a real `--startup-smoke` that constructs `QApplication + OLEDDesignerWindow`, while `--check` is explicitly a core/runtime check.
- Added controlled `.venv-runtime` bootstrap, diagnostic launch path, launcher-source GUI startup validation, and Windows Real-Qt JUnit zero-skip enforcement.
- Made Agent Bridge timer/thread lifecycle on-demand and deterministic; application close now stops the bridge and disconnects SystemThemeProvider.
- Reworked EditorSession geometry/smart-guides so queries no longer full-render the scene; added content-hashed persistent decoded-resource cache and QImage framebuffer paint cache.
- Converted drag/nudge/align/distribute multi-element gestures to one history command per user operation.
- Added Preferences corruption quarantine, atomic FontPack/export/Scene writes, best-effort shortcut conflict preservation, and diagnostic rotating logs.
- Added V8.3 static duplicate-method, startup, marquee, lifecycle, cache, history, launcher and hot-path regression/stress gates while continuing to pin 464 product assets and 14 clinical Golden frames.

## 8.2.0 — 2026-08-23

### Native Interaction & Visual Closure

- Rebuilt StudioSelect around an explicit popup state machine and mouse-press anchor toggle so second-click close cannot be followed by a native Qt.Popup reopen.
- Replaced translucent/transparent popup content with an opaque semantic surface and rounded native mask.
- Replaced the global 180px popup width floor with content-aware sizing and actual row/font height measurement.
- Added explicit Preferences theme surfaces to eliminate dark-shell/light-page splits.
- Corrected Real-Qt production API mismatch by providing `showPopup()` / `hidePopup()` and added V8.2 anchor-toggle, alpha/bleed, row-overlap and Preferences theme-raster gates.
- Added 100,000 popup-state transitions and 50,000 popup sizing/placement adversarial cases while continuing to pin 464 product assets and 14 Golden frames.

## 8.1.0 — 2026-08-23

### Interaction & Visual Reliability Closure

- Rebuilt StudioSelect popup lifecycle so the popup closes before heavy semantic callbacks execute.
- Added singleton PopupManager and available-screen geometry placement with above/below fallback and edge clamping.
- Replaced monolithic preference application with scoped PreferenceDelta effects; UI-only settings no longer trigger product render/validation refresh.
- Routed theme/language/input updates through EditorRegistry to embedded Pixel Workspace and Font Lab.
- Removed embedded Pixel Workspace local application stylesheet ownership and added semantic theme propagation.
- Added SystemThemeProvider so System mode does not infer OS appearance from an already themed application palette.
- Added semantic status colors, full UI metrics scaling, responsive navigation/inspector sizing and additional i18n closure.
- Added V8.1 popup/transition/combination/soak gates and expanded Windows DPI release design to 100–300%.

## 8.0.0 — 2026-08-23

### Unified OLED Workspace

- Embedded Pixel Workspace and Font Lab into the main document-tab host with active-editor command routing.
- Added ordered SelectionModel, Primary Selection, Ctrl-click toggle, marquee selection and Align-to Selection/Primary/Canvas.
- Added StudioSelect/StudioPopover/StudioNumericInput control system to replace native-looking popup/stepper chrome on core surfaces.
- Added Pixel Fit zoom, anchored canvas resize, crop, 180°/270° rotation and exact FontPack bitmap-text insertion.
- Added FontPack/GlyphPack persistence, Font Lab and non-destructive `bitmap_text` Scene support while preserving legacy text rendering.
- Added semantic Code AI Automation Core, localhost token-authenticated JSON-RPC, revision guard, Scene transactions and render PNG/VLSB/resolved-element/pixel-diff feedback.
- Added V8 core/Qt/release/stress gates while continuing to pin 464 production assets and 14 clinical Golden frames.

## 7.1.0 — 2026-08-23

### Product Closure

- Added semantic Preferences normalization with atomic persistence and complete runtime-effect registry.
- Added project-root confinement for screen paths, IDs, asset roots and import targets.
- Added atomic autosave, invalid-snapshot quarantine and newest-valid recovery fallback.
- Added content-hashed asset-cache invalidation.
- Added centralized Production Studio button interaction properties and same-control keyboard-to-mouse focus cleanup.
- Wired Theme Mode, UI Scale, Input, Pixel brush, Autosave/Recovery, Performance and editable Shortcuts into runtime behavior.
- Completed Preferences zh-CN/en-US live retranslation and real maintenance actions.
- Added oversized-image guard and strict-ASCII C identifiers.
- Expanded Real-Qt release design to 288 Windows production-surface constructions.
- Added frozen V7.0 product-asset and Golden manifests plus V7.1 adversarial stress verification.

## 7.0.0 — 2026-08-23

- Rebuilt interaction states to separate hover/pressed/selected/mouse focus/keyboard focus.
- Added semantic theme tokens with Light, Dark, One Dark Pro and High Contrast themes.
- Added independent Preferences with versioned persistence; removed language selector from main workspace.
- Rebuilt Pixel Studio input: left draw, right erase, stroke interpolation, wheel zoom, middle/Space pan, flat inspector.
- Added V7 host state fuzz/soak and real Qt visual interaction/DPI matrix gates.
- Preserved canonical Renderer/Scene/Golden product truth.

## 6.0.0 — 2026-08-23

- Replaced Bento-heavy editor shell with professional canvas-first workspace.
- Added contextual Inspector + State tabs and collapsed Problems/Diff/Log drawer.
- Added Design/Review modes and persisted splitter workspace layout.
- Added fast drag-preview pipeline and interaction performance profiler.
- Avoided canvas relayout when framebuffer dimensions are unchanged.
- Rebuilt Pixel Studio around tool rail / canvas / inspector and added direct selection move.
- Added Windows pytest-qt professional workspace and DPI gates.


## 5.1.0 — 2026-08-23

- Production hardening: compact header behavior, strict crash recovery, persistent asset cache, bounded/stateful Pixel Studio undo.
- Generalized UI_SPEC project naming and current-frame C symbol naming.
- Added real Qt interaction tests, DPI matrix gates, and long-running GUI soak gate for Windows releases.
- Asset directories are now watched for new files during a session.

## 5.0.0 — 2026-08-23

- Product identity frozen as **MonoOLED Studio**; Curing-Lite is now only the bundled demonstration project.
- Official application icon added to Qt, PyInstaller and the native Windows PE resource section.
- `native_only` bitmap width/height is read-only in the Inspector and routes editing to Pixel Studio.
- Added dedicated Pixel Studio: Pencil/Eraser/Line/Rectangle/Fill/Select, clipboard, Undo/Redo, invert/flip, image binarization preview, PNG/BIN/C Header export and glyph generation.
- Added Designer ↔ Pixel Studio round-trip refresh, smart guides and optional Zone Overlay.
- Pixel Studio and Designer both support Chinese/English UI.
- Windows user entry renamed to `MonoOLEDStudio.exe`; developer PyInstaller build renamed consistently.

## 4.0.0 — 2026-08-22

- Responsive editor UX and live geometry updates.
- Project Workspace, Asset Library, multi-screen, alignment/measurement, Auto Save/recovery.
- Pixel/Scene Diff, templates, thumbnail wall, batch validation, design rules and Code AI Handoff.
- Native Windows x64 `CuringLiteOLEDDesigner.exe` user entry with Unicode standard-Python discovery; old shebang launcher remains removed.
- Dynamic monochrome OLED canvas contract retained.


## 3.0.0 — 2026-08-22

- Removed the broken v2 relative-shebang SourceLauncher.
- Fixed Windows path regression tests to use platform-native temporary paths.
- Source mode now prefers a managed `.venv-runtime`; standalone release remains PyInstaller onedir.
- Added Windows EXE check, real-window, 6-case bilingual layout and interaction smoke gates.
- Refactored Qt layout to scrollable Bento inspector rails to eliminate parameter-card overlap.
- Added live X/Y/W/H rerender, dynamic canvas presets/custom sizes and integer Auto Zoom.
- Removed global 128×32 / 512B assumptions from Canvas, Validator, Exporter and Evidence paths.
- Added external Scene/project roots and portable external bitmap import.
- Added 560-combination clinical state render/validation matrix.
- Improved WCAG AA text colors while keeping Apple-inspired visual language.
