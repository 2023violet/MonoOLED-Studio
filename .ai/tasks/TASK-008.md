# TASK-008 — CLI machine-readable output and release discoverability

Status: VERIFY
Review Status: PENDING

## Goal

Close the two gaps found while comparing MonoOLED Studio's Automation API with
FirmwareSight's `fwsight` CLI: `validate`, `export` and `asset-audit` gain a
`--json` mode with the same exit codes as the text mode, and README/docs state
that the `mono` CLI ships inside every release package (including its per-platform
name) plus the exit-code contract. No Automation JSON, golden fixture or frozen
asset changes.

## Background

The project already has CLI + JSON-RPC dual形态: `apps/mono-cli` exposes
validate/export/simulate/batch-validate/handoff/asset-audit/c-header/bench/bridge,
and `tools/PACKAGE_RUST_RELEASE.py` ships `mono` alongside the GUI on Windows,
macOS and Linux. What was missing was machine-readable output (CI had to parse
human text) and an explicit note that the CLI is inside the downloaded package.

## Current Problem

- `validate`/`export`/`asset-audit` print human text only; a script must parse
  "PASS: 0 blocking finding(s), 3 total" to learn the result. `simulate` and
  `bench` already emit JSON/JSONL, so the gap is inconsistent.
- `README.md` shows CLI examples but never says the binary ships in the package,
  what it is called on each platform, or what the exit codes mean. A user reading
  the Releases page can reasonably conclude there is no CLI.

## Evidence

- `apps/mono-cli/src/main.rs:163-217` (`print_findings`, `cmd_validate`,
  `cmd_export`), `:336-358` (`cmd_asset_audit`), `:535-548` (exit codes)
- `tools/PACKAGE_RUST_RELEASE.py:51-57` (both binaries required),
  `.github/workflows/package.yml:55,69` (build + `mono.exe version`)
- `README.md:82-100` (Automation API and CLI section)

## Required Changes

1. Add `--json` to `Args` parsing as a valueless flag.
2. `validate --json` prints one JSON object: `command`, `ok`, `exit_code`,
   `blocking`, `total`, `findings[]` (`severity`, `code`, `message`,
   `element_id`, `blocking`).
3. `export --json` prints `command`, `ok`, `exit_code`, `output_dir`,
   `frame_count`, `frames[]` (`name`, `sha256`).
4. `asset-audit --json` prints `command`, `ok`, `exit_code`, `duplicates[][]`,
   `unused[]`, `invalid[]` (`path`, `error`).
5. Errors with `--json` still exit 2 and additionally print one JSON object with
   `ok: false` and `error: {code, message}`; stderr text stays unchanged.
6. Text mode output and every exit code stay exactly as today.
7. USAGE text documents `--json`.
8. README documents `--json`, the per-platform CLI location inside packages
   (Windows `mono.exe` in the zip, macOS `MonoOLED Studio.app/Contents/MacOS/mono`,
   Linux `monooled-cli`) and the exit codes 0/1/2.

## Out of Scope

No changes to Automation JSON, no new CLI subcommands, no version bump, no
release/tag/push (separate explicit authorization), no golden/test_asset edits.

## Constraints

- CI gates: fmt; clippy `-D warnings`; workspace tests; pytest; `cargo deny check`.
- Tests must write only to temp dirs; `test_assets` stays read-only.
- Exit codes are the contract: `0` pass, `1` blocking findings, `2` error.

## Allowed Files / Expected Area

- `apps/mono-cli/src/main.rs`
- `apps/mono-cli/tests/cli.rs` (new)
- `README.md`
- `.ai/tasks/TASK-008.md`, `.ai/CURRENT_STATE.md`

## Acceptance Criteria

1. `mono validate --json` on the frozen fixture exits 0 and prints a parseable
   JSON object whose `findings` length equals `total` and whose `blocking` equals
   the number of blocking findings.
2. `mono export --json` prints `output_dir`, `frame_count >= 1` and 64-hex
   SHA-256 values; the export directory is the requested one.
3. `mono asset-audit --json` prints `duplicates`, `unused` and `invalid` arrays.
4. A failing command with `--json` exits 2, prints `ok: false` and a non-empty
   `error.code` to stdout, and keeps the `ERROR:`/`FAIL:` stderr line.
5. Without `--json`, stdout is byte-identical in shape to today's text and exit
   codes are unchanged.
6. README states where the CLI binary lives in each package and documents
   `--json` and the exit codes.
7. Full gates pass; frozen assets untouched.

## Verification Plan

- `cargo test -p mono-cli` (new integration tests).
- Manual: `cargo run -p mono-cli -- validate --project test_assets/projects/curing_lite/project.oled.json --json`.
- Full: fmt, clippy, workspace tests, pytest, deny.

## Deliverables

Code, tests, and a Result section with actual commands/results.

## Result

Implemented; stopped at `VERIFY` (independent review owns `DONE`/`PASS`).

### What changed

- `apps/mono-cli/src/main.rs`: `--json` is now a valueless flag (`VALUELESS`
  also keeps `--allow-large-matrix`). `validate`, `export` and `asset-audit`
  branch to one compact JSON object on stdout; the text branches are unchanged
  byte for byte. `main` prints a JSON error object (plus the unchanged
  `ERROR:`/`FAIL:` stderr line) when the invocation carried `--json`. USAGE
  gained an `OUTPUT OPTIONS` section.
- `apps/mono-cli/tests/cli.rs` (new): five end-to-end tests against the built
  binary — validate totals/blocking consistency, export frames and 64-hex
  hashes with the requested output directory, asset-audit sections, exit 2 with
  parseable error JSON, and unchanged text mode.
- `README.md`: the CLI section now states where the binary lives in each package
  (Windows zip `mono.exe`, macOS `MonoOLED Studio.app/Contents/MacOS/mono`,
  Linux `monooled-cli`), documents `--json`, and states the 0/1/2 exit codes.

### Verification (run in this worktree)

- `cargo test -p mono-cli` — 5 integration tests pass (0 failed).
- `cargo run -p mono-cli -- validate --project test_assets/projects/curing_lite/project.oled.json --json`
  — exit 0, `{"command":"validate","ok":true,...,"total":3,...}` with three
  non-blocking `REQUIRED_ELEMENT_MISSING` findings.
- `cargo run -p mono-cli -- asset-audit --project ... --json` — exit 1 with a
  complete object (pre-existing finding: one RGB review image is not binary),
  proving `ok`/`exit_code` track the text-mode result.
- `cargo run -p mono-cli -- --help` — lists `OUTPUT OPTIONS`.

### Deviations and skipped checks

- Only the three commands named in the task gained `--json`; `batch-validate`,
  `handoff`, `c-header` and `simulate` keep their current output (`simulate`
  already streams JSONL, `bench` already prints JSON).
- No version bump or release in this task; a release needs a separate explicit
  authorization and a version/changelog update.

### Review status

Independent review is still unavailable (subagent dispatch has failed three
times: two model-queue errors, one daily usage limit). `DONE`/`PASS` remain with
an independent reviewer; the checks above are implementer-side evidence, not a
review verdict.
