# Rust V2 Validation Plan

Decision: [Rust ADR-001](ADR-001.md) — Accepted for Validation
Current execution scope: [Phase 1](PHASE-1.md) — Core and egui Pixel Slice
Full migration: NOT APPROVED

## Gate 0 — Golden Baseline

Freeze language-neutral inputs and Python V1 expected results. Verification
reads stored expectations; it never regenerates or updates them on failure.
Record the reference commit, source blob identities, environment and comparison
rules. Expected-value changes require an explicit compatibility review.

Initial batch:
- Four bit-axis/group-order combinations × two bit orders, using the existing
  independent literal goldens in `tests/test_bitmap_encoding.py`.
- Inverted polarity including padding bits.
- VLSB page boundary and clipped OR mask.
- Built-in 5×7 font pixels, baseline, advance and stored glyph roundtrip.
- Legacy schema-1 project, read-only default profile, semantic save roundtrip.
- Binary bytes plus deterministic legacy C-header formatting.

Run `python tools/VERIFY_RUST_GOLDENS.py` and the focused Python tests.
These are initial coverage, not proof of all V1 compatibility. Before porting
additional behavior, extend fixtures for that behavior (invalid inputs, gestures,
save failure recovery, external edits, font indices, scene rendering, etc.).
Protocol frames are deferred until an actual protocol and reference exist.

### Comparison contract

- Bitmaps: exact dimensions and 0/1 row strings.
- Encoding: exact bytes (lowercase hex), count, padded dimensions, SHA-256 of bytes.
- Font: exact stored pixels and integer metrics, not PNG compressed file hashes.
- Project: parsed JSON semantic object, screen paths remain relative; no broad
  path rewriting or stripping fields. JSON key order/indentation/CRLF are not
  semantic. Opening legacy projects must not rewrite their bytes.
- Export: exact bytes; exact text only for the explicitly frozen deterministic
  legacy C-header profile, UTF-8 with its specified LF convention.
- Canonical JSON in tests: sorted keys, UTF-8, compact separators, no ASCII
  escaping; object key order is irrelevant, array order and all values matter.
- Unspecified metadata is not silently ignored; add an explicit per-format rule.

Data goldens and Visual goldens are distinct. Pixel truth is established now;
grid, selection and fixed AppState renderer images are added at Gate 2. Compare
OLED pixels/coordinates strictly. Define scoped tolerance for OS font/UI chrome
before collecting images; never let that tolerance hide canvas regressions.

## Gate 1 — Rust Core

Only after Phase 0 evidence is reviewed, create the minimal workspace:
`mono_core`, `mono_cli`, `mono_desktop`. Real implementation initially belongs
in Core; CLI loads the same fixtures and reports actual output/hash with nonzero
exit on mismatch. Do not embed expected outputs as the Rust implementation.
The desktop crate may initially only launch.

Start three-platform CI with the first Rust crate. Build/test evidence and
interactive smoke evidence are recorded separately. Python reference and Rust
must consume the same versioned inputs and compare the same expectations.
No Rust business code is part of the current Phase 0 change.

## Gate 2 — egui Pixel Slice

Build the risky interactions first: drag responsiveness, line drawing,
rectangle preview before release, zoom/pan, grid and gesture-sized undo/redo.
Opening, save/reopen and export must work on real fixture data.
Grid, zoom and theme must never change exported pixels.

Before declaring UX parity, record the V1 baseline and Rust results on identical
fixtures, dimensions, hardware, DPI and scripted gesture traces. Report input
latency/frame stalls and long-task responsiveness; agree thresholds before
evaluating the Rust results. “No obvious lag” alone is insufficient evidence.
Test cancellation and shutdown during work; document bounded channels, ownership
and worker termination. Do not require an invented 10× performance target.

Desktop capability probes include clipboard, Chinese IME, font loading,
file picker, drag/drop, shortcuts and DPI 100/125/150/200%. Probe these before
framework acceptance without building full Settings/Font Studio.

## Gate 3 — 3-OS Gate

Each platform must build, launch, open fixture, edit, undo/redo, save/reopen and
export. Record OS/toolchain/dependency versions, hardware, renderer, commands,
logs and exact fixture IDs. A Windows run is not macOS/Linux evidence.

Linux Wayland and X11 must be recorded separately. Evaluate wgpu on the target
office-machine matrix: old Intel integrated graphics, AMD, NVIDIA, Apple Silicon,
Windows RDP, VM and Linux Mesa. Missing hardware remains NOT RUN. If renderer
coverage fails, investigate supported renderer alternatives before expanding
scope. Signing/notarization/installers belong to a later release gate; smoke
success does not imply distribution readiness or physical OLED validation.

## Frozen Phase 1 exit checklist

- [ ] Python golden fixtures reviewed and accepted.
- [ ] Rust Core matches key fixtures byte-for-byte / semantically as specified.
- [ ] mono_cli independently runs fixtures and prints actual hashes.
- [ ] egui Pixel Studio vertical slice.
- [ ] Pencil / Eraser.
- [ ] Line.
- [ ] Rectangle live preview before mouse release.
- [ ] Zoom / Pan / Grid.
- [ ] Undo / Redo (one continuous gesture = one undo step).
- [ ] Fixture open.
- [ ] Save and reopen with semantic parity.
- [ ] Export.
- [ ] Windows smoke.
- [ ] macOS smoke.
- [ ] Linux smoke, including stated Wayland/X11 coverage.
- [ ] Long tasks do not block the UI.
- [ ] Workers terminate correctly on application close.

### Explicit exclusions

Full UI redesign; complete Font Studio; complete device management; full
Serial/HID integration; Tokio; automatic updates; cloud features; parallel
GPUI implementation; parallel Slint implementation.

## Review and exit

Go: all agreed gate evidence is present and compatible; user may then authorize
expanded migration. Adjust: concrete gate failure with bounded remediation.
Stop: unacceptable compatibility, desktop capability, hardware coverage or cost.
No missing platform/hardware result can be relabelled PASS or silently waived.

Implementation reports end at VERIFY / PENDING. Independent review owns PASS
and closure. No commit, push, PR, tag or release is authorized by this plan.
Python regression remains targeted or uses the existing isolated group runner;
never run the full tests directory in a single pytest process.
