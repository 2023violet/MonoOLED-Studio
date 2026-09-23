# TASK-003 — Add Minimal Read-Only AI Context Builder

Status: VERIFY
Review Status: PENDING

## Goal

Add a small, standard-library-only, read-only context builder that gives a cold-start AI a disposable navigation packet without creating a second authority file or exposing local file contents, credentials, or remote URLs.

## Background

Phase 2 is closed after TASK-002. A fresh handoff currently requires repeated manual reads of the control plane, Git state, version, and handoff documentation. No equivalent context builder or generated context file exists in the repository.

## Initial Implementation Boundary

During the TASK-003 local implementation and verification phase, staging, commit, push, PR, tag, and release actions were not authorized. The implementation was required to stop at `Status: VERIFY` and `Review Status: PENDING`.

## Review-baseline Publication Authorization

After TASK-003 reached `VERIFY / PENDING`, the user separately authorized creation of a GitHub Independent Review Baseline. This publication authorization is limited to the task's formal seven-file Review Scope. `.ai/GENERATED_CONTEXT.md` is derived and must not enter the commit; `BLOCKED.md` and `PROGRESS.md` are protected local records and must not enter the commit. Publication is limited to a normal fast-forward push to `origin/main`. Force push, force-with-lease, amend, rebase, merge, PR, tag, release, history rewrite, and new branch operations are not authorized. The resulting commit SHA will be recorded only in subsequent review or closure history after the commit succeeds.

## Current Problem and Failure Evidence

- Cold start requires many separate manual reads and Git queries.
- Repository search found no `GENERATED_CONTEXT`, `AI_CONTEXT`, `context builder`, or `build_ai_context` implementation.
- `.ai/GENERATED_CONTEXT.md` did not exist and was not ignored before this task.
- The generated packet must remain a derived navigation cache; authoritative sources remain live Git, source, tests, `AGENTS.md`, active TASK, `.ai/` authority, and `docs/AI_HANDOFF.md` in their documented order.

## Required Changes

1. Add `tools/BUILD_AI_CONTEXT.py` with a read-only, stdlib-only implementation.
2. Add isolated tests in `tests/test_ai_context_builder.py`.
3. Ignore `.ai/GENERATED_CONTEXT.md` in `.gitignore`.
4. Add minimal navigation notes to `AGENTS.md` and `.ai/README.md`.
5. Move `.ai/CURRENT_STATE.md` to Phase 3 with TASK-003 active.
6. Generate this TASK contract and finish at `VERIFY / PENDING` only.

## Architecture

Authoritative sources → read-only builder → `.ai/GENERATED_CONTEXT.md` (derived navigation cache). The cache is disposable, stale-able, ignored, and never authoritative.

## Out of Scope

No Drive, MCP, Cloudflare, ChatGPT plugin, GitHub API, remote shell, production data bridge, automatic TASK/decision edits, commits, pushes, PRs, reviews, PASS/DONE closure, version/release changes, popup changes, or product behavior changes. Do not create TASK-004 or another context authority file.

## Protected Existing Work

`BLOCKED.md` and `PROGRESS.md` are pre-existing local work records. They must not be read for content, modified, staged, committed, deleted, or included in the generated packet. Their SHA-256 values are recorded in the implementation report and must match after verification.

## Constraints

- Python 3.13 and Windows-compatible standard library only.
- No network access, credentials, environment dumps, shell profiles, SSH/browser/account access, GitHub API, remote URLs, diffs, object contents, or untracked file contents.
- Git commands are read-only and use argument lists without a shell.
- Output is rendered in memory and written with a UTF-8 LF temporary file followed by atomic replace.
- `--stdout` writes only the packet to stdout and does not create the default file.
- `--recent` accepts 1–20 and defaults to 5; `--output` and `--repo-root` are repository-bound.
- Missing required sources, missing Git repository, detached HEAD, and malformed Git state fail clearly without traceback garbage. Missing upstream and missing active TASK are nonfatal.

## Allowed Files / Expected Area

- `tools/BUILD_AI_CONTEXT.py`
- `tests/test_ai_context_builder.py`
- `.gitignore`
- `AGENTS.md`
- `.ai/README.md`
- `.ai/CURRENT_STATE.md`
- `.ai/tasks/TASK-003.md`

`.ai/GENERATED_CONTEXT.md` may be generated locally for verification, but is ignored and is not source scope.

## Acceptance Criteria

1. The builder runs from the repository root with `python tools/BUILD_AI_CONTEXT.py`.
2. The builder is Python 3.13 compatible and uses only the standard library.
3. The default output is `.ai/GENERATED_CONTEXT.md`.
4. The default output is ignored by Git and is not a committed authority file.
5. `--stdout` emits the packet without creating the default output.
6. `--output` writes a repository-bound custom packet atomically.
7. `--recent` defaults to 5 and rejects values outside 1–20.
8. `--repo-root` supports isolated temporary Git repositories while enforcing the repository boundary.
9. The header contains `# GENERATED AI CONTEXT`, `GENERATED FILE — DERIVED CONTEXT ONLY`, `NOT AUTHORITATIVE`, and `REGENERATE BEFORE USE`.
10. The packet warns that live authoritative sources win on conflict.
11. The packet contains project name, product version, and repository-relative context without absolute user paths.
12. The packet contains branch and full HEAD.
13. The packet contains upstream name and ahead/behind when configured.
14. Missing upstream is reported as `NOT CONFIGURED` without failure.
15. Staged, modified tracked, and untracked paths are listed by path/status only.
16. File contents, secrets, environment values, and untracked payloads never enter the packet.
17. Workflow phase, last completed task, active task, independent review, and next action are summarized from CURRENT_STATE.
18. The active TASK path is included when present without copying the whole TASK.
19. Missing active TASK is reported as `NONE` without failure.
20. Confirmed ADR number/title and a short summary are included from DECISIONS.
21. Only explicitly recorded deferred/unresolved issues are included; no issue is invented.
22. Recent commits contain SHA and subject only.
23. Recommended next reads include AGENTS, `.ai/README.md`, DECISIONS, CURRENT_STATE, active TASK, and `docs/AI_HANDOFF.md`.
24. The packet states that it is an index and not a substitute for authority.
25. Missing required Git, VERSION, CURRENT_STATE, or DECISIONS inputs fail clearly without traceback garbage.
26. Detached HEAD is rejected clearly.
27. Output writes use a temporary UTF-8 LF file and atomic replacement.
28. The builder performs no network access and imports no network or third-party dependency.
29. Tests cover the snapshot, status classification, leakage prevention, no-upstream/no-active-task cases, stdout/default output, warning, ignore rule, source preservation, and dependency boundary.
30. TASK-003 ends at `Status: VERIFY` and `Review Status: PENDING`; no commit, push, PR, closure, or full regression is performed.

## Verification Plan

- `python -m pytest tests\test_ai_context_builder.py -q`
- `python tools\BUILD_AI_CONTEXT.py --stdout`
- `python tools\BUILD_AI_CONTEXT.py`
- `Test-Path .ai\GENERATED_CONTEXT.md`
- `git check-ignore -v .ai\GENERATED_CONTEXT.md`
- `git status --short --branch`
- `git diff --check`
- Re-check protected SHA-256 values.

Do not run the entire `tests/` collection or `tests/test_v112_pixel_canvas_github_hygiene.py`; local `BLOCKED.md` and `PROGRESS.md` intentionally trigger a known root Markdown hygiene conflict.

## Result

Implemented the minimal read-only builder and isolated regression coverage.

- Live baseline remained `a143ee673fb952fd0503eee6d1cda74e7306ae7a` on `main`, synchronized with `origin/main` (`0/0`); no commit or push was performed.
- `python -m pytest tests\test_ai_context_builder.py -q`: 8 passed.
- `python tools\BUILD_AI_CONTEXT.py --stdout`: passed; no default generated file was created by the stdout mode.
- `python tools\BUILD_AI_CONTEXT.py`: passed; `.ai/GENERATED_CONTEXT.md` was created by atomic replacement and is ignored by Git.
- `git check-ignore -v .ai\GENERATED_CONTEXT.md`: passed.
- `git diff --check`: passed with only the repository's normal LF-to-CRLF advisory warnings.
- Protected SHA-256 values were unchanged: `BLOCKED.md` `79853ED896432CA943ACE99407347C390BF3690C2336B57F58B1ACD3D6C1CCA6`; `PROGRESS.md` `68618B3B10DB24A32B08F1EA60D1AD025C8F29666890266CD8893990E0623CAF`.
- The generated packet contains no file contents, secret markers, environment dump, credential data, or remote URL. It reports only repository-relative paths and status.
- Full regression, `tests/test_v112_pixel_canvas_github_hygiene.py`, build, release, commit, push, PR, and independent review were not run in this task.

Deleting `.ai/GENERATED_CONTEXT.md` loses no authoritative information; it only removes a disposable derived index that can be regenerated.

## Review Status

PENDING — independent review is required before DONE/PASS.
