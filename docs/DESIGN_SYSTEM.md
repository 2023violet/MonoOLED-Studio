# MonoOLED Studio — UI Design System (Slint)

> 真源：`apps/mono-desktop/ui/theme.slint`（颜色、密度、字体）与 `widgets.slint`（控件状态）。
> 本文档描述这些文件实现的规则；与代码冲突时以代码为准，并更新本文档。

## Product language

MonoOLED Studio is a professional editor, not a dashboard. The canvas is the visual center. Inspector and settings surfaces use flat sections and thin separators; cards are reserved for genuinely summary-oriented surfaces.

## Interaction vocabulary

Every control distinguishes Normal, Hover, Pressed, Selected, Selected+Hover, Keyboard Focus and Disabled. State changes must not change control geometry. Mouse focus and keyboard focus are separate. Overlays return keyboard focus to the workspace when they close (`focus_if_idle`).

## Themes

`Theme.mode` selects one of three token sets:

| Mode | Name | Use |
| --- | --- | --- |
| 0 | `monooled-light` | Default light UI |
| 1 | `one-dark-pro` | Dark UI |
| 2 | High contrast | Black background, maximum-contrast text and accents |

The mode comes from `appearance.theme_mode` (`system` resolves the OS hint, defaulting to light). Pixel Studio can either follow the theme (`pixel_studio.palette_mode = auto`) or keep custom colours (`custom`).

## Semantic colour tokens

Components consume `app-background`, `surface-*`, `text-*`, `border-*`, `accent-*`, `status-*` and `canvas-*` tokens from `Theme`; components must not invent local colours for ordinary states. Selected pixels use `canvas-selection`; editor-only guides use `canvas-guide`; the pixel palette derives from `canvas-off` / `canvas-on` / `canvas-grid` / `canvas-selection` in `auto` mode.

## Shape and density

| Token | Value |
| --- | --- |
| `radius-panel` | 12px |
| `radius-control` | 8px |
| `radius-pill` | 16px |
| `control-height` | 28 / 32 / 38px (compact / comfortable / spacious) |
| `pad`, `gap` | 6 / 8 / 12px |

Density changes control height and padding without changing information architecture. Font sizes: body 13px, small 11px, title 15px.

## Component rules

- **Button**: primary only for the current document's main action (Save); secondary for workspace and delivery actions; ghost for utilities; danger for destructive actions. Disabled controls keep their size.
- **IconButton / ToolButton**: always expose `accessible-label`; show a tooltip with the same text on hover. Pixel tool buttons show icon + short label.
- **Segmented**: workspace switch; selected segment uses `surface-selected` plus a 2px accent underline.
- **StatusPill**: severity/tone; never the only carrier of meaning (text is always present).
- **Dialog / Scrim**: modal overlays trap Escape and restore focus on close. Non-modal panels (Agent Bridge) never use a scrim.
- **ListView / ListRow**: `text` plus optional right-aligned `detail` (shortcut chords, codes).
- **NoteRow** (批注): kind chip, title, anchor and explicit Edit/Delete buttons on their own line; sticky notes use the warning background plus a text badge, never colour alone.
- **EvidenceRow** (Review): fixed 96px label, monospace value; a hash is only shown with a Copy button and the source contract name, so a badge always points at a real artifact.
- **GalleryOverlay**: full-window scrim panel (not a workspace tab), category headers inside one list, pixelated thumbnails in a fixed card size; cards carry a text badge (`valid` / `N blockers`) plus explicit Open/Review buttons.

## Layout

- Designer: Navigator | Canvas | Context Inspector, with a collapsible Problems/Diff/Logs drawer.
- Diff Review: side-by-side baseline/current with the changed-pixel bounds and element change lists; Device/Code switch in the header, evidence panel under the canvas.
- Pixel Studio: Tool Rail | Pixel Canvas | Flat Context Inspector, plus status/input hints.
- Font Lab: Glyph list | Canvas + on-screen preview | Generator form.
- Preferences: a separate flat dialog; global preferences never occupy the authoring header.

## Accent grammar

Blue/teal is semantic rather than decorative:

- block = primary action;
- rail = current interaction / selected tool;
- dot = changed/current state;
- corner = primary selected object;
- 1px outline = current spatial hover;
- anchor = active smart-guide snap confirmation.

A local surface should not accumulate multiple competing accent cues. The smallest sufficient cue wins.
