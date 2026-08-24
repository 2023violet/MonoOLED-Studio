# MonoOLED Studio 8.4.1 Test Matrix

## New state-model closure gates

- State API discovery and Automation API 1.1 identity.
- Schema validation with no mutation on failure.
- Explicit discrete domain `{3,5}`; `4` must never enumerate.
- Relational legality `current_cycle <= total_cycles`; illegal `4/3` and `5/3` must never enumerate.
- Concrete `state.validate` valid/invalid cases.
- Revision guard rejects stale schema writes.
- Transaction rollback restores the original root scene schema.
- Committed state-schema transaction is one Designer undo.
- Save/reopen preserves states and relations.
- Localhost token-authenticated JSON-RPC can discover, set, validate and enumerate the new schema.
- Font lifecycle methods expose real machine-readable parameter/return contracts.
- Historical Automation API 1.0 project/pixel/font/export behavior remains compatible under API 1.1.

## Inherited gates

All V8.0–V8.4 Host/Core tests, V8.2 adversarial visual-state stress, V8.3 reliability/performance stress, V8.4 project/Code-AI graduation, frozen 464 product assets and 14×512B Clinical Golden remain mandatory.

## Windows GA boundary

`BUILD_WINDOWS_EXE.bat` must run the full suite, every `test_qt_*.py` at 100/125/150/175/200/225/250/300% with JUnit zero-skip enforcement, V8.2/V8.3/V8.4/V8.4.1 gates, then build and smoke the PyInstaller onedir artifact.
