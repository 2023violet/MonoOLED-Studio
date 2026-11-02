# TASK-015 — Close TASK-014's Verification Gaps

Status: APPROVED
Review Status: PENDING (no independent review yet)

## Goal

Close the four gaps TASK-014 left unverified on the integrated tree (`integrate/2.4.0`), so that the planned 2.4.0 release does not rest on figures or scans that predate the integration. Do not ship, tag or push.

## Background

TASK-014 merged the unshipped TASK-010..013 line onto 2.3.0. Its Result lists what it did not verify:

- the gallery and the Review evidence panel with an escaping member: both render through the checked renderer, but no test exercises them;
- `tools/CHECK_GUI_TRUST.py` checks Inspector tabs 0 to 4, while the integrated Inspector has six tabs (notes moved to index 5);
- the TASK-012/TASK-013 performance figures in `docs/rewrite/G4_EVIDENCE.md` §4 and `CHANGELOG.md` `Unreleased` were measured before the integration;
- `every_model_property_is_used` (`ui_source_tests` in `apps/mono-desktop/src/main.rs`) does not scan the globals 2.3.0 added.

The user approved this scope in the plan of the session that started this task (2026-11-02).

## Current Problem

1. A scene that references `../outside.png` is refused by the renderer and by validation, but nothing proves the gallery card or the Review panel shows that refusal, or that they never read the file. The gallery card shows a blank thumbnail and a blocker count; it does not say the render failed.
2. The GUI trust check would pass even if the notes tab (5) rendered nothing.
3. Performance claims for the integrated tree are unmeasured.
4. Dead bindings on `ReviewModel`, `GalleryModel`, `NoteModel`, `AgentModel` and `NewProjectModel` would not be caught.

## Evidence

- `.ai/tasks/TASK-014.md` Result, "Not verified" and the Inspector note.
- `apps/mono-desktop/src/gallery.rs` `build_cards` drops the render error (`.ok()`).
- `tools/CHECK_GUI_TRUST.py` `check_inspector_tabs_at_min_size` loops `range(5)`.
- `CHANGELOG.md` `Unreleased`: "All figures in this section were measured before the integration with 2.3.0 and have not been re-run on it."
- `apps/mono-desktop/src/main.rs` `every_model_property_is_used` lists only the pre-2.3.0 globals.

## Required Changes

1. Desktop tests with a scene member `../outside.png`, for the gallery card and for the Review panel's render and evidence. Each asserts that a render failure is reported and that the file outside the project is not read. The gallery card names the render failure in its detail line (existing key `status.render_failed`).
2. `check_inspector_tabs_at_min_size` covers tabs 0 to 5 and says "six".
3. Re-run `mono bench`, the desktop `--bench` and the `tools/BENCH_DESIGNER_PROJECT.py` 1005-element and 50-digit scenes on a release build of the integrated tree; record them in `docs/rewrite/G4_EVIDENCE.md` §4 and replace the "measured before the integration" sentence in `CHANGELOG.md` `Unreleased` with the measured values.
4. Extend `every_model_property_is_used` to `ReviewModel`, `GalleryModel`, `NoteModel`, `AgentModel` and `NewProjectModel`, with their `.slint` files; record the failure evidence; remove or wire every dead binding it finds.

## Out of Scope

- A release, version bump, tag, push or PR.
- The review-pack release-gate question TASK-014 left to the user.
- Performance work to bring a missed budget back under its limit.
- Any change to `fixtures/golden/` or `test_assets/`.

## Protected Existing Work

- TASK-014's merge and record; every 2.3.0 release entry and evidence file.
- `fixtures/golden/` and `test_assets/`.

## Constraints

- `AGENTS.md` gates; GUI runs with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in temporary directories, on fixture copies.
- No push, tag, rebase, stash or clean without explicit instruction.
- The implementer stops at VERIFY.

## Allowed Files / Expected Area

- `apps/mono-desktop/src/app.rs`, `apps/mono-desktop/src/gallery.rs`, `apps/mono-desktop/src/main.rs`, and `apps/mono-desktop/ui/*.slint` only where a dead binding is removed or wired;
- `tools/CHECK_GUI_TRUST.py`;
- `docs/rewrite/G4_EVIDENCE.md`, `CHANGELOG.md`;
- `.ai/tasks/TASK-015.md`, `.ai/CURRENT_STATE.md`.

## Acceptance Criteria

1. The new desktop tests pass, and each would fail if the gallery or the Review panel read the outside file or hid the failure.
2. `CHECK_GUI_TRUST.py` checks six tabs and passes on a release build.
3. G4 §4 and `CHANGELOG.md` carry figures measured on the integrated tree, with the misses stated as misses.
4. The extended scan passes with no allow-list entry added to hide a dead binding.
5. fmt, clippy `-D warnings`, `cargo test --workspace --locked`, pytest on `tools/tests` and `cargo deny check` pass.
6. `git diff origin/main -- fixtures/golden test_assets` is empty.

## Verification Plan

Run the five CI gates; build release; run `tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` with the three configuration variables in a temporary directory; run the benchmarks on the release build; check the golden diff.

## Deliverables

- Commits on the session branch (not pushed).
- This record and `.ai/CURRENT_STATE.md`.

## Result

(pending)
