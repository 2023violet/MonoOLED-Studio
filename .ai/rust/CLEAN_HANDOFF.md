# MonoOLED Studio Rust V2 Clean Handoff

Updated: 2026-09-26

## Current answer

Rust V2 is a validation lane, not an approved full rewrite. Python V1 remains
the supported reference implementation. The approved framework candidate is
egui/eframe. Slint is a fallback only after an explicit egui gate failure.

Rust Phase 1 is at `VERIFY / PENDING`. The workspace contains `mono_core`,
`mono_cli`, and `mono_desktop`, plus the deterministic Golden fixtures and the
egui Pixel Slice. Independent review has not granted PASS or closure.

## Checkouts and protection boundary

- Python reference checkout: `D:\study\Software\MonoOLED-Studio`
  - branch: `main`
  - pre-existing dirty files are protected and must not enter Rust commits:
    `.ai/tasks/TASK-003.md`, `tests/test_ai_context_builder.py`,
    `tools/BUILD_AI_CONTEXT.py`, `BLOCKED.md`, `PROGRESS.md`,
    `pelican_lakeshore.svg`, and `文档.md`.
- Rust validation checkout:
  `C:\Users\16429\.codex\worktrees\monooled-rust-v2\MonoOLED-Studio`
  - branch: `rust`
  - HEAD and `origin/rust` were equal at the last audit; query them live before work.
  - the worktree is expected to be clean after this handoff commit; verify it.

Do not merge the two worktrees by copying dirty files, stashing, resetting,
cleaning, or rebasing without a new explicit decision.

## Verified evidence

- Phase 0 Python fixtures: 13/13 matched.
- Phase 0 focused test: `16 passed`.
- Rust workspace tests: `mono_core` 3 passed and `mono_desktop` 5 passed.
- Rust formatting, clippy, release build, Golden CLI and Windows launch smoke:
  PASS.
- GitHub Actions run `36213134064`: Windows, Ubuntu and macOS all succeeded.
- Rust Golden CLI: 13/13 fixtures matched.

Evidence details are in [PHASE-0.md](PHASE-0.md),
[PHASE-1.md](PHASE-1.md), and [PHASE-1-REPORT.md](PHASE-1-REPORT.md).

## Current limits

The following remain pending and must not be described as passed:

- macOS and Linux GUI smoke;
- separate Linux Wayland and X11 runs;
- real GUI interaction, Save -> Open through the running app, DPI and
  renderer probes;
- long-task responsiveness and worker shutdown;
- physical OLED compatibility;
- independent review of the Phase 1 evidence.

Save and Export currently write validation artifacts under `target/`; they are
not yet the V1 project persistence or export contract.

## Next action

Read `AGENTS.md`, `.ai/README.md`, `.ai/DECISIONS.md`,
`.ai/rust/ADR-001.md`, `.ai/rust/VALIDATION_PLAN.md`, the active TASK, and
`docs/AI_HANDOFF.md`. Query Git state live before any work. Continue with the
remaining Phase 1 evidence, then request independent review. Do not expand to
Font Studio, DeviceSession, Serial/HID, Tokio, automatic updates, cloud work,
GPUI, Slint, or a complete UI redesign.

## Publication state

The `rust` branch is pushed and CI is green. No PR, tag, release, deployment,
or production/live verification exists. The main checkout remains a protected
dirty lane. No cleanup has been performed; the review scene is preserved.

## Memory state

No MonoOLED-specific Codex memory entry was found. Generated Codex memory files
were not edited. Durable project facts are kept in the repository control plane
and this branch handoff; future memory updates should use the Codex memory
control surface rather than editing generated memory files directly.
