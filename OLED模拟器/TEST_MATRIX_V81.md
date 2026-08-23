# MonoOLED Studio 8.1 — UI/UX Reliability Test Matrix

## Fast PR / Host gate

- Package integrity and frozen product truth.
- Full Host/Core pytest suite.
- `PreferenceDelta` effect isolation.
- 432 semantic appearance combinations.
- 10,000 preference-transition persistence operations.
- Popup geometry deterministic/fuzz tests.
- EditorRegistry preference broadcast.
- Theme semantic-token completeness.
- UI metrics scaling invariants.
- 1,000 malformed Preferences fuzz cases.
- 10,000 SelectionModel transitions.
- 30,000 PixelDocument operations.
- 1,400 Renderer frames / 14 deterministic states.

## Windows Real-Qt gate

### Surfaces

1. Designer
2. Embedded Pixel Workspace
3. Font Lab
4. Preferences
5. Diagnostics / Agent / floating Popup states

### DPI

100%, 125%, 150%, 175%, 200%, 225%, 250%, 300%.

### Theme

MonoOLED Light, MonoOLED Dark, One Dark Pro, High Contrast.

### Language

zh-CN, en-US.

### Density

Compact, Comfortable, Spacious.

### UI Scale

Auto, 90%, 100%, 110%, 125%, 150%.

Full surface configuration space: `5 × 8 × 4 × 2 × 3 × 6 = 5,760` constructions. The release workflow may shard this matrix; every release candidate must aggregate all shards.

## Popup P0 matrix

Each production StudioSelect must be tested for:

- open / click / keyboard activation / Escape / outside click;
- only one active popup;
- bottom-edge opens above;
- right-edge clamp;
- list scroll for constrained height;
- theme/language/density/UI-scale change while open;
- tab close, window move/resize, app deactivate;
- 100 repeated open/commit cycles;
- popup is hidden before heavy preference effects execute.

## Transition invariants

For every UI-only theme/language/density/UI-scale change:

- active tab preserved;
- dirty state preserved;
- selection and primary selection preserved;
- zoom/scroll preserved;
- visible StudioPopup count returns to zero;
- framebuffer SHA-256 remains unchanged;
- no stale local stylesheet in embedded Pixel Workspace;
- Font Lab and Preferences use the target language;
- no unexpected top-level window or QObject growth.

## Latency budgets (Windows P95)

- Button feedback: ≤16 ms
- Popup open: ≤32 ms
- Popup select → closed: ≤50 ms
- Tab switch: ≤50 ms
- Language switch: ≤100 ms
- Theme switch: ≤120 ms
- Density switch: ≤120 ms
- UI Scale switch: ≤150 ms
- Inspector edit commit: ≤50 ms
- Drag frame: 16.7 ms target, 33 ms hard maximum

Any ordinary UI operation that creates an event-loop stall >100 ms must be reported as a release finding.

## Soak gate

- 1,000 popup open/close cycles
- 1,000 language transitions
- 1,000 theme transitions
- 1,000 tab switches
- 500 Pixel editor open/close cycles
- 500 Font Lab open/close cycles

Track RSS, QObject count, top-level widgets, visible popups, timers, file watchers, duplicate signal callbacks, and P95 latency slope.


## Implemented V8.1 test modules

- `tests/test_v81_ui_reliability_core.py` — PreferenceDelta, popup geometry, editor bus, semantic status tokens, UI metrics.
- `tests/test_v81_combination_stress.py` — 432 appearance semantics, 10,000 runtime transitions, 20,000 popup geometry fuzz cases, responsive extremes.
- `tests/test_v81_latency_contract.py` — release latency budgets and profiler math.
- `tests/test_v81_product_closure_contract.py` — production wiring/no-legacy-path contracts.
- `tests/test_qt_v81_visual_reliability.py` — real popup lifecycle, singleton popup, screen geometry, no full refresh on language, embedded editor propagation, popup leak cycle.
- `tests/test_qt_v81_visual_matrix.py` — five-surface theme/language/density/UI-scale matrix and framebuffer invariants.
- `tests/test_qt_v81_transition_latency.py` — real Qt popup/language/theme latency budgets.
- `Developer_Tools/VERIFY_V81_STRESS.py` — frozen truth + 1,000 malformed Preferences + 432 appearance combos + 10,000 transitions + 20,000 popup geometry cases + 10,000 Selection + 30,000 Pixel ops + Font determinism + 1,000 Automation calls + 1,400 Renderer frames.

The PySide6-dependent modules are intentionally skipped on a host without PySide6. A skip is not a GUI PASS.
