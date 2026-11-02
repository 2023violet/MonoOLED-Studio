# TASK-013 — Stress Findings: Gate Short-Circuit, Bounded Export Memory, Member Containment

> Renumbered from TASK-007 on 2026-11-02 by TASK-014, when this line of work was integrated with `origin/main`, whose own TASK-004 to TASK-009 already used those numbers. The body below is unchanged: where it says TASK-004, TASK-005, TASK-006 or TASK-007 it means TASK-010, TASK-011, TASK-012 or TASK-013.

Status: DONE
Review Status: PASS (confirmation review of the fourth rework, 2026-11-02)

## Goal

Fix the three defects the 2026-10-31 stress campaign reported, without changing
the export contract, the golden corpus or the release-gate semantics:

1. a blocked export no longer evaluates the whole state matrix before refusing;
2. an export no longer keeps every frame's contract in memory (or aborts at
   multi-GB private usage on a large matrix);
3. scene members can no longer read outside the project root.

## Background

The user asked for a brute-force stress pass over the CLI, the Automation API and
the GUI (2026-10-31), then authorised fixing every real defect it found and
re-running the same stress suite. The campaign stayed read-only; this task is
the fix round it authorised. Repo rule: a behaviour change starts from failure
evidence, recorded below before any source edit.

## Current Problem and Failure Evidence

Measured with the pre-fix release binary on the stress projects under
`target/stress/` (throwaway copies; `test_assets/` untouched):

- **Blocked export evaluates all 560 representative states.** `valid-1005`
  (1005 elements, 1000 out-of-bounds battery clones) `export --states all`
  returned `export blocked` after **464.3 s**, peak private **814 MB**. Every
  state re-rendered 1001 image sequences before the gate was consulted.
- **The export writer holds the whole matrix.** `p-10000` (10 000 elements,
  560 states) `export --states all` **aborted** with exit 3221226505
  (`memory allocation of 3145728 bytes failed`) after 30.7 s at a measured
  **1 951.6 MB** peak private; the same scene + `handoff` aborted around 93 s in
  the campaign. The per-state `frames` map, the contract `Value`, its serialised
  string and the finding map were all live at once.
- **Members escape the project root.** `validate` on the fuzz scene reported
  `NON_BINARY_ASSET … Invalid PNG signature` for
  `"asset": "../../../AGENTS.md"`, i.e. it read a file outside the project; the
  campaign also decoded `../outside.png`. `AGENTS.md` requires project member
  paths to resolve inside the project root.

## Required Changes

1. **Gate short-circuit.** `preflight` and `export_scene_with_report` validate
   states in matrix order and stop at the first state with a blocking finding.
   The blocked report says how many frames were checked out of the matrix
   (`stopped at the first blocking frame`). Clean scenes are still validated in
   full before any artefact is written. `batch-validate` still evaluates the
   whole matrix on purpose — that is the command's contract.
2. **Bounded export memory.** `ui_contract.json` and `UI_SPEC.md` are streamed
   frame by frame through a new incremental atomic writer
   (`AtomicWriter`: temp file + fsync + rename), instead of building a
   `BTreeMap<String, Value>` for every frame, the whole contract `Value`, and
   one serialised string. Per-frame values are written and dropped; memory is
   bounded by one frame plus the asset set.
3. **Member containment.** `mono_core::render::member_path` / `resolve_member`
   resolve a member and refuse anything that leaves `root` (lexically
   normalised). The renderer uses it for image assets, sequence directories and
   joined `{n}`/`{d}` patterns, font headers and font packs; validation uses the
   same helpers. Validation reports `ASSET_PATH_ESCAPE`; rendering returns
   `E-CORE-PATH`.

## Out of Scope

- `batch-validate` cost and report size: it is the full-matrix command and the
  stress report listed its numbers as context, not as a defect.
- Symlink/junction containment: this round enforces lexical containment at
  resolution time. The export-prune walk already refuses to follow links; a
  canonical containment pass for existing links needs its own decision.
- A hard cap on scene size or state count: streaming removes the abort without
  inventing a new product limit.
- The Output Workbench and `export.bitmap_data` (outside the gate by ADR-006).
- Art/camera/theme work and the three out-of-scope performance budgets (G4 §4).

## Protected Existing Work

No unrelated user changes were edited, reverted or staged. `fixtures/golden/**`
and `test_assets/**` are untouched; all stress projects and reports live under
`target/stress/` (ignored). The TASK-006 working-tree changes were preserved.

## Constraints

- No new dependencies; no `unwrap`/`expect`/`panic`/`unsafe` in production code.
- The successful-export contract must stay byte-identical: checked by exporting
  the same three states with the pre-fix and post-fix binaries and diffing the
  output trees (identical).
- GUI runs use a throwaway `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` and copies
  of `test_assets`.
- Verification stops at VERIFY; DONE/PASS belongs to the independent review.

## Allowed Files / Expected Area

- `crates/mono-core/src/render.rs` (member resolution)
- `crates/mono-project/src/export.rs` (gate short-circuit, streamed artefacts)
- `crates/mono-project/src/atomic.rs` (`AtomicWriter`)
- `crates/mono-project/tests/export_gate.rs`, `tests/safety.rs`
- `CHANGELOG.md`, `docs/AUTOMATION_API_V1.md`, `docs/USER_GUIDE_CN.md`,
  `docs/USER_GUIDE_EN.md`
- `target/stress/*` (throwaway harness and report)
- `.ai/CURRENT_STATE.md`, this task file

## Acceptance Criteria

- A blocked export validates only through the first blocking frame; the report
  says so; a clean scene still validates every state before writing.
- A clean 1000-element × 560-state export writes the same bytes as before and
  keeps private memory flat: measured **18.1 MB peak** for 233 MB of artefacts on
  the final build (OS `PeakPagefileUsage`; decimal MB).
- `p-10000` (blocked) refuses in well under a second without an abort; a real
  escape is reported as `ASSET_PATH_ESCAPE` and never read.
- Regression tests cover: early-stop report scope, traversal via `asset` and via
  a sequence `pattern`, and absolute paths outside the root.
- `fixtures/golden/` and `test_assets/` unchanged; no new dependencies.

## Verification Plan

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- `cargo test --workspace --locked`
- `python -m pytest tools/tests -q`
- `cargo deny check`
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe`
- Re-run `target/stress/fuzz_cli.py`, `stress_cli.py`, `bridge_stress.py`, the
  monitored 10 000-element export, and the clean 560-state export.

## Deliverables

- The code and test changes in Required Changes, the Unreleased CHANGELOG entries
  and the listed manual updates.
- Stress re-run evidence in `target/stress/REPORT.md` (ignored scratch).

## Result

This section was added during the 2026-11-01 review correction: the implementation
round did not write one. The figures come from `target/stress/REPORT.md`
(implementer, release build):

- blocked `valid-1005` export: 464.3 s and 814 MB before; 0.4 s and 6.1 MB after;
- blocked `p-10000` export: abort at 1 951.6 MB before; 0.4 s, 26.4 MB, exit 2 after;
- blocked `p-10000` handoff: abort around 93 s before; 0.4 s, 39.2 MB, exit 2 after;
- clean 1000 elements × 560 states: 137.2 s, 16.7 MB peak private, exit 0, zero
  findings.

Not measured: a clean 10 000-element export.

The figures above were polled. After the second 2026-11-01 rework, on the final
release build, with the OS `PeakPagefileUsage`:

- `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --locked
  -- -D warnings`, `cargo test --workspace --locked`, `python -m pytest tools/tests
  -q` (33 passed, 1 skipped) and `cargo deny check`: clean. Clippy and the test runs
  used `RUSTFLAGS="-C debuginfo=0"` to stay within memory.
- `python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` on the
  final release build: 17/17 PASS.
- Blocked `valid-1005` export: exit 2, 0.99 s, 8.8 MB.
- Blocked `p-10000` export and handoff: exit 2, 0.28 s and 0.29 s, 53.1 and 53.3 MB.
- Clean 1000 elements × 560 states: exit 0, 148.9 s, 18.1 MB, 233.2 MB of artefacts,
  byte-identical to `target/stress/out/clean-560` (a recursive file comparison).

## Review Status

Independent review (2026-11-01): **REWORK REQUIRED**. The gate short-circuit,
streamed artefacts (byte-identical to the frozen corpus) and the renderer/validator
containment were accepted. The review record was re-checked the same day; this
section is the corrected scope. No source changes were made in either round.
`DONE` / `PASS` needs the rework and a new independent review.

Required fixes:

1. **Font Lab still follows a scene `font_pack` member outside the root.**
   `apps/mono-desktop/src/app.rs:401-417` does `root.join(rel)` and a raw
   `starts_with(&root)` on the unresolved path, so `../outside-pack` passes,
   is walked and listed. `font:open:../outside-pack` loaded the outside pack
   (reproduced; saving back through `FontLab::save` is from reading the code, not
   run). `pixel_ui.rs:596,890` load from the same list. Use
   `member_path`/`resolve_under_root` and store only project-relative ids.
2. **FontPack fingerprints read outside the pack before the containment check.**
   `crates/mono-project/src/fontpack_io.rs:21-35` reads every `glyphs[*].asset`
   with `std::fs::read(root.join(asset))`; `resources.rs:126` computes this
   fingerprint before `load_font_pack`'s check at `fontpack_io.rs:94-97`.
   Reproduced: a 300 MB file outside the project gave a 301.2 MB peak and 4.85 s
   before `FONT_INVALID`. Check containment before reading (and consider a size
   bound).
3. **`CHANGELOG.md:8` claims more than was measured.** "A 10 000-element matrix ...
   now completes within that bound" has no evidence: `p-10000` was only measured
   blocked. The comment at `export.rs:1436-1438` has the same problem. Measure a
   clean run or remove the claim. The re-check's concern about findings held in
   `all` was withdrawn in the rework: `validate_scene` emits only `BLOCKER`
   findings, so a passing export keeps one empty entry per frame.
4. **Member containment is a behaviour change filed under Fixed.** Projects with
   `../` or outside absolute members that exported under 2.1.0 are now blocked.
   `AGENTS.md` requires containment, but the entry belongs under Compatibility,
   with the known limitation: containment is lexical, and members that reach
   outside through a symlink or junction are not refused.

Also fix in this scope:

- Windows containment is case-sensitive, so an in-root absolute path that differs
  in case from the root is rejected (reproduced), as is an in-root `\\?\` path.
  Compare per component case-insensitively on Windows or document the rule.
- The blocked-dialog and status counts do not say "first N frames"
  (`strings.json:79,378,601`).
- The report header repeats the checked count (`export.rs:1224`).
- `app.rs:2148` still says `export_scene` validated the whole set.
- `CHANGELOG.md:7` says 0.3 s/6 MB; the report says 0.4 s/6.1 MB.
- Add tests for `AtomicWriter` drop/finish failure, zero-frame export, cancellation
  cleanup, a blocked export that must not touch an earlier successful output, and
  font-header/pack traversal. Strengthen the escape test so the outside file would
  decode successfully and declare a different size; then "no decode finding"
  proves it was never opened.

Library API hardening, not reachable from product paths today (re-checked 2026-11-01):

- Duplicate frame names: the reviewer reported this as a public-API robustness
  issue, and that stands. `select_export_states` dedupes, `--states 0,0` exports
  one frame, and Automation `export.all` uses generated names from
  `build_export_states`. A library caller passing duplicates to `export_scene`
  could still produce duplicate JSON keys; dedupe or reject there if the API is kept.
- `member_path` provides no containment for an empty or `.` root
  (`render.rs:68-75`). Relative `--project` and `--scene` runs were checked and do
  refuse an escape; reject an empty root in the library.
- `render::resolve` has no callers left; note that new code must use
  `resolve_member`.

Files outside this task's original Allowed Files that the fix scope may touch
(confirmed by the user, 2026-11-01): `apps/mono-desktop/src/app.rs`,
`apps/mono-desktop/src/fontlab_ui.rs`,
`apps/mono-desktop/src/pixel_ui.rs`, `apps/mono-desktop/i18n/strings.json`,
`crates/mono-project/src/fontpack_io.rs`.

Rework (2026-11-01): all items above are done, and no item was deferred.

- Failing first: the fingerprint, the case/verbatim and unanchored-root containment,
  the repeated frame name and the report header each had a test that failed before
  the fix. The strengthened escape test, font traversal, `AtomicWriter`, zero-frame,
  cancellation and earlier-output tests passed on the old code: they add coverage.
- `member_path` compares verbatim prefixes as plain ones and folds case on Windows;
  an unanchored root now contains its members instead of accepting everything.
- The Font Lab open path and both Pixel paths go through `App::font_pack_root`; a
  folder picked in the Open dialog is an explicit user choice and stays allowed.
- The duplicate frame name is refused in `export_scene_with_report`. The CHANGELOG
  claim was removed, not measured, and containment moved under Compatibility.
- `CHANGELOG.md` keeps the lexical limitation: links and junctions are not refused.

Second independent review (2026-11-01): **REWORK REQUIRED**. No Critical findings.
The gate, streaming (bytes equal to a self-built HEAD binary and to the 560-frame
reference), the read-path sweep (scene, font pack, Automation, mono-font, desktop) and
the repeated-frame refusal were accepted. All gates and GUI trust re-ran clean. The
fix scope:

1. **The Windows case folding added by the rework allows a real escape.**
   `render.rs` folds with `to_lowercase`, which is wider than NTFS. With root `kit`
   and a sibling directory whose name starts with U+212A KELVIN SIGN, the member
   `../<KELVIN>it/secret.png` was opened and decoded. Reproduced independently on the
   release binary: the two directories are different on NTFS and the run reported
   `ASSET_SIZE_MISMATCH` for the outside file, not `ASSET_PATH_ESCAPE`. Compare a
   joined relative member against `root` exactly, without folding; use
   `to_ascii_lowercase` only for absolute members; add a Kelvin regression test.
2. **"Accepted however it is spelled" is false.** An 8.3 alias of the root was refused
   (reviewer's run). Say that only case and the verbatim prefix are normalised, and
   that 8.3 aliases and linked spellings of the root are refused.
3. **Deviations are not recorded.** `docs/AI_HANDOFF.md` §6.3 requires new 1.x
   deviations in the evidence file. Add containment and the first-blocker report
   scope to G4 §5; add the report scope to Compatibility (reviewer: 36 frames and
   1188 findings at HEAD, 1 of 36 and 33 now); say in the Automation API doc that
   `export.*` now refuses escaping members.
4. **`digits` containment has no test.** Removing all three digits checks kept
   `safety`, `export_gate` and the lib tests green. Add digits `dir` and pattern cases
   and give the sequence case a different declared size, asserting no
   `ASSET_SIZE_MISMATCH`.

Also fix in this scope (reviewer's findings, not independently reproduced):

- `normalize_path` pops a preceding `..` under a relative root, so `"", "../../a.png"`
  silently becomes `a.png`. Pop only a `Normal` component; library-only.
- Memory figures are polled and low. OS peak was 8.7 MB for the blocked 1005-element
  export (CHANGELOG says 6.1 MB) and 53.2 MB for `p-10000` (this file says 26.4 and
  39.2 MB). Use `PeakPagefileUsage`, or call the figures approximate. 226 MB is about
  222 MiB.
- "An aborted export leaves no partial artefact" holds only for the contract and spec:
  `golden/` and `reference/` batches stay on disk (pre-existing). Narrow the sentence.
- `SCENE_SCHEMA.md` should state containment and that a standalone scene's own
  `project_root` defines the root, and CHANGELOG should say so (pre-existing).
- Pin the zero-frame newline, and add a positive in-root case to the Font Lab GUI check.
- This rework also touched `apps/mono-desktop/src/guard.rs` and
  `tools/CHECK_GUI_TRUST.py`, which were not on this task's confirmed list. Both
  changes are in scope in substance; the list above is corrected by this note and
  needs the user's confirmation when the rework starts.

For the user's release decision, not this rework: both Compatibility changes alter
`export.*` behaviour, so this cannot ship as a patch. `API_VERSION` stays 1.3.0 and the
product version 2.1.0 until a release is requested; the 2.1.0 precedent bumped the
product version only.

Second rework (2026-11-01), against the second review's list:

1. Done. A relative member is compared exactly, an absolute member with ASCII folding
   on Windows only, and `windows_containment_does_not_fold_unicode_or_relative_members`
   failed first. Residual risk: in a case-sensitive Windows folder, an absolute member
   differing from the root only in ASCII case still compares as contained.
2. Done. CHANGELOG, G4 and `SCENE_SCHEMA.md` state what is normalised and what is
   refused.
3. Done. G4 §5 records both deviations as items 11 and 12; Compatibility and the
   Automation API doc cover the report scope and the refusal.
4. Done. `sequence_and_digit_members_cannot_escape_the_project_root` covers `dir` and
   pattern for both types, with a decodable outside file of a different size.

A mutation run on a throwaway copy applied the review's surviving mutations at once
and every one failed its intended test: no `bind_scene` reset, flush ignoring the
epoch, `after_edit` back to synchronous validation, `hit_test` picking the bottom
element, no null filter, Unicode folding plus relative folding, the old `..`
handling, and unchecked digits in both the renderer and the validator. Mutations
sharing a test were applied together, so they were not separated from each other.

Also-fix list: done. `normalize_path` only pops a name; its behaviour changes only for
a path with more than one leading `..`. Memory figures are now OS peaks. The
"no partial artefact" sentence is narrowed. `SCENE_SCHEMA.md` states containment and
the standalone root. The zero-frame newline is pinned and the Font Lab GUI case has
an in-root positive control.

The user confirmed `guard.rs` and `tools/CHECK_GUI_TRUST.py` by starting this rework.
`docs/SCENE_SCHEMA.md`, `apps/mono-desktop/src/main.rs` (TASK-006's scripted click) and
`crates/mono-core/src/render.rs` `normalize_path` are in this round's diff as well.

The release decision above is still open and is the user's.

Third independent review (2026-11-01): **REWORK REQUIRED**. No Critical findings. The
code items of both earlier scopes hold, and Unicode, NTFS-stream, device and UNC
escapes all failed on the real binary. Legitimate projects were not falsely refused.
`normalize_path` changed nothing outside containment, the gate and streaming hold, and
the CHANGELOG figures are supported. 156 tests passed and GUI trust was 17/17 (this
reviewer did not run clippy or deny). The scope is about 20 lines plus some sentences;
no gate needs re-measuring beyond the normal re-run.

Required fixes:

1. **Second-review item 1 was only half done.** A relative `dir` is resolved to an
   absolute path first, so `dir.join(pattern)` takes the absolute branch and is folded.
   Reproduced independently: `image` with `../KIT/assets/sub/0.png` under root `kit`
   gives `ASSET_PATH_ESCAPE`, while `image_seq` with `dir: assets` and pattern
   `../../KIT/assets/sub/{n}.png` does not. On default NTFS this is the same directory
   and harmless; in a case-sensitive folder it could read a sibling (reading was
   inferred, not run: `fsutil setCaseSensitiveInfo` was refused). The comment at
   `render.rs:121-123` and the residual-risk note above are therefore wrong.
   Add a helper that joins the member `dir` and the file once before `member_path`, use
   it at the sequence and digits sites in `render.rs`, `export.rs` and `editor.rs`, and
   add a Windows regression test for this pattern.
2. **The case-sensitive-folder limitation is only in this file.** State it in
   CHANGELOG or G4 §5 item 11. The reviewer accepts it as a known limitation for
   absolute members once documented.
3. **Compatibility covers only exports.** The same scenes also fail to render: `mono
   simulate` went from exit 0 to exit 2, Automation `render.current` returns
   `INVALID_REQUEST`, and the Designer canvas shows a render failure for the whole
   scene (run on the current tree; HEAD's `render.current`, `export.bitmap_data` and
   the Output Workbench are from reading code). Extend `CHANGELOG.md:7`. In
   `AUTOMATION_API_V1.md`, name `export.current`, `export.all`, `export.c_header` and
   `export.code_ai_handoff` instead of `export.*`, because `export.font_data` and
   `export.font_pack` do not use scene members and `export.bitmap_data` fails through
   rendering, not the gate.

Minor, to fix with it where cheap: this file's line 110 still shows the old polled
16.7 MB and 226 MB; the 8.8 and 53.1 figures are MiB while 233 MB is decimal; G4 §5
numbering runs 10, 11, 12, 9 (historical). Accepted without a change: `validate_scene`
messages now show the path as written, not canonicalised (text only).

Tooling note: the mutation run reused `target/_review2_t`, which left mutated binaries
that cargo treats as fresh; do not run `--workspace` tests there. Use a fresh target
directory for mutation copies.

Third rework (2026-11-01), against the third review's list:

1. Done. `joined_member(root, dir, file)` checks `dir`, joins the two as written and
   checks once, so a relative `dir` plus a relative `pattern` stays relative and is
   compared exactly. It replaces the join at the sequence and digits sites in
   `render.rs`, `export.rs` and `editor.rs`.
   `windows_sequence_members_are_compared_exactly_like_other_relative_members` covers
   validate, render and the Inspector's geometry. It failed first: validation opened
   `...\KIT\assets\sub\0.bmp` and reported `ASSET_SIZE_MISMATCH`.
   `a_pattern_cannot_rescue_a_dir_outside_the_project` keeps the separate `dir` check.
   A scene that used this spelling on default NTFS rendered before and is now refused;
   this is the same refusal `image` already gave, and Compatibility covers it.
2. Done. CHANGELOG Compatibility and G4 §5 item 11 state the case-sensitive-folder
   limitation, for absolute members only.
3. Done. Compatibility now covers the Designer, `mono simulate`, the Output Workbench
   and Automation rendering, and `AUTOMATION_API_V1.md` names the four gated methods.
   The API's message is `project member path escapes project root: ...` under
   `INVALID_REQUEST`; `E-CORE-PATH` does not appear in it.

Minor: the acceptance line now shows 18.1 MB and 233 MB with its unit. The second
rework's residual-risk note is superseded by the above: the risk it describes now
holds, and only for absolute members. The 8.8 and 53.1 figures remain MiB, which the
third review already notes. G4 §5 numbering stays historical. `joined_member` re-checks
`dir` per file, which costs one path normalisation per digit; the bench was not re-run
for it.

Gates on the final tree: `cargo fmt --all -- --check`, `cargo clippy --workspace
--all-targets --locked -- -D warnings`, `cargo test --workspace --locked`, `python -m
pytest tools/tests -q` and `cargo deny check` were clean, and
`python tools/CHECK_GUI_TRUST.py --exe target/release/monooled-studio.exe` passed on a
fresh release build (17/17, exit 0). 158 tests passed, 0 failed; pytest 33 passed,
1 skipped. On that build `mono validate` reports `ASSET_PATH_ESCAPE` for both the
`image` and the `image_seq` form of the reproduction.

Scoped independent review (2026-11-01): **REWORK REQUIRED**, documentation only. No
Critical findings. The code is accepted: `joined_member`, its call sites and the tests
need no change, and nothing needs re-measuring. All five call sites were reverted one
at a time and each failed the new test. A 48-case differential of the old join against
the current build found no false refusal: only the two intended refusals and one
message text. Running confirmed all 8 `render.*` methods, `export.bitmap_data` with the
current-scene source and `mono simulate` exit 2 on an escaped scene (exit 0 on the
previous reviewer's HEAD build, whose provenance was not confirmed). The Designer
failure and the Output Workbench's `bench_source` were also run, the latter through a
scripted action on a debug copy, so the Compatibility text no longer rests on reading
code.

Required fixes:

1. `CHANGELOG.md:8` lists `export.c_header` among the methods whose report ends at the
   first blocking frame. `export.c_header` has no report and no matrix: it checks one
   state and returns the blockers in the error (checked in `dispatch.rs`; the reviewer
   ran it). Drop it from that sentence. The four-method list in `AUTOMATION_API_V1.md`
   describes the gate and is correct.
2. `CHANGELOG.md:7` lost a word: "reports `ASSET_PATH_ESCAPE` the export is blocked"
   (checked). Restore it.

Minor, to fix with it where cheap: `CHANGELOG.md:28` should name `joined_member` as a
checked resolver. The third rework's "one path normalisation per digit" understates the
cost: each digit pays one extra `member_path`, measured at about 6–9 µs, or about 1 ms
of a 14 ms render and 5 ms of an 81 ms validate pass on the 50-digit scene. It is not
visible at UI level (TASK-006). Removing the `render.rs` or `export.rs` sequence
pre-loop check fails no test, though both do real work; a test for an escaped `dir`
with `count` 0 and with empty digit text would pin them. The pre-loop check for digits
in `export.rs` is redundant and harmless.

Gates the reviewer ran: fmt in the repository; clippy, 158 workspace tests, pytest (33
passed, 1 skipped) and deny on a throwaway copy matching `crates/` and `apps/`; GUI
trust 17/17 on the release binary. Not verified: a real case-sensitive Windows folder,
macOS and Linux, the 1005-element and fixture benches. No repository file was changed
in the review.

Fourth rework (2026-11-01), against the scoped review's list:

1. Done. `CHANGELOG.md:8` no longer names `export.c_header`.
2. Done. `CHANGELOG.md:7` reads "reports `ASSET_PATH_ESCAPE`, the export is blocked,
   and the scene no longer renders".

Minor: `CHANGELOG.md:28` names `joined_member`. The new test
`an_escaped_dir_is_refused_even_when_no_file_is_joined` pins the `render.rs` digits
check and the `export.rs` sequence check. Removing each on a throwaway copy fails it.
The first version of the test did not catch the `export.rs` removal: `validate_scene`'s
own render still reports the escape, without an element id. So what that check adds is
the element, for an element the render would report only at scene level, and the test
now asserts the id. The check's comment is still true. The `export.rs` digits check
stays redundant and has no comment; it was left as it is.

No production code changed, so the release build and GUI trust from the third rework
still apply and were not re-run. On the final tree: fmt, clippy and `cargo test
--workspace --locked` (159 passed, 0 failed) were clean. pytest (33 passed, 1 skipped)
and `cargo deny check` were clean before the last test-only edit.

Confirmation review of the fourth rework (2026-11-02): **PASS**. No Critical, High or
Medium findings. The reviewer ran every check itself:

- CHANGELOG lines 7, 8 and 28 hold. Line 8 was run through a dispatch harness:
  `export.current`, `export.all` and `export.code_ai_handoff` write the stopped report
  (1 of 1, 1 of 560, 1 of 560), and `export.c_header` writes none.
- The new test pins both pre-loop checks: removing each fails it, and removing the
  `export.rs` digits check does not, which confirms it is redundant.
- No production code changed, the release binary carries the checks, and skipping
  the release build and GUI trust was accepted.
- Gates on a byte-identical copy: fmt, clippy, `cargo test --workspace --locked`
  (27 groups, 159 passed, 0 failed) and deny all exited 0. pytest failed once on the
  deep copy path with git's "Filename too long" in
  `test_ai_context_builder.py::test_required_source_and_detached_head_fail_without_traceback`.
  On a short-path copy hashed identical to the repository it gave 33 passed, 1 skipped.
  That test fails on a deep Windows path without long-path support; this is a property
  of the tool test, not of this work.

Info, left for its own decision: `CHANGELOG.md:35` (the released 2.1.0 entry) says a
blocked C-header export also saves a report through the API, but `export.c_header`
writes none. The fourth rework's own `gates5.log` predates the last test edit and shows
no deny line; the review's runs cover clippy, tests and deny on the final tree.

Not verified: macOS, Linux, a case-sensitive Windows folder, and a fresh release build
or GUI trust after the fourth rework.
