# MonoOLED Studio 8.4.2 — Automation Reliability & GA Closure

## Scope

V8.4.2 is a narrow reliability release driven by the real Curing-Lite ORTHO blind graduation. It does not redesign Desktop UI, Renderer semantics, VLSB, Golden frames, clinical assets, Pixel Studio or Font Lab.

The graduation proved that Code AI can create multi-screen OLED UI, author State Schema, build FontPack glyphs, render/validate thousands of legal states, export C headers and create a Studio handoff using public Automation API calls. It also exposed reliability issues that must be closed before Automation is frozen as GA.

## Closed P0: unsaved Scene data loss

Transaction commit and disk persistence are separate concepts. V8.4.2 tracks Scene dirty state from persistent content, not from transaction completion. `project.get.dirty` remains true until the active Scene is saved.

`project.open_screen` is fail-closed when the active Scene is dirty. The caller must choose one explicit policy:

- no policy: return `UNSAVED_CHANGES` and keep the active screen unchanged;
- `save_current=true`: save current Scene first, then switch;
- `discard_current=true`: explicitly discard current in-memory changes, then switch.

`save_current` and `discard_current` are mutually exclusive. Save failure never changes the active screen.

The same guard is used before an operation would replace/delete the active Scene.

## Automation API 1.2

Automation API 1.2 retains the V1.1 State Model surface and adds reliability/usability capabilities:

- `state.count`
- `job.start`
- `job.status`
- `job.result`
- `job.cancel`
- `summary_only` / response-size controls on long matrix methods
- complete `history.commit` / `history.rollback` transaction parameter contracts
- bridge handshake version sourced from the same Automation version constant as capabilities/contract generation

Asynchronous jobs are intentionally limited to four long operations:

- `render.all_states`
- `validate.all_states`
- `export.all`
- `export.code_ai_handoff`

Jobs capture a Scene snapshot when started. They are server-owned and expose monotonic progress, terminal result/error state and cooperative cancellation.

## State-matrix awareness

`state.count` lets an Agent inspect legal matrix size before launching an expensive operation. Matrix operations preserve existing safety limits and report large-matrix warnings. Extremely large matrices require explicit caller intent.

## Response-size control

`render.all_states` can omit per-frame metadata. `validate.all_states` can omit per-case finding payloads. `export.all` can omit the frame-hash map. These controls reduce JSON-RPC payload size without changing canonical Renderer/Validator/Exporter truth.

## Runtime hygiene and release boundary

`__pycache__`, `.pyc`, `.pytest_cache` and build/runtime transient directories remain excluded from source delivery packaging. Runtime cache files are not product truth and must not participate in Project dirty semantics or Code AI handoff truth.

The Windows standalone remains a separate GA gate. The Windows builder runs every `test_qt_*.py` suite over the existing DPI matrix and rejects any Real-Qt skip/failure before building the standalone package.

## Frozen truth

V8.4.2 must preserve:

- 464/464 frozen product assets;
- 14/14 Clinical Golden frames;
- 512-byte framebuffer truth for the 128×32 clinical baseline;
- Renderer/VLSB semantics;
- existing V8.2/V8.3/V8.4/V8.4.1 graduation behavior.

## Stop condition

After V8.4.2 passes its data-safety soak, historical gates, package integrity gate and Windows zero-skip Real-Qt gate, MonoOLED Studio should enter Maintenance Mode. Future releases should be defect-driven bugfixes rather than proactive feature expansion unless a new real project demonstrates a missing capability.
