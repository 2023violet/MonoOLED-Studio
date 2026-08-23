# MonoOLED Studio 8.3 Test Matrix

## Release truth gates

| Gate | Required evidence |
|---|---|
| Package | SHA256SUMS complete, no unmanaged files, safe UTF-8 ZIP paths |
| Frozen OLED truth | 464/464 product assets and 14/14 Golden ×512B byte-identical |
| Host/Core | full pytest, zero failure |
| Compile | `compileall` pass |
| Startup | real `QApplication + OLEDDesignerWindow` smoke on a Qt-capable host |
| Windows Qt | all `test_qt_*.py`, 8 DPI scales, **zero JUnit skips** |
| Standalone | PyInstaller onedir + executable startup/layout/interaction/soak |

## V8.3 correctness tests

- AST gate: no duplicate method names in a Python class.
- Real marquee press → move → release selects the expected elements and clears marquee gesture state.
- StudioSelect callbacks/event filters cannot observe partially initialized popup/list state.
- Main window startup populates the Fonts inventory.
- English `workspace.design/review` values are actually English.
- Corrupt Preferences are quarantined before fallback.
- Shortcut conflict recovery preserves unrelated custom bindings.

## Lifecycle tests

- Agent timer stopped when bridge is disabled.
- Start creates one worker/timer lifecycle.
- Stop shuts down and joins the worker.
- Main close stops Agent Bridge.
- SystemThemeProvider disconnects its application-level signal.
- Repeated startup/close on Windows must not show thread/timer/QObject growth.

## Performance tests

### Current bundled 5-element project

- render warm-cache distribution;
- `geometry()` distribution;
- `smart_guides()` distribution;
- decoded resource cache hit/miss counts.

### Synthetic 20-element project

- smart guide P95 without full-render amplification.

### Targets

| Operation | Target |
|---|---:|
| geometry P95 | < 0.10 ms |
| smart guides P95 @ 20 objects | < 1.0 ms |
| interactive warm render P95 | < 1.5 ms on packaging reference host |
| drag core P95 | < 8 ms |
| Windows GUI frame target | 16.7 ms; 33 ms hard interaction ceiling |

Performance thresholds are architecture regression guards, not guarantees for every machine.

## Frozen regression inherited from V8.2

V8.3 also reruns V8.2 adversarial coverage: malformed Preferences, 432 appearance semantics, runtime transitions, popup geometry/state/sizing, theme surfaces, responsive layouts, SelectionModel, PixelDocument, FontPack determinism, Agent JSON-RPC and 1,400 clinical renderer frames.

## Windows DPI scales

```text
100 / 125 / 150 / 175 / 200 / 225 / 250 / 300 %
```

Every Qt module is collected automatically from `test_qt_*.py`; the release builder writes JUnit XML and `VERIFY_JUNIT_NO_SKIPS.py` fails any scale containing a skip.
