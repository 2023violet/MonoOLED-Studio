# Changelog

## 2.2.1 - 2026-10-26

No application behaviour changes. The `v2.2.0` tag was cut one commit before a test-only fix, so the source snapshot attached to that release fails three tests on Windows and macOS (`image_element_asset_opens_canonical_rows`, `opening_a_project_remembers_it_once`, `asset_save_preserves_canonical_rows`): CI temporary directories can be symlinks, and those tests compared the raw temp path with the canonical path the project layer resolves. 2.2.1 re-cuts the same application from a source tree whose tests are green on every platform. The `v2.2.0` tag and its assets stay as published.

### Fixed

- Test fixtures resolve their temporary project root with `mono_project::project::py_resolve`, matching the canonical path the application stores, instead of canonicalising by hand.

## 2.2.0 - 2026-10-26

This release bundles the 2.0.4 trust fixes, the 2.0.5 project loop and the 2.1.0 professional workflow, which shipped from one branch; their detailed entries follow in the 2.1.0/2.0.5/2.0.4 sections below. Headlines:

- Shortcuts can be cleared, reset and read correctly, overlay Esc and focus behave, and the no-project state is guarded by a welcome view with a dynamic save label.
- `PixelDocument` and `EditorSession` have real save points, Font Lab reports dirty state, the output profile has apply/commit/default states, canvas assets remember their origin, verify SHA-256 before an atomic write-back, and recent projects are remembered.
- One command registry drives menus, the palette and shortcuts; Diff Review is a side-by-side workspace; the Code AI Bridge is a non-modal panel with permissions; Pixel colours follow the theme; Font Lab has a true 1-bit preview; validation findings are localised.

### Added

- New Project opens a wizard instead of a bare folder picker: project name (defaults to the folder name), canvas width and height (default 128×32), and inline validation. Height must be a multiple of 8; invalid input never creates a half-written project.
- Help menu now offers Keyboard Shortcuts, the User Manual (local `docs/USER_GUIDE_CN.md`/`USER_GUIDE_EN.md` when present, otherwise the GitHub copy) and Report an Issue.
- Icon buttons, ordinary buttons and Pixel tool buttons show hover tooltips; Pixel tool buttons also carry visible short labels, and the pixel selection outline has a contrasting outer stroke.

### Changed

- The Chinese UI uses one term per concept (场景 for Scene/screen containers, 像素工作室, 字库实验室, 差异评审, 实际输出预览, 帧缓冲, 叠加层, 像素基准, 生成位图数组). A glossary is appended to both user guides.
- `DESIGN_SYSTEM.md` is rewritten around `theme.slint`/`widgets.slint` as the current truth; `AI_HANDOFF.md` documents the background-job, save-point, asset write-back, output-profile, recent-project and command-registry contracts.
- A version-consistency test keeps `Cargo.toml`, `ui/main.slint`, `.ai/CURRENT_STATE.md` and `CHANGELOG.md` on the same version.

### Fixed

- The Agent Bridge panel's Start/Stop/copy buttons did nothing: the panel fired the `AgentModel` callback while the app listened on `AppModel`'s.
- The bridge permission combo could disagree with the running bridge, and the Font Lab preview scale was pinned to 12×: Slint's `ComboBox.selected` carries the row label, not its index.

## 2.1.0 - 2026-10-25

### Added

- One command registry (`apps/mono-desktop/src/commands.rs`) now drives the menus, the command palette, configurable shortcuts and fixed chords. The palette covers 25+ actions, shows each command's current shortcut, and filters out commands whose context is unavailable. Adding a command touches one list plus its dispatch branch.
- Diff Review is a real workspace: the last opened/saved frame and the current frame are shown side by side, the changed-pixel bounds are outlined, and added/removed/modified elements are listed. The Designer diff drawer keeps its numbers. No version history is implied.
- Code AI Bridge is a non-modal panel. It shows the endpoint and permission (Observe / Edit / Full), keeps the token masked until revealed, and copies either the token or the full endpoint. Changing the permission restarts the bridge with a new token and invalidates connected clients. No dialog blocks the window, and the token never appears in logs.
- Pixel Studio colours follow the active theme (Light / Dark / High contrast) by default. High contrast is selectable in Preferences, “Follow theme” is a switch in the display settings, and editing any colour switches to custom without losing the stored values. Older preference files with custom colours migrate to `custom`.
- Font Lab shows a true 1-bit preview strip (white lit on black, 4×/8×/12×) next to the editing canvas, with a Real preview switch; the glyph/pack save state remains visible.
- Validation findings start with a localized label (e.g. “缺少必需元素 — …”) while keeping the original English detail and the finding code. All 23 codes are covered in both languages.

### Fixed

- Switching to the Review workspace no longer mutates the Designer drawer tab.
- The Agent Bridge no longer opens a modal dialog and no longer depends on a one-shot token popup.

## 2.0.5 - 2026-10-24

### Added

- The welcome page lists recent projects (newest first, at most eight, no duplicates). Missing projects disappear from the list, and clicking an entry opens it with the usual unsaved-changes check. `startup.last_project` and its reopen setting are unchanged.
- A static PNG `image` element can be opened from the Designer inspector in Pixel Studio (“Edit in Pixel Studio”). The canvas uses the same decoder as the renderer, so the pixels match the scene. Template assets, BMP files, sequence assets and paths outside the project are refused with a specific reason.
- Asset edits can be saved back to the project PNG with an atomic write. The document is marked clean and the canvas is refreshed with the new asset. The asset's source polarity is preserved when it round-trips.
- If the PNG changed on disk after it was opened, saving asks before overwriting; choosing No leaves the file and the document untouched. Bitmaps whose polarity cannot be written back unambiguously are refused instead of being silently inverted.

### Fixed

- Asset-origin documents lock their size: canvas resize, 90°/270° rotation and cropping are disabled, while 180° rotation, flips and inverts still work. The top button reads “Save Asset”.

## 2.0.4 - 2026-10-24

### Fixed

- Preferences → Keyboard no longer shows blank shortcut fields. `shortcuts.*` preferences are read as flat keys, so the eight commands show their real bindings. A binding can be cleared, and clearing it no longer reports a conflict with other empty fields.
- Each shortcut row has a "restore default" button.
- Window-level shortcuts work again after closing a dialog or overlay. Esc closes every overlay and returns focus to the canvas.
- Undoing back to the last saved state now clears the unsaved marker for Pixel documents and scenes instead of staying dirty forever. External file changes and Automation edits still mark the document dirty.

### Added

- A first-run welcome screen with the next steps. Actions that need a project, an export target or a handoff target are disabled and explain what is missing, and the save button names the object it saves.
- Font Lab shows whether the current glyph or the whole pack is unsaved, and the unsaved-changes prompt now names the affected objects (scene, pixel document, font pack).
- Output profiles have explicit states: editing and browsing stay in memory, "Save to project" writes them, and "Set as project default" marks the default. A builtin can be the default without being copied into the project. Opening a project loads its active profile, and the profile row shows builtin/project/draft state plus the default marker.

## 2.0.3 - 2026-10-23

### Performance

- When an Automation API client calls `render.all_states`, `validate.all_states` or `export.all` synchronously through the bridge, the call is now computed on a worker thread from a snapshot. The desktop window no longer freezes, and the client receives the same response. Revision and permission checks still run first.

### Security

- tokio 1.54.1 fixes RUSTSEC-2026-0384, a race in `tokio::time::Interval`. tokio is only used by the Linux desktop-portal file dialogs. clipboard-win is updated to 5.4.3 because 5.4.1 was yanked.

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
