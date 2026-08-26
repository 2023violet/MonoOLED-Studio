# V9 Phase 1 Test Matrix

## Acceptance gates

| Gate | Evidence |
| --- | --- |
| GEN-STATE-001 | `gui.py` has no fixed Curing state-editor members |
| GEN-STATE-002 | enum, discrete-int, and ranged-int mappings are covered by unit and Qt tests |
| GEN-STATE-003 | generic fields can be previewed, edited, and rendered through `EditorSession` |
| GEN-STATE-004 | empty and invalid schemas create no editors and show a generic status |
| GEN-TIME-001 | timeline controls appear only for a non-empty Scene timeline |
| GEN-TIME-002 | arbitrary state names drive Timeline; no `standby/running` dependency |
| COMPAT-001 | existing Curing Runtime tests remain green |
| COMPAT-002 | existing state-matrix and renderer tests remain green |
| LAYOUT-001 | State Panel has no horizontal scrollbar or horizontal violation for long fields |
| REGRESSION-001 | Phase 1 narrow regression is green |

## Narrow regression

Executed from the V8.4.4 audit source tree:

```powershell
python -m pytest `
  'OLED模拟器/tests/test_schema_state_preview.py' `
  'OLED模拟器/tests/test_qt_schema_state_preview.py' `
  'OLED模拟器/tests/test_runtime.py' `
  'OLED模拟器/tests/test_state_matrix_v3.py' `
  'OLED模拟器/tests/test_render.py' `
  'OLED模拟器/tests/test_i18n.py' `
  -q

python -m compileall -q 'OLED模拟器' 'Developer_Tools' VERIFY_PACKAGE.py
git diff --check
```

The current run recorded 24 passed and 0 failed. The dedicated Qt module uses
PySide6 with the offscreen platform and does not require `pytest-qt`; it covers the
generic four-field fixture, empty and invalid schemas, arbitrary-name Timeline
behavior, and 8 long fields at 900x620, 1440x900, and 1920x1080.

## Existing Qt inventory

The repository's historical Qt modules use the `pytest-qt` `qtbot` fixture. This
environment has PySide6 but does not provide `pytest-qt`, so those historical modules
were not counted as Phase 1 evidence. No test was deleted, skipped by changing its
contract, or replaced with a Windows-only claim.

## Explicit boundary

This matrix does not claim a fresh Windows Real-Qt eight-DPI run, PyInstaller run, or
EXE soak. Those remain V8.4.4 release evidence and are re-triggered only by the
conditions documented in `GENERALIZATION_PHASE1_SCHEMA_STATE_PREVIEW.md`.
