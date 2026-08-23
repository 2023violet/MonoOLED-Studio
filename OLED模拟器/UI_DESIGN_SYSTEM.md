# MonoOLED Studio 7.1 — UI Design System

## Product language

MonoOLED Studio is a **professional editor**, not a Bento dashboard. Canvas remains the visual center. Inspector/settings surfaces use flat sections and thin separators; cards are reserved for genuinely summary-oriented surfaces.

## Interaction vocabulary

Every control must distinguish Normal, Hover, Pressed, Selected, Selected+Hover, Keyboard Focus and Disabled. State changes must not change control geometry. Mouse focus and keyboard focus are separate.

## Semantic color tokens

Components consume `app.background`, `surface.*`, `text.*`, `border.*`, `accent.*`, `status.*` and `canvas.*` tokens from `theme_system.py`; components must not invent local colors for ordinary states.

## Density

Compact, Comfortable and Spacious alter control height/padding without changing information architecture.

## Workspace

Designer: Navigator | Canvas | Context Inspector, with a collapsible Problems/Diff/Logs drawer.

Pixel Studio: Tool Rail | Pixel Canvas | Flat Context Inspector, plus status/input hints.

Preferences: independent flat Settings window; global preferences never occupy the main authoring header.
