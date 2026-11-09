# TASK-019 — Correctness Follow-ups from the 2.4.0 Reviews

Status: VERIFY
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

All results come from commands actually run on Windows 10, on `claude/perf-task-018` after TASK-018.

1. **`ASSET_PATH_ESCAPE` in `FINDING_CODES`.**
   - Failure evidence: the new `export::tests::every_emitted_finding_code_is_listed` scans `export.rs`'s `Finding::new` calls. It failed with "emitted but not in FINDING_CODES: [\"ASSET_PATH_ESCAPE\"]".
   - Fix: the code is added (24 codes), with labels `finding.ASSET_PATH_ESCAPE` in en ("Asset path is outside the project") and zh ("资源路径在项目目录之外"). `every_finding_code_has_label` now covers it.
   - No document enumerates the codes.
2. **`palette_actions_are_dispatchable` rewritten.**
   - The old test checked `is_known`, which reads the same registry the palette lists.
   - The new test requires every palette action, in all five contexts, to be an arm of one of the three dispatchers: `handle_action` (main.rs), `App::extra_action` or `App::action`. A dynamic family must have its prefix matched. Line matching ignores `\r`, because this checkout uses CRLF.
   - It passes on the current code. A mutation that renamed the `asset-health` arm in `extras.rs` made it fail with "palette actions no dispatcher handles: {\"asset-health\"}". The mutation was reverted with `git checkout`.
3. **The drawer without a baseline.**
   - Failure evidence: `diff_summary_says_when_there_is_no_baseline` got "Changed 4 px (100.00%)".
   - `diff_summary` (extracted from `refresh_canvas`) now returns `diff.no_baseline` in en and zh when the baseline is empty, which happens when the scene did not render at open.
4. **`CHANGELOG.md`**: 2.1.0, 2.0.5 and 2.0.4 each say they were never tagged or published, and that their changes first shipped in the tagged 2.2.0. Checked against `git tag`: there is no `v2.0.4`, `v2.0.5` or `v2.1.0`.
5. **TASK-017 gaps.** Each of these new tests passed on its first run, so they add coverage, not fixes:
   - `a_blocking_review_pack_says_so_in_text_and_json` (CLI): the exact line "NOT A DELIVERABLE: 1 of 2 frames have blocking findings", `blocking_frames: 1` in `--json`, and the HTML banner. It uses a temporary fixture copy with a placeholder.
   - `a_blocker_only_in_an_annotated_state_still_marks_the_pack` (core): an annotated state with `seconds: 123456` puts `hero_digits` out of bounds in that state only. `blocking` is 0, `blocking_frames` is 1, and the banner says "1 of 3". No font-pack fixture was needed.
   - `review_pack_status_names_blocking_frames` (desktop): `review_pack_status`, extracted from `start_review_pack`, picks `status.review_pack_blocking` only when frames block, in en and zh.

### Gates

- `cargo fmt --all -- --check`: clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: clean. The first run flagged a `panic!` in the new CLI test; it is now `expect`.
- `cargo test --workspace --locked --no-fail-fast`: 30 groups, 327 passed, 0 failed.
- `python -m pytest tools/tests -q`: 36 passed, 1 skipped.
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` on a release build of the TASK-019 product code, with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in a temporary directory: 17 of 17 PASS.
- `git diff origin/main -- fixtures/golden test_assets`: empty.
- **`cargo deny check`: advisories FAILED** on RUSTSEC-2026-0441 (`pin-utils` unmaintained, via Slint 1.18.1). This is the same upstream advisory recorded in TASK-018. `Cargo.lock` is unchanged from `origin/main`. Accepting it was the user's dependency-policy decision. On 2026-11-08 the user approved accepting it; `deny.toml` now ignores RUSTSEC-2026-0441 with that rationale, and `cargo deny check` reports "advisories ok, bans ok, licenses ok, sources ok".

### Not verified

macOS and Linux (three-platform CI needs a push).
