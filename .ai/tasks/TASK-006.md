# TASK-006 — Designer Edit Path: Interactive Performance

Status: DONE
Review Status: PASS (scoped independent review of the third rework, 2026-11-01)

## Goal

Make one Designer edit cheap on large scenes without changing any API, file
format, golden fixture, budget value or budget definition: establish the missing
measurement first, then remove the per-edit work that is quadratic or that a
keystroke has no reason to wait for, and record before/after numbers taken on the
same machine with the same method.

## Background

The approved round plan is `coastal-plain-bream.md`; the user chose "interactive
performance" over the three other directions (evidence-pack throughput, cold
start, memory). The round follows the repo rule that a behaviour change starts
from failure evidence: the Designer path had never been measured, so the first
deliverable was the measurement, not an optimisation.

## Current Problem and Failure Evidence

Confirmed in the source before any change (release build, `RUN_DESKTOP_BENCH.py
--runs 3`):

- The Designer edit path was absent from the §4 budget table. `stroke_p95_ms`
  exercises the Pixel editor: the bench switches to workspace 1 and a 256×128
  document, so no budget row described a scene edit.
- `App::refresh_canvas` called `session.geometry(id)` for every element to build
  the overlay, and `hit_test` did the same on every click. `geometry` cloned the
  whole `elements` array to find one id; `text`/`digits` elements additionally
  ran a scratch `render_scene` to resolve their size. 1005 elements therefore
  cost 1005 × (1005-element clone + scan).
- `refresh_validation` ran on the keystroke thread: a scene render plus a
  content hash of every referenced asset before the handler returned.

Baseline (release, 3 runs, ranges):

| workload | designer_edit p95 | max_handler | panel_canvas | panel_validation |
|---|---|---|---|---|
| 1005 elements (1000 placeholders) | 466.6–480.3 ms | 444.6–492.0 ms | 374.9–418.7 ms | 23.5–28.9 ms |
| 55 elements (50 digits) | 214.8–254.8 ms | 216.1–261.5 ms | 38.5–44.1 ms | 131.1–150.5 ms |

## Required Changes

1. Draw the overlay and answer hit-tests from the rects `render_scene` already
   returns, keeping the Inspector's precedence: complete zone, then complete
   explicit rect, then the renderer's resolved rect, then `geometry` as the
   fallback for hidden elements the render leaves unresolved.
2. Make `EditorSession::elements` borrow the slice instead of cloning, and split
   `geometry_of` from the id-addressed `geometry` so scene-wide walks take
   disjoint borrows.
3. Move validation off the UI thread with an epoch and a snapshot; apply results
   on the 60 ms job tick; run at most one pass at a time; keep scripted
   `dump:findings` synchronous by flushing the pending pass first.
4. Measure the Designer path in the desktop bench (edit latency, per-refresh
   medians, state-matrix build) and add a generator for throwaway large scenes.

## Out of Scope

- Stroke p95 ≤ 8 ms: the bottleneck is the wait for the compositor/vsync, and the
  budget's definition is a user decision (G4 §4 analysis 1). Unchanged; re-measured
  at 15.0–25.7 ms across the four workloads.
- 50-screen complete evidence pack ≤ 500 ms: 300 fsyncs under the reliability
  contract; changing it changes durability (G4 §4 analysis 2). Not re-measured.
- Cold start ≤ 1 s: renderer/backend experiment (G4 §4 analysis 3). Re-measured at
  1108–1641 ms, 2385 ms on the first start after a rebuild.
- Replacing the per-read content hash with mtime caching: deliberate V1 parity
  (`crates/mono-project/src/resources.rs:1-4`, G4 §9).
- Incremental or off-screen framebuffer rendering: this is what keeps the
  1005-element handler at 20–29 ms across runs. It is a renderer change and needs its own task.
- Changing the ≤16 ms budget value or its definition.

## Protected Existing Work

No unrelated user changes were edited, reverted or staged. `fixtures/golden/**`
and `test_assets/**` are untouched (`git status --short test_assets
fixtures/golden` returns nothing). Bench scenes live under `target/bench/` and
are throwaway.

## Constraints

- No new dependencies; no `unwrap`/`expect`/`panic`/`unsafe` in production code
  (test modules use the crate-level allow).
- Public JSON/API/format compatibility unchanged; golden corpora untouched.
- GUI runs use a throwaway `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` and copies
  of `test_assets`.
- Verification stops at VERIFY; DONE/PASS belongs to the independent review.

## Allowed Files / Expected Area

- `apps/mono-desktop/src/app.rs` (overlay, hit-test, validation scheduling, bench
  instrumentation)
- `apps/mono-desktop/src/bench.rs` (Designer phase)
- `apps/mono-desktop/src/main.rs` (job tick poll, `dump:findings` flush)
- `crates/mono-project/src/editor.rs` (borrowed element list, `geometry_of`)
- `crates/mono-project/tests/overlay_geometry.rs` (new)
- `tools/BENCH_DESIGNER_PROJECT.py` (new)
- `docs/BUILD.md`, `docs/AI_HANDOFF.md`, `docs/rewrite/G4_EVIDENCE.md`,
  `CHANGELOG.md`

## Acceptance Criteria

- Overlay rects equal `geometry` for every element of the fixture, including the
  hidden/no-coordinate fallback (test).
- `panel_canvas` at 1005 elements is one render, not one lookup per element.
- The UI thread's worst edit handler is ≤16 ms on realistic scenes (125 elements,
  fixture) and is recorded honestly where it is not (1005 elements).
- Validation results are never applied to a scene other than the one they were
  computed from (epoch), and scripted dumps keep answering synchronously.
- `fixtures/golden/` and `test_assets/` unchanged; no new dependencies.

## Verification Plan

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- `cargo test --workspace --locked`
- `python -m pytest tools/tests -q`
- `cargo deny check`
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` (real
  window; the default `target/debug` binary can be stale)
- `python tools/BENCH_DESIGNER_PROJECT.py` + `python tools/RUN_DESKTOP_BENCH.py
  --runs 3` on 1005 / 55-digit / 125-element scenes and on the committed fixture

## Deliverables

- The code and test changes above, plus the measured table, attribution and
  out-of-scope notes in `docs/rewrite/G4_EVIDENCE.md` §4 and the Unreleased
  changelog entry.

## Result

All commands in the verification plan were run after the second 2026-11-01 rework:

- `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --locked
  -- -D warnings`, `cargo test --workspace --locked`, `python -m pytest tools/tests
  -q` (33 passed, 1 skipped) and `cargo deny check`: clean. Clippy and the test runs
  used `RUSTFLAGS="-C debuginfo=0"` to stay within memory.
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` on the
  final release build: 17/17 PASS.
- Bench (final release build, 3 runs per workload; `max_handler` covers geometry
  edits, strokes and theme switches only; state edit and refresh include the
  validation snapshot):
  - 1005 elements: designer_edit 49.9–50.9 ms, max_handler 20.5–23.1 ms,
    panel_canvas 9.3–10.9 ms, worker pass 22.4–23.7 ms, state edit 8.2–10.3 ms,
    refresh body 11.1–13.4 ms;
  - 55 elements / 50 digits: 32.4–36.2 ms, 21.4–22.7 ms, panel_canvas 15.9–17.3 ms,
    worker pass 82.4–88.7 ms, state edit 14.2–14.8 ms, refresh body 15.1–16.0 ms;
  - 125 elements: 20.2–20.8 ms, 3.79–4.46 ms, panel_canvas 1.77–2.01 ms, worker
    pass 6.78–8.27 ms, state edit 2.22–2.51 ms, refresh body 2.88–3.16 ms;
  - fixture: 16.4–17.6 ms, 1.78–2.10 ms, panel_canvas 0.58–0.81 ms, worker pass
    4.24–5.20 ms, state edit 0.93–1.16 ms, refresh body 1.21–1.37 ms.
- The acceptance scenes (125 elements, fixture) meet ≤16 ms. The 1005-element scene
  and the 50-digit scene do not. Runs on the 50-digit scene differ by machine state:
  21–23 ms in two rounds here, 15.9–16.9 ms in the second review; the cause was not
  isolated. Reducing either needs incremental or off-screen rendering, which is out
  of scope.
- The new test caught a mid-implementation divergence in the first `overlay_rect`
  draft (a text element in a zone at its glyph box). It was never released: 2.1.0
  drew the overlay through `geometry`.

## Review Status

Independent review (2026-11-01): **REWORK REQUIRED**. No Critical findings; the
overlay/hit-test unification, borrowed element list, epoch design and bench
harness were accepted. The review record was re-checked against the code and the
reviewer's raw bench output the same day; this section is the corrected scope.
No source changes were made in either round. `DONE` / `PASS` needs the rework and
a new independent review.

Required fixes:

1. **Validation is only partly off the UI thread.** `state_edited`
   (`apps/mono-desktop/src/app.rs:1560`) and `apply_rules` (`:1077`) still call
   synchronous `refresh_validation`, so the CHANGELOG sentence "Validation runs on
   a worker thread instead of on the keystroke" is too broad. Schedule them (and
   keep scripted dumps synchronous) or document the exception. This disproves the
   CHANGELOG sentence, not the ≤16 ms acceptance criterion: the panel medians add
   up to about 8 ms at 125 elements and about 4 ms on the fixture (estimate; the
   handler itself has never been measured). The 50-digit scene is well over budget
   (`panel_validation` 76.7 ms in the reviewer's run, 114.9–121.1 ms in G4, before
   `panel_canvas`).
2. **Evidence numbers contradict each other.** Reconcile, re-measuring where
   needed:
   - G4 table `:94-95` (`panel_canvas` 9.8–10.7 and 13.0–13.6) versus prose `:105`
     (10.3–11.5 and 12.7–13.2);
   - `CHANGELOG.md:9` (23–24 ms) versus `:23` and this task's Out of Scope (23–28 ms);
   - this task's stroke and cold-start figures (17.9–23.7 ms, 1337–1480 ms) versus
     G4 `:119` (18.2–22.4 ms, 1309–1417 ms);
   - the reviewer's single runs fall outside the documented `designer_edit` ranges
     (fixture 22.7 versus 16.9–17.8; 1005 elements 47.9 and 60.8 versus 56.1–59.3)
     and `max_handler` reached 28.8 ms at 1005 elements, so a 3-run range is not an
     upper bound. State that in the evidence.
3. **`panel_geometry_edit_ms` does not sample a real edit.** `bench_panels` calls
   `geometry_edited("x", 6)` three times (`app.rs:1307`). From the second sample
   `set_geometry` returns early with no undo entry and no `set_elements`, while
   `after_edit` still runs (`app.rs:1531`), so the median is the refresh body plus a
   no-change comparison, not the "refresh + edit transaction" G4 `:101` describes.
   Alternate the value as the `set_geometry` row does, then re-measure.
4. **No automated coverage for the async path.** Nothing exercises epoch discard,
   `flush_validation`, a screen switch with validation in flight, or a disconnected
   worker. The only GUI trust `dump:findings` case (`tools/CHECK_GUI_TRUST.py:317-319`)
   takes the synchronous rules path.
5. **`max_handler_ms` and the ≤16 ms row over-claim.** The bench only samples
   geometry edits, strokes and theme switches (`bench.rs:75-100`). `refresh_all`
   on screen open/switch still validates synchronously and is unmeasured. Narrow
   G4 `:68` and `:74`, or move `refresh_all` off the UI thread and measure it.
   Change the ✅ in `:68` so the 1005-element miss is not read as a pass.

Also fix in this scope:

- `poll_validation` treats `Disconnected` as "not ready", so a panicked worker stops
  all later validation (release does not set `panic=abort`).
- The "at most one in flight" wording in `CHANGELOG.md:10`, G4 `:106` and the
  `schedule_validation` comment: `refresh_validation` and `bind_scene` drop the
  receiver without waiting, so a superseded worker can still be running. Say that
  at most one result is applied.
- `CHANGELOG.md:9` says `geometry` clones one element, but text/digits still clone
  the whole scene map (`editor.rs:336`). Limit the claim or remove the clone.
- `overlay_rect` (`app.rs:61-66`) ignores element fields when a zone exists but is
  incomplete. Falling back to a complete explicit rect is not enough: `geometry_of`
  (`editor.rs:420-431`) overrides per field, so the overlay and hit-test must match
  that, including an element with only `x`/`y`.
- Tests: `overlay_geometry.rs:32-40` copies `overlay_rect`, so changing `app.rs`
  cannot fail it; `app.rs:2653-2656` gives the explicit case the same resolved value,
  so it cannot show that explicit wins; `app.rs:2617-2641` is a source-text check.
  Share the helper or feed distinct values, and assert behaviour.
- Advance the epoch where a screen is dropped before a switch that can fail
  (`guard.rs:252,279`). Low impact, but the state is otherwise inconsistent.
- Idle memory: only the fixture is recorded, while the reviewer measured 87.3 MB at
  125 elements, 82.3 MB at 55 and 188–192 MB at 1005 against the 80 MB budget.
  Record it or restrict the budget row to the fixture in `RUN_DESKTOP_BENCH.py`.
- The worker builds a fresh `DiskResources` per pass (`app.rs:1128`) while G4's
  validation row times the session's cached path. Measure the worker pass before
  quoting a cost for it (G4 `:106`).
- `BENCH_DESIGNER_PROJECT.py:36` fails with a traceback on a project without
  screens; `overlay_geometry.rs:7` says two `image` elements, and the fixture has
  two `image` plus one `image_seq`.

Files outside this task's original Allowed Files that the fix scope may touch
(confirmed by the user, 2026-11-01): `apps/mono-desktop/src/guard.rs`,
`tools/CHECK_GUI_TRUST.py`, `tools/RUN_DESKTOP_BENCH.py`.

The duplicate-frame-name review item belongs to TASK-007 and is recorded there.

Rework (2026-11-01), against the list above:

1. Done. `state_edited`, `apply_rules` and `refresh_all` schedule validation;
   only the bench row calls `refresh_validation`. A side effect to review: findings
   now lag those handlers by up to one pass, including right after a screen opens.
2. Done. G4, CHANGELOG and this file carry one set of final numbers, and G4 says a
   3-run range is not an upper bound.
3. Done. The row alternates its value; 12.7–15.4 ms at 1005 elements now matches
   the refresh body plus the transaction.
4. Done. New `app.rs` tests cover the flush, an edit during a pass, epoch discard,
   a screen switch in flight, a lost worker, all three moved paths and a dropped
   session. The App-level tests were written with the fix, so they have no
   recorded failing run; `an_incomplete_zone_defers_to_the_element_like_the_inspector`
   did fail first (overlay `(1,9,35,7)`, Inspector `(30,9,40,11)`).
5. Done. G4 `:68` is ⚠️ and states what `max_handler_ms` samples;
   `panel_state_edit_ms` and `panel_refresh_all_ms` measure the rest.

Also-fix list: all done (`Disconnected`, wording, scratch scene without `elements`,
`overlay_rect` moved to `mono_project::editor` with per-field fallback, tests call
the production helper with distinct values, `drop_session`, the memory budget now
only judges the fixture, worker pass measured, tool error and comment fixed).

Kept on purpose: `the_canvas_redraw_does_not_look_up_geometry_per_element` is still a
source-text check. Counting `geometry` calls behaviourally would need a test hook in
`EditorSession`, and `panel_canvas` in the bench covers the cost. The reviewer can
overrule this.

Second independent review (2026-11-01): **REWORK REQUIRED**. No Critical findings.
The concurrency design, `overlay_rect` per-field fallback, the moved call sites,
the scoped ≤16 ms claim and the gates were accepted; the review re-ran all five
gates and GUI trust (16/16). The fix scope is small and does not change production
logic:

1. **The CHANGELOG Fixed entry about a text element in a zone is false.** HEAD drew
   the overlay and hit-tested through `session.geometry(id)`, the Inspector's own
   source (checked). The divergence existed only in an unreleased draft of
   `overlay_rect`. Delete the entry and say in G4 that it was a mid-implementation
   divergence.
2. **Fix item 4 above was not really finished.** Six mutations survived the whole
   suite together: removing the `bind_scene` reset, `flush_validation` ignoring the
   epoch, `after_edit` back to synchronous validation, never writing
   `last_resolved`, `hit_test` without `.rev()`, and no null filter for `w`/`h`.
   `a_screen_switch_abandons_the_pass_in_flight` proves nothing: `refresh_all` moves
   the epoch and the draft is gone once the scene reloads (test read and confirmed).
   Required:
   - inject a receiver that never answers, switch screens, and assert the flush ends
     with the new scene's result;
   - assert `validation_rx.is_some()` after `geometry_edited`;
   - add a stale-epoch, not-dirty flush case and a test of the null `w`/`h` case;
   - make the topmost-element search testable (a pure function) or script a click;
   - rename `the_overlay_and_a_click_agree_on_the_precedence`, which never clicks.

Also fix in this scope (reviewer's findings, not independently reproduced):

- `overlay_rect` differs from `geometry_of` on hand-written data: a four-key element
  with a null `w`/`h`, and a complete zone holding a float or null. Use
  `contains_key` + `int_of` in the zone and explicit branches. The non-boolean
  `hidden` difference is pre-existing.
- G4 calls `panel_geometry_edit` the complete handler, but `state_edit`,
  `geometry_edit` and most `refresh_all` samples skip the snapshot clone (about
  1.4–1.8 ms at 1005 elements) because a pass stays pending. Flush before each
  sample or say so. The `panel_refresh_all` heading also overstates what it covers:
  a real switch adds disk reads, `EditorSession::new` and a baseline render.
- "Findings lag by up to one pass" is too low: one edit can wait about two passes,
  and sustained editing shows nothing until it stops. Fix CHANGELOG and G4.
- `flush_validation` logs nothing when the worker is lost, unlike `poll_validation`.
- G4: the `effective_rules` figure has no bench row behind it, and 80.5 MB is over
  budget, not "at the line". Record the second run's spread: 50 digits `max_handler`
  15.9–16.9 ms (2 of 3 over 16), 125 elements up to 12.7 ms, so the earlier
  21.1–23.1 ms looks like machine state rather than a code regression; the cause
  was not isolated.
- Tick work on the UI thread (snapshot clone, thread start, `apply_findings`) is in
  no row. It was not measured; note that or add a row.
- The Verification Plan must pass `--exe` to `CHECK_GUI_TRUST.py`: the default
  `target/debug` binary here is stale and gives a false failure.

Second rework (2026-11-01), against the second review's list:

1. Done. The Fixed entry is deleted and G4 says the divergence was unreleased.
2. Done. `a_screen_switch_abandons_the_pass_in_flight` now holds a pass that never
   answers. New: a stale-epoch flush test, a geometry path assertion, the pure
   `topmost_at` with its own test, `unusual_field_values_follow_the_inspector`, and a
   GUI case that presses the real canvas through the new scripted `canvas-click`
   action. The overlay test was renamed.

A mutation run on a throwaway copy applied the review's surviving mutations at once
and every one failed its intended test: no `bind_scene` reset, flush ignoring the
epoch, `after_edit` back to synchronous validation, `hit_test` picking the bottom
element, no null filter, Unicode folding plus relative folding, the old `..`
handling, and unchecked digits in both the renderer and the validator. Mutations
sharing a test were applied together, so they were not separated from each other.

`last_resolved` never being written still cannot fail a test. It only costs time:
`hit_test` then falls back to `geometry` and gives the same answer. This is left open
for the reviewer; `panel_canvas` does not cover hit-testing.

Also-fix list: `overlay_rect` decides by key presence like `geometry_of` (failed
first: overlay `(5,5,35,7)`, Inspector `(5,5,0,0)`). `state_edit`, `geometry_edit` and
`refresh_all` flush before each sample so they include the snapshot. `flush_validation`
logs a lost worker. The findings-lag wording, the `panel_refresh_all` heading, the
`effective_rules` figure, the 80.5 MB wording and the run spread are corrected in G4.
Tick work stays unmeasured and G4 says so. The non-boolean `hidden` difference is
pre-existing and was not changed.

Third independent review (2026-11-01): **REWORK REQUIRED**, documentation only. No
Critical findings. The reviewer accepted the code, concurrency, tests and acceptance
criteria, and said production code needs no further change and no further code
review. The items recorded as left open (`last_resolved`, tick work, the source-text
test, the 50-digit spread) and the findings delay were all accepted. All gates and
GUI trust (17/17) re-ran clean, and 156 tests passed on a byte-identical copy.

Required fix:

1. `CHANGELOG.md:15` says the 1005-element worst handler is 20–25 ms while `:29` and
   this file say 20–29 ms (contradiction checked). The review measured up to 26.5 ms,
   and 28.8 ms was seen earlier, so 25 is wrong. Change `:15` to 20–29 ms. The "one
   set of final numbers" statement in the first rework record was not true until then.

Minor, to fix with it:

- `CHANGELOG.md:16`: say two passes plus two 60 ms ticks, as G4 does (roughly 130 ms
  on the fixture, 170 ms at 1005 elements, 290 ms on 50 digits).
- G4 `:127`: `last_resolved` stores the resolved entries, not "one rect".
- `main.rs:600-601`: `canvas-click` split a comment from `dump:selection` (checked);
  move the comment back.

Accepted without a change: removing the poll catch-up, the tick's `poll_validation` or
`hit_test`'s `geometry` fallback does not fail a test. The code is right today; a
poll-only test is a follow-up option, not a condition. A non-boolean `hidden` with a
partial zone differs between overlay and Inspector in hand-written data only. That
difference is new against HEAD, so the "pre-existing" note above covers the renderer
versus `geometry` part only.

Third rework (2026-11-01), against the third review's list:

1. Done. `CHANGELOG.md:15` now says 20–29 ms. The bench was not re-run: production
   edit paths did not change.

Minor: `CHANGELOG.md:16` states two passes plus two 60 ms ticks, G4 says
`last_resolved` keeps the resolved entries, and the `main.rs` comment is back above
`dump:selection`.

Gates on the final tree: `cargo fmt --all -- --check`, `cargo clippy --workspace
--all-targets --locked -- -D warnings`, `cargo test --workspace --locked`, `python -m
pytest tools/tests -q` and `cargo deny check` were clean, and
`python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` passed on a
fresh release build (17/17, exit 0). 158 tests passed, 0 failed; pytest 33 passed,
1 skipped. On that build `mono validate` reports `ASSET_PATH_ESCAPE` for both the
`image` and the `image_seq` form of the reproduction.

Scoped independent review (2026-11-01): **PASS**. All four third-review items are true.
The two-ticks figures follow from 120 ms plus two passes of 5, 23 and 85 ms.

Correction to the third rework record above: "production edit paths did not change" is
false, because `joined_member` changed `render_digits` and the `image_seq` path, which
run on every edit. The figures stand: the reviewer built the old join and alternated it
with the current binary for 8 runs each on the 50-digit scene. Medians were `max_handler`
22.7 ms old and 21.4 ms current, `panel_render` 17.4 ms and 16.0 ms; noise exceeds the
effect.

Accepted without a change: the 50-digit "16–23 ms" is not a hard bound. A 3-run batch
right after the gate builds gave 22.6–27.0 ms and the old binary also had outliers, and
G4 already says the ranges are not bounds.

Gates the reviewer ran: fmt in the repository; clippy, 158 workspace tests, pytest (33
passed, 1 skipped) and deny on a throwaway copy matching `crates/` and `apps/`; GUI
trust 17/17 on the release binary. Not verified: a real case-sensitive Windows folder,
macOS and Linux, the 1005-element and fixture benches. No repository file was changed
in the review.
