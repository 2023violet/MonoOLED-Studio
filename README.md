# MonoOLED Studio V1.1.0 — Output Workbench Release

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MonoOLED Studio is a Windows-focused, generic 1-bit OLED scene and pixel authoring workbench.

## Download for Windows — GitHub Releases

**Normal users do not need Python, Git, or any BAT file.** Open this repository's **GitHub Releases** page, download:

`MonoOLEDStudio_v1.1.0_Windows_x64.zip`

Extract the ZIP, keep the extracted folder together, and double-click:

`MonoOLEDStudio\MonoOLEDStudio.exe`

The release also provides `MonoOLEDStudio_v1.1.0_Windows_x64.zip.sha256` for integrity verification. The Windows application is an onedir PyInstaller build for faster startup and more predictable Qt plugin loading.

## Release model

- Normal `push` / pull request → `.github/workflows/ci.yml` runs the fast Windows source gate.
- Push a version tag such as `v1.1.0` → `.github/workflows/release-windows.yml` runs the full Windows GA, creates the EXE package, computes SHA-256, and publishes both files to GitHub Releases.
- `tools\BUILD_WINDOWS_QUICK.bat` → developer-only fast local EXE build.
- `tools\BUILD_WINDOWS_GA.bat` → developer/CI full Windows certification and release package build.

## Developer source run

```bash
python -m pip install -r requirements.txt
python src/gui.py
```

Developer verification:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
python VERIFY_PACKAGE.py
```

Deterministic source delivery ZIP:

```bash
python tools/BUILD_SOURCE_DELIVERY.py
```

## Repository

| Path | Purpose |
| --- | --- |
| `src/` | Production application, generic scene, branding |
| `tests/` | Regression and release-engineering tests |
| `tools/` | Quick/GA build, release, and verification tooling |
| `test_assets/` | Test fixtures and frozen product regression assets |
| `docs/` | Current product, API, design, and release documentation |
| `.github/` | CI and automated GitHub Release workflows |

The root intentionally does not ship a stale `MonoOLEDStudio.exe`. End-user Windows binaries belong in GitHub Releases and are built from the tagged source on a native Windows runner.

## License

[MIT](LICENSE). See [CONTRIBUTING](CONTRIBUTING.md) for contribution guidelines and [SECURITY](SECURITY.md) for reporting vulnerabilities.
