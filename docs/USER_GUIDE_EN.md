# MonoOLED Studio 1.1.0 User Guide

MonoOLED Studio is a Windows-focused workbench for designing generic 1-bit OLED scenes, pixel assets, and FontPack glyphs. The default project is generic; product-specific assets remain in test fixtures.

## First Run

1. Start `MonoOLEDStudio.exe` from the Windows release, or run `python src/gui.py` during development.
2. Open or create a project and choose a scene from the project navigator.
3. Use `Ctrl+S` to save. The active document tab owns Save, Undo, and Redo.

The main window keeps Scene Designer, Pixel Studio, and Font Lab in one tabbed workspace. Reopening an asset reuses its existing tab.

## Scene Designer

Click an element to select it. Use Ctrl-click to add or remove elements, or drag across empty canvas space for marquee selection. The last selected item is the primary selection. Alignment and distribution can target the selection, primary element, or canvas; the Inspector reports bounds and measurements for the current selection.

Use the scene list to add, duplicate, rename, or remove screens. Opening another screen prompts before discarding unsaved work. Export and handoff commands are available from the project actions.

## Pixel Studio

Pixel Studio edits 1-bit assets in an embedded tab. Left-drag paints and right-drag erases. Fit zoom, middle-button panning, anchored resize, crop, rotate, flip, and one-step undo/redo are available. Imported non-PNG files are saved as a new PNG so the source file is never overwritten.

The Output Workbench selects the current canvas, selection, active Designer frame, or a FontPack. It exposes the four traversal formulas, first-point bit placement, lit-point polarity, hexadecimal/decimal and custom wrappers, plus FontPack indexes. Generate, copy, save, and clear-output are available directly below the canvas; clearing output never clears pixels. See `OUTPUT_WORKBENCH.md` for exact formulas and the portable project profile format.

## Font Lab

FontPack assets live inside the project, normally under `.oled/fonts/`. A pack stores cell size, baseline, advance, characters, and glyph pixels. Generate glyphs from a TTF/OTF with shared font-set or per-glyph-width horizontal alignment and 1×/2×/4× supersampling, then inspect or edit individual glyphs. Scene `bitmap_text` elements use the same FontPack data used by Font Lab.

## Automation API

The optional localhost Code AI bridge exposes semantic JSON-RPC 2.0 commands. Start with `automation.capabilities`, then inspect the project and scene contracts. Use revision guards for edits and transactions for a group of scene changes. A committed transaction changes memory first; call `project.save` or `project.save_all` to persist it.

Long operations use `job.start`, `job.status`, `job.result`, `job.cancel`, and `job.release`. Rendering can return PNG, VLSB bytes, framebuffer hashes, resolved geometry, and pixel diffs. The complete contract is in `AUTOMATION_API_V1.md`.

## Export and Validation

Use `python src/validate.py <scene>` for a direct scene check, `python src/exporter.py <scene> <output>` for a scene export, and `python src/batch_validate.py` for a state matrix. The GUI and Automation API expose the same renderer and validation logic.

## Windows Distribution

End users download `MonoOLEDStudio_v1.1.0_Windows_x64.zip`, extract it, and run `MonoOLEDStudio\MonoOLEDStudio.exe`. Python is not required. Developers can use `tools\BUILD_WINDOWS_QUICK.bat`; native release certification uses `tools\BUILD_WINDOWS_GA.bat` and the Real-Qt test groups.

Runtime data such as logs, autosaves, previews, and asset caches is kept under `.oled/` and is excluded from source delivery packages.
