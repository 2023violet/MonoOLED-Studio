# Generalization Phase 2: Generic Matrix / Export / Handoff

## Scope

Phase 2 makes the current Qt and CLI batch export paths derive their states from
the active Scene State Schema. Generic scenes and the Curing scene use the same
matrix construction, deterministic case naming, size limits, canonical Renderer,
PNG and VLSB Golden output, and Code AI handoff path.

The default policy for GUI and CLI export is `representative`. `boundaries` and
`full` remain explicit policies. Matrix generation validates the existing State
Schema and relation contract before any export work begins.

## Matrix contract

Case names are deterministic and include the zero-based matrix index:

```text
case_0000
case_0000__page-HOME__channel-1__level-0__alarm-OFF
```

Fields follow Schema declaration order. Case components are path-safe and the
index prevents collisions after sanitization. Invalid or unknown case selections
fail without guessing or falling back to Curing-specific names.

The default limit is 5,000 cases. A matrix above 100,000 cases requires explicit
`allow_large_matrix=true`; a matrix above the caller's `max_cases` is rejected,
never truncated or silently sampled.

## Export and handoff

Qt `Export State Matrix`, thumbnail-wall export, and Code AI Handoff call the same
Schema-driven representative matrix. CLI `export` and `handoff` expose
`--integer-policy`, `--max-cases`, `--allow-large-matrix`, and case-name/index
selection. The old `normal_standby` / `normal_running` implicit Clinical names are
not accepted by the new batch CLI path.

`export_scene()` remains the canonical producer of PNG, Golden BIN, UI contract,
asset manifest, and validation report. `build_handoff_package()` receives the
selected policy so its batch-validation report describes the same matrix as the
exported frames. Automation API method count and public method contracts are
unchanged.

## Compatibility and non-goals

Single-state Curing rendering, framebuffer bytes, VLSB semantics, existing Golden
files, product assets, State/Scene/Project/FontPack contracts, Renderer, and the
Windows release chain are outside this phase. `presets.clinical_states()` remains
available as a historical preset implementation and regression fixture, but is no
longer used by the current Qt/CLI batch export path.

The Curing representative matrix currently contains 560 legal states and has zero
validation blockers. This replaces the former 14-state default export behavior by
explicit product decision; it is not a claim that the old 14-state export bytes are
unchanged.

## Verification boundary

This phase does not repeat Windows Real-Qt deep validation. It does not modify the
Windows Builder, PyInstaller, QPA/DPI/native executable, Renderer, Framebuffer, or
VLSB Codec. That validation must be reopened if a narrow regression reveals a
platform-specific Qt/export failure, or any excluded rendering/release boundary is
later changed.
