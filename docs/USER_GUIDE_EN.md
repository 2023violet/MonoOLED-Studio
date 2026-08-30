# MonoOLED Studio 8.0 User Guide

MonoOLED Studio 8.0 uses one main-window document workspace. Scene Designer, Pixel assets and Font Lab open as reusable tabs. Save/Undo/Redo are routed to the active editor.

Designer supports ordered multi-selection, Ctrl+left-click toggle, marquee selection, explicit Primary Selection and Align-to Selection/Primary/Canvas.

Pixel Workspace keeps left-draw/right-erase, adds Fit zoom, anchored canvas resize, crop, 90/180/270 rotation, flips and exact FontPack text insertion.

Font Lab stores durable FontPack/GlyphPack assets with cell size, baseline, advance and exact glyph pixels. `bitmap_text` Scene elements use the same FontPack truth.

The optional localhost Code AI bridge is semantic rather than coordinate-driven. It uses a session token, permission levels, revision guards and transactions, and can return rendered PNG/VLSB/framebuffer hashes/resolved geometry/validation evidence.


## V8.4.2 Code AI data safety and long operations

Automation API 1.2 separates transaction commit from disk persistence. After an Agent commits an in-memory Scene transaction, `project.get.dirty` stays true until the Scene is saved. `project.open_screen` fails closed with `UNSAVED_CHANGES` unless the caller explicitly chooses `save_current=true` or `discard_current=true`.

For large state matrices, call `state.count` first. Use summary responses when per-frame metadata is unnecessary, or run `render.all_states`, `validate.all_states`, `export.all`, and `export.code_ai_handoff` through `job.start/status/result/cancel` for server-owned progress and cooperative cancellation.

## V8.4.3 Windows release validation

V8.4.3 adds no Designer or Automation feature surface. It makes the Windows GA path reproducible: delivered `.bat/.cmd` files are CRLF-only, source tests run in bounded groups, and each `test_qt_*.py` module runs in its own timed process at 100–300% DPI with JUnit/log evidence and zero-skip enforcement. Native Windows GA still requires the delivered `tools\BUILD_WINDOWS_GA.bat` to complete on Windows.


## V12.3 Windows distribution

End users download `MonoOLEDStudio_v1.0.0_Windows_x64.zip` from GitHub Releases, extract it, and double-click `MonoOLEDStudio\MonoOLEDStudio.exe`. End users do not need Python or BAT files. Developers use `tools\BUILD_WINDOWS_QUICK.bat` for a fast local EXE; the full `tools\BUILD_WINDOWS_GA.bat` is reserved for native Windows certification and the tag-driven GitHub Release workflow.
