# TASK-020 — Project Audit Fixes (2026-11-10)

Status: VERIFY
Review Status: PENDING (no independent review yet)

## Goal

The user asked on 2026-11-10: read the whole project, find what is broken, inconsistent, inefficient or no longer needed, fix what is certain, and list the rest for review. Do not push, tag or release.

## Scope

Only changes whose correctness can be shown by a test, a build or a direct file check. Everything else is listed for the user under "Not fixed".

## Result

All results come from commands run on Windows 10 on branch `fix/audit-2026-11-10`, based on `main` 999a214 (2.4.2).

1. **Review panel without a baseline** (TASK-018 review M3): the summary line counted every lit pixel as changed ("100%") when the scene did not render at open. `review_summary` now says `diff.no_baseline`, as the drawer does, and the changed count and box are zero. Test: `review_summary_says_when_there_is_no_baseline`.
2. **Unused dependency**: `mono-automation` declared `sha2` but hashes through `mono_project::resources::hex_digest`. Removed; `Cargo.lock` loses one line, no package changes.
3. **Stale or missing documentation**:
   - `README.md`: "2.3.0 不模拟…" is now version-neutral; the documentation table lists `docs/REVIEW_PACK.md`.
   - `docs/README.md`: stray blank line removed, G1 listed before G2, G6 evidence described as the 2.x release record.
   - `tools/README.md`: `BENCH_DESIGNER_PROJECT.py` was missing; `CHECK_GUI_TRUST.py` described only the 2.0.3 checks and said it needs a debug build.
   - `tools/BENCH_DESIGNER_PROJECT.py`: said `digits` take the scratch-render geometry path, which TASK-018 removed.
4. **`.gitignore`**: entries for `spike/` and `src/reports/`, neither of which exists since G6, removed.
5. **`.ai/CURRENT_STATE.md`**: TASK-011's line still described the refused-rename defect as open; it was fixed in `f5e2653`.

### Gates

- `cargo fmt --all -- --check`: clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings`: clean.
- `cargo test --workspace --locked --no-fail-fast`: 30 groups, 330 passed, 0 failed.
- `python -m pytest tools/tests -q`: 36 passed, 1 skipped.
- `cargo deny check`: ok.
- `git diff main -- fixtures/golden test_assets`: empty.

### Not fixed (listed for the user)

Behaviour or policy changes that need a decision, and checks that need CI or a person; see the audit report in the session that produced this TASK.
