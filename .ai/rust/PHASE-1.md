# Rust Phase 1 — Core and egui Pixel Slice

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
- .github/workflows/rust-validation.yml configures the Windows, Linux, and macOS validation matrix; remote CI execution is not yet run in this unpushed worktree.
- cargo test -p mono_desktop --locked: 4/4 PASS

## Remaining Gate

The next required gate is 3-OS evidence. Windows is the only live desktop
smoke run so far. macOS and Linux (Wayland/X11 separately) remain NOT RUN.
Before declaring the Pixel Slice accepted, record the target OS/toolchain,
renderer, DPI, interaction and save/export results. Fixture serialization and parser roundtrip are covered by unit tests;
direct GUI interaction evidence and reopen evidence through the running application
remain to be recorded.

No commit, push, PR, tag or release is performed by this phase.
