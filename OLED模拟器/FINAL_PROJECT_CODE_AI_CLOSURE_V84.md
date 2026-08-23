# MonoOLED Studio 8.4 — Final Project & Code AI Closure

V8.4 is the project-closure release on top of V8.3. It does not redesign the OLED renderer, clinical pages or frozen production assets.

## Closure delivered

- Automation API 1.0 machine-readable contract and capability discovery.
- Project Screen create/open/duplicate/rename/delete/save-all orchestration.
- Active screen switching through the same EditorSession used by the GUI.
- Representative state enumeration and all-state render/validation.
- Project-owned asset lifecycle and blank PixelDocument creation.
- Studio-owned current/all-state/C-header/FontPack/Code-AI-handoff exports.
- Canonical preview and annotated preview feedback.
- Direct Automation graduation test and localhost JSON-RPC graduation test.
- First-start font scan retained in the real main-window construction path.
- Windows release builder automatically executes every `test_qt_*.py` at eight DPI scales and rejects any JUnit skip.

## Frozen product truth

V8.4 must preserve:

- 464 frozen V7.0 production assets byte-for-byte;
- 14 clinical Golden BIN files byte-for-byte;
- 512-byte 128×32 VLSB framebuffer contract;
- legacy Scene/Renderer semantics used by the clinical baseline.

## Correct Code AI positioning

Automation API 1.0 is intended to let an Agent design and validate a complete multi-Screen OLED project without GUI-coordinate automation. It can discover project structure/fonts/assets, edit screens/pixels/fonts, observe canonical rendered pixels, enumerate states, validate, save and export.

It does **not** replace physical OLED verification of panel scan/remap, bus timing, power integrity, brightness or hardware-specific visual artifacts.

## Windows GA boundary

The Linux source/package host cannot execute PySide6. V8.4 therefore does not claim Windows GUI GA from Linux results. `Developer_Tools/BUILD_WINDOWS_EXE.bat` is the authoritative Windows gate and requires zero failed **and zero skipped** Real-Qt tests before producing the standalone release ZIP.
