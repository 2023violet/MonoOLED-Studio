# Rust Phase 1 — Independent Review Request

Status: REVIEW REQUESTED
Date: 2026-09-26
Scope: Phase 1 evidence (egui Pixel Slice + three-OS GUI evidence)
Review basis: `.ai/rust/VALIDATION_PLAN.md` Gate 2 exit checklist

## What is being reviewed

Whether the Phase 1 evidence satisfies the frozen exit checklist in
`VALIDATION_PLAN.md`, and the Go / Adjust / Stop recommendation for the
next step. Phase 1 is at VERIFY/PENDING; this document requests review
and does not claim PASS.

## Evidence package (all committed on `rust`, HEAD 1a4c486)

| Artifact | Location |
| --- | --- |
| Evidence record | `.ai/rust/PHASE-1-EVIDENCE.md` |
| Implementation report | `.ai/rust/PHASE-1-REPORT.md` |
| Phase scope | `.ai/rust/PHASE-1.md` |
| Evidence-mode code | `crates/mono_desktop/src/evidence.rs`, `worker.rs`, `main.rs` |
| CI workflow | `.github/workflows/rust-validation.yml` |
| Commits | 25f172d → f6c2ffd → 68ffeb3 → 1a4c486 |
| CI runs | 36238943132 → 36240861666 → 36241440052 (all recorded, incl. failures) |
| Artifacts | `rust-evidence-{Windows,Linux,macOS}` from the final run |

## Checklist item → evidence map (reviewer: verify each against artifacts)

| Checklist item | Evidence | Where |
| --- | --- | --- |
| Pencil / Eraser | Scripted steps 2–3, pixels verified | evidence JSON `steps` |
| Line | Step 4, live preview + stale-preview cleared | evidence JSON |
| Rectangle live preview | Step 5, outline + empty interior verified | evidence JSON |
| Zoom / Pan / Grid | Step 7, zoom 4→24, pan ±80/40 draw-mapped | evidence JSON |
| Undo / Redo one-gesture-one-step | Step 6, 4 gestures → zero → restored | evidence JSON |
| Fixture open | Step 9, rows equal pre-seeded fixture | evidence JSON |
| Save and reopen semantic parity | Step 10, save → parse → reopen equal | evidence JSON |
| Export | Step 10, bytes equal `to_vlsb()`, sha256 recorded | evidence JSON |
| Windows smoke | Local run `all_passed: true` (Intel UHD, GL 3.3); CI runner FAIL recorded as environment-limited | local JSON + run 36241440052 |
| macOS smoke | CI `all_passed: true` (Apple Software Renderer GL 4.1) | artifact |
| Linux X11 smoke | CI `all_passed: true` (llvmpipe, Xvfb, hard gate) | artifact |
| Linux Wayland smoke | CI `all_passed: true` (weston headless, soft gate) | artifact |
| Long tasks do not block UI | Worker churn ~2 s, frame percentiles recorded, mid-churn draw, no frame >1000 ms, all OS | evidence JSON `worker` + `frame_times_ms` |
| Workers terminate on close | Real `on_exit` path, stop+join 5 s timeout, 5–17 ms measured, all OS | evidence JSON `worker.close_path` |
| DPI 100/125/150/200 % | `set_pixels_per_point` probes, readback exact + draw-verified, all OS | evidence JSON `dpi.probes` |

## Specific questions the reviewer must rule on

1. **Scripted pointer evidence sufficiency.** The driver injects
   coordinates into the same `canvas_*` handlers the winit pointer path
   uses, inside the real event loop (real window/renderer/layout/file
   IO). No OS-level event injection is claimed. Does this satisfy the
   Gate 2 interaction requirement, or is OS-level injection required?
2. **Windows CI classification.** The GitHub-hosted Windows runner cannot
   create a GL 2.0+ context (`egui_glow requires opengl 2.0+`); the same
   binary passes locally (Intel UHD, GL 3.3, full report). The CI failure
   is recorded, never waived. Ruling requested: accept
   "environment-limited, evidenced locally", or require a renderer change
   before CI can go green?
3. **Frame-time thresholds.** Agreed in the implementation plan: churn
   window ≥10 frames, no frame >1000 ms, mid-churn draw completes; raw
   percentiles always reported alongside. Accept, or tighten?
4. **Vacuous-pass fix adequacy.** `all_passed` now requires
   `launch_error.is_none()` (regression test included, verified in CI run
   3). Any remaining aggregation gaps?

## Known limits (not claimed as passed)

- Save/Export remain validation artifacts under `target/`, not the V1
  project persistence or export contract.
- Renderer coverage is the runners' GPUs + llvmpipe; the office-machine
  GPU matrix is NOT RUN.
- Physical OLED compatibility is untested.
- Real mouse/IME/clipboard/file-picker/drag-drop behavior is NOT proven
  (Gate 2 capability probes remain open — proposed as the next step).
- Existing Python baseline red tests were not altered.

## Proposed next step (subject to this review's outcome)

1. This review: PASS / REWORK REQUIRED.
2. On PASS: Gate 2 remaining desktop capability probes — Chinese IME
   (highest risk, first), clipboard, file picker, drag-drop, shortcuts —
   as further self-driven evidence steps.
3. On REWORK: bounded remediation per the review's findings.

## Review result

(To be filled by the independent reviewer.)

- Verdict: PASS / REWORK REQUIRED
- Findings:
- Required changes (if REWORK):
