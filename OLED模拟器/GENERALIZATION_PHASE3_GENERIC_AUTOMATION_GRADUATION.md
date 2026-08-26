# V9 Phase 3: Generic Project Code AI Automation Graduation

Phase 3 validates the complete Generic Project workflow through the public Automation API only.
It starts from an empty 128x32 project, creates `generic_status` and `generic_detail` screens,
applies the same four-variable state schema, creates a FontPack and a 1-bit bitmap, adds scene
elements, renders and validates the deterministic matrix, exports and creates a Code AI handoff,
then saves, reopens, and checks the persisted scene and render truth.

## Public API-only boundary

The graduation test discovers the API with `automation.capabilities` and
`automation.describe_method`. It does not read implementation files to guess parameters and it
does not write Scene JSON, FontPack manifests, or PNG files directly. A failure is recorded as an
`blocked_api_step` with the method, duration, revision, active screen, and stable error summary.
No new Automation method is introduced by this phase; the contract remains API `1.2.0` with 82
methods.

## Fixture and matrix

Both screens use the declaration-ordered schema `page`, `channel`, `level`, `alarm`. The existing
representative policy retains all four ranged `channel` values, so this fixture produces 80 cases
for both `representative` and `full`; this is observed Phase 2 behavior, not a new matrix policy.
The renderer remains canonical and each framebuffer is 512 bytes for the 128x32 canvas.

## Evidence and validation boundary

`tests/run_v9_phase3_generic_graduation.py` writes a machine-readable JSON report and a Markdown
summary into an external evidence directory. The report distinguishes observed passes, API
blockers, and unverified work. Windows Real-Qt deep validation is not rerun because this phase
does not modify the Windows builder, PyInstaller, QPA/DPI, native Qt interaction, renderer,
framebuffer, codec, or release chain. It must be triggered if any of those boundaries change or a
platform-specific failure appears.

The engineering result format is:

```text
Phase 3 GA Release Gates = PASS / FAIL
Known blockers = <count>
Known P0/P1 = <count>
Evidence confidence = High / Medium / Low
```

This phase does not declare a V9 release and does not alter V8.4.4 sealed delivery content.
