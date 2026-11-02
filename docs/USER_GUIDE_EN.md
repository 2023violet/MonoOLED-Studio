# MonoOLED Studio 2 User Guide

MonoOLED Studio is a workbench for generic 1-bit OLED scenes, pixel assets and Font Pack glyphs. It runs on Windows, macOS and Linux. Project files are compatible with 1.2.3, so existing projects open directly.

## Installing and first run

1. Download the package for your platform from GitHub Releases. Installation steps are in the [README](../README.md).
2. Open a project with File → Open Project (`Ctrl+Shift+O`) and choose `project.oled.json`, or create one with `Ctrl+N`. You can also pass the project path when starting: `monooled-studio path/to/project`.
3. Save with `Ctrl+S`.

The segmented control at the top switches between four workspaces: Design (Scene Designer), Pixel Studio (`Ctrl+Shift+P`), Font Lab (`Ctrl+Shift+F`) and Review. `Ctrl+K` opens the command palette to search for and run commands by name.

## Scene Designer

- Click an element to select it. `Ctrl`+click adds or removes elements; pressing on empty canvas clears the selection. The last selected element is the primary selection.
- Alignment and distribution can use the selection, the primary element or the canvas as reference. The Inspector shows the bounds and spacing of the selection.
- `Ctrl+G` groups and `Ctrl+Shift+G` ungroups. `Ctrl+1` and `Ctrl+2` show or hide the navigator and the Inspector.
- The project navigator adds, duplicates, renames and deletes screens. **Rename** moves the scene file with the screen and re-opens it under the new id.
- Viewing a screen is not an edit: switching screens does not rewrite `project.oled.json`. The active screen is recorded on the next explicit save, so after a restart the project reopens on the last **saved** screen, not the last one you looked at.
- If there are unsaved changes, switching or deleting a screen, opening another project or closing the window asks whether to save, discard or cancel. The prompt names the documents that actually changed (Designer scene, Pixel Studio bitmap, Font Lab pack). This also covers unsaved work in Pixel Studio and Font Lab.
- Undo back to the saved scene clears the title's `•` marker. Pixel Studio is a standalone PNG and keeps its own `•` in its panel header.
- Export, handoff, batch validation and thumbnail-wall export run the same validation gate. When a blocking finding exists they stop, list the findings in a dialog (with **Go to** for each element) and write no export artefact; the findings themselves are saved as a report next to where the output would have gone. Export and handoff stop at the first blocking frame, and the report says how many frames were checked.
- Esc closes any dialog, and so does clicking the dimmed area outside it.
- The Navigator scrolls to the selected page, element or glyph, so a selection made from the canvas or with the arrow keys is never hidden below the fold.
- The canvas toolbar's **Zones** toggle draws the project's design zones over the canvas, in the same editor-only layer as the grid and bounds.
- The Inspector's **Schema** tab (State schema) edits the scene's state variables and their relations; **Rules** (Design rules) edits required elements, zones and baseline groups. The tab strip abbreviates both names because five tabs do not fit the panel at the smallest window width; inside, each section is titled by what it edits. An entry the engine cannot accept stays on screen with its own message, and is never written to disk.
- Design rules live in `project.oled.json` and are written as you edit them, so the title's `•` does not track that file; the panel names the manifest it wrote.
- Export, handoff, batch validation and the thumbnail wall run in the background: the status bar shows their progress and offers **Cancel background job**.
- Autosave runs every 3 minutes by default. After a crash, reopening the same screen offers to restore the autosaved copy.

## Device preview, annotations and review

- The State tab in the Inspector starts with a device bezel. Play advances the timeline with a minimum 500 ms step interval (approximately two steps per second, not a real-time clock), Step pauses and advances once, and Reset returns to the init state; the event list below records `RESET` and `STATE`. Playback only changes runtime state and never marks the scene as modified.
- The preset section lists the init state, every non-initial enum value and both bounds of every integer. Save the current state as a named scenario; scenarios live in the project's `review/review.json`.
- The 批注 (annotations) tab records a defect, decision or explanation against the current screen and state. With an element selected the note is anchored to it and stores the frame's SHA-256 and lit-pixel count; when the frame changes in the same state the note shows a stale badge.
- The Review workspace switches between Device and Code: the device view compares the last opened/saved frame with the current one, the code view shows the C array and the VLSB hex. The Evidence panel shows the frame hash, the golden hash from `exports/latest/ui_contract.json`, lit pixels and visible elements. A fresh export is adopted automatically; Load contract… accepts another file.
- `Ctrl+Shift+L` opens the screen gallery: one init-frame card per screen, grouped by category, searchable and filterable by All/Blocking/Annotated. Open goes to Designer (after the unsaved check, with the runtime reset); Review goes straight to the Review workspace.
- File → Review pack (HTML) writes an offline single-file review pack; the CLI equivalent is `mono review-pack`. Contents and scope are in [REVIEW_PACK.md](REVIEW_PACK.md).
- This build does not simulate keys or hardware events, and there is no second renderer: the in-app simulator boundary text and the review pack both say so.

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
- Glyphs can be generated from a TTF/OTF font file, or from the built-in 5×7 glyphs when no font is given. Size, threshold, alignment and antialias sampling are adjustable, as is the horizontal/vertical glyph offset — an offset leaves the built-in 5×7 path, so it needs a font file.
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

In the desktop app, export, the Code AI handoff, batch validation and the thumbnail wall run in the background. Progress and a **Cancel** control sit in the status bar, and you can keep editing. One background job runs at a time; `Ctrl+K` → "Cancel background job" does the same thing. The app will not close or open another project until the job finishes.

## Preferences and data locations

- Preferences (`Ctrl+,`) cover language, appearance, UI scale, input, autosave, performance and shortcuts.
- The preferences file is the same one 1.2.3 used:
  - Windows: `%LOCALAPPDATA%\MonoOLEDStudio\preferences.json`.
  - macOS and Linux: `~/.config/monooled-studio/preferences.json`, or under `XDG_CONFIG_HOME` when that is set.
- Logs, autosaves, previews and asset caches are kept in the project's `.oled/` folder.

## Glossary

The English UI keeps the product names and the established OLED vocabulary below. The Chinese UI uses the translations listed in the Chinese guide.

| Term | Meaning |
| --- | --- |
| Scene | One exportable screen of a project (the UI container; not a hardware display) |
| Screen | Hardware/display context only |
| Pixel Studio | 1-bit editor workspace (brand name kept in English) |
| Font Lab | Glyph-pack workspace (brand name kept in English) |
| Diff Review | Compares the last opened/saved state with the current scene; no version history is implied |
| Production Preview | Render output that matches export bit for bit |
| Framebuffer | The 1-bit output buffer |
| Overlay | Editor-only guides and selection marks that never reach the export |
| Pixel Truth | The canonical renderer's 1-bit pixels |
| Generate glyphs | Font-pack context |
| Generate bitmap array | Generic bitmap output (not “font matrix”) |
