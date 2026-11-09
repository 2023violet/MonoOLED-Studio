# TASK-019 — Correctness Follow-ups from the 2.4.0 Reviews

Status: APPROVED
Review Status: PENDING (no independent review yet)

## Goal

Close the small follow-ups that the TASK-006/007 and TASK-017 reviews left. Do not ship, tag or push.

## Background

The user approved this TASK on 2026-11-08, as the second part of the plan "Next optimization round", to run after TASK-018. The items come from:

- `.ai/CURRENT_STATE.md`, "Proposed follow-up fix task" from the TASK-006/007 review;
- `.ai/tasks/TASK-017.md`, Review Status (Low, follow-up).

## Current Problem

1. `ASSET_PATH_ESCAPE` is emitted by validation but missing from `FINDING_CODES` (`crates/mono-project/src/export.rs`), so it has no en/zh label. No test checks that every emitted code is listed.
2. `palette_actions_are_dispatchable` (`apps/mono-desktop/src/commands.rs`) is tautological: it would pass for an action no handler dispatches.
3. With no baseline, the Designer drawer reports that 100% of pixels changed instead of saying there is no baseline.
4. `CHANGELOG.md` does not say that 2.0.4, 2.0.5 and 2.1.0 were never tagged.
5. TASK-017 gaps with no test:
   - the CLI's text line for a review pack with blocking findings;
   - a non-zero `blocking_frames` in `--json`;
   - the desktop status key choice;
   - a pack whose only blocker is in an annotated state.

## Evidence

The review records named above. Failure evidence for each behaviour change is recorded in Result.

## Required Changes

1. Add `ASSET_PATH_ESCAPE` to `FINDING_CODES` with en/zh labels. Add a test that every code the validator can emit is listed (failure evidence first).
2. Replace `palette_actions_are_dispatchable` with a test that each palette action reaches a real handler.
3. With no baseline, the drawer says so (en/zh), with a test.
4. Add a `CHANGELOG.md` note on the untagged versions.
5. Tests for the TASK-017 gaps. The annotated-state case builds its font-pack fixture in a temporary directory inside the test.

## Out of Scope

- TASK-014's Low/Nit rename edge cases.
- Any performance work (TASK-018).
- `fixtures/golden/` and `test_assets/`.
- A release, tag, push or PR.

## Protected Existing Work

- TASK-018's changes and record.
- The 2.4.0 release records.
- `fixtures/golden/` and `test_assets/`.

## Constraints

- `AGENTS.md` gates.
- The implementer stops at VERIFY.
- No push, tag, rebase, stash or clean without explicit instruction.

## Allowed Files / Expected Area

- `crates/mono-project/src/export.rs`;
- `apps/mono-desktop/src/commands.rs`, `app.rs` and `i18n/strings.json`;
- `apps/mono-cli/tests/`;
- `CHANGELOG.md`;
- `.ai/tasks/TASK-019.md` and `.ai/CURRENT_STATE.md`.

## Acceptance Criteria

1. Each item is closed with a test, or for item 4 the text.
2. The five gates and `CHECK_GUI_TRUST.py` pass.
3. The golden diff is empty.

## Verification Plan

The five gates, `CHECK_GUI_TRUST.py` on a release build with temporary configuration directories, and the golden diff.

## Deliverables

- Commits on `claude/perf-task-018` after TASK-018 (not pushed).
- This record and `.ai/CURRENT_STATE.md`.

## Result

(pending)
