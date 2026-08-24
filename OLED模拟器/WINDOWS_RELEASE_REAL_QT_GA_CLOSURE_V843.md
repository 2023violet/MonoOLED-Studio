# MonoOLED Studio 8.4.3 — Windows Release & Real-Qt GA Closure

## Scope

V8.4.3 is a release-engineering closure. It does **not** change Automation API 1.2, Renderer semantics, Scene/Project/State/FontPack schemas, VLSB, the 14 Clinical Golden frames, or the 464 frozen product assets.

It closes four issues reproduced from the sealed V8.4.2 Windows validation:

1. Windows command scripts were delivered LF-only and could be misparsed by `cmd.exe`.
2. The Windows builder ran the entire source suite in one unbounded pytest process.
3. Real-Qt tests were collected as one large process per DPI, making hangs/failures expensive to localize.
4. Selected Automation tests depended on running from `OLED模拟器` because repository-root import configuration was absent.

## Windows command-script contract

Every delivered `.bat` / `.cmd` under `Developer_Tools` is CRLF-only. The source package contains `.gitattributes` rules:

```text
*.bat text eol=crlf
*.cmd text eol=crlf
```

`VERIFY_WINDOWS_RELEASE_TEXT.py` and `VERIFY_PACKAGE.py` both reject command scripts with bare LF records.

`BUILD_DELIVERY_V843.py` normalizes Windows command scripts before checksums and ZIP creation so a Linux packaging host cannot silently reintroduce LF-only batch files.

## Bounded source regression

`RUN_WINDOWS_TEST_GROUPS.py --phase source` discovers all `test_*.py` modules except `test_qt_*.py`, splits them into small groups, executes every group in a separate Python process, stores JUnit + plain-text logs, and enforces a hard timeout.

A failed or hanging group therefore has an explicit terminal result and evidence path rather than stalling the complete GA build.

## Isolated Real-Qt gate

`RUN_WINDOWS_TEST_GROUPS.py --phase qt` discovers every `test_qt_*.py` module. For each of the mandatory scale factors:

```text
1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0
```

it launches **one pytest process per Qt module**, writes JUnit + log evidence, enforces a per-module timeout, and invokes `VERIFY_JUNIT_NO_SKIPS.py`. Any failure, error, skip, or timeout stops the Windows GA build with the exact module/scale identified.

Startup and layout smoke checks are also run for each scale.

## Repository-root pytest contract

The source package now includes `pytest.ini`:

```ini
[pytest]
pythonpath = OLED模拟器
testpaths = OLED模拟器/tests
```

This makes direct commands from a fresh source-package root deterministic, including:

```text
python -m pytest OLED模拟器/tests/test_automation_reliability_v842.py -q
```

without requiring `cd OLED模拟器` or an externally supplied `PYTHONPATH`.

## Windows GA builder

`BUILD_WINDOWS_EXE.bat` now performs:

1. pinned build/test environment setup;
2. CRLF release-text verification;
3. bounded non-Qt source groups;
4. core + real-window startup checks;
5. isolated Real-Qt modules at all eight DPI scales with zero-skip enforcement;
6. V8.2, V8.3, V8.4, V8.4.1, V8.4.2 and V8.4.3 gates;
7. PyInstaller onedir build;
8. executable core/startup/layout/interaction/soak checks;
9. release ZIP + SHA-256.

## Evidence boundary

A Linux packaging host can prove source/package integrity, CRLF bytes, import isolation, deterministic ZIPs, non-Qt regressions and inherited stress gates. It **cannot** claim native Windows Real-Qt or PyInstaller execution success.

Windows GA is established only when the original delivered `BUILD_WINDOWS_EXE.bat` completes on a Windows fresh extraction with all mandatory Real-Qt suites reporting zero failures and zero skips.
