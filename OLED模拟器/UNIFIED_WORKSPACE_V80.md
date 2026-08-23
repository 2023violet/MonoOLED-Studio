# MonoOLED Studio 8.0 — Unified OLED Workspace Architecture

## Product boundary

V8 keeps the existing Renderer, VLSB export semantics, Clinical state truth and frozen Curing-Lite assets. The new architecture sits above those truths.

```text
App Shell
  └─ WorkspaceHost / EditorRegistry
       ├─ Scene Editor
       ├─ Pixel Editor
       └─ Font Lab

Application Services
  ├─ SelectionModel
  ├─ EditorSession / History
  ├─ FontPack / PixelDocument
  └─ StudioAutomationService

Renderer / Validation / Framebuffer / Golden
```

## Unified workspace

The main Designer owns a movable/closable document tab host. The first tab is the Scene editor. Opening a bitmap creates or reuses an `asset:<path>` tab; opening a font creates or reuses a `font:<path>` tab. Global Save/Undo/Redo are routed to the active editor through `EditorRegistry` rather than being permanently bound to the Scene editor.

Pixel Studio remains a `QMainWindow` subclass for source/API backward compatibility, but when hosted by the Designer it is assigned `Qt.Widget` flags and is therefore an embedded document editor, not a second top-level window.

## Selection 2.0

`SelectionModel` is the authority for ordered selected IDs and explicit `primary_id`. Canvas, Navigator and Inspector synchronize through the same model. The interaction contract is:

- Left click: replace selection and set Primary.
- Ctrl + Left click: toggle object; the latest added object becomes Primary.
- Drag on empty canvas: marquee selection.
- Ctrl + marquee: additive/toggle-compatible multi-selection path.
- Primary Selection remains explicit instead of being inferred from Scene element ordering.

Alignment supports `selection`, `primary` and `canvas` reference modes. Multi-selection metrics expose group bounds and ordered horizontal/vertical gaps.

## Control System 2.0

`StudioSelect` owns both its closed button and its frameless translucent `StudioPopover`, preventing the old mismatch where a rounded closed QComboBox opened a square native popup. `StudioNumericInput` removes native platform stepper chrome. Production buttons continue to use explicit hover/pressed/keyboard-focus dynamic properties.

## Pixel Workspace 2.0

Pixel editing retains fixed product semantics: left mouse draws and right mouse erases. New operations include:

- Fit zoom with automatic recomputation on viewport changes.
- Canvas resize with 9-point anchors.
- 90°/180°/270° rotation, horizontal/vertical flip and crop.
- FontPack bitmap-text insertion at an exact pixel coordinate.
- Existing Pencil/Eraser/Line/Rectangle/Fill/Select, Bresenham interpolation and one gesture/one Undo.

Arbitrary-angle rotation is intentionally not promoted as a core operation because it requires destructive 1-bit re-rasterization.

## Font Lab

A FontPack is a project-owned durable asset:

```text
<font>/
  fontpack.json
  glyphs/
    U+0041.png
    ...
```

The manifest stores cell size, baseline, default advance and per-glyph metrics. Font Lab can rasterize from a TTF/OTF path or deterministic fallback font, edit exact glyph pixels and save them back to the pack. `bitmap_text` is a new Scene element type that renders exact FontPack glyphs. Legacy `text` rendering is unchanged, protecting existing Golden output.

## Code AI automation

`StudioAutomationService` operates on semantic project objects, never GUI coordinates. It exposes project/scene/selection/layout/pixel/font/render/validation/history surfaces. Every response includes a revision. Mutating requests may provide an expected revision; stale edits fail rather than overwriting newer human changes.

Scene transactions group multiple AI changes into one Designer Undo step. The localhost bridge requires a random session token and supports `observe`, `edit` and `full` permission levels. In the live GUI, `QtAutomationBridge` drains requests on the Qt UI thread.

Automation feedback includes:

- Scene and selection state.
- Resolved elements.
- VLSB bytes and framebuffer SHA-256.
- Base64 PNG render evidence.
- State-to-state pixel diff.
- Validation findings and blockers.
- Session events/revisions.

The bridge is disabled by default and only binds to localhost when explicitly enabled.

## Hardware boundary

The automation/render pipeline can replace most repeated physical-board checks for layout, glyph, clipping, overlap and framebuffer truth. It does **not** replace SSD1316 bus timing, real scan/remap configuration, panel brightness/ghosting, power integrity or MCU transfer validation.
