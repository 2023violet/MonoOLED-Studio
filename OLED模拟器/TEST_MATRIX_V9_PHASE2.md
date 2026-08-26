# V9 Phase 2 Test Matrix

| Gate | Evidence |
| --- | --- |
| GEN-MATRIX-001 | Generic Schema produces enum, discrete-int, ranged-int combinations in declaration order |
| GEN-MATRIX-002 | Relation filtering, deterministic names, path-safe values and index selection are tested |
| GEN-MATRIX-003 | Empty and invalid schemas fail closed; no Curing fallback is generated |
| GEN-EXPORT-001 | Qt batch export and thumbnail wall use `build_export_states()` |
| GEN-EXPORT-002 | CLI export/handoff use generic case names and reject implicit Clinical names |
| GEN-HANDOFF-001 | Exported frames and `batch_validation.md` use the same matrix policy |
| MATRIX-GUARD-001 | `max_cases` and explicit large-matrix approval reject unsafe work |
| CURING-RENDER-001 | Existing Renderer and single-state render tests remain green |
| CURING-MATRIX-001 | Curing representative matrix is 560 cases with zero validation blockers |
| API-CONTRACT-001 | Automation API 1.2.0 and 82 methods remain unchanged |
| DETERMINISM-001 | Generic Handoff ZIP is byte-identical across repeated builds |

## Narrow regression

```powershell
python -m pytest `
  'OLED模拟器/tests/test_export_matrix.py' `
  'OLED模拟器/tests/test_generic_export.py' `
  'OLED模拟器/tests/test_exporter.py' `
  'OLED模拟器/tests/test_handoff_v4.py' `
  'OLED模拟器/tests/test_cli.py' `
  'OLED模拟器/tests/test_i18n.py' `
  'OLED模拟器/tests/test_runtime.py' `
  'OLED模拟器/tests/test_state_matrix_v3.py' `
  'OLED模拟器/tests/test_render.py' `
  'OLED模拟器/tests/test_presets.py' `
  -q

python -m pytest `
  'OLED模拟器/tests/test_automation_api_v1_final.py' `
  'OLED模拟器/tests/test_automation_reliability_v842.py' `
  -q

python -m compileall -q 'OLED模拟器' 'Developer_Tools' VERIFY_PACKAGE.py
git diff --check
```

The phase boundary intentionally excludes a new Windows Real-Qt deep run unless
the Windows release chain, native Qt behavior, DPI geometry, Renderer/Framebuffer/
VLSB output, or platform-specific export behavior is changed or fails.
