# TASK-004 — Experience Audit Closeout: One Truth Per Signal

Status: VERIFY
Review Status: three independent slices run (see Review Status below)

## Goal

Remove the "says one thing, does another" gaps found by a real-desktop experience
audit of the released 2.0.3 app: one owner for the keyboard, the dirty marker, the
settings value, the validation count and the export decision, plus the missing UI
mechanisms (Escape, scroll-to-selection, empty state, layout floor).

## Background

Two audit rounds drove the desktop app for real (temp `APPDATA` / `LOCALAPPDATA` /
`XDG_CONFIG_HOME`, operations on a copy of `test_assets`), first blind then
task-scenario, and recorded observed facts separately from technical causes. The
findings were grouped into 12 work packages in the approved plan
`windy-wave-robin.md`; the user chose the full 12 packages and both contract
changes (see ADR-006).

## Current Problem and Failure Evidence

Recorded as root causes in the plan, each reproduced before the fix:

- R1 `Ctrl+S` worked only sometimes: five overlays were siblings of the single
  shortcut `FocusScope`, so a modal owned the keyboard and closing one destroyed
  the focused element (Slint drops the key with no focus owner).
- R2 Preferences → Keyboard rendered eight empty rows and edits never reached the
  file: shortcuts are stored as flat dotted keys but read through a nested path.
- R3 The title `•` lied: `dirty` was set by every `apply()` including undo/redo,
  and the unsaved prompt merged Pixel/Font state that is not part of the project.
- R4/R5 The C-header writers bypassed the release gate (desktop, CLI, Automation),
  and the blocked-report path pointed at a directory deleted right after.
- R6/R7 The panel and batch validation used different state sets and rule sets;
  one out-of-bounds element reported twice.
- R8–R12 Font Lab collapsed its right column at the minimum width, no overlay
  answered Escape or a backdrop click, lists never scrolled to the selection, an
  empty window still looked like an editor, and menus/status carried stale state.

## Required Changes

1. Shared release gate in `mono-project`: `preflight`, `BlockedExport`,
   `write_validation_report`, `export_scene_with_report`; handoff report survives
   staging as `<zip>.validation.md`; findings deduplicated per element+message.
2. All three producers honour the gate: desktop C-header export, `mono c-header`,
   Automation `export.c_header`; the desktop shows a blocked dialog that can jump
   to each element and copy the report path.
3. Keyboard routing: overlays live inside the shortcut `FocusScope`; `Scrim` owns
   Escape and backdrop dismissal; chords and bare tool keys are inert behind a
   modal; focus returns when the last modal closes.
4. Preferences: flat shortcut reads with nested fallback, two-way text editing,
   debounced flush on section change / close / Enter / exit, conflict rejection.
5. Dirty truth: `EditorSession` compares against a saved snapshot
   (`is_dirty` / `mark_clean` / `mark_dirty`), the title dot follows the scene
   only, and the prompt names the documents that actually changed.
6. Viewing a screen no longer writes `project.oled.json`.
7. Usability: batch validation shares the export state set and design rules,
   `AutoList` scrolls to the selection, Font Lab column floors plus an elided
   caption, empty state with New/Open/Continue, explicit "no document" errors.
8. Polish: tooltips rendered, View-menu check marks, About repository and
   documentation links, status reset per project.
9. Tests: `editor_dirty`, `export_gate` (project + automation), `findings`,
   desktop prefs/guard unit tests, `ui_source_tests` overlay invariants, and
   `tools/CHECK_GUI_TRUST.py` for the seams only a real window can prove.
10. Docs: CHANGELOG Unreleased, `docs/AUTOMATION_API_V1.md` release gate,
    `docs/USER_GUIDE_CN.md` / `_EN.md` behaviour notes, `tools/README.md` index.

## Out of Scope

No export/validation architecture rewrite beyond `preflight` and `BlockedExport`;
no change to `fixtures/golden/**` or to `matrix_report` / `validation_markdown`
byte formats; no new dependencies; no theme or colour redesign, and Pixel Studio
versus Font Lab visual language (black-background white dots versus white
background black shapes) is deliberately left for a separate design round.

## Protected Existing Work

Everything already in the tree before this task, including `test_assets` fixtures
and the user's released 2.0.3 tags. Audit runs never touched the repository
fixtures: they copied them into a temp directory.

## Constraints

- Gates from `AGENTS.md`: `cargo fmt --all -- --check`,
  `cargo clippy --workspace --all-targets --locked -- -D warnings`,
  `cargo test --workspace --locked`, `python -m pytest tools/tests -q`,
  `cargo deny check`.
- No `unwrap` / `expect` / `panic` / `unsafe` in production code.
- Successful export output stays byte-identical to 2.0.3; blocked paths reuse the
  existing error classes.
- Commits, tags, pushes and releases require explicit user authorization and were
  not performed here.

## Allowed Files / Expected Area

`crates/mono-project/src/{editor.rs,export.rs}`, `crates/mono-automation/src/*`,
`apps/mono-cli/src/main.rs`, `apps/mono-desktop/{src,ui,i18n}`, the four new test
files under `crates/*/tests/`, `tools/CHECK_GUI_TRUST.py`, `tools/README.md`,
`CHANGELOG.md`, `docs/AUTOMATION_API_V1.md`, `docs/USER_GUIDE_CN.md`,
`docs/USER_GUIDE_EN.md`, `Cargo.lock` (single advisory patch), and `.ai/`.

## Acceptance Criteria

1. A blocking scene writes no file through any of the three producers, and each
   names a report path that still exists afterwards.
2. Every overlay closes with one Escape and with a backdrop click, and the next
   bare key reaches the app afterwards.
3. Preferences → Keyboard shows the configured chord and a committed edit lands
   in the preferences file; a conflicting chord is refused visibly.
4. Undo back to the saved state clears the title `•`; the unsaved prompt names the
   edited documents.
5. Opening another screen leaves the manifest bytes untouched until an explicit save.
6. Batch validation and the panel agree on the state set and the design rules.
7. Font Lab keeps three usable columns at the minimum window size.
8. An empty window offers an action instead of an inert editor, and design
   commands without a document report that.
9. All five gates pass, and `python tools/CHECK_GUI_TRUST.py` reports 6 PASS.

## Verification Plan

- The five gates above, run after the last edit.
- `python tools/CHECK_GUI_TRUST.py --keep` (real window, temp config, fixture copy).
- `cargo run -p mono-cli -- validate --project test_assets/projects/curing_lite/project.oled.json`
  plus a `c-header` run against a temp copy with an out-of-bounds placeholder
  (expected: `FAIL: export blocked; see …validation.md`, exit 2, no header file).
- Headless screenshots of the empty state, About, Font Lab at 1166x800 and the
  blocked dialog.

## Result

All 12 work packages implemented. The figures below are from the run after the
rework in the next section, where acceptance criteria 1–9 were re-verified.

- `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --locked -- -D warnings`:
  clean after the final edit.
- `cargo test --workspace --locked`: 24 result blocks, 0 failures, including
  `golden_handoff`, `golden_projects`, `golden_scenes`, `golden_fonts`,
  `golden_automation`, `safety` and the new `editor_dirty` / `export_gate` /
  `findings` suites.
- `python -m pytest tools/tests -q`: 21 passed, 1 skipped.
- `cargo deny check`: advisories/bans/licenses/sources ok.
- `python tools/CHECK_GUI_TRUST.py`: 6 PASS (modal Escape and focus return,
  settings render and flush, dirty across undo, blocked C-header with report,
  Font Lab at 1166x800, and the navigator scrolling to an off-screen selection).
- CLI gate smoke: `FAIL: export blocked; see …frame.validation.md`, exit 2, no
  header written, report lists one `OUT_OF_BOUNDS` plus one `DRAFT_PLACEHOLDER`.

Two notes for the reviewer.

1. `cargo deny` failed on RUSTSEC-2026-0414 (`pulldown-cmark` 0.13.4, reached
   through Slint's markdown support) after the advisory database was refreshed;
   it is unrelated to this task's code. It was cleared with the patch-level
   `cargo update -p pulldown-cmark --precise 0.13.5` (2-line `Cargo.lock`) rather
   than an ignore entry, and recorded under Security in the CHANGELOG.
2. Slint 1.18.1 cannot two-way-bind `MenuItem.checked`: the framework flips it on
   activation and `MenuBar` internals are unreachable from the enclosing
   component. The View menu therefore renders its check mark from `Shell` state
   inside the title, which stays truthful; this is a library limitation, not a
   shortcut.

## Review Findings And Rework

Two independent read-only reviews (agent reviewers, 2026-10-30) found real
defects. Each claim below was re-checked against the source before acting.

Fixed in this rework:

1. A blocked `export_scene` still created `reference/` and `golden/` before the
   gate, so "writes nothing" was false. Directory creation moved after the gate;
   pinned by `blocked_export_leaves_no_directories_behind`.
2. The desktop's export / handoff / thumbnail jobs ran `preflight` and then
   `export_scene`, which validated the whole state set again — every successful
   export paid for two full matrix validations. The eager preflight is gone: the
   job runs once and, only when the gate refuses it, collects the findings for
   the dialog (`blocked_after_failure`).
3. The thumbnail wall wrote `.oled/validation_report.md` on success too, sharing
   the path a blocked C-header write uses. The report is now written only when
   the gate refuses something, so its presence means something.
4. `EditorSession::is_dirty` deep-cloned the whole scene twice per refresh, on a
   path that runs every drag frame. It now compares in place.
5. **WP8 did not work at all, and the earlier "verified" note was wrong.** The
   verification read the selection index, not the pixels. Two separate causes:
   - In Slint 1.18 a component that *inherits* `ListView` lays its delegates out
     outside the flickable viewport: every row stacks at one offset. Forwarding
     `@children` into a `ListView` is rejected outright ("a ListView can just
     have a single 'for' as children"). `AutoList` was therefore never a list at
     all; the navigator's asset and font-pack lists were broken by it too.
   - A `changed` handler on a bound private property only runs while something
     reads that property (Slint evaluates lazily), so even the corrected
     component never fired. **[Corrected in the TASK-005 review: this diagnosis
     was wrong.]** `ChangeTracker::init` evaluates eagerly in 1.18.1
     (`i-slint-core-1.18.1/properties/change_tracker.rs:188-209`), and
     `MainWindow.overlay-open` has no reader outside its own `changed` handler
     yet reliably restores focus after a modal closes. The `visible` mirror read
     stayed in place because the feature was already working with it and the
     actual cause of the original failure was never isolated; it is not a rule
     the next round should reproduce.
   The list is now a plain `ListView` with an id, and the owning component
   installs the scroll from a `changed` handler on a mirror property that its
   `visible` binding reads. `tools/CHECK_GUI_TRUST.py::check_scroll_to_selection`
   proves it on pixels: two adjacent off-screen selections must render
   differently, which is only true if the viewport moved. `no_list_is_a_subclassed_listview`
   pins the Slint lesson in CI.
6. Doc overstatements corrected: the gate covers the *scene* exporters, not every
   producer; a blocked export now really writes nothing; the API doc no longer
   names an unreleased version.

Found, documented, deliberately not changed:

- The Output Workbench (`workbench.rs`, source `scene`) and Automation
  `export.bitmap_data` (default source `current_scene`) can render the live scene
  into a file without the gate. Gating them changes API 1.3 behaviour, which
  ADR-005/006 reserve for an explicit decision; the CHANGELOG, `AI_HANDOFF` §5.5
  and the `preflight` doc comment now say so instead of claiming full coverage.
- `mono batch-validate` defaults to `boundaries` while the desktop batch uses the
  representative set. The CLI default is user-selectable and pre-dates this task.
- Choosing an output profile in Pixel Studio writes `project.oled.json` without
  dirty tracking (pre-existing; outside ADR-006's "viewing" case).
- The C-header writers preflight with a frozen resource cache and then render
  through the session's own cache; an asset changed in between is not re-checked.
  Accepted: both happen inside one user action.
- A blocked handoff leaves a previously built ZIP in place; nothing overwrites it.

## Review Status

Covered by the first of three independent review slices dispatched for the
2026-10-30 round (the two rounds share one working tree, so TASK-004 and
TASK-005 were reviewed together). Six Important findings came back.

- Four were accepted and fixed in the same slice.
- One was refused after reading the code: "cancelling a rename still prints a
  success status" is false, because `finish_prompt` refreshes only on `Ok`. The
  finding was checked against `apps/mono-desktop/src/main.rs` before being set
  aside rather than "fixed".
- One stayed open through that round — backdrop dismissal was wired but never
  behaviourally proved. The 2.1.0 slice closed it with
  `tools/tests/test_docs_match_code.py::test_every_dialog_really_closes_on_the_backdrop`:
  each of the eight `inherits Scrim` components handles `dismissed`, `Scrim`'s
  own TouchArea emits it, and nothing sets `dismissable: false`.

The fixes shipped with `2.1.0`, split across code, checks and docs commits.
Status stays `VERIFY`: `AGENTS.md` reserves `DONE` / `PASS` for an independent
reviewer, and this record does not award it.
