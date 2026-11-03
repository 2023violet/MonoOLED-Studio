# TASK-017 — Review Pack Marks Blocking Findings as Not a Deliverable

Status: VERIFY
Review Status: NOT REVIEWED

## Goal

When a review pack contains a frame with a blocking finding, the page says plainly that it is not a deliverable. The pack is still generated (ADR-007 D1, option C). This TASK precedes the 2.4.0 release.

## Background

TASK-014 left one product question open: the review pack added in 2.3.0 renders every screen whatever its findings, outside the release gate (ADR-006). The user delegated the remaining decisions and the 2.4.0 release on 2026-11-02 ("全程自行决策执行直到发布新版本"). ADR-007 records the choice: keep generating the pack, and mark it.

## Required Changes

1. `crates/mono-project/src/review_pack.rs`:
   - count the rendered frames (init frames plus annotated states) that carry at least one blocking finding;
   - when that count is non-zero, write a static banner into the page, readable without JavaScript, that says the pack is not a deliverable, gives the count, and says export refuses these scenes;
   - expose the count as `totals.blocking_frames` in the embedded data and `ReviewPackSummary::blocking_frames`.
2. A pack without blocking frames keeps the existing page structure; only the version string and the additive `blocking_frames` field change.
3. `mono review-pack --json` adds `blocking_frames`. The desktop status line names the blocking frames when there are any (en/zh key).
4. Tests:
   - a blocking scene gets the banner with the right count;
   - a clean project has no banner;
   - a blocker only in an annotated state also triggers the banner.
5. Documentation: `docs/REVIEW_PACK.md`, `CHANGELOG.md` `Unreleased`.

## Out of Scope

- Refusing to write the pack (option B) or gating the Output Workbench and `export.bitmap_data` (ADR-007 D2).
- Rendering the full state matrix in the pack.
- Changes to `fixtures/golden/` or `test_assets/`.

## Acceptance Criteria

- The banner appears exactly when a rendered frame has a blocking finding.
- Two runs over the same inputs remain byte-identical.
- All CI gates pass.

## Verification Plan

New unit tests in `review_pack.rs`, CLI JSON test, the five CI gates.

## Result

- `review_pack.rs`: `blocking_frames` counts rendered frames with a blocking finding; `gate_banner` writes a static `<div id="gate" role="alert">` after the renderer-honesty banner when it is non-zero. The placeholder `__GATE_BANNER__` is replaced before the pack data, so annotation text cannot trigger it. A clean pack's page differs from 2.3.0's template only by the version and the additive `totals.blocking_frames` field. The banner styles itself inline, so the shared stylesheet is unchanged.
- `ReviewPackSummary::blocking_frames`; `mono review-pack` prints `NOT A DELIVERABLE: …` in text mode and adds `blocking_frames` to `--json`. The desktop status uses the new key `status.review_pack_blocking` (en/zh) when the count is non-zero.
- Tests: `a_clean_pack_has_no_gate_banner`, `a_blocking_scene_marks_the_pack_as_not_a_deliverable`, `annotated_frames_count_towards_the_gate_banner` (an editor placeholder is a `DRAFT_PLACEHOLDER` blocker that still renders; an escaping member cannot be used because the pack refuses to render it). The CLI test asserts `blocking_frames` is 0 on the clean fixture.
- Deviation from the contract: requirement 4's "blocker only in an annotated state" case was replaced by the annotated-frame counting test. Per-element blockers in `validate_scene` ignore `visible_when`, and state-dependent blockers that still render need a font pack fixture; the counting test proves that annotated frames are included.
- Failure evidence: the three new review-pack tests fail on the pre-change code (no `blocking_frames`, no banner).
- Docs: `docs/REVIEW_PACK.md` (new section, `--json` fields), `CHANGELOG.md` Unreleased (Compatibility sentence and Added), `docs/AI_HANDOFF.md` §5.5 boundary text, ADR-007.
