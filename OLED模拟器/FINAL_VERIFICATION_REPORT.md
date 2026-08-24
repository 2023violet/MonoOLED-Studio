# MonoOLED Studio 8.4.3 — Final Verification Report

> Release: **Windows Release & Real-Qt GA Closure**  
> Automation API: **1.2.0 / 82 methods (unchanged)**  
> Date: **2026-08-24**

## 1. Purpose

V8.4.3 is a narrow release-engineering response to the real Windows validation of the V8.4.2 sealed source package. The Automation/ORTHO graduation itself passed; the blocking evidence was in the Windows GA delivery path:

- `Developer_Tools/BUILD_WINDOWS_EXE.bat` was LF-only in the sealed ZIP and was misparsed by real `cmd.exe`;
- the builder used one monolithic source pytest process;
- Real-Qt execution had insufficient process isolation when a module failed or did not terminate;
- selected Automation tests depended on running from `OLED模拟器` rather than the source-package root.

V8.4.3 does **not** modify Automation API behavior, Renderer/VLSB semantics, Project/Scene/State/FontPack schema semantics, frozen product assets, Clinical Golden frames, or Curing-Lite ORTHO product pixels.

## 2. TDD evidence

The untouched V8.4.2 source delivery was first tested against the V8.4.3 release requirements.

Initial V8.4.3 RED results reproduced:

```text
BUILD_WINDOWS_EXE.bat: CRLF=0 / LF-only=105
RUN_MONOOLED_DIAGNOSTIC.bat: LF-only
CREATE_RUNTIME_ENV.bat: LF-only
.gitattributes: missing
bounded Windows test runner: missing
repository-root selected Automation collection: ModuleNotFoundError: automation_service
V8.4.3 release identity/tools: missing
```

During runner validation, two additional test-runner lifecycle defects were intentionally converted into RED regressions:

1. timeout killed only the parent process and could leave descendants holding output handles;
2. successful pytest parent exit could still make a PIPE-based runner wait for a descendant-owned stdout handle.

Both are now covered by explicit V8.4.3 tests.

## 3. Windows command-script closure

The source tree and delivery contract now require:

```text
*.bat text eol=crlf
*.cmd text eol=crlf
```

Current source-package command scripts:

```text
Developer_Tools/BUILD_WINDOWS_EXE.bat
Developer_Tools/CREATE_RUNTIME_ENV.bat
Developer_Tools/RUN_MONOOLED_DIAGNOSTIC.bat
```

`VERIFY_WINDOWS_RELEASE_TEXT.py` result:

```text
PASS: Windows command scripts CRLF-clean (3 file(s), 0 LF-only records)
```

`BUILD_DELIVERY_V843.py` normalizes every included `.bat/.cmd` before checksums and ZIP creation. `VERIFY_PACKAGE.py` independently rejects any delivered Windows command script with a bare LF record.

## 4. Repository-root pytest isolation

A new root `pytest.ini` defines:

```ini
[pytest]
pythonpath = OLED模拟器
testpaths = OLED模拟器/tests
```

The V8.4.3 gate removes external `PYTHONPATH` and proves that this command collects successfully from a fresh source-package root:

```text
python -m pytest OLED模拟器/tests/test_automation_reliability_v842.py --collect-only -q
```

This closes the previously observed `ModuleNotFoundError: automation_service` when selecting Automation tests from the repository root.

## 5. Bounded Windows source runner

`Developer_Tools/RUN_WINDOWS_TEST_GROUPS.py` replaces the monolithic source pytest invocation.

Source phase:

- discovers all non-Qt `test_*.py` modules;
- runs bounded module groups (default 8 modules/process);
- uses a hard per-group timeout;
- preserves one JUnit XML and one text log per group;
- stops on the first failure/error/timeout with a deterministic exit code.

Real-Qt phase:

- discovers every `test_qt_*.py` module;
- runs one Qt module per process at each mandatory DPI scale;
- preserves JUnit + log evidence per scale/module;
- enforces zero skips using `VERIFY_JUNIT_NO_SKIPS.py`;
- applies a hard per-module timeout;
- runs startup/layout smoke checks at each scale.

Mandatory scales remain:

```text
1.0 / 1.25 / 1.5 / 1.75 / 2.0 / 2.25 / 2.5 / 3.0
```

## 6. Process termination closure

The runner writes subprocess output directly to log files instead of using `PIPE`. This prevents a descendant process that inherits stdout from keeping the parent runner blocked after pytest exits.

On timeout:

- Windows uses `taskkill /PID <pid> /T /F`;
- POSIX uses a dedicated process session and `killpg`.

Regression probes confirm:

```text
parent + descendant timeout → runner returns 124 within bound
parent exits while descendant retains stdout → runner returns parent result without waiting for pipe EOF
absolute external report directory → supported
```

This is specifically intended to turn Real-Qt hangs into bounded, diagnosable GA failures instead of a build with no terminal state.

## 7. Bounded Host/Core regression

Because the execution harness itself has a bounded command window, the current Linux source inventory was executed in bounded groups rather than relying on one long pytest process.

Results across non-Qt source groups:

```text
306 passed
1 skipped
0 failed
```

The single skip is the PySide6-dependent GUI smoke path on this Linux host.

The `test_qt_*.py` inventory on the same host:

```text
3 passed
12 skipped
0 failed
```

Combined bounded inventory:

```text
309 passed
13 skipped
0 failed
```

All 13 skips are native PySide6/Real-Qt platform skips. They are **not** Windows GA evidence.

## 8. Compile/source gates

```text
compileall: PASS
clang -target x86_64-pc-windows-msvc windows_launcher.c: PASS
```

The clang result is a Windows-target **source syntax** check only. It does not claim execution of a rebuilt Windows launcher.

## 9. Inherited product/reliability gates

### V8.2 native visual/adversarial

```text
Frozen product assets:      464 / 464
Clinical Golden:             14 / 14 × 512 B
Preferences fuzz:             1,000
Appearance combinations:        432
Preference transitions:      10,000
Popup geometry:              20,000
Popup state transitions:    100,000
Popup sizing:                50,000
Pixel operations:            30,000
Automation calls:             1,000
Renderer frames:              1,400
Deterministic states:          14 / 14
Renderer P95:              ~3.304 ms on this run
```

### V8.3 reliability/performance

```text
Duplicate methods:                     0
Warm render P95:                  ~0.629 ms
geometry() P95:                   ~0.054 ms
smart_guides() P95:               ~0.146 ms
20-object smart guides P95:       ~0.064 ms
100 coalesced moves → Undo commands:   1
```

### V8.4 Project / Code-AI graduation

```text
Automation API: 1.2.0
Methods:        82
Clinical representative states: 560
Framebuffer/state: 512 B
Blockers: 0
Direct project flow: PASS
localhost JSON-RPC: PASS
Handoff: PASS
```

### V8.4.1 State Model closure

```text
legal cycle cases: 8
{3,5} discrete domain: PASS
current_cycle <= total_cycles: PASS
revision guard: PASS
transaction rollback: PASS
Designer undo: PASS
save/reopen: PASS
localhost JSON-RPC: PASS
Font contract discovery: PASS
```

### V8.4.2 Automation reliability/data safety

```text
Cross-screen iterations:       1,000
Unsafe switches rejected:        143
Silent data loss:                  0
save_current: PASS
discard_current: PASS
fresh reopen: PASS
state count/summary: PASS
job progress: PASS
stable job business fields match synchronous result: PASS
history transaction params: PASS
bridge API version: PASS
```

The wording deliberately excludes runtime telemetry such as `elapsed_ms` from deterministic result equality.

### V8.4.3 release gate

```text
Windows command text: PASS
Repository-root pytest import: PASS
Bounded source runner: PASS
Process-tree timeout: PASS
Orphan-stdout non-blocking behavior: PASS
Isolated Real-Qt runner: PRESENT / native Windows execution required
```

## 10. Windows builder contract

The delivered `Developer_Tools\BUILD_WINDOWS_EXE.bat` now performs, in order:

1. isolated Python build environment;
2. pinned dependencies;
3. CRLF release-text gate;
4. bounded non-Qt source groups;
5. core + real-window startup checks;
6. one Real-Qt module/process at all 8 DPI scales with zero-skip enforcement;
7. V8.2 gate;
8. V8.3 gate;
9. V8.4 gate;
10. V8.4.1 gate;
11. V8.4.2 gate;
12. V8.4.3 gate;
13. PyInstaller onedir build;
14. executable core check;
15. executable startup/layout checks;
16. executable interaction smoke;
17. executable soak smoke;
18. Windows release ZIP + SHA-256.

The old monolithic command:

```text
pytest "OLED模拟器\tests" -q
```

is intentionally absent.

## 11. Product truth preservation

V8.4.3 must preserve the V7.0 frozen truth:

```text
Product assets: 464 / 464 byte-identical
Clinical Golden: 14 / 14 byte-identical
Golden size: 512 B each
```

Automation API remains:

```text
1.2.0 / 82 methods
```

No new Code-AI design capability is introduced in V8.4.3.

## 12. Native Windows boundary

This Linux packaging host cannot execute `cmd.exe`, PySide6 Real-Qt Windows behavior, mixed-DPI native windows, or the PyInstaller Windows executable.

Therefore V8.4.3 source/package verification does **not** itself claim Windows GA PASS.

The remaining authoritative evidence is:

```text
fresh Windows extraction
→ original delivered BUILD_WINDOWS_EXE.bat
→ bounded source groups have terminal results
→ every test_qt_*.py at 8 DPI scales: 0 failed / 0 skipped
→ inherited gates PASS
→ PyInstaller PASS
→ EXE startup/layout/interaction/soak PASS
```

The purpose of V8.4.3 is to make that Windows gate executable, bounded and diagnosable from the sealed source package itself.

## 13. Release conclusion

V8.4.3 closes the release-engineering defects exposed by the real V8.4.2 Windows validation without reopening the product or Automation architecture. The source package now enforces Windows command-file bytes, deterministic repository-root test imports and bounded process-isolated GA execution.

After deterministic candidate/final ZIP construction, package integrity and fresh-extract verification must be repeated before the formal source delivery is accepted. Native Windows GA remains a separate final platform gate.


## 14. Independent candidate fresh-extract evidence

Two independent pre-report candidate archives were byte-identical:

```text
Candidate SHA-256:
e67836d8e574a71e36e7e78adf4debc213dc0b7448bc332e4afe0b8a31455670
```

The candidate was extracted into a new directory and verified without importing modules from the work tree.

Structure:

```text
ZIP entries:                    765
SHA256SUMS managed files:        764
Non-ASCII UTF-8 paths:       721/721
Duplicate entries:                0
Unsafe/traversal paths:            0
```

Windows text bytes from the extracted ZIP:

```text
BUILD_WINDOWS_EXE.bat        CRLF 111 / LF-only 0
CREATE_RUNTIME_ENV.bat       CRLF 49  / LF-only 0
RUN_MONOOLED_DIAGNOSTIC.bat  CRLF 22  / LF-only 0
```

Package and V8.4.3 gates:

```text
VERIFY_PACKAGE.py:                  PASS
VERIFY_WINDOWS_RELEASE_TEXT.py:     PASS
VERIFY_V843_FINAL.py:               PASS
compileall:                         PASS
Windows-target launcher C syntax:  PASS
```

Fresh bounded source inventory:

```text
Group A: 66 passed
Group B: 62 passed / 1 skipped
Group C: 93 passed
Group D: 85 passed
---------------------------------
Non-Qt: 306 passed / 1 skipped / 0 failed
Qt-on-Linux: 3 passed / 12 skipped / 0 failed
Combined: 309 passed / 13 skipped / 0 failed
```

Fresh inherited gates:

```text
V8.2 stress:                         PASS
  renderer frames:                  1,400
  deterministic states:             14/14
  renderer P95:                     ~3.287 ms

V8.3 reliability/performance:       PASS
  warm render P95:                  ~0.629 ms
  geometry P95:                     ~0.054 ms
  smart-guides P95:                 ~0.134 ms
  20-object guides P95:             ~0.072 ms

V8.4 Project/Code-AI:               PASS
V8.4.1 State Model:                 PASS
V8.4.2 Automation Reliability:      PASS
  cross-screen iterations:          1,000
  unsafe switches rejected:         143
  silent data loss:                 0
V8.4.3 Windows release closure:     PASS (source/package gate)
```

Continuity against the formal V8.4.2 delivery:

```text
V8.4.2 paths:          755
V8.4.3 candidate:      765
V8.4.2 paths missing:    0
V8.4.3 added paths:     10
```

The 10 new paths are limited to `.gitattributes`, `pytest.ini`, V8.4.3 release/test documents, the bounded Windows test runner, the CRLF verifier, the V8.4.3 package builder/final gate, and its generated report.

Native Windows `cmd.exe` / Real-Qt / PyInstaller execution is still intentionally **not inferred** from Linux candidate validation.
