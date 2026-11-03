# TASK-014 — Integrate the Unshipped 2026-10-30 Line onto 2.3.0

Status: DONE
Review Status: PASS (confirmation review of the third rework, 2026-11-02)

## Goal

Bring the unshipped line (TASK-010 to TASK-013, formerly numbered TASK-004 to TASK-007 on that line) onto `origin/main` at 2.3.0, so that one history carries both. Where both lines fixed the same defect, keep one implementation. Keep every gate green. Do not ship, tag or push.

## Background

Both lines branched at `v2.0.3` and both started from the 2026-10-24 experience report.

- `origin/main` released 2.0.4, 2.0.5, 2.1.0, 2.2.0, 2.2.1 and 2.3.0, with its own TASK-004 to TASK-009.
- The local line made eight commits (truthful controls, the export gate, Designer performance, project-root containment). Its "2.1.0" version bump was never tagged or pushed.

The user reviewed an inventory of the two lines on 2026-11-02 and approved this plan ("按这个方案做"):

- `origin/main` is the base;
- the local line's 2.1.0 release commit is not shipped, and its notes become `Unreleased`;
- duplicate fixes are reconciled one by one;
- the local tasks are renumbered to TASK-010 to TASK-013;
- TASK-006/TASK-007's missing independent review stays a separate item;
- the version, push and tag are the user's.

## Current Problem

A trial merge (`git merge-tree`) left 26 files in conflict, the largest being:

- `app.rs`: about 1960 lines;
- `strings.json`: 34 hunks;
- `main.rs`, `main.slint`, `i18n.rs` and `prefs_ui.rs`.

The four `.ai/tasks/TASK-004..007.md` files were added on both sides with different content. The two version numbers collide (two different "2.1.0" releases).

Some semantic conflicts merged without any text conflict:

- the release gate and member containment met paths 2.3.0 added (review pack, gallery, review panel, CLI `--json`);
- "Pixel Studio is standalone" met 2.3.0's asset-origin documents;
- the removed Inspector Play button met 2.3.0's real playback;
- synchronous validation on open met the worker-thread validation.

## Evidence

- Merge on branch `integrate/2.4.0` from `origin/main` (merge commit, no rebase), local `main` merged in.
- Before the fixes below, `cargo test -p mono-desktop` had 7 failures, all caught by the unshipped line's scans:
  - dead model bindings;
  - unread preference rows;
  - orphaned and missing translation keys;
  - a scan anchor 2.3.0 had renamed;
  - 2.3.0's open-project blocker test assuming synchronous validation.
- `python -m pytest tools/tests`: 2.3.0's version test required a literal version default in `main.slint`, which the unshipped line had removed on purpose.
- `cargo deny check`: RUSTSEC-2026-0433 against `pulldown-cmark` 0.13.5. It is published since and also fails on both parent lines.

## Required Changes (as done)

1. `.ai`:
   - `origin/main`'s TASK-004..009 kept as they are.
   - Local tasks saved as TASK-010..013, each with a renumbering note; their bodies are unchanged.
   - References renamed in `.ai/DECISIONS.md`, `docs/rewrite/G4_EVIDENCE.md` and `tools/CHECK_GUI_TRUST.py`.
2. Version stays 2.3.0. `CHANGELOG.md` gets one `Unreleased` section; 2.3.0 and older entries are untouched.
3. Dirty state:
   - `EditorSession` keeps the local saved-snapshot design (`is_dirty()`, `mark_clean()`, `mark_dirty()` for a restored autosave).
   - 2.3.0's `saved_fingerprint` / `sync_dirty` / `mark_saved` on the session are removed, and its callers and tests use the snapshot API.
   - `PixelDocument` keeps 2.3.0's own save point.
4. Unsaved prompt keeps 2.3.0's per-document keys (`unsaved_context`). The local `DirtyDoc` / `unsaved_message` duplicate and its keys are removed.
5. Shortcuts: 2.3.0's command registry, plus the local nested-key fallback in `Preferences::get`. The local modal guard in `run_shortcut` now also covers 2.3.0's new-project, note and gallery overlays.
6. Dialogs:
   - The local focus model: overlays inside `shortcuts := FocusScope`, `Scrim` owns Escape, and `overlay-open` restores focus. It covers 2.3.0's overlays too.
   - The Prompt, Picker, About, Preferences and Pixel dialogs use the local `Scrim` versions; the Picker uses 2.3.0's `PickerItem` rows.
   - 2.3.0's own `refocus` wiring remains for its new dialogs, and its Pixel `refocus` callback is removed.
   - The local `@markdown` Tooltip children are removed, so 2.3.0's tooltip popups are the only ones.
7. Views:
   - 2.3.0's welcome page replaces the local `EmptyState`, together with the `has-document` / `recent-project` properties and the `open-recent` action.
   - 2.3.0's Review workspace replaces "review mode = Designer".
   - The Inspector has six tabs: properties, state, canvas, schema, rules and notes; notes moved from index 3 to 5.
   - 2.3.0's Play / Step / Reset are kept.
8. Validation:
   - The local worker-thread validation is kept.
   - 2.3.0's open-project blocker hint is deferred: `blocker_hint` is set on open and emitted by `apply_findings` once the worker's result lands.
   - The test calls `flush_validation()` before it reads the findings.
9. Export jobs:
   - The local blocked-export dialog is combined with 2.3.0's contract adoption. A blocked job clears `pending_contract`, so a stale `ui_contract.json` is never adopted.
   - The review-pack job sets `blocked: None`.
10. Preferences: dropped `appearance.reduced_motion`, `appearance.color_theme`, `performance.drag_preview` / `validation_mode` / `asset_cache_mb` / `overlay`, because nothing reads them; kept 2.3.0's `startup.recent_projects`.
11. Dead bindings removed: `DesignerModel.selection-count` and `OutputModel.profile-source` (2.3.0 set both and no view read them).
12. `strings.json`:
    - Three-way merge by key: local deletions apply only where 2.3.0 had not changed the key, and keys still referenced by code are restored.
    - Unused keys are pruned, and `pref.shortcut.view.gallery` is added.
    - `finding.` and `notes.kind.` are added to the orphan scan's constructed prefixes, because `finding_label` and the annotation kind build them.
    - Both tables hold 699 keys in sorted order.
13. Pixel Studio shows "Standalone PNG · not part of the project" only when `!PixelModel.asset-locked`.
14. `tools/tests/test_version_consistency.py`: the literal-default check is replaced by one that asserts no literal default and `set_version(env!("CARGO_PKG_VERSION"))`.
15. `pulldown-cmark` 0.13.6 (`cargo update -p pulldown-cmark --precise 0.13.6`).
16. Two CLI tests for the new seams:
    - a gate-blocked `export --json` returns one object, exit 2, `E-EXPORT-BLOCKED`, and writes no artefact;
    - `validate --json` reports `ASSET_PATH_ESCAPE` as blocking (exit 1).
    - `README.md` now says a gate refusal exits 2.

## Out of Scope

- A release, version bump, tag, push or PR.
- TASK-006/TASK-007's independent review.
- Re-measuring the TASK-012/TASK-013 performance figures on the integrated tree.
- Gating the Output Workbench, `export.bitmap_data` or the review pack.
- Any change to `fixtures/golden/`.

## Protected Existing Work

- Every 2.3.0 release entry, tag and evidence file.
- The renumbered task bodies.
- `fixtures/golden/` and `test_assets/`.

## Constraints

- `AGENTS.md` gates on three platforms.
- No push, tag, rebase, stash or clean without explicit instruction.
- The implementer stops at VERIFY.

## Allowed Files / Expected Area

The whole merge diff. Beyond conflict resolution, the touched files were:

- `apps/mono-cli/tests/cli.rs`;
- `tools/tests/test_version_consistency.py`;
- `README.md`;
- `Cargo.lock` (pulldown-cmark);
- `.ai/DECISIONS.md`, `docs/rewrite/G4_EVIDENCE.md` and `tools/CHECK_GUI_TRUST.py` (task-number renames only).

## Acceptance Criteria

1. No conflict markers; one history containing both lines.
2. fmt, clippy `-D warnings`, `cargo test --workspace --locked`, pytest on `tools/tests` and `cargo deny check` all pass.
3. `CHECK_GUI_TRUST.py` passes against a release build of the integrated tree.
4. Every duplicate fix has exactly one implementation, named in `CHANGELOG.md` under Integration.
5. Golden corpus unchanged.

## Verification Plan

Run the five CI gates on the integrated tree, build release, run `tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` pointed at temporary directories, then check `git diff origin/main -- fixtures/golden` is empty.

## Deliverables

- The merge on `integrate/2.4.0` (not pushed).
- `CHANGELOG.md` `Unreleased`.
- This record and `.ai/CURRENT_STATE.md`.

## Result

Results, from the commands that were actually run on Windows 10:

- `cargo fmt --all -- --check`: clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: clean.
- `cargo test --workspace --locked --no-fail-fast` on the final tree: 28 groups, 300 passed, 0 failed.
- `python -m pytest tools/tests -q`: 36 passed, 1 skipped.
- `cargo deny check`: advisories, bans, licenses and sources ok.
- `tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` against a release build of the final tree, with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in a temporary directory: 17 of 17 PASS. Its Inspector check covers tabs 0 to 4. A separate screenshot at the minimum size (1166×800) on a fixture copy showed all six tab labels readable and the notes tab (5) opening.
- `git diff origin/main -- fixtures/golden test_assets`: empty.

Open product question for the user: the 2.3.0 review pack writes every frame's C header and hex into an HTML page whatever its blocking findings. It is not inside the release gate. ADR-006 names the Output Workbench and `export.bitmap_data` as deliberate exceptions, but the review pack did not exist when that decision was made. Member containment does apply to it, because it renders through the checked renderer.

Not verified:

- macOS and Linux;
- the performance budgets on the integrated tree;
- the gallery and review panel with an escaping member (their render goes through the same renderer, but no test exercises them).

## Review Status

Independent review of `a35d425` against `origin/main` (2026-11-02, fresh-context agent, read-only): **REWORK REQUIRED**. No Critical or High findings.

What passed:
- Every duplicate fix has one implementation.
- No export path bypasses the gate without documentation.
- No member read skips containment.
- The reviewer's own run of the five gates matched the Result above: 300 passed, pytest 36 passed and 1 skipped, deny ok. The release build and GUI trust were not re-run.

Findings:
- **F1 (Medium)**: the desktop Rename (from the unshipped line) leaves 2.3.0's annotations under the old screen id. The Notes tab and the gallery then show none for the renamed screen. This was confirmed with a scratch test (`annotations_for("renamed") == 0`). The API's `project.rename_screen` already behaved this way in 2.3.0.
- **F2 (Low)**: `CHANGELOG.md` gives the wrong report path for `mono c-header`; it actually writes `<output>.validation.md`.
- **F3 (Low)**: "every dialog closes on a backdrop click" is false for 2.3.0's `NewProjectDialog`, `NoteDialog` and `GalleryOverlay`, which do not bind `dismissed`. The scrim test does not scan their files.
- **F4 (Low)**: `export.c_header` lists up to 8 blockers plus "… and N more", not every blocker.
- **F5 (Low)**: `docs/AUTOMATION_API_V1.md` still says `export.c_header` writes a report, and refers to "2.1.0". `docs/rewrite/G4_EVIDENCE.md` has the same stale "2.1.0".
- **F6 (Low)**: `docs/rewrite/G4_EVIDENCE.md:68/74` still point to the "TASK-006" section.
- **F7 (Low)**: RUSTSEC-2026-0414 was already fixed in 2.3.0; only 0433 is new.
- **F8 (Low)**: three gaps between the notes or docs and the code:
  - the title `•` no longer follows Pixel or Font documents, and this is not in the notes;
  - the user guides still call Pixel standalone-only and list batch validation as gated;
  - `docs/AI_HANDOFF.md:129` says a blocked export writes nothing, and it omits the review pack.
- **F9 (Low)**: the nested-shortcut fallback only affects `Preferences::get`. Dispatch reads the flat object, so the CHANGELOG sentence overstates it.

Rework scope:
1. F1: move annotations with a renamed screen, or document the limitation. This is the user's choice.
2. F3: bind `dismissed` in the three dialogs and extend the scrim test, or narrow the claim.
3. Text corrections for F2 and F4 to F9.
4. Re-run the five gates, then a delta review.

Suspicions recorded, not caused by the merge (present on both parents):
- `start_export` sets `pending_contract` before the job start can fail.
- The Navigator's `delete-elements` action has no handler.
- `ReviewModel.percent` / `hash-match` and `AgentModel.endpoint` are set but never read. The truthful-controls scan does not cover the 2.3.0 globals; TASK-015 item 4 targets this.

### Rework (2026-11-02)

The user approved the recommended scope ("按建议一起返工"): move notes with a rename, bind backdrop dismissal, fix the text. TASK-015 and TASK-016 (on `claude/heuristic-goldberg-a5634a`) and the TASK-006/007/010/011 verdicts (on `claude/blissful-pasteur-3bfb53`) were merged into `integrate/2.4.0` first. Changes by finding:

- **F1**:
  - New `ReviewStore::rename_screen(from, to)` (`crates/mono-project/src/review.rs`) re-keys a screen's annotations and saves through the existing fingerprint guard.
  - The desktop `rename_active_screen` calls it on the in-memory store, so the store's fingerprint stays current.
  - The API's `project.rename_screen` calls it on `ReviewStore::for_root` after the rename. If that step fails, the error says the rename was already applied, and the response shape is unchanged; `docs/AUTOMATION_API_V1.md` documents this.
  - Tests:
    - `review::tests::rename_screen_moves_only_that_screens_notes`
    - `app::tests::renaming_a_screen_moves_its_notes`
    - `session_reset::renaming_a_screen_moves_its_annotations`
  - Failure evidence: on a pre-fix worktree the API test failed (`left: 0, right: 1`). The desktop case had been reproduced by the reviewer.
  - Known edge: while the desktop Agent Bridge renames a screen, the desktop's own in-memory store sees an external change, and its next note save is refused with `E-REVIEW-EXTERNAL` ("reopen the project"). That refusal is safe: no note is lost.
- **F3**:
  - `NewProjectDialog`, `NoteDialog` and `GalleryOverlay` bind `dismissed` to their existing cancel or close.
  - The gallery panel swallows clicks on its empty space, the same way `Dialog` does.
  - `scrim_owns_escape_and_every_dialog_binds_dismissal` now scans `gallery.slint`, `notes.slint` and `new_project.slint`.
- **F2, F4, F7 and F9**: corrected in `CHANGELOG.md`:
  - the report paths per producer;
  - "up to eight blockers";
  - only RUSTSEC-2026-0433 is new;
  - the nested shortcut key is readable but does not bind.
- **F5**: `docs/AUTOMATION_API_V1.md`: `export.c_header` writes no report; "2.1.0" becomes 2.3.0.
- **F6**: `docs/rewrite/G4_EVIDENCE.md`: TASK-006 becomes TASK-012, and the stale 2.1.0 references are corrected.
- **F8**:
  - CHANGELOG Integration now names the title-dot change and the rename fix.
  - Both user guides now describe project-asset PNGs in Pixel Studio and say batch validation is not a gated export.
  - `docs/AI_HANDOFF.md` §5.5 says a blocked export still writes its report and lists the review pack outside the gate.
- TASK-011's rework (a refused rename keeps the page open) is in the same change; see that file.

Gates after the rework (Windows):
- fmt clean;
- clippy `-D warnings` clean;
- `cargo test --workspace --locked --no-fail-fast`: 28 groups, 308 passed, 0 failed (before the duplicate-id case was added to one test, which passes on its own);
- pytest 36 passed, 1 skipped;
- deny ok.

GUI trust on a fresh release build of the reworked tree, with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in a temporary directory: 17 of 17 PASS. Not verified: a real backdrop click on the three dialogs, because the scripted hooks have no pointer action outside the canvas; the source test pins the binding.

A shared-target worktree build of the pre-fix tree overwrote the workspace crates' artefacts in `target/`, and the next test build linked against them (a spurious "no method `rename_screen`"). `cargo clean -p` on the six workspace crates fixed it. Failure-evidence worktrees must use their own `CARGO_TARGET_DIR`.

### Delta review of the rework (2026-11-02)

The verdict on TASK-014's rework at `f5e2653` was **REWORK REQUIRED**. The reviewer re-ran the gates: 308 passed, a release build and GUI trust exit 0. Separate verdicts went to TASK-015 and TASK-016 (both PASS).

Confirmed resolved: F1 on the desktop and on the API success path, F2–F5, F7–F9, F3 including the gallery panel's click swallow, and the TASK-011 rework.

New findings:
- **A1 (Medium)**: when the annotation move fails in the API's `project.rename_screen`, it returned before rebinding the session. The next save recreated the old scene file. Reproduced with a review file at schema version 99.
- **A2 (Low)**: a rename through the Agent Bridge did not reload the desktop's in-memory review store. The renamed page looked as if it had no notes, and later desktop note saves were refused as an external change.
- **A3 (Low)**: `G4_EVIDENCE.md:68` still pointed to a TASK-006 section.
- Nits: the docs used a Unicode "…" where the code prints "...", and a comment still said "Name every blocker".

### Second rework (2026-11-02)

- **A1**: `dispatch.rs` `project.rename_screen` now rebinds the session before moving annotations. On a failed move it bumps the revision, sends the `project.rename_screen` notification, and then returns the error.
  - The new test `session_reset::a_failed_annotation_move_still_rebinds_the_session_to_the_renamed_file` exposed a deeper cause. The service had opened `main` while the manifest's active screen was another one. `was_active`, read from the manifest, was false, so the session was never rebound, on success or on failure.
  - The service now also rebinds when the session's own path is the renamed screen's file. The test failed before this change (`left == right`, the old path) and passes after it.
- **A2**: on a structural change, the Agent Bridge rebind now reloads `self.review = self.load_review()`. Every store operation saves at once, so nothing unsaved is dropped.
- **A3**: the reference now points to TASK-012. Nits: the docs now print "... and N more" and the comment says up to eight.
- **B1** (from TASK-015's review): the CHANGELOG now gives the fixture memory before (62–64 MB) and after (74–76 MB) the refresh fix, and says the growth is not separated from machine state.

Gates after the second rework (Windows):
- fmt clean;
- clippy `-D warnings` clean;
- `cargo test --workspace --locked --no-fail-fast`: 28 groups, 309 passed, 0 failed;
- pytest 36 passed, 1 skipped;
- deny ok.

Not re-run: the release build and GUI trust. No `.slint` file changed, and `agent.rs`'s reload path has no GUI trust case.

### Confirmation review of the second rework (2026-11-02)

**REWORK REQUIRED.** The reviewer ran the gates at `e864cdf`: 309 passed, everything else clean. A1, A3, B1 and the nits are confirmed, and TASK-011 is PASS. Findings:

- **A2-1 (Low–Medium, introduced by `e864cdf`)**: the review-store reload after a bridged rename left an open note draft keyed to the old screen id. Saving it put the note back under the dead id, with no error. Before the reload that save was refused. A probe showed `main=1 renamed=0`.
- **A1-1 (Low, pre-existing, library-only state)**: `was_active = bound || active_screen() == old` could rebind a session that edits another screen. A probe renamed `123` while the session was on `main`, and `main`'s content overwrote it.

### Third rework (2026-11-02)

- **A2-1**: the reload moved into `App::reload_review_after_structure_change(&screens_before)` (`agent.rs`).
  - If the open draft's screen was the one screen that disappeared while exactly one appeared (a rename), the draft is re-keyed to the new id.
  - If the screen vanished any other way, the dialog is closed with the new status `notes.page_gone` (en/zh) instead of saving under a dead id.
  - Tests: `an_open_note_follows_a_bridged_rename` (saved under `renamed`, nothing under `main`) and `an_open_note_for_a_vanished_page_is_closed_not_saved`.
- **A1-1**: the rebind now depends only on whether the session edits the renamed screen's file (`dispatch.rs`).
  - Test: `session_reset::renaming_another_screen_leaves_the_session_on_its_own_file`.
- Failure evidence for both: the reviewer's probes on `e864cdf`, recorded above.

Gates (Windows):
- fmt clean;
- clippy `-D warnings` clean;
- `cargo test --workspace --locked --no-fail-fast`: 28 groups, 312 passed, 0 failed;
- pytest 36 passed, 1 skipped;
- deny ok.

Not re-run: the release build and GUI trust. No `.slint` file changed.

### Confirmation review of the third rework (2026-11-02)

**PASS.** The reviewer re-ran the gates at `9620bc3`: fmt and clippy clean, 312 passed, pytest 36 passed and 1 skipped, deny ok.

- **A2-1 confirmed fixed by probes.** An edited or new note follows a rename, and so does a chain of renames. A draft for a page that is not active also follows. Two unrelated renames, a rename plus a create, or a delete close the draft with `notes.page_gone`.
- **A1-1 confirmed fixed.** The new test fails against the old condition.

Remaining findings, none blocking 2.4.0 in the reviewer's judgement, left as follow-ups:
- (Low) An agent that reuses the old id in the same batch (rename `main`→`x` then create `main`) catches an open draft on the new `main`.
- (Low, suspicion, since `e864cdf`) A rename whose annotation move fails returns an error response, so the desktop skips the rebind and the review reload, and an open draft stays on the old id.
- (Nit) After a re-key the open dialog's anchor text still names the old page.
- (Nit) The byte-length assertion in `renaming_another_screen_leaves_the_session_on_its_own_file` is not discriminating; the path check and `assert_ne!` carry the test.

Not verified on this tree: macOS and Linux (they need the three-platform CI), and a release build with GUI trust after `f5e2653`. The `.slint` files have not changed since that GUI trust run.

### Three-platform CI rework (2026-11-02)

The first push of `integrate/2.4.0` ran the Rust workflow on every platform. Three failures, all from local-only work that had never been through CI:

- **Clippy on macOS and Linux (all four runners)**: `crates/mono-project/tests/safety.rs` imported `EditorSession` and `load_scene` unconditionally, but only a `#[cfg(windows)]` test uses them. Outside Windows the imports were unused, and `-D warnings` failed. Fix: both imports are now `#[cfg(windows)]`.
- **Tests on windows-latest**: `guard::tests::renaming_the_active_screen_rebinds_the_session_and_never_writes_the_old_path` compared paths literally. The runner's `temp_dir()` is the 8.3 short path `C:\Users\RUNNER~1\…`, while the session holds the project's resolved root `C:\Users\runneradmin\…`. Same file, different spelling. Fix: the test canonicalizes both sides. Test-only; the product rebinds correctly.
- **Dependency policy**: `async-executor 1.14.0` (via `accesskit_unix` and `zbus`, under Slint) was yanked after the last local `cargo deny` run. Fix: `cargo update -p async-executor` to 1.14.1, Cargo.lock only.

Failure evidence: the CI logs of the first run on the branch, quoted above. No `.slint` or product source changed.
