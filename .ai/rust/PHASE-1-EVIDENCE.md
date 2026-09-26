# Rust Phase 1 GUI Evidence Record

Status: VERIFY
Review Status: PENDING

This document records the evidence for the remaining Phase 1 checklist items:
real GUI interaction, DPI probes, long-task responsiveness, worker shutdown,
and the three-OS GUI smoke runs. It complements
[PHASE-1-REPORT.md](PHASE-1-REPORT.md), which covers the build/test/lint/CLI
parity matrix.

## Evidence mechanism

`mono_desktop --evidence [path]` runs inside the real `eframe::run_native`
event loop: a real OS window, the real glow renderer, the real layout pass,
the real gesture model, and real file IO. Only the origin of pointer
coordinates is scripted — the driver computes screen positions from the
canvas rect the real layout produced and feeds them into the same
`canvas_drag_started` / `canvas_dragged` / `canvas_drag_stopped` handlers
the winit pointer path uses. No OS-level event injection is performed or
claimed. The app closes itself via `ViewportCommand::Close`; `main()` then
writes a JSON report and exits nonzero when any step failed.

Commit: 25f172d (pushed to origin/rust as the evidence checkpoint).

## Scripted steps (frozen order, guarded by unit test)

1. `env_probe` — native `pixels_per_point`, GL renderer/version strings.
2. `pencil_drag` — drag (5,5)→(9,5), row segment verified.
3. `eraser_tap` — tap (7,5), pixel cleared, neighbors preserved.
4. `undo_redo` — undo restores, redo re-clears.
5. `line_preview` — 3-frame live preview; stale preview cleared after the
   target moved (only the final Bresenham line persists).
6. `rectangle_outline` — outline set, interior empty.
7. `gesture_history` — 4 gestures undo to a zero canvas, redo restores all
   (one continuous gesture = one undo step).
8. `zoom_pan_mapping` — draws at zoom 4/24 and pan ±80/40 map to the
   intended document pixels.
9. `dpi_probes` — `set_pixels_per_point` at 1.0/1.25/1.5/2.0, effective
   value read back next frame (1% tolerance) plus a scripted draw
   verification at each scale.
10. `fixture_open` — rows equal the pre-seeded deterministic fixture.
11. `save_reopen_export` — edit, save, parse the saved file for semantic
    parity, export bytes equal `PixelDocument::to_vlsb` (SHA-256 recorded),
    reopen through the app, rows match.
12. `worker_churn` — std::thread worker encodes a 128×64 document to VLSB
    and hashes it for ~2 s; the UI keeps repainting (frame times recorded)
    and a scripted draw completes mid-churn.
13. `worker_close` — a second worker is spawned and left running; the real
    close path (`App::on_exit`) stops and joins it with a 5 s timeout,
    elapsed recorded.

## Local Windows evidence

Command:

    cargo run --release --locked -p mono_desktop -- --evidence target/evidence_windows_local.json

Result (2026-09-26, Intel UHD Graphics, GL 3.3.0):

- `all_passed: true`; 0 failed steps out of 17 recorded.
- Renderer: `Intel(R) UHD Graphics`, GL `3.3.0 - Build 27.20.100.9365`.
- DPI: native 1.0; probes 1.0/1.25/1.5/2.0 all read back exact and
  draw-verified.
- Frame times: 221 frames, p50 8.3 ms, p95 9.1 ms, p99 16.6 ms,
  max 495.1 ms (first-frame window creation).
- Worker churn: 182 frames during the ~2 s churn window; scripted draw
  completed mid-churn; no frame over 1000 ms.
- Worker close path: joined within timeout, elapsed 5 ms.
- Save/reopen/export: parity confirmed, export 256 bytes,
  sha256 b075bc93de9a0304ba3fd2f171f3e033044812e8e6f4e19178d7f2bd04fedb9d.

## Three-OS CI evidence

Workflow: Rust Validation, run 36238943132, commit 25f172d, branch rust.

First run outcomes (recorded, then remediated):

- macOS: PASS — `all_passed: true`, renderer `Apple Software Renderer`
  (GL 4.1), 70 frames, p50 47.7 ms, worker close joined in 17 ms.
- Windows: FAIL — `egui_glow requires opengl 2.0+` (runner GPU context
  without GL 2.0 in the session the step ran in). Launch failure.
- Linux X11: FAIL — `libxkbcommon-x11.so could not be loaded`
  (runtime library not installed; only the -dev package was).
- Linux Wayland: NOT RUN in that job — the X11 hard-gate failure stopped
  the job before the Wayland step (steps run sequentially).

Remediation (commit follows): add `libxkbcommon-x11-0` to the Linux apt
install list; record `launch_error` in the evidence JSON and exit nonzero
after writing the report so GL failures stay visible with a full report;
guard the summary step against missing report fields.

- Windows: `GUI evidence (Windows)` step — hard gate.
- macOS: `GUI evidence (macOS)` step — hard gate.
- Linux X11: `xvfb-run` with `LIBGL_ALWAYS_SOFTWARE=1 WINIT_UNIX_BACKEND=x11`
  — hard gate (llvmpipe software renderer expected in `gl_renderer`).
- Linux Wayland: weston headless-backend attempt with
  `WINIT_UNIX_BACKEND=wayland` — `continue-on-error: true` soft gate. A
  failure is recorded as an attempt (stderr artifact `wayland_attempt.txt`),
  never silently waived; the final classification (PASS / NOT RUN with
  rationale) belongs to independent review.

Per-OS evidence JSON artifacts are uploaded as `rust-evidence-<OS>` and a
summary table (all_passed, renderer, frame count, p99, worker join) is
appended to the run's step summary.

Second run (36240861666, remediated, artifacts downloaded and inspected):

- macOS: PASS — `all_passed: true`, `Apple Software Renderer` GL 4.1,
  71 frames, p50 47.3 ms, p99 463.3 ms, churn 32 frames, worker close
  joined in 14 ms, DPI probes all pass.
- Linux X11: PASS — `all_passed: true`, `llvmpipe (LLVM 20.1.2, 256
  bits)` GL 4.5, 252 frames, p50 7.1 ms, p99 8.0 ms, churn 213 frames,
  worker close joined in 5 ms, DPI probes all pass.
- Linux Wayland (weston headless, soft gate): PASS — `all_passed: true`,
  same llvmpipe renderer, 100 frames, p50 25.1 ms, p99 31.9 ms, churn
  61 frames, worker close joined in 5 ms, DPI probes all pass.
  `wayland_attempt.txt` is empty (no stderr from the attempt).
- Windows: FAIL — launch failed again with `egui_glow requires opengl
  2.0+` in the runner session. The remediation worked as designed: the
  evidence JSON was written with `launch_error` recorded and the step
  exited nonzero. The first remediated report wrongly reported
  `all_passed: true` alongside the launch error (zero steps recorded,
  vacuous pass); fixed by making `all_passed` require
  `launch_error.is_none()` (with a regression test) in the follow-up
  commit.

Third run (36241440052, aggregation fix, artifacts downloaded):

- macOS: PASS — `all_passed: true`, `Apple Software Renderer`, 72 frames.
- Linux X11: PASS — `all_passed: true`, llvmpipe, 203 frames.
- Linux Wayland: PASS — `all_passed: true`, llvmpipe, 100 frames.
- Windows: FAIL, now correctly reported — `all_passed: false` with
  `launch_error: "egui_glow: OpenGL: egui_glow requires opengl 2.0+"`
  and zero steps. The report is honest; the job exits red.

Windows CI classification note for review: the same binary reports
`all_passed: true` on the local Windows 10 machine (Intel UHD, GL 3.3,
evidence above), so this is a runner GPU-context limitation, not a code
defect. The runner outcome stays recorded as FAIL; reclassification to
"environment-limited, evidenced locally" belongs to independent review.

## Test-first discipline

Red output before implementation (`cargo test -p mono_desktop --locked`):

    error[E0432]: unresolved import `crate::evidence`
    error[E0432]: unresolved import `crate::worker`
    error[E0433]: cannot find module or crate `egui` in this scope
    error[E0061]: this function takes 1 argument but 0 arguments were supplied
    error: could not compile `mono_desktop` (bin "mono_desktop" test) due to 11 previous errors

Green output after implementation: 16 passed, 0 failed
(mono_core 3, mono_desktop 16 total across the workspace).

First full local evidence run exposed a real script bug — `env_probe` was
missing its `finish_step()` (the script stalled on step 0) and the
`line_preview` assertion used a point that is not on the Bresenham line.
Both were fixed and re-run; the fix history is preserved in the working
session log, not hidden.

## Local verification sequence (all after the final fix)

- `cargo fmt --all -- --check`: PASS
- `cargo test --workspace --locked`: PASS (mono_core 3, mono_desktop 16)
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: PASS
- `cargo build --workspace --release --locked`: PASS
- `cargo run --locked -p mono_cli -- test_assets/rust_v2/goldens.json`:
  All Rust Core fixtures matched.
- `git diff --check`: PASS

## Honest scope statement

This evidence covers the Phase 1 slice boundaries only:

- Save/Export remain validation artifacts under `target/`, not the V1
  project persistence or export contract.
- Scripted pointer coordinates exercise the app's gesture model through
  the same handlers as the mouse; real OS-level event injection, real
  mouse/IME/clipboard/file-picker/drag-drop behavior are NOT proven here.
- Renderer coverage is the runners' GPUs (Windows/macOS) and llvmpipe
  (Linux). No dedicated GPU matrix was run; the target office-machine
  matrix (old Intel iGPU, AMD, NVIDIA, RDP, VM) remains NOT RUN.
- Physical OLED compatibility remains untested and unclaimed.
- Wayland evidence status depends on the CI attempt outcome recorded above.
