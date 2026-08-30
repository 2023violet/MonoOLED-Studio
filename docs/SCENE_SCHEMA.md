# OLED Scene Schema v1 — MonoOLED Studio 5.0 usage

## Coordinate and framebuffer contract

- `(0,0)` is top-left; X increases right, Y increases down.
- Production coordinates are integer pixels.
- Bounding box is `[x,x+w) × [y,y+h)`.
- Canvas width is a positive integer.
- Canvas height is a positive **multiple of 8** for VLSB page storage.
- Framebuffer bytes are calculated as `width × (height / 8)`; 128×32 is 512B, 256×64 is 2048B.
- `1 = OLED lit`, `0 = background`.

## Portable project root

An external Scene may declare a project root relative to its JSON file:

```json
{
  "schema_version": 1,
  "project_root": "..",
  "canvas": {"w": 128, "h": 64, "preview_scale": 6}
}
```

Without `project_root`, an external Scene uses its own directory as the project root. Asset paths are resolved relative to that root. The built-in Curing-Lite Scene continues to use the bundled repository root.

## Canvas

```json
"canvas": {"w": 128, "h": 32, "preview_scale": 6},
"storage": {
  "layout": "VLSB column-page (SSD1306)",
  "bytes_per_frame": 512,
  "polarity": "1 = lit"
}
```

When Canvas size is changed through the editor, `bytes_per_frame` is updated automatically.

## Bitmap paths

Images already inside the project are stored as portable relative paths. When the user assigns an image located outside the project, the editor copies it into `<project_root>/assets/imported/` and stores that relative path.

## Element types

### image

```json
{
  "id": "mode_icon",
  "type": "image",
  "asset": "icons/{mode}.png",
  "x": 94, "y": 19, "w": 24, "h": 12,
  "visible_when": {"phase": "standby"},
  "resize_policy": "native_only"
}
```

### image_seq / digits / text

The existing `dir`, `pattern`, `bind`, `zone`, `tracking`, `font_header`, `visible_when` contracts are unchanged. Dynamic text/digits may expose authoring zones while rendered W/H are calculated from glyph content.

### placeholder

Placeholder is editor-only. It creates no production framebuffer pixels and is a `DRAFT_PLACEHOLDER` blocker until replaced by a real bitmap.

## Bitmap polarity

Strict binary assets are normalized in memory to OLED semantics. Opaque black-on-white assets are inverted in memory; white-on-black assets are preserved; transparent background is off. Source files are never rewritten.

## V8 bitmap_text / FontPack

V8 adds `bitmap_text` without changing the legacy `text` contract:

```json
{
  "id": "cycle_label",
  "type": "bitmap_text",
  "text": "2X",
  "font_pack": ".oled/fonts/clinical_small",
  "x": 22,
  "y": 22,
  "visible_when": {"mode": "ORTHO", "phase": "running"}
}
```

`font_pack` must resolve inside the project root and contain `fontpack.json` plus exact glyph PNGs. Render width is derived from per-glyph `advance` and cell geometry. Missing FontPack/glyphs are validation findings. Existing `text` elements keep their previous renderer semantics and are not migrated automatically.
