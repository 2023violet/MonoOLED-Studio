# MonoOLED Studio 8.4.4 — Windows Real-Qt GA Final Closure

## Scope

V8.4.4 is limited to issues reproduced from the formal V8.4.3 sealed ZIP on native Windows. It does not change Automation API 1.2.0, Renderer/VLSB semantics, Scene/Project/State/FontPack schemas, the 464 frozen product assets, the 14 Clinical Golden frames, or Curing-Lite ORTHO pixels.

## Closed failures

1. Inspector content no longer exceeds its viewport horizontally. Long alignment labels use full-width rows where required, while vertical scrolling remains intentional and accessible.
2. `layout_violations()` distinguishes horizontal clipping from controls that are only outside the current vertical scroll position.
3. startup, layout, interaction and soak smoke checks wait for two consecutive stable geometry signatures instead of using a no-op timer.
4. `StatusPill` applies syntactically valid local QSS without Qt stylesheet warnings.
5. the Windows group runner keeps UTF-8 logs byte-faithful and mirrors unencodable text safely to CP936 consoles.
6. Windows Real-Qt modules use the native `windows` QPA unless the caller explicitly overrides it; this prevents the PySide6 6.11 offscreen backend's empty font database from creating false Windows geometry results.
7. theme-only transitions update a semantic `QPalette` while the structural stylesheet remains unchanged. The existing 19 stylesheet tokens retain their exact values, representative controls remain pixel-identical to the literal stylesheet, and the original 120 ms p95 budget is unchanged.
8. keyboard focus styling honors both actual Tab key navigation and Qt's explicit `TabFocusReason`/`BacktabFocusReason`, removing process-history-dependent focus-ring results at scaled DPI.
9. explicit, zone-free Editor geometry is returned directly without resolving an asset that cannot affect those coordinates, and Renderer resource lookups reuse already-canonical paths while retaining per-render byte reads and SHA-256 content validation.
10. persistent asset-cache saves are idempotent: an unchanged serialized cache is not atomically replaced again, preventing the packaged Editor's directory watcher from feeding identical cache writes back into asset rescans during layout settlement.
11. the exact hover/leave raster regression drives the Qt Enter/Leave handlers directly, so its baseline is independent of the physical Windows cursor while still requiring a changed hover raster and byte-identical post-Leave restoration.
12. the Windows runtime ZIP checksum is generated and immediately verified by the pinned build Python. The Builder fails closed if hashing, sidecar writing or read-back verification fails; it no longer depends on PowerShell non-terminating error behavior.

The performance work does not alter the V8.3 limits (`render p95 <= 6.00 ms`, `geometry p95 <= 0.50 ms`, `smart-guides p95 <= 2.00 ms`). Three independent post-change V8.3 runs passed without changing those thresholds; observed render p95 values were 4.4836 ms, 3.7431 ms and 3.6541 ms, while geometry p95 remained between 0.0021 ms and 0.0036 ms.

## GA evidence boundary

Source and candidate results are diagnostic evidence only. GA is established only when the original `Developer_Tools\BUILD_WINDOWS_EXE.bat` from the formal V8.4.4 sealed ZIP completes from a Windows fresh extraction, followed by the public-API-only ORTHO Automation Graduation with unchanged framebuffer hashes.

The formal run must report zero Real-Qt failures, errors, skips, timeouts and unexplained Qt warnings across every discovered `test_qt_*.py` module at all eight mandatory DPI scales.

The release decision is reported as four engineering facts rather than an absolute confidence claim:

- `GA Release Gates = PASS`
- `Known blockers = 0`
- `Known P0/P1 = 0`
- `Evidence confidence = High`

These statements are permitted only after the formal sealed-ZIP fresh run and ORTHO graduation have both completed. They do not assert that unknown defects are impossible.
