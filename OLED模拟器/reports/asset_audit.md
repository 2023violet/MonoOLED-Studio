# OLED Asset Polarity & Binary Audit

> Source files are never rewritten by this audit. `black_on_white` assets are inverted only in memory by the Canonical Renderer.

- Images scanned: **436**
- Opaque black-on-white (auto-normalized): **166**
- Opaque white-on-black: **241**
- Transparent binary: **26**
- Non-binary / invalid: **3**

## Non-binary / Invalid

- `Curing_Lite光固化机产品 - UI设计初稿/english_5x7_v2/clinical_14screens_v2_integration_4x.png` — Curing_Lite光固化机产品 - UI设计初稿/english_5x7_v2/clinical_14screens_v2_integration_4x.png: non-binary RGB (25, 25, 25) at (0, 128)
- `字库转PNG脚本/out_ttf/10x16_consola_sheet.png` — 字库转PNG脚本/out_ttf/10x16_consola_sheet.png: non-binary RGB (90, 90, 90) at (6, 6)
- `字库转PNG脚本/png_out/8x16_ascii_8x16_sheet.png` — 字库转PNG脚本/png_out/8x16_ascii_8x16_sheet.png: non-binary RGB (90, 90, 90) at (6, 6)

## Polarity Contract

- OLED production semantics are always `0 = background`, `1 = lit`.
- Fully opaque white-background / black-foreground assets are auto-inverted in memory.
- Transparent background is always off; opaque white is lit.
- Partial alpha and non-binary RGB are rejected for production bitmap loading.
- Review sheets may intentionally be non-binary; they are not production assets unless referenced by a Scene.
