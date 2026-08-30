# V12.3.9 Automation Lifecycle Integrity Hardening

## Scope

V12.3.9 hardens the long-lived Automation/Agent lifecycle without changing the canonical Scene/Renderer/Exporter model. The pass targets bounded server memory, deterministic timeout semantics, resource ownership, and explicit release paths.

## Frozen invariants

- A localhost JSON-RPC request may return `TIMEOUT` only while it is still queued. If the UI thread has claimed the request, the caller waits for the real result so a mutating command cannot execute after the client was told it timed out.
- Server-owned Automation jobs have a bounded active-job count and a bounded terminal-result retention count. Running jobs are never evicted; terminal retention is ordered by completion time.
- `job.release` explicitly releases one terminal result after the client has consumed it. Active jobs cannot be released.
- Active Scene transactions are capped because each transaction owns a full Scene snapshot. Callers must commit or rollback before opening more.
- `session.events` is a bounded event ring with an absolute cursor. Responses publish `retained_from`, `dropped_before`, and `next_cursor` so event compaction is explicit rather than silent.
- Agent-owned PixelDocuments are capped. `pixel.close` releases them; dirty documents fail closed unless the caller explicitly chooses `discard=true`.

## Default lifecycle budgets

- active Automation jobs: 4
- retained terminal jobs: 16
- active Scene transactions: 16
- retained semantic events: 4096
- open Agent PixelDocuments: 64

These are safety ceilings, not target operating levels. Long-running clients should release jobs and PixelDocuments as soon as they are no longer needed.

## Verification

`tests/test_v1239_automation_lifecycle_integrity.py` is the release regression for this pass. It covers timeout/claim races, bounded job retention, active-job caps, explicit job release, transaction caps, bounded event cursors, and PixelDocument close/discard semantics.
