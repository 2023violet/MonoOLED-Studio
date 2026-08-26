# MonoOLED Studio 8.4.4 — Test Matrix

## Targeted regressions

- CP936 console fallback preserves an escaped representation while the UTF-8 log remains unchanged.
- process-tree timeout and orphan-stdout termination remain bounded.
- every StatusPill semantic status and light/dark theme applies with zero stylesheet warning.
- Inspector and State content have no horizontal scroll range across 900×620 through 2560×1440, both languages and all mandatory DPI scales.
- intentional vertical scrolling is not reported as clipping.
- layout settlement reaches the same geometry signature on two consecutive passes.
- native Windows QPA is selected by default while explicit QPA overrides remain supported.
- all 19 stylesheet theme tokens map byte-for-byte to semantic palette roles.
- representative controls render pixel-identically under literal and adaptive theme styles.
- theme-only transitions keep the application stylesheet unchanged and remain within the original 120 ms p95 budget.
- explicit Tab/Backtab focus reasons show the keyboard focus ring, and a same-control mouse click clears it immediately.
- explicit, zone-free Editor geometry does not resolve an unused bitmap;
- the Renderer hot path still detects a bitmap mutation when file size and mtime are deliberately held constant;
- a repeated unchanged asset scan performs zero cache replacements, while a real bitmap content change performs exactly one atomic replacement;
- the StudioButton Enter/Leave regression requires hover pixels to differ and the post-Leave RGBA image to equal baseline byte-for-byte; 20 pinned Windows processes must pass independently;
- runtime ZIP SHA generation must produce exactly 64 lowercase hexadecimal characters plus the filename, verify its sidecar byte-for-byte, and propagate any failure to the batch exit code;
- V8.3 performance limits remain exactly 6.00 ms render p95, 0.50 ms geometry p95 and 2.00 ms smart-guides p95.

## Windows source and Real-Qt matrix

- bounded non-Qt groups: zero failure/error;
- every discovered `test_qt_*.py` module runs in an isolated process;
- DPI scales: 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5 and 3.0;
- each module/scale has JUnit and UTF-8 log evidence;
- Real-Qt permits zero skip, failure, error or timeout;
- source startup smoke runs 20 consecutive times;
- startup and layout smoke run at every DPI scale.

The post-optimization native Windows source matrix contains 104 isolated module/DPI processes and 1,048 test cases: 0 failed, 0 errors, 0 skipped and 0 timeouts. All eight startup and all eight 14-combination layout smokes passed. This source-tree result remains diagnostic until repeated by the original Builder from the formal sealed ZIP.

## Inherited and standalone gates

- V8.2 visual/adversarial stress;
- V8.3 reliability/performance;
- V8.4 Project and Code-AI graduation;
- V8.4.1 State Model;
- V8.4.2 Automation data safety;
- V8.4.3 Windows release mechanism;
- V8.4.4 final closure;
- PyInstaller onedir;
- EXE startup 20/20, layout 5/5, interaction 5/5 and soak 10/10 (2,400 cycles).

## Frozen boundaries

- Automation API 1.2.0 / 82 methods;
- frozen product assets 464/464;
- Clinical Golden 14/14, 512 bytes each;
- ORTHO standby and running framebuffer hashes remain unchanged after save/reopen.
