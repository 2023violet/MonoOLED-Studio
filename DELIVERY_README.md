# MonoOLED Studio 8.4.4 — Windows Real-Qt GA Final Closure Complete Delivery

## Identity

- Version: **8.4.4**
- Release: **Windows Real-Qt GA Final Closure**
- Automation API: **1.2.0 / 82 methods (unchanged)**
- Delivery profile: **source**

## What V8.4.4 changes

V8.4.4 is deliberately limited to the failures reproduced by the real Windows validation of the V8.4.3 sealed package:

- Inspector content no longer overflows horizontally and vertical scrolling is not misreported as clipping;
- smoke checks wait for a stable layout signature;
- `StatusPill` applies parse-clean QSS;
- the bounded runner mirrors UTF-8 logs safely to CP936 consoles;
- explicit Editor geometry and canonical Renderer resource paths avoid redundant hot-path work while keeping the original V8.3 thresholds and content-hash invalidation;
- identical asset-cache payloads are no longer atomically replaced, so packaged layout settlement cannot self-trigger through the asset directory watcher;
- the runtime ZIP checksum is generated and verified by the pinned build Python, and a hash/sidecar error terminates the Builder;
- the Windows builder retains every V8.4.3 release gate and adds V8.4.4 repeated source/EXE smoke evidence.

V8.4.4 does **not** redesign or modify Renderer/VLSB semantics, Automation API 1.2 behavior, Scene/Project/State/FontPack schema behavior, the 464 frozen assets, the 14 Golden frames, or Curing-Lite ORTHO product pixels.

## Primary documents

- `OLED模拟器/WINDOWS_REAL_QT_GA_FINAL_CLOSURE_V844.md`
- `OLED模拟器/TEST_MATRIX_V844.md`
- `OLED模拟器/FINAL_VERIFICATION_REPORT.md`
- `OLED模拟器/CODE_AI_AUTOMATION_API_V1.md`

## Primary release tools

- `Developer_Tools/BUILD_WINDOWS_EXE.bat`
- `Developer_Tools/RUN_WINDOWS_TEST_GROUPS.py`
- `Developer_Tools/VERIFY_WINDOWS_RELEASE_TEXT.py`
- `Developer_Tools/VERIFY_V844_FINAL.py`
- `Developer_Tools/BUILD_DELIVERY_V844.py`

## Windows GA boundary

A Linux source/package validation does not establish native Windows GA. Windows GA is established only when the **original delivered** `Developer_Tools\BUILD_WINDOWS_EXE.bat` runs from a Windows fresh extraction and completes its bounded source groups, all Real-Qt modules at 100–300% DPI with `0 failed / 0 skipped`, inherited release gates, PyInstaller build, executable interaction checks and soak.

The final decision record uses `GA Release Gates = PASS`, `Known blockers = 0`, `Known P0/P1 = 0` and `Evidence confidence = High`; it does not use an absolute 100% confidence claim.
