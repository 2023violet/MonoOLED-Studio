# MonoOLED Studio 8.2 — Native Interaction & Visual Closure

MonoOLED Studio 8.2 retains the unified OLED IDE and closes native Select/Popup and theme-surface defects found through Windows use. The canonical Renderer / Scene / Framebuffer / Golden pipeline remains the machine truth; the upgrade is concentrated in document hosting, selection/layout, pixel authoring, bitmap fonts and semantic Code AI automation.

## V8 highlights

- **Unified Workspace Tabs** — Designer, Pixel assets and Font Lab live in one main window. Pixel Studio no longer opens a second top-level window in the integrated workflow.
- **Selection 2.0** — ordered multi-selection, explicit Primary Selection, `Ctrl + Left Click` toggle, marquee selection, multi-object bounds/spacing, Align to Selection / Primary / Canvas.
- **Control System 2.0** — Studio-owned Select/Popover/Numeric/Segmented controls replace native-looking popup/stepper chrome in core surfaces.
- **Pixel Workspace 2.0** — Fit zoom, canvas resize with 9 anchors, crop, 90°/180°/270° rotation, flips, exact FontPack bitmap-text insertion and one-gesture Undo semantics.
- **Font Lab** — FontPack/GlyphPack manifest, glyph pixel editor, cell/baseline/advance metrics, deterministic rasterization and `bitmap_text` Scene integration.
- **Code AI Automation** — semantic Scene/Selection/Layout/Pixel/Font/Render/Validation API, localhost token-authenticated JSON-RPC, observe/edit/full permissions, optimistic revision guard and atomic Scene transactions.
- **Render feedback** — framebuffer VLSB, SHA-256, rendered PNG, resolved element geometry and state-to-state pixel diff are available to automation clients.

## Frozen truth

V8 must not alter the frozen Curing-Lite product assets or the 14 clinical Golden frames. `VERIFY_PACKAGE.py` and `Developer_Tools/VERIFY_V80_STRESS.py` enforce this.

See `UNIFIED_WORKSPACE_V80.md`, `TEST_MATRIX_V80.md`, `USER_GUIDE_CN.md` and `FINAL_VERIFICATION_REPORT.md`.
