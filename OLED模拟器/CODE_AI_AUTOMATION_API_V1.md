# MonoOLED Studio Automation API 1.2

> Machine-readable source of truth: `AUTOMATION_API_V1.json`  
> Transport: in-process `StudioAutomationService` or localhost token-authenticated JSON-RPC  
> API version: `1.2.0`

## Purpose

Automation API 1.2 lets Code AI operate MonoOLED Studio by project/scene/state/pixel/font semantics rather than GUI coordinates. Canonical Renderer and Studio Exporter remain the only pixel/export truth.

API 1.2 is backward-compatible with API 1.1 and closes the next real graduation gaps discovered by the Curing-Lite ORTHO task: fail-closed cross-screen persistence, complete transaction contracts, version-consistent bridge discovery, matrix-size awareness, summary responses, and bounded long-running jobs.

## Recommended blind-Agent bootstrap

1. `automation.capabilities`
2. `automation.describe_method` for methods the Agent intends to call
3. `project.get_contract`
4. `scene.get_schema`
5. `state.get_schema`
6. `project.list_screens`
7. `project.list_assets`
8. `font.list`

The Agent should not read MonoOLED implementation code to guess public parameters.

## Project orchestration

`project.get`, `project.list_screens`, `project.open_screen`, `project.create_screen`, `project.duplicate_screen`, `project.rename_screen`, `project.delete_screen`, `project.save`, `project.save_all`.

## Scene / selection / layout

Scene CRUD, semantic selection, align/distribute/measure and Agent transactions are exposed through `scene.*`, `selection.*`, `layout.*`, `history.*`.

## Product state model — API 1.1+ (retained in 1.2)

### Read

- `state.get_schema`
- `state.list`
- `state.enumerate`

### Author / validate

- `state.validate_schema` — validate proposed schema without mutation.
- `state.set_schema` — atomic, revision-guarded root schema replacement; transaction-safe.
- `state.validate` — validate one concrete state against domains and relations.

Canonical schema shape:

```json
{
  "variables": {
    "total_cycles": {"type":"int","values":[3,5],"init":3},
    "current_cycle": {"type":"int","min":1,"max":5,"init":1}
  },
  "relations": [
    {"left":"current_cycle","operator":"<=","right":"total_cycles"}
  ]
}
```

Integer domains support either `min/max` or explicit `values`. Relations intentionally support only `<`, `<=`, `==`, `!=`, `>=`, `>` between named state variables. No script/eval rule language exists.

`state.enumerate`, `render.all_states`, `validate.all_states` consume the same legal-state rules; illegal relation combinations are excluded by Studio rather than filtered by Agent prompts.

## Pixel / asset lifecycle

The Agent can create blank PixelDocuments, edit pixel-exact content, save assets, and manage project-owned bitmaps through `pixel.*` and `asset.*`.

## Font

`font.*` exposes FontPack creation, discovery, glyph generation, glyph read/update and metrics. Since API 1.1 every Font lifecycle method publishes real required/optional parameter metadata and return contracts through `automation.capabilities`, `automation.describe_method`, and `AUTOMATION_API_V1.json` from the same production method registry.

For example `font.generate_glyphs` publicly describes `font_id`, `characters`, `font_path`, `font_size`, `threshold`, and `offset`, including required flags and numeric limits/defaults.

## Render / validation feedback

The Agent can request canonical framebuffer bytes and SHA-256, PNG, resolved geometry, pixel diff, validation findings, preview files and annotated previews.

## Export

Use Studio-owned export methods instead of reimplementing VLSB/C-header rules:

- `export.current`
- `export.all`
- `export.c_header`
- `export.font_pack`
- `export.code_ai_handoff`

## Revision / transaction contract

All writes may use `expected_revision`. Stale writes fail closed.

`state.set_schema` supports the existing Agent transaction mechanism. Rollback restores the prior root scene schema. When attached to Designer, a committed root state-schema transaction is recorded as one Designer undo step.

Project/asset/pixel/font filesystem lifecycle operations remain explicit and are not falsely advertised as part of the in-memory scene rollback.

## Cross-screen persistence — API 1.2

A successful Agent transaction commit is an in-memory authoring commit, **not** an implicit disk save. When the active Scene differs from its last persisted snapshot, `project.get.dirty` is true.

`project.open_screen` is fail-closed by default:

- dirty + no policy → `UNSAVED_CHANGES`;
- `save_current=true` → save succeeds first, then switch;
- `discard_current=true` → explicitly discard the in-memory Scene and switch;
- `save_current=true` with `discard_current=true` → invalid argument.

The same unsaved-change guard is used when an operation would replace/delete the active Scene. A failed save never changes the active screen.

## Long state-matrix operations — API 1.2

Use `state.count` before starting expensive state-matrix operations. `state.enumerate`, `render.all_states`, `validate.all_states`, `export.all`, and `export.code_ai_handoff` accept bounded matrix options and summary-oriented response flags.

For long operations, use the server-owned Job API:

- `job.start`
- `job.status`
- `job.result`
- `job.cancel`

V1.2 intentionally limits asynchronous jobs to `render.all_states`, `validate.all_states`, `export.all`, and `export.code_ai_handoff`. Jobs run against a Scene snapshot captured at start; later GUI edits do not silently change a running job's input. Cancellation is cooperative.

## Transaction discovery

`history.commit` and `history.rollback` explicitly publish the required `transaction` parameter. Code AI should never infer this field from implementation code or failed calls.

## Graduation boundary

The real Curing-Lite ORTHO blind graduation proved that Project/Screen/State/Font/Render/Validation/Export/Handoff authoring is viable through Automation alone. API 1.2 closes the reliability issues found during that graduation. Future Graduation runs must treat any direct JSON/PNG/FontPack/VLSB bypass as a failure of the test, not as an acceptable workaround.
