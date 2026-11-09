# TASK-018 — Designer Edit Hot Path

Status: APPROVED
Review Status: PENDING (no independent review yet)

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

- Commits on `claude/perf-task-018` (not pushed).
- This record, `.ai/CURRENT_STATE.md`, G4 §4 and `CHANGELOG.md`.

## Result

(pending)
