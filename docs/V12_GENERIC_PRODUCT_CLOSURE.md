# MonoOLED Studio V12 — Generic Product Closure

## Product boundary

V12 is a generic 1-bit OLED authoring workbench. The default scene is product-neutral. Curing-Lite remains available only as a regression/test fixture under `test_assets/projects/curing_lite/`.

## Repository layout

- `src/` — production Python application and generic runtime scene.
- `tests/` — source and contract regression tests.
- `tools/` — developer, verification, and Windows build tools.
- `test_assets/` — regression fixtures and frozen historical assets.
- `docs/` — current product documentation only.
- `.github/` — source repository automation.

All distributed paths are ASCII-only. The obsolete root `MonoOLEDStudio.exe` launcher is not shipped. Windows binaries are generated from tagged current source by `tools/BUILD_WINDOWS_GA.bat` and distributed through GitHub Releases; `BUILD_WINDOWS_QUICK.bat` is developer-only.

## V12 interaction closure

- Global **Run** menu removed. Timeline UI is exposed only through explicit Preview capabilities.
- Pixel Studio Line and Rectangle tools render live pixel previews during drag and commit once on release; Fill remains immediate.
- Preferences content is centered and responsive up to 760 px.
- `StudioSelect` derives geometry from polished Qt size hints.
- OLED grid remains visible at low zoom using adaptive 1/2/4/8 major-grid stride.
- Main and Pixel Studio canvas splitters cannot collapse the central canvas to 0 px.
- Settings is a true toggle. Design/Review always reactivate the Scene Editor.
- Theme changes directly replace the active stylesheet and repolish widgets; there is no empty-QSS intermediate frame.
- Windows caption/border/text colors use DWM best-effort attributes while retaining native window chrome.

## Verification contract

A V12 source package is releasable only after production-source compilation, test collection, grouped regression, package verification, frozen-asset hash verification, and independent ZIP extraction verification. Native Real-Qt Windows verification is owned by `tools/VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py` and the Windows GA builder.

## Source delivery

`python tools/BUILD_DELIVERY_V120.py` is the authoritative V12 source-package builder. It regenerates `SHA256SUMS.txt`, enforces ASCII-only release paths, writes a deterministic ZIP, and creates a verified SHA-256 sidecar.

