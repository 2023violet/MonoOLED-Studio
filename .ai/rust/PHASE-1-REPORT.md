# Rust Phase 1 Checkpoint Report

Status: VERIFY
Review Status: PENDING

## What this phase did

Built the minimal Rust workspace with mono_core, mono_cli, and mono_desktop. Added the egui Pixel Slice controls and deterministic Core fixture parity. Completed fixture Save and Open parsing with in-memory and real file roundtrips, legacy binary-row compatibility, and invalid-row validation.

## Tests and results

Python source baseline, isolated groups:

- 9 source groups passed.
- source_10 baseline red output:

    2 failed, 81 passed in 4.84s

    FAILED tests/test_v112_pixel_canvas_github_hygiene.py::test_github_root_markdown_is_curated
    FAILED tests/test_v120_generic_product_closure.py::test_v12_repository_layout_is_ascii_and_legacy_roots_removed

These failures are caused by pre-existing untracked root files BLOCKED.md, PROGRESS.md, and the non-ASCII document file in the main worktree. They are outside Rust V2 scope and were not changed.

Python Qt baseline:

- The first runner attempt failed before tests because isolated APPDATA hid the user-site pytest installation: No module named pytest.
- With the actual pytest user-site path supplied, the existing Qt tests ran in isolated processes.
- Complete Qt matrix evidence: 8 scales, 34 modules per scale, 272 module runs.
- 271 module runs passed.
- One existing red module run occurred at scale 2.0:

    FAILED tests/test_qt_micro_signature_v103.py::test_primary_corner_and_smart_guide_anchor_render_with_accent
    1 failed, 3 passed in 2.19s

- The continuation run independently completed the remaining 136 module runs at scales 2.0, 2.25, 2.5, and 3.0: 135 passed and 1 failed.

This is existing Python/Qt behavior and is outside Rust V2 scope.

Rust test-first evidence:

- Before implementation, cargo test -p mono_desktop --locked failed with:

    error[E0425]: cannot find function `fixture_bytes` in module `super`
    error[E0425]: cannot find function `parse_fixture` in module `super`

- Compatibility test red output before parser expansion:

    called `Result::unwrap()` on an `Err` value: "fixture row is not an array"

- After implementation:

    running 4 tests
    test tests::fixture_file_roundtrip_writes_and_reads_real_bytes ... ok
    test tests::fixture_parser_accepts_binary_string_rows ... ok
    test tests::fixture_parser_rejects_non_binary_rows ... ok
    test tests::fixture_save_payload_roundtrips_pixel_document ... ok
    test result: ok. 4 passed; 0 failed

- Export test-first red output before implementation:

    error[E0425]: cannot find function `write_export` in module `super`

- Export implementation green output:

    running 5 tests
    test tests::export_file_writes_the_document_vlsb_bytes ... ok
    test result: ok. 5 passed; 0 failed

Rust verification after implementation:

- cargo fmt --all -- --check: PASS
- cargo test --workspace --locked: PASS; mono_core 3 tests and mono_desktop 4 tests
- cargo clippy --workspace --all-targets --locked -- -D warnings: PASS
- cargo run --locked -p mono_cli -- test_assets/rust_v2/goldens.json: 13/13 PASS
- cargo build --workspace --release --locked: PASS
- Windows desktop launch smoke: started and stayed alive for 4 seconds, then was stopped by the runner.
- git diff --check: PASS

Workflow test-first evidence:

- First YAML assertion red output:

    AssertionError: literal backslash-n found in Linux install command

- Second shell assertion red output:

    AssertionError: missing shell line continuation after apt install

- Final workflow checks:

    workflow_yaml_and_shell_continuation: PASS
    workflow_structure: PASS

## Changed files

- Cargo.toml and Cargo.lock
- crates/mono_core
- crates/mono_cli
- crates/mono_desktop
- test_assets/rust_v2
- tests/test_rust_golden_baseline.py
- tools/VERIFY_RUST_GOLDENS.py
- .github/workflows/rust-validation.yml
- .ai/rust/ADR-001.md
- .ai/rust/VALIDATION_PLAN.md
- .ai/rust/PHASE-0.md
- .ai/rust/PHASE-1.md
- .ai/rust/PHASE-1-REPORT.md
- .ai/DECISIONS.md
- .ai/README.md
- .gitignore

## Scope self-check

The work remains within the approved Rust V2 Validation plan: Golden Baseline, mono_core parity, mono_cli parity, and the egui Pixel Slice. Fixture parsing was a planned Phase 1 requirement. The only intentional test-environment decision was supplying the installed pytest user-site path after the runner isolated APPDATA; no product or test contract was weakened.

## Remaining assumptions and risks

- GitHub Actions three-OS matrix is configured but has not run because the rust branch is not pushed.
- macOS and Linux GUI smoke evidence is missing.
- Live GUI interaction, reopen through the running application, long-task behavior, and worker shutdown evidence remain incomplete.
- Save and Export currently write validation artifacts under target and are not the V1 project/export contract.
- Existing Python baseline red tests remain unresolved and were not altered.

## Checkpoint

A local backup was created at:

C:\Temp\MonoOLED-Rust-Phase1-VERIFY-20260926.zip

No commit, push, PR, tag, or release was performed.
