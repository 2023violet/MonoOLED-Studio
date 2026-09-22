# Current State

本文件只记录生命周期较长的项目和工作流状态。它不持久化瞬时 Git 工作区或同步状态。

## Project

- Project: MonoOLED Studio
- Product version: 1.2.3
- Current phase: AI workflow adoption

## Workflow

- Last completed workflow task: NONE
- Active task: TASK-001
- Next workflow action: Independent Review of TASK-001

## Current workstream

- User-owned theme visual changes are in progress.
- The dark theme routing strategy remains an unresolved product decision.
- Existing theme work must remain protected while workflow control files are added.

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
