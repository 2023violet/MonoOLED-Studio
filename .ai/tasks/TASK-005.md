# TASK-005 — 2.0.5 Project Loop (Phase 2)

Status: DONE
Review Status: PASS (independent review 2026-10-24: PASS WITH MINOR NOTES — no Critical/Important issues; all gates re-verified)

## Goal

Close the project loop identified by the 2026-10-24 CXO report: recent projects on the welcome page (T9), opening a project image asset in Pixel Studio (T10), and safe atomic write-back with external-modification protection and locked dimensions (T11). Ship as 2.0.5 without changing Automation JSON, golden fixtures, or the Scratch-document behaviour.

## Background

Phase 1 (2.0.4) is DONE (TASK-004). The approved plan is `C:\Users\16429\.qoder\plans\faint-pool-trout.md`; this TASK covers its Phase 2 tasks T9–T11 only. The CXO report found that only `startup.last_project` is remembered, that Pixel Studio always opens a 32×16 scratch document, and that project assets cannot be reached from the Designer.

## Current Problem

- Preferences store a single `startup.last_project`; there is no recent list and the welcome page cannot reopen anything without File → Open.
- `PixelStudio::blank()` is the only entry point; a project PNG asset selected in the Designer has no path into Pixel Studio.
- There is no write-back path, so even a read-only asset view would be a dead end.

## Evidence

- `apps/mono-desktop/src/prefs.rs:13` (startup defaults), `:78-117` (validation), `:145-162` (load/normalize)
- `apps/mono-desktop/src/app.rs:182-206` (`open_project`, only `last_project`)
- `apps/mono-desktop/src/main.rs:789-800` (startup open logic)
- `apps/mono-desktop/ui/welcome.slint` (no recent list)
- `apps/mono-desktop/src/pixel.rs` (scratch-only studio)
- `crates/mono-project/src/resources.rs` (`decode_bitmap`), `project.rs::resolve_member`

## Required Changes

1. **T9 — recent projects:** add `startup.recent_projects` (default `[]`, array-of-strings validation), `App::recent_projects()` (filter missing files), `remember_project` (canonical POSIX path, dedupe, newest first, cap 8), `AppModel.recent-projects` + `recent-chosen(int)`, welcome list, index-based guarded open. Keep `last_project` working.
2. **T10 — asset into Pixel:** `PixelOrigin` (`Scratch`/`Png`/`Asset`), `open_asset`, asset-aware title; `App::open_element_asset` accepts only literal `.png` image elements inside the project root, decodes through the canonical bitmap path, refuses templates/BMP/sequences with a specific reason; Inspector action “edit in Pixel Studio” with `can-edit-asset`; do not touch Scratch behaviour.
3. **T11 — atomic write-back:** explicit save from an asset-origin document, atomic write inside the project root, external-change guard (compare stored SHA/fingerprint before writing), dimension lock (no resize of asset documents), and tests for conflict/refusal paths.

## Architecture

- Recent projects are a preference list of absolute POSIX paths; reads filter non-existent files, writes dedupe/cap. Opening goes through `open_path_guarded` with an index callback, never a path embedded in an action string.
- Pixel documents carry an explicit origin; Scratch documents never write to a project. Asset documents remember root/relative path/SHA/inverted flag.
- Write-back reuses the existing atomic-write helper and the project's external-modification fingerprint rules; a changed file is reported, not overwritten.
- All new UI state is computed in Rust; Slint only binds and forwards events.

## Out of Scope

Phases 3–4 (command registry/palette, review workspace, Agent panel, theme palette, Font preview, localization, Help, new-project wizard, docs truth-up). No Automation JSON changes, no golden/test_asset edits, no release/tag/push.

## Protected Existing Work

- `fixtures/golden/` and `test_assets/` are frozen.
- The 2.0.4 changes in this worktree are approved context: do not revert or rewrite them.
- Atomic writes, project/scene fingerprints, and external-modification checks must remain intact.
- No pre-existing user work is present in this worktree; verify with `git status` before each task.

## Constraints

- CI gates: `cargo fmt --all -- --check`; `cargo clippy --workspace --all-targets --locked -- -D warnings`; `cargo test --workspace --locked`; `python -m pytest tools/tests -q`; `cargo deny check`.
- GUI checks must use isolated `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` and copies of `test_assets`.
- Prefer existing helpers; do not duplicate persistence, decoding, or render logic.
- Keep changes scoped to the allowed files; document deviations in Result.
- Stop at `Status: VERIFY`; independent review may promote to DONE.

## Allowed Files / Expected Area

- `apps/mono-desktop/src/prefs.rs`
- `apps/mono-desktop/src/app.rs`
- `apps/mono-desktop/src/main.rs`
- `apps/mono-desktop/src/guard.rs`
- `apps/mono-desktop/src/pixel.rs`
- `apps/mono-desktop/src/pixel_ui.rs`
- `apps/mono-desktop/ui/welcome.slint`
- `apps/mono-desktop/ui/main.slint`
- `apps/mono-desktop/ui/designer.slint`
- `apps/mono-desktop/i18n/strings.json`
- `crates/mono-project/src/resources.rs`
- `crates/mono-project/src/project.rs`
- `crates/mono-core/src/pixel.rs`
- `.ai/tasks/TASK-005.md`
- `.ai/CURRENT_STATE.md`
- `Cargo.toml`, `Cargo.lock`, `CHANGELOG.md` (phase close-out only)

## Acceptance Criteria

1. Opening two projects and restarting shows both on the welcome page, newest first; reopening a project does not duplicate it; deleting a project removes its entry; the list is capped at 8; `last_project` still works and its reopen setting is unchanged.
2. A static PNG `image` element can be opened in Pixel Studio and shows the renderer-canonical pixels; templates, BMP, sequence assets, and paths outside the project root are refused with a specific message.
3. An asset-origin document cannot be resized; saving writes atomically inside the project root; if the file changed externally since opening, the save is refused instead of overwriting.
4. Scratch documents behave exactly as before and never write into a project.
5. T9–T11 focused tests, the full workspace test suite, and clippy pass; golden/test_assets untouched.
6. 2.0.5 version metadata (`Cargo.toml`, `Cargo.lock`, `CHANGELOG.md`, `.ai/CURRENT_STATE.md`) updated at phase close-out only.

## Verification Plan

- Focused: `cargo test -p mono-desktop prefs`, `cargo test -p mono-desktop app`, `cargo test -p mono-desktop pixel`.
- Full: fmt, clippy, workspace tests, pytest, deny.
- GUI isolation: temp config dirs + `test_assets` copy; recent list, asset open, refused asset types, external-change save refusal, resize lock.
- Manual matrix: welcome with 0/1/2 recent projects, missing entry, asset open from Inspector, save-back, external edit conflict, 1100×700 and 1440×900.

## Deliverables

Code, tests, GUI evidence, and a Result section listing actual commands/results, skipped checks, and deviations. Do not mark PASS/DONE; independent review owns that.

## Result

### T9 — recent projects (implemented)

- `startup.recent_projects` added to preference defaults (`[]`); `valid` accepts only arrays of strings, and `normalize` falls back to `[]` for malformed files.
- `App::recent_projects()` returns absolute stored paths filtered to files that still exist, newest first. `remember_project` stores the POSIX path, removes duplicates, inserts at the front, and caps at 8. `open_project` calls it and still performs a single `prefs.save()`; `startup.last_project` and `reopen_last_project` are unchanged.
- `AppModel` gained `recent-projects` and `recent-chosen(int)`. `refresh_app` builds labels from the project folder name (falling back to the full path). `WelcomeView` lists them above the Open/New buttons.
- The Rust callback resolves the index against the filtered list, opens through `open_path_guarded` (unsaved prompt included), then refreshes; no path is embedded in an action string.
- Tests: `recent_projects_dedupe_and_cap`, `missing_recent_entries_are_filtered`, `opening_a_project_remembers_it_once`, `recent_list_persists`, `invalid_recent_schema_falls_back`.
- GUI (isolated config, two copies of `curing_lite` named `proj-alpha` / `proj-beta`): opening alpha then beta and relaunching without a project showed 最近项目 = `proj-beta` (newest), `proj-alpha`. Deleting the beta folder removed it from the list. With only alpha left, clicking the `proj-alpha` row opened the project (window title became “Curing-Lite OLED”). Opening the same project again did not duplicate its entry.
- Deviation: the plan listed an `open-recent` action; the welcome callback is enough for T9 (no menu/palette entry needed), so only `recent-chosen` was wired.
- Note: the stored list keeps stale paths until they are displaced; reads filter them, so a deleted project disappears from the UI without rewriting preferences.

### T10 — open a project asset in Pixel Studio (implemented)

- `PixelStudio` gained `PixelOrigin` (`Scratch` / `Png` / `Asset { root, rel, element_id, sha256, inverted }`). `replace` sets Scratch or Png; the new `open_asset` sets an Asset origin. `is_asset()` and `title()` (“asset: <rel>”) are asset-aware; Scratch behaviour is unchanged.
- `App::asset_member` validates the element: type `image`, non-empty literal `asset`, no `{`/`}`, extension `.png` (case-insensitive), resolved through `ProjectWorkspace::resolve_member` (inside the project root). Distinct errors: `asset.not_static_image`, `asset.template`, `asset.not_png`, `asset.no_project`, `asset.no_selection`.
- `App::open_element_asset` decodes through `DiskResources::decode_bitmap` (the canonical renderer path), builds the document with `PixelDocument::from_rows`, asks about unsaved Pixel edits only after the asset validates, switches to Pixel Studio, and reports `status.asset_opened`. `can_edit_asset()` drives the inspector button.
- Designer inspector: “在 Pixel Studio 中编辑” button bound to `DesignerModel.can-edit-asset`; the new action goes through `handle_action` and uses the primary selection.
- Tests: `image_element_asset_opens_canonical_rows` (rows equal the decoder output, origin/SHA/inverted, workspace switch, status), `template_asset_is_refused`, `bmp_asset_is_refused`, `image_seq_has_no_asset_target`, `asset_outside_root_is_refused`.
- GUI (isolated config, `curing_lite` copy): switched to the `main` screen, selected `running_icon`; the inspector showed `assets/clinical_ui/running.png` with the new button enabled. Clicking it opened Pixel Studio with title `asset: assets/clinical_ui/running.png`, a 24×12 canvas showing the same artwork, and status `资产：assets/clinical_ui/running.png`.
- Deviation: `confirm_unsaved_pixel` and `undo_limit` became `pub(crate)` so `open_element_asset` (in `app.rs`) can reuse them instead of duplicating the save prompt.
- Not GUI-verified: the disabled state for template/BMP elements (covered by unit tests; switching back to the Designer segment by coordinate was unreliable in the automation session).

### Gate evidence (after T10)

- `cargo fmt --all -- --check` — pass.
- `cargo clippy --workspace --all-targets --locked -- -D warnings` — pass.
- `cargo test --workspace --locked` — 135 passed / 0 failed (mono-desktop 82).
- `python -m pytest tools/tests -q` — 21 passed, 1 skipped.
- `fixtures/golden/` and `test_assets/` untouched; no commit/tag/push performed.

### T11 — atomic write-back, external-change guard, size lock (implemented)

- `PixelStudio::save_asset(force)` resolves the stored `root`/`rel` inside the project, compares the file's SHA-256 with the one recorded at open time, and returns `E-ASSET-EXTERNAL-MODIFICATION` when they differ unless `force` is set. It writes with the existing atomic helper, updates the recorded SHA, and calls `mark_saved()`.
- Polarity: the preferred encoding preserves the source polarity; if that would decode back to different canonical rows, the complement is tried. If neither round-trips, the save is refused with `E-ASSET-ENCODE-POLARITY` instead of silently inverting the rendered result.
- `save_asset` on a Scratch/Png document returns `E-ASSET-NOT-ASSET`; Scratch still never writes into a project.
- `asset_locked()` guards `resize`, `rotate90`, `rotate270` and `crop` in `try_action`/`resize` (`E-ASSET-SIZE-LOCKED`); 180° rotation, flips and inverts stay allowed. The UI disables the same buttons and the canvas-size action.
- `pixel_save` routes asset documents to a new `pixel_save_asset`: external-change errors ask “资源已被外部修改，是否覆盖？” in interactive runs (No leaves both file and document untouched), non-interactive runs report the error. Success clears the scene resource cache, refreshes canvas/navigator/Pixel, and reports `asset.saved`. `save_label` returns `action.save_asset` for asset documents.
- Tests: `asset_save_preserves_canonical_rows`, `asset_save_complements_inverted_source`, `asset_save_refuses_external_change`, `asset_force_overwrites_after_confirmation`, `asset_save_refuses_unrepresentable_polarity`, `asset_origin_blocks_resize_and_rotate`, `scratch_never_writes_project`, plus integration `saving_an_asset_writes_the_project_file` and `saving_an_externally_changed_asset_is_refused`.
- GUI (isolated config, `curing_lite` copy): opened `running_icon` directly into Pixel Studio; 旋转 90°/270°、画布尺寸、裁剪 were greyed while 180° remained enabled; painting a pixel showed `●` and Ctrl+S cleared it with status `已写回资源：assets/clinical_ui/running.png` (file md5 changed `c7026e…` → `4d1745…`). Replacing the PNG externally and saving again produced the dialog `资源已被外部修改，是否覆盖？`; choosing 否 left the file at `c7026e…` and the document dirty.
- Deviation: the plan's `asset_save_complements_inverted_source` expectation was refined: because V1 polarity detection is content-dependent, the encoder now verifies the round-trip and falls back to the complement; the new `asset_save_refuses_unrepresentable_polarity` covers the ambiguous case.

### Phase close-out — 2.0.5 version metadata

- `[workspace.package] version` → `2.0.5`; `Cargo.lock` refreshed with `cargo update -w` (six workspace packages, no third-party change).
- `CHANGELOG.md` gained `## 2.0.5 - 2026-10-24` (recent projects, asset open, atomic write-back, external-change guard, size lock).
- `.ai/CURRENT_STATE.md` product version → 2.0.5; phase line keeps the `Rust Rewrite G6` prefix.
- No tag, push, release, or draft release performed.

### Gate evidence (after T9–T11 and the 2.0.5 version bump)

- `cargo fmt --all -- --check` — pass.
- `cargo clippy --workspace --all-targets --locked -- -D warnings` — pass.
- `cargo test --workspace --locked` — 144 passed / 0 failed (mono-desktop 91).
- `python -m pytest tools/tests -q` — 21 passed, 1 skipped.
- `cargo deny check` — exit 0 (`advisories/bans/licenses/sources ok`).
- `fixtures/golden/` and `test_assets/` untouched; no commit/tag/push performed.

## Review Status

PASS — independent review 2026-10-24 (PASS WITH MINOR NOTES). Reviewer re-ran all gates: workspace tests 144/0 (mono-desktop 91), pytest 21 passed/1 skipped, fmt/clippy/deny exit 0, `fixtures/` and `test_assets/` clean. No Critical or Important findings.

Minor notes accepted as non-blocking follow-ups:

1. An Asset-origin Pixel document can survive a project switch and still point at the old project root; a guard/clear on project change is desirable.
2. The polarity complement fallback is not covered by a test that forces the fallback branch, and the stored `inverted` flag is not refreshed after a complement write.
3. `save_label` for asset documents has no dedicated test.
4. The force-overwrite path after confirmation surfaces the raw error message rather than a localized string.
5. `confirm_unsaved_pixel` does not consider `interactive`.
6. Read-side recent list is not capped (only the write path is); labels fall back to the full path when two projects share a folder name.
7. Recent dedupe compares strings rather than canonicalized paths.
8. A recent project whose file disappeared is reported through the external-modification path rather than a “missing project” message.
9. The Designer “edit in Pixel Studio” button is visible but disabled; hiding it would be clearer.
