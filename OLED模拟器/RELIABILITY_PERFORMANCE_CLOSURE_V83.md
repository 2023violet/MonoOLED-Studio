# MonoOLED Studio 8.3 — Reliability & Performance Closure

## Scope

V8.3 is a correctness, lifecycle, performance and Windows-release hardening pass over V8.2. It deliberately does not alter OLED framebuffer semantics, the 14 clinical Golden frames, or the 464 frozen product assets.

## Correctness closure

- `OLEDCanvas.mouseReleaseEvent` now has a single implementation. Marquee release, Ctrl-marquee toggle, selection emission and drag release share one lifecycle instead of one method silently overriding another.
- `StudioSelect` fully constructs `popup/list` before installing event filters and connecting active callbacks. Defensive null guards remain.
- English workspace labels `Design` and `Review` no longer contain Chinese source text.
- The first-run font scan remains part of main-window initialization and is covered by the Real-Qt startup test.

## Startup truth

V8.3 separates three different checks:

- `--core-check` / legacy `--check`: dependency + project + renderer truth. This is intentionally not described as a GUI startup test.
- `--startup-smoke`: constructs a real `QApplication` and `OLEDDesignerWindow`, processes the Qt event loop and closes cleanly.
- Windows standalone smoke: runs the PyInstaller application through startup, interaction, layout and soak gates.

The source launcher now validates both runtime imports and real GUI startup. The source delivery also includes `Developer_Tools/CREATE_RUNTIME_ENV.bat` for a controlled `.venv-runtime` and `RUN_MONOOLED_DIAGNOSTIC.bat` for a visible diagnostic console.

The root `MonoOLEDStudio.exe` in this source delivery is the previously verified compatibility runtime-locator binary, not a falsely relabeled V8.3 rebuild. Its SHA-256 is pinned in `DELIVERY_MANIFEST.json`. A rebuilt authoritative launcher/standalone is produced by the Windows release gate.

## Qt lifecycle closure

- Agent Bridge no longer runs a permanent 100 Hz timer while disabled.
- `start()` owns server/thread/timer activation; `stop()` stops the timer, shuts down the server, joins the worker and clears references.
- Main-window close invokes Agent Bridge shutdown.
- `SystemThemeProvider` uses a bound slot and explicit disconnect instead of an application-lifetime signal retaining a window-owned lambda.

## Interactive performance architecture

### Geometry

`EditorSession.geometry()` no longer renders a full framebuffer. It resolves geometry directly from the scene/runtime state using the same resource service as the renderer.

### Smart guides

`smart_guides()` therefore no longer performs `N × full-render` work. Multi-object guide lookup is geometry-bound rather than framebuffer-bound.

### Resource cache

`RenderResources` persists decoded bitmap, mode-font and FontPack resources across EditorSession renders. Correctness is protected with content digests, so same-size/same-mtime mutation cannot silently reuse stale pixels.

### Canvas paint

The Qt canvas caches the framebuffer as a `QImage` and uses nearest-neighbour `drawImage` for the OLED pixel plane. Selection, rulers, grid and guide overlays remain separate editor paint layers.

### History

Drag, nudge, align and distribute operations use batch/coalesced commands so one user gesture produces one undo command rather than N independent geometry commands.

## Data robustness and diagnostics

- Corrupt Preferences are copied to a timestamped quarantine before defaults are recovered.
- FontPack manifests/glyphs, exporter JSON/PNG and Scene writes share atomic write primitives where applicable.
- Shortcut conflicts reject the conflicting override while preserving unrelated valid custom bindings.
- A rotating standard diagnostic log supplements (not replaces) the existing domain SessionLogger.

## Windows GA rule

A Windows GA artifact must have:

1. full source suite pass;
2. real `--startup-smoke` pass;
3. every `test_qt_*.py` suite at 100/125/150/175/200/225/250/300% with JUnit `0 skipped / 0 failed`;
4. V8.2 visual stress and V8.3 reliability/performance stress pass;
5. PyInstaller onedir build pass;
6. executable core/startup/layout/interaction/soak pass.

The Linux source-packaging host cannot satisfy this Windows-native gate because PySide6 is unavailable locally. That boundary remains explicit.
