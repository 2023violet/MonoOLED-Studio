# TASK-004 — 2.0.4 Trust Fixes (Phase 1)

Status: DONE
Review Status: PASS (independent re-review 2026-10-24: PASS WITH MINOR NOTES — four Important fixes verified, all gates pass; residual notes are non-blocking)

## Goal

Close the six P1 trust defects and the undo-dirty defect identified by the 2026-10-24 CXO report: shortcut settings/focus, first-run guards, per-document save points, contextual unsaved prompts, and output-profile persistence semantics. Ship as 2.0.4 without changing the public Automation JSON or the golden corpus.

## Background

The CXO deep-use report (F1–F17) found a strong engineering core with weak high-frequency trust: shortcut settings render blank, shortcuts die after menu/dialog focus changes, first launch offers destructive actions with no project, saving means different objects per workspace, undo does not clear the dirty marker, Pixel Studio has no project-asset path, and browsing output profiles writes the project manifest. The approved implementation plan is `C:\Users\16429\.qoder\plans\faint-pool-trout.md`; this TASK covers its Phase 1 tasks T1–T8 only.

## Current Problem

- `Preferences::get` treats the flat `shortcuts.*` namespace as JSON-pointer segments, so the Keyboard page reads empty strings; `valid` rejects empty bindings, so users cannot clear a shortcut.
- Global key handling lives in a single `FocusScope` that is focused once at startup; dialogs are sibling overlays and closing them leaves no focus owner. `MenuBar` must remain a direct child of `Window` (Slint 1.18.1 only lowers direct children).
- No project yields blank content and silently no-op project actions; batch/handoff/save buttons remain enabled.
- Top Save routes by workspace, but the unsaved prompt always says “Scene”.
- `PixelDocument.dirty` and `EditorSession.dirty` are set true by undo/redo even when content returns to the saved value.
- Pixel Studio always opens a 32×16 scratch document; no project asset round-trip.
- `bench_field` and `bench_profile` persist the profile to `project.oled.json` on every edit/selection.

## Evidence

- Baseline worktree `feat/2.0.4-trust` at `ef4a1aa`; `cargo test --workspace --locked` passed (all crates) before edits.
- `apps/mono-desktop/src/prefs.rs:154-163,178-185,97-99`
- `apps/mono-desktop/ui/main.slint:218-317`
- `apps/mono-desktop/src/main.rs:289-297,551-595`
- `apps/mono-desktop/src/guard.rs:36-50,94-135`
- `crates/mono-core/src/pixel.rs:24,123-131,468-489`
- `crates/mono-project/src/editor.rs:62,515-538,939-947`
- `apps/mono-desktop/src/pixel.rs:96-101,496-514`
- `apps/mono-desktop/src/pixel_ui.rs:782-828`
- `crates/mono-project/src/project.rs:508-545`

## Required Changes

1. **T1 — shortcut settings:** fix flat-key lookup, allow empty bindings, skip empty conflict targets, add reset-to-default, tests.
2. **T2 — focus/Esc:** add `overlay-open`, `focus-shortcuts()`, overlay `FocusScope` Esc handlers, Rust refocus, testable fixed-chord mapping.
3. **T3 — first-run guards:** add `has-project`/`can-*`/`save-label`; disable unavailable actions; add `WelcomeView`; open-project blocker hint.
4. **T4 — Pixel save point:** content fingerprint, `sync_dirty`/`mark_saved`/`mark_clean`, correct undo/redo dirty, converge direct writes.
5. **T5 — scene save point:** same for `EditorSession`; sync Automation `Service::refresh_saved_baseline`.
6. **T6 — contextual prompts:** designer/pixel/font/multi unsaved keys; FontLab save point; pack-state hint.
7. **T7 — output profile semantics:** apply in memory, explicit commit, active may reference builtins, load active on project open.
8. **T8 — output profile UI:** source/draft/default state, commit/default buttons, draft-switch confirmation.

## Architecture

- Keep `MenuBar` as a direct child of `Window`; never nest it in a `FocusScope`.
- `shortcuts.` is a flat namespace in preferences; all other dotted keys retain JSON-pointer lookup.
- Dirty state is content equality against a saved fingerprint; `dirty` remains a bool for UI/Automation compatibility but is only written through the new helpers.
- Output profiles have three explicit states: applied (memory), committed (project `profiles`), default (`active_profile`).
- UI models consume Rust-computed properties; no business rules in Slint.

## Out of Scope

Phase 2–4 tasks (recent projects, asset round-trip, command registry, Review workspace, Agent panel, theme palette, Font preview, localization, Help, new-project wizard, docs truth-up). No OS title-bar theming, no new platform dependencies, no Automation JSON shape changes, no golden fixture edits, no release/tag/push.

## Protected Existing Work

- `fixtures/golden/` and `test_assets/` are frozen; do not edit them.
- The worktree baseline is clean; do not clean/overwrite main worktree files.
- No pre-existing user work is present in this worktree; verify with `git status` before each task.
- Atomic writes, project/scene fingerprints, and external-modification checks must remain intact.

## Constraints

- CI gates: `cargo fmt --all -- --check`; `cargo clippy --workspace --all-targets --locked -- -D warnings`; `cargo test --workspace --locked`; `python -m pytest tools/tests -q`; `cargo deny check`.
- GUI checks must use isolated `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` and copies of `test_assets`.
- Prefer existing helpers; do not duplicate persistence or render logic.
- Keep changes scoped to the allowed files; if a shared file must change, document why in Result.
- Stop at `Status: VERIFY`; independent review may promote to DONE.

## Allowed Files / Expected Area

- `apps/mono-desktop/src/prefs.rs`
- `apps/mono-desktop/src/prefs_ui.rs`
- `apps/mono-desktop/ui/preferences.slint`
- `apps/mono-desktop/ui/main.slint`
- `apps/mono-desktop/ui/welcome.slint` (new)
- `apps/mono-desktop/src/main.rs`
- `apps/mono-desktop/src/app.rs`
- `apps/mono-desktop/src/guard.rs`
- `apps/mono-desktop/src/pixel.rs`
- `apps/mono-desktop/src/pixel_ui.rs`
- `apps/mono-desktop/src/fontlab.rs`
- `apps/mono-desktop/src/workbench.rs`
- `apps/mono-desktop/ui/pixel.slint`
- `apps/mono-desktop/ui/fontlab.slint`
- `apps/mono-desktop/i18n/strings.json`
- `crates/mono-core/src/pixel.rs`
- `crates/mono-project/src/editor.rs`
- `crates/mono-project/src/project.rs`
- `crates/mono-automation/src/dispatch.rs`
- `crates/mono-automation/src/service.rs`
- `.ai/tasks/TASK-004.md`
- `.ai/CURRENT_STATE.md`

## Acceptance Criteria

1. Keyboard page shows all eight default chords; clearing a binding persists and does not conflict; reset restores the default.
2. `Ctrl+K`/`Ctrl+Shift+P`/`Ctrl+S` work after menu, dialog, and segmented-control interaction; Esc closes every overlay; `MenuBar` still renders.
3. No project shows `WelcomeView`; batch/handoff/export/agent/save unavailable with an explanatory status; save label matches Scene/Pixel/Font.
4. Undo back to the saved pixel/scene content clears dirty; redo makes it dirty again; saving clears it; direct `dirty` writes are converged.
5. Unsaved prompts name the actual dirty object(s); Font Lab pack state is visible.
6. Selecting/browsing output profiles does not modify `project.oled.json`; explicit commit writes once; active builtin loads on project open.
7. T1–T8 focused tests, `cargo test --workspace --locked`, and `cargo clippy` pass.
8. No golden/test-asset edits; no commit/push/tag/release performed by this TASK.

## Verification Plan

- Focused: `cargo test -p mono-desktop prefs`, `cargo test -p mono-desktop guard`, `cargo test -p mono-desktop workbench`, `cargo test -p mono-core pixel`, `cargo test -p mono-project`, `cargo test -p mono-automation`.
- Full: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --locked -- -D warnings`, `cargo test --workspace --locked`, `python -m pytest tools/tests -q`.
- GUI isolation: temp `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME`, `test_assets` copy; screenshots via `--action preferences` and `--screenshot`; `python tools/CHECK_SMOKE_SCREENSHOT.py`.
- Manual matrix: welcome/no-project, shortcut focus, per-object save/undo, profile browse/commit, Esc overlays, 1100×700 and 1440×900.

## Deliverables

Code, tests, GUI evidence, and a Result section listing actual commands/results, skipped checks, and any scope deviations. Do not mark PASS/DONE; independent review owns that.

## Result

Baseline `cargo test --workspace --locked` passed in `feat/2.0.4-trust` before edits.

### T1 — shortcut settings (implemented)

- `Preferences::get` strips a single `shortcuts.` prefix and reads the remaining string as one flat key; all other dotted keys keep JSON-pointer lookup.
- `valid` accepts empty `shortcuts.*` values (clear binding) and still rejects `none`/`null`.
- `command_for` ignores empty bindings; `shortcut_conflict` only compares non-empty wanted/bound chords.
- Added `default_shortcut`, `reset_shortcut`, `pref_button("shortcut-reset:<row-key>")`, and a per-row Reset button in Preferences → Keyboard.
- Tests added: `shortcuts_read_as_flat_keys`, `dotted_paths_still_resolve`, `set_then_get_shortcut_round_trips`, `empty_shortcut_clears_binding_and_resets`, `unknown_shortcut_reset_is_rejected`, `empty_binding_does_not_resolve`, `cleared_binding_does_not_conflict`, `reset_action_accepts_pref_row_keys`.
- GUI (isolated APPDATA/LOCALAPPDATA/XDG_CONFIG_HOME, temp `mono-t2` config): Keyboard page shows defaults; cleared row stays empty after restart; Reset restores the default and reports 已保存.

### T2 — focus and Esc (implemented)

- `MainWindow.overlay-open`, `focus-shortcuts()`, overlay guard in `shortcuts.key-pressed`.
- Rust `fallback_action` (fixed-chord map) + `focus_if_idle` called after every `AppModel.action`, picker choice, prompt accept/cancel, and Preferences close. `PixelModel.refocus` covers Slint-only pixel dialog closes.
- Slint global `changed` handlers are not supported for dotted property paths in 1.18.1 (parse error), so overlays ask for refocus explicitly instead.
- Esc handled by a `FocusScope` in Preferences, Prompt, Picker, About, and Pixel dialogs; About/Pixel/Preferences scopes take focus in `init`.
- Tests: `fallback_action_maps_fixed_chords`, `fallback_action_rejects_unknown_or_configured_chords`.
- GUI matrix (isolated config + copy of `curing_lite`): `Ctrl+K` opens; Esc closes; `Ctrl+K` works again. `Ctrl+,` → Esc → `Ctrl+K` works. Help → About (menu) → Esc → `Ctrl+K` works. Pixel Studio → 画布尺寸 → Esc → `Ctrl+K` works. Segment switch (Pixel→Design) → `Ctrl+S` saved `scenes/123.json` (status confirmed). `MenuBar` still renders as a direct Window child.

### T3 — first-run guards, welcome page, dynamic save label (implemented)

- `AppModel` gained `has-project`, `can-save`, `can-export`, `can-handoff`, `can-agent`, `save-label`; `refresh_app` computes them every refresh.
- `App::can_save` is workspace-aware (Scene/Pixel/Font) rather than the plan's plain union, because the top Save button acts on the current workspace; documented as the only deviation.
- `App::feature_available` + `require_document` guard `handle_action` for save/export/batch/handoff/assign-bitmap/add-placeholder/duplicate/delete/agent; the status bar explains the no-op instead of silently returning.
- New `ui/welcome.slint` empty state (open / new / single-scene hints) replaces the Designer canvas when `workspace == 0 && !has-project`; wired to the same actions.
- Command bar Batch/Handoff/Save and File/Edit/Tools menu items bind their enabled state; Save and the File menu show the workspace-specific label.
- `refresh_validation` now stores findings before UI sync, so headless `App` instances also have findings; `open_project` reports “scene has N blockers, switch screens” when the active scene blocks and the project has multiple screens.
- Tests: `save_label_matches_workspace`, `save_without_document_reports_status`, `export_without_project_errors`, `agent_start_without_project_errors`, `open_project_with_blockers_hints_at_scene_list`.
- GUI (isolated config, no project): WelcomeView with New/Open; Save disabled and labelled 保存场景; palette-invoked Batch Validate left a status “请先打开项目或场景”. With `curing_lite` open: buttons enabled, label 保存场景; switching to Pixel Studio changed it to 保存像素.

### T4 — PixelDocument save point (implemented)

- `PixelDocument` stores `saved_fingerprint` (width + height + pixels, `DefaultHasher`); `content_fingerprint`, `sync_dirty`, `mark_saved`, `mark_clean` added. `from_pixels` sets the baseline.
- Undo, redo, and gesture end re-derive `dirty` from that baseline, so undoing back to the saved content clears the marker.
- Semantics compromise for Automation 1.3.0: a direct edit still sets `dirty = true` (the frozen golden replay expects that for same-value paints/erases), while undo/redo recompute. The plan's `same_value_edit_stays_clean` / `resize_back_to_saved_is_clean` tests were therefore dropped; `undo_to_saved_state_is_clean`, `redo_after_save_is_dirty`, `mark_saved_records_the_current_content`, `from_pixels_starts_clean` cover the acceptance criterion.
- Direct `dirty = false` writes replaced by `mark_saved()` / `mark_clean()` in `apps/mono-desktop/src/pixel.rs`, `guard.rs`, `fontlab.rs`, and `crates/mono-automation/src/dispatch.rs`; redundant resets after `from_pixels` were removed.
- GUI: drawing a pixel showed the `•` marker; `Ctrl+Z` removed both the command-bar marker and the window-title marker; content returned to blank.
- `cargo test -p mono-core`, `-p mono-automation` (incl. `v1_automation_sessions_replay_identically`), `-p mono-desktop`, and workspace clippy all pass; `fixtures/golden/` untouched.

### T5 — EditorSession save point (implemented)

- `EditorSession` stores `saved_fingerprint` of the persisted scene JSON (all keys except `_`-prefixed UI/editor keys, `DefaultHasher`); `scene_fingerprint`, `sync_dirty`, `mark_saved`, `mark_clean` added.
- `new`/`reset_scene` set the baseline; `save` calls `mark_saved()`; undo/redo (`apply`), coalesced geometry, `batch_edit`, `record_external_batch`, `record_external_scene`, and `set_canvas_size` now call `sync_dirty()` instead of forcing `dirty = true`.
- Dependent write sites converged: `Service::refresh_saved_baseline` → `session.mark_saved()`, schema-apply dispatch → `session.sync_dirty()`, delete-screen in `guard.rs` → `session.mark_clean()`.
- Deviation: `extras.rs` autosave recovery intentionally keeps `session.dirty = true` (with a comment). Recovery re-reads the persisted scene, so the file matches content and the standard helpers would report clean; the flag must stay true so the user is told there is an unsaved recovery buffer.
- Tests added in `editor.rs`: `undo_to_saved_scene_is_clean`, `redo_after_save_is_dirty`, `external_record_marks_dirty`, `save_failure_keeps_dirty`, `successful_save_clears_dirty`, `reset_scene_resets_fingerprint`.
- `cargo test -p mono-project` (11), `cargo test -p mono-automation` (incl. golden replay), `cargo test -p mono-desktop --locked` (57) pass.
- GUI (isolated config, `curing_lite` copy): Edit menu → 添加占位元素 → command bar and title show `•`, findings 4/1 blocker; `Ctrl+Z` → both markers clear, findings return to 3/0. Then `Ctrl+S` (status 已保存: `scenes/123.json`), add placeholder again (`•`), `Ctrl+Z` → markers clear again, confirming undo back to the saved scene is clean.

### T6 — contextual unsaved prompts and Font Lab state (implemented)

- `App::unsaved_mask()` (scene/pixel/font bits) now backs both `has_unsaved()` and the new `unsaved_context()`, which returns `dialog.unsaved_designer`, `dialog.unsaved_pixel`, `dialog.unsaved_font`, or `dialog.unsaved_multi`. `confirm_transition` uses it; `confirm_scene_transition` is fixed to the designer key; `confirm_unsaved_pixel` uses `dialog.unsaved_pixel` instead of the generic `dialog.save_changes`.
- New zh/en strings: `dialog.unsaved_designer|pixel|font|multi`, `font.pack_state.clean|glyph|pack`, `font.save_scope_hint`.
- `FontModel` gained `pack-state` and `pack-tone`; `refresh_font` derives them from glyph dirtiness, metric dirtiness, and `FontLab::dirty()`; the header shows a pill next to the cell size and a caption explains “save current glyph” vs “generate whole pack”.
- Deviation found during GUI verification: editing a glyph goes through the shared Pixel canvas (`refresh_pixel`), which refreshed the AppModel but not `FontModel`, so the pill stayed “已保存” while the document was dirty. `refresh_pixel` now also calls `refresh_font()` when the workspace is Font Lab (document-change paths only, not hover).
- Tests: `unsaved_context_designer`, `unsaved_context_pixel`, `unsaved_context_font`, `unsaved_context_multi`, `pixel_prompt_key_is_pixel_specific` (guard) and `glyph_undo_to_saved_state_is_clean` (fontlab).
- GUI (isolated config, `curing_lite` copy): created a pack, generated 37 glyphs, pill `已保存` + hint visible; painted a cell → pill `当前字形未保存` and `●`; 保存当前字形 → `已保存`. Prompts: font-only → `当前字库存在未保存修改…`; scene-only → `当前场景存在未保存修改…`; pixel-only → `像素文档存在未保存修改…`; scene+pixel → `场景、像素文档或字库中存在多处未保存修改…`.
- `cargo test -p mono-desktop --locked` → 63 passed; `cargo fmt --check` and `cargo clippy -p mono-desktop --all-targets -- -D warnings` pass.

### T7 — output profile apply/commit/default (implemented)

- `Workbench` gained `profile_dirty`. Selecting a profile or editing a field now only updates memory; `bench_field` calls `bench_apply()` (marks the draft, regenerates an existing preview) and `bench_profile` clears the draft instead of persisting.
- Added `bench_commit_profile(activate)` (one explicit `upsert_output_profile` write) and `bench_set_default()` (`set_active_output_profile`). Removed `persist_profile`; `Prompt::ProfileName` now routes through `bench_commit_profile(true)`.
- `ProjectWorkspace::set_active_output_profile` and its manifest validation accept builtin ids, so “set as default” does not copy the builtin into `profiles`; unknown ids still fail.
- `App::open_project` calls `bench_load_active()` after scanning files, so a reopened project restores its active profile.
- New strings: `bench.profile_default_set`; tests `builtin_selection_does_not_write_the_manifest`, `field_edits_stay_in_memory_until_commit`, `open_project_loads_the_active_profile`, `default_may_reference_a_builtin_without_copying_it`, `legacy_manifest_without_workbench_opens_with_defaults`, `switching_profiles_discards_the_draft_without_writing`, and `active_output_profile_may_be_a_builtin` (mono-project).
- Deviation: manifest validation had to learn builtin ids (not just `set_active_output_profile`); without it every save after choosing a builtin default failed with “active output profile does not exist”. Backward compatible: existing manifests keep validating.
- GUI (isolated config, fresh `curing_lite` copy): opening the project → Output tab shows the built-in profile with the `项目` pill and the `项目默认` caption. Editing 每行字节 left the manifest byte-identical (md5 `c5130a0e…`); 保存到项目 wrote once (`bytes_per_line: 8`, md5 changed) and the pill switched to `项目`; switching to `Raw Hex` did not touch the manifest (`内置`); 设为项目默认 set `active_profile: raw_hex` while `profiles` kept only `ssd1306_vlsb_c`; relaunching restored `Raw Hex` as the selected, default profile.

### T8 — output profile state UI (implemented)

- `OutputModel` gained `profile-dirty`, `profile-source` (0 builtin / 1 project), `profile-is-default`, `profile-state-text`, `profile-state-tone`; `refresh_bench` computes them from the saved profile list and active id.
- The profile row shows a StatusPill (`内置` neutral / `项目` success / `未保存` warning), a `项目默认` caption, and “保存到项目” / “设为项目默认” buttons bound to the draft/default state. `bench_action` handles `commit-profile` and `set-default-profile`.
- `bench_profile` asks for confirmation before discarding a draft in interactive runs (new key `bench.draft_switch_confirm`); non-interactive runs switch directly (tests, screenshots, benches).
- New strings: `bench.profile_state.builtin|project|draft`, `bench.profile_is_default`, `bench.commit_profile`, `bench.set_default_profile`, `bench.draft_switch_confirm`.
- GUI confirmed the three pill states and that the default marker follows `active_profile` across restart (see T7 evidence).

### Review rework (first independent review: REWORK REQUIRED)

Four Important findings fixed; no Critical findings were reported. Minor notes were left for later unless noted.

1. **Pixel dialog OK did not restore shortcut focus.** `pixel_dialog_accepted` destroyed the dialog's `FocusScope` and the `on_dialog_accepted` wiring did not call `focus_if_idle` (unlike Esc/cancel). The wiring now calls `focus_if_idle` after accepting, so `Ctrl+K`/`Ctrl+S` work again once the dialog closes.
   - GUI (rebuilt binary, isolated config, project copy): Pixel Studio → 画布尺寸… → 调整尺寸 (OK) → `Ctrl+K` opened 命令面板. The title showed `•` from the resize. The earlier attempt failed because the running exe predated the fix; after `cargo build -p mono-desktop` the check passed.
2. **Opening a scene file left the workbench on the closed project's profile.** `open_scene_file` now calls `bench_load_active()` after clearing the project, so the workbench falls back to the builtin default (plan T7 step 4).
   - Test: `open_scene_file_resets_the_workbench_to_the_builtin`.
3. **Re-selecting the current profile discarded a dirty draft.** Slint's ComboBox fires `selected` even for the same index; `bench_profile` now returns early when the id is unchanged, preserving the draft (no confirmation needed because nothing is switched).
   - Test: `reselecting_the_current_profile_keeps_the_draft`.
4. **Failed “Save As” left the workbench on the new id and lost the previous profile.** `Prompt::ProfileName` now snapshots the id/profile/dirty state, commits, and restores the snapshot if the commit fails.
   - Test: `failed_save_as_keeps_the_previous_profile`.
5. Minor (fixed opportunistically): `legacy_manifest_without_workbench_opens_with_defaults` now actually removes `output_workbench` and reopens the project instead of asserting against the synthesized list.

Remaining Minor findings (recovery flag durability, same-value direct edits, builtin-as-“项目” label in legacy manifests, unused `profile-source`, write-count test strength, no screenshot artifact, welcome hint wording, draft-dirty on unchanged field) are recorded but not fixed in this TASK; they do not affect the acceptance criteria.

Re-ran after the fixes: `cargo fmt --all -- --check` pass; `cargo clippy --workspace --all-targets --locked -- -D warnings` pass; `cargo test --workspace --locked` 125 passed / 0 failed (mono-desktop 72); `python -m pytest tools/tests -q` 21 passed, 1 skipped; `cargo deny check` exit 0.

Independent re-review (2026-10-24): all four findings FIXED; no Critical/Important regressions. Verdict `PASS WITH MINOR NOTES — ready for DONE`. Re-verified gates: fmt, clippy, 125 tests, pytest 21/1, deny — all pass; metadata consistent; no fixture edits, commit, tag, or push. Residual non-blocking notes recorded for later phases:

- `open_scene_file` resets the workbench only after `bind_scene` succeeds; a malformed scene leaves the old profile in memory while the project is already cleared (edge case).
- `failed_save_as_keeps_the_previous_profile` starts clean and fails before mutation; it does not cover a save-time failure with a previously dirty draft.
- Pre-existing minors: same-value direct pixel edits still dirty; `profile-source` unused; legacy manifests label the synthesized builtin as 项目; commit write count not asserted; unchanged field edits mark the draft.
- Some palette-only actions (`thumbnail-wall`, `asset-health`, `save-template`, `insert-template`, `convert-asset`) remain selectable without a project and silently no-op; T3's enumerated guards (save/batch/handoff/export/agent) are covered.

### Phase close-out — 2.0.4 version metadata

- `[workspace.package] version` → `2.0.4`; `Cargo.lock` refreshed with `cargo update -w` (all six workspace packages at 2.0.4, no third-party change).
- `CHANGELOG.md` gained a `## 2.0.4 - 2026-10-24` section (fixed/added: shortcuts, focus/Esc, welcome guards, save points, contextual prompts, output-profile three-state).
- `.ai/CURRENT_STATE.md` product version → 2.0.4; phase line keeps the `Rust Rewrite G6 complete;` prefix required by the governance test.
- No tag, push, release, or draft release performed.

### Gate evidence (after T1–T8 and the 2.0.4 version bump)

- `cargo fmt --all -- --check` — pass.
- `cargo clippy --workspace --all-targets --locked -- -D warnings` — pass.
- `cargo test --workspace --locked` — pass (125 tests; mono-desktop 72, mono-project 12, mono-automation incl. golden replay, mono-core, mono-font, mono-cli).
- `python -m pytest tools/tests -q` — 21 passed, 1 skipped.
- `cargo deny check` — exit 0 (`advisories/bans/licenses/sources ok`; existing `license-exception-not-encountered` warning for `i-slint-backend-testing`).
- Governance note: `test_rewrite_governance.py` requires `.ai/CURRENT_STATE.md` to start the phase line with `Rust Rewrite G<digit>`; the 2.0.4 line was reworded to keep that prefix (first run failed, second passed).
- `fixtures/golden/` and `test_assets/` untouched; no commit/tag/push performed.

## Review Status

PENDING
