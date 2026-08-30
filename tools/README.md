# MonoOLED Studio Developer Tools

## V12 source/package verification

- `VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py` — native Windows Real-Qt V12 closure gate.
- `BUILD_DELIVERY_V120.py` — regenerates `SHA256SUMS.txt`, creates the deterministic ASCII-path V12 source ZIP, and writes a verified SHA-256 sidecar.
- `BUILD_WINDOWS_EXE.bat` — Windows-only full GA builder for source groups, Real-Qt/DPI gates, PyInstaller, executable smoke/soak, ZIP and SHA-256.
- `MonoOLEDStudio.spec` — current PyInstaller onedir specification rooted at `src/gui.py`.

Historical verification scripts remain under `tools/` only as regression gates; they are not the current release identity.
