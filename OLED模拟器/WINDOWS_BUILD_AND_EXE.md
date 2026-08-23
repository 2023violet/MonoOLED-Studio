# MonoOLED Studio 8.0 — Windows Build and Real-Qt Gate

Run from a Windows x64 machine:

```bat
Developer_Tools\BUILD_WINDOWS_EXE.bat
```

The builder creates an isolated `.venv-build`, installs pinned runtime/build/dev requirements, runs the complete source regression, then executes the Real-Qt suites (including `test_qt_v80_unified_workspace.py`) at `QT_SCALE_FACTOR=1.0/1.25/1.5/2.0`.

Only after those tests pass does it build the PyInstaller onedir application and execute `--check`, real-window smoke, layout smoke, interaction smoke and soak smoke.

The root `MonoOLEDStudio.exe` in the source delivery remains the native runtime-locator launcher. It is not represented as a newly built Python-free V8 standalone. The Windows PyInstaller artifact is the authoritative standalone release after this gate passes.
