# TASK-016 — Large-Scene Refresh Regression from the 2.3.0 Integration

Status: VERIFY
Review Status: PENDING (no independent review yet)

## Goal

Bring a full refresh on large scenes back to its pre-integration cost without changing what the Review workspace shows. Do not ship, tag or push.

## Background

TASK-015 re-measured performance on the integrated tree (`docs/rewrite/G4_EVIDENCE.md` §4 "2026-11-02"):

| Scene | `panel_refresh_all` before the integration | after |
|---|---|---|
| 1005 elements | 11.1–13.4 ms | 306.9–517.3 ms |
| 50 digits | 15.1–16.0 ms | 58.4–73.7 ms |

The user approved this TASK on 2026-11-02 ("Yes, open TASK-016").

## Current Problem

2.3.0 added `refresh_review()` to `App::refresh_all_inner`, so a screen open, an Agent refresh or any other full refresh rebuilds the Review workspace even when it is not visible. Each rebuild:

- renders the scene again;
- builds the C header and hex;
- diffs the elements pairwise: `Vec::contains` over ids for added and removed, and an `any` scan of the baseline per element for modified, allocating id strings with `py_str` for every pair.

The Designer's own diff (`refresh_canvas`) already indexes by id.

The before-measurement (Result) showed that Review explains the 1005-element regression but only 16 of the 61 ms on 50 digits. The second cause, also from 2.3.0: `refresh_inspector` → `refresh_notes` → `note_rows` calls `compute_frame_evidence()`, which renders the whole scene again on every Inspector refresh, even right after `refresh_canvas` has stored that frame's evidence. Its doc comment says it should do so only "when the canvas has not done it". This affects every edit path, not only full refreshes (`panel_inspector_ms` 16.5–17.1 ms on 50 digits).

## Evidence

- `apps/mono-desktop/src/app.rs`: `refresh_all_inner` calls `refresh_review`, and `refresh_review` diffs elements with `contains` / `any`.
- `apps/mono-desktop/src/main.rs` `switch_workspace` already calls `refresh_review` on entering workspace 3.
- Before the fix, a direct timing of `refresh_review` (new bench row `panel_review_ms`) — recorded in Result.

## Required Changes

1. Bench: add `panel_review_ms`, the Review refresh body on its own.
2. `refresh_all_inner` refreshes Review only while the Review workspace (3) is open; entering it keeps refreshing it (`switch_workspace`).
3. `refresh_review`'s element diff uses id sets and an id index, as `refresh_canvas` does; added / removed / modified lists and their order stay the same.
4. Where `refresh_canvas` runs immediately before `refresh_inspector` in the same call (`refresh_all_inner`, `after_edit`, `state_edited` and the other sites with that pair), the note rows reuse the canvas's evidence instead of rendering again. A bare `refresh_inspector` (selection change, headless tests) keeps recomputing.
5. A unit test pins the diff (added, removed, modified, order) against the previous pairwise definition.
6. Re-measure the fixture, the 1005-element and the 50-digit scenes; update G4 §4 and `CHANGELOG.md` `Unreleased`.

## Out of Scope

- The other budgets (stroke, theme, cold start, evidence export, encode).
- Incremental rendering or the undo snapshot model.
- A release, version bump, tag, push or PR; any change to `fixtures/golden/` or `test_assets/`.

## Protected Existing Work

- TASK-014 and TASK-015 commits and records.
- `fixtures/golden/` and `test_assets/`.

## Constraints

- `AGENTS.md` gates; GUI runs with temporary configuration directories on fixture copies.
- No push, tag, rebase, stash or clean without explicit instruction.
- The implementer stops at VERIFY.

## Allowed Files / Expected Area

- `apps/mono-desktop/src/app.rs`, `apps/mono-desktop/src/bench.rs` (if needed);
- `docs/rewrite/G4_EVIDENCE.md`, `CHANGELOG.md`;
- `.ai/tasks/TASK-016.md`, `.ai/CURRENT_STATE.md`.

## Acceptance Criteria

1. `panel_refresh_all` on 1005 elements and 50 digits returns to the range measured before the integration, or the remaining difference is explained by measurement.
2. Review shows the same diff lists, and is current whenever its workspace is opened.
3. The five CI gates and `CHECK_GUI_TRUST.py` (release, temporary configuration directories) pass.
4. `git diff origin/main -- fixtures/golden test_assets` is empty.

## Verification Plan

Release build; `RUN_DESKTOP_BENCH.py --runs 3` on the three projects before and after; the five gates; `CHECK_GUI_TRUST.py`; the golden diff.

## Deliverables

- Commits on the session branch (not pushed).
- This record, `.ai/CURRENT_STATE.md`, G4 §4 and `CHANGELOG.md`.

## Result

Results come from the commands that were actually run on Windows 10 (release builds, `python tools/RUN_DESKTOP_BENCH.py --runs 3` on the fixture and on the `BENCH_DESIGNER_PROJECT.py` 1005-element and 50-digit projects from TASK-015).

Failure evidence, on a build with only the new `panel_review_ms` row (commit "bench(desktop): time the Review refresh on its own"):

- 1005 elements: `panel_review_ms` 261.9–295.9 ms of a 296.6–313.9 ms `panel_refresh_all`.
- 50 digits: `panel_review_ms` 15.9–17.2 ms of 61.5–61.9 ms. The rest came from `panel_inspector_ms` 16.5–17.1 ms, which is one full render by `note_rows`.

Changes:

1. Review is rebuilt in `refresh_all_inner` only while `workspace == REVIEW_WORKSPACE` (3). `switch_workspace` still rebuilds it on entry, and the contract-adoption path still refreshes it.
2. `element_diff` indexes ids. `review_element_diff_matches_the_pairwise_definition` compares it with the pairwise definition 2.3.0 shipped, including duplicate ids, missing ids and order.
3. `refresh_inspector_after_canvas` lets the note rows reuse the evidence `refresh_canvas` has just stored. It is used at the six sites where the canvas refresh immediately precedes the Inspector refresh. A bare `refresh_inspector` and the headless tests still render (`note_rows_reuse_the_canvas_frame_only_right_after_it`).
4. The first after-measurement still showed 29.8–32.3 ms for a 50-digit full refresh: `refresh_all_inner` called `refresh_notes()` a second time, outside the reuse bracket. That duplicate call was removed (the Inspector refreshes the notes).

Final measurement:

| Scene | `panel_refresh_all` | `max_handler` | Before the integration |
|---|---|---|---|
| 1005 elements | 11.8–15.0 ms | 19.5–24.1 ms | 11.1–13.4 ms; 20.5–23.1 ms |
| 50 digits | 14.9–16.1 ms | 22.2–27.1 ms | 15.1–16.0 ms; 21.4–22.7 ms |
| Fixture | 1.38–1.61 ms | 1.77–2.31 ms | — |

- State and geometry edits are back in their pre-integration ranges.
- The 16 ms handler budget is still missed on the two generated scenes, as before the integration.
- The full figures are in `docs/rewrite/G4_EVIDENCE.md` §4 "整合回退的修复（TASK-016）", and the `CHANGELOG.md` `Unreleased` sentence is updated.

Gates:

- `cargo fmt --all -- --check`: clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: clean.
- `cargo test --workspace --locked --no-fail-fast`: 28 groups, 304 passed, 0 failed.
- `python -m pytest tools/tests -q`: 36 passed, 1 skipped.
- `cargo deny check`: advisories, bans, licenses and sources ok.
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe`, on the final release build with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in a fresh temporary directory: 17 of 17 PASS, exit 0.
- `git diff origin/main -- fixtures/golden test_assets`: empty.

Not verified:

- macOS and Linux.
- A manual GUI walk of the Review workspace after an edit made in another workspace. Entering Review goes through `switch_workspace`, which still rebuilds it, but no automated check opens Review after such an edit.
