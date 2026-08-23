# MonoOLED Studio 8.0 — Verification Matrix

## Host/Core gates

- V7/V7.1 regression suite.
- SelectionModel order/Primary invariants.
- Selection bounds/gap metrics and Align-to Selection/Primary/Canvas.
- Pixel resize/anchor/rotation/crop/font insertion and Undo semantics.
- FontPack round-trip and deterministic raster generation.
- `bitmap_text` renderer compatibility without changing legacy `text`.
- Automation permissions, revision guard, transaction rollback and one-transaction/one-Designer-Undo.
- Render PNG/framebuffer/resolved-elements/pixel-diff surfaces.
- Real localhost JSON-RPC token rejection/acceptance.
- Project observation and atomic scene save.

## Windows Real-Qt gates

The Windows release workflow runs the Qt suites at:

```text
4 DPI scales
× 4 themes
× 2 languages
× 3 densities
× 3 production surfaces
= 288 production-surface constructions
```

DPI scales: 100%, 125%, 150%, 200%.

Surfaces: Designer, Pixel Workspace, Preferences.

V8-specific Real-Qt checks additionally cover:

- StudioSelect uses a frameless translucent Studio-owned popup.
- Pixel assets open inside the main document tab host and reuse an existing tab.
- Ctrl-click selection preserves order and Primary Selection.
- Marquee selects multiple Scene objects.
- Font Lab is embeddable, not a second top-level editor.
- Prior V7.1 production ToolRail raster/focus/pan/shortcut gates remain mandatory.

## Adversarial/stress gate

`Developer_Tools/VERIFY_V80_STRESS.py` performs:

- 464 frozen production-asset hash checks.
- 14 frozen Golden hash/size checks.
- 1,000 malformed Preferences payloads.
- 10,000 randomized SelectionModel transitions.
- 30,000 PixelDocument operations including resize/rotation/flip.
- deterministic FontPack generation.
- 1,000 JSON-RPC/automation calls.
- 1,400 Renderer frames across all 14 clinical states with deterministic SHA checks.

## Release truth wording

A non-Windows packaging host may claim Host/Core/Product Truth only. Windows Real-Qt and PyInstaller standalone are `UNVERIFIED` until executed on the Windows release gate. Prepared workflow/configuration is not a PASS result.
