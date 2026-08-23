# MonoOLED Studio 7.1 — Interaction System

V7 separates **Selected**, **Hover**, **Pressed**, **Keyboard Focus** and **Disabled**. Mouse focus must not leave a keyboard-focus ring. Focus styling never changes border width or widget geometry.

## Control state rules

- Normal → Hover → Pressed → Selected are independent visual transitions.
- Mouse leave always clears hover/pressed visual state.
- Selecting another tool must return the previous tool to its exact normal baseline.
- Disabled is authoritative: no hover, pressed, or visible focus state can remain.
- Keyboard focus is shown only after keyboard navigation (Tab / Shift+Tab).
- Dynamic roles such as Design ↔ Review must use `set_button_role()` so Qt is explicitly unpolished/polished after `objectName` changes.

## Pixel Studio input grammar

- Left mouse: draw / set 1.
- Right mouse: erase / set 0.
- Pencil therefore does not require switching to Eraser for normal work.
- Fill, Line and Rectangle use the same left=1 / right=0 binary grammar.
- Select keeps selection semantics; right click does not erase in Select mode.
- Wheel zooms.
- Middle drag pans.
- Space + left drag pans.
- Fast strokes are Bresenham-interpolated so sparse mouse events cannot create gaps.
- One mouse stroke is one undo transaction.

## Release tests

Pure-host tests cover state fuzzing and pixel continuity. `test_qt_v7_interactions.py` is the real Qt visual/interaction gate and runs on Windows with pytest-qt across the configured DPI matrix.
