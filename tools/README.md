# MonoOLED Studio Developer Tools

Python 3 scripts used by CI and maintainers. None of them is a runtime dependency of the app.

- `PACKAGE_RUST_RELEASE.py` — packages the release binaries for the current platform (Windows zip, macOS dmg, Linux deb) and writes `SHA256SUMS`. `--print-version` prints the workspace version.
- `CHECK_SMOKE_SCREENSHOT.py` — rejects blank, single-colour or text-less desktop smoke screenshots (CI install tests).
- `RUN_DESKTOP_BENCH.py` — runs the desktop app's `--bench` mode and reports the spec §5 interactive budgets and idle memory.
- `CHECK_GUI_TRUST.py` — drives the real window to pin the interface-truth fixes a user touches (modal focus, settings rendering, zones overlay, job status and Cancel, undo naming, state schema and design-rule editing, page rename, dirty across undo, the export gate, glyph offsets and font-pack containment, canvas picking, multi-select naming, scroll to selection, Font Lab and Inspector layouts at the minimum size). Needs a display; defaults to the debug build, `--exe` takes any build. Not part of the CI gate.
- `BENCH_DESIGNER_PROJECT.py` — writes a disposable copy of the fixture project with N extra elements (and optionally K `digits` elements) for the Designer edit benchmark; pass its output to `RUN_DESKTOP_BENCH.py --project`.
- `BUILD_AI_CONTEXT.py` — writes the disposable `.ai/GENERATED_CONTEXT.md` navigation packet.
- `tests/` — pytest tests for these scripts and the rewrite governance rules (`python -m pytest tools/tests -q`).

The 1.x build, delivery and golden-corpus export tools are kept at the `v1-final` tag.
