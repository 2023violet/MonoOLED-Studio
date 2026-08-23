# Unified OLED Workspace Implementation Plan

**Goal:** Upgrade MonoOLED Studio 7.1 into a unified single-window OLED IDE with tab-hosted Pixel/Font editors, authoritative multi-selection, modern Studio controls, Pixel transform/fit tools, FontPack/GlyphPack workflow, and a semantic Code AI automation bridge.

**Architecture:** Preserve renderer/scene/VLSB/Golden/product assets. Introduce focused application services and editor adapters around existing models. GUI changes consume those services; automation uses the same services rather than widget coordinates.

**Tech Stack:** Python 3.11+, PySide6, Pillow, pytest/pytest-qt.

**Spec:** `/mnt/data/MonoOLED_Studio_Unified_Workspace_AI_FontLab_Upgrade_Design_v1.0.md`

## Global Constraints
- Existing 14 Golden BIN and 464 frozen production assets must remain byte-identical.
- Pixel left mouse = draw, right mouse = erase.
- Do not redesign Curing-Lite OLED screens.
- Automation operates on semantic project/document APIs, never screen coordinates.
- New Qt controls may not change geometry across hover/focus/selected states.

### Task 1: Selection Model and Layout 2.0
- Add `selection_model.py` with ordered selection + primary id.
- Extend `selection_tools.py` with align-to selection/primary/canvas and selection measurements.
- Integrate `OLEDCanvas` Ctrl-click + marquee + ordered primary semantics.
- Remove dual `elementSelected`/`selectionChanged` ownership in `gui.py`.
- Add core + Qt tests.

### Task 2: Workspace Host and Editor Routing
- Add `workspace_host.py` with editor protocol and tab registry.
- Refactor Pixel Studio body into embeddable `PixelStudioEditor(QWidget)`; retain `PixelStudioWindow` compatibility wrapper.
- Host Designer as first editor tab; open pixel assets as tabs, not top-level windows.
- Route save/undo/redo to active editor.
- Add tab reuse/dirty/close tests.

### Task 3: Studio Control System 2.0
- Add `StudioSelect`, `StudioPopover`, `StudioNumericInput`, `StudioSegmentedControl`.
- Replace core Designer/Pixel selectors and numeric inputs.
- Add open/close/focus/raster regression tests.

### Task 4: Pixel Workspace 2.0
- Add auto-fit/shared zoom controller.
- Add canvas resize with anchor, rotate 90/180/270, flip, crop/selection transform primitives.
- Integrate toolbar/inspector controls.
- Add deterministic transform + undo tests.

### Task 5: Font Lab / FontPack
- Add `font_pack.py` manifest model and deterministic glyph generation/import.
- Add embeddable `FontLabEditor` with glyph grid + glyph Pixel editor integration.
- Add font packs to project asset discovery.
- Preserve existing font generator compatibility.
- Add glyph metrics/manifest/export tests.

### Task 6: Designer Bitmap Font Integration
- Add non-breaking bitmap-font provider path without changing legacy text semantics.
- Add a new bitmap text element renderer/schema adapter only where explicitly used.
- Add render/Golden non-regression tests.

### Task 7: Code AI Automation Core
- Add revisioned `StudioAutomationService` supporting project/scene/selection/layout/pixel/font/render/validate/history operations.
- Add transactions, stale-revision guard, structured results, session events.
- Add JSON-RPC stdio/local bridge; transport remains adapter around automation core.
- Add read-only, edit, rollback, stale-revision tests.

### Task 8: Release Verification and Packaging
- Update version/docs/manifest to 8.0.0 Unified OLED Workspace.
- Run full host suite, Qt offscreen suite when dependency is available, fuzz/stress, deterministic export, asset freeze and Golden checks.
- Build deterministic ZIP twice and compare bytes.
- Fresh-extract final ZIP and rerun verifier/test suite.
