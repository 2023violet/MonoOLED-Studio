# MonoOLED Studio 2 User Guide

MonoOLED Studio is a workbench for generic 1-bit OLED scenes, pixel assets and Font Pack glyphs. It runs on Windows, macOS and Linux. Project files are compatible with 1.2.3, so existing projects open directly.

## Installing and first run

1. Download the package for your platform from GitHub Releases. Installation steps are in the [README](../README.md).
2. Open a project with File → Open Project (`Ctrl+Shift+O`) and choose `project.oled.json`, or create one with `Ctrl+N`. You can also pass the project path when starting: `monooled-studio path/to/project`.
3. Save with `Ctrl+S`.

The segmented control at the top switches between four workspaces: Design (Scene Designer), Pixel Studio (`Ctrl+Shift+P`), Font Lab (`Ctrl+Shift+F`) and Review. `Ctrl+K` opens the command palette to search for and run commands by name.

## Scene Designer

- Click an element to select it. `Ctrl`+click adds or removes elements, and dragging on empty canvas draws a marquee. The last selected element is the primary selection.
- Alignment and distribution can use the selection, the primary element or the canvas as reference. The Inspector shows the bounds and spacing of the selection.
- `Ctrl+G` groups and `Ctrl+Shift+G` ungroups. `Ctrl+1` and `Ctrl+2` show or hide the navigator and the Inspector.
- The project navigator adds, duplicates, renames and deletes screens.
- If there are unsaved changes, switching or deleting a screen, opening another project or closing the window asks whether to save, discard or cancel. This also covers unsaved work in Pixel Studio and Font Lab.
- Autosave runs every 3 minutes by default. After a crash, reopening the same screen offers to restore the autosaved copy.

## Pixel Studio

- Drag with the left button to draw and with the right button to erase. One drag is one undo step.
- Tools: pencil, eraser, line, rectangle, fill and selection.
  - The selection can be copied, cut, pasted and cropped to.
  - The canvas can be rotated, flipped, inverted, resized (nine-point anchor) and cleared.
- The mouse wheel zooms, and the Zoom box picks Fit or a fixed factor. Drag with the middle button, or hold Space and drag, to pan.
- Move the canvas cursor with the arrow keys. Enter lights a pixel, Delete/Backspace clears it and Esc hides the cursor.
- Pixel rulers run along the top and left edges and can be turned off in Preferences.
- When you open a JPG, BMP or other non-PNG image, it is converted to 1-bit by threshold. Saving writes a new PNG; the original file is not overwritten.

### Output workbench

The Inspector's Output tab is the output workbench.

- **Source**: the current Pixel canvas, the current selection, the current Designer frame, a project Font Pack, or an image file. Only images need thresholding; every other source is already 1-bit.
- **Raster and encoding**: the four scan modes, whether the first pixel goes to bit7 or bit0, and whether lit pixels encode as 1 or 0.
- **Format**: text array or BIN, hex or decimal, bytes per line, Font Pack index mode, and the prefix and suffix fields.
- **Profiles**: output profiles can be saved into the project.
- **Display**: these settings only affect display, never the exported bytes.
  - Canvas background, grid, pixel fill and pixel border colours. Click a swatch to pick from the palette, or type `#RRGGBB`.
  - Pixel size.
  - Font and size of the output text.

The output panel at the bottom generates, copies, saves or clears the output. Clear only empties the output; it does not touch the canvas. The exact formulas are in [OUTPUT_WORKBENCH.md](OUTPUT_WORKBENCH.md).

## Font Lab

- Font Packs normally live in the project's `.oled/fonts/` folder. A pack stores the cell size, baseline, advance, the character set and the pixels of every glyph.
- Glyphs can be generated from a TTF/OTF font file, or from the built-in 5×7 glyphs when no font is given. Size, threshold, alignment and antialias sampling are adjustable.
- Generation runs in the background. Progress appears in the status bar and the window stays usable.
- Pick a character in the glyph list to edit it pixel by pixel. When you switch characters, an edited glyph is saved automatically.
- Scene `bitmap_text` elements and Font Lab use the same Font Pack data.

## Automation API (Code AI Bridge)

Tools → Code AI Bridge starts a JSON-RPC 2.0 endpoint on the loopback interface and shows its port and session token. The endpoint shares the live Designer session, and each batch of agent edits becomes one undoable step.

- Call `automation.capabilities` first, then read the project and scene contracts.
- Use revision guards when editing and transactions for multi-step changes. A commit only changes memory; call `project.save` or `project.save_all` to write files.
- Long-running work uses `job.start`, `job.status`, `job.result`, `job.cancel` and `job.release`.

Without the desktop app, the same API runs from the command line: `mono bridge --project <project.oled.json> --permission edit` (on Linux the command is `monooled-cli`). The full protocol is in [AUTOMATION_API_V1.md](AUTOMATION_API_V1.md).

## Command-line validation and export

```bash
mono validate --project project.oled.json
mono export --project project.oled.json --output exports/latest
mono batch-validate --project project.oled.json
mono handoff --project project.oled.json
```

The desktop app, the CLI and the Automation API share one renderer and one set of validation rules.

In the desktop app, export, the Code AI handoff, batch validation and the thumbnail wall run in the background. Progress shows in the status bar and you can keep editing. One background job runs at a time; to cancel it, use `Ctrl+K` → "Cancel background job". The app will not close or open another project until the job finishes.

## Preferences and data locations

- Preferences (`Ctrl+,`) cover language, appearance, UI scale, input, autosave, performance and shortcuts.
- The preferences file is the same one 1.2.3 used:
  - Windows: `%LOCALAPPDATA%\MonoOLEDStudio\preferences.json`.
  - macOS and Linux: `~/.config/monooled-studio/preferences.json`, or under `XDG_CONFIG_HOME` when that is set.
- Logs, autosaves, previews and asset caches are kept in the project's `.oled/` folder.
