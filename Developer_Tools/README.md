# MonoOLED Studio Developer Tools

## V8 source/package verification

- `VERIFY_V80_STRESS.py` — frozen-asset/Golden checks plus Preferences, Selection, Pixel, Font, Automation and Renderer stress.
- `BUILD_DELIVERY_V80.py` — regenerates `SHA256SUMS.txt` and creates a deterministic UTF-8-safe source delivery ZIP.
- `BUILD_WINDOWS_EXE.bat` — Windows-only PyInstaller/Real-Qt release gate.
- `MonoOLEDStudio.spec` — PyInstaller onedir specification.

The Windows build gate executes all source tests and the V8 Real-Qt suite at 100/125/150/200% scaling before it creates the standalone archive.
