# MonoOLED Studio 7.1 — Product Closure

## 1. Baseline

V7.1 is an incremental closure release built from the complete V7.0 delivery, not a reduced rewrite.

- V7.0 baseline ZIP SHA-256: `7210e33807643a6b1e743cf18aefa074fd51534f97e7e2bb0e2cbd2713256da7`
- Baseline delivery files: 653 before cache exclusions
- Baseline files removed in V7.1: **0**
- Frozen Curing-Lite/product assets: **464**
- Frozen clinical Golden BIN: **14 × 512 B**

The root `MonoOLEDStudio.exe` remains the exact V7.0 native PE runtime-locator launcher. It launches the source application from the delivery tree and is intentionally not represented as a V7.1 self-contained PyInstaller build. The self-contained Windows build must be produced by the Windows release gate.

## 2. Closure architecture

V7.1 preserves Renderer/Scene/VLSB/Golden/product-asset truth and closes the product shell around it.

### 2.1 Preferences

`preferences.py` now performs field-level semantic normalization. A syntactically valid but semantically corrupt JSON file cannot propagate arbitrary lists/dicts/strings into runtime settings. Known fields fail closed to their defaults while unknown/future fields are preserved.

`runtime_settings.py` is the materialization boundary between stored values and production consumers. Every public default Preference is listed in `RUNTIME_EFFECTS`; adding a new Preference without an explicit runtime effect causes a development-time failure.

The Preferences UI now includes real runtime wiring for:

- language and live page retranslation;
- startup reopen-last-project;
- Theme Mode / Color Theme / Density / UI Scale;
- wheel, middle-button pan and Space+left pan;
- canvas overlays and snap;
- Pixel Studio brush size / grid / interpolation / preview;
- autosave interval / retention / recovery prompt;
- drag preview / validation timing / undo bound / asset cache budget / performance overlay;
- editable, conflict-checked shortcuts;
- real Clear Asset Cache and Reset Workspace actions.

The fixed product interaction `left mouse = draw/set 1`, `right mouse = erase/set 0` remains non-configurable in behavior even though legacy keys are normalized for backward compatibility.

### 2.2 Interaction foundation

`ui_controls.py` provides the Production button layer:

- `StudioButton`
- `StudioToolButton`

They explicitly own the dynamic visual properties:

- `hoverVisible`
- `pressedVisible`
- `keyboardFocusVisible`

Hover/pressed/focus cleanup happens on Leave, release, FocusOut and disable. Mouse press clears a keyboard-origin focus ring immediately, including the same-control `Tab → mouse click` case where Qt may not send a second FocusIn.

The stylesheet consumes those explicit properties instead of relying on implicit `:hover` / `:pressed` lifetimes for Studio controls.

### 2.3 Project/filesystem safety

All project-owned screen and asset paths are resolved through a root-confinement boundary. V7.1 rejects:

- `../` traversal;
- absolute/external screen paths;
- unsafe screen IDs;
- project asset directories outside the project root;
- import destinations escaping the project root.

External reusable asset libraries, if needed in a future version, must be designed as an explicit mount concept rather than smuggled through relative traversal.

### 2.4 Autosave and recovery

Autosave writes now use temporary file + flush/fsync + atomic replace. Recovery scans newest to oldest and quarantines malformed or semantically invalid snapshots instead of letting a corrupt newest file hide an older valid recovery point.

### 2.5 Asset cache

Cache identity now includes a content SHA-256. A file whose byte content changes while size and mtime remain identical is invalidated correctly.

### 2.6 Pixel Studio

V7.1 retains the V7 mouse grammar and extends the product closure around it:

- left draw / right erase;
- Bresenham continuous interpolation;
- one gesture = one undo transaction;
- brush size 1–8;
- preference-gated wheel zoom;
- preference-gated middle-button pan;
- preference-gated Space+left pan;
- oversized image pre-allocation guard;
- strict-ASCII C identifier generation.

### 2.7 Theme system

Custom editor chrome consumes semantic tokens. Primary-button text gets an explicit `accent.on_primary` token, and the shipped token pairs used by the closure tests meet a 4.5:1 contrast floor for primary-button text and muted panel text.

## 3. Test philosophy

V7.1 distinguishes architecture contracts from behavioral proof.

A source-string test may still protect an architectural invariant, but it is not treated as sufficient evidence for a user-visible feature. Product behavior is expected to follow:

`Requirement → Production object → User stimulus → Observable effect → Persistence/negative path → Regression evidence`.

Real Qt tests instantiate Production Studio controls, PixelCanvas, PixelStudioWindow, PreferencesWindow and OLEDDesignerWindow.

## 4. Windows release boundary

The repository contains a mandatory Windows workflow and `Developer_Tools/BUILD_WINDOWS_EXE.bat`.

The V7.1 Real-Qt matrix is:

`4 DPI × 4 themes × 2 languages × 3 densities × 3 production surfaces = 288 production-surface constructions`.

The Windows gate additionally tests:

- Production ToolRail exact raster restoration;
- same-control keyboard-focus → mouse-focus cleanup;
- real middle/Space pan;
- shortcut conflict atomicity;
- source regression;
- `--check`;
- real-window smoke;
- layout smoke;
- interaction smoke;
- soak smoke;
- PyInstaller onedir construction.

A non-Windows packaging host must not claim those Windows gates passed.

## 5. Release invariant

A V7.1 package is acceptable only if all of these remain true:

1. all 464 frozen product assets are byte-identical to V7.0;
2. all 14 Golden BIN are byte-identical to V7.0 and exactly 512 bytes;
3. the complete V7.0 file set is retained unless an explicitly documented replacement exists;
4. `VERIFY_PACKAGE.py` passes after fresh extraction;
5. Host/Core regression is green;
6. Windows Real-Qt/standalone status is reported accurately rather than inferred from prepared workflow files.
