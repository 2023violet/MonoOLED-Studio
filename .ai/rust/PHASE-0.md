# Rust Phase 0 — Isolation and First Golden Baseline

Status: IN_PROGRESS
Review Status: PENDING

## Goal

Isolate Rust validation from pre-existing Python changes, record the approved
decision and freeze the first small, executable Python reference fixture set.
This is a branch-specific Rust workstream, not TASK-003 closure or TASK-004.

## Background and historical evidence

User approved Rust V2 validation and requested isolation before implementation.
Initial branch base: `d56af87ff71cbfd60321d4867c387130a2464a15`.
The managed worktree was initially detached, then attached to existing `rust`
after the original worktree switched to `main`. Both branches pointed at the
same commit, so the switch preserved original file content.
This is historical evidence only; query Git for current branch/remote/dirty state.

## Required changes and allowed area

- `.ai/rust/ADR-001.md`, `VALIDATION_PLAN.md`, `PHASE-0.md`.
- Navigation-only additions to `.ai/DECISIONS.md` and `.ai/README.md`.
- `test_assets/rust_v2/goldens.json` and `README.md`.
- `tools/VERIFY_RUST_GOLDENS.py`.
- `tests/test_rust_golden_baseline.py`.

No product source changes, Cargo workspace, Rust implementation, V1 release
changes, protocol invention, CI claims, staging or publication.

## Protected existing work

Original worktree's TASK-003 contract, context-builder code/test, BLOCKED.md,
PROGRESS.md, pelican_lakeshore.svg and 文档.md remain there. None is copied into
this worktree. The committed TASK-003 baseline is inherited history; its local
rework is not imported or declared reviewed. CURRENT_STATE retains TASK-003
workflow status; this branch's separate scope is navigated through .ai/README.

## Acceptance criteria

1. Rust worktree is on rust, isolated from original dirty main.
2. Approved validation decision and exclusions are recorded without overwriting
   governance ADR-001 or declaring full rewrite approved.
3. Frozen inputs/expected values are machine-readable, language-neutral and
   reference pinned Python source.
4. Verification invokes actual production functions and never rewrites goldens.
5. Encoding fixtures agree with existing independent literal goldens.
6. Deliberate expected-output corruption is detected.
7. Semantic JSON tolerates key order/formatting but detects value differences.
8. Focused tests pass; unsupported platforms/hardware remain NOT RUN.
9. Original protected file hashes are unchanged during Phase 0 implementation.
10. Stop at VERIFY / PENDING, with no Rust business code or publication.

## Verification plan

- `python tools/VERIFY_RUST_GOLDENS.py` twice.
- `python -m pytest tests/test_rust_golden_baseline.py -q`.
- Individually run existing bitmap_encoding, framebuffer, output_formatter,
  project_output_profiles and font_pipeline_e2e_v122 test modules.
- Compare source blob identities to pinned base, inspect diff and Git status
  of both worktrees, hash-check original protected files, git diff --check.

## Result

Pending execution. macOS/Linux, Rust, GUI, renderer matrix, physical hardware,
full regression and release checks are NOT RUN in Phase 0.

## Approval and current prerequisite

The user approved this Validation Plan. That approval authorizes Phase 1 after
its prerequisites and does not declare a Go/PASS result or approve full
migration. On 2026-09-25 the managed rust worktree has no available `rustc` or
`cargo` in PATH or the checked common installation directories. Phase 1 Rust
workspace creation is therefore **WAITING FOR TOOLCHAIN**; no uncompiled Rust
business code is added under this blocker.
