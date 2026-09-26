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
Before declaring the Pixel Slice accepted, record the target OS/toolchain,
renderer, DPI, interaction, save/export, long-task, and worker-shutdown results.
Linux Wayland and X11 are not separately exercised. Fixture serialization and
parser roundtrip are covered by unit tests; direct GUI interaction and reopen
evidence through the running application remain to be recorded.

Status remains VERIFY and Review Status remains PENDING. No PR, tag, or release
was created by this phase.
