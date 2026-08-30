# V12.4.0 Windows Critical Path Reliability Hardening

V12.4.0 closes three Windows product-critical paths that source-only gates did not cover sufficiently: real adaptive-theme startup, embedded Settings geometry convergence, and Font Lab generation/open lifecycle reliability.

## Startup

- Adaptive startup now resolves persisted `PreferencesStore` values through `RuntimeSettings` and `resolve_theme_name()` in the startup smoke path, matching normal launch.
- Adaptive palette coverage includes success/warning/error semantic tokens.
- Qt 6 QSS palette names use `tooltip-base` / `tooltip-text`.
- Editor chrome no longer assumes Undo/Redo actions exist while `QTabWidget.currentChanged` can fire during construction.

## Settings

- Embedded `PreferencesView` no longer imposes a top-level 700×520 minimum; the floating `PreferencesWindow` remains responsible for window minimum geometry.
- Narrow shell margins/navigation/gaps compress before setting content.
- Native combo/spin/button controls participate in the bounded control column.
- Setting labels wrap and the layout violation gate checks wrapped label/help vertical clipping.

## Font Lab

- Opening an existing FontPack is load-only and does not immediately rewrite the pack.
- FontPack PNG encode/decode avoids per-pixel Pillow access loops.
- TrueType/OpenType rasterization is anchored to `FontPack.baseline` instead of independently vertically centering every glyph.
- Small OLED cells choose a cell-relative default font size.
- Generate/Update executes in a `QThread`; the UI reports non-modal progress and remains locked until the thread actually finishes.
- A Font Lab tab/application close is rejected while its generation worker is running, preventing destroyed-widget callbacks or cross-pack completion.
- Successful generation selects and renders the first available glyph when no prior glyph remains selected.

## Release identity

`src/VERSION` is the canonical current release identity. Python UI surfaces use `version_info.load_version()`, and Windows builders read `src\VERSION` rather than embedding a release number.

## Certification requirement

Source tests are necessary but not sufficient. Final release certification still requires native Windows PySide6/PyInstaller GA, including startup, Settings DPI/language/theme matrices, Font Lab async generation/reopen lifecycle, package verification, and execution from the final extracted runtime ZIP.
