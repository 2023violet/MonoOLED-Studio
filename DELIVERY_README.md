# MonoOLED Studio 8.4.3 — Windows Release & Real-Qt GA Closure Complete Delivery

## Identity

- Version: **8.4.3**
- Release: **Windows Release & Real-Qt GA Closure**
- Automation API: **1.2.0 / 82 methods (unchanged)**
- Delivery profile: **source**

## What V8.4.3 changes

V8.4.3 is deliberately limited to release engineering after the real Windows validation of the V8.4.2 sealed package:

- all delivered `.bat/.cmd` files are CRLF-only;
- `.gitattributes` freezes the Windows EOL contract;
- `pytest.ini` makes selected tests runnable from source-package root without external `PYTHONPATH`;
- Windows source tests run in bounded isolated groups;
- each `test_qt_*.py` module runs in its own bounded process at 8 mandatory DPI scales;
- every Real-Qt module writes JUnit + text log evidence and rejects skips;
- the Windows builder runs V8.2 → V8.4.3 gates before PyInstaller;
- source packaging verifies the CRLF contract before a ZIP can be accepted.

V8.4.3 does **not** redesign or modify Renderer/VLSB semantics, Automation API 1.2 behavior, Scene/Project/State/FontPack schema behavior, the 464 frozen assets, the 14 Golden frames, or Curing-Lite ORTHO product pixels.

## Primary documents

- `OLED模拟器/WINDOWS_RELEASE_REAL_QT_GA_CLOSURE_V843.md`
- `OLED模拟器/TEST_MATRIX_V843.md`
- `OLED模拟器/FINAL_VERIFICATION_REPORT.md`
- `OLED模拟器/CODE_AI_AUTOMATION_API_V1.md`

## Primary release tools

- `Developer_Tools/BUILD_WINDOWS_EXE.bat`
- `Developer_Tools/RUN_WINDOWS_TEST_GROUPS.py`
- `Developer_Tools/VERIFY_WINDOWS_RELEASE_TEXT.py`
- `Developer_Tools/VERIFY_V843_FINAL.py`
- `Developer_Tools/BUILD_DELIVERY_V843.py`

## Windows GA boundary

A Linux source/package validation does not establish native Windows GA. Windows GA is established only when the **original delivered** `Developer_Tools\BUILD_WINDOWS_EXE.bat` runs from a Windows fresh extraction and completes its bounded source groups, all Real-Qt modules at 100–300% DPI with `0 failed / 0 skipped`, inherited release gates, PyInstaller build, executable interaction checks and soak.
