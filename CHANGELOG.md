# Changelog

## 2.0.2 - 2026-10-21

### Performance

- Export, Code AI handoff, batch validation and the thumbnail wall now run in the background. The window stays responsive, progress shows in the status bar, and Ctrl+K → "Cancel background job" stops a running job. Starting a job takes about 5 ms on the UI thread; before, these operations blocked it for hundreds of milliseconds.
- Still blocking: Automation API clients that call long methods such as `export.all` synchronously. They can use `job.start` instead.

## 2.0.1 - 2026-10-21

### Packages

- Intel macOS (`macos-x64.dmg`) and Linux arm64 (`arm64.deb`) packages. CI now builds, tests and install-tests five platforms: Windows x64, macOS arm64 and x64, and Linux amd64 and arm64.
- The application is unchanged from 2.0.0; its compatibility notes and known limitations still apply.

## 2.0.0 - 2026-10-20

MonoOLED Studio 2.0 is a full rewrite in Rust with a Slint user interface. It runs on Windows, macOS and Linux and replaces the Python/Qt 1.x line. The last 1.x source is kept at the `v1-final` tag.

### Platforms and packages

- Windows x64: zip, no installer, no Visual C++ runtime needed.
- macOS arm64: dmg with an ad-hoc signed, not notarised app. On first launch, allow it in System Settings → Privacy & Security → "Open Anyway".
- Linux amd64: `.deb` for Ubuntu 24.04 / Debian 13 or newer (`libc6 >= 2.39`). It pulls in a CJK font. The CLI is installed as `monooled-cli`.
- `SHA256SUMS` is attached to every release.

### Compatibility

- Same project, scene, asset, Font Pack and output-profile files as 1.2.3.
- Same preferences file and keys.
- Same Automation API 1.3.0 (JSON-RPC 2.0 over localhost).
- Firmware arrays, BIN and C headers are byte-identical to 1.2.3 on the frozen golden corpus.
- PNG and ZIP files have the same content, but their bytes differ because the encoder differs.
- Documented differences are listed in `docs/rewrite/G1_EVIDENCE.md` and `docs/rewrite/G4_EVIDENCE.md`.

### Performance (measured on the same Windows machine as 1.2.3)

- Encoding and formatting a 256×128 frame: about 1.5 ms (1.2.3: about 34 ms).
- Firmware export of 50 screens: about 0.3 s (1.2.3: about 0.5 s).
- Full evidence export of 50 screens: about 1.3 s (1.2.3: about 2.6 s).
- Cold start: about 0.95 s (1.2.3: about 2.1 s).

### Known limitations

- Four 2.0 performance budgets are recorded as not met. Details are in `docs/rewrite/G4_EVIDENCE.md` §4.
  - Pixel stroke to screen p95 is 20–22 ms against an 8 ms budget; most of the wait is display vsync.
  - Full evidence export of 50 screens exceeds its 500 ms budget, because every file is fsync'd.
  - Cold start sometimes exceeds 1 s.
  - Export-all, handoff, batch validation and the thumbnail wall still run on the UI thread.
- Output colour fields accept hex values only. The output font is typed by name.
- Real-hardware OLED checks, hands-on use on macOS and Linux desktops, and Intel Mac / Linux arm64 builds are not verified.

### Removed

- The Python 1.x application, its PyInstaller build and the Python CI. They are available from the `v1-final` tag.

## 1.2.3 - 2026-09-11

### Fixes

- Repolish hidden-but-created widgets during appearance switches (deferred, paint-free) so inactive tab pages, closed panels, and dropdown menus no longer keep the previous theme when shown again.

## 1.2.2 - 2026-09-06

### Fixes

- Set the first-run and corrupted-preference defaults to Simplified Chinese, Light appearance, and 100% UI scale.

### Performance

- Re-polish only visible widgets during appearance switches, keeping the application-wide theme change within the interactive latency budget at every supported DPI scale.

## 1.2.1 - 2026-09-06

### Fixes

- Keep the Windows GA Real-Qt gate strict while allowing only the documented CI-only Font Lab skip in `test_qt_v1240_windows_critical_paths.py`.

## 1.2.0 - 2026-09-06

### Features

- Add an image file output source to the workbench: color images are thresholded to 1-bit with luma/RGB thresholds and inversion; raster controls activate only for this source.
- Add viewport-edge pixel rulers to Pixel Studio with adaptive tick steps, togglable from preferences.
- Add keyboard painting: arrow keys place a canvas cursor, Enter lights, Delete/Backspace clears, Esc hides.
- Add a deterministic studio icon registry; inspector, command bar, and workbench actions recolor with the theme.
- Add a color-swatch picker for canvas background, grid, pixel fill, and pixel border colors.

### Performance

- Rebuild the pixel canvas base cache through C-level bytes expansion and an indexed QImage color table (~3x faster on large canvases); wheel zoom no longer stalls.
- Skip set_zoom work for unchanged values so Fit-mode refits stop invalidating the pixel cache.
- Patch the output preview per stroke damage instead of full rebuilds.
- Defer the theme-switch paint flush to the next event-loop frame (theme p95 at 2.5x DPI: 126ms -> 46ms).

### Fixes

- Hold the in-flight generation task until its queued completion event is delivered; busy UI threads no longer drop completions and stall the output panel.
- Theme switches now repolish every widget (Qt 6.11 keeps stale palette() rules on palette swaps alone).
- Standalone Pixel Studio windows resolve their own theme instead of inheriting a stale one.
- Clean corrupted shortcut preferences (nested dicts / 'None' values), store shortcut bindings flat, and reset the default ui_scale to 100%.
- Remove the permanently disabled raster decoration controls; pixel borders render from the visible-region pass.

### Compatibility

- Preserve the existing export.c_header, legacy Pixel C header, project schema version, Code AI handoff outputs, and the Automation API surface; RasterProfile fields remain in persisted profiles.

## 1.1.0 - 2026-09-04

### Features

- Add a unified bitmap output workbench for Pixel Studio, Designer frames, image sources, selections, and Font Packs.
- Add configurable rasterization, four bitmap traversal modes, bit order, polarity, padding, binary/text output, C51 formatting, custom wrappers, and Font Pack indexes.
- Add project-persisted output profiles and Automation API 1.3.0 methods for profile management, previews, bitmap export, and font export.
- Add trace-driven extraction animation plus direct generate, copy, save, and clear-output actions in Pixel Studio.

### Performance

- Update Pixel Studio incrementally during drawing and debounce expensive preview and byte generation work.
- Keep theme switching within the interaction budget by reusing palette-driven QSS and repolishing only top-level windows.

### Fixes

- Apply light and dark themes immediately without requiring a follow-up mouse or keyboard event.
- Handle missing GitHub release probes without failing the release check.

### Compatibility

- Preserve the existing `export.c_header`, legacy Pixel C header, project schema version, and Code AI handoff outputs.
