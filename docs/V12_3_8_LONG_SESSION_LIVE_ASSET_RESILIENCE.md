# V12.3.8 Long-Session & Live-Asset Resilience Hardening

V12.3.8 keeps the V12.3.7 Windows Release Integrity chain intact and hardens long-running editor sessions plus live asset workflows. It does not change the project or scene schema.

## Scope

- Session JSONL startup sequence recovery is streaming and resumes from the highest valid sequence found in an existing log.
- Session Markdown generation streams the JSONL source into a sibling temporary file and atomically replaces the final report.
- Session-log disk failures enter an observable degraded state instead of turning a successful editor mutation into a user-visible operation failure.
- `RenderResources` bitmap/font/font-pack decode caches are bounded LRU caches; cache hits refresh recency and stale entries are evicted deterministically.
- Font-pack resource hashing validates that every glyph asset resolves inside the pack before any glyph bytes are read.
- Asset Library live scans skip project-external symlink/junction entries and tolerate files disappearing during an in-flight scan, allowing the rest of the library to remain usable.

## Product invariants

1. Diagnostic/session evidence must never invalidate an already-successful editor action.
2. Long-running sessions must have bounded in-memory decode caches.
3. Cache layers may not weaken model-layer path-containment rules.
4. A single transient or unsafe asset entry may not take down the whole live asset scan.
5. Session event sequence numbers remain monotonic after crash-corrupted or manually repaired JSONL logs.

## Release identity

- Source version: `12.3.8`
- Git tag: `v12.3.8`
- Windows asset: `MonoOLEDStudio_v12.3.8_Windows_x64.zip`
- Checksum: `MonoOLEDStudio_v12.3.8_Windows_x64.zip.sha256`
- The V12.3.7 tag/commit/provenance and immutable-release gates remain mandatory.
