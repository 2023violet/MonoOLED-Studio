# V12.2 Font Pipeline Validation

## Scope

V12.2 treats FontPack as a production asset pipeline shared by Font Lab, Pixel Studio, the canonical renderer, Automation API, and deterministic export.

## Validated lifecycle

`create FontPack -> generate glyphs -> save manifest/PNG -> reload -> edit glyph pixels/metrics -> compose text -> insert into PixelDocument -> undo -> render bitmap_text -> Automation get/update/set metrics -> deterministic FontPack ZIP export`

The standalone Pixel Studio font generator is also covered for PNG + `glyph_manifest.json` + VLSB C-header output and Unicode codepoint naming.

## Model-boundary hardening

- Font cell width/height must be positive.
- Baseline must stay inside the cell height.
- Pack-level and per-glyph advance must be greater than zero.
- Changing the pack-level advance explicitly propagates to existing glyph spacing, so Font Lab/Automation metric edits immediately affect already-generated text.
- Rasterization rejects invalid font size, threshold, and malformed offset before Pillow is invoked.
- Manifest glyph assets are resolved and verified to remain inside the FontPack root; `../` path escape is rejected.
- FontPack schema mismatch and missing glyph assets are rejected during load.
- Saving a regenerated pack removes stale `U+*.png` glyph files that are no longer referenced by the manifest.
- Automation metric writes use the same `FontPack.set_metrics()` validation as GUI/model callers.

## Font Lab behavior

- Baseline input is constrained to `0..cell_height-1` and updates when cell height changes.
- Generation errors from invalid/missing fonts or invalid metrics are surfaced as an explicit warning instead of leaving silent partial state.
- Saving metrics goes through the shared FontPack validator.

## Real font-file probe

The closure procedure also exercises an actual TTF file through `font_path -> rasterize -> FontPack reload -> compose -> PixelDocument insert` and requires non-zero lit pixels. This complements portable automated tests without bundling third-party font binaries.

## Regression tests

Primary V12.2 coverage lives in `tests/test_font_pipeline_e2e_v122.py`, with existing renderer, Automation, resource-cache and Pixel Studio suites retained as regression evidence.
