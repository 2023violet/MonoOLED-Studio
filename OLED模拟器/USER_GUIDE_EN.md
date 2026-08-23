# MonoOLED Studio 8.0 User Guide

MonoOLED Studio 8.0 uses one main-window document workspace. Scene Designer, Pixel assets and Font Lab open as reusable tabs. Save/Undo/Redo are routed to the active editor.

Designer supports ordered multi-selection, Ctrl+left-click toggle, marquee selection, explicit Primary Selection and Align-to Selection/Primary/Canvas.

Pixel Workspace keeps left-draw/right-erase, adds Fit zoom, anchored canvas resize, crop, 90/180/270 rotation, flips and exact FontPack text insertion.

Font Lab stores durable FontPack/GlyphPack assets with cell size, baseline, advance and exact glyph pixels. `bitmap_text` Scene elements use the same FontPack truth.

The optional localhost Code AI bridge is semantic rather than coordinate-driven. It uses a session token, permission levels, revision guards and transactions, and can return rendered PNG/VLSB/framebuffer hashes/resolved geometry/validation evidence.
