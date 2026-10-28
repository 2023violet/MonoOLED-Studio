# Current State

本文件只记录生命周期较长的项目和工作流状态。它不持久化瞬时 Git 工作区或同步状态。

## Project

- Project: MonoOLED Studio
- Product version: 2.2.1 (Rust; Python 1.x source at the v1-final tag)
- Current phase: Rust Rewrite G6 complete; 2.0.4 trust fixes complete (TASK-004 DONE); 2.0.5 project loop complete (TASK-005 DONE, review PASS WITH MINOR NOTES); 2.1.0 professional workflow implemented (TASK-006 VERIFY, T12–T17); 2.2.0 polish and governance implemented (TASK-007 VERIFY, T18–T21)
- Rewrite spec: docs/rewrite/2026-10-19-rust-rewrite-design.md
- Rewrite plan: docs/rewrite/2026-10-19-g0-plan.md
- Current gate evidence: docs/rewrite/G6_EVIDENCE.md (G4/G5 reviewed); plan: docs/rewrite/G6_CUTOVER_PLAN.md
- Decision: ADR-005 (Rust full rewrite, main-only)

## Workflow

- Last completed workflow task: TASK-005
- TASK-001 status: DONE
- TASK-002 status: DONE
- TASK-003 status: DONE
- TASK-004 status: DONE (2.0.4 trust fixes T1–T8 plus review rework; all CI gates green)
- TASK-005 status: DONE (2.0.5; T9 recent projects, T10 asset-to-Pixel, T11 atomic write-back; review PASS WITH MINOR NOTES)
- TASK-006 status: VERIFY (2.1.0; T12–T17 professional workflow; Result recorded, two GUI-found defects fixed)
- TASK-007 status: VERIFY (2.2.0; T18–T21 terminology, help/tooltips, new-project wizard, docs and version truth)
- TASK-008 status: VERIFY (CLI `--json` for validate/export/asset-audit and package discoverability docs; no version bump yet)
- Independent Review: PASS (TASK-003, TASK-004, TASK-005); PENDING for TASK-006/TASK-007 (subagent dispatch failed three times — two model-queue errors and one daily usage limit — so only inline self-review and implementer-side evidence are recorded; DONE/PASS remain open)
- Active tasks: `.ai/tasks/TASK-006.md`, `.ai/tasks/TASK-007.md`, `.ai/tasks/TASK-008.md`
- Next workflow action: an independent reviewer confirms TASK-006/TASK-007/TASK-008 (then `DONE`/`PASS`); 2.2.0 and 2.2.1 are published (`v2.2.1` is Latest, `v2.2.0` kept as published); TASK-008's CLI `--json` work is unreleased and would ship as 2.2.2 when the user authorizes a release

## Current workstream

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
