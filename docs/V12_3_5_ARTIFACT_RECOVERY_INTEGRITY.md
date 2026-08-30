# V12.3.5 Artifact & Recovery Integrity Hardening

V12.3.5 is an autonomous integrity pass on top of V12.3.4. The goal is not another visual redesign. It closes remaining gaps where generated artifacts, recovery state, or auxiliary project state could become misleading or partially corrupted even though the core Scene editor remained functional.

## Priority findings

### P0 — Cross-platform export path safety

`export_scene()` now validates every frame name before creating output directories. Path separators, dot paths, Windows-reserved device names, invalid Windows filename characters, control characters, trailing dots/spaces, non-string names, and case-insensitive collisions such as `HOME` / `home` are rejected before output begins.

This prevents generated Golden/reference paths from escaping or colliding on Windows.

### P0 — Existing deliverables survive failed replacement

The following outputs now use temporary-file + flush/fsync + atomic replace semantics where they previously wrote directly to the destination:

- Golden `.bin` frames
- generated C headers
- Handoff ZIP packages
- Template Library JSON
- Font Generator glyph PNG/manifest/header outputs
- Batch Validation Markdown
- Asset Audit JSON/Markdown
- Session Markdown export

A failed replace therefore leaves the prior successful destination intact instead of truncating it.

### P1 — Repeat export no longer leaves stale frame truth

After a successful export, the managed `golden/` and `reference/` trees are reconciled against the current frame set. Frames from previous exports, including legacy nested paths produced by older unsafe naming behavior, are removed only after the new export completed successfully.

### P1 — Font Generator owns only what its manifest owns

A new generation pass removes glyph PNGs only when the previous `glyph_manifest.json` explicitly identified those files as managed outputs. Files that merely look like `U+XXXX.png` but were not owned by the previous manifest are preserved.

Glyph rasterization completes in memory before any output is committed, so a rendering failure does not partially modify the previous output set.

### P1 — Corrupt Template Library cannot block the project

A malformed or semantically invalid `.oled/templates.json` is copied to:

`.oled/quarantine/templates.corrupt.<timestamp>.json`

The project then continues with an empty Template Library. Auxiliary template state can no longer prevent the primary editor from opening.

Template save failure also rolls the in-memory library back to the last persisted state.

### P1 — Autosave retention is best-effort, snapshot creation remains authoritative

If an old recovery point is busy or cannot be deleted, a newly written autosave remains a successful autosave. Adjusting the retention count likewise does not fail solely because an old snapshot is temporarily undeletable.

If source/snapshot file metadata becomes temporarily unavailable while deciding whether to prompt for recovery, the recovery candidate is preserved rather than allowing an OS metadata race to escape into the UI.

### P2 — Session logging cannot be broken by its UI mirror

The JSONL session log is authoritative. A failure in the optional UI callback no longer propagates back into the edit operation after the record has already been durably written.

## Regression contract

`tests/test_v1235_artifact_integrity.py` covers:

- unsafe and case-colliding export frame names
- stale direct and legacy nested export artifacts
- Golden and C-header replace failures
- Handoff ZIP packaging failure
- Template save rollback and corrupt-library quarantine
- Font Generator stale ownership and generation failure isolation
- Autosave retention/pruning and metadata races
- Session callback isolation
- atomic Session/Batch Validation/Asset Audit report replacement

## Release identity

- Source version: `12.3.5`
- Git tag: `v12.3.5`
- Windows asset: `MonoOLEDStudio_v12.3.5_Windows_x64.zip`
- Windows checksum: `MonoOLEDStudio_v12.3.5_Windows_x64.zip.sha256`

V12.3.1 Settings Real-Qt/DPI/soak gates, V12.3.2 UX/data-safety work, V12.3.3 resilience hardening, and V12.3.4 autonomous transactional/editor quality hardening remain cumulative release requirements.
