# Windows Build and Release — V1.0.0

## End users

Do not build locally. Download `MonoOLEDStudio_v1.0.0_Windows_x64.zip` from the repository's **GitHub Releases**, extract it, and double-click `MonoOLEDStudio\MonoOLEDStudio.exe`. Python is not required.

## Developer Quick Build

```bat
tools\BUILD_WINDOWS_QUICK.bat
```

This reuses `.venv-build` when possible, builds the current `src/gui.py` with the PyInstaller onedir spec, then performs the executable `--check` and one startup smoke. It intentionally skips the full DPI matrix, historical regression matrix, and soak certification.

## Full Windows GA Build

```bat
tools\BUILD_WINDOWS_GA.bat
```

GA runs the current source regression groups, native Real-Qt tests across the configured DPI scale matrix, V12 Generic Product Closure, PyInstaller packaging, executable startup/layout/settings/font/interaction/soak gates, and creates the Windows release ZIP plus SHA-256. Historical V8–V11 behavior remains covered by the current test suite; obsolete version-specific verifier scripts are not executed as independent release gates.

## GitHub Release

Push a semver tag matching `src/VERSION`, for example `v1.0.0`. `.github/workflows/release-windows.yml` validates the tag, executes the full GA builder on `windows-latest`, preserves evidence as a workflow artifact, and publishes the Windows ZIP plus checksum to GitHub Releases.
