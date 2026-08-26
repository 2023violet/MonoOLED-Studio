# Generalization Phase 1: Schema-Driven State Preview

## Scope

Phase 1 changes the Designer State tab from a Curing-specific runtime form into a
generic preview/editor generated from the active Scene state schema. The source
baseline is MonoOLED Studio V8.4.4. The canonical renderer remains the only
framebuffer producer.

The active schema continues to use the existing `variables`, `type`, `values`,
`min`, `max`, `init`, and `relations` contract. No new public schema fields or
Automation API methods are introduced.

## Mapping

| Schema | Editor | Domain |
| --- | --- | --- |
| `type=enum` | `StudioSelect` | `values`, in declaration order |
| `type=int` with `values` | `StudioSelect` | discrete integer values |
| `type=int` with `min/max` | `StudioNumericInput` | original inclusive range |
| invalid schema | no editor | stable schema error summary |
| empty schema | no editor | generic empty-state message |

`state_preview.py` validates through the existing `state_schema.validate_state_schema`
implementation and preserves JSON declaration order. Labels are formatted from the
field identifier only (`current_cycle` becomes `Current Cycle`); no Curing-specific
names or fallback controls are created.

Each editor is registered in `OLEDDesignerWindow.state_editors` with the field name,
normalized field metadata, label, and editor widget. Changes are normalized back to
the schema type before calling the existing `EditorSession.set_state()` path. Render,
validation, dirty state, session logging, and existing undo/session behavior remain
owned by the existing session and renderer code.

## Timeline

Timeline preview controls are available only when the Scene declares a non-empty
timeline. Play/Pause, Step, Reset, elapsed time, and speed continue to use the
existing `SceneRuntime`; the GUI does not infer `standby`, `running`, `phase`, or any
other product state. An empty timeline shows a generic `No timeline defined` message
and disables its controls. Unknown timeline state references remain explicit Runtime
errors.

## Curing compatibility

Curing Scenes still use their existing schema values and runtime timeline. The GUI now
discovers those fields in declaration order instead of naming `mode`, `phase`,
`battery`, or `seconds` in code. Renderer, framebuffer, VLSB export, Clinical presets,
Golden data, product assets, and Automation API contracts are outside this phase.

## Failure behavior

- Invalid schema: show a stable error summary and create no editable state controls.
- Empty schema: show a generic empty-state message and create no controls.
- Invalid editor value: reject it before writing to Runtime.
- Unknown Timeline state: preserve the existing Runtime exception path; the GUI does
  not guess or repair the reference.

## Non-goals

This phase does not change `state_schema.py`, `runtime.py`, `render.py`,
`framebuffer.py`, VLSB encoding, export matrices, presets, assets, Windows Builder,
PyInstaller, or the V8.4.4 sealed source ZIP. It does not claim V9 readiness or
generalize Clinical export behavior.

## Verification boundary

The Phase 1 gate is a narrow source and Qt regression. Windows Real-Qt deep validation
is not repeated for this GUI-only change unless a native Qt interaction, DPI geometry,
QPA, Renderer/Codec, PyInstaller, launcher, or Windows release path is modified, or a
narrow regression exposes a platform-specific failure.
