# Current State

本文件只记录生命周期较长的项目和工作流状态。它不持久化瞬时 Git 工作区或同步状态。

## Project

- Project: MonoOLED Studio
- Product version: 2.0.0 (Rust; Python 1.x source at the v1-final tag)
- Current phase: Rust Rewrite complete — v2.0.0 released 2026-10-21 (G6 B1–B4 executed on explicit user confirmation)
- Rewrite spec: docs/rewrite/2026-10-19-rust-rewrite-design.md
- Rewrite plan: docs/rewrite/2026-10-19-g0-plan.md
- Current gate evidence: docs/rewrite/G6_EVIDENCE.md (G4/G5 reviewed); plan: docs/rewrite/G6_CUTOVER_PLAN.md
- Decision: ADR-005 (Rust full rewrite, main-only)

## Workflow

- Last completed workflow task: TASK-003
- TASK-001 status: DONE
- TASK-002 status: DONE
- TASK-003 status: DONE
- Independent Review: PASS (TASK-003, agent review)
- Active task: NONE (Rust Rewrite G4 evidence recorded)
- Next workflow action: NONE (2.x maintenance; known gaps in CHANGELOG 2.0.0 and docs/rewrite/G6_EVIDENCE.md §6)

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
