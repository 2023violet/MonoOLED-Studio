# TASK-018 — Designer Edit Hot Path

Status: VERIFY (review rework M1/R1 awaits a confirmation review)
Review Status: PASS WITH MINOR NOTES (independent review 2026-11-09); M1 fixed after the review

## Goal

Remove the avoidable work in a Designer edit on large or glyph-heavy scenes, so that the UI-thread handler approaches the 16 ms budget. Render output must stay byte-identical. Do not ship, tag or push.

## Background

2.4.0 shipped on 2026-11-03. `docs/rewrite/G4_EVIDENCE.md` §4 still records a missed 16 ms handler budget on the generated scenes: 22–27 ms on 50 digits and 20–24 ms on 1005 elements.

The user approved this plan on 2026-11-08 (plan "Next optimization round", approved through plan mode), with two choices:

- the cache is **per render only**: a file is still read and hashed at least once per render;
- the correctness follow-ups are a separate TASK-019.

## Current Problem

A read-only exploration, confirmed in the code, found four sources of avoidable work.

1. **Per-character and per-element resource lookups.**
   - `render_digits` calls `Ctx::bitmap` once per character (`crates/mono-core/src/render.rs`).
   - `Ctx::bitmap` never consults its per-render `cache`.
   - The session's `DiskResources` is not frozen, so every lookup does `std::fs::read` plus SHA-256 (`crates/mono-project/src/resources.rs`).
   - `render_text` and `render_bitmap_text` call `mode_font` and `font_pack` once per element. `font_pack` fingerprints the whole pack (`fontpack_io.rs` `fontpack_fingerprint`) on every call.
2. **Scratch renders.** `EditorSession::geometry` renders a one-element scene for `digits`, `text` and `bitmap_text` elements without a full rect. It is called from `geometry_changes` (inside the undo transaction) and from `refresh_inspector`.
3. **Undo transaction copies.** `batch_set_geometry` clones the elements array three times and deep-compares it once per edit.
4. **Navigator copies.** `refresh_navigator` deep-clones the whole elements array to iterate it, and rebuilds every model after geometry-only edits.

## Evidence

- `crates/mono-core/tests/render_resource_lookups.rs`, written before any change, uses a counting `Resources` double:
  - `a_digits_string_reads_each_glyph_file_once` fails: ten glyphs over two files produced 8 lookups for `1.png` and 2 for `2.png`.
  - `a_font_header_and_a_font_pack_are_read_once_per_render` fails: two `text` elements looked the header up twice.
  - `every_render_looks_its_files_up_again` passes and pins the per-render boundary the user chose.
- Before and after benchmarks are recorded in Result.

## Required Changes

1. A per-render memo in `Ctx` for `bitmap`, `mode_font` and `font_pack`, keyed by the resolved path. `used_files`, `used_assets` and `resolved` keep their entries and order.
2. `geometry_changes` and `refresh_inspector` use the rect the latest render resolved when it is current for the session, falling back to `geometry()`. Overlay rect and Inspector geometry stay equal (`crates/mono-project/tests/overlay_geometry.rs`, plus a digits/text case).
3. `batch_set_geometry` changes the targeted elements in place and records per-element before/after. Undo, redo, coalescing and `is_dirty()` stay unchanged.
4. `refresh_navigator` no longer clones the elements array. Geometry-only edits skip the element-list rebuild.
5. A `dump:mem` scripted command, plus a fixture bench with the software renderer, to tell app heap from renderer/driver memory. No memory change unless that points at app code.
6. Re-measure the fixture, 1005-element and 50-digit scenes, and run `mono bench` once. Update G4 §4 and `CHANGELOG.md` `Unreleased`.

## Out of Scope

- Keeping decoded assets cached across renders (declined by the user).
- An incremental framebuffer.
- The stroke, cold-start, evidence-export and encode budgets.
- Any change to `fixtures/golden/` or `test_assets/`.
- A release, tag, push or PR.

## Protected Existing Work

- The 2.4.0 release and its records.
- `fixtures/golden/` and `test_assets/`.
- The content-hash guarantee in `resources.rs` (a changed file shows on the next render).

## Constraints

- `AGENTS.md` gates. GUI runs use temporary configuration directories and fixture copies.
- No push, tag, rebase, stash or clean without explicit instruction.
- The implementer stops at VERIFY.

## Allowed Files / Expected Area

- `crates/mono-core/src/render.rs` and its tests;
- `crates/mono-project/src/editor.rs` and its tests;
- `apps/mono-desktop/src/app.rs`, `main.rs` and `bench.rs`;
- `docs/rewrite/G4_EVIDENCE.md` and `CHANGELOG.md`;
- `.ai/tasks/TASK-018.md` and `.ai/CURRENT_STATE.md`.

## Acceptance Criteria

1. The lookup tests pass, and the golden, corpus and Automation replay tests pass unchanged.
2. Undo, redo and dirty behaviour are unchanged, with tests.
3. Before and after figures for the three scenes are recorded, and misses stay misses.
4. The five gates and `CHECK_GUI_TRUST.py` (release, temporary configuration directories) pass.
5. `git diff origin/main -- fixtures/golden test_assets` is empty.

## Verification Plan

- Release build of the base: `RUN_DESKTOP_BENCH.py --runs 3` on the fixture and on the `BENCH_DESIGNER_PROJECT.py` 1005-element and 50-digit projects.
- The same after each change group.
- The five gates, `CHECK_GUI_TRUST.py`, the golden diff.

## Deliverables

- Commits for TASK-018 (branch facts live in Git).
- This record, `.ai/CURRENT_STATE.md`, G4 §4 and `CHANGELOG.md`.

## Result

All results come from commands actually run on Windows 10, on `claude/perf-task-018`, which branches from `origin/main` 22fda94 (2.4.0).

### Failure evidence

`crates/mono-core/tests/render_resource_lookups.rs`, written before any change, failed on the base:

- digits: `1.png` was looked up 8 times and `2.png` twice for 10 glyphs;
- text: a shared header was looked up twice.

### Changes, by commit

1. `61a6801`: `Ctx` memoises `bitmap`, `mode_font` and `font_pack` by path for one render. `every_render_looks_its_files_up_again` pins that the next render looks the files up again.
2. `c95f3c5`:
   - `editable_of` replaces the scratch render in `geometry_changes`;
   - `batch_set_geometry` changes elements in place and records `Command::Patch`;
   - `geometry_from_frame` is added.
   - Tests: `crates/mono-project/tests/editor_patch_undo.rs`, including frame geometry equal to `geometry()` for every fixture element (a zoned element, a digits element, an `image_seq` and images).
3. `ce27a34`:
   - the Inspector uses the fresh frame's geometry, including the two drag paths;
   - Inspector X/Y/W/H edits and arrow nudges skip the Navigator;
   - the Navigator no longer clones the element list.
4. A later commit adds the `dump:mem` self-check, with `history_len` / `entries` accessors.

### Measurement

The base and the change were measured on the same machine on the same day: `python tools/RUN_DESKTOP_BENCH.py --exe <copy> --runs 3` on the fixture and on `BENCH_DESIGNER_PROJECT.py --elements 1000` and `--elements 0 --digits 50`.

| Scene | Metric | Base | After |
|---|---|---|---|
| 50 digits | `max_handler` | 15.0–20.5 ms | 4.54–5.89 ms |
| 50 digits | render | 11.1–11.6 ms | 3.17–3.60 ms |
| 1005 elements | `max_handler` | 14.3–16.5 ms | 7.95–9.02 ms |
| 1005 elements | undo transaction | 2.97–4.41 ms | 0.01 ms |
| 1005 elements | idle memory | 196 MB | 91–97 MB |

- Fixture memory, measured alternately: base 74.5–80.1 MB, after 77.0–79.2 MB (unchanged within noise, close to the 80 MB budget).
- `dump:mem` on the fixture at idle: 5 elements, 4 cached bitmaps, 1 font, empty histories.
- The software-renderer comparison could not be completed: `RUN_DESKTOP_BENCH.py` with `SLINT_BACKEND=winit-software` never finished ("bench did not finish").
- `mono bench` ×3 on each side: no change apart from one disk outlier on each side.
- The full tables are in `docs/rewrite/G4_EVIDENCE.md` §4 "2026-11-08" and in `CHANGELOG.md` `Unreleased`.

### Gates

- `cargo fmt --all -- --check`: clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: clean.
- `cargo test --workspace --locked --no-fail-fast`: 30 groups, 322 passed, 0 failed. The golden corpus and Automation replay tests are unchanged and pass.
- `python -m pytest tools/tests -q`: 36 passed, 1 skipped (re-run after the docs edit).
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` with `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` in a temporary directory: 17 of 17 PASS.
- `git diff origin/main -- fixtures/golden test_assets`: empty.
- **`cargo deny check`: advisories FAILED.**
  - The cause is RUSTSEC-2026-0441 (`pin-utils` unmaintained, upstream archived 2026-10-01). It arrives only via Slint 1.18.1 (`spin_on` under `i-slint-renderer-skia`, `slint-build`, `slint-macros`), and no safe upgrade exists.
  - `Cargo.lock` is identical to `origin/main`, so `main` fails this gate too. It is not caused by this TASK.
  - `deny.toml` already ignores four unmaintained transitive advisories under the same rationale. Adding this one was a dependency-policy decision left to the user. On 2026-11-08 the user approved accepting it; `deny.toml` now ignores RUSTSEC-2026-0441 with that rationale, and `cargo deny check` reports "advisories ok, bans ok, licenses ok, sources ok".

### Not verified

- macOS and Linux (they need three-platform CI, which needs a push).
- The software-renderer memory comparison, as above.

## Review Status

**PASS WITH MINOR NOTES** (independent review 2026-11-09, fresh context, read-only on source).

- Gates re-run by the reviewer: fmt and clippy clean; tests 327 passed, 0 failed; pytest 36 passed, 1 skipped; `cargo deny check` ok; golden diff empty; `CHECK_GUI_TRUST.py` 17 of 17 PASS with temporary configuration directories.
- Benchmarks reproduced on release builds of base and change, alternated, `RUN_DESKTOP_BENCH.py --runs 3`: 50 digits `max_handler` 13.96–16.83 → 4.73–6.13 ms; 1005 elements `max_handler` 11.47–17.45 → 7.98–10.24 ms; 1005 elements idle memory 189–202 → 92–99 MB; 50 digits idle memory 82–87 → 71–74 MB. The fixture's idle memory exceeded 80 MB on both sides in several runs (pre-existing, not caused by this TASK).
- Compatibility: no file-format, `Cargo.lock`, CLI-output, golden or Automation API 1.3.0 change; patch-release safe.

Findings:

- (Minor, M1) `Command::Patch` restored elements by list index without checking the id. A change made without an undo step (an open Automation transaction: `changed()` records nothing inside one) can shift the list; undo then wrote the element into a neighbour's slot, duplicating one id and losing another. **Fixed after the review:** failure evidence `undo_follows_the_element_id_when_the_list_moved_underneath` (`crates/mono-project/tests/editor_patch_undo.rs`) failed with `["c", "b", "b", "z"]`; `apply` now checks the recorded index against the element id, looks the element up by id when the list moved, and skips a vanished element. Gates after the fix: fmt and clippy clean, tests 328 passed, 0 failed, pytest 36 passed and 1 skipped, deny ok, golden diff empty. A confirmation review of the fix is pending.
- (Minor, R1) The confirmation review of the M1 fix (2026-11-09) returned REWORK REQUIRED: the coalescing path in `batch_set_geometry` still merged entries by index. With the list shifted mid-drag, a multi-select drag undid to `b.x = 11` instead of 10 and redid to `["c", "a", "a", "z"]`, and a single drag undid to its middle value. **Fixed:** failure evidence `a_coalesced_drag_follows_the_element_id_when_the_list_moves_mid_drag` failed with 11 against 10; entries now merge by element id and take the element's current index, and undo walks a step's entries in reverse. Gates after the fix: fmt and clippy clean, tests 329 passed, 0 failed, pytest 36 passed and 1 skipped, deny ok, golden diff empty. A second confirmation review is pending.
- (Minor, M2, accepted) An Inspector X/Y/W/H edit on an element that cannot render (for example a missing font header) used to be refused by the scratch render and now succeeds; `geometry()` still reports the render error, and `batch_move`, align, distribute, snap and Automation are unchanged. Accepted as the better behaviour; no test pins it yet.
- (Minor, M3, follow-up) The Review panel's summary line still reports 100% changed when there is no baseline; this TASK and TASK-019 fixed only the drawer.
- (Minor, M4, follow-up) Coverage: the frame-geometry equality test meets no unzoned text without a full rect, no `bitmap_text` and no hidden element (the reviewer's probe found the code correct for them), and no desktop test pins that `refresh_inspector` uses the frame only when `canvas_frame_fresh` is set.
- (Nit) Two doc comments sat on the wrong functions (`app.rs` note-row test, `editor.rs` `geometry_of`). Fixed with M1. The Deliverables line held push state; reworded.
- (Nit) `dump:mem` ships in release builds like the other `dump:*` self-check commands: it only prints counts and cannot write.
