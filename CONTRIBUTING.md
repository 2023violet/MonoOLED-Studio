# Contributing to MonoOLED Studio

Thanks for taking the time to contribute! This project is a Windows-focused,
generic 1-bit OLED scene and pixel authoring workbench.

## Getting started

1. Fork the repository and clone it.
2. Create a feature branch: `git checkout -b feat/my-change`.
3. Install development dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

4. Run the source gate before and after your change:

```bash
python -m pytest
python VERIFY_PACKAGE.py
```

## Making changes

- Keep changes focused; one logical change per commit.
- Match the existing code style and naming conventions.
- Do not add comments unless they clarify intent the code cannot.
- Update the relevant tests when you change behavior.
- Do not commit build artifacts (`build/`, `dist/`, `.artifacts/`, `release/`)
  or runtime state (`.oled/`).

## Running the app

```bash
python src/gui.py
```

## Building the Windows executable (developers)

```bash
tools\BUILD_WINDOWS_QUICK.bat
```

The full certified build is `tools\BUILD_WINDOWS_GA.bat`. End users download
the prebuilt ZIP from GitHub Releases; do not commit a root `MonoOLEDStudio.exe`.

## Reporting issues

Open a GitHub issue and include:

- The MonoOLED Studio version (`src/VERSION`) and Windows version.
- Steps to reproduce.
- Expected vs. actual behavior.
- Any relevant screenshots or `--startup-smoke` / `--check` output.

## Code of conduct

Please be respectful and constructive. Harassment or abusive behavior will
not be tolerated.
