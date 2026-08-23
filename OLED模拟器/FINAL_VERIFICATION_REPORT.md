# MonoOLED Studio 8.4 — Final Verification Report

> Release: **Final Project & Code AI Closure**  
> Automation API: **1.0.0**  
> Packaging host: Linux / Python 3.13; PySide6 unavailable on this host.

## Work-tree verification before candidate packaging

### Regression suite

The complete test inventory was executed in bounded chunks because a single all-suite command exceeds the harness execution window. Combined result:

```text
272 passed
13 skipped
0 failed
```

All 13 skips are PySide6/pytest-qt Real-Qt modules. They are not interpreted as Windows GUI passes.

### Compile/source

```text
python -m compileall -q OLED模拟器 Developer_Tools VERIFY_PACKAGE.py
PASS

clang -fsyntax-only -target x86_64-pc-windows-msvc OLED模拟器/windows_launcher.c
PASS
```

`gui.py --check` cannot run on this Linux packaging host because the module intentionally requires PySide6; the authoritative real-window startup check remains a Windows release gate.

### Frozen OLED product truth

```text
Frozen production assets: 464 / 464 byte-identical
Clinical Golden BIN:        14 / 14 byte-identical
Golden bytes each:                  512
```

### Inherited V8.2 adversarial gate

```text
Preferences malformed fuzz:       1,000 PASS
Appearance combinations:            432 PASS
Preference transitions:          10,000 PASS
Popup geometry:                  20,000 PASS
Popup state transitions:        100,000 PASS
Popup sizing/placement:          50,000 PASS
Theme surfaces:                      60 PASS
Responsive layouts:                 120 PASS
Selection transitions:           10,000 PASS
PixelDocument operations:        30,000 PASS
FontPack determinism:               PASS
Automation calls:                 1,000 PASS
Renderer frames:                  1,400 PASS
Renderer deterministic states:    14 / 14
Framebuffer bytes:                    512
```

### V8.3 reliability/performance gate

```text
Duplicate class methods:                   0
Warm EditorSession render P95:       ~0.635 ms
geometry() P95:                      ~0.055 ms
smart_guides() P95:                  ~0.146 ms
20-object smart_guides() P95:        ~0.069 ms
100 coalesced moves:                 1 undo
```

Host timings are informative rather than hardware-independent performance guarantees. Structural regressions are protected by the V8.3 budgets.

### Automation API 1.0 graduation gate

```text
API methods:                         74
Representative clinical states:    560
Canonical framebuffer/state:       512 B
All-state validation blockers:       0
Direct multi-screen project flow:  PASS
localhost JSON-RPC flow:           PASS
Studio Code-AI handoff:            PASS
```

The graduation flow proves: capability discovery → create/open Screen → create/edit/save Pixel asset → create Scene element → canonical render → validation → save all → Studio handoff → project reopen. A second path proves capability/project observation through the actual localhost token-authenticated JSON-RPC server.

## Windows GA gate

`Developer_Tools/BUILD_WINDOWS_EXE.bat` is the authoritative Windows gate. It:

1. installs pinned Python/Qt test/build dependencies;
2. runs the complete source regression suite;
3. runs real `QApplication + OLEDDesignerWindow` startup;
4. discovers every `test_qt_*.py` module, including V8.4 project automation integration;
5. runs them at 100/125/150/175/200/225/250/300% scale;
6. rejects every JUnit skip as well as every failure;
7. runs V8.2, V8.3 and V8.4 adversarial/graduation gates;
8. builds the PyInstaller onedir application;
9. runs core/startup/layout/interaction/soak executable smokes;
10. creates the final Windows x64 standalone ZIP and SHA-256.

This Linux package does **not** claim those Windows-native results already passed.

## Release interpretation

V8.4 closes the project-level Code AI orchestration gap while retaining V8.3 correctness/performance closure. Code AI can now discover the product contract, operate across Screens, create/edit assets, enumerate/validate project states and use Studio-owned exports without reimplementing framebuffer/export truth.

Physical OLED verification remains required for scan/remap, bus timing, power integrity, brightness and panel-specific behavior.

## Candidate fresh-extract acceptance

The deterministic candidate ZIP was extracted into a new directory and all release gates above were rerun from that extracted tree.

```text
ZIP entries:                         739
SHA256SUMS managed files:             738
Non-ASCII UTF-8 paths:            705/705
Duplicate entries:                      0
Unsafe/traversal entries:                0
Package Verify:                       PASS
Host/Core:             272 passed / 13 skipped / 0 failed
compileall:                           PASS
Windows-target launcher C syntax:    PASS
V8.2 inherited stress:               PASS
V8.3 reliability/performance:        PASS
V8.4 Code-AI graduation:             PASS
```

Candidate fresh V8.3 hot-path measurements: warm render P95 ≈0.626 ms; geometry P95 ≈0.056 ms; smart-guides P95 ≈0.152 ms; 20-object smart-guides P95 ≈0.064 ms.

Upgrade continuity: V8.3 delivered 727 paths; V8.4 candidate delivers 739 paths; **0 V8.3 paths are missing** and 12 V8.4 paths are additional.
