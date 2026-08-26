# MonoOLED Studio V9 — UI Design System

## Product language

MonoOLED Studio is a **professional editor**, not a Bento dashboard. Canvas remains the visual center. Inspector/settings surfaces use flat sections and thin separators; cards are reserved for genuinely summary-oriented surfaces.

## Interaction vocabulary

Every control must distinguish Normal, Hover, Pressed, Selected, Selected+Hover, Keyboard Focus and Disabled. State changes must not change control geometry. Mouse focus and keyboard focus are separate.

## Semantic color tokens

Components consume `app.background`, `surface.*`, `text.*`, `border.*`, `accent.*`, `status.*` and `canvas.*` tokens from `theme_system.py`; components must not invent local colors for ordinary states.

## Border Radius Systematic Scale (V9)

**Professional editor refinement** — consistent visual hierarchy:

| Element | Radius | Rationale |
|---------|--------|-----------|
| **Panels** (ProfessionalPanel, CanvasWorkspace, Popups, Lists) | **8px** | Primary containment surfaces |
| **Controls** (Buttons, Inputs, Tabs, List Items) | **6px** | Interactive elements — unified hierarchy |
| **Pills** (StatusPill badges) | **10px** | Deliberately rounded pill shape |
| **Menus** (Menu items, Scrollbar handles) | **5px** | Ephemeral transient surfaces |

**Implementation:** Tokens defined in `ui_metrics.py` (`radius_panel`, `radius_control`, `radius_pill`, `radius_menu`) and applied systematically in `qt_theme.py`.

**Removed:** Legacy unused METRICS values (`radius_large: 24`, `radius_medium: 20`, `radius_small: 16`) eliminated.

## Command Bar Visual Hierarchy (V9)

**Professional editor refinement** — semantic button roles without visual competition:

| Tier | Role | Buttons | Rationale |
|------|------|---------|-----------|
| **Primary** | Main document action | **Save** | Single primary CTA — most frequent critical action |
| **Secondary** | Workspace modes & delivery | Design, Pixel, Review, Project, Validate, Handoff | Supporting actions — equal weight within tier |
| **Ghost** | Utility & settings | Diagnostics, Settings, AI Agent | De-emphasized support tools |

**Key principles:**
- Only **one Primary button** visible at a time (Save)
- Workspace mode buttons (Design/Pixel/Review) use **consistent Secondary style** — no role swapping
- Enabled/disabled state indicates active mode, not role changes
- Delivery actions (Validate/Handoff) treated as secondary, not competing primary CTAs

## Density

Compact, Comfortable and Spacious alter control height/padding without changing information architecture.

## Workspace

Designer: Navigator | Canvas | Context Inspector, with a collapsible Problems/Diff/Logs drawer.

Pixel Studio: Tool Rail | Pixel Canvas | Flat Context Inspector, plus status/input hints.

Preferences: independent flat Settings window; global preferences never occupy the main authoring header.
