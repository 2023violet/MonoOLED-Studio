"""Deterministic built-in OLED bitmap font.

The default Font Lab experience must not depend on host font discovery.  This
module contains a deliberately simple, hand-authored 5x7 uppercase/digit font
with shapes optimized for recognition on monochrome OLED cells.
"""
from __future__ import annotations

DEFAULT_CHARACTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/'

BUILTIN_5X7: dict[str, tuple[str, ...]] = {
    'A': ('01110','10001','10001','11111','10001','10001','10001'),
    'B': ('11110','10001','10001','11110','10001','10001','11110'),
    'C': ('01110','10001','10000','10000','10000','10001','01110'),
    'D': ('11110','10001','10001','10001','10001','10001','11110'),
    'E': ('11111','10000','10000','11110','10000','10000','11111'),
    'F': ('11111','10000','10000','11110','10000','10000','10000'),
    'G': ('01110','10001','10000','10111','10001','10001','01110'),
    'H': ('10001','10001','10001','11111','10001','10001','10001'),
    'I': ('11111','00100','00100','00100','00100','00100','11111'),
    'J': ('00111','00010','00010','00010','00010','10010','01100'),
    'K': ('10001','10010','10100','11000','10100','10010','10001'),
    'L': ('10000','10000','10000','10000','10000','10000','11111'),
    'M': ('10001','11011','10101','10101','10001','10001','10001'),
    'N': ('10001','11001','10101','10011','10001','10001','10001'),
    'O': ('01110','10001','10001','10001','10001','10001','01110'),
    'P': ('11110','10001','10001','11110','10000','10000','10000'),
    'Q': ('01110','10001','10001','10001','10101','10010','01101'),
    'R': ('11110','10001','10001','11110','10100','10010','10001'),
    'S': ('01111','10000','10000','01110','00001','00001','11110'),
    'T': ('11111','00100','00100','00100','00100','00100','00100'),
    'U': ('10001','10001','10001','10001','10001','10001','01110'),
    'V': ('10001','10001','10001','10001','10001','01010','00100'),
    'W': ('10001','10001','10001','10101','10101','10101','01010'),
    'X': ('10001','01010','00100','00100','00100','01010','10001'),
    'Y': ('10001','01010','00100','00100','00100','00100','00100'),
    'Z': ('11111','00001','00010','00100','01000','10000','11111'),
    '0': ('01110','10001','10011','10101','11001','10001','01110'),
    '1': ('00100','01100','00100','00100','00100','00100','01110'),
    '2': ('01110','10001','00001','00010','00100','01000','11111'),
    '3': ('11110','00001','00001','01110','00001','00001','11110'),
    '4': ('00010','00110','01010','10010','11111','00010','00010'),
    '5': ('11111','10000','10000','11110','00001','00001','11110'),
    '6': ('01110','10000','10000','11110','10001','10001','01110'),
    '7': ('11111','00001','00010','00100','01000','01000','01000'),
    '8': ('01110','10001','10001','01110','10001','10001','01110'),
    '9': ('01110','10001','10001','01111','00001','00001','01110'),
    '/': ('00001','00010','00100','01000','10000','00000','00000'),
}


def recommended_baseline(cell: tuple[int, int]) -> int:
    """Return a shared baseline with one safety row below for normal cells."""
    width, height = map(int, cell)
    if width <= 0 or height <= 0:
        raise ValueError('font cell dimensions must be positive')
    return max(0, height - 2) if height > 1 else 0


def recommended_advance(cell: tuple[int, int]) -> int:
    """Keep one pixel of inter-glyph breathing room by default."""
    width, height = map(int, cell)
    if width <= 0 or height <= 0:
        raise ValueError('font cell dimensions must be positive')
    return width + 1


def supports_builtin_5x7(cell: tuple[int, int]) -> bool:
    width, height = map(int, cell)
    return width >= 5 and height >= 7


def builtin_glyph_rows(char: str, cell: tuple[int, int], *, baseline: int | None = None) -> list[list[int]]:
    """Render one canonical 5x7 glyph into ``cell`` using integer scaling.

    Glyphs share the supplied baseline.  The bitmap is never antialiased and
    therefore stays legible at native 5x7/5x8 sizes and crisp when enlarged.
    """
    if char not in BUILTIN_5X7:
        raise KeyError(char)
    width, height = map(int, cell)
    if not supports_builtin_5x7((width, height)):
        raise ValueError('built-in OLED 5x7 requires a cell of at least 5x7')
    resolved_baseline = recommended_baseline((width, height)) if baseline is None else int(baseline)
    if not 0 <= resolved_baseline < height:
        raise ValueError('font baseline must be inside cell height')

    max_scale_x = width // 5
    max_scale_y = (resolved_baseline + 1) // 7
    scale = max(1, min(max_scale_x, max_scale_y))
    glyph_w = 5 * scale
    glyph_h = 7 * scale
    x0 = max(0, (width - glyph_w) // 2)
    y0 = resolved_baseline - glyph_h + 1
    if y0 < 0:
        # A valid >=5x7 cell can always fit scale=1, but a very high custom
        # baseline may not. Align to the top instead of clipping the glyph.
        scale = 1
        glyph_w = 5
        glyph_h = 7
        x0 = max(0, (width - glyph_w) // 2)
        y0 = 0

    rows = [[0 for _ in range(width)] for __ in range(height)]
    pattern = BUILTIN_5X7[char]
    for sy, source_row in enumerate(pattern):
        for sx, value in enumerate(source_row):
            if value != '1':
                continue
            px = x0 + sx * scale
            py = y0 + sy * scale
            for dy in range(scale):
                yy = py + dy
                if not 0 <= yy < height:
                    continue
                for dx in range(scale):
                    xx = px + dx
                    if 0 <= xx < width:
                        rows[yy][xx] = 1
    return rows
