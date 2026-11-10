# TASK-020 — Project Audit Fixes (2026-11-10)

Status: DONE
Review Status: PASS WITH MINOR NOTES (independent review 2026-11-10); every note fixed afterwards

## Goal

The user asked on 2026-11-10: read the whole project, find what is broken, inconsistent, inefficient or no longer needed, fix what is certain, and list the rest for review. Do not push, tag or release.

## Scope

Only changes whose correctness can be shown by a test, a build or a direct file check. Everything else is listed for the user under "Not fixed".

## Result

All results come from commands run on Windows 10 on branch `fix/audit-2026-11-10`, based on `main` 999a214 (2.4.2).

1. **Review panel without a baseline** (TASK-018 review M3): the summary line counted every lit pixel as changed ("100%") when the scene did not render at open. `review_diff` now returns a zero count, no change box and `diff.no_baseline`, as the drawer does. Test: `review_diff_says_when_there_is_no_baseline`.
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

## Review Status

**PASS WITH MINOR NOTES** (independent review 2026-11-10, fresh context, read-only). The reviewer re-ran all gates (fmt and clippy clean; tests 330 passed, 0 failed; pytest 36 passed, 1 skipped; deny ok; golden diff empty) and confirmed each claim: the zeroed count and box are read only inside the `has-baseline` branch of `review.slint`; `sha2` has no use anywhere in `mono-automation`; neither `spike/` nor `src/` exists or is produced; `f5e2653` fixed the refused rename and `a_refused_rename_keeps_the_page_open` pins it. No compatibility change.

Notes, all fixed afterwards:

- (Minor) `docs/README.md` claimed G6 evidence records every 2.x release; 2.2.0 and 2.2.1 are not there. Reworded.
- (Minor) The new test covered only the summary helper, not the call site's flag or the zeroed count and box. The whole decision now lives in `review_diff`, which the call site uses directly, and the test checks all three results.
- (Nit) A doc comment had moved onto the new test; moved back to the drawer test.
- (Nit) The bench docstring made an unmeasured claim on an unwrapped line; reworded and wrapped.
- (Nit) The `CHECK_GUI_TRUST.py` description left five checks out; it now lists them all.
- (Note, pre-existing) `diff.no_baseline` said the scene "did not render when it was opened", but the baseline is also taken on save (`App::save`). The en and zh texts now say "opened or last saved".

Gates after the fixes: fmt and clippy clean; tests 330 passed, 0 failed; pytest 36 passed, 1 skipped; deny ok; golden diff empty.
