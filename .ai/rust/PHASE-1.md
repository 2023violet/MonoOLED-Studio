# Rust Phase 1 - Core and egui Pixel Slice

Status: VERIFY
Review Status: PENDING

## Goal

Create the smallest Rust workspace that proves deterministic Core behavior and
an operational egui Pixel Studio slice without expanding into the full V1 UI.

## Implemented

- \`mono_core\`: deterministic bitmap encoding, VLSB framebuffer, built-in
  5x7 glyph fixture behavior, glyph composition, Legacy Pixel C export, and
  \`PixelDocument\` gesture model.
- \`PixelDocument\`: Pencil, Eraser, Line, Rectangle outline preview, one
  undo step per gesture, redo, cancellation boundary, and VLSB export.
- \`mono_cli\`: reads the language-neutral \`goldens.json\`, computes actual
  Core results and SHA-256 values, and exits nonzero on mismatch.
- \`mono_desktop\`: eframe/egui desktop slice with Pencil, Eraser, Line,
  Rectangle live preview, Grid, Zoom, middle-button Pan, Undo, Redo, Save,
  and Export controls.
- Fixture serialization/parser tests cover in-memory and real file Save -> Open
  roundtrip, legacy binary string rows, and invalid rows.
- \`Cargo.lock\`: dependency graph frozen for the workspace.
- \`target/\`: ignored build output.

## Scope boundaries

This phase does not claim complete V1 compatibility. It does not include
complete project persistence or migration, scene rendering, Font Studio,
DeviceSession, protocol frames, Serial/HID, Tokio, automatic updates, cloud
features, or three-OS evidence.

Save currently writes a small validation fixture under \`target/\`; Export
writes VLSB bytes under \`target/\`. These actions prove the slice boundary and
are not yet the V1 project/export contract.

## Verification

- \`cargo fmt --all -- --check\`: PASS
- \`cargo test --workspace\`: PASS
- \`cargo clippy --workspace --all-targets -- -D warnings\`: PASS
- \`cargo build --workspace --release\`: PASS
- \`cargo run -p mono_cli -- test_assets\\\\rust_v2\\\\goldens.json\`: 13/13 PASS
- Windows desktop launch smoke: process started and remained alive for 4
  seconds; the smoke process was then terminated by the runner.
- Python Golden verifier and focused V1 tests remain PASS from Phase 0.
- GitHub Actions run 36212314032 passed on windows-latest, ubuntu-latest, and macos-latest. The matrix covered fmt, workspace tests, clippy, release compilation, and mono_cli Golden parity.
- cargo test -p mono_desktop --locked: 5/5 PASS

## Remaining Gate

The three-OS build, test, lint, release, and CLI parity gate is complete.
Scripted GUI interaction evidence is now recorded in
[PHASE-1-EVIDENCE.md](PHASE-1-EVIDENCE.md): macOS, Linux X11, and Linux
Wayland (weston headless) CI runs and a local Windows run all report
`all_passed: true` with DPI probes, frame-time percentiles, worker churn,
and bounded close-path shutdown. The GitHub-hosted Windows runner cannot
create a GL 2.0+ context; that failure is recorded as an environment
limit, not waived. Independent review of the evidence remains open.

Status remains VERIFY and Review Status remains PENDING. No PR, tag, or release
was created by this phase.
