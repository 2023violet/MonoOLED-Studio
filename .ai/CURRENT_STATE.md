# Current State

本文件只记录生命周期较长的项目和工作流状态。它不持久化瞬时 Git 工作区或同步状态。

## Project

- Project: MonoOLED Studio
- Product version: 2.4.0 (Rust; Python 1.x source at the v1-final tag; version truth is `[workspace.package] version` in `Cargo.toml`)
- Current phase: Rust Rewrite G6 complete; the 2.x line is in maintenance. Released (tagged): 2.2.0/2.2.1 (TASK-004 to TASK-007; the 2.0.4, 2.0.5 and 2.1.0 changelog versions were never tagged and first shipped in v2.2.0), 2.3.0 (TASK-008, TASK-009), 2.4.0 (TASK-010 to TASK-017: a second line of work that branched at 2.0.3 and never shipped on its own, integrated onto 2.3.0 by TASK-014, plus its verification, the refresh-regression fix and the review-pack banner; the user delegated the decisions and the release on 2026-11-02, ADR-007).
- Rewrite spec: docs/rewrite/2026-10-19-rust-rewrite-design.md
- Rewrite plan: docs/rewrite/2026-10-19-g0-plan.md
- Current gate evidence: docs/rewrite/G6_EVIDENCE.md (G4/G5 reviewed); plan: docs/rewrite/G6_CUTOVER_PLAN.md
- Decision: ADR-005 (Rust full rewrite, main-only); ADR-006 (release gate covers every *scene* export producer — the Output Workbench and `export.bitmap_data` stay outside it by decision, viewing a screen never writes)

## Workflow

- TASK-001 status: DONE
- TASK-002 status: DONE
- TASK-003 status: DONE
- TASK-004 status: DONE (2.0.4 trust fixes T1–T8 plus review rework; all CI gates green)
- TASK-005 status: DONE (2.0.5; T9 recent projects, T10 asset-to-Pixel, T11 atomic write-back; review PASS WITH MINOR NOTES)
- TASK-006 status: DONE (T12–T17 professional workflow, first shipped in v2.2.0; post-release independent review PASS 2026-11-02 with three Minor findings, fixed by TASK-019)
- TASK-007 status: DONE (2.2.0; T18–T21 terminology, help/tooltips, new-project wizard, docs and version truth; post-release independent review PASS 2026-11-02)
- TASK-008 status: DONE (CLI `--json`; independent review PASS WITH MINOR NOTES; folded into 2.3.0, not released separately)
- TASK-009 status: DONE (2.3.0 T22–T28; independent re-review PASS after gallery invalidation, note refresh, sidecar protection and documentation corrections)
- TASK-010 status: DONE (experience audit closeout, formerly TASK-004 on the unshipped line; three review slices, final independent review PASS 2026-11-02 on the integrated code)
- TASK-011 status: DONE, confirmation review PASS 2026-11-02 (truthful controls, exposed engine, formerly TASK-005 on the unshipped line; final review 2026-11-02: a refused page rename drops the Designer session, `guard.rs:255`; fix scope in the TASK)
- TASK-012 status: DONE (Designer edit-path performance, formerly TASK-006; scoped review PASS 2026-11-01)
- TASK-013 status: DONE (stress findings: gate short-circuit, bounded export memory, member containment, formerly TASK-007; confirmation review PASS 2026-11-02)
- TASK-014 status: DONE, confirmation review PASS 2026-11-02 after three reworks (integration of TASK-010 to TASK-013 onto 2.3.0; see `.ai/tasks/TASK-014.md`)
- TASK-016 status: DONE, review PASS 2026-11-02 (large-scene refresh regression from the 2.3.0 integration: Review rebuilt only while visible with an indexed diff, note rows reuse the canvas frame; refresh back to pre-integration figures)
- TASK-015 status: DONE, review PASS 2026-11-02 (closes TASK-014's verification gaps: escaping members in the gallery and Review panel, six Inspector tabs in the GUI trust check, performance re-measured on the integrated tree, dead-binding scan over the 2.3.0 globals)
- TASK-018 status: VERIFY, independent review PASS WITH MINOR NOTES 2026-11-09; review finding M1 (geometry undo restored by index, not id) and its coalescing-path remainder R1 fixed afterwards and awaiting a confirmation review (Designer edit hot path: one resource lookup per file per render, no scratch renders or whole-list undo copies on geometry edits; both generated scenes under the 16 ms handler budget, reproduced by the reviewer; RUSTSEC-2026-0441 accepted in `deny.toml` with user approval)
- TASK-019 status: DONE, review PASS WITH MINOR NOTES 2026-11-09 (correctness follow-ups from the 2.4.0 reviews: ASSET_PATH_ESCAPE listed and labelled, a palette test that checks real dispatch, the drawer says when there is no baseline, untagged versions noted, the TASK-017 test gaps covered)
- TASK-017 status: DONE, review PASS 2026-11-02 (ADR-007 D1: a review pack with blocking findings is written with a static "Not a deliverable" banner; the same review covered TASK-014's three-platform CI rework)
- Independent Review: PASS (TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-009, TASK-010, TASK-012, TASK-013); PASS WITH MINOR NOTES (TASK-008); PASS (TASK-011, TASK-014, TASK-015, TASK-016 after rework where noted). PASS WITH MINOR NOTES (TASK-018, TASK-019; 2026-11-09). TASK-006/007 were reviewed after release (2026-11-02).
- Active task: TASK-018 awaits a confirmation review of its M1/R1 fix. Follow-ups: the Review panel still shows 100% without a baseline and the frame-geometry coverage gaps (TASK-018 Review Status), plus the lists at the end of `.ai/tasks/TASK-014.md` and in `.ai/tasks/TASK-017.md` Review Status.
- Next workflow action: after the TASK-018 confirmation review, three-platform CI and, on an explicit instruction, a 2.4.1 patch release (the review found no compatibility change). Tagging, pushing and publishing need an explicit instruction (`.ai/README.md` Operating rules). Release facts belong to GitHub and `docs/rewrite/G6_EVIDENCE.md`, not this file.

## Current workstream

- TASK-014 integrates the unshipped line onto 2.3.0. Where both lines fixed the same defect it kept one implementation: `EditorSession` judges dirtiness by comparing with a saved snapshot, Pixel documents keep 2.3.0's save point, the unsaved prompt keeps 2.3.0's per-document wording, shortcuts come from 2.3.0's command registry, and dialogs follow the unshipped line's focus model (overlays inside the shortcut `FocusScope`, `Scrim` owns Escape and backdrop dismissal, a modal blocks chords in `run_shortcut`).
- TASK-010 (experience audit closeout) converged five "one signal, two owners" defects onto single sources of truth; `mono_project::export::preflight` is the one gate every export producer runs. `tools/CHECK_GUI_TRUST.py` re-checks the seams that only a real window can prove.
- TASK-011 (truthful controls, exposed engine) removed the rows and properties nothing ever read, drew `design_rules.zones` behind a real toggle, put the job stage and a Cancel control in the status bar, opened the state schema, design rules, page rename and glyph offsets from the Inspector and Navigator, and rewrote the manual and rule files to match the code. Four text scans plus `tools/tests/test_docs_match_code.py` keep the seams from drifting back; during TASK-014 they caught every binding and translation key the integration left dead.
- TASK-012 (interactive performance) draws the overlay and answers hit-tests from the rects the renderer already resolved, and moves validation for geometry, state and rule edits and `refresh_all` onto a worker thread (epoch-gated). Budgets and the remaining misses are in `docs/rewrite/G4_EVIDENCE.md` §4. TASK-015 re-measured them after TASK-014 and found a regression on large scenes. TASK-016 fixed it: Review is rebuilt only while visible, and the note rows reuse the canvas frame. Full refreshes are back to their pre-integration figures.
- TASK-013 (stress findings): the export gate stops at the first blocking frame, `ui_contract.json` and `UI_SPEC.md` stream frame by frame, and scene members are contained to the project root (`ASSET_PATH_ESCAPE` / `E-CORE-PATH`). The check is lexical: links and junctions are a recorded limitation.
- Deferred by decision, not by omission: the Pixel Studio versus Font Lab visual language and any theme/colour revision are left for a separate design round.
- Decided for 2.4.0 (ADR-007): the Output Workbench and Automation `export.bitmap_data` stay outside the release gate (`docs/AI_HANDOFF.md` §5.5); the review pack is written whatever its findings but marks itself "Not a deliverable" when a rendered frame has a blocking finding.
- Slint 1.18 constraints: a component that inherits `ListView` mislays its delegates, and `@children` cannot be forwarded into a `ListView` (pinned by `no_list_is_a_subclassed_listview`). A `changed` handler on a bound property is evaluated eagerly (`ChangeTracker::init`), so `MainWindow.overlay-open` restores focus after every modal. Slint 1.18.1 cannot two-way-bind `MenuItem.checked`, so View-menu check marks are rendered from `Shell` state.
- Theme Visual Workstream is closed by TASK-002 under the approved product
  decision B.
- Dark theme routing decision resolved: preserve one-dark-pro runtime routing and
  apply approved dark visual tokens there.
- Popup native-mask versus Design System classification remains a
  `DEFERRED FOLLOW-UP CANDIDATE`; TASK-002 does not modify `ui_controls.py` or
  popup tests to resolve it.
- The pre-existing theme files remain auditable through the TASK-002 baseline.
- TASK-A archived former root `BLOCKED.md` and `PROGRESS.md` as
  `.ai/records/UI_CRAFT_BLOCKED_2026_09_12.md` and
  `.ai/records/UI_CRAFT_PROGRESS_2026_09_12.md`. They remain historical
  maintenance records, not authoritative for active tasks, product decisions,
  or workflow state. Eligible records may enter source delivery, but are not
  Windows runtime application resources.

## Phase 2 Result

ChatGPT × Codex Workflow Phase 2 — Real Product TASK E2E VALIDATED.

TASK-002 completed the full path from user product decision through implementation,
failure evidence, targeted verification, independent review, scope rework, GitHub
Review Baseline publication, control-plane rework, final Independent Review PASS,
and Closure.

## Dynamic repository facts

Before starting or reviewing a task, query these facts from the working tree and remote rather than copying them into this file:

```powershell
git rev-parse HEAD
git status --short --branch
git branch -vv
git remote -v
git rev-list --left-right --count origin/main...main
```

The active TASK, `AGENTS.md`, current source and tests, and machine-readable contracts remain the sources for task-specific scope and verification.
