# V12.4.2 Settings Geometry Convergence

V12.4.2 is a corrective release driven by Windows desktop screenshots showing that several Settings rows still clipped or overlapped wrapped helper text at 1680×900 even after the V12.4.1 text/control-column split.

## Root causes

1. `PreferencesContent` was inserted into the page layout with horizontal alignment. Qt therefore honored the widget size hint instead of expanding the content to the available desktop width. The nominal 760px maximum was not a 760px target; on the reported Windows geometry the content collapsed to roughly the natural width of the text/control pair and forced unnecessary wrapping.
2. The generic QWidget used as the text column did not reliably propagate the wrapped QLabel height-for-width requirement through the nested layout on Windows. The child copy could wrap to two lines while the outer SettingRow still received a one-line height.

## Corrective geometry model

- The scroll viewport is the width source of truth. `PreferencesContent` receives a dynamic minimum width equal to the usable viewport width capped by the 760px product maximum. This preserves centered desktop composition without allowing the content to shrink to its size hint.
- `SettingsTextColumn` explicitly implements `hasHeightForWidth()` and `heightForWidth()` and synchronizes its minimum height whenever its width changes.
- `SettingRow` also exposes height-for-width for both side-by-side and compact stacked modes. No page-specific fixed row heights or translated-string exceptions are used.
- `layout_violations()` now checks the text-column aggregate height in addition to individual label/help widgets.

## Regression matrix

The V12.4.2 Real-Qt regression iterates all seven Settings pages at 1680×900 for Simplified Chinese and English at 100%, 125%, and 150% UI scale. It requires content width >=740px when the viewport permits, zero layout violations, complete text-column height, and non-overlap between row content and dividers. The generic Windows GA runner already executes every `test_qt_*.py` module at all configured DPI scales, so this module is automatically part of the zero-skip Windows gate.

## Release boundary

Linux Source gates can validate source contracts, package integrity, deterministic builds, and non-Qt behavior. They cannot certify native Windows font metrics or Qt layout. Windows GA remains mandatory before calling a Windows executable Final/GA.
