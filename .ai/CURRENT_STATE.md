# Current State

本文件只记录生命周期较长的项目和工作流状态。它不持久化瞬时 Git 工作区或同步状态。

## Project

- Project: MonoOLED Studio
- Product version: 2.1.0 (Rust; Python 1.x source at the v1-final tag; version truth is `[workspace.package] version` in `Cargo.toml`)
- Current phase: Rust Rewrite G6 complete; the 2.x line is in maintenance (2.0.3 on 2026-10-23, 2.1.0 on 2026-10-30)
- Active round: the 2026-10-30 truthful-controls batch (TASK-005) stacked on the 2026-10-29 experience-audit fixes (TASK-004); both shipped as `2.1.0`
- Rewrite spec: docs/rewrite/2026-10-19-rust-rewrite-design.md
- Rewrite plan: docs/rewrite/2026-10-19-g0-plan.md
- Current gate evidence: docs/rewrite/G6_EVIDENCE.md (G4/G5 reviewed); plan: docs/rewrite/G6_CUTOVER_PLAN.md
- Decision: ADR-005 (Rust full rewrite, main-only); ADR-006 (release gate covers every *scene* export producer — the Output Workbench and `export.bitmap_data` stay outside it by decision, viewing a screen never writes)

## Workflow

- Last completed workflow task: TASK-003
- TASK-001 status: DONE
- TASK-002 status: DONE
- TASK-003 status: DONE
- Independent Review: PASS (TASK-003, agent review)
- Active task: TASK-005 (stacked on TASK-004 in the same working tree), both committed
- Active task state: VERIFY with three independent review slices absorbed and their findings re-verified by the gates; `DONE` / `PASS` is the reviewer's or the maintainer's verdict and has not been awarded here (see each TASK's Review Status section)
- Next workflow action: the maintainer confirms `PASS` / `DONE` for TASK-004 and TASK-005. Tagging, pushing and publishing need an explicit instruction (`.ai/README.md` Operating rules).

## Current workstream

- TASK-004 (experience audit closeout) converges five "one signal, two owners"
  defects onto single sources of truth: the shortcut `FocusScope` owns the
  keyboard and the overlays sit inside it, `Scrim` owns Escape/backdrop dismissal,
  `EditorSession::is_dirty` compares against a saved snapshot, preferences read
  flat dotted shortcut keys, and `mono_project::export::preflight` is the one gate
  every export producer runs. `tools/CHECK_GUI_TRUST.py` re-checks the seams that
  only a real window can prove.
- TASK-005 (truthful controls, exposed engine) removes the rows and properties
  nothing ever read, draws `design_rules.zones` behind a real toggle, puts the job
  stage and a Cancel control in the status bar, opens the state schema, design
  rules, page rename and glyph offsets from the Inspector and Navigator, and
  rewrites the manual and rule files to match the code. Four text scans plus
  `tools/tests/test_docs_match_code.py` keep the seams from drifting back.
- Deferred by decision, not by omission: the Pixel Studio versus Font Lab visual
  language (black-background white dots versus white-background black shapes) and
  any theme/colour revision are left for a separate design round.
- Deferred for a product decision: the Output Workbench and Automation
  `export.bitmap_data` can still render the current scene into a file without the
  release gate. Including them changes API 1.3 behaviour, so it needs its own
  ADR rather than a silent fix; `docs/AI_HANDOFF.md` §5.5 records the boundary.
- Slint 1.18 constraints that cost this round a broken feature: a component that
  inherits `ListView` mislays its delegates, and `@children` cannot be forwarded
  into a `ListView`. Scroll-to-selection is a plain `ListView` plus a `changed`
  handler in the owning component, pinned by `no_list_is_a_subclassed_listview`.
- Corrected during the TASK-005 review: the earlier claim that a `changed` handler
  on a bound property "only runs while something reads it" is **wrong for 1.18**.
  `ChangeTracker::init` evaluates eagerly (`i-slint-core-1.18.1/properties/change_tracker.rs:188-209`),
  and `MainWindow.overlay-open` (`ui/main.slint:334`) has no reader outside its own
  `changed` handler yet still restores focus after every modal — which
  `check_overlays_and_focus` proves on the real binary. The `visible: x >= -1`
  guards left in `designer.slint` / `fontlab.slint` are therefore belt-and-braces
  from the original fix, not load-bearing; their real cause was never isolated.
- Known library limitation recorded in TASK-004: Slint 1.18.1 cannot two-way-bind
  `MenuItem.checked`, so View-menu check marks are rendered from `Shell` state.
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
