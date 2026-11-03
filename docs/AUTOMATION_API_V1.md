# MonoOLED Studio Automation API 1.3

> Machine-readable source of truth: `AUTOMATION_API_V1.json`  
> Transport: in-process `StudioAutomationService` or localhost token-authenticated JSON-RPC  
> API version: `1.3.0`

## Purpose

Automation API 1.3 lets Code AI operate MonoOLED Studio by project/scene/state/pixel/font/output semantics rather than GUI coordinates. Canonical Renderer and the shared bitmap encoder remain the only pixel/export truth.

API 1.3 is additive and retains API 1.2 methods and byte behavior. In particular, `export.c_header`, `export.current`, `export.all`, and Code AI handoff output are unchanged when no new parameters are supplied and the scene passes the release gate (see [Release gate](#release-gate)).

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

`project.rename_screen` also moves the screen's annotations in `review/review.json` to the new id. If that file cannot be updated (for example it changed on disk), the call returns that error after the rename itself has already been applied; the response shape is unchanged.

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
- `export.bitmap_data`
- `export.font_data`
- `export.font_pack`
- `export.code_ai_handoff`

### Release gate

`export.current`, `export.all`, `export.c_header` and `export.code_ai_handoff` refuse to write files when validation reports a blocking finding (`BLOCKER` or `ERROR`) for the exported state(s). `export.c_header` honours the same gate as the other producers instead of rendering regardless of findings.

A blocked call returns JSON-RPC error `INVALID_REQUEST` and writes no export artefact: no header, no `golden/` or `reference/` output, and no handoff ZIP. `export.current`, `export.all` and `export.code_ai_handoff` still write the blocking report — `validation_report.md` next to the intended output, or `<zip>.validation.md` for a handoff — because the refusal has to be readable after the call returns. `export.c_header` writes no report: its error lists up to eight blockers, then "… and N more". `export.all` and `export.code_ai_handoff` validate states in matrix order and stop at the first blocking state; the report says how many states were checked (the gate is already decided). Clean matrices are still validated in full before anything is written. A directory an earlier successful export created is left as it was. Fix the findings (the validation report and `validate.*` methods name the element ids) and call again.

A scene member that resolves outside the project root is a blocking finding (`ASSET_PATH_ESCAPE`), so `export.current`, `export.all`, `export.c_header` and `export.code_ai_handoff` refuse such a scene; a scene that exported under 2.3.0 with `../` or an outside absolute path now needs its files moved into the project. It also stops rendering: `render.current`, the other methods that render the scene, and the current-scene source of `export.bitmap_data` return `INVALID_REQUEST`. `export.font_data` and `export.font_pack` take no scene members and are unaffected.

`export.bitmap_data` and the Output Workbench are **not** behind the gate: they can render the current scene into a file of their own. Changing that would alter API 1.3 behaviour and needs its own decision.

## Output profiles — API 1.3

`output.list_profiles`, `output.get_profile`, `output.upsert_profile`, `output.delete_profile`, and `output.set_active_profile` manage the portable `output_workbench.schema=1` project section. `output.preview` accepts either `profile_id` or an unsaved `profile` draft and returns a byte count, SHA-256, bounded text/hex preview, truncation flags, and index summary without writing files.

`export.bitmap_data` accepts `current_scene`, `pixel_document`, or `current_selection` sources. `export.font_data` applies the same encoder to FontPack glyphs and can return a sidecar index path and SHA-256. File writes remain confined to the project root. See `OUTPUT_WORKBENCH.md` for exact traversal and padding semantics.

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
- `job.release` — explicitly release a terminal result after the caller has consumed it.

V1.2 intentionally limits asynchronous jobs to `render.all_states`, `validate.all_states`, `export.all`, and `export.code_ai_handoff`. Jobs run against a Scene snapshot captured at start; later GUI edits do not silently change a running job's input. Cancellation is cooperative. The server caps concurrent active jobs and retains only a bounded number of terminal results; running jobs are never evicted, and retention is ordered by completion time rather than start time.


## Long-session lifecycle hardening

Automation state is intentionally bounded for long-lived Agent sessions:

- only a bounded number of Scene transactions may be open simultaneously; callers must commit or rollback before opening more;
- `session.events` uses an absolute `since` cursor and returns `retained_from`, `dropped_before`, and `next_cursor`; old events may be compacted from memory rather than retained forever;
- in-memory PixelDocuments are capped; `pixel.close` releases a clean document, while a dirty document requires an explicit `discard=true` after the caller has decided not to save it;
- `render.all_states`, `validate.all_states` and `export.all` called through the bridge are checked (revision, permission) when dequeued and then computed on a worker thread from a snapshot of the scene, so the desktop UI stays responsive. The response is the same as an in-process call; inside a transaction they run inline.
- the desktop bridge may return `TIMEOUT` only while a request is still queued. Once the UI thread has claimed a request, the transport waits for the real response so a mutating command cannot execute after the caller was told it timed out.

## Transaction discovery

`history.commit` and `history.rollback` explicitly publish the required `transaction` parameter. Code AI should never infer this field from implementation code or failed calls.

## Graduation boundary

The real Curing-Lite ORTHO blind graduation proved that Project/Screen/State/Font/Render/Validation/Export/Handoff authoring is viable through Automation alone. API 1.2 closes the reliability issues found during that graduation. Future Graduation runs must treat any direct JSON/PNG/FontPack/VLSB bypass as a failure of the test, not as an acceptable workaround.
