# TASK-015 — Close TASK-014's Verification Gaps

Status: VERIFY
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

Results come from the commands that were actually run on Windows 10, on the session branch based on `integrate/2.4.0`.

1. Escaping members:
   - Failure evidence: `gallery_card_reports_an_escaping_member_without_reading_it` failed first with "the card must say why it has no frame: main · 1 blockers · 0 warnings · 0 notes". The card hid the refusal.
   - Fix: `GalleryCard.render_error` keeps the renderer's message, and `gallery_detail` appends "Render failed: …" (existing key `status.render_failed`).
   - Refactors for testing, with no behaviour change: `App::review_render` was extracted from `refresh_review`, and the Review summary uses the shared `render_failed`.
   - `review_panel_reports_an_escaping_member_without_reading_it` passed on first run, so it is coverage, not a fix. The render is refused with "escapes project root", and the evidence view has no frame hash and no C or hex code.
   - Both tests put a decodable image at `<base>/outside.png` and declare it 1x1. They assert `ASSET_PATH_ESCAPE` is blocking and that there is no `ASSET_SIZE_MISMATCH`, which proves the file was never opened.
2. `tools/CHECK_GUI_TRUST.py`: `check_inspector_tabs_at_min_size` loops over tabs 0 to 5, requires six distinct shots and says "six".
3. Performance, re-measured on a release build of the integrated tree:
   - `target/release/mono.exe bench --project test_assets/projects/curing_lite/project.oled.json` ×3;
   - `python tools/RUN_DESKTOP_BENCH.py --runs 3` on the fixture and on the `tools/BENCH_DESIGNER_PROJECT.py --elements 1000` and `--elements 0 --digits 50` projects.
   - Results are in `docs/rewrite/G4_EVIDENCE.md` §4 "2026-11-02", and `CHANGELOG.md` `Unreleased` carries them.
   - **Regression found, not fixed (out of scope):** on 1005 elements, `panel_refresh_all` went from 11.1–13.4 ms to 306.9–517.3 ms, and `max_handler` to 31.0–73.2 ms. On 50 digits they are 58.4–73.7 ms and 49.3–72.7 ms.
   - HYPOTHESIS (read-only diagnosis): 2.3.0 put `refresh_review()` in `refresh_all_inner`. On every refresh it renders the scene again, builds the C header and diffs the elements pairwise, whichever workspace is open.
   - Other figures: the fixture's handler (4.26–10.63 ms) and memory (62.2–63.7 MB) are within budget. The encode p95 is 1.84–2.04 ms (one run over 2 ms). The evidence export takes 1654–1749 ms. The stroke, theme and cold-start waits are all higher than before the integration, and machine state versus code was not separated.
   - A first attempt at the generated-scene desktop runs passed a wrong project path (`}`). Those outputs were discarded and the runs repeated with the generated `project.oled.json` files.
4. `every_model_property_is_used`:
   - It now scans `ReviewModel`, `GalleryModel`, `NoteModel`, `AgentModel` and `NewProjectModel`, with `review.slint`, `gallery.slint`, `notes.slint`, `agent.slint` and `new_project.slint` added to `files`.
   - Failure evidence: the first run reported `AgentModel.endpoint`, `ReviewModel.hash-match` and `ReviewModel.percent` as read by no view.
   - All three were removed, together with their setters. The agent panel shows `host:port`; the Review view uses `contract-status` and `summary`.

Gates:

- `cargo fmt --all -- --check`: clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: clean.
- `cargo test --workspace --locked --no-fail-fast`: 28 groups, 302 passed, 0 failed.
- `python -m pytest tools/tests -q`: 36 passed, 1 skipped.
- `cargo deny check`: advisories, bans, licenses and sources ok.
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe`, with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in a fresh temporary directory: 17 of 17 PASS, exit 0. It ran against a release build of the code commits; the later commits change only documentation.
- `git diff origin/main -- fixtures/golden test_assets`: empty.

Not verified: macOS and Linux; a direct timing of `refresh_review` inside `refresh_all`.

Follow-up for the user: decide whether the refresh regression on large scenes is fixed before 2.4.0. That needs its own TASK.
