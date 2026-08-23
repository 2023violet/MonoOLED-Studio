# MonoOLED Studio Automation API 1.0

> Machine-readable source of truth: `AUTOMATION_API_V1.json`  
> Transport: in-process `StudioAutomationService` or localhost token-authenticated JSON-RPC  
> API version: `1.0.0`

## Purpose

Automation API 1.0 lets Code AI operate MonoOLED Studio by project/scene/pixel/font semantics rather than GUI coordinates. The Canonical Renderer and Studio Exporter remain the only pixel/export truth.

## Recommended Agent bootstrap

1. `automation.capabilities`
2. `project.get_contract`
3. `scene.get_schema`
4. `state.get_schema`
5. `project.list_screens`
6. `project.list_assets`
7. `font.list`

The Agent should never assume screen ids, font dimensions, framebuffer layout or available methods when these discovery calls can provide them.

## Project orchestration

- `project.get`
- `project.list_screens`
- `project.open_screen`
- `project.create_screen`
- `project.duplicate_screen`
- `project.rename_screen`
- `project.delete_screen`
- `project.save`
- `project.save_all`

Screen switches rebind the active EditorSession without requiring GUI-coordinate automation.

## Scene / selection / layout

Scene CRUD, semantic selection, align/distribute/measure and scene transactions are exposed through `scene.*`, `selection.*`, `layout.*` and `history.*`.

Revision guards reject stale writes. Scene/layout/selection transactions can be committed or rolled back as one Designer history operation.

## State proof

- `state.list`
- `state.enumerate`
- `render.all_states`
- `validate.all_states`

For the bundled clinical scene, the representative policy enumerates **560 deterministic cases**. Each canonical framebuffer is **512 bytes** for the 128×32 product scene.

## Pixel / asset lifecycle

The Agent can create a blank PixelDocument, edit it using pixel-exact operations, save it, and manage project-owned assets through `pixel.*` and `asset.*`.

An image scene element created without explicit `w/h` resolves the actual bitmap size through the Studio asset loader instead of requiring the Agent to guess dimensions.

## Font

`font.*` exposes FontPack discovery, glyph observations, glyph updates, generation and metrics. FontPack remains the shared Designer/Pixel/Agent font truth.

## Visual feedback

The Agent can request:

- canonical framebuffer bytes / SHA-256;
- PNG render;
- resolved element geometry;
- pixel diff;
- validation findings;
- a preview file under the project;
- an annotated preview with element bounds/ids.

This is the primary feedback loop for OLED design without flashing hardware after every layout iteration.

## Export

Use Studio-owned export methods rather than reimplementing VLSB or C-header rules in the Agent:

- `export.current`
- `export.all`
- `export.c_header`
- `export.font_pack`
- `export.code_ai_handoff`

## Permissions

Three modes exist:

- `observe`: read/measure/render/validate;
- `edit`: normal project editing;
- `full`: full local automation operations.

The JSON-RPC bridge listens on localhost and requires a session token.

## Transaction boundary

The scene/layout/selection transaction is explicitly undoable/rollback-capable. Pixel files, FontPack files, asset CRUD and project-manifest file operations are not falsely presented as part of that same in-memory scene rollback. Agents should save/commit those operations deliberately.

## Graduation workflow

The V8.4 release gate proves this sequence automatically:

`discover → create/open Screen → create Pixel asset → edit/save → create Scene element → render → validate → save all → Studio handoff → reopen project`, plus a real localhost JSON-RPC capability/project roundtrip.

For final clinical work, the Agent should additionally run `render.all_states` and `validate.all_states` before export.
