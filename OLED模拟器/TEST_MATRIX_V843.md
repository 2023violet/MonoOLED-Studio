# MonoOLED Studio 8.4.3 — Test Matrix

## P0 release-text gates

- all `Developer_Tools/*.bat` / `*.cmd` contain CRLF records;
- zero bare LF records;
- `.gitattributes` pins `eol=crlf` for `.bat/.cmd`;
- delivery builder normalizes Windows scripts before checksums/ZIP;
- package verifier rejects LF-only Windows command scripts.

## Root import isolation

From source-package root with no external `PYTHONPATH`:

```text
python -m pytest OLED模拟器/tests/test_automation_reliability_v842.py --collect-only -q
```

must collect successfully.

## Windows bounded source phase

- discover non-Qt `test_*.py` modules;
- execute in isolated groups (default 8 modules/process);
- 300 s default process timeout;
- one JUnit XML and one text log per group;
- first failure/error/timeout stops GA with preserved evidence.

## Windows isolated Real-Qt phase

For every `test_qt_*.py` module at each scale:

```text
100 / 125 / 150 / 175 / 200 / 225 / 250 / 300 %
```

require:

- isolated pytest process;
- bounded timeout;
- JUnit XML;
- zero failure/error;
- zero skip via `VERIFY_JUNIT_NO_SKIPS.py`;
- startup smoke and layout smoke per scale.

## Inherited gates

- V8.2 native visual/stress;
- V8.3 reliability/performance;
- V8.4 Project/Code-AI graduation;
- V8.4.1 State Model closure;
- V8.4.2 Automation Reliability/data safety;
- frozen assets 464/464;
- Clinical Golden 14/14 × 512 B;
- Automation API remains 1.2.0 / 82 methods.

## Standalone Windows gate

After source + Real-Qt gates:

- PyInstaller onedir;
- executable `--check`;
- `--startup-smoke`;
- `--smoke-ms 900`;
- `--layout-smoke`;
- `--interaction-smoke`;
- `--soak-smoke`;
- final Windows ZIP and SHA-256.

## Platform boundary

Linux execution may skip PySide6/Real-Qt modules. Such skips are not counted as Windows GA evidence. Windows GA requires the delivered builder itself to finish with `0 failed / 0 skipped` for the Real-Qt phase.
