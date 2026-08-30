# V12.4.1 Settings + Font Reliability Hardening

V12.4.1 is a corrective release driven by real Windows screenshots and Font Lab usage. It does not treat V12.4.0 source-test success as sufficient evidence for visual correctness.

## Settings row geometry

The V12.4.0 Settings implementation allowed wrapped label/help copy and the right-side control to participate in the same `QGridLayout` row-span geometry. On Windows this could allocate an insufficient height to wrapped help text even when static overlap checks appeared clean. The visible result was clipped Chinese help copy, dividers crossing text, and adjacent setting rows appearing stacked on top of each other.

V12.4.1 replaces that row model with two independent siblings: a vertical text column containing label + help copy and a control column containing the control. Standard mode uses left-to-right flow; compact mode switches the two complete columns to top-to-bottom flow. No label/help widget shares a grid row with a spanning control. Translation, resize, density/scale changes, viewport layout requests, and page switches refresh the row geometry.

Acceptance remains geometry-based: no horizontal scrollbar, no label/help clipping, no text/control overlap, no row/section overlap. A new Real-Qt matrix specifically covers the user-reported Appearance, Canvas & Input, and Recovery pages in zh_CN/en_US at 100%, 125%, and 150% UI scale on a desktop-sized embedded Settings viewport.

## Built-in readable OLED 5x7 font

Blank Font Lab source now means **Built-in OLED 5x7**, not an implicit system TrueType font. The built-in family is hand-authored and deterministic, with canonical A-Z, 0-9 and `/` glyphs. A standard `Clinical 5x7` pack uses a 5x8 storage cell with the seven ink rows ending on the shared baseline and one safety row below it.

Representative shapes such as A, B, E, N, 0, 8 and `/` are locked by exact bitmap regression tests. The full default character set is also required to produce non-empty glyphs, preventing the previous small-cell failure where characters such as `I` could threshold to an empty bitmap.

The default source is host-independent: generation does not depend on Windows font discovery, Pillow locating DejaVu Sans, or a user-installed typeface. Choosing a TTF/OTF file explicitly switches to the imported-font path.

## Shared baseline and auto-fit

New packs derive baseline and advance from the cell. While the user has not explicitly overridden these fields, changing cell dimensions updates baseline, advance and preferred font size automatically. Imported TrueType fonts are measured as a family: representative ascenders/descenders/wide glyphs are fitted as one batch and a single shared baseline is selected from the union of their ink bounds. Individual glyphs are never vertically centered independently.

Explicit baseline/advance/font-size edits become user overrides and are preserved across later cell changes where applicable.

## Generation performance

FontPack persistence now supports changed-glyph writes. A generation batch writes each changed/new glyph asset at most once and commits `fontpack.json` once; unchanged glyph PNG files are not re-encoded. Opening an existing FontPack remains load-only and does not call save.

The Qt generation worker remains on `QThread`. Progress signals are bounded to roughly 50 UI updates for large batches instead of emitting one UI update for every character. Font Lab refreshes the glyph list/canvas once after success.

On the current Linux source-model environment, the built-in 37-character A-Z/0-9/`/` batch measured approximately 0.03 s, a 37-glyph reload approximately 0.01 s, and a one-glyph update approximately 0.002 s. These are diagnostic model numbers, not Windows GA performance claims.

## Release gates

Source delivery requires: package verifier PASS, full source pytest gate with zero failures/errors, deterministic double ZIP build, byte-identical ZIPs, SHA-256 sidecar, safe empty-directory extraction, internal `SHA256SUMS.txt` verification, Windows batch-file CRLF verification, and a second full source gate from the extracted final ZIP.

Windows GA additionally requires the native Windows Real-Qt matrix at all configured DPI scales and the source/EXE/post-extract startup, layout, Settings, Font and interaction smokes. A source package must not be described as Windows GA Final unless that native Windows evidence has actually been produced.
