# Changelog

## 2.1.0 - 2026-10-30

### Compatibility (contract changes)

- **The release gate now covers every scene export.** A scene with a blocking finding can no longer be written as a C header through the desktop menu, `mono c-header`, or the Automation API's `export.c_header`. All three now behave like `export.current`/`export.all`: no export artefact is written — not even the `reference/` and `golden/` directories — while the blocking findings are still saved as a report (`validation_report.md`, or `<zip>.validation.md` for a handoff) so the refusal is readable after the call; the CLI prints `FAIL:` and exits 2, the API returns `INVALID_REQUEST` naming every blocker, and the desktop opens a dialog that lists the blocking findings and can jump to each element. Successful exports are byte-identical to 2.0.3. Still outside the gate, on purpose: the Output Workbench and `export.bitmap_data` can render the current scene into a file of their own; gating them would change API 1.3 behaviour and needs its own decision.
- **Viewing a screen no longer rewrites the project.** Switching screens previously saved `project.oled.json` immediately; it now only changes the session. The active screen is persisted by the next explicit save, so after a restart a project reopens on the last *saved* screen. The Automation API's `project.open_screen` still writes, as documented for API compatibility.

### Added

- Inspector → **Schema** (State schema) edits the scene's state variables (type, initial value, range or value list) and the relations between them, showing the engine's own validation while you type. An accepted edit is one undo step and re-seeds the preview at once. Editing a variable's *value* still affects only the preview — the panel says so.
- Inspector → **Rules** (Design rules) edits the project's required elements, zones and baseline groups. Findings follow immediately, without reopening the project. These live in `project.oled.json` and are written as you edit them, so the title's `•` does not track that file; the panel names what it wrote.
- The Navigator renames a page. **Rename** moves the scene file with it and re-opens it under the new id.
- The canvas toolbar's **Zones** toggle (and the `canvas.zones` preference) draws the project's design zones over the canvas, in the same editor-only layer as the grid and bounds.
- The status bar shows what a running background job is doing (`Export · 12/40`) and carries a **Cancel** control; the Edit menu and status bar name what the next undo reverts ("Undo: move battery").
- Font Lab can offset the glyphs horizontally and vertically. The generator always supported `GenerateOptions::offset`; no control could set it.

### Fixed

- Keyboard shortcuts (for example `Ctrl+S`) keep working after a dialog closes: the shortcut scope now owns the dialogs, so closing one no longer leaves the window without a focus owner. Bare tool keys no longer fire behind a modal.
- Every dialog closes with Esc or a click on the dimmed backdrop; the Pixel import dialog also releases its converted image instead of leaking it.
- Preferences → Keyboard shows the configured chords again (they were stored as flat keys but read as nested paths), text fields commit on Enter and are debounced otherwise, and shortcut conflicts are rejected with a visible message.
- A failed preferences write no longer clears the pending flag, so the value the row shows is retried instead of silently lost.
- The unsaved-changes prompt names the documents that changed; undo back to the saved scene clears the title `•`; Pixel Studio is labelled as a standalone PNG that is not part of the project.
- One element now yields one diagnostic per distinct problem (a single out-of-bounds placeholder no longer reports twice), and a blocked handoff keeps its report at `<zip>.validation.md` instead of pointing at a deleted temporary directory. The thumbnail wall writes its report to `.oled/validation_report.md`.
- Automation's `export.c_header` refuses with every blocking finding, not only the first one.
- Batch validation uses the same representative state set and design rules as export and handoff, so the panel and the batch report agree.
- The Navigator scrolls to the selected page, element or glyph; a selection made from the canvas or with the arrow keys is no longer hidden below the fold.
- Font Lab keeps all three columns at the minimum window width (the generator column is no longer clipped by a long pack path, which now elides).
- An empty window offers New Project / Open Project / Open Last Project instead of an inert editor; design commands without a document report that instead of silently doing nothing.
- Icon buttons show tooltips, the View menu shows check marks, About links to the repository and documentation, and the status bar no longer keeps the previous project's message.
- The canvas overlay switches (grid, bounds, rulers, zones) are restored when a project opens, not only after you touch one.
- The State schema and Design rules panels refresh on every edit path, including the ones that go through undo and redo.
- The Output Workbench's scan-mode names, its empty-source error and its truncated-preview note were hardcoded Chinese and ignored the language setting; so was the status bar's "Pixel Truth" line. All are translated now, and the workbench now reports a real render failure instead of blaming a missing project.
- `pixel.standalone` carried the Chinese text inside the English table, so an English interface showed Chinese.
- The user manual described a marquee (rubber-band) selection the canvas does not implement; it now says pressing empty canvas clears the selection, and documents the rename, zones, schema and design-rules entries.
- `AGENTS.md` claimed that opening a screen writes the project manifest back. It does not (see Compatibility above).
- Font Lab: clearing the font file disabled the two offset rows, so an offset you had already set could not be cleared and every later generation failed while blaming the characters for needing a TrueType font. The rows stay editable, and the engine now says when it is the offset that left the built-in path.
- The Inspector's five tabs share about 290px at the minimum window width, so "State" and "State schema" elided to the same letters. The tab strip abbreviates the two long names, and the sections inside each panel still name what they edit.
- A glyph offset outside ±64 px is refused by the generator instead of overflowing its own arithmetic, which the Automation API's `font.generate` could reach directly (the Font Lab form already clamped).

### Removed

- Controls that had never been wired: the multi-document tab model (`AppModel.tabs`, `struct DocTab`), `AppModel.toast`, and the `appearance.reduced_motion` / `performance.overlay` preferences, which were stored, shown in Settings, and read by nothing.
- The Preferences rows for drag preview, validation timing and asset-cache size. Nothing read those values either; they stay in an existing `preferences.json` as inert leftovers.
- The Inspector's **Play** button: there is no animated preview, so it only ever stepped the runtime state once — which is what the remaining **Step** button says.
- 112 translation keys that no view or controller asked for, including the 1.x timeline, diff, measure and preview copy; 67 keys were added for the schema, rules, undo, workbench and dialog copy, leaving 520 per language.

### Security

- `pulldown-cmark` 0.13.5 (via Slint's markdown support) fixes RUSTSEC-2026-0414, exponential event growth with `ENABLE_WIKILINKS`. The option is off by default here; the lockfile is bumped so `cargo deny` stays clean.

### Internal

- Four scans now fail the build when a control stops telling the truth: every property and callback of the six model globals is used on both sides of the Slint bridge; every preference row reaches an accessor outside its own row table; `strings.json` is exactly paired in content and order, duplicate-free and orphan-free (including the `pref.` namespace that rows resolve by suffix), with no user-facing copy bypassing it; and `tools/tests/test_docs_match_code.py` pins the manual's claims to the code that proves them. `tools/CHECK_GUI_TRUST.py` grew to 15 end-to-end cases against the real binary.
- The orphan-key scan no longer counts a key that survives only inside a source comment as used.
- The scripted `later:` and `select-later:` hooks skip their step while a nested dialog holds the app state, the way pointer and close events already did, instead of panicking on the second borrow.

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
