# Changelog

## 2.4.1 - 2026-11-09

A patch release: Designer edit performance on large scenes and small correctness fixes from the 2.4.0 reviews. No file format, CLI output, Automation API or export behaviour changes.

### Performance

- A Designer edit no longer reads and hashes the same file again for every character or label. A render used to look a digit glyph up once per character, and a font header or font pack once per element; each lookup read the file and hashed it (and a font pack hashed every glyph in it). A render now looks each file up once, and the next render still re-reads it, so a file changed by another program still shows on the next frame. Rendered output is unchanged.
- Editing X/Y/W/H in the Inspector or nudging with the arrow keys no longer re-renders `digits` and `text` elements on a scratch canvas, no longer copies the whole element list into the undo history (undo records only the elements that changed), and no longer rebuilds the Navigator.
- Measured on the same machine on the same day (release, 3 runs; `docs/rewrite/G4_EVIDENCE.md` §4 "2026-11-08"): the worst edit handler drops from 15.0–20.5 ms to 4.5–5.9 ms on a 50-digit scene, and from 14.3–16.5 ms to 8.0–9.0 ms on a 1005-element scene. Both now meet the 16 ms budget in these runs. On the 1005-element scene, idle memory after the benchmark falls from about 196 MB to about 91–97 MB. The `curing_lite` fixture is unchanged at about 77–83 MB across runs, before and after, around its 80 MB budget; the new `dump:mem` self-check shows that the app itself holds almost nothing at that point.

### Fixed

- The Designer drawer says there is no baseline instead of "Changed … (100.00%)" when the scene did not render when it was opened.
- The `ASSET_PATH_ESCAPE` finding (a scene member outside the project root) now has a label in the findings list, in English and Chinese, instead of its raw code.
- Changelog: 2.0.4, 2.0.5 and 2.1.0 are now marked as never tagged; their changes first shipped in 2.2.0.

### Dependencies

- `cargo deny` accepts RUSTSEC-2026-0441 (`pin-utils` is unmaintained; not a vulnerability). It arrives only through Slint 1.18.1 and no Slint release drops it yet.

## 2.4.0 - 2026-11-02

This release is the 2026-10-30 to 2026-11-02 work (truthful controls, the export gate, Designer performance, project-root containment, a review pack that marks blocking findings). It was developed on a line that branched at 2.0.3, never shipped, and is integrated onto 2.3.0. Where both lines fixed the same defect, one implementation was kept; those items are listed under **Integration** instead of being announced twice.

### Compatibility (contract changes)

- **The release gate now covers every scene export.** A scene with a blocking finding can no longer be written as a C header through the desktop menu, `mono c-header`, or the Automation API's `export.c_header`. All three now behave like `export.current`/`export.all`: no export artefact is written, not even the `reference/` and `golden/` directories. The CLI prints `FAIL:` and exits 2 (with `--json`, one object with `"ok": false` and `E-EXPORT-BLOCKED`), the API returns `INVALID_REQUEST` listing the blockers (up to eight, then "... and N more"), and the desktop opens a dialog that lists the blocking findings and can jump to each element. The blockers are also saved as a report: the desktop menu writes `.oled/validation_report.md` in the project and `mono c-header` writes `<output>.validation.md`; the API's `export.c_header` writes no report. Successful exports are byte-identical to 2.3.0. Still outside the gate, on purpose: the Output Workbench and `export.bitmap_data` can render the current scene into a file of their own (gating them would change API 1.3 behaviour and needs its own decision), and so can the review pack, which shows every frame's findings next to its code and now says on its first screen when it is not a deliverable (see Added).
- **Viewing a screen no longer rewrites the project.** Switching screens, including from the screen gallery, previously saved `project.oled.json` immediately; it now only changes the session. The active screen is persisted by the next explicit save, so after a restart a project reopens on the last *saved* screen. The Automation API's `project.open_screen` still writes, as documented for API compatibility.
- **Scene members must stay inside the project root.** A project whose images, sequence directories, font headers or font packs use `../` or an absolute path outside the root validated and exported under 2.3.0; it now reports `ASSET_PATH_ESCAPE`, the export is blocked, and the scene no longer renders: the Designer shows a render failure for the whole scene, `mono simulate` exits 2 instead of 0, the screen gallery, the review evidence panel and the review pack cannot render it, the Output Workbench's current-scene source fails, and the Automation API's `render.current`, its other rendering methods and the current-scene source of `export.bitmap_data` return `INVALID_REQUEST`. Move the file into the project and reference it relatively. The check is lexical: a link or junction inside the project that points outside it is not detected. On Windows an absolute member may differ from the root in ASCII case or use the `\\?\` prefix; an 8.3 alias or a linked spelling of the root is refused. Known limitation: in a case-sensitive Windows folder, such an absolute member can name a sibling whose name differs from the root only in ASCII case. Relative members, including a sequence's `dir` plus `pattern`, are compared exactly. A standalone scene's own `project_root` defines its root (`docs/SCENE_SCHEMA.md`).
- **A blocked export's report now ends at the first blocking frame.** 2.3.0 listed every frame of the matrix; `validation_report.md`, `<zip>.validation.md` and the blocked dialog now cover the frames checked up to that point, and the report says how many of the matrix that was. This applies to the Automation API's `export.current`, `export.all` and `export.code_ai_handoff` too. Use `batch-validate` for the whole matrix.
- `export_scene` now refuses a repeated frame name instead of keeping the last one. Selection through the CLI, the desktop app and the Automation API already produces unique names, so only direct library callers can see this.

### Added

- Inspector → **Schema** (State schema) edits the scene's state variables (type, initial value, range or value list) and the relations between them, showing the engine's own validation while you type. An accepted edit is one undo step and re-seeds the preview at once.
- Inspector → **Rules** (Design rules) edits the project's required elements, zones and baseline groups. Findings follow immediately, without reopening the project. These live in `project.oled.json` and are written as you edit them, so the title's `•` does not track that file; the panel names what it wrote.
- The Navigator renames a page. **Rename** moves the scene file with it and re-opens it under the new id.
- The canvas toolbar's **Zones** toggle (and the `canvas.zones` preference) draws the project's design zones over the canvas, in the same editor-only layer as the grid and bounds.
- The status bar shows what a running background job is doing (`Export · 12/40`) and carries a **Cancel** control; the Edit menu names what the next undo reverts ("Undo: move battery").
- **A review pack with blocking findings says it is not a deliverable.** The pack is still written, because reviewing problems is its purpose, but when any rendered frame (an init frame or an annotated state) has a `BLOCKER` or `ERROR` finding the page opens with a static banner, readable without JavaScript: "Not a deliverable. N of M rendered frames have blocking findings". The text output of `mono review-pack` adds `NOT A DELIVERABLE: N of M frames have blocking findings`, `--json` adds `blocking_frames`, and the desktop status line names the count. A pack without blocking frames has no banner. The pack renders init frames and annotated states only, so the banner does not predict the export verdict exactly: an annotated state outside the export's state matrix is not checked by the export gate.
- Font Lab can offset the glyphs horizontally and vertically. The generator always supported `GenerateOptions::offset`; no control could set it.

### Performance

- A refused export no longer validates the rest of the state matrix. The gate stops at the first frame with a blocking finding and the report says how many frames were checked; a 1005-element, 560-state blocked export drops from 464 s to under 1 s and from 814 MB to about 9 MB private memory. Clean exports still validate every state before writing anything. `batch-validate` keeps evaluating the full matrix on purpose.
- Large exports keep memory flat: `ui_contract.json` and `UI_SPEC.md` are streamed frame by frame through incremental atomic writes (temp file + fsync + rename) instead of keeping every frame's contract in memory. A clean 1000-element × 560-state export (233 MB of artefacts) peaks at about 18 MB private memory. A 10 000-element matrix used to abort at multi-GB private usage; blocked, it now refuses in under 0.5 s at about 53 MB. A clean 10 000-element export has not been measured.
- A Designer edit no longer pays for every element twice. The canvas overlay and hit-testing read the rects the renderer already resolved instead of asking `geometry(id)` per element, which cloned the whole element list — and re-rendered text or digits elements on a scratch scene — once per element. On a 1005-element scene the canvas refresh drops from 375–419 ms to 9–11 ms and the worst edit handler from 445–492 ms to 20–29 ms; on a 50-digit scene the canvas refresh drops from 39–44 ms to 16–18 ms. Elements with a complete zone or explicit rect are unchanged; only renderer-sized elements take the new path. `EditorSession::geometry` now clones one element instead of the list (text and digits still render it on a scratch scene), and its scene-wide helper is shared with smart guides.
- Validation runs on a worker thread for geometry, state and rule edits and for screen opens: the handler passes a snapshot and the 60 ms job tick applies only the newest result, so findings can lag one edit by up to about two passes plus two 60 ms ticks (roughly 130 ms on the fixture, 170 ms at 1005 elements, 290 ms on 50 digits), and sustained editing shows no new findings until it pauses. A superseded pass may still be finishing, but its result is dropped. A scripted `dump:findings` still waits for the pending result, so its answers do not change. On the 50-digit scene the synchronous pass was 131–151 ms of the edit handler; the handler now measures 16–23 ms across runs, still above the 16 ms budget.
- The figures above were measured before the integration with 2.3.0. Re-measured on the integrated tree (release, Windows 10, 3 runs each; `docs/rewrite/G4_EVIDENCE.md` §4, "2026-11-02"): on the `curing_lite` fixture the worst edit handler is 4.3–10.6 ms, within budget. Idle private memory measured 62–64 MB before the refresh fix below and 74–76 MB after it (a later review run saw 76–78 MB), inside the 80 MB budget but close to it; whether the growth is the code or the machine has not been separated. On the generated scenes the integration first made things worse (a full refresh took 307–517 ms on 1005 elements, and an edit on 50 digits about twice as long). Two 2.3.0 paths caused it, and both are fixed: the Review workspace was rebuilt on every refresh even when hidden, with a pairwise element diff, and the note list rendered the scene again on every Inspector refresh. After the fix, a full refresh takes 12–15 ms on 1005 elements and 15–16 ms on 50 digits, matching the figures before the integration; the worst edit handler is 20–24 ms and 22–27 ms, still over the 16 ms budget as before. The 50-screen evidence export takes 1654–1749 ms against a 500 ms budget, and the 256×128 encode p95 is 1.84–2.04 ms against 2 ms, over budget in one run of three.
- The desktop bench measures the Designer edit path (`designer_edit_p95_ms` plus per-panel `panel_*_ms`, including the worker pass, a state edit and a full refresh), and the new `tools/BENCH_DESIGNER_PROJECT.py` builds throwaway large scenes for it. `docs/BUILD.md` and `docs/AI_HANDOFF.md` document both.

### Fixed

- Scene members can no longer read outside the project root. Image assets, sequence directories and joined `{n}`/`{d}` patterns, font headers and font packs are resolved with a containment check: `../outside.png`, absolute paths outside the root and `pattern` traversal are reported as `ASSET_PATH_ESCAPE` by validation and refused by the renderer with `E-CORE-PATH` instead of being opened. Font Lab no longer lists or opens a scene `font_pack` outside the project, and a font pack's fingerprint no longer reads a glyph asset outside the pack before the load rejects it.
- Keyboard shortcuts (for example `Ctrl+S`) keep working after a dialog closes: the dialogs live inside the shortcut scope, so closing one no longer leaves the window without a focus owner. No chord or bare tool key fires behind a modal, including the new-project, annotation and gallery overlays.
- Every dialog closes with Esc or a click on the dimmed backdrop, including 2.3.0's new-project, annotation and gallery overlays (whose backdrop click did nothing); the Pixel import dialog also releases its converted image instead of leaking it.
- Preference text fields commit on Enter and are debounced otherwise; a hand-edited nested shortcut key is still readable as a preference, but bindings come only from the flat `shortcuts` object. A failed preferences write no longer clears the pending flag, so the value the row shows is retried instead of silently lost.
- One element now yields one diagnostic per distinct problem (a single out-of-bounds placeholder no longer reports twice), and a blocked handoff keeps its report at `<zip>.validation.md` instead of pointing at a deleted temporary directory. The thumbnail wall writes its report to `.oled/validation_report.md`. A blocked report states that validation stopped at the first blocking frame and how many frames were checked; the blocked dialog and status bar count only those frames.
- Automation's `export.c_header` refuses with up to eight blocking findings (then "... and N more"), not only the first one.
- Batch validation uses the same representative state set and design rules as export and handoff, so the panel and the batch report agree.
- The Navigator scrolls to the selected page, element or glyph; a selection made from the canvas or with the arrow keys is no longer hidden below the fold.
- Font Lab keeps all three columns at the minimum window width (the generator column is no longer clipped by a long pack path, which now elides).
- Design commands without a document report that instead of silently doing nothing, and adding a screen without a project says so.
- The View menu shows check marks, About links to the repository and documentation and shows the version the binary was built as, and the status bar no longer keeps the previous project's message.
- The canvas overlay switches (grid, bounds, rulers, zones) are restored when a project opens, not only after you touch one.
- The State schema and Design rules panels refresh on every edit path, including the ones that go through undo and redo.
- The Output Workbench's scan-mode names, its empty-source error and its truncated-preview note were hardcoded Chinese and ignored the language setting; so was the status bar's "Pixel Truth" line. All are translated now, and the workbench now reports a real render failure instead of blaming a missing project.
- The user manual described a marquee (rubber-band) selection the canvas does not implement; it now says pressing empty canvas clears the selection, and documents the rename, zones, schema and design-rules entries.
- `AGENTS.md` claimed that opening a screen writes the project manifest back. It does not (see Compatibility above).
- Font Lab: clearing the font file disabled the two offset rows, so an offset you had already set could not be cleared and every later generation failed while blaming the characters for needing a TrueType font. The rows stay editable, and the engine now says when it is the offset that left the built-in path.
- A glyph offset outside ±64 px is refused by the generator instead of overflowing its own arithmetic, which the Automation API's `font.generate` could reach directly (the Font Lab form already clamped).

### Removed

- Controls that had never been wired: the multi-document tab model (`AppModel.tabs`, `struct DocTab`), `AppModel.toast`, and the `appearance.reduced_motion` and `performance.overlay` preferences, which were stored, shown in Settings, and read by nothing. The `appearance.color_theme` default is gone too: no row showed it and nothing read it.
- The Preferences rows for drag preview, validation timing and asset-cache size. Nothing read those values either; they stay in an existing `preferences.json` as inert leftovers.
- Model properties that no view read (`DesignerModel.selection-count`, `OutputModel.profile-source`, `OutputModel.profiles`) and translation keys that no view or controller asked for. Both language tables now hold the same 699 keys in the same order.

### Integration (2.3.0 and the 2026-10-30 line fixed the same thing)

- Undo back to the saved scene: `EditorSession` keeps the saved-snapshot comparison (`is_dirty()`), which also marks a restored autosave as unsaved. 2.3.0's fingerprint counter on the session is gone. Pixel documents keep 2.3.0's own save point.
- The unsaved-changes prompt keeps 2.3.0's wording per document (scene, Pixel, Font Lab, several).
- Shortcuts come from 2.3.0's command registry; a chord that another command already uses is still refused.
- The Inspector keeps 2.3.0's playback and annotation tab next to the new Schema and Rules tabs.
- The Pixel Studio header labels a document "Standalone PNG · not part of the project" only when it is not a project asset opened from the Designer.
- Opening a multi-screen project still names its blockers in the status bar, once the worker's validation result arrives.
- The window title's `•` now speaks for the project scene only. In 2.3.0 it followed the Pixel or Font Lab document while that workspace was open; those documents keep their own `●` in their panel headers.
- Renaming a page (the Navigator's **Rename**, new here, and the Automation API's `project.rename_screen`) moves its 2.3.0 annotations in `review/review.json` to the new id; before, they stayed under the old id and the renamed page showed none. A refused rename (an invalid or duplicate id) keeps the page open instead of leaving the Designer empty.

### Security

- `pulldown-cmark` 0.13.6 (via Slint's markdown support) fixes RUSTSEC-2026-0433, quadratic parsing of nested wikilinks with `ENABLE_WIKILINKS` (RUSTSEC-2026-0414 was already fixed in 2.3.0). The option is off by default here; the lockfile is bumped so `cargo deny` stays clean.

### Internal

- `mono_project::atomic::AtomicWriter` writes incrementally to a sibling temp file and only fsyncs and renames on `finish`; dropping it unfinished removes the temp file, so an aborted export leaves no partial contract or spec. Golden and reference frames are independent files, and batches already written stay on disk.
- `mono_core::render::{member_path, resolve_member, joined_member}` are the single checked member resolvers; the renderer and the validator share them.
- Four scans fail the build when a control stops telling the truth. Every property and callback of the six model globals is used on both sides of the Slint bridge. Every preference row reaches an accessor outside its own row table. `strings.json` is exactly paired in content and order, duplicate-free and orphan-free, with no user-facing copy bypassing it. `tools/tests/test_docs_match_code.py` pins the manual's claims to the code that proves them. `tools/CHECK_GUI_TRUST.py` runs end-to-end cases against the real binary, and a source test keeps every overlay, including the ones 2.3.0 added, inside the shortcut scope.
- The scripted `later:` and `select-later:` hooks skip their step while a nested dialog holds the app state, instead of panicking on the second borrow.
- Budgets, attribution and the three out-of-scope measurements (stroke, evidence pack, cold start) are recorded in `docs/rewrite/G4_EVIDENCE.md` §4. The 1005-element stress scene (20–29 ms across runs) and the 50-digit scene (16–23 ms) still exceed the 16 ms budget per edit; the remaining floor is the framebuffer rebuild, the overlay model build and V1's whole-array undo snapshot.

## 2.3.0 - 2026-10-28

This release turns the static preview into a device-level verification and review
loop, and shows the evidence the exporter already produced (golden hashes, the
contract, per-frame code) inside the app.

### Added

- **Device preview and playback.** The State tab draws the framebuffer inside a
  device bezel and the Play button actually plays: a minimum 500 ms interval
  advances the scene timeline by one tick (approximately two steps per second,
  not a real-time clock). Step pauses and
  advances once, Reset returns to the init state. A runtime event feed lists
  `RESET` and `STATE` records. Playback and preset changes are runtime-only and
  never mark the scene dirty.
- **Annotations.** Defect / decision / explanation notes anchored to the current
  screen, state and selected element, with the frame's SHA-256 and lit-pixel
  count as evidence. Notes can be added, edited and deleted from the Designer's
  批注 tab or the Review workspace; a note whose recorded frame no longer matches
  the live frame in the same state shows a stale badge.
- **Named scenarios and derived presets.** The State tab offers the init state,
  every non-initial enum value and both bounds of every int state, derived from
  the scene schema (no guessed semantics). The current state can be saved as a
  named scenario.
- **Review evidence panel.** `Review` gains a Device/Code switch (pixel diff vs
  C header and VLSB hex), a frame hash, the exported golden hash, a
  `golden match` / `frame changed` / `state not exported` / `no contract` badge,
  lit-pixel counts and the contract's visible elements. `ui_contract.json` is
  discovered at `exports/latest/`, adopted after an export, or loaded by hand.
- **Screen gallery.** A full-window overlay with one init-frame card per screen,
  grouped by category (explicit `screens[].category`, otherwise the id prefix),
  with search, All/Blocking/Annotated filters, blocker and note counts, and
  buttons to open the screen in Designer (resetting the runtime) or in Review.
  Cards render saved scenes and resources afresh whenever the gallery opens;
  annotation counts reflect the in-memory review sidecar. At most 200 screens
  are listed.
- **Review pack HTML.** One deterministic, self-contained page (inline CSS and
  JavaScript, no new dependency) with raw VLSB frames, SHA-256, lit pixels,
  findings, visible elements, C headers, hex, annotations and a contract page.
  `mono review-pack --project … --output review/review.html [--json]` and the
  File → Review pack command write it. Two runs over the same inputs are
  byte-identical, and annotation text cannot break out of the data script. The
  pack states that MonoOLED Studio has a single renderer and makes no L2 claim.
- **CLI `--json`.** `validate`, `export` and `asset-audit` accept `--json`
  (same exit codes as the text mode); README documents that `mono` ships inside
  every release package and what exit codes 0/1/2 mean.

### Fixed

- Configured shortcuts release the shortcut lookup borrow before dispatch,
  preventing a desktop panic when opening the gallery with `Ctrl+Shift+L`.

### Changed

- The View menu and command palette gain Screen gallery (`Ctrl+Shift+L`); the
  File menu gains Review pack.
- `review/review.json` is a committable sidecar: atomic writes, a fingerprint
  check that refuses to overwrite external edits, quarantine for malformed
  files, and a hard error for an unknown schema version. It is outside
  `project.oled.json` and outside the export contract.
- Documentation: new `docs/REVIEW_PACK.md`; the user guides, `AI_HANDOFF.md`,
  `SCENE_SCHEMA.md` and the docs index describe the review loop.
- Dependency: `pulldown-cmark` 0.13.4 → 0.13.5 for RUSTSEC-2026-0414 (pulled in
  by Slint; no API change), and `review/quarantine/` is ignored.

### Not in this release

- No key or hardware event model (states are explicit presets; the UI says so),
  no motor/buzzer/BLE/power simulation, no second renderer (so no L2 badge), no
  fifth workspace tab (the gallery is an overlay), and no Automation JSON or
  scene-schema changes.

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

This version was never tagged or published as a release; its changes first shipped in the tagged 2.2.0.

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

This version was never tagged or published as a release; its changes first shipped in the tagged 2.2.0.

### Added

- The welcome page lists recent projects (newest first, at most eight, no duplicates). Missing projects disappear from the list, and clicking an entry opens it with the usual unsaved-changes check. `startup.last_project` and its reopen setting are unchanged.
- A static PNG `image` element can be opened from the Designer inspector in Pixel Studio (“Edit in Pixel Studio”). The canvas uses the same decoder as the renderer, so the pixels match the scene. Template assets, BMP files, sequence assets and paths outside the project are refused with a specific reason.
- Asset edits can be saved back to the project PNG with an atomic write. The document is marked clean and the canvas is refreshed with the new asset. The asset's source polarity is preserved when it round-trips.
- If the PNG changed on disk after it was opened, saving asks before overwriting; choosing No leaves the file and the document untouched. Bitmaps whose polarity cannot be written back unambiguously are refused instead of being silently inverted.

### Fixed

- Asset-origin documents lock their size: canvas resize, 90°/270° rotation and cropping are disabled, while 180° rotation, flips and inverts still work. The top button reads “Save Asset”.

## 2.0.4 - 2026-10-24

This version was never tagged or published as a release; its changes first shipped in the tagged 2.2.0.

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
