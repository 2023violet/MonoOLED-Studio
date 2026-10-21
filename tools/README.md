# MonoOLED Studio Developer Tools

Python 3 scripts used by CI and maintainers. None of them is a runtime dependency of the app.

- `PACKAGE_RUST_RELEASE.py` — packages the release binaries for the current platform (Windows zip, macOS dmg, Linux deb) and writes `SHA256SUMS`. `--print-version` prints the workspace version.
- `CHECK_SMOKE_SCREENSHOT.py` — rejects blank, single-colour or text-less desktop smoke screenshots (CI install tests).
- `RUN_DESKTOP_BENCH.py` — runs the desktop app's `--bench` mode and reports the spec §5 interactive budgets and idle memory.
- `BUILD_AI_CONTEXT.py` — writes the disposable `.ai/GENERATED_CONTEXT.md` navigation packet.
- `tests/` — pytest tests for these scripts and the rewrite governance rules (`python -m pytest tools/tests -q`).

The 1.x build, delivery and golden-corpus export tools are kept at the `v1-final` tag.
