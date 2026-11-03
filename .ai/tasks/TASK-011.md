# TASK-011 — Truthful Controls, Exposed Engine

> Renumbered from TASK-005 on 2026-11-02 by TASK-014, when this line of work was integrated with `origin/main`, whose own TASK-004 to TASK-009 already used those numbers. The body below is unchanged: where it says TASK-004, TASK-005, TASK-006 or TASK-007 it means TASK-010, TASK-011, TASK-012 or TASK-013.

Status: VERIFY
Review Status: REWORK REQUIRED (final verdict 2026-11-02; see `### Final verdict`)

## Goal

Two defect classes left over after TASK-004:

1. Controls and documents that say something the code does not do — a preference
   row nothing reads, a model property nothing renders, a manual describing a
   feature that does not exist, and rule files stating behaviour that has already
   changed.
2. Engine capabilities that outrun the interface — state schema and relations,
   design rules, page rename, glyph offsets are implemented and validated in the
   crates, but the desktop app has no entry point for them.

## Background

The approved plan `clever-ridge-darter.md` sets the audience as the maintainer
plus a small circle of colleagues and the community, so the round is scoped as a
minimum verifiable batch: six work packages in three tiers, each tier releasable
and revertable on its own. The user chose both themes and kept the release-gate
boundary where it is (Output Workbench and `export.bitmap_data` stay outside
`preflight`, documented rather than silently widened).

## Current Problem and Failure Evidence

Each row was grep-confirmed before the change:

- R1/WP1 `canvas.zones`, `appearance.reduced_motion` and `performance.overlay`
  were written by Preferences and read by nothing; `AppModel.tabs`/`DocTab` and
  `AppModel.toast` were declared and never driven.
- R2/WP2 the zone geometry exists in `mono-project/src/export.rs` yet no control
  could show it, and the overlay flags were applied only on edit, never at startup.
- R3/WP3 `bgjob.rs` computed a progress stage that `app.rs` threw away, so the
  status bar showed `12/40` with no label; cancelling needed the command palette;
  `EditorSession::undo_label()` existed with no exit point.
- R4/WP4 `validate_state_schema` and the relation vocabulary were engine-only;
  `apply_state_schema` was a private duplicate inside `dispatch.rs`.
- R5/WP5 `ProjectWorkspace::rename_screen` and `design_rules` were reachable only
  through the Automation API or by hand-editing JSON.
- R6/WP6 the guides claimed a marquee selection that `app.rs` does not implement
  and a Navigator rename that did not exist; `AI_HANDOFF.md` still called the four
  background jobs synchronous; `AGENTS.md` still claimed opening a screen rewrites
  the manifest; workbench copy was hardcoded Chinese that bypassed i18n.

## Required Changes

1. Delete the pipes that were never wired; make `template.none` tell the user what
   to do next.
2. Draw `design_rules.zones` on the canvas behind a real toggle, fed by the
   `canvas.zones` preference and restored at startup.
3. Show the job stage and a Cancel control in the status bar; name what the next
   undo reverts.
4. Inspector → State schema tab: edit variables and relations, validated by the
   engine, one undo step, preview re-seeded; lift `apply_state_schema` into
   `mono-core/src/state.rs` so Automation and the panel share one implementation.
5. Inspector → Design rules tab and Navigator rename: `set_design_rules` via
   `transact`, session re-bound after `fs::rename`, findings following without a
   reopen; never write `design_rules` for a project that was not edited.
6. Documentation truth pass plus i18n bypass cleanup, and the Font Lab glyph
   offset rows feeding `GenerateOptions::offset`.
7. Shared anti-regression scans: `every_model_property_is_used`,
   `every_preference_row_is_consumed`, `strings_json_is_exactly_paired_and_used`,
   `no_user_facing_copy_bypasses_i18n`, and `tools/tests/test_docs_match_code.py`.

## Verification

- CI gates: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets
  --locked -- -D warnings`, `cargo test --workspace --locked` (125 passed),
  `python -m pytest tools/tests -q` (33 passed, 1 skipped), `cargo deny check`.
- Golden corpora unchanged: `golden_{encoding,raster,manifest,scenes,projects,fonts,handoff,automation}`.
- New SELFCHECK hooks: `dump:zones`, `dump:job`, `dump:undo-label`, `dump:states`,
  `dump:rules`, `dump:findings`, `dump:screen-ids`, `dump:selection`,
  `dump:font-offset`, plus `later:<ms>:<action>`, `font-edit:`, `schema:`,
  `rules:`, `prompt-answer:` drivers.
- `tools/CHECK_GUI_TRUST.py`: 15 end-to-end cases against the real binary, all
  PASS, each on a throwaway copy of `test_assets/projects/curing_lite` with the
  config environment pointed at a temp directory.
- Negative proof for the new scans: an injected dead model property and an
  injected unread preference row each make their guard fail, then were reverted.

## Deliberately Not Changed

- Marquee selection, resize handles, animation frames and onion skin,
  cross-project copy/paste, multi-document tabs (deleted instead of finished).
- The release-gate boundary, performance budgets and G4 evidence, real-device
  validation, new dependencies.
- `mono-core`'s Chinese engine messages stay Chinese and are now documented as
  engine-level copy: `mono-core` has no i18n layer, so CLI, Automation and the
  desktop return the identical string.

## Review Status

Three independent review slices were dispatched over the combined TASK-004 +
TASK-005 tree. Every Critical/Important finding was reproduced in the source
before it was acted on, and one was refused:

- Slice 1 (TASK-004 scope): six Important findings, four accepted and fixed, one
  rejected after reading the code — the claim that cancelling a rename still
  prints a success status is false, because `finish_prompt` refreshes only on
  `Ok` — and one downgraded to Minor.
- Slice 2 (TASK-005 scope): the `every_preference_row_is_consumed` guard could be
  satisfied by the row's own table; the release-gate sentence in `CHANGELOG.md`,
  `docs/AUTOMATION_API_V1.md` and both guides promised "nothing is written" while
  the blocking report *is* written; a failed rename rollback swallowed its
  second error; the Design rules panel could show rules a project never had after
  another screen's edit; and no crate test proved the write-on-edit behaviour. All
  five fixed, the last by `crates/mono-project/tests/design_rules.rs`.
- Slice 3 (UI and runtime): the Font Lab offset rows were disabled exactly when
  they were the only way out (a leftover offset is what makes a TrueType file
  required, and the engine blamed the characters instead) — the rows now stay
  editable and `mono-font` names the real cause; an Automation `font.generate`
  offset far outside ±64 reached `ox * antialias_scale` and overflowed, so the
  generator now validates the range every caller shares; the scripted `later:` /
  `select-later:` timers were the only event-loop entries borrowing the app state
  unconditionally, which panics when a nested dialog is open, so they skip while
  busy like the pointer and close handlers; five Inspector tabs in a 310px panel
  elided "State" and "State schema" to the same letters, so the strip abbreviates
  the two long names (`tab.schema` / `tab.rules`) and both guides say so; and the
  orphan-key scan counted a key that survived only inside a comment as used, so
  comments are stripped before the search.
- Pinned by tests rather than by reading: `test_every_dialog_really_closes_on_the_
  backdrop` (the manuals promise a backdrop click dismisses any dialog; each of
  the eight `inherits Scrim` components handles `dismissed`, `Scrim`'s TouchArea
  emits it, and nothing sets `dismissable: false`), `test_the_offset_rows_stay_
  reachable_with_no_font_file`, and `the_unsaved_prompt_agrees_with_its_subject`
  (one dirty document no longer reads "Designer scene have unsaved changes").

Accepted and left as known gaps, each checked before being called acceptable:

- A case-only page rename (`Main` → `main`) is refused on Windows because
  `Path::exists()` is case-insensitive there, while Linux allows it. Failing with
  `E-EXISTS` is the safe side; making the two platforms agree needs a rename
  strategy for the file *and* the id, not a looser guard.
- Renaming a zone uses `shift_remove` + `insert`, so its row moves to the end of
  the panel. Nothing is lost and the manifest keeps its key order.
- `tooltip.export` names what the Handoff button produces (contract, PNG, Golden
  BIN), so the tooltip is accurate even though the key is named after exporting.
- `App::action`'s no-document guard does refuse `save` with no session, which is
  correct; `new-project` / `open-project` / `open-recent` never reach it, because
  `handle_action` intercepts them first — that is why the empty window's buttons
  work.
- The remaining minors (a stronger ordering assertion in
  `crates/mono-project/tests/state_schema.rs`, the `_`-prefixed runtime-key filter
  written in three places, `session_reset.rs` not asserting `is_dirty`) are left
  for the next round; none of them is a control that lies.

Outcome: implementation is complete and the gates below were re-run after the
last fix. `AGENTS.md` reserves `DONE` / `PASS` for an independent reviewer, so
this task stays at `VERIFY` with three absorbed review slices recorded above —
the verdict itself belongs to the maintainer, and was not awarded here.

### Final verdict (independent review, 2026-11-02)

**REWORK REQUIRED.** Checked against the integrated code on `integrate/2.4.0`
(a35d425).

- Re-run on `integrate/2.4.0` (a35d425) rather than taken from the recorded
  results: `cargo test --locked -p mono-desktop` (171 passed), `-p mono-core`
  (including the 3 `diff` tests), `-p mono-automation`, `-p mono-project` and
  `-p mono-cli` (all passed, 0 failed); `python -m pytest tools/tests -q`
  (36 passed, 1 skipped, including `test_version_consistency.py` and
  `test_docs_match_code.py`). fmt, clippy and `cargo deny` were not re-run by
  this review.
- Verified as recorded: `apply_state_schema` lives once in
  `mono-core/src/state.rs:40` and is used by Automation (`dispatch.rs:704`) and
  the editor (`editor.rs:745`); the zones overlay is a real toggle fed by
  `canvas.zones` (`prefs_ui.rs:491`, `designer.slint:428`); the anti-regression
  scans pass.

Finding (Important):

1. `apps/mono-desktop/src/guard.rs:255` - `rename_active_screen` calls
   `drop_session()` before `rename_screen`, and returns on its error without
   re-binding, so any refused rename leaves the Designer with no scene.
   Scenario: Navigator rename with an id `validate_screen_id` refuses (a space
   or `/`), an existing page id, or, on Windows, a case-only rename (`Main` to
   `main`, `E-EXISTS`, which this record calls "the safe side"). The error is
   shown and `finish_prompt` refreshes, but the Designer stays empty until the
   user reopens a page. Reproduced with a throwaway test (reverted, not
   committed): `app.rename_active_screen("bad id with spaces/..")` returns `Err`
   and leaves `app.session` as `None`. No data is lost (the prompt already
   saved or discarded), but the control leaves the app in a state the user did
   not ask for, which is the defect class this task exists to remove.

Fix scope (only this):

- In `rename_active_screen`, run the checks that can refuse the rename
  (`validate_screen_id`, the duplicate-id check, the target-exists check) before
  `drop_session()`; or, when `rename_screen` returns `Err` and the old scene
  file still exists, re-bind with `switch_screen(&active)` before returning the
  error. Keep dropping the session before the file move itself.
- Add a guard test next to
  `renaming_the_active_screen_rebinds_the_session_and_never_writes_the_old_path`:
  an invalid id and a duplicate id each return `Err` with `app.session` still
  bound to the original path and `is_dirty()` false.
- No other change; the known gaps listed above stay accepted.

Status stays `VERIFY` until that rework is reviewed.
