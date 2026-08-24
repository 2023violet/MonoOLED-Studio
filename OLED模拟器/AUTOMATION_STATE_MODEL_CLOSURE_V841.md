# MonoOLED Studio 8.4.1 — Automation State Model Closure

V8.4.1 is a deliberately small Code-AI closure release. Desktop UX, Renderer semantics, VLSB encoding, Clinical Golden and frozen product assets remain unchanged.

## Automation API 1.1

The project-level Automation API now owns the missing root state-model lifecycle:

- `state.get_schema` — returns the current variables + relations contract.
- `state.validate_schema` — validates a proposed schema without mutation.
- `state.set_schema` — atomically replaces the active scene schema, revision-guarded and transaction-safe.
- `state.validate` — validates one concrete state against domains and relations.
- `state.enumerate` — enumerates only legal combinations.

### Supported domains

Integer state variables may use either a continuous `min/max` range or an explicit discrete `values` array. Enum variables keep their existing `values` contract. `default` is accepted as an input alias; normalized output uses `init`.

### Supported relations

Relations are deliberately constrained to state-variable comparisons:

`<`, `<=`, `==`, `!=`, `>=`, `>`

No Python/JavaScript expression evaluation is introduced.

Example:

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

The legal full matrix is eight states: 1..3 for total=3 and 1..5 for total=5. No 4X, 4/3 or 5/3 state can be produced by Studio enumeration/export-all/validate-all.

## Safety contract

`state.set_schema` validates before mutation, obeys the standard revision guard, supports Agent transaction rollback, persists through project save/reopen, and records a committed root-scene transaction as one Designer undo operation when attached to the editor.

## Font API discovery

The six Font lifecycle methods now publish their real required/optional parameters, type information, limits/defaults and result contracts through `automation.capabilities`, `automation.describe_method`, and `AUTOMATION_API_V1.json` from the same production `METHOD_SPECS` registry.

## Freeze boundary

This release does **not** implement ORTHO pages. It only closes the Automation capability gap so a blind Code AI can subsequently create/validate/export those pages through the public API without editing JSON/assets outside Studio.
