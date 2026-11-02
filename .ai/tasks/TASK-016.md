# TASK-016 — Large-Scene Refresh Regression from the 2.3.0 Integration

Status: APPROVED
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

(pending)
